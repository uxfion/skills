# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Move Zotero items or attachments to the trash (undoable for 30 days), or restore them, once the user has confirmed the list.

Use it only after the user has seen and confirmed the list (run --dry-run
first and show it): superseded attachments, duplicate items the user agreed to
drop, stray attachments that never got a parent. The trash is a 30-day undo:
the user, or --restore, brings an item back, and Zotero deletes for good what
has been in the trash longer (its trashAutoEmptyDays setting, 30 by default).
Nothing here empties the trash or deletes anything itself.

Items are named by --key (top-level items or child attachments / notes, by
their own key) and/or --cite CITEKEY (resolved to the one top-level item
carrying that citationKey). For each: GET the item -> already in the wanted
state? report it -> PATCH {"deleted": 1} (--restore: {"deleted": 0}) with
If-Unmodified-Since-Version (on 412: re-read and retry once) -> GET again and
verify. Trashing a parent takes its child attachments and notes along, as in
Zotero; `children` in the output says how many.

stdout: one JSON line per item, then {"summary": {total, ok, skipped, failed}}.
Each line: {key, code, itemType, title, parent, parent_title?, children?,
cite?, version?, hint?}. Diagnostics go to stderr; the API key is never
printed.

Codes (exit):
  ok                 0  moved to the trash (--restore: restored) and read back so
  already_trashed    0  skipped: the item is in the trash already
  not_in_trash       0  skipped (--restore): the item is not in the trash
  not_found          1  no item with that key
  cite_not_found     1  no top-level item carries the --cite citationKey
  cite_ambiguous     1  several items carry it; `keys` lists them, pass --key
  version_conflict   1  the item changed twice while writing; wait, then re-run
  write_denied       1  the library is not editable
  patch_failed       1  the local API rejected the write; see body
  readback_mismatch  1  the PATCH was accepted but the item still shows its old state
  not_run            2  Zotero stopped answering before this item (see summary.stopped)
Exit 0 = every item ok or skipped, 1 = some item failed, 2 = cannot check
(zotero_unreachable, local_api_disabled, no_key, key_rejected,
server_mismatch); before any item is touched these print one JSON object.

Examples:
  uv run scripts/trash_item.py --key ABCD1234 EFGH5678 --dry-run   # show the list to the user first
  uv run scripts/trash_item.py --key ABCD1234 EFGH5678             # after the user confirmed it
  uv run scripts/trash_item.py --cite liu2022progressive --dry-run
  uv run scripts/trash_item.py --key ABCD1234 --restore            # undo
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
KEY_RE = re.compile(r"^[A-Z0-9]{8}$")


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


def get_item(api, key):
    status, _, body = api.request("GET", f"{LIB}/items/{key}")
    check_common(status, body)
    if status == 404:
        return None
    if status != 200:
        raise Stop("unexpected_response", 1, "Unexpected local API reply; see status and body.", item_key=key, status=status, body=text(body))
    item = json.loads(body)
    return item if isinstance(item, dict) and item.get("key") == key else None


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


def resolve_cites(api, cites):
    """{cite: [item keys]} — a q=everything search per citationKey (verified to hit on the local API, 2026-09-23),
    then one paged scan of /items/top (the fallback) for those the search missed."""
    hits = {}
    for cite in cites:
        query = urllib.parse.urlencode({"q": cite, "qmode": "everything", "limit": 50})
        hits[cite] = [r["key"] for r in get_list(api, f"{LIB}/items?{query}")
                      if is_top(r) and (r.get("data") or {}).get("citationKey") == cite]
    missing = [c for c in cites if not hits[c]]
    if missing:
        log(f"no search hit for citationKey {', '.join(map(repr, missing))}; scanning /items/top (fallback)")
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


def is_trashed(item):
    # The local API sends `deleted: true` on a trashed item; after a restore the property may be absent.
    return bool((item.get("data") or {}).get("deleted"))


def describe(api, item, parent_titles):
    """{key, itemType, title, parent, parent_title?, children?} for the list the user confirms."""
    data = item.get("data") or {}
    out = {"key": item["key"], "itemType": data.get("itemType"), "title": data.get("title") or (data.get("note") or "")[:80],
           "parent": data.get("parentItem") or None}
    if out["parent"]:
        if out["parent"] not in parent_titles:
            parent = get_item(api, out["parent"])
            parent_titles[out["parent"]] = ((parent or {}).get("data") or {}).get("title")
        out["parent_title"] = parent_titles[out["parent"]]
    else:
        children = (item.get("meta") or {}).get("numChildren")
        if isinstance(children, int):
            out["children"] = children
    return out


def process(api, key, want, args, api_key, server_id, parent_titles):
    """Trash (want=True) or restore (want=False) one item -> (summary line, outcome ok|skipped|failed)."""
    item = get_item(api, key)
    if item is None:
        return {"key": key, "code": "not_found", "hint": "No item with that key; check it with find_in_library.py --key."}, "failed"
    line = describe(api, item, parent_titles)
    line["version"] = item.get("version")
    settled = "already_trashed" if want else "not_in_trash"
    if is_trashed(item) == want:
        return {**line, "code": settled}, "skipped"
    if args.dry_run:
        return {**line, "code": "ok", "dry_run": True}, "ok"

    retried = False
    for attempt in (1, 2):
        status, _, body = api.request("PATCH", f"{LIB}/items/{key}", {"deleted": 1 if want else 0},
                                      write_headers(api_key, server_id, item.get("version")))
        check_common(status, body)
        if status == 204:
            break
        if status == 412 and attempt == 1:
            log(f"{key}: 412 on PATCH ({text(body, 120)}); re-reading the item and retrying once")
            retried = True
            item = get_item(api, key)
            if item is None:
                return {**line, "code": "not_found", "hint": "The item disappeared while writing."}, "failed"
            if is_trashed(item) == want:
                return {**line, "code": settled, "version": item.get("version"), "retried": True}, "skipped"
            continue
        if status == 412:
            return {**line, "code": "version_conflict", "status": status, "body": text(body),
                    "hint": "The item keeps changing under us (Zotero sync or the user editing); wait, then re-run."}, "failed"
        if status == 403:
            return {**line, "code": "write_denied", "status": status, "body": text(body),
                    "hint": "This library is not editable."}, "failed"
        return {**line, "code": "patch_failed", "status": status, "body": text(body),
                "hint": "The local API rejected the write; see body."}, "failed"

    after = get_item(api, key)
    if after is None or is_trashed(after) != want:
        return {**line, "code": "readback_mismatch", "retried": retried,
                "hint": "The PATCH returned 204 but the item does not show the new state; look at it in Zotero."}, "failed"
    return {**line, "code": "ok", "version": after.get("version"), "retried": retried}, "ok"


def split_values(values):
    """--key / --cite values: repeatable, several after one flag, or comma-separated."""
    out = []
    for v in values or []:
        out += [x.strip() for x in v.split(",") if x.strip()]
    return out


def parse_args():
    p = argparse.ArgumentParser(
        description="Move Zotero items or attachments to the trash (undoable for 30 days) or restore them, via the local write API. "
                    "Only after the user has confirmed the list: run --dry-run first and show it. "
                    "Nothing here empties the trash or deletes permanently.",
        epilog="Codes: ok | already_trashed | not_in_trash (skipped) | not_found | cite_not_found | cite_ambiguous | "
               "version_conflict | write_denied | patch_failed | readback_mismatch. Exit 0 = every item ok or skipped; "
               "1 = some item not done, see its code/hint; 2 = cannot check (zotero_unreachable, local_api_disabled, "
               "no_key, key_rejected, server_mismatch). stdout: one JSON line per item, then {\"summary\": ...}.")
    p.add_argument("--key", metavar="ITEMKEY", nargs="+", action="extend",
                   help="item key(s) to trash: top-level items or child attachments / notes (repeatable, or comma-separated)")
    p.add_argument("--cite", metavar="CITEKEY", nargs="+", action="extend",
                   help="citationKey(s) of top-level items, each resolved to the one item carrying it")
    p.add_argument("--restore", action="store_true", help="take the items out of the trash instead")
    p.add_argument("--dry-run", action="store_true",
                   help="list {key, itemType, title, parent, parent_title, children} and what would happen; write nothing")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    args = p.parse_args()
    args.key, args.cite = split_values(args.key), split_values(args.cite)
    if not args.key and not args.cite:
        p.error("name the items with --key and/or --cite")
    bad = [k for k in args.key if not KEY_RE.match(k)]
    if bad:
        p.error(f"--key takes 8-character item keys: {', '.join(bad)}")
    return args


def main():
    args = parse_args()
    api = Api(args.base_url)
    server_id = live_server_id(api)
    api_key = load_key(server_id)
    want = not args.restore

    # Work list in the order given: --key values, then --cite values; a key named twice (also via a cite) is handled once.
    cites = list(dict.fromkeys(args.cite))
    hits = resolve_cites(api, cites) if cites else {}
    todo, seen = [], set()
    for key, cite in [(k, None) for k in args.key] + [(None, c) for c in cites]:
        if cite is not None:
            keys = hits[cite]
            if not keys:
                todo.append({"cite": cite, "line": {"cite": cite, "code": "cite_not_found", "hint":
                             "No item carries this citationKey; check it with read_library.py items --q, or pass --key."}})
                continue
            if len(keys) > 1:
                todo.append({"cite": cite, "line": {"cite": cite, "code": "cite_ambiguous", "keys": keys,
                                                    "hint": "Several items carry this citationKey; pass --key for the one you mean."}})
                continue
            key = keys[0]
        if key in seen:
            log(f"{key} is named more than once; handled once")
            continue
        seen.add(key)
        todo.append({"key": key, "cite": cite})

    lines, outcomes, stopped, parent_titles = [], [], None, {}
    for entry in todo:
        if "line" in entry:  # an unresolved --cite
            line, outcome = entry["line"], "failed"
        elif stopped is not None:
            line, outcome = {"key": entry["key"], "code": "not_run"}, "failed"
        else:
            try:
                line, outcome = process(api, entry["key"], want, args, api_key, server_id, parent_titles)
            except Stop as stop:
                if stop.exit_code == 2:  # Zotero is gone or refuses us: nothing more can be written
                    stopped = stop
                    line = {"key": entry["key"], "code": "not_run"}
                else:
                    line = {"key": entry["key"], "code": stop.code, **stop.extra, **({"hint": stop.hint} if stop.hint else {})}
                outcome = "failed"
        if entry.get("cite") and "key" in line:
            line = {"key": line.pop("key"), "cite": entry["cite"], **line}
        lines.append(line)
        outcomes.append(outcome)

    counts = {"total": len(lines), "ok": outcomes.count("ok"), "skipped": outcomes.count("skipped"),
              "failed": outcomes.count("failed")}
    if args.dry_run:
        counts["dry_run"] = True
    if stopped is not None:
        counts["stopped"] = stopped.code
        log(f"stopped early: {stopped.code} - {stopped.hint}")
    for line in lines:
        print(json.dumps(line, ensure_ascii=False))
    print(json.dumps({"summary": counts}, ensure_ascii=False))
    if stopped is not None:
        sys.exit(2)
    sys.exit(1 if counts["failed"] else 0)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
