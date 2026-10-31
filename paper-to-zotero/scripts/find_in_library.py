#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Look each record's paper up in the Zotero library, read-only: the record's `found` and `near_matches`.

With --file, it looks files up among the library's attachments instead (below).

Only an identifier confirms a paper is there: the DOI (a doi.org url and an Extra "DOI:" line count), else the
arXiv id — unless the record's item has a DOI of its own that the library lacks: then an arXiv hit is its preprint,
a candidate. A title never confirms: whatever a quick search for the title finds is a candidate (near_matches), with
the evidence a judge needs. Open candidates go into a same_paper handoff (handoffs/<slug>.<n>.json), which a judge
answers with answer.py: same_as or distinct_from in the record; then this runs again, and items in distinct_from are
left out at every step.

`found` is computed again only when it is not done: absent (an older run's `found`, written without `from`,
counts as absent), or the item's identifiers or title, same_as or distinct_from changed since; each line says why
(`reason`). A paper added to the library after the lookup is caught by create_item.py, which looks again before
it creates anything.

stdout: one line per record {slug, code, reason?, key?, citationKey?, matched_by?, title?, attachments?,
near_matches?}, then {"summary"}.
  found        in the library (`matched_by`: doi | arxiv | same_as; `duplicates` when several items match)
  not_found    not in the library; nothing is like it
  near_match   not confirmed, but candidates are open (`near_matches`), and `handoff` is the same_paper handoff
               that hands them to a judge (also on a rerun while they stay open)
  no_item      the record has no `item` to look up
  skipped      reason done: `found` is up to date
Exit 0 = every record found, not found or done; 1 = a near match or no item; 2 = cannot check
(zotero_unreachable, local_api_disabled).

--file FILE...: each file's md5 against the library's attachments (in the trash or not there: not_found), for files
a run left behind (paper-fetch's claim --sweep lists them). Lines {file, md5, code: found | not_found, attachment?,
parent?, citationKey?, title?}: found names the attachment, its parent item and that item's citation key and title.

Examples:
  uv run scripts/find_in_library.py <scratch>/paper-to-zotero/records/*.json
  uv run scripts/find_in_library.py --file ~/Downloads/2006.11239v2.pdf
"""
from pathlib import Path

from p2zlib import cli, run, zotero

def setup(args, records):
    return zotero.Zotero(args.base_url)


def summary(rec, found):
    if found["code"] == "found":
        return {"code": "found", "key": found["key"], "citationKey": found["citationKey"] or None,
                "matched_by": found["matched_by"], "title": found["title"][:80], "attachments": len(found["attachments"]),
                **({"duplicates": found["duplicates"]} if found.get("duplicates") else {})}
    handoff, still = run.ask_same_paper(rec), set(run.unsettled(rec))
    if handoff:
        return {"code": "near_match", "near_matches": run.near_lines(m for m in rec["near_matches"] if m["key"] in still),
                "handoff": handoff, "hint": run.HINT_NEAR}
    return {"code": "not_found"}


def process(rec, zot):
    if not rec.item:
        return {"code": "no_item", "hint": run.HINT_NO_ITEM}
    due = run.due(rec, "found")
    if due is None:
        line = summary(rec, rec["found"])
        if line["code"] == "near_match":  # done, and still open: the judge's
            return line
        return cli.skipped("done", found=rec["found"]["code"], **({"key": rec["found"]["key"]} if rec["found"].get("key") else {}))
    found, _ = run.look_up(rec, zot)
    line = summary(rec, found)
    return {"code": line.pop("code"), "reason": due, **line}


def by_file(files, base_url):
    """--file: each file's md5 looked up among the library's attachments -> the exit code."""
    md5s, unreadable = {}, {}
    for f in files:
        try:
            md5s[f] = run.md5_of(Path(f).expanduser())
        except OSError as e:
            unreadable[f] = {"file": f, "code": "unreadable", "detail": str(e), "hint": "No such file, or it cannot be read."}
    held = zotero.Zotero(base_url).files_by_md5(list(md5s.values())) if md5s else {}
    lines = [unreadable.get(f) or {"file": f, "md5": md5s[f], "code": "found" if md5s[f] in held else "not_found",
                                   **held.get(md5s[f], {})} for f in files]
    return cli.finish(lines, answers=("found", "not_found"))


def main(argv=None):
    p = cli.records_parser(__doc__, zotero=True, dry_run=True)
    p.add_argument("--file", nargs="+", default=[], metavar="FILE", help="files to look up among the attachments, by md5")
    args = p.parse_args(argv)
    if args.file and args.records:
        p.error("--file looks files up; record paths are another run")
    if args.file:
        return cli.run(lambda: by_file(args.file, args.base_url))
    return cli.run(lambda: cli.each_record(args, process, setup=setup, answers=("found", "not_found")))


if __name__ == "__main__":
    raise SystemExit(main())
