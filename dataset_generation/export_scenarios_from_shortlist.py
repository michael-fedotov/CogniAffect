#!/usr/bin/env python3
"""
Build scenarios_transcript_set.json from transcript_set.csv for the BWS app.

Context is prior_dialog with <speaker>/<listener> tags replaced by Client/Therapist labels.
Response A = human (CSV text); B/C = placeholders until LLM generation fills them in.

Usage:
  1. cd dataset_generation
  2.1 python export_scenarios_from_shortlist.py OR
  2.2 python export_scenarios_from_shortlist.py --input outputs/transcript_set.csv --output outputs/scenarios_transcript_set.json

Defaults: reads `outputs/transcript_set.csv`, writes `outputs/scenarios_transcript_set.json`.
"""  

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_DATASET_DIR = Path(__file__).resolve().parent
if str(_DATASET_DIR) not in sys.path:
    sys.path.insert(0, str(_DATASET_DIR))

from text_sanitize import sanitize_transcript_row 

_OUTPUT_DIR = _DATASET_DIR / "outputs"


def format_context(prior_dialog: str) -> str:
    """
    Convert tagged dialog context into plain text for annotators.

    Replaces ``<speaker>`` / ``</speaker>`` with ``Client:`` and line breaks,
    ``<listener>`` / ``</listener>`` with ``Therapist:`` and line breaks,
    then collapses excessive blank lines.

    Parameters
    ----------
    prior_dialog : str
        Value of the CSV ``prior_dialog`` column (XML-style tags).

    Returns
    -------
    str
        Multi-line string suitable for the CogniAffect ``context`` field.
    """
    s = prior_dialog or ""
    s = s.replace("<speaker>", "Client: ").replace("</speaker>", "\n\n")
    s = s.replace("<listener>", "Therapist: ").replace("</listener>", "\n\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def main() -> None:
    """
    Command-line entry point: shortlist CSV to scenarios JSON.

    Reads each row of the shortlist, builds ``SCENARIO_XX`` entries with human
    response A and placeholder B/C for LLM-generated cognitive and affective
    replies, and writes wrapped JSON including ``import_timestamp`` and
    ``source_csv``.

    Returns
    -------
    None
        Writes ``--output`` (default under ``outputs/``) and prints a summary line.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=_OUTPUT_DIR / "transcript_set.csv")
    ap.add_argument("--output", type=Path, default=_OUTPUT_DIR / "scenarios_transcript_set.json")
    args = ap.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    with args.input.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({k.lstrip("\ufeff"): v for k, v in row.items()})

    rows = [sanitize_transcript_row(dict(r)) for r in rows]

    scenarios = []
    for i, row in enumerate(rows, start=1):
        sid = f"SCENARIO_{i:02d}"
        pd = row.get("prior_dialog") or ""
        scenarios.append(
            {
                "scenario_id": sid,
                "source_dialog_id": row.get("dialog_id", ""),
                "source_row_index": row.get("index", ""),
                "turn": row.get("turn", ""),
                "final_agreed_label": row.get("final_agreed_label", ""),
                "context": format_context(pd),
                "responses": [
                    {
                        "response_id": "A",
                        "text": (row.get("text") or "").strip(),
                    },
                    {
                        "response_id": "B",
                        "text": "[LLM Cognitive empathy — replace with generated response]",
                    },
                    {
                        "response_id": "C",
                        "text": "[LLM Affective empathy — replace with generated response]",
                    },
                ],
                "ground_truth_labels": {
                    "A": "HUMAN",
                    "B": "LLM_COGNITIVE",
                    "C": "LLM_AFFECTIVE",
                },
            }
        )

    out = {
        "annotator_id": None,
        "import_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_csv": str(args.input.as_posix()),
        "scenarios": scenarios,
    }

    args.output.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output} ({len(scenarios)} scenarios)")


if __name__ == "__main__":
    main()
