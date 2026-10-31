"""What a paper is, as rules only: identifiers, titles, attachment titles read back and ranked, tags, creators,
citation keys. No I/O here.

An attachment's title says which version of the paper it is and where it came from, in the scheme titles.py holds
(paper-fetch's, of which p2z carries a copy): Preprint-arXiv-v7, Accepted-CVF, Published-Elsevier-in_press,
Snapshot-IEEE, Unknown. Here it is read back (attachment_label), ranked (ordered) and judged replaced by another
(superseded). A title outside the scheme (Zotero's "Full Text PDF", an older run's "Preprint (arXiv)") says nothing
about the version.
"""
import difflib
import re
import unicodedata
import urllib.parse
from urllib.parse import unquote

from .titles import SOURCES, VERSIONS, label_title, parse_title  # noqa: F401 (label_title: zotero.py's)

CHILD_TYPES = {"attachment", "note", "annotation"}
ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})"
DOI_FORM = re.compile(r"^10\.\d{4,9}/\S+$")
TEX_SPECIAL = re.compile(r"[\\^_&%$#{}~]")


def is_top(data):
    """A regular item: not an attachment, note or annotation, and no parent."""
    return data.get("itemType") not in CHILD_TYPES and not data.get("parentItem")


def is_pdf(data):
    """A PDF attachment."""
    return data.get("itemType") == "attachment" and data.get("contentType") == "application/pdf"


PACKAGE = "application/zip"


def is_package(data, pdf_titles):
    """A PDF's structured package (structured.py): a zip attachment under the title of one of the item's PDFs. A zip
    under a title of its own is an ordinary file, such as a supplement's source data."""
    return (data.get("itemType") == "attachment" and data.get("contentType") == PACKAGE
            and data.get("title") in pdf_titles)


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


def same_paper(a, b):
    """Why two items are one paper: "doi" or "arxiv" (the same identifier), "title" (the same title, which alone
    proves nothing: the agent decides); None when nothing ties them."""
    (doi_a, aid_a), (doi_b, aid_b) = identifiers(a), identifiers(b)
    if doi_a and doi_a == doi_b:
        return "doi"
    if aid_a and aid_a == aid_b:
        return "arxiv"
    title = norm_title(a.get("title"))
    return "title" if title and title == norm_title(b.get("title")) else None


# ---- titles -------------------------------------------------------------------------------------------------

def norm_title(s):
    """NFKC, casefolded, letters and digits only (any script)."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", s or "").casefold() if ch.isalnum())


def title_similarity(a, b):
    """0..1 between two titles after norm_title."""
    a, b = norm_title(a), norm_title(b)
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


# ---- files and hosts ----------------------------------------------------------------------------------------

HTML_SNIFF = re.compile(rb"<(?:!doctype\s+html|html|head|body|title|meta)\b", re.I)


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


# ---- attachment titles --------------------------------------------------------------------------------------

# The versions of the paper itself, best first, as read back (lowercase); a supplement and a snapshot are not one.
PAPER_VERSIONS = ("published", "accepted", "preprint", "unknown")
ORDER = {v.lower(): n for n, v in enumerate(VERSIONS)}


def attachment_label(data, pdf_titles=()):
    """What an attachment's title says -> {version, source, detail, standard}. A title in the scheme: as written,
    standard True. Any other title: standard False, source None, and the version the content type alone gives —
    "unknown" for a PDF, "snapshot" for an HTML page; a link, or a file of another type, has version and standard
    None (a supplement in another format is read from a title in the scheme only). A structured package (is_package,
    given the titles of the item's PDFs) carries its PDF's title but is no version of the paper: version and
    standard None."""
    if is_package(data, pdf_titles):
        return {"version": None, "source": None, "detail": [], "standard": None}
    parsed = None if data.get("linkMode") == "linked_url" else parse_title(data.get("title"))
    if parsed:
        return {**parsed, "standard": True}
    version = None
    if data.get("linkMode") != "linked_url":
        version = {"application/pdf": "unknown", "text/html": "snapshot"}.get(data.get("contentType"))
    return {"version": version, "source": None, "detail": [], "standard": False if version else None}


def source_of(url):
    """The source a file's url names, by its host (SOURCES); None for a site not in the table. A proxied url is
    turned back into the publisher's before it comes here."""
    return by_host(host_of(url), SOURCES)


def version_number(detail):
    """The largest vN among the detail fields (v7 -> 7); 0 without one."""
    return max((int(d[1:]) for d in detail or () if re.fullmatch(r"v\d+", d)), default=0)


def ordered(attachments):
    """Attachments as read back (attachment_label's fields, with dateAdded) best first: the paper's versions —
    Published, Accepted, Preprint, Unknown; within one, final before in_press, the larger vN first (a file without
    one after those with one), the later added first — then supplements, snapshots, and the rest."""
    newest = sorted(attachments, key=lambda a: a.get("dateAdded") or "", reverse=True)
    return sorted(newest, key=lambda a: (ORDER.get(a.get("version"), len(ORDER)), "in_press" in (a.get("detail") or ()),
                                         -version_number(a.get("detail"))))


def superseded(attachments):
    """Which of one item's attachments another one replaces -> [(attachment, the one that replaces it)]. Only titles
    in the scheme that name a source count: of each version of the paper one per source stays, the first in ordered()
    (an older arXiv vN gives way to a newer one; an accepted manuscript stands beside the published version); among
    supplements one per source and detail; among snapshots one per source, the later added. Different sources stand
    side by side. A file without a vN beside one with a vN, the two alike otherwise, is no one's to replace: its
    version number is not known, so both stay."""
    groups = {}
    for a in ordered(attachments):
        if not a.get("standard") or not a.get("source"):
            continue
        version = a.get("version")
        if version in PAPER_VERSIONS:
            key = (version, a["source"])
        elif version == "supplement":
            key = ("supplement", a["source"], tuple(a.get("detail") or ()))
        elif version == "snapshot":
            key = ("snapshot", a["source"])
        else:
            continue
        groups.setdefault(key, []).append(a)
    return [(loser, group[0]) for group in groups.values() for loser in group[1:] if not undecided(loser, group[0])]


def undecided(a, b):
    """Two files alike but for a vN only one of them names: which is newer is not known."""
    def rank(x):
        return ORDER.get(x.get("version")), "in_press" in (x.get("detail") or ())
    return rank(a) == rank(b) and bool(version_number(a.get("detail"))) != bool(version_number(b.get("detail")))


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
