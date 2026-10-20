#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Resolve DOIs or arXiv ids into Zotero item drafts, one record per identifier.

Fetches the CSL JSON record from doi.org (content negotiation) and maps it
onto a Zotero item using the live Zotero schema (GET /api/schema: csl.types,
csl.fields, csl.names) plus a small built-in table for Crossref's own type
vocabulary.

Single mode (v1): `--doi ID --out item.json` writes the draft and prints one
report object. Stream mode: identifiers from repeated --doi, an --ids list
(`identifier[<TAB>citation key]` per line), a --bib file, existing record
files (their `item` is filled) or stdin (either identifier lines or records
as JSONL / an array / one object) each become a record {slug, id,
citationKey?, item, tags?, warnings?}. --out-dir writes DIR/<slug>.json and prints one summary
line per record (a record already there for the same identifier is skipped,
never overwritten); -i writes record files back in place; otherwise the
full records go to stdout as JSONL and the summary to stderr. A failed
identifier yields a record with slug, id and `code` and does not stop the
others. Exit 0 = every record ok or skipped, 1 = some failed, 2 = Zotero
unreachable / local API disabled.

Drafting rules beyond the plain field mapping:
- A CSL `subtitle` is appended to the title ("Title: Subtitle") unless the
  title already ends with it.
- An arXiv record (DataCite CSL) carries `categories`; "FOS: ..." entries and
  repeats are dropped and the rest become automatic (type 1) tags in the form
  Zotero's arXiv translator writes: "Machine Learning (cs.LG)" -> "Computer
  Science - Machine Learning", "Quantum Physics (quant-ph)" -> "Quantum
  Physics"; an archive outside the translator's table keeps the DataCite
  string. They go to the record's `tags` only when it has none yet (v1
  mode: the item's `tags`). No other tags are written: Crossref `subject` is
  a journal category, not author keywords.
- A book-chapter with an ISSN (doi.org collapses an LNCS-style
  container-title to the series name) triggers one GET to
  api.crossref.org/works/<DOI>: when its container-title is [known
  proceedings series, volume title], the draft becomes a conferencePaper with
  proceedingsTitle = the volume title and series = the series; otherwise, or
  when Crossref cannot be read, it stays a bookSection with a warning.
- `warnings` flag a possible erratum / correction / retraction notice: the
  title starts with Correction / Erratum / Corrigendum / Retraction (also
  "Author Correction", "RETRACTED"); an article with no authors; or a single
  page that is not an article number (equal to `article-number`, or 5+
  digits such as e0360436).

Published versions of preprints (stream mode; never in v1 mode, and never a
change to the item, B#4): a record drafted from an arXiv id gets
`published_candidates` = [{doi, venue, year, title, url, source, sources?,
title_differs, type?, journal_ref?, redraft}], one entry per published version,
from
- arXiv: the API's journal_ref / doi (one call per 100 ids); a DOI arXiv lists
  is completed from its Crossref record, a journal_ref alone is a DOI-less entry;
- Crossref: a title (+ first author) search; arXiv DOIs and posted-content
  left out, title similarity (difflib on the normalized title) >= 0.9.
The same DOI from both is one entry. `title_differs` compares with the
preprint's title and alt_titles; `redraft` is the argument for --redraft. The
summary line carries the arXiv comment ("Accepted at ...") and any source
that failed; a failing source never fails the record. What neither finds (the
venues without DOIs: ICLR, ICML, TMLR...) the agent looks up on papers.cool.
--candidates does the same for records that already have a preprint item.

--redraft <DOI | page URL> RECORD [-i] replaces the record's item in place by
the published version: slug, citationKey, tags, collection and everything
else stay; `extra` gains `arXiv: <id>`; the old title goes to alt_titles when
the titles differ; found, checks, links, published_candidates and pdf are
cleared (they described the preprint). DOI form: drafted from the DOI as
usual. Page form (NeurIPS, ICLR, PMLR, ACL Anthology, ... pages): the page's
citation_* meta tags, read over plain HTTP, give a conferencePaper
(citation_conference_title, or a journal title naming proceedings, as NeurIPS
pages have it) or a journalArticle (citation_journal_title, TMLR too); the preprint's creators and abstract fill what the page lacks, and
its citation_pdf_url becomes the record's one `links` entry. A record already
in Zotero (saved / attach) is refused.

Requests are paced per host inside this process (the bulk lookups run in one
process, in the main conversation); an HTTP 429 stops that source for the rest
of the run (`source_blocked`).

Only GET requests. Remote services go through the normal proxy settings
(env DOI_BASE_URL, CROSSREF_BASE_URL, ARXIV_API_URL override the endpoints,
for tests); the Zotero local API bypasses the proxy.
"""

import argparse
import difflib
import html
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
DOI_BASE_URL = os.environ.get("DOI_BASE_URL", "https://doi.org").rstrip("/")
CROSSREF_BASE_URL = os.environ.get("CROSSREF_BASE_URL", "https://api.crossref.org").rstrip("/")
ARXIV_API_URL = os.environ.get("ARXIV_API_URL", "https://export.arxiv.org/api/query")
CSL_ACCEPT = "application/vnd.citationstyles.csl+json"
USER_AGENT = "paper-to-zotero/doi_to_item (stdlib urllib)"
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# Pacing keys: the real services' hosts, also when a test points the base URLs elsewhere.
HOST_DOI, HOST_CROSSREF, HOST_ARXIV_API = "doi.org", "api.crossref.org", "export.arxiv.org"

# published_candidates: a Crossref title counts from this similarity on.
CANDIDATE_SIMILARITY = 0.9
# NeurIPS 2022-2025 DOIs, registered for the printed proceedings: they lead to its sales page, not to the paper, so
# the item's url is the paper's page at the venue (SKILL.md step 2).
SALES_PAGE_DOI = re.compile(r"^10\.52202/", re.I)
# A citation_journal_title that names proceedings, not a journal (NeurIPS pages give theirs as a journal title).
# A living list: add a form when a real page shows one.
PROCEEDINGS_TITLE = re.compile(r"\b(?:proceedings|conference|symposium|workshop)\b"
                               r"|^advances in neural information processing systems\b", re.I)
# Fields that describe the preprint and go when --redraft swaps in the published version.
REDRAFT_CLEARS = ("found", "checks", "links", "published_candidates", "pdf")

# Book series whose volumes are conference proceedings, as Crossref names them: a chapter in one of them is a
# conference paper. A starting list - add a series when one shows up.
PROCEEDINGS_SERIES = (
    "Lecture Notes in Computer Science",
    "Lecture Notes in Artificial Intelligence",
    "Lecture Notes in Bioinformatics",
    "Communications in Computer and Information Science",
    "Lecture Notes of the Institute for Computer Sciences, Social Informatics and Telecommunications Engineering",
    "IFIP Advances in Information and Communication Technology",
    "Lecture Notes in Business Information Processing",
    "Lecture Notes in Networks and Systems",
    "Lecture Notes in Electrical Engineering",
    "Advances in Intelligent Systems and Computing",
)

# arXiv archives that Zotero's arXiv translator writes as "<Archive> - <Category>"; a category without a
# subject class (quant-ph, hep-th, gr-qc, ...) is written as its name alone.
ARXIV_ARCHIVES = {
    "cs": "Computer Science",
    "econ": "Economics",
    "eess": "Electrical Engineering and Systems Science",
    "math": "Mathematics",
    "nlin": "Nonlinear Sciences",
    "physics": "Physics",
    "q-bio": "Quantitative Biology",
    "q-fin": "Quantitative Finance",
    "stat": "Statistics",
    "astro-ph": "Astrophysics",
    "cond-mat": "Condensed Matter",
}
ARXIV_CATEGORY = re.compile(r"(.+?)\s*\(([a-z][a-z-]*)(?:\.([A-Za-z][A-Za-z-]*))?\)")

ERRATUM_TITLE = re.compile(r"(?:(?:author|publisher)\s+)?(?:corrections?|errat(?:um|a)|corrigend(?:um|a)|retract(?:ion|ed))\b", re.I)
# Item types where a one-page notice can pass for the paper; titles are checked for every type.
ERRATUM_TYPES = {"journalArticle", "conferencePaper", "bookSection"}

# Crossref type vocabulary -> Zotero itemType (Crossref does not use CSL types).
CROSSREF_TYPES = {
    "journal-article": "journalArticle",
    "proceedings-article": "conferencePaper",
    "book-chapter": "bookSection",
    "book-part": "bookSection",
    "book-section": "bookSection",
    "posted-content": "preprint",
    "book": "book",
    "monograph": "book",
    "edited-book": "book",
    "reference-book": "book",
    "dataset": "dataset",
    "report": "report",
    "report-component": "report",
    "dissertation": "thesis",
    "reference-entry": "encyclopediaArticle",
    "standard": "standard",
}
# Crossref-only keys that Zotero would also read; CSL proper uses `event-title`.
EVENT_KEYS = ("event-title", "event")
DATE_FALLBACKS = ("published", "published-online", "published-print", "created")

EPILOG = """\
codes (stdout `code`, exit status):
  ok                   0  draft written
  unknown_type         1  CSL/Crossref type not in the map; draft written as journalArticle
  not_found            1  doi.org returned 404
  no_csl_record        1  doi.org answered but not with CSL JSON (HTML page, 406, bad JSON)
  invalid_identifier   1  input is neither a DOI nor an arXiv id
  doi_org_unreachable  2  network error, timeout or 5xx from doi.org
  source_blocked       2  doi.org answered 429 earlier in this run; rerun later
  zotero_unreachable   2  Zotero local API not answering (Zotero not running?)
  local_api_disabled   2  Zotero answered 403: local API is switched off
  no_identifier        1  (stream) a --bib entry without DOI / arXiv id; id = its title
  no_records           1  (stream) nothing to do
  skipped              -  (stream summary) reason exists | has_item | has_candidates | duplicate
  --redraft:
  already_saved          1  the record has saved / attach: the item is in Zotero already, change it there
  not_published          1  a 10.48550 DOI is the preprint itself
  page_unreachable       1  the page refuses plain HTTP (read it in the browser, fill the item by hand)
  no_citation_meta       1  the page has no citation_title meta tag
  skipped (same_doi)     0  the item already carries that DOI

published_candidates (stream mode, arXiv ids; --no-candidates skips, --candidates adds them to drafted records):
  [{doi, venue, year, title, url, source, sources?, title_differs, type?, journal_ref?, redraft}]
  from arXiv journal_ref / doi and a Crossref title search (>= 0.9); never edits the item; the rest: papers.cool
--redraft <DOI | page URL> RECORD [-i]:
  item <- published version; keeps slug, citationKey, tags, collection; extra += "arXiv: <id>"; old title -> alt_titles;
  clears found, checks, links, published_candidates, pdf; page form: citation_* meta -> conferencePaper /
  journalArticle, citation_pdf_url -> links

input forms accepted by --doi:
  10.1109/CVPR.2016.90   doi:10.1109/CVPR.2016.90   https://doi.org/10.1109/CVPR.2016.90
  2006.11239   2006.11239v2   arXiv:2006.11239   https://arxiv.org/abs/2006.11239

beyond the field mapping (details in the module docstring):
  subtitle      CSL subtitle appended: "Title: Subtitle"
  arXiv         categories -> type 1 tags ("Computer Science - Machine Learning") when the record has no tags
  LNCS & co.    book-chapter with an ISSN -> one Crossref call; known proceedings series -> conferencePaper
                (proceedingsTitle = volume title, series = series name); else bookSection + warning
  warnings      possible erratum / correction / retraction notice (title, no authors, single page)
env: DOI_BASE_URL, CROSSREF_BASE_URL, ARXIV_API_URL (endpoints, for tests)
"""


class Failure(Exception):
    def __init__(self, code, exit_code, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit_code, self.hint, self.extra = code, exit_code, hint, extra


class Blocked(Exception):
    """A host that answered HTTP 429 in this run: it is not asked again until the process ends."""

    def __init__(self, host, block):
        super().__init__(host)
        self.host, self.block = host, block

    def fields(self):
        return {"code": "source_blocked", "host": self.host, "reason": self.block.get("reason"),
                **({"retry_after": self.block["retry_after"]} if self.block.get("retry_after") else {})}


def log(msg):
    print(msg, file=sys.stderr)


# Pacing, per process: the bulk lookups run in one process in the main conversation (spec §4.4), so a minimum gap
# per host is enough; a host that answers 429 is not asked again in this run.
PACE_INTERVALS = {HOST_ARXIV_API: 3.0, HOST_CROSSREF: 1.0, HOST_DOI: 0.5}
PACE_DEFAULT = 1.0
LAST_CALL, STOPPED = {}, {}


def retry_after(headers):
    """Seconds from a Retry-After header (delta or HTTP date), or None."""
    value = (headers.get("Retry-After") or "").strip() if headers else ""
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, IndexError):
        return None


def http_get(url, host, headers=None, timeout=30):
    """Paced GET (normal proxy settings) -> (status, content type, body, final URL).

    A host stopped by a 429 earlier in this run raises Blocked without a request; a 429 now stops the host and raises
    Blocked; other HTTP errors raise urllib's HTTPError, network errors URLError / OSError. Logs show the URL without
    its query string."""
    shown = url.split("?", 1)[0]
    if host in STOPPED:
        log(f"GET {shown} skipped: {host} answered 429 earlier in this run")
        raise Blocked(host, STOPPED[host])
    wait = LAST_CALL.get(host, 0.0) + PACE_INTERVALS.get(host, PACE_DEFAULT) - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    LAST_CALL[host] = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            log(f"GET {shown} -> {resp.status}")
            return resp.status, resp.headers.get("Content-Type", ""), body, resp.geturl()
    except urllib.error.HTTPError as e:
        if e.code != 429:
            log(f"GET {shown} -> {e.code}")
            raise
        STOPPED[host] = {"reason": "HTTP 429", "retry_after": retry_after(e.headers)}
        log(f"GET {shown} -> 429: {host} is not asked again in this run")
        raise Blocked(host, STOPPED[host])


def emit(code, exit_code, hint=None, **fields):
    out = {"code": code, **fields}
    if hint and code != "ok":
        out["hint"] = hint
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


# ---------------------------------------------------------------- identifier

ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})"


def parse_identifier(raw):
    """Return (doi, arxiv_id, arxiv_version) from a DOI / DOI URL / arXiv id / arXiv URL."""
    s = raw.strip()
    s = re.sub(r"^(?:https?://)?(?:www\.)?arxiv\.org/(?:abs|pdf)/", "arXiv:", s, flags=re.I)
    s = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", s, flags=re.I)
    s = re.sub(r"^doi:\s*", "", s, flags=re.I)
    s = re.sub(r"[\s.,;:'\"<>\]}]+$", "", s)
    if s.endswith(")") and s.count("(") < s.count(")"):
        s = s[:-1]
    m = re.fullmatch(rf"(?:arxiv:)?\s*({ARXIV_ID})(v\d+)?(?:\.pdf)?", s, flags=re.I)
    if m:
        return f"10.48550/arXiv.{m.group(1)}", m.group(1), m.group(2) or ""
    m = re.fullmatch(rf"10\.48550/arxiv\.({ARXIV_ID})(v\d+)?", s, flags=re.I)
    if m:
        return f"10.48550/arXiv.{m.group(1)}", m.group(1), m.group(2) or ""
    if re.fullmatch(r"10\.\d{4,9}/\S+", s):
        return s, None, ""
    raise Failure("invalid_identifier", 1,
                  "pass a DOI (10.xxxx/...), a doi.org URL, or an arXiv id such as 2006.11239", input=raw)


# ------------------------------------------------------------------- network

def fetch_csl(doi):
    url = DOI_BASE_URL + "/" + urllib.parse.quote(doi, safe="/")
    try:
        status, ctype, body, final = http_get(url, HOST_DOI, {"Accept": CSL_ACCEPT})
    except Blocked as b:
        raise Failure("source_blocked", 2, "doi.org answered 429 earlier in this run; rerun later",
                      url=url, **{k: v for k, v in b.fields().items() if k != "code"})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise Failure("not_found", 1, "check the DOI for typos; if it is fresh, the registration agency may "
                          "not have indexed it yet - search the title instead", url=url)
        if e.code in (406, 415) or 400 <= e.code < 500:
            raise Failure("no_csl_record", 1, "hand-write item.json or use the recognizer fallback",
                          url=url, status=e.code)
        raise Failure("doi_org_unreachable", 2, "doi.org returned a server error; retry later", url=url, status=e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log(f"GET {url} -> {e}")
        raise Failure("doi_org_unreachable", 2, "check network / proxy and retry", url=url, error=str(e))
    log(f"  {status} {ctype} (final: {final})")
    if "json" not in ctype.lower():
        raise Failure("no_csl_record", 1, "hand-write item.json or use the recognizer fallback",
                      url=url, content_type=ctype, final_url=final)
    try:
        record = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise Failure("no_csl_record", 1, "hand-write item.json or use the recognizer fallback",
                      url=url, content_type=ctype, final_url=final)
    if not isinstance(record, dict):
        raise Failure("no_csl_record", 1, "hand-write item.json or use the recognizer fallback", url=url)
    # Registration agency, for libraryCatalog: Crossref says so in `source`; DataCite answers from crosscite.org.
    agency = first_str(record.get("source")) or ("Datacite" if "crosscite.org" in final or "datacite" in final else "")
    return record, agency


def fetch_schema(base_url):
    url = base_url.rstrip("/") + "/api/schema"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with opener.open(req, timeout=15) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        log(f"GET {url} -> {e.code}")
        if e.code == 403:
            raise Failure("local_api_disabled", 2,
                          "ask the user to enable the local API in Zotero (Settings > Advanced), then rerun", url=url)
        raise Failure("zotero_unreachable", 2, "Zotero answered unexpectedly; ask the user to check Zotero",
                      url=url, status=e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log(f"GET {url} -> {e}")
        raise Failure("zotero_unreachable", 2, "ask the user to start Zotero, then rerun", url=url, error=str(e))
    log(f"GET {url} -> 200")
    return json.loads(body)


def crossref_work(doi):
    """(Crossref REST `message` of one DOI, None) or (None, why) - never raises."""
    url = CROSSREF_BASE_URL + "/works/" + urllib.parse.quote(doi, safe="/")
    try:
        _, _, body, _ = http_get(url, HOST_CROSSREF, {"Accept": "application/json"})
    except Blocked:
        return None, "source_blocked (429 earlier in this run)"
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log(f"GET {url} -> {getattr(e, 'reason', None) or type(e).__name__}")
        return None, "network error"
    try:
        message = json.loads(body.decode("utf-8")).get("message")
    except (UnicodeDecodeError, ValueError, AttributeError):
        return None, "unexpected response"
    return (message, None) if isinstance(message, dict) else (None, "unexpected response")


def crossref_container_titles(doi):
    """(container-title list, None) from Crossref's REST record of one DOI, or (None, why) - never raises."""
    message, why = crossref_work(doi)
    if message is None:
        return None, why
    titles = message.get("container-title")
    if not isinstance(titles, list):
        return None, "no container-title"
    return [strip_markup(first_str(t)) for t in titles if first_str(t)], None


def series_key(name):
    return re.sub(r"\s+", " ", name).strip().casefold()


KNOWN_SERIES = {series_key(s) for s in PROCEEDINGS_SERIES}


def proceedings_from_crossref(doi):
    """For a book-chapter with an ISSN: {"series", "title"} when Crossref names a known proceedings series and the
    volume title; otherwise {"note"} saying why the draft stays a bookSection."""
    titles, why = crossref_container_titles(doi)
    if titles is None:
        return {"note": f"Crossref lookup failed: {why}"}
    if len(titles) == 2 and series_key(titles[0]) in KNOWN_SERIES:
        return {"series": titles[0], "title": titles[1]}
    return {"note": f"Crossref container-title: {json.dumps(titles, ensure_ascii=False)}"}


# ------------------------------------------------------------------- mapping

def first_str(value):
    """CSL allows string-or-list for titles; numbers show up in DataCite records."""
    if isinstance(value, list):
        value = value[0] if value else ""
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def join_list(value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return first_str(value)


def strip_markup(text):
    """Drop JATS/HTML tags (<jats:p>, <i>, ...) and collapse whitespace."""
    text = re.sub(r"</?[A-Za-z][^<>]*>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def format_date(value):
    """CSL date -> 'YYYY-MM-DD' / 'YYYY-MM' / 'YYYY' (or '' when absent)."""
    if not isinstance(value, dict):
        return ""
    parts = value.get("date-parts") or []
    if not parts or not parts[0]:
        return first_str(value.get("raw") or value.get("literal") or "")
    nums = [int(p) for p in parts[0] if p not in (None, "")]
    if not nums:
        return ""
    return "-".join([str(nums[0])] + [f"{n:02d}" for n in nums[1:3]])


def comparable(text):
    """Casefolded letters and digits only, for 'does the title already end with the subtitle'."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold() if ch.isalnum())


def add_subtitle(title, subtitle):
    """'Title: Subtitle' from CSL `subtitle` (string or list); unchanged when there is none or the title ends with it."""
    sub = next((s for s in (strip_markup(first_str(v)) for v in (subtitle if isinstance(subtitle, list) else [subtitle])) if s), "")
    if not title or not sub or comparable(title).endswith(comparable(sub)):
        return title
    return title + (" " if title[-1] in ":?!" else ": ") + sub


def arxiv_category_tags(categories):
    """DataCite's arXiv `categories` -> tag names as Zotero's arXiv translator writes them; FOS entries and repeats dropped."""
    tags = []
    for raw in categories if isinstance(categories, list) else [categories]:
        text = raw.strip() if isinstance(raw, str) else ""
        if not text or text.casefold().startswith("fos:"):
            continue
        m = ARXIV_CATEGORY.fullmatch(text)
        if not m:
            tag = text
        elif not m.group(3):
            tag = m.group(1)  # single-archive category such as quant-ph or hep-th
        elif m.group(2) in ARXIV_ARCHIVES:
            tag = f"{ARXIV_ARCHIVES[m.group(2)]} - {m.group(1)}"
        else:
            tag = text  # archive outside the translator's table: keep DataCite's wording
        if tag not in tags:
            tags.append(tag)
    return tags


def single_page(page):
    parts = [p.strip() for p in re.split(r"[-‐-―]", page)]
    return len(parts) == 1 or (len(parts) == 2 and parts[0] == parts[1])


def erratum_signals(record, item_type):
    """Why this DOI may be an erratum / correction / retraction notice rather than the paper ([] when nothing points to it)."""
    signals = []
    m = ERRATUM_TITLE.match(strip_markup(first_str(record.get("title"))))
    if m:
        signals.append(f"title starts with {m.group(0)!r}")
    if item_type in ERRATUM_TYPES:
        if not any(isinstance(p, dict) for p in record.get("author") or []):
            signals.append("no authors")
        page = first_str(record.get("page"))
        # An article number (Elsevier 104336, PLOS e0360436, JAMA Netw Open e2640040) is not a one-page notice.
        article_number = page == first_str(record.get("article-number")) or re.fullmatch(r"[eE]?\d{5,}", page)
        if page and single_page(page) and not article_number:
            signals.append(f"single page {page!r}")
    return signals


def map_type(csl_type, schema):
    if csl_type in CROSSREF_TYPES:
        return CROSSREF_TYPES[csl_type]
    zotero_types = schema.get("csl", {}).get("types", {}).get(csl_type)
    if zotero_types:
        return zotero_types[0]
    return None


class TypeFields:
    """Field/creator tables of one Zotero itemType, with baseField-aware lookup."""

    def __init__(self, schema, item_type):
        entry = next(t for t in schema["itemTypes"] if t["itemType"] == item_type)
        self.order = ["itemType", "title", "creators"] + [f["field"] for f in entry["fields"]]
        self.base = {f["field"]: f.get("baseField") for f in entry["fields"]}
        self.creator_types = [c["creatorType"] for c in entry["creatorTypes"]]
        self.primary = next((c["creatorType"] for c in entry["creatorTypes"] if c.get("primary")), None)

    def resolve(self, candidates):
        """First candidate that is a field of this type, directly or as a baseField."""
        for c in candidates:
            if c in self.base:
                return c
            for field, base in self.base.items():
                if base == c:
                    return field
        return None


def build_creators(record, schema, tf, warnings):
    csl_to_zotero = {}
    for zotero_type, csl_var in schema["csl"]["names"].items():
        csl_to_zotero.setdefault(csl_var, []).append(zotero_type)
    creators = []
    for csl_var, zotero_types in csl_to_zotero.items():
        people = record.get(csl_var)
        if not isinstance(people, list) or not people:
            continue
        if csl_var == "author" and tf.primary:  # CSL author = the type's primary creator (programmer, artist, ...)
            zotero_types = [tf.primary] + zotero_types
        ctype = next((z for z in zotero_types if z in tf.creator_types), None)
        if ctype is None:
            if "contributor" in tf.creator_types:
                ctype = "contributor"
                warnings.append(f"{csl_var} stored as contributor (no matching creatorType in {tf.order[0]})")
            else:
                warnings.append(f"{csl_var} dropped (no creatorType for it)")
                continue
        for p in people:
            if not isinstance(p, dict):
                continue
            family = first_str(p.get("family"))
            given = first_str(p.get("given"))
            literal = first_str(p.get("literal") or p.get("name"))
            if family and given:
                creators.append({"creatorType": ctype, "firstName": given, "lastName": family})
            elif family or literal:
                creators.append({"creatorType": ctype, "name": family or literal})
    return creators


def build_item(record, schema, doi, arxiv_id, arxiv_version, agency, warnings, proceedings=None):
    """CSL record -> Zotero item. `proceedings` is proceedings_from_crossref()'s answer for a book-chapter with an ISSN."""
    csl_type = first_str(record.get("type"))
    is_arxiv = doi.lower().startswith("10.48550/arxiv.")
    in_series = bool(proceedings and proceedings.get("series"))
    item_type = "preprint" if is_arxiv else "conferencePaper" if in_series else map_type(csl_type, schema)
    unknown = item_type is None
    if unknown:
        item_type = "journalArticle"
        warnings.append(f"unknown CSL/Crossref type {csl_type!r}; itemType defaulted to journalArticle")
    tf = TypeFields(schema, item_type)
    text_map = schema["csl"]["fields"]["text"]
    date_map = schema["csl"]["fields"]["date"]
    item = {"itemType": item_type}
    dropped = []
    # Handled below, or not wanted: `version` is the metadata record version, `source` the agency.
    special = {"title", "abstract", "URL", "DOI", "container-title", "ISSN", "ISBN", "source", "citation-key", "version"}
    if item_type == "journalArticle":
        special.add("publisher")  # Zotero's own DOI import leaves it blank for journal articles

    item["title"] = add_subtitle(strip_markup(first_str(record.get("title"))), record.get("subtitle"))
    if not item["title"]:
        warnings.append("record has no title")

    for csl_key, candidates in text_map.items():
        if csl_key in special or csl_key not in record:
            continue
        value = record[csl_key]
        if isinstance(value, (dict, list)) and not (isinstance(value, list) and all(isinstance(v, (str, int)) for v in value)):
            continue
        value = join_list(value) if isinstance(value, list) else first_str(value)
        if not value:
            continue
        target = tf.resolve(candidates)
        if target:
            item[target] = value
        else:
            dropped.append(csl_key)

    container = proceedings["title"] if in_series else first_str(record.get("container-title"))
    if in_series:
        if tf.resolve(["series"]):
            item[tf.resolve(["series"])] = proceedings["series"]
        warnings.append(f"book-chapter in the proceedings series {proceedings['series']!r}: drafted as conferencePaper "
                        "with the volume title from Crossref; the date is the volume's, check it against the conference year")
    elif csl_type == "book-chapter" and record.get("ISSN"):
        note = f" ({proceedings['note']})" if proceedings and proceedings.get("note") else ""
        warnings.append("book-chapter with an ISSN: container-title is probably the series name "
                        f"(e.g. LNCS); check bookTitle / series{note}")
    if container:
        target = tf.resolve(["publicationTitle"])
        if target:
            item[target] = container
        else:
            dropped.append("container-title")
    elif item_type in ("journalArticle", "conferencePaper", "bookSection"):
        warnings.append("record has no container-title")

    for key, field in (("ISSN", "ISSN"), ("ISBN", "ISBN")):
        if record.get(key):
            target = tf.resolve([field])
            if target:
                item[target] = join_list(record[key])
            else:
                dropped.append(key)

    abstract = strip_markup(first_str(record.get("abstract")))
    if abstract:
        item["abstractNote"] = abstract
    else:
        warnings.append("record has no abstract")

    for csl_key, field in date_map.items():
        if csl_key == "accessed" or csl_key not in record:
            continue
        value = format_date(record[csl_key])
        if value and tf.resolve([field]):
            item[tf.resolve([field])] = value
    if not item.get("date"):
        for key in DATE_FALLBACKS:
            value = format_date(record.get(key))
            if value:
                item["date"] = value
                warnings.append(f"date taken from {key!r} (no usable 'issued')")
                break
    if not item.get("date"):
        warnings.append("record has no date")
    elif re.fullmatch(r"\d{4}", item["date"]):
        warnings.append("date is year-only")

    event = None
    for key in EVENT_KEYS:
        raw = record.get(key)
        event = first_str(raw.get("name") if isinstance(raw, dict) else raw)
        if event:
            break
    if event:
        target = tf.resolve(["conferenceName", "meetingName"])
        if target:
            item[target] = event
    place = first_str(record.get("publisher-place") or record.get("publisher-location"))
    if place and tf.resolve(["place"]):
        item[tf.resolve(["place"])] = place

    item["creators"] = build_creators(record, schema, tf, warnings)
    if not item["creators"]:
        warnings.append("record has no creators")
    signals = erratum_signals(record, item_type)
    if signals:
        warnings.append(f"possible erratum, correction or retraction notice ({'; '.join(signals)}): "
                        "open the landing page and make sure this DOI is the paper itself")

    doi_url = f"https://doi.org/{doi}"
    if is_arxiv:
        item["url"] = f"https://arxiv.org/abs/{arxiv_id}{arxiv_version}"
        item["repository"] = "arXiv"
        item["archiveID"] = f"arXiv:{arxiv_id}"
    else:  # the version of record: its DOI link, which always leads to the publisher's current page
        item["url"] = doi_url
        if SALES_PAGE_DOI.match(doi):
            warnings.append("this DOI leads to the printed proceedings' sales page: set item.url to the paper's page "
                            "on proceedings.neurips.cc")

    if tf.resolve(["DOI"]):
        item["DOI"] = doi
    else:
        item["extra"] = "\n".join(x for x in (f"DOI: {doi}", item.get("extra", "")) if x)
        warnings.append(f"{item_type} has no DOI field; DOI written to extra")

    if tf.resolve(["libraryCatalog"]):
        item["libraryCatalog"] = f"DOI.org ({agency})" if agency else "DOI.org"

    if dropped:
        warnings.append(f"fields not in {item_type}, dropped: {', '.join(sorted(dropped))}")

    ordered = {k: item[k] for k in tf.order if k in item}
    ordered.update({k: v for k, v in item.items() if k not in ordered})
    return ordered, csl_type, unknown


# ------------------------------------------------------------------- records

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json_records(text, source):
    """Parse JSONL, a JSON array or one object into a list of [record|None, error|None]."""
    text = text.strip()
    if not text:
        return []
    entries = []
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = None
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


def load_record_files(paths):
    """One entry per path: {path, record, orig, error}; unreadable files become failed entries, never written back."""
    entries = []
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


def write_record(path, record):
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


def write_results(results, quiet):
    """results: [(path, record, summary, outcome)], outcome ok|skipped|failed.

    quiet (-i / --out-dir): records were written to files; stdout gets one summary line per record and the
    final {"summary"} line. Otherwise stdout gets the full records as JSONL and the summary goes to stderr.
    Returns the exit status: 1 when anything failed."""
    counts = {"total": len(results), "ok": 0, "skipped": 0, "failed": 0}
    for path, record, summary, outcome in results:
        counts[outcome] += 1
        if quiet:
            print(json.dumps(summary, ensure_ascii=False))
        elif record is not None:
            print(json.dumps(record, ensure_ascii=False))
        else:
            print(json.dumps(summary, ensure_ascii=False))
    summary_line = json.dumps({"summary": counts}, ensure_ascii=False)
    print(summary_line, file=sys.stdout if quiet else sys.stderr)
    return 1 if counts["failed"] else 0


# ---------------------------------------------------------------- id sources

def parse_id_lines(text, source):
    """`identifier[<TAB>citation key]` per line; '#' comments and blank lines skipped."""
    out = []
    for n, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        ident, _, key = s.partition("\t")
        ident, key = ident.strip(), key.strip()
        if not ident:
            log(f"{source} line {n}: no identifier before the tab, skipped")
            continue
        out.append({"id": ident, "citationKey": key or None})
    return out


def bib_close(text, start, close_ch):
    """Index of the closing delimiter of an entry body starting at `start`, honouring nested braces."""
    depth = 0
    for pos in range(start, len(text)):
        c = text[pos]
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0 and close_ch == "}":
                return pos
            depth -= 1
        elif c == close_ch and depth == 0:
            return pos
    return len(text)


def bib_value(body, pos):
    """Parse one field value at pos: {braced}, "quoted", or a bare token; '#' concatenation joined. Returns (value, pos)."""
    parts = []
    n = len(body)
    while True:
        while pos < n and body[pos].isspace():
            pos += 1
        if pos >= n:
            break
        c = body[pos]
        if c == "{":
            depth, start = 0, pos
            while pos < n:
                if body[pos] == "{":
                    depth += 1
                elif body[pos] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                pos += 1
            parts.append(body[start + 1:pos])
            pos += 1
        elif c == '"':
            depth, start = 0, pos + 1
            pos += 1
            while pos < n:
                if body[pos] == "{":
                    depth += 1
                elif body[pos] == "}":
                    depth -= 1
                elif body[pos] == '"' and depth == 0:
                    break
                pos += 1
            parts.append(body[start:pos])
            pos += 1
        else:
            m = re.match(r"[^,#\s]+", body[pos:])
            if not m:
                break
            parts.append(m.group(0))
            pos += m.end()
        while pos < n and body[pos].isspace():
            pos += 1
        if pos < n and body[pos] == "#":
            pos += 1
            continue
        break
    return "".join(parts), pos


def bib_clean(value):
    """Drop braces and collapse whitespace (titles and identifiers only; no LaTeX decoding)."""
    return re.sub(r"\s+", " ", value.replace("{", "").replace("}", "")).strip()


def parse_bib(text):
    """Minimal BibTeX reader: yields (entry_type, key, fields) with lower-cased field names; @comment/@string/@preamble skipped."""
    pos = 0
    while True:
        at = text.find("@", pos)
        if at < 0:
            return
        m = re.match(r"@\s*([A-Za-z]+)\s*([{(])", text[at:])
        if not m:
            pos = at + 1
            continue
        etype, open_ch = m.group(1).lower(), m.group(2)
        body_start = at + m.end()
        end = bib_close(text, body_start, "}" if open_ch == "{" else ")")
        body = text[body_start:end]
        pos = end + 1
        if etype in ("comment", "string", "preamble"):
            continue
        key, _, rest = body.partition(",")
        fields = {}
        p = 0
        while True:
            fm = re.match(r"\s*,?\s*([^\s=,]+)\s*=\s*", rest[p:])
            if not fm:
                break
            value, p = bib_value(rest, p + fm.end())
            fields[fm.group(1).lower()] = bib_clean(value)
        yield etype, key.strip(), fields


def bib_identifier(fields):
    """DOI, else an arXiv id (eprint / a URL or journal mentioning arXiv), else None."""
    doi = (fields.get("doi") or "").strip()
    if doi:
        return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
    eprint = (fields.get("eprint") or "").strip()
    prefix = (fields.get("archiveprefix") or fields.get("eprinttype") or "").strip().lower()
    m = re.fullmatch(rf"(?:arxiv:)?({ARXIV_ID})(v\d+)?", eprint, flags=re.I)
    if eprint and (prefix == "arxiv" or m):
        return "arXiv:" + (m.group(1) + (m.group(2) or "") if m else eprint)
    for name in ("url", "journal", "howpublished", "note", "eprint"):
        m = re.search(rf"(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*)({ARXIV_ID})(v\d+)?", fields.get(name) or "", flags=re.I)
        if m:
            return "arXiv:" + m.group(1) + (m.group(2) or "")
    return None


def entries_from_bib(text):
    out = []
    for etype, key, fields in parse_bib(text):
        ident = bib_identifier(fields)
        entry = {"id": ident or fields.get("title") or "", "citationKey": key or None}
        if not ident:
            entry["no_identifier"] = True
        out.append(entry)
    return out


# ---------------------------------------------------------------------- slugs

SLUG_UNSAFE = re.compile(r'[<>:"/\\|?*\s]+')


def clean(s, limit=None):
    """Lower-case letters and digits only; accents stripped."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if ch.isalnum() and not unicodedata.combining(ch)).lower()
    return s[:limit] if limit else s


def derive_slug(item):
    """<first author surname><year><first title word of >= 4 letters>, e.g. liu2022progressive; '' when nothing usable."""
    creators = item.get("creators") or []
    first = creators[0] if creators and isinstance(creators[0], dict) else {}
    surname = first.get("lastName") or (first.get("name") or "").split()[-1:] or ""
    surname = surname[0] if isinstance(surname, list) else surname
    year = re.match(r"\d{4}", item.get("date") or "")
    word = next((w for w in re.findall(r"[^\W_]+", item.get("title") or "") if sum(ch.isalpha() for ch in w) >= 4), "")
    return clean(surname) + (year.group(0) if year else "") + clean(word)


def slug_for(record, given_key):
    if record.get("slug"):
        return str(record["slug"])
    key = given_key or record.get("citationKey")
    if key:
        return SLUG_UNSAFE.sub("_", key).strip("_") or clean(key)
    slug = derive_slug(record.get("item") or {}) if isinstance(record.get("item"), dict) else ""
    return slug or clean(str(record.get("id") or ""), 60) or "record"


def normalize_id(ident):
    try:
        return parse_identifier(ident)[0].lower()
    except Failure:
        return ident.strip().lower()


# --------------------------------------------------------- published versions

ATOM_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def arxiv_id_of(rec):
    """The record's arXiv id: from `id`, else the item's archiveID, DOI, extra or url; None when there is none."""
    try:
        aid = parse_identifier(str(rec.get("id") or ""))[1]
        if aid:
            return aid
    except Failure:
        pass
    item = rec.get("item") if isinstance(rec.get("item"), dict) else {}
    for value, pattern in ((item.get("archiveID"), rf"^arxiv:\s*({ARXIV_ID})"), (item.get("DOI"), rf"^10\.48550/arxiv\.({ARXIV_ID})"),
                           (item.get("extra"), rf"^arxiv:\s*({ARXIV_ID})"), (item.get("url"), rf"arxiv\.org/(?:abs|pdf)/({ARXIV_ID})")):
        m = re.search(pattern, str(value or ""), re.I | re.M)
        if m:
            return m.group(1)
    return None


def is_preprint_draft(rec):
    """A record whose item is still the arXiv preprint: the ones published_candidates is for."""
    item = rec.get("item") if isinstance(rec.get("item"), dict) else {}
    return bool(arxiv_id_of(rec)) and (item.get("itemType") == "preprint" or str(item.get("DOI") or "").lower().startswith("10.48550/"))


def clean_text(value):
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) and value.strip() else None


def year_in(text):
    m = re.search(r"\b(19|20)\d{2}\b", text or "")
    return int(m.group(0)) if m else None


def similarity(a, b):
    a, b = comparable(a or ""), comparable(b or "")
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0


def problem(e):
    """A source failure for the summary line (never with a URL)."""
    if isinstance(e, Blocked):
        return e.fields()
    if isinstance(e, urllib.error.HTTPError):
        return {"code": "unreachable", "detail": f"HTTP {e.code}"}
    if isinstance(e, (ET.ParseError, ValueError, KeyError, TypeError, AttributeError, UnicodeDecodeError)):
        return {"code": "unexpected_response", "detail": type(e).__name__}
    return {"code": "unreachable", "detail": str(getattr(e, "reason", None) or type(e).__name__)}


def arxiv_api(ids):
    """{id: {journal_ref, doi, comment}} from one arXiv API call (<= 100 ids); raises on failure."""
    url = ARXIV_API_URL + "?" + urllib.parse.urlencode({"id_list": ",".join(ids), "max_results": len(ids)})
    _, _, body, _ = http_get(url, HOST_ARXIV_API, {"Accept": "application/atom+xml"}, timeout=60)
    out = {}
    for entry in ET.fromstring(body).findall("a:entry", ATOM_NS):
        m = re.search(rf"arxiv\.org/abs/({ARXIV_ID})(?:v\d+)?$", (entry.findtext("a:id", "", ATOM_NS) or "").strip(), re.I)
        if m:
            out[m.group(1)] = {"journal_ref": clean_text(entry.findtext("arxiv:journal_ref", None, ATOM_NS)),
                               "doi": clean_text(entry.findtext("arxiv:doi", None, ATOM_NS)),
                               "comment": clean_text(entry.findtext("arxiv:comment", None, ATOM_NS))}
    return out


def arxiv_refs(ids):
    """id -> {journal_ref, doi, comment}, and id -> source status; the API in chunks of 100 ids."""
    refs, status = {}, {}
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        try:
            got = arxiv_api(chunk)
        except (Blocked, urllib.error.URLError, TimeoutError, OSError, ET.ParseError) as e:
            for aid in chunk:
                status[aid] = problem(e)
            continue
        for aid in chunk:
            refs[aid], status[aid] = got.get(aid, {}), {"code": "ok"}
    return refs, status


def candidate(source, doi=None, venue=None, year=None, title=None, url=None, **extra):
    return {"doi": doi, "venue": venue, "year": year, "title": title, "url": url, "source": source,
            **{k: v for k, v in extra.items() if v is not None}}


def from_arxiv_ref(ref):
    """The author-declared published version: each DOI arXiv lists (10.48550 aside), else the journal_ref alone."""
    journal = ref.get("journal_ref")
    out = []
    for doi in re.findall(r"10\.\d{4,9}/[^\s,;]+", ref.get("doi") or ""):
        doi = doi.rstrip(".")
        if not doi.lower().startswith("10.48550/"):
            out.append(candidate("arxiv", doi=doi, venue=journal, year=year_in(journal), url=f"https://doi.org/{doi}",
                                 journal_ref=journal))
    if not out and journal:
        out.append(candidate("arxiv", venue=journal, year=year_in(journal), journal_ref=journal))
    return out


def crossref_fields(work):
    """Title (with subtitle), venue, year and type of a Crossref work; a chapter in a proceedings series (LNCS & co.)
    names its volume, not the series."""
    event = work.get("event")
    containers = [first_str(c) for c in work.get("container-title") or [] if first_str(c)] if isinstance(work.get("container-title"), list) \
        else [first_str(work.get("container-title"))] if first_str(work.get("container-title")) else []
    if len(containers) > 1 and series_key(containers[0]) in KNOWN_SERIES:
        containers = containers[1:]
    venue = (containers[0] if containers else "") or first_str(event.get("name") if isinstance(event, dict) else event) or None
    issued = (work.get("issued") or {}).get("date-parts") or [[None]]
    year = issued[0][0] if issued and issued[0] and isinstance(issued[0][0], int) else None
    title = add_subtitle(strip_markup(first_str(work.get("title"))), work.get("subtitle")) or None
    return {"title": title, "venue": strip_markup(venue) if venue else None, "year": year, "type": work.get("type")}


def crossref_search(title, family, titles):
    """Crossref works whose title (with or without subtitle) is >= CANDIDATE_SIMILARITY to one of `titles`;
    arXiv DOIs and posted-content (other preprints) left out. Raises on failure."""
    params = {"query.bibliographic": title, "rows": 10,
              "select": "DOI,title,subtitle,container-title,type,issued,event,URL"}
    if family:
        params["query.author"] = family
    url = CROSSREF_BASE_URL + "/works?" + urllib.parse.urlencode(params)
    _, _, body, _ = http_get(url, HOST_CROSSREF, {"Accept": "application/json"})
    out = []
    for work in json.loads(body.decode("utf-8"))["message"]["items"]:
        doi = first_str(work.get("DOI"))
        if not doi or doi.lower().startswith("10.48550/") or work.get("type") == "posted-content":
            continue
        fields = crossref_fields(work)
        plain = strip_markup(first_str(work.get("title")))
        if max(similarity(t, c) for t in titles for c in (plain, fields["title"] or "")) >= CANDIDATE_SIMILARITY:
            out.append(candidate("crossref", doi=doi, venue=fields["venue"], year=fields["year"], title=fields["title"],
                                 url=f"https://doi.org/{doi}", type=fields["type"]))
    return out


def merge_candidates(found, titles):
    """One entry per DOI (its sources listed); a DOI-less entry (an arXiv journal_ref alone) stays as it is."""
    merged = []
    for c in found:
        same = c["doi"] and next((m for m in merged if m["doi"] and m["doi"].lower() == c["doi"].lower()), None)
        if not same:
            merged.append({**c, "sources": [c["source"]]})
            continue
        for key in ("venue", "year", "title", "type", "journal_ref"):
            if same.get(key) is None and c.get(key) is not None:
                same[key] = c[key]
        if c["source"] not in same["sources"]:
            same["sources"].append(c["source"])
    keys = {comparable(t) for t in titles if t}
    order = ("doi", "venue", "year", "title", "url", "source", "sources", "title_differs", "type", "journal_ref", "redraft")
    out = []
    for m in merged:
        m["title_differs"] = None if not m["title"] else comparable(m["title"]) not in keys
        m["redraft"] = m["doi"]
        if len(m["sources"]) == 1:
            m.pop("sources")
        out.append({k: m[k] for k in order if k in m and (m[k] is not None or k in ("doi", "venue", "year", "title", "redraft"))})
    return out


def add_candidates(records):
    """Fill published_candidates on preprint records (the item is never touched, B#4) from arXiv's journal_ref / doi and a
    Crossref title search -> {id(record): {"sources": ..., "comment": ...}} for the summary lines. A failing source is
    noted there, never fatal; what no source finds, the agent looks up on papers.cool."""
    info = []
    for rec in records:
        item = rec["item"]
        titles = [t for t in [item.get("title")] + list(rec.get("alt_titles") or []) if isinstance(t, str) and t.strip()]
        first = next((c for c in item.get("creators") or [] if isinstance(c, dict)), {})
        family = first.get("lastName") or ((first.get("name") or "").split() or [None])[-1]
        info.append({"rec": rec, "aid": arxiv_id_of(rec), "titles": titles, "family": family, "found": [], "sources": {}})
    refs, arxiv_status = arxiv_refs(list(dict.fromkeys(i["aid"] for i in info)))
    notes = {}
    for i in info:
        ref = refs.get(i["aid"], {})
        i["sources"]["arxiv"] = arxiv_status.get(i["aid"], {"code": "error"})
        i["found"] += from_arxiv_ref(ref)
        if i["titles"]:
            try:
                i["found"] += crossref_search(i["titles"][0], i["family"], i["titles"])
                i["sources"]["crossref"] = {"code": "ok"}
            except (Blocked, urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as e:
                i["sources"]["crossref"] = problem(e)
        else:
            i["sources"]["crossref"] = {"code": "skipped", "detail": "no title"}
        # A DOI arXiv declares that the search did not return: its own Crossref record gives title, venue and year.
        searched = {c["doi"].lower() for c in i["found"] if c["source"] == "crossref"}
        for c in i["found"]:
            if c["source"] == "arxiv" and c["doi"] and c["doi"].lower() not in searched:
                work, _ = crossref_work(c["doi"])
                if work:
                    fields = crossref_fields(work)
                    c.update(title=fields["title"], type=fields["type"], venue=fields["venue"] or c["venue"],
                             year=fields["year"] or c["year"])
        i["rec"]["published_candidates"] = merge_candidates(i["found"], i["titles"])
        notes[id(i["rec"])] = {"sources": i["sources"], "comment": ref.get("comment")}
    return notes


def candidates_summary(rec, note):
    out = {"candidates": len(rec.get("published_candidates") or [])}
    if note.get("comment"):
        out["arxiv_comment"] = note["comment"]
    trouble = {k: v for k, v in note.get("sources", {}).items() if v.get("code") not in ("ok", "skipped")}
    if trouble:
        out["candidate_sources"] = trouble
    return out


# --------------------------------------------------------------------- redraft

def add_arxiv_line(item, aid):
    lines = [ln for ln in str(item.get("extra") or "").splitlines() if ln.strip()]
    if not any(re.match(rf"arxiv:\s*{re.escape(aid)}\b", ln, re.I) for ln in lines):
        lines.append(f"arXiv: {aid}")
    item["extra"] = "\n".join(lines)


def split_name(name):
    """'Last, First' or 'First Last' -> a Zotero creator."""
    name = name.strip()
    if "," in name:
        last, first = (p.strip() for p in name.split(",", 1))
    else:
        first, _, last = name.rpartition(" ")
    return {"creatorType": "author", "firstName": first, "lastName": last} if first and last else {"creatorType": "author", "name": name}


class CitationMeta(HTMLParser):
    """A page's <meta name="citation_*"> tags (the Highwire Press tags Google Scholar asks publishers for), plus the
    description tags as an abstract fallback. Attribute order varies between sites, hence a parser, not a regex."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        a = {k.lower(): (v or "").strip() for k, v in attrs}
        name = (a.get("name") or a.get("property") or "").lower()
        if (name.startswith("citation_") or name in ("description", "og:description", "dc.description")) and a.get("content"):
            self.meta.setdefault(name, []).append(a["content"])


def meta_first(meta, *names):
    for name in names:
        for value in meta.get(name) or []:
            if clean_text(value):
                return clean_text(value)
    return None


def page_meta(url):
    """GET a paper's landing page -> (its citation_* meta, the final URL); raises Failure."""
    host = urllib.parse.urlsplit(url).hostname or ""
    try:
        _, ctype, body, final = http_get(url, host, {"Accept": "text/html", "User-Agent": BROWSER_UA}, timeout=30)
    except Blocked as b:
        raise Failure("source_blocked", 1, "that host answered 429 earlier in this run; read the page in the browser and "
                      "fill the item from it", url=url, **{k: v for k, v in b.fields().items() if k != "code"})
    except urllib.error.HTTPError as e:
        raise Failure("page_unreachable", 1, "the page refuses a plain HTTP request; read it in the browser and fill the "
                      "item from what it shows", url=url, status=e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Failure("page_unreachable", 1, "check the URL, network or proxy", url=url, error=str(getattr(e, "reason", e)))
    m = re.search(r"charset=([\w\-]+)", ctype or "", re.I)
    parser = CitationMeta()
    try:
        parser.feed(body.decode(m.group(1) if m else "utf-8", errors="replace"))
    except LookupError:
        parser.feed(body.decode("utf-8", errors="replace"))
    if not meta_first(parser.meta, "citation_title"):
        raise Failure("no_citation_meta", 1, "the page has no citation_title meta tag (an OpenReview page behind a "
                      "challenge, or a site without the tags): fill the item by hand from the page", url=final)
    return parser.meta, final


def meta_date(value):
    m = re.match(r"(\d{4})(?:[/-](\d{1,2}))?(?:[/-](\d{1,2}))?", value or "")
    if not m:
        return value
    return "-".join([m.group(1)] + [f"{int(g):02d}" for g in m.groups()[1:] if g])


def item_from_page(meta, url, old, schema, warnings):
    """A conferencePaper (citation_conference_title, or a journal title that names proceedings: NeurIPS) or a
    journalArticle (citation_journal_title: TMLR too) from a page's citation_* meta; the preprint's creators and
    abstract fill what the page lacks -> (item, citation_pdf_url)."""
    conference = meta_first(meta, "citation_conference_title", "citation_conference")
    journal = meta_first(meta, "citation_journal_title")
    if not conference and journal and PROCEEDINGS_TITLE.search(journal):
        conference, journal = journal, None
    if conference:
        item_type = "conferencePaper"
    elif journal:
        item_type = "journalArticle"
    else:
        item_type = "conferencePaper"
        warnings.append("the page names neither a conference nor a journal (citation_conference_title / "
                        "citation_journal_title): drafted as conferencePaper, check the type and the venue")
    tf = TypeFields(schema, item_type)
    first_page, last_page = meta_first(meta, "citation_firstpage"), meta_first(meta, "citation_lastpage")
    pages = f"{first_page}-{last_page}" if first_page and last_page and first_page != last_page else first_page
    date = meta_date(meta_first(meta, "citation_publication_date", "citation_date", "citation_online_date"))
    fields = {"title": meta_first(meta, "citation_title"),
              "abstractNote": meta_first(meta, "citation_abstract") or old.get("abstractNote")
              or meta_first(meta, "dc.description", "og:description", "description"),
              "publicationTitle": conference or journal, "volume": meta_first(meta, "citation_volume"),
              "issue": meta_first(meta, "citation_issue"), "pages": pages, "date": date,
              "DOI": meta_first(meta, "citation_doi"), "publisher": meta_first(meta, "citation_publisher"),
              "ISSN": meta_first(meta, "citation_issn"), "ISBN": meta_first(meta, "citation_isbn"), "url": url,
              "libraryCatalog": urllib.parse.urlsplit(url).hostname, "extra": old.get("extra")}
    item = {"itemType": item_type}
    for field, value in fields.items():
        target = tf.resolve([field]) if value else None
        if target:
            item[target] = value
    authors = [a for a in meta.get("citation_author") or [] if clean_text(a)]
    old_creators = [c for c in old.get("creators") or [] if isinstance(c, dict)]
    item["creators"] = [split_name(clean_text(a)) for a in authors] or old_creators
    if authors and old_creators and len(authors) != len(old_creators):
        warnings.append(f"the page lists {len(authors)} authors, the preprint {len(old_creators)}: check the creators")
    if not date:
        warnings.append("the page gives no date: set it from the venue's year")
    ordered = {k: item[k] for k in tf.order if k in item}
    ordered.update({k: v for k, v in item.items() if k not in ordered})
    return ordered, meta_first(meta, "citation_pdf_url")


def run_redraft(args):
    """--redraft <DOI | page URL> RECORD: swap the preprint item for the published one in place (spec §6 doi_to_item)."""
    entry = load_record_files(args.records)[0]
    path = entry["path"]
    if entry["error"]:
        return write_results([(path, None, {"slug": path.stem, **entry["error"]}, "failed")], quiet=True)
    rec = entry["record"]
    slug = rec.get("slug") or path.stem
    target = args.redraft.strip()

    def done(code, outcome, hint=None, **extra):
        summary = {"slug": slug, "code": code, "redraft": target, **extra}
        if hint:
            summary["hint"] = hint
        return write_results([(path, None, summary, outcome)], quiet=True)

    if rec.get("saved") or rec.get("attach"):
        return done("already_saved", "failed", "the item is already in Zotero (saved / attach): change it there with "
                    "update_item.py, or start a new record")
    old = rec.get("item") if isinstance(rec.get("item"), dict) else {}
    aid = arxiv_id_of(rec)
    old_title = old.get("title") or ""
    try:
        schema = fetch_schema(args.base_url)
    except Failure as f:
        emit(f.code, f.exit_code, f.hint, **f.extra)
    warnings, pdf_url = [], None
    if re.match(r"https?://", target, re.I) and not re.match(r"https?://(?:dx\.)?doi\.org/|https?://(?:www\.)?arxiv\.org/",
                                                              target, re.I):
        try:
            meta, final = page_meta(target)
        except Failure as f:
            return done(f.code, "failed", f.hint, **f.extra)
        item, pdf_url = item_from_page(meta, final, old, schema, warnings)
    else:
        try:
            doi, published_arxiv, _ = parse_identifier(target)
        except Failure as f:
            return done(f.code, "failed", f.hint)
        if published_arxiv:
            return done("not_published", "failed", "10.48550 is the arXiv preprint's own DOI: give the published version's DOI")
        if str(old.get("DOI") or "").lower() == doi.lower():
            return done("skipped", "skipped", reason="same_doi")
        try:
            item, warnings, _, _, doi, _ = fetch_and_map(doi, schema)
        except Failure as f:
            out = done(f.code, "failed", f.hint, **{k: v for k, v in f.extra.items() if k != "input"})
            sys.exit(2 if f.exit_code == 2 else out)
        if not item.get("abstractNote") and old.get("abstractNote") and "record has no abstract" in warnings:
            item["abstractNote"] = old["abstractNote"]
            warnings[warnings.index("record has no abstract")] = "the DOI record has no abstract: the preprint's is kept"
    if aid:
        add_arxiv_line(item, aid)
    else:
        warnings.append("no arXiv id on the record: extra has no arXiv line")
    if old_title and comparable(old_title) != comparable(item.get("title") or ""):
        alt = [t for t in rec.get("alt_titles") or [] if isinstance(t, str)]
        if comparable(old_title) not in {comparable(t) for t in alt}:
            rec["alt_titles"] = alt + [old_title]
    cleared = [k for k in REDRAFT_CLEARS if k in rec]
    for k in REDRAFT_CLEARS + ("code", "hint", "detail"):
        rec.pop(k, None)
    rec["item"] = item
    if pdf_url:  # the venue's own PDF: a DOI-based link lookup would not find it for ICLR / PMLR and the like
        rec["links"] = [{"url": urllib.parse.urljoin(item.get("url") or target, pdf_url), "source": "page",
                         "version": "published", "needs_browser": False}]
    if warnings:
        rec["warnings"] = warnings
    else:
        rec.pop("warnings", None)
    summary = {"slug": slug, "code": "ok", "redraft": target, "itemType": item["itemType"], "title": item.get("title", "")[:80],
               "url": item.get("url")}
    if cleared:
        summary["cleared"] = cleared
    if rec.get("links") and pdf_url:
        summary["pdf_url"] = rec["links"][0]["url"]
    if rec.get("alt_titles"):
        summary["alt_titles"] = rec["alt_titles"]
    if warnings:
        summary["warnings"] = warnings
    if args.in_place:
        write_record(path, rec)
    return write_results([(path, rec, summary, "ok")], quiet=args.in_place)


# ---------------------------------------------------------------------- main

def fetch_and_map(ident, schema):
    """identifier -> (item, warnings, csl_type, unknown_type, doi, category tag names); raises Failure."""
    doi, arxiv_id, arxiv_version = parse_identifier(ident)
    record, agency = fetch_csl(doi)
    warnings = []
    record_doi = first_str(record.get("DOI"))
    if record_doi and record_doi.lower() != doi.lower():
        warnings.append(f"record DOI {record_doi!r} differs from requested {doi!r}; using the record's")
        doi = record_doi
    proceedings = None
    if first_str(record.get("type")) == "book-chapter" and record.get("ISSN"):
        proceedings = proceedings_from_crossref(doi)
    item, csl_type, unknown = build_item(record, schema, doi, arxiv_id, arxiv_version, agency, warnings, proceedings)
    categories = arxiv_category_tags(record.get("categories")) if doi.lower().startswith("10.48550/arxiv.") else []
    return item, warnings, csl_type, unknown, doi, categories


def category_tags(names):
    return [{"tag": name, "type": 1} for name in names]


def run_single(args):
    """v1: one --doi, one --out; writes the item draft and prints the v1 report."""
    ident = args.doi[0]
    try:
        schema = fetch_schema(args.base_url)
        item, warnings, csl_type, unknown, doi, categories = fetch_and_map(ident, schema)
    except Failure as f:
        emit(f.code, f.exit_code, f.hint, **{"input": ident, **f.extra})
    if categories and not item.get("tags"):
        item["tags"] = category_tags(categories)  # no record in v1: the item's own tags (create_item uses them without --tags-file)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(item, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    log(f"wrote {args.out} ({item['itemType']}, {len(item['creators'])} creators, {len(warnings)} warnings)")

    result = {"out": args.out, "itemType": item["itemType"], "title": item.get("title", ""), "doi": doi,
              "csl_type": csl_type, "warnings": warnings}
    if unknown:
        emit("unknown_type", 1, "set the right itemType in item.json (check_item.py --help lists the skeleton) "
             "or keep journalArticle if it fits", **result)
    emit("ok", 0, **result)


def collect_entries(args):
    """Every input becomes an entry {path, record, orig, error, given_key, no_identifier}."""
    entries = []

    def from_ids(specs):
        for spec in specs:
            entries.append({"path": None, "record": {"id": spec["id"]}, "orig": None, "error": None,
                            "given_key": spec.get("citationKey"), "no_identifier": spec.get("no_identifier", False)})

    from_ids([{"id": d} for d in args.doi])
    if args.ids:
        from_ids(parse_id_lines(Path(args.ids).read_text(encoding="utf-8"), args.ids))
    if args.bib:
        from_ids(entries_from_bib(Path(args.bib).read_text(encoding="utf-8")))
    if args.records:
        for e in load_record_files(args.records):
            entries.append({**e, "given_key": None, "no_identifier": False})
    if not (args.doi or args.ids or args.bib or args.records):
        text = sys.stdin.read()
        if text.lstrip()[:1] in ("{", "["):
            for rec, err in read_json_records(text, "stdin"):
                entries.append({"path": None, "record": rec, "orig": None, "error": err, "given_key": None, "no_identifier": False})
        else:
            from_ids(parse_id_lines(text, "stdin"))
    return entries


def index_out_dir(out_dir):
    """normalized id -> (path, has_item) for the records already in DIR."""
    index = {}
    for path in sorted(out_dir.glob("*.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and isinstance(rec.get("id"), str) and rec["id"].strip():
            index[normalize_id(rec["id"])] = (path, bool(rec.get("item")))
    return index


def unique_slug(base, ident, used, out_dir):
    """First of base, base-2, base-3 ... that is free (or already holds this very identifier)."""
    slug, n = base, 1
    while True:
        holder = used.get(slug)
        if holder is None and out_dir is not None and (out_dir / f"{slug}.json").exists():
            try:
                holder = normalize_id(str(json.loads((out_dir / f"{slug}.json").read_text(encoding="utf-8")).get("id") or "")) or "?"
            except (OSError, ValueError, AttributeError):
                holder = "?"
        if holder is None or holder == ident:
            used[slug] = ident
            return slug
        n += 1
        slug = f"{base}-{n}"


def process_entry(entry, schema, ctx):
    """Fill one entry's record; returns (summary, outcome). The record gets `code` only on failure."""
    rec = entry["record"]
    if entry["error"]:
        stem = entry["path"].stem if entry["path"] else "stdin"
        entry["record"] = {"slug": stem, "code": entry["error"]["code"], "detail": entry["error"]["detail"]}
        return {"slug": stem, "code": entry["error"]["code"], "detail": entry["error"]["detail"]}, "failed"
    if entry["given_key"] and not rec.get("citationKey"):
        rec["citationKey"] = entry["given_key"]
    ident = rec.get("id")
    ident = ident.strip() if isinstance(ident, str) else ""
    if isinstance(rec.get("item"), dict) and rec["item"]:
        # Already filled; with --out-dir it is still copied there, so keep the slug free of collisions.
        rec["slug"] = unique_slug(slug_for(rec, entry["given_key"]), normalize_id(ident) if ident else "?", ctx["used"], ctx["out_dir"])
        return {"slug": rec["slug"], "code": "skipped", "reason": "has_item", "id": ident}, "skipped"
    if not ident:
        rec["slug"] = rec.get("slug") or slug_for(rec, entry["given_key"])
        rec["code"] = "no_id"
        return {"slug": rec["slug"], "code": "no_id", "hint": "the record has no `id` to resolve"}, "failed"
    norm = normalize_id(ident)
    if norm in ctx["seen"]:
        rec["slug"] = rec.get("slug") or ctx["seen"][norm]
        return {"slug": rec["slug"], "code": "skipped", "reason": "duplicate", "id": ident}, "skipped"
    existing = ctx["existing"].get(norm)
    if existing and existing[1]:
        ctx["seen"][norm] = existing[0].stem
        return {"slug": existing[0].stem, "code": "skipped", "reason": "exists", "id": ident, "file": existing[0].name}, "skipped"
    if entry.get("no_identifier"):
        rec["slug"] = ctx["seen"][norm] = unique_slug(slug_for(rec, entry["given_key"]), norm, ctx["used"], ctx["out_dir"])
        rec["code"] = "no_identifier"
        return {"slug": rec["slug"], "code": "no_identifier", "id": ident,
                "hint": "no DOI or arXiv id in the source; search the title, then set `id` by hand"}, "failed"
    try:
        item, warnings, csl_type, unknown, doi, categories = fetch_and_map(ident, schema)
    except Failure as f:
        rec["slug"] = existing[0].stem if existing else unique_slug(slug_for(rec, entry["given_key"]), norm, ctx["used"], ctx["out_dir"])
        ctx["seen"][norm] = rec["slug"]
        rec["code"] = f.code
        for k in ("hint", "detail"):
            rec.pop(k, None)
        if f.hint:
            rec["hint"] = f.hint
        return {"slug": rec["slug"], "code": f.code, "id": ident, **{k: v for k, v in f.extra.items() if k != "input"},
                **({"hint": f.hint} if f.hint else {})}, "failed"
    rec["item"] = item
    if categories and not rec.get("tags"):
        rec["tags"] = category_tags(categories)
    for k in ("code", "hint", "detail"):
        rec.pop(k, None)
    if warnings:
        rec["warnings"] = warnings
    else:
        rec.pop("warnings", None)
    rec["slug"] = existing[0].stem if existing else unique_slug(slug_for(rec, entry["given_key"]), norm, ctx["used"], ctx["out_dir"])
    ctx["seen"][norm] = rec["slug"]
    summary = {"slug": rec["slug"], "code": "ok", "id": ident, "itemType": item["itemType"], "title": item.get("title", "")[:80]}
    if rec.get("citationKey"):
        summary["citationKey"] = rec["citationKey"]
    if warnings:
        summary["warnings"] = warnings
    return summary, "ok"


def wants_candidates(entry, summary, outcome, args):
    """Newly drafted arXiv preprints; with --candidates also records that already had an item (unless they have
    candidates already, or --refresh)."""
    rec = entry["record"]
    if not isinstance(rec, dict) or rec.get("code") or not isinstance(rec.get("item"), dict) or not is_preprint_draft(rec):
        return False
    if outcome == "ok":
        return True
    if args.candidates and summary.get("reason") == "has_item":
        if "published_candidates" in rec and not args.refresh:
            summary["reason"] = "has_candidates"
            return False
        return True
    return False


def run_stream(args):
    entries = collect_entries(args)
    if not entries:
        emit("no_records", 1, "pass --doi / --ids / --bib, record paths, or feed identifiers or records on stdin")
    schema = None
    if any(not e["error"] and not (isinstance(e["record"].get("item"), dict) and e["record"]["item"]) for e in entries):
        try:
            schema = fetch_schema(args.base_url)
        except Failure as f:
            emit(f.code, f.exit_code, f.hint, **f.extra)
    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    ctx = {"seen": {}, "used": {}, "out_dir": out_dir, "existing": index_out_dir(out_dir) if out_dir else {}}

    def save(entry, summary):
        rec = entry["record"]
        if out_dir and rec is not None and summary.get("reason") not in ("exists", "duplicate"):
            path = out_dir / f"{rec['slug']}.json"
            write_record(path, rec)
            summary["file"] = path.name
        elif args.in_place and entry["path"] and rec is not None and not entry["error"] \
                and json.dumps(rec, sort_keys=True) != entry["orig"]:
            write_record(entry["path"], rec)

    results = []
    for entry in entries:
        summary, outcome = process_entry(entry, schema, ctx)
        save(entry, summary)  # drafts are on disk before the (slower) candidate lookups
        results.append([entry, summary, outcome])
    if not args.no_candidates:
        todo = [r for r in results if wants_candidates(*r, args)]
        if todo:
            notes = add_candidates([entry["record"] for entry, _, _ in todo])
            for r in todo:
                entry, summary, outcome = r
                rec = entry["record"]
                if outcome == "skipped":  # --candidates on a record drafted earlier
                    r[1] = summary = {"slug": rec["slug"], "code": "ok", "id": summary.get("id"),
                                      "title": str(rec["item"].get("title") or "")[:80]}
                    r[2] = "ok"
                summary.update(candidates_summary(rec, notes.get(id(rec), {})))
                save(entry, summary)
    return write_results([(e["path"], e["record"], s, o) for e, s, o in results], quiet=bool(args.in_place or out_dir))


def parse_args():
    ap = argparse.ArgumentParser(
        description="Resolve DOIs / arXiv ids to Zotero item drafts: one --doi with --out (v1), or a stream of records.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doi", action="append", default=[], metavar="ID",
                    help="DOI, doi.org URL, 'doi:' form, arXiv id (with or without 'arXiv:' / version) or arXiv URL; repeatable")
    ap.add_argument("--ids", metavar="FILE", help="list of `identifier[<TAB>citation key]`, one per line; '#' comments and blank lines skipped")
    ap.add_argument("--bib", metavar="FILE", help="BibTeX file: each entry's key becomes citationKey; id from doi / eprint / arXiv URL, else the title")
    ap.add_argument("--out", metavar="FILE", help="v1 single mode (exactly one --doi): write the item JSON draft here")
    ap.add_argument("--out-dir", metavar="DIR", help="stream mode: write one record per identifier to DIR/<slug>.json; existing records are kept")
    ap.add_argument("-i", "--in-place", action="store_true", help="write each record back to its file; stdout gets one summary line per record")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, metavar="URL",
                    help=f"Zotero local API base for GET /api/schema (default {DEFAULT_BASE_URL}; proxy is bypassed)")
    ap.add_argument("--no-candidates", action="store_true",
                    help="draft only: no published_candidates lookup for arXiv ids (stream mode looks them up by default)")
    ap.add_argument("--candidates", action="store_true",
                    help="also records that already have a preprint item: add published_candidates (item untouched); "
                         "records whose candidates are complete are skipped")
    ap.add_argument("--refresh", action="store_true", help="with --candidates: look up again records that have them")
    ap.add_argument("--redraft", metavar="DOI|URL",
                    help="swap ONE record's preprint item for its published version, given by DOI or by its official page "
                         "(citation_* meta); slug, citationKey, tags, collection kept; see the module docstring")
    ap.add_argument("records", nargs="*", metavar="RECORD", help="existing record files whose `item` is to be filled")
    args = ap.parse_args()
    if args.redraft:
        if len(args.records) != 1 or args.doi or args.ids or args.bib or args.out or args.out_dir or args.candidates \
                or args.no_candidates or args.refresh:
            ap.error("--redraft takes exactly one record path (and -i to write it back), nothing else")
        return args
    if args.candidates and (args.no_candidates or args.out):
        ap.error("--candidates is a stream-mode lookup: not with --no-candidates or --out")
    if args.refresh and not args.candidates:
        ap.error("--refresh goes with --candidates")
    if args.out:
        if len(args.doi) != 1 or args.ids or args.bib or args.records or args.out_dir or args.in_place:
            ap.error("--out is the v1 single mode: exactly one --doi and nothing else (use --out-dir for a batch)")
    if args.in_place and args.out_dir:
        ap.error("-i writes records back to their files; --out-dir writes new ones - pick one")
    if args.in_place and not args.records:
        ap.error("-i needs record paths (stdin input cannot be written back)")
    if args.out_dir and args.records:
        ap.error("record paths are updated with -i, not copied to --out-dir")
    return args


def main():
    args = parse_args()
    if args.redraft:
        sys.exit(run_redraft(args))
    if args.out:
        run_single(args)
    sys.exit(run_stream(args))


if __name__ == "__main__":
    main()
