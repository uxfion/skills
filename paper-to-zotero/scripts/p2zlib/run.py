"""One import's records: where they are, what they hold, when a block of theirs is done.

An import works in <scratch>/paper-to-zotero/: paper-fetch's directory fetch/ (its results, their files, its log),
records/, one record per paper, records/<slug>.json under its result's slug, handoffs/, what a script leaves to an
agent, and tags/, the curated tags of each paper whose item the import creates. p2z reads a result as plain JSON
and never writes it; paper-fetch never reads a record.

A record is one JSON object, the main agent's. Its fields — scripts read them and never change them; p2z.py draft
writes their first values:
  fetched         the result file's absolute path (paper-fetch's <dir>/results/<slug>.json): the paper's ids, CSL,
                  versions, and the files got for it with their labels and checks
  item            the Zotero item to create (p2z.py draft drafts it from the result; the agent revises it)
  warnings        [str]: what p2z.py draft noticed (a type guessed, the DOI put in extra, fields dropped)
  tags            [{tag, type}]: p2z.py draft's automatic tags (the curated ones are the tags file's, below)
  collection      a collection or a list: its key, path or name   citationKey    str
  keep_preprint   str: why the item stays the preprint, with or without a published version (report lists it)
  accepted        [str]: what the agent accepts as it is: a check's flag (check_flags: "mapped:publicationTitle")
                  or a warning's text; decisions no longer list them
  blocker         str: what the record waits for (the last pass with the user, ...)
Blocks, each written by one script and nothing else:
  checks          p2z.py check: {from, code: ok | needs_attention | unknown_item_type, itemType, ok_fields, mapped,
                  to_extra, dropped_or_rewritten, empty_fields, missing_minimum, suggestions?}
  found           zotero.Zotero.lookup (p2z.py have; p2z.py create's look before it posts): {from, code: found,
                  key, version, citationKey, title, date, collections, tags, attachments: [{key, title, version,
                  source, detail, standard, contentType, linkMode, filename, md5, url}], matched_by: doi | arxiv |
                  same_paper (a same_paper handoff's answer)} or
                  {from, code: not_found, searched: [{q, qmode, hits}], more?}; a candidate is never here
  near_matches    written with found, under its `from`: the candidates (paper.candidates: {key, title, year,
                  first_author, doi, arxiv, itemType, venue, similarity, matched_by?, attachments: [titles]}); several
                  items carrying the paper's DOI or arXiv id are candidates too, each with its matched_by
  saved           p2z.py create: {pending: true, at} right before the POST, then {key, version, citationKey, created_at};
                  or p2z.py recognize, for a stub's PDF Zotero's recognizer made an item from: the same, with via: recognizer
  recognize       p2z.py recognize: {md5, title, url, sessionID, at, code: sent | recognized | not_recognized, attachment?}:
                  the stub's PDF sent through the connector, and what came of it (sent: a rerun asks again, never sends twice)
  attach          p2z.py attach: [{attachment, md5, title, filename, kind, url, at, existing?}], an entry per file of the
                  result it attached (existing: the item had this file already, under its own title)
The blocks prepare fills (PREPARED) carry `from`, a short hash of the inputs they were computed from (inputs() names
them), and `incomplete: [sources]` when a source did not answer. Such a block is due again when it is absent (or has
no `from`: an older run's, not trusted), incomplete, or stale; due() says which. `saved` and `attach` record writes
to the library and are trusted as they are.

Handoffs, handoffs/<slug>.<n>.json, written by the command that stops (p2z.py have, p2z.py create), the shape
paper-fetch's take: {id, kind: same_paper, slug, record, paper: the item's evidence, candidates: the near matches
still open, more?, answers, answered: [{key, answer, reason, by, at}], at}; `answered` is `p2z.py answer`'s alone,
one entry appended per answer. Who takes a handoff is SKILL.md's to say. Which library item is this paper lives only
in the handoffs' `answered` (decided()), never in the record: per candidate the latest answer stands (the user's
word after a judge's pair), across all of the record's handoffs; `same` names the item, `distinct` drops a candidate,
`pair` and `unknown` leave it open for the user. A handoff is open while one of its candidates is still open
(unsettled()). A record an earlier version of this skill wrote may carry such decisions as fields of its own: they
are read no more, the handoffs' `answered` holds every answer `p2z.py answer` recorded, and a choice made outside it
is asked again through a handoff.

A tags file, tags/<slug>.json, is the paper's curated tags, written only by whoever tags it (references/tagging.md):
a JSON list in p2z.py tag's tag-list form, "name" or {"tag": "name", "type": 0} (other keys are notes). p2z.py create
writes them with the record's `tags`, and creates nothing for a paper whose tags file is not there yet (untagged).
A paper the library holds already gets none: its item is not tagged at import.
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
    """An import's directory: records/, handoffs/, tags/, and scratch/ for what a run keeps for itself (Zotero's
    schema, the library's tags for the taggers, a judge's own notes)."""

    def __init__(self, root):
        self.root = Path(root).expanduser().absolute()
        self.records, self.scratch, self.handoffs = self.root / "records", self.root / "scratch", self.root / "handoffs"
        self.tags = self.root / "tags"
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
        """An agent field holding one value or several (collection), as a list."""
        value = self.get(field)
        return [value] if isinstance(value, str) and value else [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def result_of(rec):
    """The record's result, read as plain JSON -> (result, its path); Stop no_result when it cannot be read. A result
    renamed since (paper-fetch's renamed_from) is followed to its new name."""
    path = Path(str(rec.get("fetched") or ""))
    if rec.get("fetched") and not path.exists() and path.parent.is_dir():
        path = next((p for p in sorted(path.parent.glob("*.json")) if path.stem in (renamed_from(p) or ())), path)
    try:
        res = json.loads(path.read_text(encoding="utf-8")) if rec.get("fetched") else None
    except (OSError, ValueError) as e:
        raise Stop("no_result", path=str(path), detail=str(e), hint="The record's result file cannot be read: draft the "
                                                                   "record again from its result (p2z.py draft).") from None
    if not isinstance(res, dict):
        raise Stop("no_result", hint="The record names no result file (`fetched`): draft it from its result with "
                                     "p2z.py draft.")
    return res, path


def renamed_from(result_path):
    try:
        value = json.loads(Path(result_path).read_text(encoding="utf-8")).get("renamed_from")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, list) else None


def read(path):
    """The record at path -> Record; no such file -> Stop file_not_found; a file that is not one JSON object -> Stop
    record_invalid."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Stop("file_not_found", exit=ACT, hint="No such file.", path=str(path)) from None
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
        same, distinct = decided(rec)
        return [doi, aid, paper.norm_title(item.get("title")), same, sorted(distinct)]
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


HINT_NO_ITEM = ("The record has no item: draft it from its result with p2z.py draft; a stub's record gets its item from "
                "its PDF (p2z.py recognize, references/no-doi-record.md).")
HINT_NEAR = ("The library may hold this paper (near_matches): a judge reads the handoff and answers with p2z.py answer "
             "(references/import.md, step 3); then run p2z.py prepare (or save) again.")


def look_up(rec, zot):
    """The record's found and near_matches from the library lookup (zotero.Zotero.lookup), with what the handoffs
    decided, written -> both."""
    same, distinct = decided(rec)
    found, near = zot.lookup(rec.item, distinct=distinct, same=same)
    stamp(rec, "found", found)
    rec["near_matches"] = near
    return found, near


def near_lines(near):
    return [{k: m.get(k) for k in ("key", "title", "similarity")} for m in near]


def item_key(rec):
    """The library item this record is: the one this run created (saved.key; a pending creation has none), else the
    one the lookup confirmed (found.key, while found is done) — never a near match, which names another item, nor
    one of several items with the paper's identifier, which are candidates until a handoff's answer names one."""
    saved = rec.get("saved")
    if isinstance(saved, dict) and saved.get("key"):
        return saved["key"]
    found = rec.get("found")
    if isinstance(found, dict) and found.get("code") == "found" and found.get("key") and due(rec, "found") is None:
        return found["key"]
    return None


def tags_file(rec):
    """The paper's tags file, tags/<slug>.json: its curated tags, the tagger's to write."""
    return rec.work.tags / f"{rec.slug}.json"


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


def latest_answers(rec):
    """{candidate key: the latest answer on it}, oldest first, across the record's handoffs: every `answered` entry
    in the order given (`at`; on a tie, the handoffs' order, then the order appended), a later one standing."""
    entries = [a for h in handoffs_of(rec) for a in h.get("answered") or [] if isinstance(a, dict) and a.get("key")]
    latest = {}
    for a in sorted(entries, key=lambda a: str(a.get("at") or "")):
        latest.pop(a["key"], None)
        latest[a["key"]] = a
    return latest


def decided(rec):
    """What the handoffs' answers decided -> (the key of the item that is this paper or None, [keys of other
    papers]), from the latest answer on each candidate."""
    latest = latest_answers(rec)
    same = [k for k, a in latest.items() if a.get("answer") == "same"]
    return (same[-1] if same else None), sorted(k for k, a in latest.items() if a.get("answer") == "distinct")


def unsettled(rec):
    """The near matches the record leaves open -> [keys]: none once a handoff's answer names the item or found
    confirms one; a candidate answered distinct is closed, one answered pair or unknown stays open (the user's)."""
    found = rec.get("found") if isinstance(rec.get("found"), dict) else {}
    same, distinct = decided(rec)
    if same or found.get("code") == "found":
        return []
    return [m["key"] for m in rec.get("near_matches") or [] if isinstance(m, dict) and m.get("key") not in distinct]


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
    handoff = {"id": f"{rec.slug}.{n}", "kind": "same_paper", "slug": rec.slug, "record": str(rec.path),
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
