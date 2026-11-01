#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Walk one pass of the chain for the results that still need their file: each route over all of them, then the next.

  route       its candidates                                                                   SKILL.md's chain
  open        the result's links of the published version, then those of unknown version      1
  publisher   https://doi.org/<DOI> (else the CSL's URL), the papers grouped by publisher      2
  discovery   the paper's records in the library's discovery system (config institution.discovery, a search
              URL with {title} where the title goes)                                          3
  accepted    the links of the accepted manuscript                                            4
  preprint    the links of the preprint                                                       5
  snapshot    the article page's HTML, filed as <slug>.html (only with --route: the last pass)

A paper stops at the first file that settles it (run.satisfied): a file of the version the result wants, or a file
whose version is not labelled yet; once labelled below the wanted version, the paper goes on down the chain when the
pass is run again. A candidate that needs no browser (needs_browser false or unknown) is first asked over plain HTTP;
what is not a PDF goes to the browser (the opencli session: --session, else run.json's; a background window,
--window foreground for the last pass). On a page the browser takes the PDF the page itself offers
(pflib/browser.py: the declared PDF, an embedded document or viewer, a link saying PDF; three at most, the next one
tried when a file is refused): requested inside the page with its cookies (through the institution's proxy: the same
path on the proxied host), else opened as a click would — a download, a pdf.js viewer, or an HTML page that is looked
through once more (IEEE's stamp.jsp). The discovery route takes the search's links whose text is the title (0.9
alike, arXiv records last) and works each page. Each candidate's version goes along to the check and the file's
name: the version it was wanted as. An arXiv link is fetched as its latest version (https://arxiv.org/pdf/<id>v<N>:
the vN identify recorded, versions.preprint.latest, else one request to arXiv's API for all of the pass's arXiv links).

Every file goes through the check (run.claim): pass -> filed; refused -> the next candidate; uncertain -> held, with a
`file` handoff, and the paper waits. Where fetch cannot get a PDF from a page — a sign-in, a challenge, no PDF link,
no record in the discovery search — it judges nothing: it writes a `page` handoff with what it saw, the paper waits on
that route, and the walk goes on with the others. The paper's agent works the page and hands back with
`--start <url> --session pf-<slug>`, or answers with a verdict (pf.py answer; run.VERDICTS). The bulk walk skips a
paper with an open page or file handoff, and a paper an answer holds on its route this pass (blocked, gate_timeout);
a run with --session or --start does not skip its paper. When the command ends, the fold gives each filed file
without a label a `label` handoff (settle.py) holding the host's word recorded at download — the page's title,
metadata and words around the paper's title, the link taken, arXiv's comment on the version — then the file's (page
1). The browser itself failing (OpenCLI's BROWSER_CONNECT) ends the pass with a `browser_down` handoff. Handoffs: pflib/run.py; pf.py todo lists
them, pf.py answer answers them.

A candidate is tried once a pass: a try is (paper, pass, route, candidate) with its result — ok, held, wrong_file,
error — or an agent's verdict on its page handoff. A page handoff is no try, so the paper's agent's rerun asks that
page again.
  --start URL [--version V]  one result: a candidate the paper's agent found or opened the way to (a page past a
                         sign-in, a PMC page, a repository); never the route's try
Before each candidate the result's file is looked for (the watcher may have filed it; while no watcher runs, this
command scans Downloads itself). Requests to one host keep their gap (web.GAPS; full text through the institution
15 s), in the machine's pace file.

stdout: the try and skip lines as they happen, one short line per page, file or browser_down handoff ({handoff, slug,
kind, taker, path}), then {"summary": {results, satisfied, handoffs: {kind: n}, routes}}: every open handoff of these
results, label handoffs included (pf.py todo lists them; --start prints no summary). When it ends it folds the
results it was given (and any other its scan of Downloads filed a file for) into their files and outcome, as
settle.py does. Exit 0 = the pass went through with nothing open; 1 = handoffs are open for the agent (or the browser
failed); 2 = cannot run (no opencli, results of two directories, no pdftotext).

Examples:
  uv run scripts/fetch.py --pass 1 <dir>/results/*.json
  uv run scripts/fetch.py --pass 1 --session pf-<slug> --start https://pmc.ncbi.nlm.nih.gov/articles/PMC123/ <dir>/results/<slug>.json
  uv run scripts/fetch.py --pass 3 --route snapshot <dir>/results/<slug>.json
"""
import os
import time
import urllib.parse
from pathlib import Path

from pflib import cli, config, paper, run, verify, web
from pflib.browser import Browser, BrowserDown

ROUTES = ("open", "publisher", "discovery", "accepted", "preprint")
PAGE_CANDIDATES = 3   # tried on one page at most
WORDS_BEFORE, WORDS_AFTER = 600, 900  # a page's words kept around the paper's title
PAGE_TEXT_CHARS = 4000                # of a page handed to an agent
CLICK_WAIT = float(os.environ.get("PAPER_FETCH_CLICK_WAIT", "20"))        # an opened page: to show a viewer or its PDF link
DOWNLOAD_WAIT = float(os.environ.get("PAPER_FETCH_DOWNLOAD_WAIT", "60"))  # the tab stayed, Chrome downloads: PMC took 45-60 s
DISCOVERY_WAIT = float(os.environ.get("PAPER_FETCH_DISCOVERY_WAIT", "30"))  # the results to render
MAX_BYTES = 200 * 1024 * 1024


class Stopped(Exception):
    """A page fetch could not get a PDF from: why, the page's url and title, what was tried."""

    def __init__(self, why, url, title=None, note=None):
        super().__init__(why)
        self.why, self.url, self.title, self.note = why, url, title, note


class Pass:
    def __init__(self, args, results):
        works = {run.Work.of(r.path).root for r in results}
        if len(works) != 1:
            raise cli.Stop("mixed_work_dirs", exit=cli.CANNOT, hint="Pass the results of one directory.",
                           work_dirs=sorted(map(str, works)))
        self.args, self.results, self.work, self.route = args, results, run.Work(works.pop()), None
        self.arxiv = None  # arXiv id -> arXiv's word on its latest version (arxiv_entry)
        self.pacer = web.Pacer(web.pace_path())
        inst, settings = config.institution(), self.work.settings()
        self.proxy, self.discovery = inst["proxy"], inst["discovery"]
        dl = settings.get("downloads")
        self.scanner = run.Scanner(self.work, dl) if dl and Path(dl).is_dir() else None
        self.filed = set()  # slugs a scan filed a file for
        self.browser = Browser(args.session or settings.get("session") or "pf", args.window)
        self.inner = None  # a reading page's own stop, kept for the outer page's handoff

    def log(self, event, **fields):
        line = self.work.append({"event": event, "pass": self.args.pass_, **fields})
        cli.emit(line)
        return line

    def scan(self):
        if self.scanner and not run.watcher_alive(self.work):
            self.filed.update(e["slug"] for e in self.scanner.scan() if e.get("slug"))

    def has_file(self, res):
        self.scan()
        return run.satisfied(self.work, res)

    def touched(self):
        """The results to fold when the command ends: those it was given, and any other a scan filed a file for."""
        given = {r.slug for r in self.results}
        return self.results + [run.read(self.work.results / f"{s}.json") for s in sorted(self.filed - given)
                               if (self.work.results / f"{s}.json").is_file()]

    def claim(self, res, data, url, version, html=False, page=None, link=None):
        """Bytes -> inbox -> checked and filed -> (the try's result: ok | held | wrong_file, {check}). `page` is the
        page the file came from (find()'s answer), `link` the candidate taken on it: evidence for the file's label."""
        self.work.inbox.mkdir(exist_ok=True)
        path = self.work.inbox / f"{res.slug}.{self.route}.{'html' if html else 'pdf'}"
        path.write_bytes(data)
        event = run.claim(self.work, path, res.slug, kind=version if version in paper.KINDS else None, source=url,
                          via=self.route, came=self.came(url, page, link), pass_=self.args.pass_)
        result = {"claimed": "ok", "held": "held", "refused": "wrong_file"}[event["result"]]
        if event.get("handoff"):
            self.announce(event["handoff"], res.slug, "file")
        return result, {"check": event.get("code")}

    def came(self, url, page=None, link=None):
        """How a file came, for its claim or arrival event: the route, the url (an arXiv one without a version as the
        latest version's, the one arXiv serves there), the version the agent named for a start page, the page and
        the link taken on it. An arXiv file's page is arXiv's word on its version, however its bytes came."""
        url = self.arxiv_url(url) if url and self.route != "snapshot" else url
        seen = {k: page[k] for k in ("href", "title", "meta", "words") if page.get(k)} if page else None
        page = self.arxiv_page(url) or seen
        return {"route": self.route, "url": url, "given": self.args.version if self.route == "start" else None,
                "page": page or None,
                "link": {k: link[k] for k in ("url", "why", "text", "near") if link.get(k)} if link else None}

    def downloaded_here(self, res, url, page=None, link=None):
        """A file Chrome downloaded on a link this command opened: its arrival noted -> the try's result."""
        run.note_arrival(self.work, res.slug, self.came(url, page, link))
        return "ok", {"note": "downloaded by Chrome, filed from Downloads"}

    def pace(self, url):
        """The gap before a request for full text: the institution's for anything through its proxy or its discovery
        system, else the host's own."""
        host = paper.host_of(url)
        key = web.INSTITUTION if self.route == "discovery" or (self.proxy and web.is_proxy_host(host, self.proxy)) else host
        if key in web.GAPS:
            try:
                self.pacer.wait(key)
            except web.Blocked:  # a script met a 429 there; the browser asks anyway, after the gap
                pass

    def announce(self, hid, slug, kind):
        cli.emit({"handoff": hid, "slug": slug, "kind": kind, "taker": run.HANDOFF_TAKERS[kind],
                  "path": str(self.work.handoffs / f"{hid}.json")})

    # ---- one candidate ----------------------------------------------------------------------------------------

    def get(self, res, cand):
        """Try one candidate -> (result, extra fields); Stopped on a page fetch cannot get a PDF from."""
        url, version, note = cand["url"], cand.get("version"), None
        if cand.get("needs_browser") is not True:
            try:
                status, _, data, final = web.get(url, headers={"User-Agent": web.BROWSER_UA, "Accept": "application/pdf,*/*"},
                                                 pacer=self.pacer, timeout=60, max_bytes=MAX_BYTES)
                if status == 200 and data.lstrip()[:5] == b"%PDF-":
                    return self.claim(res, data, final, version)
                note = f"http: {status}" if status != 200 else "http: not a PDF"
            except web.Blocked:
                note = "http: 429"
            except OSError as e:
                note = f"http: {e}"[:120]
        before = self.browser.document()
        err = self.browser.open(url)
        if err:
            return "error", {"note": f"open: {err}"}
        if self.downloaded(res, before):
            return self.downloaded_here(res, url)
        return self.on_page(res, version, note)

    def downloaded(self, res, before):
        """After an open: while the tab keeps the document it had (before), Chrome is downloading -> whether the
        paper got its file, within DOWNLOAD_WAIT; False at once when another document opened."""
        deadline = time.monotonic() + DOWNLOAD_WAIT
        while before is not None and time.monotonic() < deadline:
            if self.has_file(res):
                return True
            doc = self.browser.document()
            if doc is not None and doc != before:  # None: the page did not answer this time
                break
            time.sleep(1.0)
        return self.has_file(res)

    def on_page(self, res, version, note=None, depth=0, outer=None):
        """The PDF the current page offers -> (result, extra); Stopped when it offers none that works. `outer` is the
        page a reading page was reached from (IEEE's article page before its stamp.jsp): the page a file's evidence
        names is the first of the chain, the one that speaks of the paper."""
        b = self.browser
        info = b.find()
        if outer is None:
            info["words"] = self.page_words(res)
        shown = outer or info
        if info.get("viewer"):
            data = b.viewer()
            if data:
                result, extra = self.claim(res, data, info.get("href"), version, page=shown,
                                           link={"url": info.get("href"), "why": "viewer"})
                if result != "wrong_file":
                    return result, {**extra, "note": "the page's pdf.js viewer"}
        tried, page = 0, info.get("href") or ""
        for cand in (info.get("candidates") or [])[:PAGE_CANDIDATES]:
            if self.has_file(res):
                return "ok", {"note": "filed from Downloads"}
            if tried and page and (b.find().get("href") or "") != page:
                b.open(page)  # back on the page that offered the candidates: its origin, its cookies
            tried += 1
            got = self.click(res, cand, info, version, depth, shown)
            if got:
                return got
        if self.has_file(res):
            return "ok", {"note": "filed from Downloads"}
        after = b.find() or info
        inner, self.inner = self.inner, None
        raise Stopped("refused" if tried else "no_pdf_link", after.get("href") or info.get("href"), after.get("title"),
                      "; ".join(x for x in (note, f"{tried} PDF links tried" if tried else None,
                                            f"a reading page: {inner.why} at {inner.url}" if inner else None) if x)
                      or None)

    def click(self, res, cand, page, version, depth, shown=None):
        """One PDF link of a page: requested inside the page, else opened as a click would -> (result, extra), or None
        to try the next (nothing came, or the file was refused). `page` is the page the link is on; `shown`, the page
        the file's evidence names (on_page's)."""
        b, link, here = self.browser, cand["url"], page
        page = shown or page
        req = request_url(link, here.get("href") or "", self.proxy)
        self.pace(req)
        data, why = b.fetch(req)
        if data:
            got = self.claim(res, data, link, version, page=page, link=cand)
            return got if got[0] != "wrong_file" else None
        before = b.document()
        b.open(req)
        if self.downloaded(res, before):
            return self.downloaded_here(res, link, page, cand)
        deadline, now = time.monotonic() + CLICK_WAIT, {}
        while time.monotonic() < deadline:  # another document: a viewer, or a page to look through
            now = b.find()  # {}: the page did not answer this time (a redirect under way)
            if now and now.get("doc") == before:  # still the old document: nothing opened
                break
            if now.get("viewer"):
                data = b.viewer()
                if data:
                    got = self.claim(res, data, link, version, page=page, link=cand)
                    return (got[0], {**got[1], "note": "read from the pdf.js viewer"}) if got[0] != "wrong_file" else None
            elif depth == 0 and now.get("candidates"):
                try:
                    return self.on_page(res, version, f"in-page: {why}", depth=1, outer=page)
                except Stopped as s:
                    self.inner = s
                    return None
            if self.has_file(res):  # a page that downloads in the end
                return self.downloaded_here(res, link, page, cand)
            time.sleep(1.0)
        return None

    # ---- routes -----------------------------------------------------------------------------------------------

    def candidates(self, res, route):
        if route in ("open", "accepted", "preprint"):
            found = run.links_of(res)
            if found is None:  # none yet, or found for other ids than the result has now
                return []
            wanted = ("published", "unknown") if route == "open" else (route,)
            links = found.get("items") or []
            chosen = sorted((dict(l) for l in links if isinstance(l, dict) and l.get("url") and l.get("version") in wanted),
                            key=lambda l: wanted.index(l["version"]))
            return [{**l, "url": self.arxiv_url(l["url"])} for l in chosen]
        if route in ("publisher", "snapshot"):
            url = landing(res)
            return [{"url": url, "version": None, "needs_browser": True}] if url else []
        title = res.subject.title
        return [{"url": discovery_url(self.discovery, title), "version": None, "needs_browser": True}] if title else []

    def page_words(self, res):
        """The current page's words about the paper: its text around the paper's title, where a page puts its labels,
        dates, volume and issue (else its start), whitespace collapsed; None when the page gives no text."""
        text = self.browser.text().get("text") or ""
        if not text.strip():
            return None
        title = verify.normalize(res.subject.title)
        found = len(title) >= verify.MIN_TITLE_CHARS and title in verify.normalize(text)
        start = verify.title_span(text, title)[0] if found else 0
        return " ".join(text[max(0, start - WORDS_BEFORE):start + WORDS_AFTER].split()) or None

    def arxiv_entry(self, aid):
        """arXiv's word on its latest version of an id: {version, comment?, journal_ref?}, {} when arXiv gave none.
        The version and comment identify recorded for a result's own arXiv id (versions.preprint); for the rest, one
        request to arXiv's API for every arXiv link of this command's results (and this id), the first time one is
        asked for."""
        if self.arxiv is None:
            self.arxiv = {}
            for res in self.results:
                preprint = (res.get("versions") or {}).get("preprint") or {}
                own = res.subject.arxiv
                if own and preprint.get("latest"):
                    self.arxiv[own] = {"version": preprint["latest"], "comment": preprint.get("comment")}
            links = [l.get("url") for r in self.results if not run.satisfied(self.work, r)
                     for l in ((run.links_of(r) or {}).get("items") or []) if isinstance(l, dict)]
            ids = [paper.arxiv_link(u)[0] for u in links] + [aid]
            ids = list(dict.fromkeys(i for i in ids if i and i not in self.arxiv))
            for i, (entry, _) in web.arxiv_entries(ids, self.pacer).items() if ids else ():
                if entry.get("version"):
                    self.arxiv[i] = entry
        return self.arxiv.get(aid) or {}

    def arxiv_url(self, url):
        """An arXiv link as its latest version's PDF (https://arxiv.org/pdf/<id>v<N>), so the file's title can name
        its vN; any other url, one naming a version, or an id arXiv does not answer for: as it is."""
        aid, vn = paper.arxiv_link(url)
        version = self.arxiv_entry(aid).get("version") if aid and not vn else None
        return f"https://arxiv.org/pdf/{aid}{version}" if version else url

    def arxiv_page(self, url):
        """arXiv's page for the version an arXiv url names, as arXiv's API gives it: {href, words: its comment and
        journal reference}; None for any other url, or a version other than the latest (its comment is not known)."""
        aid, vn = paper.arxiv_link(url)
        entry = self.arxiv_entry(aid) if aid and vn else {}
        if not entry or entry.get("version") != vn:
            return None
        words = "; ".join(f"{name}: {entry[key]}" for key, name in (("comment", "Comments"), ("journal_ref", "Journal-ref"))
                          if entry.get(key))
        return {"href": f"https://arxiv.org/abs/{aid}{vn}", **({"words": words} if words else {})}

    def discover(self, res, cand):
        """The paper's records among the discovery system's results, each page worked in turn; Stopped with the search
        page when no link there is the paper's (signed out, another spelling, not held: the paper's agent looks)."""
        b = self.browser
        err = b.open(cand["url"])
        if err:
            return "error", {"note": f"open: {err}"}
        titles = [t for t in [res.subject.title, *res.subject.alt_titles] if isinstance(t, str) and t]
        deadline, matches = time.monotonic() + DISCOVERY_WAIT, []
        while True:
            anchors = b.anchors()
            matches = list({a["href"]: a for a in anchors if max(paper.title_similarity(a["text"], t) for t in titles) >= 0.9}.values())
            if matches or time.monotonic() >= deadline:
                break
            time.sleep(1.5)
        if not matches:
            page = b.text()
            raise Stopped("no_record", page.get("href") or cand["url"], page.get("title"),
                          f"{len(anchors)} links on the search page, none with this title")
        stopped = None
        for m in sorted(matches, key=lambda a: "arxiv" in a["href"].lower()):
            if b.open(m["href"]):
                continue
            deadline = time.monotonic() + DISCOVERY_WAIT
            while not (b.find().get("candidates") or time.monotonic() >= deadline):
                time.sleep(1.5)  # a discovery system renders its full-text links after the page
            try:
                return self.on_page(res, None)
            except Stopped as s:
                stopped = s
        raise stopped or Stopped("error", cand["url"], note="no result page opened")

    def snapshot(self, res, cand):
        err = self.browser.open(cand["url"])
        if err:
            return "error", {"note": f"open: {err}"}
        data, href = self.browser.html()
        if not data:
            return "error", {"note": "the page gave no HTML"}
        return self.claim(res, data, href, "snapshot", html=True, page={"href": href})

    def hand_page(self, res, url, s):
        """A page fetch cannot get a PDF from -> its `page` handoff's id (an open one for the same page and paper is
        reused): what fetch saw there, for the paper's agent."""
        same = next((h for h in run.open_handoffs(self.work, slug=res.slug)
                     if h["kind"] == "page" and h.get("route") == self.route and h.get("url") == url), None)
        if same:
            self.announce(same["id"], res.slug, "page")
            return same["id"]
        text = (self.browser.text().get("text") or "")[:PAGE_TEXT_CHARS]
        record = run.handoff(self.work, "page", res, pass_=self.args.pass_, route=self.route, url=url,
                             code=s.why, note=s.note, evidence={"page": {"href": s.url, "title": s.title},
                                                                "words": text or None})
        self.announce(record["id"], res.slug, "page")
        return record["id"]

    def walk(self, routes):
        """The routes in turn over the results that still need their file -> ACT when the browser failed, else OK."""
        self.routes = routes
        events = self.work.events()
        logged = {e.get("slug") for e in events if e.get("event") == "pass" and e.get("pass") == self.args.pass_}
        for res in self.results:  # from here on a download for it is filed, whoever starts it (run.wanted)
            if not run.satisfied(self.work, res, events) and res.slug not in logged:
                self.work.append({"event": "pass", "pass": self.args.pass_, "slug": res.slug})
        for res in self.results:
            if not run.satisfied(self.work, res, events) and run.links_of(res) is None:
                cli.emit({"slug": res.slug, "code": "not_prepared", "hint": "Its links are missing or were found for "
                          "other ids: run pf.py fulltext_links on it; until then only the page routes try it."})
        mine = bool(self.args.session)  # an agent's run on its own paper: open handoffs do not hold it
        paused = set()
        try:
            for route in routes:
                self.route = route
                if route == "discovery" and not (self.discovery and "{title}" in self.discovery):
                    cli.emit({"route": route, "code": "no_discovery", "hint": "The config's institution.discovery is "
                              "missing, or holds no {title}: ask the user once for their library's discovery search "
                              "page and write it as a search URL with {title} where the title goes (ready.py says how)."})
                    continue
                events = self.work.events()
                todo = [r for r in self.results if r.slug not in paused and not run.satisfied(self.work, r, events)
                        and not run.held_on_route(self.work, r.slug, self.args.pass_, events)
                        and (mine or not any(h["kind"] in ("page", "file")
                                             for h in run.open_handoffs(self.work, events, r.slug)))]
                if route == "publisher":  # one publisher's papers together
                    todo.sort(key=lambda r: (r.subject.doi or "").split("/")[0])
                get = {"discovery": self.discover, "snapshot": self.snapshot}.get(route, self.get)
                for res in todo:
                    tries = [e for e in self.work.events("try") if e.get("slug") == res.slug
                             and e.get("pass") == self.args.pass_ and e.get("route") == route]
                    for cand in self.candidates(res, route):
                        if self.has_file(res):
                            cli.emit({"slug": res.slug, "code": "skipped", "reason": "has_file"})
                            break
                        if any(t.get("url") == cand["url"] for t in tries):
                            continue
                        try:
                            result, extra = get(res, cand)
                        except Stopped as s:
                            self.hand_page(res, cand["url"], s)
                            paused.add(res.slug)
                            break
                        self.log("try", slug=res.slug, route=route, url=cand["url"], version=cand.get("version"),
                                 result=result, **extra)
                        if result == "held":
                            paused.add(res.slug)
                        if result in ("ok", "held"):
                            break
        except BrowserDown as e:
            record = run.handoff(self.work, "browser_down", note=str(e), pass_=self.args.pass_, route=self.route)
            self.announce(record["id"], None, "browser_down")
            cli.emit({"code": "browser_down", "hint": "The browser failed (OpenCLI could not reach Chrome): run "
                      "`opencli doctor`, restart the daemon if it says so, else ask the user to open Chrome; then "
                      "answer the handoff `resolved` and rerun.", "detail": str(e)})
            return cli.ACT
        return cli.OK


def landing(res):
    sub = res.subject
    if sub.doi:
        return f"https://doi.org/{urllib.parse.quote(sub.doi, safe='/')}"
    return sub.url


def discovery_url(template, title):
    """The discovery system's search for a title: the config's search URL with the title, URL-encoded, at {title}."""
    return template.replace("{title}", urllib.parse.quote_plus(title))


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


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("results", nargs="+", metavar="RESULT", help="result files: <dir>/results/<slug>.json")
    p.add_argument("--pass", dest="pass_", type=int, default=1, choices=(1, 2, 3), help="which pass of the chain")
    p.add_argument("--route", choices=ROUTES + ("snapshot",), help="this route only")
    p.add_argument("--start", metavar="URL", help="one result: a candidate the agent found or opened the way to")
    p.add_argument("--version", choices=list(paper.KINDS), help="with --start: the version it is")
    p.add_argument("--session", metavar="NAME", help="the opencli session (a paper's agent: pf-<slug>); default run.json's")
    p.add_argument("--window", choices=("background", "foreground"), default="background",
                   help="where pages open (foreground: the last pass, with the user)")
    args = p.parse_args(argv)
    if args.start and len(args.results) != 1:
        p.error("--start takes exactly one result")
    if args.version and not args.start:
        p.error("--version goes with --start")

    def one_pass(walk, results):
        verify.require_pdftotext()
        if not args.start:
            return walk.walk([args.route] if args.route else list(ROUTES))
        walk.route, res = "start", results[0]
        url = walk.arxiv_url(args.start)
        try:
            result, extra = walk.get(res, {"url": url, "version": args.version, "needs_browser": None})
        except Stopped as s:
            walk.hand_page(res, url, s)
            return cli.ACT
        except BrowserDown as e:
            record = run.handoff(walk.work, "browser_down", note=str(e), pass_=args.pass_, route="start")
            walk.announce(record["id"], None, "browser_down")
            return cli.ACT
        walk.log("try", slug=res.slug, route="start", url=url, version=args.version, result=result, **extra)
        return cli.OK

    def go():
        results, invalid = [], 0
        for path in args.results:
            try:
                results.append(run.read(path))
            except cli.Stop as stop:  # a file that is no result is its own line; the others go on
                cli.emit(stop.line(slug=Path(path).stem))
                invalid += 1
        if not results:
            return cli.ACT
        walk = Pass(args, results)
        try:
            code = one_pass(walk, results)
        finally:  # whatever the pass did, a handoff included, the results it touched say it (their labels asked for)
            run.settle(walk.work, walk.touched())
        slugs, counts = {r.slug for r in results}, {}
        for h in run.open_handoffs(walk.work):
            if h.get("slug") in slugs or h.get("slug") is None:
                counts[h["kind"]] = counts.get(h["kind"], 0) + 1
        if not args.start:  # the walk's summary; --start's line is its try
            cli.emit({"summary": {"results": len(results),
                                  "satisfied": sum(1 for r in results if run.satisfied(walk.work, r)),
                                  **({"handoffs": counts} if counts else {}), "routes": walk.routes,
                                  **({"invalid": invalid} if invalid else {})}})
        return cli.ACT if code or counts or invalid else cli.OK

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
