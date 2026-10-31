#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Set the collections and tags of existing Zotero items, or add to and take from them; re-running is a no-op.

A change says, for one item:
  collection         its collections become exactly these: a key or a list of keys; null, "none" or [] clears
  add_collection     add it to these (a key or a list), keeping its others
  remove_collection  take it out of these, keeping its others; one it is not in is a no-op, so it is not looked up
  tags               its COMPLETE tag set: a list of "name" (type 0) or {"tag": "name", "type": 0|1} (0 manual,
                     1 automatic); a tag given twice keeps its last occurrence, with a warning on stderr
  add_tags           tags to add to the ones it has, in the same form
  remove_tags        take these off (a tag name or a list of names, whatever their type), keeping its others; one
                     it does not have is a no-op
collection excludes add_collection and remove_collection, which combine (a move that keeps the others); tags
excludes add_tags and remove_tags, which combine the same way.

--batch FILE holds JSON lines, a change per line, each naming its item by "key" or by "cite" (its citationKey) —
the batch format update_item.py reads too:
  {"cite": "liu2022progressive", "add_collection": "NEWCOLL1", "remove_collection": ["OLDCOLL1"]}
  {"key": "ABCD1234", "tags": ["CVPR", {"tag": "Deep learning", "type": 1}]}
--key / --cite with --collection, --add-collection, --remove-collection, --tags-file, --add-tags-file (a file
holding a tag list as above), --remove-tags (tag names) give every item they name the same change. An item named
twice is handled once when both ask the same; two different changes for one item are invalid_changes.

Nothing is written unless every change passes its checks: each cite names one top-level item, each item exists,
only top-level items change collections, each destination collection is in the collection tree and not in the
trash (this script never creates one). Then one POST per 50 items, each sent with its version (an item that
changed meanwhile is read again, planned again and sent once more), and each item is checked in Zotero's reply.

stdout: one line per item {key, cite?, code, title, collection?: {from, to}, tags_added?, tags_removed?, version},
then {"summary": {total, ok, skipped, failed[, dry_run]}}.
  ok                    written, and Zotero's reply shows it (--dry-run: would be written)
  skipped               reason unchanged: the item already is as asked
  cite_not_found        no top-level item carries the citationKey; cite_ambiguous: several do (`keys`), give the key
  not_found             no item with that key
  not_a_parent          an attachment or note is in no collection: name its parent item (`parent`)
  collection_not_found  a destination is not in the collection tree, or is in the trash (`collections`)
  not_run               another item failed a check, so nothing was written; fix that one and rerun
  version_conflict      the item changed meanwhile, and again after it was read anew; rerun
  write_failed          Zotero did not take this item (`status`, `detail`); rerun
  write_denied          the library is not editable
  readback_mismatch     Zotero took the write, but the item does not show it (`now`)
invalid_changes is one line instead: the changes are malformed (`detail` names each entry and what is wrong with
it), and nothing is written.
Exit 0 = every item ok or skipped, 1 = not (or invalid_changes), 2 = cannot check (zotero_unreachable,
local_api_disabled, no_key, key_rejected, server_mismatch).

Examples:
  uv run scripts/file_and_tag.py --batch changes.jsonl --dry-run    # show the change list to the user first
  uv run scripts/file_and_tag.py --batch changes.jsonl              # after the user confirmed it
  uv run scripts/file_and_tag.py --cite liu2022progressive --add-collection NEWCOLL1 --remove-collection OLDCOLL1
  uv run scripts/file_and_tag.py --key ABCD1234 EFGH5678 --add-tags-file tags.json
  uv run scripts/file_and_tag.py --cite liu2022progressive --remove-tags "to read" "Deep learning, theory"
"""
import json
from pathlib import Path

from p2zlib import cli, paper, zotero

FIELDS = ("collection", "add_collection", "remove_collection", "tags", "add_tags", "remove_tags")


def invalid(problems):
    return cli.Stop("invalid_changes", hint="Fix the changes, then rerun; nothing was written.", detail=problems)


def read_json(path, what):
    """-> (the file's JSON, a problem or None)."""
    try:
        return json.loads(Path(path).expanduser().read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"{what} {path}: no such file"
    except (OSError, ValueError) as e:
        return None, f"{what} {path}: {e}"


def collection_keys(field, value):
    """A collection field as a list of keys -> (keys, problem or None); for collection, null, "none" or "" clears."""
    if field == "collection" and (value is None or isinstance(value, str) and value.strip().lower() in ("", "none")):
        return [], None
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not all(isinstance(v, str) and cli.KEY_RE.match(v.strip()) for v in values):
        return [], f"{field}: an 8-character collection key or a list of them, not {json.dumps(value, ensure_ascii=False)}"
    return list(dict.fromkeys(v.strip() for v in values)), None


def tag_names(value):
    """remove_tags as a list of names -> (names, problem or None)."""
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
        return [], f"remove_tags: a tag name or a list of them, not {json.dumps(value, ensure_ascii=False)}"
    return list(dict.fromkeys(v.strip() for v in values)), None


def parse_change(raw, where=""):
    """A change's fields, checked -> (change, problems): the collection fields as key lists, the tag fields normalized."""
    change, problems = {}, []
    for field in raw:
        if field not in FIELDS + ("key", "cite"):
            cli.log(f"{where}ignoring the field {field!r}")
    for field in (f for f in FIELDS if f in raw):
        if field == "remove_tags":
            change[field], bad = tag_names(raw[field])
            problems += [bad] if bad else []
        elif field.endswith("tags"):
            change[field], bad, warnings = paper.normalize_tags(raw[field])
            for w in warnings:
                cli.log(f"{where}{field}: {w}")
            problems += [f"{field}: {b}" for b in bad]
        else:
            change[field], bad = collection_keys(field, raw[field])
            problems += [bad] if bad else []
    if not change:
        problems.append("no change: give collection, add_collection, remove_collection, tags, add_tags or remove_tags")
    if "collection" in change and ("add_collection" in change or "remove_collection" in change):
        problems.append("collection replaces, add_collection / remove_collection edit: give one or the other")
    if "tags" in change and ("add_tags" in change or "remove_tags" in change):
        problems.append("tags replaces, add_tags / remove_tags edit: give one or the other")
    both = [k for k in change.get("add_collection", []) if k in change.get("remove_collection", [])]
    both += [t["tag"] for t in change.get("add_tags", []) if t["tag"] in change.get("remove_tags", [])]
    if both:
        problems.append(f"added and removed at once: {', '.join(both)}")
    return change, [where + p for p in problems]


def from_batch(path):
    """The --batch file -> entries {key | cite, change, name}; invalid_changes when any of it is malformed."""
    found, problems = cli.batch_entries(path)
    problems = [f"--batch {p}" if p.startswith(str(path)) else p for p in problems]
    entries = []
    for b in found:
        change, bad = parse_change(b["entry"], f"{b['where']}: ")
        problems += bad
        entries.append({"key": b["key"], "cite": b["cite"], "change": change, "name": b["where"]})
    if problems:
        raise invalid(problems)
    return entries


def from_flags(args):
    """--key / --cite and the change flags -> one entry per item named, all with the same change."""
    raw, problems = {}, []
    if args.collection is not None:
        raw["collection"] = args.collection
    for field, values in (("add_collection", args.add_collection), ("remove_collection", args.remove_collection)):
        if values:
            raw[field] = cli.split(values)
    for field, flag, path in (("tags", "--tags-file", args.tags_file), ("add_tags", "--add-tags-file", args.add_tags_file)):
        if path:
            raw[field], problem = read_json(path, flag)
            problems += [problem] if problem else []
    if args.remove_tags:
        raw["remove_tags"] = args.remove_tags
    if problems:
        raise invalid(problems)
    change, problems = parse_change(raw)
    if problems:
        raise invalid(problems)
    return ([{"key": k, "cite": None, "change": change, "name": f"key {k}"} for k in args.key]
            + [{"key": None, "cite": c, "change": change, "name": f"cite {c}"} for c in args.cite])


def head(e):
    return cli.head(e["key"], e["cite"])


def once(entries):
    """An item several entries name: handled once when they ask the same, invalid_changes when not."""
    first, out, problems = {}, [], []
    for e in entries:
        twin = first.setdefault(e["key"], e) if e["key"] else e
        if twin is e:
            out.append(e)
        elif twin["change"] == e["change"]:
            cli.log(f"{e['name']} names {e['key']} again; handled once")
        else:
            problems.append(f"{twin['name']} and {e['name']} both name item {e['key']}: merge them into one change")
    if problems:
        raise invalid(problems)
    return out


def destinations(change):
    return change.get("collection", []) + change.get("add_collection", [])


def refusal(item, change, tree):
    """Why this item cannot take the change (a Stop), or None."""
    if item is None:
        return cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND)
    parent = zotero.data(item).get("parentItem")
    if parent and any(f in change for f in ("collection", "add_collection", "remove_collection")):
        return cli.Stop("not_a_parent", hint="Only top-level items are in collections; name the parent item.", parent=parent)
    missing = [k for k in destinations(change) if k not in tree]
    if missing:
        return cli.Stop("collection_not_found", collections=missing,
                        hint="Pick the key from read_library.py collections --tree (one in the trash is not a destination); "
                             "make_collection.py creates a new one.")
    return None


def tag_map(tags):
    return {t.get("tag"): t.get("type", 0) for t in tags or [] if isinstance(t, dict)}


def tag_list(mapping):
    return [{"tag": t, "type": k} for t, k in mapping.items()]


def plan(data, change):
    """-> (what to send: {collections?, tags?}, the line's fields: {collection?: {from, to}, tags_added?, tags_removed?})."""
    body, fields = {}, {}
    has = list(data.get("collections") or [])
    want = change.get("collection")
    if "add_collection" in change or "remove_collection" in change:
        grown = has + [k for k in change.get("add_collection", []) if k not in has]
        want = [k for k in grown if k not in change.get("remove_collection", [])]
    if want is not None and set(want) != set(has):
        body["collections"], fields["collection"] = want, {"from": has, "to": want}
    tags = change.get("tags")
    if "add_tags" in change or "remove_tags" in change:
        kept = {**tag_map(data.get("tags")), **tag_map(change.get("add_tags", []))}
        tags = tag_list({t: k for t, k in kept.items() if t not in change.get("remove_tags", [])})
    if tags is not None:
        now, then = tag_map(data.get("tags")), tag_map(tags)
        added = {t: k for t, k in then.items() if now.get(t) != k}
        removed = {t: k for t, k in now.items() if then.get(t) != k}
        if added or removed:
            body["tags"] = tags
            fields.update({name: tag_list(m) for name, m in (("tags_added", added), ("tags_removed", removed)) if m})
    return body, fields


def mismatch(data, body):
    """What of body the item does not show, as the item has it: {collections?, tags?}."""
    now = {}
    if "collections" in body and set(data.get("collections") or []) != set(body["collections"]):
        now["collections"] = data.get("collections") or []
    if "tags" in body and tag_map(data.get("tags")) != tag_map(body["tags"]):
        now["tags"] = data.get("tags") or []
    return now


def settle(zot, e, result):
    """The line's update for Zotero's answer to one object."""
    retried = {"retried": True} if result.get("retried") else {}
    if "failed" in result:
        return {**result["failed"], **retried}
    if "unchanged" in result:
        return {**cli.skipped("unchanged"), **retried}
    after = result["ok"] if "data" in result["ok"] else zot.item(e["key"]) or {}
    now = mismatch(zotero.data(after), e["body"])
    if now:
        return {"code": "readback_mismatch", "version": after.get("version"), "now": now,
                "hint": "Zotero took the write, but the item does not show it (it may have normalized a value); look at it, then rerun."}
    return {"version": after.get("version"), **retried}


def apply(zot, entries, dry_run):
    """Every check for every entry first; any failure and nothing is written. -> the lines."""
    cites = [e["cite"] for e in entries if e["cite"]]
    hits = zot.resolve_cites(cites) if cites else {}
    for e in entries:
        if e["cite"] and len(hits[e["cite"]]) != 1:
            e["line"] = zot.cite_failure(e["cite"], hits[e["cite"]]).line(**head(e))
        elif e["cite"]:
            e["key"] = hits[e["cite"]][0]
    entries = once(entries)
    named = [e for e in entries if "line" not in e]
    items = zot.items([e["key"] for e in named])
    tree = zot.collections() if any(destinations(e["change"]) for e in named) else {}
    for e in named:
        stop = refusal(items.get(e["key"]), e["change"], tree)
        if stop:
            e["line"] = stop.line(**head(e))
    if any("line" in e for e in entries):
        return [e.get("line") or {**head(e), "code": "not_run"} for e in entries]

    def planned(e, item):
        """Plan the entry on the item as it is -> the object to send, or None; the line follows the plan."""
        e["body"], fields = plan(zotero.data(item), e["change"])
        title, version = zotero.data(item).get("title"), item.get("version")
        e["line"] = ({**head(e), "code": "ok", "title": title, **fields, "version": version} if e["body"]
                     else {**head(e), **cli.skipped("unchanged"), "title": title, "version": version})
        return {"key": e["key"], "version": version, **e["body"]} if e["body"] else None

    objects = [planned(e, items[e["key"]]) for e in entries]
    todo = [(e, obj) for e, obj in zip(entries, objects) if obj]
    if dry_run:
        for e, _ in todo:
            e["line"]["dry_run"] = True
    elif todo:
        results = zot.post([obj for _, obj in todo], replan=lambda i, item: planned(todo[i][0], item))
        for (e, _), result in zip(todo, results):
            e["line"].update(settle(zot, e, result))
    return [e["line"] for e in entries]


def run(args):
    entries = from_batch(args.batch) if args.batch else from_flags(args)
    zot = zotero.Zotero(args.base_url)
    if not args.dry_run:
        zot.write_headers()
    return cli.finish(apply(zot, entries, args.dry_run), extra={"dry_run": True} if args.dry_run else None)


def main(argv=None):
    p = cli.parser(__doc__)
    cli.add_targets(p)
    p.add_argument("--batch", metavar="CHANGES.jsonl", help='JSON lines, a change per line, each naming its item by "key" or "cite"')
    p.add_argument("--collection", metavar="KEY", help="the items' collections become exactly this one; 'none' clears them")
    p.add_argument("--add-collection", nargs="+", action="extend", default=[], metavar="KEY", help="add the items to these")
    p.add_argument("--remove-collection", nargs="+", action="extend", default=[], metavar="KEY",
                   help="take the items out of these")
    p.add_argument("--tags-file", metavar="TAGS.json", help="the items' complete tag set")
    p.add_argument("--add-tags-file", metavar="TAGS.json", help="tags to add to the ones each item has")
    p.add_argument("--remove-tags", nargs="+", action="extend", default=[], metavar="NAME",
                   help="take these tags off the items, keeping their others (each value one name, commas and all)")
    p.add_argument("--dry-run", action="store_true", help="show what would be written; write nothing")
    cli.add_base_url(p)
    args = cli.targets_of(p, p.parse_args(argv), required=False)
    named = args.key or args.cite
    flags = (args.collection is not None or args.add_collection or args.remove_collection or args.tags_file
             or args.add_tags_file or args.remove_tags)
    if args.batch and (named or flags):
        p.error("--batch names the items and their changes in the file: leave out --key, --cite and the change flags")
    if not args.batch and not named:
        p.error("name the items with --key / --cite, or pass --batch")
    return cli.run(lambda: run(args))


if __name__ == "__main__":
    raise SystemExit(main())
