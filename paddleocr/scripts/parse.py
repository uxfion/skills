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
hash, options and output format is skipped; --force parses it again. A skipped document that
older checks examined is checked again from its JSON ("rechecked": true; the Markdown is kept).

The VL layout model boxes a multi-panel figure panel by panel; such figures are put back
together. Each becomes a "figure" block whose crop takes its first panel's image line in the
Markdown; its panels keep their own crops, and they and its panel letters get merged_into its
id. A whole-figure box from PP-StructureV3's layout model (PP-DocLayout_plus-L, loaded when a
page first needs it) joins the panels inside it, the caption under them joins the rest; when
that model cannot load, captions alone, and stderr says so. A skipped document parsed before
this grouping existed is grouped from its pages rendered again ("regrouped": true; every other
Markdown line is kept); "regroup" in its summary says why one was not (--photo pages cannot be
rendered again: --force parses anew).

The VL model runs natively (one block at a time, about 10-15 s a page) or in a vLLM server
(continuous batching, 0.5-1 s a page). --backend auto, the default, asks the vllm-serve skill
(installed beside this one, or VLLM_SERVE = its serve.py) for the server whenever a run has
pages to parse, however few: `serve.py up paddleocr-vl` starts it unless it runs, and it stops
by itself once idle. Without vllm-serve, without vLLM, or with too little free GPU memory for
the server, the run goes native and stderr says why. --backend vllm insists on the server,
--backend native avoids it, and --vl-server URL uses a given vLLM server.
Each summary names its "backend" and "pages_per_minute".

Warnings in the summary and the JSON:
  missing_text        a run of text-layer words absent from the parse (sample in "detail")
  missing_numbers     numbers of two or more digits on text-layer lines but not in the parse
  extra_text          a run of parsed words the text layer lacks: text the model invented
  foreign_script      CJK, kana or Hangul characters the text layer lacks: invented by the model
  table_mismatch      text-layer tokens inside a table's box absent from that table
  unchecked_table     a table with no text layer in its box (embedded as an image)
  table_empty_column  a headed column empty in every row: values shifted under the wrong headers
  formula_number_gap  equation numbers missing from an otherwise continuous run
  low_coverage        under 80% of the page's text-layer word trigrams were found
  repetition          a block repeats one fragment, or cycles through the same words (decoding ran away)
  empty_page          a page yielded no text
  uncropped_figure    a figure caption with no figure crop beside it: the figure was read as text or a
                      table, or missed (or no figure is there: a list of figure captions)
  no_text_layer       pages that cannot be checked (scans, images)
A warning about one block carries "block" (its id) and, for a PDF, "region": the block's box in
PDF points [x, y, w, h], ready for pdftotext -layout -x -y -W -H. The summary's min_coverage is
the lowest page's share of text-layer trigrams found.
Text inside figure and display-formula boxes is not checked; tables are checked on their own;
line numbers (a numbered column at the page edge, as in manuscripts under review) are ignored.

`uv run` starts this script in a bare environment; it re-executes itself with the Python of
the `paddleocr` uv tool (PADDLEOCR_PYTHON overrides), with CUDA_MODULE_LOADING=EAGER set
before CUDA initialises (lazy loading hung the VL model on WSL2 + RTX 50, 2026-10) and
LD_LIBRARY_PATH stripped of CUDA toolkit directories when the environment ships its own CUDA
runtime, so that Paddle loads those libraries rather than a system toolkit's.

Errors: "error" in a summary line (not_found, unsupported_input, bad_pages, parse_failed);
alone on stdout when nothing can start: paddleocr_missing (no tool environment), vl_server_failed
(--backend vllm, with vllm-serve's error), vl_server_unreachable (--vl-server).
Exit 0 = every document parsed or skipped; 1 = some document failed; 2 = nothing could start.

Examples:
  uv run parse.py paper.pdf -o out/
  uv run parse.py a.pdf b.pdf scans/ -o out/ --pages 1-8
  uv run parse.py papers/*.pdf -o out/ --vl-server http://127.0.0.1:8118/v1
"""
from __future__ import annotations

import argparse
import copy
import glob
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
import urllib.request
import warnings as pywarnings  # "warnings" names the check results below
from collections import Counter
from datetime import date
from pathlib import Path

FORMAT = 2               # bump when the output changes, so older parses are redone
CHECK = 3                # bump when the checks change, so older parses are checked again (no GPU)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
NOISE_LABELS = ["number", "header", "header_image", "footer", "footer_image"]
FIGURE_LABELS = {"figure", "image", "chart", "seal", "header_image", "footer_image"}
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
MIN_LOOP_GRAMS = 30      # a block with this many word trigrams ...
LOOP_DISTINCT = 0.30     # ... of which under this share are distinct is a loop (normal text: 0.56 and up, 2026-10)
LINE_NUMBER_RUN = 10     # numbers counting up by one, one per line, in a column at the page edge: line numbers
LINE_NUMBER_EDGE = 0.20  # share of the page width on either side where line numbers sit
LINE_NUMBER_ALIGN = 12   # pixels the centres of one column of line numbers may stray
FOREIGN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]")  # CJK, kana, Hangul

VL_PROFILE = "paddleocr-vl"   # the vllm-serve profile that serves the VL model


# ---------------------------------------------------------------- environment

def uv_tool_dir() -> Path | None:
    try:
        return Path(subprocess.run(["uv", "tool", "dir"], capture_output=True, text=True, check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return None


def tool_python() -> str | None:
    """The interpreter of the paddleocr uv tool environment."""
    if os.environ.get("PADDLEOCR_PYTHON"):
        return os.environ["PADDLEOCR_PYTHON"]
    tool_dir = uv_tool_dir()
    for name in ("bin/python", "Scripts/python.exe") if tool_dir else ():
        candidate = tool_dir / "paddleocr" / name
        if candidate.exists():
            return str(candidate)
    entry = shutil.which("paddleocr")
    if entry:
        try:
            first = Path(entry).read_bytes()[:512].split(b"\n", 1)[0].decode()
            if first.startswith("#!"):
                return first[2:].strip()
        except OSError:
            pass
    return None


def without_cuda_toolkit(path: str) -> str | None:
    """LD_LIBRARY_PATH minus the directories holding a CUDA runtime; None when nothing is left.

    A system toolkit ahead of the environment's own nvidia-* wheels made Paddle load its
    libcudart and a second libcublas next to the bundled ones (2026-10: 12.8 beside 12.9).
    """
    kept = [d for d in path.split(":") if not (d and glob.glob(os.path.join(glob.escape(d), "libcudart.so*")))]
    return ":".join(kept) if any(kept) else None


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
    # The loader reads LD_LIBRARY_PATH when a process starts, so this takes effect only across
    # the exec; started directly with the tool's Python, the script keeps the path it was given.
    # An environment without its own CUDA runtime keeps the system toolkit it depends on.
    env = glob.escape(str(Path(python).parent.parent))
    ships_cuda = glob.glob(os.path.join(env, "lib", "python3*", "site-packages", "nvidia", "cuda_runtime", "lib", "libcudart.so*"))
    if ships_cuda and "LD_LIBRARY_PATH" in os.environ:
        path = without_cuda_toolkit(os.environ["LD_LIBRARY_PATH"])
        if path is None:
            del os.environ["LD_LIBRARY_PATH"]
        else:
            os.environ["LD_LIBRARY_PATH"] = path
    os.execv(python, [python, os.path.abspath(__file__), *sys.argv[1:]])


# ---------------------------------------------------------------- VL backend

def find_serve() -> str | None:
    """serve.py of the vllm-serve skill, which runs this machine's vLLM servers: VLLM_SERVE, else the skill
    installed beside this one (resolved first: installed skills are symlinked)."""
    if os.environ.get("VLLM_SERVE"):
        return os.environ["VLLM_SERVE"]
    sibling = Path(__file__).resolve().parents[2] / "vllm-serve" / "scripts" / "serve.py"
    return str(sibling) if sibling.exists() else None


def choose_backend(requested: str, server_url: str | None, serve: str | None) -> tuple[str, str]:
    """(backend, why): "server" (one given by URL), "vllm" (from vllm-serve) or "native". Auto takes vllm-serve's
    server for any number of pages: even cold it overtakes native at about three (2026-10, 2 pages: native 32 s,
    a server start plus parse 42 s, a running server 11 s), and it stays up for the next call."""
    if server_url:
        return "server", f"the server at {server_url}"
    if requested == "native":
        return "native", "--backend native"
    if requested == "vllm":
        return "vllm", "--backend vllm"
    if not serve:
        guide = Path(__file__).resolve().parents[1] / "references" / "install.md"
        return "native", f"vllm-serve is not installed; a vLLM server parses ten to twenty times faster, see {guide}"
    return "vllm", "vllm-serve is installed"


def served_models(url: str) -> list[str] | None:
    """The model names an OpenAI-compatible server lists, or None when it does not answer."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/models", timeout=5) as r:
            return [m["id"] for m in json.load(r).get("data", [])]
    except (OSError, ValueError, KeyError):
        return None


def serve_up(serve: str) -> dict:
    """The VL model's server from vllm-serve: {"url", "model", ...} or {"error", "detail"}. vllm-serve starts it
    unless it runs, shares it with other callers and stops it once idle, so this run leaves it running."""
    try:
        done = subprocess.run(["uv", "run", serve, "up", VL_PROFILE], stdout=subprocess.PIPE, text=True)
    except OSError as e:
        return {"error": "uv_missing", "detail": str(e)}
    try:
        return json.loads(done.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {"error": "no_answer", "detail": f"vllm-serve printed {done.stdout[-300:]!r}"}


def load_backend(args, state: dict) -> dict | None:
    """Load the pipeline with the VL backend this run uses (state: pipeline, backend, load_seconds); an error
    summary when the backend asked for cannot be had."""
    t0 = time.time()
    serve = None if args.vl_server or args.backend == "native" else find_serve()
    if args.vl_server and not (listed := served_models(args.vl_server)):
        return {"error": "vl_server_unreachable", "detail": f"no model list at {args.vl_server.rstrip('/')}/models"}
    if args.backend == "vllm" and not args.vl_server and not serve:
        return {"error": "vl_server_failed", "detail": "vllm-serve not found beside this skill (or VLLM_SERVE); "
                                                       "see references/install.md"}
    backend, why = choose_backend(args.backend, args.vl_server, serve)
    # The client asks for PaddleOCR-VL-1.6-0.9B unless told the served name (vLLM's PaddleOCR-VL recipe).
    url, model = args.vl_server, listed[0] if args.vl_server else None
    if backend == "vllm":
        print(f"[paddleocr] asking vllm-serve for the VL model's server ({why}) ...", file=sys.stderr, flush=True)
        got = serve_up(serve)
        if "error" in got:
            guide = Path(serve).resolve().parents[1] / "references" / "install.md"
            detail = f"vllm-serve {got['error']}: {got.get('detail', '')} (its guide: {guide})"
            if args.backend == "vllm":
                return {"error": "vl_server_failed", "detail": detail}
            print(f"[paddleocr] {detail}", file=sys.stderr, flush=True)
            backend, why = "native", "vllm-serve could not provide a server"
        else:
            url, model = got["url"], got["model"]
    print(f"[paddleocr] VL backend: {backend} ({why}); loading models ...", file=sys.stderr, flush=True)
    state["pipeline"] = make_pipeline(args, None if backend == "native" else url, model)
    state["backend"] = "native" if backend == "native" else "vllm-server"
    state["load_seconds"] = round(time.time() - t0, 1)
    return None


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
    """A phrase looped many times, or a long block that keeps cycling through the same words, such as an author
    line repeated over and over (2026-10: 8,857 characters, 6% of its word trigrams distinct)."""
    if m := REPEAT_RE.search(text):
        return f"repeats {m.group(1)[:80]!r}"
    grams = ngrams(words(tokens(_MATH.sub(" ", text))))
    if len(grams) >= MIN_LOOP_GRAMS and len(set(grams)) < LOOP_DISTINCT * len(grams):
        return f"{len(text)} characters, {len(set(grams))} of {len(grams)} word trigrams distinct"
    return None


def stray_script(text: str, known: set) -> str | None:
    """Snippets around CJK, kana or Hangul characters of `text` that are not in `known`, the text layer's characters."""
    spans = []
    for m in FOREIGN.finditer(text):
        if m.group() in known:
            continue
        if spans and m.start() - spans[-1][1] <= 20:
            spans[-1][1] = m.end()
        else:
            spans.append([m.start(), m.end()])
    if not spans:
        return None
    return " | ".join("..." + text[max(0, s - 20):e + 20].replace("\n", " ") + "..." for s, e in spans[:MAX_SAMPLES])


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


def invented(text: str, found: set) -> list[str]:
    """Samples of word runs in a parsed block whose trigrams the text layer (`found`) lacks, given only when the
    block has such runs with its inline math dropped and with it glued: either spelling alone mismatches the
    text layer's math (2026-10: dropped, "yields where returns"; glued, ORCID marks and matrices)."""
    plain = words(tokens(_MATH.sub(" ", text)))
    runs = missing_runs(plain, found)[1]
    if not runs or not missing_runs(words(tokens(glue_math(text))), found)[1]:
        return []
    return [" ".join(plain[s:e])[:300] for s, e in runs[:MAX_SAMPLES]]


def in_order(missing: Counter, toks: list[str]) -> list[str]:
    seen, out = Counter(), []
    for t in toks:
        if seen[t] < missing[t]:
            seen[t] += 1
            out.append(t)
    return out


def check_document(blocks: list[dict], layer: dict[int, list[tuple] | None],
                   heights: dict[int, float] | None = None) -> tuple[list[dict], list[dict]]:
    """Per-page check results and warnings.

    `blocks` carry id/page/label/text/bbox (page-image pixels); `layer` maps each page to its text-layer
    characters [(ch, x, y)] in the same pixels, or None when the page has no text layer; `heights`, each page's
    image height, enables the uncropped_figure check.
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
        # Text the parse has and the text layer lacks: an invented continuation, a hallucinated line, characters of a
        # script the source never uses. Only blocks over text-layer text: words read from a raster image (a figure, a
        # scanned insert) have nothing to match.
        near = page_list[max(0, idx - 1): idx + 2]
        window = set().union(*(layer_grams.get(p, set()) for p in near))
        known = {c[0] for p in near for c in (layer.get(p) or [])}
        for b in pblocks:
            if (b["label"] in FIGURE_LABELS or not b["text"].strip() or not b["bbox"]
                    or sum(1 for ch, x, y in chars if ch.strip() and inside(x, y, b["bbox"])) < MIN_LAYER_CHARS):
                continue
            if stray := stray_script(b["text"], known):
                warnings.append({"code": "foreign_script", "page": page, "block": b["id"], "detail": stray})
            if b["label"] in FORMULA_LABELS | NOISE_SET | {"table"}:
                continue
            for detail in invented(b["text"], window):
                warnings.append({"code": "extra_text", "page": page, "block": b["id"], "detail": detail})
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
    if heights:
        warnings.extend(uncropped_figures(blocks, heights))
    for b in blocks:
        if b["label"] != "table" and (loop := repetition(b["text"])):
            warnings.append({"code": "repetition", "page": b["page"], "block": b["id"], "detail": loop})
    if no_layer:
        warnings.append({"code": "no_text_layer", "pages": no_layer})
    return pages_info, warnings


# ---------------------------------------------------------------- check (PDF)

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


def run_checks(doc: dict, blocks: list[dict], sizes: list[tuple]) -> tuple[list[dict], list[dict]]:
    """check_document against the document's text layer, with each page's image size in its info and, for a PDF,
    each one-block warning's box in PDF points ("region", for pdftotext -x -y -W -H)."""
    heights = {page: h for page, (_, h) in zip(doc["pages"], sizes)}
    if doc["kind"] != "pdf":
        pages_info, warnings = check_document(blocks, {page: None for page in doc["pages"]}, heights)
    else:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(doc["path"]))
        layer = {page: layer_chars(pdf, page, size) for page, size in zip(doc["pages"], sizes)}
        pages_info, warnings = check_document(blocks, layer, heights)
        by_id = {b["id"]: b for b in blocks}
        for w in warnings:
            if "block" in w:
                width_pt, height_pt = pdf[w["page"] - 1].get_size()
                img_w, img_h = sizes[doc["pages"].index(w["page"])]
                x1, y1, x2, y2 = by_id[w["block"]]["bbox"]
                sx, sy = img_w / width_pt, img_h / height_pt
                w["region"] = [int(x1 / sx) - 4, int(y1 / sy) - 4, int((x2 - x1) / sx) + 8, int((y2 - y1) / sy) + 8]
    for info, (w, h) in zip(pages_info, sizes):
        info.update(width=w, height=h)
    return pages_info, warnings


# ---------------------------------------------------------------- figure groups

FIGURES = 1              # bump when figure grouping changes; parses grouped by an older one need a migration of their own
COVER = 0.7              # share of a figure block's area inside a layout box that makes it one of the box's members
SWALLOW = 0.2            # share of a blocker's area a figure may cover
ROW = 0.0075             # share of the page height within which blocks sit in one row (12 px on a Letter page at scale 2)
LONG_TEXT = 300          # characters: a text block this long is running text, never part of a figure
UNCROPPED_REACH = 0.4    # share of the page height within which a figure crop goes with a caption
LAYOUT_PIPELINE = "PP-StructureV3"   # its layout model (PP-DocLayout_plus-L), with its settings, draws whole figures
CAPTION = re.compile(r"\s*(\*\*)?\s*(extended\s+data\s+|supplementary\s+)?(fig\.?|figure|图)\s*[A-Z]?\d", re.I)
CAPTION_TEXT = re.compile(r"\s*(\*\*)?\s*((extended\s+data\s+|supplementary\s+)?(fig\.?|figure)\s*[A-Z]?\d+[a-z]?\s*(\*\*)?\s*[.:|]"
                          r"|图\s*\d+)", re.I)
TABLE_CAPTION = re.compile(r"\s*(\*\*)?\s*((extended\s+data\s+|supplementary\s+)?table\s*([A-Z]?\d+|[IVX]+\b)|表\s*\d+)", re.I)
PANEL = re.compile(r"\(?[A-Za-z]{1,2}\)?[.:]?")
HEADING_LABELS = {"paragraph_title", "doc_title", "abstract"}
RUNNING_LABELS = {"text", "reference", "reference_content", "footnote", "algorithm", "content"}


def box_area(b) -> float:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def box_overlap(a, b) -> float:
    return box_area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def box_union(boxes) -> list:
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def is_caption(b: dict) -> bool:
    """A figure caption ("Fig. 3 ...", "Figure 2:", "Extended Data Fig. 1 |", "图 3"). The VL model labels some captions
    text, which then need punctuation after the number: "Fig. 3 shows ..." opens running text."""
    t = b["text"].strip()
    if b["label"] == "figure_title":
        return bool(CAPTION.match(t))
    return b["label"] in ("text", "vision_footnote") and bool(CAPTION_TEXT.match(t))


def is_panel(b: dict) -> bool:
    """A panel letter: "a", "(b)", "C."."""
    return b["label"] == "figure_title" and bool(PANEL.fullmatch(b["text"].strip()))


def is_table_caption(b: dict) -> bool:
    """A table caption ("Table 2.", "TABLE IV", "Extended Data Table 1 |"), which the VL model labels figure_title
    more often than not (2026-10: 77 of 96)."""
    return b["label"] in ("figure_title", "table_title", "text", "vision_footnote") and bool(TABLE_CAPTION.match(b["text"].strip()))


def is_subtitle(b: dict) -> bool:
    """A title inside a figure, which the VL model labels figure_title too: "Step 1: ...", "(a) in silico"."""
    return b["label"] == "figure_title" and not is_caption(b) and not is_panel(b) and not is_table_caption(b)


def is_blocker(b: dict) -> bool:
    """A block that parts figures: a figure or table caption, a heading, running text."""
    return (is_caption(b) or is_table_caption(b) or b["label"] in HEADING_LABELS
            or (b["label"] in RUNNING_LABELS and len(b["text"]) >= LONG_TEXT))


def group_page(blocks: list[dict], layout: list[dict] | None, height: float, charts: bool = False) -> list[dict]:
    """The figures of one page that several image/chart blocks make up (the VL layout model boxes each panel):
    [{"members": [ids], "panels": [ids], "bbox", "by"}], members in block order.

    A unit is a figure block or a figure made so far. `layout` holds the boxes of a layout model that draws whole
    figures; one with two or more figure blocks inside makes them a figure ("layout") unless it covers a blocker
    or two captions sit side by side right under it (it spans two figures). Then the units whose nearest caption
    below is one and the same, with no blocker between, make a figure ("caption") unless together they cover a
    blocker. Panel letters and titles within two rows of a figure widen its box; the letters join it. With
    `charts`, charts are data tables and stay out."""
    row = ROW * height
    kinds = {"image"} if charts else {"image", "chart"}
    figs = [b for b in blocks if b["label"] in kinds and b["bbox"] and "merged_into" not in b]
    if len(figs) < 2:
        return []
    order = {b["id"]: i for i, b in enumerate(blocks)}
    captions = [b for b in blocks if b["bbox"] and is_caption(b)]
    # A caption set in two columns goes on to its right on the same row, in a block the VL model labels text or
    # figure_title; that block is the caption too. Another caption beside it is not.
    tails = {c["id"]: [b for b in blocks if b is not c and b["bbox"] and b["label"] in ("text", "figure_title", "vision_footnote")
                       and not is_caption(b) and abs(b["bbox"][1] - c["bbox"][1]) <= row and b["bbox"][0] >= c["bbox"][2] - row]
             for c in captions}
    spans = {c["id"]: box_union([c["bbox"]] + [t["bbox"] for t in tails[c["id"]]]) for c in captions}
    tail_ids = {t["id"] for ts in tails.values() for t in ts}
    # A caption across the middle of the text area sits under a figure as wide as the text: a short centred caption
    # speaks for every panel of a grid above it (2026-10: appendix figures of 2 x 2 plots, each panel wider than the
    # part of the caption below it). A caption within one column speaks for its own width.
    text = [b["bbox"] for b in blocks if b["bbox"] and b["label"] not in NOISE_SET]
    left, right = min(b[0] for b in text), max(b[2] for b in text)
    for cid, span in spans.items():
        if span[0] < (left + right) / 2 - row and span[2] > (left + right) / 2 + row:
            spans[cid] = [left, span[1], right, span[3]]
    blockers = [b for b in blocks if b["bbox"] and (is_blocker(b) or b["id"] in tail_ids)]
    units = {b["id"]: {"members": [b["id"]], "bbox": b["bbox"], "by": None} for b in figs}
    owner = {b["id"]: b["id"] for b in figs}

    def merge(ids, bbox, by):
        roots = sorted({owner[i] for i in ids})
        keep = units[roots[0]]
        for r in roots[1:]:
            gone = units.pop(r)
            keep["members"] += gone["members"]
            keep["bbox"] = box_union([keep["bbox"], gone["bbox"]])
            keep["by"] = keep["by"] or gone["by"]
            for m in gone["members"]:
                owner[m] = roots[0]
        keep["bbox"] = box_union([keep["bbox"]] + ([bbox] if bbox else []))
        keep["by"] = keep["by"] or by

    def covers_blocker(bbox, spare=None):
        return any(x is not spare and box_overlap(bbox, x["bbox"]) > SWALLOW * box_area(x["bbox"]) for x in blockers)

    def caption_below(bbox):
        """The nearest caption below bbox speaking for half its width or more, with no blocker between."""
        best = None
        for c in captions:
            span = spans[c["id"]]
            if bbox[3] > c["bbox"][1] + row or min(bbox[2], span[2]) - max(bbox[0], span[0]) < 0.5 * (bbox[2] - bbox[0]):
                continue
            if any(x is not c and x["bbox"][1] >= bbox[3] - row and x["bbox"][3] <= c["bbox"][1] + row
                   and min(x["bbox"][2], bbox[2]) > max(x["bbox"][0], bbox[0]) for x in blockers):
                continue
            if best is None or c["bbox"][1] < best["bbox"][1]:
                best = c
        return best

    for f in layout or []:
        if f["label"] not in ("image", "chart"):
            continue
        members = [b["id"] for b in figs if box_overlap(f["bbox"], b["bbox"]) >= COVER * box_area(b["bbox"])]
        under = [c for c in captions if f["bbox"][3] - row <= c["bbox"][1] <= f["bbox"][3] + 4 * row
                 and min(c["bbox"][2], f["bbox"][2]) > max(c["bbox"][0], f["bbox"][0])]
        if len(members) >= 2 and len(under) <= 1 and not covers_blocker(f["bbox"]):
            merge(members, f["bbox"], "layout")
    found = {root: caption_below(unit["bbox"]) for root, unit in units.items()}
    # A row of panels (tops and bottoms aligned, side by side) shares the caption right under it: a unit that would
    # pass it for a lower caption, or find none, takes it (2026-10, TMI: a row across the page over a caption under
    # its left half; the right half went on to the next figure's caption in the right column).
    rows = []
    for root in sorted(units, key=lambda r: units[r]["bbox"][0]):
        x1, y1, _, y2 = units[root]["bbox"]
        for r in rows:
            last = units[r[-1]]["bbox"]
            if abs(y1 - last[1]) <= 2 * row and abs(y2 - last[3]) <= 2 * row and x1 - last[2] <= 2 * row:
                r.append(root)
                break
        else:
            rows.append([root])
    for r in rows:
        bottom = max(units[root]["bbox"][3] for root in r)
        under = [c for c in (found[root] for root in r) if c and c["bbox"][1] - bottom <= 4 * row]
        if len(r) >= 2 and under:
            c = min(under, key=lambda c: c["bbox"][1])
            for root in r:
                if found[root] is None or found[root]["bbox"][1] > c["bbox"][3]:
                    found[root] = c
    by_caption = {}
    for root, c in found.items():
        if c:
            by_caption.setdefault(c["id"], (c, []))[1].append(root)
    for c, roots in by_caption.values():
        if len(roots) >= 2 and not covers_blocker(box_union([units[r]["bbox"] for r in roots]), spare=c):
            merge(roots, None, "caption")

    figures, taken = [], set()
    for unit in units.values():
        if len(unit["members"]) < 2:
            continue
        bbox, panels = unit["bbox"], []
        x1, y1, x2, y2 = bbox
        reach = [x1 - 2 * row, y1 - 2 * row, x2 + 2 * row, y2 + 2 * row]
        for b in blocks:
            if b["bbox"] and "merged_into" not in b and b["id"] not in taken | tail_ids and (is_panel(b) or is_subtitle(b)) \
                    and box_overlap(reach, b["bbox"]) > 0 and not covers_blocker(wider := box_union([bbox, b["bbox"]])):
                bbox = wider
                if is_panel(b):
                    panels.append(b["id"])
        taken.update(panels)
        figures.append({"members": sorted(unit["members"], key=order.get), "panels": panels,
                        "bbox": [int(round(v)) for v in bbox], "by": unit["by"]})
    return figures


def uncropped_figures(blocks: list[dict], heights: dict[int, float]) -> list[dict]:
    """uncropped_figure warnings: figure captions that no crop goes with. Each figure crop (a "figure" block, or an
    image or chart in none) goes with the nearest caption below it sharing its columns, else the nearest above it
    (captions set above figures); a caption left over marks a figure the VL model read as text (a prompt, a sample
    output) or as a table, or missed (2026-10: 7 of 303 captions in 22 papers). A caption at the top of a page whose
    page before ends in a crop without a caption is that crop's (Nature Extended Data: figure page, then caption)."""
    out, orphan = [], None
    for page in sorted(heights):
        pblocks = [b for b in blocks if b["page"] == page and b["bbox"]]
        reach = UNCROPPED_REACH * heights[page]
        crops = [b["bbox"] for b in pblocks if b["label"] == "figure" or (b["label"] in ("image", "chart") and "merged_into" not in b)]
        captions = [b for b in pblocks if is_caption(b)]
        taken, spare = set(), None
        for x1, y1, x2, y2 in crops:
            cols = [c for c in captions if min(x2, c["bbox"][2]) > max(x1, c["bbox"][0])]
            below = [c for c in cols if y1 < c["bbox"][1] and y2 <= c["bbox"][3] and c["bbox"][1] - y2 <= reach]
            above = [c for c in cols if c["bbox"][1] <= y1 and c["bbox"][3] < y2 and y1 - c["bbox"][3] <= reach]
            if below or above:
                taken.add((min(below, key=lambda c: c["bbox"][1]) if below else max(above, key=lambda c: c["bbox"][3]))["id"])
            elif y2 > heights[page] / 2:
                spare = True
        for c in captions:
            if c["id"] in taken or (orphan and page == orphan + 1 and c["bbox"][1] < heights[page] / 3):
                continue
            out.append({"code": "uncropped_figure", "page": page, "block": c["id"], "detail": c["text"].strip()[:100]})
        orphan = page if spare else None
    return out


def regroup_markdown(markdown: str, figures: list[tuple[dict, list[dict], list[dict]]]) -> str:
    """`markdown` with, for each (figure, members, panel letters), the figure's crop on its first member's image line,
    the other members' image lines gone, and the letters' lines (bare, usually right before their image) gone from
    around and between them, each removed line with the blank line after it. Every other line stays as it was."""
    lines = markdown.split("\n")
    drop = set()
    for fig, members, panels in figures:
        refs = [f"({m['image']})" for m in members if m.get("image")]
        hits = [i for i, line in enumerate(lines) if any(r in line for r in refs)]
        if not hits:
            continue
        first = next(r for r in refs if r in lines[hits[0]])
        lines[hits[0]] = lines[hits[0]].replace(first, f"({fig['image']})")
        drop.update(hits[1:])
        letters = Counter(p["text"].strip() for p in panels)
        lo, hi = hits[0], hits[-1]
        while lo > 0 and (not lines[lo - 1].strip() or letters[lines[lo - 1].strip()]):
            lo -= 1
        while hi + 1 < len(lines) and (not lines[hi + 1].strip() or letters[lines[hi + 1].strip()]):
            hi += 1
        for i in range(lo, hi + 1):
            if lines[i].strip() and letters[lines[i].strip()] and i != hits[0] and i not in drop:
                letters[lines[i].strip()] -= 1
                drop.add(i)
    out, after_drop = [], False
    for i, line in enumerate(lines):
        if i in drop or (after_drop and not line.strip()):
            after_drop = i in drop
            continue
        after_drop = False
        out.append(line)
    return "\n".join(out)


def layout_model(state: dict):
    """(name, model, settings) of the layout model that draws whole figures, with its pipeline's settings, loaded
    once on first use (PaddleX downloads it the first time); None when it cannot load, with the reason in
    state["layout_error"]."""
    if "layout" not in state:
        try:
            from paddlex import create_model
            from paddlex.inference.pipelines import load_pipeline_config
            cfg = load_pipeline_config(LAYOUT_PIPELINE)["SubModules"]["LayoutDetection"]
            settings = {k: cfg[k] for k in ("threshold", "layout_nms", "layout_unclip_ratio", "layout_merge_bboxes_mode")
                        if cfg.get(k) is not None}
            print(f"[paddleocr] loading {cfg['model_name']} to group figures ...", file=sys.stderr, flush=True)
            state["layout"] = (cfg["model_name"], create_model(model_name=cfg["model_name"]), settings)
        except Exception as e:  # noqa: BLE001 - any failure leaves the grouping to captions
            print(f"[paddleocr] figures are grouped by their captions alone: the layout model did not load "
                  f"({type(e).__name__}: {e})", file=sys.stderr, flush=True)
            state["layout"], state["layout_error"] = None, f"{type(e).__name__}: {e}"
    return state["layout"]


def layout_boxes(model, image) -> list[dict] | None:
    """The layout model's boxes on a page image (BGR), [{"label", "bbox"}]; None when it fails on the page."""
    _, net, settings = model
    try:
        res = next(iter(net.predict(image, batch_size=1, **settings)))
        return [{"label": b["label"], "bbox": [float(v) for v in b["coordinate"]]} for b in res.json["res"]["boxes"]]
    except Exception as e:  # noqa: BLE001 - this page is grouped by its captions
        print(f"[paddleocr] layout model failed on a page ({type(e).__name__}: {e}); grouping it by captions",
              file=sys.stderr, flush=True)
        return None


def save_crop(image, bbox: list, path: Path) -> None:
    import cv2
    x1, y1, x2, y2 = bbox
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(cv2.imencode(".jpg", image[y1:y2, x1:x2])[1].tobytes())


def page_image(doc: dict, page: int, size: tuple, pdf=None):
    """Page `page` as the pipeline saw it (BGR, `size` pixels): rendered as PaddleX renders a PDF (the layout model
    answers differently to another rendering), or the input image scaled to the size it was parsed at."""
    import cv2
    if doc["kind"] == "pdf":
        from paddlex.inference.utils.pdf_rendering import render_pdf_page_to_numpy
        image = render_pdf_page_to_numpy(pdf[page - 1], page_index=page)
    else:
        image = cv2.imread(str(doc["files"][page - 1]), cv2.IMREAD_COLOR)
    if (image.shape[1], image.shape[0]) != tuple(size):
        image = cv2.resize(image, tuple(size), interpolation=cv2.INTER_AREA)
    return image


def group_figures(blocks: list[dict], markdown: str, sizes: dict, image_of, outdir: Path, charts: bool,
                  state: dict) -> tuple[list[dict], str, dict]:
    """Put the figures that several blocks make up back together, on each page with two or more figure blocks
    (sizes: page -> (width, height); image_of(page): the page image the boxes refer to). Each figure becomes a
    "figure" block before its first member, its members and panel letters get merged_into its id, its crop goes
    to outdir/imgs, and regroup_markdown puts that crop in the Markdown. Returns (blocks, markdown, the record for
    parser.figures: the layout model's name, or None when no page used it, and why when it failed to load)."""
    width = max(2, len(str(max(sizes))))
    by_id = {b["id"]: b for b in blocks}
    next_id = max(by_id, default=-1) + 1
    kinds = {"image"} if charts else {"image", "chart"}
    made, used, needed = [], None, False
    for page in sorted(sizes):
        pblocks = [b for b in blocks if b["page"] == page]
        if sum(b["label"] in kinds and bool(b["bbox"]) and "merged_into" not in b for b in pblocks) < 2:
            continue
        image, layout, needed = None, None, True
        if model := layout_model(state):
            image = image_of(page)
            if (layout := layout_boxes(model, image)) is not None:
                used = model[0]
        for g in group_page(pblocks, layout, sizes[page][1], charts):
            if image is None:
                image = image_of(page)
            w, h = sizes[page]
            x1, y1, x2, y2 = g["bbox"]
            bbox = [max(0, x1), max(0, y1), min(w, x2), min(h, y2)]
            name = f"imgs/p{page:0{width}d}_figure_box_{bbox[0]}_{bbox[1]}_{bbox[2]}_{bbox[3]}.jpg"
            save_crop(image, bbox, outdir / name)
            fig = {"id": next_id, "page": page, "label": "figure", "text": "", "bbox": bbox, "image": name, "by": g["by"]}
            next_id += 1
            members, panels = [by_id[i] for i in g["members"]], [by_id[i] for i in g["panels"]]
            for b in members + panels:
                b["merged_into"] = fig["id"]
            made.append((fig, members, panels))
    first = {id(members[0]): fig for fig, members, _ in made}
    grouped = []
    for b in blocks:
        if id(b) in first:
            grouped.append(first[id(b)])
        grouped.append(b)
    figures = {"version": FIGURES, "layout_model": used}
    if needed and not used and state.get("layout_error"):
        figures["layout_error"] = state["layout_error"]
    return grouped, regroup_markdown(markdown, made), figures


def regroup(json_path: Path, md_path: Path, doc: dict, state: dict) -> dict:
    """Group the figures of a parse made before figure grouping, from its pages rendered again, and store the result:
    the figure blocks in its JSON, its Markdown's figure lines rewritten (every other line, fixes included, stays),
    the checks run again when that changed anything or older checks examined it."""
    record = json.loads(json_path.read_text(encoding="utf-8"))
    sizes = {p["page"]: (p["width"], p["height"]) for p in record["pages"]}
    pdf = None
    if doc["kind"] == "pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(doc["path"]))
        pdf.init_forms()
    markdown = md_path.read_text(encoding="utf-8")
    blocks, markdown, figures = group_figures(record["blocks"], markdown, sizes, lambda page: page_image(doc, page, sizes[page], pdf),
                                              md_path.parent, record["parser"].get("options", {}).get("charts", False), state)
    if len(blocks) > len(record["blocks"]):
        md_path.write_text(markdown, encoding="utf-8")
    if len(blocks) > len(record["blocks"]) or record["parser"].get("check", 1) < CHECK:
        record["pages"], record["warnings"] = run_checks(doc, blocks, list(sizes.values()))
        record["parser"]["check"] = CHECK
    record["blocks"] = blocks
    record["parser"]["figures"] = figures
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


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


def make_pipeline(args, server_url: str | None, model: str | None = None):
    """The pipeline; with server_url its VL step goes to that vLLM server, asking for `model`."""
    from paddleocr import PaddleOCRVL
    server = {"vl_rec_backend": "vllm-server", "vl_rec_server_url": server_url} if server_url else {}
    if server_url and model:
        server["vl_rec_api_model_name"] = model
    return PaddleOCRVL(use_doc_orientation_classify=args.photo, use_doc_unwarping=args.photo, **server)


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


def out_paths(doc: dict, args) -> tuple[Path, Path, Path]:
    outdir = Path(args.output) / doc["stem"]
    return outdir, outdir / f"{doc['stem']}.md", outdir / f"{doc['stem']}.json"


def recheck(json_path: Path, doc: dict) -> dict:
    """Run the current checks over a parse that older ones checked and store the results in its JSON. The
    Markdown, with any fixes made to it, stays as it is."""
    record = json.loads(json_path.read_text(encoding="utf-8"))
    sizes = [(p["width"], p["height"]) for p in record["pages"]]
    record["pages"], record["warnings"] = run_checks(doc, record["blocks"], sizes)
    record["parser"]["check"] = CHECK
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def process(doc: dict, args, state: dict) -> dict:
    outdir, md_path, json_path = out_paths(doc, args)
    summary = {"input": doc["input"], "md": str(md_path), "json": str(json_path)}
    if doc["fresh"]:
        old = json.loads(json_path.read_text(encoding="utf-8"))
        stale = old["parser"].get("check", 1) < CHECK
        if "figures" not in old["parser"] and old["parser"].get("options", {}).get("photo"):
            summary["regroup"] = "figures not grouped: --photo pages cannot be rendered again; --force parses anew"
        elif "figures" not in old["parser"]:
            try:
                old = regroup(json_path, md_path, doc, state)
                summary["regrouped"] = True
            except Exception as e:  # noqa: BLE001 - the parse stays as it was
                summary["regroup"] = f"figures not grouped: {type(e).__name__}: {e}"
        if old["parser"].get("check", 1) < CHECK:
            old = recheck(json_path, doc)
        if stale:
            summary["rechecked"] = True
        summary.update(skipped="up_to_date", pages=len(old["pages"]), warnings=old.get("warnings", []))
        return summary
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
        images = [r["doc_preprocessor_res"]["output_img"] for r in results]
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

    span = f"page{'s' if len(doc['pages']) > 1 else ''} {format_pages(doc['pages'])} of {doc['page_count']}"
    header = f"<!-- source: {doc['path'].name} | {span} | PaddleOCR-VL-1.6 | {date.today()} -->"
    markdown, figures = header + "\n\n" + "\n\n".join(parts) + "\n", None
    try:
        blocks, markdown, figures = group_figures(copy.deepcopy(blocks), markdown, dict(zip(doc["pages"], sizes)),
                                                  lambda page: images[doc["pages"].index(page)], outdir, args.charts, state)
    except Exception as e:  # noqa: BLE001 - keep the parse; a later run without --force groups it
        print(f"[paddleocr] {doc['stem']}: figures not grouped ({type(e).__name__}: {e})", file=sys.stderr, flush=True)
    pages_info, warnings = run_checks(doc, blocks, sizes)

    import paddleocr
    md_path.write_text(markdown, encoding="utf-8")
    record = {
        "source": {"path": str(doc["path"].resolve()), "sha256": doc["sha"], "page_count": doc["page_count"], "pages": doc["pages"]},
        "parser": {"pipeline": "PaddleOCR-VL-1.6", "paddleocr": getattr(paddleocr, "__version__", None),
                   "backend": state["backend"], "format": FORMAT, "check": CHECK, "options": options_of(args)},
        "pages": pages_info,
        "blocks": blocks,
        "warnings": warnings,
    }
    if figures:
        record["parser"]["figures"] = figures
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")

    counts = {}
    for b in blocks:
        counts[b["label"]] = counts.get(b["label"], 0) + 1
    covered = [p["coverage"] for p in pages_info if p["coverage"] is not None]
    seconds = time.time() - t0
    summary.update(
        pages=len(doc["pages"]),
        blocks=counts,
        min_coverage=round(min(covered), 3) if covered else None,
        warnings=warnings,
        backend=state["backend"],
        seconds=round(seconds, 1),
        pages_per_minute=round(len(doc["pages"]) * 60 / seconds, 1),
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
    p.add_argument("--backend", choices=["auto", "vllm", "native"], default="auto",
                   help="VL model backend (default auto: the vllm-serve skill's server when it can provide one, "
                        "else native)")
    p.add_argument("--vl-server", metavar="URL", help="use this running vLLM server, e.g. http://127.0.0.1:8118/v1")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ensure_tool_env()
    docs = [resolve_input(raw, args.pages) for raw in args.inputs]
    for doc in docs:
        if "error" not in doc:
            doc["sha"] = sha256_of(doc["files"] if doc["kind"] == "images" else [doc["path"]])
            doc["fresh"] = not args.force and up_to_date(out_paths(doc, args)[2], doc["sha"], options_of(args))
    pending = sum(len(doc["pages"]) for doc in docs if "error" not in doc and not doc["fresh"])
    state, failed = {}, False
    if pending and (error := load_backend(args, state)):
        print(json.dumps(error, ensure_ascii=False), flush=True)
        return 2
    for doc in docs:
        if "error" not in doc:
            try:
                doc = process(doc, args, state)
            except Exception as e:  # noqa: BLE001 - report and continue with the next document
                doc = {"input": doc["input"], "error": "parse_failed", "detail": f"{type(e).__name__}: {e}"}
        failed |= "error" in doc
        print(json.dumps(doc, ensure_ascii=False), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
