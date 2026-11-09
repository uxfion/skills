#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Parse documents, PDFs or page images, with PaddleOCR-VL into a record, Markdown and figures.

Each INPUT is one document (a directory: its page images in natural order); - reads their paths from stdin, a path a
line or our JSON lines by `input` (parse's own, p2z.py package take's). Each document goes to DIR/<stem>/, the folder
every other ocr.py word works on:
  <stem>.json   the record: what the models gave, as given (PaddleOCR's blocks, with ids p<page>-<block_id>; the
                second layout model's boxes on each page), every change made to it since, in order ("auto:<step>"
                by processing, "agent" / "user" by settling, each with its reason), the figures, and the findings
  <stem>.md     the reading copy, generated from the record: <!-- page N --> before each page, LaTeX formulas with
                \\tag*{(n)}, HTML tables (merged across pages), each figure's image where its first panel was, inside
                <!-- figure ID --> markers with the text the model read in it, a note before each open finding
  imgs/         the figures, and the images inside tables, PNG cut from the source at 300 dpi, named by figure id
  pages/        --photo only: the corrected page images the boxes refer to

Processing: PaddleOCR's restructure_pages (tables continued across pages merged, heading levels); figures put together
from their panels by the second layout model's whole-figure boxes and the captions (PP-StructureV3's
PP-DocLayout_plus-L, run on every page; when it cannot load, captions alone, and stderr says so); then the checks
against the PDF's text layer and of each figure against its caption, whose findings ocr.py findings lists.

A document whose record holds the same source (sha256, pages) and options is processed again from the stored model
output, without the GPU, when the code that processes or checks a record has changed since (rendered: true), else
skipped (reason up_to_date). -f parses it again; the edits an agent or the user made
carry over to the new parse (matched by block id and the text they changed), and those that no longer fit become
stale_edit findings. A folder holding a parse of an older format is moved aside to <stem>.format2/ and the document
parsed anew (archived). Markdown edits not recorded yet are committed first.

The VL model runs natively (one block at a time, about 10-15 s a page) or in a vLLM server (continuous batching,
0.5-1 s a page). --backend auto asks the vllm-serve skill (installed beside this one, or VLLM_SERVE = its serve.py)
for the server whenever a run has pages to parse, however few: `serve.py up paddleocr-vl` starts it unless it runs,
and it stops by itself once idle. Without vllm-serve, without vLLM, or with too little free GPU memory for the server,
the run goes native and stderr says why. --backend vllm insists on the server; native avoids it.

The models run in the Python of the `paddleocr` uv tool (PADDLEOCR_PYTHON overrides): the command re-executes itself
there with CUDA_MODULE_LOADING=EAGER and, when that environment ships its own CUDA runtime, without the CUDA toolkit
directories in LD_LIBRARY_PATH (the skill's references/install.md says why).

stdout: one line per document as it is done, {input, code, folder, md, json, ...}:
  ok         parsed (backend, seconds, pages_per_minute, load_seconds, edits_carried, archived) or rendered: true;
             then pages, blocks (by label), figures, min_coverage, checks, open and unresolved (finding ids), and
             recorded, gone, new, reopened when Markdown edits were recorded or findings came and went
  skipped    reason up_to_date, with the same counts
  file_not_found, unsupported_input, bad_pages, parse_failed, edit_refused, locked: that document failed, see hint
  not_run    not reached: the run stopped (exit 2)
A line of a - list that names no input and reports a skip or a failure upstream is passed on as it is.
stderr: progress ([paddleocr] ... page N done) and warnings that bear on the result (why the run went native, the
second layout model not loaded); empty when every document is skipped.
Exit 0 = every document parsed or skipped; 1 = some failed, and stderr's last line is {"summary": {total, ok,
skipped, failed}}; 2 = it could not go on, and stderr's last line {code, hint} says why: paddleocr_missing (no tool
environment), vl_server_failed (--backend vllm, with vllm-serve's reason), vl_server_unreachable (--vl-server),
invalid_list (a - list line names no input; nothing was parsed), usage.

Examples:
  ocr.py parse paper.pdf -o /abs/out/
  ocr.py parse -f --pages 1-8 a.pdf b.pdf scans/ -o /abs/out/
  p2z.py package take K1 K2 --missing -o /abs/d/ | ocr.py parse -o /abs/d/ -
"""
from __future__ import annotations

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
import urllib.request
import warnings as pywarnings
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
ENGINE = "PaddleOCR-VL-1.6"
LAYOUT_PIPELINE = "PP-StructureV3"   # its layout model (PP-DocLayout_plus-L), with its settings, draws whole figures
VL_PROFILE = "paddleocr-vl"         # the vllm-serve profile that serves the VL model
sys.path.insert(0, str(Path(__file__).resolve().parent))   # the record's code (doc), and ocrlib
from ocrlib import cli  # noqa: E402


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


def ensure_tool_env(script: str = __file__) -> None:
    """Return inside an interpreter that has paddleocr, or raise paddleocr_missing (exit 2); `script` is what to run
    again in the tool's interpreter (render passes its own)."""
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
        guide = Path(__file__).resolve().parents[1] / "references" / "install.md"
        raise cli.Stop("paddleocr_missing", exit=cli.CANNOT, detail="no paddleocr uv tool found",
                       hint=f"Install it as {guide} says (PADDLEOCR_PYTHON names its Python when it is elsewhere).")
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
    os.execv(python, [python, os.path.abspath(script), *sys.argv[1:]])


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
    """The VL model's server from vllm-serve: its `up` line {"url", "model", ...} or {"error", "detail"}. vllm-serve
    starts it unless it runs, shares it with other callers and stops it once idle, so this run leaves it running.
    Its stderr, the progress of a start that can take minutes, passes on to ours as it comes. The answer is the code
    of its last line: stdout's when it exits 0 or 1, stderr's when it exits 2 (nothing tried); only ok serves."""
    try:
        proc = subprocess.Popen(["uv", "run", "--quiet", serve, "up", VL_PROFILE], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    except OSError as e:
        return {"error": "uv_missing", "detail": str(e)}
    last_err = ""
    for line in proc.stderr:
        print(line, end="", file=sys.stderr, flush=True)
        last_err = line.strip() or last_err
    out = proc.stdout.read()
    proc.wait()
    last = last_err if proc.returncode == 2 else (out.strip().splitlines() or [""])[-1]
    try:
        got = json.loads(last)
    except ValueError:
        got = None
    if not (isinstance(got, dict) and isinstance(got.get("code"), str)):
        return {"error": "no_answer", "detail": f"vllm-serve exited {proc.returncode}; its last line: {last[-300:]!r}"}
    if got["code"] != "ok":
        return {"error": got["code"], "detail": "; ".join(str(got[k]) for k in ("detail", "hint") if got.get(k))}
    if got.get("foreign_cuda"):
        guide = Path(serve).resolve().parents[1] / "references" / "install.md"
        print(f"[paddleocr] vllm-serve foreign_cuda: the VL server loaded CUDA libraries from outside vLLM's "
              f"environment: {', '.join(got['foreign_cuda'])}; {guide}, entry `foreign_cuda`, traces them",
              file=sys.stderr, flush=True)
    return got


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


def sha256_of(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def resolve_input(raw: str, pages_spec: str | None) -> dict:
    """Describe one document, or return the line of its failure, {"input", "code", "detail"?, "hint"}."""
    path = Path(raw).expanduser()
    unsupported = "A document is a PDF, an image, or a directory of page images."
    if not path.exists():
        return {"input": raw, "code": "file_not_found", "hint": "No such file or directory."}
    if path.is_dir():
        files = sorted((p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES), key=lambda p: natural_key(p.name))
        if not files:
            return {"input": raw, "code": "unsupported_input", "detail": "directory holds no page images",
                    "hint": unsupported}
        kind = "images"
    elif path.suffix.lower() == ".pdf":
        files, kind = [path], "pdf"
    elif path.suffix.lower() in IMAGE_SUFFIXES:
        files, kind = [path], "images"
    else:
        return {"input": raw, "code": "unsupported_input", "detail": f"not a PDF or image: {path.suffix}",
                "hint": unsupported}
    if kind == "pdf":
        import pypdfium2 as pdfium
        try:
            count = len(pdfium.PdfDocument(str(path)))
        except Exception as e:  # noqa: BLE001 - pdfium raises its own error types
            return {"input": raw, "code": "unsupported_input", "detail": f"unreadable PDF: {e}", "hint": unsupported}
    else:
        count = len(files)
    try:
        pages = parse_pages(pages_spec, count)
    except ValueError as e:
        return {"input": raw, "code": "bad_pages", "detail": str(e),
                "hint": f"--pages takes page numbers and ranges within the document's {count} pages: 1-3,8 or 5-."}
    return {"input": raw, "path": path, "kind": kind, "files": files, "page_count": count, "pages": pages,
            "stem": path.stem if path.is_file() else path.name}



# ---------------------------------------------------------------- the models

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
            state["layout"] = (cfg["model_name"], create_model(model_name=cfg["model_name"]), settings)
        except Exception as e:  # noqa: BLE001 - any failure leaves the grouping to captions
            print(f"[paddleocr] figures are grouped by their captions alone: the layout model did not load "
                  f"({type(e).__name__}: {e})", file=sys.stderr, flush=True)
            state["layout"], state["layout_error"] = None, f"{type(e).__name__}: {e}"
    return state["layout"]


def layout_rows(model, image) -> list | None:
    """The layout model's boxes on a page image (BGR) as [label, score, x1, y1, x2, y2]; None when it fails."""
    _, net, settings = model
    try:
        res = next(iter(net.predict(image, batch_size=1, **settings)))
        return [[b["label"], round(float(b["score"]), 3), *[int(round(float(v))) for v in b["coordinate"]]]
                for b in res.json["res"]["boxes"]]
    except Exception as e:  # noqa: BLE001 - this page is grouped by its captions
        print(f"[paddleocr] layout model failed on a page ({type(e).__name__}: {e}); grouping it by captions",
              file=sys.stderr, flush=True)
        return None


def quiet_paddlex() -> None:
    """PaddleX's logger at WARNING: what it says at INFO as models load (which model it creates, that cached files are
    used) is neither progress nor a warning; its warnings and errors still reach stderr. Its import sets INFO, so this
    comes after it; the level holds for the process, the layout model loaded later included. PADDLE_PDX_DEBUG, PaddleX's
    own switch, keeps it talking."""
    from paddlex.utils import flags
    from paddlex.utils.logging import setup_logging
    if not flags.DEBUG:
        setup_logging("WARNING")


def make_pipeline(args, server_url: str | None, model: str | None = None):
    """The pipeline; with server_url its VL step goes to that vLLM server, asking for `model`."""
    from paddleocr import PaddleOCRVL
    quiet_paddlex()
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


def is_rectangle(points, box) -> bool:
    x1, y1, x2, y2 = box
    corners = {(x1, y1), (x2, y1), (x2, y2), (x1, y2)}
    return len(points) == 4 and all(any(abs(px - cx) <= 1 and abs(py - cy) <= 1 for cx, cy in corners) for px, py in points)


def page_scale(doc: dict, page: int, size: tuple, photo: bool) -> float:
    """Engine pixels per source unit: PaddleX's render scale for a PDF page (2 within its pixel budget), the engine's
    size over the image's for image input; 1 for --photo, whose boxes refer to the corrected page image."""
    if photo:
        return 1.0
    if doc["kind"] == "pdf":
        import pypdfium2 as pdfium
        from paddlex.inference.utils.pdf_rendering import get_pdf_render_scale_within_pixel_limit
        return get_pdf_render_scale_within_pixel_limit(pdfium.PdfDocument(str(doc["path"]))[page - 1].get_size(), page_index=page)
    import cv2
    image = cv2.imread(str(doc["files"][page - 1]), cv2.IMREAD_UNCHANGED)
    return size[0] / image.shape[1]


def raw_page(res, page: int, scale: float, layout: list | None, photo: bool) -> tuple[dict, list[dict]]:
    """One page of the record as the models gave it: the page (size, scale, the layout model's boxes) and its blocks,
    id p<page>-<block_id> (PaddleOCR's position in its reading order), label, box, text, the group the block's text
    went to when not its own, and the polygon when not the box."""
    j = res.json["res"]
    info = {"page": page, "image_size": [int(j["width"]), int(j["height"])], "scale": scale}
    if photo:
        info["photo"] = True
    if layout is not None:
        info["layout"] = layout
    blocks = []
    for b in j["parsing_res_list"]:
        rec = {"id": f"p{page}-{b['block_id']}", "label": b["block_label"], "box": [int(v) for v in b["block_bbox"]],
               "text": b["block_content"] or ""}
        if b.get("group_id") is not None and b["group_id"] != b["block_id"]:
            rec["group"] = f"p{page}-{b['group_id']}"
        if (pts := b.get("block_polygon_points")) and not is_rectangle(pts, rec["box"]):
            rec["polygon"] = [[round(float(x), 1), round(float(y), 1)] for x, y in pts]
        blocks.append(rec)
    return info, blocks


def run_models(doc: dict, args, state: dict, folder: Path) -> dict:
    """The record of a document as the models give it: PaddleOCR-VL's blocks and the second layout model's boxes,
    page by page; for --photo the corrected page images go to folder/pages."""
    import paddleocr
    pipeline, model, t0 = state["pipeline"], layout_model(state), time.time()
    pages, blocks = [], []
    with tempfile.TemporaryDirectory(prefix="paddleocr-") as tmp:
        for k, res in enumerate(pipeline.predict_iter(predict_input(doc, Path(tmp)), use_chart_recognition=args.charts,
                                                      use_ocr_for_image_block=args.figure_text)):
            page = doc["pages"][k]
            image = res["doc_preprocessor_res"]["output_img"]
            if args.photo:
                import cv2
                (folder / "pages").mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(folder / "pages" / f"p{page}.png"), image)
            size = (int(res["width"]), int(res["height"]))
            info, bs = raw_page(res, page, page_scale(doc, page, size, args.photo), layout_rows(model, image) if model else None,
                                args.photo)
            pages.append(info)
            blocks += bs
            print(f"[paddleocr] {doc['stem']}: page {page} done ({k + 1}/{len(doc['pages'])}, "
                  f"{time.time() - t0:.0f} s since this document started)", file=sys.stderr, flush=True)
    source = {"kind": doc["kind"], "file": doc["path"].name, "path": str(doc["path"].resolve()), "sha256": doc["sha"],
              "page_count": doc["page_count"], "pages": doc["pages"]}
    if doc["kind"] == "images":
        source["files"] = [f.name for f in doc["files"]]
    layout = {"name": model[0], "settings": model[2]} if model else {"error": state.get("layout_error")}
    import doc as D
    return {"format": D.FORMAT, "source": source,
            "run": {"engine": ENGINE, "paddleocr": getattr(paddleocr, "__version__", None), "backend": state["backend"],
                    "options": options_of(args), "layout_model": layout, "at": D.now(), "versions": {}},
            "pages": pages, "blocks": blocks, "figures": [], "findings": []}


# ---------------------------------------------------------------- documents

def options_of(args) -> dict:
    return {"charts": args.charts, "figure_text": args.figure_text, "photo": args.photo}


def stored(json_path: Path) -> dict | None:
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def current(old: dict | None, doc: dict, args) -> bool:
    """Whether a stored record is of this source, pages and options: then the models need not run again."""
    import doc as D
    return bool(old) and old.get("format") == D.FORMAT and old["source"]["sha256"] == doc["sha"] \
        and old["source"]["pages"] == doc["pages"] and old["run"]["options"] == options_of(args)


def archive(folder: Path) -> Path:
    """Move a parse of an older format aside, Markdown fixes and all, for reference."""
    target, n = folder.with_name(f"{folder.name}.format2"), 2
    while target.exists():
        target, n = folder.with_name(f"{folder.name}.format2-{n}"), n + 1
    shutil.move(str(folder), str(target))
    return target


def process(doc: dict, args, state: dict) -> dict:
    """One document parsed, processed again or skipped -> its line's fields."""
    import doc as D
    folder = args.output / doc["stem"]
    json_path, md_path = D.paths(folder)
    line = {"folder": str(folder), "md": str(md_path), "json": str(json_path)}
    src = {"kind": doc["kind"], "path": doc["path"], "files": doc["files"]}
    old = stored(json_path)
    if old and old.get("format") != D.FORMAT:
        line["archived"] = str(archive(folder))
        old = None
    t0 = time.time()
    if doc["fresh"]:
        with D.locked(folder):
            moves = D.settle_edits(folder, old, src)
            if old["run"].get("versions") != D.versions():
                moves = D.tally(moves, D.build(old, src, folder))
                line["rendered"] = True
            else:
                line.update(code="skipped", reason="up_to_date")
        return {**line, **D.summary(old), **moves}
    folder.mkdir(parents=True, exist_ok=True)
    record = run_models(doc, args, state, folder)
    moves = {}
    with D.locked(folder):
        if old and old["source"]["sha256"] == doc["sha"]:
            moves = D.settle_edits(folder, old, src)
            if carried := D.migrate(old, record):
                line["edits_carried"] = carried
        D.build(record, src, folder)
    seconds = time.time() - t0
    line.update(backend=state["backend"], seconds=round(seconds, 1),
                pages_per_minute=round(len(doc["pages"]) * 60 / seconds, 1))
    if "load_seconds" in state:
        line["load_seconds"] = state.pop("load_seconds")
    return {**line, **D.summary(record), **moves}


def attempt(doc: dict, args, state: dict) -> dict:
    """process(); whatever fails is this document's own line, a lock another run holds on its folder too."""
    try:
        return process(doc, args, state)
    except cli.Stop as stop:
        stop.exit = cli.ACT
        raise
    except Exception as e:  # noqa: BLE001 - this document fails, the next is parsed
        raise cli.Stop("parse_failed", detail=f"{type(e).__name__}: {e}",
                       hint="Parse this document again on its own; take a failure that repeats to the user.") from e


BACKEND_HINTS = {
    "vl_server_unreachable": "Nothing answered at --vl-server: check the URL, or leave --vl-server out and the "
                             "vllm-serve skill provides the server.",
    "vl_server_failed": "--backend vllm takes only vllm-serve's server, and detail says why there is none; without "
                        "--backend the run goes native.",
}


def build_parser() -> cli.Parser:
    p = cli.parser(__doc__)
    p.add_argument("inputs", nargs="*", metavar="INPUT",
                   help="a PDF, an image, or a directory of page images; - reads a list of paths from stdin")
    p.add_argument("-o", "--output", required=True, metavar="DIR/", help="each document goes to DIR/<stem>/")
    p.add_argument("--pages", metavar="RANGES", help="pages to parse, e.g. 1-3,8 or 5- (output keeps original numbers)")
    p.add_argument("-f", "--force", action="store_true", help="parse again even when the record is of this source and options")
    p.add_argument("--charts", action="store_true", help="turn charts into data tables (values are model-read; check them)")
    p.add_argument("--figure-text", action="store_true", help="OCR the text inside figures into the Markdown")
    p.add_argument("--photo", action="store_true", help="correct orientation and warping (photographed or skewed scans)")
    p.add_argument("--backend", choices=["auto", "vllm", "native"], default="auto",
                   help="VL model backend (default auto: the vllm-serve skill's server when it can provide one, "
                        "else native)")
    p.add_argument("--vl-server", metavar="URL", help="use this running vLLM server, e.g. http://127.0.0.1:8118/v1")
    return p


def main(argv=None) -> int:
    p = build_parser()
    args = cli.parse(p, argv)
    if not args.inputs:
        p.error("name the documents: PDFs, images or directories of page images; - reads their paths from stdin")
    args.output = Path(args.output).expanduser().resolve()
    try:
        ensure_tool_env()       # may run this again in the tool's Python, with the same stdin: - is read after it
        missing = None
    except cli.Stop as stop:    # no tool environment: the list is read here, and no document is parsed
        missing = stop
    try:
        named = cli.paths(args.inputs, "input")
    except cli.Stop as stop:
        cli.emit(stop.line(), sys.stderr)
        return stop.exit
    out, state = cli.Lines(), {}
    docs = {} if missing else {i: resolve_input(raw, args.pages) for i, raw in enumerate(named) if isinstance(raw, str)}
    for doc in docs.values():
        if "code" not in doc:
            doc["sha"] = sha256_of(doc["files"] if doc["kind"] == "images" else [doc["path"]])
            json_path = args.output / doc["stem"] / f"{doc['stem']}.json"
            doc["fresh"] = not args.force and current(stored(json_path), doc, args)
    pending = sum(len(doc["pages"]) for doc in docs.values() if "code" not in doc and not doc["fresh"])
    if missing and any(isinstance(raw, str) for raw in named):
        out.stop(missing)
    elif pending and (error := load_backend(args, state)):
        out.stop(cli.Stop(error["error"], exit=cli.CANNOT, detail=error.get("detail"),
                          hint=BACKEND_HINTS.get(error["error"])))
    for i, raw in enumerate(named):
        doc = docs.get(i)
        if isinstance(raw, dict) or doc and "code" in doc:   # passed on from upstream, or failed before parsing
            out.put(raw if isinstance(raw, dict) else doc)
        else:
            out.add({"input": raw}, lambda: attempt(doc, args, state))
    return out.finish()


if __name__ == "__main__":
    sys.exit(main())
