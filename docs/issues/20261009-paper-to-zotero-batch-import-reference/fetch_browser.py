# /// script
# requires-python = ">=3.11"
# ///
"""Fetch the PDFs that need the user's Chrome, while the user is online.

Works through candidates/_access.tsv rows marked `openreview` or `browser`, one at a time:

1. OpenReview: fetch /pdf?id=<id> inside an openreview.net tab (the site refuses scripts);
2. publisher page: tools/pubfetch.sh (citation_pdf_url fetched inside the page with the user's
   cookies; the Zotero Connector may route it through the library proxy);
3. library discovery system: tools/primo_links.sh by title; a ProQuest `linktopdf` goes to
   tools/pq.sh (PDF bytes from ProQuest's viewer), another `linktopdf` is opened and fetched in-page.

A gate (login, CAPTCHA, browser check) prints `GATE <page>` at once and is polled every 15 s for
up to 15 minutes. Each success is saved to prefetch/<slug>.pdf, added to prefetch/INDEX.tsv and
rewrites its _access.tsv row to `prefetched`; each failure sets `note` and moves on, so a rerun
retries only failures (use --retry) and the run resumes after an interruption.
"""
import csv
import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE / "tools"
ACC = HERE / "candidates" / "_access.tsv"
PRE = HERE / "prefetch"
ROWS = {r["merged_id"]: r for r in csv.DictReader(open(HERE / "candidates" / "ingest_list.tsv"), delimiter="\t")}
SP = os.environ.get("SP", os.environ.get("TMPDIR", "/tmp"))
ENV = os.environ | {"SP": SP, "LOG": os.environ.get("LOG", f"{SP}/opencli.log")}
DOWNLOADS = Path(os.environ["DOWNLOADS"])  # the browser's download folder, as this machine sees it
GATE = re.compile(r"just a moment|verifying|robot|captcha|请稍候|sign in|log ?in|access denied|authenticat|shibboleth|single sign|\bsso\b|\bcas\b|webvpn|统一身份|身份认证|认证|登录|授权", re.I)


def sh(args, timeout=240):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=ENV)
        return p.returncode, p.stdout.strip()
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def title_now():
    _, out = sh(["opencli", "browser", "p2z", "state"], 40)
    m = re.search(r"^title: ?(.*)$", out, re.M)
    return m.group(1) if m else ""


def wait_gate(page):
    print(f"GATE {page}", flush=True)
    for _ in range(60):  # up to 15 minutes: the user may be logging in (2026-10-10: 「别那么快关，我还没登录」)
        time.sleep(15)
        t = title_now()
        if t and not GATE.search(t):
            print(f"PASSED {t[:80]}", flush=True)
            return True
    print("GATE-TIMEOUT", flush=True)
    return False


def norm(s):
    return re.sub(r"[^a-z0-9]", "", html.unescape(s).lower())


def title_ok(pdf, title):
    text = sh(["pdftotext", "-l", "3", str(pdf), "-"], 60)[1].lower()
    return all(w in text for w in re.findall(r"[a-z]{5,}", title.lower())[:4])


def downloads_now():
    return {f.name for f in DOWNLOADS.iterdir() if f.is_file()} if DOWNLOADS.is_dir() else set()


def take_download(before, title, out, keep=True):
    """A route may make Chrome save the PDF instead of returning it (Content-Disposition: attachment).
    Move a new, title-matching PDF from Downloads to `out` (keep=False: `out` is already fetched)
    and delete this attempt's other copies of the same paper."""
    for _ in range(6):
        new = downloads_now() - before
        if not any(n.endswith(".crdownload") for n in new):
            break
        time.sleep(5)
    got = not keep
    for n in sorted(new):
        f = DOWNLOADS / n
        if not n.lower().endswith(".pdf") or f.read_bytes()[:4] != b"%PDF":
            continue
        if not got and title_ok(f, title):
            f.replace(out) if f.stat().st_dev == out.parent.stat().st_dev else (out.write_bytes(f.read_bytes()), f.unlink())
            got = True
        elif got and title_ok(f, title):
            f.unlink()
            print(f"  removed duplicate download {n}", flush=True)
        elif not title_ok(f, title):  # another paper's PDF, or the user's own download: leave it, report it
            print(f"  unrelated download {n} left in Downloads", flush=True)
    return got


def openreview(oid, out):
    sh(["opencli", "browser", "p2z", "open", f"https://openreview.net/forum?id={oid}", "--window", "foreground"], 90)
    time.sleep(5)
    t = title_now()
    if GATE.search(t) and not wait_gate(t):
        return "gate"
    code, txt = sh(["bash", str(TOOLS / "samefetch.sh"), "p2z", f"/pdf?id={oid}", str(out)])
    return "ok" if code == 0 and "Pages" in txt else f"openreview: {txt.splitlines()[0] if txt else code}"


def publisher(doi, out):
    code, txt = sh(["bash", str(TOOLS / "pubfetch.sh"), doi, str(out)])
    if code == 2:
        if wait_gate(txt[5:]):
            code, txt = sh(["bash", str(TOOLS / "pubfetch.sh"), doi, str(out)])
        else:
            return "gate"
    return "ok" if code == 0 else f"publisher: {txt[:90]}"


def discovery(title, out):
    code, txt = sh(["bash", str(TOOLS / "primo_links.sh"), title], 300)
    for line in txt.splitlines()[1:]:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if norm(d.get("t") or "")[:40] != norm(title)[:40]:
            continue
        for link in d.get("pdf") or []:
            m = re.search(r"proquest\.com/docview/(\d+)", link)
            if m:
                c, t = sh(["bash", str(TOOLS / "pq.sh"), m.group(1), str(out)], 300)
                if c == 0 and out.exists() and out.read_bytes()[:4] == b"%PDF":
                    return f"ok proquest {m.group(1)}"
            else:
                sh(["opencli", "browser", "p2z", "open", link, "--window", "foreground"], 90)
                time.sleep(8)
                t = title_now()
                if GATE.search(t) and not wait_gate(t):
                    return "gate"
                _, here = sh(["opencli", "browser", "p2z", "eval", "location.href"], 40)
                c, t = sh(["bash", str(TOOLS / "samefetch.sh"), "p2z", here.strip('"'), str(out)])
                if c == 0 and "Pages" in t:
                    return f"ok discovery {link.split('/')[2]}"
        return f"discovery: holding found, no PDF fetched ({len(d.get('pdf') or [])} pdf, {len(d.get('html') or [])} html links)"
    return "discovery: no matching record"


def main() -> int:
    retry = "--retry" in sys.argv
    acc = list(csv.DictReader(open(ACC), delimiter="\t"))
    for a in acc:
        if a["access"] not in ("openreview", "browser") or (a["note"] and not retry):
            continue
        r = ROWS[a["merged_id"]]
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", a["merged_id"]) + ".pdf"
        out = PRE / name
        out.unlink(missing_ok=True)
        ids = [x for x in (a["merged_id"], a["id"]) if x.startswith("openreview:")]
        doi = a["id"][4:] if a["id"].startswith("doi:") else ""
        routes = []
        if ids:
            routes.append(("openreview", lambda: openreview(ids[0].split(":", 1)[1], out)))
        if doi:
            routes.append(("publisher", lambda: publisher(doi, out)))
        routes.append(("discovery", lambda: discovery(r["title"], out)))
        notes, got = [], None
        for name_, fn in routes:
            before = downloads_now()
            res = fn()
            if res.startswith("ok") and out.exists() and out.read_bytes()[:4] == b"%PDF":
                take_download(before, r["title"], out, keep=False)  # drop a stray copy Chrome also saved
                got = (name_, res)
                break
            if take_download(before, r["title"], out):
                got = (name_, f"ok via Chrome download ({res[:60]})")
                break
            notes.append(res)
        if got:
            ok = title_ok(out, r["title"])
            pages = (re.search(r"Pages:\s+(\d+)", sh(["pdfinfo", str(out)], 30)[1]) or [None, "?"])[1]
            with open(PRE / "INDEX.tsv", "a") as f:
                f.write("\t".join([name, "", a["merged_id"], got[1], f"via {got[0]} (user's Chrome)", pages,
                                   "ok" if ok else "CHECK"]) + "\n")
            a.update(access="prefetched", file=name, note=f"browser: {got[1]}" + ("" if ok else "; title not on p1-3"))
        else:
            out.unlink(missing_ok=True)
            a["note"] = " | ".join(notes)[:300]
        with open(ACC, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(acc[0]), delimiter="\t")
            w.writeheader()
            w.writerows(acc)
        print(f"{'OK  ' if got else 'MISS'} {a['merged_id']:40} {a['note'][:110]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
