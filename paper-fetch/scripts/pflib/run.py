"""paper-fetch's directory: its layout and settings, the result files, the log, how a file reaches a result, the
handoffs to agents and their answers, and the fold of the log into the results.

Layout (ready.py makes it). <dir> is <scratch>/paper-fetch/, or the directory a caller names with -o (an import:
<scratch>/paper-to-zotero/fetch/):
  results/<slug>.json   one result per paper (below); its files beside it, named by the version each was wanted as
                        (its kind, paper.KINDS): <slug>.pdf, .accepted.pdf, .preprint.pdf, .supplement.pdf, .html; a
                        second file of one kind is numbered (<slug>.2.pdf). Files are told apart by md5.
  links/<slug>.json     where copies may be had (fulltext_links): {from, items: [{url, source, version: published |
                        accepted | preprint | unknown, needs_browser}], incomplete?: [sources]}
  handoffs/<id>.json    a handoff to an agent (below), written once; its evidence files in handoffs/<id>/
  inbox/ unverified/ scratch/    bytes a script fetched / files the check did not file / one-off files
  .started              the run's start: Downloads files newer than it are this run's
  run.json              the run's settings: downloads, session, the watcher's pid
  fetch.jsonl           what happened, one JSON event per line, appended under a lock (below)
A caller reads results/ and nothing else. Request gaps live in the machine's pace file (web.pace_path()).

A result file, results/<slug>.json, one JSON object:
  slug, slug_given      the file's name; whether the caller chose it (--slug)
  renamed_from          [old slugs]: names the result had before a key given later renamed it (before fetching began)
  cite                  the citation key exactly as the caller gave it (a .bib key may hold ':' or '/'), else absent
  wanted                the version the caller wants: published (default) | accepted | preprint
  request               {given}: what identify was asked for (an id or url)
  record_of             preprint | published: which version the CSL describes
  ids                   {doi, arxiv, pmid, pmcid}, each a string or null
  csl                   the paper's metadata as normalized CSL-JSON (identify.py says how), with `source` the agency
                        that gave it and, by name, what CSL has no variable for (arXiv's `categories`); `keyword` is
                        the authors' keywords as a list
  alt_titles            [str]: other titles the paper went by
  versions              {preprint?: {ids, latest, comment, title, abstract, author, categories?}, published: [{ids, venue,
                        year, title, title_differs, type, sources}], incomplete: [sources that did not answer]}
  files                 [{name, md5, kind, label: {title, version, source, detail, by, why}, check: ok | accepted |
                        unconfirmed | cannot_judge, accepted_reason?, url, evidence}]: every file of the paper, its
                        versions side by side; the paper's file is the one whose label is the wanted version
  outcome               {status, waiting_on?: [kinds of the paper's open handoffs: page, file, label], tried: [hosts
                        tried], last: {event, route, result, url} | null (the last try, handoff or answer)}; status:
                        got (a file of the paper is there, an unconfirmed one included; a supplement alone is not),
                        waiting (none yet, and a page or file handoff is open: an agent may still bring one), not_got
  enrichment            {incomplete: [sources]: identify's lookups (OpenAlex, Europe PMC) that did not answer,
                        openalex_keywords?: [str]: OpenAlex's model's keywords, a hint for tagging, never metadata}
  warnings              [str]: what identify noticed (an erratum-like title, a date filled in from another field)
  settled_at            when files and outcome were last folded
A stub result (identify could not identify the paper: a page with no metadata) holds only slug, slug_given, cite?,
wanted, request, warnings; its files are checked against nothing: cannot_judge.

Writers: identify writes all but files and outcome; settle() writes those two and settled_at, from fetch.jsonl, every
time from the whole log (so whoever folds last is right), and first opens a `label` handoff for each filed file
without a label (ask_labels), whichever command filed it. fetch, wait, claim and answer fold the results they touched
when they end; settle.py does it on its own, after the watcher filed something. The watcher and agents only append
events, through scripts.

Handoffs. Where a script reaches the edge of what it can be certain of, it writes a handoff: handoffs/<id>.json
{id, kind, taker, slug, pass, route, url, file, md5, code, note, paper: {title, doi, wanted}, evidence: {files,
...}, answers, at} and a `handoff` event. The evidence's long texts (a file's page excerpts, a page's words) and, for
a handoff about a PDF (file, label, left), pages 1-2 as images (pdftoppm) are files in handoffs/<id>/, listed in
evidence.files; the short facts stay in the record. Kinds (HANDOFF_TAKERS):
  page          a page fetch could not get a PDF from (a sign-in, a challenge, no PDF link): the paper's agent works
                it, then hands back with `fetch --start <url> --session pf-<slug>`, or answers with a verdict
  file          a file the check could not be certain of, held in unverified/: accept [--label] | refuse | unknown
  label         a filed file whose version is not settled yet: label (with --label, --why) | unknown
  left          a download in Downloads that matched no paper, or several: claim (with --slug) | not_ours
  browser_down  the browser itself failed (OpenCLI's BROWSER_CONNECT): resolved
A handoff is open until answered (answer()); a page or file handoff also closes once a confirmed file is filed for
its paper; a label handoff once its file has a label or is withdrawn; a left one once its file is filed. A paper with
an open page or file handoff is skipped by the bulk walk; its own agent's runs (fetch --session, --start) are not.
Answers that hold a paper on its route until the next pass: HOLD. Every other verdict, refuse and unknown let it go on.

Events, each with `at`:
  claim    {file, slug, result: claimed | refused | held | left, kind, code, md5, source, route?, proposal,
           evidence: {url?, page?, link?, file}, handoff?}: a file checked against a result (left: a download that
           matched no result, or several: {why, matched?, against})
  accept   claim's shape plus `reason` (and `unconfirmed`: answered unknown): a file filed on an agent's reading of it
  withdraw {slug, file, md5}: an unconfirmed file moved back to unverified/ when a confirmed one was filed
  arrival  {slug, md5, route, proposal, evidence}: how a file came that its claim could not see (Chrome downloaded
           it on a link fetch opened, and the watcher filed it from Downloads)
  label    {slug, md5, file, title, why, by}: the attachment title an agent gave a file
  pass     {pass, slug}: fetch is about to walk the chain for a paper without its file (from here on the watcher
           files a download for it)
  try      {pass, slug, route, url?, version?, result, check?, by?}: one candidate tried for one paper (an answer's
           verdict on a page handoff is logged as its try)
  handoff  {id, slug, kind, taker, md5?, route?, url?, path}; answer {id, slug, kind, answer, reason?, by}
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # not POSIX: appends rely on O_APPEND alone
    fcntl = None

from . import paper, titles, verify, web
from .cli import ACT, CANNOT, Stop

FILE_SUFFIXES = tuple(paper.KINDS.values())
# A file beside a result: <slug><kind suffix, its extension last>, numbered before the extension when one is taken.
FILE_RE = re.compile(r"(?P<kind>\.accepted|\.preprint|\.supplement)?(?:\.(?P<n>\d+))?\.(?P<ext>pdf|html)", re.I)
WANTED = ("published", "accepted", "preprint")
# The conclusions an agent may give on a page: the one table (fetch --help, answer --help).
VERDICTS = {
    "no_access": "the institution has no access to it",
    "no_pdf": "the page offers no PDF",
    "not_public": "not public (withdrawn, embargoed, not out yet)",
    "proxy_unconfigured": "the proxy does not serve this host (Host Needed)",
    "skipped_by_user": "the user said to skip it",
    "blocked": "the site blocked this browser (a 429, a bot check): the paper waits on the route until the next pass",
    "gate_timeout": "a gate nobody passed in time: the paper waits on the route until the next pass",
}
HOLD = ("blocked", "gate_timeout")
HANDOFF_TAKERS = {"page": "paper_agent", "file": "paper_agent", "label": "judge", "left": "judge",
                  "browser_down": "agent"}
ANSWERS = {"page": tuple(VERDICTS), "file": ("accept", "refuse", "unknown"), "label": ("label", "unknown"),
           "left": ("claim", "not_ours"), "browser_down": ("resolved",)}
PAGE_IMAGES_DPI = 80


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- the directory ------------------------------------------------------------------------------------------

class Work:
    def __init__(self, root):
        self.root = Path(root).expanduser().absolute()
        for name in ("results", "links", "handoffs", "inbox", "unverified", "scratch"):
            setattr(self, name, self.root / name)
        self.started, self.log, self.settings_path = self.root / ".started", self.root / "fetch.jsonl", self.root / "run.json"

    @classmethod
    def of(cls, result_path):
        """The directory a result file lives in (<dir>/results/<slug>.json)."""
        return cls(Path(result_path).absolute().parent.parent)

    def settings(self):
        try:
            value = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def set(self, **fields):
        """Merge fields into run.json (None removes one)."""
        merged = {k: v for k, v in {**self.settings(), **fields}.items() if v is not None}
        atomic_write(self.settings_path, json.dumps(merged, ensure_ascii=False, indent=2) + "\n")

    def files_of(self, slug):
        """Every file beside the result, in KINDS order, numbered ones after the first of their kind."""
        order = {s: i for i, s in enumerate(FILE_SUFFIXES)}
        out = []
        for f in self.results.glob(f"{glob_escape(slug)}.*"):
            m = FILE_RE.fullmatch(f.name[len(slug):])
            if m and f.name.startswith(slug) and f.is_file():
                suffix = (m["kind"] or "") + "." + m["ext"].lower()
                out.append((order.get(suffix, len(order)), int(m["n"] or 1), f))
        return [f for *_, f in sorted(out)]

    def append(self, event):
        """One line onto fetch.jsonl, under an exclusive lock: several agents' scripts and the watcher write it."""
        line = {**{k: v for k, v in event.items() if v is not None}, "at": now_iso()}
        fd = os.open(self.log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            if fcntl:
                fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)  # releases the lock
        return line

    def events(self, kind=None):
        """The log's events, oldest first (a broken line is skipped); only those of one `event` when given."""
        out = []
        try:
            with open(self.log, encoding="utf-8") as fh:
                for raw in fh:
                    try:
                        obj = json.loads(raw)
                    except ValueError:
                        continue
                    if isinstance(obj, dict) and (kind is None or obj.get("event") == kind):
                        out.append(obj)
        except OSError:
            pass
        return out

    def owns(self, path):
        """A file this run may consume when it files it: one in this directory, or one of this run's downloads.
        Anything else (a PDF in Zotero's storage, a file the user keeps) is copied and left where it is."""
        path = Path(path).absolute()
        if path.is_relative_to(self.root):
            return True
        dl = self.settings().get("downloads")
        try:
            return bool(dl) and path.parent == Path(dl).absolute() and self.started.exists() \
                and path.stat().st_mtime >= self.started.stat().st_mtime
        except OSError:
            return False


def glob_escape(text):
    return re.sub(r"([*?\[])", r"[\1]", text)


def atomic_write(path, text):
    """Replace a file's content at once (a temp file beside it, then os.replace), keeping the mode it had, or the
    mode an ordinary new file gets. Copied from paper-to-zotero/scripts/p2zlib/run.py (commit 90cecdf)."""
    path = Path(path)
    try:
        mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(value):
    return hashlib.sha1(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


# ---- results ------------------------------------------------------------------------------------------------

@dataclass
class Subject:
    """What a result says its paper is, in the terms the scripts look for it by. `arxiv` is the paper's arXiv id, also
    when the result describes its published version (versions.preprint): the preprint is a route to its text."""
    title: str = ""
    alt_titles: list = field(default_factory=list)
    doi: str | None = None
    arxiv: str | None = None
    surname: str | None = None
    year: int | None = None
    url: str | None = None


def first_str(value):
    """CSL keeps some strings as lists (title, container-title): the first non-empty one, or ""."""
    if isinstance(value, list):
        value = next((v for v in value if isinstance(v, str) and v.strip()), "")
    return value.strip() if isinstance(value, str) else ""


class Result(dict):
    """A result file's object, with its path; slug = the file name."""

    def __init__(self, path, data):
        super().__init__(data)
        self.path = Path(path)
        self.slug = self.path.stem

    @property
    def ids(self):
        return self.get("ids") if isinstance(self.get("ids"), dict) else {}

    @property
    def csl(self):
        return self.get("csl") if isinstance(self.get("csl"), dict) else {}

    @property
    def subject(self):
        csl, alts = self.csl, self.get("alt_titles")
        alts = [alts] if isinstance(alts, str) else alts if isinstance(alts, list) else []
        parts = ((csl.get("issued") or {}).get("date-parts") or [[None]])[0] or [None]
        preprint = ((self.get("versions") or {}).get("preprint") or {}).get("ids") or {}
        return Subject(title=first_str(csl.get("title")), alt_titles=[a for a in alts if isinstance(a, str) and a.strip()],
                       doi=self.ids.get("doi") or None, arxiv=self.ids.get("arxiv") or preprint.get("arxiv") or None,
                       surname=paper.first_surname(csl.get("author")),
                       year=parts[0] if isinstance(parts[0], int) else None, url=first_str(csl.get("URL")) or None)

    @property
    def stub(self):
        """Identify could not identify the paper: no metadata to check a file against."""
        return not self.csl

    @property
    def wanted(self):
        """The version the caller wants, as a label's version (titles.parse_title): published, accepted, preprint."""
        return self.get("wanted") if self.get("wanted") in WANTED else "published"

    @property
    def work(self):
        return Work.of(self.path)

    def file(self):
        """The paper's file (paper_file()), or None."""
        return paper_file(self.work, self)

    def save(self):
        atomic_write(self.path, json.dumps(self, ensure_ascii=False, indent=2) + "\n")


def read(path):
    """The result at path -> Result; a file that is not one JSON object -> Stop result_invalid."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Stop("result_invalid", exit=ACT, hint="No such result file.", path=str(path)) from None
    except (OSError, ValueError) as e:
        raise Stop("result_invalid", exit=ACT, hint="A result file holds one JSON object; identify the paper again.",
                   path=str(path), detail=str(e)) from None
    if not isinstance(data, dict):
        raise Stop("result_invalid", exit=ACT, hint="A result file holds one JSON object; identify the paper again.",
                   path=str(path))
    return Result(path, data)


def results_of(work):
    """The directory's results; a file that is not one is left out."""
    out = []
    for path in sorted(work.results.glob("*.json")):
        try:
            out.append(read(path))
        except Stop:
            continue
    return out


# ---- links: where copies may be had -------------------------------------------------------------------------

def links_inputs(res):
    sub = res.subject
    return [sub.doi, sub.arxiv, sub.url]


def links_of(res):
    """The result's links (fulltext_links), or None when there are none yet or they were found for other ids."""
    try:
        value = json.loads((res.work.links / f"{res.slug}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) and value.get("from") == fingerprint(links_inputs(res)) else None


def write_links(res, value, incomplete=()):
    res.work.links.mkdir(exist_ok=True)
    value = {**value, "from": fingerprint(links_inputs(res)), **({"incomplete": sorted(incomplete)} if incomplete else {})}
    atomic_write(res.work.links / f"{res.slug}.json", json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    return value


# ---- a paper's files and their labels -----------------------------------------------------------------------

def labels(work, slug, events):
    """The last label event of each of the result's files, by md5 ({md5: event}). An older log's label names its file
    instead: it counts for the file of that name."""
    names = {}
    out = {}
    for e in events:
        if e.get("event") != "label" or e.get("slug") != slug:
            continue
        md5 = e.get("md5")
        if not md5 and e.get("file"):
            if not names:
                names = {f.name: md5_of(f) for f in work.files_of(slug)}
            md5 = names.get(e["file"])
        if md5:
            out[md5] = e
    return out


def filed_by(work, slug, events):
    """The event that filed each of the result's files, by md5: claim or accept (claimed), with what an arrival adds."""
    return {e["md5"]: arrived(work, slug, e["md5"], events) for e in events
            if e.get("slug") == slug and e.get("event") in ("claim", "accept") and e.get("result") == "claimed"
            and e.get("md5")}


def paper_files(work, res, events=None):
    """The result's files but supplements, each as (path, md5, label version or None, unconfirmed)."""
    events = work.events() if events is None else events
    labelled, filed = labels(work, res.slug, events), filed_by(work, res.slug, events)
    out = []
    for f in work.files_of(res.slug):
        if paper.kind_of_file(f.name) == "supplement":
            continue
        md5 = md5_of(f)
        lab = labelled.get(md5)
        version = (titles.parse_title(lab["title"]) or {}).get("version") if lab else None
        out.append((f, md5, version, bool((filed.get(md5) or {}).get("unconfirmed"))))
    return out


def satisfied(work, res, events=None):
    """Whether the paper needs no more fetching: it has a confirmed file labelled the wanted version, or one with no
    label yet (it holds the paper until its label says otherwise), or a snapshot, or (a stub) any file. A file
    labelled another version, or Unknown, leaves the paper going down the chain (the spec's decision A)."""
    for f, _, version, unconfirmed in paper_files(work, res, events):
        if unconfirmed:
            continue
        if res.stub or version is None or version == res.wanted or paper.kind_of_file(f.name) == "snapshot":
            return True
    return False


VERSION_RANK = {"published": 1, "accepted": 2, "preprint": 3}


def paper_file(work, res, events=None):
    """The paper's file: confirmed before unconfirmed, the wanted version first, then published, accepted, preprint,
    the rest; None when the result has none."""
    files = paper_files(work, res, events)
    rank = lambda e: (e[3], 0 if e[2] == res.wanted else VERSION_RANK.get(e[2], 4))  # noqa: E731
    return min(files, key=rank)[0] if files else None


# ---- files reaching a result --------------------------------------------------------------------------------

def file_name(slug, kind, n=1):
    suffix = paper.KINDS[kind]
    if n == 1:
        return slug + suffix
    stem, ext = suffix.rsplit(".", 1)
    return f"{slug}{stem}.{n}.{ext}"


def place(work, slug, src, kind, consume=True):
    """File src beside the result under its kind's name -> ("claimed", its path). A file of the same content beside it
    already is that file; a name taken by another file gets the next number. src is consumed when `consume` (a file of
    this run), else copied and left where it was."""
    md5 = md5_of(src)
    same = next((f for f in work.files_of(slug) if md5_of(f) == md5), None)
    if same is not None:
        if consume and Path(src).absolute() != same.absolute():
            Path(src).unlink(missing_ok=True)
        return "claimed", same
    tmp = work.results / f".{slug}.{uuid.uuid4().hex[:8]}.tmp"
    shutil.copy2(src, tmp)
    try:
        n = 1
        while True:
            target = work.results / file_name(slug, kind, n)
            try:
                os.link(tmp, target)
                break
            except FileExistsError:
                n += 1
    finally:
        tmp.unlink(missing_ok=True)
    if consume:
        Path(src).unlink(missing_ok=True)
    return "claimed", target


def move(src, directory, name, consume=True):
    """Move (or, not consume, copy) src into directory under name, numbered when the name is taken -> the new path."""
    directory.mkdir(exist_ok=True)
    dest, n = directory / name, 2
    while dest.exists():
        stem, dot, ext = name.partition(".")
        dest, n = directory / f"{stem}-{n}{dot}{ext}", n + 1
    if consume:
        shutil.move(str(src), str(dest))
    else:
        shutil.copy2(src, dest)
    return dest


def withdraw_unconfirmed(work, slug, events=None):
    """A confirmed file was filed: any file of the paper filed unconfirmed goes back to unverified/ -> the events."""
    events = work.events() if events is None else events
    filed, out = filed_by(work, slug, events), []
    for f in work.files_of(slug):
        md5 = md5_of(f)
        if (filed.get(md5) or {}).get("unconfirmed"):
            dest = move(f, work.unverified, f.name)
            out.append(work.append({"event": "withdraw", "slug": slug, "file": dest.name, "md5": md5}))
    return out


def arrival(evidence, came=None):
    """What a claim or accept event says of its file's arrival, for its label: {route?, proposal, evidence}. `came`
    is how it came: {route, url (where it was downloaded), given (a version the agent named), page: {href, title,
    meta, words}, link: {url, why, text, near}}; a file from Downloads or from the agent comes without route or url. A url
    through the institution's proxy is turned back into the publisher's first."""
    came = came or {}
    url = web.unproxy(came["url"]) if came.get("url") else None
    page, link = dict(came.get("page") or {}), dict(came.get("link") or {})
    for part, key in ((page, "href"), (link, "url")):
        if part.get(key):
            part[key] = web.unproxy(part[key])
    file = {k: evidence[k] for k in ("excerpt", "excerpt_page_2", "excerpt_title_page", "pdf_dates", "arxiv_stamp",
                                     "html_title") if evidence.get(k)}
    check = {k: evidence[k] for k in ("title_page", "title_words", "doi_found", "dois_on_page_1", "first_author_found",
                                      "first_author_in_byline", "erratum_marker", "supplement_marker") if evidence.get(k)}
    ev = {"url": url, "page": page, "link": link, "file": file, "check": check}
    return {"route": came.get("route"), "proposal": paper.proposal(came.get("route"), url, came.get("given")),
            "evidence": {k: v for k, v in ev.items() if v}}


def claim(work, src, slug, *, kind=None, source=None, via=None, cache=None, came=None, consume=True, pass_=None):
    """Check a file against one result and act on the verdict's outcome (verify.outcome): pass -> filed beside the
    result; refuse -> unverified/; uncertain -> held in unverified/ with a `file` handoff for the paper's agent.
    -> the claim event, logged, with arrival(came) (and the handoff's id). `kind` as verify.kind_of takes it (a link's
    version, or None: the file's name says). `consume`: see place()."""
    src = Path(src)
    res = read(work.results / f"{slug}.json")
    verdict = verify.check(src, res, kind, cache)
    outcome = verify.outcome(verdict["code"], res.stub)
    came_fields = arrival(verdict["evidence"], came)
    if outcome == "pass":
        withdraw_unconfirmed(work, slug)  # first, so the confirmed file takes its kind's own name
        result, path = place(work, slug, src, verdict["kind"], consume)
    else:
        ext = ".html" if verdict["kind"] == "snapshot" else ".pdf"
        result = "held" if outcome == "uncertain" else "refused"
        path = move(src, work.unverified, f"{slug}.{via or 'file'}{ext}", consume)
    event = {"event": "claim", "file": path.name, "slug": slug, "result": result, "kind": verdict["kind"],
             "code": verdict["code"], "md5": verdict["md5"], "source": source, **came_fields}
    if result == "held":
        event["handoff"] = handoff(work, "file", res, pass_=pass_, route=came_fields.get("route"), file=path,
                                   md5=verdict["md5"], code=verdict["code"], evidence=came_fields["evidence"])["id"]
    return work.append(event)


def accept(work, src, slug, reason, kind=None, consume=True, unconfirmed=False):
    """File a file the check did not file, on an agent's reading of it -> the accept event (claim's shape plus the
    reason; unconfirmed when the agent could not tell), logged. `kind` is the version the agent named. A file already
    beside the result (a stub's, filed as cannot_judge) is accepted where it is."""
    src = Path(src)
    if not src.is_file():
        raise Stop("file_not_found", hint="No such file; give the path of the file to accept.", file=str(src))
    read(work.results / f"{slug}.json")
    ex = verify.extract(src)
    named, kind = kind, verify.kind_of(src, kind)
    md5 = ex.md5 if ex else md5_of(src)
    evidence = verify.evidence_base(ex, kind) if ex else {}
    refused = next((e for e in reversed(work.events("claim")) if e.get("slug") == slug and e.get("md5") == md5), {})
    seen = refused.get("evidence") or {}  # how the file came, when it came through claim before the check held it
    came = {"route": refused.get("route"), "url": seen.get("url"), "page": seen.get("page"), "link": seen.get("link"),
            "given": named}
    if not unconfirmed:
        withdraw_unconfirmed(work, slug)
    here = next((f for f in work.files_of(slug) if md5_of(f) == md5), None)
    result, path = ("claimed", here) if here else place(work, slug, src, kind, consume)
    return work.append({"event": "accept", "file": path.name, "slug": slug, "result": result, "kind": kind, "md5": md5,
                        "reason": reason, "source": str(src), "unconfirmed": unconfirmed or None,
                        **arrival(evidence, came)})


def arrived(work, slug, md5, events=None):
    """How this result's file with this md5 came: the claim or accept event that filed it, with what an arrival event
    about it adds (route, proposal, url, page, link; the claim's file evidence stays), or None."""
    filed = extra = None
    for e in work.events() if events is None else events:
        if e.get("slug") != slug or e.get("md5") != md5:
            continue
        if e.get("event") == "arrival":
            extra = e
        elif e.get("event") in ("claim", "accept") and e.get("result") == "claimed":
            filed = e
    if not (filed and extra):
        return filed or extra
    seen = {k: v for k, v in (extra.get("evidence") or {}).items() if k not in ("file", "check")}
    return {**filed, "route": extra.get("route"), "proposal": extra.get("proposal"),
            "evidence": {**(filed.get("evidence") or {}), **seen}}


def note_arrival(work, slug, came):
    """Record how the result's latest filed file came when its claim could not see it (Chrome downloaded it on a link
    fetch opened, and the watcher filed it from Downloads) -> the arrival event; None when there is no file, or its
    claim knew."""
    filed = [e for e in work.events() if e.get("slug") == slug and e.get("event") in ("claim", "accept")
             and e.get("result") == "claimed"]
    if not filed:
        return None
    md5 = filed[-1]["md5"]
    known = arrived(work, slug, md5) or {}
    if known.get("route"):
        return None
    return work.append({"event": "arrival", "slug": slug, "md5": md5,
                        **arrival((known.get("evidence") or {}).get("file") or {}, came)})


def label(work, slug, title, why, by="agent", md5=None):
    """An agent's attachment title for one of the result's files (md5; default the paper's file) -> the label event,
    logged. A title outside the scheme (titles.py) is a Stop."""
    if not titles.parse_title(title):
        raise Stop("bad_label", hint=f"An attachment title is <Version>-<Source>-<detail>, a version word of "
                   f"{', '.join(titles.VERSIONS)} (references/attachment-titles.md).", title=title)
    res = read(work.results / f"{slug}.json")
    files = {md5_of(f): f for f in work.files_of(res.slug)}
    if md5 is None:
        own = paper_file(work, res)
        md5 = md5_of(own) if own else None
    if md5 not in files:
        raise Stop("no_such_file", hint="The result has no file with that md5; settle.py lists its files.", md5=md5,
                   files={f.name: m for m, f in files.items()})
    return work.append({"event": "label", "slug": slug, "md5": md5, "file": files[md5].name, "title": title.strip(),
                        "why": why, "by": by})


# ---- handoffs ------------------------------------------------------------------------------------------------

TEXTS = ("excerpt", "excerpt_page_2", "excerpt_title_page")  # a file's evidence written to files, not the record


def handoff(work, kind, res=None, *, slug=None, pass_=None, route=None, url=None, file=None, md5=None, code=None,
            evidence=None, note=None):
    """Hand one thing to an agent -> the handoff record, written once to handoffs/<id>.json (id: <slug>.<n>, or
    <kind>.<n> without a paper) with its evidence files in handoffs/<id>/, and logged as a `handoff` event."""
    slug = res.slug if res is not None else slug
    work.handoffs.mkdir(exist_ok=True)
    prefix, n = slug or kind, 1
    while True:
        hid = f"{prefix}.{n}"
        try:
            fd = os.open(work.handoffs / f"{hid}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            break
        except FileExistsError:
            n += 1
    os.close(fd)
    files = evidence_files(work.handoffs / hid, file, evidence or {})
    record = {"id": hid, "kind": kind, "taker": HANDOFF_TAKERS[kind], "slug": slug, "pass": pass_, "route": route,
              "url": url, "file": str(file) if file else None, "md5": md5, "code": code, "note": note,
              "paper": {"title": res.subject.title, "doi": res.subject.doi, "wanted": res.wanted} if res else None,
              "evidence": {**{k: v for k, v in (evidence or {}).items() if k not in ("file", "words")},
                           "file": {k: v for k, v in ((evidence or {}).get("file") or {}).items() if k not in TEXTS} or None,
                           "files": files},
              "answers": list(ANSWERS[kind]), "at": now_iso()}
    record = {k: v for k, v in record.items() if v is not None}
    atomic_write(work.handoffs / f"{hid}.json", json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    work.append({"event": "handoff", "id": hid, "slug": slug, "kind": kind, "taker": record["taker"], "md5": md5,
                 "route": route, "url": url, "path": str(work.handoffs / f"{hid}.json")})
    return record


def evidence_files(folder, file, evidence):
    """Write a handoff's evidence where an agent reads it rather than in the conversation -> [paths]: the file's page
    texts and, for a PDF with poppler's pdftoppm, pages 1-2 as images; a page's words."""
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    texts = dict(evidence.get("file") or {})
    if evidence.get("words"):
        texts["page_words"] = evidence["words"]
    for name in (*TEXTS, "page_words"):
        if texts.get(name):
            path = folder / f"{name}.txt"
            path.write_text(texts[name], encoding="utf-8")
            out.append(str(path))
    if file and str(file).lower().endswith(".pdf") and shutil.which("pdftoppm"):
        try:
            subprocess.run(["pdftoppm", "-r", str(PAGE_IMAGES_DPI), "-f", "1", "-l", "2", "-png", str(file),
                            str(folder / "page")], capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            pass
        out += [str(p) for p in sorted(folder.glob("page-*.png"))]
    return out


def read_handoff(work, hid):
    path = work.handoffs / f"{hid}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Stop("no_such_handoff", exit=ACT, hint="No such handoff in this directory: pf.py todo lists the open ones.",
                   id=hid) from None
    return value


def open_handoffs(work, events=None, slug=None):
    """The handoff events still open, oldest first (only one paper's, with slug): not answered, and for a page or
    file handoff no confirmed file filed for its paper since, for a label one its file neither labelled nor withdrawn,
    for a left one its file not filed."""
    events = work.events() if events is None else events
    answered = {e.get("id") for e in events if e.get("event") == "answer"}
    out = []
    for i, h in enumerate(events):
        if h.get("event") != "handoff" or h.get("id") in answered or (slug and h.get("slug") != slug):
            continue
        later = events[i + 1:]
        if h["kind"] in ("page", "file"):
            closed = any(e.get("slug") == h.get("slug") and e.get("event") in ("claim", "accept")
                         and e.get("result") == "claimed" and not e.get("unconfirmed") for e in later)
        elif h["kind"] == "label":
            closed = any(e.get("event") in ("label", "withdraw") and e.get("slug") == h.get("slug")
                         and e.get("md5") == h.get("md5") for e in later)
        elif h["kind"] == "left":
            closed = any(e.get("event") in ("claim", "accept") and e.get("result") == "claimed"
                         and e.get("md5") == h.get("md5") for e in later)
        else:
            closed = False
        if not closed:
            out.append(h)
    return out


def held_on_route(work, slug, pass_, events=None):
    """Whether an answer this pass holds the paper on its route until the next pass (HOLD)."""
    events = work.events() if events is None else events
    return any(e.get("event") == "try" and e.get("slug") == slug and e.get("pass") == pass_ and e.get("result") in HOLD
               for e in events)


def answer(work, hid, word, *, reason=None, title=None, why=None, slug=None, version=None, by="agent"):
    """An agent's answer to a handoff -> the events it wrote (the answer last). page: a verdict, logged as the
    candidate's try; file: accept (filed, labelled when title is given) | refuse | unknown (filed unconfirmed); label:
    label (title, why) | unknown (Unknown-<Source>); left: claim (filed for slug) | not_ours; browser_down: resolved."""
    record = read_handoff(work, hid)
    kind = record["kind"]
    if word not in ANSWERS[kind]:
        raise Stop("bad_answer", exit=ACT, hint=f"A {kind} handoff takes one of: {', '.join(ANSWERS[kind])}.",
                   id=hid, answer=word)
    if not any(h["id"] == hid for h in open_handoffs(work)):
        raise Stop("not_open", exit=ACT, hint="This handoff is answered or closed already: pf.py todo lists the open ones.",
                   id=hid)
    out, target = [], record.get("slug")
    if kind == "page":
        out.append(work.append({"event": "try", "pass": record.get("pass"), "slug": target, "route": record.get("route"),
                                "url": record.get("url"), "result": word, "by": by}))
    elif kind == "file" and word in ("accept", "unknown"):
        out.append(accept(work, record["file"], target, reason, kind=version, unconfirmed=word == "unknown"))
        if word == "accept" and title:
            out.append(label(work, target, title, why, by=by, md5=out[-1]["md5"]))
    elif kind == "label":
        if word == "label":
            if not title:
                raise Stop("no_label", exit=ACT, hint="Give the attachment title: --label TITLE --why WHY.", id=hid)
            out.append(label(work, target, title, why, by=by, md5=record.get("md5")))
        else:
            came = arrived(work, target, record.get("md5")) or {}
            source = (came.get("proposal") or {}).get("source")
            out.append(label(work, target, titles.label_title("Unknown", source), why or reason, by=by,
                             md5=record.get("md5")))
    elif kind == "left" and word == "claim":
        if not slug:
            raise Stop("no_slug", exit=ACT, hint="Name the paper the file is for: --slug SLUG.", id=hid)
        target = slug
        out.append(accept(work, record["file"], slug, reason, kind=version))
    out.append(work.append({"event": "answer", "id": hid, "slug": target, "kind": kind, "answer": word,
                            "reason": reason, "by": by}))
    return out


# ---- the fold: fetch.jsonl -> each result's files and outcome -----------------------------------------------

def folded(work, res, events):
    """The result's files and outcome as the log tells them (nothing written)."""
    mine = [e for e in events if e.get("slug") == res.slug]
    labelled = labels(work, res.slug, mine)
    files = []
    for f in work.files_of(res.slug):
        md5, kind = md5_of(f), paper.kind_of_file(f.name)
        came = arrived(work, res.slug, md5, mine) or {}
        given = labelled.get(md5)
        if given:
            parsed = titles.parse_title(given["title"])
            lab = {"title": given["title"], **parsed, "by": given.get("by"), "why": given.get("why")}
        else:
            source = (came.get("proposal") or {}).get("source")
            title = titles.label_title("Snapshot" if kind == "snapshot" else "Unknown", source)
            lab = {"title": title, **titles.parse_title(title), "by": "settle", "why": "no label given"}
        check = ("unconfirmed" if came.get("unconfirmed") else "accepted" if came.get("event") == "accept"
                 else "cannot_judge" if came.get("code") == "cannot_judge" else "ok" if came else "cannot_judge")
        entry = {"name": f.name, "md5": md5, "kind": kind, "label": lab, "check": check,
                 **({"accepted_reason": came.get("reason")} if came.get("event") == "accept" else {}),
                 "url": (came.get("evidence") or {}).get("url"), "evidence": came.get("evidence") or {}}
        files.append(entry)
    got = any(f["kind"] != "supplement" for f in files)
    waiting_on = sorted({h["kind"] for h in open_handoffs(work, events, res.slug)})
    tries = [e for e in mine if e.get("event") == "try"]
    tried = list(dict.fromkeys(paper.host_of(web.unproxy(e["url"])) for e in tries if e.get("url")))  # the site, not the proxy
    last = next((e for e in reversed(mine) if e.get("event") in ("try", "handoff", "answer")), None)
    status = "got" if got else "waiting" if {"page", "file"} & set(waiting_on) else "not_got"  # a label brings no file
    return files, {"status": status, **({"waiting_on": waiting_on} if waiting_on else {}), "tried": tried,
                   "last": {"event": last["event"], "route": last.get("route"),
                            "result": last.get("result") or last.get("answer") or last.get("why") or last.get("kind"),
                            "url": last.get("url")} if last else None}


def ask_labels(work, results, events=None):
    """A `label` handoff for each filed file of these results with no label and none asked for yet, with the host's
    word recorded at its arrival -> the records. A snapshot needs none: its bytes say what it is."""
    events = work.events() if events is None else events
    asked = {(h.get("slug"), h.get("md5")) for h in open_handoffs(work, events) if h["kind"] == "label"}
    out = []
    for res in results:
        labelled = labels(work, res.slug, events)
        for f in work.files_of(res.slug):
            if paper.kind_of_file(f.name) == "snapshot":
                continue
            md5 = md5_of(f)
            if md5 in labelled or (res.slug, md5) in asked:
                continue
            e = arrived(work, res.slug, md5, events) or {}
            ev = e.get("evidence") or {}
            out.append(handoff(work, "label", res, route=e.get("route"), url=ev.get("url"), file=f, md5=md5,
                               evidence={**ev, "proposal": (e.get("proposal") or {}).get("title")}))
    return out


def settle(work, results=None):
    """Fold the log into the results named (default: all) and write them -> [(result, changed)]. A file without a
    label is asked about first (ask_labels), whichever command filed it."""
    results = [read(r.path) for r in (results if results is not None else results_of(work))]  # as identify last wrote them
    ask_labels(work, results)
    events, out = work.events(), []
    for res in results:
        files, outcome = folded(work, res, events)
        changed = (files, outcome) != (res.get("files"), res.get("outcome"))
        res.update(files=files, outcome=outcome, settled_at=now_iso())
        res.save()
        out.append((res, changed))
    return out


# ---- the browser's Downloads ---------------------------------------------------------------------------------

PARTIAL = (".crdownload", ".part", ".tmp", ".download")


def new_downloads(work, dl):
    """Complete files newer than .started, oldest first."""
    if not work.started.exists():
        raise Stop("no_started", exit=CANNOT, hint="The directory has no .started: run ready.py first.")
    started, out = work.started.stat().st_mtime, []
    for f in dl.iterdir():
        try:
            if f.is_file() and not f.name.startswith(".") and f.suffix.lower() not in PARTIAL and f.stat().st_mtime >= started:
                out.append((f.stat().st_mtime, f))
        except OSError:
            continue
    return [f for _, f in sorted(out)]


def wanted(work, results):
    """The results a download may be for: fetch was asked for their file (a pass, try or handoff event names them)
    and they are not satisfied yet. A paper whose file nobody asked for (the caller has it already) is never matched."""
    events = work.events()
    asked = {e.get("slug") for e in events if e.get("event") in ("pass", "try", "handoff")}
    return [r for r in results if r.slug in asked and not satisfied(work, r, events)]


class Scanner:
    """Claims the new files in Downloads (dl), remembering what it saw: a file is looked at again only when its size or
    time changed, and counts as complete once two looks found it the same; a file that is no PDF is never opened
    again; the results are read again only when results/ changed. Each PDF is checked against every result fetch was
    asked for and that is not satisfied yet (wanted()): passing for exactly one -> filed, else left there (it may be
    the user's own; an agent's own download is handed over with `claim --file`) and checked again only against
    results that became wanted since."""

    def __init__(self, work, dl):
        self.work, self.dl = work, Path(dl)
        self.seen, self.md5 = {}, {}  # name -> (size, mtime) at the last look; name -> ((size, mtime), md5)
        self.results, self.results_at = [], None

    def scan(self):
        """One look -> the events, logged."""
        changed = self.work.results.stat().st_mtime_ns
        if changed != self.results_at:
            self.results, self.results_at = results_of(self.work), changed
        left = {}  # (name, md5) -> the slugs it was checked against when it was left
        for e in self.work.events("claim"):
            if e.get("result") == "left":
                left.setdefault((e.get("file"), e.get("md5")), set()).update(e.get("against") or [])
        events = []
        for f in new_downloads(self.work, self.dl):
            try:
                st = f.stat()
                sig, before = (st.st_size, st.st_mtime_ns), self.seen.get(f.name)
                self.seen[f.name] = sig
                if sig != before or self.md5.get(f.name, (None,))[0] == "no pdf":
                    continue  # new or still growing: the next look decides; or known not to be a PDF
                if self.md5.get(f.name, (None,))[0] != sig:
                    with open(f, "rb") as fh:
                        if not fh.read(1024).lstrip().startswith(b"%PDF-"):
                            self.md5[f.name] = ("no pdf", None)
                            continue
                    self.md5[f.name] = (sig, md5_of(f))
            except OSError:
                continue
            md5 = self.md5[f.name][1]
            results = [r for r in wanted(self.work, self.results) if r.slug not in left.get((f.name, md5), ())]
            if not results:
                continue
            cache = {}
            matched = [r.slug for r in results if verify.check(f, r, cache=cache)["code"] in verify.PASS_CODES]
            if len(matched) == 1:
                events.append(claim(self.work, f, matched[0], cache=cache, source=str(f)))
            else:
                hid = handoff(self.work, "left", file=f, md5=md5, note="ambiguous" if matched else "unmatched",
                              evidence={"matched": matched or None, "against": sorted(r.slug for r in results)})["id"]
                events.append(self.work.append({"event": "claim", "file": f.name, "result": "left", "md5": md5,
                                                "source": str(f), "why": "ambiguous" if matched else "unmatched",
                                                "matched": matched or None, "handoff": hid,
                                                "against": sorted(r.slug for r in results)}))
                left.setdefault((f.name, md5), set()).update(r.slug for r in results)
        return events


def watcher_alive(work):
    """Whether the watcher (claim.py --watch) of this directory is running: its pid in run.json, alive."""
    pid = work.settings().get("watcher")
    try:
        os.kill(int(pid), 0)
    except PermissionError:  # alive, another user's
        return True
    except (TypeError, ValueError, ProcessLookupError):
        return False
    return True
