#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Create Zotero items through the local write API, filed and tagged in one POST, from records or one item.json.

Single mode (--item; v1, unchanged): pre-checks — item.json is a parent item
with itemType and title; the tags file is valid; Zotero is reachable with the
local API on; a key is stored and belongs to this instance; the collection
exists — then one POST to /api/users/0/items with `collections` and `tags`
set, and the response object is compared with what was sent. --dry-run stops
after the pre-checks. Output: exactly one JSON object on stdout with a stable
`code`.

Stream mode (record paths, or records on stdin as JSONL / a JSON array / one
object): the same for each record's `item`. The destination is the record's
`collection` (one key or a list), else --collection (repeatable; neither ->
no_collection); tags are the record's `tags` (absent -> the item's own, else
none, with a warning on stderr); a record `citationKey` is written into the
item, which Zotero pins. Records already carrying `saved.key` or a resolved
`found.key` are skipped; a `found` that is still a near_match is reported as
possible_duplicate until the agent resolves it.

Before anything is posted, the pending records go through find_in_library.py
(one subprocess, records on stdin), so a duplicate never depends on the agent
remembering to look: a DOI / arXiv hit writes `found` and the record is
skipped as `exists` (its file is attached to that item later); a near match
(title only, preprint/published pair, same title with another DOI) fails as
possible_duplicate with its candidates and nothing is written. The agent then
either sets `found` to {"key": KEY} (same paper) or adds KEY to the record's
`distinct_from` (another paper) and re-runs. Up to 50 objects go in one POST;
an object the server rejects fails only its own record. On success the record gains `saved = {key, version, created_at}` and
the read-back is compared with what was sent (collections, tags, citationKey;
a difference is `readback_mismatch` — the item exists, so `saved` is still
recorded). Without -i the updated records go to stdout one per line, and
one summary line per record plus the final {"summary": ...} go to stderr;
with -i each changed record is written back to its file and stdout carries
those summary lines instead. Exit 0 = every record ok or skipped, 1 = some
failed, 2 = the run could not (or could no longer) check Zotero.

Nothing is retried: an object the server reports as failed was not created;
fix the record and re-run (records with `saved` are skipped). Diagnostics go
to stderr. The API key is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
ITEMS_PATH = "/api/users/0/items"
COLLECTION_KEY_RE = re.compile(r"^[A-Z0-9]{8}$")
TEX_SPECIAL = re.compile(r"[\\^_&%$#{}~]")
NOT_PARENT_TYPES = {"attachment", "note", "annotation"}
POST_TIMEOUT = 60
CHUNK = 50
FIND_SCRIPT = Path(__file__).resolve().parent / "find_in_library.py"

EXIT_OK, EXIT_FAIL, EXIT_CANNOT = 0, 1, 2

EPILOG = """\
exit codes:
  0  ok                  item(s) created; single mode: `filed` and `tags_ok` say whether the read-back matches;
                         stream mode: every record ok or skipped
  1  not passed          single: item_invalid | tags_invalid | collection_invalid | collection_not_found |
                         create_failed (server's code + message verbatim, nothing created) |
                         readback_mismatch (item exists: fix it with file_and_tag.py)
                         stream: some record failed (its code is in its summary line: no_collection, item_invalid,
                         tags_invalid, collection_not_found, possible_duplicate, create_failed, readback_mismatch,
                         ...); skipped records say why (saved, found, exists = a DOI / arXiv hit in the library);
                         no_records | record_invalid | input_invalid (nothing done)
  2  cannot check        zotero_unreachable | local_api_disabled | no_key | config_unreadable |
                         key_rejected | server_mismatch | server_id_required |
                         library_not_editable | post_incomplete | lookup_failed (find_in_library could not check)

files:
  item.json   a Zotero item object (itemType, title, creators, ...) without key/version/
              collections; `tags` inside it are used only when --tags-file is absent
  tags.json   a JSON list; each entry is "name" (manual tag) or {"tag": "name", "type": 0|1}
              (0 manual, 1 automatic); it is the item's complete tag list
  saved.json  written on success: item_key, version, collection, tags, title, itemType
  record      {"slug", "item": {...}, "tags": [...], "collection": "KEY" | ["KEY", ...], "citationKey": "...",
              "distinct_from": ["KEY", ...], ...};
              gains "saved": {"key", "version", "created_at"}

examples:
  uv run create_item.py --item item.json --collection ABCD1234 --tags-file tags.json --out saved.json
  uv run create_item.py -i records/*.json                      # write `saved` back into each record
  cat records.jsonl | uv run create_item.py --collection ABCD1234 > created.jsonl
"""


class Stop(Exception):
    """Carry a result code out of any depth; main() turns it into JSON + exit."""

    def __init__(self, code, exit_code=EXIT_FAIL, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit_code, self.hint, self.extra = code, exit_code, hint, extra


class Unreachable(Exception):
    """No answer from the local API (connection refused, timed out, ...)."""


def log(message: str) -> None:
    print(message, file=sys.stderr)


def emit(code: str, exit_code: int = EXIT_OK, hint=None, **fields) -> None:
    out = {"code": code, **fields}
    if hint:
        out["hint"] = hint
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


def text(body: bytes, limit: int = 300) -> str:
    return body.decode("utf-8", errors="replace").strip()[:limit]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Api:
    """Minimal client for the local API; bypasses any proxy from the environment."""

    def __init__(self, base_url):
        self.base = base_url.rstrip("/")
        # Ignore http_proxy & co.: the local API only listens on the loopback interface.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, body=None, headers=None, timeout=30):
        """Return (status, headers, bytes). Raises Unreachable when no answer came."""
        h = {"Accept": "application/json", **(headers or {})}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()
        except urllib.error.URLError as e:
            raise Unreachable("timed out" if isinstance(e.reason, TimeoutError) else str(e.reason)) from e
        except TimeoutError as e:
            raise Unreachable("timed out") from e
        except OSError as e:
            raise Unreachable(str(e)) from e


# ---- local input -----------------------------------------------------------

def load_json_file(path: Path, what: str, code: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Stop(code, EXIT_FAIL, f"fix {path.name} and re-run", path=str(path),
                   problems=[f"{what} could not be read as JSON: {e}"])


def normalize_tags(raw, problems: list[str]) -> list[dict]:
    """Turn strings / {tag, type} objects into [{tag, type}], collecting problems."""
    tags: list[dict] = []
    if not isinstance(raw, list):
        problems.append("tags must be a JSON list")
        return tags
    for i, entry in enumerate(raw):
        if isinstance(entry, str):
            name, kind = entry, 0
        elif isinstance(entry, dict):
            name, kind = entry.get("tag"), entry.get("type", 0)
        else:
            problems.append(f"tags[{i}]: expected a string or an object with 'tag'")
            continue
        if not isinstance(name, str) or not name.strip():
            problems.append(f"tags[{i}]: 'tag' must be a non-empty string")
            continue
        if isinstance(kind, bool) or kind not in (0, 1):
            problems.append(f"tags[{i}] ({name!r}): 'type' must be 0 (manual) or 1 (automatic)")
            continue
        name = name.strip()
        if any(t["tag"] == name for t in tags):
            problems.append(f"tags[{i}]: duplicate tag {name!r}")
            continue
        tags.append({"tag": name, "type": kind})
    return tags


def check_item(item) -> list[str]:
    problems = []
    if not isinstance(item, dict):
        return ["item.json must be a JSON object"]
    item_type = item.get("itemType")
    if not isinstance(item_type, str) or not item_type.strip():
        problems.append("'itemType' is missing")
    elif item_type in NOT_PARENT_TYPES:
        problems.append(f"itemType {item_type!r} is not a parent item (attachments go through attach_file.py)")
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        problems.append("'title' is missing or empty")
    for field in ("key", "version"):
        if field in item:
            problems.append(f"'{field}' must not be set on a new item")
    if "collections" in item:
        problems.append("'collections' must not be in item.json: the destination is --collection")
    return problems


# ---- records (stream mode) -------------------------------------------------

def slug_of(path, record):
    slug = record.get("slug")
    if isinstance(slug, str) and slug:
        return slug
    return path.stem if path is not None else None


def parse_stream(raw: str) -> list[dict]:
    """Records from stdin text: JSONL, a JSON array or one object (any sequence of JSON values, really)."""
    decoder, records, i, n = json.JSONDecoder(), [], 0, len(raw)
    while True:
        while i < n and raw[i].isspace():
            i += 1
        if i >= n:
            break
        try:
            value, i = decoder.raw_decode(raw, i)
        except ValueError as e:
            raise Stop("input_invalid", EXIT_FAIL, "stdin must carry records as JSONL, a JSON array or one JSON object",
                       error=str(e))
        for rec in (value if isinstance(value, list) else [value]):
            if not isinstance(rec, dict):
                raise Stop("input_invalid", EXIT_FAIL, "every record is a JSON object", got=type(rec).__name__)
            records.append(rec)
    return records


def load_records(paths) -> list[tuple[Path | None, dict]]:
    """[(path or None, record)] from the record files, else from stdin; none at all -> no_records."""
    if paths:
        entries = []
        for p in paths:
            path = Path(p)
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise Stop("record_invalid", EXIT_FAIL, "every record file holds one JSON object; nothing was done",
                           path=str(path), error=str(e))
            if not isinstance(rec, dict):
                raise Stop("record_invalid", EXIT_FAIL, "every record file holds one JSON object; nothing was done",
                           path=str(path))
            entries.append((path, rec))
    else:
        entries = [(None, rec) for rec in parse_stream(sys.stdin.read())]
    if not entries:
        raise Stop("no_records", EXIT_FAIL, "pass record files, or pipe records (JSONL, a JSON array or one object) to stdin")
    return entries


def save_record(path: Path, record: dict) -> None:
    """Write the record back atomically: a temp file in the same directory, then os.replace."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Outcome:
    """One record's result: status ok | skipped | failed, its summary line, and whether the record changed."""

    def __init__(self, path, record):
        self.path, self.record, self.changed = path, record, False
        self.status, self.line = "failed", {"slug": slug_of(path, record), "code": "not_run"}

    def set(self, status, code, /, changed=False, **fields):
        self.status, self.changed = status, changed
        self.line = {"slug": self.line["slug"], "code": code, **fields}

    def fail(self, stop: Stop, changed=False):
        self.set("failed", stop.code, changed, **stop.extra, **({"hint": stop.hint} if stop.hint else {}))


def write_results(outcomes: list[Outcome], in_place: bool, stopped: Stop | None = None) -> int:
    """Print the stream output; return the exit code (0 all ok/skipped, 1 any failed, the Stop's when stopped early)."""
    counts = {"total": len(outcomes), "ok": 0, "skipped": 0, "failed": 0}
    for o in outcomes:
        if in_place and o.changed and o.path is not None:
            try:
                save_record(o.path, o.record)
            except OSError as e:
                o.set("failed", "write_failed", path=str(o.path), error=str(e),
                      hint="the record file could not be rewritten; what was written to Zotero stands")
        counts[o.status] += 1
        line = json.dumps(o.line, ensure_ascii=False)
        if in_place:
            print(line)
        else:
            print(json.dumps(o.record, ensure_ascii=False))
            log(line)
    if stopped is not None:
        counts["stopped"] = stopped.code
        log(f"stopped early: {stopped.code}" + (f" - {stopped.hint}" if stopped.hint else ""))
    summary = json.dumps({"summary": counts}, ensure_ascii=False)
    print(summary) if in_place else log(summary)
    if stopped is not None:
        return stopped.exit_code
    return EXIT_FAIL if counts["failed"] else EXIT_OK


# ---- Zotero side -----------------------------------------------------------

def live_server_id(api: Api) -> str:
    """GET /api/ and return the running instance's Zotero-Server-ID."""
    try:
        status, headers, body = api.request("GET", "/api/")
    except Unreachable as e:
        raise Stop("zotero_unreachable", EXIT_CANNOT,
                   "Zotero is not listening there: wait at the gate (ask the user to start Zotero), then re-run",
                   base_url=api.base, detail=str(e))
    if status == 403:
        raise Stop("local_api_disabled", EXIT_CANNOT,
                   "the local API is off: wait at the gate (ask the user to enable it in Zotero Settings > Advanced, "
                   "'Allow other applications on this computer to communicate with Zotero'), then re-run",
                   detail=text(body))
    if status != 200:
        raise Stop("unexpected_response", EXIT_CANNOT, "GET /api/ should answer 200; check what is listening on this port",
                   status=status, detail=text(body))
    server_id = headers.get("Zotero-Server-ID")
    if not server_id:
        raise Stop("no_server_id", EXIT_CANNOT,
                   "this Zotero sends no Zotero-Server-ID, so it has no local write API; it needs Zotero 10 or newer")
    log(f"GET /api/ -> {status}, server {server_id}")
    return server_id


def config_path() -> Path:
    return Path(os.environ.get("PAPER_TO_ZOTERO_CONFIG") or Path.home() / ".config" / "paper-to-zotero" / "config.json")


def load_key(server_id: str) -> str:
    """The local API key from the config file's "zotero" block (ready.py --authorize writes it). Never printed."""
    path = config_path()
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        config = {}
    except (OSError, ValueError) as e:
        raise Stop("config_unreadable", EXIT_CANNOT, "the config file is unreadable: fix it, then re-run",
                   config=str(path), detail=str(e))
    zot = config.get("zotero") if isinstance(config, dict) else None
    zot = zot if isinstance(zot, dict) else {}
    if not isinstance(zot.get("key"), str) or not zot["key"]:
        raise Stop("no_key", EXIT_CANNOT,
                   "no key for the local write API: run ready.py --authorize first "
                   "(the user clicks Always Allow in Zotero), then re-run", config=str(path))
    stored = zot.get("serverID")
    if stored and stored != server_id:
        raise Stop("server_mismatch", EXIT_CANNOT,
                   "the stored key belongs to another Zotero instance: run ready.py --authorize again, then re-run",
                   config=str(path), stored_server_id=stored, server_id=server_id)
    return zot["key"]


def check_collection(api: Api, key: str) -> str:
    """Return the collection's name; Stops when it does not exist."""
    try:
        status, _, body = api.request("GET", f"/api/users/0/collections/{key}")
    except Unreachable as e:
        raise Stop("zotero_unreachable", EXIT_CANNOT, "Zotero stopped answering: check it is running, then re-run",
                   detail=str(e))
    if status == 404:
        raise Stop("collection_not_found", EXIT_FAIL,
                   "no collection with this key: check the tree from ready.py or create it, then re-run", collection=key)
    if status != 200:
        raise Stop("unexpected_response", EXIT_CANNOT, "the collection lookup failed; check the local API",
                   status=status, detail=text(body), collection=key)
    data = json.loads(body).get("data", {})
    if data.get("deleted"):
        raise Stop("collection_not_found", EXIT_FAIL,
                   "this collection is in the trash: choose another from the tree, then re-run",
                   collection=key, name=data.get("name"))
    name = data.get("name")
    log(f"collection {key} = {name!r}")
    return name


def post_items(api: Api, objects: list[dict], key: str, server_id: str) -> dict:
    """POST an array of item objects; returns the parsed 200 body or Stops."""
    headers = {"Zotero-API-Key": key, "Zotero-Server-ID": server_id}
    try:
        status, _, body = api.request("POST", ITEMS_PATH, objects, headers, timeout=POST_TIMEOUT)
    except Unreachable as e:
        raise Stop("post_incomplete", EXIT_CANNOT,
                   "the POST did not complete, so the item may or may not exist: "
                   "look for it with find_in_library.py before creating it again", detail=str(e))
    log(f"POST {ITEMS_PATH} -> {status}")
    if status == 401:
        raise Stop("key_rejected", EXIT_CANNOT, "Zotero rejected the key: run ready.py --authorize again, then re-run",
                   detail=text(body))
    if status == 412:
        raise Stop("server_mismatch", EXIT_CANNOT,
                   "Zotero says the server ID does not match (Zotero restarted?): re-run; "
                   "if it persists, run ready.py --authorize again", detail=text(body), server_id=server_id)
    if status == 428:
        raise Stop("server_id_required", EXIT_CANNOT,
                   "Zotero says Zotero-Server-ID was missing although it was sent; report this as a script bug",
                   detail=text(body))
    if status == 403:
        if "not enabled" in text(body):
            raise Stop("local_api_disabled", EXIT_CANNOT,
                       "the local API was switched off: wait at the gate (ask the user to enable it), then re-run",
                       detail=text(body))
        raise Stop("library_not_editable", EXIT_CANNOT, "Zotero refuses writes to this library; tell the user",
                   detail=text(body))
    if status != 200:
        raise Stop("create_failed", EXIT_FAIL, "the request itself was rejected (nothing created): fix the item and re-run",
                   status=status, message=text(body))
    try:
        return json.loads(body)
    except ValueError:
        raise Stop("create_failed", EXIT_FAIL, "Zotero answered 200 with a body that is not JSON; report it",
                   status=status, message=text(body))


def normalize_readback_tags(tags) -> list[dict]:
    """Zotero may omit `type` for manual tags on the way back."""
    return [{"tag": t.get("tag"), "type": t.get("type", 0)} for t in (tags or []) if isinstance(t, dict)]


def readback(api: Api, created: dict, collections: list[str], tags: list[dict], citation_key):
    """Compare the created object with what was sent -> (filed, read_tags, tags_ok, citation_key_ok, missing, the
    item's citation key as Zotero has it)."""
    data = created.get("data") or {}
    needed = ["collections", "tags", "citationKey"]
    if any(field not in data for field in needed):  # the POST answer was thin: read the item itself
        try:
            status, _, body = api.request("GET", f"{ITEMS_PATH}/{created['key']}")
            if status == 200:
                data = json.loads(body).get("data") or data
        except (Unreachable, ValueError, AttributeError):
            pass
    missing = [c for c in collections if c not in (data.get("collections") or [])]
    filed = not missing if collections else None
    read_tags = normalize_readback_tags(data.get("tags"))
    tags_ok = {(t["tag"], t["type"]) for t in read_tags} == {(t["tag"], t["type"]) for t in tags}
    cite_ok = None if citation_key is None else data.get("citationKey") == citation_key
    return filed, read_tags, tags_ok, cite_ok, missing, data.get("citationKey") or None


def key_hint(key):
    """A citation key with a character TeX treats specially breaks \\cite{}: suggest it without them."""
    if not key or not TEX_SPECIAL.search(key):
        return {}
    return {"citation_key_hint": {"suggested": TEX_SPECIAL.sub("", key),
                                  "why": "TeX treats ^ _ & % $ # { } ~ \\ specially; ask the user, then "
                                         "update_item.py --key KEY --set citationKey=<suggested>"}}


# ---- single mode (v1) ----------------------------------------------------

def run_single(api: Api, args: argparse.Namespace) -> None:
    # 1. Local input: item.json, collection key format, tags.
    item = load_json_file(args.item, "item.json", "item_invalid")
    problems = check_item(item)
    if problems:
        raise Stop("item_invalid", EXIT_FAIL,
                   "fix item.json (check_item.py shows what the local API will do with each field), then re-run",
                   path=str(args.item), problems=problems)

    collections = list(dict.fromkeys(args.collection or []))
    for collection in collections:
        if not COLLECTION_KEY_RE.match(collection):
            raise Stop("collection_invalid", EXIT_FAIL,
                       "a collection key is 8 characters like ABCD1234: take it from the collection tree",
                       collection=collection)

    tag_problems: list[str] = []
    if args.tags_file is not None:
        raw_tags = load_json_file(args.tags_file, "tags file", "tags_invalid")
        tags = normalize_tags(raw_tags, tag_problems)
        if "tags" in item:
            log("tags in item.json are replaced by --tags-file")
    elif "tags" in item:
        tags = normalize_tags(item["tags"], tag_problems)
    else:
        tags = []
    if tag_problems:
        raise Stop("tags_invalid", EXIT_FAIL,
                   'tags are a JSON list of "name" or {"tag": "name", "type": 0|1}: fix the file, then re-run',
                   path=str(args.tags_file or args.item), problems=tag_problems)

    # 2. Zotero side: reachable, key usable, collection exists.
    server_id = live_server_id(api)
    api_key = load_key(server_id)
    names = [check_collection(api, c) for c in collections]

    payload = {k: v for k, v in item.items() if k not in ("tags", "collections")}
    payload["collections"] = collections
    payload["tags"] = tags
    summary = dict(title=payload["title"], itemType=payload["itemType"], collection=one_or_list(collections),
                   collection_name=one_or_list(names), unfiled=not collections, tags=tags)

    if args.dry_run:
        emit("ok", EXIT_OK, dry_run=True, server_id=server_id, **summary)

    # 3. The one write.
    result = post_items(api, [payload], api_key, server_id)
    failed = (result.get("failed") or {}).get("0")
    if failed is not None:
        raise Stop("create_failed", EXIT_FAIL, "the local API rejected the item (nothing created): fix item.json and re-run",
                   server_code=failed.get("code"), message=failed.get("message"))
    created = (result.get("successful") or {}).get("0")
    if not isinstance(created, dict) or not created.get("key"):
        raise Stop("create_failed", EXIT_FAIL, "unexpected response from the local API; report it",
                   message="200 without successful[\"0\"]", response=result)

    item_key, version = created["key"], created.get("version")
    filed, read_tags, tags_ok, _, _, _ = readback(api, created, collections, tags, None)
    log(f"created {item_key} v{version}; filed={filed} tags_ok={tags_ok}")

    saved = {"item_key": item_key, "version": version, "collection": one_or_list(collections), "tags": read_tags,
             "title": payload["title"], "itemType": payload["itemType"]}
    args.out.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fields = dict(item_key=item_key, version=version, filed=filed, tags_ok=tags_ok, out=str(args.out),
                  **{**summary, "tags": read_tags})
    if filed is False or not tags_ok:
        raise Stop("readback_mismatch", EXIT_FAIL,
                   f"the item exists but is not filed/tagged as sent: fix it with file_and_tag.py --key {item_key}",
                   **fields, tags_sent=tags)
    emit("ok", EXIT_OK, **fields)


# ---- stream mode -----------------------------------------------------------

def lookup_collection(api: Api, key: str, cache: dict) -> str:
    """check_collection with a per-run cache; a missing collection is remembered as its Stop."""
    if key not in cache:
        try:
            cache[key] = check_collection(api, key)
        except Stop as stop:
            if stop.exit_code != EXIT_FAIL:
                raise
            cache[key] = stop
    if isinstance(cache[key], Stop):
        raise cache[key]
    return cache[key]


def one_or_list(values):
    """One key prints as a string, several as a list (the record's own form)."""
    values = list(values)
    return values[0] if len(values) == 1 else values or None


def collection_keys(value) -> list[str]:
    if value is None or value == "":
        return []
    return [value] if isinstance(value, str) else list(value) if isinstance(value, list) else [value]


def candidates_of(found: dict) -> list[dict]:
    first = {"key": found.get("key"), "title": found.get("title"), "reason": found.get("reason")}
    if found.get("matched_by"):
        first["matched_by"] = found["matched_by"]
    return [first] + [{"key": c.get("key"), "title": c.get("title"), "reason": c.get("reason")}
                      for c in found.get("candidates") or [] if isinstance(c, dict)]


HINT_DUPLICATE = ("the library may already hold this paper (see `candidates`): if it is the same paper, set the "
                  "record's `found` to {\"key\": KEY}; if not, add KEY to `distinct_from`; then re-run. A "
                  "preprint/published pair is the user's call.")


def prepare_record(api: Api, rec: dict, slug, default_collections: list[str], cache: dict) -> dict:
    """Pre-check one record -> {"skipped": (section, key)} or {"payload", "collections", "names", "tags", "citation_key"}."""
    saved, found = rec.get("saved"), rec.get("found")
    if isinstance(saved, dict) and saved.get("key"):
        return {"skipped": ("saved", saved["key"])}
    if isinstance(found, dict) and found.get("key"):
        if found.get("code") == "near_match":
            raise Stop("possible_duplicate", EXIT_FAIL, HINT_DUPLICATE, candidates=candidates_of(found))
        return {"skipped": ("found", found["key"])}
    distinct = rec.get("distinct_from")
    if distinct is not None and not isinstance(distinct, str) and not (
            isinstance(distinct, list) and all(isinstance(k, str) for k in distinct)):
        raise Stop("distinct_from_invalid", EXIT_FAIL, "`distinct_from` is a list of item keys", distinct_from=distinct)
    item = rec.get("item")
    problems = check_item(item) if item is not None else ["the record has no `item`"]
    if problems:
        raise Stop("item_invalid", EXIT_FAIL, "fix the record's `item` (check_item.py shows what the local API will do "
                   "with each field), then re-run", problems=problems)

    collections = collection_keys(rec.get("collection")) or default_collections
    if not collections:
        raise Stop("no_collection", EXIT_FAIL, "put the destination key in the record's `collection` or pass --collection")
    for collection in collections:
        if not isinstance(collection, str) or not COLLECTION_KEY_RE.match(collection):
            raise Stop("collection_invalid", EXIT_FAIL,
                       "a collection key is 8 characters like ABCD1234: take it from the tree", collection=collection)
    collections = list(dict.fromkeys(collections))
    names = [lookup_collection(api, c, cache) for c in collections]

    tag_problems: list[str] = []
    if "tags" in rec:
        tags = normalize_tags(rec["tags"], tag_problems)
    elif item.get("tags"):
        tags = normalize_tags(item["tags"], tag_problems)
        log(f"{slug}: no `tags` in the record; using the tags inside `item`")
    else:
        tags = []
        log(f"{slug}: warning: no `tags` in the record; the item is created without tags")
    if tag_problems:
        raise Stop("tags_invalid", EXIT_FAIL, 'tags are a JSON list of "name" or {"tag": "name", "type": 0|1}',
                   problems=tag_problems)

    citation_key = rec.get("citationKey")
    if citation_key is not None:
        if not isinstance(citation_key, str) or not citation_key.strip():
            raise Stop("citation_key_invalid", EXIT_FAIL, "`citationKey` must be a non-empty string (or absent)",
                       citationKey=citation_key)
        citation_key = citation_key.strip()

    payload = {k: v for k, v in item.items() if k not in ("tags", "collections")}
    payload["collections"] = collections
    payload["tags"] = tags
    if citation_key:
        payload["citationKey"] = citation_key  # Zotero (and Better BibTeX) pin a key set on creation
    return {"payload": payload, "collections": collections, "names": names, "tags": tags,
            "citation_key": citation_key}


def look_up(base_url: str, pending: list) -> list[dict]:
    """find_in_library.py over the pending records (stdin -> stdout, one record per line, same order) -> their `found`."""
    lines = []
    for o, _ in pending:
        rec = o.record
        distinct = rec.get("distinct_from") or []
        lines.append(json.dumps({"slug": o.line["slug"], "item": rec.get("item"),
                                 "distinct_from": [distinct] if isinstance(distinct, str) else distinct},
                                ensure_ascii=False))
    try:
        done = subprocess.run([sys.executable, str(FIND_SCRIPT), "--base-url", base_url], input="\n".join(lines) + "\n",
                              capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Stop("lookup_failed", EXIT_CANNOT, "find_in_library.py could not run; nothing was posted", detail=str(e))
    rows = []
    for line in done.stdout.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    if done.returncode >= 2 or len(rows) != len(pending):
        raise Stop("lookup_failed", EXIT_CANNOT, "the duplicate check could not run; nothing was posted",
                   exit=done.returncode, detail=done.stderr.strip()[-400:])
    return [row.get("found") if isinstance(row.get("found"), dict) else None for row in rows]


def settle_duplicates(base_url: str, pending: list, dry_run: bool) -> list:
    """Look the pending records up; skip those already in the library (exists), fail the near matches; return the rest."""
    if not pending:
        return pending
    rest = []
    for (o, p), found in zip(pending, look_up(base_url, pending)):
        if found and found.get("code") == "found":
            if not dry_run:
                o.record["found"] = found
            extra = {"duplicates": found["duplicates"]} if found.get("duplicates") else {}
            o.set("skipped", "exists", changed=not dry_run, key=found.get("key"), matched_by=found.get("matched_by"),
                  citationKey=found.get("citationKey") or None, **extra)
        elif found and found.get("code") == "near_match":
            o.set("failed", "possible_duplicate", candidates=candidates_of(found), hint=HINT_DUPLICATE)
        else:
            rest.append((o, p))
    return rest


def post_pending(api: Api, pending: list, api_key: str, server_id: str) -> Stop | None:
    """POST the prepared records 50 at a time, filling each Outcome; returns the Stop that ended the run early, if any."""
    total_chunks = (len(pending) + CHUNK - 1) // CHUNK
    for start in range(0, len(pending), CHUNK):
        chunk = pending[start:start + CHUNK]
        log(f"chunk {start // CHUNK + 1}/{total_chunks}: {len(chunk)} item(s)")
        try:
            result = post_items(api, [p["payload"] for _, p in chunk], api_key, server_id)
        except Stop as stop:
            if stop.exit_code == EXIT_CANNOT:  # Zotero is gone or refuses us: nothing more can be written
                for o, _ in pending[start:]:
                    o.fail(stop)
                return stop
            for o, _ in chunk:  # the whole request was rejected; later chunks may still be fine
                o.fail(stop)
            continue
        successful, failed = result.get("successful") or {}, result.get("failed") or {}
        created_at = now_iso()
        for i, (o, p) in enumerate(chunk):
            created = successful.get(str(i))
            if not isinstance(created, dict) or not created.get("key"):
                f = failed.get(str(i)) or {"code": None, "message": "no result for this index"}
                o.set("failed", "create_failed", server_code=f.get("code"), message=f.get("message"),
                      hint="the local API rejected this item (nothing created): fix the record's `item` and re-run")
                continue
            key, version = created["key"], created.get("version")
            o.record["saved"] = {"key": key, "version": version, "created_at": created_at}
            filed, _, tags_ok, cite_ok, missing, cite = readback(api, created, p["collections"], p["tags"],
                                                                 p["citation_key"])
            fields = dict(key=key, version=version, collection=one_or_list(p["collections"]),
                          **({"citationKey": cite} if cite else {}), **key_hint(cite))
            if filed is False or not tags_ok or cite_ok is False:
                o.set("failed", "readback_mismatch", changed=True, **fields, filed=filed, collections_missing=missing,
                      tags_ok=tags_ok, citation_key_ok=cite_ok,
                      hint=f"the item exists (`saved` recorded) but is not filed/tagged/keyed as sent: "
                           f"fix it with file_and_tag.py / update_item.py --key {key}")
            else:
                o.set("ok", "ok", changed=True, **fields)
    return None


def run_stream(api: Api, args: argparse.Namespace) -> None:
    entries = load_records(args.records)
    for collection in args.collection or []:
        if not COLLECTION_KEY_RE.match(collection):
            raise Stop("collection_invalid", EXIT_FAIL,
                       "a collection key is 8 characters like ABCD1234: take it from the tree", collection=collection)
    server_id = live_server_id(api)
    api_key = load_key(server_id)

    outcomes, pending, cache = [], [], {}
    for path, rec in entries:
        o = Outcome(path, rec)
        outcomes.append(o)
        try:
            prepared = prepare_record(api, rec, o.line["slug"], args.collection or [], cache)
        except Stop as stop:
            if stop.exit_code == EXIT_CANNOT:
                raise  # nothing has been written yet: the whole run stops cleanly
            o.fail(stop)
            continue
        if "skipped" in prepared:
            section, key = prepared["skipped"]
            o.set("skipped", "skipped", reason=section, key=key)
        else:
            pending.append((o, prepared))

    pending = settle_duplicates(args.base_url, pending, args.dry_run)
    stopped = None
    if args.dry_run:
        for o, p in pending:
            o.set("ok", "ok", dry_run=True, collection=one_or_list(p["collections"]),
                  collection_name=one_or_list(p["names"]), tags=len(p["tags"]), citationKey=p["citation_key"],
                  title=p["payload"]["title"])
    else:
        stopped = post_pending(api, pending, api_key, server_id)
    sys.exit(write_results(outcomes, args.in_place, stopped))


# ---- main ----------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create Zotero items through the local write API, each filed into a collection and tagged "
                    "in a single POST, then verify the read-back: one item.json (--item) or a stream of records.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("records", nargs="*", metavar="RECORD",
                        help="record files (stream mode); none, and no --item: records are read from stdin")
    parser.add_argument("-i", "--in-place", action="store_true",
                        help="stream mode: write each updated record back to its file; stdout gets one summary line per record")
    parser.add_argument("--item", type=Path, metavar="item.json",
                        help="single mode: the item to create, in Zotero's item JSON format")
    parser.add_argument("--collection", metavar="KEY", action="append",
                        help="8-character key of a destination collection (from the tree ready.py prints), repeatable; "
                             "single mode: omitted = the item stays unfiled; stream mode: default for records without "
                             "`collection`")
    parser.add_argument("--tags-file", type=Path, metavar="tags.json",
                        help="single mode: complete tag list for the item (see files below)")
    parser.add_argument("--out", type=Path, metavar="saved.json",
                        help="single mode: where to write the result (required unless --dry-run)")
    parser.add_argument("--dry-run", action="store_true",
                        help="run every pre-check and report what would be sent; nothing is written")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help="Zotero's local server (default: %(default)s)")
    args = parser.parse_args(argv)
    if args.item is not None:
        if args.records:
            parser.error("--item (single mode) and record paths (stream mode) exclude each other")
        if args.in_place:
            parser.error("-i belongs to stream mode; single mode writes --out")
        if not args.dry_run and args.out is None:
            parser.error("--out is required unless --dry-run")
    else:
        if args.out is not None or args.tags_file is not None:
            parser.error("--out and --tags-file belong to single mode (--item); records carry their own `tags`")
        if not args.records and args.in_place:
            parser.error("-i needs record paths: records from stdin have no file to write back to")
        if not args.records and sys.stdin.isatty():
            parser.error("pass record files, pipe records to stdin, or use --item for single mode")
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
    api = Api(args.base_url)
    if args.item is not None:
        run_single(api, args)
    else:
        run_stream(api, args)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
