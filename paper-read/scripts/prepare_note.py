#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Take a paper's note, PDF and structured package out of Zotero into a scratch directory: step 1 of every change to a note.

The paper is its citation key or item key, resolved first by p2z.py items; - reads it from stdin, as a list that
names one paper (a value a line, or paper-to-zotero's JSON lines by `key`, else `cite`): several are `ambiguous` and
nothing is taken, a line reporting a skip or a failure upstream is passed on as it is, an empty list does nothing.
Into DIR, through paper-to-zotero's own commands, where <name> is <citation key>.<PDF title>:
  - <name>.pdf, the PDF the note was read in (its "读的版本：" line), or the best one for a new note (by the order
    `p2z.py pdf -h` gives); --title takes another PDF of the paper, and for a note read in another one, that one's
    PDF and package too, to compare the two versions;
  - <name>/, the PDF's structured package, and <name>.zotero.json, which PDF it is;
  - <name>.note.md, the note titled 论文笔记 without the links pr.py put added to its figures and tables, or, when
    the paper has none, a new note from the skeleton in references/note-format.md, its version in the 读的版本
    paragraph; --bare leaves the eight questions out, for a note that starts with one looked-up answer;
  - <name>.note.md.taken, the note as taken, which pr.py check compares question numbers against;
  - notes/, the paper's other child notes, left as leads.
pr.py check, quotes and put find these beside the note. A rerun into the same directory, after a parse for instance,
picks up what is already there.

stdout: one JSON object.
  ok          {note, taken, created, input, pdf_title, package, better_pdf, previous, old_notes, open_findings, paper}:
              input is <name>.pdf; better_pdf, the title of the library's best PDF when the note was read in a lesser
              one, else null; previous {pdf_title, input, package, code}, the version the note was read in when
              --title took another, else null (input and package null when it could not be taken, code saying why);
              open_findings counts the package's open findings by code; paper holds title, first_author, year,
              venue, doi and aka (the aka/ names) for the reader's identity check
  no_package  the same fields, package null: the PDF has no structured package yet (hint: how to make it). The note
              file is ready either way, for reading the PDF alone
  two_notes   two notes titled 论文笔记 (keys)
  any other   paper-to-zotero's own line about the paper, with step (its command) and, once the note is read,
              version (the PDF title it names): not_found, ambiguous (keys), no_pdf, not_on_disk, no_such_title
              (titles: the PDFs there; --title takes one), ...
Exit 0 = ok; 1 = any other code, or a line passed on reports a failure upstream; 2 = cannot go on (Zotero not
running, a usage error): stderr's last line is {code, hint}, with step when a paper-to-zotero command could not.

Examples:
  pr.py take xiaoTCACE2026 -o <scratch>/
  pr.py take --bare 9ZFX6QP6 -o <scratch>/
  pr.py take xiaoTCACE2026 --title Published-IEEE -o <scratch>/moved/
"""
import json
import re
import shlex
import shutil
import sys
from pathlib import Path

from prlib import cli, sources

TITLE = "论文笔记"
VERSION = re.compile(r"^读的版本：\s*(\S.*?)\s*$", re.M)
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")  # Zotero holds the date as typed: "2026-03", "6/2016"
TRUNK = [
    "这篇论文要解决什么问题，为什么重要？这是哪类论文？",
    "之前的工作怎么做，缺在哪里？",
    "论文如何解决这个问题？",
    "创新点是什么？",
    "做了哪些实验？",
    "结论站得住吗？",
    "有什么可以进一步探索的点？",
    "总结一下论文的主要内容",
]


def p2z(step, *args):
    """A paper-to-zotero command's JSON lines. Each gets the one resolved item key, so its first line is about it."""
    return cli.sibling(cli.P2Z, *step.split(), *args, step=step)[0]


def skeleton(cite, pdf_title, bare=False):
    head = f"---\nparent: {cite}\n---\n# {TITLE}\n\n"
    if bare:
        return f"{head}读的版本：{pdf_title}\n"
    trunk = "\n\n".join(f"## Q{i} {q} [待答]" for i, q in enumerate(TRUNK, 1))
    return f"{head}[待答]\n\n读的版本：{pdf_title}\n\n{trunk}\n"


def paper_of(item):
    first = (item.get("creators") or [{}])[0]
    year = YEAR.search(item.get("date") or "")
    venue = (item.get("publicationTitle") or item.get("proceedingsTitle") or item.get("conferenceName")
             or item.get("bookTitle") or "")
    return {"title": item.get("title"), "first_author": first.get("lastName") or first.get("name"),
            "year": year and year.group(), "venue": venue or None, "doi": item.get("DOI") or None,
            "aka": sorted(t["tag"][4:] for t in item.get("tags", []) if t.get("tag", "").startswith("aka/"))}


def open_findings(folder):
    record = next(Path(folder).glob("*.json"), None) if folder else None
    if not record:
        return {}
    try:
        findings = json.loads(record.read_text(encoding="utf-8")).get("findings", [])
    except (OSError, json.JSONDecodeError):
        return {}
    counts = {}
    for f in findings:
        if f.get("status") == "open":
            counts[f.get("code")] = counts.get(f.get("code"), 0) + 1
    return counts


def package_take(key, out, title=None):
    return p2z("package take", key, "-o", f"{out}/", *(["--title", title] if title else []))[0]


def previous_version(key, out, title):
    """The PDF and package of the version the note was read in, taken beside the new one."""
    got = package_take(key, out, title)
    if got.get("code") not in ("ok", "skipped"):
        return {"pdf_title": title, "input": None, "package": None, "code": got.get("code")}
    folder = Path(got["folder"])
    return {"pdf_title": title, "input": str(out / f"{folder.name}.pdf"),
            "package": str(folder) if folder.is_dir() else None, "code": got["code"]}


def take(value, out, args):
    """The one paper's line."""
    item = p2z("items", value)[0]
    if "itemType" not in item:   # not_found, ambiguous
        return {**item, "step": "items"}
    key = item["key"]
    cite = item.get("citationKey") or key
    out.mkdir(parents=True, exist_ok=True)
    notes = p2z("note take", key, "-o", f"{out / 'notes'}/")
    failed = next((l for l in notes if l.get("code") not in ("ok", "no_notes")), None)
    if failed:
        return {**failed, "step": "note take"}
    mine = [n for n in notes if n.get("code") == "ok" and n.get("title") == TITLE]
    if len(mine) > 1:
        return {"code": "two_notes", "keys": [n["key"] for n in mine],
                "hint": f"The paper has two notes titled {TITLE}: which to keep is the user's decision. Take the note "
                        "again once one is left."}
    text = Path(mine[0]["file"]).read_text(encoding="utf-8") if mine else None
    version = VERSION.search(text).group(1) if text and VERSION.search(text) else None

    got = package_take(key, out, args.title or version)
    if got.get("code") not in ("ok", "skipped"):
        return {**got, "step": "package take", "version": version}
    pdf_title = got.get("title")
    folder = Path(got["folder"])  # <cite>.<PDF title, made safe as a file name>, as package take names it
    pdf = out / f"{folder.name}.pdf"
    note = out / f"{folder.name}.note.md"
    taken = Path(f"{note}.taken")
    created = False
    if note.exists():
        # A rerun in the same change: the working file and its .taken stay as they are.
        if mine:
            Path(mine[0]["file"]).unlink(missing_ok=True)
    else:
        if mine:
            shutil.move(mine[0]["file"], note)
            note.write_text(sources.strip(note.read_text(encoding="utf-8")), encoding="utf-8")
        else:
            note.write_text(skeleton(cite, pdf_title, args.bare), encoding="utf-8")
            created = True
        shutil.copyfile(note, taken)

    package = folder.is_dir()
    best = p2z("pdf", key)[0].get("attachment_title")
    moved = bool(args.title and version and args.title != version)
    line = {
        "code": "ok" if package else "no_package", "note": str(note), "taken": str(taken), "created": created,
        "input": str(pdf), "pdf_title": pdf_title, "package": str(folder) if package else None,
        "better_pdf": best if best and best != pdf_title else None,
        "previous": previous_version(key, out, version) if moved else None,
        "old_notes": sorted(str(p) for p in (out / "notes").glob("*.note.md")),
        "open_findings": open_findings(folder) if package else {}, "paper": paper_of(item),
    }
    if not package:
        q = shlex.quote
        line["hint"] = (f"Parse the PDF: ocr.py parse {q(str(pdf))} -o {q(str(out))}/, then p2z.py package put "
                        f"{q(str(folder))}, then run this take again. Without paddleocr, read the PDF alone.")
    return line


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("paper", metavar="PAPER", help="its citation key or item key; - reads it from stdin")
    p.add_argument("-o", "--output", required=True, metavar="DIR/",
                   help="the scratch directory of this change, made if absent")
    p.add_argument("--bare", action="store_true", help="a new note without the eight questions (a looked-up answer)")
    p.add_argument("--title", metavar="PDF_TITLE", help="this PDF of the paper, not the one the note names or the best")
    args = cli.parse(p, argv)
    out = Path(args.output).expanduser().resolve()

    def run():
        named = cli.names([args.paper])
        passed = [n.line for n in named if n.line is not None]
        papers = [n.value for n in named if n.line is None]
        for line in passed:
            cli.emit(line)
        status = cli.ACT if any(line.get("code") != "skipped" for line in passed) else cli.OK
        if len(papers) > 1:
            cli.emit({"code": "ambiguous", "items": papers,
                      "hint": "The list names several papers; take one at a time. Nothing was taken."})
            return cli.ACT
        if papers:
            line = take(papers[0], out, args)
            cli.emit(line)
            status = max(status, cli.OK if line["code"] == "ok" else cli.ACT)
        return status

    return cli.run(run)


if __name__ == "__main__":
    sys.exit(main())
