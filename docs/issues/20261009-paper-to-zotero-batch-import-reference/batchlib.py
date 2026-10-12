"""Shared state for the browser batch: candidates/browser_batch.tsv, read and written under a file lock by
fetch_batch.py (the driver) and watch_downloads.py (the Downloads watcher), plus claiming and attaching.

Row status: "" or MISS = pending (MISS is retried only with --retry, but the watcher still takes a download
for it); CLAIMED:<who> = one process is attaching it; OK = attached (or fetched, for a row without a
Zotero item); CHECK = needs a look; a `supplement` row is handled by hand.
"""
import csv
import fcntl
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCH = HERE / "candidates" / "browser_batch.tsv"
LOCK = HERE / "candidates" / ".browser_batch.lock"
OUT = HERE / "prefetch" / "batch"
P2Z = Path.home() / ".claude" / "skills" / "paper-to-zotero"


@contextmanager
def locked():
    with open(LOCK, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def _read():
    return list(csv.DictReader(open(BATCH), delimiter="\t"))


def _write(rows):
    with open(BATCH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def stem(row):
    return row["citation_key"] or re.sub(r"[^A-Za-z0-9._-]+", "_", row["doi"])


def read_rows():
    with locked():
        return _read()


def pending(row):
    return row["kind"] != "supplement" and row["status"] in ("", "MISS")


def status_of(key):
    return next((r["status"] for r in read_rows() if stem(r) == key), "")


def update(key, **fields):
    with locked():
        rows = _read()
        for r in rows:
            if stem(r) == key:
                r.update(fields)
        _write(rows)


def claim(row, who):
    """Mark the row as taken by `who` unless another process got there first; True if this one won."""
    with locked():
        rows = _read()
        for r in rows:
            if stem(r) == stem(row):
                if not pending(r):
                    return False
                r["status"] = f"CLAIMED:{who}"
                _write(rows)
                return True
    return False


def move(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.stat().st_dev == dst.parent.stat().st_dev:
        src.replace(dst)
    else:
        dst.write_bytes(src.read_bytes())
        src.unlink()


LIGATURES = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "’": "'", "‘": "'"})


def _text(pdf, last_page):
    p = subprocess.run(["pdftotext", "-l", str(last_page), str(pdf), "-"], capture_output=True, text=True, timeout=60)
    t = p.stdout.translate(LIGATURES).lower()
    return re.sub(r"\s+", " ", re.sub(r"-\n", "", t))


def verify(pdf, row):
    """Identity check before anything is attached (user, 2026-10-10: 下载后入库前要核对): at least 80% of the
    title's words on pages 1-3; when page 1 prints a DOI it must be the row's DOI; not a supplement (unless the
    row is one), a correction or a retraction notice. Returns (ok, reason)."""
    text, p1 = _text(pdf, 3), _text(pdf, 1)
    words = re.findall(r"[a-z]{4,}", row["title"].lower().translate(LIGATURES))
    hit = sum(w in text for w in words) / max(1, len(words))
    if hit < 0.8:
        return False, f"title words on p1-3: {hit:.0%}"
    doi = row["doi"].lower()
    printed = {d.rstrip(".,;)") for d in re.findall(r"10\.\d{4,9}/[^\s\"<>]+", p1[:3000])}
    if doi and printed and not any(doi in d or d in doi for d in printed):
        return False, f"page 1 prints another DOI: {sorted(printed)[0][:60]}"
    if row["kind"] != "supplement" and re.search(r"supplementary (information|materials?|appendix)|supplemental material", p1[:400]):
        return False, "looks like a supplementary file"
    if re.search(r"\b(correction|erratum|retraction)\b", p1[:300]):
        return False, "looks like a correction or retraction notice"
    return True, f"title words {hit:.0%}" + ("; DOI on p1" if doi and doi in p1 else "")


def attach(row, pdf):
    title = "PDF (published version)" if row["kind"] == "published" else "PDF"
    url = f"https://doi.org/{row['doi']}" if row["doi"] else f"https://openreview.net/forum?id={row['openreview_id']}"
    p = subprocess.run(["uv", "run", "scripts/attach_file.py", "--key", row["zotero_key"], "--file", str(pdf),
                        "--url", url, "--title", title], cwd=P2Z, capture_output=True, text=True, timeout=300)
    out = p.stdout + p.stderr
    m = re.search(r'"code":\s*"([^"]+)"', out)
    return p.returncode == 0, (m.group(1) if m else out.strip()[-160:])


def finish(row, pdf, via):
    """After a successful claim: attach (when the row has a Zotero item) and write the final status."""
    rel = str(pdf.relative_to(HERE))
    if row["zotero_key"]:
        ok, msg = attach(row, pdf)
        status, note = ("OK", f"{via}; attached") if ok else ("CHECK", f"{via}; attach failed: {msg}")
    else:
        status, note = "OK", f"{via}; no Zotero item yet"
    update(stem(row), status=status, file=rel, note=note)
    return status, note
