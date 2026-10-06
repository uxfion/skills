# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Parse papers (PDFs or page images) into full-text Markdown and block JSON with PaddleOCR-VL.

Each INPUT is one document: a PDF, an image, or a directory of page images (natural order).
For each document this writes

  OUTDIR/<stem>/<stem>.md     full text; <!-- page N --> before each page; LaTeX formulas
                              with \\tag*{(n)}; HTML tables (merged across pages); figures as
                              ![](imgs/...) crops next to their captions
  OUTDIR/<stem>/<stem>.json   source, parser, per-page check results, and every block in
                              reading order: page, label, text, bbox (page-image pixels),
                              level (headings), image, merged_into (content moved to that id)
  OUTDIR/<stem>/imgs/         figure crops, p<NN>_ prefixed

checks the result against the PDF text layer, and prints one JSON summary line per document
on stdout (progress goes to stderr). A document whose JSON already records the same source
hash, options and output format is skipped; --force parses it again.

Warnings in the summary and the JSON:
  missing_text        a run of text-layer words absent from the parse (sample in "detail")
  missing_numbers     numbers of two or more digits on text-layer lines but not in the parse
  extra_text          a run of parsed words the text layer lacks: text the model invented
  table_mismatch      text-layer tokens inside a table's box absent from that table
  unchecked_table     a table with no text layer in its box (embedded as an image)
  table_empty_column  a headed column empty in every row: values shifted under the wrong headers
  formula_number_gap  equation numbers missing from an otherwise continuous run
  low_coverage        under 80% of the page's text-layer word trigrams were found
  repetition          a block repeats one fragment many times (VLM decoding ran away)
  empty_page          a page yielded no text
  no_text_layer       pages that cannot be checked (scans, images)
A warning about one block carries "block" (its id) and, for a PDF, "region": the block's box in
PDF points [x, y, w, h], ready for pdftotext -layout -x -y -W -H. The summary's min_coverage is
the lowest page's share of text-layer trigrams found.
Text inside figure and display-formula boxes is not checked; tables are checked on their own.

`uv run` starts this script in a bare environment; it re-executes itself with the Python of
the `paddleocr` uv tool (PADDLEOCR_PYTHON overrides), with CUDA_MODULE_LOADING=EAGER set
before CUDA initialises (lazy loading hung the VL model on WSL2 + RTX 50, 2026-10).

Errors: "error" in a summary line (not_found, unsupported_input, bad_pages, parse_failed);
{"error": "paddleocr_missing"} when the tool environment cannot be found.
Exit 0 = every document parsed or skipped; 1 = some document failed; 2 = nothing could start.

Examples:
  uv run parse.py paper.pdf -o out/
  uv run parse.py a.pdf b.pdf scans/ -o out/ --pages 1-8
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import warnings as pywarnings  # "warnings" names the check results below
from collections import Counter
from datetime import date
from pathlib import Path

FORMAT = 2               # bump when the output changes, so older parses are redone
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
NOISE_LABELS = ["number", "header", "header_image", "footer", "footer_image"]
FIGURE_LABELS = {"image", "chart", "seal", "header_image", "footer_image"}
FORMULA_LABELS = {"display_formula", "formula", "formula_number"}
NOISE_SET = set(NOISE_LABELS) | {"aside_text"}
TEXTLESS_LABELS = FIGURE_LABELS | set(NOISE_LABELS) | {"formula_number"}

GRAM = 3                 # word n-gram size for the text-layer check
MIN_MISSING_RUN = 8      # consecutive missing n-grams that make a missing_text warning
MIN_CHECK_GRAMS = 40     # pages with fewer text-layer n-grams get no low_coverage warning
LOW_COVERAGE = 0.80
MAX_SAMPLES = 5
FIGURE_MARGIN = 20       # pixels added around figure boxes before their text is left out
MIN_TABLE_TOKENS = 6     # fewer text-layer tokens in a table box: an image table, not checked
TABLE_TOLERANCE = 0.03   # share of a table's text-layer tokens allowed to be absent
MIN_LINE_TOKENS = 5      # text-layer lines shorter than this give no numbers to check
MIN_LAYER_CHARS = 20     # a block over fewer text-layer characters was read from an image: no extra_text check
REPEAT_RE = re.compile(r"(.{10,200}?)\1{4,}", re.S)


# ---------------------------------------------------------------- environment

def tool_python() -> str | None:
    """The interpreter of the paddleocr uv tool environment."""
    if os.environ.get("PADDLEOCR_PYTHON"):
        return os.environ["PADDLEOCR_PYTHON"]
    try:
        tool_dir = subprocess.run(["uv", "tool", "dir"], capture_output=True, text=True, check=True).stdout.strip()
        for name in ("bin/python", "Scripts/python.exe"):
            candidate = Path(tool_dir) / "paddleocr" / name
            if candidate.exists():
                return str(candidate)
    except (OSError, subprocess.CalledProcessError):
        pass
    entry = shutil.which("paddleocr")
    if entry:
        try:
            first = Path(entry).read_bytes()[:512].split(b"\n", 1)[0].decode()
            if first.startswith("#!"):
                return first[2:].strip()
        except OSError:
            pass
    return None


def ensure_tool_env() -> None:
    """Return inside an interpreter that has paddleocr, or exit with paddleocr_missing."""
    os.environ.setdefault("CUDA_MODULE_LOADING", "EAGER")
    os.environ.setdefault("PYTHONWARNINGS", "ignore")      # Paddle's UserWarnings would bury the progress lines
    pywarnings.filterwarnings("ignore")
    try:
        import paddleocr  # noqa: F401
        return
    except ImportError:
        pass
    python = tool_python()
    if not python or not Path(python).exists() or os.environ.get("_PADDLEOCR_REEXEC"):
        print(json.dumps({"error": "paddleocr_missing",
                          "detail": "no paddleocr uv tool found; see references/install.md"}), flush=True)
        sys.exit(2)
    os.environ["_PADDLEOCR_REEXEC"] = "1"
    os.execv(python, [python, os.path.abspath(__file__), *sys.argv[1:]])


# ---------------------------------------------------------------- inputs

def natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def parse_pages(spec: str | None, count: int) -> list[int]:
    """'1-3,8' -> [1, 2, 3, 8] (1-based, sorted, within 1..count); None -> all pages."""
    if not spec:
        return list(range(1, count + 1))
    pages = set()
    for part in spec.split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)(?:-(\d+)?)?", part)
        if not m:
            raise ValueError(f"bad page range: {part!r}")
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else (count if part.endswith("-") else lo)
        if lo < 1 or hi < lo:
            raise ValueError(f"bad page range: {part!r}")
        pages.update(range(lo, min(hi, count) + 1))
    if not pages:
        raise ValueError(f"no pages of {count} selected by {spec!r}")
    return sorted(pages)


def format_pages(pages: list[int]) -> str:
    """[1, 2, 3, 8] -> '1-3,8'."""
    runs, start = [], pages[0]
    for prev, cur in zip(pages, pages[1:] + [None]):
        if cur != prev + 1:
            runs.append(f"{start}-{prev}" if prev > start else f"{start}")
            start = cur
    return ",".join(runs)


def sha256_of(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def resolve_input(raw: str, pages_spec: str | None) -> dict:
    """Describe one document, or return {"input", "error", "detail"}."""
    path = Path(raw).expanduser()
    if not path.exists():
        return {"input": raw, "error": "not_found"}
    if path.is_dir():
        files = sorted((p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES), key=lambda p: natural_key(p.name))
        if not files:
            return {"input": raw, "error": "unsupported_input", "detail": "directory holds no page images"}
        kind = "images"
    elif path.suffix.lower() == ".pdf":
        files, kind = [path], "pdf"
    elif path.suffix.lower() in IMAGE_SUFFIXES:
        files, kind = [path], "images"
    else:
        return {"input": raw, "error": "unsupported_input", "detail": f"not a PDF or image: {path.suffix}"}
    if kind == "pdf":
        import pypdfium2 as pdfium
        try:
            count = len(pdfium.PdfDocument(str(path)))
        except Exception as e:  # noqa: BLE001 - pdfium raises its own error types
            return {"input": raw, "error": "unsupported_input", "detail": f"unreadable PDF: {e}"}
    else:
        count = len(files)
    try:
        pages = parse_pages(pages_spec, count)
    except ValueError as e:
        return {"input": raw, "error": "bad_pages", "detail": str(e)}
    return {"input": raw, "path": path, "kind": kind, "files": files, "page_count": count, "pages": pages,
            "stem": path.stem if path.is_file() else path.name}


# ---------------------------------------------------------------- check (pure)

# Line-end hyphenation inside a word (pdfium marks it U+FFFE); not after a digit, as "2023-\n2023" is a range.
_HYPHEN_BREAK = re.compile(r"\ufffe|(?<=[^\W\d_])[-\u00ad\u2010\u2011\x02]\s*\r?\n\s*")
_MATH = re.compile(r"\$\$.*?\$\$|\$[^$]*\$", re.S)
_HTML_TAG = re.compile(r"<[^>]+>")
_LATEX_CMD = re.compile(r"\\[A-Za-z]+")
_TOKEN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]|[^\W\d_]{2,}|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", re.U)
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_GREEK = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")  # Greek in a text layer is math; the parse spells it as LaTeX


def tokens(text: str, layer: bool = False) -> list[str]:
    """Lowercased word, number and CJK-character tokens, Greek-bearing ones dropped. layer=True joins line-end hyphenation."""
    text = unicodedata.normalize("NFKC", text)
    if layer:
        text = _HYPHEN_BREAK.sub("", text)
    else:
        text = _LATEX_CMD.sub(" ", _HTML_TAG.sub(" ", text))
    return [t.lower() for t in _TOKEN.findall(text) if not _GREEK.search(t)]


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
    m = REPEAT_RE.search(text)
    return m.group(1)[:80] if m else None


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


def formula_number_gaps(blocks: list[dict]) -> list[dict]:
    """formula_number_gap warnings: (n) absent while the numbers around it are there, on adjacent pages."""
    seen = sorted({(int(m), b["page"]) for b in blocks if b["label"] == "formula_number"
                   for m in re.findall(r"\((\d{1,3})\)", b["text"])})
    out = []
    for (a, pa), (z, pz) in zip(seen, seen[1:]):
        if z - a > 1 and pz - pa <= 1:
            lost = " ".join(f"({n})" for n in range(a + 1, z))
            out.append({"code": "formula_number_gap", "page": pa, "detail": f"{lost} between ({a}) and ({z}), page {pa}-{pz}"})
    return out


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
    formulas = [b["bbox"] for b in pblocks if b["bbox"] and b["label"] in FORMULA_LABELS]
    figures = [b["bbox"] for b in pblocks if b["bbox"] and b["label"] in FIGURE_LABELS]
    tables = [b["bbox"] for b in pblocks if b["bbox"] and b["label"] == "table"]
    texts = [b["bbox"] for b in pblocks if b["bbox"] and b["label"] not in FORMULA_LABELS | FIGURE_LABELS | {"table"}]

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


def in_order(missing: Counter, toks: list[str]) -> list[str]:
    seen, out = Counter(), []
    for t in toks:
        if seen[t] < missing[t]:
            seen[t] += 1
            out.append(t)
    return out


def check_document(blocks: list[dict], layer: dict[int, list[tuple] | None]) -> tuple[list[dict], list[dict]]:
    """Per-page check results and warnings.

    `blocks` carry id/page/label/text/bbox (page-image pixels); `layer` maps each page to its text-layer
    characters [(ch, x, y)] in the same pixels, or None when the page has no text layer.
    """
    by_id = {b["id"]: b for b in blocks}
    layer_grams = {p: set(ngrams(words(tokens(layer_text(c, lambda x, y: True), layer=True)))) if c else set()
                   for p, c in layer.items()}
    streams: dict[int, list[list[str]]] = {}
    for b in blocks:
        s = streams.setdefault(b["page"], [[], []])
        s[0].extend(tokens(b["text"]))                  # LaTeX letters kept, as in "x_{s}"
        s[1].extend(tokens(_MATH.sub(" ", b["text"])))  # inline math dropped: text layers garble it
    pages_info, warnings, no_layer = [], [], []
    page_list = sorted(layer)
    for idx, page in enumerate(page_list):
        info = {"page": page, "coverage": None}
        pblocks = [b for b in blocks if b["page"] == page]
        has_text = any(b["label"] not in TEXTLESS_LABELS and (b["text"].strip() or "merged_into" in b) for b in pblocks)
        if not has_text and not any(b["label"] in FIGURE_LABELS for b in pblocks):
            warnings.append({"code": "empty_page", "page": page})
        chars = layer.get(page)
        if not chars:
            no_layer.append(page)
            pages_info.append(info)
            continue
        grams, nums = set(), Counter()
        for p in page_list[max(0, idx - 1): idx + 2]:
            for s in streams.get(p, []):
                grams.update(ngrams(s))
            nums += numbers(streams.get(p, [[]])[0])
        text = layer_text(chars, page_keep(pblocks))
        toks = tokens(text, layer=True)
        coverage, runs = missing_runs(toks, grams)
        if coverage is not None:
            info["coverage"] = round(coverage, 3)
            for start, end in runs[:MAX_SAMPLES]:
                warnings.append({"code": "missing_text", "page": page, "detail": " ".join(toks[start:end])[:300]})
            if coverage < LOW_COVERAGE and len(toks) - GRAM + 1 >= MIN_CHECK_GRAMS:
                warnings.append({"code": "low_coverage", "page": page, "detail": f"{coverage:.0%} of text-layer trigrams found"})
        # Text the parse has and the text layer lacks: an invented continuation, a hallucinated line. Only blocks
        # over text-layer text: words read from a raster image (a figure, a scanned insert) have nothing to match.
        window = set().union(*(layer_grams.get(p, set()) for p in page_list[max(0, idx - 1): idx + 2]))
        for b in pblocks:
            if (b["label"] in FORMULA_LABELS | FIGURE_LABELS | NOISE_SET | {"table"} or not b["text"].strip() or not b["bbox"]
                    or sum(1 for ch, x, y in chars if ch.strip() and inside(x, y, b["bbox"])) < MIN_LAYER_CHARS):
                continue
            btoks = words(tokens(_MATH.sub(" ", b["text"])))
            for start, end in missing_runs(btoks, window)[1][:MAX_SAMPLES]:
                warnings.append({"code": "extra_text", "page": page, "block": b["id"],
                                 "detail": " ".join(btoks[start:end])[:300]})
        # Numbers from lines of running text or table rows only: short lines are legends and axis ticks.
        line_nums = Counter()
        for line in text.split("\n"):
            line_toks = tokens(line, layer=True)
            if len(line_toks) >= MIN_LINE_TOKENS:
                line_nums += numbers(line_toks)
        lost = in_order(Counter({t: c for t, c in (line_nums - nums).items() if not superscripted(t, nums)}), toks)
        if lost:
            warnings.append({"code": "missing_numbers", "page": page, "detail": " ".join(lost[:20])})
        for b in pblocks:
            if b["label"] != "table" or not b["bbox"]:
                continue
            region = tokens(layer_text(chars, lambda x, y, box=b["bbox"]: inside(x, y, box)), layer=True)
            if len(region) < MIN_TABLE_TOKENS:
                if "merged_into" not in b:              # a table embedded as an image: nothing to compare
                    warnings.append({"code": "unchecked_table", "page": page, "block": b["id"]})
                continue
            target = by_id.get(b.get("merged_into"), b)
            absent = in_order(Counter(region) - Counter(tokens(target["text"])), region)
            if len(absent) >= 2 and len(absent) / len(region) > TABLE_TOLERANCE:
                warnings.append({"code": "table_mismatch", "page": page, "block": b["id"],
                                 "detail": f"{len(absent)} of {len(region)} text-layer tokens absent: " + " ".join(absent[:20])})
        pages_info.append(info)
    for b in blocks:
        if b["label"] == "table" and (empty := empty_columns(b["text"])):
            warnings.append({"code": "table_empty_column", "page": b["page"], "block": b["id"], "detail": ", ".join(empty)})
    warnings.extend(formula_number_gaps(blocks))
    for b in blocks:
        if b["label"] != "table" and (frag := repetition(b["text"])):
            warnings.append({"code": "repetition", "page": b["page"], "detail": f"block {b['id']} repeats {frag!r}"})
    if no_layer:
        warnings.append({"code": "no_text_layer", "pages": no_layer})
    return pages_info, warnings


# ---------------------------------------------------------------- check (PDF)

def layer_chars(pdf, page_no: int, image_size: tuple) -> list[tuple] | None:
    """One PDF page's text-layer characters as (ch, x, y), the centre in page-image pixels; None without a text layer."""
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
    return chars if any(c.strip() for c, _, _ in chars) else None


# ---------------------------------------------------------------- parse

def options_of(args) -> dict:
    return {"pages": args.pages, "keep_all": args.keep_all, "charts": args.charts,
            "figure_text": args.figure_text, "photo": args.photo}


def up_to_date(json_path: Path, sha: str, options: dict) -> bool:
    try:
        old = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    parser = old.get("parser", {})
    return (old.get("source", {}).get("sha256") == sha and parser.get("options") == options
            and parser.get("format") == FORMAT)


def make_pipeline(args):
    from paddleocr import PaddleOCRVL
    return PaddleOCRVL(use_doc_orientation_classify=args.photo, use_doc_unwarping=args.photo)


def predict_input(doc: dict, workdir: Path):
    """What to hand to predict_iter: the PDF itself, a sub-PDF of the selected pages, or image paths."""
    if doc["kind"] == "images":
        return [str(doc["files"][p - 1]) for p in doc["pages"]]
    if len(doc["pages"]) == doc["page_count"]:
        return str(doc["path"])
    import pypdfium2 as pdfium
    src = pdfium.PdfDocument(str(doc["path"]))
    sub = pdfium.PdfDocument.new()
    sub.import_pages(src, [p - 1 for p in doc["pages"]])
    out = workdir / "selected.pdf"
    sub.save(str(out))
    return str(out)


def block_record(block, page: int, offset: int, local: int, image: str | None) -> dict:
    # Global ids run over the pages in PaddleOCR's own block order; group_id indexes that order within a page.
    gid = getattr(block, "global_block_id", None)
    gid = offset + local if gid is None else gid
    target = getattr(block, "global_group_id", None)
    if target is None or target == gid:
        group = getattr(block, "group_id", None)
        target = offset + group if group is not None else None
    bbox = [int(round(float(v))) for v in list(block.bbox)[:4]] if block.bbox is not None else None
    rec = {"id": gid, "page": page, "label": block.label, "text": block.content or "", "bbox": bbox}
    if getattr(block, "title_level", None) is not None:
        rec["level"] = block.title_level
    if image:
        rec["image"] = image
    if target is not None and target != gid:
        rec["merged_into"] = target
    return rec


def attach_formula_numbers(blocks: list) -> tuple[list, list]:
    """Put each formula number right after the formula on its line, and a lead-in line that sits above a
    formula back before it. PaddleOCR merges a number into \\tag only when it directly follows its formula
    and drops it otherwise; its reading order sometimes slips a text block between them (2026-10).

    Returns (for_markdown, for_json): one order, but a formula with several numbers gets them as one
    "(22), (23)" block in the Markdown copy, while the JSON keeps every block as parsed."""
    def box(b):
        return [float(v) for v in list(b.bbox)[:4]] if b.bbox is not None else None

    formulas = [b for b in blocks if b.label in ("display_formula", "formula") and box(b)]
    owner = {}
    for n in blocks:
        if n.label != "formula_number" or not box(n):
            continue
        x1, y1, x2, y2 = box(n)
        cy = (y1 + y2) / 2
        row = [f for f in formulas if box(f)[1] <= cy <= box(f)[3] and box(f)[2] <= x1 + 10]
        if row:
            owner[id(n)] = min(row, key=lambda f: x1 - box(f)[2])
    order = [b for b in blocks if id(b) not in owner]
    numbers = {}
    for n in sorted((n for n in blocks if id(n) in owner), key=lambda n: box(n)[1]):
        numbers.setdefault(id(owner[id(n)]), []).append(n)
    for_json = []
    for b in order:
        for_json.append(b)
        for_json.extend(numbers.get(id(b), []))
    # A text block that follows a formula (and its numbers) but lies wholly above it, in the same column, leads in.
    i = 0
    while i < len(for_json):
        f = for_json[i]
        if f.label in ("display_formula", "formula") and box(f):
            j = i + 1 + len(numbers.get(id(f), []))
            if j < len(for_json) and for_json[j].label == "text" and box(for_json[j]):
                tx1, _, tx2, ty2 = box(for_json[j])
                fx1, fy1, fx2, _ = box(f)
                overlap = min(tx2, fx2) - max(tx1, fx1)
                if ty2 <= fy1 and overlap > 0.5 * min(tx2 - tx1, fx2 - fx1):
                    for_json.insert(i, for_json.pop(j))
                    i += 1
        i += 1
    for_markdown = []
    for b in for_json:
        if b.label == "formula_number" and id(b) in owner:
            group = numbers[id(owner[id(b)])]
            if b is not group[0]:
                continue
            if len(group) > 1:
                b = copy.copy(b)
                b.content = ", ".join(n.content.strip() for n in group)
        for_markdown.append(b)
    return for_markdown, for_json


def write_page(res, page: int, width: int, outdir: Path, tmp: Path) -> tuple[str, dict]:
    """Markdown of one restructured page (footnotes last, formula numbers attached), its figure crops moved into
    outdir/imgs; leaves the page's blocks in the same order for the JSON; returns (markdown, renames)."""
    page_tmp = tmp / f"p{page}"
    blocks = res["parsing_res_list"]
    blocks = [b for b in blocks if b.label != "footnote"] + [b for b in blocks if b.label == "footnote"]
    for_markdown, res_json = attach_formula_numbers(blocks)
    res["parsing_res_list"] = for_markdown
    res.save_to_markdown(str(page_tmp), pretty=False, show_formula_number=True)
    res["parsing_res_list"] = res_json
    md_files = list(page_tmp.glob("*.md"))
    text = md_files[0].read_text(encoding="utf-8") if md_files else ""
    renames = {}
    for img in sorted((page_tmp / "imgs").glob("*")) if (page_tmp / "imgs").exists() else []:
        new = f"p{page:0{width}d}_{img.name}"
        (outdir / "imgs").mkdir(exist_ok=True)
        shutil.move(str(img), str(outdir / "imgs" / new))
        renames[f"imgs/{img.name}"] = f"imgs/{new}"
    for old, new in renames.items():
        text = text.replace(old, new)
    return re.sub(r"\n{3,}", "\n\n", text).strip(), renames


def process(doc: dict, args, state: dict) -> dict:
    outdir = Path(args.output) / doc["stem"]
    md_path, json_path = outdir / f"{doc['stem']}.md", outdir / f"{doc['stem']}.json"
    sha = sha256_of(doc["files"] if doc["kind"] == "images" else [doc["path"]])
    options = options_of(args)
    summary = {"input": doc["input"], "md": str(md_path), "json": str(json_path)}
    if not args.force and up_to_date(json_path, sha, options):
        old = json.loads(json_path.read_text(encoding="utf-8"))
        summary.update(skipped="up_to_date", pages=len(old["pages"]), warnings=old.get("warnings", []))
        return summary

    if state.get("pipeline") is None:
        t0 = time.time()
        print("[paddleocr] loading models ...", file=sys.stderr, flush=True)
        state["pipeline"] = make_pipeline(args)
        state["load_seconds"] = round(time.time() - t0, 1)
    pipeline = state["pipeline"]

    t0 = time.time()
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="paddleocr-") as tmpname:
        tmp = Path(tmpname)
        results = []
        for res in pipeline.predict_iter(
            predict_input(doc, tmp),
            use_chart_recognition=args.charts,
            use_ocr_for_image_block=args.figure_text,
            markdown_ignore_labels=[] if args.keep_all else NOISE_LABELS,
        ):
            results.append(res)
            print(f"[paddleocr] {doc['stem']}: page {doc['pages'][len(results) - 1]} done "
                  f"({len(results)}/{len(doc['pages'])}, {time.time() - t0:.0f} s since this document started)",
                  file=sys.stderr, flush=True)
        sizes = [(int(r["width"]), int(r["height"])) for r in results]
        pages = pipeline.restructure_pages(results, merge_tables=True, relevel_titles=True, concatenate_pages=False)

        width = max(2, len(str(doc["pages"][-1])))
        parts, blocks, offset = [], [], 0
        for res, page in zip(pages, doc["pages"]):
            text, renames = write_page(res, page, width, outdir, tmp)
            parts.append(f"<!-- page {page} -->\n\n{text}" if text else f"<!-- page {page} -->")
            for local, block in enumerate(res["parsing_res_list"]):
                path = block.image["path"] if getattr(block, "image", None) else None
                blocks.append(block_record(block, page, offset, local, renames.get(path)))
            offset += len(res["parsing_res_list"])

    layer = {}
    if doc["kind"] == "pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(doc["path"]))
        for page, size in zip(doc["pages"], sizes):
            layer[page] = layer_chars(pdf, page, size)
    else:
        layer = {page: None for page in doc["pages"]}
    pages_info, warnings = check_document(blocks, layer)
    for info, (w, h) in zip(pages_info, sizes):
        info.update(width=w, height=h)
    if doc["kind"] == "pdf":
        by_id = {b["id"]: b for b in blocks}
        for w in warnings:
            if "block" in w:                      # the table's box in PDF points, for pdftotext -x -y -W -H
                width_pt, height_pt = pdf[w["page"] - 1].get_size()
                img_w, img_h = sizes[doc["pages"].index(w["page"])]
                x1, y1, x2, y2 = by_id[w["block"]]["bbox"]
                sx, sy = img_w / width_pt, img_h / height_pt
                w["region"] = [int(x1 / sx) - 4, int(y1 / sy) - 4, int((x2 - x1) / sx) + 8, int((y2 - y1) / sy) + 8]

    import paddleocr
    span = f"page{'s' if len(doc['pages']) > 1 else ''} {format_pages(doc['pages'])} of {doc['page_count']}"
    header = f"<!-- source: {doc['path'].name} | {span} | PaddleOCR-VL-1.6 | {date.today()} -->"
    md_path.write_text(header + "\n\n" + "\n\n".join(parts) + "\n", encoding="utf-8")
    record = {
        "source": {"path": str(doc["path"].resolve()), "sha256": sha, "page_count": doc["page_count"], "pages": doc["pages"]},
        "parser": {"pipeline": "PaddleOCR-VL-1.6", "paddleocr": getattr(paddleocr, "__version__", None),
                   "format": FORMAT, "options": options},
        "pages": pages_info,
        "blocks": blocks,
        "warnings": warnings,
    }
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")

    counts = {}
    for b in blocks:
        counts[b["label"]] = counts.get(b["label"], 0) + 1
    covered = [p["coverage"] for p in pages_info if p["coverage"] is not None]
    summary.update(
        pages=len(doc["pages"]),
        blocks=counts,
        min_coverage=round(min(covered), 3) if covered else None,
        warnings=warnings,
        seconds=round(time.time() - t0, 1),
    )
    if "load_seconds" in state:
        summary["load_seconds"] = state.pop("load_seconds")
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inputs", nargs="+", metavar="INPUT", help="PDF, image, or directory of page images")
    p.add_argument("-o", "--output", required=True, metavar="OUTDIR", help="each document goes to OUTDIR/<stem>/")
    p.add_argument("--pages", metavar="RANGES", help="pages to parse, e.g. 1-3,8 or 5- (output keeps original numbers)")
    p.add_argument("--force", action="store_true", help="parse again even when the output is up to date")
    p.add_argument("--keep-all", action="store_true", help="keep running headers, footers and page numbers in the Markdown")
    p.add_argument("--charts", action="store_true", help="turn charts into data tables (values are model-read; check them)")
    p.add_argument("--figure-text", action="store_true", help="OCR the text inside figures into the Markdown")
    p.add_argument("--photo", action="store_true", help="correct orientation and warping (photographed or skewed scans)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ensure_tool_env()
    state, failed = {}, False
    for raw in args.inputs:
        doc = resolve_input(raw, args.pages)
        if "error" not in doc:
            try:
                doc = process(doc, args, state)
            except Exception as e:  # noqa: BLE001 - report and continue with the next document
                doc = {"input": raw, "error": "parse_failed", "detail": f"{type(e).__name__}: {e}"}
        failed |= "error" in doc
        print(json.dumps(doc, ensure_ascii=False), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
