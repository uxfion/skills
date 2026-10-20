#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Draft records from DOIs and arXiv ids; look up a preprint's published versions; swap in the published version.

  doi_to_item.py --doi ID... | --ids FILE | --bib FILE  --out-dir <work>/records      draft
  doi_to_item.py <work>/records/*.json                                                published versions (prepare)
  doi_to_item.py --redraft <DOI | the paper's page> RECORD                             redraft

Draft. Each identifier (a DOI, doi.org url, "doi:" form, arXiv id with or without "arXiv:" or a version, arxiv.org
url) becomes <work>/records/<slug>.json: {id, citationKey?, item, tags?, warnings?}. The item is mapped from doi.org's
CSL JSON with the Zotero schema's CSL tables (and Crossref's type names). --ids lists `identifier[<TAB>citation key]`
per line ('#' comments); --bib takes each entry's key as the citation key and its doi, eprint or arXiv url as the
identifier. The slug is the citation key, else <first author's surname><year><first title word of 4+ letters>
(liu2022progressive), -2, -3 ... when taken. A record already there for the identifier (by its `id` or its item's
DOI or arXiv id) is kept as it is (skipped, reason exists); one there without an item is drafted in place, its other
fields kept. An identifier that cannot be drafted gets a line and no file, so a rerun tries it again.
Drafting rules beyond the field mapping:
  subtitle     a CSL subtitle is appended ("Title: Subtitle") unless the title already ends with it
  arXiv        the categories become automatic (type 1) tags as Zotero's arXiv translator writes them ("Machine
               Learning (cs.LG)" -> "Computer Science - Machine Learning", "Quantum Physics (quant-ph)" -> "Quantum
               Physics"; an archive outside its table keeps DataCite's wording; FOS entries dropped), when the record
               has no tags yet. No other tags: Crossref's subjects are journal categories, not the paper's keywords
  LNCS & co.   a book-chapter with an ISSN (doi.org gives the series as its container) asks Crossref once: a known
               proceedings series and a volume title -> conferencePaper, proceedingsTitle = the volume, series = the
               series; else bookSection with a warning
  warnings     a title like a notice (Correction to: ..., Author Correction, Erratum, Retraction Note, RETRACTED: ...),
               an article without authors, or one page that is not an article number: maybe a notice, not the paper;
               a DOI for NeurIPS's printed proceedings (10.52202/...) leads to a sales page
Draft lines: {id, cite?, code, slug?, itemType?, title?, warnings?} (an identifier has no slug until its record is
written).
  ok                    drafted
  skipped               reason exists (a record is there) | duplicate (named twice in this run)
  no_identifier         neither a DOI nor an arXiv id (a --bib entry: id is its title)
  not_found             doi.org does not know the DOI
  no_csl_record         doi.org answered with no CSL record (a landing page): write the item by hand
  doi_org_error         doi.org or the DOI's agency failed on this DOI (5xx): rerun later
  doi_org_unreachable   2: the network or proxy is down; the identifiers after it are not_run
  source_blocked        2: doi.org answered 429; nothing is asked of it before `until` (pace.json of the work
                        directory), the identifiers after it are not_run

Published versions. A record whose item is still the preprint (itemType preprint, or the arXiv DOI) gets
`published_candidates`: {items: [{doi, venue, year, title, url?, sources: [arxiv | crossref], title_differs, type?,
journal_ref?}], comment?: arXiv's comment ("Accepted at ICLR 2024"), incomplete?}, one item per published version:
  arxiv     the journal_ref and DOI the authors gave arXiv (one API call per 100 records); a DOI is completed from
            Crossref, a journal_ref alone is an item without a DOI
  crossref  a title (+ first author) search: works whose title is at least 0.9 alike, arXiv DOIs and posted content
            (other preprints) left out
title_differs compares with the item's title and alt_titles. The item itself never changes. What neither source
finds (venues without DOIs: ICLR, ICML, TMLR ...) the agent looks up on papers.cool; the comment often names the
venue. The block is computed again only when it is not done: absent, incomplete (a source did not answer; what it
gave last time stays), or stale (the arXiv id or the title changed). A record whose item is not a preprint has no
such block (it goes once a redraft made the item the published version).
Lines: {slug, code, reason?, candidates?, comment?, sources: {arxiv, crossref: ok | no_title | source_blocked |
network_error | http_<n> | bad_response}}.
  ok          computed       no_answer   no source answered: rerun later       no_item   the record has no item
  skipped     reason done | not_preprint

Redraft. --redraft <DOI | page url> RECORD replaces the record's item by the published version: every other field
stays; `extra` gains "arXiv: <id>"; the old title goes to alt_titles when it differs. The blocks computed from the
old item are then stale, and the next prepare computes them again. A DOI is drafted as above, keeping the preprint's
abstract when the DOI record has none. A page (NeurIPS, PMLR, ACL Anthology, OpenReview ...) is read over plain HTTP:
its citation_* tags give a conferencePaper (a conference title, or a journal title naming proceedings, as NeurIPS
pages give theirs), a journalArticle (a journal title, TMLR too) or a bookSection, with the preprint's creators and
abstract where the page has none; its PDF link is fulltext_links' to list (source page).
  ok           redrafted
  skipped      reason same_doi: the item has that DOI already
  already_saved     the record is saved (or being saved) to Zotero: change the item there (update_item.py)
  not_published     a 10.48550 DOI is the preprint itself
  no_citation_meta  the page has no citation_title tag: fill the item by hand from what the page shows
  page_unreachable  the page refuses a plain HTTP request: read it in the browser and fill the item by hand
  source_blocked    the page's host answered 429

Exit 0 = every line ok or skipped; 1 = not; 2 = cannot go on (Zotero not running or its local API off, doi.org down
or blocked). Requests keep a gap per host, shared by the work directory's scripts (pace.json); env DOI_BASE_URL,
CROSSREF_BASE_URL, ARXIV_API_URL point the services elsewhere (tests). Only GET requests.
"""
import html
import json
import re
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from p2zlib import cli, paper, run, web, zotero

CSL_ACCEPT = "application/vnd.citationstyles.csl+json"
# The hosts requests are paced and stopped under: the real services', also when a test points the urls elsewhere.
HOST_DOI, HOST_CROSSREF, HOST_ARXIV = "doi.org", "api.crossref.org", "export.arxiv.org"
ANSWERED = ("ok", "no_title")
CANDIDATE_SIMILARITY = 0.9
# NeurIPS 2022-2025 DOIs, registered for the printed proceedings: they lead to its sales page, not to the paper.
SALES_PAGE_DOI = re.compile(r"^10\.52202/", re.I)

# Book series whose volumes are conference proceedings, as Crossref names them: a chapter in one is a conference paper.
# A living list: add a series when one shows up.
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

# arXiv archives that Zotero's arXiv translator writes as "<Archive> - <Category>"; a category without a subject
# class (quant-ph, hep-th, gr-qc, ...) is written as its name alone.
ARXIV_ARCHIVES = {
    "cs": "Computer Science", "econ": "Economics", "eess": "Electrical Engineering and Systems Science",
    "math": "Mathematics", "nlin": "Nonlinear Sciences", "physics": "Physics", "q-bio": "Quantitative Biology",
    "q-fin": "Quantitative Finance", "stat": "Statistics", "astro-ph": "Astrophysics", "cond-mat": "Condensed Matter",
}
ARXIV_CATEGORY = re.compile(r"(.+?)\s*\(([a-z][a-z-]*)(?:\.([A-Za-z][A-Za-z-]*))?\)")
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

# Item types where a one-page notice can pass for the paper; titles are checked for every type.
ERRATUM_TYPES = {"journalArticle", "conferencePaper", "bookSection"}
# Crossref's type vocabulary -> Zotero itemType (Crossref does not use CSL's).
CROSSREF_TYPES = {
    "journal-article": "journalArticle", "proceedings-article": "conferencePaper", "book-chapter": "bookSection",
    "book-part": "bookSection", "book-section": "bookSection", "posted-content": "preprint", "book": "book",
    "monograph": "book", "edited-book": "book", "reference-book": "book", "dataset": "dataset", "report": "report",
    "report-component": "report", "dissertation": "thesis", "reference-entry": "encyclopediaArticle",
    "standard": "standard",
}
# Crossref-only keys that Zotero would also read; CSL proper uses `event-title`.
EVENT_KEYS = ("event-title", "event")
DATE_FALLBACKS = ("published", "published-online", "published-print", "created")
PAGE_TYPES = {"conference": "conferencePaper", "journal": "journalArticle", "book": "bookSection"}



class Session:
    """What one run shares: Zotero (for the schema, kept in <work>/scratch for the run) and the pacer of the work
    directory; the arXiv answers looked up for all records at once."""

    def __init__(self, base_url, work=None):
        self.zot, self.pacer = zotero.Zotero(base_url), web.Pacer(work)
        self.cache = work.schema_file if work else None
        self.arxiv = {}  # arXiv id -> (its entry, the source's code)

    def schema(self):
        return self.zot.schema(cache=self.cache)

    def arxiv_entry(self, aid):
        if aid not in self.arxiv:
            self.arxiv.update(arxiv_entries(self, [aid]))
        return self.arxiv[aid]


# ---- identifiers --------------------------------------------------------------------------------------------

def parse_identifier(raw):
    """(DOI, arXiv id or None, arXiv version or '') of a DOI / doi.org url / arXiv id / arxiv.org url."""
    s = raw.strip()
    s = re.sub(r"^(?:https?://)?(?:www\.)?arxiv\.org/(?:abs|pdf)/", "arXiv:", s, flags=re.I)
    s = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", s, flags=re.I)
    s = re.sub(r"^doi:\s*", "", s, flags=re.I)
    s = re.sub(r"[\s.,;:'\"<>\]}]+$", "", s)
    if s.endswith(")") and s.count("(") < s.count(")"):
        s = s[:-1]
    m = (re.fullmatch(rf"(?:arxiv:)?\s*({paper.ARXIV_ID})(v\d+)?(?:\.pdf)?", s, flags=re.I)
         or re.fullmatch(rf"10\.48550/arxiv\.({paper.ARXIV_ID})(v\d+)?", s, flags=re.I))
    if m:
        return f"10.48550/arXiv.{m.group(1)}", m.group(1), m.group(2) or ""
    if re.fullmatch(r"10\.\d{4,9}/\S+", s):
        return s, None, ""
    raise cli.Stop("no_identifier", hint="Give a DOI (10.xxxx/...), a doi.org url, or an arXiv id such as 2006.11239.")


def normalize_id(ident):
    """The identifier in one spelling (lower-case DOI form), for telling whether two name one paper; '' when none."""
    try:
        return parse_identifier(ident or "")[0].lower()
    except cli.Stop:
        return ""


def preprint_id(item):
    """The arXiv id of an item that is still the preprint (itemType preprint, or the arXiv DOI); None otherwise."""
    aid = paper.identifiers(item)[1]
    if aid and (item.get("itemType") == "preprint" or paper.doi_of(item).startswith("10.48550/")):
        return aid
    return None


# ---- doi.org and Crossref -----------------------------------------------------------------------------------

def fetch_csl(s, doi):
    """doi.org's CSL JSON for a DOI -> (record, the registration agency's name for libraryCatalog)."""
    url = f"{web.endpoint('DOI_BASE_URL', 'https://doi.org')}/{urllib.parse.quote(doi, safe='/')}"
    no_csl = cli.Stop("no_csl_record", hint="doi.org has no CSL record for this DOI: write the item by hand from the "
                                            "landing page.")
    try:
        body, headers, final = web.read(url, full=True, host=HOST_DOI, pacer=s.pacer, headers={"Accept": CSL_ACCEPT})
    except web.NoData as e:
        if e.code == "source_blocked":
            raise cli.Stop("source_blocked", exit=cli.CANNOT, hint="doi.org answered 429: rerun after `until`.", **e.extra) from None
        if e.code == "network_error":
            raise cli.Stop("doi_org_unreachable", exit=cli.CANNOT, hint="Check the network or proxy, then rerun.", **e.extra) from None
        if e.code == "not_found":
            raise cli.Stop("not_found", hint="doi.org does not know this DOI: check it for typos; a fresh one may not be "
                                             "registered yet: search the title instead.") from None
        if e.status and e.status >= 500:
            raise cli.Stop("doi_org_error", status=e.status, hint="doi.org or the DOI's agency failed on this DOI; rerun "
                                                                  "later, or write the item by hand from the landing page.") from None
        no_csl.extra["status"] = e.status
        raise no_csl from None
    if "json" not in (headers.get("Content-Type") or "").lower():
        raise no_csl
    try:
        record = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise no_csl from None
    if not isinstance(record, dict):
        raise no_csl
    # Crossref names itself in `source`; DataCite answers from its own host.
    agency = first_str(record.get("source")) or ("Datacite" if re.search(r"datacite|crosscite", final, re.I) else "")
    return record, agency


def crossref_url(path):
    return f"{web.endpoint('CROSSREF_BASE_URL', 'https://api.crossref.org')}/{path}"


def crossref_work(s, doi):
    """(Crossref's record of one DOI, None) or (None, why); never raises."""
    try:
        data = web.read_json(crossref_url("works/" + urllib.parse.quote(doi, safe="/")), host=HOST_CROSSREF, pacer=s.pacer)
    except web.NoData as e:
        return None, e.code.replace("http_", "HTTP ").replace("_", " ")
    message = data.get("message") if isinstance(data, dict) else None
    return (message, None) if isinstance(message, dict) else (None, "unexpected response")


def series_key(name):
    return re.sub(r"\s+", " ", name).strip().casefold()


KNOWN_SERIES = {series_key(s) for s in PROCEEDINGS_SERIES}


def proceedings_from_crossref(s, doi):
    """For a book-chapter with an ISSN: {"series", "title"} when Crossref names a known proceedings series and the
    volume title; else {"note"} saying why the draft stays a bookSection."""
    work, why = crossref_work(s, doi)
    titles = work.get("container-title") if work else None
    if not isinstance(titles, list):
        return {"note": f"Crossref lookup failed: {why or 'no container-title'}"}
    titles = [strip_markup(first_str(t)) for t in titles if first_str(t)]
    if len(titles) == 2 and series_key(titles[0]) in KNOWN_SERIES:
        return {"series": titles[0], "title": titles[1]}
    return {"note": f"Crossref container-title: {json.dumps(titles, ensure_ascii=False)}"}


# ---- CSL -> item --------------------------------------------------------------------------------------------

def first_str(value):
    """CSL gives a title as a string or a list; DataCite records carry numbers."""
    if isinstance(value, list):
        value = value[0] if value else ""
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def join_list(value):
    return ", ".join(str(v) for v in value if v) if isinstance(value, list) else first_str(value)


def strip_markup(text):
    """JATS / HTML tags (<jats:p>, <i>, ...) dropped, entities decoded, whitespace collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"</?[A-Za-z][^<>]*>", " ", text))).strip()


def format_date(value):
    """A CSL date -> 'YYYY-MM-DD' / 'YYYY-MM' / 'YYYY'; '' when absent."""
    if not isinstance(value, dict):
        return ""
    parts = value.get("date-parts") or []
    if not parts or not parts[0]:
        return first_str(value.get("raw") or value.get("literal") or "")
    nums = [int(p) for p in parts[0] if p not in (None, "")]
    return "-".join([str(nums[0])] + [f"{n:02d}" for n in nums[1:3]]) if nums else ""


def add_subtitle(title, subtitle):
    """'Title: Subtitle' from a CSL subtitle (a string or a list); the title as it is when there is none or it ends
    with it."""
    subs = subtitle if isinstance(subtitle, list) else [subtitle]
    sub = next((t for t in (strip_markup(first_str(v)) for v in subs) if t), "")
    if not title or not sub or paper.norm_title(title).endswith(paper.norm_title(sub)):
        return title
    return title + (" " if title[-1] in ":?!" else ": ") + sub


def arxiv_category_tags(categories):
    """DataCite's arXiv categories -> tag names as Zotero's arXiv translator writes them; FOS entries and repeats dropped."""
    tags = []
    for raw in categories if isinstance(categories, list) else [categories]:
        text = raw.strip() if isinstance(raw, str) else ""
        if not text or text.casefold().startswith("fos:"):
            continue
        m = ARXIV_CATEGORY.fullmatch(text)
        if m and not m.group(3):
            tag = m.group(1)  # a category of a single-archive group: quant-ph, hep-th
        elif m and m.group(2) in ARXIV_ARCHIVES:
            tag = f"{ARXIV_ARCHIVES[m.group(2)]} - {m.group(1)}"
        else:
            tag = text
        if tag not in tags:
            tags.append(tag)
    return tags


def single_page(page):
    parts = [p.strip() for p in re.split(r"[-‐-―]", page)]
    return len(parts) == 1 or (len(parts) == 2 and parts[0] == parts[1])


def erratum_signals(record, item_type):
    """Why the DOI may be a correction, erratum or retraction notice rather than the paper; [] when nothing says so."""
    signals = []
    notice = paper.notice_title(strip_markup(first_str(record.get("title"))))
    if notice:
        signals.append(f"title starts with {notice!r}")
    if item_type in ERRATUM_TYPES:
        if not any(isinstance(p, dict) for p in record.get("author") or []):
            signals.append("no authors")
        page = first_str(record.get("page"))
        # An article number (Elsevier 104336, PLOS e0360436) is not a one-page notice.
        article_number = page == first_str(record.get("article-number")) or re.fullmatch(r"[eE]?\d{5,}", page)
        if page and single_page(page) and not article_number:
            signals.append(f"single page {page!r}")
    return signals


def own(t, *names):
    """The type's own field for the first of the names it has (directly or as a base field); None when none."""
    return next((f for f in (zotero.own_field(t, n) for n in names) if f), None)


def ordered(item, t):
    """The item's fields in the schema's order, after itemType, title and creators."""
    order = ["itemType", "title", "creators"] + t["order"]
    return {**{k: item[k] for k in order if k in item}, **{k: v for k, v in item.items() if k not in order}}


def build_creators(record, schema, t, item_type, warnings):
    by_var = {}
    for zotero_type, csl_var in schema["csl"]["names"].items():
        by_var.setdefault(csl_var, []).append(zotero_type)
    creators = []
    for csl_var, zotero_types in by_var.items():
        people = record.get(csl_var)
        if not isinstance(people, list) or not people:
            continue
        if csl_var == "author":  # CSL's author is the type's primary creator (programmer, artist, ...)
            zotero_types = [t["primary"]] + zotero_types
        ctype = next((z for z in zotero_types if z in t["creator_types"]), None)
        if ctype is None and "contributor" in t["creator_types"]:
            ctype = "contributor"
            warnings.append(f"{csl_var} stored as contributor (no matching creatorType in {item_type})")
        elif ctype is None:
            warnings.append(f"{csl_var} dropped (no creatorType for it in {item_type})")
            continue
        for p in people:
            if not isinstance(p, dict):
                continue
            family, given = first_str(p.get("family")), first_str(p.get("given"))
            literal = first_str(p.get("literal") or p.get("name"))
            if family and given:
                creators.append({"creatorType": ctype, "firstName": given, "lastName": family})
            elif family or literal:
                creators.append({"creatorType": ctype, "name": family or literal})
    return creators


def build_item(record, schema, doi, aid, version, agency, warnings, proceedings=None):
    """A CSL record -> a Zotero item. `proceedings` is proceedings_from_crossref()'s answer for a book-chapter with an
    ISSN."""
    csl_type = first_str(record.get("type"))
    in_series = bool(proceedings and proceedings.get("series"))
    item_type = ("preprint" if aid else "conferencePaper" if in_series
                 else CROSSREF_TYPES.get(csl_type) or (schema["csl"]["types"].get(csl_type) or [None])[0])
    if item_type is None:
        item_type = "journalArticle"
        warnings.append(f"unknown CSL/Crossref type {csl_type!r}; itemType defaulted to journalArticle")
    t = zotero.types_of(schema)[item_type]
    item, dropped = {"itemType": item_type}, []
    # Handled below, or not wanted: `version` is the metadata record's version, `source` the agency.
    special = {"title", "abstract", "URL", "DOI", "container-title", "ISSN", "ISBN", "source", "citation-key", "version"}
    if item_type == "journalArticle":
        special.add("publisher")  # Zotero's own DOI import leaves it blank for journal articles

    item["title"] = add_subtitle(strip_markup(first_str(record.get("title"))), record.get("subtitle"))
    if not item["title"]:
        warnings.append("record has no title")
    for csl_key, candidates in schema["csl"]["fields"]["text"].items():
        value = record.get(csl_key)
        if csl_key in special or value is None:
            continue
        if isinstance(value, dict) or (isinstance(value, list) and not all(isinstance(v, (str, int)) for v in value)):
            continue
        value = join_list(value)
        if value:
            target = own(t, *candidates)
            if target:
                item[target] = value
            else:
                dropped.append(csl_key)

    container = proceedings["title"] if in_series else first_str(record.get("container-title"))
    if in_series:
        if own(t, "series"):
            item[own(t, "series")] = proceedings["series"]
        warnings.append(f"book-chapter in the proceedings series {proceedings['series']!r}: drafted as conferencePaper "
                        "with the volume title from Crossref; the date is the volume's, check it against the conference year")
    elif csl_type == "book-chapter" and record.get("ISSN"):
        note = f" ({proceedings['note']})" if proceedings and proceedings.get("note") else ""
        warnings.append(f"book-chapter with an ISSN: container-title is probably the series name (e.g. LNCS); check "
                        f"bookTitle / series{note}")
    if container:
        if own(t, "publicationTitle"):
            item[own(t, "publicationTitle")] = container
        else:
            dropped.append("container-title")
    elif item_type in ("journalArticle", "conferencePaper", "bookSection"):
        warnings.append("record has no container-title")
    for key in ("ISSN", "ISBN"):
        if record.get(key):
            if own(t, key):
                item[own(t, key)] = join_list(record[key])
            else:
                dropped.append(key)

    abstract = strip_markup(first_str(record.get("abstract")))
    if abstract:
        item["abstractNote"] = abstract
    else:
        warnings.append("record has no abstract")
    for csl_key, field in schema["csl"]["fields"]["date"].items():
        value = format_date(record.get(csl_key)) if csl_key != "accessed" else ""
        if value and own(t, field):
            item[own(t, field)] = value
    if not item.get("date"):
        key, value = next(((k, format_date(record.get(k))) for k in DATE_FALLBACKS if format_date(record.get(k))), (None, ""))
        if value:
            item["date"] = value
            warnings.append(f"date taken from {key!r} (no usable 'issued')")
    if not item.get("date"):
        warnings.append("record has no date")
    elif re.fullmatch(r"\d{4}", item["date"]):
        warnings.append("date is year-only")

    event = next((e for e in (first_str(r.get("name") if isinstance(r, dict) else r)
                              for r in (record.get(k) for k in EVENT_KEYS)) if e), "")
    if event and own(t, "conferenceName", "meetingName"):
        item[own(t, "conferenceName", "meetingName")] = event
    place = first_str(record.get("publisher-place") or record.get("publisher-location"))
    if place and own(t, "place"):
        item[own(t, "place")] = place

    item["creators"] = build_creators(record, schema, t, item_type, warnings)
    if not item["creators"]:
        warnings.append("record has no creators")
    signals = erratum_signals(record, item_type)
    if signals:
        warnings.append(f"possible erratum, correction or retraction notice ({'; '.join(signals)}): open the landing "
                        "page and make sure this DOI is the paper itself")

    if aid:
        item.update(url=f"https://arxiv.org/abs/{aid}{version}", repository="arXiv", archiveID=f"arXiv:{aid}")
    else:  # the version of record: its DOI link, which leads to the publisher's current page
        item["url"] = f"https://doi.org/{doi}"
        if SALES_PAGE_DOI.match(doi):
            warnings.append("this DOI leads to the printed proceedings' sales page: set item.url to the paper's page "
                            "on proceedings.neurips.cc")
    if own(t, "DOI"):
        item["DOI"] = doi
    else:
        item["extra"] = "\n".join(x for x in (f"DOI: {doi}", item.get("extra", "")) if x)
        warnings.append(f"{item_type} has no DOI field; DOI written to extra")
    if own(t, "libraryCatalog"):
        item["libraryCatalog"] = f"DOI.org ({agency})" if agency else "DOI.org"
    if dropped:
        warnings.append(f"fields not in {item_type}, dropped: {', '.join(sorted(dropped))}")
    return ordered(item, t)


def draft(s, ident):
    """An identifier -> (item, warnings, DOI, the arXiv category tags)."""
    doi, aid, version = parse_identifier(ident)
    schema = s.schema()
    record, agency = fetch_csl(s, doi)
    warnings = []
    record_doi = first_str(record.get("DOI"))
    if record_doi and record_doi.lower() != doi.lower():
        warnings.append(f"record DOI {record_doi!r} differs from requested {doi!r}; using the record's")
    if record_doi and not aid:  # the registry's spelling (an arXiv DOI keeps its canonical form)
        doi = record_doi
    proceedings = (proceedings_from_crossref(s, doi)
                   if first_str(record.get("type")) == "book-chapter" and record.get("ISSN") else None)
    item = build_item(record, schema, doi, aid, version, agency, warnings, proceedings)
    tags = [{"tag": name, "type": 1} for name in arxiv_category_tags(record.get("categories"))] if aid else []
    return item, warnings, doi, tags


# ---- drafting records ---------------------------------------------------------------------------------------

def bib_close(text, start, close_ch):
    """Index of the delimiter closing an entry body that starts at `start`, nested braces honoured."""
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
    """One field value at pos: {braced}, "quoted" or a bare token, '#' concatenations joined -> (value, pos)."""
    parts, n = [], len(body)
    while True:
        while pos < n and body[pos].isspace():
            pos += 1
        if pos >= n:
            break
        c = body[pos]
        if c in "{\"":
            depth, start = 0, pos + (c == '"')
            pos += c == '"'
            while pos < n:
                if body[pos] == "{":
                    depth += 1
                elif body[pos] == "}":
                    depth -= 1
                    if c == "{" and depth == 0:
                        break
                elif c == '"' and body[pos] == '"' and depth == 0:
                    break
                pos += 1
            parts.append(body[start + (c == "{"):pos])
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


def parse_bib(text):
    """A minimal BibTeX reader: (entry type, key, {field (lower-case): value, braces dropped}); @comment, @string and
    @preamble skipped. No LaTeX decoding: titles and identifiers only."""
    pos = 0
    while (at := text.find("@", pos)) >= 0:
        m = re.match(r"@\s*([A-Za-z]+)\s*([{(])", text[at:])
        if not m:
            pos = at + 1
            continue
        etype, body_start = m.group(1).lower(), at + m.end()
        end = bib_close(text, body_start, "}" if m.group(2) == "{" else ")")
        body, pos = text[body_start:end], end + 1
        if etype in ("comment", "string", "preamble"):
            continue
        key, _, rest = body.partition(",")
        fields, p = {}, 0
        while fm := re.match(r"\s*,?\s*([^\s=,]+)\s*=\s*", rest[p:]):
            value, p = bib_value(rest, p + fm.end())
            fields[fm.group(1).lower()] = re.sub(r"\s+", " ", value.replace("{", "").replace("}", "")).strip()
        yield etype, key.strip(), fields


def bib_identifier(fields):
    """An entry's DOI, else its arXiv id (eprint, or an arXiv url / mention in url, journal, howpublished, note), else None."""
    doi = paper.normalize_doi(fields.get("doi"))
    if doi:
        return doi
    eprint = (fields.get("eprint") or "").strip()
    prefix = (fields.get("archiveprefix") or fields.get("eprinttype") or "").strip().lower()
    m = re.fullmatch(rf"(?:arxiv:)?({paper.ARXIV_ID})(v\d+)?", eprint, flags=re.I)
    if eprint and (prefix == "arxiv" or m):
        return "arXiv:" + (m.group(1) + (m.group(2) or "") if m else eprint)
    for name in ("url", "journal", "howpublished", "note", "eprint"):
        m = re.search(rf"(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*)({paper.ARXIV_ID})(v\d+)?", fields.get(name) or "", flags=re.I)
        if m:
            return "arXiv:" + m.group(1) + (m.group(2) or "")
    return None


def identifiers_of(args):
    """[(identifier, citation key or None, has an identifier)] from --doi, --ids and --bib, in that order."""
    out = [(d, None, True) for d in args.doi]
    for name, path in (("--ids", args.ids), ("--bib", args.bib)):
        if not path:
            continue
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise cli.Stop("no_records", hint=f"Cannot read the {name} file.", path=str(path), detail=str(e)) from None
        if name == "--ids":
            for line in text.splitlines():
                ident, _, cite = line.strip().partition("\t")
                if ident.strip() and not ident.startswith("#"):
                    out.append((ident.strip(), cite.strip() or None, True))
        else:
            for _, key, fields in parse_bib(text):
                ident = bib_identifier(fields)
                out.append((ident or fields.get("title") or "", key or None, bool(ident)))
    return out


def clean(s, limit=None):
    """Lower-case letters and digits only, accents stripped."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if ch.isalnum() and not unicodedata.combining(ch)).lower()
    return s[:limit] if limit else s


def derive_slug(item):
    """<first author's surname><year><first title word of 4+ letters> (liu2022progressive); '' when nothing is usable."""
    year = re.match(r"\d{4}", item.get("date") or "")
    word = next((w for w in re.findall(r"[^\W_]+", item.get("title") or "") if sum(ch.isalpha() for ch in w) >= 4), "")
    return clean(paper.first_surname(item.get("creators"))) + (year.group(0) if year else "") + clean(word)


def slug_for(cite, item, ident):
    if cite:
        return re.sub(r'[<>:"/\\|?*\s]+', "_", cite).strip("_") or clean(cite)
    return derive_slug(item) or clean(ident, 60) or "record"


def index(out_dir):
    """The records in the directory: their identifiers (the `id` they were drafted from, their item's DOI and arXiv
    id, one spelling) -> (slug, whether it has an item)."""
    known = {}
    for path in sorted(out_dir.glob("*.json")):
        try:
            rec = run.read(path)
        except cli.Stop:
            continue
        doi, aid = paper.identifiers(rec.item)
        for key in (normalize_id(rec.get("id")), doi, aid and f"10.48550/arxiv.{aid}"):
            if key:
                known.setdefault(key, (rec.slug, bool(rec.item)))
    return known


def draft_records(args):
    """Draft mode: one line per identifier, then the summary -> the exit code."""
    wanted = identifiers_of(args)
    if not wanted:
        raise cli.Stop("no_records", hint="Nothing to draft: give --doi, --ids or --bib (the files hold no identifier).")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    s = Session(args.base_url, run.Work(out_dir.parent))
    known, taken, this_run = index(out_dir), {p.stem for p in out_dir.glob("*.json")}, {}

    def one(ident, cite, has_id):
        key = normalize_id(ident)
        if key in this_run:
            return cli.skipped("duplicate", **({"slug": this_run[key]} if this_run[key] else {}))
        this_run[key] = None
        slug, has_item = known.get(key, (None, False))
        if has_item:
            this_run[key] = slug
            return cli.skipped("exists", slug=slug)
        if not has_id:
            raise cli.Stop("no_identifier", hint="No DOI or arXiv id in the entry: find the paper's (papers.cool, "
                                                 "Crossref, the publisher), then draft it with --ids: identifier<TAB>citation key.")
        item, warnings, _, tags = draft(s, ident)
        if slug is None:
            base = slug = slug_for(cite, item, ident)
            n = 1
            while slug in taken:
                n += 1
                slug = f"{base}-{n}"
        taken.add(slug)
        path = out_dir / f"{slug}.json"
        rec = run.read(path) if path.exists() else run.Record(path, {})
        for k in ("code", "hint", "detail"):  # a failed draft's leftovers, which records no longer carry
            rec.pop(k, None)
        rec["id"] = ident
        if cite and not rec.get("citationKey"):
            rec["citationKey"] = cite
        rec["item"] = item
        if tags and not rec.get("tags"):
            rec["tags"] = tags
        rec.pop("warnings", None)
        if warnings:
            rec["warnings"] = warnings
        if not args.dry_run:
            rec.save()
        this_run[key] = slug
        return {"slug": slug, "itemType": item["itemType"], "title": item.get("title", "")[:80],
                **({"warnings": warnings} if warnings else {})}

    out = cli.Lines()
    for ident, cite, has_id in wanted:
        out.add({"id": ident, **({"cite": cite} if cite else {})}, lambda: one(ident, cite, has_id))
    return out.finish({"dry_run": True} if args.dry_run else None)


# ---- published versions -------------------------------------------------------------------------------------

def arxiv_entries(s, ids):
    """{arXiv id: ({journal_ref, doi, comment}, the source's code)}, one API call per 100 ids."""
    out = {}
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        try:
            body = web.read(web.endpoint("ARXIV_API_URL", "https://export.arxiv.org/api/query"), host=HOST_ARXIV,
                            pacer=s.pacer, params={"id_list": ",".join(chunk), "max_results": len(chunk)},
                            headers={"Accept": "application/atom+xml"}, timeout=60)
            got = {}
            for entry in ET.fromstring(body).findall("a:entry", ATOM):
                m = re.search(rf"arxiv\.org/abs/({paper.ARXIV_ID})(?:v\d+)?$", (entry.findtext("a:id", "", ATOM) or "").strip(), re.I)
                if m:
                    got[m.group(1)] = {tag: web.clean(entry.findtext(f"arxiv:{tag}", None, ATOM)) for tag in ("journal_ref", "doi", "comment")}
        except web.NoData as e:
            out.update({aid: ({}, e.code) for aid in chunk})
            continue
        except ET.ParseError:
            out.update({aid: ({}, "bad_response") for aid in chunk})
            continue
        out.update({aid: (got.get(aid, {}), "ok") for aid in chunk})
    return out


def year_in(text):
    m = re.search(r"\b(19|20)\d{2}\b", text or "")
    return int(m.group(0)) if m else None


def candidate(source, doi=None, venue=None, year=None, title=None, **extra):
    return {"doi": doi, "venue": venue, "year": year, "title": title, "source": source,
            **{k: v for k, v in extra.items() if v is not None}}


def from_arxiv(entry):
    """The published version the authors declared: each DOI arXiv lists (10.48550 aside), else the journal_ref alone."""
    journal = entry.get("journal_ref")
    out = [candidate("arxiv", doi=d.rstrip("."), venue=journal, year=year_in(journal), journal_ref=journal)
           for d in re.findall(r"10\.\d{4,9}/[^\s,;]+", entry.get("doi") or "") if not d.lower().startswith("10.48550/")]
    if not out and journal:
        out.append(candidate("arxiv", venue=journal, year=year_in(journal), journal_ref=journal))
    return out


def crossref_fields(work):
    """Title (with subtitle), venue, year and type of a Crossref work; a chapter in a proceedings series names its
    volume, not the series."""
    event, titles = work.get("event"), work.get("container-title")
    containers = [first_str(c) for c in (titles if isinstance(titles, list) else [titles]) if first_str(c)]
    if len(containers) > 1 and series_key(containers[0]) in KNOWN_SERIES:
        containers = containers[1:]
    venue = (containers[0] if containers else "") or first_str(event.get("name") if isinstance(event, dict) else event)
    issued = ((work.get("issued") or {}).get("date-parts") or [[None]])[0] or [None]
    return {"title": add_subtitle(strip_markup(first_str(work.get("title"))), work.get("subtitle")) or None,
            "venue": strip_markup(venue) or None, "year": issued[0] if isinstance(issued[0], int) else None,
            "type": work.get("type")}


def crossref_search(s, titles, family):
    """Crossref works whose title (with or without its subtitle) is at least CANDIDATE_SIMILARITY alike to one of the
    titles; arXiv DOIs and posted content left out. NoData when Crossref does not answer."""
    params = {"query.bibliographic": titles[0], "rows": 10, "select": "DOI,title,subtitle,container-title,type,issued,event"}
    if family:
        params["query.author"] = family
    data = web.read_json(crossref_url("works"), params=params, host=HOST_CROSSREF, pacer=s.pacer)
    try:
        works = data["message"]["items"]
    except (KeyError, TypeError):
        raise web.NoData("bad_response") from None
    out = []
    for work in works if isinstance(works, list) else []:
        doi = first_str(work.get("DOI")) if isinstance(work, dict) else ""
        if not doi or doi.lower().startswith("10.48550/") or work.get("type") == "posted-content":
            continue
        f = crossref_fields(work)
        plain = strip_markup(first_str(work.get("title")))
        if max(paper.title_similarity(t, c) for t in titles for c in (plain, f["title"] or "")) >= CANDIDATE_SIMILARITY:
            out.append(candidate("crossref", doi=doi, venue=f["venue"], year=f["year"], title=f["title"], type=f["type"]))
    return out


def complete(s, declared, searched):
    """Title, venue, year and type of the DOIs arXiv lists, from Crossref: its search answer, else the DOI's record."""
    found = {c["doi"].lower(): c for c in searched}
    for c in declared:
        if not c["doi"]:
            continue
        got = found.get(c["doi"].lower())
        if got is None:
            work, _ = crossref_work(s, c["doi"])
            got = crossref_fields(work) if work else None
        if got:
            c.update(title=got["title"], type=got["type"], venue=got["venue"] or c["venue"], year=got["year"] or c["year"])


def merge_candidates(found, titles):
    """One item per DOI, its sources listed; an item without a DOI (a journal_ref alone) stays as it is."""
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
    keys = {paper.norm_title(t) for t in titles}
    out = []
    for m in merged:
        item = {k: m.get(k) for k in ("doi", "venue", "year", "title")}
        if m["doi"]:
            item["url"] = f"https://doi.org/{m['doi']}"
        item.update(sources=m["sources"], title_differs=None if not m["title"] else paper.norm_title(m["title"]) not in keys)
        out.append({**item, **{k: m[k] for k in ("type", "journal_ref") if m.get(k) is not None}})
    return out


def setup(args, records):
    s = Session(args.base_url, run.Work.of(records[0].path) if records else None)
    s.redraft = args.redraft
    if not args.redraft:  # every arXiv id that is due, in one call
        due = [aid for r in records for aid in [preprint_id(r.item)] if aid and run.due(r, "published_candidates")]
        s.arxiv.update(arxiv_entries(s, list(dict.fromkeys(due))))
    return s


def candidates(rec, s):
    """The record's published_candidates, when its item is a preprint and the block is not done."""
    item = rec.item
    if not item:
        return {"code": "no_item", "hint": run.HINT_NO_ITEM}
    aid = preprint_id(item)
    if not aid:
        rec.pop("published_candidates", None)
        return cli.skipped("not_preprint")
    due = run.due(rec, "published_candidates")
    old = rec.get("published_candidates") if isinstance(rec.get("published_candidates"), dict) else {}
    if due is None:
        return cli.skipped("done", candidates=len(old.get("items") or []))
    titles = [t for t in [item.get("title"), *(rec.get("alt_titles") or [])] if isinstance(t, str) and t.strip()]
    entry, arxiv_code = s.arxiv_entry(aid)
    answers, codes = {"arxiv": from_arxiv(entry), "crossref": []}, {"arxiv": arxiv_code, "crossref": "no_title"}
    if titles:
        try:
            answers["crossref"], codes["crossref"] = crossref_search(s, titles, paper.first_surname(item.get("creators"))), "ok"
        except web.NoData as e:
            codes["crossref"] = e.code
    unanswered = sorted(k for k, code in codes.items() if code not in ANSWERED)
    if due == "incomplete":  # what a silent source gave last time stays
        for source in unanswered:
            answers[source] = [{**c, "source": source} for c in old.get("items") or []
                               if isinstance(c, dict) and source in (c.get("sources") or [])]
    complete(s, answers["arxiv"], answers["crossref"])
    items = merge_candidates(answers["arxiv"] + answers["crossref"], titles)
    comment = old.get("comment") if "arxiv" in unanswered else entry.get("comment")
    run.stamp(rec, "published_candidates", {"items": items, **({"comment": comment} if comment else {})}, incomplete=unanswered)
    line = {"reason": due, "candidates": len(items), **({"comment": comment} if comment else {}), "sources": codes}
    if len(unanswered) == sum(1 for code in codes.values() if code != "no_title"):
        return {"code": "no_answer", **line, "hint": "No source answered; run this (or p2z.py prepare) again later."}
    return {"code": "ok", **line}


# ---- redraft ------------------------------------------------------------------------------------------------

def item_from_page(s, url, old, warnings):
    """The published version from its page's citation_* tags; the preprint's creators and abstract fill what the page
    lacks."""
    try:
        body, headers, final = web.read(url, full=True, pacer=s.pacer, headers={"User-Agent": web.BROWSER_UA, "Accept": "text/html"})
    except web.NoData as e:
        if e.code == "source_blocked":
            raise cli.Stop("source_blocked", hint="That host answered 429: read the page in the browser and fill the "
                                                  "item from it.", **e.extra) from None
        raise cli.Stop("page_unreachable", **({"status": e.status} if e.status else e.extra),
                       hint="The page refuses a plain HTTP request (or cannot be reached): read it in the browser and "
                            "fill the item from what it shows.") from None
    m = web.page_meta(body, final, headers)
    if not web.first_meta(m["meta"], "citation_title", "dc.title"):
        raise cli.Stop("no_citation_meta", url=final, hint="The page has no citation_title tag (an OpenReview page behind "
                                                           "a challenge, a site without the tags): fill the item by hand.")
    item_type = PAGE_TYPES.get(m["venue_kind"], "conferencePaper")
    if not m["venue_kind"]:
        warnings.append("the page names no venue (citation_conference_title / citation_journal_title): drafted as "
                        "conferencePaper, check the type and the venue")
    t = zotero.types_of(s.schema())[item_type]
    abstract = web.first_meta(m["meta"], "citation_abstract", "dcterms.abstract") or old.get("abstractNote") or m["abstract"]
    values = {"title": m["title"], "abstractNote": abstract, "publicationTitle": m["venue"], "volume": m["volume"],
              "issue": m["issue"], "pages": m["pages"], "date": m["date"], "DOI": m["doi"], "publisher": m["publisher"],
              "ISSN": m["issn"], "ISBN": m["isbn"], "url": final, "libraryCatalog": web.host_of(final),
              "extra": old.get("extra")}
    item = {"itemType": item_type, **{own(t, k): v for k, v in values.items() if v and own(t, k)}}
    old_creators = [c for c in old.get("creators") or [] if isinstance(c, dict)]
    item["creators"] = [{"creatorType": "author", **a} for a in m["authors"]] or old_creators
    if m["authors"] and old_creators and len(m["authors"]) != len(old_creators):
        warnings.append(f"the page lists {len(m['authors'])} authors, the preprint {len(old_creators)}: check the creators")
    if not m["date"]:
        warnings.append("the page gives no date: set it from the venue's year")
    return ordered(item, t)


def redraft(rec, s):
    """--redraft: the record's item becomes the published version, given by DOI or by its page."""
    target = s.redraft
    if rec.get("saved") or rec.get("attach"):
        return {"code": "already_saved", "hint": "The item is in Zotero already (or being created): change it there with "
                                                 "update_item.py, or start a new record."}
    old, warnings = rec.item, []
    if re.match(r"https?://", target, re.I) and not re.match(r"https?://(?:dx\.)?doi\.org/|https?://(?:www\.)?arxiv\.org/", target, re.I):
        item = item_from_page(s, target, old, warnings)
    else:
        doi, aid, _ = parse_identifier(target)
        if aid:
            return {"code": "not_published", "hint": "A 10.48550 DOI is the arXiv preprint itself: give the published version's DOI."}
        if paper.doi_of(old) == doi.lower():
            return cli.skipped("same_doi")
        item, warnings, _, _ = draft(s, doi)
        if not item.get("abstractNote") and old.get("abstractNote") and "record has no abstract" in warnings:
            item["abstractNote"] = old["abstractNote"]
            warnings[warnings.index("record has no abstract")] = "the DOI record has no abstract: the preprint's is kept"
    aid = paper.identifiers(old)[1]
    if aid:
        lines = [ln for ln in str(item.get("extra") or "").splitlines() if ln.strip()]
        if not any(re.match(rf"arxiv:\s*{re.escape(aid)}\b", ln, re.I) for ln in lines):
            lines.append(f"arXiv: {aid}")
        item["extra"] = "\n".join(lines)
    else:
        warnings.append("no arXiv id on the old item: extra has no arXiv line")
    old_title = old.get("title") or ""
    alt = [t for t in rec.get("alt_titles") or [] if isinstance(t, str)]
    if old_title and paper.norm_title(old_title) not in {paper.norm_title(t) for t in [item.get("title"), *alt]}:
        rec["alt_titles"] = alt + [old_title]
    rec["item"] = item
    rec.pop("warnings", None)
    if warnings:
        rec["warnings"] = warnings
    return {"code": "ok", "redraft": target, "itemType": item["itemType"], "title": (item.get("title") or "")[:80],
            "url": item.get("url"), **({"alt_titles": rec["alt_titles"]} if rec.get("alt_titles") else {}),
            **({"warnings": warnings} if warnings else {})}


# ---- main ---------------------------------------------------------------------------------------------------

def main(argv=None):
    p = cli.records_parser(__doc__, zotero=True, dry_run=True)
    p.add_argument("--doi", action="append", default=[], metavar="ID", help="a DOI or arXiv id to draft (repeatable)")
    p.add_argument("--ids", metavar="FILE", help="identifiers to draft, `identifier[<TAB>citation key]` per line")
    p.add_argument("--bib", metavar="FILE", help="a BibTeX file to draft: each entry's key is its citation key")
    p.add_argument("--out-dir", metavar="DIR", help="where drafted records go: <work>/records")
    p.add_argument("--redraft", metavar="DOI|URL", help="the published version for ONE record: its DOI or its page")
    args = p.parse_args(argv)
    drafting = args.doi or args.ids or args.bib
    if drafting and (args.records or args.redraft):
        p.error("--doi / --ids / --bib draft new records; record paths and --redraft are another run")
    if drafting and not args.out_dir:
        p.error("drafted records go to --out-dir <work>/records")
    if args.out_dir and not drafting:
        p.error("--out-dir goes with --doi, --ids or --bib")
    if args.redraft and len(args.records) != 1:
        p.error("--redraft takes exactly one record")
    if drafting:
        return cli.run(lambda: draft_records(args))
    return cli.run(lambda: cli.each_record(args, redraft if args.redraft else candidates, setup=setup))


if __name__ == "__main__":
    raise SystemExit(main())
