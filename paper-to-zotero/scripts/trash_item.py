#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Move Zotero items or attachments to the trash (undoable for 30 days), or restore them, once the user has confirmed the list.

Run --dry-run first and show its list to the user: superseded attachments, duplicate items the user agreed to drop,
stray attachments. The trash is a 30-day undo: the user, or --restore, brings an item back, and Zotero deletes for
good what has sat there longer (its trashAutoEmptyDays setting, 30 by default). Nothing here empties the trash.

Items: --key (a top-level item, or an attachment or note by its own key) and --cite (the top-level item carrying
that citationKey). For each: read it; already where it should be -> skipped; else PATCH {"deleted": 1} (--restore:
0) with its version and read it back. Trashing a parent takes its attachments and notes along, as in Zotero;
`children` says how many.

stdout: one line per item {key, cite?, code, itemType, title, parent, parent_title?, children?, version, retried},
then {"summary": {total, ok, skipped, failed}}.
  ok                 moved to the trash (--restore: restored) and read back so
  skipped            reason already_trashed, or not_in_trash with --restore
  not_found          no item with that key
  cite_not_found     no top-level item carries the citationKey; cite_ambiguous: several do (`keys`), pass --key
  version_conflict   the item changed twice while it was being written; wait, then rerun
  write_denied       the library is not editable
  readback_mismatch  the write was accepted, but the item still shows its old state
  not_run            Zotero stopped answering before this item (summary.stopped says why)
Exit 0 = every item ok or skipped, 1 = some item not, 2 = cannot check (zotero_unreachable, local_api_disabled,
no_key, key_rejected, server_mismatch).

Examples:
  uv run scripts/trash_item.py --key ABCD1234 EFGH5678 --dry-run   # show the list to the user first
  uv run scripts/trash_item.py --key ABCD1234 EFGH5678             # after the user confirmed it
  uv run scripts/trash_item.py --cite liu2022progressive --dry-run
  uv run scripts/trash_item.py --key ABCD1234 --restore            # undo
"""
from p2zlib import cli, zotero


def describe(zot, item):
    """{itemType, title, parent, parent_title?, children?}: what the user confirms."""
    d = zotero.data(item)
    out = {"itemType": d.get("itemType"), "title": d.get("title") or (d.get("note") or "")[:80],
           "parent": d.get("parentItem") or None}
    if out["parent"]:
        out["parent_title"] = zotero.data(zot.item(out["parent"])).get("title")
    elif isinstance((item.get("meta") or {}).get("numChildren"), int):
        out["children"] = item["meta"]["numChildren"]
    return out


def process(zot, key, args):
    item = zot.item(key)
    if item is None:
        raise cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND)
    return {**describe(zot, item), **zot.trash(key, restore=args.restore, item=item, dry_run=args.dry_run)}


def configure(p):
    p.add_argument("--restore", action="store_true", help="take the items out of the trash instead")


def main(argv=None):
    return cli.main_items(__doc__, process, argv, configure=configure)


if __name__ == "__main__":
    raise SystemExit(main())
