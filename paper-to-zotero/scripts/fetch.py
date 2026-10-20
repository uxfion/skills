#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Walk one pass of the chain for the records without a file: each route over all of them, then the next.

  route       its candidates                                                                   SKILL.md's chain
  open        the record's links of the published version, then those of unknown version      1
  publisher   https://doi.org/<DOI> (else item.url), the papers grouped by publisher           2
  discovery   the paper's records in the library's discovery system (config institution.discovery)   3
  accepted    the links of the accepted manuscript                                            4
  preprint    the links of the preprint                                                       5
  snapshot    the article page's HTML, filed as <slug>.html (only with --route: the last pass)

A paper stops at the first file that passes the check. A candidate that needs no browser (needs_browser false or
unknown) is first asked over plain HTTP; what is not a PDF goes to the browser (the opencli session in run.json, a
background window, --window foreground for the last pass). On a page the browser takes the PDF the page itself offers
(p2zlib/browser.py: the declared PDF, an embedded document or viewer, a link saying PDF; three at most): requested
inside the page with its cookies (through the institution's proxy: the same path on the proxied host), else opened as
a click would — a download, a pdf.js viewer, or an HTML page that is looked through once more (IEEE's stamp.jsp). The
discovery route takes the result links whose text is the title (0.9 alike, arXiv records last) and works each page.
Each candidate's version goes along to the check and the file's name (an unknown version is set there by the file).

A candidate is tried once a pass: a try is (paper, pass, route, candidate) with its result — ok, wrong_file (the
check refused it: unverified/), stray, not_in_discovery, error — or the agent's verdict. A page the browser cannot get
past stops the whole command (exit 1), the tab left on it: a `stop` event {slug, pass, route, url, why: no_pdf_link |
refused, page, title}, no try, so a rerun asks that page again. The agent looks, acts, and either reruns the same
command or records a verdict.
  --verdict V            the agent's conclusion on the paper's last stop (one record); with --route R: on the whole
                         route for the records given (the papers behind a gate that timed out, a page nobody passes)
  --start URL [--version V]  one record: a candidate the agent found (a PMC page, a repository); never the route's try
Verdicts (VERDICTS below, the one table): no_access, no_pdf, gate_timeout, proxy_unconfigured, site_blocked,
not_public, skipped_by_user. Before each candidate the record's file is looked for (the watcher may have filed it;
while no watcher runs, this command scans Downloads itself). Requests to one host keep their gap (web.GAPS; full text
through the institution 15 s).

stdout: the try, stop and skip lines as they happen, then {"summary": {records, with_file, routes, stopped?}}.
Exit 0 = the pass went through (papers may still lack a file); 1 = stopped on a page; 2 = cannot run (no opencli,
records of two work directories, no pdftotext).

Examples:
  uv run scripts/fetch.py --pass 1 <work>/records/*.json
  uv run scripts/fetch.py --pass 1 --verdict no_access <work>/records/<slug>.json
  uv run scripts/fetch.py --pass 1 --start https://pmc.ncbi.nlm.nih.gov/articles/PMC123/ <work>/records/<slug>.json
  uv run scripts/fetch.py --pass 3 --route snapshot <work>/records/<slug>.json
"""
import os
import time
import urllib.parse
from pathlib import Path

from p2zlib import cli, config, paper, run, verify, web
from p2zlib.browser import Browser

ROUTES = ("open", "publisher", "discovery", "accepted", "preprint")
VERDICTS = {
    "no_access": "the institution has no access to it",
    "no_pdf": "the page offers no PDF",
    "gate_timeout": "a gate nobody passed in time",
    "proxy_unconfigured": "the proxy does not serve this host (Host Needed)",
    "site_blocked": "the site blocks this browser",
    "not_public": "not public (withdrawn, embargoed, not out yet)",
    "skipped_by_user": "the user said to skip it",
}
PAGE_CANDIDATES = 3   # tried on one page at most
CLICK_WAIT = float(os.environ.get("PAPER_TO_ZOTERO_CLICK_WAIT", "25"))         # an opened link: to download or show a viewer
DISCOVERY_WAIT = float(os.environ.get("PAPER_TO_ZOTERO_DISCOVERY_WAIT", "30"))  # the results to render
MAX_BYTES = 200 * 1024 * 1024


class Stopped(Exception):
    def __init__(self, why, url, title=None, note=None):
        super().__init__(why)
        self.why, self.url, self.title, self.note = why, url, title, note


class Pass:
    def __init__(self, args, records):
        works = {run.Work.of(r.path).root for r in records}
        if len(works) != 1:
            raise cli.Stop("mixed_work_dirs", exit=cli.CANNOT, hint="Pass the records of one work directory.",
                           work_dirs=sorted(map(str, works)))
        self.args, self.records, self.work, self.route = args, records, run.Work(works.pop()), None
        self.pacer = web.Pacer(self.work)
        inst, settings = config.institution(), self.work.settings()
        self.proxy, self.discovery = inst["proxy"], inst["discovery"]
        dl = settings.get("downloads")
        self.scanner = run.Scanner(self.work, dl) if dl and Path(dl).is_dir() else None
        self.browser = Browser(settings.get("session") or "p2z", args.window)

    def log(self, event, **fields):
        line = self.work.append({"event": event, "pass": self.args.pass_, **fields})
        cli.emit(line)
        return line

    def has_file(self, slug):
        if self.scanner and not run.watcher_alive(self.work):
            self.scanner.scan()
        return self.work.file_of(slug) is not None

    def claim(self, rec, data, url, version, html=False):
        """Bytes -> inbox -> checked and filed -> (the try's result, {check: the check's code})."""
        self.work.inbox.mkdir(exist_ok=True)
        path = self.work.inbox / f"{rec.slug}.{self.route}.{'html' if html else 'pdf'}"
        path.write_bytes(data)
        event = run.claim(self.work, path, rec.slug, kind=version if version in paper.KINDS else None, source=url,
                          via=self.route)
        return {"claimed": "ok", "unverified": "wrong_file"}.get(event["result"], event["result"]), {"check": event.get("code")}

    def pace(self, url):
        host = web.host_of(url)
        key = web.INSTITUTION if self.proxy and web.is_proxy_host(host, self.proxy) else host
        if key in web.GAPS:
            try:
                self.pacer.wait(key)
            except web.Blocked:  # a script met a 429 there; the browser asks anyway, after the gap
                pass

    # ---- one candidate ----------------------------------------------------------------------------------------

    def get(self, rec, cand):
        """Try one candidate -> (result, extra fields); Stopped on a page the agent must look at."""
        url, version, note = cand["url"], cand.get("version"), None
        if cand.get("needs_browser") is not True:
            try:
                status, _, data, final = web.get(url, headers={"User-Agent": web.BROWSER_UA, "Accept": "application/pdf,*/*"},
                                                 pacer=self.pacer, timeout=60, max_bytes=MAX_BYTES)
                if status == 200 and data.lstrip()[:5] == b"%PDF-":
                    return self.claim(rec, data, final, version)
                note = f"http: {status}" if status != 200 else "http: not a PDF"
            except web.Blocked:
                note = "http: 429"
            except OSError as e:
                note = f"http: {e}"[:120]
        err = self.browser.open(url)
        if err:
            return "error", {"note": f"open: {err}"}
        return self.on_page(rec, version, note)

    def on_page(self, rec, version, note=None, depth=0):
        """The PDF the current page offers -> (result, extra); Stopped when it offers none that works."""
        b = self.browser
        info = b.find()
        if info.get("viewer"):
            data = b.viewer()
            if data:
                result, extra = self.claim(rec, data, info.get("href"), version)
                return result, {**extra, "note": "the page's pdf.js viewer"}
        tried = 0
        for cand in (info.get("candidates") or [])[:PAGE_CANDIDATES]:
            if self.has_file(rec.slug):
                return "ok", {"note": "filed from Downloads"}
            tried += 1
            got = self.click(rec, cand["url"], info.get("href") or "", version, depth)
            if got:
                return got
        if self.has_file(rec.slug):
            return "ok", {"note": "filed from Downloads"}
        after = b.find() or info
        raise Stopped("refused" if tried else "no_pdf_link", after.get("href") or info.get("href"), after.get("title"),
                      "; ".join(x for x in (note, f"{tried} PDF links tried" if tried else None) if x) or None)

    def click(self, rec, link, page_href, version, depth):
        """One PDF link: requested inside the page, else opened as a click would -> (result, extra), or None."""
        b, req = self.browser, request_url(link, page_href, self.proxy)
        self.pace(page_href)
        data, why = b.fetch(req)
        if data:
            return self.claim(rec, data, link, version)
        token = f"{rec.slug}-{time.time():.0f}"
        b.mark(token)
        b.open(req)
        deadline = time.monotonic() + CLICK_WAIT
        while True:
            if self.has_file(rec.slug):
                return "ok", {"note": "downloaded by Chrome, filed from Downloads"}
            now = b.find()
            if now and now.get("mark") != token:  # another document: a viewer, or a page to look through once
                if now.get("viewer"):
                    data = b.viewer()
                    if data:
                        result, extra = self.claim(rec, data, link, version)
                        return result, {**extra, "note": "read from the pdf.js viewer"}
                elif depth == 0 and now.get("candidates"):
                    try:
                        return self.on_page(rec, version, f"in-page: {why}", depth=1)
                    except Stopped:
                        return None
            if time.monotonic() >= deadline:
                return None
            time.sleep(1.0)

    # ---- routes -----------------------------------------------------------------------------------------------

    def candidates(self, rec, route):
        if route in ("open", "accepted", "preprint"):
            wanted = ("published", "unknown") if route == "open" else (route,)
            links = (rec.get("links") or {}).get("items") or []
            return sorted((dict(l) for l in links if isinstance(l, dict) and l.get("url") and l.get("version") in wanted),
                          key=lambda l: wanted.index(l["version"]))
        if route in ("publisher", "snapshot"):
            url = landing(rec)
            return [{"url": url, "version": None, "needs_browser": True}] if url else []
        title = rec.item.get("title")
        return [{"url": with_query(self.discovery, title), "version": None, "needs_browser": True}] if title else []

    def discover(self, rec, cand):
        """The paper's records among the discovery system's results, each page worked in turn."""
        b = self.browser
        err = b.open(cand["url"])
        if err:
            return "error", {"note": f"open: {err}"}
        titles = [t for t in [rec.item.get("title"), *(rec.get("alt_titles") or [])] if isinstance(t, str) and t]
        deadline, matches = time.monotonic() + DISCOVERY_WAIT, []
        while True:
            anchors = b.anchors().get("anchors") or []
            matches = list({a["href"]: a for a in anchors if max(paper.title_similarity(a["text"], t) for t in titles) >= 0.9}.values())
            if matches or time.monotonic() >= deadline:
                break
            time.sleep(1.5)
        if not matches:
            return "not_in_discovery", {"note": f"{len(anchors)} links, none with this title"}
        stopped = None
        for m in sorted(matches, key=lambda a: "arxiv" in a["href"].lower()):
            if b.open(m["href"]):
                continue
            try:
                return self.on_page(rec, None)
            except Stopped as s:
                stopped = s
        raise stopped or Stopped("error", cand["url"], note="no result page opened")

    def snapshot(self, rec, cand):
        err = self.browser.open(cand["url"])
        if err:
            return "error", {"note": f"open: {err}"}
        data, href = self.browser.html()
        if not data:
            return "error", {"note": "the page gave no HTML"}
        return self.claim(rec, data, href, "snapshot", html=True)

    def stop(self, rec, url, s):
        self.log("stop", slug=rec.slug, route=self.route, url=url, why=s.why, page=s.url, title=s.title, note=s.note)
        cli.emit({"slug": rec.slug, "code": "stopped", "route": self.route, "why": s.why, "url": s.url, "title": s.title,
                  "hint": "The tab stays on this page: look at it, act, then rerun the same command; or record your "
                          "conclusion with --verdict."})
        return cli.ACT

    def walk(self, routes):
        """The routes in turn over the records without a file -> the exit code."""
        for route in routes:
            self.route = route
            if route == "discovery" and not self.discovery:
                cli.emit({"code": "skipped", "route": route, "reason": "no_discovery",
                          "hint": "Ask the user once for their library's discovery search page; add it to the config as "
                                  "institution.discovery."})
                continue
            todo = [r for r in self.records if not self.work.file_of(r.slug)]
            if route == "publisher":  # one publisher's papers together
                todo.sort(key=lambda r: paper.doi_of(r.item).split("/")[0])
            get = {"discovery": self.discover, "snapshot": self.snapshot}.get(route, self.get)
            for rec in todo:
                tries = [e for e in self.work.events("try") if e.get("slug") == rec.slug
                         and e.get("pass") == self.args.pass_ and e.get("route") == route]
                if any(t.get("url") is None for t in tries):
                    continue  # the agent closed this route for the paper in this pass
                for cand in self.candidates(rec, route):
                    if self.has_file(rec.slug):
                        cli.emit({"slug": rec.slug, "code": "skipped", "reason": "has_file"})
                        break
                    if any(t.get("url") == cand["url"] for t in tries):
                        continue
                    try:
                        result, extra = get(rec, cand)
                    except Stopped as s:
                        return self.stop(rec, cand["url"], s)
                    self.log("try", slug=rec.slug, route=route, url=cand["url"], version=cand.get("version"),
                             result=result, **extra)
                    if result == "ok":
                        break
        return cli.OK


def landing(rec):
    doi, url = paper.doi_of(rec.item, url=False), rec.item.get("url")
    if doi:
        return f"https://doi.org/{urllib.parse.quote(doi, safe='/')}"
    return url.strip() if isinstance(url, str) and url.strip() else None


def with_query(base, title):
    parts = urllib.parse.urlsplit(base)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != "query"]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode([("query", title)] + query)))


def request_url(link, page_href, proxy):
    """The url to request inside the page: the same path on the page's origin when the page is the link's host behind
    the proxy, or the link is plain http on the https page's own host; else the link."""
    link = urllib.parse.urljoin(page_href, link)
    page, target = urllib.parse.urlsplit(page_href), urllib.parse.urlsplit(link)
    cur, own = (page.hostname or "").lower(), (target.hostname or "").lower()
    behind = bool(proxy and cur != own and web.original_host(cur, proxy) == own)
    if behind or (cur == own and page.scheme == "https" and target.scheme == "http"):
        return urllib.parse.urlunsplit((page.scheme, page.netloc, target.path, target.query, ""))
    return link


def verdict(walk, rec, args):
    """--verdict: the agent's conclusion, logged as this pass's try."""
    if args.route or args.start:
        return walk.log("try", slug=rec.slug, route="start" if args.start else args.route, url=args.start,
                        result=args.verdict, by="agent")
    stops = [e for e in walk.work.events("stop") if e.get("slug") == rec.slug and e.get("pass") == args.pass_]
    if not stops:
        raise cli.Stop("nothing_stopped", hint="This paper has not stopped in this pass: name the route with --route.")
    return walk.log("try", slug=rec.slug, route=stops[-1]["route"], url=stops[-1]["url"], result=args.verdict, by="agent")


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("records", nargs="+", metavar="RECORD")
    p.add_argument("--pass", dest="pass_", type=int, default=1, choices=(1, 2, 3), help="which pass of the chain")
    p.add_argument("--route", choices=ROUTES + ("snapshot",), help="this route only")
    p.add_argument("--start", metavar="URL", help="one record: a candidate the agent found")
    p.add_argument("--version", choices=list(paper.KINDS), help="with --start: the version it is")
    p.add_argument("--verdict", choices=sorted(VERDICTS), help="the agent's conclusion (see above)")
    p.add_argument("--window", choices=("background", "foreground"), default="background",
                   help="where pages open (foreground: the last pass, with the user)")
    args = p.parse_args(argv)
    if (args.start or (args.verdict and not args.route)) and len(args.records) != 1:
        p.error("--start, and --verdict without --route, take exactly one record")
    if args.version and not args.start:
        p.error("--version goes with --start")

    def go():
        records = [run.read(path) for path in args.records]
        walk = Pass(args, records)
        if args.verdict:
            for rec in records:
                verdict(walk, rec, args)
            return cli.OK
        verify.require_pdftotext()
        if args.start:
            walk.route, rec = "start", records[0]
            try:
                result, extra = walk.get(rec, {"url": args.start, "version": args.version, "needs_browser": None})
            except Stopped as s:
                return walk.stop(rec, args.start, s)
            walk.log("try", slug=rec.slug, route="start", url=args.start, version=args.version, result=result, **extra)
            return cli.OK
        routes = [args.route] if args.route else list(ROUTES)
        code = walk.walk(routes)
        cli.emit({"summary": {"records": len(records), "with_file": sum(1 for r in records if walk.work.file_of(r.slug)),
                              "routes": routes, **({"stopped": True} if code == cli.ACT else {})}})
        return code

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
