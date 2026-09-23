# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Create a Zotero collection by name under an optional parent, idempotently, through the local write API.

List the collections (paged, trashed ones skipped) -> look for the same name
under the same parent (top level when --parent is absent) -> `exists` with its
key when there is exactly one, `ambiguous` when there are several,
`parent_not_found` when --parent names no live collection -> otherwise POST
[{name, parentCollection}] and read the new collection back. Re-running gives
`exists`, so the script never creates a second copy.

stdout: exactly one JSON object {code, key, name, parent, path} with a stable
`code`; `path` is the names from the root joined by "/". Diagnostics go to
stderr. Exit 0 = done (ok / exists), 1 = not done (ambiguous,
parent_not_found, create_failed, verify_failed), 2 = cannot check (Zotero
unreachable, local API disabled, no key, key rejected, key belongs to another
Zotero instance).

Examples:
  uv run scripts/make_collection.py --name "Mean Flow" --parent SV9NEBPJ --dry-run
  uv run scripts/make_collection.py --name "投稿文献"
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
DEFAULT_KEY_FILE = "~/.config/zotero/local-api-key"
LIB = "/api/users/0"
PAGE = 100
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


def load_key(key_file, server_id):
    """Return the API key; ZOTERO_LOCAL_API_KEY overrides the key file. Never printed."""
    env = os.environ.get("ZOTERO_LOCAL_API_KEY")
    if env:
        return env.strip()
    path = Path(key_file).expanduser()
    if not path.is_file():
        raise Stop("no_key", 2, "No local API key yet; run ready.py --authorize first (or set ZOTERO_LOCAL_API_KEY).",
                   key_file=str(path))
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        key = info["key"]
    except (ValueError, KeyError, TypeError) as e:
        raise Stop("no_key", 2, "The key file is unreadable; run ready.py --authorize again.",
                   key_file=str(path), error=str(e))
    saved = info.get("serverID")
    if saved and saved != server_id:
        raise Stop("server_mismatch", 2, "The saved key was issued by another Zotero instance; run ready.py --authorize again.",
                   key_file=str(path))
    return key


def write_headers(key, server_id, version=None):
    h = {"Zotero-API-Key": key, "Zotero-Server-ID": server_id}
    if version is not None:
        h["If-Unmodified-Since-Version"] = str(version)
    return h


def get_json(api, path):
    status, _, body = api.request("GET", path)
    check_common(status, body)
    if status == 404:
        return None
    if status != 200:
        raise Stop("unexpected_response", 1, "Unexpected local API reply; see status and body.", path=path, status=status, body=text(body))
    try:
        return json.loads(body)
    except ValueError:
        raise Stop("unexpected_response", 1, "The local API did not return JSON.", path=path, body=text(body))


def list_collections(api):
    """All live collections as {key: {"name", "parent"}}; parent is None at the top level. Paged; trashed ones skipped."""
    cols, start = {}, 0
    while True:
        rows = get_json(api, f"{LIB}/collections?limit={PAGE}&start={start}")
        if not isinstance(rows, list):
            raise Stop("unexpected_response", 1, "The collection listing is not a JSON list.", start=start)
        for row in rows:
            data = row.get("data") or {}
            if data.get("deleted"):
                continue
            cols[row.get("key")] = {"name": data.get("name") or "", "parent": data.get("parentCollection") or None}
        if len(rows) < PAGE:
            return cols
        start += PAGE


def path_of(cols, key, name=None):
    """Names from the root down to `key` (or to a new child `name` of `key`), joined by '/'."""
    parts, seen = [], set()
    while key and key in cols and key not in seen:
        seen.add(key)
        parts.append(cols[key]["name"])
        key = cols[key]["parent"]
    parts.reverse()
    if name is not None:
        parts.append(name)
    return "/".join(parts)


def run(api, args, api_key, server_id):
    name = args.name.strip()
    if not name:
        raise Stop("invalid_name", 1, "--name must not be empty.")
    parent = args.parent
    cols = list_collections(api)
    if parent and parent not in cols:
        raise Stop("parent_not_found", 1, "No live collection has this key (it may be in the trash); pick the key from ready.py's tree.",
                   name=name, parent=parent)
    same = [k for k, c in cols.items() if c["name"] == name and c["parent"] == parent]
    if len(same) == 1:
        emit("exists", 0, key=same[0], name=name, parent=parent, path=path_of(cols, same[0]))
    if len(same) > 1:
        raise Stop("ambiguous", 1, "Several collections with this name sit under the same parent; the user decides which stays.",
                   keys=sorted(same), name=name, parent=parent, path=path_of(cols, parent, name))
    path = path_of(cols, parent, name)
    if args.dry_run:
        emit("ok", 0, dry_run=True, key=None, name=name, parent=parent, path=path)

    status, _, body = api.request("POST", f"{LIB}/collections", [{"name": name, "parentCollection": parent or False}],
                                  write_headers(api_key, server_id))
    check_common(status, body)
    if status == 403:
        raise Stop("write_denied", 1, "This library is not editable.", status=status, body=text(body))
    if status != 200:
        raise Stop("create_failed", 1, "The local API rejected the collection; see body.", status=status, body=text(body), name=name, parent=parent)
    try:
        resp = json.loads(body)
        ok = (resp.get("successful") or {}).get("0")
    except (ValueError, AttributeError):
        raise Stop("create_failed", 1, "The POST reply is not the expected JSON.", body=text(body))
    if not ok:
        failed = (resp.get("failed") or {}).get("0") or {}
        raise Stop("create_failed", 1, "Zotero reported the collection as failed; nothing was created.",
                   status=failed.get("code"), message=failed.get("message"), name=name, parent=parent)
    key = ok.get("key")
    back = get_json(api, f"{LIB}/collections/{key}")
    data = (back or {}).get("data") or {}
    if back is None or data.get("name") != name or (data.get("parentCollection") or None) != parent:
        raise Stop("verify_failed", 1, "The collection was created but reads back differently; inspect it in Zotero.",
                   key=key, name=name, parent=parent, read_back=data)
    emit("ok", 0, key=key, name=name, parent=parent, path=path, version=back.get("version"))


def parse_args():
    p = argparse.ArgumentParser(
        description="Create a Zotero collection by name under an optional parent, idempotently, via the local write API.",
        epilog="Exit 0 = done (ok / exists); 1 = not done (ambiguous, parent_not_found, create_failed); "
               "2 = cannot check (zotero_unreachable, local_api_disabled, no_key, key_rejected, server_mismatch). "
               "Output is one JSON object {code, key, name, parent, path} on stdout.")
    p.add_argument("--name", required=True, metavar="NAME", help="the collection's name (exact match decides `exists`)")
    p.add_argument("--parent", metavar="COLLKEY", help="key of the parent collection; omitted = top level")
    p.add_argument("--dry-run", action="store_true", help="check for an existing collection and the parent; create nothing")
    p.add_argument("--key-file", default=DEFAULT_KEY_FILE, metavar="PATH",
                   help="JSON file holding the local API key (default: %(default)s); env ZOTERO_LOCAL_API_KEY overrides")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    args = p.parse_args()
    if args.parent is not None and not KEY_RE.match(args.parent):
        p.error("--parent is an 8-character collection key")
    return args


def main():
    args = parse_args()
    api = Api(args.base_url)
    server_id = live_server_id(api)
    api_key = load_key(args.key_file, server_id)
    run(api, args, api_key, server_id)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
