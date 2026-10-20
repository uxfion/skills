"""The text-layer checks: a parse is compared with its PDF's text layer, where there is one, and with itself; what does
not hold up becomes a finding for the settling agent.

A finding is {"id": "<code>@<object>", "code", "page", "block", "items", "detail"}, one per code and object: a block
("table_mismatch@p3-39"), a page ("missing_text@p3"), or the whole document ("no_text_layer", without page and
block). "items" is the set of things seen, as stable strings: a finding judged ok stays ok while a later check finds
no item outside the ones judged. "detail" sums it up for a person.

  missing_text        runs of text-layer words absent from the parse; items: each run as the text layer writes it
  missing_numbers     numbers of two or more digits on text-layer lines but not in the parse; items: the numbers
  extra_text          runs of parsed words the text layer lacks: text the model invented; items: each run as parsed
  foreign_script      CJK, kana or Hangul characters the text layer lacks: invented by the model; items: snippets
  table_mismatch      text-layer tokens inside a table's box absent from that table; items: the tokens
  unchecked_table     a table with no text layer in its box (embedded as an image)
  table_empty_column  a headed column empty in every row: values shifted under the wrong headers; items: the headers
  formula_number_gap  equation numbers missing from an otherwise continuous run, on the page of the number before
                      the gap; items: "(4)"
  low_coverage        under 80% of the page's text-layer word trigrams were found
  repetition          a block repeats one fragment, or cycles through the same words (decoding ran away)
  empty_page          a page yielded no text
  no_text_layer       pages that cannot be checked (scans, images); items: the page numbers

Text inside figure and display-formula boxes is not checked; tables are checked on their own; line numbers (a
numbered column at the page edge, as in manuscripts under review) are ignored. Equation numbers are read through the
conventions, so a \\tag*{(n)} an agent writes closes a gap.

Blocks are the document's current state in reading order: id ("p4-19", "p9-n1"), page, label, text, box (page-image
pixels, or None), and merged_into where the block's content moved into another block. Pure Python but pdf_layer,
which needs pypdfium2."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

import conventions

VERSION = 5              # bump when the checks change, so stored parses are checked again

NOISE_LABELS = ["number", "header", "header_image", "footer", "footer_image"]
FIGURE_LABELS = {"image", "chart", "seal", "header_image", "footer_image"}
FORMULA_LABELS = {"display_formula", "formula", "formula_number"}
NOISE_SET = set(NOISE_LABELS) | {"aside_text"}
TEXTLESS_LABELS = FIGURE_LABELS | set(NOISE_LABELS) | {"formula_number"}

GRAM = 3                 # word n-gram size for the text-layer check
MIN_MISSING_RUN = 8      # consecutive missing n-grams that make a missing_text finding
MIN_CHECK_GRAMS = 40     # pages with fewer text-layer n-grams get no low_coverage finding
LOW_COVERAGE = 0.80
FIGURE_MARGIN = 20       # pixels added around figure boxes before their text is left out
MIN_TABLE_TOKENS = 6     # fewer text-layer tokens in a table box: an image table, not checked
TABLE_TOLERANCE = 0.03   # share of a table's text-layer tokens allowed to be absent
MIN_LINE_TOKENS = 5      # text-layer lines shorter than this give no numbers to check
MIN_LAYER_CHARS = 20     # a block over fewer text-layer characters was read from an image: no extra_text check
REPEAT_RE = re.compile(r"(.{10,200}?)\1{4,}", re.S)
MIN_LOOP_GRAMS = 30      # a block with this many word trigrams ...
LOOP_DISTINCT = 0.30     # ... of which under this share are distinct is a loop (normal text: 0.56 and up, 2026-10)
LINE_NUMBER_RUN = 10     # numbers counting up by one, one per line, in a column at the page edge: line numbers
LINE_NUMBER_EDGE = 0.20  # share of the page width on either side where line numbers sit
LINE_NUMBER_ALIGN = 12   # pixels the centres of one column of line numbers may stray
FOREIGN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]")  # CJK, kana, Hangul


# ---------------------------------------------------------------- pure

# Line-end hyphenation inside a word (pdfium marks it U+FFFE); not after a digit, as "2023-\n2023" is a range.
_HYPHEN_BREAK = re.compile(r"\ufffe|(?<=[^\W\d_])[-\u00ad\u2010\u2011\x02]\s*\r?\n\s*")
_MATH = re.compile(r"\$\$.*?\$\$|\$[^$]*\$", re.S)
_HTML_TAG = re.compile(r"<[^>]+>")
_LATEX_CMD = re.compile(r"\\[A-Za-z]+")
_TOKEN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]|[^\W\d_]{2,}|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", re.U)
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_GREEK = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")  # Greek in a text layer is math; the parse spells it as LaTeX
_STYLE_CMD = re.compile(r"\\(?:math[a-z]+|text[a-z]*|operatorname\*?|boldsymbol|bm|hat|widehat|bar|overline"
                        r"|tilde|widetilde|vec|dot|ddot|check|breve)(?![A-Za-z])")
_SYMBOL_CMD = re.compile(r"\\(?:[A-Za-z]+|.)")


def glue_math(text: str) -> str:
    """Inline math spelt the way a text layer prints it: subscripts, superscripts and accents run into their letter
    ("T_p(a_k)" -> "Tp(ak)", "D_{\\mathrm{KL}}" -> "DKL"), while operators and Greek letters part words. LaTeX
    tokens alone never match the text layer's "tp", "ak" or "dkl" (2026-10)."""
    def render(m):
        s = _SYMBOL_CMD.sub("\0", _STYLE_CMD.sub("", m.group(0).strip("$")))
        return " " + re.sub(r"[\s_^{}]", "", s) + " "
    return _MATH.sub(render, text)


def blank(pattern: re.Pattern, text: str) -> str:
    """`text` with each match of `pattern` turned into as many spaces, so that offsets into it still hold."""
    return pattern.sub(lambda m: " " * len(m.group()), text)


def token_matches(text: str, layer: bool = False) -> tuple[str, list[re.Match]]:
    """The text tokens() reads and the matches of its tokens in it. The text is NFKC-normalised, then has line-end
    hyphenation joined (layer=True) or HTML tags and LaTeX commands blanked in place, so that in a parse a match
    also locates its token in the normalised text as written."""
    text = unicodedata.normalize("NFKC", text)
    if layer:
        text = _HYPHEN_BREAK.sub("", text)
    else:
        text = blank(_LATEX_CMD, blank(_HTML_TAG, text))
    return text, [m for m in _TOKEN.finditer(text) if not _GREEK.search(m.group())]


def tokens(text: str, layer: bool = False) -> list[str]:
    """Lowercased word, number and CJK-character tokens, Greek-bearing ones dropped. layer=True joins line-end hyphenation."""
    return [m.group().lower() for m in token_matches(text, layer)[1]]


def quote(text: str, matches: list[re.Match], start: int, end: int) -> str:
    """Tokens start to end - 1 as `text` writes them, from the first one's start to the last one's end, whitespace
    collapsed: a finding's item reads as the source does, for the settling agent to find and restore."""
    return " ".join(text[matches[start].start():matches[end - 1].end()].split())


def ngrams(toks: list[str], n: int = GRAM) -> list[tuple]:
    return [tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)]


def missing_runs(layer_toks: list[str], found: set, n: int = GRAM, min_run: int = MIN_MISSING_RUN):
    """(coverage, [(start, end) token spans]) of the layer's n-grams that are absent from `found`."""
    grams = ngrams(layer_toks, n)
    if not grams:
        return None, []
    miss = [g not in found for g in grams]
    runs, start = [], None
    for i, m in enumerate(miss + [False]):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if i - start >= min_run:
                runs.append((start, i - 1 + n))
            start = None
    return 1 - sum(miss) / len(grams), runs


def repetition(text: str) -> str | None:
    """A phrase looped many times, or a long block that keeps cycling through the same words, such as an author
    line repeated over and over (2026-10: 8,857 characters, 6% of its word trigrams distinct)."""
    if m := REPEAT_RE.search(text):
        return f"repeats {m.group(1)[:80]!r}"
    grams = ngrams(words(tokens(_MATH.sub(" ", text))))
    if len(grams) >= MIN_LOOP_GRAMS and len(set(grams)) < LOOP_DISTINCT * len(grams):
        return f"{len(text)} characters, {len(set(grams))} of {len(grams)} word trigrams distinct"
    return None


def stray_script(text: str, known: set) -> list[str]:
    """Snippets around the CJK, kana or Hangul characters of `text` that are not in `known`, the text layer's
    characters."""
    spans = []
    for m in FOREIGN.finditer(text):
        if m.group() in known:
            continue
        if spans and m.start() - spans[-1][1] <= 20:
            spans[-1][1] = m.end()
        else:
            spans.append([m.start(), m.end()])
    return ["..." + text[max(0, s - 20):e + 20].replace("\n", " ") + "..." for s, e in spans]


def line_number_chars(chars: list[tuple], width: float) -> set[int]:
    """Indices of the characters of line numbers: whole numbers in a column near the left or right page edge,
    one per line, counting up by one, as manuscripts under review carry them (2026-10). Left in, they break
    every line's word trigrams and fill table regions with numbers the parse rightly lacks."""
    words_at, run = [], []
    for i, c in enumerate(chars + [(" ", 0.0, 0.0)]):
        if c[0].strip():
            run.append(i)
        elif run:
            words_at.append(run)
            run = []
    numbers = []
    for idx in words_at:
        text = "".join(chars[i][0] for i in idx)
        x = sum(chars[i][1] for i in idx) / len(idx)
        if text.isascii() and text.isdigit() and len(text) <= 4 \
                and (x < LINE_NUMBER_EDGE * width or x > (1 - LINE_NUMBER_EDGE) * width):
            numbers.append((x, sum(chars[i][2] for i in idx) / len(idx), int(text), idx))
    columns = []
    for n in sorted(numbers, key=lambda n: n[0]):
        if columns and n[0] - columns[-1][-1][0] <= LINE_NUMBER_ALIGN:
            columns[-1].append(n)
        else:
            columns.append([n])
    found = set()
    for column in columns:
        column.sort(key=lambda n: n[1])
        seq = column[:1]
        for prev, cur in zip(column, column[1:] + [None]):
            if cur is not None and cur[2] == prev[2] + 1 and cur[1] > prev[1]:
                seq.append(cur)
                continue
            if len(seq) >= LINE_NUMBER_RUN:
                found.update(i for n in seq for i in n[3])
            seq = [cur]
    return found


def empty_columns(html: str) -> list[str]:
    """Headers whose column is empty in every full-width row: the values slid into the next column over,
    as when a figure grid is read as a table (2026-10)."""
    rows = [_CELL.findall(r) for r in _ROW.findall(html)]
    if len(rows) < 3:
        return []
    head = [_HTML_TAG.sub("", c).strip() for c in rows[0]]
    body = [r for r in rows[1:] if len(r) == len(head)]
    if len(body) < 2:
        return []
    return [h for j, h in enumerate(head) if h and all(not _HTML_TAG.sub("", r[j]).strip() for r in body)]


def add_finding(findings: dict, code: str, page: int | None = None, block: str | None = None,
                items: list | tuple = (), detail: str = "") -> None:
    """Record a finding in `findings` (id -> finding). Its object is the block, else the page, else the document;
    a second finding with the same id adds its items and detail to the first."""
    fid = f"{code}@{block}" if block else f"{code}@p{page}" if page is not None else code
    if fid not in findings:
        findings[fid] = {"id": fid, "code": code}
        if page is not None:
            findings[fid]["page"] = page
        if block:
            findings[fid]["block"] = block
        findings[fid].update(items=[], detail="")
    f = findings[fid]
    f["items"].extend(i for i in dict.fromkeys(items) if i not in f["items"])
    f["detail"] = "; ".join(d for d in (f["detail"], detail) if d)


def formula_number_gaps(blocks: list[dict]) -> list[dict]:
    """formula_number_gap findings: (n) absent while the numbers around it are there, on adjacent pages; one per page
    of the number before a gap. Numbers come from formula_number blocks and from \\tag in formulas alike."""
    seen = sorted({(n, b["page"]) for b in blocks for n in conventions.equation_numbers(b)})
    findings = {}
    for (a, pa), (z, pz) in zip(seen, seen[1:]):
        if z - a > 1 and pz - pa <= 1:
            lost = [f"({n})" for n in range(a + 1, z)]
            add_finding(findings, "formula_number_gap", pa, items=lost,
                        detail=f"{' '.join(lost)} between ({a}) and ({z}), page {pa}-{pz}")
    return list(findings.values())


def numbers(toks: list[str]) -> Counter:
    """Numbers worth checking: two or more digits, or a decimal ("3.04", "16", "2020"); single digits are noise."""
    return Counter(t for t in toks if t[0].isdigit() and len(t) >= 2)


def words(toks: list[str]) -> list[str]:
    """Tokens without the numbers, which superscripts and footnote marks scatter differently on each side."""
    return [t for t in toks if not t[0].isdigit()]


def superscripted(t: str, found: Counter) -> bool:
    """A text layer glues a raised digit to its number: "512" + superscript "2" reads "5122"."""
    return len(t) > 2 and t[-1].isdigit() and t[:-1] in found


def inside(x: float, y: float, box, margin: float = 0) -> bool:
    x1, y1, x2, y2 = box
    return x1 - margin <= x <= x2 + margin and y1 - margin <= y <= y2 + margin


def page_keep(pblocks: list[dict]):
    """keep(x, y) for the page check: text in formulas, figures (with axis labels and legends around them)
    and tables is left out, unless the parse found a text block there. Tables get their own check, as their
    text-layer order (cells, multi-line headers) is not reading order."""
    formulas = [b["box"] for b in pblocks if b["box"] and b["label"] in FORMULA_LABELS]
    figures = [b["box"] for b in pblocks if b["box"] and b["label"] in FIGURE_LABELS]
    tables = [b["box"] for b in pblocks if b["box"] and b["label"] == "table"]
    texts = [b["box"] for b in pblocks if b["box"] and b["label"] not in FORMULA_LABELS | FIGURE_LABELS | {"table"}]

    def keep(x, y):
        if any(inside(x, y, box) for box in formulas):
            return False
        if any(inside(x, y, box) for box in texts):
            return True
        return not (any(inside(x, y, box, FIGURE_MARGIN) for box in figures) or any(inside(x, y, box) for box in tables))
    return keep


def layer_text(chars: list[tuple], keep) -> str:
    """Text of `chars` [(ch, x, y)], blanking each word (a run of visible characters) whose centre fails keep(x, y)."""
    out, word = [], []

    def flush():
        if word:
            x = sum(c[1] for c in word) / len(word)
            y = sum(c[2] for c in word) / len(word)
            out.append("".join(c[0] for c in word) if keep(x, y) else " " * len(word))
            word.clear()
    for c in chars:
        if c[0].strip():
            word.append(c)
        else:
            flush()
            out.append(c[0])
    flush()
    return "".join(out)


def invented(text: str, found: set) -> list[str]:
    """Word runs in a parsed block whose trigrams the text layer (`found`) lacks, as the block writes them, given only
    when the block has such runs with its inline math dropped and with it glued: either spelling alone mismatches the
    text layer's math (2026-10: dropped, "yields where returns"; glued, ORCID marks and matrices)."""
    norm = unicodedata.normalize("NFKC", text)
    plain = [m for m in token_matches(blank(_MATH, norm))[1] if not m.group()[0].isdigit()]
    runs = missing_runs([m.group().lower() for m in plain], found)[1]
    if not runs or not missing_runs(words(tokens(glue_math(text))), found)[1]:
        return []
    return [quote(norm, plain, s, e) for s, e in runs]


def in_order(missing: Counter, toks: list[str]) -> list[str]:
    seen, out = Counter(), []
    for t in toks:
        if seen[t] < missing[t]:
            seen[t] += 1
            out.append(t)
    return out


def check_document(blocks: list[dict], layer: dict[int, list[tuple] | None]
                   ) -> tuple[dict[int, float | None], list[dict]]:
    """Each page's coverage (share of its text-layer trigrams found, None without a text layer) and the findings
    about the text (figures: figcheck.py).

    `blocks` carry id/page/label/text/box (page-image pixels, or None) and merged_into where their content moved;
    `layer` maps each page to its text-layer characters [(ch, x, y)] in the same pixels, or None when the page has
    no text layer.
    """
    by_id = {b["id"]: b for b in blocks}
    layer_grams = {p: set(ngrams(words(tokens(layer_text(c, lambda x, y: True), layer=True)))) if c else set()
                   for p, c in layer.items()}
    streams: dict[int, list[list[str]]] = {}
    for b in blocks:
        s = streams.setdefault(b["page"], [[], [], []])
        s[0].extend(tokens(b["text"]))                  # LaTeX letters kept, as in "x_{s}"
        s[1].extend(tokens(_MATH.sub(" ", b["text"])))  # inline math dropped: text layers garble it
        s[2].extend(tokens(glue_math(b["text"])))       # inline math glued as a text layer prints it
    coverage, findings, no_layer = {}, {}, []
    page_list = sorted(layer)
    for idx, page in enumerate(page_list):
        coverage[page] = None
        pblocks = [b for b in blocks if b["page"] == page]
        has_text = any(b["label"] not in TEXTLESS_LABELS and (b["text"].strip() or "merged_into" in b) for b in pblocks)
        if not has_text and not any(b["label"] in FIGURE_LABELS for b in pblocks):
            add_finding(findings, "empty_page", page, detail="no text parsed")
        chars = layer.get(page)
        if not chars:
            no_layer.append(page)
            continue
        grams, nums = set(), Counter()
        for p in page_list[max(0, idx - 1): idx + 2]:
            for s in streams.get(p, []):
                grams.update(ngrams(s))
            nums += numbers(streams.get(p, [[]])[0])
        text = layer_text(chars, page_keep(pblocks))
        joined, matches = token_matches(text, layer=True)
        toks = [m.group().lower() for m in matches]
        cover, runs = missing_runs(toks, grams)
        if cover is not None:
            coverage[page] = round(cover, 3)
            if runs:
                add_finding(findings, "missing_text", page, items=[quote(joined, matches, s, e) for s, e in runs],
                            detail=f"{len(runs)} run(s) of text-layer words absent from the parse")
            if cover < LOW_COVERAGE and len(toks) - GRAM + 1 >= MIN_CHECK_GRAMS:
                add_finding(findings, "low_coverage", page, detail=f"{cover:.0%} of text-layer trigrams found")
        # Text the parse has and the text layer lacks: an invented continuation, a hallucinated line, characters of a
        # script the source never uses. Only blocks over text-layer text: words read from a raster image (a figure, a
        # scanned insert) have nothing to match.
        near = page_list[max(0, idx - 1): idx + 2]
        window = set().union(*(layer_grams.get(p, set()) for p in near))
        known = {c[0] for p in near for c in (layer.get(p) or [])}
        for b in pblocks:
            if (b["label"] in FIGURE_LABELS or not b["text"].strip() or not b["box"]
                    or sum(1 for ch, x, y in chars if ch.strip() and inside(x, y, b["box"])) < MIN_LAYER_CHARS):
                continue
            if stray := stray_script(b["text"], known):
                add_finding(findings, "foreign_script", page, b["id"], stray,
                            "CJK, kana or Hangul characters the text layer lacks")
            if b["label"] in FORMULA_LABELS | NOISE_SET | {"table"}:
                continue
            if extra := invented(b["text"], window):
                add_finding(findings, "extra_text", page, b["id"], extra,
                            f"{len(extra)} run(s) of parsed words the text layer lacks")
        # Numbers from lines of running text or table rows only: short lines are legends and axis ticks.
        line_nums = Counter()
        for line in text.split("\n"):
            line_toks = tokens(line, layer=True)
            if len(line_toks) >= MIN_LINE_TOKENS:
                line_nums += numbers(line_toks)
        lost = in_order(Counter({t: c for t, c in (line_nums - nums).items() if not superscripted(t, nums)}), toks)
        if lost:
            add_finding(findings, "missing_numbers", page, items=lost,
                        detail=f"{len(lost)} number(s) on text-layer lines absent from the parse")
        for b in pblocks:
            if b["label"] != "table" or not b["box"]:
                continue
            region = tokens(layer_text(chars, lambda x, y, box=b["box"]: inside(x, y, box)), layer=True)
            if len(region) < MIN_TABLE_TOKENS:
                if "merged_into" not in b:              # a table embedded as an image: nothing to compare
                    add_finding(findings, "unchecked_table", page, b["id"],
                                detail="no text layer in the table's box: embedded as an image")
                continue
            target = by_id.get(b.get("merged_into"), b)
            absent = in_order(Counter(region) - Counter(tokens(target["text"])), region)
            if len(absent) >= 2 and len(absent) / len(region) > TABLE_TOLERANCE:
                add_finding(findings, "table_mismatch", page, b["id"], absent,
                            f"{len(absent)} of {len(region)} text-layer tokens absent")
    for b in blocks:
        if b["label"] == "table" and (empty := empty_columns(b["text"])):
            add_finding(findings, "table_empty_column", b["page"], b["id"], empty,
                        "headed column(s) empty in every row: values shifted under the wrong headers")
    findings.update((f["id"], f) for f in formula_number_gaps(blocks))
    for b in blocks:
        if b["label"] != "table" and (loop := repetition(b["text"])):
            add_finding(findings, "repetition", b["page"], b["id"], detail=loop)
    if no_layer:
        add_finding(findings, "no_text_layer", items=[str(p) for p in no_layer],
                    detail=f"{len(no_layer)} page(s) without a text layer, not checked against one")
    return coverage, list(findings.values())


# ---------------------------------------------------------------- PDF

def layer_chars(pdf, page_no: int, image_size: tuple) -> list[tuple] | None:
    """One PDF page's text-layer characters as (ch, x, y), the centre in page-image pixels, line numbers blanked;
    None without a text layer."""
    page = pdf[page_no - 1]
    tp = page.get_textpage()
    n = tp.count_chars()
    if n == 0:
        return None
    left, _, _, top = page.get_cropbox()
    width_pt, height_pt = page.get_size()
    sx, sy = image_size[0] / width_pt, image_size[1] / height_pt
    chars = []
    for k in range(n):
        ch = tp.get_text_range(k, 1)
        if ch.strip():
            l, b, r, t = tp.get_charbox(k)
            chars.append((ch, ((l + r) / 2 - left) * sx, (top - (b + t) / 2) * sy))
        else:
            chars.append((ch, 0.0, 0.0))
    numbered = line_number_chars(chars, image_size[0])
    chars = [(" ", 0.0, 0.0) if k in numbered else c for k, c in enumerate(chars)]
    return chars if any(c.strip() for c, _, _ in chars) else None


def pdf_layer(pdf_path, sizes: dict[int, tuple]) -> dict[int, list[tuple] | None]:
    """The text layer for check_document: each page of `sizes` ({page: (width, height)} of its image) mapped to its
    characters (layer_chars), or None."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(pdf_path))
    return {page: layer_chars(pdf, page, size) for page, size in sizes.items()}
