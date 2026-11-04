#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Put a paper note into Zotero with its figures and tables clickable: step 4 of every change to a note.

  uv run scripts/put_note.py <note>

In one go: the links an earlier put left are taken off; each figure and table the note names (sources.py;
references/note-format.md, *Clickable figures and tables*) becomes a link to a rectangle annotation on it in the PDF,
which `p2z.py annotate` finds or creates (blue, tagged paper-read, its comment "paper-read · Fig. 9"), placed by the
paddleocr skill's `doc.py objects` from the structured package; paper-to-zotero's `note put <note> -i` puts the note;
then the links are taken off the file again, whatever the put answered, so the file holds the note's text alone (and
the key and version -i wrote). The PDF's key (`attachment` in <stem>.zotero.json), the PDF (<stem>.pdf) and the
package (<stem>/) are read beside the note <stem>.note.md, where prepare_note.py left them.

A figure or table that cannot be linked stays plain text, the rest linked and the note put. It is listed in
`unmatched`, with why:
  not_in_package     no figure or table in the package has this number, or two captions give it
  rotated_page       it sits on a rotated page, where no rectangle is placed
  no_package         no structured package beside the note
  no_paddleocr       the paddleocr skill is not installed beside this one
  objects_failed     doc.py objects failed: detail holds its stderr
  annotate_failed    p2z.py annotate neither found nor created the annotation: detail holds what it printed
  no_pdf             no <stem>.zotero.json with the PDF's key beside the note: nothing is linked

stdout: one JSON object {code, put, links: {figures, tables}, unmatched: [{token, lines, why, detail?}],
annotations: {created, kept}}.
  code  note put's own code (ok, skipped, version_conflict, same_title, ...; its line is in put), or failed: the
        note file could not be read or written, or note put printed nothing (detail); then nothing was put
Exit 0 = ok or skipped; 1 = anything else.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sources  # noqa: E402

SKILL = Path(__file__).resolve().parent.parent
P2Z = os.environ.get("PAPER_READ_P2Z") or str(SKILL.parent / "paper-to-zotero" / "scripts" / "p2z.py")
DOC = os.environ.get("PAPER_READ_DOC") or str(SKILL.parent / "paddleocr" / "scripts" / "doc.py")
COLOR, TAG = "#2ea8e5", "paper-read"
DETAIL = 600


def run(script, *args):
    """A sibling skill's script run through uv -> (its JSON lines, exit code, stderr)."""
    done = subprocess.run(["uv", "run", "--quiet", script, *args], capture_output=True, text=True)
    lines = []
    for line in done.stdout.splitlines():
        try:
            lines.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return [l for l in lines if isinstance(l, dict)], done.returncode, done.stderr


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
    if not Path(DOC).is_file():
        return {}, {k: ("no_paddleocr", None) for k in keys}, counts
    objects, code, err = run(DOC, "objects", str(package), "--source", str(pdf))
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
        lines, _, err = run(P2Z, "annotate", key, "--batch", batch)
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
        entry = unmatched.setdefault((t[3], why), {"token": t[3], "lines": [], "why": why, **({"detail": detail} if detail else {})})
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
    first, _, rest = __doc__.strip().partition("\n")
    ap = argparse.ArgumentParser(description=first, epilog=rest.strip(), formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("note", metavar="NOTE", help="the note file, <stem>.note.md as prepare_note.py wrote it")
    note = Path(ap.parse_args(argv).note)

    def out(result):
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["code"] in ("ok", "skipped") else 1

    try:
        clean = sources.strip(note.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        return out({"code": "failed", "detail": f"the note file: {e}"})
    linked, counts, unmatched, made = link(note, clean)
    try:
        write(note, linked)
    except OSError as e:
        return out({"code": "failed", "detail": f"the note file: {e}"})
    lines, _, err = run(P2Z, "note", "put", str(note), "-i")
    put = next((l for l in lines if "summary" not in l), None)
    try:  # the file -i rewrote, links off: it keeps the new key and version
        write(note, sources.strip(note.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError) as e:
        print(f"the links could not be taken off {note}: {e}", file=sys.stderr)
    result = {"code": put.get("code", "failed") if put else "failed", "put": put}
    if put is None:
        result["detail"] = err.strip()[-DETAIL:] or "note put printed nothing"
    return out({**result, "links": counts, "unmatched": unmatched, "annotations": made})


if __name__ == "__main__":
    sys.exit(main())
