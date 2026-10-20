"""One import run's work directory: its layout and settings, the records and when a block of theirs is done, the log.

Layout (ready.py makes it):
  records/<slug>.json     one record per paper; its file beside it, named by kind: <slug>.pdf, <slug>.accepted.pdf,
                          <slug>.preprint.pdf, <slug>.supplement.pdf, <slug>.html (paper.KINDS)
  inbox/ stray/ unverified/ scratch/    bytes a script fetched / second copies / files the check refused / one-off files
  .started                the run's start: Downloads files newer than it are this run's
  run.json                the run's settings: downloads, session, the watcher's pid
  fetch.jsonl             what happened to the files: one JSON line per event, appended
  pace.json               request gaps per host (web.Pacer)

A record holds the agent's fields (item, tags, collection, citationKey, alt_titles, distinct_from, same_as,
keep_preprint, blocker), which scripts read and never change, and blocks each written by one script. The blocks
prepare fills (published_candidates, checks, found + near_matches, links) carry `from`, a short hash of the inputs
they were computed from, and `incomplete: [sources]` when a source did not answer. Such a block is due again when
it is absent (or has no `from`: an older run's), incomplete, or stale (its inputs changed); due() says which.
`saved` (the item this run created) and `attach` (keyed by the file's md5) record writes to the library and are
trusted as they are.
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import paper
from .cli import ACT, Stop

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
