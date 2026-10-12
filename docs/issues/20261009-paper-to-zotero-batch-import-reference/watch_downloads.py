# /// script
# requires-python = ">=3.11"
# ///
"""Downloads watcher for the browser batch: takes any new PDF in Downloads, whoever clicked it.

Runs in the background for the whole browser phase (user, 2026-10-10: 「后台下载监控程序要持续的，不要以你
自己点击为准才开始监控下载目录……你一旦检测到下载了，然后内容符合，就进行下一步」). Every 2 s it lists
Downloads; a new, complete PDF (no .crdownload, size stable) is matched by title against the pending rows
of candidates/browser_batch.tsv and must pass batchlib.verify (title, DOI on page 1, not a supplement or\ncorrection) before anything is attached. A match is claimed under the batch lock, moved to prefetch/batch/<stem>.pdf,
attached to its Zotero item and marked OK; fetch_batch.py sees the status and moves on. A PDF for a row
that is already taken goes to prefetch/stray/ as a duplicate; a supplement row's file is kept for attaching by hand; a PDF that matches no row may be the user's own and stays in Downloads, reported as UNMATCHED.
Files present when the watcher starts are left alone. Stops when no row is pending, or on SIGTERM.

    uv run --no-project watch_downloads.py
"""
import sys
import time
from pathlib import Path

import batchlib as bl
import fetch_browser as fb


def main() -> int:
    seen = fb.downloads_now()
    sizes: dict[str, int] = {}
    print(f"watching {fb.DOWNLOADS}", flush=True)
    while True:
        rows = bl.read_rows()
        if not any(bl.pending(r) for r in rows):
            print("no pending rows left: watcher stops", flush=True)
            return 0
        for n in sorted(fb.downloads_now() - seen):
            f = fb.DOWNLOADS / n
            if n.endswith(".crdownload") or not f.exists():
                continue
            size = f.stat().st_size
            if sizes.get(n) != size:  # wait one more tick until the size is stable
                sizes[n] = size
                continue
            seen.add(n)
            if not n.lower().endswith(".pdf") or f.read_bytes()[:4] != b"%PDF":
                continue
            loose = [r for r in rows if fb.title_ok(f, r["title"])]
            checked = [(r, bl.verify(f, r)) for r in loose]
            row = next((r for r, (ok, _) in checked if ok), None)
            if row is None:  # the user's own download, or ours failing the identity check: leave it, report it
                why = "; ".join(f"{bl.stem(r)}: {reason}" for r, (_, reason) in checked) or "no title match"
                print(f"{'UNVERIFIED' if loose else 'UNMATCHED'} {n} (left in Downloads; {why[:120]})", flush=True)
                continue
            reason = dict((bl.stem(r), why) for r, (_, why) in checked)[bl.stem(row)]
            if row["kind"] == "supplement":
                dst = bl.OUT / f"{bl.stem(row)}-supplement-{n}"
                bl.move(f, dst)
                bl.update(bl.stem(row), status="CHECK", file=str(dst.relative_to(bl.HERE)), note=f"supplement downloaded ({n}); attach by hand")
                print(f"SUPPL  {n} -> {dst.name}", flush=True)
                continue
            if not bl.pending(row) or not bl.claim(row, "watcher"):
                bl.move(f, fb.PRE / "stray" / n)
                print(f"DUP    {n} (row {bl.stem(row)} already taken) -> prefetch/stray/", flush=True)
                continue
            out = bl.OUT / f"{bl.stem(row)}.pdf"
            bl.move(f, out)
            status, note = bl.finish(row, out, f"via Chrome download ({n}; clicked by the user or a route); checked: {reason}")
            print(f"{status:6} {row['kind']:9} {bl.stem(row):45} {note[:90]}", flush=True)
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
