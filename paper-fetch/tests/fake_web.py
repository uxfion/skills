"""A fake of the outside web for the tests: doi.org, Crossref, arXiv's API, OpenAlex, Europe PMC and publisher pages,
all served over real HTTP by one server on a free port.

    web = FakeWeb()                     # serving at web.base_url until web.close()
    web.reset()                         # only the services' routes, nothing registered (call it in setUp)
    web.doi("10.1000/x.1", {"type": "journal-article", "title": "A Paper", "source": "Crossref"}, landing="/pub/1")
    web.page("/pub/1", "A Paper", meta={"citation_title": "A Paper", "citation_pdf_url": "/pub/1.pdf"})
    web.pdf("/pub/1.pdf", "A Paper\\nWei Liu")
    r = smoke("doi_to_item", "--doi", "10.1000/x.1", "--base-url", zot.base_url, env=web.env())
                                        # /api/schema is Zotero's: a FakeZotero whose schema has a csl block

env() is the environment the scripts read to find the services (DOI_BASE_URL, CROSSREF_BASE_URL, ARXIV_API_URL,
OPENALEX_BASE_URL, EUROPEPMC_BASE_URL), all pointing here, plus no_proxy for 127.0.0.1. A script that reads them at
import time sees them only if they are set before it is loaded.

Routes. route(path, body, status=200, headers=None, delay=0, times=None) answers a path: exact, or every path below a
prefix ending in *; the path is matched unquoted, the query not at all. `body` is bytes, str or JSON (dict / list), its
Content-Type guessed (JSON; %PDF- -> application/pdf; "<..." -> text/html; else text/plain) unless `headers` names one;
or a callable fn(request) -> body or (status, headers, body) for a dynamic answer. The route registered last is asked
first; an answer of None (body=None, or a callable returning None) passes the request on to the routes below it, and a
request nothing answers is a 404. `delay` sleeps before answering; `times=N` answers the first N requests, then steps
aside, so a route on top of another is "fail the first N times":

    web.route("/crossref/works*", status=503, times=2)    # Crossref fails twice, then answers as usual
    web.rate_limit("/doi/*", retry_after=120)             # 429 with Retry-After on every doi.org request
    web.redirect("/old", "/pub/1")                        # 302 to the page
    web.route("/openalex/*", None, delay=2)               # OpenAlex answers, two seconds late

Services, each under its own prefix and answering in the real service's shape. DOIs match without regard to case, as
the real services do; registering in one service never registers in another (a DOI given to doi() is not in Crossref's
REST API until crossref() adds it).
  doi(doi, csl, landing)        /doi/<doi>: an Accept naming CSL JSON gets a 302 to the agency, which answers the CSL
                                (Crossref's /crossref/v1/works/<doi>/transform when the CSL's source is "Crossref",
                                else DataCite's /datacite/<doi>); a DOI without CSL, or any other Accept, gets a 302 to
                                its landing page (none registered: 404); an unknown DOI 404s.
  crossref(doi, work, **fields) /crossref/works/<doi>: {"status": "ok", "message-type": "work", "message": work};
                                unknown 404. /crossref/works?query.bibliographic=...: message.items, the works whose
                                title shares a word with any query.* parameter, in registration order, at most `rows`.
  arxiv(id, title, ...)         /arxiv/api/query: an Atom feed of the entries in id_list (a version suffix asks for
                                that version) and / or matching search_query (every word of it, field prefixes and
                                operators aside); start, max_results.
  openalex(doi, locations)      /openalex/works/doi:<doi>: id, doi, best_oa_location, locations (see location()), and
                                the fields given (abstract_inverted_index, ids); unknown 404. /openalex/works?filter=
                                doi:a|b|...: results, the works with those DOIs (bare or as doi.org urls).
  europepmc(doi, full_text)     /epmc/europepmc/webservices/rest/search?query=DOI:"..." (or PMCID:..., several ORed):
                                hitCount, resultList.result (see full_text_url()).
Pages, anywhere else: page(path, title, meta=, links=, iframe=, head=, body=) serves html_page(...), an article page
with citation_* / dc.* meta tags, "PDF" links and an iframe; pdf(path, text) serves pdf_bytes(text); gate(path, kind) a
page that stands in the way (GATES: a login form, a bot challenge). Every builder returns the URL it serves.

`requests` logs Request(method, path, query, headers, body) for every request: the path unquoted, the query a dict of
first values, header names lower-case. requested(method, path) filters it (path as in route()).
"""
import html
import json
import re
import threading
import time
import traceback
import urllib.parse
from collections import namedtuple
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

Request = namedtuple("Request", "method path query headers body")
CSL_TYPES = ("application/vnd.citationstyles.csl+json", "application/citeproc+json")
# Crossref fields that are lists in its REST API; a str given for one is wrapped.
CROSSREF_LISTS = ("title", "subtitle", "original-title", "short-title", "container-title", "short-container-title",
                  "ISSN", "ISBN")
# Words of an arXiv search_query that are syntax, not search terms.
ARXIV_SYNTAX = {"ti", "au", "abs", "co", "jr", "cat", "rn", "id", "all", "and", "or", "andnot"}
EPMC_AVAILABILITY = {"OA": "Open access", "F": "Free", "S": "Subscription required", "R": "Registration required"}
AUTO = object()


def pdf_bytes(text=""):
    """A test PDF: the header, then the text (the tests' pdftotext stub prints what follows the 9-byte header)."""
    return b"%PDF-1.4\n" + text.encode("utf-8")


def html_page(title="", meta=None, links=(), iframe=None, head="", body=""):
    """An HTML page: <title>, a <meta name content> per value in `meta` (a list gives one tag per item, as
    citation_author does), an <a href> per (text, href) in `links` (or a dict text -> href), an <iframe src>, and any
    extra `head` / `body` HTML."""
    esc = lambda s: html.escape(str(s))  # noqa: E731
    tags = "".join(f'<meta name="{esc(name)}" content="{esc(v)}">' for name, values in (meta or {}).items()
                   for v in (values if isinstance(values, (list, tuple)) else [values]))
    anchors = "".join(f'<a href="{esc(href)}">{esc(text)}</a>'
                      for text, href in (links.items() if isinstance(links, dict) else links))
    frame = f'<iframe src="{esc(iframe)}"></iframe>' if iframe else ""
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>{esc(title)}</title>{tags}{head}</head>'
            f"<body>{anchors}{frame}{body}</body></html>")


# Pages that stand between a request and the paper: kind -> (status, headers, body). A living table.
GATES = {
    "login": (200, {}, html_page("Sign in", body='<form method="post" action="/login"><input name="username">'
                                                 '<input name="password" type="password"><button>Sign in</button>'
                                                 '</form>')),
    "challenge": (403, {"Server": "cloudflare", "cf-mitigated": "challenge"},
                  html_page("Just a moment...", body="<p>Checking if the site connection is secure</p>")),
}


def location(pdf_url=None, landing_page_url=None, version=None, *, is_oa=True, source_type="journal",
             source_name="A Source"):
    """One OpenAlex location; version publishedVersion | acceptedVersion | submittedVersion | None."""
    return {"is_oa": is_oa, "landing_page_url": landing_page_url, "pdf_url": pdf_url, "version": version,
            "is_accepted": version in ("acceptedVersion", "publishedVersion"),
            "is_published": version == "publishedVersion", "license": None,
            "source": {"display_name": source_name, "type": source_type}}


def full_text_url(code, style, site, url):
    """One Europe PMC fullTextUrlList entry: code OA | F | S | R, style pdf | html | doi, site Europe_PMC |
    PubMedCentral | DOI | Unpaywall | ..."""
    return {"availability": EPMC_AVAILABILITY.get(code, code), "availabilityCode": code, "documentStyle": style,
            "site": site, "url": url}


def words(text):
    return re.findall(r"\w+", str(text or "").casefold())


def quote(doi):
    return urllib.parse.quote(doi, safe="/")


def matches(pattern, path):
    return path.startswith(pattern[:-1]) if pattern.endswith("*") else path == pattern


class Route:
    def __init__(self, path, answer, delay, times):
        self.path, self.answer, self.delay, self.left = path, answer, delay, times


class FakeWeb:
    def __init__(self):
        fake = self

        class Handler(_Handler):
            web = fake

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.reset()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def reset(self):
        self.lock = threading.Lock()
        self.routes, self.requests = [], []
        self.dois, self.works, self.entries, self.oa_works, self.epmc = {}, {}, {}, {}, []
        self.route("/doi/*", self._doi)
        self.route("/crossref/v1/works/*",
                   lambda r: self._csl(r.path[len("/crossref/v1/works/"):].removesuffix("/transform")))
        self.route("/datacite/*", lambda r: self._csl(r.path[len("/datacite/"):]))
        self.route("/crossref/works", self._crossref_search)
        self.route("/crossref/works/*", self._crossref_work)
        self.route("/arxiv/api/query", self._arxiv)
        self.route("/openalex/works", self._openalex_list)
        self.route("/openalex/works/*", self._openalex)
        self.route("/epmc/europepmc/webservices/rest/search", self._europepmc)

    def env(self):
        b = self.base_url
        return {"DOI_BASE_URL": f"{b}/doi", "CROSSREF_BASE_URL": f"{b}/crossref",
                "ARXIV_API_URL": f"{b}/arxiv/api/query", "OPENALEX_BASE_URL": f"{b}/openalex",
                "EUROPEPMC_BASE_URL": f"{b}/epmc", "no_proxy": "127.0.0.1,localhost"}

    def url(self, path):
        """The absolute URL of a path here; an absolute URL stays as it is."""
        return urllib.parse.urljoin(self.base_url + "/", path)

    def requested(self, method=None, path=None):
        """The logged requests, filtered by method and path (a prefix ending in * matches every path below it)."""
        return [r for r in self.requests if (not method or r.method == method) and (not path or matches(path, r.path))]

    # ---- routes ---------------------------------------------------------------------------------------------------

    def route(self, path, body="", *, status=200, headers=None, delay=0, times=None):
        answer = body if body is None or callable(body) else (status, headers or {}, body)
        self.routes.append(Route(path, answer, delay, times))
        return self.url(path.rstrip("*"))

    def redirect(self, path, to, status=302, **options):
        """A redirect from `path` to `to` (a path here or any URL)."""
        return self.route(path, "", status=status, headers={"Location": self.url(to)}, **options)

    def rate_limit(self, path, retry_after=120, **options):
        """429 Too Many Requests with Retry-After (seconds, or an HTTP date as a str)."""
        return self.route(path, "Too Many Requests", status=429, headers={"Retry-After": str(retry_after)}, **options)

    def answer(self, req):
        for route in reversed(list(self.routes)):
            if not matches(route.path, req.path):
                continue
            with self.lock:
                if route.left is not None:
                    if route.left <= 0:
                        continue
                    route.left -= 1
            if route.delay:
                time.sleep(route.delay)
            try:
                got = route.answer(req) if callable(route.answer) else route.answer
            except Exception:
                return 500, {}, traceback.format_exc()
            if got is not None:
                return got if isinstance(got, tuple) and len(got) == 3 else (200, {}, got)
        return 404, {}, "Not Found"

    # ---- pages ------------------------------------------------------------------------------------------------------

    def page(self, path, title="", *, meta=None, links=(), iframe=None, head="", body="", **options):
        """html_page(...) at `path`; options as for route()."""
        return self.route(path, html_page(title, meta, links, iframe, head, body), **options)

    def pdf(self, path, text="", **options):
        return self.route(path, pdf_bytes(text), **options)

    def gate(self, path, kind="login", **options):
        status, headers, body = GATES[kind]
        return self.route(path, body, status=status, headers=headers, **options)

    # ---- doi.org ----------------------------------------------------------------------------------------------------

    def doi(self, doi, csl=None, *, landing=None):
        """A DOI: its CSL JSON (None: its agency has none) and its landing page (a path here or a URL)."""
        self.dois[doi.casefold()] = (csl, self.url(landing) if landing else None)
        return self.url("/doi/" + quote(doi))

    def _doi(self, req):
        doi = req.path[len("/doi/"):]
        if doi.casefold() not in self.dois:
            return 404, {}, html_page("DOI Not Found", body=f"<h1>DOI Not Found</h1><p>{html.escape(doi)}</p>")
        csl, landing = self.dois[doi.casefold()]
        if csl is not None and any(t in req.headers.get("accept", "") for t in CSL_TYPES):
            crossref = csl.get("source") == "Crossref"
            agency = f"/crossref/v1/works/{quote(doi)}/transform" if crossref else f"/datacite/{quote(doi)}"
            return 302, {"Location": self.url(agency)}, ""
        if landing:
            return 302, {"Location": landing}, ""
        return 404, {}, "No landing page for this DOI in the fake"

    def _csl(self, doi):
        csl = self.dois.get(doi.casefold(), (None, None))[0]
        return (200, {"Content-Type": CSL_TYPES[0]}, csl) if csl is not None else (404, {}, "Not Found")

    # ---- Crossref ---------------------------------------------------------------------------------------------------

    def crossref(self, doi, work=None, **fields):
        """A work in Crossref's REST API: `work` in Crossref's shape, and / or fields with _ for - (container_title)."""
        work = {"DOI": doi, **(work or {}), **{k.replace("_", "-"): v for k, v in fields.items()}}
        self.works[doi.casefold()] = {k: [v] if k in CROSSREF_LISTS and isinstance(v, str) else v
                                      for k, v in work.items()}
        return self.url("/crossref/works/" + quote(doi))

    def _crossref_work(self, req):
        work = self.works.get(req.path[len("/crossref/works/"):].casefold())
        if work is None:
            return 404, {}, "Resource not found."
        return 200, {}, {"status": "ok", "message-type": "work", "message-version": "1.0.0", "message": work}

    def _crossref_search(self, req):
        asked = set(words(" ".join(v for k, v in req.query.items() if k == "query" or k.startswith("query."))))
        rows = int(req.query.get("rows", 20))
        title = lambda w: " ".join((w.get("title") or []) + (w.get("subtitle") or []))  # noqa: E731
        hits = [w for w in self.works.values() if asked & set(words(title(w)))]
        return 200, {}, {"status": "ok", "message-type": "work-list", "message-version": "1.0.0",
                         "message": {"total-results": len(hits), "items-per-page": rows, "items": hits[:rows]}}

    # ---- arXiv ------------------------------------------------------------------------------------------------------

    def arxiv(self, aid, title, *, version=1, authors=(), summary="", category="cs.LG", journal_ref=None, doi=None,
              comment=None):
        """A paper in arXiv's API: `aid` without a version, `version` its latest."""
        published = f"20{aid[:2]}-{aid[2:4]}-01T00:00:00Z" if re.match(r"\d{4}\.", aid) else "2000-01-01T00:00:00Z"
        self.entries[aid] = {"title": title, "version": version, "authors": list(authors), "summary": summary,
                             "category": category, "published": published, "journal_ref": journal_ref, "doi": doi,
                             "comment": comment}
        return self.url("/arxiv/api/query?id_list=" + aid)

    def _arxiv(self, req):
        q = req.query
        asked = [a.strip() for a in q.get("id_list", "").split(",") if a.strip()]
        found = [m.groups() for m in (re.fullmatch(r"(.+?)(v\d+)?", a) for a in asked)] if asked \
            else [(aid, None) for aid in self.entries]
        found = [(aid, v) for aid, v in found if aid in self.entries]
        if q.get("search_query"):
            wanted = {w for w in words(q["search_query"]) if w not in ARXIV_SYNTAX}
            text = lambda e: " ".join([e["title"], e["summary"], *e["authors"]])  # noqa: E731
            found = [(aid, v) for aid, v in found if wanted <= set(words(text(self.entries[aid])))]
        start, size = int(q.get("start", 0)), int(q.get("max_results", 10))
        feed = ('<?xml version="1.0" encoding="UTF-8"?>'
                '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" '
                'xmlns:arxiv="http://arxiv.org/schemas/atom"><title type="html">ArXiv Query</title>'
                f"<opensearch:totalResults>{len(found)}</opensearch:totalResults>"
                f"<opensearch:startIndex>{start}</opensearch:startIndex>"
                f"<opensearch:itemsPerPage>{size}</opensearch:itemsPerPage>"
                + "".join(self._entry(aid, v) for aid, v in found[start:start + size]) + "</feed>")
        return 200, {"Content-Type": "application/atom+xml; charset=utf-8"}, feed

    def _entry(self, aid, version):
        e, x = self.entries[aid], lambda s: html.escape(str(s), quote=False)
        vid = aid + (version or f"v{e['version']}")
        scheme = 'scheme="http://arxiv.org/schemas/atom"'
        return (f"<entry><id>http://arxiv.org/abs/{vid}</id><updated>{e['published']}</updated>"
                f"<published>{e['published']}</published><title>{x(e['title'])}</title>"
                f"<summary>{x(e['summary'])}</summary>"
                + "".join(f"<author><name>{x(n)}</name></author>" for n in e["authors"])
                + "".join(f"<arxiv:{tag}>{x(e[tag])}</arxiv:{tag}>" for tag in ("doi", "journal_ref", "comment") if e[tag])
                + f'<link href="http://arxiv.org/abs/{vid}" rel="alternate" type="text/html"/>'
                f'<link title="pdf" href="http://arxiv.org/pdf/{vid}" rel="related" type="application/pdf"/>'
                f'<arxiv:primary_category term="{e["category"]}" {scheme}/><category term="{e["category"]}" {scheme}/>'
                "</entry>")

    # ---- OpenAlex ---------------------------------------------------------------------------------------------------

    def openalex(self, doi, locations=(), *, best=AUTO, **fields):
        """A work in OpenAlex: its locations (location()) and best_oa_location (by default its first open location)."""
        locations = list(locations)
        best = next((loc for loc in locations if loc.get("is_oa")), None) if best is AUTO else best
        self.oa_works[doi.casefold()] = {"id": f"https://openalex.org/W{len(self.oa_works) + 1:09d}",
                                         "doi": f"https://doi.org/{doi.lower()}", "best_oa_location": best,
                                         "locations": locations, **fields}
        return self.url("/openalex/works/doi:" + quote(doi))

    def _openalex(self, req):
        m = re.fullmatch(r"(?:doi:|https?://(?:dx\.)?doi\.org/)(.+)", req.path[len("/openalex/works/"):], re.I)
        work = self.oa_works.get(m.group(1).casefold()) if m else None
        return (200, {}, work) if work else (404, {}, {"error": "Not Found", "message": "not found"})

    def _openalex_list(self, req):
        m = re.fullmatch(r"doi:(.+)", req.query.get("filter", ""), re.I)
        asked = [re.sub(r"^https?://(?:dx\.)?doi\.org/", "", d, flags=re.I).casefold() for d in m.group(1).split("|")] if m else []
        works = [self.oa_works[d] for d in dict.fromkeys(asked) if d in self.oa_works]
        return 200, {}, {"meta": {"count": len(works), "per_page": int(req.query.get("per-page", 25))}, "results": works}

    # ---- Europe PMC -------------------------------------------------------------------------------------------------

    def europepmc(self, doi, full_text=(), **fields):
        """A Europe PMC search result, fields named as Europe PMC names them (source, pmcid, inPMC, authMan, ...; inPMC
        follows pmcid unless given); full_text its fullTextUrlList entries (full_text_url())."""
        n = len(self.epmc) + 1
        result = {"id": f"{n}", "source": "MED", "pmid": f"{n}", "doi": doi, "isOpenAccess": "N", "inEPMC": "N",
                  "inPMC": "Y" if fields.get("pmcid") else "N", "hasPDF": "N", "authMan": "N", "epmcAuthMan": "N",
                  "nihAuthMan": "N", **({"fullTextUrlList": {"fullTextUrl": list(full_text)}} if full_text else {}), **fields}
        self.epmc.append(result)
        return self.url("/epmc/europepmc/webservices/rest/search?" + urllib.parse.urlencode({"query": f'DOI:"{doi}"'}))

    def _europepmc(self, req):
        query = req.query.get("query", "")
        asked = {(k.lower(), v.casefold()) for k, v in re.findall(r'\b(DOI|PMCID):"?([^"\s)]+)"?', query, re.I)}
        hits = [r for r in self.epmc if any(str(r.get(k) or "").casefold() == v for k, v in asked)]
        size = int(req.query.get("pageSize", 25))
        return 200, {}, {"version": "6.9", "hitCount": len(hits), "request": {"queryString": query, "pageSize": size},
                         "resultList": {"result": hits[:size]}}


def encode(body):
    """(bytes, guessed Content-Type) of a route body."""
    if isinstance(body, (dict, list)):
        return json.dumps(body).encode(), "application/json"
    data = body.encode("utf-8") if isinstance(body, str) else bytes(body or b"")
    if data.startswith(b"%PDF-"):
        return data, "application/pdf"
    return data, "text/html; charset=utf-8" if data.lstrip()[:1] == b"<" else "text/plain; charset=utf-8"


class _Handler(BaseHTTPRequestHandler):
    web: FakeWeb
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def serve(self):
        url = urllib.parse.urlsplit(self.path)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(url.query, keep_blank_values=True).items()}
        length = int(self.headers.get("Content-Length") or 0)
        req = Request(self.command, urllib.parse.unquote(url.path), query,
                      {k.lower(): v for k, v in self.headers.items()}, self.rfile.read(length) if length else b"")
        self.web.requests.append(req)
        status, headers, body = self.web.answer(req)
        payload, ctype = encode(body)
        headers = dict(headers or {})
        if payload and not any(k.lower() == "content-type" for k in headers):
            headers["Content-Type"] = ctype
        try:
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, str(v))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_GET = do_HEAD = do_POST = serve
