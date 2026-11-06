#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Identify papers and pin their versions: identify, search and redraft, each its own word of pf.py."""
import html
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from pflib import cli, config, paper, run, web
from pflib.paper import clean, safe_slug

CSL_ACCEPT = "application/vnd.citationstyles.csl+json"
# The hosts requests are paced and stopped under: the real services', also when a test points the urls elsewhere.
HOST_DOI, HOST_CROSSREF = "doi.org", "api.crossref.org"
ANSWERED = ("ok", "no_title")
CANDIDATE_SIMILARITY = 0.9
WANTED = ("published", "accepted", "preprint")
# NeurIPS 2022-2025 DOIs, registered for the printed proceedings: they lead to its sales page, not to the paper.
SALES_PAGE_DOI = re.compile(r"^10\.52202/", re.I)
NO_ABSTRACT = "record has no abstract"
PREPRINT_ABSTRACT = "the published record has no abstract; the preprint's is in versions.preprint"
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")

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

# Crossref's types -> CSL's. CSL's own types pass as they are.
CSL_TYPES = {
    "journal-article": "article-journal", "proceedings-article": "paper-conference", "book-chapter": "chapter",
    "book-part": "chapter", "book-section": "chapter", "posted-content": "article", "monograph": "book",
    "edited-book": "book", "reference-book": "book", "report-component": "report", "dissertation": "thesis",
    "reference-entry": "entry-encyclopedia",
}
# Crossref's keys -> CSL's.
CSL_KEYS = {"event": "event-title", "publisher-location": "publisher-place", "short-container-title": "container-title-short"}
DATE_FALLBACKS = ("published", "published-online", "published-print", "created")
# CSL 1.0.2's variables: what a result's csl keeps (with `categories`, arXiv's subject classes, by name). The rest of
# a Crossref record (its reference list, deposit dates, scores, links, licences as objects) is left out.
CSL_TEXT = set("""type citation-key categories abstract annote archive archive_collection archive_location archive-place
authority call-number chapter-number citation-label collection-number collection-title container-title
container-title-short dimensions division DOI edition event-place event-title genre ISBN ISSN issue jurisdiction
keyword language license medium note number number-of-pages number-of-volumes original-publisher
original-publisher-place original-title page page-first part-number part-title PMCID PMID publisher publisher-place
references reviewed-genre reviewed-title scale section source status supplement-number title title-short URL version
volume volume-title volume-title-short""".split())
CSL_DATES = {"accessed", "available-date", "event-date", "issued", "original-date", "submitted"}
CSL_NAMES = set("""author chair collection-editor compiler composer container-author contributor curator director editor
editorial-director executive-producer guest host illustrator interviewer narrator organizer original-author performer
producer recipient reviewed-author script-writer series-creator translator""".split())


def csl_value(key, value):
    """Whether a value is CSL's: a name list, a date, or text (a string, a number, or a list of them, not empty)."""
    if key in CSL_NAMES:
        return isinstance(value, list) and bool(value)
    if key in CSL_DATES:
        return isinstance(value, dict)
    if key not in CSL_TEXT:
        return False
    return isinstance(value, (str, int)) or (isinstance(value, list) and bool(value)
                                             and all(isinstance(v, (str, int)) for v in value))
# Types where a one-page notice can pass for the paper; titles are checked for every type.
ERRATUM_TYPES = {"article-journal", "paper-conference", "chapter"}
PAGE_TYPES = {"conference": "paper-conference", "journal": "article-journal", "book": "chapter"}


def pending(first, due, answered):
    """first, then the ids due that have no answer yet: what one batched lookup asks for."""
    return list(dict.fromkeys([first] + [i for i in due if i not in answered]))


class Session:
    """What one run shares: the machine's pacer, the OpenAlex key, and the answers of the sources asked about many ids
    at once (arXiv, OpenAlex, Europe PMC): the first lookup asks for every id expect()ed and not yet answered."""

    def __init__(self):
        self.pacer = web.Pacer(web.pace_path())
        self.key = config.openalex_key()
        self.arxiv, self.openalex, self.epmc = {}, {}, {}  # id -> (its record, the source's code)
        self.due_arxiv, self.due_dois = [], []

    def expect(self, arxiv=(), dois=()):
        self.due_arxiv += list(arxiv)
        self.due_dois += [d.lower() for d in dois]

    def arxiv_entry(self, aid):
        if aid not in self.arxiv:
            self.arxiv.update(web.arxiv_entries(pending(aid, self.due_arxiv, self.arxiv), self.pacer))
        return self.arxiv[aid]

    def lookups(self, doi):
        """((OpenAlex's work, its code), (Europe PMC's record, its code)) for a DOI."""
        doi = doi.lower()
        if doi not in self.openalex:
            batch = pending(doi, self.due_dois, self.openalex)
            self.openalex.update(web.openalex_works(batch, self.pacer, self.key))
            self.epmc.update(web.europepmc_records(batch, self.pacer))
        return self.openalex[doi], self.epmc[doi]


# ---- what was asked for -------------------------------------------------------------------------------------

def parse_identifier(raw):
    """(DOI, arXiv id or None, arXiv version or '') of a DOI / doi.org url / arXiv id / arxiv.org url; ("page", url,
    '') for another http(s) url."""
    s = raw.strip()
    if s.lower().startswith("title:"):
        raise cli.Stop("needs_pinning", hint="A title is not an identifier: find the paper's DOI or arXiv id first "
                       "(SKILL.md, Identify a paper), then identify that.")
    if re.match(r"https?://", s, re.I) and not re.match(r"https?://(?:dx\.)?doi\.org/|https?://(?:www\.)?arxiv\.org/", s, re.I):
        return "page", s, ""
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
    raise cli.Stop("no_identifier", hint="Give a DOI (10.xxxx/...), a doi.org url, an arXiv id such as 2006.11239, or "
                                         "the paper's page.")


def request_key(raw):
    """The request in one spelling, for telling whether two name one paper; '' when it names none."""
    try:
        doi, aid, _ = parse_identifier(raw or "")
    except cli.Stop:
        return ""
    return aid.lower() if doi != "page" and aid else (aid if doi == "page" else doi.lower())


# ---- doi.org and Crossref -----------------------------------------------------------------------------------

def fetch_csl(s, doi):
    """doi.org's CSL JSON for a DOI -> (record, the registration agency's name)."""
    url = f"{web.endpoint('DOI_BASE_URL', 'https://doi.org')}/{urllib.parse.quote(doi, safe='/')}"
    no_csl = cli.Stop("no_csl_record", hint="doi.org has no metadata for this DOI: identify the paper's page instead, "
                                            "or write its metadata by hand.")
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
            raise cli.Stop("doi_org_error", status=e.status, hint="doi.org or the DOI's agency failed on this DOI; run "
                                                                  "again later.") from None
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
    volume title; else {"note"} saying why it stays a chapter."""
    work, why = crossref_work(s, doi)
    titles = work.get("container-title") if work else None
    if not isinstance(titles, list):
        return {"note": f"Crossref lookup failed: {why or 'no container-title'}"}
    titles = [strip_markup(first_str(t)) for t in titles if first_str(t)]
    if len(titles) == 2 and series_key(titles[0]) in KNOWN_SERIES:
        return {"series": titles[0], "title": titles[1]}
    return {"note": f"Crossref container-title: {json.dumps(titles, ensure_ascii=False)}"}


# ---- CSL ----------------------------------------------------------------------------------------------------

def first_str(value):
    """CSL gives a title as a string or a list; DataCite records carry numbers."""
    if isinstance(value, list):
        value = value[0] if value else ""
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def strip_markup(text):
    """JATS / HTML tags (<jats:p>, <i>, ...) dropped, entities decoded, whitespace collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"</?[A-Za-z][^<>]*>", " ", text))).strip()


def add_subtitle(title, subtitle):
    """'Title: Subtitle' from a CSL subtitle (a string or a list); the title as it is when there is none or it ends
    with it."""
    subs = subtitle if isinstance(subtitle, list) else [subtitle]
    sub = next((t for t in (strip_markup(first_str(v)) for v in subs) if t), "")
    if not title or not sub or paper.norm_title(title).endswith(paper.norm_title(sub)):
        return title
    return title + (" " if title[-1] in ":?!" else ": ") + sub


def has_date(value):
    return isinstance(value, dict) and bool((value.get("date-parts") or [[]])[0] or value.get("raw") or value.get("literal"))


def single_page(page):
    parts = [p.strip() for p in re.split(r"[-‐-―]", page)]
    return len(parts) == 1 or (len(parts) == 2 and parts[0] == parts[1])


def erratum_signals(record, csl_type):
    """Why the DOI may be a correction, erratum or retraction notice rather than the paper; [] when nothing says so."""
    signals = []
    notice = paper.notice_title(strip_markup(first_str(record.get("title"))))
    if notice:
        signals.append(f"title starts with {notice!r}")
    if csl_type in ERRATUM_TYPES:
        if not any(isinstance(p, dict) for p in record.get("author") or []):
            signals.append("no authors")
        page = first_str(record.get("page"))
        # An article number (Elsevier 104336, PLOS e0360436) is not a one-page notice.
        article_number = page == first_str(record.get("article-number")) or re.fullmatch(r"[eE]?\d{5,}", page)
        if page and single_page(page) and not article_number:
            signals.append(f"single page {page!r}")
    return signals


def normalize(record, doi, agency, warnings, proceedings=None):
    """doi.org's record -> CSL in CSL's own vocabulary (the module docstring lists what changes)."""
    csl = {CSL_KEYS.get(k, k): v for k, v in record.items() if not (k in CSL_KEYS and CSL_KEYS[k] in record)}
    csl = {k: v for k, v in csl.items() if csl_value(k, v)}
    event = record.get("event")
    if "event-title" not in csl and isinstance(event, dict) and strip_markup(first_str(event.get("name"))):
        csl["event-title"] = strip_markup(first_str(event.get("name")))
    raw_type = first_str(record.get("type"))
    csl["type"] = CSL_TYPES.get(raw_type, raw_type)
    signals = erratum_signals(record, csl["type"])
    if signals:
        warnings.append(f"possible erratum, correction or retraction notice ({'; '.join(signals)}): open the landing "
                        "page and make sure this DOI is the paper itself")
    csl["title"] = add_subtitle(strip_markup(first_str(record.get("title"))), record.get("subtitle"))
    csl.pop("subtitle", None)
    if not csl["title"]:
        warnings.append("record has no title")
    if record.get("abstract"):
        csl["abstract"] = strip_markup(first_str(record["abstract"]))
    if not csl.get("abstract"):
        warnings.append(NO_ABSTRACT)
    if not has_date(record.get("issued")):
        key = next((k for k in DATE_FALLBACKS if has_date(record.get(k))), None)
        if key:
            csl["issued"] = record[key]
            warnings.append(f"date taken from {key!r} (no usable 'issued')")
        else:
            warnings.append("record has no date")
    parts = ((csl.get("issued") or {}).get("date-parts") or [[]])[0] or []
    if len([p for p in parts if p not in (None, "")]) == 1:
        warnings.append("date is year-only")
    if not any(isinstance(p, dict) for p in csl.get("author") or []):
        warnings.append("record has no creators")
    if proceedings and proceedings.get("series"):
        csl.update({"type": "paper-conference", "container-title": proceedings["title"],
                    "collection-title": proceedings["series"]})
        warnings.append(f"book-chapter in the proceedings series {proceedings['series']!r}: made a paper-conference "
                        "with the volume title from Crossref; the date is the volume's, check it against the conference year")
    elif raw_type == "book-chapter" and record.get("ISSN"):
        note = f" ({proceedings['note']})" if proceedings and proceedings.get("note") else ""
        warnings.append(f"book-chapter with an ISSN: container-title is probably the series name (e.g. LNCS); check "
                        f"the volume and the series{note}")
    elif csl["type"] in ("article-journal", "paper-conference", "chapter") and not first_str(csl.get("container-title")):
        warnings.append("record has no container-title")
    if SALES_PAGE_DOI.match(doi):
        warnings.append("this DOI leads to the printed proceedings' sales page: the paper's page is on "
                        "proceedings.neurips.cc")
    csl["source"] = f"DOI.org ({agency})" if agency else "DOI.org"
    return csl


def from_doi(s, doi, aid, warnings):
    """A DOI's normalized CSL -> (csl, the DOI in the registry's spelling)."""
    record, agency = fetch_csl(s, doi)
    record_doi = first_str(record.get("DOI"))
    if record_doi and record_doi.lower() != doi.lower():
        warnings.append(f"record DOI {record_doi!r} differs from requested {doi!r}; using the record's")
    if record_doi and not aid:  # the registry's spelling (an arXiv DOI keeps its canonical form)
        doi = record_doi
    proceedings = (proceedings_from_crossref(s, doi)
                   if first_str(record.get("type")) == "book-chapter" and record.get("ISSN") else None)
    return normalize(record, doi, agency, warnings, proceedings), doi


def date_parts(text, warnings):
    """[year, month?, day?] of a page's date: 2023-12-10 or 2023-12 (web.meta_date's forms), "10 December 2023",
    "Dec. 10, 2023", "December 2023"; only the year, with a warning, when the rest cannot be read for certain (10/12/2023:
    which is the month?); None without a year."""
    text = (text or "").strip()
    m = re.fullmatch(r"(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", text)
    if m:
        return [int(g) for g in m.groups() if g]
    year = re.search(r"(?<!\d)(?:1[89]|20)\d{2}(?!\d)", text)
    if not year:
        return None
    rest = text[:year.start()] + " " + text[year.end():]
    months = [n for w in re.findall(r"[^\W\d_]{3,}", rest) for n, name in enumerate(MONTHS, 1) if name.startswith(w.lower())]
    days = [int(d) for d in re.findall(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?(?!\d)", rest)]
    parts = [int(year.group(0))]
    if len(months) == 1:
        parts.append(months[0])
        if len(days) == 1 and 1 <= days[0] <= 31:
            parts.append(days[0])
    if (days or months) and len(parts) < 2 + bool(days):
        warnings.append(f"the page's date {text!r} read as {parts}: check it")
    return parts


def from_page(s, url, warnings, body=None):
    """A paper's page, read over plain HTTP or, `body` given, from its HTML as a browser saved it -> (its citation_*
    tags as CSL, the page's final url, its DOI or None)."""
    headers, final = None, url
    if body is None:
        try:
            body, headers, final = web.read(url, full=True, pacer=s.pacer, headers={"User-Agent": web.BROWSER_UA, "Accept": "text/html"})
        except web.NoData as e:
            if e.code == "source_blocked":
                raise cli.Stop("source_blocked", exit=cli.CANNOT, hint="That host answered 429: read the page in the "
                                                                       "browser instead.", **e.extra) from None
            raise cli.Stop("page_unreachable", **({"status": e.status} if e.status else e.extra),
                           hint="The page refuses a plain HTTP request (or cannot be reached): save its HTML from the "
                                "browser, then pf.py redraft <url> <result> --html <file>.") from None
    m = web.page_meta(body, final, headers)
    if not web.first_meta(m["meta"], "citation_title", "dc.title"):
        raise cli.Stop("no_citation_meta", url=final, hint="The page has no citation_title tag. A page behind a challenge "
                                                           "(OpenReview): save its HTML from the browser, then pf.py "
                                                           "redraft <url> <result> --html <file>; a site without the tags "
                                                           "leaves the result a stub.")
    if not m["venue_kind"]:
        warnings.append("the page names no venue (citation_conference_title / citation_journal_title): made a "
                        "paper-conference, check the type and the venue")
    abstract = web.first_meta(m["meta"], "citation_abstract", "dcterms.abstract") or m["abstract"]
    authors = [{"family": a["lastName"], **({"given": a["firstName"]} if a.get("firstName") else {})}
               if a.get("lastName") else {"literal": a.get("name")} for a in m["authors"]]
    date = date_parts(m["date"], warnings)
    values = {"type": PAGE_TYPES.get(m["venue_kind"], "paper-conference"), "title": m["title"], "author": authors,
              "abstract": abstract, "container-title": m["venue"], "volume": m["volume"], "issue": m["issue"],
              "page": m["pages"], "issued": {"date-parts": [date]} if date else None, "DOI": m["doi"],
              "publisher": m["publisher"], "ISSN": m["issn"], "ISBN": m["isbn"], "URL": final,
              "source": paper.host_of(final)}
    if not date:
        warnings.append("the page gives no date: set it from the venue's year")
    return {k: v for k, v in values.items() if v}, final, m["doi"] or None


# ---- OpenAlex and Europe PMC: what the CSL lacks ------------------------------------------------------------

def inverted_text(index):
    """OpenAlex's abstract_inverted_index ({word: [positions]}) as text; '' when there is none."""
    if not isinstance(index, dict):
        return ""
    at = {p: w for w, ps in index.items() if isinstance(ps, list) for p in ps if isinstance(p, int)}
    return " ".join(at[p] for p in sorted(at)).strip()


def pm_id(value, prefix=""):
    """A PMID (prefix '') or PMCID (prefix 'PMC') from a bare id or an id url; None when there is none."""
    m = re.search(r"(\d+)/?$", str(value or "").strip())
    return prefix + m.group(1) if m else None


def author_keywords(record):
    """The authors' own keywords, as Europe PMC's record lists them (keywordList: PubMed's author keywords, the
    article's for a PMC paper), each once, in their order; [] when it has none. OpenAlex's `keywords` are not the
    authors': its tagging model's, from title and abstract (help.openalex.org, the work object)."""
    words = ((record.get("keywordList") or {}).get("keyword")) if isinstance(record.get("keywordList"), dict) else None
    return list(dict.fromkeys(w.strip() for w in words if isinstance(w, str) and w.strip())) if isinstance(words, list) else []


def openalex_keywords(work):
    """OpenAlex's keywords for the work (its model's, from title and abstract): a hint for whoever tags the paper,
    never metadata; [] when it has none."""
    return [k["display_name"] for k in work.get("keywords") or [] if isinstance(k, dict) and k.get("display_name")]


def enrich(s, doi, csl, warnings, old=None):
    """What the CSL lacks, by the paper's DOI, from OpenAlex and Europe PMC (the module docstring says what) -> the
    result's `enrichment`: {incomplete: the sources that did not answer, openalex_keywords?}. `old`: the result an
    earlier identify wrote; what it had stays while a source is silent."""
    if not doi:
        return {"incomplete": []}
    (work, oa_code), (record, epmc_code) = s.lookups(doi)
    silent = sorted(name for name, code in (("openalex", oa_code), ("europepmc", epmc_code)) if code not in ANSWERED)
    hints = openalex_keywords(work)
    if not hints and "openalex" in silent:
        hints = ((old or {}).get("enrichment") or {}).get("openalex_keywords")
    old = (old or {}).get("csl")
    oa_abstract, epmc_abstract = inverted_text(work.get("abstract_inverted_index")), strip_markup(first_str(record.get("abstractText")))
    found = {"abstract": epmc_abstract or oa_abstract, "keyword": author_keywords(record),
             "PMID": pm_id(record.get("pmid")) or pm_id((work.get("ids") or {}).get("pmid")),
             "PMCID": pm_id(record.get("pmcid"), "PMC") or pm_id((work.get("ids") or {}).get("pmcid"), "PMC")}
    for key, value in found.items():
        if csl.get(key):
            continue
        if not value and silent and (old or {}).get(key):
            value = old[key]
            if key == "abstract":
                warnings.append(f"abstract kept from the earlier identify ({', '.join(silent)} did not answer)")
        elif value and key == "abstract":
            warnings.append(f"abstract from {'Europe PMC' if epmc_abstract else 'OpenAlex'} (the record has none)")
            a, b = paper.norm_title(epmc_abstract), paper.norm_title(oa_abstract)
            if a and b and a not in b and b not in a:
                warnings.append(f"Europe PMC's and OpenAlex's abstracts differ: Europe PMC's kept; OpenAlex's begins "
                                f"{oa_abstract[:120]!r}: check which is the paper's")
        if value:
            csl[key] = value
            if key == "abstract":
                warnings[:] = [w for w in warnings if w not in (NO_ABSTRACT, PREPRINT_ABSTRACT)]
    return {"incomplete": silent, **({"openalex_keywords": hints} if hints else {})}


def ids_of_csl(ids, csl):
    ids.update(pmid=first_str(csl.get("PMID")) or None, pmcid=first_str(csl.get("PMCID")) or None)
    return ids


# ---- versions -----------------------------------------------------------------------------------------------

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


def crossref_works(s, title, family, rows, select="DOI,title,subtitle,container-title,type,issued,event"):
    """Crossref's works for a title (and first author), in its order, each with a DOI. NoData when Crossref does not
    answer."""
    params = {"query.bibliographic": title, "rows": rows, "select": select, **({"query.author": family} if family else {})}
    data = web.read_json(crossref_url("works"), params=params, host=HOST_CROSSREF, pacer=s.pacer)
    try:
        works = data["message"]["items"]
    except (KeyError, TypeError):
        raise web.NoData("bad_response") from None
    return [w for w in works if isinstance(w, dict) and first_str(w.get("DOI"))] if isinstance(works, list) else []


def title_match(titles, work, fields):
    """How alike a Crossref work's title (with or without its subtitle) is to the closest of the titles, 0..1."""
    plain = strip_markup(first_str(work.get("title")))
    return max(paper.title_similarity(t, c) for t in titles for c in (plain, fields["title"] or ""))


def crossref_search(s, titles, family):
    """Crossref works whose title is at least CANDIDATE_SIMILARITY alike to one of the titles; arXiv DOIs and posted
    content left out. NoData when Crossref does not answer."""
    out = []
    for work in crossref_works(s, titles[0], family, 10, select="DOI,title,subtitle,container-title,type,issued,event,author"):
        doi = first_str(work.get("DOI"))
        if doi.lower().startswith("10.48550/") or work.get("type") == "posted-content":
            continue
        f = crossref_fields(work)
        if title_match(titles, work, f) >= CANDIDATE_SIMILARITY:
            first = next((a for a in work.get("author") or [] if isinstance(a, dict)), {})
            out.append(candidate("crossref", doi=doi, venue=f["venue"], year=f["year"], title=f["title"], type=f["type"],
                                 first_author=first_str(first.get("family") or first.get("name")) or None))
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
    """One entry per DOI, its sources listed; an entry without a DOI (a journal_ref alone) stays as it is."""
    merged = []
    for c in found:
        same = c["doi"] and next((m for m in merged if m["doi"] and m["doi"].lower() == c["doi"].lower()), None)
        if not same:
            merged.append({**c, "sources": [c["source"]]})
            continue
        for key in ("venue", "year", "title", "type", "journal_ref", "first_author"):
            if same.get(key) is None and c.get(key) is not None:
                same[key] = c[key]
        if c["source"] not in same["sources"]:
            same["sources"].append(c["source"])
    keys = {paper.norm_title(t) for t in titles}
    out = []
    for m in merged:
        entry = {"ids": {"doi": m["doi"]}, **{k: m.get(k) for k in ("venue", "year", "title")}}
        entry.update(title_differs=None if not m["title"] else paper.norm_title(m["title"]) not in keys,
                     type=CSL_TYPES.get(m.get("type"), m.get("type")), sources=m["sources"])
        out.append({**entry, **{k: m[k] for k in ("first_author", "journal_ref") if m.get(k)}})
    return out


def versions_of_preprint(s, aid, csl, alt_titles, old=None):
    """A preprint's versions: itself (arXiv's latest vN and comment) and its published versions. `old`: the versions
    an earlier identify found; a source that does not answer now keeps what it gave then."""
    titles = [t for t in [csl.get("title"), *alt_titles] if isinstance(t, str) and t.strip()]
    entry, arxiv_code = s.arxiv_entry(aid)
    answers, codes = {"arxiv": from_arxiv(entry), "crossref": []}, {"arxiv": arxiv_code, "crossref": "no_title"}
    if titles:
        try:
            answers["crossref"] = crossref_search(s, titles, paper.first_surname(csl.get("author")))
            codes["crossref"] = "ok"
        except web.NoData as e:
            codes["crossref"] = e.code
    complete(s, answers["arxiv"], answers["crossref"])
    silent, old = sorted(k for k, code in codes.items() if code not in ANSWERED), old or {}
    for source in silent:
        answers[source] = [candidate(source, doi=(c.get("ids") or {}).get("doi"), venue=c.get("venue"), year=c.get("year"),
                                     title=c.get("title"), type=c.get("type"), journal_ref=c.get("journal_ref"))
                           for c in old.get("published") or [] if isinstance(c, dict) and source in (c.get("sources") or [])]
    said = (old.get("preprint") or {}) if "arxiv" in silent else entry
    preprint = {"ids": {"arxiv": aid, "doi": f"10.48550/arXiv.{aid}"}, "latest": said.get("latest", said.get("version")),
                "comment": said.get("comment"), "title": csl.get("title"), "abstract": csl.get("abstract"),
                "author": csl.get("author") or [], **({"categories": csl["categories"]} if csl.get("categories") else {})}
    return {"preprint": preprint, "published": merge_candidates(answers["arxiv"] + answers["crossref"], titles),
            "incomplete": silent}


# ---- slugs and the results there already ----------------------------------------------------------------------

def derive_slug(csl):
    """<first author's surname><year><first title word of 4+ letters> (liu2022progressive); '' when nothing is usable."""
    parts = ((csl.get("issued") or {}).get("date-parts") or [[None]])[0] or [None]
    year = str(parts[0]) if isinstance(parts[0], int) else ""
    word = next((w for w in re.findall(r"[^\W_]+", csl.get("title") or "") if sum(ch.isalpha() for ch in w) >= 4), "")
    return clean(paper.first_surname(csl.get("author"))) + year + clean(word)


def known(work):
    """The results there: {the request's key and its ids' keys: slug}."""
    out = {}
    for res in run.results_of(work):
        keys = [request_key((res.get("request") or {}).get("given")), (res.ids.get("doi") or "").lower(),
                (res.ids.get("arxiv") or "").lower()]
        for key in keys:
            if key:
                out.setdefault(key, res.slug)
    return out


def for_good(res):
    """Whether a result there is identified for good: not a stub, its versions complete or chosen (redrafted)."""
    return not res.stub and (bool((res.get("request") or {}).get("redraft"))
                             or not (res.get("versions") or {}).get("incomplete"))


def lookups_due(res):
    """Whether a result's OpenAlex / Europe PMC lookups are to be made (never made, or a source did not answer)."""
    done = res.get("enrichment")
    return not res.stub and (not isinstance(done, dict) or bool(done.get("incomplete")))


def expect(s, work, items, seen):
    """Tell the session the arXiv ids and DOIs this run will ask about, so that each source is asked for them
    together: every item's, but those of results there for good (their DOI still, when its lookups are due)."""
    aids, dois = [], []
    for ident, _ in items:
        try:
            doi, aid, _ = parse_identifier(ident)
        except cli.Stop:
            continue
        there = seen["known"].get(request_key(ident))
        res = run.read(work.results / f"{there}.json") if there else None
        if res is None or not for_good(res):
            aids += [aid.lower()] if aid else []
            dois += [doi] if doi != "page" else []
        elif lookups_due(res) and res.ids.get("doi"):
            dois.append(res.ids["doi"])
    s.expect(aids, dois)


# ---- identify one -------------------------------------------------------------------------------------------

def identify(s, work, ident, cite, wanted, seen):
    raw = ident.strip()
    doi, aid, version = parse_identifier(raw)
    key = request_key(raw)
    if key in seen["this_run"]:
        slug = seen["this_run"][key]
        return cli.skipped("duplicate", slug=slug, path=str(work.results / f"{slug}.json"))
    slug = safe_slug(cite) if cite else None
    there, renamed, refused = seen["known"].get(key), None, None
    if there:
        res = run.read(work.results / f"{there}.json")
        if slug and slug != there:
            moved = reslug(work, res, slug, seen)
            renamed, refused = (there, None) if moved else (None, slug)
            res, there = moved or res, slug if moved else there
        if for_good(res):                             # its version is chosen, or complete: kept, never the preprint again
            seen["this_run"][key] = there
            silent = touch(s, res, cite, wanted)
            if renamed:
                return {"slug": there, "path": str(res.path), "renamed_from": renamed,
                        **({"incomplete": silent} if silent else {})}
            return cli.skipped("exists", slug=there, path=str(res.path), **({"slug_not_applied": refused} if refused else {}),
                               **({"incomplete": silent} if silent else {}))
        slug = there                                  # a stub, or versions to complete: written again in place
    if slug and slug != there and (work.results / f"{slug}.json").exists():
        other = run.read(work.results / f"{slug}.json")
        if not other.stub and request_key((other.get("request") or {}).get("given")) != key:
            raise cli.Stop("slug_taken", slug=slug, hint="That slug names another paper's result: give another slug.")
    warnings = []
    try:
        if doi == "page":
            csl, final, page_doi = from_page(s, aid, warnings)
            ids = {"doi": paper.normalize_doi(page_doi or "") or None, "arxiv": None}
            record_of = "published"
        else:
            csl, doi = from_doi(s, doi, aid, warnings)
            ids = {"doi": doi, "arxiv": aid.lower() if aid else None}
            record_of = "preprint" if aid else "published"
    except cli.Stop as stop:
        if stop.code not in ("no_csl_record", "page_unreachable", "no_citation_meta"):
            raise
        slug = slug or free(work, clean(re.sub(r"^https?://(www\.)?", "", raw), 48) or "paper", key, seen)
        write(work, slug, {**head(slug, cite, wanted, result_at(work, slug)), "request": {"given": raw},
                           "warnings": [stop.code]})
        seen["this_run"][key] = slug
        raise cli.Stop(stop.code, hint=stop.hint, slug=slug, path=str(work.results / f"{slug}.json"),
                       stub=True, **stop.extra) from None
    if not slug:
        slug = free(work, derive_slug(csl) or clean(raw, 60) or "paper", key, seen)
    path, old = work.results / f"{slug}.json", result_at(work, slug)  # versions completed, or a stub replaced
    alt = [t for t in (old or {}).get("alt_titles") or [] if isinstance(t, str)]
    versions = (versions_of_preprint(s, aid.lower(), csl, alt, old.get("versions") if old else None)
                if record_of == "preprint" and aid else {"published": [], "incomplete": []})
    enrichment = enrich(s, ids["doi"], csl, warnings, old)
    silent = enrichment["incomplete"]
    result = {**head(slug, cite, wanted, old), "request": {"given": raw}, "record_of": record_of,
              "ids": ids_of_csl(ids, csl), "csl": csl, "alt_titles": alt, "versions": versions,
              "enrichment": enrichment, "warnings": warnings}
    for k in ("files", "set_aside", "outcome", "settled_at", "renamed_from"):     # what was got stays
        if old and k in old:
            result[k] = old[k]
    write(work, slug, result)
    seen["this_run"][key] = slug
    incomplete = sorted(versions["incomplete"] + silent)
    return {"slug": slug, "path": str(path), "record_of": record_of, "title": (csl.get("title") or "")[:80],
            **({"versions": len(versions["published"])} if record_of == "preprint" else {}),
            **({"incomplete": incomplete} if incomplete else {}),
            **({"renamed_from": renamed} if renamed else {}), **({"slug_not_applied": refused} if refused else {}),
            **({"warnings": warnings} if warnings else {})}


def result_at(work, slug):
    path = work.results / f"{slug}.json"
    return run.read(path) if path.exists() else None


def head(slug, cite, wanted, old):
    """A result's head: its slug, and slug_given, cite and wanted as given now, else as `old` (the result there, or
    None) has them."""
    old = old or {}
    cite = cite or old.get("cite")
    return {"slug": slug, "slug_given": bool(cite and safe_slug(cite) == slug) or bool(old.get("slug_given")),
            **({"cite": cite} if cite else {}), "wanted": wanted or old.get("wanted") or "published"}


def touch(s, res, cite, wanted):
    """A result kept as it is: the key and the version given now written into it, its lookups made when due -> the
    sources that still did not answer."""
    before = json.dumps(res, sort_keys=True)
    res.update({k: v for k, v in (("cite", cite), ("wanted", wanted)) if v})
    silent = []
    if lookups_due(res):
        warnings = [w for w in res.get("warnings") or [] if isinstance(w, str)]
        enrichment = enrich(s, res.ids.get("doi"), res.csl, warnings, res)
        silent = enrichment["incomplete"]
        res.update(ids=ids_of_csl(dict(res.ids), res.csl), enrichment=enrichment, warnings=warnings)
    if json.dumps(res, sort_keys=True) != before:
        res.save()
    return silent


def reslug(work, res, slug, seen):
    """A slug given for a paper whose result has a derived one: the result renamed to it -> the renamed result; None
    when the result has its own given slug, or the name is taken, or fetching has begun (its files and log name the
    old slug)."""
    old = res.slug
    if (res.get("slug_given") or (work.results / f"{slug}.json").exists() or work.files_of(old)
            or any(e.get("slug") == old for e in work.events())):
        return None
    write(work, slug, {**res, "slug": slug, "slug_given": True,
                       "renamed_from": list(dict.fromkeys([*(res.get("renamed_from") or []), old]))})
    res.path.unlink()
    for k, v in list(seen["known"].items()):
        if v == old:
            seen["known"][k] = slug
    return run.read(work.results / f"{slug}.json")


def free(work, base, key, seen):
    """base, else base-2, -3 ...: the first name no other paper's result has (a stub of this same request may be
    replaced)."""
    slug, n = base, 1
    while slug in seen["this_run"].values() or (work.results / f"{slug}.json").exists():
        other = run.read(work.results / f"{slug}.json") if (work.results / f"{slug}.json").exists() else None
        if other is not None and other.stub and request_key((other.get("request") or {}).get("given")) == key:
            return slug
        n += 1
        slug = f"{base}-{n}"
    return slug


def write(work, slug, result):
    work.results.mkdir(parents=True, exist_ok=True)
    run.atomic_write(work.results / f"{slug}.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")


# ---- redraft ------------------------------------------------------------------------------------------------

def redraft(s, res, target, body=None):
    """The result becomes the published version given by DOI or page (`body`: the page's HTML, saved from the
    browser); the preprint stays in versions.preprint."""
    warnings = []
    doi, aid, _ = ("page", target, "") if body is not None else parse_identifier(target)
    if doi == "page":
        csl, final, page_doi = from_page(s, aid, warnings, body)
        new_doi = paper.normalize_doi(page_doi or "") or None
    else:
        if aid:
            return {"code": "not_published", "hint": "A 10.48550 DOI is the arXiv preprint itself: give the published "
                                                     "version's DOI."}
        if (res.ids.get("doi") or "").lower() == doi.lower():
            return cli.skipped("same_doi", path=str(res.path))
        csl, new_doi = from_doi(s, doi, None, warnings)
    old = res.csl
    versions = dict(res.get("versions") or {"published": [], "incomplete": []})
    if res.get("record_of") == "preprint" and not versions.get("preprint"):
        versions["preprint"] = {"ids": {k: res.ids.get(k) for k in ("arxiv", "doi")}, "title": old.get("title"),
                                "abstract": old.get("abstract"), "author": old.get("author") or [],
                                **({"categories": old["categories"]} if old.get("categories") else {})}
    alt = [t for t in res.get("alt_titles") or [] if isinstance(t, str)]
    old_title = first_str(old.get("title"))
    if old_title and paper.norm_title(old_title) not in {paper.norm_title(t) for t in [csl.get("title"), *alt]}:
        alt.append(old_title)
    preprint = versions.get("preprint") or {}
    if not csl.get("abstract") and preprint.get("abstract"):
        warnings = [w for w in warnings if w != NO_ABSTRACT]
        warnings.append(PREPRINT_ABSTRACT)
    authors = [a for a in preprint.get("author") or [] if isinstance(a, dict)]
    if doi == "page" and csl.get("author") and authors and len(csl["author"]) != len(authors):
        warnings.append(f"the page lists {len(csl['author'])} authors, the preprint {len(authors)}: check the creators")
    if not res.stub and not (res.ids.get("arxiv") or (preprint.get("ids") or {}).get("arxiv")):
        warnings.append("no arXiv id on the result before the redraft: no preprint route to its text and no arXiv "
                        "line for the item")
    enrichment = enrich(s, new_doi, csl, warnings)
    silent = enrichment["incomplete"]
    res.update(record_of="published", ids=ids_of_csl({"doi": new_doi, "arxiv": None}, csl), csl=csl, alt_titles=alt,
               versions=versions, enrichment=enrichment, warnings=warnings)
    res["request"] = {**(res.get("request") or {}), "redraft": target}
    res.setdefault("wanted", "published")
    res.save()
    return {"code": "ok", "redraft": target, "path": str(res.path), "title": (csl.get("title") or "")[:80],
            **({"alt_titles": alt} if alt else {}), **({"incomplete": silent} if silent else {}),
            **({"warnings": warnings} if warnings else {})}




# ---- search -------------------------------------------------------------------------------------------------

def same_name(a, b):
    """Whether two surnames are one, accents, case and spacing aside (or one holds the other: van der Maaten, Maaten)."""
    a, b = clean(a), clean(b)
    return bool(a and b and (a in b or b in a))


def search(title, author):
    """Crossref's candidates for a title, a line each as it comes -> OK, or ACT when there is none."""
    s = Session()
    try:
        works = crossref_works(s, title, author, 5, select="DOI,title,subtitle,container-title,type,issued,event,author")
    except web.NoData as e:
        raise cli.Stop("source_blocked" if e.code == "source_blocked" else "crossref_unreachable", exit=cli.CANNOT,
                       hint="Crossref did not answer; try the opencli adapters (SKILL.md, Identify a paper).", **e.extra) from None
    for work in works:
        f = crossref_fields(work)
        families = [first_str(a.get("family") or a.get("name")) for a in work.get("author") or [] if isinstance(a, dict)]
        line = {"doi": first_str(work.get("DOI")), "title": f["title"], "venue": f["venue"], "year": f["year"],
                "type": CSL_TYPES.get(f["type"], f["type"]), "authors": families,
                "similarity": round(title_match([title], work, f), 2), "code": "ok"}
        if author and not same_name(author, families[0] if families else ""):
            line["first_author_differs"] = True
        cli.emit(line)
    return cli.OK if works else cli.ACT


# ---- the commands -------------------------------------------------------------------------------------------

LIST_HINT = ("A list holds one paper a line: an ID, a TAB and a citation key optional (what p2z.py ids prints), or "
             "one of our JSON lines with `id` (identify's own; a judge's pin lines: jq -c 'select(.id)'). A search "
             "line is a candidate, not an ID: confirm a candidate (title, first author), then `pf.py identify <doi>`. "
             "Nothing was done.")


def default_dir():
    return Path(os.environ.get("TMPDIR") or "/tmp") / "paper-fetch"


def items_of(values, slug):
    """The papers named after the options -> [(ID, citation key or None), or a JSON line to pass on]; `-` reads the
    list from stdin (LIST_HINT), blank and '#' lines skipped."""
    out = []
    for value in values:
        if value != "-":
            out.append((value, slug))
            continue
        for n, line in enumerate(sys.stdin.read().splitlines(), 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            named, passed = cli.list_value(line.strip(), n, "id", LIST_HINT)
            if passed is not None:
                out.append(passed)
                continue
            ident, _, cite = named.partition("\t")
            out.append((ident.strip(), cite.strip() or None))
    return out


def identify_main(argv):
    """Identify papers: each DOI, arXiv id or paper page becomes a result file with the paper's metadata and versions.

Nothing is downloaded. Each paper gets <dir>/results/<slug>.json (pflib/run.py has the format), <dir> being -o's,
else ${TMPDIR:-/tmp}/paper-fetch/. An ID is a DOI, a doi.org url, an arXiv id or arxiv.org url, or a paper's page.
- reads a list from stdin: an ID a line, a TAB and a citation key after it optional (p2z.py ids prints these), or one
of our JSON lines by `id` (identify's own; a judge's pin lines, the null ones dropped: jq -c 'select(.id)'); blank and
'#' lines are skipped. A JSON line without `id` that reports a skip or a failure is passed on as it is; any other (a
search line, a pin line whose id is null) makes the list unreadable: nothing is done (invalid_list).

--slug KEY is a citation key (a .bib's, as it is): the result keeps it verbatim in `cite`, and its file-safe form
(unsafe characters as _) is the slug; without one the slug is <first author's surname><year><first title word of 4+
letters> (liu2022progressive), -2, -3 ... when another paper has it. --wanted is the version the caller wants (a
caller that keeps the preprint passes preprint). A result identified again keeps its slug_given, cite and wanted
unless given anew.

Metadata. A DOI's CSL-JSON comes from doi.org and is normalized into CSL's own vocabulary, which Crossref's records
do not use: types (journal-article -> article-journal, proceedings-article -> paper-conference, book-chapter ->
chapter, posted-content -> article, ...), keys (event -> event-title, an event object by its name, publisher-location
-> publisher-place, short-container-title -> container-title-short), a missing `issued` from published /
published-online / published-print / created (with a warning), the subtitle joined to the title, markup stripped
from title and abstract. A record whose DOI differs from the one asked for (an alias) gives its own, with a warning.
`source` is where the metadata came from, as Zotero's libraryCatalog says it: DOI.org (Crossref), DOI.org
(Datacite), or the page's host. What CSL has no variable for stays under its own name (arXiv's `categories`). A
chapter of a known proceedings series (LNCS and co., asked of Crossref once) becomes a paper-conference: the volume as
container-title, the series as collection-title. A paper's page is read over plain HTTP: its citation_* tags give
the CSL (paper-conference, article-journal or chapter by the venue tag; the abstract from citation_abstract, else a
description tag; a date as 2023-12-10, "10 December 2023" or "Dec 10, 2023", only its year when the rest is
ambiguous, as in 10/12/2023, with a warning).

Lookups. Every result with a DOI asks OpenAlex (filter doi:a|b|..., the config's openalex_key as api_key) and Europe
PMC (DOI:"a" OR ..., resultType core), 50 DOIs a request for all of a run's papers, for what its CSL lacks: the
abstract (Europe PMC's, which is PubMed's, else OpenAlex's, rebuilt from its inverted index; a warning names where
it came from, and says so when the two differ: Europe PMC's is kept), PMID and PMCID (Europe PMC's, else OpenAlex's),
and the authors' keywords as a list in `keyword` (Europe PMC's keywordList). OpenAlex's keywords, its model's guesses
from title and abstract, go to enrichment.openalex_keywords: a hint for whoever tags the paper, never metadata. A
source that does not answer (a network error, a 5xx, a 429) is in enrichment.incomplete and does not fail the line;
identifying the paper again asks it again, and what it gave before stays meanwhile.

Versions. An arXiv preprint gets versions.preprint (its ids, arXiv's latest vN and comment, title, abstract, authors,
arXiv's categories) and versions.published: the published versions the authors declared to arXiv, and Crossref works
whose title matches (90%), each {ids: {doi}, venue, year, title, title_differs, type, sources, first_author?}. arXiv
is asked once per 100 ids for all of a run's preprints. Sources that did not answer are in versions.incomplete, and
identifying the same id again asks them again (not once it is redrafted); a source still silent keeps what it gave
the last time (its published versions, arXiv's latest and comment). Choosing one is the caller's: then pf.py redraft.
A published paper's versions are empty.

One line per ID as it is done: {id, code, slug?, path?, record_of?, title?, versions?, incomplete?, warnings?}.
  ok                written; renamed_from: a key given for a paper whose result had a derived slug, now its name
  skipped           reason exists: a result for this paper is there; slug_not_applied: the key's slug, when
                    fetching had begun under the old one (the key is in cite); reason duplicate: the same paper
                    earlier in this run's input
  slug_taken        the key's slug names another paper's result: nothing written
  needs_pinning     a title, not an identifier (a `title:` line): find the paper's DOI or arXiv id first
  no_identifier     neither a DOI, an arXiv id nor a page url
  not_found         doi.org does not know the DOI
  no_csl_record     doi.org has no metadata for the DOI          a stub result is written: {slug, slug_given, cite?,
  page_unreachable  the page refuses a plain HTTP request         wanted, request, warnings}; files claimed for it are
  no_citation_meta  the page has no citation_title tag            checked against nothing (cannot_judge); identify it
                                                                  again, or redraft it (a page: with --html)
  doi_org_error     doi.org or the DOI's agency failed (5xx): run again later
Exit 0 = every line ok or skipped; 1 = not, then stderr's last line is {"summary": {total, ok, skipped, failed}};
2 = cannot go on (doi_org_unreachable; source_blocked: nothing is asked of the host before `until`; invalid_list),
then stderr's last line is {code, hint} and the IDs not done are not_run. Requests keep a gap per host, shared
through the machine's pace file (pflib/web.py); env DOI_BASE_URL, CROSSREF_BASE_URL, ARXIV_API_URL,
OPENALEX_BASE_URL, EUROPEPMC_BASE_URL point the services elsewhere (tests).

Examples:
  pf.py identify -o <dir>/ 1505.04597
  pf.py identify -o <dir>/ --slug He:2016:ResNet --wanted preprint 10.1109/CVPR.2016.90
  p2z.py ids refs.bib | pf.py identify -o <dir>/ -
"""
    p = cli.parser(identify_main.__doc__, sub="identify")
    p.add_argument("ids", nargs="*", metavar="ID", help="DOIs, arXiv ids or paper pages; - reads a list from stdin")
    p.add_argument("-o", "--output", metavar="DIR/", help="the run's directory (default: ${TMPDIR:-/tmp}/paper-fetch/)")
    p.add_argument("--slug", metavar="KEY", help="the citation key (cite; its file-safe form names the result); one ID")
    p.add_argument("--wanted", choices=WANTED, help="the version the caller wants (default: published)")
    args = cli.parse(p, argv)
    if not args.ids:
        p.error("name the papers: DOIs, arXiv ids or pages, or - to read a list from stdin")
    if args.slug and (len(args.ids) != 1 or args.ids == ["-"]):
        p.error("--slug names one ID's result")
    work = run.Work(args.output or default_dir())

    def all_of():
        items = items_of(args.ids, args.slug)
        if not items:   # `-` with an empty list: nothing to do
            return cli.OK
        work.root.mkdir(parents=True, exist_ok=True)
        s, seen = Session(), {"known": known(work), "this_run": {}}
        expect(s, work, [i for i in items if isinstance(i, tuple)], seen)
        out = cli.Lines()
        for item in items:
            if isinstance(item, dict):
                out.put(item)
                continue
            ident, cite = item
            out.add({"id": ident}, lambda: identify(s, work, ident, cite, args.wanted, seen))
        return out.finish()

    return cli.run(all_of)


def search_main(argv):
    """Crossref's top 5 for a title, for an agent to judge; writes nothing.

The words after the options make one query, quoted or not. One line per candidate as Crossref orders them,
unfiltered: {doi, title, venue, year, type, authors: [family names], similarity: the title's to the query (0..1),
first_author_differs?: true when --author is given and is not the first author's, code: ok}. Which one is the paper
is the judge's or the agent's call: a candidate is no ID, so identify reads none of these lines; confirm one (title,
first author), then pf.py identify <its doi>.
Exit 0 = candidates; 1 = none (as grep), stderr empty; 2 = crossref_unreachable, or source_blocked (Crossref answered
429: ask again after `until`), then stderr's last line is {code, hint}.

Examples:
  pf.py search U-Net: Convolutional Networks for Biomedical Image Segmentation --author Ronneberger
  pf.py search "Deep residual learning for image recognition" > <dir>/scratch/search/3.jsonl
"""
    p = cli.parser(search_main.__doc__, sub="search")
    p.add_argument("words", nargs="*", metavar="WORD", help="the title, or words of it: one query")
    p.add_argument("--author", metavar="NAME", help="the first author's surname")
    args = cli.parse(p, argv)
    if not args.words:
        p.error("name the title to search for")
    return cli.run(lambda: search(" ".join(args.words), args.author))


def redraft_main(argv):
    """Make a result the published version's: TARGET is that version's DOI, or its page.

The result's metadata becomes TARGET's; the preprint stays in versions.preprint, its title joins alt_titles, files
already got stay; warnings when the page and the preprint list different numbers of authors, and when the result had
no arXiv id (no preprint route to its text, no arXiv line for the item). The operand ending in .json is the result,
the other TARGET, in either order. --html FILE reads the page from FILE, its HTML as the browser saved it, through
the same parser, TARGET then the url it came from: for a page that refuses plain HTTP. A stub result
(page_unreachable) is filled the same way.

One line: {slug, code, redraft?, path?, title?, alt_titles?, incomplete?, warnings?}.
  ok                written
  skipped           reason same_doi: the result has that DOI already
  not_published     a 10.48550 DOI is the arXiv preprint itself: give the published version's
  result_invalid    the result is not there, or not a result
  and identify's codes for TARGET: not_found, no_csl_record, page_unreachable, no_citation_meta, doi_org_error
Exit 0 = ok or skipped; 1 = not, the line says why; 2 = cannot go on (doi_org_unreachable; source_blocked; --html's
file_not_found), then stdout is empty and stderr's last line is {code, hint}.

Examples:
  pf.py redraft 10.1007/978-3-319-24574-4_28 <dir>/results/ronneberger2015unet.json
  pf.py redraft https://example.org/paper/1 <dir>/results/<slug>.json --html <dir>/scratch/pages/<slug>.html
"""
    p = cli.parser(redraft_main.__doc__, sub="redraft")
    p.usage = f"{p.prog} [-h] [--html FILE] TARGET RESULT"
    p.add_argument("operands", nargs="*", metavar="TARGET RESULT",
                   help="the published version's DOI or page url, and the result: <dir>/results/<slug>.json")
    p.add_argument("--html", metavar="FILE", help="the page's HTML, saved from the browser; TARGET is the page's url")
    args = cli.parse(p, argv)
    result, others = cli.split_result(p, args.operands)
    if len(others) != 1:
        p.error("name one target: the published version's DOI, or its page's url")
    target = others[0]
    if args.html and not re.match(r"https?://", target, re.I):
        p.error("--html goes with a target that is the url of the page the HTML was saved from")

    def one():
        if args.html and not Path(args.html).is_file():
            raise cli.Stop("file_not_found", exit=cli.CANNOT, path=args.html,
                           hint="No such file: --html names the page's HTML as the browser saved it.")
        try:
            res = run.read(result)
            line = {"slug": res.slug, **redraft(Session(), res, target,
                                                Path(args.html).read_bytes() if args.html else None)}
        except cli.Stop as stop:
            if stop.exit == cli.CANNOT:
                raise
            line = stop.line(slug=Path(result).stem)
        cli.emit(cli.tidy(line))
        return cli.ACT if cli.outcome(line) == "failed" else cli.OK

    return cli.run(one)


COMMANDS = {"identify": identify_main, "search": search_main, "redraft": redraft_main}


def main(argv=None):
    name, rest = cli.subcommand(__doc__, COMMANDS, argv)
    return COMMANDS[name](rest)


if __name__ == "__main__":
    raise SystemExit(main())
