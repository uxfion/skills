# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""A stand-in for paper-to-zotero's p2z.py in paper-read's tests: the commands prepare_note.py, put_note.py and
index_heading.py run, answered from the library in the JSON file FAKE_P2Z names, as the real ones answer (their
docstrings) at paper-to-zotero's commit 2788f2b (annotate: as added with paper-read's put_note.py): when their output
changes, change this to match. Each call's arguments go to FAKE_P2Z.log, one JSON line each. Called as `objects`, it
stands in for the paddleocr skill's `doc.py objects` (PAPER_READ_DOC).

The library: {"items": {cite: item}, "notes": {cite: [{key, title, text}]}, "pdfs": {cite: [PDF title, best first]},
"packages": {cite: [PDF titles that have one]}, "findings": [finding], "objects": [doc.py objects' lines],
"annotations": {comment: key}, "put_code": the code note put answers (ok by default)}. note put keeps each file it
is given, as given, in FAKE_P2Z.put.<n>.
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
    (out / f"{cite}.{title}.zotero.json").write_text(json.dumps({"key": "ITEMKEY1", "cite": cite, "attachment": "PDFKEY01",
                                                               "title": title}), encoding="utf-8")
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


def note_put(lib, args, path):
    note = Path(args[2])
    text = note.read_text(encoding="utf-8")
    n = len(list(path.parent.glob(f"{path.name}.put.*")))
    Path(f"{path}.put.{n}").write_text(text, encoding="utf-8")
    code = lib.get("put_code", "ok")
    if code != "ok":
        print(json.dumps({"file": str(note), "code": code, "hint": "as the real one says"}))
        return 1
    if "-i" in args and text.startswith("---\n") and "\nkey: NOTEKEY1\n" not in text:  # the key and version written in
        note.write_text(text.replace("---\n", "---\nkey: NOTEKEY1\nversion: 8\n", 1), encoding="utf-8")
    print(json.dumps({"file": str(note), "code": "ok", "key": "NOTEKEY1", "version": 8, "action": "updated"}))
    return 0


def annotate(lib, args, path):
    known = lib.setdefault("annotations", {})
    for raw in Path(args[args.index("--batch") + 1]).read_text(encoding="utf-8").splitlines():
        e = json.loads(raw)
        code = "kept" if e["comment"] in known else "created"
        known.setdefault(e["comment"], f"ANNOT{len(known):03d}")
        print(json.dumps({"comment": e["comment"], "code": code, "key": known[e["comment"]]}, ensure_ascii=False))
    path.write_text(json.dumps(lib, ensure_ascii=False), encoding="utf-8")
    return 0


def objects(lib):
    for o in lib.get("objects", []):
        print(json.dumps(o, ensure_ascii=False))
    return 0


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
    if command == ("note", "put"):
        return note_put(lib, args, path)
    if args[0] == "annotate":
        return annotate(lib, args, path)
    if args[0] == "objects":
        return objects(lib)
    print(f"fake p2z: no such command {args}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
