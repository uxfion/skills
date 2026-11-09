#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Show whether files are their paper: the check's verdict and its evidence. Read-only: it writes nothing.

Operands: results, <dir>/results/<slug>.json (- reads their paths from stdin, a path a line or our JSON lines by
`path`), each checked by the paper's own file beside it; or files and one result (the operand ending in .json), each
file checked against that result. pf.py claim runs this check itself; this shows why a file passed or not.

One line per result, or per file named: {slug, code, file, kind, md5, evidence, hint?}, the codes and the evidence
below; no_file: the result has no file yet.
Exit 0 = every file passes; 1 = not, then stderr's last line is {"summary": {total, ok, skipped, failed}}; 2 = no
pdftotext, then each is not_run and stderr's last line is {code, hint}.
"""
from pathlib import Path

from pflib import cli, run, verify

EXAMPLES = """
Examples:
  pf.py check <dir>/results/*.json
  pf.py check ~/Downloads/x.pdf <dir>/results/<slug>.json
"""


def verdict(path, res):
    if path is None:
        return {"code": "no_file", "hint": "The result has no file yet: fetch it (pf.py fetch), or claim one."}
    v = verify.check(path, res)
    return {"code": v["code"], "file": str(path), "kind": v["kind"], "md5": v["md5"], "evidence": v["evidence"],
            "hint": verify.HINTS.get(v["code"])}


def main(argv=None):
    p = cli.parser(__doc__ + "\n" + verify.__doc__ + EXAMPLES)
    p.add_argument("operands", nargs="*", metavar="RESULT|FILE",
                   help="result files, - reading their paths from stdin; or files and one result")
    args = cli.parse(p, argv)
    if not args.operands:
        p.error("name the results: <dir>/results/*.json, - to read their paths from stdin; or files and one result")
    files = [v for v in args.operands if v != "-" and not v.lower().endswith(".json")]

    if not files:
        args.results = args.operands

        def setup(args, results):
            verify.require_pdftotext()
            return args

        return cli.run(lambda: cli.each_result(p, args, lambda res, _: verdict(res.file(), res), setup=setup,
                                               answers=verify.PASS_CODES))
    result, _ = cli.split_result(p, [v for v in args.operands if v not in files])

    def against_one():
        try:
            res = run.read(result)
        except cli.Stop as stop:
            cli.emit(stop.line(slug=Path(result).stem))
            return cli.ACT
        out = cli.Lines(verify.PASS_CODES)
        try:
            verify.require_pdftotext()
        except cli.Stop as stop:
            out.stop(stop)
        for f in files:
            out.add({"slug": res.slug, "file": f}, lambda: verdict(Path(f), res))
        return out.finish()

    return cli.run(against_one)


if __name__ == "__main__":
    raise SystemExit(main())
