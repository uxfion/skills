# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""A stand-in for paper-to-zotero's p2z.py in paper-read's tests: the commands pr.py take, put and heading run,
answered from the library in the JSON file FAKE_P2Z names, as the real ones answer (their -h) since paper-to-zotero's
Unix conventions (2026-11-05): when their output changes, change this to match. Each call's arguments go to
FAKE_P2Z.log, one JSON line each. Called as `objects`, it stands in for the paddleocr skill's `ocr.py objects`
(PAPER_READ_OCR).

The library: {"items": {cite: item, with its own 8-character "key"}, "notes": {cite: [{key, title, text}]}, "pdfs":
{cite: [PDF title, best first]}, "packages": {cite: [PDF titles that have one]}, "findings": [finding], "objects":
[ocr.py objects' lines], "annotations": {comment: key}, "put_code": the code note put answers (ok by default)}. An
item is named by its key or its citation key. note put keeps each file it is given, as given, in FAKE_P2Z.put.<n>.
"""
import json
import os
import sys
from pathlib import Path


def arg(args, flag):
    return args[args.index(flag) + 1] if flag in args else None


def cite_of(lib, name):
    """The citation key of the item a key or citation key names, or None."""
    if name in lib["items"]:
        return name
    return next((cite for cite, item in lib["items"].items() if item["key"] == name), None)


def note_take(lib, args):
    cite, out = cite_of(lib, args[2]), Path(arg(args, "-o"))
    notes = lib["notes"].get(cite, [])
    if not notes:
        print(json.dumps({"code": "no_notes", "hint": "No note matches."}))
        return 1
    out.mkdir(parents=True, exist_ok=True)
    for n in notes:
        f = out / f"{cite}.{n['key']}.note.md"
        f.write_text(f"---\nkey: {n['key']}\nparent: {cite}\n---\n# {n['title']}\n\n{n['text']}\n", encoding="utf-8")
        print(json.dumps({"key": n["key"], "cite": cite, "title": n["title"], "code": "ok", "file": str(f), "version": 7},
                         ensure_ascii=False))
    return 0


def package_take(lib, args):
    cite, out, title = cite_of(lib, args[2]), Path(arg(args, "-o")), arg(args, "--title")
    key = lib["items"][cite]["key"]
    pdfs = lib["pdfs"][cite]
    head = {"cite": cite, "key": key}
    if title and title not in pdfs:
        print(json.dumps({**head, "code": "no_such_title", "titles": pdfs,
                          "hint": "No PDF of the item has that title; p2z.py pdf lists them."}, ensure_ascii=False))
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
    (out / f"{cite}.{title}.zotero.json").write_text(json.dumps({"key": key, "cite": cite, "attachment": "PDFKEY01",
                                                               "title": title}), encoding="utf-8")
    print(json.dumps({**head, "title": title, "code": "ok", "pdf": "/zotero/storage/x.pdf", "input": str(link),
                      "folder": str(folder), "package": "PKGKEY01" if package else None}, ensure_ascii=False))
    return 0


def read_pdfs(lib, args):
    cite = cite_of(lib, args[1])
    for n, title in enumerate(lib["pdfs"].get(cite, [])):
        print(json.dumps({"key": lib["items"][cite]["key"], "citationKey": cite, "attachment": f"PDF{n:05d}",
                          "attachment_title": title}, ensure_ascii=False))
    return 0


def read_items(lib, args):
    failed = 0
    for name in args[1:]:
        cite = cite_of(lib, name)
        if cite:
            print(json.dumps({"itemType": "journalArticle", "citationKey": cite, **lib["items"][cite]}, ensure_ascii=False))
        else:
            print(json.dumps({"item": name, "code": "not_found", "hint": "No item has this key or citation key."}))
            failed = 1
    if failed:
        print(json.dumps({"summary": {"total": len(args) - 1, "failed": 1}}), file=sys.stderr)
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
    for raw in Path(args[2]).read_text(encoding="utf-8").splitlines():
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
    if command == ("package", "take"):
        return package_take(lib, args)
    if args[0] == "items":
        return read_items(lib, args)
    if args[0] == "pdf":
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
