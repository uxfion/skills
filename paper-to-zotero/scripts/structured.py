#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Take a PDF's structured package out of Zotero to read, or put one back: the paddleocr parse beside each PDF.

Every PDF of a paper has a structured package beside it: a zip attachment of the same item under the PDF's title
(Published-IEEE). Outside Zotero no item tells which paper a file is, so the package is named <cite>.<title>
(zotero.package_stem: zhuUnpairedImagetoImageTranslation2017.Published-CVF): its file <cite>.<title>.zip holds the
paddleocr skill's folder for that PDF, <cite>.<title>/ with <cite>.<title>.md, .json and imgs/. The PDF stays the
authority; the package is what agents read. Everything unpacked or parsed lives in DIR, a scratch directory, never
in a project.

  take   For each PDF named, into DIR: <cite>.<title>.pdf, a link to the PDF in Zotero's storage (paddleocr's input:
         it names its output after it), <cite>.<title>.zotero.json, where it came from (put reads it), and, when the
         PDF has a package, <cite>.<title>/ unzipped from it (under today's name, should the key or title have
         changed since): read it. No
         package (`package: null`): run the paddleocr skill's parse on the link with -o DIR, which writes that same
         folder, then put. The PDFs of the items named: by default the best (read_library pdf's first row); --title
         the one with that attachment title; --every all of them; --missing those without a package. With no item
         named, --missing and --every cover the whole library: the PDFs without a package (links only), for a
         batch parse; every PDF, for reprocessing them all after the paddleocr skill changed.
  put    Each FOLDER take prepared, zipped back onto its item as that PDF's package: after a parse, after edits
         (settling a parse), after a new paddleocr processed it again. The zip is built the same way every time, so
         an unchanged folder gives the bytes the item already holds: skipped. A package the PDF has is replaced only
         when it is the one take unzipped: the new zip is attached and read back, then the old one goes to the trash
         (a derived copy, undoable for 30 days; no confirmation asked).
  names  Each package of the items named (no item named: the library's) renamed in place to <cite>.<title>.zip, as
         Zotero renames a file (no upload). trash_item, merge_items and update_item keep packages in step with their
         PDFs by themselves; this is for a citation key changed in Zotero itself.

stdout: one line per PDF (take) or folder (put), then {"summary"}.
  take  {cite, key, title, code ok, pdf, input, folder, package: its key | null}
        skipped already_taken: DIR already holds that folder (read it, or delete it and take again)
  put   {folder, cite, key, title, code ok, package, md5, replaced?: [old package keys]}
        skipped already_current: the item holds this very zip
  names {key, code ok, renamed: [{key, from, to}]} | skipped all_named
  no_pdf (take: the item has none), no_such_title, not_on_disk (the file is not on this machine: sync Zotero),
  not_taken (no <folder>.zotero.json beside the folder), not_parsed (no <stem>.json and .md in the folder),
  pdf_gone (the PDF left the library), source_mismatch (the folder was parsed from another file),
  changed_since_take (another run put a package meanwhile: take again into a new DIR, redo the changes there,
  put that), bad_package (a zip entry outside its folder), + attach's codes.
Exit 0 = all ok or skipped; 1 = not; 2 = cannot go on (Zotero not running, local API off, no key).

Examples:
  uv run scripts/structured.py take --cite savageLargeLanguageModel2024 --to <scratch>/papers
  uv run scripts/structured.py take --key ABCD1234 --missing --to <work>/structured
  uv run scripts/structured.py put <work>/structured/*/
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
    rows = zot.pages(f"{LIB}/items")
    kids = {}
    for r in rows:
        parent = zotero.data(r).get("parentItem")
        if parent:
            kids.setdefault(parent, []).append(r)
    return [(r, kids.get(r["key"], [])) for r in rows if zotero.is_top(r) and not zotero.in_trash(r)]


def cmd_take(zot, args):
    to = Path(args.to).expanduser().resolve()
    to.mkdir(parents=True, exist_ok=True)
    out = cli.Lines()
    if args.key or args.cite:
        named = []
        for key, cite, failure in zot.targets(args.key, args.cite):
            if failure is not None:
                out.lines.append(failure.line(**cli.head(key, cite)))
            else:
                named.append((key, cite))
        found = zot.items([k for k, _ in named])
        groups = []
        for key, cite in named:
            if key not in found:
                out.lines.append(cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND).line(**cli.head(key, cite)))
            else:
                groups.append((found[key], zot.children(key)))
    else:
        groups = library(zot)
    for item, children in groups:
        head = {"cite": zotero.data(item).get("citationKey"), "key": item["key"]}
        pdfs, packages = files_of(children)
        picked = chosen(pdfs, packages, args)
        if not pdfs and (args.key or args.cite):
            out.lines.append(cli.Stop("no_pdf", hint="The item has no PDF; paper-to-zotero's import steps can fetch one.")
                             .line(**head))
        elif args.title and not picked:
            out.lines.append(cli.Stop("no_such_title", hint="No PDF of the item has that title; read_library pdf lists "
                                      "them.", titles=[p["title"] for p in pdfs]).line(**head))
        for pdf in picked:
            out.add({**head, "title": pdf["title"]}, lambda: take_one(zot, item, pdf, packages, to))
    return out.finish()


# ---- put --------------------------------------------------------------------------------------------------------

def put_one(zot, folder, args):
    side_path = folder.with_name(folder.name + SIDE)
    if not side_path.is_file():
        raise cli.Stop("not_taken", hint="put takes a folder take prepared, its <name>.zotero.json beside it: take the "
                       "PDF, parse the link take made into that directory, then put.")
    side = json.loads(side_path.read_text(encoding="utf-8"))
    head = {"cite": side.get("cite"), "key": side["key"], "title": side["title"]}
    json_path, md_path = folder / f"{folder.name}.json", folder / f"{folder.name}.md"
    if not (json_path.is_file() and md_path.is_file()):
        raise cli.Stop("not_parsed", hint="No <name>.json and <name>.md in the folder: run the paddleocr skill's parse "
                       "on the link take made, with -o its directory.", **head)
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
                       "and parse the link take made.", **head)
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


def cmd_put(zot, args):
    if not args.dry_run:
        zot.write_headers()
    out = cli.Lines()
    for f in args.folders:
        folder = Path(f).expanduser().resolve()
        out.add({"folder": str(folder)}, lambda: put_one(zot, folder, args))
    return out.finish({"dry_run": True} if args.dry_run else None)


# ---- names ------------------------------------------------------------------------------------------------------

def cmd_names(zot, args):
    zot.write_headers()
    out = cli.Lines()
    if args.key or args.cite:
        keys = []
        for key, cite, failure in zot.targets(args.key, args.cite):
            if failure is not None:
                out.lines.append(failure.line(**cli.head(key, cite)))
            else:
                keys.append(key)
    else:
        keys = sorted({zotero.data(r).get("parentItem") for r in zot.pages(f"{LIB}/items")
                       if zotero.data(r).get("contentType") == paper.PACKAGE and not zotero.in_trash(r)} - {None})
    for key in keys:
        out.add({"key": key}, lambda: (cli.ok(renamed=r) if (r := zot.name_packages(key)) else cli.skipped("all_named")))
    return out.finish()


def parse_args(argv):
    p = cli.parser(__doc__)
    cli.add_base_url(p)
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")
    s = sub.add_parser("take", help="unzip PDFs' packages (or link the PDFs for a parse) into a scratch directory")
    cli.add_targets(s)
    which = s.add_mutually_exclusive_group()
    which.add_argument("--title", help="the PDF with this attachment title (Preprint-arXiv-v7)")
    which.add_argument("--every", action="store_true", help="every PDF of the items (no item named: the library's)")
    which.add_argument("--missing", action="store_true", help="the PDFs without a package (no item named: the library's)")
    s.add_argument("--to", required=True, metavar="DIR", help="the scratch directory (made if absent)")
    s.set_defaults(func=cmd_take)
    s = sub.add_parser("put", help="zip folders back onto their items as their PDFs' packages")
    s.add_argument("folders", nargs="+", metavar="FOLDER", help="folders take prepared: DIR/<cite>.<title>/")
    s.add_argument("--dry-run", action="store_true", help="show what would be written; write nothing")
    s.set_defaults(func=cmd_put)
    s = sub.add_parser("names", help="rename packages in place to <cite>.<title>.zip")
    cli.add_targets(s)
    s.set_defaults(func=cmd_names)
    args = p.parse_args(argv)
    if args.command == "take":
        cli.targets_of(p, args, required=not (args.missing or args.every))
    elif args.command == "names":
        cli.targets_of(p, args, required=False)
    return args


def main(argv=None):
    args = parse_args(argv)
    return cli.run(lambda: args.func(zotero.Zotero(args.base_url), args))


if __name__ == "__main__":
    raise SystemExit(main())
