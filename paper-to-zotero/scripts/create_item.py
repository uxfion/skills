#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Create each record's Zotero item, filed and tagged in one POST: the record's `saved`.

The item is the record's `item`; it goes into the record's `collection` (one or several, each a key, a path from p2z.py
collections or a name one collection has) with its `citationKey`, which Zotero then keeps, and with its tags: the
record's `tags` (else the item's own), p2z.py draft's automatic ones, together with the curated tags of the paper's tags
file, <scratch>/paper-to-zotero/tags/<slug>.json (a tag in both takes the file's type). Before anything is posted the
library is looked up again (the lookup that writes `found` and `near_matches`, p2z.py have's): a paper added since the
last prepare is caught here. Right before the POST the record gets `saved: {pending: true, at}`; then `saved: {key,
version, citationKey, created_at}`. A run cut off between the two leaves the pending mark: the next run's lookup finds
the item that POST created and records it, or creates it when there is none, so a rerun is always safe. What comes back
is compared with what was sent (collections, tags, citation key).

stdout: one line per record {slug, code, key?, version?, citationKey?, collection?, citation_key_hint?}; collection
lists the item's collections, each {key, path}.
  ok                   created (with -n: would be, with the `tags` it would carry; nothing written)
  skipped              reason saved (this run created it) | exists (the library has it: `found`, matched_by)
  possible_duplicate   the library may hold it (`near_matches`, the same_paper `handoff` a judge answers with
                       p2z.py answer); nothing is created meanwhile
  untagged             the paper's tags file (`tags_file`) is not written yet: tag it (references/tagging.md), then
                       run this again; nothing created meanwhile
  no_item | item_invalid | no_collection | collection_not_found | invalid_tags    the record's fault (invalid_tags:
                       the record's tags or the tags file's; no_collection only for a paper the library does not
                       hold): nothing written
  write_denied | write_failed      Zotero did not take it (nothing created; the pending mark is gone)
  readback_mismatch    created (`saved` written) but not filed, tagged or keyed as sent: fix it with p2z.py tag
                       or p2z.py update
citation_key_hint: the key holds a character TeX treats specially (^ _ & % $ # { } ~ \\), and the key without them.
Exit 0 = every record created or skipped; 1 = not, then stderr's last line is {"summary": {total, ok, skipped,
failed}}; 2 = cannot go on (Zotero not running, local API off, no key, the key rejected, another Zotero than the
key's), then stderr's last line is {code, hint}. A file that is not a record stops the run before anything is
written.

Example:
  p2z.py create <scratch>/paper-to-zotero/records/*.json
"""
import json

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
        raise cli.Stop("item_invalid", problems=problems, hint="Fix the record's item (p2z.py check shows what Zotero "
                                                               "makes of each field), then run this again.")
    named = rec.keys_of("collection")    # none is asked for only once the library is known not to hold the paper
    if ctx["tree"] is None:
        ctx["tree"] = ctx["zot"].collections()
    collections = list(dict.fromkeys(ctx["zot"].collection(value, ctx["tree"]) for value in named))
    curated = curated_tags(rec)
    own = rec["tags"] if "tags" in rec else item.get("tags") or []
    tags, problems, _ = paper.normalize_tags(own + (curated or []) if isinstance(own, list) else own)
    if problems:
        raise cli.Stop("invalid_tags", problems=problems, hint='Tags are a list of "name" or {"tag": "name", "type": 0|1}: '
                                                              "fix the record's tags or the paper's tags file.")
    obj = {**{k: v for k, v in item.items() if k not in ("tags", "collections")}, "collections": collections, "tags": tags}
    cite = str(rec.get("citationKey") or "").strip()
    if cite:
        obj["citationKey"] = cite
    return obj, collections


def curated_tags(rec):
    """The paper's tags file (run.tags_file) -> its tag list; None while it is not written; invalid_tags when it
    is not a JSON list."""
    path = run.tags_file(rec)
    try:
        tags = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise cli.Stop("invalid_tags", tags_file=str(path), detail=str(e),
                       hint="The paper's tags file is not JSON: its tagger writes it again.") from None
    if not isinstance(tags, list):
        raise cli.Stop("invalid_tags", tags_file=str(path), hint='A tags file holds a JSON list of "name" or '
                                                                  '{"tag": "name", "type": 0}.')
    return tags


def saved_line(saved, refs):
    cite = saved.get("citationKey")
    hint = paper.suggested_cite(cite)
    return {"key": saved["key"], "version": saved.get("version"), **({"citationKey": cite} if cite else {}),
            "collection": refs,
            **({"citation_key_hint": {"suggested": hint, "why": "TeX treats ^ _ & % $ # { } ~ \\ specially: ask the user, "
                                      "then p2z.py update KEY --set citationKey=<suggested>"}} if hint else {})}


def process(rec, ctx):
    saved = rec.get("saved") if isinstance(rec.get("saved"), dict) else {}
    if saved.get("key"):
        return cli.skipped("saved", key=saved["key"])
    obj, collections = payload_of(rec, ctx)
    zot, args, refs = ctx["zot"], ctx["args"], zotero.collection_refs(collections, ctx["tree"])
    found, near = run.look_up(rec, zot)
    if found["code"] == "found":
        if saved.get("pending"):  # the POST of a run cut off did create it
            rec["saved"] = {"key": found["key"], "version": found["version"], "citationKey": found["citationKey"] or None,
                            "created_at": saved.get("at")}
            return {"code": "ok", "recovered": True, **saved_line(rec["saved"], refs)}
        return cli.skipped("exists", key=found["key"], matched_by=found["matched_by"])
    if not collections:
        raise cli.Stop("no_collection", hint="Put the destination in the record's collection: its key, path or name.")
    if run.unsettled(rec):
        return {"code": "possible_duplicate", "near_matches": run.near_lines(near), "handoff": run.ask_same_paper(rec),
                "hint": run.HINT_NEAR}
    if not run.tags_file(rec).exists():
        return {"code": "untagged", "tags_file": str(run.tags_file(rec)),
                "hint": "The paper has no tags file yet: its tagger writes it (references/tagging.md); then run this "
                        "again. Nothing was created."}
    if args.dry_run:
        return {"code": "ok", "title": obj["title"][:80], "collection": refs, "tags": [t["tag"] for t in obj["tags"]]}
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
    line = saved_line(rec["saved"], refs)
    sent_tags = {(t["tag"], t["type"]) for t in obj["tags"]}
    wrong = {"collections": [c for c in collections if c not in (got.get("collections") or [])],
             "tags": sent_tags != {(t.get("tag"), t.get("type", 0)) for t in got.get("tags") or []},
             "citationKey": bool(obj.get("citationKey")) and got.get("citationKey") != obj["citationKey"]}
    if any(wrong.values()):
        return {"code": "readback_mismatch", **line, "wrong": {k: v for k, v in wrong.items() if v},
                "hint": f"The item exists (saved), but is not filed, tagged or keyed as sent: fix it with "
                        f"p2z.py tag / p2z.py update {created['key']}."}
    return {"code": "ok", **line}


def main(argv=None):
    return cli.main_records(__doc__, process, argv, setup=setup, zotero=True, dry_run=True, all_valid=True)


if __name__ == "__main__":
    raise SystemExit(main())
