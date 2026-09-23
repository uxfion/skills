# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check that a PDF is the paper an item describes, with evidence from its first pages, for one file or a stream of records.

Facts: %PDF- header and version, size, encryption, how much text the naive
extractor got, the text of the first three pages, and whether the first page
mentions supplementary material. The one rule: the whole title, normalized
(NFKC, casefold, letters and digits only), occurs in a page's normalized
text. The `evidence` object says on which page (title_page), whether the
item's DOI and the first author's surname appear in the scanned pages,
whether page 1 looks like a repository cover sheet in front of the paper
(cover_page_suspected), whether the file looks like a whole proceedings or
booklet rather than one paper (collection_suspected: title on page 3, or a
file over 80 pages with the title after page 1), the page count, and an
excerpt of page 1 and of the title page.

Single mode (--item --pdf; v1, unchanged plus `evidence`): the rule is applied
to the first page; codes ok | title_not_found | no_text_layer | encrypted |
not_pdf | file_not_found (exit 1) | cannot_judge | item_unreadable (exit 2).

Stream mode (record paths, or records on stdin as JSONL / a JSON array / one
object): the file is the record's `file` (relative to the record's directory;
stdin records: the working directory), else --pdf, none -> no_file. Each
record gains `pdf = {code, evidence, checked_at}`; codes ok (title on page 1)
| ok_on_page_2 | ok_on_page_3 (a cover sheet, accept) | title_not_found |
no_text_layer (also an encrypted file; evidence.encrypted) | not_a_pdf |
cannot_judge (title under 10 characters). Without -i the updated records go
to stdout one per line, and one summary line per record plus the final
{"summary": ...} go to stderr; with -i each record is written back to its
file and stdout carries those summary lines instead. Exit 0 = every record
ok / ok_on_page_n, 1 = some record is not (its code and evidence say why).

Pages are resolved through the page tree (trailer /Root -> /Pages -> /Kids,
depth first, including objects packed in object streams). When that fails or
yields no text at all, the first content streams in file order (up to about
4000 characters) stand in for page 1 and nothing else is scanned;
`first_page` (single mode) and `evidence.page_source` say which. File order
is not page order in general (arXiv/pdfTeX files can write page 1 last),
hence the page tree.

Text extraction is deliberately minimal and standard-library only: streams are
found by scanning for `stream ... endstream`, FlateDecode ones are inflated
with zlib (other filters are skipped), and strings are taken from the text
operators Tj, TJ, ' and ". There is no font, CMap or ToUnicode handling, so
fonts with custom encodings (typical of subsetting, and all Identity-H CID
fonts) yield garbage; that is reported as is, via text_chars and the excerpt.
The only concession to fonts: control-range codes that the file's /Differences
arrays (or TeX's OT1/T1 slots) assign to the ligatures ff, fi, fl, ffi, ffl are
expanded, because those are common in arXiv PDFs and would break the title rule.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import unicodedata
import zlib
from datetime import datetime, timezone
from pathlib import Path

FIRST_PAGE_CHARS = 4000
EXCERPT_CHARS = 600
MAX_TEXT_CHARS = 300_000
MIN_TITLE_CHARS = 10
MAX_PAGES = 3
COVER_MAX_CHARS = 2500  # a cover sheet is short; a paper's first page is not
LONG_FILE_PAGES = 80    # over this, a title after page 1 suggests a whole booklet

STREAM_START = re.compile(rb"(?<![A-Za-z])stream(?:\r\n|\n|\r)")
OBJ_RE = re.compile(rb"(?<![0-9])(\d+)\s+(\d+)\s+obj\b")
REF_RE = re.compile(rb"(\d+)\s+\d+\s+R\b")
SKIP_DICT = re.compile(rb"/Subtype\s*/Image|/Type\s*/(?:XRef|ObjStm|Metadata|EmbeddedFile|Font\w*)"
                       rb"|/Length[123]\b|/FunctionType|/ShadingType")
FILTER_RE = re.compile(rb"/Filter\s*(?:\[([^\]]*)\]|/([A-Za-z0-9]+))")
LENGTH_RE = re.compile(rb"/Length\s+(\d+)(?:\s+(\d+)\s+R)?")
ENCRYPT_RE = re.compile(rb"/Encrypt\s*(?:\d+\s+\d+\s+R|<<)")
DIFFERENCES_RE = re.compile(rb"/Differences\s*\[([^\]]*)\]")
NAME_RE = re.compile(rb"/[^\s/\[\]()<>{}%]*")
NUM_RE = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)")
OP_RE = re.compile(rb"[A-Za-z'\"*]+")
INLINE_IMAGE_END = re.compile(rb"\sEI(?=\s|$)")
KIDS_RE = re.compile(rb"/Kids\s*(?:\[([^\]]*)\]|(\d+)\s+\d+\s+R)")
CONTENTS_RE = re.compile(rb"/Contents\s*(?:(\d+)\s+\d+\s+R|\[([^\]]*)\])")
ESCAPES = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
LIGATURE_NAMES = {b"ff", b"fi", b"fl", b"ffi", b"ffl"}
# OT1 (0x0B-0x0F) and T1 (0x1B-0x1F) ligature slots of TeX fonts; /Differences arrays override.
TEX_LIGATURES = {0x0B: "ff", 0x0C: "fi", 0x0D: "fl", 0x0E: "ffi", 0x0F: "ffl",
                 0x1B: "ff", 0x1C: "fi", 0x1D: "fl", 0x1E: "ffi", 0x1F: "ffl"}
SUPPLEMENT_RE = re.compile(r"supplement(?:ary|al)|appendix", re.I)
# Phrases typical of the sheet a repository, publisher or institution puts in front of a paper.
COVER_RE = re.compile(r"downloaded from|repository|this is a|author manuscript|accepted|citation:", re.I)

EPILOG = """\
single mode codes (stdout `code`, exit status):
  ok               0  the whole normalized title occurs in the first-page text
  title_not_found  1  it does not; judge from `excerpt` / `evidence` (garbled text = custom font encoding)
  no_text_layer    1  nothing decodable (scanned, or only unsupported filters)
  encrypted        1  the file declares /Encrypt; text is not extracted
  not_pdf          1  no %PDF- header
  file_not_found   1  --pdf does not exist
  cannot_judge     2  normalized title shorter than 10 characters; judge from `excerpt`
  item_unreadable  2  --item is not a JSON object

stream mode codes (in each record's `pdf.code` and summary line):
  ok | ok_on_page_2 | ok_on_page_3   exit 0      title_not_found | no_text_layer | not_a_pdf |
  cannot_judge | no_file | file_not_found   exit 1

evidence: page_count, pages_scanned (<= 3), page_source (page_tree | file_order), page_chars, title_page
(int | null), doi_found (bool | null: item has no DOI), first_author_found (bool | null), cover_page_suspected,
collection_suspected, supplementary, text_chars, size_bytes, pdf_version, excerpt (page 1), excerpt_title_page
(when the title is on a later page).

examples:
  uv run check_pdf.py --item item.json --pdf paper.pdf
  uv run check_pdf.py -i records/*.json                 # each record's `file`, `pdf` written back
"""


def log(msg):
    print(msg, file=sys.stderr)


def emit(code, exit_code, hint=None, **fields):
    out = {"code": code, **fields}
    if hint and code != "ok":
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


# ------------------------------------------------------------ string decoding

def ligature_table(data):
    """TeX slots, overridden by the file's /Differences arrays where all fonts agree."""
    seen = {}
    for m in DIFFERENCES_RE.finditer(data):
        code = 0
        for tok in re.findall(rb"\d+|/[^\s/\[\]()<>{}%]*", m.group(1)):
            if tok.isdigit():
                code = int(tok)
                continue
            name = tok[1:]
            if name in LIGATURE_NAMES and code < 0x20:
                seen.setdefault(code, set()).add(name.decode("ascii"))
            code += 1
    table = dict(TEX_LIGATURES)
    for code, names in seen.items():
        if len(names) == 1:
            table[code] = next(iter(names))
        else:
            table.pop(code, None)
    return table


def decode(raw, ligatures):
    """Bytes of one PDF string -> text. cp1252 covers WinAnsi; controls are dropped."""
    out = []
    for ch in raw.decode("cp1252", errors="replace"):
        code = ord(ch)
        if code in ligatures:
            out.append(ligatures[code])
        elif ch in "\n\t" or (ch != "�" and unicodedata.category(ch) != "Cc"):
            out.append(ch)
    return "".join(out)


def read_literal(buf, i):
    """Parse a (...) string starting at buf[i]; returns (bytes, index after ')')."""
    out = bytearray()
    depth, i, n = 1, i + 1, len(buf)
    while i < n:
        c = buf[i]
        if c == 0x5C:  # backslash
            i += 1
            if i >= n:
                break
            c = buf[i]
            if c in ESCAPES:
                out.append(ESCAPES[c])
            elif 0x30 <= c <= 0x37:
                j, val = i, 0
                while j < n and j < i + 3 and 0x30 <= buf[j] <= 0x37:
                    val = val * 8 + (buf[j] - 0x30)
                    j += 1
                out.append(val & 0xFF)
                i = j
                continue
            elif c == 0x0D:
                if buf[i + 1:i + 2] == b"\n":
                    i += 1
            elif c != 0x0A:
                out.append(c)
            i += 1
        elif c == 0x28:
            depth += 1
            out.append(c)
            i += 1
        elif c == 0x29:
            depth -= 1
            i += 1
            if depth == 0:
                break
            out.append(c)
        else:
            out.append(c)
            i += 1
    return bytes(out), i


def read_hex(buf, i):
    """Parse a <...> hex string starting at buf[i]."""
    j = buf.find(b">", i + 1)
    if j < 0:
        j = len(buf)
    digits = re.sub(rb"[^0-9A-Fa-f]", b"", buf[i + 1:j])
    if len(digits) % 2:
        digits += b"0"
    return bytes.fromhex(digits.decode("ascii")), j + 1


def skip_dict(buf, i):
    depth, n = 0, len(buf)
    while i < n:
        if buf.startswith(b"<<", i):
            depth += 1
            i += 2
        elif buf.startswith(b">>", i):
            depth -= 1
            i += 2
            if depth == 0:
                break
        else:
            i += 1
    return i


# ---------------------------------------------------------- content streams

def text_from_content(buf, ligatures):
    """Walk one content stream and collect the strings shown by Tj / TJ / ' / \"."""
    out, operands, array = [], [], None
    i, n = 0, len(buf)
    while i < n:
        c = buf[i]
        target = array if array is not None else operands
        if c in b" \t\r\n\x0c\x00":
            i += 1
        elif c == 0x28:
            s, i = read_literal(buf, i)
            target.append(decode(s, ligatures))
        elif c == 0x3C:
            if buf.startswith(b"<<", i):
                i = skip_dict(buf, i)
            else:
                s, i = read_hex(buf, i)
                target.append(decode(s, ligatures))
        elif c == 0x5B:
            array = []
            i += 1
        elif c == 0x5D:
            operands.append(array if array is not None else [])
            array = None
            i += 1
        elif c == 0x2F:
            i = NAME_RE.match(buf, i).end()
        elif c == 0x25:
            j = buf.find(b"\n", i)
            i = n if j < 0 else j + 1
        elif c in b"+-.0123456789":
            m = NUM_RE.match(buf, i)
            if m:
                try:
                    target.append(float(m.group()))
                except ValueError:
                    pass
                i = m.end()
            else:
                i += 1
        elif c in b"{}":
            i += 1
        else:
            m = OP_RE.match(buf, i)
            if not m:
                i += 1
                continue
            op = m.group()
            i = m.end()
            last = operands[-1] if operands else None
            if op == b"Tj":
                if isinstance(last, str):
                    out.append(last)
            elif op in (b"'", b'"'):
                out.append("\n")
                if isinstance(last, str):
                    out.append(last)
            elif op == b"TJ":
                if isinstance(last, list):
                    for el in last:
                        if isinstance(el, str):
                            out.append(el)
                        elif isinstance(el, float) and el < -120:  # word gaps run -150..-350; pair kerns stay smaller
                            out.append(" ")
            elif op in (b"T*", b"ET", b"Tm"):
                out.append("\n")
            elif op in (b"Td", b"TD"):
                out.append("\n" if isinstance(last, float) and last != 0 else " ")
            elif op == b"BI":
                m = INLINE_IMAGE_END.search(buf, i)
                i = n if not m else m.end()
            operands = []
    return "".join(out)


def parse_filters(dict_text):
    m = FILTER_RE.search(dict_text)
    if not m:
        return []
    if m.group(2):
        return [m.group(2)]
    return re.findall(rb"/([A-Za-z0-9]+)", m.group(1))


def read_stream(data, m, stats):
    """Decode the stream whose `stream` keyword is match m -> (dict_text, bytes or None)."""
    start = m.end()
    head = data[max(0, m.start() - 4000):m.start()]
    k = head.rfind(b" obj")
    dict_text = head[k:] if k >= 0 else head
    filters = parse_filters(dict_text)
    if filters and filters != [b"FlateDecode"]:
        stats["unsupported"].update(f.decode("ascii") for f in filters)
        return dict_text, None
    raw = None
    lm = LENGTH_RE.search(dict_text)
    if lm and lm.group(2) is None:
        length = int(lm.group(1))
        if data[start + length:start + length + 12].lstrip().startswith(b"endstream"):
            raw = data[start:start + length]
    if raw is None:
        end = data.find(b"endstream", start)
        if end < 0:
            return dict_text, None
        raw = data[start:end]
        raw = raw[:-2] if raw.endswith(b"\r\n") else raw[:-1] if raw[-1:] in (b"\n", b"\r") else raw
    if filters:
        try:
            raw = zlib.decompressobj().decompress(raw)
        except zlib.error:
            stats["inflate_errors"] += 1
            return dict_text, None
    stats["decoded"] += 1
    return dict_text, raw


def iter_content_streams(data, stats):
    """Decoded bytes of every stream that may be page content, in file order."""
    for m in STREAM_START.finditer(data):
        stats["streams"] += 1
        head = data[max(0, m.start() - 4000):m.start()]
        k = head.rfind(b" obj")
        if SKIP_DICT.search(head[k:] if k >= 0 else head):
            continue
        _, raw = read_stream(data, m, stats)
        if raw is not None:
            yield raw


class Objects:
    """Lazy object lookup: raw `N G obj` bodies, plus objects packed in object streams."""

    def __init__(self, data, stats):
        self.data, self.stats = data, stats
        self.raw = {int(m.group(1)): m.end() for m in OBJ_RE.finditer(data)}  # last definition wins
        self.packed = None

    def get(self, num):
        """Object body up to its `stream` keyword, or None."""
        if num in self.raw:
            start = self.raw[num]
            end = self.data.find(b"endobj", start, start + 200_000)
            body = self.data[start:end if end >= 0 else start + 200_000]
            sm = STREAM_START.search(body)
            return body[:sm.start()] if sm else body
        if self.packed is None:
            self.packed = self._unpack()
        return self.packed.get(num)

    def stream(self, num):
        """Decoded stream of raw object `num` (content streams are never packed)."""
        start = self.raw.get(num)
        if start is None:
            return None
        sm = STREAM_START.search(self.data, start, start + 4000)
        return read_stream(self.data, sm, self.stats)[1] if sm else None

    def _unpack(self):
        packed = {}
        for m in re.finditer(rb"/Type\s*/ObjStm", self.data):
            sm = STREAM_START.search(self.data, m.end(), m.end() + 4000)
            if not sm:
                continue
            dict_text, body = read_stream(self.data, sm, self.stats)
            n, first = re.search(rb"/N\s+(\d+)", dict_text), re.search(rb"/First\s+(\d+)", dict_text)
            if body is None or not n or not first:
                continue
            first = int(first.group(1))
            header = body[:first].split()
            pairs = [(int(header[i]), int(header[i + 1])) for i in range(0, min(len(header) - 1, 2 * int(n.group(1))), 2)]
            for idx, (num, off) in enumerate(pairs):
                end = pairs[idx + 1][1] if idx + 1 < len(pairs) else len(body) - first
                packed[num] = body[first + off:first + end]
        return packed


def refs_in(objects, m, group_ref, group_array):
    """Object numbers of an array given inline (group_array) or as a reference to an array object (group_ref)."""
    if m.group(group_array) is not None:
        return [int(x) for x in REF_RE.findall(m.group(group_array))]
    ref = int(m.group(group_ref))
    target = objects.get(ref) or b""
    return [int(x) for x in REF_RE.findall(target)] if target.lstrip().startswith(b"[") else [ref]


def page_tree_pages(data, stats, ligatures, limit=MAX_PAGES):
    """Text of the first `limit` pages via the page tree, and the root's /Count -> (pages or None, count or None)."""
    roots = re.findall(rb"/Root\s+(\d+)\s+\d+\s+R", data)
    if not roots:
        return None, None
    objects = Objects(data, stats)
    m = re.search(rb"/Pages\s+(\d+)\s+\d+\s+R", objects.get(int(roots[-1])) or b"")
    if not m:
        return None, None
    root = int(m.group(1))
    cm = re.search(rb"/Count\s+(\d+)", objects.get(root) or b"")
    count = int(cm.group(1)) if cm else None
    leaves, stack, seen = [], [root], set()
    while stack and len(leaves) < limit:  # depth first, leftmost first
        num = stack.pop()
        if num in seen:
            continue
        seen.add(num)
        body = objects.get(num)
        if body is None:
            continue
        km = KIDS_RE.search(body)
        if km is None:
            leaves.append(body)
        else:
            stack.extend(reversed(refs_in(objects, km, 2, 1)))
    pages = []
    for body in leaves:
        cm = CONTENTS_RE.search(body)
        nums = refs_in(objects, cm, 1, 2) if cm else []
        streams = [s for s in (objects.stream(n) for n in nums) if s is not None]
        pages.append(clean("".join(text_from_content(s, ligatures) for s in streams)))
    return (pages or None), count


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


# --------------------------------------------------------------- the check

def build_evidence(pages, source, count, title, doi, surname):
    """The §4.1 evidence object from the scanned pages."""
    norm_title = normalize(title)
    title_page = None
    if len(norm_title) >= MIN_TITLE_CHARS:
        for n, page in enumerate(pages, 1):
            if norm_title in normalize(page):
                title_page = n
                break
    scanned = "\n".join(pages)
    doi_found = None if not doi else normalize(doi) in normalize(scanned)
    author_found = None
    if surname:
        pattern = rf"(?<![^\W\d_]){re.escape(fold(surname))}(?![^\W\d_])"  # letter boundaries: 'Liu1' still matches
        author_found = re.search(pattern, fold(scanned)) is not None
    page1 = pages[0] if pages else ""
    return {
        "page_count": count,
        "pages_scanned": len(pages),
        "page_source": source,
        "page_chars": [len(p) for p in pages],
        "title_page": title_page,
        "doi_found": doi_found,
        "first_author_found": author_found,
        "cover_page_suspected": title_page in (2, 3) and len(page1) < COVER_MAX_CHARS and COVER_RE.search(page1) is not None,
        "collection_suspected": title_page is not None and (
            title_page >= 3 or (count is not None and count > LONG_FILE_PAGES and title_page > 1)),
        "supplementary": SUPPLEMENT_RE.search(page1[:EXCERPT_CHARS]) is not None,
        "excerpt": page1[:EXCERPT_CHARS],
        "excerpt_title_page": pages[title_page - 1][:EXCERPT_CHARS] if title_page and title_page > 1 else None,
    }


def empty_evidence(**extra):
    return {"page_count": None, "pages_scanned": 0, "page_source": None, "page_chars": [], "title_page": None,
            "doi_found": None, "first_author_found": None, "cover_page_suspected": False, "collection_suspected": False,
            "supplementary": False, "excerpt": "", "excerpt_title_page": None, **extra}


def check_file(pdf, title, doi=None, surname=None):
    """Inspect one file -> (v1 code, exit code, hint, v1 facts, evidence)."""
    if not pdf.is_file():
        return "file_not_found", 1, "check the path; a fresh download is located with `wait download`", {"pdf": str(pdf)}, None
    data = pdf.read_bytes()
    facts = {"pdf": str(pdf), "size_bytes": len(data)}
    m = re.search(rb"%PDF-(\d\.\d)", data[:1024])
    if not m:
        head = data[:40].decode("latin-1")
        return ("not_pdf", 1, "not a PDF (an HTML page saved as .pdf?); fetch the file again", {**facts, "head": head},
                empty_evidence(size_bytes=len(data), excerpt=head))
    facts["pdf_version"] = m.group(1).decode("ascii")
    if ENCRYPT_RE.search(data):
        return ("encrypted", 1, "the PDF is encrypted; check the first page with the pdf skill or by eye", facts,
                empty_evidence(size_bytes=len(data), pdf_version=facts["pdf_version"], encrypted=True))

    stats = {"streams": 0, "decoded": 0, "inflate_errors": 0, "unsupported": set()}
    ligatures = ligature_table(data)
    parts, total = [], 0
    for content in iter_content_streams(data, stats):
        chunk = text_from_content(content, ligatures)
        if chunk.strip():
            parts.append(chunk)
            total += len(chunk)
        if total > MAX_TEXT_CHARS:
            break
    text = clean("".join(parts))

    first_page, first_text = "file_order", text[:FIRST_PAGE_CHARS]
    try:
        pages, count = page_tree_pages(data, stats, ligatures)
    except Exception as e:  # the page tree is a best effort; file order remains the fallback
        log(f"page tree: {e!r}")
        pages, count = None, None
    if pages and pages[0]:
        first_page, first_text = "page_tree", pages[0]
    if pages and any(pages):
        source = "page_tree"
    else:
        pages, source = [first_text], "file_order"
    log(f"streams: {stats['streams']}, decoded: {stats['decoded']}, inflate errors: {stats['inflate_errors']}, "
        f"unsupported filters: {sorted(stats['unsupported']) or '-'}, text chars: {len(text)}, first page: {first_page}, "
        f"pages scanned: {len(pages)} ({source}), page count: {count}")

    excerpt = first_text[:EXCERPT_CHARS]
    facts.update(text_chars=len(text), first_page=first_page, title=title,
                 supplementary=bool(SUPPLEMENT_RE.search(excerpt)), excerpt=excerpt)
    evidence = build_evidence(pages, source, count, title, doi, surname)
    evidence.update(text_chars=len(text), size_bytes=len(data), pdf_version=facts["pdf_version"])
    if not text and not first_text:
        return ("no_text_layer", 1, "no extractable text (scanned, or unsupported stream filters); read the first page "
                "with the pdf skill or by eye", facts, evidence)

    norm_title = normalize(title)
    if len(norm_title) < MIN_TITLE_CHARS:
        return "cannot_judge", 2, "title too short for the rule; judge from `excerpt`", facts, evidence
    if norm_title in normalize(first_text):
        return "ok", 0, None, facts, evidence
    if norm_title in normalize(text):
        facts["title_in_later_text"] = True
    return ("title_not_found", 1, "compare `excerpt` with the title; garbled text means custom font encodings, "
            "then read the first page with the pdf skill", facts, evidence)


def stream_code(code, evidence):
    """The stream-mode code for a file: page-aware where the v1 rule only looked at page 1."""
    if code == "not_pdf":
        return "not_a_pdf"
    if code == "encrypted":
        return "no_text_layer"
    if code in ("ok", "title_not_found"):
        tp = evidence["title_page"]
        return "ok" if tp == 1 else f"ok_on_page_{tp}" if tp else "title_not_found"
    return code


# ---- records (stream mode) -------------------------------------------------

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


class Outcome:
    """One record's result: status ok | skipped | failed, its summary line, and whether the record changed."""

    def __init__(self, path, record):
        self.path, self.record, self.changed = path, record, False
        self.status, self.line = "failed", {"slug": slug_of(path, record), "code": "not_run"}

    def set(self, status, code, /, changed=False, **fields):
        self.status, self.changed = status, changed
        self.line = {"slug": self.line["slug"], "code": code, **fields}

    def fail(self, stop, changed=False):
        self.set("failed", stop.code, changed, **stop.extra, **({"hint": stop.hint} if stop.hint else {}))


def write_results(outcomes, in_place, stopped=None):
    """Print the stream output; return the exit code (0 all ok/skipped, 1 any failed, the Stop's when stopped early)."""
    counts = {"total": len(outcomes), "ok": 0, "skipped": 0, "failed": 0}
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
    if stopped is not None:
        counts["stopped"] = stopped.code
        log(f"stopped early: {stopped.code}" + (f" - {stopped.hint}" if stopped.hint else ""))
    summary = json.dumps({"summary": counts}, ensure_ascii=False)
    print(summary) if in_place else log(summary)
    if stopped is not None:
        return stopped.exit_code
    return 1 if counts["failed"] else 0


def check_record(o, args):
    """Run the check for one record, filling its Outcome and the record's `pdf`."""
    rec = o.record
    name = rec.get("file")
    if isinstance(name, str) and name.strip():
        pdf = Path(name.strip()).expanduser()
        if not pdf.is_absolute():
            pdf = (o.path.parent if o.path is not None else Path.cwd()) / pdf
    elif args.pdf:
        pdf = Path(args.pdf).expanduser()
    else:
        raise Stop("no_file", 1, "put the file name (relative to the record) in the record's `file`, or pass --pdf")
    item = rec.get("item") if isinstance(rec.get("item"), dict) else {}
    title = str(item.get("title") or "")
    doi = item.get("DOI") if isinstance(item.get("DOI"), str) else None

    code, _, hint, facts, evidence = check_file(pdf, title, doi, first_author_surname(item))
    if evidence is None:  # file_not_found: nothing to record
        raise Stop(code, 1, hint, file=str(pdf))
    code = stream_code(code, evidence)
    rec["pdf"] = {"code": code, "evidence": evidence, "checked_at": now_iso()}
    fields = dict(file=str(pdf), title_page=evidence["title_page"], page_count=evidence["page_count"],
                  cover_page_suspected=evidence["cover_page_suspected"],
                  collection_suspected=evidence["collection_suspected"])
    if code.startswith("ok"):
        o.set("ok", code, changed=True, **fields)
    else:
        o.set("failed", code, changed=True, **fields, hint=hint)


def run_stream(args):
    entries = load_records(args.records)
    outcomes = []
    for path, rec in entries:
        o = Outcome(path, rec)
        outcomes.append(o)
        try:
            check_record(o, args)
        except Stop as stop:
            o.fail(stop)
    sys.exit(write_results(outcomes, args.in_place))


def run_single(args):
    try:
        with open(args.item, encoding="utf-8") as fh:
            item = json.load(fh)
        if not isinstance(item, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as e:
        emit("item_unreadable", 2, "item.json must be a JSON object with a title", item=args.item, error=str(e))
    title = str(item.get("title") or "")
    doi = item.get("DOI") if isinstance(item.get("DOI"), str) else None
    code, exit_code, hint, facts, evidence = check_file(Path(args.pdf), title, doi, first_author_surname(item))
    if evidence is not None:
        facts["evidence"] = evidence
    emit(code, exit_code, hint, **facts)


# ---------------------------------------------------------------------- main

def parse_args():
    ap = argparse.ArgumentParser(
        description="Check that a PDF carries the item's title on its first pages, and report evidence about it: "
                    "one file (--item --pdf) or a stream of records.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("records", nargs="*", metavar="RECORD",
                    help="record files (stream mode); none, and no --item: records are read from stdin")
    ap.add_argument("-i", "--in-place", action="store_true",
                    help="stream mode: write each updated record back to its file; stdout gets one summary line per record")
    ap.add_argument("--item", metavar="FILE", help="single mode: Zotero item JSON; the title is read from here")
    ap.add_argument("--pdf", metavar="FILE",
                    help="single mode: the PDF to inspect; stream mode: fallback for records without `file`")
    args = ap.parse_args()
    if args.item:
        if args.records:
            ap.error("--item (single mode) and record paths (stream mode) exclude each other")
        if args.in_place:
            ap.error("-i belongs to stream mode")
        if not args.pdf:
            ap.error("single mode needs --item and --pdf")
    else:
        if not args.records and args.in_place:
            ap.error("-i needs record paths: records from stdin have no file to write back to")
        if not args.records and sys.stdin.isatty():
            ap.error("pass record files, pipe records to stdin, or use --item --pdf for single mode")
    return args


def main():
    args = parse_args()
    if args.item:
        run_single(args)
    else:
        run_stream(args)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
