# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""List each record's full-text links (where a copy of the paper may be had), before any file is fetched.

Every record gets
  links: [{url, source, version, needs_browser}]   version: published | accepted | preprint | unknown
from three sources (--sources picks a subset):
  arxiv      the record's arXiv id (item.archiveID, an "arXiv: ..." line in extra, a 10.48550 DOI, an arxiv.org
             url or the record id) -> https://arxiv.org/pdf/<id>, version preprint; no request
  openalex   GET api.openalex.org/works/doi:<DOI>, with the config's openalex_key as the api_key parameter (a
             single-DOI lookup costs nothing; without a key it runs unkeyed). best_oa_location and every location
             that is open or has a pdf_url: pdf_url, else landing_page_url. OpenAlex already carries Unpaywall's
             repository copies
  europepmc  GET www.ebi.ac.uk/europepmc/webservices/rest/search, query DOI:"<DOI>", resultType=core: the result
             with this DOI gives its open (OA) or free (F) fullTextUrlList entries, one per site (pdf > html >
             doi); when the paper is in PMC and no PMC link came from anywhere, its PMC article page
             https://pmc.ncbi.nlm.nih.gov/articles/<PMCID>/ is added
Library discovery systems and aggregators are not queried here: the agent uses them in the browser
(references/publishers.md).

Version of a link, first rule that applies:
  1. arxiv.org, biorxiv.org, medrxiv.org -> preprint;
  2. PMC and Europe PMC hosts -> Europe PMC's answer for the paper (a preprint record -> preprint, an author
     manuscript -> accepted, else published), unknown when Europe PMC did not answer (OpenAlex labels publisher
     PDFs in PMC submittedVersion); Europe PMC's DOI-site link -> published (preprint for a preprint record);
  3. a repository location (OpenAlex source.type repository, a third-party Europe PMC site) -> unknown: an
     institutional repository entry can be metadata without a PDF, so only the fetched and checked file says
     what it is;
  4. OpenAlex's label: publishedVersion -> published, acceptedVersion -> accepted, submittedVersion -> preprint;
     none -> unknown.
Links are deduplicated by URL (arXiv URLs and arXiv DOIs reduce to https://arxiv.org/pdf/<id>, PMC article URLs
to https://pmc.ncbi.nlm.nih.gov/articles/PMC<n>/; scheme, host case and a trailing slash are ignored); a
duplicate keeps the more specific version. Order: published, accepted, preprint, unknown; within one version
plain-HTTP hosts first, then unknown hosts, then browser-only ones.

needs_browser comes from NEEDS_BROWSER below (a host or any parent domain): true for PMC, Europe PMC,
medRxiv / bioRxiv, JAMA and the aggregators, and for hosts under the config's institution.proxy; false for arXiv
and the open proceedings hosts; null (unknown) otherwise, so HTTP is tried first. The table is a starting point:
add a host once a run has shown which way it goes.

Stream: record files as arguments or records on stdin (JSONL, an array or one object). A record that already has
`links` is skipped (reason has_links) unless --refresh. A source that fails or cannot run never fails the
record: its code goes into the summary line (`sources`) and the links it gave last time are kept; with
--refresh only the sources that answered replace their own links. When no source answers at all, nothing is
written (no_answer), so a rerun tries again. Without -i the full records go to stdout as JSONL and the summary
lines to stderr; with -i each record is written back to its file and stdout gets one summary line per record
plus {"summary": {...}}.

Requests are paced per host inside this process (the bulk lookups run in the main conversation only); a host
that answers 429 is not asked again in this run (source_blocked). Only GET requests, through the normal proxy
settings; env OPENALEX_BASE_URL and EUROPEPMC_BASE_URL override the hosts (tests). The key travels only as a
query parameter; logged URLs carry no query string. Exit 0 = every record ok or skipped, 1 = some failed, 2 = the
config file cannot be read.
"""

import argparse
import html
import http.client
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OPENALEX_BASE_URL = os.environ.get("OPENALEX_BASE_URL", "https://api.openalex.org").rstrip("/")
EUROPEPMC_BASE_URL = os.environ.get("EUROPEPMC_BASE_URL", "https://www.ebi.ac.uk").rstrip("/")
USER_AGENT = "paper-to-zotero/fulltext_links (stdlib urllib)"

SOURCES = ("arxiv", "openalex", "europepmc")
# The host each source is paced and stopped under: the real service, also when a test points the base URL elsewhere.
SOURCE_HOSTS = {"openalex": "api.openalex.org", "europepmc": "www.ebi.ac.uk"}
PACE_INTERVALS = {"api.openalex.org": 0.1, "www.ebi.ac.uk": 0.2}
VERSIONS = ("published", "accepted", "preprint", "unknown")
VERSION_RANK = {v: n for n, v in enumerate(VERSIONS)}
VERSION_LABELS = {"publishedVersion": "published", "acceptedVersion": "accepted", "submittedVersion": "preprint"}

# needs_browser by host; a parent domain covers its subdomains. Unlisted -> None (HTTP is tried first).
NEEDS_BROWSER = {
    "www.ncbi.nlm.nih.gov": True,   # PMC answers curl with a JavaScript check; a reCAPTCHA on the PDF link
    "pmc.ncbi.nlm.nih.gov": True,
    "europepmc.org": True,          # ?pdf=render answers curl with HTML; the article pages are a JavaScript app
    "medrxiv.org": True,            # Cloudflare; a few automated requests get the whole browser blocked
    "biorxiv.org": True,
    "jamanetwork.com": True,        # 403 to plain HTTP, "Host Needed" through the proxy: PMC is the route
    "proquest.com": True,           # aggregators, reached through the institution
    "ovid.com": True,
    "ebscohost.com": True,
    "arxiv.org": False,             # preprint server and open proceedings: a plain GET returns the PDF
    "raw.githubusercontent.com": False,
    "proceedings.mlr.press": False,
    "proceedings.neurips.cc": False,
    "proceedings.iclr.cc": False,
    "aclanthology.org": False,
    "openaccess.thecvf.com": False,
    "papers.miccai.org": False,
}
FIXED_VERSION = {"arxiv.org": "preprint", "biorxiv.org": "preprint", "medrxiv.org": "preprint"}
PMC_HOSTS = ("ncbi.nlm.nih.gov", "europepmc.org")
EPMC_OPEN = {"OA", "F"}  # open access, free to read; S (subscription), R (registration) are not full-text links
EPMC_STYLE_RANK = {"pdf": 0, "html": 1, "doi": 2}
EPMC_OWN_SITES = {"Europe_PMC", "PubMedCentral", "DOI"}

ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})"
ARXIV_URL = re.compile(rf"^https?://(?:www\.|export\.)?arxiv\.org/(?:abs|pdf)/({ARXIV_ID})(?:v\d+)?(?:\.pdf)?/?(?:[?#].*)?$", re.I)
ARXIV_DOI_URL = re.compile(rf"^https?://(?:dx\.)?doi\.org/10\.48550/arxiv\.({ARXIV_ID})(?:v\d+)?/?$", re.I)
PMC_URL = re.compile(r"^https?://(?:www\.ncbi\.nlm\.nih\.gov/pmc|pmc\.ncbi\.nlm\.nih\.gov)/articles/(?:PMC)?(\d+)(/.*)?$", re.I)
ANSWERED = ("ok", "not_found")

EPILOG = """\
summary codes: ok | skipped (has_links) | no_identifier (no DOI or arXiv id) | no_answer (no source answered;
nothing written) | unreadable / invalid_json / invalid_record (input)
source codes (summary `sources`): ok | not_found | no_identifier | source_blocked (429 earlier in this run) |
http_<n> | network_error | bad_response
examples:
  uv run fulltext_links.py -i records/*.json
  uv run fulltext_links.py --sources arxiv,europepmc -i records/x.json
config: ${PAPER_TO_ZOTERO_CONFIG:-~/.config/paper-to-zotero/config.json} -> openalex_key, institution.proxy
"""


def log(msg):
    print(msg, file=sys.stderr)


# ------------------------------------------------------------------ config

def load_config():
    path = Path(os.environ.get("PAPER_TO_ZOTERO_CONFIG") or Path.home() / ".config" / "paper-to-zotero" / "config.json")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise SystemExit(json.dumps({"code": "bad_config", "config": str(path), "detail": str(e),
                                     "hint": "fix the config file or move it away"}))
    return cfg if isinstance(cfg, dict) else {}


def config_str(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


# ------------------------------------------------------------------ HTTP

class SourceStop(Exception):
    """A source gave no answer for this record; `code` goes into the summary line."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def get_json(ctx, host, url, params=None):
    """Paced GET under `host` -> parsed JSON, or SourceStop. A 429 stops the host for the rest of the run."""
    if host in ctx["stopped"]:
        raise SourceStop("source_blocked")
    wait = ctx["last"].get(host, 0.0) + PACE_INTERVALS.get(host, 1.0) - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    ctx["last"][host] = time.monotonic()
    query = "?" + urllib.parse.urlencode(params) if params else ""
    req = urllib.request.Request(url + query, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            log(f"GET {url} -> {resp.status}")
    except urllib.error.HTTPError as e:
        log(f"GET {url} -> {e.code}")
        if e.code == 429:
            ctx["stopped"].add(host)
            raise SourceStop("source_blocked")
        raise SourceStop("not_found" if e.code == 404 else f"http_{e.code}")
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e:
        log(f"GET {url} -> {type(getattr(e, 'reason', None) or e).__name__}")
        raise SourceStop("network_error")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise SourceStop("bad_response")


# ------------------------------------------------------------------ identifiers

def strip_doi(value):
    s = value.strip() if isinstance(value, str) else ""
    s = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", s, flags=re.I).strip()
    return s if re.fullmatch(r"10\.\d{4,9}/\S+", s) else None


def identifiers(rec):
    """{doi, arxiv} from the record's item (DOI, extra, archiveID, url) and its id."""
    item = rec.get("item") if isinstance(rec.get("item"), dict) else {}
    extra = item.get("extra") if isinstance(item.get("extra"), str) else ""
    rid = rec.get("id") if isinstance(rec.get("id"), str) else ""
    doi = strip_doi(item.get("DOI"))
    if not doi:
        m = re.search(r"(?im)^\s*DOI:\s*(10\.\d{4,9}/\S+)", extra)
        doi = m.group(1) if m else strip_doi(item.get("url")) or strip_doi(rid)
    m = re.search(rf"(?im)^\s*arxiv(?:\s*id)?\s*:\s*({ARXIV_ID})", extra)
    arxiv = m.group(1) if m else None
    for value in (item.get("archiveID"), doi, item.get("url"), rid):
        if arxiv or not isinstance(value, str):
            continue
        m = (re.fullmatch(rf"\s*(?:arxiv:\s*)?({ARXIV_ID})(?:v\d+)?\s*", value, re.I)
             or re.fullmatch(rf"\s*10\.48550/arxiv\.({ARXIV_ID})(?:v\d+)?\s*", value, re.I)
             or ARXIV_URL.match(value.strip()))
        if m:
            arxiv = m.group(1)
    return {"doi": doi, "arxiv": arxiv}


def pmcid_of(value):
    m = re.search(r"(?:PMC)?(\d+)/?$", str(value or "").strip(), re.I)
    return f"PMC{m.group(1)}" if m and value else None


# ------------------------------------------------------------------ links

def url_host(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def lookup(host, table):
    """The table's value for the host or its closest listed parent domain; None when none is listed."""
    parts = host.split(".")
    for i in range(len(parts) - 1):
        if ".".join(parts[i:]) in table:
            return table[".".join(parts[i:])]
    return None


def under(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def canonical_url(url):
    """arXiv abs/pdf URLs and arXiv DOIs -> https://arxiv.org/pdf/<id>; PMC article URLs -> pmc.ncbi.nlm.nih.gov."""
    url = html.unescape(url.strip())
    m = ARXIV_URL.match(url) or ARXIV_DOI_URL.match(url)
    if m:
        return f"https://arxiv.org/pdf/{m.group(1)}"
    m = PMC_URL.match(url)
    if m:
        return f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{m.group(1)}{m.group(2) or '/'}"
    return url


def dedupe_key(url):
    parts = urllib.parse.urlsplit(url)
    return f"{(parts.hostname or '').lower()}{parts.path.rstrip('/')}{'?' + parts.query if parts.query else ''}"


def raw_link(url, source, claim=None, repository=False):
    return {"url": url, "source": source, "claim": claim, "repository": repository}


def link_version(host, claim, repository, pmc_version):
    fixed = lookup(host, FIXED_VERSION)
    if fixed:
        return fixed
    if under(host, PMC_HOSTS):
        return pmc_version or "unknown"
    if repository:
        return "unknown"
    return claim if claim in VERSION_RANK else "unknown"


def finalize(raws, pmc_version, in_pmc, proxy):
    """Raw links -> the record's links: version and needs_browser decided, deduplicated, ordered."""
    if in_pmc and not any(under(url_host(canonical_url(r["url"])), ["ncbi.nlm.nih.gov"]) for r in raws):
        raws = raws + [raw_link(f"https://pmc.ncbi.nlm.nih.gov/articles/{in_pmc}/", "europepmc")]
    kept = {}
    for seq, r in enumerate(raws):
        if not isinstance(r.get("url"), str) or not re.match(r"https?://", r["url"].strip(), re.I):
            continue
        url = canonical_url(r["url"])
        host = url_host(url)
        if not host:
            continue
        version = r["version"] if r.get("version") in VERSION_RANK else link_version(host, r.get("claim"),
                                                                                     r.get("repository"), pmc_version)
        browser = True if proxy and under(host, [proxy.lower().lstrip(".")]) else lookup(host, NEEDS_BROWSER)
        link = {"url": url, "source": r["source"], "version": version, "needs_browser": browser}
        key = dedupe_key(url)
        if key not in kept:
            kept[key] = (seq, link)
        elif VERSION_RANK[version] < VERSION_RANK[kept[key][1]["version"]]:
            kept[key] = (kept[key][0], {**link, "url": kept[key][1]["url"]})  # first spelling, better version
    browser_rank = {False: 0, None: 1, True: 2}
    ordered = sorted(kept.values(), key=lambda p: (VERSION_RANK[p[1]["version"]], browser_rank[p[1]["needs_browser"]], p[0]))
    return [link for _, link in ordered]


# ------------------------------------------------------------------ sources (each -> {"links": [...]} or SourceStop)

def src_arxiv(ids, ctx):
    if not ids["arxiv"]:
        raise SourceStop("no_identifier")
    return {"links": [raw_link(f"https://arxiv.org/pdf/{ids['arxiv']}", "arxiv", "preprint")]}


def src_openalex(ids, ctx):
    if not ids["doi"]:
        raise SourceStop("no_identifier")
    work = get_json(ctx, SOURCE_HOSTS["openalex"], f"{OPENALEX_BASE_URL}/works/doi:{urllib.parse.quote(ids['doi'], safe='/')}",
                    {"api_key": ctx["key"]} if ctx["key"] else None)
    if not isinstance(work, dict):
        raise SourceStop("bad_response")
    links = []
    for loc in [work.get("best_oa_location")] + list(work.get("locations") or []):
        if not isinstance(loc, dict) or not (loc.get("is_oa") or loc.get("pdf_url")):
            continue
        url = loc.get("pdf_url") or loc.get("landing_page_url")
        source = loc.get("source") if isinstance(loc.get("source"), dict) else {}
        if url:
            links.append(raw_link(url, "openalex", VERSION_LABELS.get(loc.get("version")), source.get("type") == "repository"))
    return {"links": links}


def src_europepmc(ids, ctx):
    if not ids["doi"] or ids["doi"].lower().startswith("10.48550/arxiv."):
        raise SourceStop("no_identifier")
    data = get_json(ctx, SOURCE_HOSTS["europepmc"], f"{EUROPEPMC_BASE_URL}/europepmc/webservices/rest/search",
                    {"query": f'DOI:"{ids["doi"]}"', "resultType": "core", "format": "json", "pageSize": "5"})
    results = ((data.get("resultList") or {}).get("result") or []) if isinstance(data, dict) else None
    if results is None:
        raise SourceStop("bad_response")
    hit = next((r for r in results if isinstance(r, dict) and str(r.get("doi") or "").lower() == ids["doi"].lower()), None)
    if hit is None:
        raise SourceStop("not_found")
    if hit.get("source") == "PPR":
        version = "preprint"
    elif any(hit.get(k) == "Y" for k in ("authMan", "epmcAuthMan", "nihAuthMan")):
        version = "accepted"
    else:
        version = "published"
    best = {}
    for entry in ((hit.get("fullTextUrlList") or {}).get("fullTextUrl") or []):
        if not isinstance(entry, dict) or entry.get("availabilityCode") not in EPMC_OPEN or not entry.get("url"):
            continue
        style, site = entry.get("documentStyle"), entry.get("site") or ""
        if style in EPMC_STYLE_RANK and (site not in best or EPMC_STYLE_RANK[style] < EPMC_STYLE_RANK[best[site]["documentStyle"]]):
            best[site] = entry
    # The DOI site is the publisher's (or preprint server's) own copy; sites other than PMC and Europe PMC are
    # third-party copies ("Unpaywall": HAL and the like): unknown.
    links = []
    for site, e in best.items():
        if site == "DOI":
            links.append(raw_link(e["url"], "europepmc", "preprint" if version == "preprint" else "published"))
        else:
            links.append(raw_link(e["url"], "europepmc", version, repository=site not in EPMC_OWN_SITES))
    return {"links": links, "pmc_version": version,
            "in_pmc": pmcid_of(hit.get("pmcid")) if hit.get("inPMC") == "Y" else None}


SOURCE_FUNCS = {"arxiv": src_arxiv, "openalex": src_openalex, "europepmc": src_europepmc}


# ------------------------------------------------------------------ records

def read_json_records(text, source):
    """Parse JSONL, a JSON array or one object into a list of [record|None, error|None]."""
    text = text.strip()
    if not text:
        return []
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        entries = []
        for n, ln in enumerate(text.splitlines(), 1):
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError as e:
                entries.append([None, {"code": "invalid_json", "detail": f"{source} line {n}: {e.msg}"}])
                continue
            entries.append([rec, None] if isinstance(rec, dict) else [None, {"code": "invalid_record", "detail": f"{source} line {n}"}])
        return entries
    return [[rec, None] if isinstance(rec, dict) else [None, {"code": "invalid_record", "detail": source}]
            for rec in (obj if isinstance(obj, list) else [obj])]


def load_entries(paths):
    """One entry per record: {path, record, orig, error}; unreadable files become failed entries."""
    if not paths:
        return [{"path": None, "record": rec, "orig": None, "error": err} for rec, err in read_json_records(sys.stdin.read(), "stdin")]
    entries = []
    for raw in paths:
        path = Path(raw)
        try:
            parsed = read_json_records(path.read_text(encoding="utf-8"), str(path))
        except (OSError, UnicodeDecodeError) as e:
            entries.append({"path": path, "record": None, "orig": None, "error": {"code": "unreadable", "detail": f"{path}: {e}"}})
            continue
        if len(parsed) != 1 or parsed[0][0] is None:
            err = parsed[0][1] if parsed and parsed[0][1] else {"code": "invalid_record", "detail": f"{path}: expected one object"}
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
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def process(rec, ctx):
    """Fill one record's links; returns (summary, outcome ok|skipped|failed)."""
    slug = rec.get("slug") or ""
    if "links" in rec and not ctx["refresh"]:
        return {"slug": slug, "code": "skipped", "reason": "has_links", "links": len(rec.get("links") or [])}, "skipped"
    ids = identifiers(rec)
    if not (ids["doi"] or ids["arxiv"]):
        return {"slug": slug, "code": "no_identifier",
                "hint": "the record has no DOI or arXiv id; fill item.DOI / extra, or look for copies in the browser"}, "failed"
    statuses, answers = {}, {}
    for name in ctx["run"]:
        try:
            answers[name] = SOURCE_FUNCS[name](ids, ctx)
            statuses[name] = "ok"
        except SourceStop as stop:
            statuses[name] = stop.code
    answered = {name for name, code in statuses.items() if code in ANSWERED}
    if not answered:
        return {"slug": slug, "code": "no_answer", "sources": statuses,
                "hint": "no source answered; nothing written - rerun later"}, "failed"
    raws = [r for answer in answers.values() for r in answer["links"]]
    old = rec.get("links") if isinstance(rec.get("links"), list) else []
    # Links from sources that did not answer this time are kept, already decided.
    raws += [{**o, "claim": None, "repository": False} for o in old if isinstance(o, dict) and o.get("source") not in answered]
    epmc = answers.get("europepmc") or {}
    rec["links"] = links = finalize(raws, epmc.get("pmc_version"), epmc.get("in_pmc"), ctx["proxy"])
    summary = {"slug": slug, "code": "ok", "links": len(links), "sources": statuses}
    if links:
        summary["first"] = {k: links[0][k] for k in ("version", "needs_browser")} | {"host": url_host(links[0]["url"])}
    return summary, "ok"


def run(args):
    cfg = load_config()
    inst = cfg.get("institution") if isinstance(cfg.get("institution"), dict) else {}
    ctx = {"refresh": args.refresh, "run": args.sources, "key": config_str(cfg.get("openalex_key")),
           "proxy": config_str(inst.get("proxy")), "last": {}, "stopped": set()}
    entries = load_entries(args.records)
    if not entries:
        print(json.dumps({"code": "no_records", "hint": "pass record files or feed records on stdin"}))
        return 1
    counts = {"total": len(entries), "ok": 0, "skipped": 0, "failed": 0}
    for entry in entries:
        rec = entry["record"]
        if entry["error"]:
            summary, outcome = {"slug": entry["path"].stem if entry["path"] else "stdin", **entry["error"]}, "failed"
        else:
            summary, outcome = process(rec, ctx)
            if not summary.get("slug") and entry["path"]:
                summary["slug"] = entry["path"].stem
        counts[outcome] += 1
        if args.in_place:
            if rec is not None and entry["path"] and json.dumps(rec, sort_keys=True) != entry["orig"]:
                write_record(entry["path"], rec)
            print(json.dumps(summary, ensure_ascii=False))
        else:
            print(json.dumps(rec if rec is not None else summary, ensure_ascii=False))
            log(json.dumps(summary, ensure_ascii=False))
    final = dict(counts)
    if "openalex" in ctx["run"] and not ctx["key"]:
        final["openalex_key"] = False
    if ctx["stopped"]:
        final["stopped"] = sorted(ctx["stopped"])
    print(json.dumps({"summary": final}, ensure_ascii=False), file=sys.stdout if args.in_place else sys.stderr)
    return 1 if counts["failed"] else 0


def source_list(text):
    names = [s.strip().lower() for s in text.split(",") if s.strip()]
    bad = [s for s in names if s not in SOURCES]
    if bad or not names:
        raise argparse.ArgumentTypeError(f"unknown source(s) {', '.join(bad) or '(none)'}; choose from {','.join(SOURCES)}")
    return [s for s in SOURCES if s in names]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Full-text links for each record (records get `links`).",
                                 epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("records", nargs="*", metavar="RECORD", help="record files; none = read records from stdin")
    ap.add_argument("-i", "--in-place", action="store_true",
                    help="write each record back to its file; stdout gets one summary line per record")
    ap.add_argument("--sources", type=source_list, default=list(SOURCES), metavar="LIST",
                    help=f"comma-separated subset of {','.join(SOURCES)} (default: all)")
    ap.add_argument("--refresh", action="store_true",
                    help="query records that already have links; answering sources replace their own links")
    args = ap.parse_args(argv)
    if args.in_place and not args.records:
        ap.error("-i needs record paths (stdin input cannot be written back)")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
