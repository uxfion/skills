# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check existing Zotero items for problems worth tidying, read-only: duplicates, stray webpages, extra PDFs, bad fields.

The whole library is read once (GET /items, every page: items, attachments and notes; trashed ones dropped), so
duplicates are found across the library whatever the scope. The scope only chooses which items are reported:
--collection KEY (--recursive takes its subcollections too), --key / --cite, or nothing for every top-level item.

Problem codes (each problem is {"code", ...}):
  duplicate_of            other items with the same DOI or arXiv id ({"keys", "by": doi | arxiv}), or the same
                          title ({"by": "title"}: a near match, maybe a preprint/published pair - "pair" says so)
  unfiled_webpage         a webpage item in no collection
  multiple_pdfs           more than one PDF attachment ({"attachments": [{key, title, md5}]})
  date_unparseable        a date Zotero cannot parse (no meta.parsedDate), e.g. "十一月 23, 2021"
  abbreviation_misplaced  journalAbbreviation longer than publicationTitle (they are swapped: "patch" swaps them
                          back), or publicationTitle looks abbreviated with no journalAbbreviation
  missing_doi             a journal article or conference paper without a DOI (venues that issue none - ICML,
                          ICLR - are expected here: their official page is the url); --crossref adds a "candidate"
                          from a Crossref title search (similarity >= 0.9 and the first author's surname)
  missing_abstract        a research item with no abstract
  no_identifier           no DOI, no arXiv id and no url: nothing locates the paper
  name_not_tagged         the abstract names a model or system ("we propose EchoWDiff") that no tag carries
                          ({"name"}: a bare tag, or dataset/ for a benchmark - the agent decides)

stdout: one JSON line per reported item with problems {key, citationKey, title, itemType, collections, problems},
then {"summary": {items, with_problems, by_code}}. "patch" appears only where the fix is mechanical; it is a
fields object for one item: write it to a file for `update_item.py --key KEY --patch FILE`. Every other problem is
the agent's to judge and the user's to confirm. Exit 0 = no problems, 1 = problems listed, 2 = cannot check.
"""

import argparse
import difflib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
LIB = "/api/users/0"
PAGE_SIZE = 100
TIMEOUT = 30
CHILD_TYPES = {"attachment", "note", "annotation"}
RESEARCH_TYPES = {"journalArticle", "conferencePaper", "preprint", "bookSection", "thesis", "report"}
DOI_TYPES = {"journalArticle", "conferencePaper"}
ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})"
# "we propose EchoWDiff", "Here we present AMIFound", "an approach, PromptIR, for": a capitalised token with a
# second capital or a digit, so ordinary words ("We propose Deep ...") stay out, and not followed by another
# capitalised word, which makes it the start of a phrase ("We propose Weight-Decomposed Low-Rank Adaptation").
NAME = r"([A-Z][\w^+\-]*[A-Z0-9][\w^+\-]*)(?![\w^+\-])(?!\s+[A-Z][a-z])"
NAME_PATTERNS = (re.compile(r"\b[Ww]e\s+(?:propose|present|introduce|develop|name|call)\s+(?:it\s+)?" + NAME),
                 re.compile(r"\b(?:approach|framework|model|method|system|network|pipeline|agent),\s+" + NAME + r","))
CROSSREF = "https://api.crossref.org/works"
USER_AGENT = "paper-to-zotero lint_items (mailto:none)"


class Stop(Exception):
    def __init__(self, code, hint, **extra):
        super().__init__(code)
        self.code, self.hint, self.extra = code, hint, extra


def get(base, path, params=None):
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise Stop("local_api_disabled", "turn on Zotero's local API (Settings > Advanced)")
        raise Stop("api_error", f"GET {path} -> {e.code}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise Stop("zotero_unreachable", f"Zotero does not answer at {base}: start it and rerun", detail=str(e))


def get_all(base, path):
    out, start = [], 0
    while True:
        page = get(base, path, {"limit": PAGE_SIZE, "start": start})
        if not isinstance(page, list):
            return out
        out.extend(page)
        if len(page) < PAGE_SIZE:
            return out
        start += PAGE_SIZE


def norm_title(s):
    return "".join(ch for ch in unicodedata.normalize("NFKC", s or "").casefold() if ch.isalnum())


def identifiers(data):
    """(doi, arXiv id) of an item, '' when absent; an arXiv DOI counts as the arXiv id."""
    doi = (data.get("DOI") or "").strip().lower()
    if not doi:
        m = re.search(r"(?mi)^\s*DOI:\s*(\S+)", data.get("extra") or "")
        doi = m.group(1).lower() if m else ""
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi)
    aid = ""
    m = re.fullmatch(r"10\.48550/arxiv\.(.+)", doi)
    if m:
        aid, doi = m.group(1), ""
    for source in (data.get("archiveID") or "", data.get("url") or "", data.get("extra") or ""):
        if aid:
            break
        m = re.search(rf"(?:arxiv:\s*|arxiv\.org/(?:abs|pdf)/)({ARXIV_ID})", source, flags=re.I)
        aid = m.group(1) if m else ""
    return doi, re.sub(r"v\d+$", "", aid.lower())


def looks_abbreviated(title):
    words = title.split()
    return len(words) >= 2 and sum(w.endswith(".") for w in words) >= 2


def names_in(abstract):
    seen = []
    for pattern in NAME_PATTERNS:
        for m in pattern.finditer(abstract or ""):
            name = m.group(1).rstrip("-")
            if len(name) >= 3 and name not in seen:
                seen.append(name)
    return seen


class Crossref:
    def __init__(self):
        self.last, self.stopped = 0.0, False

    def candidate(self, data):
        if self.stopped or not data.get("title"):
            return None
        wait = self.last + 1.0 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        first = next((c.get("lastName") or c.get("name") or "" for c in data.get("creators") or []), "")
        params = {"query.bibliographic": f"{data['title']} {first}".strip(), "rows": 3,
                  "select": "DOI,title,container-title,issued,author"}
        req = urllib.request.Request(CROSSREF + "?" + urllib.parse.urlencode(params), headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                items = json.loads(r.read().decode("utf-8")).get("message", {}).get("items") or []
        except urllib.error.HTTPError as e:
            if e.code == 429:
                self.stopped = True
            return None
        except (urllib.error.URLError, OSError, ValueError):
            return None
        want = norm_title(data["title"])
        for it in items:
            title = (it.get("title") or [""])[0]
            surnames = {norm_title(a.get("family")) for a in it.get("author") or []}
            if difflib.SequenceMatcher(None, want, norm_title(title)).ratio() >= 0.9 and \
                    (not first or norm_title(first) in surnames):
                return {"doi": it.get("DOI"), "title": title, "venue": (it.get("container-title") or [""])[0],
                        "year": ((it.get("issued") or {}).get("date-parts") or [[None]])[0][0]}
        return None


def problems_of(item, children, index, crossref):
    data, meta = item["data"], item.get("meta") or {}
    out = []
    doi, aid = identifiers(data)
    others = set()
    for by, value in (("doi", doi), ("arxiv", aid)):
        keys = sorted(k for k in index[by].get(value, ()) if k != item["key"]) if value else []
        if keys:
            others.update(keys)
            out.append({"code": "duplicate_of", "by": by, "keys": keys})
    title_keys = sorted(k for k in index["title"].get(norm_title(data.get("title")), ())
                        if k != item["key"] and k not in others) if len(norm_title(data.get("title"))) >= 12 else []
    if title_keys:
        types = {index["types"][k] for k in title_keys} | {data.get("itemType")}
        out.append({"code": "duplicate_of", "by": "title", "keys": title_keys,
                    **({"pair": "preprint/published"} if "preprint" in types and len(types) > 1 else {})})
    if data.get("itemType") == "webpage" and not data.get("collections"):
        out.append({"code": "unfiled_webpage", "url": data.get("url")})
    pdfs = [c for c in children if c["data"].get("itemType") == "attachment"
            and c["data"].get("contentType") == "application/pdf"]
    if len(pdfs) > 1:
        out.append({"code": "multiple_pdfs", "attachments": [{"key": c["key"], "title": c["data"].get("title"),
                                                              "md5": c["data"].get("md5")} for c in pdfs]})
    if (data.get("date") or "").strip() and not meta.get("parsedDate"):
        out.append({"code": "date_unparseable", "date": data["date"]})
    full, abbr = (data.get("publicationTitle") or "").strip(), (data.get("journalAbbreviation") or "").strip()
    if full and abbr and len(abbr) > len(full):
        out.append({"code": "abbreviation_misplaced", "publicationTitle": full, "journalAbbreviation": abbr,
                    "patch": {"publicationTitle": abbr, "journalAbbreviation": full}})
    elif full and not abbr and "journalAbbreviation" in data and looks_abbreviated(full):
        out.append({"code": "abbreviation_misplaced", "publicationTitle": full,
                    "hint": "publicationTitle looks abbreviated: move it to journalAbbreviation, find the full title"})
    if data.get("itemType") in DOI_TYPES and not doi:
        problem = {"code": "missing_doi", "url": data.get("url") or None}
        cand = crossref.candidate(data) if crossref else None
        out.append({**problem, **({"candidate": cand} if cand else {})})
    if data.get("itemType") in RESEARCH_TYPES and not (data.get("abstractNote") or "").strip():
        out.append({"code": "missing_abstract"})
    if not doi and not aid and not (data.get("url") or "").strip() and data.get("itemType") in RESEARCH_TYPES:
        out.append({"code": "no_identifier"})
    tags = {t.get("tag", "") for t in data.get("tags") or []}
    for name in names_in(data.get("abstractNote")):
        if not any(t == name or t.endswith("/" + name) for t in tags):
            out.append({"code": "name_not_tagged", "name": name})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], epilog="\n".join(__doc__.splitlines()[2:]),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--collection", metavar="KEY", help="report the items of this collection")
    ap.add_argument("--recursive", action="store_true", help="with --collection: its subcollections too")
    ap.add_argument("--key", nargs="+", default=[], metavar="ITEMKEY", help="report these items")
    ap.add_argument("--cite", nargs="+", default=[], metavar="CITEKEY", help="report the items with these citation keys")
    ap.add_argument("--only", metavar="CODES", help="comma-separated problem codes to report (default: all)")
    ap.add_argument("--crossref", action="store_true",
                    help="look up a DOI candidate on Crossref for each missing_doi (network, 1 s apart; main conversation)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"local API base URL (default: {DEFAULT_BASE_URL})")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    try:
        rows = [r for r in get_all(base, f"{LIB}/items") if isinstance(r, dict) and not (r.get("data") or {}).get("deleted")]
        cols = {c["key"]: c["data"] for c in get_all(base, f"{LIB}/collections")}
    except Stop as e:
        print(json.dumps({"code": e.code, "hint": e.hint, **e.extra}, ensure_ascii=False))
        sys.exit(2)

    def path_of(key, depth=0):
        d = cols.get(key)
        if not d:
            return key
        parent = d.get("parentCollection")
        return (path_of(parent, depth + 1) + " / " if parent and parent in cols and depth < 20 else "") + d.get("name", key)

    top = [r for r in rows if r["data"].get("itemType") not in CHILD_TYPES and not r["data"].get("parentItem")]
    children = {}
    for r in rows:
        if r["data"].get("parentItem"):
            children.setdefault(r["data"]["parentItem"], []).append(r)
    index = {"doi": {}, "arxiv": {}, "title": {}, "types": {}}
    for r in top:
        doi, aid = identifiers(r["data"])
        for by, value in (("doi", doi), ("arxiv", aid), ("title", norm_title(r["data"].get("title")))):
            if value:
                index[by].setdefault(value, set()).add(r["key"])
        index["types"][r["key"]] = r["data"].get("itemType")

    scope = top
    if args.collection:
        if args.collection not in cols:
            print(json.dumps({"code": "collection_not_found", "collection": args.collection}))
            sys.exit(2)
        wanted = {args.collection}
        if args.recursive:
            grew = True
            while grew:
                more = {k for k, d in cols.items() if d.get("parentCollection") in wanted} - wanted
                wanted |= more
                grew = bool(more)
        scope = [r for r in scope if wanted & set(r["data"].get("collections") or [])]
    if args.key or args.cite:
        scope = [r for r in scope if r["key"] in args.key or r["data"].get("citationKey") in args.cite]
    only = set(args.only.split(",")) if args.only else None
    crossref = Crossref() if args.crossref else None
    counts, reported = {}, 0
    for r in scope:
        found = [p for p in problems_of(r, children.get(r["key"], []), index, crossref) if not only or p["code"] in only]
        if not found:
            continue
        reported += 1
        for p in found:
            counts[p["code"]] = counts.get(p["code"], 0) + 1
        d = r["data"]
        print(json.dumps({"key": r["key"], "citationKey": d.get("citationKey") or None, "title": d.get("title"),
                          "itemType": d.get("itemType"), "collections": [path_of(c) for c in d.get("collections") or []],
                          "problems": found}, ensure_ascii=False))
    summary = {"items": len(scope), "with_problems": reported, "by_code": dict(sorted(counts.items()))}
    if crossref and crossref.stopped:
        summary["crossref"] = "stopped after a 429"
    print(json.dumps({"summary": summary}, ensure_ascii=False))
    sys.exit(1 if reported else 0)


if __name__ == "__main__":
    main()
