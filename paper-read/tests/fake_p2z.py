# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""A stand-in for paper-to-zotero's p2z.py in paper-read's tests: the commands prepare_note.py and index_heading.py
run, answered from the library in the JSON file FAKE_P2Z names, as the real ones answer (their docstrings). Each call's
arguments go to FAKE_P2Z.log, one JSON line each.

The library: {"items": {cite: item}, "notes": {cite: [{key, title, text}]}, "pdfs": {cite: [PDF title, best first]},
"packages": {cite: [PDF titles that have one]}, "findings": [finding]}.
"""
import json
import os
import sys
from pathlib import Path


def arg(args, flag):
    return args[args.index(flag) + 1] if flag in args else None


def note_take(lib, args):
    cite, out = arg(args, "--cite"), Path(arg(args, "-o"))
    notes = lib["notes"].get(cite, [])
    if not notes:
        print(json.dumps({"cite": cite, "code": "no_notes"}))
        return 1
    out.mkdir(parents=True, exist_ok=True)
    for n in notes:
        f = out / f"{cite}.{n['key']}.note.md"
        f.write_text(f"---\nkey: {n['key']}\nparent: {cite}\n---\n# {n['title']}\n\n{n['text']}\n", encoding="utf-8")
        print(json.dumps({"key": n["key"], "cite": cite, "title": n["title"], "code": "ok", "file": str(f), "version": 7},
                         ensure_ascii=False))
    return 0


def structured_take(lib, args):
    cite, out, title = arg(args, "--cite"), Path(arg(args, "-o")), arg(args, "--title")
    pdfs = lib["pdfs"][cite]
    head = {"cite": cite, "key": "ITEMKEY1"}
    if title and title not in pdfs:
        print(json.dumps({**head, "code": "no_such_title", "titles": pdfs}, ensure_ascii=False))
        return 1
    title = title or pdfs[0]
    folder, link = out / f"{cite}.{title}", out / f"{cite}.{title}.pdf"
    package = title in lib["packages"].get(cite, [])
    if package and folder.exists():
        print(json.dumps({**head, "title": title, "code": "skipped", "reason": "already_taken", "folder": str(folder)},
                         ensure_ascii=False))
        return 0
    out.mkdir(parents=True, exist_ok=True)
    link.write_bytes(b"%PDF-1.4\n")
    if package:
        folder.mkdir()
        (folder / f"{folder.name}.md").write_text("# package\n", encoding="utf-8")
        (folder / f"{folder.name}.json").write_text(json.dumps({"findings": lib.get("findings", [])}), encoding="utf-8")
    print(json.dumps({**head, "title": title, "code": "ok", "pdf": "/zotero/storage/x.pdf", "input": str(link),
                      "folder": str(folder), "package": "PKGKEY01" if package else None}, ensure_ascii=False))
    return 0


def read_pdfs(lib, args):
    cite = arg(args, "--cite")
    for n, title in enumerate(lib["pdfs"].get(cite, [])):
        print(json.dumps({"key": "ITEMKEY1", "citationKey": cite, "attachment": f"PDF{n:05d}", "attachment_title": title},
                         ensure_ascii=False))
    return 0


def read_items(lib, args):
    cites = args[args.index("--cite") + 1:]
    failed = 0
    for cite in cites:
        if cite in lib["items"]:
            print(json.dumps({"key": "ITEMKEY1", "itemType": "journalArticle", "citationKey": cite, **lib["items"][cite]},
                             ensure_ascii=False))
        else:
            print(json.dumps({"cite": cite, "code": "cite_not_found"}))
            failed = 1
    return failed


def main(args):
    path = Path(os.environ["FAKE_P2Z"])
    with open(f"{path}.log", "a", encoding="utf-8") as log:
        log.write(json.dumps(args, ensure_ascii=False) + "\n")
    lib = json.loads(path.read_text(encoding="utf-8"))
    command = tuple(args[:2])
    if command == ("note", "take"):
        return note_take(lib, args)
    if command == ("structured", "take"):
        return structured_take(lib, args)
    if command == ("read_library", "items"):
        return read_items(lib, args)
    if command == ("read_library", "pdf"):
        return read_pdfs(lib, args)
    print(f"fake p2z: no such command {args}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
