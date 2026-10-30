"""Requests to the outside world: one User-Agent, one table of gaps between requests to a host, 429s, what a paper's
page declares about it, proxy hosts.

Pacing. GAPS is the seconds between two requests to one host. INSTITUTION ("institution") is the key a caller paces
full text under when it comes through the institution's proxy or discovery system: 15 s, env
PAPER_FETCH_INSTITUTION_GAP, because licences forbid systematic downloading and a proxy that sees too many
suspends the institution's account, not just this browser. A gap counts on the host actually requested: get() paces a
redirect to another host under that host before following it. A host that answers 429 is stopped: no request goes to
it until the stop ends, and Blocked carries the Retry-After and the end.
  Pacer()      this process only; a stop lasts as long as the pacer (an organizing tool: one process is the run).
  Pacer(work)  shared by every script of an import run through <work>/pace.json, so a rerun keeps the gaps and a 429
               holds across processes: until its Retry-After, else STOP seconds. Every wait reads the file, and every
               read-modify-write holds an exclusive flock on <work>/pace.json.lock (it holds on drvfs, /mnt/c, too). A
               process reserves its slot under the lock and sleeps outside it, so a long gap on one host does not hold
               up another.
pace.json: {"last": {host: epoch seconds of the last request, or of the slot reserved for the next},
"stopped": {host: {"at", "until", "retry_after"}}}; a stop past its end is dropped on the next write.

Remote services go through the environment's proxy settings, unlike Zotero's local API; endpoint() gives a
service's base URL, which a test may point elsewhere.

Paper pages. page_meta() reads a landing page's citation_* tags (Highwire Press, which Google Scholar asks
publishers for), with Dublin Core (dc.*), PRISM and Open Graph (og:*) standing in where one is missing, and
<link rel=alternate type=application/pdf>.

The institution's proxy (config institution.proxy, EZproxy style) serves a host under its own domain: the host with
real dashes doubled and dots as dashes, then .<proxy> (ieeexplore.ieee.org -> ieeexplore-ieee-org.<proxy>).
"""
import codecs
import contextlib
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

try:
    import fcntl
except ImportError:  # not POSIX: no file locks, so pacing stays in the process
    fcntl = None

from . import config, paper
from .cli import log

USER_AGENT = "paper-fetch (stdlib urllib)"
# For pages and files that answer a script differently from a browser.
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
INSTITUTION = "institution"
INSTITUTION_GAP_ENV = "PAPER_FETCH_INSTITUTION_GAP"
# Seconds between two requests to one host; a living table.
GAPS = {"api.crossref.org": 1.0, "export.arxiv.org": 3.0, "doi.org": 0.5, "api.openalex.org": 0.1,
        "www.ebi.ac.uk": 0.2, "www.medrxiv.org": 10.0, "www.biorxiv.org": 10.0, INSTITUTION: 15.0}
DEFAULT_GAP = 1.0
# Seconds a 429 without Retry-After stops a host for a work directory's scripts; a living value.
STOP = 3600.0
PACE_FILE = "pace.json"
# Proxies other than the configured one that a stored url may still carry.
OTHER_PROXIES = re.compile(r"\.idm\.oclc\.org$|(?:^|[.-])(?:ezproxy|webvpn)(?:[.-]|$)", re.I)


def gap(host):
    """Seconds between two requests to the host."""
    if host == INSTITUTION and os.environ.get(INSTITUTION_GAP_ENV):
        try:
            return float(os.environ[INSTITUTION_GAP_ENV])
        except ValueError:
            pass
    return GAPS.get(host, DEFAULT_GAP)


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Blocked(Exception):
    """The host answered 429 (now or earlier): it is not asked again before `until` (epoch seconds; None = while the
    pacer lives)."""

    def __init__(self, host, retry_after=None, until=None):
        super().__init__(host)
        self.host, self.retry_after, self.until = host, retry_after, until

    def fields(self):
        """For a result line: {"host", "retry_after"?, "until"? (UTC)}."""
        return {"host": self.host, **({"retry_after": self.retry_after} if self.retry_after is not None else {}),
                **({"until": iso(self.until)} if self.until is not None else {})}


class Pacer:
    """When each host was last asked and which hosts a 429 stopped: in this process, or (work given: a directory or
    anything with a .root) in <work>/pace.json. `last` and `stopped` ({host: retry_after}) are this process's own, or
    with a work directory the file's as of the last wait or stop."""

    def __init__(self, work=None):
        self.last, self.stopped = {}, {}
        root = work if work is None or isinstance(work, (str, os.PathLike)) else work.root
        self.path = self.lock = None
        if root is not None and fcntl is None:
            log("no file locks on this system: requests are paced in this process only")
        elif root is not None:
            self.path = Path(root) / PACE_FILE
            self.lock = self.path.with_name(PACE_FILE + ".lock")

    def wait(self, host):
        """Sleep until the host's gap has passed and count this request; Blocked when a 429 stopped the host."""
        if self.path is None:
            if host in self.stopped:
                raise Blocked(host, self.stopped[host])
            pause = self.last.get(host, 0.0) + gap(host) - time.monotonic()
            if pause > 0:
                time.sleep(pause)
            self.last[host] = time.monotonic()
            return
        now = time.time()
        with self.state() as state:
            stop = state["stopped"].get(host)
            if stop is None:
                slot = max(now, state["last"].get(host, 0.0) + gap(host))
                state["last"][host] = slot
        if stop is None and slot > now:
            time.sleep(slot - now)
            with self.state() as state:  # another script may have met a 429 there meanwhile
                stop = state["stopped"].get(host)
        if stop is not None:
            raise Blocked(host, stop.get("retry_after"), stop.get("until"))

    def stop(self, host, retry_after=None):
        """Stop the host after a 429 -> (retry_after, until)."""
        if self.path is None:
            self.stopped[host] = retry_after
            log(f"{host} answered 429: not asked again in this run")
            return retry_after, None
        now = time.time()
        until = now + (retry_after if retry_after is not None else STOP)
        with self.state() as state:
            earlier = (state["stopped"].get(host) or {}).get("until") or 0.0
            state["stopped"][host] = {"at": now, "until": max(until, earlier), "retry_after": retry_after}
            until = state["stopped"][host]["until"]
        log(f"{host} answered 429: not asked again before {iso(until)}")
        return retry_after, until

    @contextlib.contextmanager
    def state(self):
        """pace.json under the lock (a dict with "last" and "stopped", expired stops left out); what the block
        changes is written back atomically when it ends without an error. Work-directory pacers only."""
        if self.path is None:
            raise ValueError("a pacer without a work directory has no pace.json")
        fd = os.open(self.lock, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            state = self._read()
            before = json.dumps(state, sort_keys=True)
            yield state
            if json.dumps(state, sort_keys=True) != before:
                self._write(state)
            self.last = dict(state["last"])
            self.stopped = {h: s.get("retry_after") for h, s in state["stopped"].items()}
        finally:
            os.close(fd)  # releases the lock

    def _read(self):
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            state = {}
        except (OSError, ValueError) as e:
            log(f"{self.path} is unreadable ({e}): its gaps start afresh")
            state = {}
        state = state if isinstance(state, dict) else {}
        last, stopped, now = state.get("last"), state.get("stopped"), time.time()
        state["last"] = {h: float(t) for h, t in (last if isinstance(last, dict) else {}).items()
                         if isinstance(t, (int, float)) and not isinstance(t, bool)}
        state["stopped"] = {h: s for h, s in (stopped if isinstance(stopped, dict) else {}).items()
                            if isinstance(s, dict) and (s.get("until") is None or s["until"] > now)}
        return state

    def _write(self, state):
        from .run import atomic_write
        atomic_write(self.path, json.dumps(state, sort_keys=True))


PACER = Pacer()


def endpoint(env, default):
    """A service's base URL: the environment variable `env` when set (the tests point it at a fake), else `default`;
    read at each call, so a test may set it after the script is loaded."""
    return os.environ.get(env, default).rstrip("/")


def host_of(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def retry_after(headers):
    """Seconds from a Retry-After header (seconds or an HTTP date), or None."""
    value = ((headers.get("Retry-After") if headers else None) or "").strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, IndexError):
        return None


class _Hops(urllib.request.HTTPRedirectHandler):
    """Paces each host of a redirect chain once, before it is asked; `key` is the host asked last."""

    def __init__(self, pacer, url, key):
        self.pacer, self.own, self.first, self.key, self.seen = pacer, host_of(url), key, key, set()

    def enter(self, key):
        if key not in self.seen:
            self.pacer.wait(key)
            self.seen.add(key)
        self.key = key

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            hop = host_of(new.full_url)
            try:
                self.enter(self.first if hop == self.own else hop)
            except Blocked:
                fp.close()
                raise
        return new


def get(url, *, params=None, headers=None, host=None, timeout=30, pacer=None, max_bytes=None):
    """A paced GET -> (status, headers, body, final url after redirects); an HTTP error status is returned, not raised.
    `host` is the key the url's own host is paced and stopped under (the real service's when a test points the url
    elsewhere; INSTITUTION for full text through the institution); a redirect to another host is paced under that
    host. headers add to or replace the User-Agent (BROWSER_UA for pages) and set Accept; max_bytes caps the body
    read. A 429 stops the host that answered it and raises Blocked, as does a host already stopped; network failures
    raise OSError. The log line leaves out the query (it may carry a key)."""
    pacer = pacer or PACER
    hops = _Hops(pacer, url, host or host_of(url))
    hops.enter(hops.first)
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        try:
            with urllib.request.build_opener(hops).open(req, timeout=timeout) as resp:
                status, rheaders, final = resp.status, resp.headers, resp.geturl()
                body = resp.read() if max_bytes is None else resp.read(max_bytes)
        except urllib.error.HTTPError as e:
            status, rheaders, final = e.code, e.headers, e.filename or full
            body = e.read() if max_bytes is None else e.read(max_bytes)
    except http.client.HTTPException as e:  # a broken reply: a network failure to the caller
        raise ConnectionError(f"{type(e).__name__}: {e}") from e
    log(f"GET {url.split('?', 1)[0]} -> {status}")
    if status == 429:
        raise Blocked(hops.key, *pacer.stop(hops.key, retry_after(rheaders)))
    return status, rheaders, body, final


class NoData(Exception):
    """A request that gave nothing to read; `code` says why: source_blocked (the host answered 429, now or earlier;
    `extra` holds Blocked.fields()), network_error (`extra` the detail), not_found (404, 410), http_<status>,
    bad_response (not what was asked for). `status` is the HTTP status when there was one."""

    def __init__(self, code, status=None, **extra):
        super().__init__(code)
        self.code, self.status, self.extra = code, status, extra


def read(url, *, full=False, **kwargs):
    """get() that only a 200 answers: its body (full: body, headers, final url), else NoData."""
    try:
        status, headers, body, final = get(url, **kwargs)
    except Blocked as b:
        raise NoData("source_blocked", **b.fields()) from None
    except OSError as e:
        raise NoData("network_error", detail=str(e)) from None
    if status != 200:
        raise NoData("not_found" if status in (404, 410) else f"http_{status}", status)
    return (body, headers, final) if full else body


def read_json(url, **kwargs):
    """read() with Accept: application/json, parsed; NoData("bad_response") for a body that is not JSON."""
    kwargs["headers"] = {"Accept": "application/json", **(kwargs.get("headers") or {})}
    try:
        return json.loads(read(url, **kwargs).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise NoData("bad_response") from None


# ---- arXiv's API ------------------------------------------------------------------------------------------------

ARXIV_HOST = "export.arxiv.org"  # paced and stopped under the real service's host, also when a test points elsewhere
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def arxiv_entries(ids, pacer=None):
    """{arXiv id: ({journal_ref, doi, comment, version: the latest vN}, the source's code)}, one request per 100 ids
    (env ARXIV_API_URL points it elsewhere); an id arXiv does not know gets ({}, "ok"), every id of a request that
    failed ({}, NoData's code)."""
    out = {}
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        try:
            body = read(endpoint("ARXIV_API_URL", "https://export.arxiv.org/api/query"), host=ARXIV_HOST, pacer=pacer,
                        params={"id_list": ",".join(chunk), "max_results": len(chunk)},
                        headers={"Accept": "application/atom+xml"}, timeout=60)
            got = {}
            for entry in ET.fromstring(body).findall("a:entry", ATOM):
                m = re.search(rf"arxiv\.org/abs/({paper.ARXIV_ID})(v\d+)?$", (entry.findtext("a:id", "", ATOM) or "").strip(), re.I)
                if m:
                    got[m.group(1)] = {**{tag: clean(entry.findtext(f"arxiv:{tag}", None, ATOM)) for tag in ("journal_ref", "doi", "comment")},
                                       "version": (m.group(2) or "").lower() or None}
        except NoData as e:
            out.update({aid: ({}, e.code) for aid in chunk})
            continue
        except ET.ParseError:
            out.update({aid: ({}, "bad_response") for aid in chunk})
            continue
        out.update({aid: (got.get(aid, {}), "ok") for aid in chunk})
    return out


# ---- paper pages ----------------------------------------------------------------------------------------------

# A journal or book title that names proceedings (NeurIPS pages give theirs as a journal title). A living list: add a
# form when a real page shows one.
PROCEEDINGS_TITLE = re.compile(r"\b(?:proceedings|conference|symposium|workshop)\b"
                               r"|^advances in neural information processing systems\b", re.I)
# Pages that declare a subset charset and use its superset.
CHARSET_ALIASES = {"gb2312": "gb18030", "gbk": "gb18030"}
# The first tag with a value wins.
TITLE_TAGS = ("citation_title", "dc.title", "og:title")
DATE_TAGS = ("citation_publication_date", "citation_date", "citation_online_date", "dc.date", "prism.publicationdate")
DOI_TAGS = ("citation_doi", "prism.doi", "dc.identifier")
PUBLISHER_TAGS = ("citation_publisher", "dc.publisher")
KEYWORD_TAGS = ("citation_keywords", "dc.subject", "keywords")
ABSTRACT_TAGS = ("citation_abstract", "dcterms.abstract", "dc.description", "og:description", "description")


def _header(headers, name):
    """A header from urllib's headers or a plain dict, any case."""
    if not headers:
        return None
    value = headers.get(name)
    if value is None and isinstance(headers, dict):
        value = next((v for k, v in headers.items() if k.lower() == name.lower()), None)
    return value


def text_of(body, headers=None):
    """An HTTP body as text: by its BOM, else the Content-Type charset, else the page's own <meta charset>, else
    UTF-8; bytes that do not decode become U+FFFD."""
    if isinstance(body, str):
        return body
    body = bytes(body or b"")
    if body.startswith(codecs.BOM_UTF8):
        return body[len(codecs.BOM_UTF8):].decode("utf-8", errors="replace")
    m = re.search(r"charset\s*=\s*[\"']?([\w.:-]+)", _header(headers, "Content-Type") or "", re.I)
    charset = m.group(1) if m else None
    if not charset:
        m = re.search(rb"<meta[^>]{0,300}?charset\s*=\s*[\"']?([\w.:-]+)", body[:8192], re.I)
        charset = m.group(1).decode("ascii") if m else "utf-8"
    try:
        return body.decode(CHARSET_ALIASES.get(charset.lower(), charset), errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


class _PageReader(HTMLParser):
    """The <meta name|property=... content=...> tags, PDF alternates and <base href>. Attribute order and quoting
    vary between sites, hence a parser, not a regex."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.pdf_links, self.base = {}, [], None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "").strip() for k, v in attrs if k}
        if tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            if name and a.get("content"):
                self.meta.setdefault(name, []).append(a["content"])
        elif tag == "link":
            if ("alternate" in a.get("rel", "").lower().split() and a.get("href")
                    and a.get("type", "").split(";")[0].strip().lower() == "application/pdf"):
                self.pdf_links.append(a["href"])
        elif tag == "base" and a.get("href") and self.base is None:
            self.base = a["href"]


def clean(value):
    """Whitespace collapsed; None for an empty value or a non-string."""
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", value).strip() or None


def first_meta(meta, *names):
    """The first non-empty value among the tags, whitespace collapsed; None when none has one."""
    for name in names:
        for value in meta.get(name) or []:
            if clean(value):
                return clean(value)
    return None


def split_name(name):
    """'Last, First' or 'First Last' -> {"lastName", "firstName"}; a single word (a CJK name) -> {"name"}."""
    name = name.strip()
    if "," in name:
        last, first = (p.strip() for p in name.split(",", 1))
    else:
        first, _, last = name.rpartition(" ")
    return {"lastName": last, "firstName": first} if first and last else {"name": name}


def meta_date(value):
    """'2023/10/1', '2023-10-01T00:00Z' -> '2023-10-01'; '2021/3' -> '2021-03'; anything else unchanged."""
    m = re.match(r"(\d{4})(?:[/-](\d{1,2}))?(?:[/-](\d{1,2}))?", value or "")
    if not m:
        return value
    return "-".join([m.group(1)] + [f"{int(g):02d}" for g in m.groups()[1:] if g])


def page_meta(body, url, headers=None):
    """What a paper's page declares about it -> {"title", "authors": [{"lastName", "firstName"} | {"name"}] in order,
    "date", "doi" (normalized), "venue", "venue_kind": conference | journal | book, "publisher", "volume", "issue",
    "pages", "issn", "isbn", "pdf_url" (absolute), "keywords", "abstract", "meta": {tag name, lowercased: [contents]}};
    what the page does not give is None ([] for a list). body is bytes (decoded per text_of, with the reply's
    headers) or text; url, the page's final url, resolves relative links. Broken HTML gives what could be read.

    The abstract may be a description tag (often cut short) and the title an og:title: `meta` says which tags there
    were. A conference title wins over a journal title; a journal or book title that names proceedings is a
    conference."""
    reader = _PageReader()
    try:
        reader.feed(text_of(body, headers))
        reader.close()
    except Exception:  # html.parser can still trip on some broken markup: keep what was read
        pass
    meta = reader.meta
    first = lambda *names: first_meta(meta, *names)  # noqa: E731
    base = urllib.parse.urljoin(url or "", reader.base) if reader.base else url or ""

    names = [n for v in meta.get("citation_author") or [] for n in [clean(v)] if n]
    if not names:
        names = [n for v in meta.get("citation_authors") or [] for n in map(clean, v.split(";")) if n]
    if not names:
        names = [n for v in meta.get("dc.creator") or [] for n in [clean(v)] if n]

    conference = first("citation_conference_title", "citation_conference")
    journal, book = first("citation_journal_title"), first("citation_inbook_title", "citation_book_title")
    venue, kind = ((conference, "conference") if conference else
                   (journal, "journal") if journal else (book, "book") if book else (None, None))
    if kind in ("journal", "book") and PROCEEDINGS_TITLE.search(venue):
        kind = "conference"

    first_page, last_page = first("citation_firstpage"), first("citation_lastpage")
    pages = f"{first_page}-{last_page}" if first_page and last_page and first_page != last_page else first_page
    doi = next((d for n in DOI_TAGS for v in meta.get(n) or []
                for d in [paper.normalize_doi(re.sub(r"^info:doi/", "", v.strip(), flags=re.I))] if d), None)
    pdf = None
    for value in (meta.get("citation_pdf_url") or []) + reader.pdf_links:
        candidate = urllib.parse.urljoin(base, value.strip())
        if urllib.parse.urlsplit(candidate).scheme in ("http", "https"):
            pdf = candidate
            break
    keywords = []
    for name in KEYWORD_TAGS:
        for value in meta.get(name) or []:
            for k in re.split(r"\s*;\s*" if ";" in value else r"\s*,\s*", value):
                if clean(k) and clean(k).casefold() not in {x.casefold() for x in keywords}:
                    keywords.append(clean(k))
        if keywords:
            break
    return {"title": first(*TITLE_TAGS), "authors": [split_name(n) for n in names],
            "date": meta_date(first(*DATE_TAGS)), "doi": doi, "venue": venue, "venue_kind": kind,
            "publisher": first(*PUBLISHER_TAGS), "volume": first("citation_volume"), "issue": first("citation_issue"),
            "pages": pages, "issn": first("citation_issn"), "isbn": first("citation_isbn"), "pdf_url": pdf,
            "keywords": keywords, "abstract": first(*ABSTRACT_TAGS), "meta": meta}


# ---- proxy hosts ----------------------------------------------------------------------------------------------

def proxy_domain():
    return config.institution()["proxy"]


def is_proxy_host(host, proxy=None):
    """Does the host belong to a library proxy: the configured one, or another EZproxy-style one?"""
    host = (host or "").lower()
    proxy = proxy if proxy is not None else proxy_domain()
    return bool(host) and (bool(proxy and host.endswith("." + proxy)) or bool(OTHER_PROXIES.search(host)))


def proxied_host(host, proxy):
    """The host as the proxy serves it."""
    return f"{host.lower().replace('-', '--').replace('.', '-')}.{proxy}"


def original_host(host, proxy=None):
    """The publisher's host behind a host of the configured proxy, or None when it is not one."""
    host, proxy = (host or "").lower(), proxy if proxy is not None else proxy_domain()
    if not proxy or not host.endswith("." + proxy):
        return None
    inner = host[: -len(proxy) - 1]
    return inner.replace("--", "\0").replace("-", ".").replace("\0", "-")


def unproxy(url, proxy=None):
    """The url with the publisher's own host when it went through the configured proxy; else the url unchanged."""
    parts = urllib.parse.urlsplit(url)
    host = original_host(parts.hostname, proxy)
    if not host:
        return url
    netloc = host + (f":{parts.port}" if parts.port else "")
    return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
