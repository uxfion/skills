"""Whether a file is the paper a result describes, judged from its first pages: the verdict, its evidence, its kind.

Text: pages 1-3 come from poppler's `pdftotext -f 1 -l 3 -enc UTF-8` (split at form feeds) and the page count from
`pdfinfo`. Without pdftotext on PATH no PDF can be checked: no_pdftotext (exit 2); install poppler-utils
(references/install.md).

Two ways to pass. A: the whole title, normalized (NFKC, casefold, letters and digits only), or one of the result's
`alt_titles`, occurs in a page's normalized text -> ok | ok_on_page_2 | ok_on_page_3. B: at least 80% of the words of
four or more letters of a title (ligatures, curly quotes and diacritics folded alike on both sides) occur in pages
1-3 (plain substrings, line-end hyphens joined, whitespace collapsed), AND the item's DOI occurs there too or the
first author's surname occurs in the byline (the first 1500 characters of page 1, where author lists are; a paper on
the same topic has most of the title's words and may cite "Author et al." in its introduction) -> ok_by_words.

Three outcomes (outcome()): only `ok`, the whole title on page 1, is certain enough to file a file: pass. A file that
certainly is not the paper is refused: not_a_pdf, doi_mismatch, not_the_article (REFUSE_CODES). Every other code is
uncertain — ok_on_page_2/3 (a paper citing this one prints its title in its first pages too), ok_by_words, a short
title (cannot_judge), no text layer, a veto on a title match, title_not_found — and the file is held for an agent to
look at (run.claim writes the handoff). A stub result, with no metadata to check against, files its file:
cannot_judge passes there.

Three failures that override a pass, each only when unambiguous. The head of page 1 is the text of page 1 before the
earliest position of a title (A), and never more than its first 500 characters; when no title is on page 1, it is
those first 500 characters (an HTML snapshot: its <title> and title meta tags before the title). A marker counts only
as a heading (paper.ERRATUM_HEAD, paper.SUPPLEMENT_HEAD): at the start of a line (after Author / Publisher at most)
and followed by a colon or the end of the line, or by a space and a dash or to / for / note / notice / regarding.
  erratum_suspected     the head has Correction / Corrigendum / Erratum / Retraction (plural forms too), and the
                        result's own title has none of these words
  supplement_suspected  the head has Supplementary / Supplemental Material / Information / Appendix / Data /
                        Methods / Online Content. Not checked when the file's kind is supplement or the result's
                        title says supplement
  doi_mismatch          page 1 prints at least one DOI, none is the item's, and the item's DOI occurs nowhere in
                        pages 1-3. Checked only when the file's kind is published and page 1 has no arXiv margin
                        stamp (accepted manuscripts and preprints print their own DOI). HTML: the page's citation_doi
                        / dc.identifier / prism.doi meta tags stand for page 1.

The file's kind (paper.KINDS: the version it was wanted as) is the one the caller gives, else the one its name
carries (<slug>.pdf published, <slug>.accepted.pdf, <slug>.preprint.pdf, <slug>.supplement.pdf, <slug>.html
snapshot), else published. What the file actually is, the agent settles from the evidence (its `label`):
arXiv's margin stamp on page 1 ("arXiv:2303.11366v4 [cs.AI] ...") is `evidence.arxiv_stamp`, the PDF's own dates
`evidence.pdf_dates`.

HTML snapshots: a file whose name does not end in .pdf and whose first 4 KB look like HTML (a .pdf holding HTML is a
failed download: not_a_pdf). Script, style, noscript, template and svg are dropped, tags removed, entities unescaped;
the <title>, citation_title, dc.title and og:title lines followed by the first 20000 characters of visible text are
page 1, and A / B apply. A page without any text -> not_the_article.

codes:
  pass:          ok (the whole title on page 1)
  refuse:        doi_mismatch | not_the_article (HTML) | not_a_pdf | file_not_found
  uncertain:     ok_on_page_2 | ok_on_page_3 (whole title on that page) | ok_by_words (path B) | erratum_suspected |
                 supplement_suspected | title_not_found | no_text_layer | cannot_judge (no title of 10 characters or more)
  cannot check:  no_pdftotext (exit 2)

evidence: page_count, pages_scanned (<= 3), extractor (pdftotext | html), page_chars, title_page (int | null),
matched_title, title_words ({share, found, total, missing} of the best title), doi_found (bool | null: item has no
DOI), first_author_found (bool | null), first_author_in_byline (in the first 1500 characters of page 1),
dois_on_page_1, erratum_marker, supplement_marker (str | null), doi_mismatch (bool | null: not checked), kind,
arxiv_stamp, supplementary, encrypted, text_chars, size_bytes,
pdf_version, pdf_dates ({created, modified} as pdfinfo -isodates prints them, each when the PDF has it), excerpt
(page 1), excerpt_page_2, excerpt_title_page (when the title is on a later page); HTML also html_title.

Use: check(path, result) -> {code, evidence, md5, kind}; with a cache, one file met by several results is read once.
Underneath, extract(path) reads a file and judge(extraction, **subject(result), kind=...) gives one verdict.
"""
import hashlib
import re
import shutil
import subprocess
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

from . import paper
from .cli import CANNOT, Stop, log

EXCERPT_CHARS = 1500     # of page 1, as evidence: far enough for a journal's online-first line ("Radiology 2022; 000:1-8")
EXCERPT_2_CHARS = 600    # of page 2, past a repository's cover sheet
SUPPLEMENT_SCAN = 600    # where page 1 is searched for words of supplementary material
MIN_TITLE_CHARS = 10
MAX_PAGES = 3
HEAD_CHARS = 500        # the head of page 1 never reaches further
WORD_SHARE = 0.8        # path B
BYLINE_CHARS = 1500     # path B: the first author counts here, before an introduction's citations
TOOL_TIMEOUT = 60       # seconds, for pdftotext / pdfinfo
HTML_SCAN_CHARS = 20_000
PASS_CODES = ("ok",)
REFUSE_CODES = ("not_a_pdf", "doi_mismatch", "not_the_article", "file_not_found")

ENCRYPT_RE = re.compile(rb"/Encrypt\s*(?:\d+\s+\d+\s+R|<<)")
TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")
# arXiv's margin stamp: "arXiv:2303.11366v4 [cs.AI] 10 Oct 2023", old style "arXiv:hep-th/9901001v1 [hep-th] ...".
ARXIV_STAMP_RE = re.compile(rf"arXiv:\s?{paper.ARXIV_ID}(?:v\d+)?\s*\[[^\]\n]{{2,24}}\]")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")
DOI_TRAIL = ".,;:)]}>'\"”’"
HTML_SKIP = {"script", "style", "noscript", "template", "svg"}
HTML_BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table", "section", "article", "header",
              "footer", "nav", "main", "aside", "h1", "h2", "h3", "h4", "h5", "h6", "title", "dd", "dt", "figcaption"}
HTML_TITLE_META = ("citation_title", "dc.title", "og:title")
HTML_DOI_META = ("citation_doi", "dc.identifier", "prism.doi", "bepress_citation_doi")
B_TRANSLATE = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
                             "’": "'", "‘": "'"})

HINTS = {
    "title_not_found": "compare `excerpt` and `title_words` with the title; the file's `file` handoff is the paper's "
                       "agent's to answer (pf.py answer HANDOFF accept | refuse | unknown)",
    "no_text_layer": "no extractable text (scanned, or encrypted beyond pdftotext); read the first page with the pdf "
                     "skill or by eye",
    "not_a_pdf": "not a PDF (an HTML page saved as .pdf?); fetch the file again",
    "cannot_judge": "title too short for the rule; judge from `excerpt`",
    "file_not_found": "check the path",
    "erratum_suspected": "page 1 opens with a correction / erratum / retraction notice (`erratum_marker`): the file "
                         "is the notice, not the paper; get the article itself, and check the result's DOI is not "
                         "the notice's",
    "supplement_suspected": "page 1 opens as supplementary material (`supplement_marker`): get the main article, or "
                            "name the file <slug>.supplement.pdf if the supplement is what is wanted",
    "doi_mismatch": "page 1 prints another DOI (`dois_on_page_1`): another paper or another version; check the "
                    "result's DOI, and name an accepted manuscript or preprint as such (<slug>.accepted.pdf, "
                    "<slug>.preprint.pdf)",
    "not_the_article": "a page without text, not the article; do not attach it",
    "no_pdftotext": "pdftotext / pdfinfo (poppler-utils, a system package) are required; tell the user and install "
                    "it only with their OK (references/install.md)",
}
# The evidence field a failing verdict's summary line carries.
EXTRA_FIELD = {"erratum_suspected": "erratum_marker", "supplement_suspected": "supplement_marker",
               "doi_mismatch": "dois_on_page_1"}


def clean(text):
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()


def normalize(text):
    """Rule A's form of a title or a page: markup dropped, then paper.norm_title."""
    return paper.norm_title(TAG_RE.sub(" ", text))


def fold(text):
    """Casefold without diacritics, for matching a surname or a marker as a word."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).casefold()


def doi_key(doi):
    """A DOI as compared: from '10.' on, lowercased, trailing punctuation stripped; None without one."""
    if not isinstance(doi, str):
        return None
    low = doi.strip().lower()
    i = low.find("10.")
    return (low[i:].rstrip(DOI_TRAIL) or None) if i >= 0 else None


def word_text(text):
    """Text as path B compares it: ligatures, quotes and accents folded, line-end hyphens joined, spaces collapsed."""
    return re.sub(r"\s+", " ", re.sub(r"-\n", "", fold(text.translate(B_TRANSLATE))))


# ---- what a result says its paper is ------------------------------------------------------------------------

def subject(res):
    """What a result says its paper is -> {title, alt_titles, doi, surname}, the keywords judge() takes."""
    sub = res.subject
    return {"title": sub.title, "alt_titles": sub.alt_titles, "doi": sub.doi, "surname": sub.surname}


# ---- poppler ------------------------------------------------------------------------------------------------

def no_pdftotext():
    return Stop("no_pdftotext", exit=CANNOT, hint=HINTS["no_pdftotext"])


def require_pdftotext():
    """Stop with no_pdftotext unless pdftotext is on PATH: for a script to call before it changes anything."""
    if not shutil.which("pdftotext"):
        raise no_pdftotext()


def tool(name, argv):
    """Run a poppler program -> CompletedProcess, or its status: absent | timeout | failed."""
    exe = shutil.which(name)
    if not exe:
        return "absent"
    try:
        return subprocess.run([exe, *argv], capture_output=True, timeout=TOOL_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "timeout"
    except OSError:
        return "failed"


def pdftotext_pages(pdf):
    """Pages 1-3 by pdftotext -> list of page texts ([] when it fails or finds no text)."""
    p = tool("pdftotext", ["-f", "1", "-l", str(MAX_PAGES), "-enc", "UTF-8", str(pdf.absolute()), "-"])
    if isinstance(p, str):
        if p == "absent":
            raise no_pdftotext()
        log(f"pdftotext {pdf.name}: {p}")
        return []
    if p.returncode != 0:
        log(f"pdftotext {pdf.name}: exit {p.returncode}")
        return []
    pages = p.stdout.decode("utf-8", errors="replace").split("\f")
    if len(pages) > 1 and not pages[-1].strip():
        pages.pop()  # every page ends with a form feed
    pages = [clean(page) for page in pages[:MAX_PAGES]]
    return pages if any(pages) else []


def first_pages(pdf):
    """The evidence excerpts of a PDF as pdftotext gives them: (page 1's first EXCERPT_CHARS characters, page 2's first
    EXCERPT_2_CHARS), each None when it cannot be read (no such file, no pdftotext, no text layer, no page 2)."""
    pdf = Path(pdf)
    if not pdf.is_file():
        return None, None
    p = tool("pdftotext", ["-f", "1", "-l", "2", "-enc", "UTF-8", str(pdf.absolute()), "-"])
    if isinstance(p, str) or p.returncode != 0:
        return None, None
    pages = [clean(t) for t in p.stdout.decode("utf-8", errors="replace").split("\f")] + ["", ""]
    return pages[0][:EXCERPT_CHARS] or None, pages[1][:EXCERPT_2_CHARS] or None


def pdfinfo(pdf):
    """The page count (None when pdfinfo cannot tell) and the PDF's own dates {created, modified} ({} without them)."""
    p = tool("pdfinfo", ["-isodates", str(pdf.absolute())])
    if isinstance(p, str):
        return None, {}
    m = re.search(rb"^Pages:\s+(\d+)", p.stdout, re.M)
    dates = {}
    for name, key in ((b"CreationDate", "created"), (b"ModDate", "modified")):
        d = re.search(rb"^" + name + rb":\s+(\S.*?)\s*$", p.stdout, re.M)
        if d:
            dates[key] = d.group(1).decode("latin-1")
    return (int(m.group(1)) if m else None), dates


# ---- HTML snapshots -----------------------------------------------------------------------------------------

class HtmlText(HTMLParser):
    """Visible text, <title> and meta tags of a page; script, style, noscript, template and svg dropped."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title, self.meta, self.skip, self.in_title = [], [], {}, 0, False

    def handle_starttag(self, tag, attrs):
        if tag in HTML_SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            a = {k.lower(): (v or "").strip() for k, v in attrs}
            name = (a.get("name") or a.get("property") or "").lower()
            if name and a.get("content"):
                self.meta.setdefault(name, []).append(a["content"])
        if tag in HTML_BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in HTML_SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "title":
            self.in_title = False
        if tag in HTML_BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip:
            return
        (self.title if self.in_title else self.parts).append(data)


def read_html(ex, data):
    """Fill an Extraction from an HTML page: the title lines, then the visible text, are its one page."""
    m = re.search(rb"charset\s*=\s*[\"']?([A-Za-z0-9_\-]+)", data[:4096], re.I)
    try:
        text = data.decode(m.group(1).decode("ascii") if m else "utf-8", errors="replace")
    except LookupError:
        text = data.decode("utf-8", errors="replace")
    parser = HtmlText()
    try:
        parser.feed(text)
        parser.close()
    except Exception as e:  # html.parser is lenient; whatever it got so far is used
        log(f"html {ex.path.name}: {e!r}")
    doc_title = clean(" ".join(parser.title))
    lines, seen = [], set()
    for t in [doc_title, *(v for name in HTML_TITLE_META for v in parser.meta.get(name, []))]:
        t = clean(t)
        if t and t.casefold() not in seen:
            seen.add(t.casefold())
            lines.append(t)
    titles = "\n".join(lines)
    visible = clean("".join(parser.parts))
    dois = []
    for name in HTML_DOI_META:
        for v in parser.meta.get(name, []):
            key = doi_key(v)
            if key and key not in dois:
                dois.append(key)
    ex.format, ex.extractor = "html", "html"
    ex.pages = [(titles + "\n" + visible[:HTML_SCAN_CHARS]).strip()]
    ex.text, ex.head_len = visible, len(titles)
    ex.html_title, ex.meta_dois = doc_title or None, dois


# ---- extraction ---------------------------------------------------------------------------------------------

class Extraction:
    """One file, read once: its format (pdf | html | other), pages 1-3, and the facts every verdict on it shares."""

    def __init__(self, path, data):
        self.path, self.size, self.md5 = path, len(data), hashlib.md5(data).hexdigest()
        self.format, self.pdf_version, self.encrypted, self.head_bytes = "other", None, False, data[:40].decode("latin-1")
        self.pages, self.count, self.extractor, self.text, self.head_len = [], None, None, "", HEAD_CHARS
        self.dates = {}
        self.html_title = self.meta_dois = None

    def prepare(self):
        """Derived forms of the pages, computed once for any number of results."""
        page1 = self.pages[0] if self.pages else ""
        self.norm_pages = [normalize(p) for p in self.pages]
        self.norm_scanned = "".join(self.norm_pages)
        scanned = "\n".join(self.pages)
        self.folded = fold(scanned)
        self.words_text = word_text(scanned)
        if self.meta_dois is not None:
            self.page1_dois = self.meta_dois
        else:
            self.page1_dois = list(dict.fromkeys(d.rstrip(DOI_TRAIL) for d in DOI_RE.findall(fold(page1))))
        m = ARXIV_STAMP_RE.search(page1) if self.format == "pdf" else None
        self.arxiv_stamp = m.group() if m else None
        return self


def extract(path):
    """Read one file -> Extraction, or None when there is no such file; no_pdftotext for a PDF without pdftotext."""
    path = Path(path)
    if not path.is_file():
        return None
    data = path.read_bytes()
    ex = Extraction(path, data)
    fmt = paper.file_format(data, path.name)
    if fmt != "pdf":
        if fmt == "html":
            read_html(ex, data)
        return ex.prepare()
    m = re.search(rb"%PDF-(\d\.\d)", data[:1024])
    ex.format, ex.pdf_version, ex.extractor = "pdf", m.group(1).decode("ascii") if m else None, "pdftotext"
    ex.encrypted = ENCRYPT_RE.search(data) is not None
    ex.pages = pdftotext_pages(path)
    ex.text = "\n".join(ex.pages)
    ex.count, ex.dates = pdfinfo(path)
    return ex.prepare()


def kind_of(path, given=None):
    """The file's kind: `given` (a link's "unknown" counts as none), else its name's, else published."""
    if given in paper.KINDS:
        return given
    if given not in (None, "unknown"):
        raise ValueError(f"not a file kind: {given!r}")
    return paper.kind_of_file(Path(path).name) or "published"


# ---- the verdict --------------------------------------------------------------------------------------------

def title_words(title, words_text):
    """Path B for one title -> (share found, report)."""
    words = re.findall(r"[a-z]{4,}", fold(title.translate(B_TRANSLATE)))
    missing = [w for w in words if w not in words_text]
    share = (len(words) - len(missing)) / len(words) if words else 0.0
    return share, {"share": round(share, 2), "found": len(words) - len(missing), "total": len(words),
                   "missing": missing[:12]}


def title_span(page, norm_title):
    """Raw (start, end) of the first occurrence of a normalized title in a page, by bisecting on normalize()."""
    lo, hi = 0, len(page)
    while lo < hi:  # the shortest prefix that holds it ends the first occurrence
        mid = (lo + hi) // 2
        if norm_title in normalize(page[:mid]):
            hi = mid
        else:
            lo = mid + 1
    end, lo, hi = lo, 0, lo
    while lo < hi:  # the latest start that still holds it begins that occurrence
        mid = (lo + hi + 1) // 2
        if norm_title in normalize(page[mid:end]):
            lo = mid
        else:
            hi = mid - 1
    return lo, end


def evidence_base(ex, kind):
    page1 = ex.pages[0] if ex.pages else ""
    ev = {"page_count": ex.count, "pages_scanned": len(ex.pages), "extractor": ex.extractor,
          "page_chars": [len(p) for p in ex.pages], "title_page": None, "matched_title": None, "title_words": None,
          "doi_found": None, "first_author_found": None, "first_author_in_byline": None,
          "dois_on_page_1": ex.page1_dois[:10], "erratum_marker": None, "supplement_marker": None,
          "doi_mismatch": None, "kind": kind, "arxiv_stamp": ex.arxiv_stamp,
          "supplementary": paper.SUPPLEMENT_WORDS.search(page1[:SUPPLEMENT_SCAN]) is not None,
          "encrypted": ex.encrypted, "text_chars": len(ex.text), "size_bytes": ex.size, "pdf_version": ex.pdf_version,
          "pdf_dates": ex.dates, "excerpt": page1[:EXCERPT_CHARS] if ex.format != "other" else ex.head_bytes,
          "excerpt_page_2": ex.pages[1][:EXCERPT_2_CHARS] if len(ex.pages) > 1 else None, "excerpt_title_page": None}
    if ex.format == "html":
        ev.update(html_title=ex.html_title)
    return ev


def judge(ex, title, alt_titles=(), doi=None, surname=None, kind="published"):
    """The verdict on one extracted file for one paper -> (code, evidence)."""
    ev = evidence_base(ex, kind)
    if ex.format == "other":
        return "not_a_pdf", ev
    if ex.format == "pdf" and not ex.text:
        return "no_text_layer", ev
    if ex.format == "html" and not ex.pages[0]:
        return "not_the_article", ev
    pages, page1 = ex.pages, ex.pages[0]
    titles = [t for t in dict.fromkeys([title, *alt_titles]) if t.strip()]
    a_titles = [(t, n) for t in titles if len(n := normalize(t)) >= MIN_TITLE_CHARS]

    # A: the first page that holds a whole title; the head of page 1 ends where a title starts.
    title_page = matched = None
    for k, norm_page in enumerate(ex.norm_pages, 1):
        matched = next((t for t, n in a_titles if n in norm_page), None)
        if matched:
            title_page = k
            break
    starts = [title_span(page1, n)[0] for t, n in a_titles if n in ex.norm_pages[0]]
    head = fold(page1[:min([ex.head_len, *starts])])

    rdoi = doi_key(doi)
    doi_found = None if not rdoi else normalize(rdoi) in ex.norm_scanned
    author_found = in_byline = None
    if surname:
        pattern = rf"(?<![^\W\d_]){re.escape(fold(surname))}(?![^\W\d_])"  # letter boundaries: 'Liu1' still matches
        author_found = re.search(pattern, ex.folded) is not None
        in_byline = author_found and re.search(pattern, fold(page1[:BYLINE_CHARS])) is not None

    # B: the best word share over all titles, corroborated by the DOI (pages 1-3) or the first author in the byline.
    share, words, b_title = 0.0, None, None
    for t in titles:
        s, report = title_words(t, ex.words_text)
        if words is None or s > share:
            share, words, b_title = s, report, t
    b_pass = share >= WORD_SHARE and bool(doi_found or in_byline)

    title_fold = fold(title)
    m = None if paper.ERRATUM_WORDS.search(title_fold) else paper.ERRATUM_HEAD.search(head)
    erratum = m.group(1) if m else None
    m = None if kind == "supplement" or "supplement" in title_fold else paper.SUPPLEMENT_HEAD.search(head)
    supplement = m.group(1) if m else None
    mismatch = None
    if kind == "published" and rdoi and not ex.arxiv_stamp:
        printed = ex.page1_dois
        mismatch = bool(printed) and not any(rdoi in d or d in rdoi for d in printed) and doi_found is False

    ev.update(title_page=title_page, title_words=words, doi_found=doi_found, first_author_found=author_found,
              first_author_in_byline=in_byline, erratum_marker=erratum, supplement_marker=supplement,
              doi_mismatch=mismatch,
              excerpt_title_page=pages[title_page - 1][:EXCERPT_CHARS] if title_page and title_page > 1 else None)
    if erratum:
        code = "erratum_suspected"
    elif supplement:
        code = "supplement_suspected"
    elif mismatch:
        code = "doi_mismatch"
    elif not a_titles:
        code = "cannot_judge"
    elif title_page:
        code = "ok" if title_page == 1 else f"ok_on_page_{title_page}"
    elif b_pass:
        code = "ok_by_words"
    else:
        code = "title_not_found"
    ev["matched_title"] = matched if title_page else b_title if code == "ok_by_words" else None
    return code, ev


def outcome(code, stub=False):
    """What a verdict does with the file -> pass (file it) | refuse (certainly not the paper) | uncertain (held for an
    agent). A stub result has nothing to check against: its cannot_judge passes."""
    if code in PASS_CODES or (stub and code == "cannot_judge"):
        return "pass"
    return "refuse" if code in REFUSE_CODES else "uncertain"


def check(path, rec, kind=None, cache=None):
    """The verdict on one file for one result -> {code, evidence, md5, kind}; file_not_found when there is no file.

    `kind` as kind_of() takes it. `cache` ({absolute path: Extraction}) reads a file once for several results; keep
    it no longer than the files stay unchanged."""
    path = Path(path)
    if cache is None:
        ex = extract(path)
    else:
        key = str(path.absolute())
        if key not in cache:
            cache[key] = extract(path)
        ex = cache[key]
    if ex is None:
        raise Stop("file_not_found", hint=HINTS["file_not_found"], file=str(path))
    kind = kind_of(path, kind)
    code, evidence = judge(ex, **subject(rec), kind=kind)
    return {"code": code, "evidence": evidence, "md5": ex.md5, "kind": kind}


def summary_fields(code, ev):
    """The short fields a script prints for one verdict, beside its code."""
    out = {"title_page": ev["title_page"], "page_count": ev["page_count"], "kind": ev["kind"]}
    if code in ("ok_by_words", "title_not_found") and ev["title_words"]:
        out["title_words"] = ev["title_words"]["share"]
    if code in EXTRA_FIELD:
        out[EXTRA_FIELD[code]] = ev.get(EXTRA_FIELD[code])
    return out
