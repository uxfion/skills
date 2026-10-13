# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check that a PDF (or an HTML snapshot) is the paper an item describes, with evidence from its first pages, for one file, a stream of records, or one file against several records.

Text: pages 1-3 come from poppler's `pdftotext -f 1 -l 3 -enc UTF-8` (split at
form feeds) and the page count from `pdfinfo`. Both are required; without
pdftotext on PATH the script stops with no_extractor (exit 2): install
poppler-utils (references/install.md).

Two ways to pass. A: the whole title, normalized (NFKC, casefold, letters
and digits only), or one of the record's `alt_titles` / --alt-title, occurs in
a page's normalized text -> ok | ok_on_page_2 | ok_on_page_3. B: at least 80%
of the words of four or more letters of a title (ligatures, curly quotes and
diacritics folded alike on both sides) occur in pages 1-3 (plain substrings,
line-end hyphens joined, whitespace collapsed), AND the item's DOI occurs there
too or the first author's surname occurs in the byline (the first 1500
characters of page 1, where author lists are; a paper on the same topic has
most of the title's words and may cite "Author et al." in its introduction)
-> ok_by_words. Those four are the only passing codes.

Three failures that override a pass, each only when unambiguous. The head of
page 1 is the text of page 1 before the earliest position of a title (A), and
never more than its first 500 characters; when no title is on page 1, it is
those first 500 characters (an HTML snapshot: its <title> and title meta tags
before the title). A marker counts only as a heading: at the start of a line
(after Author / Publisher at most) and followed by a colon or the end of the
line, or by a space and a dash or to / for / note / notice / regarding.
  erratum_suspected     the head has Correction / Corrigendum / Erratum /
                        Retraction (plural forms too), and the record's own
                        title has none of these words
  supplement_suspected  the head has Supplementary / Supplemental Material /
                        Information / Appendix / Data / Methods / Online
                        Content. Not checked when the file's version is
                        supplement or the record's title says supplement
  doi_mismatch          page 1 prints at least one DOI, none is the item's,
                        and the item's DOI occurs nowhere in pages 1-3.
                        Checked only when the file's version is published
                        (accepted manuscripts and preprints print their own
                        DOI). HTML: the page's citation_doi / dc.identifier /
                        prism.doi meta tags stand for page 1.

The file's version comes from its name, the convention of the work
directory: <slug>.pdf published, <slug>.accepted.pdf, <slug>.preprint.pdf,
<slug>.supplement.pdf, <slug>.html snapshot; --file-version overrides it. A
file named as published whose page 1 carries arXiv's margin stamp
("arXiv:2303.11366v4 [cs.AI] ...") counts as a preprint; `evidence.arxiv_stamp`
holds the stamp.

HTML snapshots: a file whose name does not end in .pdf and whose first 4 KB
look like HTML (a .pdf holding HTML is a failed download: not_a_pdf). Script,
style, noscript, template and svg are dropped, tags removed, entities
unescaped; the <title>, citation_title, dc.title and og:title lines followed
by the first 20000 characters of visible text are page 1, and A / B apply.
An error, proxy or access page ("Host Needed", "Access denied", a block or
robot check, "does not subscribe" and the like, in the titles or the first
2000 characters) where A fails, or a page without any text -> not_the_article.

Single mode (--item item.json --pdf FILE): the same verdict for one file,
printed as one JSON object {code, evidence, md5, ...}.

Stream mode (record paths, or records on stdin as JSONL / a JSON array / one
object). The file: the record's `file` (relative to the record's directory;
stdin records: the working directory), else --pdf, else the first of
<stem>.pdf, <stem>.accepted.pdf, <stem>.preprint.pdf, <stem>.supplement.pdf,
<stem>.html next to the record (stem = the record file's name without
.json); none -> no_file. Each record gains `pdf = {code, evidence, md5,
checked_at}` (md5 of the checked file). Without -i the updated records go to
stdout one per line, and one summary line per record plus the final
{"summary": ...} go to stderr; with -i each record is written back to its
file and stdout carries those summary lines instead. Exit 0 = every record
passed, 1 = some record did not (its code and evidence say why).

--match FILE (records as in stream mode): judge one file against each record,
FILE standing in for each record's file; never writes records. stdout: one
line per record {slug, code, ...}, then {"matched": [slug...], "file", "md5",
"file_version"}. Exit 0 = at least one record matched, 1 = none did, 2 =
cannot check (FILE missing, records unreadable or none, no pdftotext).
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

EXCERPT_CHARS = 600
MIN_TITLE_CHARS = 10
MAX_PAGES = 3
COVER_MAX_CHARS = 2500  # a cover sheet is short; a paper's first page is not
LONG_FILE_PAGES = 80    # over this, a title after page 1 suggests a whole booklet
HEAD_CHARS = 500        # the head of page 1 never reaches further
WORD_SHARE = 0.8        # path B
BYLINE_CHARS = 1500     # path B: the first author counts here, before an introduction's citations
TOOL_TIMEOUT = 60       # seconds, for pdftotext / pdfinfo
HTML_SCAN_CHARS = 20_000
DENIAL_SCAN_CHARS = 2000
PASS_CODES = ("ok", "ok_on_page_2", "ok_on_page_3", "ok_by_words")
VERSIONS = ("published", "accepted", "preprint", "supplement", "snapshot")
NAME_VERSIONS = ((".accepted.pdf", "accepted"), (".preprint.pdf", "preprint"), (".supplement.pdf", "supplement"),
                 (".html", "snapshot"), (".htm", "snapshot"))
STEM_FILES = (".pdf", ".accepted.pdf", ".preprint.pdf", ".supplement.pdf", ".html")

ENCRYPT_RE = re.compile(rb"/Encrypt\s*(?:\d+\s+\d+\s+R|<<)")
SUPPLEMENT_RE = re.compile(r"supplement(?:ary|al)|appendix", re.I)
# Phrases typical of the sheet a repository, publisher or institution puts in front of a paper.
COVER_RE = re.compile(r"downloaded from|repository|this is a|author manuscript|accepted|citation:", re.I)
# arXiv's margin stamp: "arXiv:2303.11366v4 [cs.AI] 10 Oct 2023", old style "arXiv:hep-th/9901001v1 [hep-th] ...".
ARXIV_STAMP_RE = re.compile(r"arXiv:\s?(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?\s*\[[^\]\n]{2,24}\]")

# Head markers (matched on folded text, line by line). A heading, not a mention: line start, then a colon or the
# line's end, or a space and a dash or a linking word ("Correction-based" and "Supplemental content" are no
# headings). Both lists are living: extend them when a real file shows a new form.
HEADING_TAIL = r"(?=[ \t]*(?:$|:)|[ \t]+(?:[\-–—]|(?:to|for|note|notice|regarding)\b))"
ERRATUM_HEAD = re.compile(r"^[ \t]*((?:(?:author|authors'?|publisher'?s?|editorial)[ \t]+)?"
                          r"(?:corrections?|corrigend(?:um|a)|errat(?:um|a)|retractions?)(?:[ \t]+(?:note|notice))?)"
                          + HEADING_TAIL, re.M)
ERRATUM_WORDS = re.compile(r"\b(?:corrections?|corrigend(?:um|a)|errat(?:um|a)|retractions?)\b")
SUPPLEMENT_HEAD = re.compile(r"^[ \t]*((?:online[ \t]+|electronic[ \t]+)?supplement(?:ary|al)[ \t]+"
                             r"(?:materials?|information|info|appendix|appendices|data|methods|online[ \t]+content))"
                             + HEADING_TAIL, re.M)
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")
DOI_TRAIL = ".,;:)]}>'\"”’"
# Pages that are not an article: proxy errors, access refusals, block and robot checks. Living list.
DENIAL_RE = re.compile(r"host needed|access denied|access to this page has been denied|403 forbidden|access forbidden"
                       r"|404 not found|page not found|you have been blocked|just a moment|attention required"
                       r"|verify you are (?:a )?human|are you a robot|request rejected|does not subscribe"
                       r"|you do not have access|institutional login")
HTML_SNIFF = re.compile(rb"<(?:!doctype\s+html|html|head|body|title|meta)\b", re.I)
HTML_SKIP = {"script", "style", "noscript", "template", "svg"}
HTML_BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table", "section", "article", "header",
              "footer", "nav", "main", "aside", "h1", "h2", "h3", "h4", "h5", "h6", "title", "dd", "dt", "figcaption"}
HTML_TITLE_META = ("citation_title", "dc.title", "og:title")
HTML_DOI_META = ("citation_doi", "dc.identifier", "prism.doi", "bepress_citation_doi")
B_TRANSLATE = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
                             "’": "'", "‘": "'"})

HINTS = {
    "title_not_found": "compare `excerpt` and `title_words` with the title; if it is the paper after all, read page 1 "
                       "and accept it in the record's pdf_accepted with your reason",
    "no_text_layer": "no extractable text (scanned, or encrypted beyond pdftotext); read the first page with the pdf "
                     "skill or by eye",
    "not_a_pdf": "not a PDF (an HTML page saved as .pdf?); fetch the file again",
    "cannot_judge": "title too short for the rule; judge from `excerpt`",
    "file_not_found": "check the path",
    "erratum_suspected": "page 1 opens with a correction / erratum / retraction notice (`erratum_marker`): the file "
                         "is the notice, not the paper; get the article itself, and check the record's DOI is not "
                         "the notice's",
    "supplement_suspected": "page 1 opens as supplementary material (`supplement_marker`): get the main article, or "
                            "name the file <slug>.supplement.pdf if the supplement is what is wanted",
    "doi_mismatch": "page 1 prints another DOI (`dois_on_page_1`): another paper or another version; check the "
                    "record's DOI, and name an accepted manuscript or preprint as such (<slug>.accepted.pdf, "
                    "<slug>.preprint.pdf)",
    "not_the_article": "an error, proxy or access page (`denial_marker`), or a page without text, not the article; "
                       "do not attach it",
    "no_extractor": "pdftotext / pdfinfo (poppler-utils, a system package) are required; tell the user and install "
                    "it only with their OK (references/install.md)",
}

EPILOG = """\
codes (single mode `code`, each record's `pdf.code` and summary line, --match lines):
  pass, exactly these:  ok | ok_on_page_2 | ok_on_page_3 (whole title on that page) | ok_by_words (path B)
  fail:  erratum_suspected | supplement_suspected | doi_mismatch | not_the_article (HTML) | title_not_found |
         no_text_layer | not_a_pdf | cannot_judge | no_file | file_not_found
  cannot check (exit 2): no_extractor (no pdftotext on PATH) | item_unreadable
  single / stream exit: 0 = passed (every record), 1 = not
  --match exit: 0 = at least one record matched, 1 = none did, 2 = cannot check; stdout: one line per record, then
         {"matched": [slug...], "file", "md5", "file_version"}

file = `file` (relative to the record) > --pdf > <stem>.pdf | .accepted.pdf | .preprint.pdf | .supplement.pdf | .html
beside the record. Version = --file-version > the file name (a published-named file with arXiv's margin stamp is a
preprint). `alt_titles` (list) and --alt-title (repeatable) are titles that also match.

evidence: page_count, pages_scanned (<= 3), extractor (pdftotext | html), page_chars, title_page (int | null),
matched_title, title_words ({share, found, total, missing} of the best title), doi_found (bool | null: item has no
DOI), first_author_found (bool | null), first_author_in_byline (in the first 1500 characters of page 1),
dois_on_page_1, erratum_marker, supplement_marker (str | null), doi_mismatch (bool | null: not checked), file_version,
arxiv_stamp, cover_page_suspected, collection_suspected, supplementary, encrypted, text_chars, size_bytes,
pdf_version, excerpt (page 1), excerpt_title_page (when the title is on a later page); HTML also html_title,
denial_marker.

examples:
  uv run check_pdf.py -i records/*.json                          # each record's file, `pdf` written back
  uv run check_pdf.py --match ~/Downloads/x.pdf records/*.json   # which record is this file?
  uv run check_pdf.py --item item.json --pdf paper.pdf           # one file, one item
"""


def log(msg):
    print(msg, file=sys.stderr)


def emit(code, exit_code, hint=None, **fields):
    out = {"code": code, **fields}
    if hint and exit_code:
        out["hint"] = hint
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Stop(Exception):
    """Carry a result code out of any depth; main() turns it into JSON + exit."""

    def __init__(self, code, exit_code=1, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit_code, self.hint, self.extra = code, exit_code, hint, extra


def clean(text):
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()


def normalize(text):
    text = re.sub(r"</?[A-Za-z][^<>]*>", " ", text)
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold() if ch.isalnum())


def fold(text):
    """Casefold without diacritics, for matching a surname as a word."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).casefold()


def first_author_surname(item):
    creators = [c for c in (item.get("creators") or []) if isinstance(c, dict)]
    chosen = [c for c in creators if c.get("creatorType") == "author"] or creators
    if not chosen:
        return None
    c = chosen[0]
    name = (c.get("lastName") or "").strip() or (c.get("name") or "").strip().split(" ")[-1]
    return name or None


# ------------------------------------------------------------ poppler

def require_pdftotext():
    if not shutil.which("pdftotext"):
        raise Stop("no_extractor", 2, HINTS["no_extractor"])


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
            raise Stop("no_extractor", 2, HINTS["no_extractor"])
        log(f"pdftotext: {p}")
        return []
    if p.returncode != 0:
        log(f"pdftotext: exit {p.returncode}")
        return []
    pages = p.stdout.decode("utf-8", errors="replace").split("\f")
    if len(pages) > 1 and not pages[-1].strip():
        pages.pop()  # every page ends with a form feed
    pages = [clean(page) for page in pages[:MAX_PAGES]]
    return pages if any(pages) else []


def pdfinfo_count(pdf):
    p = tool("pdfinfo", [str(pdf.absolute())])
    if isinstance(p, str):
        return None
    m = re.search(rb"^Pages:\s+(\d+)", p.stdout, re.M)
    return int(m.group(1)) if m else None


# ------------------------------------------------------------ HTML snapshots

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


def extract_html(ex, data):
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
        log(f"html: {e!r}")
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
    denial = DENIAL_RE.search(fold(titles + "\n" + visible[:DENIAL_SCAN_CHARS]))
    ex.kind, ex.extractor = "html", "html"
    ex.pages = [(titles + "\n" + visible[:HTML_SCAN_CHARS]).strip()]
    ex.text, ex.head_len = visible, len(titles)
    ex.html_title, ex.meta_dois, ex.denial = doc_title or None, dois, denial.group() if denial else None
    log(f"html: title {doc_title[:80]!r}, visible chars: {len(visible)}, meta DOIs: {dois or '-'}")


# ------------------------------------------------------------ extraction

class Extraction:
    """One file, read once: its kind (pdf | html | other), pages 1-3, and the facts every verdict on it shares."""

    def __init__(self, path, data):
        self.path, self.size, self.md5 = path, len(data), hashlib.md5(data).hexdigest()
        self.kind, self.pdf_version, self.encrypted, self.head_bytes = "other", None, False, data[:40].decode("latin-1")
        self.pages, self.count, self.extractor, self.text, self.head_len = [], None, None, "", HEAD_CHARS
        self.html_title = self.meta_dois = self.denial = None

    def prepare(self):
        """Derived forms of the pages, computed once for any number of records."""
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
        m = ARXIV_STAMP_RE.search(page1) if self.kind == "pdf" else None
        self.arxiv_stamp = m.group() if m else None
        return self


def extract(path):
    """Read one file -> Extraction, or None when it does not exist."""
    if not path.is_file():
        return None
    data = path.read_bytes()
    ex = Extraction(path, data)
    m = re.search(rb"%PDF-(\d\.\d)", data[:1024])
    if not m:
        if path.suffix.lower() != ".pdf" and HTML_SNIFF.search(data[:4096]):
            extract_html(ex, data)  # a .pdf holding HTML is a failed download, not a snapshot
        return ex.prepare()
    ex.kind, ex.pdf_version, ex.extractor = "pdf", m.group(1).decode("ascii"), "pdftotext"
    ex.encrypted = ENCRYPT_RE.search(data) is not None
    ex.pages = pdftotext_pages(path)
    ex.text = "\n".join(ex.pages)
    ex.count = pdfinfo_count(path)
    log(f"pdftotext: pages scanned: {len(ex.pages)}, page count: {ex.count}, text chars: {len(ex.text)}")
    return ex.prepare()


def version_of(path, override, ex=None):
    """--file-version > the file name; a published-named PDF with arXiv's margin stamp is a preprint."""
    if override:
        return override
    name = path.name.lower()
    version = next((v for suffix, v in NAME_VERSIONS if name.endswith(suffix)), "published")
    if version == "published" and ex is not None and ex.arxiv_stamp:
        return "preprint"
    return version


# --------------------------------------------------------------- the check

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


def evidence_base(ex, file_version):
    page1 = ex.pages[0] if ex.pages else ""
    ev = {"page_count": ex.count, "pages_scanned": len(ex.pages), "extractor": ex.extractor,
          "page_chars": [len(p) for p in ex.pages], "title_page": None, "matched_title": None, "title_words": None,
          "doi_found": None, "first_author_found": None, "first_author_in_byline": None,
          "dois_on_page_1": ex.page1_dois[:10], "erratum_marker": None, "supplement_marker": None,
          "doi_mismatch": None, "file_version": file_version, "arxiv_stamp": ex.arxiv_stamp,
          "cover_page_suspected": False, "collection_suspected": False,
          "supplementary": SUPPLEMENT_RE.search(page1[:EXCERPT_CHARS]) is not None,
          "encrypted": ex.encrypted, "text_chars": len(ex.text), "size_bytes": ex.size, "pdf_version": ex.pdf_version,
          "excerpt": page1[:EXCERPT_CHARS] if ex.kind != "other" else ex.head_bytes, "excerpt_title_page": None}
    if ex.kind == "html":
        ev.update(html_title=ex.html_title, denial_marker=ex.denial)
    return ev


def judge(ex, title, alt_titles=(), doi=None, surname=None, file_version="published"):
    """The verdict on one extracted file for one item -> (code, evidence)."""
    ev = evidence_base(ex, file_version)
    if ex.kind == "other":
        return "not_a_pdf", ev
    if ex.kind == "pdf" and not ex.text:
        return "no_text_layer", ev
    if ex.kind == "html" and not ex.pages[0]:
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
    m = None if ERRATUM_WORDS.search(title_fold) else ERRATUM_HEAD.search(head)
    erratum = m.group(1) if m else None
    m = None if file_version == "supplement" or "supplement" in title_fold else SUPPLEMENT_HEAD.search(head)
    supplement = m.group(1) if m else None
    mismatch = None
    if file_version == "published" and rdoi:
        printed = ex.page1_dois
        mismatch = bool(printed) and not any(rdoi in d or d in rdoi for d in printed) and doi_found is False

    ev.update(title_page=title_page, title_words=words, doi_found=doi_found, first_author_found=author_found,
              first_author_in_byline=in_byline, erratum_marker=erratum, supplement_marker=supplement,
              doi_mismatch=mismatch, cover_page_suspected=title_page in (2, 3) and len(page1) < COVER_MAX_CHARS
              and COVER_RE.search(page1) is not None,
              collection_suspected=title_page is not None and (
                  title_page >= 3 or (ex.count is not None and ex.count > LONG_FILE_PAGES and title_page > 1)),
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
    elif ex.kind == "html" and ex.denial:
        code = "not_the_article"
    elif b_pass:
        code = "ok_by_words"
    else:
        code = "title_not_found"
    ev["matched_title"] = matched if title_page else b_title if code == "ok_by_words" else None
    return code, ev


# ---- records ----------------------------------------------------------------

def slug_of(path, record):
    slug = record.get("slug")
    if isinstance(slug, str) and slug:
        return slug
    return path.stem if path is not None else None


def parse_stream(raw):
    """Records from stdin text: JSONL, a JSON array or one object (any sequence of JSON values, really)."""
    decoder, records, i, n = json.JSONDecoder(), [], 0, len(raw)
    while True:
        while i < n and raw[i].isspace():
            i += 1
        if i >= n:
            break
        try:
            value, i = decoder.raw_decode(raw, i)
        except ValueError as e:
            raise Stop("input_invalid", 1, "stdin must carry records as JSONL, a JSON array or one JSON object", error=str(e))
        for rec in (value if isinstance(value, list) else [value]):
            if not isinstance(rec, dict):
                raise Stop("input_invalid", 1, "every record is a JSON object", got=type(rec).__name__)
            records.append(rec)
    return records


def load_records(paths):
    """[(path or None, record)] from the record files, else from stdin; none at all -> no_records."""
    if paths:
        entries = []
        for p in paths:
            path = Path(p)
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise Stop("record_invalid", 1, "every record file holds one JSON object; nothing was done",
                           path=str(path), error=str(e))
            if not isinstance(rec, dict):
                raise Stop("record_invalid", 1, "every record file holds one JSON object; nothing was done", path=str(path))
            entries.append((path, rec))
    else:
        entries = [(None, rec) for rec in parse_stream(sys.stdin.read())]
    if not entries:
        raise Stop("no_records", 1, "pass record files, or pipe records (JSONL, a JSON array or one object) to stdin")
    return entries


def save_record(path, record):
    """Write the record back atomically: a temp file in the same directory, then os.replace."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def record_item(rec):
    """(title, DOI, first author's surname, alt titles) of a record."""
    item = rec.get("item") if isinstance(rec.get("item"), dict) else {}
    alts = rec.get("alt_titles")
    alts = [alts] if isinstance(alts, str) else alts if isinstance(alts, list) else []
    doi = item.get("DOI") if isinstance(item.get("DOI"), str) else None
    return (str(item.get("title") or ""), doi, first_author_surname(item),
            [a for a in alts if isinstance(a, str) and a.strip()])


def record_file(path, rec, fallback):
    """The file to check: `file` (relative to the record) > --pdf > the first <stem>.* file beside the record."""
    name = rec.get("file")
    if isinstance(name, str) and name.strip():
        f = Path(name.strip()).expanduser()
        return f if f.is_absolute() else (path.parent if path is not None else Path.cwd()) / f
    if fallback:
        return Path(fallback).expanduser()
    if path is not None:
        for suffix in STEM_FILES:
            if (f := path.parent / (path.stem + suffix)).is_file():
                return f
    raise Stop("no_file", 1, "put the file beside the record as <slug>.pdf (or .accepted.pdf, .preprint.pdf, .html), "
               "name it in the record's `file`, or pass --pdf")


EXTRA_FIELD = {"erratum_suspected": "erratum_marker", "supplement_suspected": "supplement_marker",
               "doi_mismatch": "dois_on_page_1", "not_the_article": "denial_marker"}


def summary_fields(code, ev):
    out = {"title_page": ev["title_page"], "page_count": ev["page_count"], "file_version": ev["file_version"],
           "cover_page_suspected": ev["cover_page_suspected"], "collection_suspected": ev["collection_suspected"]}
    if code in ("ok_by_words", "title_not_found") and ev["title_words"]:
        out["title_words"] = ev["title_words"]["share"]
    if code in EXTRA_FIELD:
        out[EXTRA_FIELD[code]] = ev.get(EXTRA_FIELD[code])
    return out


class Outcome:
    """One record's result: status ok | failed, its summary line, and whether the record changed."""

    def __init__(self, path, record):
        self.path, self.record, self.changed = path, record, False
        self.status, self.line = "failed", {"slug": slug_of(path, record), "code": "not_run"}

    def set(self, status, code, /, changed=False, **fields):
        self.status, self.changed = status, changed
        self.line = {"slug": self.line["slug"], "code": code, **fields}

    def fail(self, stop, changed=False):
        self.set("failed", stop.code, changed, **stop.extra, **({"hint": stop.hint} if stop.hint else {}))


def write_results(outcomes, in_place):
    """Print the stream output; return the exit code (0 all ok, 1 any failed)."""
    counts = {"total": len(outcomes), "ok": 0, "failed": 0}
    for o in outcomes:
        if in_place and o.changed and o.path is not None:
            try:
                save_record(o.path, o.record)
            except OSError as e:
                o.set("failed", "write_failed", path=str(o.path), error=str(e),
                      hint="the record file could not be rewritten")
        counts[o.status] += 1
        line = json.dumps(o.line, ensure_ascii=False)
        if in_place:
            print(line)
        else:
            print(json.dumps(o.record, ensure_ascii=False))
            log(line)
    summary = json.dumps({"summary": counts}, ensure_ascii=False)
    print(summary) if in_place else log(summary)
    return 1 if counts["failed"] else 0


def check_record(o, args, cache):
    """Run the check for one record, filling its Outcome and the record's `pdf`."""
    rec = o.record
    pdf = record_file(o.path, rec, args.pdf)
    title, doi, surname, alts = record_item(rec)
    key = str(pdf.absolute())
    if key not in cache:
        cache[key] = extract(pdf)
    ex = cache[key]
    if ex is None:  # file_not_found: nothing to record
        raise Stop("file_not_found", 1, HINTS["file_not_found"], file=str(pdf))
    code, evidence = judge(ex, title, alts + args.alt_title, doi, surname, version_of(pdf, args.file_version, ex))
    rec["pdf"] = {"code": code, "evidence": evidence, "md5": ex.md5, "checked_at": now_iso()}
    fields = {"file": str(pdf), **summary_fields(code, evidence)}
    if code in PASS_CODES:
        o.set("ok", code, changed=True, **fields)
    else:
        o.set("failed", code, changed=True, **fields, hint=HINTS.get(code))


def run_stream(args):
    entries = load_records(args.records)
    outcomes, cache = [], {}
    for path, rec in entries:
        o = Outcome(path, rec)
        outcomes.append(o)
        try:
            check_record(o, args, cache)
        except Stop as stop:
            if stop.exit_code == 2:
                raise
            o.fail(stop)
    sys.exit(write_results(outcomes, args.in_place))


def run_match(args):
    """One file against every record: a line per record, then the slugs it matched. Never writes records."""
    try:
        entries = load_records(args.records)
    except Stop as stop:  # here exit 1 means "matched none"; a run that cannot check is 2
        raise Stop(stop.code, 2, stop.hint, **stop.extra)
    path = Path(args.match).expanduser()
    ex = extract(path)
    if ex is None:
        raise Stop("file_not_found", 2, "the file to match does not exist", file=str(path))
    version = version_of(path, args.file_version, ex)
    matched = []
    for rec_path, rec in entries:
        title, doi, surname, alts = record_item(rec)
        code, evidence = judge(ex, title, alts + args.alt_title, doi, surname, version)
        slug = slug_of(rec_path, rec)
        print(json.dumps({"slug": slug, "code": code, **summary_fields(code, evidence)}, ensure_ascii=False))
        if code in PASS_CODES:
            matched.append(slug)
    print(json.dumps({"matched": matched, "file": str(path), "md5": ex.md5, "file_version": version},
                     ensure_ascii=False))
    sys.exit(0 if matched else 1)


def run_single(args):
    try:
        with open(args.item, encoding="utf-8") as fh:
            item = json.load(fh)
        if not isinstance(item, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as e:
        raise Stop("item_unreadable", 2, "item.json must be a JSON object with a title", item=args.item, error=str(e))
    pdf = Path(args.pdf).expanduser()
    ex = extract(pdf)
    if ex is None:
        raise Stop("file_not_found", 1, HINTS["file_not_found"], file=str(pdf))
    doi = item.get("DOI") if isinstance(item.get("DOI"), str) else None
    code, evidence = judge(ex, str(item.get("title") or ""), args.alt_title, doi, first_author_surname(item),
                           version_of(pdf, args.file_version, ex))
    emit(code, 0 if code in PASS_CODES else 1, HINTS.get(code), file=str(pdf), md5=ex.md5, evidence=evidence)


# ---------------------------------------------------------------------- main

def parse_args():
    ap = argparse.ArgumentParser(
        description="Check that a PDF (or an HTML snapshot) is the item's paper, from its first pages, and report "
                    "evidence about it: a stream of records, one file against several records (--match), or one "
                    "file and one item (--item --pdf). Needs pdftotext and pdfinfo (poppler-utils).",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("records", nargs="*", metavar="RECORD",
                    help="record files (stream mode, --match); none, and no --item: records are read from stdin")
    ap.add_argument("-i", "--in-place", action="store_true",
                    help="stream mode: write each updated record back to its file; stdout gets one summary line per record")
    ap.add_argument("--match", metavar="FILE",
                    help="judge FILE against every record (FILE stands in for each record's file); never writes records")
    ap.add_argument("--item", metavar="FILE", help="single mode: Zotero item JSON; the title is read from here")
    ap.add_argument("--pdf", metavar="FILE",
                    help="single mode: the file to check; stream mode: the file for records without one")
    ap.add_argument("--alt-title", action="append", default=[], metavar="TITLE",
                    help="another title that also matches (repeatable; added to each record's alt_titles)")
    ap.add_argument("--file-version", choices=VERSIONS, metavar="V",
                    help="published | accepted | preprint | supplement | snapshot: overrides the version the file "
                         "name gives")
    args = ap.parse_args()
    if args.item:
        if args.records:
            ap.error("--item (single mode) and record paths (stream mode) exclude each other")
        if args.in_place or args.match:
            ap.error("-i and --match belong to stream mode")
        if not args.pdf:
            ap.error("single mode needs --item and --pdf")
    else:
        if args.match and (args.in_place or args.pdf):
            ap.error("--match never writes records (no -i), and FILE is the file (no --pdf)")
        if not args.records and args.in_place:
            ap.error("-i needs record paths: records from stdin have no file to write back to")
        if not args.records and sys.stdin.isatty():
            ap.error("pass record files, pipe records to stdin, or use --item --pdf for single mode")
    return args


def main():
    args = parse_args()
    require_pdftotext()
    if args.item:
        run_single(args)
    elif args.match:
        run_match(args)
    else:
        run_stream(args)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
