# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Export Zotero items as BibTeX (keys = citationKey) from a collection, item keys, citation keys, or records.

Item keys come from --collection (its top-level items, paged; --recursive adds
the sub-collections), --key, --cite (resolved per citationKey), or records
(`saved.key`, else `found.key`; records without one are skipped and listed).
Each chunk of 50 keys is one GET /items/top?itemKey=K1,K2,...&format=bibtex
(verified on the local API 2026-09-23: the filter is honoured up to the whole
library in one URL, `limit` cuts the export so it is passed explicitly, unknown
keys are dropped silently — hence the JSON read that also gives each item's
citationKey). Entries are written ordered by their BibTeX key, to stdout or
--out.

stdout is the BibTeX text (the one exception to JSON-on-stdout, with
report.py), so every JSON line goes to stderr: on success one summary
{"code", "count", "missing_citation_key", "duplicate_keys", ...}, on failure one
{code, hint, ...}. Exit 0 = exported and every item has a unique citationKey;
1 = exported, but some item lacks a citationKey / a key is shared / a key was
not found (fix with update_item.py --set citationKey=..., then re-run), or a
fatal error (collection_not_found, cite_not_found, cite_ambiguous,
no_records, ...); 2 = cannot read (Zotero unreachable, local API disabled).

Examples:
  uv run scripts/export_bib.py --collection 9EYXTC2I --recursive --out ref.bib
  uv run scripts/export_bib.py --cite liu2022progressive --cite zhou2021handheld
  uv run scripts/export_bib.py work/records/*.json > ref.bib
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
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
LIB = "/api/users/0"
PAGE = 100
CHUNK = 50
KEY_RE = re.compile(r"^[A-Z0-9]{8}$")
ENTRY_KEY = re.compile(r"^@(\w+)\s*\{\s*([^,\s]+)\s*,")
CHILD_TYPES = {"note", "attachment", "annotation"}


class Stop(Exception):
    """Carry a result code out of any depth; main() turns it into JSON + exit."""

    def __init__(self, code, exit_code=1, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit_code, self.hint, self.extra = code, exit_code, hint, extra


def log(msg):
    print(msg, file=sys.stderr)


def emit(code, exit_code=0, hint=None, **extra):
    """One JSON line on stderr (stdout carries the BibTeX), then exit."""
    out = {"code": code, **extra}
    if hint and exit_code != 0:
        out["hint"] = hint
    print(json.dumps(out, ensure_ascii=False), file=sys.stderr)
    sys.exit(exit_code)


def text(body, limit=400):
    return body.decode("utf-8", errors="replace").strip()[:limit]


class Api:
    """Minimal client for the local API; bypasses any proxy from the environment."""

    def __init__(self, base_url, timeout=120):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, body=None, headers=None):
        h = {"Accept": "application/json"}
        h.update(headers or {})
        data = None
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", None) or e
            raise Stop("zotero_unreachable", 2, "Start Zotero, then retry; check --base-url if it is not the default.",
                       base_url=self.base, error=str(reason))


def check_common(status, body):
    """Failures that mean 'cannot read' regardless of which call produced them."""
    msg = text(body)
    if status == 403 and "not enabled" in msg.lower():
        raise Stop("local_api_disabled", 2, "Ask the user to enable the local API in Zotero settings (Advanced), then retry.",
                   status=status, body=msg)


def get_json(api, path):
    status, _, body = api.request("GET", path)
    check_common(status, body)
    if status == 404:
        return None
    if status != 200:
        raise Stop("unexpected_response", 1, "Unexpected local API reply; see status and body.", path=path, status=status, body=text(body))
    try:
        return json.loads(body)
    except ValueError:
        raise Stop("unexpected_response", 1, "The local API did not return JSON.", path=path, body=text(body))


def get_pages(api, path):
    """Every row of a paged listing (limit 100)."""
    rows, start, sep = [], 0, "&" if "?" in path else "?"
    while True:
        page = get_json(api, f"{path}{sep}limit={PAGE}&start={start}")
        if not isinstance(page, list):
            raise Stop("unexpected_response", 1, "Expected a JSON list from the local API.", path=path, start=start)
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        start += PAGE


def is_top(row):
    data = row.get("data") or {}
    return data.get("itemType") not in CHILD_TYPES and not data.get("parentItem")


def resolve_cite(api, cite):
    """Item key for a citationKey: a q=everything search first (verified to hit on the local API, 2026-09-23),
    then a paged scan of /items/top as the fallback."""
    query = urllib.parse.urlencode({"q": cite, "qmode": "everything", "limit": 50})
    rows = get_json(api, f"{LIB}/items?{query}") or []
    hits = [r["key"] for r in rows if is_top(r) and (r.get("data") or {}).get("citationKey") == cite]
    if not hits:
        log(f"no search hit for citationKey {cite!r}; scanning /items/top (fallback)")
        hits = [r["key"] for r in get_pages(api, f"{LIB}/items/top") if (r.get("data") or {}).get("citationKey") == cite]
    if not hits:
        raise Stop("cite_not_found", 1, "No item carries this citationKey; check it with read_library.py items --q, or pass --key.", cite=cite)
    if len(hits) > 1:
        raise Stop("cite_ambiguous", 1, "Several items carry this citationKey; pass --key for the one you mean.", cite=cite, keys=hits)
    return hits[0]


# --- records (stream convention, read side) ----------------------------------


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


# --- collecting keys -----------------------------------------------------------


def split_keys(values):
    keys = []
    for v in values or []:
        keys.extend(k.strip() for k in v.split(",") if k.strip())
    return keys


def live_collections(api):
    cols = {}
    for row in get_pages(api, f"{LIB}/collections"):
        data = row.get("data") or {}
        if not data.get("deleted"):
            cols[row.get("key")] = {"name": data.get("name") or "", "parent": data.get("parentCollection") or None}
    return cols


def collection_keys(api, key, recursive, notes):
    """Keys of the top-level regular items of a collection (and, with --recursive, of its live sub-collections)."""
    col = get_json(api, f"{LIB}/collections/{key}")
    if col is None or (col.get("data") or {}).get("deleted"):
        raise Stop("collection_not_found", 1, "No live collection has this key; pick it from ready.py's tree.", collection=key)
    todo, seen, keys = [key], set(), []
    children = {}
    if recursive:
        for k, c in live_collections(api).items():
            children.setdefault(c["parent"], []).append(k)
    while todo:
        k = todo.pop(0)
        if k in seen:
            continue
        seen.add(k)
        for row in get_pages(api, f"{LIB}/collections/{k}/items/top"):
            if (row.get("data") or {}).get("itemType") in CHILD_TYPES:
                notes["skipped"].append({"key": row.get("key"), "reason": f"standalone {row['data']['itemType']}"})
                continue
            keys.append(row["key"])
        todo.extend(children.get(k, []))
    notes["collections"] = sorted(seen)
    return keys


def gather(api, args, notes):
    """Item keys in first-seen order, without duplicates."""
    keys = []
    if args.collection:
        keys += collection_keys(api, args.collection, args.recursive, notes)
    for k in split_keys(args.key):
        if not KEY_RE.match(k):
            raise Stop("invalid_key", 1, "--key takes 8-character item keys (repeat it or separate keys by commas).", key=k)
        keys.append(k)
    for c in split_keys(args.cite):
        try:
            keys.append(resolve_cite(api, c))
        except Stop as s:
            if s.code not in ("cite_not_found", "cite_ambiguous"):
                raise
            notes["unresolved"].append({"cite": c, "code": s.code, **s.extra})
    if args.records or not (args.collection or args.key or args.cite):
        for rec, source in load_records(args.records):
            key = (rec.get("saved") or {}).get("key") or (rec.get("found") or {}).get("key")
            if not key:
                notes["no_item_key"].append(rec.get("slug") or source)
                continue
            keys.append(key)
    seen, unique = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    return unique


# --- export ------------------------------------------------------------------


def chunks(seq):
    for i in range(0, len(seq), CHUNK):
        yield seq[i:i + CHUNK]


def fetch_items(api, keys):
    """{key: data} for the top-level items among `keys` (unknown keys are simply absent)."""
    items = {}
    for part in chunks(keys):
        for row in get_pages(api, f"{LIB}/items/top?itemKey={','.join(part)}"):
            items[row["key"]] = row.get("data") or {}
    return items


def export_bibtex(api, keys):
    out = []
    for part in chunks(keys):
        status, _, body = api.request("GET", f"{LIB}/items/top?itemKey={','.join(part)}&format=bibtex&limit={PAGE}",
                                      headers={"Accept": "text/plain, */*"})
        check_common(status, body)
        if status != 200:
            raise Stop("export_failed", 1, "The local API refused the BibTeX export; see status and body.", status=status, body=text(body))
        out.append(body.decode("utf-8", errors="replace"))
    return "\n".join(out)


def entries_of(bibtex):
    """[(bibkey, entry text)] — an entry starts with '@' at the beginning of a line."""
    entries = []
    for piece in re.split(r"(?m)^(?=@)", bibtex):
        piece = piece.strip()
        if not piece.startswith("@"):
            continue
        m = ENTRY_KEY.match(piece)
        entries.append((m.group(2) if m else "", piece))
    return entries


def run(api, args):
    notes = {"skipped": [], "unresolved": [], "no_item_key": []}
    keys = gather(api, args, notes)
    if not keys and not any(notes[k] for k in ("unresolved", "no_item_key")):
        raise Stop("no_records", 1, "Nothing to export: the collection is empty or no key was given.", **{k: v for k, v in notes.items() if v})
    items = fetch_items(api, keys)
    not_found = [k for k in keys if k not in items]
    present = [k for k in keys if k in items]
    for k in present:
        if items[k].get("itemType") in CHILD_TYPES:
            notes["skipped"].append({"key": k, "reason": f"standalone {items[k]['itemType']}"})
    present = [k for k in present if items[k].get("itemType") not in CHILD_TYPES]

    missing, by_cite = [], {}
    for k in present:
        cite = items[k].get("citationKey")
        if cite:
            by_cite.setdefault(cite, []).append(k)
        else:
            missing.append(k)
    duplicates = [{"citationKey": c, "keys": ks} for c, ks in by_cite.items() if len(ks) > 1]

    entries = sorted(entries_of(export_bibtex(api, present)), key=lambda e: (e[0].lower(), e[0])) if present else []
    output = "\n\n".join(e[1] for e in entries) + ("\n" if entries else "")
    if args.out:
        Path(args.out).expanduser().write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
        sys.stdout.flush()

    summary = {"count": len(entries), "missing_citation_key": missing, "duplicate_keys": duplicates}
    if not_found:
        summary["not_found"] = not_found
    summary.update({k: v for k, v in notes.items() if v})
    if args.out:
        summary["out"] = str(Path(args.out).expanduser())
    problems = [c for c, v in (("missing_citation_key", missing), ("duplicate_keys", duplicates), ("not_found", not_found),
                               ("cite_unresolved", notes["unresolved"]), ("no_item_key", notes["no_item_key"])) if v]
    if problems:
        emit(problems[0], 1, "The BibTeX was written; give every item a unique citationKey (update_item.py --set citationKey=...) "
             "and fix the keys listed, then re-run.", problems=problems, **summary)
    emit("ok", 0, **summary)


def parse_args():
    p = argparse.ArgumentParser(
        description="Export Zotero items as BibTeX (keys = citationKey) from a collection, item keys, citation keys, or records.",
        epilog="BibTeX goes to stdout (or --out), ordered by key; one JSON summary line goes to stderr. "
               "Exit 0 = every item has a unique citationKey; 1 = some lack one / share one / were not found (the BibTeX is still written), "
               "or a fatal error; 2 = cannot read (zotero_unreachable, local_api_disabled).")
    p.add_argument("--collection", metavar="COLLKEY", help="export the collection's top-level items")
    p.add_argument("--recursive", action="store_true", help="with --collection: include its sub-collections")
    p.add_argument("--key", metavar="ITEMKEY", action="append", help="item key (repeatable, or comma-separated)")
    p.add_argument("--cite", metavar="CITEKEY", action="append", help="citationKey (repeatable, or comma-separated)")
    p.add_argument("records", nargs="*", metavar="RECORD", help="record files (globs allowed); none of the above = records on stdin")
    p.add_argument("--out", metavar="FILE", help="write the BibTeX here instead of stdout")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    args = p.parse_args()
    if args.collection and not KEY_RE.match(args.collection):
        p.error("--collection is an 8-character collection key")
    if args.recursive and not args.collection:
        p.error("--recursive needs --collection")
    return args


def main():
    args = parse_args()
    run(Api(args.base_url), args)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
