#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check that every quotation in a paper note comes from the paper: step 3 of every change to a note, with check_note.py.

  uv run scripts/check_quotes.py <note> --pdf <PDF> [--package <package folder>]

A quotation is a line `> "<the paper's words>"` (or `> “…”`), followed by nothing but an optional source in brackets, such as
(Sec. III-A) or (Table III, p.11), and an optional check mark （已核对 …）; the words run to the line's last double
quote of its kind, so double quotes inside them are copied as they are. Where it says it is in the paper is not checked: only
whether its words are.

Both sides are brought to one form before they are compared: Unicode-normalised, LaTeX commands removed (and the
package's HTML tags and comments),
lowercased, letters and digits kept, and a point or comma kept between two digits (1.25 and 12.5 stay apart). A
quotation cut with … is matched piece by piece, in order. A piece shorter than 20 characters in that form matches too
much to prove anything.

Each quotation, in order:
  ok             found in the PDF's text layer (pdftotext, poppler)
  package_only   not in the PDF's text, but in the structured package (a table or figure without a text layer)
  not_found      in neither
  too_short      a piece too short to check
  unparsed       a line opening with `> "` or `> “` that is not in this form, so its words could not be told apart
A quotation whose line carries （已核对 …） counts as checked whatever the result: someone compared it with the page.

stdout: one JSON object {code, quotes: [{line, result, checked, text}], counts}.
  pass   every quotation is ok or checked
  open   some are not: look at the page image, correct the quotation, mark it （已核对 <source> · <date>）, run again
Exit 0 = pass; 1 = open; 2 = the note or the PDF cannot be read, or pdftotext is missing.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

MIN_PIECE = 20
OPENING = re.compile(r'^>\s*(["“])')
CLOSING = {'"': '"', "“": "”"}
TAIL = re.compile(r"^\s*(?:[（(].*[）)])?\s*$")
TAG = re.compile(r"</?[A-Za-z][^<>\n]*>")  # the package's HTML; a "<" in the text (p < 0.05) is no tag
COMMENT = re.compile(r"<!--.*?-->", re.S)
LATEX = re.compile(r"\\[A-Za-z]+")
CUT = re.compile(r"…|\.\.\.")


def canon(text):
    """Letters and digits, lowercased, with a point or comma kept between two digits."""
    text = unicodedata.normalize("NFKC", text)
    text = LATEX.sub("", text).lower()
    out = []
    for i, ch in enumerate(text):
        if ch.isalnum():
            out.append(ch)
        elif ch in ".," and 0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit():
            out.append(ch)
    return "".join(out)


def quotations(note):
    """(line number, words or None when the line is not in the form, checked)."""
    for n, line in enumerate(note.split("\n"), 1):
        line = line.strip()
        m = OPENING.match(line)
        if not m:
            continue
        close = line.rfind(CLOSING[m.group(1)])
        text, tail = line[m.end():close], line[close + 1:]
        if close < m.end() or not text or not TAIL.match(tail):
            yield n, None, False, line
        else:
            yield n, text, "已核对" in tail, line


def found(pieces, haystacks):
    for hay in haystacks:
        at = 0
        for piece in pieces:
            at = hay.find(piece, at)
            if at < 0:
                break
            at += len(piece)
        else:
            return True
    return False


def pdf_text(pdf):
    """The PDF's text layer, in pdftotext's reading order and in -raw stream order: a quote may match either."""
    texts = []
    for mode in ([], ["-raw"]):
        done = subprocess.run(["pdftotext", *mode, str(pdf), "-"], capture_output=True, text=True)
        if done.returncode != 0:
            raise OSError(done.stderr.strip() or "pdftotext failed")
        texts.append(canon(done.stdout))
    return texts


def check(note, pdf_texts, package_text):
    quotes, counts = [], {}
    for n, text, checked, line in quotations(note):
        pieces = [p for p in (canon(x) for x in CUT.split(text or "")) if p]
        if text is None:
            result = "unparsed"
        elif not pieces or any(len(p) < MIN_PIECE for p in pieces):
            result = "too_short"
        elif found(pieces, pdf_texts):
            result = "ok"
        elif package_text and found(pieces, [package_text]):
            result = "package_only"
        else:
            result = "not_found"
        counts[result] = counts.get(result, 0) + 1
        quotes.append({"line": n, "result": result, "checked": checked, "text": (text or line)[:80]})
    passed = all(q["result"] == "ok" or q["checked"] for q in quotes)
    return {"code": "pass" if passed else "open", "quotes": quotes, "counts": counts}


def main(argv=None):
    first, _, rest = __doc__.strip().partition("\n")
    p = argparse.ArgumentParser(description=first, epilog=rest.strip(), formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("note", metavar="NOTE", help="the note file")
    p.add_argument("--pdf", required=True, help="the PDF the note was read in")
    p.add_argument("--package", help="the paper's structured package folder (its .md is searched after the PDF)")
    args = p.parse_args(argv)
    if not shutil.which("pdftotext"):
        print(json.dumps({"code": "unreadable", "detail": "pdftotext (poppler) is not installed"}))
        return 2
    try:
        note = Path(args.note).read_text(encoding="utf-8")
        texts = pdf_text(args.pdf)
        md = next(Path(args.package).glob("*.md"), None) if args.package else None
        if args.package and not md:
            raise OSError(f"no .md in the package folder {args.package}")
        package_text = canon(TAG.sub(" ", COMMENT.sub(" ", md.read_text(encoding="utf-8")))) if md else None
    except (OSError, UnicodeDecodeError) as e:
        print(json.dumps({"code": "unreadable", "detail": str(e)}, ensure_ascii=False))
        return 2
    out = check(note, texts, package_text)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["code"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
