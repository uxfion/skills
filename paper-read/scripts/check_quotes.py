#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check that every quotation in a paper note comes from the paper: step 3 of every change to a note, with pr.py check.

The paper is what pr.py take put beside the note <name>.note.md: the PDF <name>.pdf, and the structured package
<name>/ when there is one (its .md is searched after the PDF).

A quotation is a line `> "<the paper's words>"` (or `> “…”`), followed by nothing but an optional source in brackets,
such as (Sec. III-A) or (Table III, p.11), and an optional check mark （已核对 …）; the words run to the line's last
double quote of its kind, so double quotes inside them are copied as they are. Where it says it is in the paper is not
checked: only whether its words are.

Both sides are brought to one form before they are compared: Unicode-normalised, LaTeX commands removed (and the
package's HTML tags and comments), lowercased, letters and digits kept, and a point or comma kept between two digits
(1.25 and 12.5 stay apart). A quotation cut with … is matched piece by piece, in order. A piece shorter than 20
characters in that form matches too much to prove anything.

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
  file_not_found, file_unreadable    {file, code, path, hint}: the note, the PDF beside it or the package (path)
         cannot be read
Exit 0 = pass; 1 = anything else; 2 = cannot go on: no_pdftotext, or a usage error.

Examples:
  pr.py quotes <scratch>/xiaoTCACE2026.Published-IEEE.note.md
"""
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from prlib import cli, sources

MIN_PIECE = 20
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
        q = sources.quotation(line)
        if q is None:
            continue
        start, end, tail = q
        if end is None:
            yield n, None, False, line.strip()
        else:
            yield n, line[start:end], "已核对" in tail, line.strip()


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
    if not pdf.is_file():
        raise cli.Stop("file_not_found", path=str(pdf),
                       hint="No PDF beside the note: take the note with pr.py take, which puts <name>.pdf there.")
    texts = []
    for mode in ([], ["-raw"]):
        done = subprocess.run(["pdftotext", *mode, str(pdf), "-"], capture_output=True, text=True)
        if done.returncode != 0:
            raise cli.Stop("file_unreadable", path=str(pdf), detail=done.stderr.strip()[-600:],
                           hint="pdftotext cannot read this PDF: open it to see whether it is whole.")
        texts.append(canon(done.stdout))
    return texts


def package_text(folder):
    """The package's Markdown in the compared form; None without a package."""
    if not folder.is_dir():
        return None
    md = next(folder.glob("*.md"), None)
    if md is None:
        raise cli.Stop("file_unreadable", path=str(folder),
                       hint="The package folder holds no .md: take the note again into a new directory.")
    return canon(TAG.sub(" ", COMMENT.sub(" ", cli.document(md, path=str(md)))))


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
    p = cli.parser(__doc__)
    p.add_argument("note", metavar="NOTE", help="the note file, <name>.note.md as pr.py take wrote it")
    args = cli.parse(p, argv)

    def run():
        if not shutil.which("pdftotext"):
            raise cli.Stop("no_pdftotext", exit=cli.CANNOT,
                           hint="Install poppler, which has pdftotext; the note is put once this check passes.")
        note = cli.document(args.note, "No such note file: name the <name>.note.md pr.py take wrote.",
                            path=args.note)
        stem = Path(args.note).name.removesuffix(".note.md")
        beside = Path(args.note).with_name(stem)
        out = check(note, pdf_text(beside.with_name(f"{stem}.pdf")), package_text(beside))
        cli.emit(out)
        return cli.OK if out["code"] == "pass" else cli.ACT

    return cli.run(run, file=args.note)


if __name__ == "__main__":
    sys.exit(main())
