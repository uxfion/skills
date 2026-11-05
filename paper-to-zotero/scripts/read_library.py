#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read the Zotero library through the local API, as JSON lines: items, searches, children, PDFs on disk, collections, tags, the schema.

Read-only; the local API answers GETs without a key and sends a listing whole. p2z.py runs each command as its own
word: p2z.py items, p2z.py search, ...
"""
import os

from p2zlib import cli, paper, zotero
from p2zlib.zotero import LIB

ITEM_LINE = """An item's line is its data, flat ({key, version, itemType, title, creators, ..., collections, tags}; no `data`
wrapper: jq '.title'). An item is named by its key or its citation key; - reads a list from stdin, a value a line or
our own JSON lines (their `key`, else `cite`). A name that is not one item prints {item, code: not_found |
ambiguous (keys), hint} in its place."""
EXIT_READ = """Exit 0; 1 = a name is not one item, then stderr's last line is {"summary": {total, failed}}; 2 = cannot read
(zotero_unreachable, local_api_disabled), then stderr's last line is {code, hint}."""


def shared(text):
    """A command's help: text with the paragraphs several commands share filled in."""
    def put(fn):
        fn.__doc__ = text.format(item_line=ITEM_LINE, exit_read=EXIT_READ)
        return fn
    return put


def flat(row):
    """The API object's data with key and version in front."""
    return {"key": row.get("key"), "version": row.get("version"), **zotero.data(row)}


def add_filters(p):
    p.add_argument("-a", "--all", action="store_true", help="attachments and notes too, not only top-level items")
    p.add_argument("--collection", metavar="COLL", help="only items in this collection: its key, path or name")
    p.add_argument("-r", "--recursive", action="store_true", help="with --collection: the collections under it too")
    p.add_argument("--tag", action="append", default=[], metavar="TAG",
                   help="only items with this tag; repeated: with each; 'a || b': with either")
    p.add_argument("--since-version", type=int, metavar="N", help="only items changed after library version N")


def filtering(args):
    return bool(args.collection or args.tag or args.since_version is not None)


def passes(zot, args):
    """The filters as a test on one row: its own tags and version; its collections, or its parent's for a child."""
    scope = set(zot.collection_scope(args.collection, args.recursive)) if args.collection else None
    wanted = [{t.strip() for t in tag.split("||")} for tag in args.tag]

    def test(row):
        d = zotero.data(row)
        if args.since_version is not None and (row.get("version") or 0) <= args.since_version:
            return False
        if wanted and not all(any(t.get("tag") in w for t in d.get("tags") or []) for w in wanted):
            return False
        if scope is not None:
            home = zotero.data(zot.item(d["parentItem"])) if d.get("parentItem") else d
            return bool(scope & set(home.get("collections") or []))
        return True

    return test


def each(zot, args, p, fn):
    """fn(key) -> failures, for each item named, once each; a name that is not one item prints its line. Zotero
    gone midway: the names not yet read are not_run. -> the exit code, after the summary when something failed."""
    if not args.items:
        p.error("name the items: keys or citation keys, or - to read a list from stdin")
    named, out, failed = cli.names(args.items), cli.Lines(), 0
    for _, name, key in cli.resolved(zot, named, out):   # a name that is not one item: its line, on out
        try:
            failed += fn(key)
        except cli.Stop as stop:
            if stop.exit == cli.CANNOT:
                out.stop(stop)
                out.put({**cli.head(name, key), "code": "not_run"})
            else:
                out.put(stop.line(**cli.head(name, key)))
    return cli.summarize(len(named), failed + out.counts["failed"], out.stopped)


@shared("""Items' data, one JSON line each: the items named, or those the filters pick from the library.

Without names, the filters pick: --collection (-r: and the collections under it), --tag, --since-version; top-level
items unless -a. With names, an item prints only when it passes the filters. Nothing named and no filter is a
usage error: an empty $(...) would otherwise print the whole library.

{item_line}

{exit_read} An empty listing is exit 0.

Examples:
  p2z.py items liuProgressiveResidualLearning2022
  p2z.py items --collection 自然图像/Diffusion | head -20
  p2z.py items --tag method/diffusion --tag 'task/denoising || task/despeckling'
""")
def items(zot, args, p):
    if args.items:
        test = passes(zot, args)

        def one(key):
            row = zot.item(key)
            if row is None:
                raise cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND)
            if test(row):
                cli.emit(flat(row))
            return 0

        return each(zot, args, p, one)
    if not filtering(args):
        p.error("name the items, - to read a list from stdin, or pick them with --collection, --tag or --since-version")
    scope = zot.collection_scope(args.collection, args.recursive) if args.collection else [None]
    params = {k: v for k, v in (("tag", args.tag), ("since", args.since_version)) if v not in (None, [])}
    seen = set()
    for coll in scope:
        path = (f"{LIB}/collections/{coll}/items" if coll else f"{LIB}/items") + ("" if args.all else "/top")
        for row in zot.rows(path, params):
            if row["key"] not in seen:
                seen.add(row["key"])
                cli.emit(flat(row))
    return cli.OK


@shared("""Items a quick search finds, one JSON line each, as Zotero's search box finds them.

The words after the options make one query, each word somewhere in the item (search speckle reduction = search
"speckle reduction"). The mode is the search box's: by default Title, Creator, Year (the citation key too);
--all-fields: All Fields & Tags (notes and annotations too); --everything: and the PDFs' full text. A hit on an
attachment or note counts for its parent; with -a it prints as itself. The filters keep the hits that pass.

{item_line}

Exit 0 = some hit; 1 = none (as grep); 2 = cannot read (zotero_unreachable, local_api_disabled), then stderr's last
line is {{code, hint}}.

Examples:
  p2z.py search POCUS | p2z.py pdf -
  p2z.py search --everything speckle reduction --collection 超声 -r
""")
def search(zot, args, p):
    query = " ".join(args.words).strip()
    if not query:
        p.error("give the words to search for")
    qmode = "fields" if args.all_fields else "everything" if args.everything else None
    rows = (zot.rows(f"{LIB}/items", {"q": query, **({"qmode": qmode} if qmode else {})}) if args.all
            else zot.search(query, qmode))
    test, hits = passes(zot, args), 0
    for row in rows:
        if test(row):
            cli.emit(flat(row))
            hits += 1
    return cli.OK if hits else cli.ACT


@shared("""Items' attachments and notes, an attachment's annotations, one JSON line each.

{item_line}

{exit_read}

Examples:
  p2z.py children liuProgressiveResidualLearning2022
  p2z.py children 32L6CM29 | jq -r '.annotationComment'     # a PDF's annotations
""")
def children(zot, args, p):
    def one(key):
        row = zot.item(key)
        kids = (zot.rows(f"{LIB}/items/{key}/children", {"itemType": "annotation"})
                if zotero.data(row).get("itemType") == "attachment" else zot.children(key))
        for child in kids:
            cli.emit(flat(child))
        return 0

    return each(zot, args, p, one)


@shared("""Where items' PDFs are on disk, with their versions, best first: one JSON line per PDF attachment.

Each line: {{key, citationKey, title, attachment, attachment_title, version, source, detail, standard, md5,
link_mode, path, exists, package}}. Version, source and detail come from the attachment title (Published-IEEE,
Accepted-arXiv-v3: version published | accepted | preprint | unknown | supplement); a title outside that scheme
reads as version unknown with standard false: the paper's file all the same, its version not checked. Order:
published, accepted, preprint, unknown; within one, final before in_press, the larger vN, the later added;
supplements last. `path` is the file as this machine opens it (a Windows path from Zotero on Windows goes through
wslpath in WSL); `exists` says whether it is there (not synced yet, or a linked file that moved). `package`: the key
of the PDF's structured package (the zip beside it under its title; p2z.py package take unzips it), or null. How
another skill gets a library paper's PDF to read or parse: take the row of the version it wants.
  {{key, citationKey, title, code: no_pdf, attachments: [content types], hint}}   an item without a PDF
  {{key, code: not_a_parent, parentItem, hint}}   an attachment or note named: name its parent

{item_line}

Exit 0 = every item has a PDF on disk; 1 = some item none (no_pdf, or no `exists`), or a name is not one item, then
stderr's last line is {{"summary": {{total, failed}}}}; 2 = cannot read, then stderr's last line is {{code, hint}}.

Examples:
  p2z.py pdf liuProgressiveResidualLearning2022 | jq -r 'select(.exists) | .path' | head -1
  p2z.py search POCUS | p2z.py pdf -
""")
def pdf(zot, args, p):
    def one(key):
        item = zot.item(key)
        d = zotero.data(item)
        if not paper.is_top(d):
            raise cli.Stop("not_a_parent", parentItem=d.get("parentItem"),
                           hint="An attachment or note has no PDFs of its own; name its parent item (parentItem).")
        head = {"key": key, "citationKey": d.get("citationKey"), "title": d.get("title")}
        attachments = zot.attachments(key)
        pdfs = [a for a in attachments if a["contentType"] == "application/pdf"]
        packages = {a["title"]: a["key"] for a in attachments if a["contentType"] == paper.PACKAGE}
        if not pdfs:
            cli.emit({**head, "code": "no_pdf", "attachments": [a["contentType"] for a in attachments],
                      "hint": "The item has no PDF attachment; paper-to-zotero's import can fetch one."})
            return 1
        on_disk = False
        for a in pdfs:
            path = zot.file_path(a["key"])
            exists = bool(path and os.path.isfile(path))
            on_disk |= exists
            cli.emit({**head, "attachment": a["key"], "attachment_title": a["title"],
                      **{k: a[k] for k in ("version", "source", "detail", "standard", "md5")},
                      "link_mode": a["linkMode"], "path": path, "exists": exists, "package": packages.get(a["title"])})
        return 0 if on_disk else 1

    return each(zot, args, p, one)


def collections(zot, args, p):
    """The collections, parents first, one JSON line each: {key, version, name, parentCollection, ..., path}.

`path` joins the names from the root with "/": what --collection, tag --add-collection and mkcol take, as well as
a key or a name only one collection has. Collections in the trash, and those under one, show only with -a.

Exit 0; 2 = cannot read, then stderr's last line is {code, hint}.

Examples:
  p2z.py collections | jq -r '.path'
"""
    for c in zot.collections(trashed=args.all).values():
        cli.emit({"key": c["key"], "version": c["version"], **c["data"], "path": c["path"]})
    return cli.OK


def tags(zot, args, p):
    """The tags with their item counts, one JSON line each: {tag, type, count}.

type 0 is a tag given by hand, 1 an automatic one. Exit 0; 2 = cannot read, then stderr's last line is {code, hint}.

Examples:
  p2z.py tags --min-count 3 | jq -r '.tag'
"""
    for t in zot.rows(f"{LIB}/tags"):
        meta = t.get("meta") or {}
        if meta.get("numItems", 0) >= args.min_count:
            cli.emit({"tag": t.get("tag"), "type": meta.get("type", 0), "count": meta.get("numItems", 0)})
    return cli.OK


def schema(zot, args, p):
    """Zotero's schema, one JSON line: item types, their fields and creator types, the CSL mappings.

Exit 0; 2 = cannot read, then stderr's last line is {code, hint}.

Examples:
  p2z.py schema | jq -r '.itemTypes[].itemType'
"""
    cli.emit(zot.schema())
    return cli.OK


def configure_items(p):
    cli.add_items(p)
    add_filters(p)


def configure_search(p):
    p.add_argument("words", nargs="*", metavar="WORD", help="what to search for; the words make one query")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--all-fields", action="store_true", help="All Fields & Tags: notes and annotations too")
    mode.add_argument("--everything", action="store_true", help="All Fields & Tags and the PDFs' full text")
    add_filters(p)


def configure_named(p):
    cli.add_items(p)


def configure_collections(p):
    p.add_argument("-a", "--all", action="store_true", help="the collections in the trash too")


def configure_tags(p):
    p.add_argument("--min-count", type=int, default=0, metavar="N", help="only tags on at least N items")


COMMANDS = {"items": items, "search": search, "children": children, "pdf": pdf, "collections": collections,
            "tags": tags, "schema": schema}
CONFIGURE = {"items": configure_items, "search": configure_search, "children": configure_named, "pdf": configure_named,
             "collections": configure_collections, "tags": configure_tags, "schema": lambda p: None}


def main(argv=None):
    name, rest = cli.subcommand(__doc__, COMMANDS, argv)
    func = COMMANDS[name]
    p = cli.parser(func.__doc__, sub=name)
    CONFIGURE[name](p)
    cli.add_base_url(p)
    args = cli.parse(p, rest)
    return cli.run(lambda: func(zotero.Zotero(args.base_url), args, p))


if __name__ == "__main__":
    raise SystemExit(main())
