#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""List library attachments whose title is not paper-fetch's label of their file, as lines for update_item --batch.

  uv run scripts/titles_from_labels.py <scratch>/paper-fetch/label -o <scratch>/titles.jsonl
  uv run scripts/update_item.py --batch <scratch>/titles.jsonl --dry-run

DIR is paper-fetch's directory: its results/*.json list each file of a paper with its md5 and label. A file's
attachment is the one in the library holding the same md5, the same bytes (the newest, none in the trash). Only a
given label counts: one `by` settle is paper-fetch's placeholder (Unknown-<Source>) while it still asks for a label,
and is never written over a title — except a snapshot's, since paper-fetch asks none for it. Each attachment whose
title is not its file's label gets one line in -o FILE: {key: the attachment, set: {title: the label}, from: its
title now, why, by, citationKey: its parent's}. update_item --batch writes them, each PDF's structured package along
with it. Nothing is written to Zotero here.

stdout: one line per file {slug, file, code, ...}, then {"summary": {total, ok, skipped, failed, batch, lines}}
(lines: how many FILE holds).
  retitle          the attachment's title is not the label: a line in FILE (`key`, `from`, `to`)
  skipped          reason titled (the attachment has the label already: `key`, `title`) | unlabelled (no label yet)
  not_in_library   no attachment holds this file (`md5`): not attached yet, or another copy of it is
  result_invalid   a result file that is not one JSON object (`path`, `detail`)
retitle and not_in_library are answers. A DIR without results/*.json is no_results: one line, nothing done.
Exit 0 = every result read; 1 = not (or no_results); 2 = cannot check (zotero_unreachable, local_api_disabled).
"""
import json
from pathlib import Path

from p2zlib import cli, run, zotero

ANSWERS = ("retitle", "not_in_library")


def read_results(folder):
    """DIR/results/*.json -> [(path, result or None, the reason it is not one)]."""
    paths = sorted((Path(folder).expanduser() / "results").glob("*.json"))
    if not paths:
        raise cli.Stop("no_results", dir=str(folder), hint="Give paper-fetch's directory, the one holding results/ "
                                                           "(an import's: <scratch>/paper-to-zotero/fetch).")
    out = []
    for path in paths:
        try:
            res = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            out.append((path, None, str(e)))
            continue
        out.append((path, res, None) if isinstance(res, dict) else (path, None, "not a JSON object"))
    return out


def label_of(f):
    """The file's label when one was given (a snapshot's is settled by its bytes), else None."""
    label = f.get("label") if isinstance(f.get("label"), dict) else {}
    given = label.get("by") != "settle" or f.get("kind") == "snapshot"
    return label if given and (label.get("title") or "").strip() else None


def line_of(f, hits, titles, batch):
    label = label_of(f)
    if label is None:
        return cli.skipped("unlabelled")
    hit = hits.get((f.get("md5") or "").lower())
    if hit is None:
        return {"code": "not_in_library", "md5": f.get("md5")}
    key, now, title = hit["attachment"], titles.get(hit["attachment"], ""), label["title"].strip()
    if now == title:
        return cli.skipped("titled", key=key, title=title)
    batch.append({"key": key, "set": {"title": title}, "from": now, "why": label.get("why"), "by": label.get("by"),
                  "citationKey": hit["citationKey"]})
    return {"code": "retitle", "key": key, "from": now, "to": title}


def files_of(res):
    return [f for f in (res or {}).get("files") or [] if isinstance(f, dict)]


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("dir", metavar="DIR", help="paper-fetch's directory, the one holding results/")
    p.add_argument("-o", "--out", required=True, metavar="FILE", help="where the update_item --batch lines go")
    cli.add_base_url(p)
    args = p.parse_args(argv)

    def go():
        results = read_results(args.dir)
        zot = zotero.Zotero(args.base_url)
        md5s = [f.get("md5") for _, res, _ in results for f in files_of(res) if label_of(f)]
        hits = zot.files_by_md5(md5s) if any(md5s) else {}
        rows = zot.items([h["attachment"] for h in hits.values()]) if hits else {}
        titles = {key: zotero.data(row).get("title") or "" for key, row in rows.items()}
        out, batch = cli.Lines(ANSWERS), []
        for path, res, problem in results:
            if res is None:
                out.lines.append({"slug": path.stem, "code": "result_invalid", "path": str(path), "detail": problem,
                                  "hint": "Not one of paper-fetch's result files: look at it, or settle it again."})
            for f in files_of(res):
                out.add({"slug": res.get("slug") or path.stem, "file": f.get("name")},
                        lambda: line_of(f, hits, titles, batch))
        target = Path(args.out).expanduser().absolute()
        target.parent.mkdir(parents=True, exist_ok=True)
        run.atomic_write(target, "".join(json.dumps(b, ensure_ascii=False) + "\n" for b in batch))
        return out.finish({"batch": str(target), "lines": len(batch)})

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
