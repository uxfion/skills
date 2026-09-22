# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Set the collection and/or the complete tag set of existing Zotero items.

Single mode (--key): GET the item -> diff against the targets -> PATCH only the
changed properties with If-Unmodified-Since-Version (one retry on 412) -> GET
again and verify. Batch mode (--batch): the same diff per item, then one POST
per chunk of 50 objects, each carrying its version; per-key results.

Targets are absolute: the tag file is the COMPLETE desired tag set, and the
collection becomes exactly the one given. Re-running is a no-op.

stdout: exactly one JSON object with a stable `code` (`ok` on success);
diagnostics go to stderr. Exit 0 = done, 1 = not done (the agent decides),
2 = cannot check (Zotero unreachable, local API disabled, no key, key
rejected, key belongs to another Zotero instance).
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
DEFAULT_KEY_FILE = "~/.config/zotero/local-api-key"
LIB = "/api/users/0"
CHUNK = 50
KEY_RE = re.compile(r"^[A-Z0-9]{8}$")
CLEAR_WORDS = {"none", ""}


class Stop(Exception):
    """Carry a result code out of any depth; main() turns it into JSON + exit."""

    def __init__(self, code, exit_code=1, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit_code, self.hint, self.extra = code, exit_code, hint, extra


def log(msg):
    print(msg, file=sys.stderr)


def emit(code, exit_code=0, hint=None, **extra):
    out = {"code": code, **extra}
    if hint and exit_code != 0:
        out["hint"] = hint
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


def text(body, limit=400):
    return body.decode("utf-8", errors="replace").strip()[:limit]


class Api:
    """Minimal client for the local API; bypasses any proxy from the environment."""

    def __init__(self, base_url, timeout=120):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, body=None, headers=None):
        h = {"Accept": "application/json"}
        h.update(headers or {})
        data = None
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        elif body is not None:
            data = str(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", None) or e
            raise Stop("zotero_unreachable", 2, "Start Zotero, then retry; check --base-url if it is not the default.",
                       base_url=self.base, error=str(reason))


def check_common(status, body):
    """Failures that mean 'cannot check' regardless of which call produced them."""
    msg = text(body)
    if status == 403 and "not enabled" in msg.lower():
        raise Stop("local_api_disabled", 2, "Ask the user to enable the local API in Zotero settings (Advanced), then retry.",
                   status=status, body=msg)
    if status == 401:
        raise Stop("key_rejected", 2, "The API key is not accepted by this Zotero; run authorize_local_api.py again.",
                   status=status, body=msg)
    if status == 412 and "server-id" in msg.lower():
        raise Stop("server_mismatch", 2, "The key belongs to another Zotero instance; run authorize_local_api.py again.",
                   status=status, body=msg)


def live_server_id(api):
    status, headers, body = api.request("GET", "/api/")
    check_common(status, body)
    sid = headers.get("Zotero-Server-ID")
    if status != 200 or not sid:
        raise Stop("zotero_unreachable", 2, "The endpoint does not behave like Zotero's local API; check --base-url.",
                   status=status, body=text(body))
    return sid


def load_key(key_file, server_id):
    """Return the API key; ZOTERO_LOCAL_API_KEY overrides the key file. Never printed."""
    env = os.environ.get("ZOTERO_LOCAL_API_KEY")
    if env:
        return env.strip()
    path = Path(key_file).expanduser()
    if not path.is_file():
        raise Stop("no_key", 2, "No local API key yet; run authorize_local_api.py first (or set ZOTERO_LOCAL_API_KEY).",
                   key_file=str(path))
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        key = info["key"]
    except (ValueError, KeyError, TypeError) as e:
        raise Stop("no_key", 2, "The key file is unreadable; run authorize_local_api.py again.",
                   key_file=str(path), error=str(e))
    saved = info.get("serverID")
    if saved and saved != server_id:
        raise Stop("server_mismatch", 2, "The saved key was issued by another Zotero instance; run authorize_local_api.py again.",
                   key_file=str(path))
    return key


def write_headers(key, server_id, version=None):
    h = {"Zotero-API-Key": key, "Zotero-Server-ID": server_id}
    if version is not None:
        h["If-Unmodified-Since-Version"] = str(version)
    return h


def normalize_tags(raw, source):
    """Accept [{"tag","type"}] or plain strings (type 0); dedupe by tag name, last wins."""
    if not isinstance(raw, list):
        raise Stop("invalid_tags_file", 1, "The tag set must be a JSON list of {\"tag\", \"type\"} objects or strings.", source=source)
    ordered = {}
    for i, entry in enumerate(raw):
        if isinstance(entry, str):
            tag, ttype = entry, 0
        elif isinstance(entry, dict) and isinstance(entry.get("tag"), str):
            tag, ttype = entry["tag"], entry.get("type", 0)
        else:
            raise Stop("invalid_tags_file", 1, "Each tag is a string or {\"tag\": str, \"type\": 0|1}.", source=source, index=i, entry=entry)
        tag = tag.strip()
        if not tag or ttype not in (0, 1):
            raise Stop("invalid_tags_file", 1, "Tags must be non-empty; type is 0 (manual) or 1 (automatic).", source=source, index=i, entry=entry)
        if tag in ordered:
            log(f"{source}: duplicate tag {tag!r}, keeping the last occurrence")
        ordered[tag] = ttype
    return [{"tag": t, "type": ty} for t, ty in ordered.items()]


def load_tags_file(path):
    p = Path(path).expanduser()
    if not p.is_file():
        raise Stop("tags_file_not_found", 1, "Write the complete desired tag set to a JSON file and pass it with --tags-file.", tags_file=str(p))
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Stop("invalid_tags_file", 1, "The tag file is not valid JSON.", tags_file=str(p), error=str(e))
    return normalize_tags(raw, str(p))


def parse_collection(value, null_clears=False):
    """Target collections: [] = clear, [KEY] = move. 'none' (and null in batch files) clears."""
    if value is None:
        return [] if null_clears else None
    if not isinstance(value, str):
        raise Stop("invalid_collection", 1, "A collection is an 8-character key from the collection tree, or 'none' to clear.", collection=value)
    value = value.strip()
    if value.lower() in CLEAR_WORDS:
        return []
    if not KEY_RE.match(value):
        raise Stop("invalid_collection", 1, "A collection is an 8-character key from the collection tree, or 'none' to clear.", collection=value)
    return [value]


def tag_map(tags):
    return {t.get("tag"): t.get("type", 0) for t in tags or [] if isinstance(t, dict)}


def plan_item(item, target_collection, target_tags):
    """Diff one item against its targets; returns the readable change record plus the patch body."""
    data = item.get("data") or {}
    patch = {}
    current_coll = list(data.get("collections") or [])
    collection = None
    if target_collection is not None and set(current_coll) != set(target_collection):
        collection = {"from": current_coll, "to": target_collection}
        patch["collections"] = target_collection
    tags_added, tags_removed = [], []
    if target_tags is not None:
        cur, tgt = tag_map(data.get("tags")), tag_map(target_tags)
        tags_added = [{"tag": t, "type": ty} for t, ty in tgt.items() if cur.get(t) != ty]
        tags_removed = [{"tag": t, "type": ty} for t, ty in cur.items() if tgt.get(t) != ty]
        if tags_added or tags_removed:
            patch["tags"] = target_tags
    title = (data.get("title") or "")[:80]
    return {"key": item.get("key"), "title": title, "version": item.get("version"), "collection": collection,
            "tags_added": tags_added, "tags_removed": tags_removed, "unchanged": not patch}, patch


def get_item(api, key):
    status, _, body = api.request("GET", f"{LIB}/items/{key}")
    check_common(status, body)
    if status == 404:
        return None
    if status != 200:
        raise Stop("unexpected_response", 1, "Unexpected local API reply; see status and body.", item_key=key, status=status, body=text(body))
    return json.loads(body)


def check_collections(api, keys):
    missing = []
    for k in sorted(keys):
        status, _, body = api.request("GET", f"{LIB}/collections/{k}")
        check_common(status, body)
        if status == 404:
            missing.append(k)
        elif status != 200:
            raise Stop("unexpected_response", 1, "Unexpected local API reply; see status and body.", collection=k, status=status, body=text(body))
    if missing:
        raise Stop("collection_not_found", 1, "Pick the key from the collection tree (zotero collections); the script never creates collections.",
                   collections_missing=missing)


def verify(data, target_collection, target_tags):
    filed = None if target_collection is None else set(data.get("collections") or []) == set(target_collection)
    tags_ok = None if target_tags is None else tag_map(data.get("tags")) == tag_map(target_tags)
    return filed, tags_ok


def run_single(api, args, api_key, server_id):
    target_collection = parse_collection(args.collection)
    target_tags = load_tags_file(args.tags_file) if args.tags_file else None
    item = get_item(api, args.key)
    if item is None:
        raise Stop("item_not_found", 1, "No item with that key; check the key from find_in_library.py.", item_key=args.key)
    if target_collection is not None and (item.get("data") or {}).get("parentItem"):
        raise Stop("not_a_parent", 1, "Only top-level items belong to collections; pass the parent item's key.",
                   item_key=args.key, parent_item=item["data"]["parentItem"])
    if target_collection:
        check_collections(api, target_collection)
    change, patch = plan_item(item, target_collection, target_tags)
    if not patch:
        emit("ok", 0, item_key=args.key, unchanged=True, version=item.get("version"))
    if args.dry_run:
        emit("ok", 0, dry_run=True, item_key=args.key, unchanged=False, collection=change["collection"],
             tags_added=change["tags_added"], tags_removed=change["tags_removed"], version=item.get("version"))

    retried = False
    for attempt in (1, 2):
        status, _, body = api.request("PATCH", f"{LIB}/items/{args.key}", patch, write_headers(api_key, server_id, item["version"]))
        check_common(status, body)
        if status == 204:
            break
        if status == 412 and attempt == 1:
            log(f"412 on PATCH ({text(body, 120)}); re-reading the item and retrying once")
            retried = True
            item = get_item(api, args.key)
            if item is None:
                raise Stop("item_not_found", 1, "The item disappeared while patching.", item_key=args.key)
            change, patch = plan_item(item, target_collection, target_tags)
            if not patch:
                emit("ok", 0, item_key=args.key, unchanged=True, retried=True, version=item.get("version"))
            continue
        if status == 412:
            raise Stop("version_conflict", 1, "The item keeps changing under us (Zotero sync or the user editing); wait, then re-run.",
                       item_key=args.key, status=status, body=text(body))
        if status == 403:
            raise Stop("write_denied", 1, "This library is not editable.", item_key=args.key, status=status, body=text(body))
        raise Stop("patch_failed", 1, "The local API rejected the patch; see body.", item_key=args.key, status=status, body=text(body), patch=patch)

    after = get_item(api, args.key)
    if after is None:
        raise Stop("item_not_found", 1, "The item disappeared after patching.", item_key=args.key)
    filed, tags_ok = verify(after.get("data") or {}, target_collection, target_tags)
    result = {"item_key": args.key, "unchanged": False, "collection": change["collection"], "tags_added": change["tags_added"],
              "tags_removed": change["tags_removed"], "filed": filed, "tags_ok": tags_ok,
              "version_before": item.get("version"), "version_after": after.get("version"), "retried": retried}
    if filed is False or tags_ok is False:
        raise Stop("verify_failed", 1, "The PATCH returned 204 but the read-back differs; inspect the item in Zotero.",
                   **result, collections_now=after["data"].get("collections"), tags_now=after["data"].get("tags"))
    emit("ok", 0, **result)


def load_batch(path):
    p = Path(path).expanduser()
    if not p.is_file():
        raise Stop("batch_file_not_found", 1, "Write the change list to a JSON file and pass it with --batch.", batch_file=str(p))
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Stop("invalid_batch_file", 1, "The batch file is not valid JSON.", batch_file=str(p), error=str(e))
    if not isinstance(raw, list) or not raw:
        raise Stop("invalid_batch_file", 1, "The batch file is a non-empty JSON list of {\"key\", \"collection\"?, \"tags\"?}.", batch_file=str(p))
    entries, seen = [], set()
    for i, e in enumerate(raw):
        if not isinstance(e, dict) or not isinstance(e.get("key"), str) or not KEY_RE.match(e["key"]):
            raise Stop("invalid_batch_file", 1, "Each entry needs an 8-character \"key\".", batch_file=str(p), index=i, entry=e)
        if e["key"] in seen:
            raise Stop("invalid_batch_file", 1, "Each key may appear once.", batch_file=str(p), index=i, key=e["key"])
        seen.add(e["key"])
        if "collection" not in e and "tags" not in e:
            raise Stop("invalid_batch_file", 1, "An entry needs \"collection\" and/or \"tags\".", batch_file=str(p), index=i, key=e["key"])
        collection = parse_collection(e["collection"], null_clears=True) if "collection" in e else None
        tags = normalize_tags(e["tags"], f"{p}[{i}].tags") if "tags" in e else None
        entries.append({"key": e["key"], "collection": collection, "tags": tags})
    return entries


def run_batch(api, args, api_key, server_id):
    entries = load_batch(args.batch)
    items, missing, colls = {}, [], set()
    for e in entries:
        item = get_item(api, e["key"])
        if item is None:
            missing.append(e["key"])
            continue
        items[e["key"]] = item
        if e["collection"] is not None and (item.get("data") or {}).get("parentItem"):
            raise Stop("not_a_parent", 1, "Only top-level items belong to collections; use the parent item's key.",
                       item_key=e["key"], parent_item=item["data"]["parentItem"])
        colls.update(e["collection"] or [])
    if missing:
        raise Stop("item_not_found", 1, "Remove or fix these keys in the batch file; nothing was written.", items_missing=missing)
    check_collections(api, colls)

    changes, objects = [], []
    for e in entries:
        change, patch = plan_item(items[e["key"]], e["collection"], e["tags"])
        changes.append(change)
        if patch:
            objects.append(({"key": e["key"], "version": items[e["key"]]["version"], **patch}, e))
    summary = {"total": len(entries), "to_write": len(objects), "unchanged": len(entries) - len(objects)}
    if args.dry_run or not objects:
        emit("ok", 0, dry_run=args.dry_run, **summary, changes=changes)

    results, failures, chunks_written = [], [], 0
    for start in range(0, len(objects), CHUNK):
        chunk = objects[start:start + CHUNK]
        status, _, body = api.request("POST", f"{LIB}/items", [o for o, _ in chunk], write_headers(api_key, server_id))
        check_common(status, body)
        if status != 200:
            raise Stop("batch_failed", 1, "A whole chunk was rejected; earlier chunks are written. Fix the cause and re-run (unchanged items are skipped).",
                       status=status, body=text(body), chunk_index=start // CHUNK, chunks_written=chunks_written, results=results)
        resp = json.loads(body)
        successful, unchanged, failed = resp.get("successful") or {}, resp.get("unchanged") or {}, resp.get("failed") or {}
        for i, (obj, e) in enumerate(chunk):
            idx, title = str(i), items[e["key"]]["data"].get("title", "")[:80]
            if idx in successful:
                data = successful[idx].get("data") or {}
                filed, tags_ok = verify(data, e["collection"], e["tags"])
                ok = filed is not False and tags_ok is not False
                results.append({"key": e["key"], "title": title, "result": "ok" if ok else "failed",
                                "version": successful[idx].get("version"), "filed": filed, "tags_ok": tags_ok})
                if not ok:
                    failures.append({"key": e["key"], "code": "verify_failed", "message": "written, but the read-back differs from the target"})
            elif idx in unchanged:
                results.append({"key": e["key"], "title": title, "result": "unchanged"})
            else:
                f = failed.get(idx) or {"code": None, "message": "no result for this index"}
                results.append({"key": e["key"], "title": title, "result": "failed", "status": f.get("code"), "message": f.get("message")})
                failures.append({"key": e["key"], "status": f.get("code"), "message": f.get("message")})
        chunks_written += 1
    unchanged_keys = [c["key"] for c in changes if c["unchanged"]]
    out = {**summary, "written": sum(1 for r in results if r["result"] == "ok"), "failed": len(failures),
           "results": results, "skipped_unchanged": unchanged_keys}
    if failures:
        raise Stop("partial_failure", 1, "Re-run the same batch: written items are skipped as unchanged; 412 means the item changed meanwhile.",
                   failures=failures, **out)
    emit("ok", 0, **out)


def parse_args():
    p = argparse.ArgumentParser(
        description="Set the collection and/or the complete tag set of existing Zotero items via the local write API.",
        epilog="Targets are absolute and re-runs are no-ops. Exit 0 = done; 1 = not done, see code/hint; "
               "2 = cannot check (zotero_unreachable, local_api_disabled, no_key, key_rejected, server_mismatch). "
               "Output is one JSON object on stdout.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--key", metavar="ITEMKEY", help="single mode: key of the item to update")
    mode.add_argument("--batch", metavar="CHANGES.json",
                      help="batch mode: JSON list of {\"key\", \"collection\": KEY|null|\"none\" (optional), \"tags\": [...] (optional)}")
    p.add_argument("--collection", metavar="COLLKEY",
                   help="single mode: the item's only collection becomes this key (a move); 'none' clears it; omitted = leave alone")
    p.add_argument("--tags-file", metavar="TAGS.json",
                   help="single mode: the COMPLETE desired tag set, a JSON list of {\"tag\", \"type\"} (type 0 manual, 1 automatic) "
                        "or plain strings (type 0); omitted = leave tags alone")
    p.add_argument("--dry-run", action="store_true", help="print the change list (per key: tags_added, tags_removed, collection from/to); write nothing")
    p.add_argument("--key-file", default=DEFAULT_KEY_FILE, metavar="PATH",
                   help="JSON file holding the local API key (default: %(default)s); env ZOTERO_LOCAL_API_KEY overrides")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    args = p.parse_args()
    if args.key and args.collection is None and args.tags_file is None:
        p.error("--key needs --collection and/or --tags-file")
    if args.batch and (args.collection is not None or args.tags_file is not None):
        p.error("--collection / --tags-file belong to single mode; put them in the batch file")
    if args.key and not KEY_RE.match(args.key):
        p.error("--key is an 8-character item key")
    return args


def main():
    args = parse_args()
    api = Api(args.base_url)
    server_id = live_server_id(api)
    api_key = load_key(args.key_file, server_id)
    if args.batch:
        run_batch(api, args, api_key, server_id)
    else:
        run_single(api, args, api_key, server_id)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
