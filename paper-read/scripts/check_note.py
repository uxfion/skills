#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Say whether a paper note's question tree is read through: the check before the note goes into Zotero.

  uv run scripts/check_note.py <scratch>/<cite>.<title>.note.md

The tree is the note's headings (references/reading.md): every question heading (## to ####) ends in
its status in brackets, [待答], [进行中], [已答], [论文没有说明], [要看别处] or [等 Qn] (a pointer after it, "→ Q4.1",
is allowed). A note is read through when no heading is still 待答, 进行中 or 等 Qn, every question heading
has a status, and the one-sentence summary — the first paragraph under the title, before the first
question — is written (not [待答]). Headings without a question number (## 用在哪里) are sections, not
questions, and carry no status. A front matter (the lines between two --- at the top) is skipped.

stdout: one JSON object {code, open: [{line, heading, status}], no_status: [{line, heading}], summary_written}.
  complete   read through: the note may be put into Zotero
  open       nodes still open, headings without a status, or no summary yet: go on reading
Exit 0 = complete; 1 = open; 2 = the file cannot be read.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CLOSED = ("已答", "论文没有说明", "要看别处")
OPEN = ("待答", "进行中")
WAITING = re.compile(r"等 ?Q\d+(?:\.\d+)*")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
QUESTION = re.compile(r"^Q\d+(?:\.\d+)*\b")
STATUS = re.compile(r"\[([^\[\]]+)\](?:[ \t]*→[ \t]*Q[\d.]+)?$")


def body(text):
    """The note without its front matter, as (first line number, lines)."""
    lines = text.split("\n")
    if lines and lines[0] == "---":
        end = next((i for i, line in enumerate(lines[1:], 1) if line == "---"), None)
        if end is not None:
            return end + 2, lines[end + 1:]
    return 1, lines


def check(text):
    start, lines = body(text)
    open_, no_status, summary, in_code = [], [], None, False
    seen_title, seen_question = False, False
    for n, line in enumerate(lines, start):
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = HEADING.match(line)
        if not m:
            if seen_title and not seen_question and summary is None and line.strip():
                summary = line.strip()
            continue
        level, text_ = len(m.group(1)), m.group(2)
        if level == 1:
            seen_title = True
            continue
        if not QUESTION.match(text_):
            continue
        seen_question = True
        s = STATUS.search(text_)
        if not s:
            no_status.append({"line": n, "heading": text_})
            continue
        status = s.group(1).strip()
        if status in OPEN or WAITING.fullmatch(status):
            open_.append({"line": n, "heading": text_, "status": status})
        elif status not in CLOSED:
            no_status.append({"line": n, "heading": text_})
    written = bool(summary) and summary != "[待答]"
    code = "complete" if not open_ and not no_status and written else "open"
    return {"code": code, "open": open_, "no_status": no_status, "summary_written": written}


def main(argv=None):
    first, _, rest = __doc__.strip().partition("\n")
    p = argparse.ArgumentParser(description=first, epilog=rest.strip(), formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("note", metavar="NOTE", help="the note file: <scratch>/<cite>.<title>.note.md")
    args = p.parse_args(argv)
    try:
        text = Path(args.note).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(json.dumps({"code": "unreadable", "path": args.note, "detail": str(e)}, ensure_ascii=False))
        return 2
    out = check(text)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["code"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
