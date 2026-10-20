#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Show whether each record's file is its paper: the verdict and its evidence. Read-only: it writes nothing.

The file is the record's own (<work>/records/<slug>.pdf, .accepted.pdf, .preprint.pdf, .supplement.pdf or .html),
or --file F for one record. claim.py and attach_file.py run this check themselves; this shows why a file passed or
not. A file the check refuses that is the paper after all: claim.py --accept FILE --slug S --reason R.

stdout: one line per record {slug, code, file, kind, md5, evidence, hint?}, then {"summary"}; the codes and the
evidence are below. no_file: the record has no file yet. Exit 0 = every file passes; 1 = not; 2 = no pdftotext.

Example:
  uv run scripts/check_pdf.py <work>/records/<slug>.json
"""
from pathlib import Path

from p2zlib import cli, verify


def configure(p):
    p.add_argument("--file", metavar="F", help="check this file instead of the record's own (one record)")


def check(p, args):
    if args.file and len(args.records) != 1:
        p.error("--file goes with exactly one record")
    verify.require_pdftotext()


def process(rec, args):
    path = Path(args.file) if args.file else rec.file()
    if path is None:
        return {"code": "no_file", "hint": "The record has no file yet: fetch it (p2z.py fetch), or claim one."}
    res = verify.check(path, rec)
    return {"code": res["code"], "file": str(path), "kind": res["kind"], "md5": res["md5"], "evidence": res["evidence"],
            "hint": verify.HINTS.get(res["code"])}


def main(argv=None):
    return cli.main_records(__doc__ + "\n" + verify.__doc__, process, argv, configure=configure, check=check,
                            answers=verify.PASS_CODES)


if __name__ == "__main__":
    raise SystemExit(main())
