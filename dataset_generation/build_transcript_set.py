#!/usr/bin/env python3
"""
Build a 64-conversation shortlist from all_rows.csv for BWS annotation.

- One row per dialog_id: row with maximum `turn` (tie-break: later row in file order).
- Quality filters on prior_dialog, prior_speaker_turn, and final listener text.
- Stratified random sample (64) by source bucket: counsel_chat vs RED.
- Writes `outputs/transcript_set.csv` and `outputs/transcript_set_build.log` (folder created if missing).

Usage:
  1. cd dataset_generation
  2.1 python build_transcript_set.py OR
  2.2 python build_transcript_set.py --input outputs/shortlist.csv --output outputs/transcript_set.csv

Defaults: input `outputs/shortlist.csv`; outputs `outputs/transcript_set.csv`.
"""

from __future__ import annotations

import argparse
import csv
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

_DATASET_DIR = Path(__file__).resolve().parent
_OUTPUT_DIR = _DATASET_DIR / "outputs"


def strip_xml_for_len(s: str) -> str:
    """
    Strip XML-like tags and normalize whitespace for measuring text length.

    Used when applying minimum-length filters to ``prior_dialog`` and
    ``prior_speaker_turn`` without counting markup.

    Parameters
    ----------
    s : str
        Raw field text, possibly containing ``<tag>`` fragments.

    Returns
    -------
    str
        Text with tags removed and runs of whitespace collapsed to single spaces.
    """
    if not s:
        return ""
    t = re.sub(r"<[^>]+>", " ", s)
    return " ".join(t.split())


def load_rows(path: Path) -> list[dict[str, Any]]:
    """
    Read a CSV file into a list of row dictionaries.

    Opens with UTF-8 and a BOM-safe encoding so Excel-exported files parse
    correctly; normalizes dict keys by stripping a leading BOM from the first
    column name when present.

    Parameters
    ----------
    path : pathlib.Path
        Path to the CSV file.

    Returns
    -------
    list of dict
        One dict per data row; keys match the file's column headers.
    """
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean = {k.lstrip("\ufeff") if k else k: v for k, v in row.items()}
            rows.append(clean)
    return rows


def collapse_final_turn(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Reduce multiple CSV rows per conversation to a single "final listener" row.

    For each ``dialog_id``, keeps the row with the largest ``turn`` value; if
    several rows share the same turn, keeps the one that appears later in
    ``rows`` (higher file index).

    Parameters
    ----------
    rows : list of dict
        All rows from the export, including multiple listener turns per dialog.

    Returns
    -------
    chosen : list of dict
        One row per distinct ``dialog_id`` (the selected final turn).
    log : list of str
        Debug lines for dialogs where more than one row was collapsed; empty
        when each dialog had only one row.
    """
    by_id: dict[str, list[tuple[int, int, dict[str, Any]]]] = defaultdict(list)
    for i, row in enumerate(rows):
        did = (row.get("dialog_id") or "").strip()
        try:
            t = int(row.get("turn") or 0)
        except (TypeError, ValueError):
            t = 0
        by_id[did].append((t, i, row))

    chosen: list[dict[str, Any]] = []
    log: list[str] = []
    for did, lst in sorted(by_id.items(), key=lambda x: x[0]):
        best = max(lst, key=lambda x: (x[0], x[1]))
        chosen.append(best[2])
        if len(lst) > 1:
            log.append(f"dialog {did!r}: collapsed {len(lst)} rows -> turn={best[0]} (index {best[1]})")
    return chosen, log


def mi_ok(row: dict[str, Any]) -> bool:
    """
    Check whether the row is flagged as motivational-interviewing adherent.

    Parameters
    ----------
    row : dict
        A CSV row; expects an ``mi_adherent`` field.

    Returns
    -------
    bool
        True if ``mi_adherent`` is one of 1, 1.0, true, True (string or numeric).
    """
    v = row.get("mi_adherent", "")
    return str(v).strip() in ("1", "1.0", "true", "True")


def passes_quality(
    row: dict[str, Any],
    min_prior_dialog: int,
    min_prior_speaker: int,
    min_text: int,
) -> tuple[bool, str]:
    """
    Apply minimum-length filters and drop trivial listener replies.

    Compares lengths after stripping XML-like tags from context fields.
    Rejects very short closings (e.g. "Take care.") when they have at most
    three words.

    Parameters
    ----------
    row : dict
        One collapsed CSV row (one per dialog).
    min_prior_dialog : int
        Minimum character length for stripped ``prior_dialog``.
    min_prior_speaker : int
        Minimum character length for stripped ``prior_speaker_turn``.
    min_text : int
        Minimum character length for the listener reply in ``text``.

    Returns
    -------
    ok : bool
        True if the row should be kept in the eligible pool.
    reason : str
        Empty when ``ok`` is True; otherwise a short machine-readable reason
        (e.g. ``prior_dialog too short (...)``).
    """
    if not mi_ok(row):
        return False, "mi_adherent!=1"

    pd = strip_xml_for_len(row.get("prior_dialog") or "")
    sp = strip_xml_for_len(row.get("prior_speaker_turn") or "")
    tx = (row.get("text") or "").strip()

    if len(pd) < min_prior_dialog:
        return False, f"prior_dialog too short ({len(pd)}<{min_prior_dialog})"
    if len(sp) < min_prior_speaker:
        return False, f"prior_speaker_turn too short ({len(sp)}<{min_prior_speaker})"
    if len(tx) < min_text:
        return False, f"text too short ({len(tx)}<{min_text})"

    short_closings = {
        "take care",
        "take care.",
        "thanks",
        "thanks.",
        "thank you",
        "thank you.",
        "ok",
        "ok.",
        "okay",
        "okay.",
    }
    key = tx.rstrip(".!?").lower()
    wc = len(tx.split())
    if wc <= 3 and key in short_closings:
        return False, "trivial closing"

    return True, ""


def source_bucket(dialog_id: str) -> str:
    """
    Map a ``dialog_id`` string to a coarse source stratum for stratified sampling.

    Parameters
    ----------
    dialog_id : str
        Dataset conversation identifier (e.g. contains ``counsel_chat`` or Reddit-style id).

    Returns
    -------
    str
        ``"counsel_chat"`` if the id is from the counsel-chat corpus; otherwise ``"RED"``.
    """
    return "counsel_chat" if "counsel_chat" in dialog_id else "RED"


def stratified_sample(
    rows: list[dict[str, Any]],
    n: int,
    seed: int,
) -> list[dict[str, Any]]:
    """
    Draw a random subset of size ``n`` with proportional counsel vs RED balance.

    Allocates counts by source bucket size, takes the first ``n_c`` / ``n_r``
    shuffled rows from each bucket, then fills any shortfall from the combined
    remainder. Shuffles the final list. Uses a fixed RNG seed for
    reproducibility.

    Parameters
    ----------
    rows : list of dict
        Eligible rows (typically one per dialog after filters).
    n : int
        Target sample size (e.g. 64).
    seed : int
        Seed for :class:`random.Random`.

    Returns
    -------
    list of dict
        Exactly ``n`` rows when ``len(rows) >= n`` and stratification succeeds.

    Raises
    ------
    SystemExit
        If fewer than ``n`` eligible rows exist, or the sample cannot be filled
        to size ``n`` after stratification.
    """
    rnd = random.Random(seed)
    counsel = [r for r in rows if source_bucket(r.get("dialog_id", "")) == "counsel_chat"]
    red = [r for r in rows if source_bucket(r.get("dialog_id", "")) == "RED"]
    total = len(rows)
    if total < n:
        raise SystemExit(f"Only {total} eligible rows; need at least {n}. Relax filters.")

    n_c = round(n * len(counsel) / total)
    n_r = n - n_c
    if n_c > len(counsel):
        n_r += n_c - len(counsel)
        n_c = len(counsel)
    if n_r > len(red):
        n_c += n_r - len(red)
        n_r = len(red)
    n_c = min(n_c, len(counsel))
    n_r = min(n_r, len(red))

    rnd.shuffle(counsel)
    rnd.shuffle(red)

    out = counsel[:n_c] + red[:n_r]
    remainder = counsel[n_c:] + red[n_r:]
    rnd.shuffle(remainder)
    while len(out) < n and remainder:
        out.append(remainder.pop())
    if len(out) < n:
        raise SystemExit(f"Could not sample {n}; only {len(out)} after stratification.")
    out = out[:n]
    rnd.shuffle(out)
    return out


def main() -> None:
    """
    Command-line entry point for building the shortlist CSV and build log.

    Parses arguments (see ``--help``), loads the input CSV, collapses to one
    row per dialog, filters by quality thresholds, stratified-samples to
    ``--n`` rows, writes the shortlist CSV and a text log of exclusions and
    collapse metadata.

    Returns
    -------
    None
        Writes files under ``outputs/`` and prints paths to stdout.
    """
    ap = argparse.ArgumentParser(description="Build 64-conversation BWS shortlist CSV.")
    ap.add_argument("--input", type=Path, default=_DATASET_DIR / "all_rows.csv")
    ap.add_argument("--output", type=Path, default=_OUTPUT_DIR / "transcript_set.csv")
    ap.add_argument("--log", type=Path, default=_OUTPUT_DIR / "transcript_set_build.log")
    ap.add_argument("--n", type=int, default=64)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min-prior-dialog", type=int, default=100)
    ap.add_argument("--min-prior-speaker", type=int, default=50)
    ap.add_argument("--min-text", type=int, default=25)
    args = ap.parse_args()

    rows = load_rows(args.input)
    collapsed, collapse_log = collapse_final_turn(rows)

    eligible: list[dict[str, Any]] = []
    excluded: list[tuple[str, str]] = []
    for row in collapsed:
        ok, reason = passes_quality(
            row,
            args.min_prior_dialog,
            args.min_prior_speaker,
            args.min_text,
        )
        if ok:
            eligible.append(row)
        else:
            excluded.append((row.get("dialog_id", ""), reason))

    sampled = stratified_sample(eligible, args.n, args.seed)

    fieldnames = list(sampled[0].keys()) if sampled else []

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in sampled:
            w.writerow(row)

    counsel_n = sum(1 for r in sampled if source_bucket(r.get("dialog_id", "")) == "counsel_chat")
    red_n = len(sampled) - counsel_n

    log_lines = [
        f"input: {args.input.resolve()}",
        f"raw rows: {len(rows)}",
        f"unique dialogs (collapsed): {len(collapsed)}",
        f"eligible after quality filters: {len(eligible)}",
        f"excluded: {len(excluded)}",
        f"sampled n={args.n} (seed={args.seed})",
        f"  counsel_chat: {counsel_n}, RED: {red_n}",
        f"output: {args.output.resolve()}",
        "",
        "=== Collapse (multi-row dialogs) ===",
        *collapse_log[:200],
        (f"... ({len(collapse_log) - 200} more)" if len(collapse_log) > 200 else ""),
        "",
        "=== Excluded after collapse (reason) ===",
    ]
    for did, reason in excluded[:300]:
        log_lines.append(f"{did}\t{reason}")
    if len(excluded) > 300:
        log_lines.append(f"... ({len(excluded) - 300} more exclusions)")

    args.log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} ({len(sampled)} rows)")
    print(f"Wrote {args.log}")


if __name__ == "__main__":
    main()
