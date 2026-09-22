# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Report facts about a PDF against an item.json draft, and apply one rule.

Facts: %PDF- header and version, size, encryption, how much text the naive
extractor got, an excerpt of the first page, and whether that excerpt mentions
supplementary material. The one rule: the whole title from item.json,
normalized (NFKC, casefold, letters and digits only), occurs in the normalized
first-page text -> ok. Otherwise the agent judges from the excerpt.

"First page" is resolved through the page tree (trailer /Root -> /Pages ->
first /Kids -> /Contents, including objects packed in object streams). When
that fails or yields no text, the first content streams in file order (up to
about 4000 characters) stand in for it; `first_page` in the output says which.
File order is not page order in general (arXiv/pdfTeX files can write page 1
last), hence the page tree.

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
import re
import sys
import unicodedata
import zlib
from pathlib import Path

FIRST_PAGE_CHARS = 4000
EXCERPT_CHARS = 600
MAX_TEXT_CHARS = 300_000
MIN_TITLE_CHARS = 10

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
ESCAPES = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
LIGATURE_NAMES = {b"ff", b"fi", b"fl", b"ffi", b"ffl"}
# OT1 (0x0B-0x0F) and T1 (0x1B-0x1F) ligature slots of TeX fonts; /Differences arrays override.
TEX_LIGATURES = {0x0B: "ff", 0x0C: "fi", 0x0D: "fl", 0x0E: "ffi", 0x0F: "ffl",
                 0x1B: "ff", 0x1C: "fi", 0x1D: "fl", 0x1E: "ffi", 0x1F: "ffl"}
SUPPLEMENT_RE = re.compile(r"supplement(?:ary|al)|appendix", re.I)

EPILOG = """\
codes (stdout `code`, exit status):
  ok               0  the whole normalized title occurs in the first-page text
  title_not_found  1  it does not; judge from `excerpt` (garbled text = custom font encoding)
  no_text_layer    1  nothing decodable (scanned, or only unsupported filters)
  encrypted        1  the file declares /Encrypt; text is not extracted
  not_pdf          1  no %PDF- header
  file_not_found   1  --pdf does not exist
  cannot_judge     2  normalized title shorter than 10 characters; judge from `excerpt`
  item_unreadable  2  --item is not a JSON object

always reported once the file was read: size_bytes, pdf_version, text_chars,
first_page (page_tree | file_order), supplementary (excerpt mentions
supplementary / supplemental / appendix), excerpt.
"""


def log(msg):
    print(msg, file=sys.stderr)


def emit(code, exit_code, hint=None, **fields):
    out = {"code": code, **fields}
    if hint and code != "ok":
        out["hint"] = hint
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


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


def first_page_streams(data, stats):
    """Decoded content streams of page 1 via the page tree, or None when it cannot be resolved."""
    roots = re.findall(rb"/Root\s+(\d+)\s+\d+\s+R", data)
    if not roots:
        return None
    objects = Objects(data, stats)
    m = re.search(rb"/Pages\s+(\d+)\s+\d+\s+R", objects.get(int(roots[-1])) or b"")
    if not m:
        return None
    node = int(m.group(1))
    for _ in range(64):  # walk down the leftmost branch
        body = objects.get(node)
        if body is None:
            return None
        if b"/Kids" not in body:
            break
        kids = re.search(rb"/Kids\s*\[\s*(\d+)\s+\d+\s+R", body) or re.search(rb"/Kids\s+(\d+)\s+\d+\s+R", body)
        if not kids:
            return None
        node = int(kids.group(1))
    else:
        return None
    m = re.search(rb"/Contents\s*(?:(\d+)\s+\d+\s+R|\[([^\]]*)\])", body)
    if not m:
        return None
    if m.group(2) is not None:
        nums = [int(x) for x in REF_RE.findall(m.group(2))]
    else:
        ref = int(m.group(1))
        target = objects.get(ref) or b""
        nums = [int(x) for x in REF_RE.findall(target)] if target.lstrip().startswith(b"[") else [ref]
    streams = [s for s in (objects.stream(n) for n in nums) if s is not None]
    return streams or None


def clean(text):
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()


def normalize(text):
    text = re.sub(r"</?[A-Za-z][^<>]*>", " ", text)
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold() if ch.isalnum())


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="Report facts about a PDF and check that the item.json title occurs on its first page.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--item", required=True, metavar="FILE", help="Zotero item JSON; the title is read from here")
    ap.add_argument("--pdf", required=True, metavar="FILE", help="the PDF to inspect")
    args = ap.parse_args()

    try:
        with open(args.item, encoding="utf-8") as fh:
            item = json.load(fh)
        if not isinstance(item, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as e:
        emit("item_unreadable", 2, "item.json must be a JSON object with a title", item=args.item, error=str(e))
    title = str(item.get("title") or "")

    pdf = Path(args.pdf)
    if not pdf.is_file():
        emit("file_not_found", 1, "check the path; a fresh download is located with `wait download`", pdf=args.pdf)
    data = pdf.read_bytes()
    facts = {"pdf": args.pdf, "size_bytes": len(data)}
    m = re.search(rb"%PDF-(\d\.\d)", data[:1024])
    if not m:
        emit("not_pdf", 1, "not a PDF (an HTML page saved as .pdf?); fetch the file again", **facts,
             head=data[:40].decode("latin-1"))
    facts["pdf_version"] = m.group(1).decode("ascii")
    if ENCRYPT_RE.search(data):
        emit("encrypted", 1, "the PDF is encrypted; check the first page with the pdf skill or by eye", **facts)

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
        streams = first_page_streams(data, stats)
    except Exception as e:  # the page tree is a best effort; file order remains the fallback
        log(f"page tree: {e!r}")
        streams = None
    if streams:
        page_text = clean("".join(text_from_content(s, ligatures) for s in streams))
        if page_text:
            first_page, first_text = "page_tree", page_text
    log(f"streams: {stats['streams']}, decoded: {stats['decoded']}, inflate errors: {stats['inflate_errors']}, "
        f"unsupported filters: {sorted(stats['unsupported']) or '-'}, text chars: {len(text)}, first page: {first_page}")

    excerpt = first_text[:EXCERPT_CHARS]
    facts.update(text_chars=len(text), first_page=first_page, title=title,
                 supplementary=bool(SUPPLEMENT_RE.search(excerpt)), excerpt=excerpt)
    if not text and not first_text:
        emit("no_text_layer", 1, "no extractable text (scanned, or unsupported stream filters); read the first page "
             "with the pdf skill or by eye", **facts)

    norm_title = normalize(title)
    if len(norm_title) < MIN_TITLE_CHARS:
        emit("cannot_judge", 2, "title too short for the rule; judge from `excerpt`", **facts)
    if norm_title in normalize(first_text):
        emit("ok", 0, **facts)
    extra = {"title_in_later_text": True} if norm_title in normalize(text) else {}
    emit("title_not_found", 1, "compare `excerpt` with the title; garbled text means custom font encodings, "
         "then read the first page with the pdf skill", **facts, **extra)


if __name__ == "__main__":
    main()
