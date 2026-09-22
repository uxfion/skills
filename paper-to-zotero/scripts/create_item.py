# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Create one Zotero item through the local write API, filed and tagged in one POST
(paper-to-zotero, step 5).

Pre-checks (also everything --dry-run does): item.json is a parent item with
itemType and title; the tags file is valid; Zotero is reachable with the local
API on; a key is stored and belongs to this instance; the collection exists.
Only then the item is POSTed to /api/users/0/items with `collections` and
`tags` set, and the response object is compared with what was sent.

Nothing is retried: when the server reports the object as failed, nothing was
created; fix item.json and run again.

Output: exactly one JSON object on stdout with a stable `code`; diagnostics go
to stderr. The API key is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
DEFAULT_KEY_FILE = Path.home() / ".config" / "zotero" / "local-api-key"
ENV_KEY = "ZOTERO_LOCAL_API_KEY"
ITEMS_PATH = "/api/users/0/items"
COLLECTION_KEY_RE = re.compile(r"^[A-Z0-9]{8}$")
NOT_PARENT_TYPES = {"attachment", "note", "annotation"}
POST_TIMEOUT = 60

EXIT_OK, EXIT_FAIL, EXIT_CANNOT = 0, 1, 2

# Ignore http_proxy & co.: the local API only listens on the loopback interface.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

EPILOG = """\
exit codes:
  0  ok                  item created; `filed` and `tags_ok` say whether the read-back matches
  1  not passed          item_invalid | tags_invalid | collection_invalid | collection_not_found |
                         create_failed (server's code + message verbatim, nothing created) |
                         readback_mismatch (item exists: fix it with file_and_tag.py)
  2  cannot check        zotero_unreachable | local_api_disabled | no_key | key_file_invalid |
                         key_rejected | server_mismatch | server_id_required |
                         library_not_editable | post_incomplete

files:
  item.json   a Zotero item object (itemType, title, creators, ...) without key/version/
              collections; `tags` inside it are used only when --tags-file is absent
  tags.json   a JSON list; each entry is "name" (manual tag) or {"tag": "name", "type": 0|1}
              (0 manual, 1 automatic); it is the item's complete tag list
  saved.json  written on success: item_key, version, collection, tags, title, itemType

example:
  uv run create_item.py --item item.json --collection ABCD1234 --tags-file tags.json --out saved.json
"""


class Unreachable(Exception):
    pass


class RequestTimeout(Exception):
    pass


def log(message: str) -> None:
    print(message, file=sys.stderr)


def emit(code: str, exit_code: int = EXIT_OK, **fields) -> None:
    print(json.dumps({"code": code, **fields}, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


def request(base_url: str, method: str, path: str, body=None, headers=None, timeout: float = 30):
    """Return (status, headers, bytes). Raises Unreachable or RequestTimeout."""
    h = {"Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(base_url + path, data=data, method=method, headers=h)
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise RequestTimeout() from e
        raise Unreachable(str(e.reason)) from e
    except TimeoutError as e:
        raise RequestTimeout() from e
    except OSError as e:
        raise Unreachable(str(e)) from e


def text(body: bytes, limit: int = 300) -> str:
    return body.decode("utf-8", errors="replace").strip()[:limit]


# ---- local input -----------------------------------------------------------

def load_json_file(path: Path, what: str, code: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        emit(code, EXIT_FAIL, path=str(path), problems=[f"{what} could not be read as JSON: {e}"],
             hint=f"fix {path.name} and re-run")


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
        problems.append(f"itemType {item_type!r} is not a parent item (attachments go through attach_pdf.py)")
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        problems.append("'title' is missing or empty")
    for field in ("key", "version"):
        if field in item:
            problems.append(f"'{field}' must not be set on a new item")
    if "collections" in item:
        problems.append("'collections' must not be in item.json: the destination is --collection")
    return problems


# ---- Zotero side -----------------------------------------------------------

def live_server_id(base_url: str) -> str:
    """GET /api/ and return the running instance's Zotero-Server-ID."""
    try:
        status, headers, body = request(base_url, "GET", "/api/")
    except (Unreachable, RequestTimeout) as e:
        emit("zotero_unreachable", EXIT_CANNOT, base_url=base_url, detail=str(e) or "timed out",
             hint="Zotero is not listening there: wait at the gate (ask the user to start Zotero), then re-run")
    if status == 403:
        emit("local_api_disabled", EXIT_CANNOT, detail=text(body),
             hint="the local API is off: wait at the gate (ask the user to enable it in Zotero Settings > Advanced, "
                  "'Allow other applications on this computer to communicate with Zotero'), then re-run")
    if status != 200:
        emit("unexpected_response", EXIT_CANNOT, status=status, detail=text(body),
             hint="GET /api/ should answer 200; check what is listening on this port")
    server_id = headers.get("Zotero-Server-ID")
    if not server_id:
        emit("no_server_id", EXIT_CANNOT,
             hint="this Zotero sends no Zotero-Server-ID, so it has no local write API; it needs Zotero 10 or newer")
    log(f"GET /api/ -> {status}, server {server_id}")
    return server_id


def load_key(key_file: Path, server_id: str) -> tuple[str, str]:
    """Return (key, source). Exits with no_key / key_file_invalid / server_mismatch."""
    env_key = os.environ.get(ENV_KEY)
    if env_key:
        log(f"key from {ENV_KEY} ({env_key[:4]}...)")
        return env_key, "env"
    if not key_file.exists():
        emit("no_key", EXIT_CANNOT, path=str(key_file),
             hint="no key for the local write API: run authorize_local_api.py first "
                  "(the user clicks Always Allow in Zotero), then re-run")
    try:
        record = json.loads(key_file.read_text(encoding="utf-8"))
        key = record["key"]
        if not isinstance(key, str) or not key:
            raise ValueError("empty key")
    except (OSError, ValueError, KeyError, TypeError) as e:
        emit("key_file_invalid", EXIT_CANNOT, path=str(key_file), detail=str(e),
             hint="the key file is unreadable: run authorize_local_api.py --force, then re-run")
    stored = record.get("serverID")
    if stored != server_id:
        emit("server_mismatch", EXIT_CANNOT, path=str(key_file), stored_server_id=stored, server_id=server_id,
             hint="the stored key belongs to another Zotero instance: run authorize_local_api.py --force, then re-run")
    log(f"key from {key_file} ({key[:4]}...), server matches")
    return key, "file"


def check_collection(base_url: str, key: str) -> str:
    """Return the collection's name; exits when it does not exist."""
    try:
        status, _, body = request(base_url, "GET", f"/api/users/0/collections/{key}")
    except (Unreachable, RequestTimeout) as e:
        emit("zotero_unreachable", EXIT_CANNOT, detail=str(e) or "timed out",
             hint="Zotero stopped answering: check it is running, then re-run")
    if status == 404:
        emit("collection_not_found", EXIT_FAIL, collection=key,
             hint="no collection with this key: check `zotero collections` or create it, then re-run")
    if status != 200:
        emit("unexpected_response", EXIT_CANNOT, status=status, detail=text(body), collection=key,
             hint="the collection lookup failed; check the local API")
    data = json.loads(body).get("data", {})
    if data.get("deleted"):
        emit("collection_not_found", EXIT_FAIL, collection=key, name=data.get("name"),
             hint="this collection is in the trash: choose another with `zotero collections`, then re-run")
    name = data.get("name")
    log(f"collection {key} = {name!r}")
    return name


def post_item(base_url: str, item: dict, key: str, server_id: str):
    """POST the one-element array; returns the parsed 200 body or exits."""
    headers = {"Zotero-API-Key": key, "Zotero-Server-ID": server_id}
    try:
        status, _, body = request(base_url, "POST", ITEMS_PATH, [item], headers, timeout=POST_TIMEOUT)
    except (Unreachable, RequestTimeout) as e:
        emit("post_incomplete", EXIT_CANNOT, detail=str(e) or "timed out",
             hint="the POST did not complete, so the item may or may not exist: "
                  "look for it with find_in_library.py before creating it again")
    log(f"POST {ITEMS_PATH} -> {status}")
    if status == 401:
        emit("key_rejected", EXIT_CANNOT, detail=text(body),
             hint="Zotero rejected the key: run authorize_local_api.py --force, then re-run")
    if status == 412:
        emit("server_mismatch", EXIT_CANNOT, detail=text(body), server_id=server_id,
             hint="Zotero says the server ID does not match (Zotero restarted?): re-run; "
                  "if it persists, run authorize_local_api.py --force")
    if status == 428:
        emit("server_id_required", EXIT_CANNOT, detail=text(body),
             hint="Zotero says Zotero-Server-ID was missing although it was sent; report this as a script bug")
    if status == 403:
        if "not enabled" in text(body):
            emit("local_api_disabled", EXIT_CANNOT, detail=text(body),
                 hint="the local API was switched off: wait at the gate (ask the user to enable it), then re-run")
        emit("library_not_editable", EXIT_CANNOT, detail=text(body),
             hint="Zotero refuses writes to this library; tell the user")
    if status != 200:
        emit("create_failed", EXIT_FAIL, status=status, message=text(body),
             hint="the request itself was rejected (nothing created): fix item.json and re-run")
    try:
        return json.loads(body)
    except ValueError:
        emit("create_failed", EXIT_FAIL, status=status, message=text(body),
             hint="Zotero answered 200 with a body that is not JSON; report it")


def normalize_readback_tags(tags) -> list[dict]:
    """Zotero may omit `type` for manual tags on the way back."""
    return [{"tag": t.get("tag"), "type": t.get("type", 0)} for t in (tags or []) if isinstance(t, dict)]


# ---- main ----------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create one Zotero item through the local write API, filed into a collection and tagged "
                    "in a single POST, then verify the read-back.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--item", type=Path, required=True, metavar="item.json",
                        help="the item to create, in Zotero's item JSON format")
    parser.add_argument("--collection", metavar="KEY",
                        help="8-character key of the destination collection (from `zotero collections`); "
                             "omitted = the item stays unfiled")
    parser.add_argument("--tags-file", type=Path, metavar="tags.json",
                        help="complete tag list for the item (see files below)")
    parser.add_argument("--out", type=Path, metavar="saved.json",
                        help="where to write the result (required unless --dry-run)")
    parser.add_argument("--dry-run", action="store_true",
                        help="run every pre-check and report what would be sent; nothing is written")
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE,
                        help=f"key stored by authorize_local_api.py (default: %(default)s); "
                             f"the environment variable {ENV_KEY} overrides it")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help="Zotero's local server (default: %(default)s)")
    args = parser.parse_args(argv)
    if not args.dry_run and args.out is None:
        parser.error("--out is required unless --dry-run")
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
    base_url = args.base_url.rstrip("/")

    # 1. Local input: item.json, collection key format, tags.
    item = load_json_file(args.item, "item.json", "item_invalid")
    problems = check_item(item)
    if problems:
        emit("item_invalid", EXIT_FAIL, path=str(args.item), problems=problems,
             hint="fix item.json (check_item.py shows what the local API will do with each field), then re-run")

    collection = args.collection
    if collection is not None and not COLLECTION_KEY_RE.match(collection):
        emit("collection_invalid", EXIT_FAIL, collection=collection,
             hint="a collection key is 8 characters like ABCD1234: take it from `zotero collections`")

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
        emit("tags_invalid", EXIT_FAIL, path=str(args.tags_file or args.item), problems=tag_problems,
             hint='tags are a JSON list of "name" or {"tag": "name", "type": 0|1}: fix the file, then re-run')

    # 2. Zotero side: reachable, key usable, collection exists.
    server_id = live_server_id(base_url)
    api_key, key_source = load_key(args.key_file, server_id)
    collection_name = check_collection(base_url, collection) if collection else None

    payload = {k: v for k, v in item.items() if k not in ("tags", "collections")}
    payload["collections"] = [collection] if collection else []
    payload["tags"] = tags
    summary = dict(title=payload["title"], itemType=payload["itemType"], collection=collection,
                   collection_name=collection_name, unfiled=collection is None, tags=tags)

    if args.dry_run:
        emit("ok", EXIT_OK, dry_run=True, key_source=key_source, server_id=server_id, **summary)

    # 3. The one write.
    result = post_item(base_url, payload, api_key, server_id)
    failed = (result.get("failed") or {}).get("0")
    if failed is not None:
        emit("create_failed", EXIT_FAIL, server_code=failed.get("code"), message=failed.get("message"),
             hint="the local API rejected the item (nothing created): fix item.json and re-run")
    created = (result.get("successful") or {}).get("0")
    if not isinstance(created, dict) or not created.get("key"):
        emit("create_failed", EXIT_FAIL, message="200 without successful[\"0\"]", response=result,
             hint="unexpected response from the local API; report it")

    data = created.get("data") or {}
    item_key, version = created["key"], created.get("version")
    filed = (collection in (data.get("collections") or [])) if collection else None
    read_tags = normalize_readback_tags(data.get("tags"))
    tags_ok = {(t["tag"], t["type"]) for t in read_tags} == {(t["tag"], t["type"]) for t in tags}
    log(f"created {item_key} v{version}; filed={filed} tags_ok={tags_ok}")

    saved = {"item_key": item_key, "version": version, "collection": collection, "tags": read_tags,
             "title": payload["title"], "itemType": payload["itemType"]}
    args.out.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fields = dict(item_key=item_key, version=version, filed=filed, tags_ok=tags_ok, out=str(args.out),
                  **{**summary, "tags": read_tags})
    if filed is False or not tags_ok:
        emit("readback_mismatch", EXIT_FAIL, **fields, tags_sent=tags,
             hint=f"the item exists but is not filed/tagged as sent: fix it with file_and_tag.py --key {item_key}")
    emit("ok", EXIT_OK, **fields)


if __name__ == "__main__":
    main()
