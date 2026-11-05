#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Change lines for library attachments whose title is not paper-fetch's label of their file: a change list for p2z.py update.

DIR is paper-fetch's directory: its results/*.json list each file of a paper with its md5 and label (`files`), and
the paper's files it filed under no label (`set_aside`). A file's attachment is the one in the library holding the same
md5, the same bytes (the newest, none in the trash). Only a given label counts: one `by` settle is paper-fetch's
placeholder (Unknown-<Source>) while it still asks for a label, and is never written over a title — except a
snapshot's, since paper-fetch asks none for it. A file not yet attached, or one whose attachment has its label,
needs no line. p2z.py update writes the lines, each PDF's structured package along with it. Nothing is written to
Zotero here.

stdout (or -o FILE): one change line per attachment to retitle, {key: the attachment, set: {title: the label}, from:
its title now, why, by, citationKey: its parent's}. Exit 0 = every result read and no file set aside; 1 = not, each
a JSON line on stderr, then {"summary": {total, failed}} last:
  not_filed        a file of the result's `set_aside` (`md5`): paper-fetch gave it no label, and `why` says why —
                   refused (not the paper; `check_code`: the check's code), held (still waiting on an agent) or
                   withdrawn (set aside for a confirmed copy). `key` and `citationKey` name the library attachment
                   holding it, when one does: for the user to look at
  result_invalid   a result file that is not one JSON object (`path`, `detail`)
  no_results       DIR has no results/*.json: nothing done
Exit 2 = cannot check (zotero_unreachable, local_api_disabled), then stderr's last line is {code, hint}.

Examples:
  p2z.py retitle <scratch>/paper-fetch/label | p2z.py update -n -
  p2z.py retitle <scratch>/paper-fetch/label -o <scratch>/titles.jsonl
"""
import json
import sys
from pathlib import Path

from p2zlib import cli, run, zotero

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


def change_of(f, hits, titles):
    """The file's change line, or None when its attachment needs none (no label yet, not attached, titled)."""
    label, hit = label_of(f), hits.get((f.get("md5") or "").lower())
    if label is None or hit is None:
        return None
    key, now, title = hit["attachment"], titles.get(hit["attachment"], ""), label["title"].strip()
    if now == title:
        return None
    return {"key": key, "set": {"title": title}, "from": now, "why": label.get("why"), "by": label.get("by"),
            "citationKey": hit["citationKey"]}


def files_of(res):
    return [f for f in (res or {}).get("files") or [] if isinstance(f, dict)]


def set_aside(res):
    """The paper's files paper-fetch gave no label: the result's set_aside [{name, md5, why, code?}]."""
    return [f for f in (res or {}).get("set_aside") or [] if isinstance(f, dict)]


def not_filed(f, hits):
    hit = hits.get((f.get("md5") or "").lower()) or {}
    return {"code": "not_filed", "md5": f.get("md5"), "why": f.get("why"), **({"check_code": f["code"]} if f.get("code") else {}),
            **({"key": hit["attachment"], "citationKey": hit["citationKey"]} if hit else {}),
            "hint": "paper-fetch gave this file no label (why). When the library holds it (key), name it to the user, "
                    "who decides what becomes of it."}


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("dir", metavar="DIR", help="paper-fetch's directory, the one holding results/")
    p.add_argument("-o", "--output", metavar="FILE", help="write the change lines here instead of stdout")
    cli.add_base_url(p)
    args = cli.parse(p, argv)

    def go():
        results = read_results(args.dir)
        zot = zotero.Zotero(args.base_url)
        md5s = [f.get("md5") for _, res, _ in results for f in files_of(res) if label_of(f)]
        md5s += [f.get("md5") for _, res, _ in results for f in set_aside(res)]
        hits = zot.files_by_md5(md5s) if any(md5s) else {}
        rows = zot.items([h["attachment"] for h in hits.values()]) if hits else {}
        titles = {key: zotero.data(row).get("title") or "" for key, row in rows.items()}
        changes, problems = [], []
        for path, res, problem in results:
            slug = (res or {}).get("slug") or path.stem
            if res is None:
                problems.append({"slug": slug, "code": "result_invalid", "path": str(path), "detail": problem,
                                 "hint": "Not one of paper-fetch's result files: look at it, or settle it again."})
            changes += [c for c in (change_of(f, hits, titles) for f in files_of(res)) if c]
            problems += [{"slug": slug, "file": f.get("name"), **not_filed(f, hits)} for f in set_aside(res)]
        text = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in changes)
        if args.output:
            target = Path(args.output).expanduser().absolute()
            target.parent.mkdir(parents=True, exist_ok=True)
            run.atomic_write(target, text)
        else:
            cli.write(text)
        return cli.summarize(len(results), len(problems), problems=problems)

    return cli.run(go, sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
