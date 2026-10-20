#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Set the collections and/or the complete tag set of existing Zotero items, or add to / remove from them.

Single mode (--key, or --cite CITEKEY resolved to the one item carrying that
citationKey): GET the item -> diff against the targets -> PATCH only the
changed properties with If-Unmodified-Since-Version (one retry on 412) -> GET
again and verify. Batch mode (--batch): each entry names its item by "key" or
by "cite" (resolved like --cite; all resolved before anything is written), the
same diff per item, then one POST per chunk of 50 objects, each carrying its
version; per-key results.

Targets are absolute: the tag file is the COMPLETE desired tag set, and the
collection becomes exactly the one given — except with --add-collection /
--remove-collection / --add-tags-file (batch: "add_collection" /
"remove_collection" / "add_tags"), which add to or take from what the item
has and touch nothing else. Adding and removing combine (a move between two
collections that keeps the others); a removed collection the item is not in
is a no-op, so removal does not check that the collection exists. Re-running
is a no-op.

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
        raise Stop("key_rejected", 2, "The API key is not accepted by this Zotero; run ready.py --authorize again.",
                   status=status, body=msg)
    if status == 412 and "server-id" in msg.lower():
        raise Stop("server_mismatch", 2, "The key belongs to another Zotero instance; run ready.py --authorize again.",
                   status=status, body=msg)


def live_server_id(api):
    status, headers, body = api.request("GET", "/api/")
    check_common(status, body)
    sid = headers.get("Zotero-Server-ID")
    if status != 200 or not sid:
        raise Stop("zotero_unreachable", 2, "The endpoint does not behave like Zotero's local API; check --base-url.",
                   status=status, body=text(body))
    return sid


def config_path():
    return Path(os.environ.get("PAPER_TO_ZOTERO_CONFIG") or Path.home() / ".config" / "paper-to-zotero" / "config.json")


def load_key(server_id):
    """The local API key from the config file's "zotero" block (ready.py --authorize writes it). Never printed."""
    path = config_path()
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        config = {}
    except (OSError, ValueError) as e:
        raise Stop("config_unreadable", 2, "The config file is unreadable; fix it, then retry.",
                   config=str(path), error=str(e))
    zot = config.get("zotero") if isinstance(config, dict) else None
    zot = zot if isinstance(zot, dict) else {}
    if not isinstance(zot.get("key"), str) or not zot["key"]:
        raise Stop("no_key", 2, "No local API key yet; run ready.py --authorize first.", config=str(path))
    if zot.get("serverID") and zot["serverID"] != server_id:
        raise Stop("server_mismatch", 2, "The key was issued by another Zotero instance; run ready.py --authorize again.",
                   config=str(path))
    return zot["key"]


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


def parse_add_collection(value, what="An added"):
    """A collection key to add (or remove); 'none' makes no sense here."""
    if not isinstance(value, str) or not KEY_RE.match(value.strip()):
        raise Stop("invalid_collection", 1, f"{what} collection is an 8-character key from the collection tree.", collection=value)
    return value.strip()


def check_add_remove(add, remove, **where):
    """The same key cannot be both added and removed."""
    both = sorted(set(add or []) & set(remove or []))
    if both:
        raise Stop("invalid_collection", 1, "A collection cannot be both added and removed.", collections=both, **where)


def tag_map(tags):
    return {t.get("tag"): t.get("type", 0) for t in tags or [] if isinstance(t, dict)}


def resolve(item, spec):
    """Absolute targets for one item: the spec's collection/tags as given, or its add_collection / remove_collection /
    add_tags applied to what the item has."""
    data = item.get("data") or {}
    target_collection, target_tags = spec.get("collection"), spec.get("tags")
    if spec.get("add_collection") or spec.get("remove_collection"):
        current = list(data.get("collections") or [])
        target_collection = current + [k for k in spec.get("add_collection") or [] if k not in current]
        target_collection = [k for k in target_collection if k not in (spec.get("remove_collection") or [])]
    if spec.get("add_tags") is not None:
        merged = tag_map(data.get("tags"))
        merged.update(tag_map(spec["add_tags"]))
        target_tags = [{"tag": t, "type": ty} for t, ty in merged.items()]
    return target_collection, target_tags


def plan_item(item, spec):
    """Diff one item against its resolved targets; returns the readable change record, the patch body and the targets."""
    data = item.get("data") or {}
    target_collection, target_tags = resolve(item, spec)
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
    return ({"key": item.get("key"), "title": title, "version": item.get("version"), "collection": collection,
             "tags_added": tags_added, "tags_removed": tags_removed, "unchanged": not patch}, patch,
            (target_collection, target_tags))


def get_item(api, key):
    status, _, body = api.request("GET", f"{LIB}/items/{key}")
    check_common(status, body)
    if status == 404:
        return None
    if status != 200:
        raise Stop("unexpected_response", 1, "Unexpected local API reply; see status and body.", item_key=key, status=status, body=text(body))
    return json.loads(body)


def get_list(api, path):
    status, _, body = api.request("GET", path)
    check_common(status, body)
    if status != 200:
        raise Stop("unexpected_response", 1, "Unexpected local API reply; see status and body.", path=path, status=status, body=text(body))
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise Stop("unexpected_response", 1, "Expected a JSON list from the local API.", path=path)
    return rows


def is_top(row):
    data = row.get("data") or {}
    return data.get("itemType") not in ("note", "attachment", "annotation") and not data.get("parentItem")


def find_cites(api, cites):
    """{citationKey: [item keys]}: a q=everything search per key first (verified to hit on the local API, 2026-09-23),
    then one paged scan of /items/top as the fallback for every key the search missed."""
    hits = {}
    for cite in cites:
        query = urllib.parse.urlencode({"q": cite, "qmode": "everything", "limit": 50})
        rows = get_list(api, f"{LIB}/items?{query}")
        hits[cite] = [r["key"] for r in rows if is_top(r) and (r.get("data") or {}).get("citationKey") == cite]
    missing = {c for c in cites if not hits[c]}
    if missing:
        log(f"no search hit for citationKey {', '.join(sorted(map(repr, missing)))}; scanning /items/top (fallback)")
        start = 0
        while True:
            page = get_list(api, f"{LIB}/items/top?limit=100&start={start}")
            for r in page:
                cite = (r.get("data") or {}).get("citationKey")
                if cite in missing:
                    hits[cite].append(r["key"])
            if len(page) < 100:
                break
            start += 100
    return hits


def resolve_cite(api, cite):
    """Item key for a citationKey; cite_not_found / cite_ambiguous otherwise."""
    hits = find_cites(api, [cite])[cite]
    if not hits:
        raise Stop("cite_not_found", 1, "No item carries this citationKey; check it with read_library.py items --q, or pass --key.", cite=cite)
    if len(hits) > 1:
        raise Stop("cite_ambiguous", 1, "Several items carry this citationKey; pass --key for the one you mean.", cite=cite, keys=hits)
    log(f"citationKey {cite!r} -> item {hits[0]}")
    return hits[0]


def check_collections(api, keys):
    missing, trashed = [], []
    for k in sorted(keys):
        status, _, body = api.request("GET", f"{LIB}/collections/{k}")
        check_common(status, body)
        if status == 404:
            missing.append(k)
            continue
        if status != 200:
            raise Stop("unexpected_response", 1, "Unexpected local API reply; see status and body.", collection=k, status=status, body=text(body))
        try:
            data = json.loads(body).get("data") or {}
        except (ValueError, AttributeError):
            raise Stop("unexpected_response", 1, "The collection lookup did not return a JSON object.", collection=k, body=text(body))
        # A collection in the trash still answers 200, with data.deleted set; it is not a destination.
        if data.get("deleted"):
            trashed.append({"key": k, "name": data.get("name")})
    if missing or trashed:
        raise Stop("collection_not_found", 1, "Pick the key from the collection tree (zotero collections); the script never creates "
                   "collections, and a collection in the trash is not a destination.",
                   collections_missing=missing, collections_in_trash=trashed)


def verify(data, target_collection, target_tags):
    filed = None if target_collection is None else set(data.get("collections") or []) == set(target_collection)
    tags_ok = None if target_tags is None else tag_map(data.get("tags")) == tag_map(target_tags)
    return filed, tags_ok


def run_single(api, args, api_key, server_id):
    spec = {"collection": parse_collection(args.collection),
            "tags": load_tags_file(args.tags_file) if args.tags_file else None,
            "add_collection": [parse_add_collection(k) for k in args.add_collection] if args.add_collection else None,
            "remove_collection": [parse_add_collection(k, "A removed") for k in args.remove_collection] if args.remove_collection else None,
            "add_tags": load_tags_file(args.add_tags_file) if args.add_tags_file else None}
    check_add_remove(spec["add_collection"], spec["remove_collection"])
    item = get_item(api, args.key)
    if item is None:
        raise Stop("item_not_found", 1, "No item with that key; check the key from find_in_library.py.", item_key=args.key)
    if ((spec["collection"] is not None or spec["add_collection"] or spec["remove_collection"])
            and (item.get("data") or {}).get("parentItem")):
        raise Stop("not_a_parent", 1, "Only top-level items belong to collections; pass the parent item's key.",
                   item_key=args.key, parent_item=item["data"]["parentItem"])
    check_collections(api, set(spec["collection"] or []) | set(spec["add_collection"] or []))
    change, patch, targets = plan_item(item, spec)
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
            change, patch, targets = plan_item(item, spec)
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
    filed, tags_ok = verify(after.get("data") or {}, *targets)
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
        raise Stop("invalid_batch_file", 1, "The batch file is a non-empty JSON list of {\"key\" | \"cite\", \"collection\"?, \"tags\"?, ...}.",
                   batch_file=str(p))
    entries, seen = [], set()
    for i, e in enumerate(raw):
        if not isinstance(e, dict) or ("key" in e) == ("cite" in e):
            raise Stop("invalid_batch_file", 1, "Each entry names its item by an 8-character \"key\" or by a \"cite\" (citationKey), not both.",
                       batch_file=str(p), index=i, entry=e)
        if "key" in e and (not isinstance(e["key"], str) or not KEY_RE.match(e["key"])):
            raise Stop("invalid_batch_file", 1, "\"key\" is an 8-character item key.", batch_file=str(p), index=i, entry=e)
        if "cite" in e and (not isinstance(e["cite"], str) or not e["cite"].strip()):
            raise Stop("invalid_batch_file", 1, "\"cite\" is a non-empty citationKey.", batch_file=str(p), index=i, entry=e)
        who = {"key": e["key"]} if "key" in e else {"cite": e["cite"].strip()}
        ident = tuple(who.items())[0]
        if ident in seen:
            raise Stop("invalid_batch_file", 1, "Each key or cite may appear once.", batch_file=str(p), index=i, **who)
        seen.add(ident)
        if not any(k in e for k in ("collection", "tags", "add_collection", "remove_collection", "add_tags")):
            raise Stop("invalid_batch_file", 1, "An entry needs \"collection\" / \"add_collection\" / \"remove_collection\" "
                       "and/or \"tags\" / \"add_tags\".", batch_file=str(p), index=i, **who)
        if ("collection" in e and ("add_collection" in e or "remove_collection" in e)) or ("tags" in e and "add_tags" in e):
            raise Stop("invalid_batch_file", 1, "An entry sets its collection either absolutely or by adding / removing, not both; "
                       "same for tags.", batch_file=str(p), index=i, **who)
        lists = {}
        for field in ("add_collection", "remove_collection"):
            value = e.get(field)
            if isinstance(value, str):
                value = [value]
            if value is not None and not isinstance(value, list):
                raise Stop("invalid_batch_file", 1, f"\"{field}\" is a key or a list of keys.", batch_file=str(p), index=i, **who)
            lists[field] = value
        add = [parse_add_collection(k) for k in lists["add_collection"]] if lists["add_collection"] else None
        remove = [parse_add_collection(k, "A removed") for k in lists["remove_collection"]] if lists["remove_collection"] else None
        check_add_remove(add, remove, batch_file=str(p), index=i, **who)
        entries.append({**who,
                        "collection": parse_collection(e["collection"], null_clears=True) if "collection" in e else None,
                        "tags": normalize_tags(e["tags"], f"{p}[{i}].tags") if "tags" in e else None,
                        "add_collection": add, "remove_collection": remove,
                        "add_tags": normalize_tags(e["add_tags"], f"{p}[{i}].add_tags") if "add_tags" in e else None})
    return entries


def resolve_batch_cites(api, entries):
    """Give every "cite" entry its item key; all-or-nothing, before anything is read or written."""
    cites = [e["cite"] for e in entries if "cite" in e]
    if not cites:
        return
    hits = find_cites(api, cites)
    not_found = [c for c in cites if not hits[c]]
    ambiguous = [{"cite": c, "keys": hits[c]} for c in cites if len(hits[c]) > 1]
    if not_found or ambiguous:
        hint = "Fix these citationKeys in the batch file (or give the item \"key\" instead); nothing was written."
        extra = {"cites_not_found": not_found, "cites_ambiguous": ambiguous}
        raise Stop("cite_not_found" if not_found else "cite_ambiguous", 1, hint, **extra)
    for e in entries:
        if "cite" in e:
            e["key"] = hits[e["cite"]][0]
            log(f"citationKey {e['cite']!r} -> item {e['key']}")
    by_key = {}
    for e in entries:
        by_key.setdefault(e["key"], []).append(e.get("cite") or e["key"])
    twice = {k: v for k, v in by_key.items() if len(v) > 1}
    if twice:
        raise Stop("invalid_batch_file", 1, "Several entries name the same item; merge them.", same_item=twice)


def run_batch(api, args, api_key, server_id):
    entries = load_batch(args.batch)
    resolve_batch_cites(api, entries)
    items, missing, colls = {}, [], set()
    for e in entries:
        item = get_item(api, e["key"])
        if item is None:
            missing.append(e["key"])
            continue
        items[e["key"]] = item
        if ((e["collection"] is not None or e["add_collection"] or e["remove_collection"])
                and (item.get("data") or {}).get("parentItem")):
            raise Stop("not_a_parent", 1, "Only top-level items belong to collections; use the parent item's key.",
                       item_key=e["key"], parent_item=item["data"]["parentItem"])
        colls.update(e["collection"] or [])
        colls.update(e["add_collection"] or [])
    if missing:
        raise Stop("item_not_found", 1, "Remove or fix these keys in the batch file; nothing was written.", items_missing=missing)
    check_collections(api, colls)

    changes, objects = [], []
    for e in entries:
        change, patch, targets = plan_item(items[e["key"]], e)
        if "cite" in e:
            change = {"key": change.pop("key"), "cite": e["cite"], **change}
        changes.append(change)
        if patch:
            objects.append(({"key": e["key"], "version": items[e["key"]]["version"], **patch}, e, targets))
    summary = {"total": len(entries), "to_write": len(objects), "unchanged": len(entries) - len(objects)}
    if args.dry_run or not objects:
        emit("ok", 0, dry_run=args.dry_run, **summary, changes=changes)

    results, failures, chunks_written = [], [], 0
    for start in range(0, len(objects), CHUNK):
        chunk = objects[start:start + CHUNK]
        status, _, body = api.request("POST", f"{LIB}/items", [o for o, _, _ in chunk], write_headers(api_key, server_id))
        check_common(status, body)
        if status != 200:
            raise Stop("batch_failed", 1, "A whole chunk was rejected; earlier chunks are written. Fix the cause and re-run (unchanged items are skipped).",
                       status=status, body=text(body), chunk_index=start // CHUNK, chunks_written=chunks_written, results=results)
        resp = json.loads(body)
        successful, unchanged, failed = resp.get("successful") or {}, resp.get("unchanged") or {}, resp.get("failed") or {}
        for i, (obj, e, targets) in enumerate(chunk):
            idx, title = str(i), items[e["key"]]["data"].get("title", "")[:80]
            who = {"key": e["key"], **({"cite": e["cite"]} if "cite" in e else {})}
            if idx in successful:
                data = successful[idx].get("data") or {}
                filed, tags_ok = verify(data, *targets)
                ok = filed is not False and tags_ok is not False
                results.append({**who, "title": title, "result": "ok" if ok else "failed",
                                "version": successful[idx].get("version"), "filed": filed, "tags_ok": tags_ok})
                if not ok:
                    failures.append({"key": e["key"], "code": "verify_failed", "message": "written, but the read-back differs from the target"})
            elif idx in unchanged:
                results.append({**who, "title": title, "result": "unchanged"})
            else:
                f = failed.get(idx) or {"code": None, "message": "no result for this index"}
                results.append({**who, "title": title, "result": "failed", "status": f.get("code"), "message": f.get("message")})
                failures.append({"key": e["key"], "status": f.get("code"), "message": f.get("message")})
        chunks_written += 1
    unchanged_keys = [c["key"] for c in changes if c["unchanged"]]
    out = {**summary, "written": sum(1 for r in results if r["result"] == "ok"), "failed": len(failures),
           "changes": changes, "results": results, "skipped_unchanged": unchanged_keys}  # `changes` as in --dry-run
    if failures:
        raise Stop("partial_failure", 1, "Re-run the same batch: written items are skipped as unchanged; 412 means the item changed meanwhile.",
                   failures=failures, **out)
    emit("ok", 0, **out)


def parse_args():
    p = argparse.ArgumentParser(
        description="Set — or add to / remove from — the collections and tags of existing Zotero items via the local write API.",
        epilog="Targets are absolute unless given as add-* / remove-*; re-runs are no-ops. Exit 0 = done; 1 = not done, see code/hint "
               "(item_not_found, cite_not_found, cite_ambiguous, collection_not_found, invalid_collection, invalid_batch_file, "
               "not_a_parent, version_conflict, verify_failed, partial_failure, ...); "
               "2 = cannot check (zotero_unreachable, local_api_disabled, no_key, key_rejected, server_mismatch). "
               "Output is one JSON object on stdout. "
               "Example batch entry: {\"cite\": \"liu2022progressive\", \"add_collection\": \"NEWCOLL1\", \"remove_collection\": [\"OLDCOLL1\"]}")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--key", metavar="ITEMKEY", help="single mode: key of the item to update")
    mode.add_argument("--cite", metavar="CITEKEY", help="single mode: the item's citationKey instead of its key "
                                                        "(cite_not_found / cite_ambiguous when it does not name exactly one item)")
    mode.add_argument("--batch", metavar="CHANGES.json",
                      help="batch mode: JSON list of {\"key\" | \"cite\", \"collection\": KEY|null|\"none\" (optional), \"tags\": [...] "
                           "(optional)}; \"add_collection\": KEY|[KEYS] and \"add_tags\": [...] add instead of replacing, "
                           "\"remove_collection\": KEY|[KEYS] takes the item out of those (combines with add_collection); "
                           "\"cite\" is resolved like --cite, every cite before anything is written")
    p.add_argument("--collection", metavar="COLLKEY",
                   help="single mode: the item's only collection becomes this key (a move); 'none' clears it; omitted = leave alone")
    p.add_argument("--tags-file", metavar="TAGS.json",
                   help="single mode: the COMPLETE desired tag set, a JSON list of {\"tag\", \"type\"} (type 0 manual, 1 automatic) "
                        "or plain strings (type 0); omitted = leave tags alone")
    p.add_argument("--add-collection", metavar="COLLKEY", action="append",
                   help="single mode: add the item to this collection, keeping its others (repeatable)")
    p.add_argument("--remove-collection", metavar="COLLKEY", action="append",
                   help="single mode: take the item out of this collection, keeping its others (repeatable; combines with "
                        "--add-collection; a collection the item is not in is a no-op)")
    p.add_argument("--add-tags-file", metavar="TAGS.json",
                   help="single mode: tags to add to the item's existing ones, same format as --tags-file")
    p.add_argument("--dry-run", action="store_true", help="print the change list (per key: tags_added, tags_removed, collection from/to); write nothing")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    args = p.parse_args()
    single_opts = (args.collection, args.tags_file, args.add_collection, args.remove_collection, args.add_tags_file)
    if (args.key or args.cite) and all(o is None for o in single_opts):
        p.error("--key / --cite needs --collection / --add-collection / --remove-collection and/or --tags-file / --add-tags-file")
    if args.batch and any(o is not None for o in single_opts):
        p.error("--collection / --tags-file / --add-* / --remove-collection belong to single mode; put them in the batch file")
    if args.collection is not None and (args.add_collection or args.remove_collection):
        p.error("--collection (replace) and --add-collection / --remove-collection (add / remove) exclude each other")
    if args.tags_file and args.add_tags_file:
        p.error("--tags-file (the complete set) and --add-tags-file (add) exclude each other")
    if args.key and not KEY_RE.match(args.key):
        p.error("--key is an 8-character item key")
    return args


def main():
    args = parse_args()
    api = Api(args.base_url)
    server_id = live_server_id(api)
    api_key = load_key(server_id)
    if args.batch:
        run_batch(api, args, api_key, server_id)
    else:
        if args.cite:
            args.key = resolve_cite(api, args.cite)
        run_single(api, args, api_key, server_id)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
