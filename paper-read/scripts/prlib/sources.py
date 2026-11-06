"""Where a paper note points at the paper's figures and tables, read from the note's text: the tokens that become
links to them in the PDF when the note is put into Zotero (pr.py put), those links taken off again (pr.py put, pr.py
take), and the quotations, whose English words are the paper's own (pr.py quotes).

A token is a figure or table written in a form references/note-format.md, *Clickable figures and tables*, lists
(tests/test_sources.py holds TOKEN to that list). Its key is its number normalised as the paddleocr skill's
`ocr.py objects` gives it: fig:9, table:III, fig:S3 (Supplementary), table:ED1 (Extended Data).
Tokens are read in the note's Markdown text, and never in: the front matter, headings, the 读的版本 paragraph, code,
math, HTML blocks and tags, links, URLs, a quotation's English words, the deletion mark (it cites another PDF) and
the 原写"…" of a correction mark (the old text).

A link has one shape, and only that shape is taken off:
  [<token>](zotero://open-pdf/library/items/<PDF key>?annotation=<annotation key>)
also as <a href="…">…</a>, as a block kept as HTML holds it. Any PDF key: an older version's links go too.
"""
import re

# ---- quotations ---------------------------------------------------------------------------------------------------

OPENING = re.compile(r'^\s*>\s*(["“])')
CLOSING = {'"': '"', "“": "”"}
TAIL = re.compile(r"^\s*(?:[（(].*[）)])?\s*$")


def quotation(line):
    """A line `> "<the paper's words>" (<source>) （已核对 …）` -> (start, end, tail), the words being line[start:end]
    (they run to the line's last double quote of their kind); (start, None, None) for a line that opens a quotation
    out of this form, whose words cannot be told apart; None for any other line."""
    m = OPENING.match(line)
    if not m:
        return None
    close = line.rfind(CLOSING[m.group(1)])
    if close <= m.end() or not TAIL.match(line[close + 1:]):
        return m.end(), None, None
    return m.end(), close, line[close + 1:]


# ---- tokens -------------------------------------------------------------------------------------------------------

TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(?:(?P<words>Supplementary|Extended Data) )?(?:(?P<fig>Figs?\.|Figures?) ?|(?P<table>Tables?) )"
    r"(?P<number>[A-Z]?\d+|[IVX]+(?![A-Za-z]))")
PREFIX = {None: "", "Supplementary": "S", "Extended Data": "ED"}


def key_of(m):
    """A token's key: fig:9, table:III, fig:S3."""
    prefix, number = PREFIX[m.group("words")], m.group("number").upper()
    return f"{'fig' if m.group('fig') else 'table'}:{number if number.startswith(prefix) else prefix + number}"


def label(key):
    """A key as a reader writes it: fig:9 -> Fig. 9, table:ED1 -> Extended Data Table 1, fig:S3 -> Fig. S3."""
    kind, number = key.split(":", 1)
    word = "Fig." if kind == "fig" else "Table"
    return f"Extended Data {word} {number[2:]}" if number.startswith("ED") else f"{word} {number}"


HTML_BLOCK = re.compile(  # CommonMark's HTML blocks: a block-level tag opens one wherever it is, any other tag only
    r"^ {0,3}(?:<!--|<[?!]|</?(?:address|article|aside|blockquote|body|caption|center|col|colgroup|dd|details|"
    r"dialog|div|dl|dt|fieldset|figcaption|figure|footer|form|h[1-6]|header|hr|html|iframe|legend|li|main|menu|nav|"
    r"ol|optgroup|option|p|pre|script|section|style|summary|table|tbody|td|textarea|tfoot|th|thead|title|tr|ul)"
    r"(?:[\s/>]|$)|(?:<[A-Za-z][\w-]*(?:\s[^<>]*)?/?>|</[A-Za-z][\w-]*\s*>)\s*$)", re.I)  # alone on its line
HEADING = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
KEPT = re.compile(  # spans inside a line that hold no token
    r"(`+)[\s\S]*?(?<!`)\1(?!`)"                        # code
    r"|\$\$[^$]*\$\$|\$[^$\n]+\$"                       # math
    r"|!?\[[^\]\n]*\]\([^)\n]*\)"                       # links and images
    r"|<a\b[^>]*>.*?</a>|<!--.*?-->|</?[A-Za-z][^<>\n]*>"   # HTML links, comments, tags
    r"|https?://\S+"                                     # addresses
    r"|（[^（）\n]*删去了这段，原见[^（）\n]*）"           # the deletion mark: a source in another PDF
    r"|原写[\"“].*?[\"”](?=，按)|原写[\"“][^\"”\n]*[\"”]")  # a correction mark's old text


def text_lines(note):
    """(line number from 1, line) of each line whose text may hold tokens: none of the front matter, a heading, the
    读的版本 paragraph, a code block, a math block or an HTML block."""
    lines, start = note.split("\n"), 0
    if lines and lines[0] == "---":
        start = next((i for i in range(1, len(lines)) if lines[i] == "---"), len(lines) - 1) + 1
    fence = math = None
    skip = False   # inside an HTML block or the 读的版本 paragraph, both running to a blank line
    blank = True   # the line before was blank: a block starts here
    for i in range(start, len(lines)):
        line, s = lines[i], lines[i].strip()
        if fence:
            fence = None if s.startswith(fence) and not s.strip(fence[0]) else fence
        elif math:
            math = None if s.endswith("$$") else math
        elif skip:
            skip = bool(s)
        elif m := FENCE.match(line):
            fence = m.group(1)
        elif s.startswith("$$"):
            math = None if len(s) > 2 and s.endswith("$$") else s
        elif HEADING.match(line):
            pass
        elif blank and (HTML_BLOCK.match(line) or s.startswith("读的版本：")):
            skip = True
        elif s:
            yield i + 1, line
        blank = not s


def tokens(note):
    """[(line number, start, end, token text, re.Match)] for each token in the note's text."""
    out = []
    for n, line in text_lines(note):
        kept = [m.span() for m in KEPT.finditer(line)]
        q = quotation(line)
        if q:
            kept.append((q[0], q[1] if q[1] is not None else len(line)))
        for m in TOKEN.finditer(line):
            if not any(a < m.end() and m.start() < b for a, b in kept):
                out.append((n, m.start(), m.end(), m.group(), m))
    return out


# ---- links --------------------------------------------------------------------------------------------------------

URL = r"zotero://open-pdf/library/items/[A-Z0-9]{8}\?annotation=[A-Z0-9]{8}"
LINK = re.compile(r"\[(?P<text>[^\[\]\n]+)\]\(" + URL + r"\)|<a\s[^>]*?href=\"" + URL + r"\"[^>]*>(?P<atext>[^<\n]+)</a>")


def link(pdf_key, token, annotation):
    return f"[{token}](zotero://open-pdf/library/items/{pdf_key}?annotation={annotation})"


def strip(note):
    """The note with every link of that shape back to its token's text; every other link as it is."""
    def back(m):
        text = m.group("text") or m.group("atext")
        return text if TOKEN.fullmatch(text) else m.group()
    return LINK.sub(back, note)
