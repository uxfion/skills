"""One import's records: where they are, what they hold, when a block of theirs is done.

An import works in <scratch>/paper-to-zotero/: paper-fetch's directory fetch/ (its results, their files, its log),
records/, one record per paper, records/<slug>.json under its result's slug, and handoffs/, what a script leaves to
an agent. p2z reads a result as plain JSON
and never writes it; paper-fetch never reads a record.

A record is one JSON object. The agent's fields — scripts read them and never change them; draft_item writes their
first values:
  fetched         the result file's absolute path (paper-fetch's <dir>/results/<slug>.json): the paper's ids, CSL,
                  versions, and the files got for it with their labels and checks
  item            the Zotero item to create (draft_item drafts it from the result; the agent revises it)
  warnings        [str]: what draft_item noticed (a type guessed, the DOI put in extra, fields dropped)
  tags            [{tag, type}]               collection     KEY or [KEYS]          citationKey   str
  distinct_from   [KEYS]: library items judged to be other papers (p2z.py answer distinct writes them)
  same_as         KEY: the library item judged to be this paper (p2z.py answer same; or the agent's choice among
                  found.duplicates)
  keep_preprint   str: why the item stays the preprint although the result's versions.published has entries
  accepted        [str]: what the agent accepts as it is: a check's flag (check_flags: "mapped:publicationTitle")
                  or a warning's text; decisions no longer list them
  blocker         str: what the record waits for (the last pass with the user, ...)
Blocks, each written by one script and nothing else:
  checks          check_item: {from, code: ok | needs_attention | unknown_item_type, itemType, ok_fields, mapped,
                  to_extra, dropped_or_rewritten, empty_fields, missing_minimum, suggestions?}
  found           zotero.Zotero.lookup (find_in_library; create_item's look before it posts): {from, code: found,
                  key, version, citationKey, title, date, collections, tags, attachments: [{key, title, version,
                  source, detail, standard, contentType, linkMode, filename, md5, url}], matched_by: doi | arxiv |
                  same_as, duplicates?: [KEYS]} or
                  {from, code: not_found, searched: [{q, qmode, hits}], more?}; a candidate is never here
  near_matches    written with found, under its `from`: the candidates (paper.candidates: {key, title, year,
                  first_author, doi, arxiv, itemType, venue, similarity, matched_by?, attachments: [titles]})
  saved           create_item: {pending: true, at} right before the POST, then {key, version, citationKey, created_at}
  attach          attach_file: [{attachment, md5, title, filename, kind, url, at, existing?}], an entry per file of the
                  result it attached (existing: the item had this file already, under its own title)
The blocks prepare fills (PREPARED) carry `from`, a short hash of the inputs they were computed from (inputs() names
them), and `incomplete: [sources]` when a source did not answer. Such a block is due again when it is absent (or has
no `from`: an older run's, not trusted), incomplete, or stale; due() says which. `saved` and `attach` record writes
to the library and are trusted as they are.

Handoffs, handoffs/<slug>.<n>.json, written once by the script that stops (find_in_library, create_item), the shape
paper-fetch's take: {id, kind: same_paper, taker: judge, slug, record, paper: the item's evidence, candidates: the
near matches still open, more?, answers, answered: [{key, answer, reason, by, at}], at}. The record is the state:
`p2z.py answer` writes same_as or distinct_from there, and keeps a pair or an unknown, which wait for the user, in the
handoff's `answered`. A handoff is open while one of its candidates is still open in the record (unsettled()).
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import paper
from .cli import ACT, Stop

PREPARED = ("checks", "found")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Work:
    """An import's directory: records/, and scratch/ for what a run keeps for itself (Zotero's schema)."""

    def __init__(self, root):
        self.root = Path(root).expanduser().absolute()
        self.records, self.scratch, self.handoffs = self.root / "records", self.root / "scratch", self.root / "handoffs"
        self.schema_file = self.scratch / "schema.json"  # Zotero's schema, read once a run

    @classmethod
    def of(cls, record_path):
        """The directory a record file lives in (<root>/records/<slug>.json)."""
        return cls(Path(record_path).absolute().parent.parent)


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

    @property
    def work(self):
        return Work.of(self.path)

    def changed(self):
        return json.dumps(self, sort_keys=True) != self.saved_text

    def save(self):
        atomic_write(self.path, json.dumps(self, ensure_ascii=False, indent=2) + "\n")
        self.saved_text = json.dumps(self, sort_keys=True)

    def keys_of(self, field):
        """An agent field holding item keys (distinct_from, collection), as a list whether given as one or several."""
        value = self.get(field)
        return [value] if isinstance(value, str) and value else [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def result_of(rec):
    """The record's result, read as plain JSON -> (result, its path); Stop no_result when it cannot be read."""
    path = Path(str(rec.get("fetched") or ""))
    try:
        res = json.loads(path.read_text(encoding="utf-8")) if rec.get("fetched") else None
    except (OSError, ValueError) as e:
        raise Stop("no_result", path=str(path), detail=str(e), hint="The record's result file cannot be read: draft the "
                                                                   "record again from its result (draft_item.py).") from None
    if not isinstance(res, dict):
        raise Stop("no_result", hint="The record names no result file (`fetched`): draft it from its result with "
                                     "draft_item.py.")
    return res, path


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
    if block == "checks":
        return item
    if block == "found":
        return [doi, aid, paper.norm_title(item.get("title")), rec.get("same_as") or None, sorted(rec.keys_of("distinct_from"))]
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


HINT_NO_ITEM = "The record has no item: draft it from its result with draft_item.py."
HINT_NEAR = ("The library may hold this paper (near_matches): a judge reads the handoff and answers with p2z.py answer "
             "(references/import.md, step 3); then run p2z.py prepare (or save) again.")


def look_up(rec, zot):
    """The record's found and near_matches from the library lookup (zotero.Zotero.lookup), written -> both."""
    found, near = zot.lookup(rec.item, distinct_from=rec.keys_of("distinct_from"), same_as=rec.get("same_as"))
    stamp(rec, "found", found)
    rec["near_matches"] = near
    return found, near


def near_lines(near):
    return [{k: m.get(k) for k in ("key", "title", "similarity")} for m in near]


def item_key(rec):
    """The library item this record is: the one this run created (saved.key; a pending creation has none), else the
    one the lookup confirmed (found.key, while found is done) — never a near match, which names another item, nor
    the first of several items with the paper's identifier (found.duplicates: the agent's to choose, as same_as)."""
    saved = rec.get("saved")
    if isinstance(saved, dict) and saved.get("key"):
        return saved["key"]
    found = rec.get("found")
    if (isinstance(found, dict) and found.get("code") == "found" and found.get("key") and not found.get("duplicates")
            and due(rec, "found") is None):
        return found["key"]
    return None


def check_flags(checks):
    """What a checks block flags, each as one string the agent can accept (`accepted`): "mapped:<field>",
    "to_extra:<field>", "dropped_or_rewritten:<field>", "missing_minimum:<what>", or the code itself."""
    if not isinstance(checks, dict) or checks.get("code") in (None, "ok"):
        return []
    if checks["code"] != "needs_attention":
        return [checks["code"]]
    out = [f"mapped:{m.get('from')}" for m in checks.get("mapped") or []]
    out += [f"{name}:{m.get('field')}" for name in ("to_extra", "dropped_or_rewritten") for m in checks.get(name) or []]
    return out + [f"missing_minimum:{m}" for m in checks.get("missing_minimum") or []]


# ---- handoffs ------------------------------------------------------------------------------------------------

ANSWERS = {"same_paper": ("same", "distinct", "pair", "unknown")}


def unsettled(rec):
    """The near matches the record leaves open -> [keys]: none once same_as names an item or found confirms one."""
    found = rec.get("found") if isinstance(rec.get("found"), dict) else {}
    if rec.get("same_as") or found.get("code") == "found":
        return []
    excluded = set(rec.keys_of("distinct_from"))
    return [m["key"] for m in rec.get("near_matches") or [] if isinstance(m, dict) and m.get("key") not in excluded]


def handoffs_of(rec):
    """The record's handoffs, oldest first, each with its `path`."""
    out = []
    for path in rec.work.handoffs.glob(f"{glob_escape(rec.slug)}.*.json"):
        try:
            h = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(h, dict) and h.get("slug") == rec.slug:
            out.append({**h, "path": str(path)})
    return sorted(out, key=lambda h: int(str(h.get("id", "")).rsplit(".", 1)[-1] or 0))


def open_handoff(rec):
    """The record's open same_paper handoff (the latest whose candidates are still open), or None."""
    keys = set(unsettled(rec))
    return next((h for h in reversed(handoffs_of(rec)) if keys & {c.get("key") for c in h.get("candidates") or []}), None)


def ask_same_paper(rec):
    """The handoff that hands the record's open near matches to a judge -> its path; a new one is written when no
    handoff of the record holds them all. None when nothing is open."""
    keys = unsettled(rec)
    if not keys:
        return None
    for h in reversed(handoffs_of(rec)):
        if set(keys) <= {c.get("key") for c in h.get("candidates") or []}:
            return h["path"]
    rec.work.handoffs.mkdir(exist_ok=True)
    n = 1
    while True:
        path = rec.work.handoffs / f"{rec.slug}.{n}.json"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            break
        except FileExistsError:
            n += 1
    os.close(fd)
    found = rec.get("found") if isinstance(rec.get("found"), dict) else {}
    handoff = {"id": f"{rec.slug}.{n}", "kind": "same_paper", "taker": "judge", "slug": rec.slug, "record": str(rec.path),
               "paper": paper.evidence(rec.item), "candidates": [m for m in rec["near_matches"] if m.get("key") in keys],
               **({"more": found["more"]} if found.get("more") else {}), "answers": list(ANSWERS["same_paper"]),
               "answered": [], "at": now_iso()}
    atomic_write(path, json.dumps(handoff, ensure_ascii=False, indent=2) + "\n")
    return str(path)


def glob_escape(text):
    return "".join(f"[{ch}]" if ch in "*?[" else ch for ch in text)


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
