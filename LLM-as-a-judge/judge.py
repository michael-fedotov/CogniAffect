#!/usr/bin/env python3
"""
LLM-as-a-Judge: annotate scenarios with cognitive / affective BWS choices via OpenAI API.
Output CSV matches server.py CSV_COLUMNS (app export format).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

# Match server.py export columns exactly
CSV_COLUMNS = [
    "annotation_id",
    "annotator_id",
    "scenario_id",
    "context_snippet",
    "response_a_label",
    "response_b_label",
    "response_c_label",
    "cognitive_most",
    "cognitive_least",
    "cognitive_reasoning",
    "affective_most",
    "affective_least",
    "affective_reasoning",
    "timestamp",
    "session_duration_seconds",
]

JUDGE_SYSTEM_PROMPT = """You are participating in a study where you evaluate counselor responses to a therapy dialogue (Best-Worst Scaling). You will receive the conversation CONTEXT and three possible next responses labeled A, B, and C.

For each of two questions, pick which response does this MOST and which does it LEAST.

Question 1 -- Cognitive Empathy: Understanding the client's perspective and situation.
A response shows strong cognitive empathy when it demonstrates that the counselor genuinely grasps what the client is going through: their situation, their point of view, what matters to them, or the dilemma they face. It is not enough to name an emotion; the response should show real understanding of the person's circumstances.

Question 2 -- Affective Empathy: Validating the client's emotional experience.
A response shows strong affective empathy when it makes the client feel heard and emotionally supported: acknowledging their feelings with warmth, care, or concern. The response conveys that the counselor genuinely cares, not just that they intellectually understand.

Important guidelines:
- Judge as a thoughtful human reader, not as a theorist. Base judgments only on the text provided.
- A response that sounds natural and genuine may be more empathetic than one that uses heavy therapeutic language or emotional vocabulary. Do not favor a response simply because it uses more explicit emotion words or clinical phrasing.
- Consider how the client would actually feel receiving each response.
- For each question, MOST and LEAST must be two different letters from A, B, or C.
- Provide brief reasoning for each dimension (one or two sentences each).

Respond with a single JSON object only (no markdown fences). Use exactly these keys:
"cognitive_most", "cognitive_least", "cognitive_reasoning", "affective_most", "affective_least", "affective_reasoning"
Each *_most and *_least value must be the single character A, B, or C."""

JSON_INSTRUCTION = """Return JSON only with keys: cognitive_most, cognitive_least, cognitive_reasoning, affective_most, affective_least, affective_reasoning. Values for *_most and *_least must be A, B, or C."""


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _short_hash(text: str, n: int = 12) -> str:
    """Hex prefix of SHA-256 for debugging (verify inputs differ per scenario)."""
    h = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    return h[:n]


def _default_scenarios_path() -> Path:
    """Preferred default: repo-root gp5-generated-responses.json (see project docs)."""
    return _project_root() / "gp5-generated-responses.json"


def _default_annotator_id(model: str) -> str:
    # e.g. gpt-5.2 -> GPT-5.2
    return model.upper() if model else "LLM-JUDGE"


def _sanitize_filename_part(s: str) -> str:
    return re.sub(r"[^\w\-]+", "_", s)


def _snippet(text: str, max_len: int = 100) -> str:
    t = (text or "").replace("\n", " ").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def _load_scenarios(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "scenarios" not in data:
        raise ValueError("JSON must contain a top-level 'scenarios' array")
    return data


def _response_by_id(scenario: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in scenario.get("responses", []):
        rid = (r.get("response_id") or "").strip().upper()
        out[rid] = (r.get("text") or "").strip()
    return out


def _labels_from_ground_truth(scenario: dict[str, Any]) -> tuple[str, str, str]:
    gt = scenario.get("ground_truth_labels") or {}
    return (
        str(gt.get("A", "") or ""),
        str(gt.get("B", "") or ""),
        str(gt.get("C", "") or ""),
    )


def _build_user_message(context: str, texts: dict[str, str]) -> str:
    parts = [
        "## CONTEXT",
        context.strip(),
        "",
        "## RESPONSE A",
        texts.get("A", ""),
        "",
        "## RESPONSE B",
        texts.get("B", ""),
        "",
        "## RESPONSE C",
        texts.get("C", ""),
        "",
        JSON_INSTRUCTION,
    ]
    return "\n".join(parts)


def _normalize_letter(x: Any) -> str | None:
    if x is None:
        return None
    s = str(x).strip().upper()
    if len(s) == 1 and s in "ABC":
        return s
    # tolerate "Response A" etc.
    m = re.search(r"\b([ABC])\b", s)
    return m.group(1) if m else None


def _validate_judge(obj: dict[str, Any]) -> tuple[bool, str]:
    cm = _normalize_letter(obj.get("cognitive_most"))
    cl = _normalize_letter(obj.get("cognitive_least"))
    am = _normalize_letter(obj.get("affective_most"))
    al = _normalize_letter(obj.get("affective_least"))
    if not all([cm, cl, am, al]):
        return False, "Missing or invalid A/B/C letter in most/least fields"
    if cm == cl:
        return False, "cognitive_most and cognitive_least must differ"
    if am == al:
        return False, "affective_most and affective_least must differ"
    return True, ""


def _call_judge(
    client: OpenAI,
    model: str,
    user_message: str,
    max_retries: int = 4,
) -> tuple[dict[str, Any], float, str]:
    """Returns (parsed_json, elapsed_seconds, last_raw_assistant_text)."""
    last_err = ""
    last_raw = ""
    for attempt in range(max_retries):
        t0 = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
            )
            elapsed = time.perf_counter() - t0
            raw = (resp.choices[0].message.content or "").strip()
            last_raw = raw
            data = json.loads(raw)
            ok, err = _validate_judge(data)
            if ok:
                return data, elapsed, raw
            last_err = err
        except Exception as e:
            elapsed = time.perf_counter() - t0
            last_err = str(e)
            # brief backoff
            time.sleep(min(2**attempt, 8))
            continue
        time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(
        f"Judge failed after {max_retries} attempts: {last_err}"
        + (f"\nLast raw model output:\n{last_raw}" if last_raw else "")
    )


def _print_api_io(sid: str, user_message: str, raw_response: str) -> None:
    """Print full prompts and model output to stderr (for inspection)."""
    sep = "=" * 72
    print(f"\n{sep}\n[show-api] {sid} — SYSTEM MESSAGE\n{sep}", file=sys.stderr)
    print(JUDGE_SYSTEM_PROMPT, file=sys.stderr)
    print(f"\n{sep}\n[show-api] {sid} — USER MESSAGE\n{sep}", file=sys.stderr)
    print(user_message, file=sys.stderr)
    print(f"\n{sep}\n[show-api] {sid} — MODEL RESPONSE (raw)\n{sep}", file=sys.stderr)
    print(raw_response, file=sys.stderr)
    print(f"{sep}\n", file=sys.stderr)


def main() -> int:
    load_dotenv(_project_root() / ".env")

    parser = argparse.ArgumentParser(description="LLM-as-a-Judge BWS annotation to CSV")
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=None,
        help="Path to scenarios JSON (with scenarios[].context, responses, ground_truth_labels). "
        "Default: <repo>/gp5-generated-responses.json, else ./scenarios.json in CWD.",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.4",
        help="OpenAI chat model name (default: gpt-5.4)",
    )
    parser.add_argument(
        "--annotator-id",
        default=None,
        help="Annotator ID for CSV (default: derived from --model, e.g. GPT-5.2)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for CSV output (default: LLM-as-a-Judge/output next to this script)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N scenarios (for testing)",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress debug logging (fingerprints, per-scenario details, summary counts).",
    )
    parser.add_argument(
        "--show-api",
        action="store_true",
        help="Print full system prompt, user message, and raw model JSON to stderr for each scenario.",
    )
    args = parser.parse_args()

    debug = not args.quiet

    scenarios_path = args.scenarios
    if scenarios_path is None:
        preferred = _default_scenarios_path()
        cwd_default = Path.cwd() / "scenarios.json"
        if preferred.is_file():
            scenarios_path = preferred
        elif cwd_default.is_file():
            scenarios_path = cwd_default
        else:
            print(
                "Error: No --scenarios path given and no default file found.\n"
                f"  Tried: {preferred}\n"
                f"  Tried: {cwd_default}\n"
                "Pass --scenarios /path/to/scenarios.json",
                file=sys.stderr,
            )
            return 1

    scenarios_path = scenarios_path.resolve()
    if not scenarios_path.is_file():
        print(f"Error: scenarios file not found: {scenarios_path}", file=sys.stderr)
        return 1

    out_dir = args.output_dir
    if out_dir is None:
        out_dir = Path(__file__).resolve().parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    annotator_id = args.annotator_id or _default_annotator_id(args.model)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_ann = _sanitize_filename_part(annotator_id)
    out_csv = out_dir / f"llm_judge_{safe_ann}_{ts}.csv"

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY is not set (use .env or environment).", file=sys.stderr)
        return 1

    client = OpenAI(api_key=api_key)
    data = _load_scenarios(scenarios_path)
    scenarios: list[dict[str, Any]] = data["scenarios"]
    if args.limit is not None:
        scenarios = scenarios[: args.limit]

    file_size = scenarios_path.stat().st_size
    print(f"Scenarios file: {scenarios_path}")
    print(f"Output CSV: {out_csv}")
    print(f"Model: {args.model} | annotator_id: {annotator_id}")
    print(f"Total scenarios: {len(scenarios)}")
    if debug:
        print(
            f"[debug] project_root={_project_root()}",
            f"json_bytes={file_size}",
            f"json_top_keys={list(data.keys())}",
            sep="\n",
            file=sys.stderr,
        )

    choice_keys: list[str] = []

    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        f.flush()

        for i, scenario in enumerate(scenarios, start=1):
            sid = str(scenario.get("scenario_id") or f"SCENARIO_{i:02d}")
            print(f"Processing {i}/{len(scenarios)} {sid} ...", flush=True)

            context = str(scenario.get("context") or "")
            texts = _response_by_id(scenario)
            la, lb, lc = _labels_from_ground_truth(scenario)
            user_msg = _build_user_message(context, texts)

            if debug:
                print(
                    f"[debug] {sid} prompt_chars={len(user_msg)} "
                    f"hash_ctx={_short_hash(context)} "
                    f"hash_A={_short_hash(texts.get('A', ''))} "
                    f"hash_B={_short_hash(texts.get('B', ''))} "
                    f"hash_C={_short_hash(texts.get('C', ''))}",
                    file=sys.stderr,
                )
                print(
                    f"[debug] {sid} labels CSV: A={la!r} B={lb!r} C={lc!r} "
                    "(labels are NOT sent to the API; CSV only)",
                    file=sys.stderr,
                )

            try:
                judged, elapsed, raw_response = _call_judge(client, args.model, user_msg)
            except RuntimeError as e:
                print(f"  FAILED: {e}", file=sys.stderr)
                return 1

            if args.show_api:
                _print_api_io(sid, user_msg, raw_response)

            cm = _normalize_letter(judged["cognitive_most"])
            cl = _normalize_letter(judged["cognitive_least"])
            am = _normalize_letter(judged["affective_most"])
            al = _normalize_letter(judged["affective_least"])
            cr = str(judged.get("cognitive_reasoning") or "").strip()
            ar = str(judged.get("affective_reasoning") or "").strip()

            ts_iso = datetime.now(timezone.utc).isoformat()
            row = {
                "annotation_id": f"{annotator_id}-{sid}",
                "annotator_id": annotator_id,
                "scenario_id": sid,
                "context_snippet": _snippet(context),
                "response_a_label": la,
                "response_b_label": lb,
                "response_c_label": lc,
                "cognitive_most": cm,
                "cognitive_least": cl,
                "cognitive_reasoning": cr,
                "affective_most": am,
                "affective_least": al,
                "affective_reasoning": ar,
                "timestamp": ts_iso,
                "session_duration_seconds": f"{elapsed:.6f}",
            }
            writer.writerow(row)
            f.flush()

            choice_keys.append(f"cog:{cm}{cl}_aff:{am}{al}")
            if debug:
                print(
                    f"[debug] {sid} judge -> "
                    f"cognitive most={cm} least={cl} | affective most={am} least={al} | "
                    f"api_s={elapsed:.3f}",
                    file=sys.stderr,
                )

    print(f"\nDone. Wrote {len(scenarios)} rows to {out_csv}")
    if debug and choice_keys:
        c = Counter(choice_keys)
        print(
            "[debug] BWS pattern counts (cognitive most/least, affective most/least):",
            file=sys.stderr,
        )
        for pattern, count in c.most_common():
            print(f"  {count}x  {pattern}", file=sys.stderr)
        if len(c) == 1 and len(choice_keys) > 1:
            print(
                "[debug] NOTE: Every row used the same BWS letters. "
                "If hashes above differ per scenario, inputs are not duplicated — "
                "the model may be responding consistently to stimulus design (B/Cognitive, C/Affective).",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
