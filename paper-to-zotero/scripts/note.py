#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown-it-py==3.0.0", "mdit-py-plugins==0.6.1", "mdit-py-cjk-friendly==0.3.0"]
# ///
"""Move notes between Zotero and Markdown files: take a note out, put one back (new or changed), list them.

A note outside Zotero is one Markdown file (note_md.py converts; p2zlib/note_md.py says what stays HTML) whose front
matter says which note it is and where it belongs:
  key          the note's item key; none in a note not yet in Zotero
  version      the note's version when taken; put refuses to write over a note changed since
  parent       the citation key (else the item key) of the item it hangs off; none in a standalone note
  collections  a standalone note's collections, keys joined by ","
  related      the papers a standalone note is related to, both ways: citation keys (else item keys) joined by ","
  schema, citation-items: the note's wrapper (note_md's)

  take   The child notes of the item named (--cite, --key), or one note (--note, a standalone one too); --title T keeps
         those whose first line, the title Zotero shows, is T. One note goes to stdout or -o FILE; several need
         -o DIR/, one file each, <cite>.<key>.note.md (a standalone note: <key>.note.md). A file there already is
         written over only when its front matter names the same note: after a version_conflict, take again into the
         same directory.
  put    Each INPUT (paths, or stdin): with a key, Zotero's note is updated (its HTML, and parent, collections and
         related where the front matter names them) unless its version moved since the take, and left alone when it
         already holds the same note; without one, a note is created under `parent`, else as a standalone note in
         `collections`, related both ways to the papers in `related`. Every write is read back. -i writes the new key
         and version into the file's front matter, so the next put follows on.
  list   One line per note: the child notes of the item named, the notes in --collection K, or every note; --q TEXT
         keeps the notes whose text holds it (Zotero's "All Fields & Tags" search).

stdout (take to files, put, list): one line per note, then {"summary"}.
  take  {key, cite?, title, code ok, file, version, kept_html?: [[block, tag]]}   (to stdout: the Markdown alone)
  put   {file, code ok, key, version, action: created | updated, kept?: [fields Zotero already held as written]}
        skipped unchanged: Zotero already holds this note as written
  list  {key, parent?, title, version, dateModified, collections}
  no_notes (the item has none, or none with that title), not_a_note, not_a_parent, not_found, cite_not_found,
  cite_ambiguous, collection_not_found, bad_front_matter, no_version (a key without a version: take the note first),
  version_conflict (the note changed after the take: take it again, redo the change there), write_denied,
  write_failed, readback_mismatch, file_not_found.
Exit 0 = all ok or skipped; 1 = some not; 2 = cannot go on (Zotero not running, local API off, no key) or usage
error (several notes taken with no -o DIR/, a file there for another note, -i on stdin).

Examples:
  uv run scripts/note.py take --cite ronneberger2015unet -o <scratch>/notes/
  uv run scripts/note.py take --note NOTE1234 > note.md
  uv run scripts/note.py put <scratch>/notes/*.note.md -i
  uv run scripts/note.py put --dry-run new.note.md
  uv run scripts/note.py list --q "flow matching"
"""
import sys
from pathlib import Path

from p2zlib import cli, note_md, zotero
from p2zlib.zotero import LIB

SUFFIX = ".note.md"


# ---- reading Zotero -----------------------------------------------------------------------------------------

def title_of(html):
    """The note's title as Zotero shows it: its first line of text."""
    lines, cur = [], []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, str):
                cur.append(n)
            elif n.tag == "br" or n.tag in note_md.BLOCK_TAGS:
                lines.append("".join(cur))
                cur.clear()
                walk(n.kids)
                lines.append("".join(cur))
                cur.clear()
            else:
                walk(n.kids)

    walk(note_md.unwrap(note_md.parse(html or ""))[0])
    lines.append("".join(cur))
    return next((" ".join(x.split()) for x in lines if x.strip()), "")


class Names:
    """Item key <-> what a front matter writes for it (the citation key, else the key), and relation URIs."""

    def __init__(self, zot):
        self.zot, self.cites, self.library = zot, {}, None

    def cite(self, key):
        if key not in self.cites:
            row = self.zot.item(key)
            self.cites[key] = (zotero.data(row).get("citationKey") if row else None) or key
        return self.cites[key]

    def key(self, name):
        """A front matter's name for an item -> its key: an item key, else a citation key."""
        if cli.KEY_RE.match(name) and self.zot.item(name) is not None:
            return name
        return self.zot.resolve_cite(name)

    def uri(self, key, row=None):
        if self.library is None:
            lib = (row or self.zot.item(key) or {}).get("library") or {}
            self.library = f"http://zotero.org/{lib.get('type', 'user')}s/{lib.get('id', 0)}"
        return f"{self.library}/items/{key}"

    @staticmethod
    def key_of_uri(uri):
        return uri.rstrip("/").rsplit("/", 1)[-1]


def meta_of(names, row):
    """The front matter note.py writes for a note row."""
    d = zotero.data(row)
    meta = {"key": row["key"], "version": row.get("version")}
    if d.get("parentItem"):
        meta["parent"] = names.cite(d["parentItem"])
    else:
        meta["collections"] = d.get("collections") or []
        meta["related"] = [names.cite(names.key_of_uri(u)) for u in (d.get("relations") or {}).get("dc:relation") or []]
    return meta


def is_note(row):
    return row is not None and zotero.data(row).get("itemType") == "note"


def notes_of(zot, key):
    return [c for c in zot.children(key) if is_note(c) and not zotero.in_trash(c)]


# ---- take ---------------------------------------------------------------------------------------------------

def named_notes(zot, args):
    """The notes take was asked for -> (rows, the item's citation key or None)."""
    if args.note:
        row = zot.item(args.note)
        if row is None:
            raise cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND, key=args.note)
        if not is_note(row):
            raise cli.Stop("not_a_note", hint="--note takes a note's key; for an item's notes, pass --key or --cite.",
                           key=args.note, itemType=zotero.data(row).get("itemType"))
        rows = [row]
    else:
        key = args.key or zot.resolve_cite(args.cite)
        item = zot.item(key)
        if item is None:
            raise cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND, key=key)
        if not zotero.is_top(item) or is_note(item):
            raise cli.Stop("not_a_parent", hint="Notes hang off regular items; pass the item's key, or --note for a note.",
                           key=key, itemType=zotero.data(item).get("itemType"))
        rows = notes_of(zot, key)
    if args.title is not None:
        rows = [r for r in rows if title_of(zotero.data(r).get("note")) == args.title]
    if not rows:
        raise cli.Stop("no_notes", hint="No note matches; note.py list shows the notes and their titles.",
                       **({"title": args.title} if args.title is not None else {}))
    return rows


def take_name(meta):
    return (f"{meta['parent']}." if meta.get("parent") else "") + f"{meta['key']}{SUFFIX}"


def cmd_take(zot, args, p):
    rows, names = named_notes(zot, args), Names(zot)
    if len(rows) > 1 and args.out is None:
        for r in rows:
            cli.log(f"{r['key']}  {title_of(zotero.data(r).get('note'))}")
    out, into_dir = cli.output(p, args.out, len(rows))
    taken = []
    for r in rows:
        meta = meta_of(names, r)
        target = out / take_name(meta) if into_dir else out
        if target is not None and target.exists():
            try:
                there = note_md.split_meta(target.read_text(encoding="utf-8"))[0].get("key")
            except (OSError, ValueError):
                there = None
            if there != r["key"]:
                p.error(f"{target} holds another note ({there or 'no key'}); take into another directory")
        taken.append((r, meta, target))
    lines = []
    for r, meta, target in taken:
        kept = []
        md = note_md.to_md(zotero.data(r).get("note") or "", meta, fallbacks=kept)
        for n, tag in kept:
            cli.log(f"{r['key']}: block {n}: <{tag}> kept as HTML")
        if target is None:
            sys.stdout.write(md)
            return cli.OK
        target.write_text(md, encoding="utf-8", newline="\n")
        lines.append({"key": r["key"], **({"cite": meta["parent"]} if meta.get("parent") else {}),
                      "title": title_of(zotero.data(r).get("note")), "code": "ok", "file": str(target),
                      "version": r.get("version"), **({"kept_html": kept} if kept else {})})
    return cli.finish(lines)


# ---- put ----------------------------------------------------------------------------------------------------

def split(value):
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def wanted(names, meta):
    """What the front matter says about where the note belongs, as Zotero fields; only the keys it names."""
    out = {}
    if meta.get("parent"):
        out["parentItem"] = names.key(meta["parent"])
    if "collections" in meta:
        known = names.zot.collections()
        missing = [c for c in split(meta["collections"]) if c not in known]
        if missing:
            raise cli.Stop("collection_not_found", hint="No live collection has that key; read_library collections "
                           "lists them.", collections=missing)
        out["collections"] = split(meta["collections"])
    if "related" in meta:
        out["related"] = [names.key(n) for n in split(meta["related"])]
    return out


def relate(zot, names, key, uri, add=True):
    """Add (or take away) one relation URI on the item `key`, the other side of a standalone note's `related`."""
    def plan(item):
        d = zotero.data(item)
        rel = {k: list(v) for k, v in (d.get("relations") or {}).items()}
        have = rel.get("dc:relation") or []
        if (uri in have) == add:
            return None
        rel["dc:relation"] = have + [uri] if add else [u for u in have if u != uri]
        if not rel["dc:relation"]:
            del rel["dc:relation"]
        return {"relations": rel}
    zot.update(key, plan)


def put_one(zot, names, text, args):
    try:
        html, meta = note_md.to_note(text)
    except ValueError as e:
        raise cli.Stop("bad_front_matter", hint="The front matter is `---`, `key: value` lines, `---`.", detail=str(e))
    where = wanted(names, meta)
    rel_want = where.pop("related", None)
    key = meta.get("key")
    if not key:
        return create(zot, names, html, where, rel_want, args)
    if not meta.get("version"):
        raise cli.Stop("no_version", hint="A note with a key needs the version it was taken at: take it, then edit "
                       "that file.", key=key)
    row = zot.item(key)
    if row is None:
        raise cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND, key=key)
    if not is_note(row):
        raise cli.Stop("not_a_note", hint="The front matter's key is not a note's.", key=key)

    def plan(item):
        if str(item.get("version")) != meta["version"]:
            raise cli.Stop("version_conflict", hint="The note changed in Zotero after it was taken: take it again, redo "
                           "the change in that file, put it.", key=key, taken=meta["version"], now=item.get("version"))
        d, body = zotero.data(item), {}
        if not note_md.same(d.get("note") or "", html):
            body["note"] = html
        for field in ("parentItem", "collections"):
            if field in where and (set(where[field]) != set(d.get(field) or []) if field == "collections"
                                   else where[field] != d.get(field)):
                body[field] = where[field]
        if rel_want is not None:
            have = (d.get("relations") or {}).get("dc:relation") or []
            want = [names.uri(k) for k in rel_want]
            if set(want) != set(have):
                body["relations"] = {**(d.get("relations") or {}), "dc:relation": want}
        return body or None

    body = plan(row)
    if body is None:
        return cli.skipped("unchanged", key=key, action="unchanged", version=row.get("version"))
    if args.dry_run:
        return cli.ok(key=key, action="updated", dry_run=True, fields=sorted(body), html=body.get("note"))
    before, sent, retried = zot.update(key, plan, row)
    if sent is None:
        return cli.skipped("unchanged", key=key, action="unchanged", version=before.get("version"))
    if "relations" in sent:
        old = set((zotero.data(before).get("relations") or {}).get("dc:relation") or [])
        new = set(sent["relations"].get("dc:relation") or [])
        for u in new - old:
            relate(zot, names, names.key_of_uri(u), names.uri(key))
        for u in old - new:
            relate(zot, names, names.key_of_uri(u), names.uri(key), add=False)
    return read_back(zot, key, sent.get("note"), "updated", retried=retried)


def create(zot, names, html, where, rel_want, args):
    obj = {"itemType": "note", "note": html}
    if "parentItem" in where:
        parent = zot.item(where["parentItem"])
        if parent is None or not zotero.is_top(parent) or is_note(parent):
            raise cli.Stop("not_a_parent", hint="parent must name a regular item.", parent=where["parentItem"])
        obj["parentItem"] = where["parentItem"]
    else:
        obj["collections"] = where.get("collections", [])
        if rel_want:
            obj["relations"] = {"dc:relation": [names.uri(k) for k in rel_want]}
    if args.dry_run:
        return cli.ok(action="created", dry_run=True, **{k: v for k, v in obj.items() if k != "itemType"})
    made = zot.post_one(obj, hint="Zotero did not create the note; see detail.")
    key = made["key"]
    for k in rel_want or []:
        relate(zot, names, k, names.uri(key))
    return read_back(zot, key, html, "created")


def read_back(zot, key, html, action, retried=False):
    after = zot.item(key)
    if after is None or (html is not None and zotero.data(after).get("note") != html):
        raise cli.Stop("readback_mismatch", hint="The write was accepted, but the note reads back otherwise; look at it "
                       "in Zotero.", key=key, action=action)
    return cli.ok(key=key, version=after.get("version"), action=action, **({"retried": True} if retried else {}))


def cmd_put(zot, args, p):
    inputs = args.inputs or ["-"]
    if args.in_place and "-" in inputs:
        p.error("-i writes back into the files given; stdin has none")
    if not args.dry_run:
        zot.write_headers()
    names, out = Names(zot), cli.Lines()
    for name in inputs:
        def one(name=name):
            if name == "-":
                text = sys.stdin.read()
            else:
                path = Path(name).expanduser()
                if not path.is_file():
                    raise cli.Stop("file_not_found", hint="Pass the note's Markdown file.")
                text = path.read_text(encoding="utf-8")
            line = put_one(zot, names, text, args)
            if args.in_place and line.get("code") == "ok" and not args.dry_run:
                path.write_text(note_md.set_meta(text, {"key": line["key"], "version": line["version"]}),
                                encoding="utf-8", newline="\n")
            return line
        out.add({"file": "-" if name == "-" else str(Path(name).expanduser())}, one)
    return out.finish({"dry_run": True} if args.dry_run else None)


# ---- list ---------------------------------------------------------------------------------------------------

def cmd_list(zot, args, p):
    if args.key or args.cite:
        key = args.key or zot.resolve_cite(args.cite)
        rows = notes_of(zot, key)
    elif args.collection:
        if args.collection not in zot.collections():
            raise cli.Stop("collection_not_found", hint="read_library collections lists them.", collection=args.collection)
        rows = zot.pages(f"{LIB}/collections/{args.collection}/items", {"itemType": "note"})
    else:
        rows = zot.pages(f"{LIB}/items", {"itemType": "note"})
    if args.q:
        hits = {r["key"] for r in zot.pages(f"{LIB}/items", {"q": args.q, "qmode": "everything", "itemType": "note"})}
        rows = [r for r in rows if r["key"] in hits]
    names, lines = Names(zot), []
    for r in rows:
        if not is_note(r) or zotero.in_trash(r):
            continue
        d = zotero.data(r)
        lines.append({"key": r["key"], **({"parent": names.cite(d["parentItem"])} if d.get("parentItem") else {}),
                      "title": title_of(d.get("note")), "code": "ok", "version": r.get("version"),
                      "dateModified": d.get("dateModified"), "collections": d.get("collections") or []})
    return cli.finish(lines)


def parse_args(argv):
    p = cli.parser(__doc__)
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")
    s = sub.add_parser("take", help="notes out of Zotero as Markdown files")
    which = s.add_mutually_exclusive_group(required=True)
    which.add_argument("--cite", help="the item's citation key: its child notes")
    which.add_argument("--key", help="the item's key: its child notes")
    which.add_argument("--note", help="one note's key (a standalone note too)")
    s.add_argument("--title", help="only the notes whose first line is this")
    s.add_argument("-o", "--out", metavar="OUT", help="a file (one note) or a directory/ (default: stdout)")
    cli.add_base_url(s)
    s.set_defaults(func=cmd_take)
    s = sub.add_parser("put", help="Markdown files into Zotero as notes, new or changed")
    s.add_argument("inputs", nargs="*", metavar="INPUT", help="note files (none, or -: stdin)")
    s.add_argument("--dry-run", action="store_true", help="show what would be written; write nothing")
    s.add_argument("-i", dest="in_place", action="store_true", help="write the new key and version into each file")
    cli.add_base_url(s)
    s.set_defaults(func=cmd_put)
    s = sub.add_parser("list", help="one line per note")
    which = s.add_mutually_exclusive_group()
    which.add_argument("--cite", help="the item's citation key: its child notes")
    which.add_argument("--key", help="the item's key: its child notes")
    which.add_argument("--collection", metavar="KEY", help="the notes in this collection")
    s.add_argument("--q", metavar="TEXT", help="only the notes whose text holds this")
    cli.add_base_url(s)
    s.set_defaults(func=cmd_list)
    args = p.parse_args(argv)
    for name in ("key", "note"):
        value = getattr(args, name, None)
        if value and not cli.KEY_RE.match(value):
            p.error(f"--{name} takes an 8-character key: {value}")
    return p, args


def main(argv=None):
    p, args = parse_args(argv)
    return cli.run(lambda: args.func(zotero.Zotero(args.base_url), args, p))


if __name__ == "__main__":
    raise SystemExit(main())
