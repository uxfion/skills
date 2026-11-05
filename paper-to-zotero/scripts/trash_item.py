#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Move Zotero items or attachments to the trash (undoable for 30 days), or restore them, once the user has confirmed the list.

Run -n first and show its list to the user: superseded attachments, duplicate items the user agreed to drop, stray
attachments. The trash is a 30-day undo: the user, or --restore, brings an item back, and Zotero deletes for good
what has sat there longer (its trashAutoEmptyDays setting, 30 by default). Nothing here empties the trash.

The items: keys or citation keys, an attachment or a note by its own key; - reads a list from stdin (a value a line,
or our JSON lines: their `key`). For each: read it; already where it should be -> skipped; else PATCH {"deleted": 1}
(--restore: 0) with its version and read it back. Trashing a parent takes its attachments and notes along, as in
Zotero; `children` says how many. Trashing a PDF takes its structured package along (the zip beside it under its
title; `packages`); restoring the PDF leaves the package in the trash: restore it by the key that line gave.

stdout: one line per item {key, cite?, code, itemType, title, parent, parent_title?, children?, packages?: [{key,
code}], version, retried}:
  ok                 moved to the trash (--restore: restored) and read back so
  skipped            reason already_trashed, or not_in_trash with --restore
  not_found          {item, code}: no item has this key or citation key; ambiguous: several do (`keys`)
  version_conflict   the item changed twice while it was being written; wait, then rerun
  write_denied       the library is not editable
  readback_mismatch  the write was accepted, but the item still shows its old state
  not_run            Zotero stopped answering before this item
Exit 0 = every item ok or skipped; 1 = some item not, then stderr's last line is {"summary": {total, ok, skipped,
failed}}; 2 = cannot check (zotero_unreachable, local_api_disabled, no_key, key_rejected, server_mismatch), then
stderr's last line is {code, hint}.

Examples:
  p2z.py trash -n ABCD1234 EFGH5678          # show the list to the user first
  p2z.py trash ABCD1234 EFGH5678             # after the user confirmed it
  p2z.py children ABCD1234 | jq -c 'select(.title == "Snapshot")' | p2z.py trash -n -
  p2z.py trash --restore ABCD1234            # undo
"""
from p2zlib import cli, paper, zotero


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
    d = zotero.data(item)
    following = zot.packages(d["parentItem"], d.get("title")) if not args.restore and paper.is_pdf(d) and d.get("parentItem") else []
    line = {**describe(zot, item), **zot.trash(key, restore=args.restore, item=item, dry_run=args.dry_run)}
    if following:
        line["packages"] = [{"key": c["key"], **zot.trash(c["key"], item=c, dry_run=args.dry_run)} for c in following]
    return line


def configure(p):
    p.add_argument("--restore", action="store_true", help="take the items out of the trash instead")


def main(argv=None):
    return cli.main_items(__doc__, process, argv, configure=configure)


if __name__ == "__main__":
    raise SystemExit(main())
