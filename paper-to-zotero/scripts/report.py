# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Summarize paper-to-zotero records as a Markdown table plus a one-line tally (or the same as JSON).

Reads records (paths, globs, or stdin: JSONL / array / object) and prints one
row per record: citationKey | title | year | item key | collection(s) | tags |
file [| blocker]. citationKey is the record's `citationKey`, else
`found.citationKey`, else the slug in italics; the item key is `saved.key`,
else `found.key`; collections and tags come from `found` when it is there
(the library's state after find_in_library.py --readback), else from the
record's own `collection` / `tags`; tags is a count; file is PDF / snapshot /
"—" from `found.attachments` and `attach`. The blocker column appears when any
record has one. Collection keys become paths ("自然图像/Diffusion") when the
local API answers; otherwise the keys are printed as they are.

stdout is the Markdown (or, with --json, one JSON object {code, rows,
summary}); JSON diagnostics and errors go to stderr. Exit 0 = report written;
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
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
LIB = "/api/users/0"
PAGE = 100
KEY_RE = re.compile(r"^[A-Z0-9]{8}$")
YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")
DASH = "—"


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


def row_of(rec, source, paths):
    found = rec.get("found") if isinstance(rec.get("found"), dict) else {}
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
        colls = [rec["collection"]] if rec.get("collection") else []
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


def run(args):
    records = load_records(args.records)
    if not records:
        raise Stop("no_records", 1, "The input holds no records.")
    paths = {} if args.no_resolve else collection_paths(Api(args.base_url))
    rows = [row_of(rec, source, paths) for rec, source in records]
    summary = summarize(rows)
    if args.json:
        print(json.dumps({"code": "ok", "rows": rows, "summary": summary}, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(markdown(rows, summary))
    sys.exit(0)


def parse_args():
    p = argparse.ArgumentParser(
        description="Summarize paper-to-zotero records as a Markdown table plus a tally (or JSON).",
        epilog="Exit 0 = report written; 1 = no records / unreadable record (JSON on stderr).")
    p.add_argument("records", nargs="*", metavar="RECORD", help="record files (globs allowed); none = records on stdin")
    p.add_argument("--json", action="store_true", help="print {code, rows, summary} as JSON instead of Markdown")
    p.add_argument("--no-resolve", action="store_true", help="print collection keys without asking the local API for names")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    return p.parse_args()


def main():
    run(parse_args())


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
