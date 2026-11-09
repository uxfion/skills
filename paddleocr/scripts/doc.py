#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python-headless", "pypdfium2"]
# ///
"""The record of a parsed document, and everything done to it after the models ran: ocr.py's words but parse.

Each command works on one parse folder, <outdir>/<stem>, and names it first on its line.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocrlib import checks, cli, conventions, figures  # noqa: E402
from ocrlib.cli import Stop  # noqa: E402

FORMAT = 3               # the record's layout; a record of another format is parsed anew
RENDER = 4               # the Markdown's layout; commit reads an edited Markdown in the layout its first line names
REFINE = 1               # bump when processing changes, so stored records are processed again (no GPU)
CROP_DPI = 300
IGNORED = {"number", "header", "header_image", "footer", "footer_image"}   # page furniture: in the record, not the Markdown
FIGURE_KINDS = {"image", "chart", "seal"}
FORMULAS = {"display_formula", "formula"}
LOCK_STALE = 1800        # seconds after which a lock left by a dead run is taken over
NOTE_CHARS = 600         # longest finding text quoted in a note


def versions() -> dict:
    return {"refine": REFINE, "checks": checks.VERSION, "figures": figures.VERSION, "conventions": conventions.VERSION}


# ---------------------------------------------------------------- record and source

def paths(folder: Path) -> tuple[Path, Path]:
    return folder / f"{folder.name}.json", folder / f"{folder.name}.md"


def load(folder: Path) -> dict:
    json_path = paths(folder)[0]
    if not folder.exists():
        raise Stop("file_not_found", hint="No such folder: name the one ocr.py parse wrote, <outdir>/<stem>.")
    try:
        record = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Stop("no_record", detail=f"{json_path}: {e}",
                   hint="The folder holds no readable record: name the one ocr.py parse wrote, <outdir>/<stem>.") from e
    if record.get("format") != FORMAT:
        raise Stop("old_format", detail=f"the record is format {record.get('format', 2)}, not {FORMAT}",
                   hint="Parse the source again (ocr.py parse <source> -o <outdir>/): it moves this parse aside.")
    return record


def write_atomic(path: Path, data: str | bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "wb") as f:
        f.write(data.encode("utf-8") if isinstance(data, str) else data)
    os.replace(tmp, path)


def save(folder: Path, record: dict, markdown: str) -> None:
    """The Markdown and the record, each replaced whole; the images are written before."""
    json_path, md_path = paths(folder)
    write_atomic(json_path, json.dumps(record, ensure_ascii=False, indent=1))
    write_atomic(md_path, markdown)


@contextmanager
def locked(folder: Path):
    """One writer per folder: a lock file holding the pid and time, taken over when its run is gone or old."""
    path = folder / ".lock"
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                pid, at = path.read_text().split()
                alive = True
                try:
                    os.kill(int(pid), 0)
                except OSError:
                    alive = False
                if alive and time.time() - float(at) < LOCK_STALE:
                    raise Stop("locked", exit=cli.CANNOT, detail=f"process {pid} is writing the folder",
                               hint="Wait until that process ends, then run this again.")
            except ValueError:
                pass
            path.unlink(missing_ok=True)
    else:
        raise Stop("locked", exit=cli.CANNOT, detail=f"could not lock {folder}", hint="Run this again.")
    with os.fdopen(fd, "w") as f:
        f.write(f"{os.getpid()} {time.time()}")
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def sha256_of(files: list[Path]) -> str:
    h = hashlib.sha256()
    for p in files:
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def source_of(record: dict, given: str | None = None, need: bool = False, folder: Path | None = None) -> dict | None:
    """The source the record was parsed from: {"kind", "path", "files"}, checked against its sha256. Where the
    record's path holds nothing (the file renamed or moved since), its `file` beside the parse folder, where
    package take and paper-read's take put it, when its sha256 is the record's. None when neither holds it and no
    --source was given, unless the command needs it."""
    src = record["source"]
    raw = given or src.get("path") or ""
    path = Path(raw).expanduser() if raw else None
    if not given and (path is None or not path.exists()) and folder is not None and src.get("file"):
        beside = folder.parent / src["file"]
        if beside.is_file() and sha256_of([beside]) == src["sha256"]:
            path = beside
    if path is None or not path.exists():
        if given:
            raise Stop("file_not_found", exit=cli.CANNOT, path=given, hint="--source names no file.")
        if need:
            raise Stop("source_not_found", path=raw or None,
                       hint="The source is not at the record's path: give it with --source FILE.")
        return None
    files = [path] if src["kind"] == "pdf" else [path / f for f in src["files"]] if path.is_dir() else [path]
    try:
        same = sha256_of(files) == src["sha256"]
    except OSError:                                    # a directory where a file was, or a page image gone
        same = False
    if not same:
        if given:
            raise Stop("source_mismatch", exit=cli.CANNOT, path=given,
                       hint="--source is not the file this parse was made from (its sha256 differs).")
        raise Stop("source_mismatch", path=raw, hint="The file at the record's path is not the one this parse was "
                   "made from (its sha256 differs): give that one with --source FILE.")
    return {"kind": src["kind"], "path": path, "files": files}


def pdf_of(src: dict):
    if "pdf" not in src:
        import pypdfium2 as pdfium
        src["pdf"] = pdfium.PdfDocument(str(src["path"]))
        src["pdf"].init_forms()
    return src["pdf"]


def page_image(src: dict, folder: Path, info: dict, scale: float | None = None):
    """A page as BGR pixels: at the engine's size (the boxes' pixels) by default, else at `scale` per source unit."""
    import cv2
    w, h = info["image_size"]
    if src["kind"] == "pdf" and not info.get("photo"):
        s = scale or info["scale"]
        image = pdf_of(src)[info["page"] - 1].render(scale=s).to_numpy()[:, :, :3]
        if scale is None and (image.shape[1], image.shape[0]) != (w, h):
            image = cv2.resize(image, (w, h), interpolation=cv2.INTER_AREA)
        return image
    file = folder / "pages" / f"p{info['page']}.png" if info.get("photo") else src["files"][min(info["page"], len(src["files"])) - 1]
    image = cv2.imread(str(file), cv2.IMREAD_COLOR)
    if scale is None:
        return cv2.resize(image, (w, h), interpolation=cv2.INTER_AREA) if (image.shape[1], image.shape[0]) != (w, h) else image
    k = scale * info["scale"] if not info.get("photo") else scale
    return image if abs(k - info["scale"]) < 1e-6 else cv2.resize(image, None, fx=k / info["scale"], fy=k / info["scale"])


def to_source(info: dict, box) -> list:
    """A box in engine pixels -> source units (PDF points, image pixels; --photo: pages/ pixels)."""
    s = 1 if info.get("photo") else info["scale"]
    return [round(v / s, 1) for v in box]


def to_engine(info: dict, box) -> list:
    s = 1 if info.get("photo") else info["scale"]
    return [int(round(v * s)) for v in box]


# ---------------------------------------------------------------- state: the models' output with its changes

def page_of(ident: str) -> int:
    return int(re.match(r"p(\d+)", ident).group(1))


def fold(block: dict) -> dict:
    """The block as it is now: its text, label and the rest as given, with every change applied in order. A text
    change ("was" -> "now") whose "was" the text no longer holds exactly once is not applied: it is stale."""
    state = {"text": block.get("text", ""), "label": block.get("label"), "level": None, "merged_into": None,
             "deleted": False, "stale": []}
    for c in block.get("changes", []):
        if "was" in c:
            if state["text"].count(c["was"]) == 1:
                state["text"] = state["text"].replace(c["was"], c["now"])
            else:
                state["stale"].append(c)
        for key in ("text", "label", "level", "merged_into", "deleted"):
            if key in c:
                state[key] = c[key]
    return state


def fold_figure(fig: dict) -> dict:
    """A figure as it is now: its box, the caption an agent or the user named for it, and whether it is hidden, from
    its changes; its members as processing last found them inside that box (the ids a change recorded are its
    history: a new parse can number blocks anew)."""
    state = {"box": None, "members": [], "caption": None, "hidden": False}
    for c in fig.get("changes", []):
        if "box" in c:
            state.update(box=c["box"], hidden=False)
        if "members" in c:
            state["members"] = c["members"]
        if "caption" in c:
            state["caption"] = c["caption"]
        if "hidden" in c:
            state["hidden"] = c["hidden"]
    if "members" in fig:
        state["members"] = fig["members"]
    return state


def blocks_view(record: dict) -> list[dict]:
    """The blocks as they are now, in record order, without the deleted ones: id, page, label, text, box, level;
    merged_into when the content moved into another block (a PaddleOCR group, a table continued across pages);
    figure when the block is an image of a figure."""
    member = {}
    for f in record.get("figures", []):
        for m in fold_figure(f)["members"]:
            member.setdefault(m, f["id"])
    out = []
    for b in record["blocks"]:
        s = fold(b)
        if s["deleted"]:
            continue
        v = {"id": b["id"], "page": page_of(b["id"]), "label": s["label"], "text": s["text"], "box": b.get("box"),
             "level": s["level"]}
        if target := s["merged_into"] or b.get("group"):
            v["merged_into"] = target
        if b["id"] in member:
            v["figure"] = member[b["id"]]
        out.append(v)
    return out


def figures_view(record: dict) -> list[dict]:
    """The figures shown, as they are now: id, page, box, image, members, inside, caption, number, named (an agent or
    the user named its caption), settled (an agent or the user cut it or named its caption)."""
    out = []
    for f in record.get("figures", []):
        s = fold_figure(f)
        if s["hidden"] or not s["box"]:
            continue
        out.append({"id": f["id"], "page": page_of(f["id"]), "box": s["box"], "image": f["image"], "members": s["members"],
                    "inside": f.get("inside", []), "caption": f.get("caption"), "number": f.get("number", ""),
                    "named": s["caption"] is not None and s["caption"] == f.get("caption"),
                    "settled": any(not c["by"].startswith("auto") for c in f.get("changes", []))})
    return out


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- processing (加工)

def restructure(record: dict) -> None:
    """PaddleOCR's own pass over the pages (restructure_pages), from the stored blocks: a table continued on the next
    page merged into its first part, heading levels set across the document, a leading "#" taken off a text. Its
    results are recorded as auto:restructure changes, so the blocks keep what the model gave. A gap in the pages
    (--pages) gets an empty page, so that no table is merged across it. Needs the paddleocr tool environment."""
    from paddlex.inference.pipelines.paddleocr_vl.pipeline import _PaddleOCRVLPipeline
    settings = {"use_doc_preprocessor": False, "use_layout_detection": True, "markdown_ignore_labels": sorted(IGNORED),
                "use_chart_recognition": record["run"]["options"].get("charts", False)}
    raw, order, prev = [], [], None
    for info in record["pages"]:
        if prev is not None and info["page"] > prev + 1:
            raw.append({"res": {"page_index": None, "page_count": None, "input_path": None, "width": 0, "height": 0,
                                "model_settings": settings, "parsing_res_list": []}})
        prev = info["page"]
        blocks = [b for b in record["blocks"] if page_of(b["id"]) == info["page"] and "added" not in b]
        order += blocks
        raw.append({"res": {"page_index": info["page"] - 1, "page_count": record["source"]["page_count"], "input_path": None,
                            "width": info["image_size"][0], "height": info["image_size"][1], "model_settings": settings,
                            "parsing_res_list": [{"block_label": b["label"], "block_content": b.get("text", ""),
                                                  "block_bbox": b["box"]} for b in blocks]}})
    pages = list(_PaddleOCRVLPipeline.restructure_pages(None, raw, merge_tables=True, relevel_titles=True))
    done = [o for res in pages for o in res["parsing_res_list"]]
    for b, o in zip(order, done):
        change = {}
        if o.global_group_id != o.global_block_id:
            change["merged_into"] = order[o.global_group_id].get("id")
        elif o.content != b.get("text", ""):
            change["text"] = o.content
        if b["label"] == "paragraph_title" and getattr(o, "title_level", None) is not None:
            change["level"] = o.title_level
        if change:
            b.setdefault("changes", []).append({"by": "auto:restructure", **change})


def refine_figures(record: dict) -> None:
    """The figures, made again: the image blocks of a page that make up one figure put together (figures.group_page,
    by the second layout model's whole-figure boxes and the captions), every other image block a figure of its own,
    then the agent's and the user's changes put back. A figure keeps its id from one processing to the next: an id
    of a figure someone changed wins, then any id it had, then its first image block's. Then each gets its caption,
    the one an agent or the user named or else one found by place (figures.pair_captions, among the captions nobody
    named), and the blocks inside its box (titles, labels: kept as the model read them, marked as the figure's)."""
    view = blocks_view({**record, "figures": []})
    charts = record["run"]["options"].get("charts", False)
    kinds = FIGURE_KINDS - ({"chart"} if charts else set())
    old = record.get("figures", [])
    kept = {f["id"]: [c for c in f.get("changes", []) if not c["by"].startswith("auto")] for f in old}
    kept = {k: v for k, v in kept.items() if v}
    seen = {f["id"] for f in old}
    made = []
    for info in record["pages"]:
        pb = [b for b in view if b["page"] == info["page"]]
        layout = None if info.get("layout") is None else [{"label": r[0], "score": r[1], "box": r[2:6]} for r in info["layout"]]
        groups = figures.group_page(pb, layout, info["image_size"][1], charts)
        grouped = {m for g in groups for m in g["members"]}
        units = [(g["members"], g["box"], g["by"]) for g in groups]
        units += [([b["id"]], b["box"], None) for b in pb
                  if b["label"] in kinds and b["box"] and "merged_into" not in b and b["id"] not in grouped]
        for members, box, by in units:
            fid = next((m for m in members if m in kept), None) or next((m for m in members if m in seen), members[0])
            auto = {"by": "auto:figures", "box": [int(v) for v in box], "members": members}
            if by:
                auto["grouped_by"] = by
            made.append({"id": fid, "changes": [auto]})
    by_id = {f["id"]: f for f in made}
    for fid, changes in kept.items():
        if fid in by_id:
            by_id[fid]["changes"] += changes
        else:
            made.append(by_id.setdefault(fid, {"id": fid, "changes": changes}))
    # A box an agent or the user drew takes the image blocks inside it, whatever ids they have now; they leave the
    # figure processing put them in.
    claimed = {}
    for f in made:
        f.pop("members", None)
        last = next((c for c in reversed(f["changes"]) if "box" in c), None)
        if f["id"] in kept and last is not None and not last["by"].startswith("auto"):
            f["members"] = covered_images(view, page_of(f["id"]), last["box"], kinds)
            claimed.update({m: f["id"] for m in f["members"]})
    for f in made:
        if "members" in f:
            continue
        auto = next((c for c in f["changes"] if c["by"].startswith("auto")), None)
        if auto is None:                                   # changed by hand, its blocks gone: nothing to show
            f["members"] = []
            continue
        left = [m for m in auto["members"] if claimed.get(m, f["id"]) == f["id"]]
        if left != auto["members"]:
            boxes = {b["id"]: b["box"] for b in view}
            auto.update(members=left, box=[int(v) for v in figures.box_union([boxes[m] for m in left])] if left else None)
        f["members"] = auto["members"]
    made = [f for f in made if fold_figure(f)["box"]]
    rank = {b["id"]: i for i, b in enumerate(view)}
    made.sort(key=lambda f: (page_of(f["id"]), min([rank.get(m, 1e9) for m in fold_figure(f)["members"]] or [1e9]),
                             fold_figure(f)["box"][1]))
    sizes = {p["page"]: tuple(p["image_size"]) for p in record["pages"]}
    text = {b["id"]: b for b in view}
    named = {f["id"]: c for f in made if not fold_figure(f)["hidden"] and (c := fold_figure(f)["caption"]) in text}
    shown = [{"id": f["id"], "page": page_of(f["id"]), "box": fold_figure(f)["box"], "image": f"imgs/{f['id']}.png",
              "members": fold_figure(f)["members"]} for f in made if not fold_figure(f)["hidden"] and f["id"] not in named]
    captions = figures.pair_captions([b for b in view if b["box"] and b["id"] not in named.values()], shown, sizes)
    captions.update(named)
    members = {m for f in made for m in fold_figure(f)["members"]}
    taken = set(captions.values()) | members
    for f in made:
        s = fold_figure(f)
        f["image"] = f"imgs/{f['id']}.png"
        f.pop("caption", None), f.pop("number", None)
        if cid := captions.get(f["id"]):
            f["caption"] = cid
            if number := conventions.figure_number(text[cid]["text"]):
                f["number"] = number
        inside = [b["id"] for b in view if b["page"] == page_of(f["id"]) and b["box"] and b["id"] not in taken
                  and b["label"] not in IGNORED and "merged_into" not in b
                  and figures.box_overlap(b["box"], s["box"]) >= figures.COVER * max(1, figures.box_area(b["box"]))]
        taken.update(inside)
        f["members"] = f.pop("members")
        f["inside"] = inside
        f["changes"] = f.pop("changes")              # key order: id, image, caption, number, members, inside, changes
    record["figures"] = made


def covered_images(view: list[dict], page: int, box: list, kinds: set) -> list[str]:
    """The image blocks of a page that lie inside a box, in reading order."""
    return [b["id"] for b in view if b["page"] == page and b["label"] in kinds and b["box"] and "merged_into" not in b
            and figures.box_overlap(b["box"], box) >= figures.COVER * max(1, figures.box_area(b["box"]))]


def strip_auto(record: dict) -> None:
    for b in record["blocks"]:
        if "changes" in b:
            b["changes"] = [c for c in b["changes"] if not c["by"].startswith("auto")]
            if not b["changes"]:
                del b["changes"]


def process(record: dict) -> None:
    """Processing from the stored models' output: the earlier auto changes go, the current code makes them again,
    the agent's and the user's changes stay after them."""
    strip_auto(record)
    agent = {b["id"]: b.pop("changes") for b in record["blocks"] if "changes" in b}
    restructure(record)
    for b in record["blocks"]:
        if b["id"] in agent:
            b["changes"] = b.get("changes", []) + agent[b["id"]]
    refine_figures(record)
    record["run"]["versions"] = versions()


def migrate(old: dict, new: dict) -> int:
    """Carry an earlier parse's edits over to a new parse of the same source, and its verdicts and figure cuts: an
    edit goes to the block with its id when that block holds the text it changed, else to the one block on its page
    that does; an edit that fits nowhere is kept in "lost" and reported as a stale_edit finding. Returns how many
    edits were carried."""
    blocks = {b["id"]: b for b in new["blocks"]}
    count = 0
    for b in old["blocks"]:
        if "added" in b:
            anchor = b["added"]["after"]
            at = next((i + 1 for i, x in enumerate(new["blocks"]) if x["id"] == anchor), None)
            if at is None:
                at = next((i for i, x in enumerate(new["blocks"]) if page_of(x["id"]) >= page_of(b["id"])), len(new["blocks"]))
            new["blocks"].insert(at, b)
            blocks[b["id"]] = b
            count += 1
            continue
        for c in b.get("changes", []):
            if c["by"].startswith("auto"):
                continue
            target = blocks.get(b["id"])
            if "was" in c and (target is None or target.get("text", "").count(c["was"]) != 1):
                hits = [x for x in new["blocks"] if page_of(x["id"]) == page_of(b["id"]) and x.get("text", "").count(c["was"]) == 1]
                target = hits[0] if len(hits) == 1 else target
            if target is None:
                new.setdefault("lost", []).append({"block": b["id"], "change": c})
                continue
            target.setdefault("changes", []).append(c)
            count += 1
    new["figures"] = [{"id": f["id"], "image": f["image"], "changes": mine} for f in old.get("figures", [])
                      if (mine := [c for c in f.get("changes", []) if not c["by"].startswith("auto")])]
    new["findings"] = [f for f in old.get("findings", []) if f.get("status") in ("ok", "unresolved")]
    return count


# ---------------------------------------------------------------- checks

def check(record: dict, src: dict | None, folder: Path) -> dict:
    """Run the text-layer checks and the figure check on the record as it is now, and keep the conclusions an agent
    or the user reached: a finding judged "ok" or "unresolved" stays so while what it reports is among what was seen
    then, and opens again when there is more. With the source at hand, the record keeps the checks' version as the
    one that made its findings. Returns what changed: {"gone", "new", "reopened"}."""
    view = blocks_view(record)
    figs = figures_view(record)
    infos = {p["page"]: p for p in record["pages"]}
    sizes = {p: tuple(i["image_size"]) for p, i in infos.items()}
    found, status = [], "ok"
    if src is None:
        # without the source nothing can be checked: the findings stay as the last check left them
        status = record.get("checks") or "skipped:no_source"
        found = [dict(f) for f in record.get("findings", []) if f["code"] != "stale_edit"]
    else:
        photo = record["run"]["options"].get("photo", False)
        layer = {p: None for p in sizes}
        if src["kind"] == "pdf" and not photo:
            layer = checks.pdf_layer(src["path"], sizes)
        # a figure's whole box keeps the text layer's words between its panels out of the text check
        boxes = [{"id": f"{f['id']}/figure", "page": f["page"], "label": "image", "text": "", "box": f["box"]} for f in figs]
        coverage, found = checks.check_document(view + boxes, layer)
        for p, c in coverage.items():
            infos[p]["coverage"] = c
        layers = text_in = None
        if src["kind"] == "pdf" and not photo:
            pdf = pdf_of(src)
            layers = {p: figures.font_chars(pdf, p, s) for p, s in sizes.items()}

            def text_in(page, box):
                pg, (w_pt, h_pt) = pdf[page - 1], pdf[page - 1].get_size()
                left, _, _, top = pg.get_cropbox()
                sx, sy = sizes[page][0] / w_pt, sizes[page][1] / h_pt
                return pg.get_textpage().get_text_bounded(left=left + box[0] / sx, bottom=top - box[3] / sy,
                                                          right=left + box[2] / sx, top=top - box[1] / sy)
        images = {}

        def image_of(page):
            if page not in images:
                images[page] = page_image(src, folder, infos[page])
            return images[page]
        layout_of = lambda p: None if infos[p].get("layout") is None else \
            [{"label": r[0], "score": r[1], "box": r[2:6]} for r in infos[p]["layout"]]
        found += figures.figure_findings(view, figs, sizes, layers, text_in, image_of, layout_of,
                                         frozenset(f["id"] for f in figs if f["settled"]),
                                         frozenset(f["id"] for f in figs if f["named"]))
    for lost in record.get("lost", []):
        c = lost["change"]
        found.append({"id": f"stale_edit@{lost['block']}", "code": "stale_edit", "page": page_of(lost["block"]),
                      "items": [c.get("was", "")], "detail": f"an edit of {lost['block']}, a block the new parse lacks: "
                      + json.dumps({k: v for k, v in c.items() if k not in ("by", "at")}, ensure_ascii=False)[:300]})
    for b in record["blocks"]:
        if stale := fold(b)["stale"]:
            found.append({"id": f"stale_edit@{b['id']}", "code": "stale_edit", "page": page_of(b["id"]), "block": b["id"],
                          "items": [c["was"] for c in stale],
                          "detail": "; ".join(f"{c['was']!r} -> {c['now']!r} no longer matches the text" for c in stale)})
    record["checks"] = status
    if src is not None:
        record["run"].setdefault("versions", {})["checks"] = checks.VERSION
    return merge_findings(record, found)


def merge_findings(record: dict, found: list[dict]) -> dict:
    """The findings of a check in place of the record's, keeping each verdict while it still covers what is
    reported; returns {"gone", "new", "reopened"}."""
    old = {f["id"]: f for f in record.get("findings", [])}
    new_ids = {f["id"] for f in found}
    moves = {"gone": sorted(i for i, f in old.items() if i not in new_ids and f.get("status") != "ok"),
             "new": [], "reopened": []}
    for f in found:
        prev = old.get(f["id"])
        f["status"] = "open"
        if prev and prev.get("status") in ("ok", "unresolved"):
            if covered(f["items"], prev.get("seen", prev["items"])):
                f.update(status=prev["status"], why=prev.get("why", ""), seen=prev.get("seen", prev["items"]))
            else:
                moves["reopened"].append(f["id"])
        elif not prev:
            moves["new"].append(f["id"])
    record["findings"] = found
    return moves


def covered(items: list, seen: list) -> bool:
    """Whether every item is among the seen ones, or part of one (a missing run that a fix shortened)."""
    return all(any(i == s or (isinstance(i, str) and isinstance(s, str) and i in s) for s in seen) for i in items)


# ---------------------------------------------------------------- Markdown (生成)
#
# The text of each block is the model's own; around it go PaddleOCR's per-label rules (markdown_format_funcs.py,
# build_handle_funcs_dict, pretty=False), so the Markdown reads as PaddleOCR writes it. Each block becomes one piece,
# and the pieces are joined with a blank line, so that every line of the Markdown is known to come from its block.

_TITLE = re.compile(r"^\s*((?:[1-9][0-9]*(?:\.[1-9][0-9]*)*[\.、]?|[\(\（](?:[1-9][0-9]*|[一二三四五六七八九十百千万亿零壹贰叁肆伍陆柒捌玖拾]+)[\)\）]"
                    r"|[一二三四五六七八九十百千万亿零壹贰叁肆伍陆柒捌玖拾]+[、\.]?|(?:I|II|III|IV|V|VI|VII|VIII|IX|X)(?:\.|\s)))(\s*)(.*)$")


def _collapse(s: str) -> str:
    return s.replace("-\n", "").replace("\n", " ")


def _title(t: str) -> str:
    if m := _TITLE.match(t):
        t = m.group(1).strip() + " " + m.group(3).lstrip()
    t = t.rstrip(".")
    return _collapse("#" * (t.count(".") + 2 if "." in t else 2) + " " + t)


def _first_line(t: str, templates: tuple, fmt, splitter: str) -> str:
    lines = t.split(splitter)
    for i, line in enumerate(lines):
        if line.strip():
            if line.lower() in templates:
                lines[i] = fmt(line)
            break
    return splitter.join(lines)


def _chart_table(t: str) -> str:
    lines = t.split("\n")
    head, rows = lines[0].split("|"), [line.split("|") for line in lines[1:]]
    html = "<table border=1 style='margin: auto; width: max-content;'>\n  <thead><tr>"
    html += "".join(f"<th style='text-align: center;'>{c.strip()}</th>" for c in head) + "</tr></thead>\n  <tbody>\n"
    for row in rows:
        html += "    <tr>" + "".join(f"<td style='text-align: center;'>{c.strip()}</td>" for c in row) + "</tr>\n"
    return html + "  </tbody>\n</table>"


def _normalize(t: str) -> str:
    return t.replace("\n\n", "\n").replace("\n", "\n\n")


FORMAT_TEXT = {
    "paragraph_title": None,          # by level: format_block
    "abstract_title": _title, "reference_title": _title, "content_title": _title,
    "doc_title": lambda t: _collapse(f"# {t}"),
    "table_title": str, "figure_title": str, "chart_title": str,
    "vision_footnote": _normalize, "text": _normalize, "ocr": _normalize, "vertical_text": _normalize,
    "reference_content": _normalize,
    "abstract": lambda t: _first_line(t, ("摘要", "abstract"), lambda l: f"## {l}\n", " "),
    "content": lambda t: t.replace("-\n", "  \n").replace("\n", "  \n"),
    "formula": str, "display_formula": str, "inline_formula": str,
    "table": lambda t: "\n\n" + t.replace("<html>", "").replace("</html>", "").replace("<body>", "").replace("</body>", ""),
    "reference": lambda t: _first_line(t, ("参考文献", "references"), lambda l: f"## {l}", "\n"),
    "algorithm": lambda t: t.strip("\n"),
    "spotting": str, "number": str, "footnote": str, "header": str, "footer": str, "aside_text": str,
}


def format_block(b: dict, options: dict) -> str:
    """A block's Markdown by PaddleOCR's rule for its label; "" for a label it does not write (formula_number)."""
    label, t = b["label"], b["text"]
    if label == "paragraph_title":
        return _title(t) if b.get("level") is None else _collapse(f"#{'#' * b['level']} {t}")
    if label == "chart" and options.get("charts"):
        return _chart_table(t)
    fmt = FORMAT_TEXT.get(label)
    return fmt(t) if fmt else ""


def piece_text(t: str) -> str:
    """A piece as it stands between blank lines: PaddleOCR collapses three newlines or more into two."""
    return re.sub(r"\n{3,}", "\n\n", t).strip("\n")


def merge_number(formula: str, number: str) -> str:
    return f"$${formula.replace('$$', '')} \\tag*{{{number}}}$$"


def page_order(pblocks: list[dict]) -> tuple[list[dict], dict]:
    """A page's blocks in Markdown order, and formula id -> its number blocks: footnotes last; each formula number
    right after the formula on its line, and a lead-in line that sits above a formula back before it. PaddleOCR
    joins a number to its formula only when it directly follows it, and its reading order sometimes slips a text
    block between them (2026-10)."""
    blocks = [b for b in pblocks if b["label"] != "footnote"] + [b for b in pblocks if b["label"] == "footnote"]
    formulas = [b for b in blocks if b["label"] in FORMULAS and b["box"]]
    owner = {}
    for n in blocks:
        if n["label"] != "formula_number" or not n["box"]:
            continue
        x1, y1, x2, y2 = n["box"]
        row = [f for f in formulas if f["box"][1] <= (y1 + y2) / 2 <= f["box"][3] and f["box"][2] <= x1 + 10]
        if row:
            owner[n["id"]] = min(row, key=lambda f: x1 - f["box"][2])["id"]
    numbers = {}
    for n in sorted((n for n in blocks if n["id"] in owner), key=lambda n: n["box"][1]):
        numbers.setdefault(owner[n["id"]], []).append(n)
    order = []
    for b in blocks:
        if b["id"] not in owner:
            order.append(b)
            order.extend(numbers.get(b["id"], []))
    i = 0
    while i < len(order):
        f = order[i]
        if f["label"] in FORMULAS and f["box"]:
            j = i + 1 + len(numbers.get(f["id"], []))
            if j < len(order) and order[j]["label"] == "text" and order[j]["box"]:
                tx1, _, tx2, ty2 = order[j]["box"]
                fx1, fy1, fx2, _ = f["box"]
                if ty2 <= fy1 and min(tx2, fx2) - max(tx1, fx1) > 0.5 * min(tx2 - tx1, fx2 - fx1):
                    order.insert(i, order.pop(j))
                    i += 1
        i += 1
    return order, numbers


def note_text(f: dict) -> str:
    quoted = f["code"] in ("missing_text", "extra_text", "foreign_script", "missing_numbers", "table_mismatch")
    text = " | ".join(f["items"]) if quoted and f["items"] else f.get("detail", "")
    text = " ".join(text.split())
    return (text[:NOTE_CHARS] + " …" if len(text) > NOTE_CHARS else text).replace("--", "–")


def fixed_note(changes: list) -> str | None:
    whys = [c.get("why", "") for c in changes if not c["by"].startswith("auto")]
    if not whys:
        return None
    joined = "; ".join(w for w in whys if w).replace("--", "–")
    return f"<!-- fixed: {joined} -->" if joined else "<!-- fixed -->"


def pieces(record: dict, layout: int = RENDER) -> list[dict]:
    """The Markdown as pieces, in order: {"kind", "text", "owners"}. Kinds: manifest, page, figure / end (the figure
    markers), image (a figure's image line), block (owners: the block, then any formula numbers joined to it), note
    (a finding's), fixed (the reason for an edit), info (a table's continuation). Every figure shown has its image
    line: with its first image block, else right after its opening marker (layout 4; layout 3 wrote none for a
    figure whose blocks hold no image)."""
    options = record["run"]["options"]
    view = blocks_view(record)
    by_id = {b["id"]: b for b in view}
    raw = {b["id"]: b for b in record["blocks"]}
    figs = [f for f in record.get("figures", []) if not fold_figure(f)["hidden"]]
    fig_of = {}
    for f in figs:
        for m in fold_figure(f)["members"] + f.get("inside", []):
            fig_of.setdefault(m, f["id"])
    continued = {}
    for b in view:
        if b["label"] == "table" and b.get("merged_into") in by_id and by_id[b["merged_into"]]["label"] == "table":
            continued.setdefault(b["merged_into"], []).append(b["page"])

    # where each open or unresolved finding's note goes: before a block, a figure, or at the top of a page
    def home(ident):
        seen = set()
        while ident in by_id and ident not in seen:
            seen.add(ident)
            b = by_id[ident]
            if ident in fig_of:
                return ("figure", fig_of[ident])
            if "merged_into" in b and b["merged_into"] in by_id:
                ident = b["merged_into"]
                continue
            if b["label"] in IGNORED or not b["text"].strip() and b["label"] not in FIGURE_KINDS:
                return ("page", b["page"])
            return ("block", ident)
        return ("page", page_of(ident)) if re.match(r"p\d+", ident or "") else ("doc", None)
    notes = {}
    for f in record.get("findings", []):
        if f["status"] == "ok":
            continue
        if f["code"] == "figure_check" and f.get("crops"):
            at = ("figure", f["crops"][0]["figure"])
        elif f.get("block"):
            at = home(f["block"])
        elif f.get("page"):
            at = ("page", f["page"])
        else:
            at = ("doc", None)
        line = f"<!-- {f['status']} {f['id']}: {note_text(f) if f['status'] == 'open' else f.get('why', '')} -->"
        notes.setdefault(at, []).append({"kind": "note", "text": line, "owners": [f["id"]]})

    out = []
    for info in record["pages"]:
        page = info["page"]
        out.append({"kind": "page", "text": f"<!-- page {page} -->", "owners": []})
        out += notes.pop(("page", page), [])
        pblocks = [b for b in view if b["page"] == page]
        order, numbers = page_order(pblocks)
        joined = {n["id"] for ns in numbers.values() for n in ns}
        # a figure's blocks go together, at its first block; one without blocks on the page goes by its box
        seq, done = [], set()
        for b in order:
            fid = fig_of.get(b["id"])
            if fid is None:
                seq.append(b)
            elif fid not in done:
                done.add(fid)
                inner = [x for x in order if fig_of.get(x["id"]) == fid]
                has_image = layout < 4 or any(x.get("figure") == fid for x in inner)
                # markers only around a figure with more than its image: text the model read in it, other panels
                bare = len(inner) == 1 and has_image and not (options.get("figure_text") and inner[0]["text"].strip())
                seq += inner if bare else [{"start": fid, "image": not has_image}, *inner, {"end": fid}]
        for f in figs:
            if page_of(f["id"]) == page and f["id"] not in done:
                box, row = fold_figure(f)["box"], figures.ROW * info["image_size"][1]
                at = next((i for i, x in enumerate(seq) if "id" in x and x["box"] and x["box"][1] >= box[1] - row
                           and min(x["box"][2], box[2]) > max(x["box"][0], box[0])), len(seq))
                seq.insert(at, {"start": f["id"], "bare": True})
        if layout >= 4:
            # a paragraph added after a figure follows it: its last line here, the end marker, its image line alone,
            # or its one block shown without markers
            here = {f["id"] for f in figs if page_of(f["id"]) == page}
            after = {x["id"]: a for x in seq if "id" in x and (a := raw.get(x["id"], {}).get("added", {}).get("after")) in here}
            if after:
                seq = [x for x in seq if x.get("id") not in after]
                for fid in dict.fromkeys(after.values()):
                    ends = [i for i, x in enumerate(seq) if fid in (x.get("end"), x.get("bare") and x.get("start"),
                                                                     fig_of.get(x.get("id")))]
                    at = ends[-1] + 1 if ends else len(seq)
                    seq[at:at] = [by_id[i] for i, a in after.items() if a == fid]
        figure = {f["id"]: f for f in figs}
        imaged, started = set(), set()
        for k, x in enumerate(seq):
            if "start" in x:
                f = figure[x["start"]]
                started.add(f["id"])
                out += notes.pop(("figure", f["id"]), [])
                if note := fixed_note(f.get("changes", [])):
                    out.append({"kind": "fixed", "text": note, "owners": [f["id"]]})
                if x.get("bare"):                          # a figure without blocks on the page: its image alone
                    out.append({"kind": "image", "text": f"![{f.get('number', '')}]({f['image']})", "owners": [f["id"]]})
                    continue
                number = f" ({f['number']})" if f.get("number") else ""
                out.append({"kind": "figure", "text": f"<!-- figure {f['id']}{number} -->", "owners": [f["id"]]})
                if x.get("image"):                         # no image block among its blocks: its image line first
                    out.append({"kind": "image", "text": f"![{f.get('number', '')}]({f['image']})", "owners": [f["id"]]})
                continue
            if "end" in x:
                out.append({"kind": "end", "text": f"<!-- end figure {x['end']} -->", "owners": [x["end"]]})
                continue
            b = x
            if b.get("figure") and b["figure"] in figure and b["figure"] not in imaged:
                imaged.add(b["figure"])
                f = figure[b["figure"]]
                if f["id"] not in started:                    # a figure without markers: its notes before its image
                    out += notes.pop(("figure", f["id"]), [])
                    if note := fixed_note(f.get("changes", [])):
                        out.append({"kind": "fixed", "text": note, "owners": [f["id"]]})
                out.append({"kind": "image", "text": f"![{f.get('number', '')}]({f['image']})", "owners": [f["id"]]})
            if b["id"] in joined or b["label"] in IGNORED or "merged_into" in b:
                continue
            if b["label"] in FIGURE_KINDS and not (b["label"] == "chart" and options.get("charts")):
                text = b["text"] if (options.get("figure_text") and b["label"] != "seal") else ""
                owners = [b["id"]]
            elif b["label"] in FORMULAS and numbers.get(b["id"]):
                ns = numbers[b["id"]]
                text = merge_number(b["text"], ", ".join(n["text"].strip() for n in ns))
                owners = [b["id"]] + [n["id"] for n in ns]
            elif b["label"] in FORMULAS and k + 1 < len(seq) and seq[k + 1].get("label") == "formula_number" \
                    and "merged_into" not in seq[k + 1]:
                n = seq[k + 1]                             # PaddleOCR joins a number that directly follows
                joined.add(n["id"])
                text, owners = merge_number(b["text"], n["text"]), [b["id"], n["id"]]
            else:
                text, owners = format_block(b, options), [b["id"]]
            text = piece_text(text)
            if not text:
                continue
            out += notes.pop(("block", b["id"]), [])
            if note := fixed_note(raw[b["id"]].get("changes", [])) if b["id"] in raw else None:
                out.append({"kind": "fixed", "text": note, "owners": [b["id"]]})
            out.append({"kind": "block", "text": text, "owners": owners})
            if b["id"] in continued:
                pages = ", ".join(str(p) for p in sorted(set(continued[b["id"]])))
                out.append({"kind": "info", "text": f"<!-- table {b['id']} continues on page {pages} -->", "owners": [b["id"]]})
        for at in [a for a in notes if a[0] in ("block", "figure") and page_of(a[1]) == page]:
            out += notes.pop(at)                           # a note whose block is not written: at the page's end
    head = notes.pop(("doc", None), []) + [n for ns in notes.values() for n in ns]
    return head + out


def manifest(record: dict, body: str, layout: int = RENDER) -> str:
    src = record["source"]
    found = record.get("findings", [])
    covered_pages = [p["coverage"] for p in record["pages"] if p.get("coverage") is not None]
    shown = figures_view(record)
    checked = [f for f in shown if f["caption"] and not f["settled"]] if record.get("checks") == "ok" else []
    name = src["file"] if re.fullmatch(r"[^\s\"]+", src["file"]) else json.dumps(src["file"], ensure_ascii=False)
    fields = [f"render={layout}", f"source={name}", f"sha256={src['sha256'][:8]}",
              f"pages={format_pages(src['pages'])}/{src['page_count']}", f"checks={record.get('checks', 'skipped:not_run')}",
              f"coverage={min(covered_pages):.2f}" if covered_pages else "coverage=none",
              f"figures={len(shown)}", f"figures_checked={len(checked)}",
              f"open={sum(f['status'] == 'open' for f in found)}", f"unresolved={sum(f['status'] == 'unresolved' for f in found)}",
              f"body={body_hash(body)}"]
    return "<!-- paddleocr " + " ".join(fields) + " -->"


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def markdown(record: dict, layout: int = RENDER) -> tuple[str, list[dict]]:
    """The Markdown in a layout, and its pieces with each one's first line (the manifest's is 0)."""
    ps = pieces(record, layout)
    for p in ps:
        if p["kind"] == "block" and "imgs/img_in_" in p["text"]:
            p["text"] = table_paths(p["text"], record)
    lines, at = [], 2
    for p in ps:
        p["line"] = at
        n = p["text"].count("\n") + 1
        lines.append(p["text"])
        at += n + 1
    body = "\n\n".join(lines) + "\n"
    return manifest(record, body, layout) + "\n\n" + body, ps


def format_pages(pages: list[int]) -> str:
    runs, start = [], pages[0]
    for prev, cur in zip(pages, pages[1:] + [None]):
        if cur != prev + 1:
            runs.append(f"{start}-{prev}" if prev > start else f"{start}")
            start = cur
    return ",".join(runs)


# ---------------------------------------------------------------- images

TABLE_IMAGE = re.compile(r"imgs/img_in_(?:image|chart|seal)_box_(\d+)_(\d+)_(\d+)_(\d+)\.jpg")


def table_images(record: dict) -> dict:
    """Images inside tables, which are no blocks: path in the model's text -> (name, page, box), named after their
    table block with a running number ("imgs/p6-14-1.png")."""
    out = {}
    for b in record["blocks"]:
        if b["label"] != "table":
            continue
        for k, m in enumerate(dict.fromkeys(TABLE_IMAGE.finditer(b.get("text", "")), None), 1):
            out.setdefault(m.group(0), (f"imgs/{b['id']}-{k}.png", page_of(b["id"]), [int(v) for v in m.groups()]))
    return out


def crop(image, box_px: list, k: float):
    h, w = image.shape[:2]
    x1, y1, x2, y2 = [int(round(v * k)) for v in box_px]
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
    return image[y1:y2, x1:x2] if x2 > x1 and y2 > y1 else None


def write_images(record: dict, src: dict, folder: Path, only: set | None = None) -> None:
    """Cut the figures (and the images inside tables) from the source at 300 dpi into imgs/, as PNG named by figure
    id; image input at its own resolution. Images no longer used go."""
    import cv2
    infos = {p["page"]: p for p in record["pages"]}
    wanted = [(f["image"], page_of(f["id"]), fold_figure(f)["box"]) for f in record.get("figures", [])
              if fold_figure(f)["box"] and not fold_figure(f)["hidden"]]
    wanted += list(table_images(record).values())
    imgdir = folder / "imgs"
    imgdir.mkdir(exist_ok=True)
    for page in sorted({p for _, p, _ in wanted}):
        todo = [(name, box) for name, p, box in wanted if p == page and (only is None or name in only)]
        if not todo:
            continue
        info = infos[page]
        if src["kind"] == "pdf" and not info.get("photo"):
            image, k = page_image(src, folder, info, CROP_DPI / 72), CROP_DPI / 72 / info["scale"]
        else:
            image, k = page_image(src, folder, info, 1.0), (1 if info.get("photo") else 1 / info["scale"])
        for name, box in todo:
            if (part := crop(image, box, k)) is not None:
                write_atomic(folder / name, cv2.imencode(".png", part)[1].tobytes())
    keep = {Path(name).name for name, _, _ in wanted}
    for old in imgdir.glob("*"):
        if old.name not in keep:
            old.unlink()


def table_paths(markdown_text: str, record: dict) -> str:
    """The images inside tables under their names in imgs/; PaddleOCR writes their tag with a stray quote, which a
    table merged across pages carries on as '"=""'."""
    for path, (name, _, _) in table_images(record).items():
        markdown_text = markdown_text.replace(f'<img src="{path}" alt="Image"" />', f'<img src="{name}" alt="Image" />')
        markdown_text = markdown_text.replace(path, name)
    return markdown_text.replace('<img "="" ', "<img ")


# ---------------------------------------------------------------- commit: Markdown edits -> changes

PROTECTED = re.compile(r"<!-- (page \d+|figure \S+( \(.*\))?|end figure \S+) -->")
NOTE = re.compile(r"<!-- (open|ok|unresolved) (\S+?)(?::\s?(.*?))? -->")
FIXED = re.compile(r"<!-- fixed(?::\s?(.*?))? -->")
INFO = re.compile(r"<!-- table \S+ continues on page [\d, ]+ -->")
IMAGE_LINE = re.compile(r"!\[[^\]]*\]\((imgs/[^)]+)\)")


def render_text(record: dict, layout: int = RENDER) -> tuple[str, list[dict]]:
    return markdown(record, layout)


def edited(folder: Path, record: dict) -> bool:
    """Whether the Markdown holds edits the record does not: its body no longer matches the hash on its first line."""
    md_path = paths(folder)[1]
    if not md_path.exists():
        return False
    text = md_path.read_text(encoding="utf-8")
    first, _, body = text.partition("\n\n")
    m = re.search(r"\bbody=(\w+)", first)
    return not (m and m.group(1) == body_hash(body))


def edit_of(old: str, new: str) -> tuple[str, str]:
    """The smallest change from old to new as (was, now), widened to whole words (letters, digits and . - _ ', so
    that "0.91" and "DeepSeek-RI" stay whole inside HTML or LaTeX) and then until `was` occurs once in old."""
    word = lambda ch: ch.isalnum() or ch in "._-'"
    p = 0
    while p < min(len(old), len(new)) and old[p] == new[p]:
        p += 1
    s = 0
    while s < min(len(old), len(new)) - p and old[-1 - s] == new[-1 - s]:
        s += 1
    a, b = p, len(old) - s
    while a > 0 and word(old[a - 1]) and (a == b or word(old[a]) or a == p):
        a -= 1
    while b < len(old) and word(old[b]) and (b == a or word(old[b - 1]) or b == len(old) - s):
        b += 1
    while (old.count(old[a:b]) != 1 or not old[a:b].strip()) and (a > 0 or b < len(old)):
        a, b = max(0, a - 1), min(len(old), b + 1)
        while a > 0 and word(old[a - 1]):
            a -= 1
        while b < len(old) and word(old[b]):
            b += 1
    return old[a:b], new[a:len(new) - (len(old) - b)]


def content_of(label: str, piece: str, level) -> tuple[str, object, str]:
    """A block's text, heading level and label back from its piece of Markdown: PaddleOCR's rules undone. A heading
    whose piece no longer opens with # is body text."""
    if label in ("paragraph_title", "abstract_title", "reference_title", "content_title", "doc_title"):
        m = re.match(r"(#+)\s*", piece)
        if m:
            return piece[m.end():], (len(m.group(1)) - 1 if label == "paragraph_title" else level), label
        return piece, None, "text"
    if label == "abstract":
        return re.sub(r"## (摘要|abstract)\n", r"\1", piece, count=1, flags=re.I), level, label
    if label == "reference":
        return re.sub(r"^## (参考文献|references)$", r"\1", piece, count=1, flags=re.I | re.M), level, label
    if label == "content":
        return piece.replace("  \n", "\n"), level, label
    return piece, level, label


def paragraphs(text: str) -> int:
    return len([s for s in re.split(r"\n\s*\n", text) if s.strip()])


def refused(detail: str, hint: str) -> Stop:
    """An edit commit cannot take: where (detail) and what to do (hint); nothing is recorded."""
    return Stop("edit_refused", detail=detail, hint=f"{hint} Nothing was recorded.")


def commit(record: dict, text: str) -> list[str]:
    """Record the edits made to the Markdown `text` as changes, in place; returns one line per change made.
    Raises edit_refused when an edit cannot be taken (a protected line changed, an image line edited, ...). The
    text is compared with the Markdown generated in the layout its first line names (render=N)."""
    layout = int(m.group(1)) if (m := re.match(r"<!-- paddleocr render=(\d+) ", text)) else RENDER
    gen, ps = render_text(record, layout)
    if text == gen:
        return []
    raw = {b["id"]: b for b in record["blocks"]}
    figs = {f["id"]: f for f in record.get("figures", [])}
    view = {b["id"]: b for b in blocks_view(record)}
    log = []

    # Notes first: a finding's verdict, and the reasons for edits; then they leave both sides.
    cur = text.split("\n")
    if not cur or not cur[0].startswith("<!-- paddleocr "):
        raise refused("the first line of the Markdown (<!-- paddleocr ... -->) is gone", "Restore it as it was.")
    findings = {f["id"]: f for f in record.get("findings", [])}
    verdict, why_at, body = {}, {}, []
    pending = []
    for line in cur[1:]:
        s = line.strip()
        if m := NOTE.fullmatch(s):
            verdict[m.group(2)] = (m.group(1), (m.group(3) or "").strip())
        elif m := FIXED.fullmatch(s):
            pending.append((m.group(1) or "").strip())
        elif INFO.fullmatch(s):
            continue
        else:
            if s and pending:
                why_at[len(body)] = pending
                pending = []
            body.append(line)
    for fid, (status, why) in verdict.items():
        f = findings.get(fid)
        if f and status != f["status"]:
            f["status"] = status
            if status == "open":
                f.pop("why", None), f.pop("seen", None)
            else:
                f.update(why="" if why == note_text(f) else why, seen=f["items"])
            log.append(f"{fid}: {status}" + (f" ({f['why']})" if f.get("why") else ""))

    # The generated lines, each with its piece; notes and info lines left out as above.
    glines, owner = [], []
    for k, p in enumerate(ps):
        if p["kind"] in ("note", "fixed", "info", "manifest"):
            continue
        if glines:
            glines.append("")
            owner.append(None)
        for line in p["text"].split("\n"):
            glines.append(line)
            owner.append(k)
    while body and not body[0].strip():
        body.pop(0)
        why_at = {i - 1: w for i, w in why_at.items()}
    keep = [i for i, line in enumerate(glines) if PROTECTED.fullmatch(line.strip())]
    have = [i for i, line in enumerate(body) if PROTECTED.fullmatch(line.strip())]
    if [glines[i].strip() for i in keep] != [body[i].strip() for i in have]:
        want = [glines[i].strip() for i in keep]
        got = [body[i].strip() for i in have]
        first = next((a for a, b in zip(want, got) if a != b), (want + got)[min(len(want), len(got))] if want != got else "")
        raise refused(f"a page or figure marker was changed, moved or removed (first difference at {first!r})",
                      "Put the markers back as they were; to hide a figure, delete only its image line.")

    # Regions between protected lines line up one to one. Each is diffed by its non-blank lines, so that blank lines
    # left where notes were taken out never pair lines wrongly; an edit takes in the whole pieces it touches.
    edits, inserts = {}, []
    bounds = list(zip([-1] + keep, keep + [len(glines)])), list(zip([-1] + have, have + [len(body)]))
    page = None
    for (g0, g1), (c0, c1) in zip(*bounds):
        if g0 >= 0 and (m := re.fullmatch(r"<!-- page (\d+) -->", glines[g0].strip())):
            page = int(m.group(1))
        g, c, go = glines[g0 + 1:g1], body[c0 + 1:c1], owner[g0 + 1:g1]
        gi = [i for i, line in enumerate(g) if line.strip()]
        ci = [j for j, line in enumerate(c) if line.strip()]
        ops = difflib.SequenceMatcher(None, [g[i] for i in gi], [c[j] for j in ci], autojunk=False).get_opcodes()
        # Lines that stayed anchor the edits between them; so do replaced lines when as many came back as went, one
        # for one, so that edits to neighbouring paragraphs stay each with its own block.
        gmap, paired = {}, set()
        for tag, i1, i2, j1, j2 in ops:
            if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
                gmap.update({gi[i1 + d]: ci[j1 + d] for d in range(i2 - i1)})
                if tag == "replace":
                    paired.add((i1, i2))
        parent = {}

        def find(x):
            while parent.setdefault(x, x) != x:
                x = parent[x]
            return x
        for tag, i1, i2, j1, j2 in ops:
            if tag == "equal":
                continue
            if (i1, i2) in paired:
                for i in range(i1, i2):
                    find(go[gi[i]])
                continue
            touched = sorted({go[gi[i]] for i in range(i1, i2) if go[gi[i]] is not None})
            if not touched:
                # lines where no piece was: part of the paragraph they touch, else a block of their own (an image
                # line is no paragraph: text against it is a block of its own)
                first, last = ci[j1], ci[j2 - 1]
                prev_g, next_g = (gi[i1 - 1] if i1 > 0 else None), (gi[i1] if i1 < len(gi) else None)
                paragraph = lambda x: x is not None and go[x] is not None and ps[go[x]]["kind"] == "block"
                if first > 0 and c[first - 1].strip() and paragraph(prev_g):
                    touched = [go[prev_g]]
                elif last + 1 < len(c) and c[last + 1].strip() and paragraph(next_g):
                    touched = [go[next_g]]
                else:
                    # a block of their own per paragraph, each with the reason written above it, after the piece
                    # before them: in this region, else the page or figure marker that opens it
                    before = next((go[gi[i]] for i in range(i1 - 1, -1, -1) if go[gi[i]] is not None),
                                  owner[g0] if g0 >= 0 else None)
                    start = None
                    for j in range(first, last + 2):
                        if j <= last and c[j].strip():
                            start = j if start is None else start
                        elif start is not None:
                            inserts.append((page, before, "\n".join(c[start:j]), why_at.get(c0 + 1 + start, [])))
                            start = None
                    continue
            for k in touched[1:]:
                parent[find(k)] = find(touched[0])
            find(touched[0])
        groups = {}
        for k in parent:
            groups.setdefault(find(k), []).append(k)
        for ks in groups.values():
            ks.sort()
            lines_of = [i for i in range(len(g)) if go[i] in ks]
            before = max((i for i in gmap if i < min(lines_of)), default=None)
            after = min((i for i in gmap if i > max(lines_of)), default=None)
            a = gmap[before] + 1 if before is not None else 0
            b = gmap[after] if after is not None else len(c)
            while a < b and not c[a].strip():
                a += 1
            while b > a and not c[b - 1].strip():
                b -= 1
            whys = [w for j in range(c0 + 1 + a, c0 + 1 + max(a + 1, b)) for w in why_at.get(j, [])]
            edits[tuple(ks)] = ("\n".join(c[a:b]), whys)

    if any(IMAGE_LINE.search(new) for _, _, new, _ in inserts):
        raise refused("an image line was added, or a paragraph moved across one (which reads the same)",
                      "Cut figures with ocr.py cut. To move a paragraph past an image line, delete it and commit, then "
                      "write it in its new place and commit again.")
    for ks, (new, whys) in edits.items():
        group = [ps[k] for k in ks]
        for p in (p for p in group if p["kind"] == "image"):
            fid = p["owners"][0]
            if p["text"] in new.split("\n"):
                new = "\n".join(line for line in new.split("\n") if line != p["text"]).strip("\n")
            elif IMAGE_LINE.search(new):
                raise refused(f"the image line of figure {fid} was edited", "Cut figures with ocr.py cut.")
            else:
                figs[fid].setdefault("changes", []).append({"by": "agent", "at": now(), "hidden": True,
                                                            "why": "; ".join(w for w in whys if w)})
                log.append(f"{fid}: figure hidden (its image line was deleted); bring it back with ocr.py cut")
        group = [p for p in group if p["kind"] == "block"]
        if not group:
            if new.strip():
                fid = next(p["owners"][0] for p in (ps[k] for k in ks) if p["kind"] == "image")
                raise refused(f"text was written in the place of the image line of figure {fid}",
                              "Keep the image line, or delete it alone to hide the figure, and write the text as a "
                              "paragraph of its own, with blank lines around it.")
            continue
        if IMAGE_LINE.search(new) and not any(IMAGE_LINE.search(p["text"]) for p in group):
            raise refused("an image line was added", "Cut figures with ocr.py cut.")
        first, rest = group[0]["owners"][0], [o for p in group for o in p["owners"]][1:]
        had, has = sum(paragraphs(p["text"]) for p in group), paragraphs(new)
        if has > had:
            # a block edited and a paragraph added beside it, in one go: which paragraph is the block cannot be told
            who, its = ", ".join(p["owners"][0] for p in group), "its" if len(group) == 1 else "their"
            raise refused(f"the edit of {who} turns {had} paragraph{'s' * (had > 1)} into {has}, and which of them "
                          f"{who} should hold cannot be told",
                          f"Commit {who} with only {its} own text first, then add the new paragraphs between blank "
                          "lines and commit again.")
        why = new_why(whys, raw[first].get("changes", []))
        b = view[first]
        if not new.strip():
            for o in [first] + rest:
                raw[o].setdefault("changes", []).append({"by": "agent", "at": now(), "deleted": True, "why": why})
                log.append(f"{o}: deleted")
            continue
        # The edit as it shows in the Markdown, when the block's text holds what it changed exactly once; else the
        # block's text rebuilt from its piece by undoing PaddleOCR's rule.
        was, now_ = edit_of(group[0]["text"], new) if len(group) == 1 else ("", "")
        label = b["label"]
        if was and b["text"].count(was) == 1:
            text, level, rest = b["text"].replace(was, now_), b["level"], []
        elif len(group) == 1 and len(group[0]["owners"]) > 1:
            # a formula with its numbers joined: they stay while their \tag stands as written
            tag = re.search(r" \\tag\*\{[^}]*\}\$\$$", group[0]["text"])
            if tag and new.endswith(tag.group(0)) and new.startswith("$$"):
                text, level, rest = "$$" + new[2:-len(tag.group(0))] + "$$", b["level"], []
            else:
                text, level = new, b["level"]
        else:
            text, level, label = content_of(b["label"], new, b["level"])
        change = {"by": "agent", "at": now()}
        if text != b["text"]:
            was, now_ = edit_of(b["text"], text)
            change.update(was=was, now=now_)
        if label != b["label"]:
            change["label"] = label
        if level != b["level"]:
            change["level"] = level
        if len(change) > 2:
            change["why"] = why
            raw[first].setdefault("changes", []).append(change)
            log.append(f"{first}: " + (f"{change['was'][:60]!r} -> {change['now'][:60]!r}" if "was" in change
                                       else f"now {label}" if "label" in change else f"level {level}"))
        for o in rest:
            raw[o].setdefault("changes", []).append({"by": "agent", "at": now(), "deleted": True, "why": why})
            log.append(f"{o}: deleted, its text now in {first}")

    for page, before, new, whys in inserts:
        # after the block above it, or after the figure whose image line or marker is above it, else first on the page
        kind = ps[before]["kind"] if before is not None else "page"
        anchor = ps[before]["owners"][0] if kind in ("block", "image", "figure", "end") else f"p{page}"
        label, text, level = "text", new, None
        if new.lstrip().startswith("<table"):
            label = "table"
        elif new.startswith("$$"):
            label = "display_formula"
        elif m := re.match(r"(#+)\s+", new):
            label, text, level = "paragraph_title", new[m.end():], len(m.group(1)) - 1
        block = {"id": new_id(record, page, "n"), "label": label,
                 "added": {"by": "agent", "at": now(), "after": anchor, "why": "; ".join(w for w in whys if w)}, "text": text}
        if level is not None:
            block["changes"] = [{"by": "agent", "level": level}]
        at = next((i + 1 for i, b in enumerate(record["blocks"]) if b["id"] == anchor), None)
        if at is None:
            at = next((i for i, b in enumerate(record["blocks"]) if page_of(b["id"]) >= page), len(record["blocks"]))
        while at < len(record["blocks"]) and record["blocks"][at].get("added", {}).get("after") == anchor:
            at += 1
        record["blocks"].insert(at, block)
        log.append(f"{block['id']}: new {label} after {anchor}")
    return log


def new_id(record: dict, page: int, kind: str) -> str:
    """The id of a new block (kind "n": p3-n1) or of a new figure cut on a page (kind "cut": p3-cut1): one past the
    highest such id that any block or figure of the page holds, so that a block and a figure never share an id."""
    pattern = re.compile(rf"p{page}-{kind}(\d+)")
    held = [int(m.group(1)) for x in record["blocks"] + record.get("figures", []) if (m := pattern.fullmatch(x["id"]))]
    return f"p{page}-{kind}{1 + max(held + [0])}"


def new_why(whys: list[str], changes: list) -> str:
    """The reason written above an edit, without the reasons the block's fixed note already gave."""
    old = fixed_note(changes)
    old = (FIXED.fullmatch(old).group(1) or "") if old else ""
    out = []
    for w in whys:
        if old and w.startswith(old):
            w = w[len(old):].lstrip("; ")
        if w:
            out.append(w)
    return "; ".join(out)


# ---------------------------------------------------------------- commands

def build(record: dict, src: dict | None, folder: Path, refine: bool = True) -> dict:
    """Process (unless refine is False), check, cut the images and write the record and the Markdown."""
    if refine:
        process(record)
    moves = check(record, src, folder)
    if src is not None:
        write_images(record, src, folder)
    text, _ = render_text(record)
    save(folder, record, text)
    return moves


def settle_edits(folder: Path, record: dict, src: dict | None) -> dict:
    """Commit the Markdown's edits the record does not hold yet -> the line's fields: recorded (a sentence per
    change), gone, new, reopened (finding ids), each only when not empty."""
    if not edited(folder, record):
        return {}
    recorded = commit(record, paths(folder)[1].read_text(encoding="utf-8"))
    moves = check(record, src, folder)
    text, _ = render_text(record)
    save(folder, record, text)
    return tally({"recorded": recorded}, moves)


def tally(fields: dict, *more: dict) -> dict:
    """recorded, gone, new, reopened gathered from several steps, in order, each only when not empty."""
    out = {}
    for part in (fields, *more):
        for key in ("recorded", "gone", "new", "reopened"):
            out.setdefault(key, []).extend(x for x in part.get(key, []) if x not in out[key])
    return {k: v for k, v in out.items() if v}


def summary(record: dict) -> dict:
    """What a parse holds: pages, blocks by label, figures, the lowest page coverage, how it was checked, and the
    findings open and judged unresolved."""
    counts = {}
    for b in record["blocks"]:
        counts[b["label"]] = counts.get(b["label"], 0) + 1
    covered = [p["coverage"] for p in record["pages"] if p.get("coverage") is not None]
    found = record.get("findings", [])
    return {"pages": len(record["pages"]), "blocks": counts, "figures": len(record.get("figures", [])),
            "min_coverage": round(min(covered), 3) if covered else None, "checks": record.get("checks"),
            "open": [f["id"] for f in found if f["status"] == "open"],
            "unresolved": [f["id"] for f in found if f["status"] == "unresolved"]}


def finding_rows(record: dict, every: bool = False) -> list[dict]:
    """The findings open, then those judged unresolved (every: then those judged ok): {id, status, page, note}; note
    is the open note's text, or the verdict's reason."""
    found = record.get("findings", [])
    return [{"id": f["id"], "status": status, "page": f.get("page"),
             "note": note_text(f) if status == "open" else f.get("why", "")}
            for status in ("open", "unresolved", "ok")[:3 if every else 2] for f in found if f["status"] == status]


def not_parsed(page: int) -> Stop:
    return Stop("not_found", detail=f"page {page} was not parsed",
                hint="The Markdown's first line lists the pages parsed (pages=).")


def media_box(page, src: dict, number: int):
    """The MediaBox, including one inherited from /Pages that PDFium's box getter cannot read."""
    box = page.get_mediabox(fallback_ok=False)
    if box is not None:
        return box
    try:
        info = subprocess.run(["pdfinfo", "-f", str(number), "-l", str(number), "-box", str(src["path"])],
                              capture_output=True, text=True, check=True, env={**os.environ, "LC_ALL": "C"})
        line = next(line for line in info.stdout.splitlines() if "MediaBox:" in line)
        return tuple(float(v) for v in line.split("MediaBox:", 1)[1].split())
    except (OSError, subprocess.CalledProcessError, StopIteration, ValueError):
        cli.log("[paddleocr] pdfinfo could not read the inherited MediaBox; no pdftotext region command is shown. "
                "Check the region in the page image below.")
        return None


def show(folder: Path, record: dict, src: dict | None, what: str, box=None, dpi: int = 300) -> list[str]:
    """What show prints; images go to a scratch folder named in the output."""
    import cv2
    infos = {p["page"]: p for p in record["pages"]}
    scratch = Path(tempfile.gettempdir()) / "paddleocr-show" / f"{folder.name}-{record['source']['sha256'][:8]}"
    scratch.mkdir(parents=True, exist_ok=True)
    view = {b["id"]: b for b in blocks_view(record)}
    figs = {f["id"]: f for f in figures_view(record)}
    raw = {b["id"]: b for b in record["blocks"]}
    found = {f["id"]: f for f in record.get("findings", [])}
    out = []
    if m := re.fullmatch(r"p(\d+)", what):
        page = int(m.group(1))
        if page not in infos:
            raise not_parsed(page)
        info = infos[page]
        if box:
            if src is None:
                raise Stop("source_not_found", hint="A crop is cut from the source: give it with --source FILE.")
            ebox = to_engine(info, box)
            image, k = (page_image(src, folder, info, dpi / 72), dpi / 72 / info["scale"]) if src["kind"] == "pdf" and not info.get("photo") \
                else (page_image(src, folder, info, 1.0), 1 if info.get("photo") else 1 / info["scale"])
            part = crop(image, ebox, k)
            if part is None:
                raise bad_box(box, page)
            path = scratch / f"p{page}_{'_'.join(str(int(v)) for v in box)}_{dpi}dpi.png"
            cv2.imwrite(str(path), part)
            return [f"crop: {path}"]
        out.append(f"page {page}: {len([b for b in view.values() if b['page'] == page])} blocks; boxes in source units")
        for b in record["blocks"]:
            if page_of(b["id"]) != page:
                continue
            s = fold(b)
            flags = [x for x, on in (("deleted", s["deleted"]), (f"merged into {s['merged_into'] or b.get('group')}", s["merged_into"] or b.get("group")),
                                     ("changed", any(not c["by"].startswith("auto") for c in b.get("changes", []))),
                                     (f"in figure {view.get(b['id'], {}).get('figure')}", view.get(b["id"], {}).get("figure"))) if on]
            box_s = to_source(info, b["box"]) if b.get("box") else None
            out.append(f"{b['id']:9} {s['label']:17} {box_s} {' '.join(s['text'].split())[:70]!r} {', '.join(flags)}")
        for f in figs.values():
            if f["page"] == page:
                out.append(f"figure {f['id']} {f['number'] or ''} box {to_source(info, f['box'])} {f['image']}")
        if src is not None:
            image = page_image(src, folder, info)
            path = scratch / f"p{page}.png"
            for b in view.values():
                if b["page"] == page and b["box"]:
                    x1, y1, x2, y2 = [int(v) for v in b["box"]]
                    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 230), 2)
                    cv2.putText(image, b["id"].split("-", 1)[1], (x1, max(12, y1 - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 230), 1)
            cv2.imwrite(str(path), image)
            out.append(f"page image with block ids: {path}")
        return out
    finding = found.get(what)
    ident = (finding.get("block") or (finding["crops"][0]["figure"] if finding.get("crops") else None)) if finding else what
    if finding:
        out.append(f"{finding['id']} [{finding['status']}] {finding.get('detail', '')}")
        if finding["items"]:
            out.append("items: " + " | ".join(str(i) for i in finding["items"]))
        if finding.get("why"):
            out.append(f"why: {finding['why']}")
        if finding["code"] == "figure_check":
            return out + figure_check_view(folder, record, src, finding, scratch)
        if ident is None:
            return out
    if ident in figs or ident in {f["id"] for f in record.get("figures", [])}:
        f = next(f for f in record["figures"] if f["id"] == ident)
        s, info = fold_figure(f), infos[page_of(ident)]
        out.append(f"figure {ident} {f.get('number', '')}: box {to_source(info, s['box']) if s['box'] else None}, image "
                   f"{folder / f['image']}{' (hidden)' if s['hidden'] else ''}")
        out.append(f"members {s['members']}; inside {f.get('inside', [])}; caption {f.get('caption')}")
        for c in f.get("changes", []):
            out.append(f"change {json.dumps({k: (to_source(info, v) if k == 'box' else v) for k, v in c.items()}, ensure_ascii=False)}")
        if src is not None:
            image = page_image(src, folder, info)
            if finding and finding["code"] == "figure_check":
                cap = view.get(finding["block"])
                path = scratch / f"{finding['id'].replace('@', '_')}.png"
                figures.draw_overlay(image, finding, [x for x in figs.values() if x["page"] == info["page"]], cap, path)
            else:
                path = scratch / f"{ident}.png"
                x1, y1, x2, y2 = [int(v) for v in s["box"]]
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 230), 3)
                cv2.imwrite(str(path), image)
            out.append(f"overlay: {path}")
        return out
    if ident not in raw:
        if finding and finding.get("page"):
            return out + show(folder, record, src, f"p{finding['page']}")
        raise Stop("not_found", detail=f"{what} is no finding, block, figure or page of this parse",
                   hint="ocr.py findings DIR lists the findings; ocr.py show DIR p<N> lists a page's blocks and figures.")
    b, s = raw[ident], fold(raw[ident])
    info = infos[page_of(ident)]
    out.append(f"block {ident} {s['label']} box {to_source(info, b['box']) if b.get('box') else None}"
               + (" (deleted)" if s["deleted"] else ""))
    for c in b.get("changes", []):
        out.append(f"change {json.dumps(c, ensure_ascii=False)}")
    out.append("text:")
    out.append(s["text"])
    if b.get("box") and src is not None:
        x1, y1, x2, y2 = to_source(info, b["box"])
        if src["kind"] == "pdf" and not info.get("photo"):
            x, y, w, h = int(x1) - 4, int(y1) - 4, int(x2 - x1) + 8, int(y2 - y1) + 8
            pdf = pdf_of(src)
            pg = pdf[info["page"] - 1]
            left, bottom, right, top = pg.get_bbox()
            media = media_box(pg, src, info["page"])
            if media is not None:
                ml, mb, mr, mt = media
                dl, db, dr, dt = left - ml, bottom - mb, mr - right, mt - top
                dx, dy = ((dl, dt), (db, dl), (dr, db), (dt, dr))[pg.get_rotation() // 90]
                px, py = int(x1 + dx) - 4, int(y1 + dy) - 4
                out.append(f"text layer (pdftotext -layout -f {info['page']} -l {info['page']} -x {px} -y {py} "
                           f"-W {w} -H {h}):")
            else:
                out.append("text layer:")
            out.append(pg.get_textpage().get_text_bounded(left=left + x, bottom=top - (y + h), right=left + x + w, top=top - y)
                       or "(none)")
        image = page_image(src, folder, info)
        bx = [int(v) for v in b["box"]]
        cv2.rectangle(image, (bx[0], bx[1]), (bx[2], bx[3]), (0, 0, 230), 3)
        path = scratch / f"{ident}.png"
        cv2.imwrite(str(path), image)
        out.append(f"page image with the block boxed: {path}")
    return out


def figure_check_view(folder: Path, record: dict, src: dict | None, finding: dict, scratch: Path) -> list[str]:
    """A figure_check finding in detail: its crops and the second opinion in source units, the caption, an overlay."""
    infos = {p["page"]: p for p in record["pages"]}
    view = {b["id"]: b for b in blocks_view(record)}
    caption = view.get(finding["block"])
    info = infos[finding["page"]]
    out = []
    for c in finding.get("crops", []):
        out.append(f"crop {c['n']}: figure {c['figure']} on page {c['page']}, box {to_source(infos[c['page']], c['box'])}")
    if s := finding.get("second_opinion"):
        out.append(f"second opinion (the figure grown out from its caption): box {to_source(info, s)}")
    if caption:
        out.append(f"caption {caption['id']}, box {to_source(info, caption['box'])}: {' '.join(caption['text'].split())[:160]}")
    if src is not None:
        page = finding["crops"][0]["page"] if finding.get("crops") else finding["page"]
        image = page_image(src, folder, infos[page])
        path = scratch / f"{finding['id'].replace('@', '_')}.png"
        figures.draw_overlay(image, finding, [f for f in figures_view(record) if f["page"] == page],
                             caption if page == finding["page"] else None, path)
        out.append(f"overlay: {path} (caption blue, crops numbered, second opinion green dashed)")
    return out


def bad_box(box: list, page: int) -> Stop:
    return Stop("bad_box", exit=cli.CANNOT, detail=f"the box {box} lies outside page {page} or is too small",
                hint=f"Boxes are in source units, from the page's top left (ocr.py show -h); ocr.py show DIR p{page} "
                     "gives the boxes of the page's blocks.")


def set_figure(record: dict, ident: str | None, page: int | None, box: list | None, why: str,
               caption: str | None = None) -> str:
    """An agent's box for a figure, or a new figure (id p<page>-cut<k>) for one the parse lacks, and the block that is
    its caption when the agent names one (box None: the caption alone); returns its id."""
    infos = {p["page"]: p for p in record["pages"]}
    if caption and caption not in {b["id"] for b in blocks_view(record)}:
        raise Stop("not_found", detail=f"no block {caption} to be the caption",
                   hint="ocr.py show DIR p<N> lists a page's blocks. A caption the parse lost: write it into the "
                        "Markdown as a paragraph of its own, commit, and name the block id commit's line gives it.")
    if ident:
        fig = next((f for f in record.get("figures", []) if f["id"] == ident), None)
        if fig is None:
            on = re.match(r"p\d+", ident)
            hint = (f"{ident} is no figure; a new one on its page: ocr.py cut DIR {on.group(0)} --box X1,Y1,X2,Y2."
                    if any(b["id"] == ident for b in record["blocks"]) else
                    "ocr.py show DIR p<N> lists a page's figures; ocr.py cut DIR p<N> --box ... makes a new one.")
            raise Stop("not_found", detail=f"no figure {ident}", hint=hint)
        page = page_of(ident)
    elif page not in infos:
        raise not_parsed(page)
    change = {"by": "agent", "at": now()}
    if box is not None:
        info = infos[page]
        w, h = info["image_size"]
        x1, y1, x2, y2 = to_engine(info, box)
        ebox = [max(0, x1), max(0, y1), min(w, x2), min(h, y2)]
        if ebox[2] - ebox[0] < 4 or ebox[3] - ebox[1] < 4:
            raise bad_box(box, page)
        kinds = FIGURE_KINDS - ({"chart"} if record["run"]["options"].get("charts") else set())
        change.update(box=ebox, members=covered_images(blocks_view({**record, "figures": []}), page, ebox, kinds))
    if caption:
        change["caption"] = caption
    if not ident:
        ident = new_id(record, page, "cut")
        fig = {"id": ident, "image": f"imgs/{ident}.png", "changes": []}
        record.setdefault("figures", []).append(fig)
    fig.setdefault("changes", []).append({**change, "why": why})
    return ident


# ---------------------------------------------------------------- objects: what a note can link to in the PDF

PREFIX = {"": "", "supplementary": "S", "extended data": "ED"}


def object_key(kind: str, words: str, number: str) -> str:
    """fig:3, fig:S2 (Supplementary), table:ED1 (Extended Data); a number that already carries its prefix
    (Supplementary Fig. S2) carries it once."""
    prefix = PREFIX.get(words, "")
    return f"{kind}:{number if number.startswith(prefix) else prefix + number}"


def objects(record: dict, src: dict) -> list[dict]:
    """The figures and tables of the objects command, in page order."""
    if src["kind"] != "pdf":
        raise Stop("not_a_pdf", hint="objects places figures and tables in a PDF; this parse was made from images.")
    found = {}
    for f in figures_view(record):
        # the pieces of one figure, cut apart under one caption, are one object
        o = found.setdefault(("figure", f["caption"] or f["id"]), {"id": f["id"], "kind": "figure", "number": f["number"],
                                                       "page": f["page"], "boxes": []})
        o["boxes"].append(f["box"])
    for b in blocks_view(record):
        if figures.is_table_caption(b):
            m = conventions.TABLE_CAPTION.match(b["text"])
            found[("table", b["id"])] = {"id": b["id"], "kind": "table", "number": " ".join(b["text"][m.start(2):m.end()].split()),
                              "page": b["page"], "boxes": [b["box"]]}
    for o in found.values():
        kind, named = ("fig", conventions.figure_id) if o["kind"] == "figure" else ("table", conventions.table_id)
        o["key"] = object_key(kind, *named({"text": o["number"]})) if o["number"] else None
    keys = [o["key"] for o in found.values()]
    pdf, infos, out = pdf_of(src), {p["page"]: p for p in record["pages"]}, []
    for o in sorted(found.values(), key=lambda o: (o["page"], min(b[1] for b in o["boxes"]))):
        info, page = infos[o["page"]], pdf[o["page"] - 1]
        rect = top = None
        if not info.get("photo") and not page.get_rotation():
            x1, y1, x2, y2 = to_source(info, figures.box_union(o["boxes"]))
            left, _, _, ptop = page.get_cropbox()
            rect, top = [round(left + x1, 2), round(ptop - y2, 2), round(left + x2, 2), round(ptop - y1, 2)], y1
        out.append({"id": o["id"], "kind": o["kind"], "key": o["key"] if keys.count(o["key"]) == 1 else None,
                    "number": o["number"], "page": o["page"],
                    "page_label": pdf.get_page_label(o["page"] - 1) or str(o["page"]), "rect": rect, "top": top})
    return out


# ---------------------------------------------------------------- the commands: ocr.py's words but parse

def command(name: str, doc: str, argv: list, configure=None, source: bool = True):
    """The parser of a command on one parse folder: DIR, --source unless `source` is False, then the command's own
    arguments -> (parser, args, the folder resolved)."""
    p = cli.parser(doc, sub=name)
    p.add_argument("folder", metavar="DIR", help="the parse's folder, <outdir>/<stem>")
    if source:
        p.add_argument("--source", metavar="FILE",
                       help="the PDF or page images the parse was made from, when they are neither at the record's "
                            "path nor beside the folder")
    if configure:
        configure(p)
    for i, a in enumerate(argv):          # --box X1 Y1 X2 Y2, four values: the box as one value is the way
        if len(a) > 2 and "--box".startswith(a) and len(argv) > i + 4 and all(map(is_number, argv[i + 1:i + 5])):
            p.error("--box takes one value", hint=f"Write the box as one value: --box {','.join(argv[i + 1:i + 5])}.")
    args = cli.parse(p, argv)
    return p, args, Path(args.folder).expanduser().resolve()


def is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def box_value(text: str) -> list[float]:
    values = text.split(",")
    if len(values) != 4 or not all(map(is_number, values)):
        raise argparse.ArgumentTypeError(f"{text!r}: a box is four numbers in one value, X1,Y1,X2,Y2")
    return [float(v) for v in values]


def warn_unrecorded(folder: Path, record: dict) -> None:
    """A read-only command: the Markdown's edits that commit has not recorded are not in what it reads; a record that
    older code processed or checked holds findings and figures the current code may not make."""
    if edited(folder, record):
        cli.log(f"[paddleocr] the Markdown holds edits not committed yet, left out here; "
                f"{cli.prog('commit')} {folder} records them")
    had = record["run"].get("versions") or {}
    if older := [f"{k} {had.get(k)}, now {v}" for k, v in versions().items() if had.get(k) != v]:
        cli.log(f"[paddleocr] older code processed or checked this parse ({'; '.join(older)}), so its findings and "
                f"figures may not be the current code's; {cli.prog('render')} {folder} processes and checks it again, "
                "keeping the edits and verdicts")


def cmd_findings(argv):
    """The findings of a parse still open, and those judged unresolved: one JSON line each.

A finding is a place where the checks against the source suspect the parse lost, garbled or invented something, or cut
a figure wrong. Each open one is a note in the Markdown, <!-- open <id>: ... -->, before its block, figure or page;
its id is <code>@<block or page>:
  missing_text        a run of text-layer words absent from the parse
  missing_numbers     numbers of two or more digits on text-layer lines but not in the parse
  extra_text          a run of parsed words the text layer lacks: text the model invented
  foreign_script      CJK, kana or Hangul characters the text layer lacks
  table_mismatch      text-layer tokens inside a table's box absent from that table
  unchecked_table     a table with no text layer in its box (embedded as an image)
  table_empty_column  a headed column empty in every row: values shifted under the wrong headers
  formula_number_gap  equation numbers missing from an otherwise continuous run
  low_coverage        under 80% of the page's text-layer word trigrams were found
  repetition          a block repeats one fragment, or cycles through the same words
  empty_page          a page yielded no text
  figure_check        a figure whose crop may be wrong (no_crop, split, two_figures, table, edge_cut, second_opinion)
  no_text_layer       pages that cannot be checked (scans, images)
  stale_edit          an earlier edit that no longer fits the block's text
A finding is settled by a fix in the Markdown or a verdict on its note, then ocr.py commit (commit -h).

stdout: {id, status: open | unresolved | ok, page, note}, open ones first; page is null for the whole document; note
is the open note's text, or the reason given with the verdict. Read-only: when the Markdown holds edits not committed
yet, stderr says so, and the lines leave them out; when older code processed or checked the parse, stderr says so and
names the render that brings it up to date.
Exit 0 = no open findings (including an empty list); unresolved findings have a verdict and do not block it.
Exit 1 = open findings remain, with {summary: {total, open, unresolved, ok}} on stderr; or the folder is no parse:
one line {folder, code, hint}, code file_not_found, no_record or old_format.

Example:
  ocr.py findings /abs/out/paper
"""
    _, args, folder = command("findings", cmd_findings.__doc__, argv, source=False, configure=lambda p: p.add_argument(
        "-a", "--all", action="store_true", help="also the findings judged ok"))

    def go():
        record = load(folder)
        warn_unrecorded(folder, record)
        for row in finding_rows(record, args.all):
            cli.emit(row)
        counts = {"total": len(record.get("findings", [])), "open": 0, "unresolved": 0, "ok": 0}
        for finding in record.get("findings", []):
            counts[finding["status"]] += 1
        if counts["open"]:
            cli.emit({"summary": counts}, sys.stderr)
            return cli.ACT
        return cli.OK
    return cli.run(go, folder=str(folder))


def cmd_show(argv):
    """A finding, block, figure or page of a parse, for reading: its text, the text layer under it, a page image.

WHAT is a finding id (missing_text@p3), a block id (p4-12), a figure id (p6-4, p6-cut1) or a page (p4):
  finding  the finding in full, then its block as below; a figure_check: its crops and the second opinion as boxes,
           and an overlay image (caption blue, crops numbered, second opinion green dashed)
  block    its label, box and changes, its text, the text layer under its box with the pdftotext command for that
           region, and the page image with the block boxed
  figure   its box, image, members, caption and changes, and the page image with it boxed
  page     every block with its id, label, box and first words, the page's figures, and the page image with the
           block ids drawn on it; --box crops that region at --dpi instead
Boxes, given and shown, are in source units from the rendered page's top left: PDF points within the crop box,
image pixels, or for --photo the pixels of pages/. Use these boxes for --box. The printed pdftotext region command
converts to that tool's media-box coordinates; its -x/-y values are not --box coordinates. Coordinates start at 0,
and a box past the page's edge is cut to the page, so no box needs a negative number.

Images go to $TMPDIR/paddleocr-show/<stem>-<hash>/, named in the output; whoever runs show deletes that folder when
done. Read-only: when the Markdown holds edits not committed yet, stderr says so, and the output leaves them out;
when older code processed or checked the parse, stderr says so and names the render that brings it up to date.

stdout: text for reading. Exit 0 = shown; 1 = nothing shown, and stderr's last line {folder, code, hint} says why:
not_found (WHAT is not in the parse, or its page was not parsed), source_not_found (--box needs the source),
source_mismatch, or the folder is no parse (file_not_found, no_record, old_format); 2 = stderr's last line {code,
hint}: bad_box, or --source names no file (file_not_found) or another file (source_mismatch).

Examples:
  ocr.py show /abs/out/paper missing_text@p3
  ocr.py show /abs/out/paper p4 --box 72,100,300,400 --dpi 400
"""
    def configure(p):
        p.add_argument("what", nargs="?", metavar="WHAT", help="a finding id, block id, figure id or page (p4)")
        p.add_argument("--box", type=box_value, metavar="X1,Y1,X2,Y2", help="with a page: crop this region")
        p.add_argument("--dpi", type=int, default=300, help="resolution of the crop from a PDF page (default 300)")
    p, args, folder = command("show", cmd_show.__doc__, argv, configure)
    if not args.what:
        p.error("name what to show: a finding, block, figure or page (p4)",
                hint=f"{cli.prog('findings')} {args.folder} lists the findings.")

    def go():
        record = load(folder)
        src = source_of(record, args.source, need=bool(args.box), folder=folder)
        warn_unrecorded(folder, record)
        cli.write("\n".join(show(folder, record, src, args.what, args.box, args.dpi)) + "\n")
        return cli.OK
    return cli.run(go, sys.stderr, folder=str(folder))


def cmd_commit(argv):
    """Record the edits and verdicts made in a parse's Markdown, check again, and write the Markdown anew.

Editing <stem>.md before commit:
  - change text anywhere in a block; a heading whose leading #s you delete becomes body text; an edit across blocks
    keeps the new text in the first and deletes the rest; a paragraph of its own (blank lines around it) becomes a new
    block, and a line added without a blank line joins the paragraph it touches; put <!-- fixed: why --> on the line
    above each edited block
  - settle a finding: change "open" in its note to "ok" (the parse is right, or it is a false alarm) or "unresolved"
    (wrong, and it cannot be fixed), with the reason after the colon
  - delete a figure's image line to hide it; cut figures with ocr.py cut
  - leave the first line, <!-- page N --> and the figure markers as they are
Each edit becomes a change of its block, each verdict keeps its reason; the checks run again, against the source when
it is at hand, and the Markdown is generated anew from the record.

stdout: one line {folder, code: ok, recorded, gone, new, reopened}: recorded holds a sentence per change, the others
finding ids, each only when not empty. Nothing to record: code skipped, reason nothing_to_commit.
Exit 0 = recorded, or nothing to; 1 = the line's code says what is wrong: edit_refused (detail says where, hint what
to change; nothing was recorded), source_mismatch, or the folder is no parse (file_not_found, no_record, old_format);
2 = stderr's last line {code, hint}: locked (another process is writing the folder), or --source names no file
(file_not_found) or another file (source_mismatch).

Example:
  ocr.py commit /abs/out/paper
"""
    _, args, folder = command("commit", cmd_commit.__doc__, argv)

    def go():
        record = load(folder)
        src = source_of(record, args.source, folder=folder)
        if src is None and record["source"].get("path"):
            cli.log("[paddleocr] the source is not at the record's path nor beside the folder: the edits are recorded "
                    "without checking them against it; give it with --source FILE to check them")
        with locked(folder):
            fields = settle_edits(folder, record, src)
        done = {"code": "ok"} if fields else {"code": "skipped", "reason": "nothing_to_commit"}
        cli.emit({"folder": str(folder), **done, **fields})
        return cli.OK
    return cli.run(go, folder=str(folder))


def cmd_cut(argv):
    """Cut a figure of a parse anew, make a new one on a page, or name the block that is a figure's caption.

WHAT is a figure id (p6-4), cut anew to --box, or a page (p6), on which --box makes a new figure (p6-cut1), for one
read as text or missed. The image blocks inside the box become part of the figure, so a figure split into several
crops is whole again once any of them is cut to the whole box; the text the model read from it stays. A figure id
takes --box, --caption or both; a page takes --box. Markdown edits not recorded yet are committed first.
Boxes are in source units, as ocr.py show gives them (show -h).

A figure's caption, and the number it gives the figure, is found by place: the caption nearest the figure, which can
be another figure's. --caption names it instead: a caption block, or a caption you restored from the text layer as a
paragraph of its own and committed (commit's line gives its block id). No other figure is paired with a named caption.

stdout: one line {folder, code: ok, figure, image, caption, number, recorded, gone, new, reopened}, the last four as
commit's; image is the new crop, caption the block id of the figure's caption (null when it has none), number the
figure number it gives.
Exit 0 = cut; 1 = the line's code says what is wrong: not_found (no such figure, a block that is no figure, no block
--caption names, or a page not parsed), edit_refused, source_not_found, source_mismatch, or the folder is no parse
(file_not_found, no_record, old_format); 2 = stderr's last line {code, hint}: usage (no --box nor --caption, or a page
without --box), bad_box, locked, or --source names no file (file_not_found) or another file (source_mismatch).

Examples:
  ocr.py cut /abs/out/paper p6-4 --box 50,80,550,400 --reason "cut off the legend"
  ocr.py cut /abs/out/paper p6 --box 50,80,550,400 --caption p6-n1 --reason "read as text; caption from the text layer"
  ocr.py cut /abs/out/paper p6-cut1 --caption p6-12
"""
    def configure(p):
        p.add_argument("what", metavar="WHAT", help="a figure id (p6-4), or a page (p6) for a new figure")
        p.add_argument("--box", type=box_value, metavar="X1,Y1,X2,Y2", help="the figure's whole extent")
        p.add_argument("--caption", metavar="BLOCK", help="the block id of the figure's caption")
        p.add_argument("--reason", metavar="TEXT", default="", help="what was wrong, kept with the change")
    p, args, folder = command("cut", cmd_cut.__doc__, argv, configure)
    page = int(m.group(1)) if (m := re.fullmatch(r"p(\d+)", args.what)) else None
    if args.box is None and (page or not args.caption):
        p.error("a page takes --box" if page else "name --box, --caption or both",
                hint=f"{cli.prog('show')} {args.folder} {args.what} gives the boxes; {cli.prog('cut')} -h says more.")

    def go():
        record = load(folder)
        src = source_of(record, args.source, need=True, folder=folder)
        with locked(folder):
            fields = settle_edits(folder, record, src)
            ident = set_figure(record, None if page else args.what, page, args.box, args.reason, args.caption)
            refine_figures(record)
            moves = check(record, src, folder)
            write_images(record, src, folder)
            text, _ = render_text(record)
            save(folder, record, text)
        fig = next(f for f in record["figures"] if f["id"] == ident)
        cli.emit({"folder": str(folder), "code": "ok", "figure": ident, "image": str(folder / "imgs" / f"{ident}.png"),
                  "caption": fig.get("caption"), "number": fig.get("number", ""), **tally(fields, moves)})
        return cli.OK
    return cli.run(go, folder=str(folder))


def cmd_render(argv):
    """Process a parse's stored model output again with the current code, check it, write the figures and Markdown.

No GPU: it starts from what the models gave, as the record holds it. The edits and verdicts made since stay; Markdown
edits not recorded yet are committed first. For a record older than the code, ocr.py parse does the same by itself.
It runs in the paddleocr uv tool environment.

stdout: the line ocr.py parse prints for a document, under its folder: {folder, code: ok, md, json, rendered: true,
pages, blocks, figures, min_coverage, checks, open, unresolved, recorded, gone, new, reopened}, the last four as
commit's.
Exit 0 = rendered; 1 = the line's code says what is wrong: edit_refused, source_not_found, source_mismatch, or the
folder is no parse (file_not_found, no_record, old_format); 2 = stderr's last line {code, hint}: paddleocr_missing,
locked, or --source names no file (file_not_found) or another file (source_mismatch).

Example:
  ocr.py render /abs/out/paper
"""
    _, args, folder = command("render", cmd_render.__doc__, argv)

    def go():
        ensure_engine()
        record = load(folder)
        src = source_of(record, args.source, need=True, folder=folder)
        with locked(folder):
            fields = settle_edits(folder, record, src)
            moves = build(record, src, folder)
        json_path, md_path = paths(folder)
        cli.emit({"folder": str(folder), "code": "ok", "md": str(md_path), "json": str(json_path), "rendered": True,
                  **summary(record), **tally(fields, moves)})
        return cli.OK
    return cli.run(go, folder=str(folder))


def cmd_objects(argv):
    """Where a parse's figures and tables sit in its PDF, for links from notes: one JSON line each, in page order.

A figure is its whole box, its pieces under one caption joined; a table is its caption line ("TABLE III"), which
carries its number. Read-only: edits in the Markdown stay uncommitted. The source must be a PDF.

stdout: {id, kind: figure | table, key, number, page, page_label, rect, top}
  number      as the caption writes it
  key         the number normalised, <fig|table>:<prefix><number>, prefix "", S (Supplementary) or ED (Extended
              Data), roman numerals upper case: fig:3, fig:S2, table:III; null when two captions give the same key,
              or there is no number
  rect        [x1, y1, x2, y2] in the PDF's user space (points, origin bottom left, the page's crop box offset
              included), as PDF annotations store it
  top         the box's top in points below the page's top edge; rect and top are null on a rotated page
  page_label  the PDF's label for the page, else its number
Exit 0 = listed; 1 = one line {folder, code, hint}: not_a_pdf (the parse was made from images), source_not_found,
source_mismatch, or the folder is no parse (file_not_found, no_record, old_format); 2 = stderr's last line {code,
hint}: --source names no file (file_not_found) or another file (source_mismatch).

Example:
  ocr.py objects /abs/out/paper --source /abs/paper.pdf
"""
    _, args, folder = command("objects", cmd_objects.__doc__, argv)

    def go():
        record = load(folder)
        for o in objects(record, source_of(record, args.source, need=True, folder=folder)):
            cli.emit(o)
        return cli.OK
    return cli.run(go, folder=str(folder))


COMMANDS = {"findings": cmd_findings, "show": cmd_show, "commit": cmd_commit, "cut": cmd_cut, "render": cmd_render,
            "objects": cmd_objects}


def main(argv=None) -> int:
    name, rest = cli.subcommand(__doc__, COMMANDS, argv)
    return COMMANDS[name](rest)


def ensure_engine() -> None:
    """render calls PaddleOCR's restructure_pages: re-run in the paddleocr tool environment when not in it (or stop
    with paddleocr_missing)."""
    try:
        import paddlex  # noqa: F401
        return
    except ImportError:
        pass
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import parse
    parse.ensure_tool_env(__file__)


if __name__ == "__main__":
    sys.exit(main())
