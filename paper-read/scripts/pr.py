#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""paper-read: a library paper's note, taken out of Zotero, checked and put back; a project paper index's headings. `pr.py WORD ...`; each word has its -h.

Each word runs one script of scripts/ (through uv, so the script's own dependencies load), its exit code passed
through. An unknown word exits 2 with this list.

Exit codes, every word: 0 done (stderr empty); 1 something is yours to act on: the line's code says what, and
heading, over several papers, ends stderr with {"summary": ...}; 2 cannot go on (Zotero not running, no pdftotext, a
usage error): stderr's last line is {code, hint}.

A paper is named by its citation key or its item key. take and heading read a list through -: a value a line, or
paper-to-zotero's JSON lines by their `key` (else `cite`); a line reporting a skip or a failure upstream is passed on
as it is. check, quotes and put take a note file, <name>.note.md, and find what take put beside it.

Examples:
  pr.py take xiaoTCACE2026 -o <scratch>/
  p2z.py search T-CACE | pr.py heading -
"""
import os
import sys
from pathlib import Path

from prlib import cli

HERE = Path(__file__).resolve().parent
SELF = Path(__file__).name

# word: (script, what it does)
WORDS = {
    "take": ("prepare_note", "a paper's note, PDF and structured package out of Zotero into a scratch directory"),
    "check": ("check_note", "a note's question tree, checked by note-format.md"),
    "quotes": ("check_quotes", "each quotation of a note: found in the PDF, in the package, or not"),
    "put": ("put_note", "a note's figures and tables linked, and the note put into Zotero"),
    "heading": ("index_heading", "each paper's heading line in a project's paper index"),
}


def listing():
    width = max(map(len, WORDS)) + 2
    first, _, rest = __doc__.strip().partition("\n")
    words = "\n".join(f"  {word:<{width}}{text}" for word, (_, text) in WORDS.items())
    return f"usage: {SELF} WORD [options] [operands]   ({SELF} WORD -h for each)\n\n{first}\n\nwords:\n{words}\n\n{rest.strip()}\n"


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        cli.write(listing())
        return cli.OK
    word = argv[0] if argv else None
    if word not in WORDS:
        sys.stderr.write(listing())
        cli.emit({"code": "usage", "detail": f"no word {word!r}" if word else "name a word", "hint": f"See {SELF} -h."},
                 sys.stderr)
        return cli.CANNOT
    os.environ[cli.PROG_ENV] = f"{SELF} {word}"
    os.execvp("uv", ["uv", "run", "--quiet", "--script", str(HERE / f"{WORDS[word][0]}.py"), *argv[1:]])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
