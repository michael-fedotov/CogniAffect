#!/usr/bin/env python3
"""
Fill scenarios JSON response B (cognitive empathy) and C (affective empathy) via OpenAI.

Joins each scenario to the source CSV by ``source_row_index`` → ``index``. Fills
``{{conversation_context}}`` with the same Client/Therapist transcript as the scenario JSON
``context`` field (via ``format_context`` on ``prior_dialog``), and ``{{last_client_utterance}}``
from ``prior_speaker_turn``.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DATASET_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _DATASET_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_DATASET_DIR) not in sys.path:
    sys.path.insert(0, str(_DATASET_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

from prompts import COGNITIVE_PROMPT, EMOTIONAL_PROMPT  
from export_scenarios_from_shortlist import format_context   

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[misc, assignment]

_OUTPUT_DIR = _DATASET_DIR / "outputs"

# Split filled prompts here: system = instructions; user = dialogue + task (matches prompts.py).
_CONV_MARKER = "DIALOGUE SO FAR"


def _word_count(s: str) -> int:
    """Count whitespace-delimited words in *s*."""
    t = (s or "").strip()
    if not t:
        return 0
    return len(t.split())


def _sentence_count(s: str) -> int:
    """Rough sentence count for length guidance (splits on . ! ?)."""
    t = (s or "").strip()
    if not t:
        return 0
    parts = [p for p in re.split(r"[.!?]+", t) if p.strip()]
    return max(1, len(parts))


def _human_baseline_text(scenario: dict[str, Any]) -> str:
    """Return response **A** text (human baseline) from a scenario dict."""
    for r in scenario.get("responses") or []:
        if r.get("response_id") == "A":
            return (r.get("text") or "").strip()
    return ""


def _length_guidance(
    human_text: str,
    *,
    min_ratio: float,
    max_ratio: float,
    disabled: bool,
) -> str:
    """Build the ``{{length_guidance}}`` paragraph from the human baseline (response A).

    Keeps LLM B/C in a similar word-count band to the human turn for fairer BWS annotation.
    """
    if disabled:
        return (
            "Length matching is disabled. Still avoid extremely long replies; prefer "
            "one short paragraph when possible unless the situation clearly requires more."
        )
    text = (human_text or "").strip()
    if (
        not text
        or "[LLM" in text
        or "replace with" in text.lower()
        or "— replace" in text
    ):
        return (
            "No usable human baseline length was found. Aim for about 2–4 sentences and "
            "roughly 40–100 words unless the client's situation clearly needs more "
            "(e.g. imminent safety concerns)."
        )
    words = _word_count(text)
    sents = _sentence_count(text)
    lo = max(12, int(round(words * min_ratio)))
    hi = max(lo + 8, int(round(words * max_ratio)))
    return (
        f"The reference human counselor reply for this same turn is about {words} word(s) "
        f"and roughly {sents} sentence(s). "
        f"Your reply should stay in a similar range: aim for about {lo}–{hi} words total. "
        f"Do not pad with filler. If the client expresses imminent danger to self or others, "
        f"you may briefly exceed this range to give appropriate safety or crisis guidance."
    )


def _strip_speaker_tags(s: str) -> str:
    """Remove XML speaker markup and normalize whitespace for ``CURRENT SPEAKER UTTERANCE``.

    Parameters
    ----------
    s : str
        Raw ``prior_speaker_turn`` from the CSV, often wrapped in ``<speaker>`` tags.

    Returns
    -------
    str
        Plain text with tags removed and internal whitespace collapsed to single spaces.
    """
    t = (s or "").replace("<speaker>", "").replace("</speaker>", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _fill_template(
    template: str,
    conversation_context: str,
    last_client_utterance: str,
    length_guidance: str,
) -> str:
    """Substitute template placeholders in ``prompts.py``.

    Parameters
    ----------
    template : str
        ``COGNITIVE_PROMPT`` or ``EMOTIONAL_PROMPT`` from ``prompts.py``.
    conversation_context : str
        Annotator-style transcript (``Client:`` / ``Therapist:``), same as scenario JSON
        ``context`` — typically ``format_context`` applied to CSV ``prior_dialog``.
    last_client_utterance : str
        Plain-text last client line before the target counselor reply (from
        ``_strip_speaker_tags`` on ``prior_speaker_turn``).
    length_guidance : str
        Human-baseline length instructions for ``{{length_guidance}}``.

    Returns
    -------
    str
        Fully expanded prompt text ready to split into chat messages.
    """
    return (
        template.replace("{{conversation_context}}", conversation_context)
        .replace("{{last_client_utterance}}", last_client_utterance)
        .replace("{{length_guidance}}", length_guidance)
    )


def _split_system_user(filled: str) -> tuple[str, str]:
    """Split a filled prompt at ``DIALOGUE SO FAR`` for OpenAI system/user messages.

    The **system** message is the instruction block (theory, constraints). The **user**
    message is everything from ``DIALOGUE SO FAR`` through ``TASK``, including the
    substituted transcript — that is how the headings are preserved for the model.

    Parameters
    ----------
    filled : str
        Output of ``_fill_template``, including a leading ``SYSTEM:`` block.

    Returns
    -------
    tuple[str, str]
        ``(system_content, user_content)`` where ``system_content`` has the ``SYSTEM:``
        prefix removed and ``user_content`` begins with ``DIALOGUE SO FAR``.

    Raises
    ------
    ValueError
        If ``DIALOGUE SO FAR`` is not present in ``filled``.
    """
    s = filled.strip()
    if _CONV_MARKER not in s:
        raise ValueError(f"Expected {_CONV_MARKER!r} in filled prompt")
    i = s.index(_CONV_MARKER)
    system_raw = s[:i].strip()
    user_raw = s[i:].strip()
    if system_raw.startswith("SYSTEM:"):
        system_raw = system_raw[7:].strip()
    return system_raw, user_raw


def _complete(
    client: Any, model: str, system: str, user: str, *, temperature: float
) -> str:
    """Run one chat completion and return the assistant message text.

    Parameters
    ----------
    client : Any
        ``openai.OpenAI`` instance.
    model : str
        Model id passed to ``chat.completions.create`` (e.g. ``gpt-5``).
    system : str
        System prompt (instructions, theoretical grounding, constraints).
    user : str
        User message (conversation history, current utterance, task).

    Returns
    -------
    str
        Stripped assistant ``content``, or an empty string if the API returns ``None``.
    """
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    content = resp.choices[0].message.content
    return (content or "").strip()


def _load_csv_index(csv_path: Path) -> dict[str, dict[str, str]]:
    """Load a CSV into a map from ``index`` to full row dicts.

    Parameters
    ----------
    csv_path : pathlib.Path
        Path to ``full_dataset_rows.csv`` (or any CSV with an ``index`` column).

    Returns
    -------
    dict[str, dict[str, str]]
        Keys are stripped ``index`` cell values; values are row dictionaries with
        BOM stripped from column names.
    """
    out: dict[str, dict[str, str]] = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row = {k.lstrip("\ufeff"): v for k, v in row.items()}
            idx = (row.get("index") or "").strip()
            if idx:
                out[idx] = row
    return out


def main() -> None:
    """CLI entry: fill response B (cognitive) and C (affective) for each scenario via OpenAI.

    Reads a scenarios JSON, joins each scenario to the source CSV by ``source_row_index``,
    calls the model twice per scenario (unless ``--dry-run``), updates ``responses`` for
    ids ``B`` and ``C``, refreshes ``import_timestamp``, and writes ``--output``.

    Raises
    ------
    SystemExit
        If the OpenAI SDK is missing, ``OPENAI_API_KEY`` is unset, the input has no
        scenarios, any ``source_row_index`` is missing from the CSV, or an API call fails.
    """
    ap = argparse.ArgumentParser(
        description="Fill LLM cognitive (B) and affective (C) responses using OpenAI."
    )
    ap.add_argument(
        "--input",
        type=Path,
        default=_OUTPUT_DIR / "scenarios_transcript_set.json",
        help="Scenarios JSON with B/C placeholders.",
    )
    ap.add_argument(
        "--csv",
        type=Path,
        default=_DATASET_DIR / "full_dataset_rows.csv",
        help="Source CSV with index, prior_dialog, prior_speaker_turn.",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=_OUTPUT_DIR / "scenarios_transcript_set_with_llm_candidates.json",
        help="Written scenarios JSON with B/C filled.",
    )
    ap.add_argument("--model", type=str, default="gpt-5", help="OpenAI chat model id.")
    ap.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Sampling temperature for chat completions.",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="Seconds between API calls (rate limiting).",
    )
    ap.add_argument(
        "--no-length-match",
        action="store_true",
        help="Do not tie B/C length to human baseline (response A); weaker fairness vs A.",
    )
    ap.add_argument(
        "--length-min-ratio",
        type=float,
        default=0.72,
        help="Lower bound for target word count as a fraction of human baseline words.",
    )
    ap.add_argument(
        "--length-max-ratio",
        type=float,
        default=1.38,
        help="Upper bound for target word count as a fraction of human baseline words.",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Log a snippet of each generated B/C to stdout.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Process only the first scenario and print B/C to stderr; still writes output.",
    )
    args = ap.parse_args()

    if not (0 < args.length_min_ratio <= args.length_max_ratio):
        raise SystemExit(
            "Require 0 < --length-min-ratio <= --length-max-ratio "
            f"(got min={args.length_min_ratio}, max={args.length_max_ratio})"
        )

    if OpenAI is None:
        raise SystemExit("Install the OpenAI SDK: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit(
            "Set OPENAI_API_KEY (e.g. export OPENAI_API_KEY=sk-...) or add it to "
            f"{_PROJECT_ROOT / '.env'} as OPENAI_API_KEY=..."
        )

    index_map = _load_csv_index(args.csv)
    raw = json.loads(args.input.read_text(encoding="utf-8"))
    scenarios: list[dict[str, Any]] = raw.get("scenarios") or []
    if not scenarios:
        raise SystemExit("No scenarios in input JSON")

    client = OpenAI(api_key=api_key)
    out_data = copy.deepcopy(raw)
    out_scenarios = out_data["scenarios"]

    missing: list[str] = []
    for sc in scenarios:
        sid = sc.get("scenario_id", "")
        idx = str(sc.get("source_row_index") or "").strip()
        if idx not in index_map:
            missing.append(f"{sid} (source_row_index={idx!r})")

    if missing:
        raise SystemExit(
            "Missing CSV rows for source_row_index:\n  "
            + "\n  ".join(missing)
            + f"\n(CSV: {args.csv})"
        )

    n = 1 if args.dry_run else len(scenarios)
    for i in range(n):
        sc = out_scenarios[i]
        sid = sc.get("scenario_id", "")
        idx = str(sc.get("source_row_index") or "").strip()
        row = index_map[idx]
        prior_dialog_raw = (row.get("prior_dialog") or "").strip()
        conversation_context = format_context(prior_dialog_raw)
        ps = (row.get("prior_speaker_turn") or "").strip()
        last_client = _strip_speaker_tags(ps)

        human_a = _human_baseline_text(sc)
        lg = _length_guidance(
            human_a,
            min_ratio=args.length_min_ratio,
            max_ratio=args.length_max_ratio,
            disabled=args.no_length_match,
        )

        cog_filled = _fill_template(
            COGNITIVE_PROMPT, conversation_context, last_client, lg
        )
        emo_filled = _fill_template(
            EMOTIONAL_PROMPT, conversation_context, last_client, lg
        )
        sys_c, usr_c = _split_system_user(cog_filled)
        sys_e, usr_e = _split_system_user(emo_filled)

        try:
            b_text = _complete(
                client,
                args.model,
                sys_c,
                usr_c,
                temperature=args.temperature,
            )
            time.sleep(args.sleep)
            c_text = _complete(
                client,
                args.model,
                sys_e,
                usr_e,
                temperature=args.temperature,
            )
        except Exception as e:
            raise SystemExit(f"{sid}: OpenAI API error: {e}") from e

        if args.verbose:
            print(f"{sid} B (tail): {b_text[-200:]!r}", flush=True)
            print(f"{sid} C (tail): {c_text[-200:]!r}", flush=True)

        for resp in sc.get("responses") or []:
            rid = resp.get("response_id")
            if rid == "B":
                resp["text"] = b_text
            elif rid == "C":
                resp["text"] = c_text

        if args.dry_run:
            print(f"[dry-run] {sid} B: {b_text[:200]!r}...", file=sys.stderr)
            print(f"[dry-run] {sid} C: {c_text[:200]!r}...", file=sys.stderr)
            break

        time.sleep(args.sleep)

    out_data["import_timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(out_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output} ({len(out_scenarios)} scenarios)")


if __name__ == "__main__":
    main()
