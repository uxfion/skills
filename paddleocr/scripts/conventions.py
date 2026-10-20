"""The conventions of a kind of document: how it writes the things processing and checks look for. Today papers:
figure and table captions, panel letters, equation numbers. A convention applies only where a document writes
that way; a document that never does gets the generic processing, complete without it.

This is a table to extend, not a closed list: a journal that writes its captions another way gets its pattern
added here (references/papers.md says how)."""
from __future__ import annotations

import re

VERSION = 1              # bump when a convention changes, so stored parses are processed again

# A figure caption opens with its number: "Fig. 3", "Figure 2:", "Extended Data Fig. 1 |", "Supplementary Figure 4",
# "图 3". The VL model labels some captions text, which then need punctuation after the number: "Fig. 3 shows ..."
# opens running text.
FIGURE_WORD = r"(extended\s+data\s+|supplementary\s+)?(fig\.?|figure|图)"
CAPTION = re.compile(r"\s*(\*\*)?\s*" + FIGURE_WORD + r"\s*[A-Z]?\d", re.I)
CAPTION_TEXT = re.compile(r"\s*(\*\*)?\s*((extended\s+data\s+|supplementary\s+)?(fig\.?|figure)\s*[A-Z]?\d+[a-z]?\s*(\*\*)?\s*[.:|]"
                          r"|图\s*\d+)", re.I)
FIGURE_ID = re.compile(r"\s*(\*\*)?\s*" + FIGURE_WORD + r"\s*([A-Z]?\d+)", re.I)
# A table caption: "Table 2.", "TABLE IV", "Extended Data Table 1 |", "表 3".
TABLE_CAPTION = re.compile(r"\s*(\*\*)?\s*((extended\s+data\s+|supplementary\s+)?table\s*([A-Z]?\d+|[IVX]+\b)|表\s*\d+)", re.I)
# A caption line in a text layer, of a figure or a table.
CAPTION_LINE = re.compile(r"(?mi)^\s*(\*\*)?\s*(extended\s+data\s+|supplementary\s+)?(figure|fig\.|table)\s*([A-Z]?\d+)\s*(\*\*)?\s*[.:|]")
# A panel letter: "a", "(b)", "C.".
PANEL = re.compile(r"\(?[A-Za-z]{1,2}\)?[.:]?")
# An equation number: "(3)", also with full-width brackets as the model sometimes reads them ("（5）", 2026-10); in
# a formula, "\tag{3}" or "\tag*{(3)}".
EQUATION_NUMBER = re.compile(r"[(（](\d{1,3})[)）]")
TAG = re.compile(r"\\tag\*?\{[(（]?(\d{1,3})[)）]?\}")


def is_caption(b: dict) -> bool:
    """A figure caption, by the block's label and text."""
    t = b["text"].strip()
    if b["label"] == "figure_title":
        return bool(CAPTION.match(t))
    return b["label"] in ("text", "vision_footnote") and bool(CAPTION_TEXT.match(t))


def figure_id(b: dict) -> tuple[str, str]:
    """The figure a caption names: ("", "3") for "Fig. 3 |" and "Figure 3:", ("extended data", "3") for
    "Extended Data Fig. 3"."""
    m = FIGURE_ID.match(b["text"])
    return " ".join((m.group(2) or "").lower().split()), m.group(4).upper()


def figure_number(text: str) -> str:
    """The number as the caption writes it, for a figure's alt text: "Fig. 1", "Supplementary Figure 2", "图 3"."""
    m = FIGURE_ID.match(text)
    return " ".join(text[m.start(2) if m.group(2) else m.start(3):m.end()].split()) if m else ""


def is_panel(b: dict) -> bool:
    return b["label"] == "figure_title" and bool(PANEL.fullmatch(b["text"].strip()))


def is_table_caption(b: dict) -> bool:
    """A table caption, which the VL model labels figure_title more often than not (2026-10: 77 of 96)."""
    return b["label"] in ("figure_title", "table_title", "text", "vision_footnote") and bool(TABLE_CAPTION.match(b["text"].strip()))


def is_subtitle(b: dict) -> bool:
    """A title inside a figure, which the VL model labels figure_title too: "Step 1: ...", "(a) in silico"."""
    return b["label"] == "figure_title" and not is_caption(b) and not is_panel(b) and not is_table_caption(b)


def equation_numbers(b: dict) -> list[int]:
    """The equation numbers a block carries: a formula_number block's "(3)", a formula's \\tag."""
    if b["label"] == "formula_number":
        return [int(m) for m in EQUATION_NUMBER.findall(b["text"])]
    if b["label"] in ("display_formula", "formula"):
        return [int(m) for m in TAG.findall(b["text"])]
    return []
