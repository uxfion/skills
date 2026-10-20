#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write a child note from a small Markdown subset on each Zotero item named, creating it or updating the note that carries a marker.

Markdown -> note HTML: paragraphs -> <p>, "- " lists -> <ul><li>, "# " / "## " / "### " -> <h1>/<h2>/<h3>,
**x** -> <strong>, *x* -> <em>, [t](u) -> <a href>; everything else is escaped as it is. --text takes a literal
\\n as a line break.

With --marker M the note opens with the paragraph <p>M</p> (Zotero shows it as the note's title), and the child
note of the item whose first paragraph or heading reads M is the one updated: PATCHed with its version (read again
and retried once on a version conflict), left alone when its HTML is already the same. Without --marker every run
adds a new note. Every write is read back.

Items: --key and --cite (the top-level item carrying that citationKey); the same note goes to each.
stdout: one line per item {key, cite?, code, note_key, action, marker, version, retried} (--dry-run: the `html`
it would write, no version), then {"summary": {total, ok, skipped, failed}}.
  ok                 action created | updated
  skipped            reason unchanged: the marked note already reads so
  not_found          no item with that key
  not_a_parent       the key is an attachment or a note (`itemType`, `parent`); notes hang off regular items
  marker_ambiguous   several child notes open with the marker (`note_keys`); delete the extras, then rerun
  cite_not_found     no top-level item carries the citationKey; cite_ambiguous: several do (`keys`), pass --key
  version_conflict   the note changed twice while it was being written; wait, then rerun
  write_denied       the library is not editable
  write_failed       Zotero did not take the note; see status and detail
  readback_mismatch  the write was accepted, but the note reads back otherwise; look at it in Zotero
  not_run            Zotero stopped answering before this item (summary.stopped says why)
A note that converts to nothing (empty_note) or a --file that is not there (file_not_found) is one line, and
nothing is asked of Zotero.
Exit 0 = every item ok, 1 = some item not (or empty_note, file_not_found), 2 = cannot check (zotero_unreachable,
local_api_disabled, no_key, key_rejected, server_mismatch).

Examples:
  uv run scripts/note.py --cite liu2022progressive --file notes/liu.md --marker "p2z: verification" --dry-run
  uv run scripts/note.py --key ABCD1234 --text "# Read 2026-09-23\\n- claims X\\n- **no** code" --marker "p2z: reading"
"""
import html
import re
from pathlib import Path

from p2zlib import cli, paper, zotero

HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
BULLET = re.compile(r"^[-*]\s+(.*)$")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
EM = re.compile(r"\*([^*]+)\*")
EDITOR_WRAP = re.compile(r"^\s*<div\b[^>]*data-schema-version[^>]*>(.*)</div>\s*$", re.S)
FIRST_BLOCK = re.compile(r"<(p|h[1-6])\b[^>]*>(.*?)</\1>", re.S)
TAG = re.compile(r"<[^>]+>")


# ---- Markdown subset -> note HTML ---------------------------------------------------------------------------

def marks(s):
    """Escape, then **bold** and *em*."""
    s = html.escape(s, quote=False)
    s = BOLD.sub(r"<strong>\1</strong>", s)
    return EM.sub(r"<em>\1</em>", s)


def inline(s):
    """Links first (their text gets the marks too, the URL is escaped as an attribute), marks on the rest."""
    out, pos = [], 0
    for m in LINK.finditer(s):
        out.append(marks(s[pos:m.start()]))
        out.append(f'<a href="{html.escape(m.group(2), quote=True)}">{marks(m.group(1))}</a>')
        pos = m.end()
    out.append(marks(s[pos:]))
    return "".join(out)


def to_html(md):
    """Paragraphs, "- " lists (indented lines continue an item), #/##/### headings; blank lines separate blocks."""
    blocks, para, items = [], [], []

    def flush():
        if para:
            blocks.append("<p>" + "\n".join(inline(line) for line in para) + "</p>")
            para.clear()
        if items:
            blocks.append("<ul>\n" + "\n".join(f"<li>{inline(i)}</li>" for i in items) + "\n</ul>")
            items.clear()

    for raw in md.splitlines():
        stripped = raw.strip()
        if not stripped:
            flush()
            continue
        m = HEADING.match(stripped)
        if m:
            flush()
            level = len(m.group(1))
            blocks.append(f"<h{level}>{inline(m.group(2).strip())}</h{level}>")
            continue
        m = BULLET.match(stripped)
        if m:
            if para:
                flush()
            items.append(m.group(1))
            continue
        if items and raw.startswith((" ", "\t")):
            items[-1] += " " + stripped
            continue
        if items:
            flush()
        para.append(stripped)
    flush()
    return "\n".join(blocks)


# The marker is a plain first paragraph <p>M</p>. Probed 2026-09-23 against the local API: <p data-p2z-marker="M">,
# <p><em>M</em></p>, <p>M</p>, a <div data-schema-version> wrapper and <h1>M</h1> all came back byte for byte, so the
# simplest form wins. It also survives the note editor, which keeps only its own schema (a data-* attribute would
# go once the user edits the note), so detection strips the editor's wrapper and inline tags before comparing.
def marker_of(note_html):
    """Text of the note's first paragraph or heading (editor wrapper and inline tags stripped); None without one."""
    inner = note_html or ""
    m = EDITOR_WRAP.match(inner)
    if m:
        inner = m.group(1)
    m = FIRST_BLOCK.match(inner.lstrip())
    if not m:
        return None
    return html.unescape(TAG.sub("", m.group(2))).strip()


# ---- the note on one item -----------------------------------------------------------------------------------

def check(p, args):
    """Read the Markdown and build the note's HTML once, before Zotero is asked."""
    if args.marker is not None and not args.marker.strip():
        p.error("--marker must not be blank")
    args.marker = args.marker.strip() if args.marker else None
    if args.text is not None:
        md = args.text if "\n" in args.text else args.text.replace("\\n", "\n")
    else:
        path = Path(args.file).expanduser()
        if not path.is_file():
            raise cli.Stop("file_not_found", hint="--file names the Markdown file to turn into the note.", file=str(path))
        md = path.read_text(encoding="utf-8")
    body = to_html(md)
    if not body:
        raise cli.Stop("empty_note", hint="The Markdown converts to nothing; give the note some text.")
    args.html = (f"<p>{html.escape(args.marker, quote=False)}</p>\n" if args.marker else "") + body


def marked_note(zot, key, marker):
    hits = [c for c in zot.children(key)
            if zotero.data(c).get("itemType") == "note" and marker_of(zotero.data(c).get("note")) == marker]
    if len(hits) > 1:
        raise cli.Stop("marker_ambiguous", hint="Several child notes open with this marker; delete the extras in Zotero, "
                       "then rerun.", marker=marker, note_keys=[n["key"] for n in hits])
    return hits[0] if hits else None


def process(zot, key, args):
    item = zot.item(key)
    if item is None:
        raise cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND)
    d = zotero.data(item)
    if not paper.is_top(d):
        raise cli.Stop("not_a_parent", hint="Notes hang off regular items; pass the parent item's key.",
                       itemType=d.get("itemType"), parent=d.get("parentItem"))
    target = marked_note(zot, key, args.marker) if args.marker else None
    line = {"marker": args.marker}

    def plan(n):
        return None if zotero.data(n).get("note") == args.html else {"note": args.html}

    if target and plan(target) is None:
        return cli.skipped("unchanged", note_key=target["key"], **line, version=target.get("version"), retried=False)
    if args.dry_run:
        return cli.ok(note_key=target and target["key"], action="updated" if target else "created", **line,
                      html=args.html, dry_run=True)
    if target:
        current, sent, retried = zot.update(target["key"], plan, target)
        if sent is None:
            return cli.skipped("unchanged", note_key=target["key"], **line, version=current.get("version"), retried=retried)
        note_key, action = target["key"], "updated"
    else:
        created = zot.post_one({"itemType": "note", "parentItem": key, "note": args.html},
                               hint="Zotero did not create the note; see detail.")
        note_key, action, retried = created["key"], "created", False
    after = zot.item(note_key)
    if after is None or zotero.data(after).get("note") != args.html:
        raise cli.Stop("readback_mismatch", hint="The write was accepted, but the note reads back otherwise; look at it in Zotero.",
                       note_key=note_key, action=action, **line, read_back=zotero.data(after).get("note"))
    return cli.ok(note_key=note_key, action=action, **line, version=after.get("version"), retried=retried)


def configure(p):
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", metavar="NOTE.md", help="Markdown file with the note's text")
    src.add_argument("--text", metavar="TEXT", help="the note's Markdown inline (a literal \\n is a line break)")
    p.add_argument("--marker", metavar="M", help="the note's first line; the child note opening with it is updated instead")


def main(argv=None):
    return cli.main_items(__doc__, process, argv, configure=configure, check=check)


if __name__ == "__main__":
    raise SystemExit(main())
