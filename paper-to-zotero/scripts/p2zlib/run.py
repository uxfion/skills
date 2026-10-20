"""One import run's work directory: its layout and settings, the records and when a block of theirs is done, the log.

Layout (ready.py makes it):
  records/<slug>.json     one record per paper; its file beside it, named by kind: <slug>.pdf, <slug>.accepted.pdf,
                          <slug>.preprint.pdf, <slug>.supplement.pdf, <slug>.html (paper.KINDS)
  inbox/ stray/ unverified/ scratch/    bytes a script fetched / second copies / files the check refused / one-off files
  .started                the run's start: Downloads files newer than it are this run's
  run.json                the run's settings: downloads, session, the watcher's pid
  fetch.jsonl             what happened to the files: one JSON line per event, appended
  pace.json               request gaps per host (web.Pacer)

A record is records/<slug>.json, one JSON object; its slug is the file name. The agent's fields — scripts read
them and never change them; doi_to_item writes their first values when it drafts the record:
  item            the Zotero item to create (doi_to_item drafts it; the agent revises it; --redraft replaces it)
  warnings        [str]: what doi_to_item noticed while drafting (an erratum-like title, a guessed type)
  tags            [{tag, type}]               collection     KEY or [KEYS]          citationKey   str
  alt_titles      [str]: other titles the file may carry (the preprint's, after a redraft)
  distinct_from   [KEYS]: library items the agent judged to be other papers
  same_as         KEY: the library item the agent judged to be this paper (a near match settled)
  keep_preprint   str: why the preprint stays the item although published_candidates has entries
  blocker         str: what the record waits for (the last pass with the user, ...)
Blocks, each written by one script and nothing else:
  published_candidates  doi_to_item, for a preprint item only:
                  {from, items: [{doi, venue, year, title, url?, sources: [arxiv | crossref], title_differs, type?,
                  journal_ref?}], comment?: arXiv's comment, incomplete?}
  checks          check_item: {from, code: ok | needs_attention | unknown_item_type, itemType, ok_fields, mapped,
                  to_extra, dropped_or_rewritten, empty_fields, missing_minimum, suggestions?}
  found           zotero.Zotero.lookup (find_in_library; create_item's look before it posts): {from, code: found,
                  key, version, citationKey, title, date, collections, tags, attachments: [{key, title, kind,
                  contentType, linkMode, filename, md5}], matched_by: doi | arxiv | same_as, duplicates?: [KEYS]} or
                  {from, code: not_found, searched: [{q, qmode, hits}]}; a near match is never here
  near_matches    written with found, under its `from`: [{key, title, itemType, reason, matched_by?}]
  links           fulltext_links: {from, items: [{url, source, version: published | accepted | preprint | unknown,
                  needs_browser: true | false | null}], incomplete?: [sources]}
  saved           create_item: {pending: true, at} right before the POST, then {key, version, citationKey, created_at}
  attach          attach_file: {attachment, md5, kind, title, filename, url, at} for the file it attached; another
                  file (another md5) is attached afresh
The four blocks prepare fills carry `from`, a short hash of the inputs they were computed from (inputs() names
them), and `incomplete: [sources]` when a source did not answer. Such a block is due again when it is absent (or has
no `from`: an older run's, not trusted), incomplete, or stale; due() says which. `saved` and `attach` record writes
to the library and are trusted as they are. The facts about files are not in the record: the file's name is its
kind, and fetch.jsonl has how it came (events claim, accept, try, stop).
"""
import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import paper, verify
from .cli import ACT, CANNOT, Stop

PREPARED = ("published_candidates", "checks", "found", "links")
FILE_SUFFIXES = tuple(paper.KINDS[k]["suffix"] for k in ("published", "accepted", "preprint", "supplement", "snapshot"))


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- the work directory -------------------------------------------------------------------------------------

class Work:
    def __init__(self, root):
        self.root = Path(root).expanduser().absolute()
        for name in ("records", "inbox", "stray", "unverified", "scratch"):
            setattr(self, name, self.root / name)
        self.started, self.log, self.settings_path = self.root / ".started", self.root / "fetch.jsonl", self.root / "run.json"

    @classmethod
    def of(cls, record_path):
        """The work directory a record file lives in (<work>/records/<slug>.json)."""
        return cls(Path(record_path).absolute().parent.parent)

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
        """The record's own file, of whichever kind, or None."""
        return next((f for f in (self.records / (slug + s) for s in FILE_SUFFIXES) if f.is_file()), None)

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


def atomic_write(path, text):
    """Replace a file's content at once (a temp file beside it, then os.replace), keeping the mode it had, or the
    mode an ordinary new file gets."""
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


# ---- records ------------------------------------------------------------------------------------------------

class Record(dict):
    """A record file's object, with its path; slug = the file name."""

    def __init__(self, path, data):
        super().__init__(data)
        self.path = Path(path)
        self.slug = self.path.stem
        self.saved_text = json.dumps(data, sort_keys=True)

    @property
    def item(self):
        return self.get("item") if isinstance(self.get("item"), dict) else {}

    def changed(self):
        return json.dumps(self, sort_keys=True) != self.saved_text

    def save(self):
        atomic_write(self.path, json.dumps(self, ensure_ascii=False, indent=2) + "\n")
        self.saved_text = json.dumps(self, sort_keys=True)

    def keys_of(self, field):
        """An agent field holding item keys (distinct_from, collection), as a list whether given as one or several."""
        value = self.get(field)
        return [value] if isinstance(value, str) and value else [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def read(path):
    """The record at path -> Record; a file that is not one JSON object -> Stop record_invalid."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Stop("record_invalid", exit=ACT, hint="No such record file.", path=str(path)) from None
    except (OSError, ValueError) as e:
        raise Stop("record_invalid", exit=ACT, hint="A record file holds one JSON object; fix or redraft it.",
                   path=str(path), detail=str(e)) from None
    if not isinstance(data, dict):
        raise Stop("record_invalid", exit=ACT, hint="A record file holds one JSON object; fix or redraft it.", path=str(path))
    return Record(path, data)


# ---- when a block is done -----------------------------------------------------------------------------------

def inputs(rec, block):
    """What a prepared block is computed from."""
    item = rec.item
    doi, aid = paper.identifiers(item)
    if block == "published_candidates":
        return [aid, paper.norm_title(item.get("title"))]
    if block == "checks":
        return item
    if block == "found":
        return [doi, aid, paper.norm_title(item.get("title")), rec.get("same_as") or None, sorted(rec.keys_of("distinct_from"))]
    if block == "links":
        return [doi, aid, (item.get("url") or "").strip()]
    raise KeyError(block)


def fingerprint(value):
    return hashlib.sha1(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def due(rec, block):
    """Why the block must be computed (again): "absent" | "incomplete" | "stale"; None when it is done."""
    b = rec.get(block)
    if not isinstance(b, dict) or "from" not in b:
        return "absent"
    if b.get("incomplete"):
        return "incomplete"
    return "stale" if b["from"] != fingerprint(inputs(rec, block)) else None


def stamp(rec, block, value, incomplete=()):
    """Write a prepared block with what it was computed from (and the sources that did not answer)."""
    rec[block] = {**value, "from": fingerprint(inputs(rec, block)), **({"incomplete": sorted(incomplete)} if incomplete else {})}
    return rec[block]


def old_format(rec):
    """The prepared blocks an older run left without `from`: not trusted, computed again by prepare."""
    return [b for b in PREPARED if b in rec and not (isinstance(rec[b], dict) and "from" in rec[b])]


def item_key(rec):
    """The library item this record is: the one this run created (saved.key; a pending creation has none), else the
    one the lookup confirmed (found.key, while found is done) — never a near match, which names another item."""
    saved = rec.get("saved")
    if isinstance(saved, dict) and saved.get("key"):
        return saved["key"]
    found = rec.get("found")
    if isinstance(found, dict) and found.get("code") == "found" and found.get("key") and due(rec, "found") is None:
        return found["key"]
    return None


# ---- files reaching a record --------------------------------------------------------------------------------

def place(work, slug, src, kind):
    """File src as the record's file of that kind -> ("claimed" | "stray", its new path); src is consumed either way.
    First come, first served: the copy is linked to its final name, so a record that already has its file (the paper
    came another way meanwhile) sends this one to stray/."""
    target = work.records / (slug + paper.KINDS[kind]["suffix"])
    if work.file_of(slug) is not None:
        return "stray", move(src, work.stray, target.name)
    tmp = work.records / f".{slug}.{uuid.uuid4().hex[:8]}.tmp"
    shutil.copy2(src, tmp)
    try:
        os.link(tmp, target)
    except FileExistsError:
        return "stray", move(src, work.stray, target.name)
    finally:
        tmp.unlink(missing_ok=True)
    Path(src).unlink(missing_ok=True)
    return "claimed", target


def move(src, directory, name):
    """Move src into directory under name, numbered when the name is taken -> the new path."""
    directory.mkdir(exist_ok=True)
    dest, n = directory / name, 2
    while dest.exists():
        stem, dot, ext = name.partition(".")
        dest, n = directory / f"{stem}-{n}{dot}{ext}", n + 1
    shutil.move(str(src), str(dest))
    return dest


def claim(work, src, slug, *, kind=None, source=None, via=None, cache=None):
    """Check a file against one record and file it: passing -> beside the record under its kind's name (stray/ when
    the record has its file already), failing -> unverified/<slug>.<via>.<ext> for the agent to look at. -> the claim
    event, logged. `kind` as verify.kind_of takes it (a link's version, or None: the file's name and page 1 say)."""
    src = Path(src)
    rec = read(work.records / f"{slug}.json")
    verdict = verify.check(src, rec, kind, cache)
    if verdict["code"] in verify.PASS_CODES:
        result, path = place(work, slug, src, verdict["kind"])
    else:
        ext = ".html" if verdict["kind"] == "snapshot" else ".pdf"
        result, path = "unverified", move(src, work.unverified, f"{slug}.{via or 'file'}{ext}")
    return work.append({"event": "claim", "file": path.name, "slug": slug, "result": result, "kind": verdict["kind"],
                        "code": verdict["code"], "md5": verdict["md5"], "source": source})


def accept(work, src, slug, reason, kind=None):
    """File a file the check refused, on the agent's reading of it -> the accept event (claim's shape plus the
    reason), logged; attach_file attaches a file with this md5 unchecked."""
    src = Path(src)
    if not src.is_file():
        raise Stop("file_not_found", hint="No such file; give the path of the file to accept.", file=str(src))
    read(work.records / f"{slug}.json")
    ex = verify.extract(src)
    kind = verify.kind_of(src, ex, kind)
    md5 = ex.md5 if ex else hashlib.md5(src.read_bytes()).hexdigest()
    result, path = place(work, slug, src, kind)
    return work.append({"event": "accept", "file": path.name, "slug": slug, "result": result, "kind": kind, "md5": md5,
                        "reason": reason, "source": str(src)})


def accepted(work, slug, md5):
    """The accept event for this record's file with this md5, or None."""
    return next((e for e in reversed(work.events("accept")) if e.get("slug") == slug and e.get("md5") == md5), None)


# ---- the browser's Downloads ---------------------------------------------------------------------------------

PARTIAL = (".crdownload", ".part", ".tmp", ".download")


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def new_downloads(work, dl):
    """Complete files newer than .started, oldest first."""
    if not work.started.exists():
        raise Stop("no_started", exit=CANNOT, hint="The work directory has no .started: run ready.py --work first.")
    started, out = work.started.stat().st_mtime, []
    for f in dl.iterdir():
        try:
            if f.is_file() and not f.name.startswith(".") and f.suffix.lower() not in PARTIAL and f.stat().st_mtime >= started:
                out.append((f.stat().st_mtime, f))
        except OSError:
            continue
    return [f for _, f in sorted(out)]


def records_of(work):
    """The work directory's records; a file that is not one is left out."""
    out = []
    for path in sorted(work.records.glob("*.json")):
        try:
            out.append(read(path))
        except Stop:
            continue
    return out


def has_pdf(rec):
    """The library item the record found holds a PDF already."""
    found = rec.get("found") if item_key(rec) and isinstance(rec.get("found"), dict) else {}
    return any(a.get("kind") in ("published", "accepted", "preprint") or a.get("contentType") == "application/pdf"
               for a in found.get("attachments") or [] if isinstance(a, dict))


class Scanner:
    """Claims the new files in Downloads (dl), remembering what it saw: a file is looked at again only when its size or
    time changed, and counts as complete once two looks found it the same; a file that is no PDF is never opened
    again; the records are read again only when records/ changed. Each PDF is checked against every record whose
    library item has no PDF yet: one match -> filed, else left there (it may be the user's own) and checked again only
    against records drafted since."""

    def __init__(self, work, dl):
        self.work, self.dl = work, Path(dl)
        self.seen, self.md5 = {}, {}  # name -> (size, mtime) at the last look; name -> ((size, mtime), md5)
        self.records, self.records_at = [], None

    def scan(self):
        """One look -> the events, logged."""
        changed = self.work.records.stat().st_mtime_ns
        if changed != self.records_at:
            self.records, self.records_at = records_of(self.work), changed
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
            records = [r for r in self.records if not has_pdf(r) and r.slug not in left.get((f.name, md5), ())]
            if not records:
                continue
            cache = {}
            matched = [r.slug for r in records if verify.check(f, r, cache=cache)["code"] in verify.PASS_CODES]
            if len(matched) == 1:
                events.append(claim(self.work, f, matched[0], cache=cache, source=str(f)))
            else:
                events.append(self.work.append({"event": "claim", "file": f.name, "result": "left", "md5": md5,
                                                "source": str(f), "why": "ambiguous" if matched else "unmatched",
                                                "matched": matched or None, "against": sorted(r.slug for r in records)}))
                left.setdefault((f.name, md5), set()).update(r.slug for r in records)
        return events


def watcher_alive(work):
    """Whether the watcher (claim.py --watch) of this work directory is running: its pid in run.json, alive."""
    pid = work.settings().get("watcher")
    try:
        os.kill(int(pid), 0)
    except (TypeError, ValueError, ProcessLookupError, PermissionError):
        return False
    return True
