"""What a paper is, as rules only: identifiers, titles, file kinds, the title a file is first proposed under,
notices. No I/O here.

A file in paper-fetch's directory sits beside its result and is named by the version it was wanted as (its kind):

  kind        file name
  published   <slug>.pdf
  accepted    <slug>.accepted.pdf
  preprint    <slug>.preprint.pdf
  supplement  <slug>.supplement.pdf
  snapshot    <slug>.html

What the file actually is goes into its label, an attachment title (titles.py).

The identifier and title rules (ARXIV_ID, DOI_FORM, normalize_doi, normalize_arxiv, norm_title, title_similarity,
file_format, host_of) are copied from paper-to-zotero/scripts/p2zlib/paper.py (commit 90cecdf).
"""
import difflib
import re
import unicodedata
import urllib.parse

from .titles import SOURCES, label_title

ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})"
DOI_FORM = re.compile(r"^10\.\d{4,9}/\S+$")

# The file kinds: the version a file was wanted as, and the file name that says so (<slug> + suffix).
KINDS = {"published": ".pdf", "accepted": ".accepted.pdf", "preprint": ".preprint.pdf",
         "supplement": ".supplement.pdf", "snapshot": ".html"}


# ---- identifiers --------------------------------------------------------------------------------------------

def normalize_doi(s):
    s = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", (s or "").strip(), flags=re.I)
    s = s.strip().lower()
    return s if DOI_FORM.match(s) else ""


def normalize_arxiv(s):
    """The bare id: no prefix, URL, .pdf or version suffix; old-style ids lowercased."""
    s = re.sub(r"^(?:https?://)?(?:www\.)?arxiv\.org/(?:abs|pdf)/", "", (s or "").strip(), flags=re.I)
    s = re.sub(r"^arxiv:\s*", "", s, flags=re.I)
    s = re.sub(r"\.pdf$", "", s, flags=re.I)
    s = re.sub(r"v\d+$", "", s)
    return s.strip().lower()


def first_surname(authors):
    """The first author's surname from CSL names ({family, given} or {literal}); None without one."""
    for a in authors or []:
        if isinstance(a, dict):
            name = (a.get("family") or "").strip() or ((a.get("literal") or "").strip().split(" ") or [""])[-1]
            if name:
                return name
    return None


# ---- titles -------------------------------------------------------------------------------------------------

def norm_title(s):
    """NFKC, casefolded, letters and digits only (any script)."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", s or "").casefold() if ch.isalnum())


def title_similarity(a, b):
    """0..1 between two titles after norm_title."""
    a, b = norm_title(a), norm_title(b)
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


# ---- file kinds ---------------------------------------------------------------------------------------------

def kind_of_file(name):
    """The kind a work-directory file name carries: <slug>.accepted.pdf -> accepted, <slug>.html -> snapshot, ..."""
    low = name.lower()
    if low.endswith((".html", ".htm")):
        return "snapshot"
    for kind in ("accepted", "preprint", "supplement"):
        if low.endswith(KINDS[kind]):
            return kind
    return "published" if low.endswith(".pdf") else None


HTML_SNIFF = re.compile(rb"<(?:!doctype\s+html|html|head|body|title|meta)\b", re.I)
PREPRINT_SERVERS = {"arxiv.org": "arXiv", "biorxiv.org": "bioRxiv", "medrxiv.org": "medRxiv", "ssrn.com": "SSRN",
                    "researchsquare.com": "Research Square", "preprints.org": "Preprints.org",
                    "openreview.net": "OpenReview", "chemrxiv.org": "ChemRxiv", "psyarxiv.com": "PsyArXiv"}


def file_format(body, name):
    """What a file's bytes are: "pdf" (a %PDF- header in the first KB), "html" (markup in the first 4 KB, under a
    name that does not end in .pdf: a .pdf holding HTML is a failed download), or None."""
    if b"%PDF-" in body[:1024]:
        return "pdf"
    if not name.lower().endswith(".pdf") and HTML_SNIFF.search(body[:4096]):
        return "html"
    return None


def host_of(url):
    """The url's host, lowercased, without port or credentials; a bare host counts; "" when it has none."""
    s = (url or "").strip()
    try:
        return (urllib.parse.urlsplit(s if "://" in s else "//" + s).hostname or "").lower()
    except ValueError:
        return ""


def by_host(host, table):
    """The table's value for the host or its closest listed parent domain; None when none is listed."""
    parts = (host or "").split(".")
    return next((table[".".join(parts[i:])] for i in range(len(parts) - 1) if ".".join(parts[i:]) in table), None)


def preprint_server(url):
    """The preprint server a url belongs to, by host ("arXiv", "bioRxiv", ...); None for any other host."""
    return by_host(host_of(url), PREPRINT_SERVERS)


# ---- proposals: the title a file is first proposed under ------------------------------------------------------

# Sites whose every file is one version unless shown otherwise (a preprint server's are preprints): the version
# proposed for their files whichever route reached them, and the version of their links (fulltext_links).
SITE_VERSIONS = {"arxiv.org": "Preprint", "biorxiv.org": "Preprint", "medrxiv.org": "Preprint"}
# The version a route proposes for what it fetched on any other site; the open route, a start page and a file that
# came another way (Downloads, a file the agent gave) propose nothing.
ROUTE_VERSIONS = {"publisher": "Published", "accepted": "Accepted", "preprint": "Preprint", "snapshot": "Snapshot"}
ARXIV_LINK = re.compile(rf"arxiv\.org/(?:pdf|abs)/({ARXIV_ID})(v\d+)?(?:\.pdf)?/?(?:$|[?#])", re.I)


def source_of(url):
    """The source a file's url names, by its host (SOURCES); None for a site not in the table. A proxied url is
    turned back into the publisher's before it comes here."""
    return by_host(host_of(url), SOURCES)


def arxiv_link(url):
    """The arXiv id and vN an arxiv.org abs or pdf url names ("https://arxiv.org/pdf/2303.11366v4" -> ("2303.11366",
    "v4")); (id, None) without a version, (None, None) for any other url."""
    m = ARXIV_LINK.search(url or "")
    return (normalize_arxiv(m.group(1)), (m.group(2) or "").lower() or None) if m else (None, None)


def proposal(route, url=None, given=None):
    """The title a file is proposed under, from how it came (the agent confirms it or writes another):
    {title, version, source, detail}. The version: the one the agent gave (`given`, a kind); a page the snapshot
    route saved is a Snapshot; else the site's (SITE_VERSIONS: a preprint server's file, whichever route reached it,
    as a preprint item's own DOI leads the publisher route to arXiv), else the route's (ROUTE_VERSIONS), else
    Unknown. The source is the url's site (SOURCES), the detail the url's arXiv vN."""
    if given or route == "snapshot":
        version = (given or route).capitalize()
    else:
        version = by_host(host_of(url), SITE_VERSIONS) or ROUTE_VERSIONS.get(route) or "Unknown"
    source, vn = source_of(url), arxiv_link(url)[1]
    detail = [vn] if vn else []
    return {"title": label_title(version, source, detail), "version": version.lower(), "source": source, "detail": detail}


# ---- what a first page says it is ---------------------------------------------------------------------------
# Matched on casefolded text, line by line. A heading, not a mention: line start, then a colon or the line's end,
# or a space and a dash or a linking word ("Correction-based" and "Supplemental content" are no headings). The
# lists are living: extend them when a real file shows a new form.

HEADING_TAIL = r"(?=[ \t]*(?:$|:)|[ \t]+(?:[\-–—]|(?:to|for|note|notice|regarding)\b))"
NOTICE_WORD = r"(?:corrections?|corrigend(?:um|a)|errat(?:um|a)|retractions?)"
# A correction, erratum or retraction notice, after Author / Publisher at most.
ERRATUM_HEAD = re.compile(r"^[ \t]*((?:(?:author|authors'?|publisher'?s?|editorial)[ \t]+)?" + NOTICE_WORD
                          + r"(?:[ \t]+(?:note|notice))?)" + HEADING_TAIL, re.M)
# A title with one of these words is a notice itself, or a paper about corrections.
ERRATUM_WORDS = re.compile(rf"\b{NOTICE_WORD}\b")
# A title that marks the paper itself as retracted ("RETRACTED: ...", "RETRACTED ARTICLE: ...").
RETRACTED_HEAD = re.compile(r"^[ \t]*(retracted(?:[ \t]+article)?)" + HEADING_TAIL)
SUPPLEMENT_HEAD = re.compile(r"^[ \t]*((?:online[ \t]+|electronic[ \t]+)?supplement(?:ary|al)[ \t]+"
                             r"(?:materials?|information|info|appendix|appendices|data|methods|online[ \t]+content))"
                             + HEADING_TAIL, re.M)
# Words that suggest supplementary material anywhere in a text, a weaker sign than the heading.
SUPPLEMENT_WORDS = re.compile(r"supplement(?:ary|al)|appendix", re.I)


def notice_title(title):
    """The words a title opens with when it names a correction, erratum or retraction notice ("Correction to: ...",
    "Author Correction: ...", "Retraction Note: ...") or a retracted paper ("RETRACTED: ..."), as the title spells
    them; None for an ordinary title."""
    title = (title or "").strip()
    m = ERRATUM_HEAD.match(title.casefold()) or RETRACTED_HEAD.match(title.casefold())
    return title[m.start(1):m.end(1)] if m else None
