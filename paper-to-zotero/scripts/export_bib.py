#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Export Zotero items as BibTeX keyed by their citationKey, from a collection, item or citation keys, or records.

The items: --collection (its top-level items; --recursive adds its sub-collections, those in the trash left out),
--key / --cite (a citation key is found by a search, then a scan of the top-level items), and record files (the
item the record created, `saved.key`, else the one it found, `found.key`; a near match names another item, so
such a record has none). An item named twice is exported once. Each 50 keys are one GET
/items/top?itemKey=...&format=bibtex (the local API drops unknown keys silently, hence the JSON read that also
gives each item's citationKey). Entries are written ordered by their BibTeX key, to stdout or --out.

stdout carries the BibTeX, so every JSON line goes to stderr. Exported: one {"summary": {count, out?,
collections?, ...}}, each list below only when it is not empty:
  missing      items without a citationKey (Zotero makes up their BibTeX key)
  duplicates   [{citationKey, keys}]: one citationKey on several items
  tex          [{key, citationKey, suggested}]: a citationKey with a character TeX treats specially
  not_found    keys that are no top-level item of the library
  unresolved   [{cite, code: cite_not_found | cite_ambiguous, keys?}]
  no_item_key  records (by file name) with no library item yet
  invalid      [{path, code: record_invalid, detail?}]: record paths that are not a file holding one JSON object
  standalone   [{key, itemType}]: standalone notes and attachments, which have no BibTeX entry
The BibTeX is written either way; fix the citation keys with update_item.py --key KEY --set citationKey=... on
the user's word, then rerun. Stopped before exporting, one {code, hint, ...}: collection_not_found, no_records
(an empty collection).

Exit 0 = exported, every item with its own clean citationKey; 1 = a list above other than standalone is not empty,
or stopped; 2 = cannot read (zotero_unreachable, local_api_disabled).

Examples:
  uv run scripts/export_bib.py --collection 9EYXTC2I --recursive --out ref.bib
  uv run scripts/export_bib.py --cite liu2022progressive zhou2021handheld
  uv run scripts/export_bib.py work/records/*.json --out ref.bib   # record paths before any --key / --cite
"""
import re
import sys
from pathlib import Path

from p2zlib import cli, paper, run, zotero
from p2zlib.zotero import LIB

ENTRY_KEY = re.compile(r"^@\w+\s*\{\s*([^,\s]+)\s*,")
PROBLEMS = ("missing", "duplicates", "tex", "not_found", "unresolved", "no_item_key", "invalid")


def read_records(paths):
    """-> ([records], [{path, code, detail?}] for the paths that are not record files)."""
    records, invalid = [], []
    for path in paths:
        try:
            records.append(run.read(path))
        except cli.Stop as stop:
            invalid.append({"path": path, "code": stop.code, **({"detail": stop.extra["detail"]} if "detail" in stop.extra else {})})
    return records, invalid


def record_key(rec):
    """The item a record names: the one it created, else the one it found (a near match names another item). Read as
    find_in_library writes `found` today, without the `from` that run.item_key asks of it."""
    saved, found = rec.get("saved"), rec.get("found")
    if isinstance(saved, dict) and saved.get("key") and not saved.get("pending"):
        return saved["key"]
    if isinstance(found, dict) and found.get("code") != "near_match":
        return found.get("key")
    return None


def collection_keys(zot, root, recursive):
    """(the item keys, the collection keys): the collection's top-level items, --recursive its live sub-collections' too."""
    cols = zot.collection_scope(root, recursive)
    keys = [row["key"] for key in cols for row in zot.pages(f"{LIB}/collections/{key}/items/top")]
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
    records, invalid = read_records(args.records)
    keys, summary = [], {}
    if args.collection:
        keys, summary["collections"] = collection_keys(zot, args.collection, args.recursive)
    unresolved, no_item_key = [], []
    for key, cite, failure in zot.targets(args.key, args.cite):
        if failure is not None:
            unresolved.append({"cite": cite, "code": failure.code, **failure.extra})
        else:
            keys.append(key)
    for rec in records:
        key = record_key(rec)
        if key:
            keys.append(key)
        else:
            no_item_key.append(rec.slug)
    keys = list(dict.fromkeys(keys))
    if not keys and not unresolved and not no_item_key and not invalid:
        raise cli.Stop("no_records", hint="Nothing to export: the collection holds no top-level item.", **summary)

    rows = zot.items(keys, f"{LIB}/items/top")
    items = {k: zotero.data(rows[k]) for k in keys if k in rows and zotero.is_top(rows[k])}
    entries = entries_of(bibtex(zot, list(items))) if items else []
    output = "\n\n".join(e for _, e in entries) + ("\n" if entries else "")
    if args.out:
        out = Path(args.out).expanduser()
        out.write_text(output, encoding="utf-8")
        summary["out"] = str(out)
    else:
        sys.stdout.write(output)
        sys.stdout.flush()

    lists = {**paper.cite_problems(items), "not_found": [k for k in keys if k not in rows], "unresolved": unresolved,
             "no_item_key": no_item_key, "invalid": invalid,
             "standalone": [{"key": k, "itemType": zotero.data(rows[k]).get("itemType")} for k in keys if k in rows and k not in items]}
    summary = {"count": len(entries), **summary, **{name: v for name, v in lists.items() if v}}
    failed = any(lists[name] for name in PROBLEMS)
    if failed:
        summary["hint"] = ("The BibTeX was written as the library has it: give each item listed its own citationKey free of TeX "
                           "specials (update_item.py --key KEY --set citationKey=..., on the user's word), check the keys, "
                           "cites and records listed, then rerun.")
    cli.emit({"summary": summary}, sys.stderr)
    return cli.ACT if failed else cli.OK


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("records", nargs="*", metavar="RECORD", help="record files (the shell expands a glob)")
    p.add_argument("--collection", metavar="KEY", help="the collection's top-level items")
    p.add_argument("--recursive", action="store_true", help="with --collection: its sub-collections too")
    cli.add_targets(p)
    p.add_argument("--out", metavar="FILE", help="write the BibTeX here instead of stdout")
    cli.add_base_url(p)
    args = cli.targets_of(p, p.parse_args(argv), required=False)
    if args.collection and not cli.KEY_RE.match(args.collection):
        p.error("--collection takes an 8-character collection key")
    if args.recursive and not args.collection:
        p.error("--recursive needs --collection")
    if not (args.collection or args.key or args.cite or args.records):
        p.error("name what to export: --collection, --key / --cite, or record paths")
    return cli.run(lambda: export(zotero.Zotero(args.base_url), args), sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
