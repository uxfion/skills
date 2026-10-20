#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The one way a file reaches a record: check it, then file it beside the record as <slug>.pdf (or .html).

Two kinds of file come in, and both go through check_pdf.py (subprocess) before they are filed:
  --file F --slug S   bytes a script fetched for one record (fetch.py writes them to <work>/inbox/ and calls this).
                      Checked against that record only: passing -> filed; failing -> moved to
                      <work>/unverified/<slug>.<via>.<ext> and logged with its source, for the agent to look at.
  --scan              new files in the browser's Downloads folder (--downloads DIR, as ready.py reports it),
                      whoever started the download: the agent, a click that opened a PDF link, or the user. Only
                      files newer than <work>/.started, complete (no .crdownload / .part), starting with %PDF-.
                      Each is checked against every record whose library item has no PDF yet: exactly one match
                      -> filed and removed from Downloads (a record that already has its file -> the copy goes
                      to <work>/stray/); no match or several -> left where it is (it may be the user's own),
                      logged with the slugs it was checked against. A left file is checked again only against
                      records drafted after that (the user downloaded a paper, then asked for it).
  --watch             --scan every --interval seconds until the work directory disappears or the process is
                      stopped: run it in the background while the browser is in use.
  --sweep             end of run: the files newer than .started still in Downloads, each marked with whether the
                      library already holds it (find_in_library.py --md5), for the report and the cleanup.

Filing is atomic and first come, first served: the file is copied to a temporary name in records/, then
os.link-ed to its final name; when that name exists (the same paper arrived another way), the copy goes to
stray/. The final name carries the version (the work directory's convention, read by check_pdf.py and
attach_file.py): <slug>.pdf published, <slug>.accepted.pdf, <slug>.preprint.pdf, <slug>.supplement.pdf,
<slug>.html snapshot. --version sets it for --file; for Downloads it is check_pdf's verdict (published, or
preprint when arXiv's margin stamp is on page 1). A wrong guess is fixed by renaming the file.

Every outcome is one line appended to <work>/fetch.jsonl (one write on an O_APPEND descriptor, so parallel
writers never interleave) and printed: {"event": "claim", "file", "slug"?, "result": claimed | stray |
unverified | left, "version"?, "code"? (check_pdf's), "source"?, "at"}; --sweep adds "in_library". Exit 0 =
done (for --file: filed), 1 = --file not filed (unverified / stray), 2 = cannot check (no work directory, no
.started, check_pdf.py could not run).
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECK_SCRIPT = HERE / "check_pdf.py"
FIND_SCRIPT = HERE / "find_in_library.py"
STEM_FILES = (".pdf", ".accepted.pdf", ".preprint.pdf", ".supplement.pdf", ".html")
PARTIAL = (".crdownload", ".part", ".tmp", ".download")
VERSIONS = ("published", "accepted", "preprint", "supplement", "snapshot")


class Stop(Exception):
    def __init__(self, code, hint, **extra):
        super().__init__(code)
        self.code, self.hint, self.extra = code, hint, extra


def log(msg):
    print(msg, file=sys.stderr)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ the work directory

def records_of(work):
    """[(path, record)] of <work>/records/*.json; unreadable files are skipped."""
    out = []
    for path in sorted((work / "records").glob("*.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict):
            out.append((path, rec))
    return out


def slug_of(path, rec):
    return rec.get("slug") if isinstance(rec.get("slug"), str) and rec.get("slug") else path.stem


def file_of(work, slug):
    """The record's filed file, if any (any version)."""
    return next((f for f in (work / "records" / (slug + s) for s in STEM_FILES) if f.is_file()), None)


def library_has_pdf(rec):
    found = rec.get("found") if isinstance(rec.get("found"), dict) else {}
    return any(isinstance(a, dict) and a.get("contentType") == "application/pdf"
               and str(a.get("linkMode") or "").startswith("imported") for a in found.get("attachments") or [])


def target_name(slug, version, html):
    if html or version == "snapshot":
        return f"{slug}.html"
    return f"{slug}.pdf" if version in (None, "published") else f"{slug}.{version}.pdf"


def append_log(work, line):
    data = (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(work / "fetch.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def emit_event(work, **fields):
    line = {"event": "claim", **{k: v for k, v in fields.items() if v is not None}, "at": now_iso()}
    append_log(work, line)
    print(json.dumps(line, ensure_ascii=False), flush=True)
    return line


def move(src, dest_dir, name):
    """Move src into dest_dir under name (a numbered name when taken); returns the new path."""
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / name
    n = 2
    while dest.exists():
        stem, dot, ext = name.partition(".")
        dest = dest_dir / f"{stem}-{n}{dot}{ext}"
        n += 1
    shutil.move(str(src), str(dest))
    return dest


def place(work, slug, src, version, html):
    """File src as the record's file -> ("claimed", path) or ("stray", path). src is consumed either way."""
    records = work / "records"
    target = records / target_name(slug, version, html)
    if file_of(work, slug) is not None:
        return "stray", move(src, work / "stray", target.name)
    tmp = records / f".{slug}.{uuid.uuid4().hex[:8]}.tmp"
    shutil.copy2(src, tmp)
    try:
        os.link(tmp, target)
    except FileExistsError:
        return "stray", move(src, work / "stray", target.name)
    finally:
        tmp.unlink(missing_ok=True)
    src.unlink(missing_ok=True)
    return "claimed", target


# ------------------------------------------------------------------ checking

def match(file, record_paths, version=None):
    """check_pdf.py --match -> (matched slugs, {slug: code}, the verdict's file_version)."""
    argv = [sys.executable, str(CHECK_SCRIPT), "--match", str(file), *map(str, record_paths)]
    if version:
        argv += ["--file-version", version]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Stop("check_failed", "check_pdf.py could not run", detail=str(e))
    rows = [json.loads(line) for line in done.stdout.splitlines() if line.startswith("{")]
    if done.returncode >= 2 or not rows or "matched" not in rows[-1]:
        detail = rows[-1] if rows else done.stderr.strip()[-400:]
        raise Stop("check_failed", "check_pdf.py could not check the file (is poppler installed?)", detail=detail)
    codes = {r["slug"]: r.get("code") for r in rows[:-1] if "slug" in r}
    return rows[-1]["matched"], codes, rows[-1].get("file_version")


# ------------------------------------------------------------------ modes

def claim_file(work, args):
    src = Path(args.file).expanduser()
    rec_path = work / "records" / f"{args.slug}.json"
    if not src.is_file():
        raise Stop("file_not_found", "the file to claim does not exist", file=str(src))
    if not rec_path.is_file():
        raise Stop("no_record", "no record with that slug in the work directory", slug=args.slug)
    html = src.suffix.lower() in (".html", ".htm") or args.version == "snapshot"
    matched, codes, version = match(src, [rec_path], args.version or ("snapshot" if html else None))
    version = args.version or version
    if args.slug in matched:
        result, path = place(work, args.slug, src, version, html)
        emit_event(work, file=path.name, slug=args.slug, result=result, version=version, code=codes.get(args.slug),
                   source=args.source)
        return 0 if result == "claimed" else 1
    ext = ".html" if html else ".pdf"
    path = move(src, work / "unverified", f"{args.slug}.{args.via or 'file'}{ext}")
    emit_event(work, file=path.name, slug=args.slug, result="unverified", version=version,
               code=codes.get(args.slug), source=args.source)
    return 1


def downloads_dir(args):
    path = Path(args.downloads or os.environ.get("PAPER_TO_ZOTERO_DOWNLOADS") or "").expanduser()
    if not args.downloads and not os.environ.get("PAPER_TO_ZOTERO_DOWNLOADS"):
        raise Stop("no_downloads", "pass --downloads DIR (ready.py reports downloads_dir)")
    if not path.is_dir():
        raise Stop("no_downloads", "the Downloads directory does not exist", downloads=str(path))
    return path


def started_at(work):
    marker = work / ".started"
    if not marker.exists():
        raise Stop("no_started", "the work directory has no .started marker: run ready.py --work first", work=str(work))
    return marker.stat().st_mtime


def new_downloads(dl, started):
    """Complete files newer than .started, oldest first."""
    out = []
    for f in dl.iterdir():
        try:
            if not f.is_file() or f.name.startswith(".") or f.suffix.lower() in PARTIAL or f.stat().st_mtime < started:
                continue
        except OSError:
            continue
        out.append(f)
    return sorted(out, key=lambda f: f.stat().st_mtime)


def left_before(work):
    """{(name, md5): slugs it was checked against} for files already logged as left in Downloads."""
    seen = {}
    try:
        with open(work / "fetch.jsonl", encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict) and obj.get("event") == "claim" and obj.get("result") == "left":
                    seen.setdefault((obj.get("file"), obj.get("md5")), set()).update(obj.get("against") or [])
    except OSError:
        pass
    return seen


def scan(work, dl):
    started = started_at(work)
    seen = left_before(work)
    events = 0
    for f in new_downloads(dl, started):
        try:
            with open(f, "rb") as fh:
                head = fh.read(1024)
            size, digest = f.stat().st_size, md5_of(f)
        except OSError:
            continue
        if not head.lstrip().startswith(b"%PDF-"):
            continue
        time.sleep(0.2)
        try:
            if f.stat().st_size != size:  # still being written
                continue
        except OSError:
            continue
        candidates = [(p, r) for p, r in records_of(work) if not library_has_pdf(r)]
        if (f.name, digest) in seen:  # left before: check it only against records drafted since
            candidates = [(p, r) for p, r in candidates if (r.get("slug") or p.stem) not in seen[(f.name, digest)]]
        if not candidates:
            continue
        matched, codes, version = match(f, [p for p, _ in candidates])
        if len(matched) == 1:
            slug = matched[0]
            result, path = place(work, slug, f, version, False)
            emit_event(work, file=path.name, slug=slug, result=result, version=version, code=codes.get(slug),
                       source=str(f), md5=digest)
        else:
            emit_event(work, file=f.name, result="left", md5=digest, source=str(f),
                       why="ambiguous" if matched else "unmatched", matched=matched or None,
                       against=sorted(r.get("slug") or p.stem for p, r in candidates))
        events += 1
    return events


def sweep(work, dl, base_url):
    started = started_at(work)
    files = new_downloads(dl, started)
    in_lib = {}
    if files:
        try:
            done = subprocess.run([sys.executable, str(FIND_SCRIPT), "--md5", *map(str, files), "--base-url", base_url],
                                  capture_output=True, text=True, timeout=300)
            for line in done.stdout.splitlines():
                if line.startswith("{"):
                    row = json.loads(line)
                    in_lib[row.get("file")] = row
        except (OSError, subprocess.TimeoutExpired, ValueError) as e:
            log(f"find_in_library --md5: {e}")
    for f in files:
        row = in_lib.get(str(f)) or {}
        emit_event(work, file=f.name, result="left", source=str(f), why="sweep",
                   in_library=(row.get("code") == "found") if row else None, attachment_key=row.get("attachment_key"),
                   citationKey=row.get("citationKey"))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Check a fetched file or the new files in Downloads and file each beside its record "
                    "(<slug>.pdf, .accepted.pdf, .preprint.pdf, .html); see the module docstring.",
        epilog="examples:\n"
               "  uv run claim.py --work W --file W/inbox/x.page.pdf --slug x --source https://...   (fetch.py does this)\n"
               "  uv run claim.py --work W --scan --downloads /mnt/c/Users/<user>/Downloads\n"
               "  uv run claim.py --work W --watch --downloads ...    # in the background while the browser is in use\n"
               "  uv run claim.py --work W --sweep --downloads ...    # end of run",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True, metavar="DIR", help="the work directory (ready.py --work)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--file", metavar="F", help="a file a script fetched for --slug")
    mode.add_argument("--scan", action="store_true", help="claim the new files in Downloads once")
    mode.add_argument("--watch", action="store_true", help="--scan in a loop")
    mode.add_argument("--sweep", action="store_true", help="list what this run left in Downloads")
    ap.add_argument("--slug", help="with --file: the record it was fetched for")
    ap.add_argument("--version", choices=VERSIONS, help="with --file: the file's version (default: check_pdf's verdict)")
    ap.add_argument("--source", metavar="URL", help="with --file: where the bytes came from (logged)")
    ap.add_argument("--via", help="with --file: the route that fetched it (names the unverified copy)")
    ap.add_argument("--downloads", metavar="DIR", help="the browser's Downloads folder (else $PAPER_TO_ZOTERO_DOWNLOADS)")
    ap.add_argument("--interval", type=float, default=3.0, help="with --watch: seconds between scans (default 3)")
    ap.add_argument("--base-url", default="http://127.0.0.1:23119", help="with --sweep: Zotero's local API")
    args = ap.parse_args()
    if args.file and not args.slug:
        ap.error("--file needs --slug")
    work = Path(args.work).expanduser()
    try:
        if not (work / "records").is_dir():
            raise Stop("no_work_dir", "the work directory has no records/ (run ready.py --work first)", work=str(work))
        if args.file:
            sys.exit(claim_file(work, args))
        dl = downloads_dir(args)
        if args.sweep:
            sys.exit(sweep(work, dl, args.base_url))
        if args.scan:
            scan(work, dl)
            sys.exit(0)
        while (work / "records").is_dir():
            scan(work, dl)
            time.sleep(args.interval)
        sys.exit(0)
    except Stop as stop:
        print(json.dumps({"code": stop.code, "hint": stop.hint, **stop.extra}, ensure_ascii=False))
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
