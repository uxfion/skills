#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The run's report: one row per record as a Markdown table and a tally, then the sections (or the same as JSON).

Each item is read from the library as it is now (citation key, collections, tags, attachments); what this run did
comes from the records, and what happened to the files from <work>/fetch.jsonl. Row: citationKey | title | year |
item key | collection(s) | tags | attachments [| blocker]. citationKey is the library's (the record's, marked, when
the two differ; the slug in italics when there is none); the item is the one this run created or the one the lookup
confirmed; attachments are the titles of the item's files, best first (Published-IEEE; Preprint-arXiv-v3). In JSON
a row also has file: PDF (a PDF of the paper, of any version) / snapshot / null.

Sections, each only when it has something to say:
  无法获取 (not obtained)      records with no PDF (filed, attached or in the library), every try pass by pass
  替代版本 (alternate versions) files this run attached as an Accepted or Preprint version
  版本未定 (version not settled) files this run attached as Unknown: no label was settled for them
  保留预印本 (preprint kept)    records whose item stays the preprint although a published version was found, and why
  接收的文件 (accepted files)   files the agent accepted although the check refused them, and why
  待清理附件 (attachments to clean)  around the file this run attached: what it replaces by paper.superseded (an
                               older or lesser file from the same source), a snapshot standing in for the PDF that
                               is now attached, the same file twice; with the trash_item.py line to run on the
                               user's word
  建议改名 (suggested renames)  files the item had already, whose title is outside the scheme or differs from the
                               record's label: the title, and the label's when there is one; renamed only on the
                               user's word (update_item.py --key <attachment> --set title=...)
  新标签 (new tags)             manual tags on this run's items that no other item carries, by prefix
  残留 (leftovers)              Downloads files claim.py left that are still there; the files in unverified/
  停下与门禁 (stops and gates)   the pages fetch.py stopped at, with the agent's verdict

stdout: the Markdown, or with --json {code, rows, summary, sections?}; problems go to stderr as JSON lines. Exit 0 =
written; 1 = no records; 2 = Zotero cannot be read.

Example:
  uv run scripts/report.py <work>/records/*.json
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from p2zlib import cli, paper, run, web, zotero

DASH = "—"
def cell(value):
    return (DASH if value in (None, "") else str(value)).replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]


def gather(zot, records):
    """[(record, the item as the library has it now or {}, its attachments)] and the collection paths."""
    keys = {r.slug: run.item_key(r) for r in records}
    items = zot.items([k for k in keys.values() if k])
    paths = {k: c["path"] for k, c in zot.collections().items()}
    return [(r, zotero.data(items.get(keys[r.slug])), zot.attachments(keys[r.slug]) if keys[r.slug] in items else [])
            for r in records], paths


def row_of(rec, lib, atts, paths):
    item, files = rec.item, [a for a in atts if a["version"]]
    pdf = any(a["version"] in paper.PAPER_VERSIONS and a["contentType"] == "application/pdf" for a in files)
    given, cite = rec.get("citationKey") or None, lib.get("citationKey") or None
    year = re.search(r"(?<!\d)(\d{4})(?!\d)", str(lib.get("date") or item.get("date") or ""))
    return {"slug": rec.slug, "citationKey": cite or given, "cite_mismatch": bool(given and cite and given != cite),
            "record_citationKey": given, "title": lib.get("title") or item.get("title") or "",
            "year": year.group(1) if year else None, "key": lib.get("key"),
            "collections": [paths.get(c, c) for c in lib.get("collections") or []], "tags": len(lib.get("tags") or []),
            "file": "PDF" if pdf else "snapshot" if any(a["version"] == "snapshot" for a in files) else None,
            "attachments": [a["title"] for a in files], "blocker": rec.get("blocker") or None}


def to_clean(mine, atts):
    """The attachments of one item that the one this run attached makes superfluous -> [{attachment, reason}]: those it
    replaces or that replace it (paper.superseded: one per source), a snapshot standing in for the paper's PDF once a
    PDF of the paper is attached, the same file twice."""
    out = {}
    for loser, winner in paper.superseded(atts):
        if mine["key"] in (loser["key"], winner["key"]):
            out.setdefault(loser["key"], f"'{loser['title']}', replaced by '{winner['title']}' from the same source")
    if mine["version"] in paper.PAPER_VERSIONS and mine["contentType"] == "application/pdf":
        for a in atts:
            if a["version"] == "snapshot" and a["key"] != mine["key"]:
                out.setdefault(a["key"], f"snapshot '{a['title']}', standing in for the PDF now attached")
    for a in atts:
        if a["key"] != mine["key"] and a.get("md5") and a["md5"] == mine.get("md5"):
            out.setdefault(a["key"], f"the attached file a second time ('{a['title']}')")
    return [{"attachment": k, "reason": why} for k, why in out.items()]


def sections_of(gathered, rows, work, zot):
    events = work.events() if work else []
    tries = defaultdict(list)
    for e in events:
        if e.get("event") == "try":
            tries[e.get("slug")].append(e)
    out = defaultdict(list)
    for (rec, lib, atts), row in zip(gathered, rows):
        attach = rec.get("attach") if isinstance(rec.get("attach"), dict) else {}
        own = work.file_of(rec.slug) if work else None
        if row["file"] != "PDF" and not (own and own.suffix == ".pdf"):
            passes = defaultdict(list)
            for t in tries.get(rec.slug, []):
                what = f"verdict {t.get('result')}" if t.get("by") == "agent" else t.get("result", "") + (f" ({t['why']})" if t.get("why") else "")
                passes[t.get("pass", 1)].append(f"{t.get('route')} {web.host_of(t.get('url'))}".strip() + f": {what}")
            out["not_obtained"].append({"slug": rec.slug, "passes": {str(k): v for k, v in sorted(passes.items())},
                                        "snapshot": row["file"] == "snapshot" or bool(own and own.suffix == ".html")})
        mine = None if attach.get("existing") else next((a for a in atts if a["key"] == attach.get("attachment")), None)
        if mine and mine["version"] in ("accepted", "preprint", "unknown"):
            out["unknown_versions" if mine["version"] == "unknown" else "alternate_versions"].append(
                {"slug": rec.slug, "title": mine["title"], "attachment": mine["key"]})
        if rec.get("keep_preprint"):
            out["preprint_kept"].append({"slug": rec.slug, "reason": rec["keep_preprint"]})
        if mine and row["key"]:
            out["attachments_to_clean"] += [{"slug": rec.slug, "key": row["key"], **c} for c in to_clean(mine, atts)]
        if attach.get("existing") and row["key"]:
            had = next((a for a in atts if a["key"] == attach.get("attachment")), None)
            label = (rec.get("label") or {}).get("title") if isinstance(rec.get("label"), dict) else None
            label = label if paper.parse_title(label) else None
            if had and (not had["standard"] or (label and label != had["title"])):
                out["renames"].append({"slug": rec.slug, "attachment": had["key"], "title": had["title"], "suggested": label})
    out["accepted"] = [{"slug": e.get("slug"), "file": e.get("file"), "reason": e.get("reason")} for e in events if e.get("event") == "accept"]
    created = {(rec.get("saved") or {}).get("key"): row for (rec, _, _), row in zip(gathered, rows) if (rec.get("saved") or {}).get("key")}
    added = defaultdict(list)
    for (_, lib, _), row in zip(gathered, rows):
        if lib.get("key") in created:
            for t in lib.get("tags") or []:
                if t.get("type", 0) == 0:
                    added[t["tag"]].append(row["citationKey"] or row["slug"])
    if added:
        counts = {t.get("tag"): (t.get("meta") or {}).get("numItems", 0) for t in zot.pages(f"{zotero.LIB}/tags")}
        for name in sorted(added, key=str.casefold):
            if 0 < counts.get(name, 0) <= len(added[name]):
                out["new_tags"].append({"tag": name, "items": sorted(added[name])})
    if work:
        latest = {e["source"]: e for e in events if e.get("event") == "claim" and e.get("source") and not str(e["source"]).startswith("http")}
        out["leftovers"] = [{"file": f"Downloads/{e['file']}", "why": e.get("why"), "in_library": e.get("in_library")}
                            for src, e in latest.items() if e.get("result") == "left" and Path(src).exists()]
        out["leftovers"] += [{"file": f"unverified/{f.name}", "why": "refused by the check"}
                             for f in sorted(work.unverified.glob("*")) if f.is_file()]
    verdicts = {(e.get("slug"), e.get("pass"), e.get("route"), e.get("url")): e.get("result") for e in events
                if e.get("event") == "try" and e.get("by") == "agent"}
    out["stops"] = [{"slug": e.get("slug"), "pass": e.get("pass"), "why": e.get("why"), "host": web.host_of(e.get("page") or e.get("url")),
                     "verdict": verdicts.get((e.get("slug"), e.get("pass"), e.get("route"), e.get("url")))}
                    for e in events if e.get("event") == "stop"]
    return {k: v for k, v in out.items() if v}


def markdown(rows, summary, sections):
    blockers = any(r["blocker"] for r in rows)
    head = ["citationKey", "title", "year", "item key", "collection(s)", "tags", "attachments"] + (["blocker"] if blockers else [])
    body = [[(r["citationKey"] or f"*{r['slug']}*") + (f" (record: {r['record_citationKey']})" if r["cite_mismatch"] else ""),
             r["title"], r["year"], r["key"], "; ".join(r["collections"]), r["tags"], "; ".join(r["attachments"])]
            + ([r["blocker"]] if blockers else []) for r in rows]
    out = table(head, body) + ["", "**Summary**: " + " · ".join(f"{k.replace('_', ' ')} {v}" for k, v in summary.items())]
    cite = {r["slug"]: r["citationKey"] or r["slug"] for r in rows}
    titles = {"not_obtained": "无法获取 (not obtained)", "alternate_versions": "替代版本 (alternate versions)",
              "unknown_versions": "版本未定 (version not settled)", "preprint_kept": "保留预印本 (preprint kept)",
              "accepted": "接收的文件 (accepted files)", "attachments_to_clean": "待清理附件 (attachments to clean)",
              "renames": "建议改名 (suggested renames)", "new_tags": "新标签 (new tags)",
              "leftovers": "残留 (leftovers)", "stops": "停下与门禁 (stops and gates)"}
    shapes = {"not_obtained": (["citationKey", "tries, pass by pass", "snapshot"], lambda r: [
                  cite[r["slug"]], " · ".join(f"pass {k}: " + "; ".join(v) for k, v in r["passes"].items()) or "not tried",
                  "yes" if r["snapshot"] else None]),
              "alternate_versions": (["citationKey", "attachment"], lambda r: [cite[r["slug"]], f"{r['title']} ({r['attachment']})"]),
              "unknown_versions": (["citationKey", "attachment"], lambda r: [cite[r["slug"]], f"{r['title']} ({r['attachment']})"]),
              "renames": (["citationKey", "attachment", "title", "label"], lambda r: [cite[r["slug"]], r["attachment"], r["title"], r["suggested"]]),
              "preprint_kept": (["citationKey", "why"], lambda r: [cite[r["slug"]], r["reason"]]),
              "accepted": (["citationKey", "file", "why"], lambda r: [cite.get(r["slug"], r["slug"]), r["file"], r["reason"]]),
              "attachments_to_clean": (["citationKey", "item key", "attachment", "reason"], lambda r: [cite[r["slug"]], r["key"], r["attachment"], r["reason"]]),
              "new_tags": (["tag", "items"], lambda r: [r["tag"], ", ".join(r["items"])]),
              "leftovers": (["file", "why", "in library"], lambda r: [r["file"], r["why"], {True: "yes", False: "no"}.get(r.get("in_library"))]),
              "stops": (["citationKey", "pass", "why", "page", "verdict"], lambda r: [cite.get(r["slug"], r["slug"]), r["pass"], r["why"], r["host"], r["verdict"]])}
    for name in (n for n in titles if n in sections):
        head, shape = shapes[name]
        rows_ = sections[name]
        out += ["", f"### {titles[name]}: {len(rows_)}", ""] + table(head, [shape(r) for r in rows_])
        if name == "attachments_to_clean":
            out += ["", "Only on the user's word: `uv run scripts/trash_item.py --dry-run --key "
                    + " ".join(r["attachment"] for r in rows_) + "`, then without --dry-run."]
        if name == "renames":
            out += ["", "Only on the user's word, a title settled for each: `uv run scripts/update_item.py --key <attachment> "
                    "--set title=<title> --dry-run`, then without --dry-run."]
    return "\n".join(out) + "\n"


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("records", nargs="*", metavar="RECORD", help="record files: <work>/records/*.json")
    p.add_argument("--work", metavar="DIR", help="the work directory (default: the records' parent)")
    p.add_argument("--json", action="store_true", help="JSON instead of Markdown")
    cli.add_base_url(p)
    args = p.parse_args(argv)

    def go():
        records = []
        for path in args.records:
            try:
                records.append(run.read(path))
            except cli.Stop as stop:
                cli.emit(stop.line(slug=Path(path).stem), sys.stderr)
        if not records:
            raise cli.Stop("no_records", hint="Pass the record files: <work>/records/*.json.")
        work = run.Work(args.work) if args.work else run.Work.of(records[0].path)
        work = work if work.records.is_dir() else None
        zot = zotero.Zotero(args.base_url)
        gathered, paths = gather(zot, records)
        rows = [row_of(rec, lib, atts, paths) for rec, lib, atts in gathered]
        summary = {"total": len(rows), "in_library": sum(1 for r in rows if r["key"]),
                   "with_pdf": sum(1 for r in rows if r["file"] == "PDF"),
                   "with_snapshot": sum(1 for r in rows if r["file"] == "snapshot"),
                   "missing": sum(1 for r in rows if not r["key"]), "blocked": sum(1 for r in rows if r["blocker"])}
        sections = sections_of(gathered, rows, work, zot)
        if args.json:
            print(json.dumps({"code": "ok", "rows": rows, "summary": summary, **({"sections": sections} if sections else {})},
                             ensure_ascii=False, indent=2))
        else:
            sys.stdout.write(markdown(rows, summary, sections))
        return cli.OK

    return cli.run(go, sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
