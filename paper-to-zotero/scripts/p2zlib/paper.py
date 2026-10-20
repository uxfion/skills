"""What a paper is, as rules only: identifiers, titles, the file kinds, tags, creators, citation keys. No I/O here.

The file kinds (one table for file names, attachment titles and which file is "the paper's PDF"):

  kind        version of the paper  file name               attachment title          rank as the paper's PDF
  published   published             <slug>.pdf              PDF                       1
  accepted    accepted manuscript   <slug>.accepted.pdf     Accepted manuscript       2
  preprint    preprint              <slug>.preprint.pdf     Preprint (<server>)       3
  supplement  -                     <slug>.supplement.pdf   Supplementary material    -
  snapshot    -                     <slug>.html             Snapshot                  -

Reading a kind back from an attachment title also knows the titles Zotero and older runs wrote ("Full Text PDF",
"Accepted Version", "Submitted Version", "arXiv Fulltext PDF", "Preprint PDF", ...).
"""
import difflib
import re
import unicodedata
from urllib.parse import unquote

CHILD_TYPES = {"attachment", "note", "annotation"}
ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})"
DOI_FORM = re.compile(r"^10\.\d{4,9}/\S+$")
TEX_SPECIAL = re.compile(r"[\\^_&%$#{}~]")

KINDS = {
    "published": {"version": "published", "suffix": ".pdf", "title": "PDF", "rank": 1},
    "accepted": {"version": "accepted", "suffix": ".accepted.pdf", "title": "Accepted manuscript", "rank": 2},
    "preprint": {"version": "preprint", "suffix": ".preprint.pdf", "title": "Preprint ({server})", "rank": 3},
    "supplement": {"version": None, "suffix": ".supplement.pdf", "title": "Supplementary material", "rank": None},
    "snapshot": {"version": None, "suffix": ".html", "title": "Snapshot", "rank": None},
}
# Title prefixes (casefolded) that name a kind, the ones this skill writes and the ones Zotero and older runs wrote.
TITLE_PREFIXES = (("preprint", "preprint"), ("submitted version", "preprint"), ("arxiv fulltext pdf", "preprint"),
                  ("accepted manuscript", "accepted"), ("accepted version", "accepted"),
                  ("supplement", "supplement"), ("snapshot", "snapshot"))


def is_top(data):
    """A regular item: not an attachment, note or annotation, and no parent."""
    return data.get("itemType") not in CHILD_TYPES and not data.get("parentItem")


def is_pdf(data):
    """A PDF attachment."""
    return data.get("itemType") == "attachment" and data.get("contentType") == "application/pdf"


def first_surname(creators):
    """The first author's surname (else the first creator's), for matching a byline or a search; None without one."""
    creators = [c for c in creators or [] if isinstance(c, dict)]
    chosen = [c for c in creators if c.get("creatorType") == "author"] or creators
    if not chosen:
        return None
    c = chosen[0]
    return (c.get("lastName") or "").strip() or (c.get("name") or "").strip().split(" ")[-1] or None


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


def doi_of(data, url=True):
    """The item's DOI: its DOI field, else a "DOI:" line in Extra, else (url=True) a doi.org url; '' when none."""
    doi = normalize_doi(data.get("DOI") or "")
    if not doi:
        m = re.search(r"(?mi)^\s*DOI:\s*(\S+)", data.get("extra") or "")
        doi = normalize_doi(m.group(1)) if m else ""
    if not doi and url:
        m = re.search(r"(?:dx\.)?doi\.org/(10\.[^?#\s]+)", data.get("url") or "", flags=re.I)
        doi = normalize_doi(unquote(m.group(1))) if m else ""
    return doi


def identifiers(data):
    """(DOI, arXiv id) of an item, '' when absent. An arXiv DOI (10.48550/arXiv.<id>) counts as the arXiv id; the id
    also comes from archiveID, an arxiv.org url or an "arXiv:" line in Extra."""
    doi, aid = doi_of(data), ""
    m = re.fullmatch(r"10\.48550/arxiv\.(.+)", doi)
    if m:
        doi, aid = "", normalize_arxiv(m.group(1))
    for source, pattern in ((data.get("archiveID"), rf"arxiv:\s*({ARXIV_ID})"),
                            (data.get("url"), rf"arxiv\.org/(?:abs|pdf)/({ARXIV_ID})"),
                            (data.get("extra"), rf"arxiv:\s*({ARXIV_ID})")):
        if aid:
            break
        m = re.search(pattern, source or "", flags=re.I)
        aid = normalize_arxiv(m.group(1)) if m else ""
    return doi, aid


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
        if low.endswith(KINDS[kind]["suffix"]):
            return kind
    return "published" if low.endswith(".pdf") else None


def kind_of_attachment(data):
    """The kind of a library attachment, from its title and content type; None for one that is none of them (a link)."""
    title = (data.get("title") or "").strip().casefold()
    for prefix, kind in TITLE_PREFIXES:
        if title.startswith(prefix):
            return kind
    if data.get("contentType") == "application/pdf":
        return "published"
    if data.get("contentType") == "text/html" and data.get("linkMode") in ("imported_url", "imported_file"):
        return "snapshot"
    return None


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


def preprint_server(url):
    """The preprint server a url belongs to, by host ("arXiv", "bioRxiv", ...); None for any other host."""
    host = re.sub(r"^[a-z]+://", "", (url or "").strip().lower()).split("/", 1)[0].split(":", 1)[0]
    return next((name for domain, name in PREPRINT_SERVERS.items() if host == domain or host.endswith("." + domain)), None)


def kind_rank(kind):
    """Order as "the paper's PDF": published, accepted, preprint, then the rest."""
    return (KINDS.get(kind) or {}).get("rank") or 9


def attachment_title(kind, server="arXiv", parent_type=None):
    """The title an attachment of this kind gets; a preprint item's own PDF is its version of record: "PDF"."""
    if kind == "preprint" and parent_type == "preprint":
        return KINDS["published"]["title"]
    return KINDS[kind]["title"].format(server=server)


# ---- tags, creators, citation keys --------------------------------------------------------------------------

def normalize_tags(raw):
    """[{"tag", "type"}] or plain strings (type 0) -> (tags, problems, warnings). A tag named twice keeps its last
    occurrence, with a warning; a type is 0 (manual) or 1 (automatic)."""
    if not isinstance(raw, list):
        return [], ['tags are a JSON list of "name" or {"tag": "name", "type": 0|1}'], []
    ordered, problems, warnings = {}, [], []
    for i, entry in enumerate(raw):
        if isinstance(entry, str):
            tag, kind = entry, 0
        elif isinstance(entry, dict):
            tag, kind = entry.get("tag"), entry.get("type", 0)
        else:
            problems.append(f"tags[{i}]: a string or {{\"tag\", \"type\"}}")
            continue
        if not isinstance(tag, str) or not tag.strip():
            problems.append(f"tags[{i}]: the tag must be a non-empty string")
            continue
        if isinstance(kind, bool) or kind not in (0, 1):
            problems.append(f"tags[{i}] ({tag!r}): type is 0 (manual) or 1 (automatic)")
            continue
        tag = tag.strip()
        if tag in ordered:
            warnings.append(f"tag {tag!r} given twice: the last one is kept")
            del ordered[tag]
        ordered[tag] = kind
    return [{"tag": t, "type": k} for t, k in ordered.items()], problems, warnings


def creator_problems(creators, allowed):
    """What is wrong with a creators list for an item type whose creator types are `allowed`; [] when nothing."""
    if not isinstance(creators, list):
        return ["creators is a list"]
    out = []
    for i, c in enumerate(creators):
        if not isinstance(c, dict) or c.get("creatorType") not in allowed:
            out.append(f"creators[{i}]: creatorType must be one of {', '.join(sorted(allowed))}")
            continue
        names = set(c) - {"creatorType"}
        if names != {"name"} and not (names <= {"firstName", "lastName"} and "lastName" in names):
            out.append(f"creators[{i}]: {{creatorType, lastName[, firstName]}} or {{creatorType, name}}")
    return out


def suggested_cite(cite):
    """A citation key holding a character TeX treats specially (^ _ & % $ # { } ~ \\) breaks \\cite{}: the key
    without them; None for a key that is fine."""
    return TEX_SPECIAL.sub("", cite) if cite and TEX_SPECIAL.search(cite) else None


def cite_problems(items):
    """Citation-key trouble across {item key: data}: {"missing": [keys], "duplicates": [{citationKey, keys}],
    "tex": [{key, citationKey, suggested}]}, each list empty when clean."""
    by_cite, missing, tex = {}, [], []
    for key, data in items.items():
        cite = (data.get("citationKey") or "").strip()
        if not cite:
            missing.append(key)
            continue
        by_cite.setdefault(cite, []).append(key)
        suggested = suggested_cite(cite)
        if suggested is not None:
            tex.append({"key": key, "citationKey": cite, "suggested": suggested})
    return {"missing": missing, "duplicates": [{"citationKey": c, "keys": ks} for c, ks in by_cite.items() if len(ks) > 1],
            "tex": tex}


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
SUPPLEMENT_HEAD = re.compile(r"^[ \t]*((?:online[ \t]+|electronic[ \t]+)?supplement(?:ary|al)[ \t]+"
                             r"(?:materials?|information|info|appendix|appendices|data|methods|online[ \t]+content))"
                             + HEADING_TAIL, re.M)
# Words that suggest supplementary material anywhere in a text, a weaker sign than the heading.
SUPPLEMENT_WORDS = re.compile(r"supplement(?:ary|al)|appendix", re.I)
