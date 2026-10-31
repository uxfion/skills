#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Walk one pass of the chain for the results without a file: each route over all of them, then the next.

  route       its candidates                                                                   SKILL.md's chain
  open        the result's links of the published version, then those of unknown version      1
  publisher   https://doi.org/<DOI> (else the CSL's URL), the papers grouped by publisher      2
  discovery   the paper's records in the library's discovery system (config institution.discovery)   3
  accepted    the links of the accepted manuscript                                            4
  preprint    the links of the preprint                                                       5
  snapshot    the article page's HTML, filed as <slug>.html (only with --route: the last pass)

A paper stops at the first file that passes the check. A candidate that needs no browser (needs_browser false or
unknown) is first asked over plain HTTP; what is not a PDF goes to the browser (the opencli session in run.json, a
background window, --window foreground for the last pass). On a page the browser takes the PDF the page itself offers
(pflib/browser.py: the declared PDF, an embedded document or viewer, a link saying PDF; three at most): requested
inside the page with its cookies (through the institution's proxy: the same path on the proxied host), else opened as
a click would — a download, a pdf.js viewer, or an HTML page that is looked through once more (IEEE's stamp.jsp). The
discovery route takes the search's links whose text is the title (0.9 alike, arXiv records last) and works each page.
Each candidate's version goes along to the check and the file's name: the version it was wanted as. An arXiv link is
fetched as its latest version (https://arxiv.org/pdf/<id>v<N>: the vN identify recorded, versions.preprint.latest,
else one request to arXiv's API for all of the pass's arXiv links).

What the file is, the agent settles (SKILL.md, Get the file), from the host's word first and the file's second. Each
claim event carries the title proposed from how the file came (paper.proposal: the site's or the route's version,
the site's name, the arXiv vN) and the host's word, recorded while it describes this very file: the url; the page
the file came from, with its title, its citation_* and dc.* tags and its words around the paper's title (where a
page puts its labels, dates, volume and issue); the link taken on it (its text and the text around it). An arXiv
file's host word is arXiv's for that version: its comment and journal reference. A file Chrome downloaded on a link
this command opened gets the same as an arrival event. When a pass goes through, a `to_label` line for each result
with a PDF that has no label yet (claim.py --label) lists the host's word, then the file's: {slug, code: to_label,
file, proposal, route, url, page, meta, words, link, stamp, dates, head (page 1's first 1000 characters)}.

A candidate is tried once a pass: a try is (paper, pass, route, candidate) with its result — ok, wrong_file (the
check refused it: unverified/), stray, not_in_discovery, error — or the agent's verdict. A page the browser cannot get
past stops the whole command (exit 1), the tab left on it: a `stop` event {slug, pass, route, url, gate?, why:
no_pdf_link | refused | sign_in (a discovery system showing a guest part of its results) | gate (a PDF link that
opened a page only the user passes and was still on it after the click's wait: ScienceDirect's PDF host asks its own
"Are you a robot?"; the link, not the article page, is what opens in front of the user), page, title}, no try, so a
rerun asks that page again. A page that looks like a gate (GATE_TITLE, GATE_TEXT: a login, a challenge) is `gate: true`
and opened again in a foreground window, in front of the user; any other stays in the background for the agent, who
works it (sign_in: the system's own sign-in, clicked through to its login page, the gate). The agent looks, acts, and
either reruns the same command or records a verdict.
  --verdict V            the agent's conclusion on the paper's last stop (one result); with --route R: on the whole
                         route for the results given (the papers behind a gate that timed out, a page nobody passes)
  --start URL [--version V]  one result: a candidate the agent found (a PMC page, a repository); never the route's try
Verdicts (VERDICTS below, the one table): no_access, no_pdf, gate_timeout, proxy_unconfigured, site_blocked,
not_public, skipped_by_user. Before each candidate the result's file is looked for (the watcher may have filed it;
while no watcher runs, this command scans Downloads itself, for the paper under way too). Requests to one host keep
their gap (web.GAPS; full text through the institution 15 s).

stdout: the try, stop and skip lines as they happen, the to_label lines, then {"summary": {results, with_file,
to_label, routes, stopped?}}. When it ends, a stop too, it folds the results it was given (and any other its scan of
Downloads filed a file for) into their files and outcome, as settle.py does.
Exit 0 = the pass went through (papers may still lack a file); 1 = stopped on a page; 2 = cannot run (no opencli,
results of two directories, no pdftotext).

Examples:
  uv run scripts/fetch.py --pass 1 <dir>/results/*.json
  uv run scripts/fetch.py --pass 1 --verdict no_access <dir>/results/<slug>.json
  uv run scripts/fetch.py --pass 1 --start https://pmc.ncbi.nlm.nih.gov/articles/PMC123/ <dir>/results/<slug>.json
  uv run scripts/fetch.py --pass 3 --route snapshot <dir>/results/<slug>.json
"""
import os
import re
import time
import urllib.parse
from pathlib import Path

from pflib import cli, config, paper, run, verify, web
from pflib.browser import Browser

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
# A discovery system shows a guest part of its results. Signed out: a control that offers to sign in (Primo shows one
# beside its account menu until then), or a notice saying so. Living lists: add a system's wording.
SIGN_IN_CONTROL = re.compile(r"^(?:sign ?in|log ?in|登录|登入)\b", re.I)
SIGNED_OUT = re.compile(r"sign in to (?:get|see|view) (?:the )?(?:complete|full|all) results|"
                        r"log ?in to (?:get|see|view) (?:the )?(?:complete|full|all) results|登录.{0,8}完整", re.I)
# What a page only the user can pass looks like (a login, a challenge): its title, or its text. A living list.
GATE_TITLE = re.compile(r"sign.?on|sign ?in|log ?in|登录|请稍候|請稍候|just a moment|robot|captcha|verif", re.I)
GATE_TEXT = re.compile(r"verify you are (?:a )?human|checking if the site connection is secure|正在进行安全验证", re.I)
PAGE_CANDIDATES = 3   # tried on one page at most
WORDS_BEFORE, WORDS_AFTER = 600, 900  # a page's words kept around the paper's title
CLICK_WAIT = float(os.environ.get("PAPER_FETCH_CLICK_WAIT", "20"))        # an opened page: to show a viewer or its PDF link
DOWNLOAD_WAIT = float(os.environ.get("PAPER_FETCH_DOWNLOAD_WAIT", "60"))  # the tab stayed, Chrome downloads: PMC took 45-60 s
DISCOVERY_WAIT = float(os.environ.get("PAPER_FETCH_DISCOVERY_WAIT", "30"))  # the results to render
MAX_BYTES = 200 * 1024 * 1024


class Stopped(Exception):
    def __init__(self, why, url, title=None, note=None, front=None):
        super().__init__(why)
        self.why, self.url, self.title, self.note, self.front = why, url, title, note, front


class Pass:
    def __init__(self, args, results):
        works = {run.Work.of(r.path).root for r in results}
        if len(works) != 1:
            raise cli.Stop("mixed_work_dirs", exit=cli.CANNOT, hint="Pass the results of one directory.",
                           work_dirs=sorted(map(str, works)))
        self.args, self.results, self.work, self.route, self.stopped = args, results, run.Work(works.pop()), None, None
        self.arxiv = None  # arXiv id -> arXiv's word on its latest version (arxiv_entry)
        self.pacer = web.Pacer(self.work)
        inst, settings = config.institution(), self.work.settings()
        self.proxy, self.discovery = inst["proxy"], inst["discovery"]
        dl = settings.get("downloads")
        self.scanner = run.Scanner(self.work, dl) if dl and Path(dl).is_dir() else None
        self.filed = set()  # slugs a scan filed a file for
        self.browser = Browser(settings.get("session") or "pf", args.window)

    def log(self, event, **fields):
        line = self.work.append({"event": event, "pass": self.args.pass_, **fields})
        cli.emit(line)
        return line

    def has_file(self, res):
        if self.scanner and not run.watcher_alive(self.work):
            self.filed.update(e["slug"] for e in self.scanner.scan() if e.get("slug"))
        return self.work.file_of(res.slug) is not None

    def touched(self):
        """The results to fold when the command ends: those it was given, and any other a scan filed a file for."""
        given = {r.slug for r in self.results}
        return self.results + [run.read(self.work.results / f"{s}.json") for s in sorted(self.filed - given)
                               if (self.work.results / f"{s}.json").is_file()]

    def claim(self, res, data, url, version, html=False, page=None, link=None):
        """Bytes -> inbox -> checked and filed -> (the try's result, {check: the check's code}). `page` is the page
        the file came from (find()'s answer), `link` the candidate taken on it: evidence for the file's label."""
        self.work.inbox.mkdir(exist_ok=True)
        path = self.work.inbox / f"{res.slug}.{self.route}.{'html' if html else 'pdf'}"
        path.write_bytes(data)
        event = run.claim(self.work, path, res.slug, kind=version if version in paper.KINDS else None, source=url,
                          via=self.route, came=self.came(url, page, link))
        return {"claimed": "ok", "unverified": "wrong_file"}.get(event["result"], event["result"]), {"check": event.get("code")}

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

    # ---- one candidate ----------------------------------------------------------------------------------------

    def get(self, res, cand):
        """Try one candidate -> (result, extra fields); Stopped on a page the agent must look at."""
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
        paper's file got filed, within DOWNLOAD_WAIT; False at once when another document opened."""
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
        raise Stopped("refused" if tried else "no_pdf_link", after.get("href") or info.get("href"), after.get("title"),
                      "; ".join(x for x in (note, f"{tried} PDF links tried" if tried else None) if x) or None)

    def click(self, res, cand, page, version, depth, shown=None):
        """One PDF link of a page: requested inside the page, else opened as a click would -> (result, extra), or None.
        `page` is the page the link is on; `shown`, the page the file's evidence names (on_page's)."""
        b, link, here = self.browser, cand["url"], page
        page = shown or page
        req = request_url(link, here.get("href") or "", self.proxy)
        self.pace(req)
        data, why = b.fetch(req)
        if data:
            return self.claim(res, data, link, version, page=page, link=cand)
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
                    result, extra = self.claim(res, data, link, version, page=page, link=cand)
                    return result, {**extra, "note": "read from the pdf.js viewer"}
            elif depth == 0 and now.get("candidates"):
                try:
                    return self.on_page(res, version, f"in-page: {why}", depth=1, outer=page)
                except Stopped as s:
                    if s.why == "gate":
                        raise
                    return None
            if self.has_file(res):  # a page that downloads in the end
                return self.downloaded_here(res, link, page, cand)
            time.sleep(1.0)
        if now and now.get("doc") != before and GATE_TITLE.search(now.get("title") or ""):  # waited: no check passes by itself
            raise Stopped("gate", now.get("href"), now.get("title"), "the PDF link opened a gate", front=req)
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
        return [{"url": with_query(self.discovery, title), "version": None, "needs_browser": True}] if title else []

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
            links = [l.get("url") for r in self.results if not self.work.file_of(r.slug)
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

    def to_label(self):
        """A to_label line for each result with a PDF that has no label (no `label` event for it): what its label is
        settled from -> how many. A snapshot needs none: its bytes say what it is."""
        n = 0
        for res in self.results:
            f = self.work.file_of(res.slug)
            if f is None or run.label_of(self.work, res.slug, f.name) or paper.kind_of_file(f.name) == "snapshot":
                continue
            n += 1
            e = run.arrived(self.work, res.slug, run.md5_of(f)) or {}
            ev = e.get("evidence") or {}
            page, link, file = ev.get("page") or {}, ev.get("link") or {}, ev.get("file") or {}
            head = " / ".join(line for line in (file.get("excerpt") or "").splitlines() if line.strip())[:1000]
            cli.emit({"slug": res.slug, "code": "to_label", "file": f.name, "proposal": (e.get("proposal") or {}).get("title"),
                      "route": e.get("route"), "url": ev.get("url"), "page": page.get("title") or page.get("href"),
                      "meta": page.get("meta"), "words": page.get("words"),
                      "link": " | ".join(filter(None, (link.get("text"), link.get("near")))) or link.get("why"),
                      "stamp": file.get("arxiv_stamp"), "dates": file.get("pdf_dates"), "head": head or None,
                      "hint": f"Settle what the file is, then label it: pf.py claim --dir {self.work.root} --label TITLE "
                              f"--why WHY --slug {res.slug} (SKILL.md, Get the file)."})
        return n

    def discover(self, res, cand):
        """The paper's records among the discovery system's results, each page worked in turn."""
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
        page = b.text()
        if SIGNED_OUT.search(page.get("text") or "") or any(map(SIGN_IN_CONTROL.match, b.controls())):  # a guest's results prove nothing
            raise Stopped("sign_in", page.get("href"), page.get("title"), "the discovery system shows a guest part of its results")
        if not matches:
            return "not_in_discovery", {"note": f"{len(anchors)} links, none with this title"}
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
                if s.why == "gate":
                    raise
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

    def stop(self, res, url, s):
        """Stop the pass here. A page that looks like a gate is opened again in a foreground window, in front of the
        user, who passes it; any other stays in the background for the agent."""
        self.stopped = s.why
        page = self.browser.text()
        gate = bool(GATE_TITLE.search(s.title or page.get("title") or "") or GATE_TEXT.search((page.get("text") or "")[:3000]))
        if gate:
            self.browser.open(s.front or url, front=True)
        self.log("stop", slug=res.slug, route=self.route, url=url, why=s.why, page=s.url, title=s.title, note=s.note,
                 gate=gate or None)
        hint = ("A gate, now in front of the user: say what to do there (sign in, tick the box), wait with pf.py wait "
                "<result>, then rerun the same command." if gate else
                "The tab stays on this page: hand it to a browser agent (SKILL.md, Get the file), then rerun the same "
                "command; or record its conclusion with --verdict.")
        cli.emit({"slug": res.slug, "code": "stopped", "route": self.route, "why": s.why, "gate": gate, "url": s.url,
                  "title": s.title, "hint": hint})
        return cli.ACT

    def walk(self, routes):
        """The routes in turn over the results without a file -> the exit code."""
        logged = {e.get("slug") for e in self.work.events("pass") if e.get("pass") == self.args.pass_}
        for res in self.results:  # from here on a download for it is filed, whoever starts it (run.wanted)
            if not self.work.file_of(res.slug) and res.slug not in logged:
                self.work.append({"event": "pass", "pass": self.args.pass_, "slug": res.slug})
        for res in self.results:
            if not self.work.file_of(res.slug) and run.links_of(res) is None:
                cli.emit({"slug": res.slug, "code": "not_prepared", "hint": "Its links are missing or were found for "
                          "other ids: run pf.py fulltext_links on it; until then only the page routes try it."})
        for route in routes:
            self.route = route
            if route == "discovery" and not self.discovery:
                cli.emit({"route": route, "code": "no_discovery", "hint": "Ask the user once for their library's discovery "
                          "search page; add it to the config as institution.discovery."})
                continue
            todo = [r for r in self.results if not self.work.file_of(r.slug)]
            if route == "publisher":  # one publisher's papers together
                todo.sort(key=lambda r: (r.subject.doi or "").split("/")[0])
            get = {"discovery": self.discover, "snapshot": self.snapshot}.get(route, self.get)
            for res in todo:
                tries = [e for e in self.work.events("try") if e.get("slug") == res.slug
                         and e.get("pass") == self.args.pass_ and e.get("route") == route]
                if any(t.get("url") is None for t in tries):
                    continue  # the agent closed this route for the paper in this pass
                for cand in self.candidates(res, route):
                    if self.has_file(res):
                        cli.emit({"slug": res.slug, "code": "skipped", "reason": "has_file"})
                        break
                    if any(t.get("url") == cand["url"] for t in tries):
                        continue
                    try:
                        result, extra = get(res, cand)
                    except Stopped as s:
                        return self.stop(res, cand["url"], s)
                    self.log("try", slug=res.slug, route=route, url=cand["url"], version=cand.get("version"),
                             result=result, **extra)
                    if result == "ok":
                        break
        return cli.OK


def landing(res):
    sub = res.subject
    if sub.doi:
        return f"https://doi.org/{urllib.parse.quote(sub.doi, safe='/')}"
    return sub.url


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


def verdict(walk, res, args):
    """--verdict: the agent's conclusion, logged as this pass's try."""
    if args.route or args.start:
        return walk.log("try", slug=res.slug, route="start" if args.start else args.route, url=args.start,
                        result=args.verdict, by="agent")
    stops = [e for e in walk.work.events("stop") if e.get("slug") == res.slug and e.get("pass") == args.pass_]
    if not stops:
        raise cli.Stop("nothing_stopped", hint="This paper has not stopped in this pass: name the route with --route.")
    return walk.log("try", slug=res.slug, route=stops[-1]["route"], url=stops[-1]["url"], result=args.verdict, by="agent")


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("results", nargs="+", metavar="RESULT", help="result files: <dir>/results/<slug>.json")
    p.add_argument("--pass", dest="pass_", type=int, default=1, choices=(1, 2, 3), help="which pass of the chain")
    p.add_argument("--route", choices=ROUTES + ("snapshot",), help="this route only")
    p.add_argument("--start", metavar="URL", help="one result: a candidate the agent found")
    p.add_argument("--version", choices=list(paper.KINDS), help="with --start: the version it is")
    p.add_argument("--verdict", choices=sorted(VERDICTS), help="the agent's conclusion (see above)")
    p.add_argument("--window", choices=("background", "foreground"), default="background",
                   help="where pages open (foreground: the last pass, with the user)")
    args = p.parse_args(argv)
    if (args.start or (args.verdict and not args.route)) and len(args.results) != 1:
        p.error("--start, and --verdict without --route, take exactly one result")
    if args.version and not args.start:
        p.error("--version goes with --start")

    def one_pass(walk, results, invalid):
        if args.verdict:
            for res in results:
                verdict(walk, res, args)
            return cli.OK
        verify.require_pdftotext()
        if args.start:
            walk.route, res = "start", results[0]
            url = walk.arxiv_url(args.start)
            try:
                result, extra = walk.get(res, {"url": url, "version": args.version, "needs_browser": None})
            except Stopped as s:
                return walk.stop(res, url, s)
            walk.log("try", slug=res.slug, route="start", url=url, version=args.version, result=result, **extra)
            return cli.OK
        routes = [args.route] if args.route else list(ROUTES)
        code = walk.walk(routes)
        unlabelled = walk.to_label() if code == cli.OK else None
        cli.emit({"summary": {"results": len(results), "with_file": sum(1 for r in results if walk.work.file_of(r.slug)),
                              **({"to_label": unlabelled} if unlabelled is not None else {}),
                              "routes": routes, **({"stopped": walk.stopped} if walk.stopped else {}),
                              **({"invalid": invalid} if invalid else {})}})
        return code if code or not invalid else cli.ACT

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
            return one_pass(walk, results, invalid)
        finally:  # whatever the pass did, a stop included, the results it touched say it
            run.settle(walk.work, walk.touched())

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
