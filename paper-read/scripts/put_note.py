#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Put a paper note into Zotero with its figures and tables clickable: step 4 of every change to a note.

In one go:
  1. the links an earlier put left are taken off;
  2. each figure and table the note names (references/note-format.md, *Clickable figures and tables*) becomes a link
     to a rectangle annotation on it in the PDF: the paddleocr skill's `ocr.py objects` places it from the structured
     package, `p2z.py annotate` finds or creates it (blue, tagged paper-read, its comment "paper-read · Fig. 9");
  3. paper-to-zotero's `note put <note> -i` puts the note;
  4. the links are taken off the file again, whatever the put answered: the file holds the note's text alone, and the
     key and version -i wrote.
The PDF's key (`attachment` in <name>.zotero.json), the PDF (<name>.pdf) and the package (<name>/) are read beside
the note <name>.note.md, where pr.py take left them.

A figure or table that cannot be linked stays plain text, the rest linked and the note put. It is listed in
`unmatched` with why and a hint: not_in_package (no figure or table in the package has this number, or two captions
give it), rotated_page (no rectangle is placed on a rotated page), no_package, no_paddleocr, objects_failed and
annotate_failed (detail: what failed), no_pdf (no <name>.zotero.json beside the note: nothing is linked).

stdout: one JSON object {code, put, links: {figures, tables}, unmatched: [{token, lines, why, hint, detail?}],
annotations: {created, kept}, hint?}.
  code  note put's own code, its line in put: ok, skipped (Zotero already holds this note), version_conflict,
        same_title, ...; hint is note put's
  file_not_found, file_unreadable, write_failed    {file, code, hint}: the note file cannot be read or rewritten;
        nothing was put
Exit 0 = ok or skipped; 1 = anything else; 2 = cannot go on: stderr's last line is {code, hint}, a usage error's or,
when paper-to-zotero could not go on (Zotero not running), its own with step: annotate (nothing put, the file as it
was) or note put (the file as it was). An annotation already made is found again by the next put.

Examples:
  pr.py put <scratch>/xiaoTCACE2026.Published-IEEE.note.md
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from prlib import cli, sources

COLOR, TAG = "#2ea8e5", "paper-read"
DETAIL = 600
HINTS = {   # why a figure or table stays unlinked -> what to do once it is looked up in the PDF
    "not_in_package": "A wrong number in the note: correct it by note-format.md, *Changing a note* (in a read-through, "
                      "send it back to the reader), and check again. A right one stays plain text.",
    "rotated_page": "It sits on a rotated page, where no box is placed: it stays plain text.",
    "no_package": "No package beside the note: it stays plain text.",
    "no_paddleocr": "The paddleocr skill is not installed beside this one: it stays plain text; tell the user.",
    "objects_failed": "Fix what detail says and put again; what you cannot fix goes into your report.",
    "annotate_failed": "Fix what detail says and put again; what you cannot fix goes into your report.",
    "no_pdf": "No <name>.zotero.json beside the note (a topic note has none): it stays plain text.",
}


def write(path, text):
    """The file replaced whole, never left half written."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def pdf_key(side):
    try:
        key = json.loads(side.read_text(encoding="utf-8")).get("attachment")
    except (OSError, ValueError, AttributeError):
        return None
    return key if isinstance(key, str) and re.fullmatch(r"[A-Z0-9]{8}", key) else None


def locate(keys, package, pdf, key):
    """The figures and tables named -> ({key: annotation key}, {key: (why, detail)}, {created, kept})."""
    counts = {"created": 0, "kept": 0}
    if not keys:
        return {}, {}, counts
    if not package.is_dir():
        return {}, {k: ("no_package", None) for k in keys}, counts
    if not Path(cli.OCR).is_file():
        return {}, {k: ("no_paddleocr", None) for k in keys}, counts
    objects, code, err = cli.sibling(cli.OCR, "objects", package, "--source", pdf)
    if code:
        return {}, {k: ("objects_failed", err.strip()[-DETAIL:]) for k in keys}, counts
    placed = {o["key"]: o for o in objects if o.get("key")}
    entries, why = {}, {}
    for k in keys:
        o = placed.get(k)
        if o is None:
            why[k] = ("not_in_package", None)
        elif o.get("rect") is None:
            why[k] = ("rotated_page", None)
        else:
            entries[k] = {"comment": f"{TAG} · {sources.label(k)}", "color": COLOR, "tag": TAG, "page": o["page"],
                          "page_label": o["page_label"], "rect": o["rect"], "top": o["top"]}
    if not entries:
        return {}, why, counts
    fd, batch = tempfile.mkstemp(suffix=".jsonl", prefix="paper-read-boxes.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries.values()))
        lines, _, err = cli.sibling(cli.P2Z, "annotate", key, batch, step="annotate")
    finally:
        os.unlink(batch)
    answers = {l["comment"]: l for l in lines if "comment" in l}
    whole = next((l for l in lines if "comment" not in l and "summary" not in l), None)  # a line for the whole run
    found = {}
    for k, e in entries.items():
        line = answers.get(e["comment"])
        if line and line.get("code") in counts:
            found[k] = line["key"]
            counts[line["code"]] += 1
        else:
            detail = line or whole
            why[k] = ("annotate_failed", json.dumps(detail, ensure_ascii=False)[-DETAIL:] if detail else err.strip()[-DETAIL:])
    return found, why, counts


def link(note, clean):
    """-> (the note with links, links counted, unmatched, annotations counted)."""
    stem = note.name.removesuffix(".note.md")
    tokens, links, unmatched = sources.tokens(clean), {}, {}
    counts = {"figures": 0, "tables": 0}

    def miss(t, why, detail=None):
        entry = unmatched.setdefault((t[3], why), {"token": t[3], "lines": [], "why": why, "hint": HINTS[why],
                                                   **({"detail": detail} if detail else {})})
        entry["lines"] += [] if t[0] in entry["lines"] else [t[0]]

    key = pdf_key(note.with_name(f"{stem}.zotero.json"))
    if key is None:
        for t in tokens:
            miss(t, "no_pdf")
        return clean, counts, list(unmatched.values()), {"created": 0, "kept": 0}
    named = list(dict.fromkeys(sources.key_of(t[4]) for t in tokens))
    boxes, why, made = locate(named, note.with_name(stem), note.with_name(f"{stem}.pdf"), key)
    for t in tokens:
        n, start, end, text, m = t
        if (k := sources.key_of(m)) in boxes:
            links[(n, start, end)] = sources.link(key, text, boxes[k])
            counts["figures" if m.group("fig") else "tables"] += 1
        else:
            miss(t, *why[k])
    lines = clean.split("\n")
    for (n, start, end), new in sorted(links.items(), reverse=True):
        lines[n - 1] = lines[n - 1][:start] + new + lines[n - 1][end:]
    return "\n".join(lines), counts, list(unmatched.values()), made


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("note", metavar="NOTE", help="the note file, <name>.note.md as pr.py take wrote it")
    args = cli.parse(p, argv)
    note = Path(args.note)

    def run():
        text = cli.document(note, "No such note file: name the <name>.note.md pr.py take wrote.")
        linked, counts, unmatched, made = link(note, sources.strip(text))
        try:
            write(note, linked)
        except OSError as e:
            raise cli.Stop("write_failed", detail=str(e), hint="The note file could not be rewritten; nothing was put.")
        try:
            lines, _, _ = cli.sibling(cli.P2Z, "note", "put", note, "-i", step="note put")
        finally:   # the file -i rewrote, links off: it keeps the new key and version
            try:
                write(note, sources.strip(note.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError) as e:
                print(f"the links could not be taken off {note}: {e}", file=sys.stderr)
        put = next(l for l in lines if "code" in l)
        code = put["code"]
        hint = {"hint": put["hint"]} if code not in ("ok", "skipped") and put.get("hint") else {}
        cli.emit({"code": code, "put": put, "links": counts, "unmatched": unmatched, "annotations": made, **hint})
        return cli.OK if code in ("ok", "skipped") else cli.ACT

    return cli.run(run, file=args.note)


if __name__ == "__main__":
    sys.exit(main())
