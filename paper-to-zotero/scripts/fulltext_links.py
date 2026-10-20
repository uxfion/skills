#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""List where copies of each record's paper may be had, before any file is fetched: the record's `links`.

links: {items: [{url, source, version: published | accepted | preprint | unknown, needs_browser}], incomplete?}, from:
  arxiv      the item's arXiv id (archiveID, an "arXiv:" line in Extra, a 10.48550 DOI, an arxiv.org url) ->
             https://arxiv.org/pdf/<id>, a preprint; no request
  openalex   GET api.openalex.org/works/doi:<DOI>, with the config's openalex_key as api_key when there is one (a
             single-DOI lookup then costs nothing): best_oa_location and every location that is open or has a pdf_url
             (its pdf_url, else its landing page). OpenAlex already carries Unpaywall's repository copies
  europepmc  GET www.ebi.ac.uk/europepmc/webservices/rest/search, DOI:"<DOI>", resultType core: the result with this
             DOI gives its open (OA) or free (F) full-text urls, one per site (pdf > html > doi); a paper in PMC
             without a PMC link from anywhere gets its PMC article page
  page       the item's url when it is the venue's own page for the paper (not doi.org, not a preprint server: a
             NeurIPS, PMLR or OpenReview page): the PDF the page declares (citation_pdf_url), the published version
Library discovery systems and aggregators are not asked here: fetch.py's routes use them.

A link's version, the first rule that applies: arxiv.org, biorxiv.org, medrxiv.org -> preprint; a PMC or Europe PMC
host -> Europe PMC's word on the paper (a preprint record, an author manuscript -> accepted, else published; unknown
when Europe PMC gave none); a repository location -> unknown (an institutional repository's entry can be metadata
without the PDF: only the checked file says); OpenAlex's label (publishedVersion, acceptedVersion,
submittedVersion); else unknown. Links are one per url (arXiv urls and DOIs reduce to https://arxiv.org/pdf/<id>,
PMC article urls to pmc.ncbi.nlm.nih.gov; scheme, host case and a trailing slash ignored), the more specific version
kept; ordered published, accepted, preprint, unknown, and within one plain-HTTP hosts, then unknown ones, then
browser-only ones. needs_browser comes from NEEDS_BROWSER below (a host or a parent domain; a host under the config's
institution.proxy is true) and is null for an unlisted host, which HTTP is tried on first; add a host once a run has
shown which way it goes.

`links` is computed again only when it is not done: absent, incomplete (a source did not answer: a network error,
a 5xx, a 429), or stale (the DOI, the arXiv id or item.url changed); each line says why (`reason`). A source that did
not answer is named in `incomplete`, and its links from the last time are kept. A host that answers 429 is not asked
again for the rest of the run (source_blocked), across runs of this script; requests to a host keep their gap.

stdout: one line per record {slug, code, reason?, links, sources: {source: its code}, first?}, then {"summary"}.
  ok              links written (`first`: the first link's version, needs_browser and host)
  no_identifier   no DOI, no arXiv id and no page of the venue's: nothing to look up
  no_answer       no source answered; `links` is written with every source incomplete, so a rerun asks again
  skipped         reason done: links up to date
Source codes: ok | not_found | no_identifier | refused (the page answered 401/403) | source_blocked | http_<n> |
network_error | bad_response. Exit 0 = every record ok or done; 1 = not; 2 = the config file is unreadable.

Example:
  uv run scripts/fulltext_links.py <work>/records/*.json
"""
import html
import re
import urllib.parse

from p2zlib import cli, config, paper, run, web

SOURCES = ("arxiv", "openalex", "europepmc", "page")
# The host each source is paced and stopped under: the real service's, also when a test points the url elsewhere.
HOSTS = {"openalex": "api.openalex.org", "europepmc": "www.ebi.ac.uk"}
VERSIONS = ("published", "accepted", "preprint", "unknown")
VERSION_RANK = {v: n for n, v in enumerate(VERSIONS)}
VERSION_LABELS = {"publishedVersion": "published", "acceptedVersion": "accepted", "submittedVersion": "preprint"}
ANSWERED = ("ok", "not_found", "no_identifier", "refused")

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
ARXIV_URL = re.compile(rf"^https?://(?:www\.|export\.)?arxiv\.org/(?:abs|pdf)/({paper.ARXIV_ID})(?:v\d+)?(?:\.pdf)?/?(?:[?#].*)?$", re.I)
ARXIV_DOI_URL = re.compile(rf"^https?://(?:dx\.)?doi\.org/10\.48550/arxiv\.({paper.ARXIV_ID})(?:v\d+)?/?$", re.I)
PMC_URL = re.compile(r"^https?://(?:www\.ncbi\.nlm\.nih\.gov/pmc|pmc\.ncbi\.nlm\.nih\.gov)/articles/(?:PMC)?(\d+)(/.*)?$", re.I)


# ---- links --------------------------------------------------------------------------------------------------

def lookup(host, table):
    """The table's value for the host or its closest listed parent domain; None when none is listed."""
    parts = host.split(".")
    return next((table[".".join(parts[i:])] for i in range(len(parts) - 1) if ".".join(parts[i:]) in table), None)


def under(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def canonical_url(url):
    """arXiv abs/pdf urls and arXiv DOIs -> https://arxiv.org/pdf/<id>; PMC article urls -> pmc.ncbi.nlm.nih.gov."""
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
    """Raw links -> the record's links: version and needs_browser decided, one per url, ordered."""
    if in_pmc and not any(under(web.host_of(canonical_url(r["url"])), ["ncbi.nlm.nih.gov"]) for r in raws):
        raws = raws + [raw_link(f"https://pmc.ncbi.nlm.nih.gov/articles/{in_pmc}/", "europepmc")]
    kept = {}
    for seq, r in enumerate(raws):
        if not isinstance(r.get("url"), str) or not re.match(r"https?://", r["url"].strip(), re.I):
            continue
        url = canonical_url(r["url"])
        host = web.host_of(url)
        if not host:
            continue
        version = r["version"] if r.get("version") in VERSION_RANK else link_version(host, r.get("claim"), r.get("repository"),
                                                                                     pmc_version)
        browser = True if proxy and under(host, [proxy]) else lookup(host, NEEDS_BROWSER)
        link = {"url": url, "source": r["source"], "version": version, "needs_browser": browser}
        key = dedupe_key(url)
        if key not in kept:
            kept[key] = (seq, link)
        elif VERSION_RANK[version] < VERSION_RANK[kept[key][1]["version"]]:
            kept[key] = (kept[key][0], {**link, "url": kept[key][1]["url"]})  # the first spelling, the better version
    browser_rank = {False: 0, None: 1, True: 2}
    ordered = sorted(kept.values(), key=lambda p: (VERSION_RANK[p[1]["version"]], browser_rank[p[1]["needs_browser"]], p[0]))
    return [link for _, link in ordered]


def venue_page(url):
    """The item's url when it is the venue's own page for the paper: not doi.org, not a preprint server's."""
    host = web.host_of(url or "")
    if not host or under(host, ["doi.org"]) or paper.preprint_server(url):
        return None
    return url


# ---- sources (each -> {"links": [...]} or web.NoData) ------------------------------------------------------

def src_arxiv(ids, ctx):
    if not ids["arxiv"]:
        raise web.NoData("no_identifier")
    return {"links": [raw_link(f"https://arxiv.org/pdf/{ids['arxiv']}", "arxiv", "preprint")]}


def src_openalex(ids, ctx):
    if not ids["doi"]:
        raise web.NoData("no_identifier")
    url = f"{web.endpoint('OPENALEX_BASE_URL', 'https://api.openalex.org')}/works/doi:{urllib.parse.quote(ids['doi'], safe='/')}"
    work = web.read_json(url, params={"api_key": ctx["key"]} if ctx["key"] else None, host=HOSTS["openalex"],
                         pacer=ctx["pacer"])
    if not isinstance(work, dict):
        raise web.NoData("bad_response")
    links = []
    for loc in [work.get("best_oa_location")] + list(work.get("locations") or []):
        if not isinstance(loc, dict) or not (loc.get("is_oa") or loc.get("pdf_url")):
            continue
        source = loc.get("source") if isinstance(loc.get("source"), dict) else {}
        if loc.get("pdf_url") or loc.get("landing_page_url"):
            links.append(raw_link(loc.get("pdf_url") or loc.get("landing_page_url"), "openalex",
                                  VERSION_LABELS.get(loc.get("version")), source.get("type") == "repository"))
    return {"links": links}


def src_europepmc(ids, ctx):
    if not ids["doi"]:
        raise web.NoData("no_identifier")
    data = web.read_json(f"{web.endpoint('EUROPEPMC_BASE_URL', 'https://www.ebi.ac.uk')}/europepmc/webservices/rest/search",
                         params={"query": f'DOI:"{ids["doi"]}"', "resultType": "core", "format": "json", "pageSize": "5"},
                         host=HOSTS["europepmc"], pacer=ctx["pacer"])
    results = ((data.get("resultList") or {}).get("result") or []) if isinstance(data, dict) else None
    if results is None:
        raise web.NoData("bad_response")
    hit = next((r for r in results if isinstance(r, dict) and str(r.get("doi") or "").lower() == ids["doi"]), None)
    if hit is None:
        raise web.NoData("not_found")
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
    # The DOI site is the publisher's (or the preprint server's) own copy; sites other than PMC and Europe PMC are
    # third-party copies (HAL and the like): unknown.
    links = []
    for site, e in best.items():
        if site == "DOI":
            links.append(raw_link(e["url"], "europepmc", "preprint" if version == "preprint" else "published"))
        else:
            links.append(raw_link(e["url"], "europepmc", version, repository=site not in EPMC_OWN_SITES))
    pmcid = re.search(r"(?:PMC)?(\d+)/?$", str(hit.get("pmcid") or ""), re.I)
    return {"links": links, "pmc_version": version, "in_pmc": f"PMC{pmcid.group(1)}" if pmcid and hit.get("inPMC") == "Y" else None}


def src_page(ids, ctx):
    if not ids["page"]:
        raise web.NoData("no_identifier")
    try:
        body, headers, final = web.read(ids["page"], full=True, pacer=ctx["pacer"], headers={"User-Agent": web.BROWSER_UA})
    except web.NoData as e:
        raise web.NoData("refused") if e.status in (401, 403) else e from None
    pdf = web.page_meta(body, final, headers)["pdf_url"]
    return {"links": [raw_link(pdf, "page", "published")] if pdf else []}


SOURCE_FUNCS = {"arxiv": src_arxiv, "openalex": src_openalex, "europepmc": src_europepmc, "page": src_page}


# ---- records ------------------------------------------------------------------------------------------------

def setup(args, records):
    config.read(strict=True)
    work = run.Work.of(records[0].path) if records else None
    return {"key": config.openalex_key(), "proxy": config.institution()["proxy"], "pacer": web.Pacer(work)}


def process(rec, ctx):
    due = run.due(rec, "links")
    if due is None:
        return cli.skipped("done", links=len(rec["links"]["items"]))
    doi, aid = paper.identifiers(rec.item)
    ids = {"doi": doi, "arxiv": aid, "page": venue_page(rec.item.get("url"))}
    if not any(ids.values()):
        return {"code": "no_identifier",
                "hint": "The item has no DOI, arXiv id or venue page; fill item.DOI / extra / url, or look for copies in the browser."}
    statuses, answers = {}, {}
    for name in SOURCES:
        try:
            answers[name] = SOURCE_FUNCS[name](ids, ctx)
            statuses[name] = "ok"
        except web.NoData as stop:
            statuses[name] = stop.code
    unanswered = sorted(name for name, code in statuses.items() if code not in ANSWERED)
    raws = [r for answer in answers.values() for r in answer["links"]]
    if due == "incomplete":  # the links a source gave last time stay while it does not answer
        raws += [{**o, "claim": None, "repository": False} for o in rec["links"].get("items") or []
                 if isinstance(o, dict) and o.get("source") in unanswered]
    epmc = answers.get("europepmc") or {}
    links = finalize(raws, epmc.get("pmc_version"), epmc.get("in_pmc"), ctx["proxy"])
    run.stamp(rec, "links", {"items": links}, incomplete=unanswered)
    line = {"reason": due, "links": len(links), "sources": statuses}
    if links:
        line["first"] = {"version": links[0]["version"], "needs_browser": links[0]["needs_browser"], "host": web.host_of(links[0]["url"])}
    if len(unanswered) == sum(1 for code in statuses.values() if code != "no_identifier"):
        return {"code": "no_answer", **line, "hint": "No source answered; run this (or p2z.py prepare) again later."}
    return {"code": "ok", **line}


def main(argv=None):
    return cli.main_records(__doc__, process, argv, setup=setup, dry_run=True)


if __name__ == "__main__":
    raise SystemExit(main())
