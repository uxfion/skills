#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Is it in the Zotero library already, read-only: each record's paper (its `found` and `near_matches`), each other file by its md5.

What follows the options is paths (- reads a list of paths from stdin): a file that holds one JSON object is a
record, any other file (a PDF a run left behind: paper-fetch's pf.py downloads lists them) is looked up among the
library's attachments by its md5.

A record: only an identifier confirms a paper is there: the DOI (a doi.org url and an Extra "DOI:" line count),
else the arXiv id — unless the record's item has a DOI of its own that the library lacks: then an arXiv hit is its
preprint, a candidate; and an identifier several items carry confirms none of them: each is a candidate. A title
never confirms: whatever a quick search for the title finds is a candidate (near_matches), with the evidence a judge
needs. Open candidates go into a same_paper handoff (handoffs/<slug>.<n>.json), which a judge answers with
p2z.py answer, into the handoff; then this runs again: the item answered same is the paper's, and items answered
distinct are left out at every step. `found` is computed again only when it is not done: absent (an older run's
`found`, written without `from`, counts as absent), or the item's identifiers or title, or the handoffs' answers,
changed since; each line says why (`reason`). A paper added to the library after the lookup is caught by
p2z.py create, which looks again before it creates anything.

stdout: one line per path, in their order. A record: {slug, code, reason?, key?, citationKey?, matched_by?, title?,
attachments?, near_matches?}:
  found        in the library (`matched_by`: doi | arxiv | same_paper, a handoff's answer)
  not_found    not in the library; nothing is like it
  near_match   not confirmed, but candidates are open (`near_matches`), and `handoff` is the same_paper handoff
               that hands them to a judge (also on a rerun while they stay open)
  no_item      the record has no `item` to look up
  skipped      reason done: `found` is up to date
Another file: {file, md5, code: found | not_found, attachment?, parent?, citationKey?, title?}: found names the
attachment, its parent item and that item's citation key and title (one in the trash is not_found).
  file_not_found  no such file
Exit 0 = every path found, not found or done; 1 = a near match, no item, or no such file, then stderr's last line is
{"summary": {total, ok, skipped, failed}}; 2 = cannot check (zotero_unreachable, local_api_disabled), then stderr's
last line is {code, hint}.

Examples:
  p2z.py have <scratch>/paper-to-zotero/records/*.json
  p2z.py have ~/Downloads/2006.11239v2.pdf
"""
from pathlib import Path

from p2zlib import cli, run, zotero

def setup(args, records):
    return zotero.Zotero(args.base_url)


def summary(rec, found):
    if found["code"] == "found":
        return {"code": "found", "key": found["key"], "citationKey": found["citationKey"] or None,
                "matched_by": found["matched_by"], "title": found["title"][:80], "attachments": len(found["attachments"])}
    handoff, still = run.ask_same_paper(rec), set(run.unsettled(rec))
    if handoff:
        return {"code": "near_match", "near_matches": run.near_lines(m for m in rec["near_matches"] if m["key"] in still),
                "handoff": handoff}  # no hint: the handoff is a judge's, and p2z.py's decisions name it
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


def read(path):
    """-> a Record, or None for a file that is not a record; file_not_found for no such file."""
    try:
        return run.read(path)
    except cli.Stop as stop:
        if stop.code == "file_not_found":
            raise
        return None


def have(p, args):
    if not args.records:
        p.error("name the records or files, or - to read their paths from stdin")
    named = cli.paths(args.records)
    entries, md5s = [], {}
    for path in named:
        try:
            rec = read(path)
            if rec is None:
                md5s[path] = run.md5_of(Path(path).expanduser())
            entries.append((path, rec, None))
        except cli.Stop as stop:
            entries.append((path, None, stop.line(file=path)))
        except OSError as e:
            entries.append((path, None, {"file": path, "code": "unreadable", "detail": str(e),
                                         "hint": "The file cannot be read."}))
    zot, out = zotero.Zotero(args.base_url), cli.Lines(answers=("found", "not_found"))
    try:
        held = zot.files_by_md5(list(md5s.values())) if md5s else {}
    except cli.Stop as stop:
        if stop.exit != cli.CANNOT:
            raise
        out.stop(stop)
        held = {}

    def save(rec):
        try:
            return process(rec, zot)
        finally:
            if rec.changed() and not args.dry_run:
                rec.save()

    for path, rec, failure in entries:
        if failure is not None:
            out.put(failure)
        elif rec is not None:
            out.add({"slug": rec.slug}, lambda: save(rec))
        elif out.stopped is not None:
            out.put({"file": path, "code": "not_run"})
        else:
            md5 = md5s[path]
            out.put({"file": path, "md5": md5, "code": "found" if md5 in held else "not_found", **held.get(md5, {})})
    return out.finish()


def main(argv=None):
    p = cli.records_parser(__doc__, zotero=True, dry_run=True)
    args = cli.parse(p, argv)
    return cli.run(lambda: have(p, args))


if __name__ == "__main__":
    raise SystemExit(main())
