"""
Deterministic cleanup for transcript CSV string fields.

Applies Unicode NFKC normalization, HTML entity decoding, and a fixed table of
common mojibake repairs (UTF-8 misread as Latin-1 / Windows-1252). Latin
letters with accents are preserved.

The main entry point for pipeline code is :func:`sanitize_transcript_row`.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Pattern

# Longest-first replacement for mojibake (UTF-8 read as Latin-1 / Windows-1252).
_MOJIBAKE_SEQUENCES: tuple[tuple[str, str], ...] = (
    ("‚Äô", "'"),  # right single quote
    ("‚Äú", '"'),
    ("‚Äù", '"'),
    ("‚Äî", "-"),  # em dash
    ("‚Äì", "-"),  # en dash
    ("‚Ä¶", "..."),
    ("Ã©", "é"),
    ("Ã¨", "è"),
    ("Ã¡", "á"),
    ("Ã³", "ó"),
    ("Ã±", "ñ"),
    ("Ã¼", "ü"),
    ("â€™", "'"),
    ("â€œ", '"'),
    ("â€", '"'),
    ("â€”", "-"),
    ("â€“", "-"),
    ("â€¦", "..."),
    ("\u00a0", " "),  # nbsp
    ("\ufeff", ""),  # BOM in text
    ("¬†", " "),  # mojibake nbsp seen in exports
)

# Control chars to remove (keep \n \t for multiline)
_CTRL_EXCEPT_NL_TAB = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _fix_mojibake(s: str) -> str:
    """
    Replace known mojibake byte sequences with their intended characters.

    Substitutions are applied in longest-first order via
    :data:`_MOJIBAKE_SEQUENCES`.

    Parameters
    ----------
    s : str
        Input text, possibly containing mis-decoded punctuation or spaces.

    Returns
    -------
    str
        Text with each known bad sequence replaced by its correction.
    """
    for bad, good in _MOJIBAKE_SEQUENCES:
        s = s.replace(bad, good)
    return s


def sanitize_field(s: str, *, multiline: bool = False) -> str:
    """
    Normalize a single string field for storage and display.

    Processing order: NFKC normalization, :func:`html.unescape`, mojibake
    repair (:func:`_fix_mojibake`), removal of stray control characters
    (except tab and newline when ``multiline`` is True), then whitespace
    normalization.

    Parameters
    ----------
    s : str
        Raw field value. Empty strings are returned unchanged.
    multiline : bool, optional
        If False (default), collapse all runs of whitespace to single spaces
        and strip ends (suitable for one-line fields such as ``text``).

        If True, collapse spaces within each line, join non-empty lines with
        ``\\n\\n``, and collapse three or more newlines to two (paragraph
        breaks preserved for tagged dialog fields).

    Returns
    -------
    str
        Cleaned string, or ``""`` if ``s`` is empty.

    Notes
    -----
    Non-breaking space (U+00A0) and common mojibake forms of NBSP are mapped
    to an ordinary space before whitespace rules apply.
    """
    if not s:
        return ""
    t = unicodedata.normalize("NFKC", s)
    t = html.unescape(t)
    t = _fix_mojibake(t)
    t = _CTRL_EXCEPT_NL_TAB.sub("", t)
    if multiline:
        lines = []
        for line in t.splitlines():
            lines.append(" ".join(line.split()))
        t = "\n\n".join(lines)
        t = re.sub(r"\n{3,}", "\n\n", t)
    else:
        t = " ".join(t.split())
    return t.strip()


# Columns that contain dialog markup or long text (multiline sanitize).
_MULTILINE_KEYS = frozenset(
    {
        "prior_dialog",
        "prior_speaker_turn",
        "target_text",
        "speaker_and_target_text",
        "dialog_and_target_text",
        "tmp_thing",
        "multi_labels",
    }
)


def sanitize_transcript_row(row: dict[str, object]) -> dict[str, object]:
    """
    Sanitize all string values in a transcript CSV row.

    Returns a shallow copy: keys and non-string values are preserved; each
    non-empty string is passed through :func:`sanitize_field` with multiline
    mode chosen by column name.

    Parameters
    ----------
    row : dict[str, object]
        One row from a transcript export (e.g. ``dialog_id``, ``text``,
        ``prior_dialog``, ``prior_speaker_turn``, and related columns).

    Returns
    -------
    dict[str, object]
        New dict with the same keys as ``row``. String fields are replaced
        with sanitized strings; non-string and empty string values are
        unchanged.

    Notes
    -----
    **Multiline** (:func:`sanitize_field` with ``multiline=True``) is used for
    keys in :data:`_MULTILINE_KEYS` (dialog markup and long combined fields).

    The ``text`` column always uses **single-line** sanitization
    (``multiline=False``), even if it were added to ``_MULTILINE_KEYS``.

    Any other string key not listed above defaults to single-line
    sanitization.
    """
    out = dict(row)
    for k, v in list(out.items()):
        if not isinstance(v, str) or not v:
            continue
        if k == "text":
            out[k] = sanitize_field(v, multiline=False)
        elif k in _MULTILINE_KEYS:
            out[k] = sanitize_field(v, multiline=True)
        else:
            out[k] = sanitize_field(v, multiline=False)
    return out
