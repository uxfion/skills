#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Export Zotero items as BibTeX keyed by their citationKey, from a collection, items or records.

What it exports: --collection (its top-level items: a key, a path from p2z.py collections or a name; -r adds the
collections under it, those in the trash left out), and what follows the options: items (keys or citation keys; -
reads a list from stdin, a value a line or our JSON lines, their `key`) and record files (a value with a "/" or
ending in .json is a path: the item the record created, `saved.key`, else the one it found, `found.key`; a near match
names another item, so such a record has none). An item named twice is exported once. Each 50 keys are one GET
/items/top?itemKey=...&format=bibtex (the local API drops unknown keys silently, hence the JSON read that also gives
each item's citationKey). Entries are written ordered by their BibTeX key, to stdout or -o.

Exit 0 = exported, every item with its own clean citationKey; stderr stays empty. Exit 1 = the BibTeX is written
all the same, and stderr's last line is {"summary": {count, output?, collections?, ...}} with each list below that
is not empty:
  missing      items without a citationKey (Zotero makes up their BibTeX key)
  duplicates   [{citationKey, keys}]: one citationKey on several items
  tex          [{key, citationKey, suggested}]: a citationKey with a character TeX treats specially
  not_found    keys that are no top-level item of the library
  unresolved   [{item, code: not_found | ambiguous, keys?}]: names that are not one item
  not_a_parent [{key, parentItem}]: attachments and notes named, which go with their parent's entry
  no_item_key  records (by file name) with no library item yet
  invalid      [{path, code: file_not_found | record_invalid, detail?}]: record paths that are not a record
  standalone   [{key, itemType}]: standalone notes and attachments, which have no BibTeX entry (exit 0 alone)
Fix the citation keys with p2z.py update KEY --set citationKey=... on the user's word, then rerun. Stopped before
exporting, stderr's last line is {code, hint, ...} with exit 1: collection_not_found or ambiguous (--collection),
no_records (an empty collection). Exit 2 = cannot read (zotero_unreachable, local_api_disabled).

Examples:
  p2z.py export --collection 自然图像 -r -o ref.bib
  p2z.py export liu2022progressive zhou2021handheld
  p2z.py export <scratch>/paper-to-zotero/records/*.json -o ref.bib
"""
import re
import sys
from pathlib import Path

from p2zlib import cli, paper, run, zotero
from p2zlib.zotero import LIB

ENTRY_KEY = re.compile(r"^@\w+\s*\{\s*([^,\s]+)\s*,")
PROBLEMS = ("missing", "duplicates", "tex", "not_found", "unresolved", "not_a_parent", "no_item_key", "invalid")


def read_records(paths):
    """-> ([records], [{path, code, detail?}] for the paths that are not record files)."""
    records, invalid = [], []
    for path in paths:
        try:
            records.append(run.read(path))
        except cli.Stop as stop:
            invalid.append({"path": path, "code": stop.code, **({"detail": stop.extra["detail"]} if "detail" in stop.extra else {})})
    return records, invalid


def collection_keys(zot, root, recursive):
    """(the item keys, the collection keys): the collection's top-level items, -r its live sub-collections' too."""
    cols = zot.collection_scope(root, recursive)
    keys = [row["key"] for key in cols for row in zot.rows(f"{LIB}/collections/{key}/items/top")]
    return keys, sorted(cols)


def bibtex(zot, keys):
    out = []
    for part in zotero.chunks(keys):
        status, _, body = zot.request("GET", f"{LIB}/items/top", headers={"Accept": "text/plain, */*"},
                                      params={"itemKey": ",".join(part), "format": "bibtex", "limit": zotero.PAGE})
        zot.check(status, body)
        if status != 200:
            raise cli.Stop("unexpected_response", hint="The local API refused the BibTeX export; see status and detail.",
                           status=status, detail=zotero.detail(body))
        out.append(body.decode("utf-8", errors="replace"))
    return "\n".join(out)


def entries_of(text):
    """[(BibTeX key, entry)] ordered by key; an entry starts with '@' at the start of a line."""
    found = []
    for piece in re.split(r"(?m)^(?=@)", text):
        piece = piece.strip()
        if piece.startswith("@"):
            m = ENTRY_KEY.match(piece)
            found.append((m.group(1) if m else "", piece))
    return sorted(found, key=lambda e: (e[0].lower(), e[0]))


def export(zot, args):
    paths = [v for v in args.items if v != "-" and cli.looks_like_path(v)]
    records, invalid = read_records(paths)
    keys, summary = [], {}
    if args.collection:
        keys, summary["collections"] = collection_keys(zot, args.collection, args.recursive)
    unresolved, no_item_key = [], []
    for name in cli.names([v for v in args.items if v not in paths]):
        try:
            keys.append(zot.resolve(name))
        except cli.Stop as stop:
            if stop.exit == cli.CANNOT:
                raise
            unresolved.append({**cli.head(name), "code": stop.code, **stop.extra})
    for rec in records:
        key = run.item_key(rec)
        if key:
            keys.append(key)
        else:
            no_item_key.append(rec.slug)
    keys = list(dict.fromkeys(keys))
    if not keys and not unresolved and not no_item_key and not invalid:
        if not args.collection:   # `-` with an empty list: nothing to export
            return cli.OK
        raise cli.Stop("no_records", hint="Nothing to export: the collection holds no top-level item.", **summary)

    rows = zot.items(keys)
    items = {k: zotero.data(rows[k]) for k in keys if k in rows and zotero.is_top(rows[k])}
    entries = entries_of(bibtex(zot, list(items))) if items else []
    output = "\n\n".join(e for _, e in entries) + ("\n" if entries else "")
    if args.output:
        out = Path(args.output).expanduser()
        out.write_text(output, encoding="utf-8")
        summary["output"] = str(out)
    else:
        cli.write(output)

    children = {k: zotero.data(rows[k]) for k in keys if k in rows and zotero.data(rows[k]).get("parentItem")}
    lists = {**paper.cite_problems(items), "not_found": [k for k in keys if k not in rows], "unresolved": unresolved,
             "not_a_parent": [{"key": k, "parentItem": d["parentItem"]} for k, d in children.items()],
             "no_item_key": no_item_key, "invalid": invalid,
             "standalone": [{"key": k, "itemType": zotero.data(rows[k]).get("itemType")} for k in keys
                            if k in rows and k not in items and k not in children]}
    if not any(lists[name] for name in PROBLEMS):
        return cli.OK
    summary = {"count": len(entries), **summary, **{name: v for name, v in lists.items() if v},
               "hint": "The BibTeX was written as the library has it: give each item listed its own citationKey free of "
                       "TeX specials (p2z.py update KEY --set citationKey=..., on the user's word), check the names and "
                       "records listed, then rerun."}
    cli.emit({"summary": summary}, sys.stderr)
    return cli.ACT


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("items", nargs="*", metavar="ITEM|RECORD",
                   help="items (keys or citation keys; - reads a list) or record files")
    p.add_argument("--collection", metavar="COLL", help="the collection's top-level items: its key, path or name")
    p.add_argument("-r", "--recursive", action="store_true", help="with --collection: the collections under it too")
    p.add_argument("-o", "--output", metavar="FILE", help="write the BibTeX here instead of stdout")
    cli.add_base_url(p)
    args = cli.parse(p, argv)
    if args.recursive and not args.collection:
        p.error("-r needs --collection")
    if not (args.collection or args.items):
        p.error("name what to export: --collection, items, or record files")
    return cli.run(lambda: export(zotero.Zotero(args.base_url), args), sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
