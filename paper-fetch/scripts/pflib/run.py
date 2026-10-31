"""paper-fetch's directory: its layout and settings, the result files, the log, how a file reaches a result, and the
fold of the log into the results.

Layout (ready.py makes it). <dir> is <scratch>/paper-fetch/, or the directory a caller names with -o (an import:
<scratch>/paper-to-zotero/fetch/):
  results/<slug>.json   one result per paper (below); its files beside it, named by the version each was wanted as
                        (its kind, paper.KINDS): <slug>.pdf, .accepted.pdf, .preprint.pdf, .supplement.pdf, .html
  links/<slug>.json     where copies may be had (fulltext_links): {from, items: [{url, source, version: published |
                        accepted | preprint | unknown, needs_browser}], incomplete?: [sources]}
  inbox/ stray/ unverified/ scratch/    bytes a script fetched / second copies / files the check refused / one-off files
  .started              the run's start: Downloads files newer than it are this run's
  run.json              the run's settings: downloads, session, the watcher's pid
  fetch.jsonl           what happened, one JSON event per line, appended (below)
  pace.json             request gaps per host (web.Pacer)
A caller reads results/ and nothing else.

A result file, results/<slug>.json, one JSON object:
  slug, slug_given      the file's name; whether the caller chose it (--slug: a citation key)
  request               {given}: what identify was asked for (an id or url)
  record_of             preprint | published: which version the CSL describes
  ids                   {doi, arxiv, pmid, pmcid}, each a string or null
  csl                   the paper's metadata as normalized CSL-JSON (identify.py says how), with `source` the agency
                        that gave it and, by name, what CSL has no variable for (arXiv's `categories`)
  alt_titles            [str]: other titles the paper went by
  versions              {preprint?: {ids, latest, comment, title, abstract, author, categories?}, published: [{ids, venue, year,
                        title, title_differs, type, sources}], incomplete: [sources that did not answer]}
  files                 [{name, md5, kind, label: {title, version, source, detail, by, why}, check: ok | accepted |
                        cannot_judge, accepted_reason?, url, evidence}]
  outcome               {status: got | not_got | waiting, tried: [hosts], stop: {route, why, url} | null}
  warnings              [str]: what identify noticed (an erratum-like title, a date filled in from another field)
  settled_at            when files and outcome were last folded
A stub result (identify could not identify the paper: a page with no metadata) holds only slug, request, warnings;
its files are checked against nothing: cannot_judge.

Writers: identify writes all but files and outcome; settle() writes those two and settled_at, from fetch.jsonl,
every time from the whole log (so whoever folds last is right). fetch, wait and claim (--file, --accept, --label)
fold the results they touched when they end; settle.py does it on its own, after the watcher filed something. The
watcher and the agent only
append events.

Events, each with `at`:
  claim    {file, slug, result: claimed | stray | unverified | left, kind, code, md5, source, route?, proposal,
           evidence: {url?, page?, link?, file}}: a file checked against a result (left: a download that matched no
           result, or several: {why, matched?, against})
  accept   claim's shape plus `reason`: a file the check refused, filed on the agent's reading of it
  arrival  {slug, md5, route, proposal, evidence}: how a file came that its claim could not see (Chrome downloaded
           it on a link fetch opened, and the watcher filed it from Downloads)
  label    {slug, file, title, why, by}: the attachment title the agent gave a file
  pass     {pass, slug}: fetch is about to walk the chain for a paper without a file (from here on the watcher
           files a download for it)
  try      {pass, slug, route, url?, version?, result, check?, by?}: one route tried for one paper
  stop     {pass, slug, route, url, why, gate?, page, title}: where fetch stopped for the agent
"""
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import paper, titles, verify, web
from .cli import ACT, CANNOT, Stop

FILE_SUFFIXES = tuple(paper.KINDS.values())


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- the directory ------------------------------------------------------------------------------------------

class Work:
    def __init__(self, root):
        self.root = Path(root).expanduser().absolute()
        for name in ("results", "links", "inbox", "stray", "unverified", "scratch"):
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

    def file_of(self, slug):
        """The result's own file, of whichever kind, or None."""
        return next((f for f in (self.results / (slug + s) for s in FILE_SUFFIXES) if f.is_file()), None)

    def files_of(self, slug):
        """Every file beside the result, in KINDS order."""
        return [f for f in (self.results / (slug + s) for s in FILE_SUFFIXES) if f.is_file()]

    def append(self, event):
        """One line onto fetch.jsonl, written in one call on an O_APPEND descriptor so parallel writers never interleave."""
        line = {**{k: v for k, v in event.items() if v is not None}, "at": now_iso()}
        fd = os.open(self.log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
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
    def work(self):
        return Work.of(self.path)

    def file(self):
        """The result's own file, of whichever kind, or None."""
        return self.work.file_of(self.slug)

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


# ---- files reaching a result --------------------------------------------------------------------------------

def place(work, slug, src, kind, consume=True):
    """File src as the result's file of that kind -> ("claimed" | "stray", its new path). src is consumed when
    `consume` (a file of this run), else copied and left where it was. First come, first served: the copy is linked to
    its final name, so a result that already has its file (the paper came another way meanwhile) sends this one to
    stray/."""
    target = work.results / (slug + paper.KINDS[kind])
    if work.file_of(slug) is not None:
        return "stray", move(src, work.stray, target.name, consume)
    tmp = work.results / f".{slug}.{uuid.uuid4().hex[:8]}.tmp"
    shutil.copy2(src, tmp)
    try:
        os.link(tmp, target)
    except FileExistsError:
        return "stray", move(src, work.stray, target.name, consume)
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
    file = {k: evidence[k] for k in ("excerpt", "excerpt_page_2", "pdf_dates", "arxiv_stamp", "html_title") if evidence.get(k)}
    ev = {"url": url, "page": page, "link": link, "file": file}
    return {"route": came.get("route"), "proposal": paper.proposal(came.get("route"), url, came.get("given")),
            "evidence": {k: v for k, v in ev.items() if v}}


def passes(res, code):
    """A verdict that files the file: a pass, or cannot_judge for a stub result, which has nothing to check against."""
    return code in verify.PASS_CODES or (code == "cannot_judge" and res.stub)


def claim(work, src, slug, *, kind=None, source=None, via=None, cache=None, came=None, consume=True):
    """Check a file against one result and file it: passing -> beside the result under its kind's name (stray/ when
    the result has its file already), failing -> unverified/<slug>.<via>.<ext> for the agent to look at. -> the claim
    event, logged, with arrival(came). `kind` as verify.kind_of takes it (a link's version, or None: the file's name
    says). `consume`: see place()."""
    src = Path(src)
    res = read(work.results / f"{slug}.json")
    verdict = verify.check(src, res, kind, cache)
    if passes(res, verdict["code"]):
        result, path = place(work, slug, src, verdict["kind"], consume)
    else:
        ext = ".html" if verdict["kind"] == "snapshot" else ".pdf"
        result, path = "unverified", move(src, work.unverified, f"{slug}.{via or 'file'}{ext}", consume)
    return work.append({"event": "claim", "file": path.name, "slug": slug, "result": result, "kind": verdict["kind"],
                        "code": verdict["code"], "md5": verdict["md5"], "source": source,
                        **arrival(verdict["evidence"], came)})


def accept(work, src, slug, reason, kind=None, consume=True):
    """File a file the check refused, on the agent's reading of it -> the accept event (claim's shape plus the
    reason), logged. `kind` is the version the agent named. A file already beside the result (a stub's, filed as
    cannot_judge) is accepted where it is."""
    src = Path(src)
    if not src.is_file():
        raise Stop("file_not_found", hint="No such file; give the path of the file to accept.", file=str(src))
    read(work.results / f"{slug}.json")
    ex = verify.extract(src)
    named, kind = kind, verify.kind_of(src, kind)
    md5 = ex.md5 if ex else md5_of(src)
    evidence = verify.evidence_base(ex, kind) if ex else {}
    refused = next((e for e in reversed(work.events("claim")) if e.get("slug") == slug and e.get("md5") == md5), {})
    seen = refused.get("evidence") or {}  # how the file came, when it came through claim before the check refused it
    came = {"route": refused.get("route"), "url": seen.get("url"), "page": seen.get("page"), "link": seen.get("link"),
            "given": named}
    here = next((f for f in work.files_of(slug) if md5_of(f) == md5), None)
    result, path = ("claimed", here) if here else place(work, slug, src, kind, consume)
    return work.append({"event": "accept", "file": path.name, "slug": slug, "result": result, "kind": kind, "md5": md5,
                        "reason": reason, "source": str(src), **arrival(evidence, came)})


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
    seen = {k: v for k, v in (extra.get("evidence") or {}).items() if k != "file"}
    return {**filed, "route": extra.get("route"), "proposal": extra.get("proposal"),
            "evidence": {**(filed.get("evidence") or {}), **seen}}


def note_arrival(work, slug, came):
    """Record how the result's file came when its claim could not see it (Chrome downloaded it on a link fetch opened,
    and the watcher filed it from Downloads) -> the arrival event; None when there is no file, or its claim knew."""
    f = work.file_of(slug)
    if f is None:
        return None
    md5 = md5_of(f)
    known = arrived(work, slug, md5) or {}
    if known.get("route"):
        return None
    return work.append({"event": "arrival", "slug": slug, "md5": md5,
                        **arrival((known.get("evidence") or {}).get("file") or {}, came)})


def label(work, slug, title, why, by="agent", file=None):
    """The agent's attachment title for one of the result's files (file: its name; default the paper's own file)
    -> the label event, logged. A title outside the scheme (titles.py) is a Stop."""
    if not titles.parse_title(title):
        raise Stop("bad_label", hint=f"An attachment title is <Version>-<Source>-<detail>, a version word of "
                   f"{', '.join(titles.VERSIONS)} (references/attachment-titles.md).", title=title)
    res = read(work.results / f"{slug}.json")
    files = {f.name: f for f in work.files_of(res.slug)}
    name = file or next((n for n in files if paper.kind_of_file(n) != "supplement"), None)
    if name not in files:
        raise Stop("no_such_file", hint="The result has no such file; settle.py lists its files.", file=name,
                   files=sorted(files))
    return work.append({"event": "label", "slug": slug, "file": name, "title": title.strip(), "why": why, "by": by})


def label_of(work, slug, name, events=None):
    """The last label event for the result's file `name`, or None: the file has no label yet."""
    return next((e for e in reversed(work.events("label") if events is None else events)
                 if e.get("event") == "label" and e.get("slug") == slug and e.get("file") == name), None)


# ---- the fold: fetch.jsonl -> each result's files and outcome -----------------------------------------------

def folded(work, res, events):
    """The result's files and outcome as the log tells them (nothing written)."""
    mine = [e for e in events if e.get("slug") == res.slug]
    files = []
    for f in work.files_of(res.slug):
        md5, kind = md5_of(f), paper.kind_of_file(f.name)
        came = arrived(work, res.slug, md5, mine) or {}
        given = label_of(work, res.slug, f.name, mine)
        if given:
            parsed = titles.parse_title(given["title"])
            lab = {"title": given["title"], **parsed, "by": given.get("by"), "why": given.get("why")}
        else:
            source = (came.get("proposal") or {}).get("source")
            title = titles.label_title("Snapshot" if kind == "snapshot" else "Unknown", source)
            lab = {"title": title, **titles.parse_title(title), "by": "settle", "why": "no label given"}
        check = ("accepted" if came.get("event") == "accept" else "cannot_judge" if came.get("code") == "cannot_judge"
                 else "ok" if came else "cannot_judge")
        entry = {"name": f.name, "md5": md5, "kind": kind, "label": lab, "check": check,
                 **({"accepted_reason": came.get("reason")} if check == "accepted" else {}),
                 "url": (came.get("evidence") or {}).get("url"), "evidence": came.get("evidence") or {}}
        files.append(entry)
    got = any(f["kind"] != "supplement" for f in files)
    tries = [e for e in mine if e.get("event") == "try"]
    tried = list(dict.fromkeys(paper.host_of(e["url"]) for e in tries if e.get("url")))
    last = next((e for e in reversed(mine) if e.get("event") in ("try", "stop")), None)
    stop = last if last and last.get("event") == "stop" else None
    status = "got" if got else "waiting" if stop and stop.get("gate") else "not_got"
    return files, {"status": status, "tried": tried,
                   "stop": {k: stop.get(k) for k in ("route", "why", "url")} if stop else None}


def settle(work, results=None):
    """Fold the log into the results named (default: all) and write them -> [(result, changed)]."""
    events, out = work.events(), []
    for res in results if results is not None else results_of(work):
        res = read(res.path)                       # as identify last wrote it
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
    """The results a download may be for: fetch was asked for their file (a pass, try or stop event names them) and
    they have none yet. A paper whose file nobody asked for (the caller has it already) is never matched."""
    asked = {e.get("slug") for e in work.events() if e.get("event") in ("pass", "try", "stop")}
    return [r for r in results if r.slug in asked and work.file_of(r.slug) is None]


class Scanner:
    """Claims the new files in Downloads (dl), remembering what it saw: a file is looked at again only when its size or
    time changed, and counts as complete once two looks found it the same; a file that is no PDF is never opened
    again; the results are read again only when results/ changed. Each PDF is checked against every result fetch was
    asked for and that has no file yet (wanted()): one match -> filed, else left there (it may be the user's own) and
    checked again only against results that became wanted since."""

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
                events.append(self.work.append({"event": "claim", "file": f.name, "result": "left", "md5": md5,
                                                "source": str(f), "why": "ambiguous" if matched else "unmatched",
                                                "matched": matched or None, "against": sorted(r.slug for r in results)}))
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
