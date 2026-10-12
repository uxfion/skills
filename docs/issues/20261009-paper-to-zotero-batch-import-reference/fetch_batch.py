# /// script
# requires-python = ">=3.11"
# ///
"""Phase C batch driver: works through candidates/browser_batch.tsv in the user's Chrome.

Run only after the user confirms they are logged in, and together with watch_downloads.py, which takes
every new PDF in Downloads, whoever clicked it (the user may click a PDF button to speed things up). This
driver does not look at Downloads itself: for each pending row it re-reads the shared state (batchlib),
skips rows the watcher has finished, and tries the routes from fetch_browser.py — OpenReview in-page fetch,
publisher page, library discovery system → ProQuest. Gate waits and the gaps between routes end early
when the watcher finishes the row. An in-page fetch that returns the PDF is claimed and attached here; a
route that makes Chrome save the file leaves it to the watcher. Rows: `fulltext`, `published` (attached
beside the preprint as "PDF (published version)"), `new` (no Zotero item: fetched only), `supplement`
(by hand, skipped). Status is shared through batchlib; --retry also retries MISS rows.

    SP=<scratchpad> LOG=<scratchpad>/opencli.log uv run --no-project fetch_batch.py [--retry]
"""
import os
import re
import signal
import subprocess
import sys
import time
import types

import batchlib as bl
import fetch_browser as fb

CURRENT = {"key": None}
_orig_wait_gate = fb.wait_gate


def done_elsewhere():
    k = CURRENT["key"]
    return k is not None and not bl.pending({"kind": "", "status": bl.status_of(k)})


def wait_gate(page):
    """fetch_browser.wait_gate, but it also ends when the watcher has finished the current row."""
    print(f"GATE {page}", flush=True)
    for _ in range(60):  # up to 15 minutes: the user may be logging in
        for _ in range(15):
            time.sleep(1)
            if done_elsewhere():
                print("PASSED (row finished by the Downloads watcher)", flush=True)
                raise RowDone
        t = fb.title_now()
        if t and not fb.GATE.search(t):
            print(f"PASSED {t[:80]}", flush=True)
            return True
    print("GATE-TIMEOUT", flush=True)
    return False


fb.wait_gate = wait_gate  # the route functions look the name up at call time


class RowDone(Exception):
    """The watcher finished the current row while a route was still working on it."""


def sh(args, timeout=240):
    """fetch_browser.sh, interruptible: every route step (opencli calls, the tools/*.sh helpers) is polled
    once a second and killed as soon as the watcher has taken the current row, so the driver never keeps
    searching for a PDF the user has already downloaded."""
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=fb.ENV,
                         start_new_session=True)
    t0 = time.time()
    while True:
        try:
            out, _ = p.communicate(timeout=1)
            return p.returncode, out.strip()
        except subprocess.TimeoutExpired:
            if done_elsewhere() or time.time() - t0 > timeout:
                os.killpg(p.pid, signal.SIGTERM)
                p.communicate()
                if done_elsewhere():
                    raise RowDone
                return 124, "TIMEOUT"


def sleep(seconds):
    end = time.time() + seconds
    while time.time() < end:
        if done_elsewhere():
            raise RowDone
        time.sleep(min(1, end - time.time()))


fb.sh = sh
fb.time = types.SimpleNamespace(sleep=sleep, time=time.time)  # fetch_browser's own pauses become interruptible


def open_pdf(res, out):
    """When fetching the PDF link inside the page is refused (403, HTML), open the link in the tab the way a
    person clicks it (user, 2026-10-10: 「我可能帮你点pdf下载并不意味着你不作为不去点，你也要尝试去获取到pdf」):
    Chrome then shows the PDF, fetched here from the viewer's URL, or saves it, and the watcher takes it."""
    m = re.search(r"(https?://\S+|/\S+)$", res.strip())
    if not m:
        return "openpdf: no link"
    link = m.group(1)
    if link.startswith("/"):
        _, origin = fb.sh(["opencli", "browser", "p2z", "eval", "location.origin"], 40)
        link = origin.strip().strip('"') + link
    fb.sh(["opencli", "browser", "p2z", "open", link, "--window", "foreground"], 90)
    sleep(8)
    t = fb.title_now()
    if fb.GATE.search(t) and not wait_gate(t):
        return "openpdf: gate"
    if wait_for_watcher(16):
        return "taken"
    _, ct = fb.sh(["opencli", "browser", "p2z", "eval", "document.contentType"], 40)
    if "pdf" in ct:
        _, here = fb.sh(["opencli", "browser", "p2z", "eval", "location.href"], 40)
        c, txt = fb.sh(["bash", str(fb.TOOLS / "samefetch.sh"), "p2z", here.strip().strip('"'), str(out)])
        if c == 0 and "Pages" in txt:
            return "ok openpdf"
    if wait_for_watcher(20):
        return "taken"
    return f"openpdf: {ct.strip()[:30]} | {t[:50]}"


def wait_for_watcher(seconds=12):
    """A route may have made Chrome save the PDF; give the watcher time to take it."""
    for _ in range(seconds // 2):
        if done_elsewhere():
            return True
        time.sleep(2)
    return done_elsewhere()


def main() -> int:
    retry = "--retry" in sys.argv
    bl.OUT.mkdir(parents=True, exist_ok=True)
    for row in bl.read_rows():
        key = bl.stem(row)
        status = bl.status_of(key)
        if row["kind"] == "supplement" or not bl.pending({"kind": row["kind"], "status": status}) or (status == "MISS" and not retry):
            continue
        CURRENT["key"] = key
        out = bl.OUT / f"{key}.pdf"
        out.unlink(missing_ok=True)
        routes = []
        if row["openreview_id"]:
            routes.append(("openreview", lambda: fb.openreview(row["openreview_id"], out)))
        if row["doi"]:
            routes.append(("publisher", lambda: fb.publisher(row["doi"], out)))
        routes.append(("discovery", lambda: fb.discovery(row["title"], out)))
        notes, got = [], None
        try:
            for name, fn in routes:
                if done_elsewhere():
                    break
                res = fn()
                if name == "publisher" and "NOTPDF" in res:  # refused in-page: open the link like a click
                    more = open_pdf(res, out)
                    if more.startswith("ok"):
                        res, name = more, "publisher (opened the PDF link)"
                    else:
                        res = f"{res[:60]} | {more}"
                if res.startswith("ok") and out.exists() and out.read_bytes()[:4] == b"%PDF":
                    got = name
                    break
                if wait_for_watcher():
                    break
                notes.append(f"{name}: {res[:80]}")
        except RowDone:
            pass
        if done_elsewhere():
            out.unlink(missing_ok=True)
            print(f"TAKEN  {row['kind']:9} {key:45} by the Downloads watcher", flush=True)
            continue
        if not got:
            out.unlink(missing_ok=True)
            bl.update(key, status="MISS", note=" | ".join(notes)[:300])
            print(f"MISS   {row['kind']:9} {key:45} {' | '.join(notes)[:100]}", flush=True)
            continue
        ok, reason = bl.verify(out, row)
        if not ok:
            bl.update(key, status="CHECK", file=str(out.relative_to(bl.HERE)), note=f"via {got}; identity check failed ({reason}), not attached")
            print(f"CHECK  {row['kind']:9} {key:45} identity check failed: {reason}", flush=True)
            continue
        if not bl.claim(row, "driver"):
            out.unlink(missing_ok=True)
            print(f"TAKEN  {row['kind']:9} {key:45} by the Downloads watcher", flush=True)
            continue
        status, note = bl.finish(row, out, f"via {got}; checked: {reason}")
        print(f"{status:6} {row['kind']:9} {key:45} {note[:90]}", flush=True)
    CURRENT["key"] = None
    return 0


if __name__ == "__main__":
    sys.exit(main())
