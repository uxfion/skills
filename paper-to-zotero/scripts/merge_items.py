#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Merge what one Zotero item holds into its duplicate, keeping one item whole; nothing is deleted.

--keep and --drop name the two items (an 8-character key or a citation key). The plan, shown by --dry-run and
carried out without it:
  fields        every field of the kept item's type (from the schema, matched across types by base field, so a
                journal's publicationTitle fills a conference paper's proceedingsTitle): a field the kept item
                leaves empty takes the dropped item's value (creators only when the kept item has none); `extra`
                takes the dropped item's lines it lacks; a field both fill differently is listed under `conflicts`
                and left as the kept item has it; a dropped value with no field in the kept type, `not_carried`
  collections   the union, without `tmp` (unless `tmp` is all there is)
  tags          the union
  attachments   the dropped item's PDFs whose md5 the kept item lacks, and its notes, move under the kept item
                (parentItem); its other attachments (snapshots, links, a PDF the kept item already has) stay and
                are listed under `left_with_drop`; children in the trash are left alone
The kept item is written in one PATCH with its version (changed meanwhile: read again, planned again and tried
once more), each moved child in its own; then everything is read back. The dropped item is left in place: the
output ends with the trash_item.py line to run once the user confirms.

stdout: one line {code, keep: {key, title, citationKey}, drop: {...}, fields: {fill, conflicts, not_carried},
collections: {before, after}, tags: {added}, move, left_with_drop, next, dry_run? | version, retried}.
  ok                 merged and read back so (--dry-run: the plan; nothing written)
  skipped            reason nothing_to_merge: the kept item already holds everything
  not_found          no item with that key
  cite_not_found     no top-level item carries the citationKey; cite_ambiguous: several do (`keys`), pass the key
  same_item          --keep and --drop name one item
  not_top_level      one of them is an attachment or a note; trashed: one is in the trash
  version_conflict   an item (`key`) changed twice while it was being written; wait, then rerun the dry run
  write_denied       the library is not editable; write_failed: Zotero rejected the write of `key` (detail)
  readback_mismatch  the writes were accepted, but the kept item does not show them (`wrong` fields, `unmoved`)
Exit 0 = ok or skipped, 1 = any other code, 2 = cannot check (zotero_unreachable, local_api_disabled, no_key,
key_rejected, server_mismatch, config_unreadable).

Examples:
  uv run scripts/merge_items.py --keep 9NB4JT94 --drop 3G7J5DN9 --dry-run   # show the plan to the user first
  uv run scripts/merge_items.py --keep goodfellow2014generative --drop 3G7J5DN9
"""
import json

from p2zlib import cli, paper, zotero

NOT_FIELDS = {"key", "version", "itemType", "collections", "tags", "relations", "dateAdded", "dateModified",
              "deleted", "parentItem"}
SHOWN = 160  # characters of a long value shown in `conflicts`


def resolve(zot, name):
    key = name if cli.KEY_RE.match(name) else zot.resolve_cite(name)
    item = zot.item(key)
    if item is None:
        raise cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND, key=key)
    return item


def empty(value):
    return value in (None, "", [], {})


def short(value):
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return s if len(s) <= SHOWN else s[:SHOWN] + "…"


def plan_merge(keep, drop, keep_children, drop_children, tmp_keys, maps):
    """-> (the plan as shown, the PATCH body for the kept item)."""
    k, d = zotero.data(keep), zotero.data(drop)
    keep_fields = maps.get(k.get("itemType")) or {f: f for f in k if f not in NOT_FIELDS}
    by_base = {base: field for field, base in
               (maps.get(d.get("itemType")) or {f: f for f in d if f not in NOT_FIELDS}).items()}
    fill, conflicts, carried = {}, {}, set()
    for field, base in list(keep_fields.items()) + [("creators", "creators")]:
        source = by_base.get(base) or (field if field in d else None)
        if source is None or source not in d:
            continue
        carried.add(source)
        kv, dv = k.get(field), d[source]
        if field == "extra":
            have = [ln for ln in (kv or "").splitlines() if ln.strip()]
            add = [ln for ln in (dv or "").splitlines() if ln.strip() and ln not in have]
            if add:
                fill[field] = "\n".join(have + add)
        elif empty(kv) and not empty(dv):
            fill[field] = dv
        elif not empty(kv) and not empty(dv) and kv != dv:
            conflicts[field] = {"keep": short(kv), "drop": short(dv)}
    not_carried = sorted(f for f, v in d.items() if f not in NOT_FIELDS and f not in carried and not empty(v))
    union = list(dict.fromkeys((k.get("collections") or []) + (d.get("collections") or [])))
    collections = [c for c in union if c not in tmp_keys] or union
    tags, seen = list(k.get("tags") or []), {t.get("tag") for t in k.get("tags") or []}
    for t in d.get("tags") or []:
        if t.get("tag") not in seen:
            tags.append(t)
            seen.add(t.get("tag"))
    keep_md5 = {zotero.data(c).get("md5") for c in keep_children if paper.is_pdf(zotero.data(c))}
    move, left = [], []
    for c in drop_children:
        cd = zotero.data(c)
        entry = {"key": c["key"], "itemType": cd.get("itemType"), "title": cd.get("title") or short(cd.get("note") or "")}
        if cd.get("itemType") == "note" or (paper.is_pdf(cd) and cd.get("md5") not in keep_md5):
            move.append(entry)
        else:
            left.append({**entry, "why": "the kept item has this PDF" if paper.is_pdf(cd) else "not a PDF or a note"})
    patch = dict(fill)
    if collections != (k.get("collections") or []):
        patch["collections"] = collections
    if len(tags) != len(k.get("tags") or []):
        patch["tags"] = tags
    return {"fields": {"fill": {f: short(v) for f, v in fill.items()}, "conflicts": conflicts, "not_carried": not_carried},
            "collections": {"before": k.get("collections") or [], "after": collections},
            "tags": {"added": [t.get("tag") for t in tags[len(k.get("tags") or []):]]},
            "move": move, "left_with_drop": left}, patch


def write(zot, key, plan, item=None):
    """zot.update, its failures naming the item: a merge writes several."""
    try:
        return zot.update(key, plan, item)
    except cli.Stop as stop:
        stop.extra.setdefault("key", key)
        raise


def merge(zot, args):
    if not args.dry_run:
        zot.write_headers()
    keep, drop = resolve(zot, args.keep), resolve(zot, args.drop)
    if keep["key"] == drop["key"]:
        raise cli.Stop("same_item", hint="--keep and --drop name the same item.", key=keep["key"])
    for item in (keep, drop):
        if not zotero.is_top(item):
            raise cli.Stop("not_top_level", hint="Both must be top-level items.", key=item["key"])
        if zotero.in_trash(item):
            raise cli.Stop("trashed", hint="That item is in the trash; restore it first (trash_item.py --restore) or pick another.",
                           key=item["key"])
    keep_children, drop_children = ([c for c in zot.children(it["key"]) if not zotero.in_trash(c)] for it in (keep, drop))
    tmp_keys = {key for key, c in zot.collections().items() if c["name"] == "tmp"}
    maps = {t: v["base_of"] for t, v in zot.item_types().items()}

    def plan(item):
        return plan_merge(item, drop, keep_children, drop_children, tmp_keys, maps)

    shown, patch = plan(keep)
    head = {side: {"key": it["key"], "title": zotero.data(it).get("title"), "citationKey": zotero.data(it).get("citationKey")}
            for side, it in (("keep", keep), ("drop", drop))}
    nxt = f"uv run scripts/trash_item.py --key {drop['key']} --dry-run   # once the user confirms the drop"
    if not patch and not shown["move"]:
        cli.emit(cli.skipped("nothing_to_merge", **head, **shown, next=nxt))
        return cli.OK
    if args.dry_run:
        cli.emit(cli.ok(**head, **shown, next=nxt, dry_run=True))
        return cli.OK

    item, sent, retried = write(zot, keep["key"], lambda it: plan(it)[1] or None, keep)
    shown = plan(item)[0]
    for c in shown["move"]:
        write(zot, c["key"], lambda it: None if zotero.data(it).get("parentItem") == keep["key"] else {"parentItem": keep["key"]})

    after = zot.item(keep["key"]) or {}
    a, sent = zotero.data(after), sent or {}
    wrong = [f for f, v in sent.items() if f not in ("tags", "collections") and a.get(f) != v]
    if "collections" in sent and set(a.get("collections") or []) != set(sent["collections"]):
        wrong.append("collections")
    if "tags" in sent and {t.get("tag") for t in a.get("tags") or []} != {t.get("tag") for t in sent["tags"]}:
        wrong.append("tags")
    under = {c["key"] for c in zot.children(keep["key"])}
    unmoved = [c["key"] for c in shown["move"] if c["key"] not in under]
    line = {**head, **shown, "version": after.get("version"), "retried": retried, "next": nxt}
    if wrong or unmoved:
        raise cli.Stop("readback_mismatch", hint="The writes were accepted, but the kept item does not show them all; look at it in Zotero.",
                       **line, **({"wrong": wrong} if wrong else {}), **({"unmoved": unmoved} if unmoved else {}))
    cli.emit(cli.ok(**line))
    return cli.OK


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("--keep", required=True, metavar="KEY|CITE", help="the item that stays and gains")
    p.add_argument("--drop", required=True, metavar="KEY|CITE", help="the duplicate whose information moves over")
    p.add_argument("--dry-run", action="store_true", help="print the plan; write nothing")
    cli.add_base_url(p)
    args = p.parse_args(argv)
    return cli.run(lambda: merge(zotero.Zotero(args.base_url), args))


if __name__ == "__main__":
    raise SystemExit(main())
