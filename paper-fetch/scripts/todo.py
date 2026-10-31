#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""List a directory's open handoffs: what agents still have to look at and answer.

  pf.py todo --dir DIR [--slug S] [--kind K]

A handoff is open until answered (pf.py answer), or until what it waited for happened: a file filed for its paper (page,
file), a label on its file (label), its download filed (left). Its record, with the evidence files to read, is the
`path` printed (pflib/run.py, Handoffs).

stdout: one line per open handoff, oldest first: {id, slug, kind, taker, route?, url?, path}; then
{"summary": {open, kinds: {kind: n}, papers: [slugs]}}.
Exit 0 = nothing open; 1 = some open.

Example:
  uv run scripts/todo.py --dir <dir>
"""
from pflib import cli, run


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("--dir", required=True, metavar="DIR", help="paper-fetch's directory")
    p.add_argument("--slug", help="one paper's only")
    p.add_argument("--kind", choices=sorted(run.HANDOFF_TAKERS), help="one kind only")
    args = p.parse_args(argv)
    work = run.Work(args.dir)

    def go():
        found = [h for h in run.open_handoffs(work, slug=args.slug) if not args.kind or h["kind"] == args.kind]
        kinds = {}
        for h in found:
            cli.emit({"id": h["id"], "slug": h.get("slug"), "kind": h["kind"], "taker": h.get("taker"),
                      "route": h.get("route"), "url": h.get("url"), "path": h.get("path")})
            kinds[h["kind"]] = kinds.get(h["kind"], 0) + 1
        cli.emit({"summary": {"open": len(found), "kinds": kinds,
                              "papers": sorted({h["slug"] for h in found if h.get("slug")})}})
        return cli.ACT if found else cli.OK

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
