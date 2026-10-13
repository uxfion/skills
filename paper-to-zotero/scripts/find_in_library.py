# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Find papers in the Zotero library by identifier, key or citation key, or refresh records from it (read-only, local API).

Single lookups (v1): --doi / --arxiv / --title look one paper up through
Zotero's local web API (GET only), confirm every candidate exactly, and
report what the library holds for it: key, citationKey, title, item type,
identifiers, attachments (with md5), collection paths and tags. --key and
--cite print that description for one known item (code found / not_found).

Search strategy
- Identifier: ``q=<id>&qmode=fields`` (the default qmode never hits DOI or
  arXiv fields), then exact comparison against data.DOI (case-insensitive),
  data.archiveID, data.url and data.extra; arXiv version suffixes (v2) are
  ignored. Hits on a child attachment are promoted to the parent item.
- Title: ``q=<title>`` with the default qmode, ``qmode=everything`` if that
  finds nothing, plus the part before a subtitle separator (": ", " - ")
  so a shorter library title can surface. Candidates are compared after
  normalization (NFKC, casefold, letters and digits only); a title that
  contains the other one is reported as a near match, e.g. preprint vs
  published version.
- Citation key (--cite): ``q=<cite>&qmode=everything`` filtered on an exact
  data.citationKey, then a scan of every top-level item as fallback;
  cite_not_found / cite_ambiguous (exit 1).

Record stream: record files as arguments (or records on stdin as JSONL, an
array or one object). A record with saved.key / found.key and --readback is
read back by key and its `found` refreshed (missing -> code
missing_in_library, `found` removed, a `blocker` noted; exit 1). Without
--readback such records are skipped; the others are deduplicated by their
item's DOI, then arXiv id, then title, and a hit writes `found` (code found
/ near_match); not_found leaves the record untouched. Without -i the full
records go to stdout as JSONL and the summary to stderr; with -i each record
is written back to its file and stdout gets one summary line per record plus
{"summary": {total, ok, skipped, failed}}.

Exit codes, single lookups: 0 = not found (safe to import); 1 = found or near
match (the agent decides); for --key / --cite 0 = found, 1 = not_found.
Stream: 0 = every record checked or skipped, 1 = missing_in_library /
unusable records. Always 2 = cannot check (Zotero unreachable, local API
disabled, API error).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
LIB = "/api/users/0"
PAGE_SIZE = 100
TIMEOUT = 15
CHILD_TYPES = {"attachment", "note", "annotation"}
SUBTITLE_SEPARATORS = (": ", " - ", " – ", " — ")
ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})"

VERBOSE = False


def log(msg: str) -> None:
    if VERBOSE:
        print(msg, file=sys.stderr)


class ApiError(Exception):
    """Carries the output code and detail; exit status 2 unless said otherwise."""

    def __init__(self, code: str, detail: str, hint: str, exit_code: int = 2, **extra):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.hint = hint
        self.exit_code = exit_code
        self.extra = extra


class LocalApi:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        # Bypass any proxy from the environment; the API is on localhost.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(self, path: str, params: dict | None = None, allow_404: bool = False):
        """Return (object, headers); (None, headers) on 404 when allowed."""
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=TIMEOUT) as resp:
                status, headers, body = resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            status, headers, body = e.code, dict(e.headers), e.read()
        except (urllib.error.URLError, OSError) as e:
            raise ApiError(
                "zotero_unreachable",
                f"{self.base_url}: {getattr(e, 'reason', e)}",
                "Zotero does not answer. Ask the user to start Zotero (never restart it "
                "from here), then rerun.",
            ) from None
        log(f"GET {url} -> {status}")
        text = body.decode("utf-8", errors="replace")
        if status == 403:
            raise ApiError(
                "local_api_disabled",
                text.strip() or "403",
                "Zotero's local API is off. Ask the user to enable it in Zotero "
                "Settings > Advanced > 'Allow other applications on this computer to "
                "communicate with Zotero', then rerun.",
            )
        if status == 404 and allow_404:
            return None, headers
        if status != 200:
            raise ApiError(
                "api_error",
                f"GET {path} -> {status} {text.strip()[:200]}",
                "Unexpected response from the local API; check Zotero and rerun.",
            )
        try:
            return json.loads(text), headers
        except json.JSONDecodeError:
            raise ApiError(
                "api_error",
                f"GET {path}: response is not JSON",
                "Unexpected response from the local API; check Zotero and rerun.",
            ) from None

    def get_all(self, path: str, params: dict | None = None) -> list:
        """Fetch a multi-object endpoint page by page."""
        out: list = []
        start = 0
        while True:
            page, _ = self.get(path, {**(params or {}), "limit": PAGE_SIZE, "start": start})
            if not isinstance(page, list):
                break
            out.extend(page)
            if len(page) < PAGE_SIZE:
                break
            start += PAGE_SIZE
        return out


# --- normalization -----------------------------------------------------------


def normalize_title(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").casefold()
    return "".join(ch for ch in s if ch.isalnum())


def normalize_doi(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", s, flags=re.I)
    return s.strip().lower()


def normalize_arxiv(s: str) -> str:
    """Bare id without prefix, URL or version suffix; lowercase for old-style ids."""
    s = (s or "").strip()
    s = re.sub(r"^(?:https?://)?(?:www\.)?arxiv\.org/(?:abs|pdf)/", "", s, flags=re.I)
    s = re.sub(r"^arxiv:\s*", "", s, flags=re.I)
    s = re.sub(r"\.pdf$", "", s, flags=re.I)
    s = re.sub(r"v\d+$", "", s)
    return s.strip().lower()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- matching ----------------------------------------------------------------


def extra_lines(data: dict) -> list[str]:
    return [ln.strip() for ln in (data.get("extra") or "").splitlines()]


def matches_doi(data: dict, doi: str) -> bool:
    if normalize_doi(data.get("DOI") or "") == doi:
        return True
    for ln in extra_lines(data):
        m = re.match(r"DOI:\s*(\S+)", ln, flags=re.I)
        if m and normalize_doi(m.group(1)) == doi:
            return True
    url = (data.get("url") or "").lower()
    return bool(re.search(r"doi\.org/" + re.escape(doi) + r"(?:$|[?#])", url))


def matches_arxiv(data: dict, aid: str) -> bool:
    if normalize_doi(data.get("DOI") or "") == f"10.48550/arxiv.{aid}":
        return True
    if normalize_arxiv(data.get("archiveID") or "") == aid:
        return True
    tail = re.escape(aid) + r"(?:v\d+)?(?![0-9])"
    if re.search(r"arxiv\.org/(?:abs|pdf)/" + tail, data.get("url") or "", flags=re.I):
        return True
    return bool(re.search(r"arxiv:\s*" + tail, data.get("extra") or "", flags=re.I))


def is_top_level(item: dict) -> bool:
    data = item.get("data", {})
    return data.get("itemType") not in CHILD_TYPES and not data.get("parentItem")


def identifiers_of(item: dict) -> tuple[str, str, str]:
    """(doi, arxiv id, title) of a record's item, each '' when absent; an arXiv DOI counts as the arXiv id."""
    doi = normalize_doi(item.get("DOI") or "")
    if not doi:
        for ln in (item.get("extra") or "").splitlines():
            m = re.match(r"\s*DOI:\s*(\S+)", ln, flags=re.I)
            if m:
                doi = normalize_doi(m.group(1))
                break
    aid = ""
    m = re.fullmatch(r"10\.48550/arxiv\.(.+)", doi)
    if m:
        aid, doi = normalize_arxiv(m.group(1)), ""
    if not aid and item.get("archiveID"):
        m = re.search(rf"arxiv:\s*({ARXIV_ID})", item["archiveID"], flags=re.I)
        aid = normalize_arxiv(m.group(1)) if m else ""
    if not aid:
        m = re.search(rf"arxiv\.org/(?:abs|pdf)/({ARXIV_ID})", item.get("url") or "", flags=re.I)
        aid = normalize_arxiv(m.group(1)) if m else ""
    if not aid:
        m = re.search(rf"arxiv:\s*({ARXIV_ID})", item.get("extra") or "", flags=re.I)
        aid = normalize_arxiv(m.group(1)) if m else ""
    return doi, aid, (item.get("title") or "").strip()


# --- library reads -----------------------------------------------------------


def search(api: LocalApi, q: str, qmode: str | None, found: dict, searched: list) -> None:
    """Run one search; add top-level candidates (children promoted to parents) to `found`."""
    params = {"q": q}
    if qmode:
        params["qmode"] = qmode
    items = api.get_all(f"{LIB}/items", params)
    hits = 0
    child_parents: list[str] = []
    for item in items:
        if is_top_level(item):
            hits += 1
            found[item["key"]] = {"item": item, "via_child": False}
        elif item["data"].get("parentItem"):
            hits += 1
            child_parents.append(item["data"]["parentItem"])
    for parent_key in child_parents:
        if parent_key in found:
            continue
        parent, _ = api.get(f"{LIB}/items/{parent_key}", allow_404=True)
        if isinstance(parent, dict) and is_top_level(parent):
            found[parent_key] = {"item": parent, "via_child": True}
    searched.append({"q": q, "qmode": qmode or "titleCreatorYear", "hits": hits})


def resolve_cite(api: LocalApi, cite: str) -> str:
    """Citation key -> item key: a q=everything search, then (fallback) a scan of every top-level item."""
    hits, _ = api.get(f"{LIB}/items", {"q": cite, "qmode": "everything", "limit": 50})
    keys = [it["key"] for it in hits if is_top_level(it) and (it.get("data") or {}).get("citationKey") == cite]
    if not keys:
        log(f"citation key {cite!r}: search found nothing, scanning {LIB}/items/top")
        keys = [it["key"] for it in api.get_all(f"{LIB}/items/top") if (it.get("data") or {}).get("citationKey") == cite]
    if not keys:
        raise ApiError("cite_not_found", f"no item carries citationKey {cite!r}",
                       "Check the spelling (case matters) or look the paper up by DOI / title.", exit_code=1, cite=cite)
    if len(keys) > 1:
        raise ApiError("cite_ambiguous", f"{len(keys)} items carry citationKey {cite!r}",
                       "Pass --key with the right one.", exit_code=1, cite=cite, keys=keys)
    return keys[0]


def collection_paths(api: LocalApi) -> dict[str, str]:
    cols = {c["key"]: c["data"] for c in api.get_all(f"{LIB}/collections")}
    paths: dict[str, str] = {}

    def path_of(key: str, seen: tuple = ()) -> str:
        if key in paths:
            return paths[key]
        data = cols.get(key)
        if data is None:
            return key
        parent = data.get("parentCollection")
        name = data.get("name", key)
        if parent and parent not in seen and parent in cols:
            name = path_of(parent, seen + (key,)) + " / " + name
        paths[key] = name
        return name

    for key in cols:
        path_of(key)
    return paths


def attachments_of(api: LocalApi, key: str) -> list[dict]:
    children = api.get(f"{LIB}/items/{key}/children")[0]
    attachments = []
    for child in children if isinstance(children, list) else []:
        cd = child.get("data", {})
        # The local API may answer for a different key; keep only real children.
        if cd.get("parentItem") != key or cd.get("itemType") != "attachment":
            continue
        attachments.append(
            {
                "key": child["key"],
                "contentType": cd.get("contentType"),
                "linkMode": cd.get("linkMode"),
                "filename": cd.get("filename"),
                "md5": cd.get("md5"),
            }
        )
    return attachments


def describe(api: LocalApi, item: dict, paths: dict[str, str]) -> dict:
    data = item["data"]
    key = item["key"]
    attachments = attachments_of(api, key)
    return {
        "key": key,
        "citationKey": data.get("citationKey"),
        "title": data.get("title"),
        "itemType": data.get("itemType"),
        "date": data.get("date"),
        "DOI": data.get("DOI"),
        "url": data.get("url"),
        "archiveID": data.get("archiveID"),
        "numAttachments": len(attachments),
        "attachments": attachments,
        "collections": [paths.get(k, k) for k in data.get("collections") or []],
        "tags": data.get("tags") or [],
        "version": item.get("version"),
    }


def readback(api: LocalApi, item: dict, code: str = "found") -> dict:
    """The record's `found` object: the library facts for one item (collection keys, not paths)."""
    data = item["data"]
    return {
        "code": code,
        "key": item["key"],
        "version": item.get("version"),
        "citationKey": data.get("citationKey") or "",
        "title": data.get("title") or "",
        "collections": list(data.get("collections") or []),
        "tags": list(data.get("tags") or []),
        "attachments": attachments_of(api, item["key"]),
        "checked_at": now_iso(),
    }


# --- lookups -----------------------------------------------------------------


def lookup_doi(api: LocalApi, doi: str) -> tuple[list, list, list]:
    found: dict[str, dict] = {}
    searched: list[dict] = []
    matches, near = [], []
    search(api, doi, "fields", found, searched)
    for entry in found.values():
        data = entry["item"]["data"]
        if matches_doi(data, doi):
            matches.append(entry["item"])
        else:
            near.append((entry["item"], "search hit on the DOI text, but data.DOI differs"
                         + (" (hit was on a child attachment)" if entry["via_child"] else "")))
    return matches, near, searched


def lookup_arxiv(api: LocalApi, aid: str) -> tuple[list, list, list]:
    found: dict[str, dict] = {}
    searched: list[dict] = []
    matches, near = [], []
    search(api, aid, "fields", found, searched)
    for entry in found.values():
        data = entry["item"]["data"]
        if matches_arxiv(data, aid):
            matches.append(entry["item"])
        else:
            near.append((entry["item"], "search hit on the arXiv id, but no identifier field confirms it"
                         + (" (hit was on a child attachment)" if entry["via_child"] else "")))
    return matches, near, searched


def lookup_title(api: LocalApi, title: str) -> tuple[list, list, list]:
    found: dict[str, dict] = {}
    searched: list[dict] = []
    matches, near = [], []
    wanted = normalize_title(title)
    search(api, title, None, found, searched)
    if not found:
        search(api, title, "everything", found, searched)
    for sep in SUBTITLE_SEPARATORS:
        head = title.split(sep, 1)[0].strip()
        if head and head != title and len(head.split()) >= 2:
            search(api, head, None, found, searched)
            break
    for entry in found.values():
        have = normalize_title(entry["item"]["data"].get("title") or "")
        if not have:
            continue
        if have == wanted:
            matches.append(entry["item"])
        elif wanted in have:
            near.append((entry["item"], "library title contains the query title"))
        elif have in wanted:
            near.append((entry["item"], "query title contains the library title"))
    return matches, near, searched


# --- single modes ------------------------------------------------------------


def emit(obj: dict, exit_code: int) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    return exit_code


def run_lookup(args: argparse.Namespace) -> int:
    """v1: --doi / --arxiv / --title."""
    api = LocalApi(args.base_url)
    if args.doi:
        query = {"doi": normalize_doi(args.doi)}
        matches, near, searched = lookup_doi(api, query["doi"])
    elif args.arxiv:
        query = {"arxiv": normalize_arxiv(args.arxiv)}
        matches, near, searched = lookup_arxiv(api, query["arxiv"])
    else:
        title = args.title.strip()
        query = {"title": title}
        if not normalize_title(title):
            return emit({"code": "bad_query", "hint": "The title has no letters or digits to compare."}, 1)
        matches, near, searched = lookup_title(api, title)

    if not matches and not near:
        return emit({"code": "not_found", "query": query, "searched": searched}, 0)

    paths = collection_paths(api)
    if matches:
        return emit(
            {
                "code": "found",
                "query": query,
                "matches": [describe(api, it, paths) for it in matches],
                "near_matches": [{**describe(api, it, paths), "reason": why} for it, why in near],
                "searched": searched,
                "hint": "This paper is already in the library. Do not import it again; report the "
                "key, attachments and collections to the user. If the request is for another "
                "version (preprint vs published), that is the user's call.",
            },
            1,
        )
    return emit(
        {
            "code": "near_match",
            "query": query,
            "near_matches": [{**describe(api, it, paths), "reason": why} for it, why in near],
            "searched": searched,
            "hint": "Not an exact match, but the titles overlap (subtitle, preprint vs published "
            "version, or an ambiguous short title). Compare the near matches with the target "
            "paper and ask the user whether it is the same paper before importing.",
        },
        1,
    )


def run_key(args: argparse.Namespace) -> int:
    """--key / --cite: describe one known item."""
    api = LocalApi(args.base_url)
    query = {"cite": args.cite} if args.cite else {"key": args.key}
    key = resolve_cite(api, args.cite) if args.cite else args.key
    item, _ = api.get(f"{LIB}/items/{key}", allow_404=True)
    if not isinstance(item, dict) or item.get("key") != key:
        return emit({"code": "not_found", "query": query, "key": key,
                     "hint": "No item with that key; look the paper up by DOI or title."}, 1)
    return emit({"code": "found", "query": query, **describe(api, item, collection_paths(api))}, 0)


# --- record stream -----------------------------------------------------------


def read_json_records(text: str, source: str) -> list:
    """Parse JSONL, a JSON array or one object into a list of [record|None, error|None]."""
    text = text.strip()
    if not text:
        return []
    entries: list = []
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        for n, ln in enumerate(text.splitlines(), 1):
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError as e:
                entries.append([None, {"code": "invalid_json", "detail": f"{source} line {n}: {e.msg}"}])
                continue
            entries.append([rec, None] if isinstance(rec, dict) else [None, {"code": "invalid_record", "detail": f"{source} line {n}: not an object"}])
        return entries
    for rec in (obj if isinstance(obj, list) else [obj]):
        entries.append([rec, None] if isinstance(rec, dict) else [None, {"code": "invalid_record", "detail": f"{source}: not an object"}])
    return entries


def load_records(paths: list[str]) -> list[dict]:
    """Entries {path, record, orig, error} from the record files, else from stdin (JSONL / array / object)."""
    entries: list[dict] = []
    if not paths:
        for rec, err in read_json_records(sys.stdin.read(), "stdin"):
            entries.append({"path": None, "record": rec, "orig": None, "error": err})
        return entries
    for raw in paths:
        path = Path(raw)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            entries.append({"path": path, "record": None, "orig": None, "error": {"code": "unreadable", "detail": f"{path}: {e}"}})
            continue
        parsed = read_json_records(text, str(path))
        if len(parsed) != 1 or parsed[0][0] is None:
            err = parsed[0][1] if parsed and parsed[0][1] else {"code": "invalid_record", "detail": f"{path}: expected one JSON object"}
            entries.append({"path": path, "record": None, "orig": None, "error": err})
            continue
        entries.append({"path": path, "record": parsed[0][0], "orig": json.dumps(parsed[0][0], sort_keys=True), "error": None})
    return entries


def write_record(path: Path, record: dict) -> None:
    """Atomic write: temp file in the same directory, then os.replace."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(tmp, 0o666 & ~umask)  # mkstemp gives 0600; behave like an ordinary file write
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_results(results: list, in_place: bool) -> int:
    """results: [(entry, summary, outcome)], outcome ok|skipped|failed.

    -i: changed records are written back to their files; stdout gets one summary line per record and the
    final {"summary"} line. Otherwise stdout gets the full records as JSONL and the summary goes to stderr.
    Returns the exit status: 1 when anything failed."""
    counts = {"total": len(results), "ok": 0, "skipped": 0, "failed": 0}
    for entry, summary, outcome in results:
        counts[outcome] += 1
        record = entry["record"]
        if in_place:
            if record is not None and entry["path"] and json.dumps(record, sort_keys=True) != entry["orig"]:
                write_record(entry["path"], record)
            print(json.dumps(summary, ensure_ascii=False))
        else:
            print(json.dumps(record if record is not None else summary, ensure_ascii=False))
    print(json.dumps({"summary": counts}, ensure_ascii=False), file=sys.stdout if in_place else sys.stderr)
    return 1 if counts["failed"] else 0


def process_record(api: LocalApi, rec: dict, slug: str, do_readback: bool) -> tuple[dict, str]:
    """Update one record; returns (summary line, outcome ok|skipped|failed)."""
    key = (rec.get("saved") or {}).get("key") or (rec.get("found") or {}).get("key")
    if key and do_readback:
        item, _ = api.get(f"{LIB}/items/{key}", allow_404=True)
        if not isinstance(item, dict) or item.get("key") != key:
            rec.pop("found", None)
            rec["blocker"] = f"missing_in_library: item {key} is no longer in the library ({now_iso()}); recreate it or fix saved/found"
            return {"slug": slug, "code": "missing_in_library", "key": key}, "failed"
        rec["found"] = readback(api, item)
        cite = item["data"].get("citationKey") or ""
        if cite:
            if rec.get("citationKey") and rec["citationKey"] != cite:
                print(f"{slug}: citationKey in the library is {cite!r}; the record keeps the given {rec['citationKey']!r} "
                      f"(found.citationKey has the library's)", file=sys.stderr)
            else:
                rec["citationKey"] = cite
        return {"slug": slug, "code": "found", "key": key, "citationKey": cite, "version": item.get("version"),
                "attachments": len(rec["found"]["attachments"])}, "ok"
    if key:
        return {"slug": slug, "code": "skipped", "reason": "already in the library (saved / found); use --readback to refresh", "key": key}, "skipped"

    item = rec.get("item")
    if not isinstance(item, dict) or not item:
        return {"slug": slug, "code": "no_item", "hint": "The record has no `item` to search with; run doi_to_item.py first."}, "failed"
    doi, aid, title = identifiers_of(item)
    matches: list = []
    near: list = []
    searched: list = []
    if doi:
        matches, _, s = lookup_doi(api, doi)
        searched += s
    if not matches and aid:
        matches, _, s = lookup_arxiv(api, aid)
        searched += s
    if not matches and normalize_title(title):
        matches, near, s = lookup_title(api, title)
        searched += s
    if not searched:
        return {"slug": slug, "code": "no_item", "hint": "The item has no DOI, arXiv id or title to search with."}, "failed"
    if matches:
        rec["found"] = readback(api, matches[0])
        if len(matches) > 1:
            rec["found"]["duplicates"] = [it["key"] for it in matches[1:]]
        return {"slug": slug, "code": "found", "key": rec["found"]["key"], "citationKey": rec["found"]["citationKey"],
                "title": rec["found"]["title"][:80], "attachments": len(rec["found"]["attachments"])}, "ok"
    if near:
        it, why = near[0]
        rec["found"] = readback(api, it, code="near_match")
        rec["found"]["reason"] = why
        if len(near) > 1:
            rec["found"]["candidates"] = [{"key": o["key"], "title": o["data"].get("title"), "reason": w} for o, w in near[1:]]
        return {"slug": slug, "code": "near_match", "key": it["key"], "title": (it["data"].get("title") or "")[:80], "reason": why,
                "hint": "Compare with the target paper; delete `found` from the record if it is a different paper."}, "ok"
    return {"slug": slug, "code": "not_found", "searched": searched}, "ok"


def run_stream(args: argparse.Namespace) -> int:
    entries = load_records(args.records)
    if not entries:
        return emit({"code": "no_records", "hint": "Pass record files or feed records on stdin."}, 1)
    api = LocalApi(args.base_url)
    results = []
    for entry in entries:
        rec = entry["record"]
        if entry["error"]:
            stem = entry["path"].stem if entry["path"] else "stdin"
            results.append((entry, {"slug": stem, **entry["error"]}, "failed"))
            continue
        slug = rec.get("slug") or (entry["path"].stem if entry["path"] else "")
        results.append((entry, *process_record(api, rec, slug, args.readback)))
    return write_results(results, args.in_place)


# --- main --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    global VERBOSE
    parser = argparse.ArgumentParser(
        description="Check whether a paper is already in the Zotero library, describe one item, or refresh "
        "records from the library (read-only, local API). Single lookups print one JSON object: "
        "code not_found (exit 0), found / near_match (exit 1); --key / --cite: found (exit 0), not_found (exit 1); "
        "zotero_unreachable / local_api_disabled / api_error (exit 2).",
        epilog="Examples:\n"
        "  uv run find_in_library.py --doi 10.1109/TMI.2024.3375871\n"
        "  uv run find_in_library.py --arxiv 2006.11239v2\n"
        '  uv run find_in_library.py --title "Denoising Diffusion Probabilistic Models"\n'
        "  uv run find_in_library.py --cite liuProgressiveResidualLearning2022\n"
        "  uv run find_in_library.py -i records/*.json            # dedupe by DOI / arXiv / title -> found\n"
        "  uv run find_in_library.py -i --readback records/*.json # refresh found from saved.key / found.key",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    what = parser.add_mutually_exclusive_group()
    what.add_argument("--doi", help="DOI (with or without doi: prefix or https://doi.org/)")
    what.add_argument("--arxiv", help="arXiv id such as 2006.11239 or 2006.11239v2 (version ignored)")
    what.add_argument("--title", help="paper title; compared after Unicode normalization")
    what.add_argument("--key", metavar="KEY", help="describe the item with this key")
    what.add_argument("--cite", metavar="CITE", help="describe the item with this citation key")
    parser.add_argument("records", nargs="*", metavar="RECORD", help="stream mode: record files; none = read records from stdin")
    parser.add_argument("-i", "--in-place", action="store_true", help="write each record back to its file; stdout gets one summary line per record")
    parser.add_argument("--readback", action="store_true", help="stream mode: refresh `found` of records that have saved.key / found.key")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"local API base URL (default {DEFAULT_BASE_URL})")
    parser.add_argument("-v", "--verbose", action="store_true", help="log each request to stderr")
    args = parser.parse_args(argv)
    VERBOSE = args.verbose
    single = any((args.doi, args.arxiv, args.title, args.key, args.cite))
    if single and (args.records or args.in_place or args.readback):
        parser.error("--doi / --arxiv / --title / --key / --cite are single lookups; record paths, -i and --readback belong to the stream mode")
    if args.in_place and not args.records:
        parser.error("-i needs record paths (stdin input cannot be written back)")
    try:
        if args.key or args.cite:
            return run_key(args)
        if single:
            return run_lookup(args)
        return run_stream(args)
    except ApiError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        return emit({"code": e.code, "detail": e.detail, "hint": e.hint, **e.extra}, e.exit_code)


if __name__ == "__main__":
    sys.exit(main())
