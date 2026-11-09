#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""paddleocr: PDFs and page images into Markdown an agent can read whole and trust.

parse writes one folder per document, <outdir>/<stem>/ (parse -h says what it holds); every other word works on such a
folder, named after the word. An unknown word exits 2 with this list.

Exit codes, every word: 0 done; 1 something is yours to act on: a line's code says what; 2 cannot go on (no paddleocr
tool environment, no VL server, a folder another process is writing, a usage error): stderr's last line is
{code, hint}.

Examples:
  ocr.py parse paper.pdf -o /abs/out/
  ocr.py findings /abs/out/paper
"""
import os
import sys
from pathlib import Path

from ocrlib import cli

HERE = Path(__file__).resolve().parent
SELF = Path(__file__).name

# word: (script, whether the word is also the script's own command, what it does)
WORDS = {
    "parse": ("parse", False, "parse PDFs or page images with the models (needs the GPU)"),
    "findings": ("doc", True, "a parse's open findings, and those judged unresolved"),
    "diff": ("doc", True, "where the parse's words and the PDF's text layer differ by one to three words"),
    "show": ("doc", True, "a finding, block, figure or page: its text, the text layer under it, a page image"),
    "commit": ("doc", True, "record the Markdown's edits and verdicts, check again, write the Markdown"),
    "cut": ("doc", True, "cut a figure anew from a box, or a new one on a page"),
    "render": ("doc", True, "process the stored model output again with the current code, without the GPU"),
    "objects": ("doc", True, "where the figures and tables sit in the PDF, for links from notes"),
}


def listing():
    width = max(map(len, WORDS)) + 2
    first, _, rest = __doc__.strip().partition("\n")
    words = "\n".join(f"  {word:<{width}}{text}" for word, (_, _, text) in WORDS.items())
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
    script, is_command, _ = WORDS[word]
    os.environ[cli.PROG_ENV] = SELF if is_command else f"{SELF} {word}"
    os.execvp("uv", ["uv", "run", "--quiet", "--script", str(HERE / f"{script}.py"),
                     *([word] if is_command else []), *argv[1:]])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
