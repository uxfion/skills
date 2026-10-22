#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read the Zotero library through the local API, as JSON lines: items, their children, a paper's PDFs on disk, collections, tags, the schema.

Read-only; the local API answers GETs without a key. One JSON object per stdout line:
  items        the item's data, flat ({key, version, itemType, title, creators, ..., collections, tags}; no `data`
               wrapper: jq '.title'). Top-level items unless --all; within a --collection; by --key / --cite; by
               --q search text; changed --since a library version; with a --tag ('a || b' for either)
  children     the attachments and notes of the items named by --key / --cite
  pdf          one line per PDF attachment of each named item, best first: {key, citationKey, title, attachment,
               attachment_title, version, source, detail, standard, md5, link_mode, path, exists}. Version, source and
               detail come from the attachment title (Published-IEEE, Accepted-arXiv-v3: version published | accepted
               | preprint | unknown | supplement); a title outside that scheme reads as version unknown with standard
               false — the paper's file all the same, its version not checked. Order: published, accepted, preprint,
               unknown; within one, final before in_press, the larger vN, the later added; supplements last. `path` is
               the file as this machine opens it (a Windows path from Zotero on Windows goes through wslpath in WSL).
               How another skill gets a library paper's PDF to read or parse: take the row of the version it wants.
               {key, citationKey, title, code: no_pdf, attachments: [content types]} for an item without one
  collections  the collection's data; --tree adds `path` (names from the root joined by "/") and leaves out the
               collections in the trash and those under one
  tags         {tag, type, count}
  schema       the schema object, once
Listings are read 100 at a time; --limit caps the total. --cite finds the item whose citationKey it is (a search,
then a scan of every top-level item). A key or citation key that does not resolve prints its {key | cite, code,
hint} line in place of its rows.

Exit 0; 1 = some --key / --cite did not resolve (cite_not_found, cite_ambiguous, not in the library), or pdf found
no PDF, or none on disk; 2 = cannot read (zotero_unreachable, local_api_disabled), then stdout holds one {code} line.

Examples:
  uv run scripts/read_library.py items --collection 9EYXTC2I --limit 20
  uv run scripts/read_library.py items --cite liuProgressiveResidualLearning2022
  uv run scripts/read_library.py items --q 'residual learning' --qmode everything
  uv run scripts/read_library.py children --cite liuProgressiveResidualLearning2022
  uv run scripts/read_library.py pdf --cite liuProgressiveResidualLearning2022
  uv run scripts/read_library.py collections --tree
  uv run scripts/read_library.py tags --min-count 3
"""
import os

from p2zlib import cli, zotero
from p2zlib.zotero import LIB


def flat(row):
    """The API object's data with key and version in front."""
    return {"key": row.get("key"), "version": row.get("version"), **zotero.data(row)}


def resolve(zot, args):
    """The keys named by --key / --cite; a cite that does not resolve prints its line. -> (keys with their cites, failed)."""
    out, failed = [], False
    for key, cite, failure in zot.targets(args.key, args.cite):
        if failure is not None:
            cli.emit(failure.line())
            failed = True
        else:
            out.append((key, cite))
    return out, failed


def cmd_items(zot, args):
    params = {k: v for k, v in (("q", args.q), ("qmode", args.qmode if args.q else None), ("since", args.since),
                                ("tag", args.tag)) if v is not None}
    base = f"{LIB}/collections/{args.collection}/items" if args.collection else f"{LIB}/items"
    failed = False
    if args.key or args.cite:
        named, failed = resolve(zot, args)
        found = zot.items([k for k, _ in named], base, params)
        for key, cite in named:
            if key not in found:
                cli.emit(cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND + (" Or it is not in that collection."
                                                                             if args.collection else "")).line(**cli.head(key, cite)))
                failed = True
        rows = [found[k] for k, _ in named if k in found][:args.limit]
    else:
        rows = zot.pages(base if args.all else base + "/top", params, limit=args.limit)
    for row in rows:
        cli.emit(flat(row))
    return cli.ACT if failed else cli.OK


def cmd_children(zot, args):
    named, failed = resolve(zot, args)
    found = zot.items([k for k, _ in named])
    for key, cite in named:
        if key not in found:
            cli.emit(cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND).line(**cli.head(key, cite)))
            failed = True
            continue
        for child in zot.children(key):
            cli.emit(flat(child))
    return cli.ACT if failed else cli.OK


def cmd_pdf(zot, args):
    named, failed = resolve(zot, args)
    for key, cite in named:
        item = zot.item(key)
        if item is None:
            cli.emit(cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND).line(**cli.head(key, cite)))
            failed = True
            continue
        d = zotero.data(item)
        head = {"key": key, "citationKey": d.get("citationKey"), "title": d.get("title")}
        attachments = zot.attachments(key)
        pdfs = [a for a in attachments if a["contentType"] == "application/pdf"]
        if not pdfs:
            cli.emit({**head, "code": "no_pdf", "attachments": [a["contentType"] for a in attachments],
                      "hint": "The item has no PDF attachment; paper-to-zotero's import steps can fetch one."})
            failed = True
            continue
        on_disk = False
        for a in pdfs:
            path = zot.file_path(a["key"])
            exists = bool(path and os.path.isfile(path))
            on_disk |= exists
            cli.emit({**head, "attachment": a["key"], "attachment_title": a["title"],
                      **{k: a[k] for k in ("version", "source", "detail", "standard", "md5")},
                      "link_mode": a["linkMode"], "path": path, "exists": exists})
        if not on_disk:
            cli.log(f"{key}: no PDF of this item is on disk (not synced, or a linked file that moved)")
            failed = True
    return cli.ACT if failed else cli.OK


def cmd_collections(zot, args):
    if args.tree:
        for c in zot.collections().values():
            cli.emit({"key": c["key"], "version": c["version"], **c["data"], "path": c["path"]})
    else:
        for row in zot.pages(f"{LIB}/collections"):
            cli.emit(flat(row))
    return cli.OK


def cmd_tags(zot, args):
    for t in zot.pages(f"{LIB}/tags"):
        meta = t.get("meta") or {}
        if meta.get("numItems", 0) >= args.min_count:
            cli.emit({"tag": t.get("tag"), "type": meta.get("type", 0), "count": meta.get("numItems", 0)})
    return cli.OK


def cmd_schema(zot, args):
    cli.emit(zot.schema())
    return cli.OK


def parse_args(argv):
    p = cli.parser(__doc__)
    cli.add_base_url(p)
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    s = sub.add_parser("items", help="items: top-level unless --all")
    s.add_argument("--all", action="store_true", help="also attachments and notes")
    s.add_argument("--collection", metavar="KEY", help="only items in this collection")
    cli.add_targets(s)
    s.add_argument("--q", metavar="TEXT", help="search text (Zotero's quick search)")
    s.add_argument("--qmode", choices=("titleCreatorYear", "everything", "fields"), help="quick-search mode for --q")
    s.add_argument("--since", type=int, metavar="VERSION", help="only items changed after this library version")
    s.add_argument("--tag", metavar="TAG", help="only items with this tag ('a || b' for either)")
    s.add_argument("--limit", type=int, metavar="N", help="at most N items in total")
    s.set_defaults(func=cmd_items, need_targets=False)

    for name, func, text in (("children", cmd_children, "the attachments and notes of items"),
                             ("pdf", cmd_pdf, "where items' PDFs are on disk, with their versions, best first")):
        s = sub.add_parser(name, help=text)
        cli.add_targets(s)
        s.set_defaults(func=func, need_targets=True)

    s = sub.add_parser("collections", help="all collections")
    s.add_argument("--tree", action="store_true", help="parents first, with `path`; collections in the trash left out")
    s.set_defaults(func=cmd_collections)

    s = sub.add_parser("tags", help="all tags with their item counts")
    s.add_argument("--min-count", type=int, default=0, metavar="N", help="only tags on at least N items")
    s.set_defaults(func=cmd_tags)

    s = sub.add_parser("schema", help="the Zotero schema (item types, fields, CSL mappings)")
    s.set_defaults(func=cmd_schema)

    args = p.parse_args(argv)
    if hasattr(args, "need_targets"):
        cli.targets_of(p, args, required=args.need_targets)
    if getattr(args, "limit", None) is not None and args.limit < 1:
        p.error("--limit must be at least 1")
    return args


def main(argv=None):
    args = parse_args(argv)
    return cli.run(lambda: args.func(zotero.Zotero(args.base_url), args))


if __name__ == "__main__":
    raise SystemExit(main())
