#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown-it-py==3.0.0", "mdit-py-plugins==0.6.1", "mdit-py-cjk-friendly==0.3.0"]
# ///
"""Move notes between Zotero and Markdown files: take a note out, put one back (new or changed), list or search them.

A note outside Zotero is one Markdown file (p2z.py convert converts, and says what stays HTML) whose front matter
says which note it is and where it belongs:
  key          the note's item key; none in a note not yet in Zotero
  version      the note's version when taken; put refuses to write over a note changed since
  parent       the citation key (else the item key) of the item it hangs off; none in a standalone note
  collections  a standalone note's collections, keys (or paths, or names) joined by ","
  related      the papers a standalone note is related to, both ways: citation keys (else item keys) joined by ","
  schema, citation-items   the note's wrapper (convert's)
Zotero has nowhere to keep any other field, so put refuses a file that holds one (bad_front_matter, `fields`).

Exit codes, every command: 0 = all ok or skipped; 1 = some not, then stderr's last line is {"summary": {total, ok,
skipped, failed}}; 2 = cannot go on (Zotero not running, local API off, no key) or a usage error, then stderr's last
line is {code, hint}.
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
        """A front matter's name for an item (a key or a citation key) -> its key."""
        return self.zot.resolve(cli.Name(name, None))

    def uri(self, key, row=None):
        if self.library is None:
            lib = (row or self.zot.item(key) or {}).get("library") or {}
            self.library = f"http://zotero.org/{lib.get('type', 'user')}s/{lib.get('id', 0)}"
        return f"{self.library}/items/{key}"

    @staticmethod
    def key_of_uri(uri):
        return uri.rstrip("/").rsplit("/", 1)[-1]


def meta_of(names, row):
    """The front matter p2z.py note writes for a note row."""
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
    """The notes take was asked for -> rows: the note named, or the item's child notes."""
    key = zot.resolve(cli.Name(args.item, None))
    item = zot.item(key)
    if item is None:
        raise cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND, key=key)
    if is_note(item):
        rows = [item]
    elif not zotero.is_top(item):
        raise cli.Stop("not_a_parent", hint="Notes hang off regular items; name the item, or the note itself.",
                       key=key, itemType=zotero.data(item).get("itemType"), parentItem=zotero.data(item).get("parentItem"))
    else:
        rows = notes_of(zot, key)
    if args.title is not None:
        rows = [r for r in rows if title_of(zotero.data(r).get("note")) == args.title]
    if not rows:
        raise cli.Stop("no_notes", hint="No note matches; p2z.py note list shows the notes and their titles.",
                       **({"title": args.title} if args.title is not None else {}))
    return rows


def take_name(meta):
    return (f"{meta['parent']}." if meta.get("parent") else "") + f"{meta['key']}{SUFFIX}"


def take(zot, args, p):
    """Notes out of Zotero as Markdown: the note named, or the child notes of the item named.

The item or note is named by its key or citation key. --title T keeps the notes whose first line, the title Zotero
shows, is T. One note goes to stdout (the Markdown alone; a block kept as HTML is named on stderr) or -o FILE;
several need -o DIR/, one file each, <cite>.<key>.note.md (a standalone note: <key>.note.md), and with none the
notes are named on stderr. A file there already is written over only when its front matter names the same note:
after a version_conflict, take again into the same directory.

stdout to files: one line per note {key, cite?, title, code ok, file, version, kept_html?: [[block, tag]]}; no_notes
(the item has none, or none with that title), not_a_parent, not_found, ambiguous.

Examples:
  p2z.py note take ronneberger2015unet -o <scratch>/notes/
  p2z.py note take NOTE1234 > note.md
"""
    rows, names = named_notes(zot, args), Names(zot)
    if len(rows) > 1 and args.output is None:
        for r in rows:
            cli.log(f"{r['key']}  {title_of(zotero.data(r).get('note'))}")
    out, into_dir = cli.output(p, args.output, len(rows))
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
        if target is None:
            for n, tag in kept:
                cli.log(f"{r['key']}: block {n}: <{tag}> kept as HTML")
            cli.write(md)
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
        out["collections"] = list(dict.fromkeys(names.zot.collection(c, known) for c in split(meta["collections"])))
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
    unknown = sorted(set(meta) - set(note_md.FIRST))
    if unknown:
        raise cli.Stop("bad_front_matter", hint="Zotero has nowhere to keep these fields: write what they say in the "
                       "note's text, or delete them. Nothing was written.", fields=unknown,
                       **({"key": meta["key"]} if meta.get("key") else {}))
    if not title_of(html):
        raise cli.Stop("empty_note", hint="The note has no text after its front matter: nothing was written.",
                       **({"key": meta["key"]} if meta.get("key") else {}))
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
        title = title_of(html)
        same = [n["key"] for n in notes_of(zot, where["parentItem"]) if title_of(zotero.data(n).get("note")) == title]
        if same:
            raise cli.Stop("same_title", title=title, keys=same,
                           hint="The item has a note of this title already: take it (p2z.py note take KEY), carry this text "
                                "into it, and put that file. Nothing was written.")
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
    """The note as Zotero now holds it is the one sent when the editor's model is the same: an editor showing the
    note saves it again at once in its own HTML (a wrapper, rel on links), and the version read back is that save's."""
    after = zot.item(key)
    if after is None or (html is not None and not note_md.same(zotero.data(after).get("note") or "", html)):
        raise cli.Stop("readback_mismatch", hint="The write was accepted, but the note reads back otherwise; look at it "
                       "in Zotero.", key=key, action=action)
    return cli.ok(key=key, version=after.get("version"), action=action, **({"retried": True} if retried else {}))


def put(zot, args, p):
    """Markdown files into Zotero as notes, new or changed.

Each file (- reads one from stdin): with a key, Zotero's note is updated (its HTML, and parent, collections and
related where the front matter names them) unless its version moved since the take, and left alone when it already
holds the same note; without one, a note is created under `parent` (unless a child note there has its title
already), else as a standalone note in `collections`, related both ways to the papers in `related`. A note without
text is refused. Every write is read back and compared in the editor's model, as an editor showing the note saves
it again at once in its own HTML. -i writes the new key and version into the file's front matter, so the next put
follows on.

stdout: one line per file {file, code ok, key, version, action: created | updated, kept?: [fields Zotero already held
as written]}; skipped unchanged: Zotero already holds this note as written; not_a_note, not_a_parent, not_found,
ambiguous, collection_not_found, bad_front_matter, empty_note (no text after the front matter), same_title (a new
note whose parent has a child note of that title: `keys`), no_version (a key without a version: take the note
first), version_conflict (the note changed after the take: take it again, redo the change there), write_denied,
write_failed, readback_mismatch, file_not_found.

Examples:
  p2z.py note put <scratch>/notes/*.note.md -i
  p2z.py note put -n new.note.md
"""
    if not args.inputs:
        p.error("name the note files, or - to read one from stdin")
    if args.in_place and "-" in args.inputs:
        p.error("-i writes back into the files given; stdin has none")
    if not args.dry_run:
        zot.write_headers()
    names, out = Names(zot), cli.Lines()
    for name in args.inputs:
        def one(name=name):
            if name != "-" and not Path(name).expanduser().is_file():
                raise cli.Stop("file_not_found", hint="Name the note's Markdown file.")
            text = cli.document(name)
            line = put_one(zot, names, text, args)
            if args.in_place and line.get("code") == "ok" and not args.dry_run:
                Path(name).expanduser().write_text(note_md.set_meta(text, {"key": line["key"], "version": line["version"]}),
                                                   encoding="utf-8", newline="\n")
            return line
        out.add({"file": "-" if name == "-" else str(Path(name).expanduser())}, one)
    return out.finish()


# ---- list, search -------------------------------------------------------------------------------------------

def notes_in(zot, args):
    """The notes list and search look among: the items named's child notes, the notes in --collection, or all."""
    if args.items:
        rows = []
        for name in cli.names(args.items):
            rows += [name.line] if name.line else notes_of(zot, zot.resolve(name))
        return rows
    if args.collection:
        return zot.rows(f"{LIB}/collections/{zot.collection(args.collection)}/items", {"itemType": "note"})
    return zot.rows(f"{LIB}/items", {"itemType": "note"})


def lines_of(zot, rows):
    names, lines = Names(zot), []
    for r in rows:
        if "code" in r:   # a line passed on from upstream
            lines.append(r)
            continue
        if not is_note(r) or zotero.in_trash(r):
            continue
        d = zotero.data(r)
        lines.append({"key": r["key"], **({"parent": names.cite(d["parentItem"])} if d.get("parentItem") else {}),
                      "title": title_of(d.get("note")), "code": "ok", "version": r.get("version"),
                      "dateModified": d.get("dateModified"), "collections": d.get("collections") or []})
    return cli.finish(lines)


def list_(zot, args, p):
    """One line per note: the child notes of the items named, the notes in --collection, or every note.

The items are named by key or citation key (- reads a list from stdin). Each line: {key, parent?, title, code ok,
version, dateModified, collections}; not_found, ambiguous, collection_not_found.

Examples:
  p2z.py note list ronneberger2015unet
  p2z.py note list --collection 自然图像/Diffusion
"""
    return lines_of(zot, notes_in(zot, args))


def search(zot, args, p):
    """The notes whose text holds the query (Zotero's All Fields & Tags search), one line each, as note list's.

The query comes first (quote a phrase: "flow matching"), then any items, whose child notes are the ones searched
(- reads a list from stdin); --collection searches the notes in it. No note found is exit 1, as grep.

Examples:
  p2z.py note search "flow matching"
  p2z.py note search denoising ronneberger2015unet
"""
    hits = {r["key"] for r in zot.rows(f"{LIB}/items", {"q": args.query, "qmode": "everything", "itemType": "note"})}
    rows = [r for r in notes_in(zot, args) if "code" in r or r["key"] in hits]
    code = lines_of(zot, rows)
    return code if any("code" not in r for r in rows) else cli.ACT


def configure_take(p):
    p.add_argument("item", metavar="ITEM|NOTE", help="a note, or the item whose child notes to take: a key or citation key")
    p.add_argument("--title", help="only the notes whose first line is this")
    p.add_argument("-o", "--output", metavar="FILE|DIR/", help="a file (one note) or a directory/ (default: stdout)")


def configure_put(p):
    p.add_argument("inputs", nargs="*", metavar="FILE", help="note files; - reads one from stdin")
    cli.add_dry_run(p)
    p.add_argument("-i", dest="in_place", action="store_true", help="write the new key and version into each file")


def configure_list(p):
    cli.add_items(p, help="an item whose child notes to list: its key or citation key; - reads a list from stdin")
    p.add_argument("--collection", metavar="COLL", help="the notes in this collection: its key, path or name")


def configure_search(p):
    p.add_argument("query", metavar="QUERY", help="what the notes' text holds")
    configure_list(p)


COMMANDS = {"take": take, "put": put, "list": list_, "search": search}
CONFIGURE = {"take": configure_take, "put": configure_put, "list": configure_list, "search": configure_search}


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
