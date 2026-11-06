#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Change the tags and collections of existing Zotero items: set them, or add to and take from them; re-running is a no-op.

With change options, what follows them is the items: keys or citation keys (- reads a list from stdin: a value a
line, or our JSON lines, their `key`), all given the same change:
  --add-tag TAG, --remove-tag TAG            a tag added (type 0, manual) or taken off, whatever its type
  --add-tags-file FILE, --set-tags-file FILE  a JSON list of tags, "name" or {"tag": "name", "type": 0|1} (1
                                              automatic): added to the item's tags, or its complete tag set
  --add-collection COLL, --remove-collection COLL, --set-collection COLL
                                              a collection the item joins or leaves, or exactly these (--set-collection
                                              none: in none); COLL is a key, a path from p2z.py collections, or a name
                                              one collection has
Each option takes one value; repeat it for more. Without change options, what follows is change lists: files of JSON
lines (- reads one from stdin), a change per line naming its item by "key" or "cite", with any of
  collection         its collections become exactly these: a collection or a list; null, "none" or [] clears
  add_collection     add it to these (a collection or a list), keeping its others
  remove_collection  take it out of these, keeping its others; one it is not in is a no-op
  tags               its complete tag set, a list as in a tags file; a tag given twice keeps its last occurrence
  add_tags           tags to add to the ones it has, in the same form
  remove_tags        take these off (a tag name or a list of names, whatever their type)
  {"cite": "liu2022progressive", "add_collection": "自然图像/Diffusion", "remove_tags": "to read"}
collection excludes add_collection and remove_collection, which combine (a move that keeps the others); tags
excludes add_tags and remove_tags, which combine the same way. An item named twice is handled once when both ask
the same; two different changes for one item are invalid_changes. A field outside these is ignored, with a warning
on stderr.

Nothing is written unless every change passes its checks: each name is one item, only top-level items change
collections (tags go on attachments and notes too), each collection named is one outside the trash (this command
never creates one: p2z.py mkcol does). Then one POST per 50 items, each sent with its version (an item that changed
meanwhile is read again, planned again and sent once more), and each item is checked in Zotero's reply.

stdout: one line per item {key, cite?, code, title, collection?: {from, to}, tags_added?, tags_removed?, version}:
  ok                    written, and Zotero's reply shows it (-n: would be written)
  skipped               reason unchanged: the item already is as asked
  not_found             {item, code}: no item has this key or citation key; ambiguous: several do (`keys`)
  not_a_parent          an attachment or note is in no collection: name its parent item (`parentItem`)
  collection_not_found  a collection named is not one outside the trash (`collection`); ambiguous: several
                        collections answer to it (`candidates`)
  not_run               another item failed a check, so nothing was written; fix that one and rerun
  version_conflict      the item changed meanwhile, and again after it was read anew; rerun
  write_failed          Zotero did not take this item (`status`, `detail`); rerun
  write_denied          the library is not editable
  readback_mismatch     Zotero took the write, but the item does not show it (`now`)
Exit 0 = every item ok or skipped; 1 = not, then stderr's last line is {"summary": {total, ok, skipped, failed}};
2 = nothing was done: the changes are malformed (invalid_changes, `detail` names each entry and what is wrong;
item_line: an item line where a change belongs) or Zotero cannot be reached (zotero_unreachable, local_api_disabled,
no_key, key_rejected, server_mismatch), then stderr's last line is {code, hint, ...}.

Examples:
  p2z.py tag -n --add-tag method/diffusion madhusoodananPOCUSNetBeamformingInclusive2026
  p2z.py search POCUS | p2z.py tag -n --add-collection 超声 -
  p2z.py tag liu2022progressive --add-collection 自然图像/Diffusion --remove-collection 待读
  p2z.py tag -n changes.jsonl                  # show the change list to the user first, then without -n
"""
import json
from pathlib import Path

from p2zlib import cli, paper, zotero

FIELDS = ("collection", "add_collection", "remove_collection", "tags", "add_tags", "remove_tags")


def invalid(problems):
    return cli.Stop("invalid_changes", exit=cli.CANNOT, hint="Fix the changes, then rerun; nothing was written.",
                    detail=problems)


def read_json(path, what):
    """-> (the file's JSON, a problem or None)."""
    try:
        return json.loads(Path(path).expanduser().read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"{what} {path}: no such file"
    except (OSError, ValueError) as e:
        return None, f"{what} {path}: {e}"


def collection_values(field, value):
    """A collection field as a list of collections (keys, paths or names) -> (values, problem or None); for
    collection, null, "none", "" or [] clears."""
    values = value if isinstance(value, list) else [value]
    if field == "collection" and (value is None or [v.strip().lower() if isinstance(v, str) else v for v in values]
                                  in ([], [""], ["none"])):
        return [], None
    if not isinstance(values, list) or not values or not all(isinstance(v, str) and v.strip() for v in values):
        return [], f"{field}: a collection or a list of them, not {json.dumps(value, ensure_ascii=False)}"
    return list(dict.fromkeys(v.strip() for v in values)), None


def tag_names(value):
    """remove_tags as a list of names -> (names, problem or None)."""
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
        return [], f"remove_tags: a tag name or a list of them, not {json.dumps(value, ensure_ascii=False)}"
    return list(dict.fromkeys(v.strip() for v in values)), None


def parse_change(raw, where=""):
    """A change's fields, checked -> (change, problems): the collection fields as lists, the tag fields normalized."""
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
            change[field], bad = collection_values(field, raw[field])
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


def from_changes(sources):
    """Change lists -> entries {name, change, where}; invalid_changes when any of it is malformed."""
    found, problems = cli.changes(sources)
    entries = []
    for b in found:
        change, bad = parse_change(b["entry"], f"{b['where']}: ")
        problems += bad
        name = cli.Name(b["key"], "key") if b["key"] else cli.Name(b["cite"], "cite")
        entries.append({"name": name, "change": change, "where": b["where"]})
    if problems:
        raise invalid(problems)
    return entries


def from_options(p, args):
    """The items named and the change options -> one entry per item, all with the same change."""
    raw, problems = {}, []
    if args.set_collection:
        raw["collection"] = args.set_collection
    for field, values in (("add_collection", args.add_collection), ("remove_collection", args.remove_collection),
                          ("remove_tags", args.remove_tag)):
        if values:
            raw[field] = values
    for field, flag, path in (("tags", "--set-tags-file", args.set_tags_file),
                              ("add_tags", "--add-tags-file", args.add_tags_file)):
        if path:
            raw[field], problem = read_json(path, flag)
            problems += [problem] if problem else []
    if args.add_tag:
        if not isinstance(raw.get("add_tags", []), list):
            problems.append("--add-tags-file: a JSON list of tags")
        else:
            raw["add_tags"] = raw.get("add_tags", []) + args.add_tag
    if problems:
        raise invalid(problems)
    change, problems = parse_change(raw)
    if problems:
        raise invalid(problems)
    named = cli.names(args.items)   # main() made sure something follows the options
    return [{"name": n, "change": change, "where": n.value} for n in named]


def head(e):
    return cli.head(e["name"], e.get("key"))


def once(entries):
    """An item several entries name: handled once when they ask the same, invalid_changes when not."""
    first, out, problems = {}, [], []
    for e in entries:
        twin = first.setdefault(e["key"], e) if e.get("key") else e
        if twin is e:
            out.append(e)
        elif twin["change"] != e["change"]:
            problems.append(f"{twin['where']} and {e['where']} both name item {e['key']}: merge them into one change")
    if problems:
        raise invalid(problems)
    return out


COLLECTION_FIELDS = ("collection", "add_collection", "remove_collection")


def place(zot, change, tree):
    """The change with its collections as keys (zot.collection) -> (change, a Stop or None)."""
    out = dict(change)
    for field in (f for f in COLLECTION_FIELDS if f in change):
        try:
            out[field] = list(dict.fromkeys(zot.collection(v, tree) for v in change[field]))
        except cli.Stop as stop:
            return change, stop
    return out, None


def refusal(item, change):
    """Why this item cannot take the change (a Stop), or None."""
    if item is None:
        return cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND)
    parent = zotero.data(item).get("parentItem")
    if parent and any(f in change for f in COLLECTION_FIELDS):
        return cli.Stop("not_a_parent", hint="Only top-level items are in collections; name the parent item (parentItem).",
                        parentItem=parent)
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
    for e in entries:
        try:
            e["key"] = zot.resolve(e["name"])
        except cli.Stop as stop:
            if stop.exit == cli.CANNOT:
                raise
            e["line"] = stop.line(**head(e))
    entries = once(entries)
    named = [e for e in entries if "line" not in e]
    items = zot.items([e["key"] for e in named])
    tree = zot.collections() if any(f in e["change"] for e in named for f in COLLECTION_FIELDS) else {}
    for e in named:
        e["change"], stop = place(zot, e["change"], tree)
        stop = stop or refusal(items.get(e["key"]), e["change"])
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


def run(p, args, options):
    entries = from_options(p, args) if options else from_changes(args.items)
    passed = [e["name"].line for e in entries if e["name"].line is not None]   # upstream's, passed on first
    entries = [e for e in entries if e["name"].line is None]   # the rest go on, a failure upstream or not
    if not entries:   # an empty list: nothing to change
        return cli.finish(passed)
    zot = zotero.Zotero(args.base_url)
    try:
        if not args.dry_run:
            zot.write_headers()
        return cli.finish(passed + apply(zot, entries, args.dry_run))
    except cli.Stop as stop:
        if stop.exit != cli.CANNOT:
            raise
        out = cli.Lines()
        out.stop(stop)
        for line in passed:
            out.put(line)
        for e in entries:
            out.put({**head(e), "code": "not_run"})
        return out.finish()


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("items", nargs="*", metavar="ITEM|CHANGES",
                   help="with change options, the items (- reads a list); without, change list files (- reads one)")
    p.add_argument("--add-tag", action="append", default=[], metavar="TAG", help="add this tag (repeat for more)")
    p.add_argument("--remove-tag", action="append", default=[], metavar="TAG", help="take this tag off (repeat for more)")
    p.add_argument("--add-tags-file", metavar="FILE", help="a JSON list of tags to add")
    p.add_argument("--set-tags-file", metavar="FILE", help="a JSON list of tags: the items' complete tag set")
    p.add_argument("--add-collection", action="append", default=[], metavar="COLL", help="add the items to this collection")
    p.add_argument("--remove-collection", action="append", default=[], metavar="COLL", help="take the items out of this one")
    p.add_argument("--set-collection", action="append", default=[], metavar="COLL",
                   help="the items' collections become exactly these ('none': in none)")
    cli.add_dry_run(p)
    cli.add_base_url(p)
    args = cli.parse(p, argv)
    options = bool(args.add_tag or args.remove_tag or args.add_tags_file or args.set_tags_file or args.add_collection
                   or args.remove_collection or args.set_collection)
    if not args.items:
        p.error("name the items with a change option, or the change list files (- reads one from stdin)")
    return cli.run(lambda: run(p, args, options))


if __name__ == "__main__":
    raise SystemExit(main())
