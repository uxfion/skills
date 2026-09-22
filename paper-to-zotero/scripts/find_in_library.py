# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Is this paper already in the Zotero library? Read-only, local API.

Looks one paper up by DOI, arXiv id or title through Zotero's local web API
(GET only), confirms every candidate exactly, and reports what the library
holds for it: key, title, item type, identifiers, attachment count,
collection paths and tags.

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

Exit codes: 0 = not found (safe to import); 1 = found or near match (the
agent decides); 2 = cannot check (Zotero unreachable, local API disabled,
API error).

Retirement condition: delete this script once the ``zotero`` skill's
``search`` can query by identifier (qmode=fields) and reports attachment
count and collection paths.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
PAGE_SIZE = 100
TIMEOUT = 15
CHILD_TYPES = {"attachment", "note", "annotation"}
SUBTITLE_SEPARATORS = (": ", " - ", " – ", " — ")

VERBOSE = False


def log(msg: str) -> None:
    if VERBOSE:
        print(msg, file=sys.stderr)


class ApiError(Exception):
    """Carries the output code and detail for exit status 2."""

    def __init__(self, code: str, detail: str, hint: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.hint = hint


class LocalApi:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        # Bypass any proxy from the environment; the API is on localhost.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(self, path: str, params: dict | None = None):
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


# --- library reads -----------------------------------------------------------


def search(api: LocalApi, q: str, qmode: str | None, found: dict, searched: list) -> None:
    """Run one search; add top-level candidates (children promoted to parents) to `found`."""
    params = {"q": q}
    if qmode:
        params["qmode"] = qmode
    items = api.get_all("/api/users/0/items", params)
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
        parent, _ = api.get(f"/api/users/0/items/{parent_key}")
        if isinstance(parent, dict) and is_top_level(parent):
            found[parent_key] = {"item": parent, "via_child": True}
    searched.append({"q": q, "qmode": qmode or "titleCreatorYear", "hits": hits})


def collection_paths(api: LocalApi) -> dict[str, str]:
    cols = {c["key"]: c["data"] for c in api.get_all("/api/users/0/collections")}
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


def describe(api: LocalApi, item: dict, paths: dict[str, str]) -> dict:
    data = item["data"]
    key = item["key"]
    children = api.get(f"/api/users/0/items/{key}/children")[0]
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
            }
        )
    return {
        "key": key,
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


# --- main --------------------------------------------------------------------


def emit(obj: dict, exit_code: int) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    return exit_code


def run(args: argparse.Namespace) -> int:
    api = LocalApi(args.base_url)
    found: dict[str, dict] = {}
    searched: list[dict] = []
    matches: list[dict] = []
    near: list[dict] = []

    if args.doi:
        query = {"doi": normalize_doi(args.doi)}
        search(api, query["doi"], "fields", found, searched)
        for entry in found.values():
            data = entry["item"]["data"]
            if matches_doi(data, query["doi"]):
                matches.append(entry["item"])
            else:
                near.append((entry["item"], "search hit on the DOI text, but data.DOI differs"
                             + (" (hit was on a child attachment)" if entry["via_child"] else "")))
    elif args.arxiv:
        query = {"arxiv": normalize_arxiv(args.arxiv)}
        search(api, query["arxiv"], "fields", found, searched)
        for entry in found.values():
            data = entry["item"]["data"]
            if matches_arxiv(data, query["arxiv"]):
                matches.append(entry["item"])
            else:
                near.append((entry["item"], "search hit on the arXiv id, but no identifier field confirms it"
                             + (" (hit was on a child attachment)" if entry["via_child"] else "")))
    else:
        title = args.title.strip()
        query = {"title": title}
        wanted = normalize_title(title)
        if not wanted:
            return emit({"code": "bad_query", "hint": "The title has no letters or digits to compare."}, 1)
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


def main(argv: list[str] | None = None) -> int:
    global VERBOSE
    parser = argparse.ArgumentParser(
        description="Check whether a paper is already in the Zotero library (read-only, local API). "
        "Prints one JSON object: code not_found (exit 0), found / near_match (exit 1), "
        "zotero_unreachable / local_api_disabled / api_error (exit 2).",
        epilog="Examples:\n"
        "  uv run find_in_library.py --doi 10.1109/TMI.2024.3375871\n"
        "  uv run find_in_library.py --arxiv 2006.11239v2\n"
        '  uv run find_in_library.py --title "Denoising Diffusion Probabilistic Models"',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--doi", help="DOI (with or without doi: prefix or https://doi.org/)")
    what.add_argument("--arxiv", help="arXiv id such as 2006.11239 or 2006.11239v2 (version ignored)")
    what.add_argument("--title", help="paper title; compared after Unicode normalization")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"local API base URL (default {DEFAULT_BASE_URL})")
    parser.add_argument("-v", "--verbose", action="store_true", help="log each request to stderr")
    args = parser.parse_args(argv)
    VERBOSE = args.verbose
    try:
        return run(args)
    except ApiError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        return emit({"code": e.code, "detail": e.detail, "hint": e.hint}, 2)


if __name__ == "__main__":
    sys.exit(main())
