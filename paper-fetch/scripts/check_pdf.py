#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Show whether each result's file is its paper: the verdict and its evidence. Read-only: it writes nothing.

The file is the result's own (<dir>/results/<slug>.pdf, .accepted.pdf, .preprint.pdf, .supplement.pdf or .html),
or --file F for one result. claim.py runs this check itself; this shows why a file passed or not. A file the check
could not be sure of is held with a `file` handoff, which its agent answers (pf.py answer).

stdout: one line per result {slug, code, file, kind, md5, evidence, hint?}, then {"summary"}; the codes and the
evidence are below. no_file: the result has no file yet. Exit 0 = every file passes; 1 = not; 2 = no pdftotext.

Example:
  uv run scripts/check_pdf.py <dir>/results/<slug>.json
"""
from pathlib import Path

from pflib import cli, verify


def configure(p):
    p.add_argument("--file", metavar="F", help="check this file instead of the result's own (one result)")


def check(p, args):
    if args.file and len(args.results) != 1:
        p.error("--file goes with exactly one result")
    verify.require_pdftotext()


def process(res, args):
    path = Path(args.file) if args.file else res.file()
    if path is None:
        return {"code": "no_file", "hint": "The result has no file yet: fetch it (pf.py fetch), or claim one."}
    v = verify.check(path, res)
    return {"code": v["code"], "file": str(path), "kind": v["kind"], "md5": v["md5"], "evidence": v["evidence"],
            "hint": verify.HINTS.get(v["code"])}


def main(argv=None):
    return cli.main_results(__doc__ + "\n" + verify.__doc__, process, argv, configure=configure, check=check,
                            answers=verify.PASS_CODES)


if __name__ == "__main__":
    raise SystemExit(main())
