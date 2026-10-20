#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Create each record's Zotero item, filed and tagged in one POST: the record's `saved`.

The item is the record's `item`; it goes into the record's `collection` (one key or several) with the record's
`tags` (else the item's own) and its `citationKey`, which Zotero then keeps. Before anything is posted the library is
looked up again (the lookup that writes `found` and `near_matches`, find_in_library's): a paper added since the
last prepare is caught here. Right before the POST the record gets `saved: {pending: true, at}`; then
`saved: {key, version, citationKey, created_at}`. A run cut off between the two leaves the pending mark: the next
run's lookup finds the item that POST created and records it, or creates it when there is none, so a rerun is
always safe. What comes back is compared with what was sent (collections, tags, citation key).

stdout: one line per record {slug, code, key?, version?, citationKey?, collection?, citation_key_hint?}, then
{"summary"}.
  ok                   created (with --dry-run: would be; nothing written)
  skipped              reason saved (this run created it) | exists (the library has it: `found`, matched_by)
  possible_duplicate   the library has something like it (`near_matches`): the agent writes same_as or
                       distinct_from in the record, then runs this again; nothing is created meanwhile
  no_item | item_invalid | no_collection | collection_not_found | invalid_tags    the record's fault: nothing written
  write_denied | write_failed      Zotero did not take it (nothing created; the pending mark is gone)
  readback_mismatch    created (`saved` written) but not filed, tagged or keyed as sent: fix it with file_and_tag.py
                       or update_item.py
citation_key_hint: the key holds a character TeX treats specially (^ _ & % $ # { } ~ \\), and the key without them.
Exit 0 = every record created or skipped; 1 = not; 2 = cannot go on (Zotero not running, local API off, no key, the
key rejected, another Zotero than the key's); a file that is not a record stops the run before anything is written.

Example:
  uv run scripts/create_item.py <work>/records/*.json
"""
from p2zlib import cli, paper, run, zotero

def setup(args, records):
    zot = zotero.Zotero(args.base_url)
    if not args.dry_run:
        zot.write_headers()  # the server id and the key, before anything is written
    return {"zot": zot, "tree": None, "args": args}


def payload_of(rec, ctx):
    """The object to POST, from the record -> (object, its collections); a Stop for the record's own fault."""
    item = rec.get("item")
    if not isinstance(item, dict) or not item:
        raise cli.Stop("no_item", hint=run.HINT_NO_ITEM)
    problems = [p for p, bad in (("itemType is missing", not isinstance(item.get("itemType"), str) or not item["itemType"]),
                                 ("an attachment or note is no parent item", item.get("itemType") in paper.CHILD_TYPES),
                                 ("title is missing", not str(item.get("title") or "").strip()),
                                 ("key and version are Zotero's", "key" in item or "version" in item)) if bad]
    if problems:
        raise cli.Stop("item_invalid", problems=problems, hint="Fix the record's item (check_item.py shows what Zotero "
                                                               "makes of each field), then run this again.")
    collections = list(dict.fromkeys(rec.keys_of("collection")))
    if not collections:
        raise cli.Stop("no_collection", hint="Put the destination's key in the record's collection.")
    if ctx["tree"] is None:
        ctx["tree"] = ctx["zot"].collections()
    for key in collections:
        ctx["zot"].collection_scope(key, tree=ctx["tree"])
    tags, problems, _ = paper.normalize_tags(rec["tags"] if "tags" in rec else item.get("tags") or [])
    if problems:
        raise cli.Stop("invalid_tags", problems=problems, hint='Tags are a list of "name" or {"tag": "name", "type": 0|1}.')
    obj = {**{k: v for k, v in item.items() if k not in ("tags", "collections")}, "collections": collections, "tags": tags}
    cite = str(rec.get("citationKey") or "").strip()
    if cite:
        obj["citationKey"] = cite
    return obj, collections


def saved_line(saved, collections):
    cite = saved.get("citationKey")
    hint = paper.suggested_cite(cite)
    return {"key": saved["key"], "version": saved.get("version"), **({"citationKey": cite} if cite else {}),
            "collection": collections[0] if len(collections) == 1 else collections,
            **({"citation_key_hint": {"suggested": hint, "why": "TeX treats ^ _ & % $ # { } ~ \\ specially: ask the user, "
                                      "then update_item.py --key KEY --set citationKey=<suggested>"}} if hint else {})}


def process(rec, ctx):
    saved = rec.get("saved") if isinstance(rec.get("saved"), dict) else {}
    if saved.get("key"):
        return cli.skipped("saved", key=saved["key"])
    obj, collections = payload_of(rec, ctx)
    zot, args = ctx["zot"], ctx["args"]
    found, near = run.look_up(rec, zot)
    if found["code"] == "found":
        if saved.get("pending"):  # the POST of a run cut off did create it
            rec["saved"] = {"key": found["key"], "version": found["version"], "citationKey": found["citationKey"] or None,
                            "created_at": saved.get("at")}
            return {"code": "ok", "recovered": True, **saved_line(rec["saved"], collections)}
        return cli.skipped("exists", key=found["key"], matched_by=found["matched_by"],
                           **({"duplicates": found["duplicates"]} if found.get("duplicates") else {}))
    if near:
        return {"code": "possible_duplicate", "near_matches": run.near_lines(near), "hint": run.HINT_NEAR}
    if args.dry_run:
        return {"code": "ok", "title": obj["title"][:80], "collection": collections, "tags": len(obj["tags"])}
    rec["saved"] = {"pending": True, "at": run.now_iso()}
    rec.save()
    try:
        created = zot.post_one(obj, hint="Zotero did not create the item (nothing was written); see detail.")
    except cli.Stop as stop:
        if stop.exit != cli.CANNOT:  # Zotero answered: nothing was created
            rec.pop("saved")
        raise
    got = created.get("data") or {}
    if not all(k in got for k in ("collections", "tags")):  # a thin reply: read the item itself
        got = zotero.data(zot.item(created["key"])) or got
    rec["saved"] = {"key": created["key"], "version": created.get("version"), "citationKey": got.get("citationKey") or None,
                    "created_at": run.now_iso()}
    line = saved_line(rec["saved"], collections)
    sent_tags = {(t["tag"], t["type"]) for t in obj["tags"]}
    wrong = {"collections": [c for c in collections if c not in (got.get("collections") or [])],
             "tags": sent_tags != {(t.get("tag"), t.get("type", 0)) for t in got.get("tags") or []},
             "citationKey": bool(obj.get("citationKey")) and got.get("citationKey") != obj["citationKey"]}
    if any(wrong.values()):
        return {"code": "readback_mismatch", **line, "wrong": {k: v for k, v in wrong.items() if v},
                "hint": f"The item exists (saved), but is not filed, tagged or keyed as sent: fix it with "
                        f"file_and_tag.py / update_item.py --key {created['key']}."}
    return {"code": "ok", **line}


def main(argv=None):
    return cli.main_records(__doc__, process, argv, setup=setup, zotero=True, dry_run=True, all_valid=True)


if __name__ == "__main__":
    raise SystemExit(main())
