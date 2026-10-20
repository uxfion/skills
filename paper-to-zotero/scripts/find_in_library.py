#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Look each record's paper up in the Zotero library: the record's `found` and `near_matches` (read-only).

Only an identifier confirms a paper is there: the DOI (a doi.org url and an Extra "DOI:" line count), else the
arXiv id — unless the record's item has a DOI of its own that the library lacks: then an arXiv hit is its preprint,
a near match. A title never confirms: the same title, or one title inside the other, is a near match, and so is
the same title under another DOI (a preprint's 10.48550 DOI, a correction notice). The agent settles a near match
in the record: `same_as: KEY` (it is this paper) or KEY added to `distinct_from` (another paper), then runs this
again; items in distinct_from are left out at every step.

`found` is computed again only when it is not done: absent (an older run's `found`, written without `from`,
counts as absent), or the item's identifiers or title, same_as or distinct_from changed since; each line says why
(`reason`). A paper added to the library after the lookup is caught by create_item.py, which looks again before
it creates anything.

stdout: one line per record {slug, code, reason?, key?, citationKey?, matched_by?, title?, attachments?,
near_matches?}, then {"summary"}.
  found        in the library (`matched_by`: doi | arxiv | same_as; `duplicates` when several items match)
  not_found    not in the library; nothing is like it
  near_match   not confirmed, but `near_matches` lists what is like it, each with its reason: the agent's to settle
  no_item      the record has no `item` to look up
  skipped      reason done: `found` is up to date
Exit 0 = every record found, not found or done; 1 = a near match or no item; 2 = cannot check
(zotero_unreachable, local_api_disabled).

Example:
  uv run scripts/find_in_library.py <work>/records/*.json
"""
from p2zlib import cli, run, zotero

def setup(args, records):
    return zotero.Zotero(args.base_url)


def summary(found, near):
    if found["code"] == "found":
        return {"code": "found", "key": found["key"], "citationKey": found["citationKey"] or None,
                "matched_by": found["matched_by"], "title": found["title"][:80], "attachments": len(found["attachments"]),
                **({"duplicates": found["duplicates"]} if found.get("duplicates") else {})}
    if near:
        return {"code": "near_match", "near_matches": run.near_lines(near), "hint": run.HINT_NEAR}
    return {"code": "not_found"}


def process(rec, zot):
    if not rec.item:
        return {"code": "no_item", "hint": run.HINT_NO_ITEM}
    due = run.due(rec, "found")
    if due is None:
        return cli.skipped("done", found=rec["found"]["code"], **({"key": rec["found"]["key"]} if rec["found"].get("key") else {}))
    found, near = run.look_up(rec, zot)
    line = summary(found, near)
    return {"code": line.pop("code"), "reason": due, **line}


def main(argv=None):
    return cli.main_records(__doc__, process, argv, setup=setup, zotero=True, dry_run=True, answers=("found", "not_found"))


if __name__ == "__main__":
    raise SystemExit(main())
