#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Put rectangle annotations on a PDF attachment, once: a rerun finds those already there and makes no second copy.

  uv run scripts/annotate.py <PDF key> --batch <file> [--dry-run]

The --batch file holds one annotation per line, a JSON object (it names no item: they all go on the PDF given):
  comment     its text; its first line and the tag tell it apart from every other annotation
  color       "#rrggbb"
  tag         one tag
  page        the page, from 1
  page_label  the page as the reader shows it
  rect        [x1, y1, x2, y2] in the PDF's user space: points, origin bottom left, as PDF annotations store it
  top         the rect's top in points below the page's top edge, for the order of the annotation list

The PDF's annotations are read (a plain children listing leaves them out; itemType=annotation lists them). One that
carries the tag and whose comment has the same first line is the same annotation: kept as it is, wherever it sits now
(the user may have moved it); with several, the oldest. Any other is created as an image annotation (Zotero's
rectangle) and read back. Nothing here changes or deletes an annotation.

stdout: one line per entry {comment, code, key}, then {"summary"}.
  created            created and read back; --dry-run: would be created, key null
  kept               already there: key is that annotation's
  readback_mismatch  created, but it reads back without its tag or its comment's first line, so a rerun would not
                     find it: look at it in Zotero
  write_failed, write_denied: Zotero did not take it (status, detail)
Or one line for the whole run: invalid_batch (detail says which lines and why; nothing was written), not_found (no
item has that key), not_a_pdf (the item is not a PDF attachment).
Exit 0 = every entry created or kept; 1 = some not; 2 = cannot check (zotero_unreachable, local_api_disabled, no_key,
key_rejected, server_mismatch).

Example:
  uv run scripts/annotate.py 4UVJVU5R --batch <scratch>/boxes.jsonl --dry-run
"""
import json
import re
from pathlib import Path

from p2zlib import cli, paper, zotero
from p2zlib.zotero import LIB

COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
ANSWERS = ("created", "kept")


def first_line(text):
    return (text or "").strip().split("\n", 1)[0].strip()


def problem(e):
    """What makes a batch line no annotation, or None."""
    number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)  # noqa: E731
    if not isinstance(e, dict):
        return "an entry is an object"
    if not isinstance(e.get("comment"), str) or not first_line(e["comment"]):
        return "comment: text, its first line not blank"
    if not isinstance(e.get("color"), str) or not COLOR.match(e["color"]):
        return 'color: "#rrggbb"'
    if not isinstance(e.get("tag"), str) or not e["tag"].strip():
        return "tag: a tag's name"
    if not isinstance(e.get("page"), int) or isinstance(e["page"], bool) or e["page"] < 1:
        return "page: the page number, from 1"
    if not isinstance(e.get("page_label"), str):
        return "page_label: text"
    r = e.get("rect")
    if not (isinstance(r, list) and len(r) == 4 and all(map(number, r)) and r[0] < r[2] and r[1] < r[3]):
        return "rect: [x1, y1, x2, y2] with x1 < x2 and y1 < y2"
    if not number(e.get("top")) or e["top"] < 0:
        return "top: points below the page's top edge, 0 or more"
    return None


def entries_of(name):
    """The batch file's annotations -> (entries, problems)."""
    try:
        text = Path(name).expanduser().read_text(encoding="utf-8")
    except OSError as e:
        return [], [f"{name}: {e.strerror or e}"]
    entries, problems = [], []
    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            e = json.loads(raw)
        except ValueError as err:
            problems.append(f"line {n}: not JSON ({err})")
            continue
        bad = problem(e)
        problems += [f"line {n}: {bad}"] if bad else []
        entries += [] if bad else [e]
    if not entries and not problems:
        problems.append("no entries")
    return entries, problems


def identity(tag, comment):
    return tag, first_line(comment)


def annotations(zot, key):
    """{(tag, first line of the comment): the annotation's key} for the PDF's annotations, the oldest first."""
    rows = [a for a in zot.pages(f"{LIB}/items/{key}/children", {"itemType": "annotation"})
            if zotero.data(a).get("parentItem") == key and not zotero.in_trash(a)]
    found = {}
    for a in sorted(rows, key=lambda a: (zotero.data(a).get("dateAdded") or "", a["key"])):
        d = zotero.data(a)
        for t in d.get("tags") or []:
            found.setdefault(identity(t.get("tag"), d.get("annotationComment")), a["key"])
    return found


def zotero_object(pdf_key, e):
    """The entry as Zotero stores an image annotation: the position a JSON string, pageIndex from 0, and the sort
    index Zotero's reader writes, page|text offset (0: no text under a rectangle)|top."""
    index = e["page"] - 1
    return {"itemType": "annotation", "parentItem": pdf_key, "annotationType": "image",
            "annotationComment": e["comment"], "annotationColor": e["color"], "annotationPageLabel": e["page_label"],
            "annotationSortIndex": f"{min(index, 99999):05d}|000000|{min(int(e['top']), 99999):05d}",
            "annotationPosition": json.dumps({"pageIndex": index, "rects": [e["rect"]]}, separators=(",", ":")),
            "tags": [{"tag": e["tag"]}]}


def annotate(args):
    entries, problems = entries_of(args.batch)
    if problems:
        raise cli.Stop("invalid_batch", hint="Fix the batch file, then rerun; nothing was written.", detail=problems)
    zot = zotero.Zotero(args.base_url)
    if not args.dry_run:
        zot.write_headers()
    item = zot.item(args.key)
    if item is None:
        raise cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND, key=args.key)
    if not paper.is_pdf(zotero.data(item)):
        raise cli.Stop("not_a_pdf", hint="Name a PDF attachment by its key: read_library pdf lists them.", key=args.key)
    found = annotations(zot, args.key)
    new = {}   # identity -> the first entry that creates it; a later entry with the same identity shares its result
    for e in entries:
        ident = identity(e["tag"], e["comment"])
        if ident not in found:
            new.setdefault(ident, e)
    done = {ident: {"code": "kept", "key": key} for ident, key in found.items()}
    if args.dry_run:
        done.update({ident: {"code": "created", "key": None, "dry_run": True} for ident in new})
    elif new:
        results = zot.post([zotero_object(args.key, e) for e in new.values()])
        back = annotations(zot, args.key)
        for ident, result in zip(new, results):
            if "failed" in result:
                done[ident] = dict(result["failed"])
            elif back.get(ident) == result["ok"]["key"]:
                done[ident] = {"code": "created", "key": result["ok"]["key"]}
            else:
                done[ident] = {"code": "readback_mismatch", "key": result["ok"]["key"],
                               "hint": "Zotero took the annotation, but it does not read back with its tag and comment; "
                                       "look at it in Zotero."}
    lines = [cli.tidy({"comment": e["comment"], **done[identity(e["tag"], e["comment"])]}, ANSWERS) for e in entries]
    return cli.finish(lines, answers=ANSWERS)


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("key", metavar="PDF_KEY", help="the PDF attachment's key")
    p.add_argument("--batch", required=True, metavar="FILE", help="the annotations, one JSON object per line")
    p.add_argument("--dry-run", action="store_true", help="read what is there; create nothing")
    cli.add_base_url(p)
    args = p.parse_args(argv)
    if not cli.KEY_RE.match(args.key):
        p.error("PDF_KEY is an attachment's 8-character key")
    return cli.run(lambda: annotate(args))


if __name__ == "__main__":
    raise SystemExit(main())
