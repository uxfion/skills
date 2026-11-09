#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Take a PDF's structured package out of Zotero to read, or put one back: the paddleocr parse beside each PDF.

Every PDF of a paper has a structured package beside it: a zip attachment of the same item under the PDF's title
(Published-IEEE). Outside Zotero no item tells which paper a file is, so the package is named <cite>.<title>
(zhuUnpairedImagetoImageTranslation2017.Published-CVF): its file <cite>.<title>.zip holds the paddleocr skill's
folder for that PDF, <cite>.<title>/ with <cite>.<title>.md, .json and imgs/. The PDF stays the authority; the
package is what agents read. Everything unpacked or parsed lives in DIR, a scratch directory, never in a project.
p2z.py trash, merge and update keep packages in step with their PDFs by themselves.

Exit codes, every command: 0 = all ok or skipped; 1 = not, then stderr's last line is {"summary": {total, ok,
skipped, failed}}; 2 = cannot go on (Zotero not running, local API off, no key) or a usage error, then stderr's last
line is {code, hint}.
"""
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

from p2zlib import cli, paper, zotero
from p2zlib.zotero import LIB

ZIP_TIME = (1980, 1, 1, 0, 0, 0)
SIDE = ".zotero.json"


def files_of(children):
    """(the PDFs best first, {title: the package rows under it, newest last}) among an item's children."""
    rows = zotero.attachment_rows(children)
    packages = {}
    for a in sorted((a for a in rows if a["contentType"] == paper.PACKAGE), key=lambda a: a["dateAdded"] or ""):
        packages.setdefault(a["title"], []).append(a)
    return [a for a in rows if a["contentType"] == "application/pdf"], packages


def on_disk(zot, key):
    path = zot.file_path(key)
    if not path or not os.path.isfile(path):
        raise cli.Stop("not_on_disk", hint="The file is not on this machine (not synced yet, or a linked file that "
                       "moved); sync Zotero, then run again.", attachment=key)
    return path


def unzip(zpath, folder):
    """The package into folder, its md and json renamed to the folder's name."""
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        inner = names[0].split("/", 1)[0] if names else ""
        for n in names:
            top, _, rest = n.partition("/")
            parts = Path(rest).parts
            if top != inner or not rest or rest.startswith("/") or ".." in parts:
                raise cli.Stop("bad_package", hint="The zip holds an entry outside its one folder; look at it in Zotero.",
                               entry=n)
            if rest in (f"{inner}.md", f"{inner}.json"):
                rest = folder.name + rest[len(inner):]
            target = folder / rest
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(n))


def build(folder, inner):
    """The folder as a zip under <inner>/, its md and json renamed to inner: sorted entries, fixed times, so the same
    content gives the same bytes. Dot files (paddleocr's .lock) stay out."""
    buf = io.BytesIO()
    files = sorted((p for p in folder.rglob("*") if p.is_file()), key=lambda p: p.relative_to(folder).as_posix())
    with zipfile.ZipFile(buf, "w") as z:
        for f in files:
            rel = f.relative_to(folder).as_posix()
            if any(part.startswith(".") for part in rel.split("/")):
                continue
            if rel in (f"{folder.name}.md", f"{folder.name}.json"):
                rel = inner + rel[len(folder.name):]
            info = zipfile.ZipInfo(f"{inner}/{rel}", ZIP_TIME)
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            z.writestr(info, f.read_bytes())
    return buf.getvalue()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---- take -------------------------------------------------------------------------------------------------------

def chosen(pdfs, packages, args):
    if args.missing:
        return [p for p in pdfs if not packages.get(p["title"])]
    if args.title:
        return [p for p in pdfs if p["title"] == args.title]
    return pdfs if args.every else pdfs[:1]


def take_one(zot, item, pdf, packages, to):
    d = zotero.data(item)
    stem = zotero.package_stem(d.get("citationKey") or item["key"], pdf["title"])
    folder, link, side = to / stem, to / f"{stem}.pdf", to / f"{stem}{SIDE}"
    package = (packages.get(pdf["title"]) or [None])[-1]
    if package and folder.exists():
        return cli.skipped("already_taken", folder=str(folder))
    path = on_disk(zot, pdf["key"])
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(path)
    if package:
        unzip(on_disk(zot, package["key"]), folder)
    side.write_text(json.dumps({"key": item["key"], "cite": d.get("citationKey"), "attachment": pdf["key"],
                                "title": pdf["title"], "pdf": path, "package": package and package["key"],
                                "package_md5": package and package["md5"]}, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    return cli.ok(pdf=path, input=str(link), folder=str(folder), package=package and package["key"])


def library(zot):
    """Every top-level item outside the trash, with its children: one listing of the whole library."""
    rows = zot.rows(f"{LIB}/items")
    kids = {}
    for r in rows:
        parent = zotero.data(r).get("parentItem")
        if parent:
            kids.setdefault(parent, []).append(r)
    return [(r, kids.get(r["key"], [])) for r in rows if zotero.is_top(r) and not zotero.in_trash(r)]


def take(zot, args, p):
    """PDFs' packages out of Zotero into DIR to read, or the PDFs linked there for a parse.

For each PDF picked, into -o DIR/: <cite>.<title>.pdf, a link to the PDF in Zotero's storage (paddleocr's input: it
names its output after it), <cite>.<title>.zotero.json, where it came from (put reads it), and, when the PDF has a
package, <cite>.<title>/ unzipped from it (under today's name, should the key or title have changed since): read it. No
package (`package: null`): the paddleocr skill's `ocr.py parse <input> -o DIR/` writes that same folder, then put. The
PDFs of the items named: by default the best (p2z.py pdf's first row); --title the one with that attachment title;
--every all of them; --missing those without a package. With no item named, --missing and --every cover the whole
library: the PDFs without a package (links only), for a batch parse; every PDF, for reprocessing them all after the
paddleocr skill changed.

stdout: one line per PDF {cite, key, title, code ok, pdf, input, folder, package: its key | null}; skipped
already_taken: DIR already holds that folder (read it, or delete it and take again); no_pdf (the item has none),
no_such_title, not_on_disk (the file is not on this machine: sync Zotero), not_a_parent (an attachment or note
named: name its parent, parentItem), not_found, ambiguous.

Examples:
  p2z.py package take savageLargeLanguageModel2024 -o <scratch>/papers/
  p2z.py package take ABCD1234 --missing -o <scratch>/structured/
"""
    if not args.items and not (args.missing or args.every):
        p.error("name the items (- reads a list from stdin), or give --missing or --every for the whole library")
    named = cli.names(args.items)
    to = Path(args.output).expanduser().resolve()
    to.mkdir(parents=True, exist_ok=True)
    out = cli.Lines()
    if args.items:
        groups = []
        for _, name, key in cli.resolved(zot, named, out):
            item = zot.item(key)
            d = zotero.data(item)
            if not zotero.is_top(item):
                out.put(cli.Stop("not_a_parent", parentItem=d.get("parentItem"),
                                 hint="An attachment or note has no PDFs of its own; name its parent item (parentItem).")
                        .line(**cli.head(name, key)))
            else:
                groups.append((item, zot.children(key)))
    else:
        groups = library(zot)
    for item, children in groups:
        head = {"cite": zotero.data(item).get("citationKey"), "key": item["key"]}
        pdfs, packages = files_of(children)
        picked = chosen(pdfs, packages, args)
        if not pdfs and named:
            out.put(cli.Stop("no_pdf", hint="The item has no PDF; paper-to-zotero's import can fetch one.").line(**head))
        elif args.title and not picked:
            out.put(cli.Stop("no_such_title", hint="No PDF of the item has that title; p2z.py pdf lists them.",
                             titles=[p["title"] for p in pdfs]).line(**head))
        for pdf in picked:
            out.add({**head, "title": pdf["title"]}, lambda: take_one(zot, item, pdf, packages, to))
    return out.finish()

def put_one(zot, folder, args):
    side_path = folder.with_name(folder.name + SIDE)
    if not side_path.is_file():
        raise cli.Stop("not_taken", hint="put takes a folder take prepared, its <name>.zotero.json beside it: take the "
                       "PDF, parse the link take made with ocr.py parse <input> -o DIR/, then put.")
    side = json.loads(side_path.read_text(encoding="utf-8"))
    head = {"cite": side.get("cite"), "key": side["key"], "title": side["title"]}
    json_path, md_path = folder / f"{folder.name}.json", folder / f"{folder.name}.md"
    if not (json_path.is_file() and md_path.is_file()):
        raise cli.Stop("not_parsed", hint="No <name>.json and <name>.md in the folder: parse the link take made with "
                       "ocr.py parse <input> -o DIR/, DIR the folder's directory.", **head)
    pdf, item = zot.item(side["attachment"]), zot.item(side["key"])
    if pdf is None or item is None or zotero.in_trash(pdf) or zotero.in_trash(item):
        raise cli.Stop("pdf_gone", hint="The PDF this folder was parsed from has left the library (trashed, or merged "
                       "away); there is nothing to put it beside.", **head)
    pd = zotero.data(pdf)
    title, parent = pd.get("title"), pd.get("parentItem")
    head["title"] = title
    path = on_disk(zot, pdf["key"])
    source = (json.loads(json_path.read_text(encoding="utf-8")).get("source") or {}).get("sha256")
    if source != sha256(path):
        raise cli.Stop("source_mismatch", hint="The folder was parsed from another file than this PDF; take the PDF again "
                       "and parse the link take made: ocr.py parse <input> -o DIR/.", **head)
    stem = zotero.package_stem(zotero.data(item).get("citationKey") or side["key"], title)
    body = build(folder, stem)
    md5 = hashlib.md5(body).hexdigest()
    _, packages = files_of(zot.children(parent))
    current = packages.get(title, [])
    same = next((a for a in current if a["md5"] == md5), None)
    if same:
        return cli.skipped("already_current", package=same["key"], md5=md5, **head)
    if {a["key"] for a in current} != ({side["package"]} - {None}):
        raise cli.Stop("changed_since_take", hint="The PDF's package in Zotero is not the one take unzipped: another run "
                       "put one meanwhile. Take it again into a new directory, redo the changes there, and put that.",
                       packages=[a["key"] for a in current], **head)
    zpath, filename = folder.with_name(folder.name + ".zip"), stem + ".zip"
    zpath.write_bytes(body)
    replaced = [a["key"] for a in current]
    try:
        res = zot.attach(parent, zpath, title=title, url=None, filename=filename, dry_run=args.dry_run)
    finally:
        zpath.unlink()
    if args.dry_run:
        return cli.ok(dry_run=True, md5=md5, size=len(body), filename=filename, replaces=replaced, **head)
    for key in replaced:
        zot.trash(key)
    side.update(package=res["attachment"], package_md5=md5)
    side_path.write_text(json.dumps(side, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return cli.ok(package=res["attachment"], md5=md5, **head, **({"replaced": replaced} if replaced else {}))


def put(zot, args, p):
    """Folders take prepared, zipped back onto their items as their PDFs' packages.

After a parse, after edits (settling a parse), after a new paddleocr processed it again. The zip is built the same way
every time, so an unchanged folder gives the bytes the item already holds: skipped. A package the PDF has is replaced
only when it is the one take unzipped: the new zip is attached and read back, then the old one goes to the trash (a
derived copy, undoable for 30 days; no confirmation asked).

stdout: one line per folder {folder, cite, key, title, code ok, package, md5, replaced?: [old package keys]};
skipped already_current: the item holds this very zip; not_taken (no <folder>.zotero.json beside the folder),
not_parsed (no <stem>.json and .md in the folder), pdf_gone (the PDF left the library), source_mismatch (the folder
was parsed from another file), changed_since_take (another run put a package meanwhile: take again into a new DIR,
redo the changes there, put that), bad_package (a zip entry outside its folder), and attach's codes.

Examples:
  p2z.py package put <scratch>/structured/*/
  p2z.py package put -n <scratch>/papers/savageLargeLanguageModel2024.Published-Nature/
"""
    if not args.folders:
        p.error("name the folders take prepared, or - to read their paths from stdin")
    folders = cli.paths(args.folders)
    if not args.dry_run:
        zot.write_headers()
    out = cli.Lines()
    for f in folders:
        folder = Path(f).expanduser().resolve()
        out.add({"folder": str(folder)}, lambda: put_one(zot, folder, args))
    return out.finish()


# ---- names ------------------------------------------------------------------------------------------------------

def names(zot, args, p):
    """Each package of the items named (none named: the library's) renamed in place to <cite>.<title>.zip.

As Zotero renames a file (no upload): for a citation key changed in Zotero itself. stdout: one line per item {key, code
ok, renamed: [{key, from, to}]} | skipped all_named; not_found, ambiguous.

Examples:
  p2z.py package names zhuUnpairedImagetoImageTranslation2017
"""
    out = cli.Lines()
    if args.items:
        keys = [key for _, _, key in cli.resolved(zot, cli.names(args.items), out)]
    else:
        keys = sorted({zotero.data(r).get("parentItem") for r in zot.rows(f"{LIB}/items")
                       if zotero.data(r).get("contentType") == paper.PACKAGE and not zotero.in_trash(r)} - {None})
    if keys and out.stopped is None:
        try:
            zot.write_headers()
        except cli.Stop as stop:
            if stop.exit != cli.CANNOT:
                raise
            out.stop(stop)
    for key in keys:
        out.add({"key": key}, lambda: (cli.ok(renamed=r) if (r := zot.name_packages(key)) else cli.skipped("all_named")))
    return out.finish()


def configure_take(p):
    cli.add_items(p)
    which = p.add_mutually_exclusive_group()
    which.add_argument("--title", help="the PDF with this attachment title (Preprint-arXiv-v7)")
    which.add_argument("--every", action="store_true", help="every PDF of the items (no item named: the library's)")
    which.add_argument("--missing", action="store_true", help="the PDFs without a package (no item named: the library's)")
    p.add_argument("-o", "--output", required=True, metavar="DIR/",
                   help="where the packages go: a folder in the scratch directory (made if absent)")


def configure_put(p):
    p.add_argument("folders", nargs="*", metavar="FOLDER", help="folders take prepared: DIR/<cite>.<title>/; - reads a list")
    cli.add_dry_run(p)


COMMANDS = {"take": take, "put": put, "names": names}
CONFIGURE = {"take": configure_take, "put": configure_put, "names": cli.add_items}


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
