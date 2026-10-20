#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Get the bytes of a paper's file for a set of records; claim.py checks and files them. Judging pages is the agent's.

  --via http      for each record, its `links` (fulltext_links.py) of --version (default published) that do not
                  need a browser, in order: a plain GET; a PDF goes to claim.py. One try line per link. The run goes
                  on through every record.
  --via page      for each record, in the browser session (--session, default p2z; the window opens in the
                  background): open --start (one record only) or https://doi.org/<DOI> (else item.url), read the
                  PDF link the page declares (citation_pdf_url), and request it inside the page with the page's
                  cookies. When the page sits behind the institution's proxy (the host is the link's host with
                  dots as dashes under the config's institution.proxy) or the link is plain http on an https page,
                  the request goes to the same path on the current origin. A refused request (403, HTML, a
                  cross-origin redirect) is followed by opening the link in the tab, as a click would: Chrome
                  downloads it (claim.py picks it up from Downloads) or shows a pdf.js viewer (its bytes are read).
                  The first record that yields no file stops the run: the tab stays on that page, and stdout says
                  {"code": "stopped", "slug", "why": no_pdf_link | refused | no_start | error, "url", "title"}.
                  The script never decides what such a page is (a login, a missing subscription, an error page):
                  the agent looks, acts, then reruns the same command, which goes on from there.
  --via discovery for each record, the library's discovery system (the config's institution.discovery: a Primo search
                  URL): search the title, take the results that carry this title (or one of alt_titles; arXiv
                  records last), open each one's full record and its "Get PDF" links, which lead to an aggregator
                  (ProQuest and the like) through the institution's proxy: a pdf.js viewer's bytes, or a download.
                  Only the discovery system's own full-text links are followed. No result with this title ->
                  logged as not_in_discovery and the run goes on; results but no file -> stopped on that page for
                  the agent. No institution.discovery in the config -> each record is logged as no_discovery and
                  stdout says to ask the user for their library's search page.
  --via viewer    one record: the pdf.js viewer in the session's current tab (ProQuest and the like); its bytes.
  --via snapshot  for each record, the article page's HTML (filed as <slug>.html, checked like a PDF): open --start
                  or https://doi.org/<DOI>; the page that arrives is checked like any file (a login page is not
                  the article); --current takes the current tab of the session for one record instead.
  --wait          one record, at a gate: read the session's current tab and the record's file every 10 s, nothing
                  else (no navigation), until the file has arrived ({"code": "arrived"}, exit 0: claim.py --watch,
                  or --downloads, filed it, whoever downloaded it), the page shows --until TEXT (text or CSS
                  selector), or without --until its URL or title changes ({"code": "passed"}, exit 0), or --timeout
                  seconds (default 300) pass: {"code": "gate_timeout"}, exit 1, logged as this pass's try by --via.
                  --for file waits for the file alone (the last pass, with the user at the page): the page is not
                  read, and a timeout is {"code": "timeout"}, exit 1, not logged.
                  A user who logs in from another window changes nothing in this tab: their word, or the file, ends
                  the wait.

Windows open in the background (--window foreground for pages the user should see: the last pass). Before each
record, and before a page route stops, the record's file is looked for again (and Downloads scanned when
--downloads is given): a file the watcher filed meanwhile — the user's download included — skips the record.

Records are skipped when they already have a file (records/<slug>.pdf, .accepted.pdf, .preprint.pdf, .html) or
when this pass already tried them by this route: <work>/fetch.jsonl holds a try line for (slug, --pass, --via,
and for http --version) whose result is not "stopped". A --start run (one record, a page the agent chose) is
never skipped and never counts as the route's try, so `--via page --start <PMC page>` leaves the publisher's page
to the plain `--via page` run. --verdict RESULT (one record) records the agent's own conclusion for it in that
pass and route (no_access, gate_timeout, no_pdf, ...) without fetching, so a rerun goes past it and the report
shows it.

Every try is one line appended to <work>/fetch.jsonl: {"event": "try", "slug", "pass", "via", "url", "result",
"at", "note"?}; result: ok | wrong_file (the check failed: claim.py moved it to unverified/) | not_pdf | no_link |
http_<n> | network_error | stopped | the agent's verdict. Fetched bytes go to <work>/inbox/ and through claim.py
--file (subprocess). The work directory is the parent of the records' directory. Requests to one host are spaced
(1 s; medRxiv / bioRxiv 10 s; full text through the institution's proxy or discovery system 15 s,
PAPER_TO_ZOTERO_INSTITUTION_GAP) inside this process. Exit 0 = the run went through (records may still lack a file:
see the lines), 1 = stopped at a record, 2 = cannot run (no opencli, records in different work directories).
"""

import argparse
import base64
import difflib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLAIM_SCRIPT = HERE / "claim.py"
STEM_FILES = (".pdf", ".accepted.pdf", ".preprint.pdf", ".supplement.pdf", ".html")
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
# Seconds between requests to one host in this process. "institution" is every full-text request made through the
# institution's subscriptions (a proxied page's PDF, a discovery system's Get PDF): licences forbid systematic
# downloading, and a proxy that sees too many suspends the institution's account, not just this browser.
PACE = {"www.medrxiv.org": 10.0, "www.biorxiv.org": 10.0,
        "institution": float(os.environ.get("PAPER_TO_ZOTERO_INSTITUTION_GAP", "15"))}
CHUNK = 1_000_000            # base64 characters per eval read
OPEN_TIMEOUT = 60
EVAL_TIMEOUT = 120
DOWNLOAD_WAIT = float(os.environ.get("PAPER_TO_ZOTERO_DOWNLOAD_WAIT", "25"))   # seconds for a download to be filed
VIEWER_WAIT = float(os.environ.get("PAPER_TO_ZOTERO_VIEWER_WAIT", "20"))
WAIT_STEP = float(os.environ.get("PAPER_TO_ZOTERO_WAIT_STEP", "10"))            # --wait: seconds between looks
DISCOVERY_WAIT = float(os.environ.get("PAPER_TO_ZOTERO_DISCOVERY_WAIT", "30"))  # seconds for results / links to render
MAX_BYTES = 200 * 1024 * 1024

INFO_JS = r"""/*p2z:info*/(()=>{const m=(n)=>{const e=document.querySelector('meta[name="'+n+'"]');return e&&e.content?e.content:null};
return {href:location.href,title:document.title||'',pdf:m('citation_pdf_url'),mark:window.__p2z_mark||null}})()"""
MARK_JS = "/*p2z:mark*/(()=>{window.__p2z_mark='__TOKEN__';return location.href})()"
FETCH_JS = r"""/*p2z:fetch*/(async()=>{try{const r=await fetch(__URL__,{credentials:'include'});
const ct=r.headers.get('content-type')||'';const b=new Uint8Array(await r.arrayBuffer());
const h=String.fromCharCode.apply(null,b.subarray(0,1024));const pdf=h.indexOf('%PDF-')>=0;let n=0;
if(pdf){let s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode.apply(null,b.subarray(i,i+32768));
window.__p2z_b64=btoa(s);n=window.__p2z_b64.length}
return {status:r.status,ct:ct,url:r.url,size:b.length,pdf:pdf,b64len:n}}catch(e){return {error:String(e)}}})()"""
HTML_JS = r"""/*p2z:html*/(()=>{const h='<!DOCTYPE html>\n'+document.documentElement.outerHTML;
const b=new TextEncoder().encode(h);let s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode.apply(null,b.subarray(i,i+32768));
window.__p2z_b64=btoa(s);return {size:b.length,b64len:window.__p2z_b64.length,href:location.href}})()"""
VIEWER_FIND = r"""const W=[window];for(const f of document.querySelectorAll('iframe,frame')){try{if(f.contentWindow&&f.contentWindow.document)W.push(f.contentWindow)}catch(e){}}
let A=null;for(const w of W){try{if(w.PDFViewerApplication){A=w.PDFViewerApplication;break}}catch(e){}}"""
VIEWER_READY_JS = "/*p2z:viewer-ready*/(()=>{" + VIEWER_FIND + "return {app:!!A,ready:!!(A&&A.pdfDocument)}})()"
VIEWER_DATA_JS = ("/*p2z:viewer-data*/(async()=>{try{" + VIEWER_FIND +
                  r"""if(!A||!A.pdfDocument)return {pdf:false,error:'no document'};const d=await A.pdfDocument.getData();
const b=d instanceof Uint8Array?d:new Uint8Array(d);let s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode.apply(null,b.subarray(i,i+32768));
window.__p2z_b64=btoa(s);return {pdf:true,size:b.length,b64len:window.__p2z_b64.length}}catch(e){return {pdf:false,error:String(e)}}})()""")
WAIT_JS = r"""/*p2z:wait*/(()=>{const u=__UNTIL__;let found=false;if(u){try{found=!!document.querySelector(u)}catch(e){}
found=found||((document.body&&document.body.innerText)||'').indexOf(u)>=0}
return {href:location.href,title:document.title||'',found:found}})()"""
RESULTS_JS = r"""/*p2z:results*/(()=>{const t=document.body?document.body.innerText:'';
const a=[...document.querySelectorAll('a[href*="fulldisplay"]')].map(x=>({title:(x.innerText||'').trim(),href:x.href}));
return {done:a.length>0||/No records found/i.test(t),results:a}})()"""
LINKS_JS = r"""/*p2z:links*/(()=>{const a=[...document.querySelectorAll('a[href]')].map(x=>({text:(x.innerText||
x.getAttribute('aria-label')||'').trim().replace(/\s+/g,' '),href:x.href}));
return {pdf:a.filter(x=>/^Get PDF/i.test(x.text)).map(x=>x.href),
online:a.filter(x=>/uresolver/i.test(x.href)||/^Read online/i.test(x.text)).length}})()"""
CHUNK_JS = "/*p2z:chunk*/(()=>{const s=window.__p2z_b64;return typeof s==='string'?s.slice(__A__,__B__):null})()"
CLEAR_JS = "/*p2z:clear*/(()=>{delete window.__p2z_b64;return true})()"


class Stop(Exception):
    def __init__(self, code, hint, **extra):
        super().__init__(code)
        self.code, self.hint, self.extra = code, hint, extra


def log(msg):
    print(msg, file=sys.stderr)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def host_of(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


# ------------------------------------------------------------------ work directory and log

class Run:
    def __init__(self, args, entries):
        self.args, self.entries = args, entries
        works = {p.resolve().parent.parent for p, _ in entries}
        if len(works) != 1:
            raise Stop("mixed_work_dirs", "pass records of one work directory", work_dirs=sorted(map(str, works)))
        self.work = works.pop()
        self.inbox = self.work / "inbox"
        self.last = {}
        inst = self.config_institution()
        proxy, discovery = inst.get("proxy"), inst.get("discovery")
        self.proxy = proxy.strip().lower().lstrip(".") if isinstance(proxy, str) and proxy.strip() else None
        self.discovery = discovery.strip() if isinstance(discovery, str) and discovery.strip() else None

    def config_institution(self):
        path = Path(os.environ.get("PAPER_TO_ZOTERO_CONFIG") or Path.home() / ".config" / "paper-to-zotero" / "config.json")
        try:
            inst = json.loads(path.read_text(encoding="utf-8")).get("institution") or {}
        except (OSError, ValueError, AttributeError):
            inst = {}
        return inst if isinstance(inst, dict) else {}

    def file_of(self, slug):
        return next((slug + s for s in STEM_FILES if (self.work / "records" / (slug + s)).is_file()), None)

    def has_file(self, slug):
        return self.file_of(slug) is not None

    def arrived(self, slug):
        """Has the record's file arrived since the run began (the watcher, the user, Downloads)? Says so."""
        self.scan_downloads()
        name = self.file_of(slug)
        if name:
            print(json.dumps({"slug": slug, "code": "skipped", "reason": "has_file", "file": name}), flush=True)
        return name is not None

    def tried(self):
        """Slugs with a try line for this pass and route (http: and version) whose result is not 'stopped'."""
        done = set()
        try:
            with open(self.work / "fetch.jsonl", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if (isinstance(obj, dict) and obj.get("event") == "try" and obj.get("pass") == self.args.pass_
                            and obj.get("via") == self.args.via and obj.get("result") != "stopped"
                            and not obj.get("start")
                            and (self.args.via != "http" or obj.get("version", "published") == self.args.version)):
                        done.add(obj.get("slug"))
        except OSError:
            pass
        return done

    def log_try(self, slug, url, result, **extra):
        line = {"event": "try", "slug": slug, "pass": self.args.pass_, "via": self.args.via,
                "version": self.args.version if self.args.via == "http" else None, "start": self.args.start,
                "url": url, "result": result, **extra, "at": now_iso()}
        line = {k: v for k, v in line.items() if v is not None}
        data = (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8")
        fd = os.open(self.work / "fetch.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        print(json.dumps(line, ensure_ascii=False))

    def claim(self, slug, data, url, version, html=False):
        """Bytes -> inbox -> claim.py --file -> "ok" | "wrong_file" | "stray"."""
        self.inbox.mkdir(exist_ok=True)
        path = self.inbox / f"{slug}.{self.args.via}.{'html' if html else 'pdf'}"
        path.write_bytes(data)
        argv = [sys.executable, str(CLAIM_SCRIPT), "--work", str(self.work), "--file", str(path), "--slug", slug,
                "--via", self.args.via, "--source", url]
        if version:
            argv += ["--version", version]
        done = subprocess.run(argv, capture_output=True, text=True, timeout=600)
        rows = [json.loads(line) for line in done.stdout.splitlines() if line.startswith("{")]
        if done.returncode == 2 or not rows:
            raise Stop("claim_failed", "claim.py could not check the file", detail=rows[-1] if rows else done.stderr[-400:])
        result = rows[-1].get("result")
        return {"claimed": "ok", "unverified": "wrong_file"}.get(result, result or "error"), rows[-1].get("code")

    def scan_downloads(self):
        if self.args.downloads:
            subprocess.run([sys.executable, str(CLAIM_SCRIPT), "--work", str(self.work), "--scan", "--downloads",
                            self.args.downloads], capture_output=True, text=True, timeout=600)

    def wait_for_file(self, slug, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.scan_downloads()
            if self.has_file(slug):
                return True
            time.sleep(1.0)
        self.scan_downloads()
        return self.has_file(slug)

    def pace(self, host):
        wait = self.last.get(host, 0.0) + PACE.get(host, 1.0) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.last[host] = time.monotonic()


def slug_of(path, rec):
    return rec.get("slug") if isinstance(rec.get("slug"), str) and rec.get("slug") else path.stem


def start_url(rec, override):
    if override:
        return override
    item = rec.get("item") if isinstance(rec.get("item"), dict) else {}
    doi = item.get("DOI") if isinstance(item.get("DOI"), str) and item.get("DOI").strip() else None
    if doi:
        return "https://doi.org/" + urllib.parse.quote(doi.strip(), safe="/")
    url = item.get("url")
    return url.strip() if isinstance(url, str) and url.strip() else None


# ------------------------------------------------------------------ http

def http_route(run, todo):
    for path, rec, slug in todo:
        if run.arrived(slug):
            continue
        links = [l for l in rec.get("links") or [] if isinstance(l, dict) and l.get("version") == run.args.version
                 and l.get("needs_browser") is not True and isinstance(l.get("url"), str)]
        if not links:
            run.log_try(slug, None, "no_link", note=f"no {run.args.version} link that plain HTTP can fetch")
            continue
        for link in links:
            if run.has_file(slug):
                break
            url = link["url"]
            run.pace(host_of(url))
            try:
                req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept": "application/pdf,*/*"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read(MAX_BYTES)
            except urllib.error.HTTPError as e:
                run.log_try(slug, url, f"http_{e.code}")
                continue
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                run.log_try(slug, url, "network_error", note=str(getattr(e, "reason", e))[:120])
                continue
            if not data.lstrip()[:5] == b"%PDF-":
                run.log_try(slug, url, "not_pdf")
                continue
            result, code = run.claim(slug, data, url, link["version"])
            run.log_try(slug, url, result, check=code)
            if result == "ok":
                break
    return 0


# ------------------------------------------------------------------ browser

class Browser:
    def __init__(self, args):
        self.session, self.window = args.session, args.window

    def run(self, *args, timeout=EVAL_TIMEOUT, window=False):
        argv = ["opencli", "browser", self.session, *args] + (["--window", self.window] if window else [])
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            raise Stop("no_opencli", "opencli is not on PATH; install it, or use --via http")
        except subprocess.TimeoutExpired:
            return None, f"opencli {args[0]} timed out"
        if p.returncode != 0:
            return None, ((p.stderr or p.stdout).strip().splitlines() or [f"exit {p.returncode}"])[-1]
        return p.stdout, None

    def open(self, url):
        _, err = self.run("open", url, timeout=OPEN_TIMEOUT, window=True)
        return err

    def eval(self, js, timeout=EVAL_TIMEOUT):
        out, err = self.run("eval", js, timeout=timeout)
        if err is not None:
            return None, err
        out = out.strip()
        try:
            return json.loads(out), None
        except ValueError:
            return out, None

    def read_b64(self, total):
        parts, start = [], 0
        while start < total:
            out, err = self.run("eval", CHUNK_JS.replace("__A__", str(start)).replace("__B__", str(start + CHUNK)))
            chunk = (out or "").strip()
            if err is not None or not chunk or chunk == "null":
                return None
            parts.append(chunk)
            start += CHUNK
        self.run("eval", CLEAR_JS, timeout=30)
        try:
            return base64.b64decode("".join(parts))
        except ValueError:
            return None


def proxied(current, link_host, proxy):
    """Is `current` the link host behind the proxy (dots as dashes, doubled dashes for real ones, then .<proxy>)?"""
    if not proxy or not current or current == link_host:
        return False
    return current in {f"{link_host.replace('-', '--').replace('.', '-')}.{proxy}", f"{link_host.replace('.', '-')}.{proxy}"}


def request_url(link, page_href, proxy):
    """The URL to fetch inside the page: the same path on the current origin when the page is the proxied form of the
    link's host, or when the link is plain http on the same host of an https page; else the link itself."""
    link = urllib.parse.urljoin(page_href, link)
    page, target = urllib.parse.urlsplit(page_href), urllib.parse.urlsplit(link)
    cur, lhost = (page.hostname or "").lower(), (target.hostname or "").lower()
    if proxied(cur, lhost, proxy) or (cur == lhost and page.scheme == "https" and target.scheme == "http"):
        return urllib.parse.urlunsplit((page.scheme, page.netloc, target.path, target.query, ""))
    return link


def read_viewer(b, wait):
    """The pdf.js viewer's document in the current tab -> bytes or None."""
    deadline = time.monotonic() + wait
    while True:
        state, err = b.eval(VIEWER_READY_JS)
        if err is None and isinstance(state, dict) and state.get("ready"):
            break
        if time.monotonic() >= deadline:
            return None
        time.sleep(1.0)
    meta, err = b.eval(VIEWER_DATA_JS)
    if err is not None or not isinstance(meta, dict) or not meta.get("pdf"):
        return None
    return b.read_b64(int(meta.get("b64len") or 0))


def stop(run, slug, why, url, title, note=None):
    run.log_try(slug, url, "stopped", why=why, note=note)
    print(json.dumps({"code": "stopped", "slug": slug, "why": why, "url": url, "title": title,
                      "hint": "the tab stays on this page: look at it (state / screenshot), act, then rerun the same "
                              "command; record a conclusion with --verdict"}, ensure_ascii=False))
    return 1


def page_route(run, todo):
    b = Browser(run.args)
    for path, rec, slug in todo:
        if run.arrived(slug):
            continue
        url = start_url(rec, run.args.start)
        if not url:
            return stop(run, slug, "no_start", None, None, "the record has neither item.DOI nor item.url")
        if host_of(url) in PACE:
            run.pace(host_of(url))
        err = b.open(url)
        if err is not None:
            return stop(run, slug, "error", url, None, f"open: {err}")
        info, err = b.eval(INFO_JS)
        if err is not None or not isinstance(info, dict):
            return stop(run, slug, "error", url, None, f"eval: {err or info}")
        href, title = info.get("href") or url, info.get("title") or ""
        if not info.get("pdf"):
            if run.arrived(slug):
                continue
            return stop(run, slug, "no_pdf_link", href, title)
        link = urllib.parse.urljoin(href, info["pdf"])
        req = request_url(info["pdf"], href, run.proxy)
        if run.proxy and host_of(href).endswith("." + run.proxy):
            run.pace("institution")
        meta, err = b.eval(FETCH_JS.replace("__URL__", json.dumps(req)))
        if err is None and isinstance(meta, dict) and meta.get("pdf"):
            data = b.read_b64(int(meta.get("b64len") or 0))
            if data:
                result, code = run.claim(slug, data, link, None)
                run.log_try(slug, link, result, check=code)
                continue
        refused = (meta or {}).get("error") if isinstance(meta, dict) else err
        refused = refused or f"{(meta or {}).get('status')} {(meta or {}).get('ct')}".strip()
        # Refused inside the page: open the link in the tab, as a click would. A download leaves the tab where it was
        # (the mark set here survives); a navigation replaces the document (the mark is gone).
        token = f"{slug}-{time.time():.0f}"
        b.eval(MARK_JS.replace("__TOKEN__", token))
        b.open(req)
        if run.wait_for_file(slug, DOWNLOAD_WAIT):
            run.log_try(slug, link, "ok", note="downloaded by Chrome, filed from Downloads")
            continue
        after, _ = b.eval(INFO_JS)
        after = after if isinstance(after, dict) else {}
        if after.get("mark") != token:
            data = read_viewer(b, VIEWER_WAIT)
            if data:
                result, code = run.claim(slug, data, link, None)
                run.log_try(slug, link, result, check=code, note="read from the pdf.js viewer")
                continue
        if run.arrived(slug):
            continue
        return stop(run, slug, "refused", after.get("href") or req, after.get("title") or title, f"in-page: {refused}")
    return 0


def same_title(a, titles):
    norm = lambda t: " ".join(re.sub(r"[^0-9a-z]+", " ", str(t or "").casefold()).split())
    a = norm(a)
    return bool(a) and any(a == norm(t) or difflib.SequenceMatcher(None, a, norm(t)).ratio() >= 0.9 for t in titles if t)


def with_query(base, title):
    parts = urllib.parse.urlsplit(base)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != "query"]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode([("query", title)] + query)))


def poll(b, js, ready, seconds):
    deadline, last = time.monotonic() + seconds, None
    while True:
        value, err = b.eval(js)
        if err is None and isinstance(value, dict):
            last = value
            if ready(value):
                return value
        if time.monotonic() >= deadline:
            return last or {}
        time.sleep(1.5)


def discovery_route(run, todo):
    if not run.discovery:
        for path, rec, slug in todo:
            if not run.arrived(slug):
                run.log_try(slug, None, "no_discovery", note="institution.discovery is not set")
        print(json.dumps({"code": "no_discovery", "hint": "ask the user once for their library's discovery search page "
                          "(a Primo search URL) and add it to the config as institution.discovery"}))
        return 0
    b = Browser(run.args)
    for path, rec, slug in todo:
        if run.arrived(slug):
            continue
        item = rec.get("item") or {}
        titles = [item.get("title")] + [t for t in rec.get("alt_titles") or [] if isinstance(t, str)]
        if not item.get("title"):
            run.log_try(slug, None, "no_title")
            continue
        url = with_query(run.discovery, item["title"])
        err = b.open(url)
        if err is not None:
            return stop(run, slug, "error", url, None, f"open: {err}")
        results = poll(b, RESULTS_JS, lambda v: v.get("done"), DISCOVERY_WAIT).get("results") or []
        matches = list({r["href"]: r for r in results if same_title(r.get("title"), titles)}.values())
        matches.sort(key=lambda r: "arxiv" in r["href"].lower())
        if not matches:
            run.log_try(slug, url, "not_in_discovery", note=f"{len(results)} results, none with this title")
            continue
        tried_links = 0
        for m in matches:
            b.open(m["href"])
            for link in poll(b, LINKS_JS, lambda v: v.get("pdf") or v.get("online"), DISCOVERY_WAIT).get("pdf") or []:
                if run.has_file(slug):
                    break
                tried_links += 1
                run.pace("institution")
                b.open(link)
                data = read_viewer(b, VIEWER_WAIT)
                if data:
                    result, code = run.claim(slug, data, link, None)
                    run.log_try(slug, link, result, check=code, note="pdf.js viewer through the discovery system")
                elif run.wait_for_file(slug, 5):
                    run.log_try(slug, link, "ok", note="downloaded by Chrome, filed from Downloads")
            if run.has_file(slug):
                break
        if run.has_file(slug):
            continue
        info, _ = b.eval(INFO_JS)
        info = info if isinstance(info, dict) else {}
        return stop(run, slug, "refused" if tried_links else "no_pdf_link", info.get("href") or m["href"],
                    info.get("title"), f"{len(matches)} records with this title, {tried_links} PDF links tried")
    return 0


def viewer_route(run, todo):
    (path, rec, slug), = todo
    if run.arrived(slug):
        return 0
    b = Browser(run.args)
    data = read_viewer(b, VIEWER_WAIT)
    info, _ = b.eval(INFO_JS)
    href = info.get("href") if isinstance(info, dict) else None
    if not data:
        return stop(run, slug, "no_pdf_link", href, info.get("title") if isinstance(info, dict) else None,
                    "no pdf.js document in the current tab")
    result, code = run.claim(slug, data, href, None)
    run.log_try(slug, href, result, check=code)
    return 0


def snapshot_route(run, todo):
    b = Browser(run.args)
    for path, rec, slug in todo:
        if run.arrived(slug):
            continue
        url = None
        if not run.args.current:
            url = start_url(rec, run.args.start)
            if not url:
                run.log_try(slug, None, "no_start")
                continue
            err = b.open(url)
            if err is not None:
                run.log_try(slug, url, "error", note=f"open: {err}")
                continue
        meta, err = b.eval(HTML_JS)
        if err is not None or not isinstance(meta, dict) or not meta.get("b64len"):
            run.log_try(slug, url, "error", note=f"page HTML: {err or meta}")
            continue
        data = b.read_b64(int(meta["b64len"]))
        if not data:
            run.log_try(slug, url, "error", note="the page lost its HTML")
            continue
        href = meta.get("href") or url
        result, code = run.claim(slug, data, href, "snapshot", html=True)
        run.log_try(slug, href, result, check=code)
    return 0


def wait_at_gate(run, slug):
    """--wait: look at the current tab and the record's file every WAIT_STEP seconds, and nothing else."""
    b = Browser(run.args)
    js = WAIT_JS.replace("__UNTIL__", json.dumps(run.args.until))
    deadline = time.monotonic() + run.args.timeout
    first = seen = None
    while True:
        run.scan_downloads()
        name = run.file_of(slug)
        if name:
            print(json.dumps({"code": "arrived", "slug": slug, "file": name}))
            return 0
        info, err = b.eval(js) if run.args.for_ == "gate" else (None, "file only")
        if err is None and isinstance(info, dict):
            seen = (info.get("href"), info.get("title"))
            if info.get("found") or (not run.args.until and first is not None and seen != first):
                print(json.dumps({"code": "passed", "slug": slug, "url": seen[0], "title": seen[1]}, ensure_ascii=False))
                return 0
            first = first or seen
        left = deadline - time.monotonic()
        if left <= 0:
            break
        time.sleep(min(WAIT_STEP, left))
    if run.args.for_ == "file":
        print(json.dumps({"code": "timeout", "slug": slug, "waited": run.args.timeout}))
        return 1
    url, title = (seen or (None, None))
    run.log_try(slug, url, "gate_timeout", note=f"waited {run.args.timeout:g} s at the gate")
    print(json.dumps({"code": "gate_timeout", "slug": slug, "url": url, "title": title,
                      "hint": "leave this tab to the user, open a new tab for what follows, take the paper's next "
                              "route; other papers behind this gate skip it for the rest of the pass"},
                     ensure_ascii=False))
    return 1


ROUTES = {"http": http_route, "page": page_route, "discovery": discovery_route, "viewer": viewer_route,
          "snapshot": snapshot_route}


def load(paths):
    entries = []
    for raw in paths:
        path = Path(raw)
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise Stop("record_invalid", "every record file holds one JSON object", path=str(path), error=str(e))
        if not isinstance(rec, dict):
            raise Stop("record_invalid", "every record file holds one JSON object", path=str(path))
        entries.append((path, rec))
    return entries


def main():
    ap = argparse.ArgumentParser(description="Get a paper's file for each record (http, page, viewer, snapshot); claim.py "
                                             "checks and files it. See the module docstring.",
                                 epilog="examples:\n"
                                        "  uv run fetch.py --via http --pass 1 records/*.json\n"
                                        "  uv run fetch.py --via page --pass 1 --downloads DIR records/*.json\n"
                                        "  uv run fetch.py --via page --pass 1 --verdict no_access records/x.json\n"
                                        "  uv run fetch.py --via discovery --pass 1 --downloads DIR records/*.json\n"
                                        "  uv run fetch.py --via page --pass 1 --wait --downloads DIR records/x.json\n"
                                        "  uv run fetch.py --via page --pass 3 --wait --for file --downloads DIR records/x.json\n"
                                        "  uv run fetch.py --via page --pass 3 --window foreground --downloads DIR records/*.json\n"
                                        "  uv run fetch.py --via snapshot --pass 3 records/x.json",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("records", nargs="+", metavar="RECORD")
    ap.add_argument("--via", required=True, choices=sorted(ROUTES))
    ap.add_argument("--pass", dest="pass_", type=int, default=1, choices=(1, 2, 3), help="which pass of the chain (1-3)")
    ap.add_argument("--version", default="published", choices=("published", "accepted", "preprint", "unknown"),
                    help="--via http: the links of this version (default published)")
    ap.add_argument("--start", metavar="URL", help="--via page / snapshot, one record: the page to open")
    ap.add_argument("--current", action="store_true", help="--via snapshot, one record: the session's current tab")
    ap.add_argument("--session", default="p2z", help="opencli browser session (default p2z)")
    ap.add_argument("--downloads", metavar="DIR",
                    help="the browser's Downloads folder: scanned when a link is opened (else claim.py --watch must run)")
    ap.add_argument("--verdict", metavar="RESULT", help="one record: log the agent's conclusion for this pass and route")
    ap.add_argument("--wait", action="store_true",
                    help="one record: wait at the gate in the current tab until its file arrives or the page changes")
    ap.add_argument("--until", metavar="TEXT", help="with --wait: text or CSS selector only the passed gate shows")
    ap.add_argument("--for", dest="for_", choices=("gate", "file"), default="gate",
                    help="with --wait: gate (default: the file, or the page passing) or file (the file alone)")
    ap.add_argument("--timeout", type=float, default=300.0, help="with --wait: seconds (default 300)")
    ap.add_argument("--window", choices=("background", "foreground"), default="background",
                    help="where pages open (default background; foreground for the last pass, with the user)")
    args = ap.parse_args()
    if (args.start or args.current or args.verdict or args.wait or args.via == "viewer") and len(args.records) != 1:
        ap.error("--start, --current, --verdict, --wait and --via viewer take exactly one record")
    if args.wait and args.verdict:
        ap.error("--wait and --verdict are two different calls")
    try:
        run = Run(args, load(args.records))
        if args.verdict:
            path, rec = run.entries[0]
            run.log_try(slug_of(path, rec), None, args.verdict, by="agent")
            sys.exit(0)
        if args.wait:
            path, rec = run.entries[0]
            sys.exit(wait_at_gate(run, slug_of(path, rec)))
        tried = run.tried()
        todo = []
        for path, rec in run.entries:
            slug = slug_of(path, rec)
            if run.file_of(slug):
                print(json.dumps({"slug": slug, "code": "skipped", "reason": "has_file", "file": run.file_of(slug)}))
            elif slug in tried and not (args.via == "viewer" or args.current or args.start):
                print(json.dumps({"slug": slug, "code": "skipped", "reason": "tried", "pass": args.pass_, "via": args.via}))
            else:
                todo.append((path, rec, slug))
        sys.exit(ROUTES[args.via](run, todo) if todo else 0)
    except Stop as e:
        print(json.dumps({"code": e.code, "hint": e.hint, **e.extra}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
