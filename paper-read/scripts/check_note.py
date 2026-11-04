#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check a paper note's structure before it goes into Zotero: step 3 of every change to a note, with check_quotes.py.

  uv run scripts/check_note.py <scratch>/<package folder name>.note.md [--taken FILE] [--full]

The note's headings are its question tree (references/note-format.md): a question heading (## to ####) starts with
its number (Q3, Q3.1) and ends in its state in brackets, [已答], [论文没有说明], [要看别处], [待答], [进行中] or [等 Qn]
(a pointer after it, "→ Q4.1", is allowed). Headings without a number are sections and carry no state. A heading
that came back from Zotero as HTML, <h3>…</h3>, counts as a heading too.

Every change (default):
  - the note holds at least one question, and every question heading ends in a state, none of them 待答, 进行中
    or 等 Qn;
  - no question heading holds TeX ($…$): Zotero shows a heading as plain text, and TeX there does not come back
    from Zotero as a heading; a symbol goes in Unicode (ŷᵢ, fθ), the formula in the answer;
  - the 读的版本 paragraph is there; a summary paragraph before it, if any, is not [待答];
  - every question number in the note as taken (--taken, default <note>.taken when it exists) is still there.
A read-through (--full) also needs:
  - Q1 to Q8 all there;
  - the one-sentence summary written;
  - Q5 and Q6 each holding their fixed items, each opening with its bold word.

stdout: one JSON object {code, questions, open, no_state, math_in_heading, missing_numbers, version, summary_written,
missing_trunk?, missing_items?}; questions counts the question headings.
  complete   the note may be put into Zotero
  open       something above failed: go on
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
HTML_HEADING = re.compile(r"^<h([1-6])>(.*?)</h\1>[ \t]*$")
NUMBER = re.compile(r"^(Q\d+(?:\.\d+)*)\b")
STATE = re.compile(r"\[([^\[\]]+)\](?:[ \t]*→[ \t]*Q[\d.]+)?$")
VERSION = "读的版本："
ITEMS = {
    "Q5": ("数据和划分", "对比方法", "指标", "主要数字", "代码和数据"),
    "Q6": ("证据和范围", "提升从哪来", "统计", "前后矛盾", "假设和局限"),
}


def body(text):
    """The note without its front matter, as (first line number, lines)."""
    lines = text.split("\n")
    if lines and lines[0] == "---":
        end = next((i for i, line in enumerate(lines[1:], 1) if line == "---"), None)
        if end is not None:
            return end + 2, lines[end + 1:]
    return 1, lines


def parse(text):
    """Questions (line, number, heading, state), the paragraphs before the first question, and each trunk section."""
    start, lines = body(text)
    questions, preamble, sections = [], [], {}
    in_code, seen_question, current = False, False, None
    for n, line in enumerate(lines, start):
        if line.startswith("```"):
            in_code = not in_code
        if in_code or line.startswith("```"):
            if current:
                sections[current].append(line)
            continue
        m, h = HEADING.match(line), HTML_HEADING.match(line)
        if m or h:
            level, text_ = (len(m.group(1)), m.group(2)) if m else (int(h.group(1)), h.group(2).strip())
            num = NUMBER.match(text_)
            if level == 2:
                current = num.group(1) if num else None
                if current:
                    sections[current] = []
            if num:
                seen_question = True
                s = STATE.search(text_)
                questions.append((n, num.group(1), text_, s.group(1).strip() if s else None))
            continue
        if not seen_question and line.strip():
            preamble.append(line.strip())
        if current:
            sections[current].append(line)
    return questions, preamble, sections


def check(text, taken=None, full=False):
    questions, preamble, sections = parse(text)
    open_, no_state = [], []
    for n, num, heading, state in questions:
        if state is None or not (state in CLOSED or state in OPEN or WAITING.fullmatch(state)):
            no_state.append({"line": n, "heading": heading})
        elif state in OPEN or WAITING.fullmatch(state):
            open_.append({"line": n, "heading": heading, "state": state})
    math = [{"line": n, "heading": heading} for n, _, heading, _ in questions if "$" in heading]
    version = next((p[len(VERSION):].strip() for p in preamble if p.startswith(VERSION)), None)
    summary = next((p for p in preamble if not p.startswith(VERSION) and not p.startswith("#")), None)
    numbers = {num for _, num, _, _ in questions}
    missing_numbers = []
    if taken is not None:
        missing_numbers = sorted({num for _, num, _, _ in parse(taken)[0]} - numbers,
                                 key=lambda q: [int(x) for x in q[1:].split(".")])
    out = {"questions": len(questions), "open": open_, "no_state": no_state, "math_in_heading": math, "missing_numbers": missing_numbers, "version": version,
           "summary_written": bool(summary) and summary != "[待答]"}
    ok = questions and not open_ and not no_state and not math and not missing_numbers and version and summary != "[待答]"
    if full:
        out["missing_trunk"] = [f"Q{i}" for i in range(1, 9) if f"Q{i}" not in numbers]
        out["missing_items"] = [f"{q} {word}" for q, words in ITEMS.items() for word in words
                                if not any(f"**{word}**" in line for line in sections.get(q, []))]
        ok = ok and out["summary_written"] and not out["missing_trunk"] and not out["missing_items"]
    out = {"code": "complete" if ok else "open", **out}
    return out


def main(argv=None):
    first, _, rest = __doc__.strip().partition("\n")
    p = argparse.ArgumentParser(description=first, epilog=rest.strip(), formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("note", metavar="NOTE", help="the note file: <scratch>/<package folder name>.note.md")
    p.add_argument("--taken", metavar="FILE", help="the note as taken (default: NOTE.taken when it exists)")
    p.add_argument("--full", action="store_true", help="a read-through: the eight questions, the summary, the fixed items")
    args = p.parse_args(argv)
    try:
        text = Path(args.note).read_text(encoding="utf-8")
        taken_path = Path(args.taken) if args.taken else Path(f"{args.note}.taken")
        taken = taken_path.read_text(encoding="utf-8") if (args.taken or taken_path.exists()) else None
    except (OSError, UnicodeDecodeError) as e:
        print(json.dumps({"code": "unreadable", "path": args.note, "detail": str(e)}, ensure_ascii=False))
        return 2
    out = check(text, taken, args.full)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["code"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
