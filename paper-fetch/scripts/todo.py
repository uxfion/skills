#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The open handoffs of a run: what agents still have to look at and answer.

A handoff is open until answered (pf.py answer), or until what it waited for happened: a file filed for its paper
(page, file), a label on its file (label), its download filed (left). Its record, with the evidence files to read,
is the `path` printed (pflib/run.py, Handoffs). --slug takes a paper's slug or its citation key as given.

One line per open handoff, {id, slug, kind, route?, url?, path}, by kind in the order the loop takes them up
(browser_down, page, file, label, left; SKILL.md, Get the file), oldest first within a kind. Who takes each kind:
SKILL.md, Handoffs.
Exit 0 = nothing open; 1 = some open, then stderr's last line is {"summary": {open, kinds: {kind: n}, papers:
[slugs]}}; or DIR is no run's directory (no_work_dir), its line on stdout.

Examples:
  pf.py todo <dir>
  pf.py todo <dir> --kind label | jq -r .path
"""
import sys

from pflib import cli, paper, run


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("dir", nargs="?", metavar="DIR", help="the run's directory")
    p.add_argument("--slug", help="one paper's only: its slug, or its citation key")
    p.add_argument("--kind", choices=sorted(run.ANSWERS), help="one kind only")
    args = cli.parse(p, argv)
    if not args.dir:
        p.error("name the run's directory")
    work = run.Work(args.dir)

    def go():
        if not work.results.is_dir():
            raise cli.Stop("no_work_dir", dir=str(work.root), hint="No results/ there: name the run's directory.")
        slug = paper.safe_slug(args.slug) if args.slug else None
        found = [h for h in run.open_handoffs(work, slug=slug) if not args.kind or h["kind"] == args.kind]
        found.sort(key=lambda h: list(run.ANSWERS).index(h["kind"]))  # stable: oldest first within a kind
        kinds = {}
        for h in found:
            cli.emit({"id": h["id"], "slug": h.get("slug"), "kind": h["kind"], "route": h.get("route"),
                      "url": h.get("url"), "path": h.get("path")})
            kinds[h["kind"]] = kinds.get(h["kind"], 0) + 1
        if not found:
            return cli.OK
        cli.emit({"summary": {"open": len(found), "kinds": kinds,
                              "papers": sorted({h["slug"] for h in found if h.get("slug")})}}, sys.stderr)
        return cli.ACT

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
