"""What a paper is, as rules only: identifiers, titles, file kinds, attachment titles, tags, creators, citation keys.
No I/O here.

A file in an import run's work directory is named by the version it was wanted as (its kind):

  kind        file name
  published   <slug>.pdf
  accepted    <slug>.accepted.pdf
  preprint    <slug>.preprint.pdf
  supplement  <slug>.supplement.pdf
  snapshot    <slug>.html

What the file actually is goes into its attachment title, which says which version of the paper it is and where it
came from: <Version>-<Source>-<detail>..., such as Preprint-arXiv-v7, Accepted-CVF, Published-Elsevier-in_press,
Snapshot-IEEE, Unknown. Fields are separated by "-"; inside a field, spaces and hyphens become "_" (Europe_PMC,
ICLR_2027_submission). The version word is one of VERSIONS, capitalized; the source is a short brand name in its own
spelling; detail fields come only after a source, so without one the title is the version word alone. A version
the agent could not settle is Unknown: the file is attached all the same. SOURCES and the detail words (vN,
in_press, ICLR_2023, ICLR_2027_submission, source_data, abstract_booklet_p66) are a starting set the agent extends
on the same pattern. A title outside this scheme (Zotero's "Full Text PDF", an older run's "Preprint (arXiv)") says
nothing about the version.
"""
import difflib
import re
import unicodedata
from urllib.parse import unquote

CHILD_TYPES = {"attachment", "note", "annotation"}
ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})"
DOI_FORM = re.compile(r"^10\.\d{4,9}/\S+$")
TEX_SPECIAL = re.compile(r"[\\^_&%$#{}~]")

# The file kinds: the version a file was wanted as, and the file name that says so (<slug> + suffix).
KINDS = {"published": ".pdf", "accepted": ".accepted.pdf", "preprint": ".preprint.pdf",
         "supplement": ".supplement.pdf", "snapshot": ".html"}


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
    """The url's host, lowercased, without port; "" when it has none."""
    return re.sub(r"^[a-z][a-z0-9+.-]*://", "", (url or "").strip().lower()).split("/", 1)[0].split(":", 1)[0]


def by_host(host, table):
    """The table's value for the host or its closest listed parent domain; None when none is listed."""
    parts = (host or "").split(".")
    return next((table[".".join(parts[i:])] for i in range(len(parts) - 1) if ".".join(parts[i:]) in table), None)


def preprint_server(url):
    """The preprint server a url belongs to, by host ("arXiv", "bioRxiv", ...); None for any other host."""
    return by_host(host_of(url), PREPRINT_SERVERS)


# ---- attachment titles --------------------------------------------------------------------------------------

VERSIONS = ("Published", "Accepted", "Preprint", "Unknown", "Supplement", "Snapshot")
# The versions of the paper itself, best first, as read back (lowercase); a supplement and a snapshot are not one.
PAPER_VERSIONS = ("published", "accepted", "preprint", "unknown")
ORDER = {v.lower(): n for n, v in enumerate(VERSIONS)}
TITLE_RE = re.compile(r"^(" + "|".join(VERSIONS) + r")((?:-[\w.]+)*)$")
# Where a file came from, by host (a parent domain covers its subdomains) -> its source in the title. A starting
# table: a site not here gets its name from the agent, on the same pattern.
SOURCES = {
    "arxiv.org": "arXiv", "biorxiv.org": "bioRxiv", "medrxiv.org": "medRxiv", "ssrn.com": "SSRN",
    "researchsquare.com": "Research_Square", "openreview.net": "OpenReview", "thecvf.com": "CVF", "ecva.net": "ECVA",
    "papers.miccai.org": "MICCAI", "neurips.cc": "NeurIPS", "nips.cc": "NeurIPS", "mlr.press": "PMLR",
    "iclr.cc": "ICLR", "aclanthology.org": "ACL", "aaai.org": "AAAI", "jmlr.org": "JMLR", "ieee.org": "IEEE",
    "sciencedirect.com": "Elsevier", "sciencedirectassets.com": "Elsevier", "elsevier.com": "Elsevier",
    "springer.com": "Springer", "nature.com": "Nature", "acm.org": "ACM", "wiley.com": "Wiley", "rsna.org": "RSNA",
    "bmj.com": "BMJ", "nejm.org": "NEJM", "science.org": "Science", "mdpi.com": "MDPI", "jmir.org": "JMIR",
    "academic.oup.com": "OUP", "pmc.ncbi.nlm.nih.gov": "PMC", "ncbi.nlm.nih.gov": "PMC", "europepmc.org": "Europe_PMC",
    "hal.science": "HAL", "archives-ouvertes.fr": "HAL", "escholarship.org": "eScholarship",
    "researchgate.net": "ResearchGate", "easychair.org": "EasyChair",
}
# Sites whose every file is one version unless shown otherwise (a preprint server's are preprints): the version
# proposed for their files whichever route reached them, and the version of their links (fulltext_links).
SITE_VERSIONS = {"arxiv.org": "Preprint", "biorxiv.org": "Preprint", "medrxiv.org": "Preprint"}
# The version a route proposes for what it fetched on any other site; the open route, a start page and a file that
# came another way (Downloads, a file the agent gave) propose nothing.
ROUTE_VERSIONS = {"publisher": "Published", "accepted": "Accepted", "preprint": "Preprint", "snapshot": "Snapshot"}
ARXIV_LINK = re.compile(rf"arxiv\.org/(?:pdf|abs)/({ARXIV_ID})(v\d+)?(?:\.pdf)?/?(?:$|[?#])", re.I)


def title_field(text):
    """One field of an attachment title: spaces and hyphens become "_", characters other than letters, digits, "_"
    and "." are dropped ("Europe PMC" -> "Europe_PMC", "T-CAIREM" -> "T_CAIREM")."""
    s = re.sub(r"[^\w.]", "", re.sub(r"[\s\-]+", "_", str(text or "").strip()))
    return re.sub(r"_+", "_", s).strip("_.")


def label_title(version, source=None, detail=()):
    """The title of a file of this version (a word of VERSIONS, any case) from this source with this detail:
    "Preprint-arXiv-v7"; without a source, the version word alone."""
    word = next((v for v in VERSIONS if v.lower() == str(version).lower()), None)
    if word is None:
        raise ValueError(f"not a version: {version!r}; one of {', '.join(VERSIONS)}")
    source = title_field(source)
    return "-".join([word, source, *filter(None, map(title_field, detail))]) if source else word


def parse_title(title):
    """A title in the scheme -> {version (lowercase), source, detail: [fields]}; None for any other title."""
    m = TITLE_RE.match((title or "").strip())
    if not m:
        return None
    fields = m.group(2).split("-")[1:]
    return {"version": m.group(1).lower(), "source": fields[0] if fields else None, "detail": fields[1:]}


def attachment_label(data):
    """What an attachment's title says -> {version, source, detail, standard}. A title in the scheme: as written,
    standard True. Any other title: standard False, source None, and the version the content type alone gives —
    "unknown" for a PDF, "snapshot" for an HTML page; a link, or a file of another type, has version and standard
    None (a supplement in another format is read from a title in the scheme only)."""
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
    in the scheme that name a source count: among the paper's versions one per source stays, the first in ordered();
    among supplements one per source and detail; among snapshots one per source, the later added. Different sources
    stand side by side. A file without a vN beside one with a vN, the two alike otherwise, is no one's to replace:
    its version number is not known, so both stay."""
    groups = {}
    for a in ordered(attachments):
        if not a.get("standard") or not a.get("source"):
            continue
        version = a.get("version")
        if version in PAPER_VERSIONS:
            key = ("paper", a["source"])
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
