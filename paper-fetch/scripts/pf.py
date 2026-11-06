#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""paper-fetch: which paper it is, what is known about it, and its full text, checked and labelled. `pf.py WORD ...`; each word has its -h.

Each word runs one script of scripts/ (through uv, so the script's own dependencies load), its exit code passed
through. An unknown word exits 2 with this list.

Exit codes, every word: 0 done (stderr empty); 1 something is yours to act on: a line's code says what, and a word
over several things ends stderr with {"summary": ...}; 2 cannot go on (a service that does not answer, no
pdftotext, no opencli, a usage error): stderr's last line is {code, hint}, and a word over several things lists each
one not done as not_run.

A list read through - takes a value a line, or our JSON lines by the field that names the thing (a result's `path`,
a paper's `id`); a JSON line without that field which reports a skip or a failure upstream is passed on as it is, so
a failure reaches the pipeline's end.

Examples:
  pf.py identify -o <dir>/ 1505.04597 10.1109/CVPR.2016.90 | pf.py locate -
  pf.py fetch --pass 1 <dir>/results/*.json
"""
# Copied from paper-to-zotero/scripts/p2z.py at 8b0a0cd without its compound words (prepare, save).
import os
import sys
from pathlib import Path

from pflib import cli

HERE = Path(__file__).resolve().parent
SELF = Path(__file__).name

# word: (script, whether the word is also the script's own command, what it does)
WORDS = {
    "ready": ("ready", False, "check poppler, OpenCLI and the config; make the run's directory"),
    "identify": ("identify", True, "identify papers: a result file each, metadata and versions"),
    "search": ("identify", True, "Crossref's top 5 for a title; writes nothing"),
    "redraft": ("identify", True, "make a result the published version's: its DOI or page"),
    "locate": ("fulltext_links", False, "find where each result's full text may be had"),
    "watch": ("claim", True, "file new downloads as they land, until stopped (in the background)"),
    "scan": ("claim", True, "file the new downloads once"),
    "fetch": ("fetch", False, "walk one pass of the chain of routes to the full text"),
    "claim": ("claim", True, "check files against a result and file them"),
    "check": ("check_pdf", False, "the check's verdict on files, and its evidence; writes nothing"),
    "wait": ("wait", False, "wait at a gate for one paper, up to about ten minutes"),
    "todo": ("todo", False, "the open handoffs of a run"),
    "answer": ("answer", False, "record an agent's or the user's answer to a handoff"),
    "sync": ("settle", False, "bring results' files and outcome in line with the run's log"),
    "downloads": ("claim", True, "the files this run left in Downloads; read-only"),
}


def command(script, *args):
    """The command line that runs scripts/<script>.py: through uv, which loads the script's own dependencies."""
    return ["uv", "run", "--quiet", "--script", str(HERE / f"{script}.py"), *args]


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
    os.execvp("uv", command(script, *([word] if is_command else []), *argv[1:]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
