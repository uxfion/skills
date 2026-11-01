#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Fold fetch.jsonl into each result's `files` and `outcome`: what a caller reads to know what was got.

fetch, claim and wait fold the results they touched when they end; run this after the background watcher filed a
file (a `claimed` event in fetch.jsonl), or to see the state of every result. Each fold starts from the whole log,
so whoever folds last is right.

files: one entry per file beside the result {name, md5, kind, label, check, accepted_reason?, url, evidence}. The
label is the last `label` event for that file (claim.py --label), else Unknown-<Source> (Snapshot-<Source> for a
page) from where it came. check: ok (the check passed), accepted (claim.py --accept: the agent read it), cannot_judge
(a stub result: nothing to check against). outcome: {status: got | waiting | not_got, tried: [hosts], stop}: got when
a file of the paper is there (a supplement alone is not), waiting when the last thing fetch did for it was to stop at
a gate in front of the user, else not_got.

stdout: one line per result {slug, code ok, status, files: [label titles], changed}, then {"summary"}.
Exit 0 = every result folded; 1 = a file named is not a result.

Examples:
  uv run scripts/settle.py <dir>/results/*.json
  uv run scripts/settle.py --dir <dir>          every result there
"""
from pathlib import Path

from pflib import cli, run


def main(argv=None):
    p = cli.results_parser(__doc__)
    p.add_argument("--dir", metavar="DIR", help="fold every result in DIR (<dir>/results/*.json)")
    args = p.parse_args(argv)
    if args.dir:
        args.results = [str(f) for f in sorted((Path(args.dir) / "results").glob("*.json"))]

    def one(res, _):
        [(res, changed)] = run.settle(res.work, [res])
        return {"status": res["outcome"]["status"], "files": [f["label"]["title"] for f in res["files"]],
                "changed": changed}

    return cli.run(lambda: cli.each_result(args, one))


if __name__ == "__main__":
    raise SystemExit(main())
