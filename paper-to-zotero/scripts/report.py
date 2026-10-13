# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Summarize paper-to-zotero records as a Markdown table plus a one-line tally (or the same as JSON).

Reads records (paths, globs, or stdin: JSONL / array / object) and prints one
row per record: citationKey | title | year | item key | collection(s) | tags |
file [| blocker]. The library's state is the record's `saved` block once
find_in_library.py --readback has refreshed it (an item this run created),
else `found` (an item that was there before), else the record itself.
citationKey is the record's `citationKey`, else the library's, else the slug in
italics; the item key is `saved.key`, else `found.key`; tags is a count; file is
PDF / snapshot / "-" from the library's attachments and `attach`. The blocker
column appears when any record has one. Collection keys become paths
("自然图像/Diffusion") when the local API answers.

Then the sections, each only when it has something to say. <work> is --work,
else the parent of the record files' directory when it holds .started or fetch.jsonl (no work directory: no
无法获取, 残留 or 停下 section).
  无法获取 (not obtained): records with no file of their own (records/<slug>.pdf,
      .accepted.pdf, .preprint.pdf, .supplement.pdf, .html), no attach.md5_ok and
      no PDF in the library's state - also the ones never tried - with every try
      from <work>/fetch.jsonl, pass by pass (route, host, result; the agent's
      verdicts included).
  替代版本 (alternate versions): attachments this run made from a file that is
      not the published version (attach.version).
  待清理附件 (attachments to clean): where this run attached the published PDF,
      the item's other attachments - a snapshot, a preprint or accepted
      manuscript (by title), the same file twice - with a trash_item.py
      --dry-run line, for the user's word.
  新标签 (new tags): curated (type 0) tags on items this run created that no
      other item carries (the library's count for the name is not above the
      number of this run's items with it), grouped by prefix. Needs the local API.
  残留 (leftovers): Downloads files claim.py left (unmatched, ambiguous, or
      listed by --sweep) that are still there, and the files in <work>/unverified/
      with their source.
  停下与门禁 (stops and gates): the pages fetch.py stopped at, with the agent's
      verdict for each.

stdout is the Markdown (or, with --json, one JSON object {code, rows, summary,
sections?}); JSON diagnostics and errors go to stderr. Exit 0 = report written;
1 = no records / unreadable record.

Examples:
  uv run scripts/report.py work/records/*.json
  cat work/records/*.json | uv run scripts/report.py --json
"""
import argparse
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
LIB = "/api/users/0"
PAGE = 100
KEY_RE = re.compile(r"^[A-Z0-9]{8}$")
YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")
DASH = "—"
STEM_FILES = (".pdf", ".accepted.pdf", ".preprint.pdf", ".supplement.pdf", ".html")
VERSION_WORDS = (("supplement", re.compile(r"supplement|补充", re.I)),
                 ("preprint", re.compile(r"preprint|arxiv|biorxiv|medrxiv|预印", re.I)),
                 ("accepted", re.compile(r"accepted|author manuscript|postprint|接受稿", re.I)),
                 ("snapshot", re.compile(r"snapshot|快照", re.I)))


class Stop(Exception):
    """Carry a result code out of any depth; main() turns it into JSON + exit."""

    def __init__(self, code, exit_code=1, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit_code, self.hint, self.extra = code, exit_code, hint, extra


def log(msg):
    print(msg, file=sys.stderr)


def emit(code, exit_code=0, hint=None, **extra):
    """One JSON line on stderr (stdout carries the report), then exit."""
    out = {"code": code, **extra}
    if hint and exit_code != 0:
        out["hint"] = hint
    print(json.dumps(out, ensure_ascii=False), file=sys.stderr)
    sys.exit(exit_code)


class Api:
    """Minimal read client for the local API; bypasses any proxy from the environment."""

    def __init__(self, base_url, timeout=5):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get_json(self, path):
        req = urllib.request.Request(self.base + path, headers={"Accept": "application/json"})
        with self.opener.open(req, timeout=self.timeout) as resp:
            if resp.status != 200:
                raise OSError(f"status {resp.status}")
            return json.loads(resp.read())


def collection_paths(api):
    """{key: "root/…/name"} for the live collections; {} when the local API cannot be read (the report still prints keys)."""
    cols, start = {}, 0
    try:
        while True:
            page = api.get_json(f"{LIB}/collections?limit={PAGE}&start={start}")
            for row in page:
                data = row.get("data") or {}
                if not data.get("deleted"):
                    cols[row.get("key")] = {"name": data.get("name") or "", "parent": data.get("parentCollection") or None}
            if len(page) < PAGE:
                break
            start += PAGE
    except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as e:
        log(f"collection names not resolved ({getattr(e, 'reason', None) or e}); printing keys")
        return {}
    paths = {}
    for key in cols:
        parts, k, seen = [], key, set()
        while k in cols and k not in seen:
            seen.add(k)
            parts.append(cols[k]["name"])
            k = cols[k]["parent"]
        paths[key] = "/".join(reversed(parts))
    return paths


# --- records -------------------------------------------------------------------


def parse_records(raw, source):
    """Any run of JSON values: JSONL, one array, one object — or pretty-printed objects concatenated (cat records/*.json)."""
    decoder, records, pos = json.JSONDecoder(), [], 0
    while True:
        while pos < len(raw) and raw[pos].isspace():
            pos += 1
        if pos >= len(raw):
            return records
        line = raw.count("\n", 0, pos) + 1
        try:
            obj, pos = decoder.raw_decode(raw, pos)
        except ValueError as e:
            raise Stop("invalid_record", 1, "Records are JSONL, a JSON array, one object, or concatenated objects.",
                       source=f"{source}:{line}", error=str(e))
        batch = obj if isinstance(obj, list) else [obj]
        if not all(isinstance(r, dict) for r in batch):
            raise Stop("invalid_record", 1, "Each record is a JSON object.", source=f"{source}:{line}")
        records.extend(batch)


def load_records(paths):
    """[(record, source)] from the paths (globs expanded) or, without paths, from stdin."""
    if not paths:
        if sys.stdin.isatty():
            raise Stop("no_records", 1, "Pass record paths, or pipe records (JSONL / array / object) on stdin.")
        return [(r, "stdin") for r in parse_records(sys.stdin.read(), "stdin")]
    out = []
    for pattern in paths:
        expanded = os.path.expanduser(pattern)
        matches = sorted(glob.glob(expanded)) if any(c in expanded for c in "*?[") else [expanded]
        if not matches:
            raise Stop("record_not_found", 1, "No file matches this record path.", path=pattern)
        for m in matches:
            p = Path(m)
            if not p.is_file():
                raise Stop("record_not_found", 1, "No such record file.", path=str(p))
            out.extend((r, str(p)) for r in parse_records(p.read_text(encoding="utf-8"), str(p)))
    return out


# --- rows ----------------------------------------------------------------------


def file_kind(attachment):
    """pdf / snapshot / other from an attachment's contentType, then its filename / title / url / path."""
    ct = (attachment.get("contentType") or "").lower()
    names = [str(attachment.get(k) or "").strip().lower() for k in ("filename", "title", "url", "path")]
    if ct == "application/pdf" or any(re.search(r"\.pdf(\?|#|$)", n) for n in names):
        return "pdf"
    if ct == "text/html" or any(re.search(r"\.html?(\?|#|$)", n) for n in names) or attachment.get("linkMode") == "imported_url":
        return "snapshot"
    return "other"


def as_dict(value):
    return value if isinstance(value, dict) else {}


def library_state(rec):
    """The read-back `saved` block of an item this run created, else `found`."""
    saved = as_dict(rec.get("saved"))
    return saved if "attachments" in saved or "tags" in saved else as_dict(rec.get("found"))


def row_of(rec, source, paths):
    found = library_state(rec)
    item = rec.get("item") if isinstance(rec.get("item"), dict) else {}
    saved = rec.get("saved") if isinstance(rec.get("saved"), dict) else {}
    attach = rec.get("attach") if isinstance(rec.get("attach"), dict) else {}
    slug = rec.get("slug") or (Path(source).stem if source != "stdin" else "?")
    given, lib_cite = rec.get("citationKey") or None, found.get("citationKey") or None
    cite = given or lib_cite
    key = saved.get("key") or found.get("key") or None
    title = item.get("title") or found.get("title") or ""
    year = YEAR_RE.search(str(item.get("date") or found.get("date") or ""))
    if found.get("collections") is not None:
        colls = list(found.get("collections") or [])
    else:
        colls = rec["collection"] if isinstance(rec.get("collection"), list) else [rec["collection"]] if rec.get("collection") else []
    colls = [paths.get(c, c) if isinstance(c, str) else str(c) for c in colls]
    tags = found.get("tags") if found.get("tags") is not None else rec.get("tags") or []
    kinds = {file_kind(a) for a in found.get("attachments") or [] if isinstance(a, dict)}
    if attach.get("key"):
        kinds.add(file_kind(attach))
    file = "PDF" if "pdf" in kinds else "snapshot" if "snapshot" in kinds else None
    return {"slug": slug, "citationKey": cite, "library_citationKey": lib_cite, "cite_mismatch": bool(given and lib_cite and given != lib_cite), "title": title, "year": year.group(1) if year else None, "item_key": key,
            "collections": colls, "tags": len(tags) if isinstance(tags, list) else 0, "file": file,
            "blocker": rec.get("blocker") or None}


def summarize(rows):
    return {"total": len(rows), "in_library": sum(1 for r in rows if r["item_key"]),
            "with_pdf": sum(1 for r in rows if r["file"] == "PDF"), "with_snapshot": sum(1 for r in rows if r["file"] == "snapshot"),
            "missing": sum(1 for r in rows if not r["item_key"]), "blocked": sum(1 for r in rows if r["blocker"])}


def cell(value):
    s = DASH if value is None or value == "" else str(value)
    return s.replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def markdown(rows, summary):
    blockers = any(r["blocker"] for r in rows)
    head = ["citationKey", "title", "year", "item key", "collection(s)", "tags", "file"] + (["blocker"] if blockers else [])
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        cite = cell(r["citationKey"]) if r["citationKey"] else f"*{cell(r['slug'])}*"
        if r.get("cite_mismatch"):
            cite += f" (≠ library: {cell(r['library_citationKey'])})"
        cells = [cite, cell(r["title"]), cell(r["year"]), cell(r["item_key"]), cell("; ".join(r["collections"])), cell(r["tags"]),
                 cell(r["file"])] + ([cell(r["blocker"])] if blockers else [])
        lines.append("| " + " | ".join(cells) + " |")
    s = summary
    lines.append("")
    lines.append(f"**Summary**: total {s['total']} · in library {s['in_library']} · with PDF {s['with_pdf']} · "
                 f"with snapshot {s['with_snapshot']} · missing {s['missing']} · blocked {s['blocked']}")
    return "\n".join(lines) + "\n"


# --- sections ------------------------------------------------------------------


def find_work(flag, records):
    if flag:
        return Path(flag).expanduser()
    dirs = {Path(src).resolve().parent.parent for _, src in records if src != "stdin"}
    work = dirs.pop() if len(dirs) == 1 else None
    return work if work is not None and ((work / ".started").exists() or (work / "fetch.jsonl").exists()) else None


def read_log(work):
    out = []
    try:
        with open(work / "fetch.jsonl", encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue  # a torn line
                if isinstance(obj, dict):
                    out.append(obj)
    except OSError:
        pass
    return out


def own_pdf(work, slug):
    """A PDF of this record filed in the work directory (any version; a snapshot does not count)."""
    return work is not None and any((work / "records" / (slug + sfx)).is_file() for sfx in STEM_FILES if sfx.endswith(".pdf"))


def library_has_pdf(rec):
    return any(isinstance(a, dict) and a.get("contentType") == "application/pdf"
               for a in library_state(rec).get("attachments") or [])


def host(url):
    try:
        return urllib.parse.urlsplit(url or "").hostname or ""
    except ValueError:
        return ""


def not_obtained(items, work, log_lines):
    tries = defaultdict(list)
    for e in log_lines:
        if e.get("event") == "try":
            tries[e.get("slug")].append(e)
    out = []
    for rec, row in items:
        attach = as_dict(rec.get("attach"))
        if own_pdf(work, row["slug"]) or (attach.get("md5_ok") and file_kind(attach) == "pdf") or library_has_pdf(rec):
            continue
        passes = defaultdict(list)
        for t in tries.get(row["slug"], []):
            if t.get("by") == "agent":
                what = f"verdict {t.get('result')}"
            else:
                what = t.get("result") + (f" ({t['why']})" if t.get("why") else "")
            route = t.get("via") + (f" ({t['version']})" if t.get("version") not in (None, "published") else "")
            passes[t.get("pass", 1)].append(f"{route} {host(t.get('url'))}".strip() + f": {what}")
        out.append({"slug": row["slug"], "passes": {str(k): v for k, v in sorted(passes.items())},
                    "snapshot": (work is not None and (work / "records" / f"{row['slug']}.html").is_file())
                    or file_kind(attach) == "snapshot"})
    return out


def alternate_versions(items):
    out = []
    for rec, row in items:
        attach = as_dict(rec.get("attach"))
        if attach.get("key") and attach.get("version") not in (None, "published", "snapshot"):
            out.append({"slug": row["slug"], "version": attach["version"], "title": attach.get("title"),
                        "attachment_key": attach["key"]})
    return out


def attachment_version(a):
    title = str(a.get("title") or "")
    for name, pattern in VERSION_WORDS:
        if pattern.search(title):
            return name
    kind = file_kind(a)
    return kind if kind in ("snapshot", "pdf") else None


def attachments_to_clean(items):
    out = []
    for rec, row in items:
        attach = as_dict(rec.get("attach"))
        if not attach.get("key") or attach.get("version", "published") != "published" or file_kind(attach) != "pdf":
            continue
        ours = as_dict(rec.get("pdf")).get("md5")
        for a in library_state(rec).get("attachments") or []:
            if not isinstance(a, dict) or a.get("key") in (None, attach["key"]) or a.get("linkMode") == "linked_url":
                continue
            kind, label = attachment_version(a), f"'{a.get('title') or a.get('filename') or a['key']}'"
            if kind in (None, "supplement"):
                continue
            if kind == "snapshot":
                why = f"snapshot {label}, superseded by the published PDF"
            elif kind in ("preprint", "accepted"):
                why = f"{kind} {label}, superseded by the published PDF"
            elif ours and a.get("md5") == ours:
                why = f"the attached file a second time ({label})"
            else:
                why = f"another PDF {label} whose version its title does not state: compare before trashing"
            out.append({"slug": row["slug"], "item_key": row["item_key"], "key": a["key"], "reason": why})
    return out


def tag_names(tags):
    out = {}
    for t in tags if isinstance(tags, list) else []:
        if isinstance(t, str) and t.strip():
            out[t] = 0
        elif isinstance(t, dict) and isinstance(t.get("tag"), str):
            out[t["tag"]] = 0 if t.get("type") in (None, 0, "0") else 1
    return out


def new_tags(items, api):
    added = defaultdict(dict)
    for rec, row in items:
        saved = as_dict(rec.get("saved"))
        if not saved.get("key"):
            continue
        for name, kind in tag_names(saved.get("tags") if "tags" in saved else rec.get("tags")).items():
            if kind == 0:
                added[name][saved["key"]] = row["citationKey"] or row["slug"]
    if not added or api is None:
        return {}
    counts, start = defaultdict(int), 0
    try:
        while True:
            page = api.get_json(f"{LIB}/tags?limit={PAGE}&start={start}")
            for t in page:
                counts[t.get("tag")] += int((t.get("meta") or {}).get("numItems") or 0)
            if len(page) < PAGE:
                break
            start += PAGE
    except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as e:
        log(f"new tags not checked ({getattr(e, 'reason', None) or e})")
        return {}
    groups = defaultdict(list)
    for name in sorted(added, key=str.casefold):
        if 0 < counts.get(name, 0) <= len(added[name]):
            prefix = name.split("/", 1)[0] + "/" if "/" in name else ""
            groups[prefix].append({"tag": name, "items": sorted(added[name].values())})
    return dict(sorted(groups.items(), key=lambda kv: (kv[0] != "", kv[0].casefold())))


def leftovers(work, log_lines):
    if work is None:
        return {}
    latest = {}
    for e in log_lines:
        if e.get("event") == "claim" and e.get("source") and not str(e["source"]).startswith(("http:", "https:")):
            latest[e["source"]] = e
    downloads = [{"file": Path(src).name, "why": e.get("why"), "in_library": e.get("in_library")}
                 for src, e in latest.items() if e.get("result") == "left" and Path(src).exists()]
    sources = {e.get("file"): e.get("source") for e in log_lines if e.get("event") == "claim" and e.get("result") == "unverified"}
    unverified = [{"file": f.name, "source": sources.get(f.name)} for f in sorted((work / "unverified").glob("*"))
                  if f.is_file()] if (work / "unverified").is_dir() else []
    return {k: v for k, v in (("downloads", downloads), ("unverified", unverified)) if v}


def stops(log_lines):
    verdicts = {(e.get("slug"), e.get("pass"), e.get("via")): e.get("result") for e in log_lines
                if e.get("event") == "try" and e.get("by") == "agent"}
    return [{"slug": e.get("slug"), "pass": e.get("pass"), "why": e.get("why"), "url": e.get("url"), "at": e.get("at"),
             "verdict": verdicts.get((e.get("slug"), e.get("pass"), e.get("via")))}
            for e in log_lines if e.get("event") == "try" and e.get("result") == "stopped"]


def build_sections(items, work, api):
    log_lines = read_log(work) if work is not None else []
    sections = {"not_obtained": not_obtained(items, work, log_lines) if work is not None else [],
                "alternate_versions": alternate_versions(items),
                "attachments_to_clean": attachments_to_clean(items), "new_tags": new_tags(items, api),
                "leftovers": leftovers(work, log_lines), "stops": stops(log_lines)}
    return {k: v for k, v in sections.items() if v}


def table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]


def sections_markdown(sections, rows):
    cite = {r["slug"]: r["citationKey"] or r["slug"] for r in rows}
    out = []

    def head(title):
        out.extend(["", f"### {title}", ""])

    if "not_obtained" in sections:
        s = sections["not_obtained"]
        head(f"无法获取 (not obtained): {len(s)}")
        out.extend(table(["citationKey", "tries, pass by pass", "snapshot"],
                         [[cite[r["slug"]], " · ".join(f"pass {k}: " + "; ".join(v) for k, v in r["passes"].items())
                           or "not tried", "yes" if r["snapshot"] else DASH] for r in s]))
    if "alternate_versions" in sections:
        s = sections["alternate_versions"]
        head(f"替代版本 (alternate versions): {len(s)}")
        out.extend(table(["citationKey", "version", "attachment"],
                         [[cite[r["slug"]], r["version"], f"{r['title'] or DASH} ({r['attachment_key']})"] for r in s]))
    if "attachments_to_clean" in sections:
        s = sections["attachments_to_clean"]
        head(f"待清理附件 (attachments to clean): {len(s)}")
        out.extend(table(["citationKey", "item key", "attachment", "reason"],
                         [[cite[r["slug"]], r["item_key"], r["key"], r["reason"]] for r in s]))
        out.extend(["", "Only on the user's word: `uv run scripts/trash_item.py --dry-run --key "
                    + " ".join(r["key"] for r in s) + "`, then without --dry-run."])
    if "new_tags" in sections:
        groups = sections["new_tags"]
        head(f"新标签 (new tags): {sum(len(v) for v in groups.values())}")
        for prefix, tags in groups.items():
            listed = "; ".join(f"{t['tag'][len(prefix):]} ({', '.join(t['items'])})" for t in tags)
            out.append(f"- {'`' + prefix + '`' if prefix else 'bare'}: {listed}")
    if "leftovers" in sections:
        s = sections["leftovers"]
        head(f"残留 (leftovers): {len(s.get('downloads', [])) + len(s.get('unverified', []))}")
        for d in s.get("downloads", []):
            out.append(f"- Downloads `{d['file']}` — {d['why']}" + (" (already in the library)" if d.get("in_library") else ""))
        for u in s.get("unverified", []):
            out.append(f"- unverified/`{u['file']}`" + (f" — from {u['source']}" if u.get("source") else ""))
    if "stops" in sections:
        s = sections["stops"]
        head(f"停下与门禁 (stops and gates): {len(s)}")
        out.extend(table(["citationKey", "pass", "why", "page", "verdict"],
                         [[cite.get(r["slug"], r["slug"]), r["pass"], r["why"], host(r["url"]) or DASH, r["verdict"] or DASH]
                          for r in s]))
    return "\n".join(out) + "\n" if out else ""


def run(args):
    records = load_records(args.records)
    if not records:
        raise Stop("no_records", 1, "The input holds no records.")
    api = None if args.no_resolve else Api(args.base_url)
    paths = {} if api is None else collection_paths(api)
    rows = [row_of(rec, source, paths) for rec, source in records]
    summary = summarize(rows)
    sections = build_sections([(rec, row) for (rec, _), row in zip(records, rows)], find_work(args.work, records), api)
    if args.json:
        out = {"code": "ok", "rows": rows, "summary": summary}
        if sections:
            out["sections"] = sections
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(markdown(rows, summary) + sections_markdown(sections, rows))
    sys.exit(0)



def parse_args():
    p = argparse.ArgumentParser(
        description="Summarize paper-to-zotero records as a Markdown table plus a tally (or JSON).",
        epilog="Exit 0 = report written; 1 = no records / unreadable record (JSON on stderr).")
    p.add_argument("records", nargs="*", metavar="RECORD", help="record files (globs allowed); none = records on stdin")
    p.add_argument("--json", action="store_true", help="print {code, rows, summary} as JSON instead of Markdown")
    p.add_argument("--no-resolve", action="store_true",
                   help="no local API reads: collection keys as they are, no new-tags section")
    p.add_argument("--work", metavar="DIR", help="the work directory (default: the parent of the records' directory)")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    return p.parse_args()


def main():
    run(parse_args())


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
