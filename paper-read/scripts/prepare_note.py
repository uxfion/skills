#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Take a paper's note, structured package and PDF out of Zotero into a scratch directory: step 1 of every change to a note.

  uv run scripts/prepare_note.py --cite <citation key> -o <scratch dir> [--bare] [--title <PDF title>]

Through paper-to-zotero's own commands (`structured take`, `note take`, `read_library items` and `pdf`):
  - the package and the PDF of the version the note was read in (its "读的版本：" line), or the best PDF for a new note
    (best by the order `p2z.py read_library pdf --help` gives); --title takes another PDF of the paper, and for a note
    read in another one, that one's PDF and package too, to compare the two versions;
  - the note titled 论文笔记 as <dir>/<package folder name>.note.md, or, when the paper has none, a new note from the
    skeleton in references/note-format.md, its version in the 读的版本 paragraph; --bare leaves the eight questions
    out, for a note that starts with one looked-up answer;
  - beside it <note>.taken, the note as taken, which check_note.py compares question numbers against;
  - the paper's other child notes, left in <dir>/notes/ as leads.
A rerun into the same directory, after a parse for instance, picks up what is already there.

stdout: one JSON object.
  ok          {note, taken, created, pdf, pdf_title, package, better_pdf, previous, old_notes, open_findings, paper}:
              better_pdf, the title of the library's best PDF when the note was read in a lesser one, else null;
              previous {pdf_title, pdf, package, code}, the version the note was read in when --title took another,
              else null; its pdf and package are null when structured take could not take it, and code says why
              (no_such_title: no PDF of that title is left, as after a rename; anything else, p2z's own code); open_findings counts the package's open
              findings by code; paper holds title, first_author, year, venue, doi and aka (the aka/ names) for the
              reader's identity check
  no_package  the same fields, package null: the PDF has no structured package yet. Parse pdf with the paddleocr skill,
              structured put, run again; the note file is ready either way, for reading the PDF alone
  two_notes   two notes titled 论文笔记 (keys): which to keep is the user's decision
  failed      a paper-to-zotero command failed: its lines are in detail, its stderr in stderr. no_such_title among them:
              the PDF the note names in 读的版本 is not in the library under that title; its titles lists those there,
              and --title takes one of them
Exit 0 = ok; 1 = no_package, two_notes or failed.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
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


def p2z(*args):
    """Run a paper-to-zotero command; its JSON lines and exit code. PAPER_READ_P2Z points elsewhere (tests)."""
    script = os.environ.get("PAPER_READ_P2Z") or str(SKILL.parent / "paper-to-zotero" / "scripts" / "p2z.py")
    done = subprocess.run(["uv", "run", "--quiet", script, *args], capture_output=True, text=True)
    lines = []
    for line in done.stdout.splitlines():
        try:
            lines.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return lines, done.returncode, done.stderr


def skeleton(cite, pdf_title, bare=False):
    head = f"---\nparent: {cite}\n---\n# {TITLE}\n\n"
    if bare:
        return f"{head}读的版本：{pdf_title}\n"
    trunk = "\n\n".join(f"## Q{i} {q} [待答]" for i, q in enumerate(TRUNK, 1))
    return f"{head}[待答]\n\n读的版本：{pdf_title}\n\n{trunk}\n"


def paper_of(cite):
    items, _, _ = p2z("read_library", "items", "--cite", cite)
    item = next((i for i in items if i.get("citationKey") == cite), None)
    if not item:
        return None
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


def best_pdf(cite):
    """The title of the paper's best PDF, by paper-to-zotero's order."""
    lines, _, _ = p2z("read_library", "pdf", "--cite", cite)
    return next((l.get("attachment_title") for l in lines if l.get("citationKey") == cite and l.get("attachment_title")),
                None)


def previous_version(cite, out, title):
    """The PDF and package of the version the note was read in, taken beside the new one."""
    lines, _, _ = p2z("structured", "take", "--cite", cite, "-o", str(out), "--title", title)
    line = next((l for l in lines if l.get("cite") == cite), {})
    if line.get("code") not in ("ok", "skipped"):
        return {"pdf_title": title, "pdf": None, "package": None, "code": line.get("code") or "failed"}
    folder = Path(line["folder"])
    return {"pdf_title": title, "pdf": str(out / f"{folder.name}.pdf"), "package": str(folder) if folder.is_dir() else None,
            "code": line["code"]}


def take_notes(cite, notes_dir):
    """The paper's child notes taken into notes_dir; exit 1 with no_notes is a paper without notes, 2 a failure."""
    lines, code, err = p2z("note", "take", "--cite", cite, "-o", f"{notes_dir}/")
    if code >= 2 or (code == 1 and not any(l.get("code") in ("ok", "no_notes") for l in lines)):
        return None, {"code": "failed", "step": "note take", "detail": lines, "stderr": err.strip()}
    return [l for l in lines if l.get("code") == "ok" and l.get("file")], None


def main(argv=None):
    first, _, rest = __doc__.strip().partition("\n")
    ap = argparse.ArgumentParser(description=first, epilog=rest.strip(), formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cite", required=True, help="the paper's citation key")
    ap.add_argument("-o", "--out", required=True, help="the scratch directory for this change (made if absent)")
    ap.add_argument("--bare", action="store_true", help="a new note without the eight questions (a looked-up answer)")
    ap.add_argument("--title", metavar="PDF_TITLE", help="this PDF of the paper, not the one the note names or the best")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cite = args.cite

    notes, failed = take_notes(cite, out / "notes")
    if failed:
        print(json.dumps(failed, ensure_ascii=False))
        return 1
    mine = [n for n in notes if n.get("title") == TITLE]
    if len(mine) > 1:
        print(json.dumps({"code": "two_notes", "keys": [n["key"] for n in mine]}, ensure_ascii=False))
        return 1
    text = Path(mine[0]["file"]).read_text(encoding="utf-8") if mine else None
    version = VERSION.search(text).group(1) if text and VERSION.search(text) else None

    wanted = args.title or version
    take = ["structured", "take", "--cite", cite, "-o", str(out)] + (["--title", wanted] if wanted else [])
    lines, code, err = p2z(*take)
    got = next((l for l in lines if l.get("cite") == cite), None)
    if not got or got.get("code") not in ("ok", "skipped"):
        print(json.dumps({"code": "failed", "step": "structured take", "version": version, "detail": lines,
                          "stderr": err.strip()}, ensure_ascii=False))
        return 1
    pdf_title = got.get("title")
    folder = Path(got["folder"])  # <cite>.<PDF title, made safe as a file name>, as structured take names it
    stem = folder.name
    pdf = out / f"{stem}.pdf"
    note = out / f"{stem}.note.md"
    taken = Path(f"{note}.taken")
    created = False
    if note.exists():
        # A rerun in the same change: the working file and its .taken stay as they are.
        if mine:
            Path(mine[0]["file"]).unlink(missing_ok=True)
    else:
        if mine:
            shutil.move(mine[0]["file"], note)
        else:
            note.write_text(skeleton(cite, pdf_title, args.bare), encoding="utf-8")
            created = True
        shutil.copyfile(note, taken)

    package = folder.is_dir()
    best = best_pdf(cite)
    moved = bool(args.title and version and args.title != version)
    print(json.dumps({
        "code": "ok" if package else "no_package", "note": str(note), "taken": str(taken), "created": created,
        "pdf": str(pdf), "pdf_title": pdf_title, "package": str(folder) if package else None,
        "better_pdf": best if best and best != pdf_title else None,
        "previous": previous_version(cite, out, version) if moved else None,
        "old_notes": sorted(str(p) for p in (out / "notes").glob("*.note.md")),
        "open_findings": open_findings(folder) if package else {}, "paper": paper_of(cite),
    }, ensure_ascii=False))
    return 0 if package else 1


if __name__ == "__main__":
    sys.exit(main())
