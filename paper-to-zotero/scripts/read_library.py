# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read the Zotero library through the local API and print it as JSONL: items, one item, its children, collections, tags, the schema.

Read-only and unauthenticated (the local API answers GETs without a key).
Every stdout line is one JSON object:

- items / item / children: the API object's `data` with `key` and `version`
  in front; `items` lists top-level items (add --all for attachments and
  notes), optionally within one collection, by key or citation key, by
  search text or changed since a library version.
- collections: the collection's data; --tree adds `path` (names joined by
  "/", parents first) and leaves collections in the trash out.
- tags: {tag, type, count}.
- schema: the schema object, once.

Multi-object endpoints are paged (limit 100, `start`), honouring
Total-Results / Link; --limit caps the total. --cite resolves a citation
key the way every script of this skill does: a q=everything search first,
then a scan of the top-level items as fallback. Exit 0; 1 = a key or
citation key did not resolve; 2 = cannot read (Zotero unreachable, local
API disabled, unexpected reply) - then stdout holds one {"code", ...} object.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
LIB = "/api/users/0"
PAGE_SIZE = 100
KEY_CHUNK = 50
TIMEOUT = 30
CHILD_TYPES = {"attachment", "note", "annotation"}

VERBOSE = False


def log(msg: str) -> None:
    if VERBOSE:
        print(msg, file=sys.stderr)


class Stop(Exception):
    """Carry a result code out of any depth; main() turns it into one JSON line + exit."""

    def __init__(self, code: str, exit_code: int = 1, hint: str | None = None, **extra):
        super().__init__(code)
        self.code, self.exit_code, self.hint, self.extra = code, exit_code, hint, extra


class Api:
    """Minimal GET client for the local API; bypasses any proxy from the environment."""

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(self, path: str, params: dict | None = None, allow_404: bool = False):
        """Return (object, headers); (None, headers) on 404 when allowed."""
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=TIMEOUT) as resp:
                status, headers, body = resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            status, headers, body = e.code, dict(e.headers), e.read()
        except (urllib.error.URLError, OSError) as e:
            raise Stop("zotero_unreachable", 2, "Zotero does not answer; ask the user to start it (never restart it from here), then rerun.",
                       base_url=self.base, error=str(getattr(e, "reason", e))) from None
        log(f"GET {url} -> {status}")
        text = body.decode("utf-8", errors="replace")
        if status == 403:
            raise Stop("local_api_disabled", 2, "Ask the user to enable the local API in Zotero Settings > Advanced, then rerun.",
                       status=status, body=text.strip()[:200])
        if status == 404 and allow_404:
            return None, headers
        if status != 200:
            raise Stop("api_error", 2, "Unexpected reply from the local API; check Zotero and rerun.",
                       path=path, status=status, body=text.strip()[:200])
        try:
            return json.loads(text), headers
        except json.JSONDecodeError:
            raise Stop("api_error", 2, "The local API did not answer with JSON.", path=path, body=text.strip()[:200]) from None

    def get_all(self, path: str, params: dict | None = None, limit: int | None = None) -> list:
        """Page through a multi-object endpoint; stop on Total-Results, a missing rel=next or a short page."""
        out: list = []
        start = 0
        while limit is None or len(out) < limit:
            page_size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - len(out))
            page, headers = self.get(path, {**(params or {}), "limit": page_size, "start": start})
            if not isinstance(page, list):
                raise Stop("api_error", 2, "Expected a JSON array from the local API.", path=path)
            out.extend(page)
            start += len(page)
            total = headers.get("Total-Results")
            if not page or len(page) < page_size:
                break
            if total is not None and total.isdigit():
                if start >= int(total):
                    break
            elif 'rel="next"' not in (headers.get("Link") or ""):
                break
        return out if limit is None else out[:limit]


def is_top_level(item: dict) -> bool:
    data = item.get("data") or {}
    return data.get("itemType") not in CHILD_TYPES and not data.get("parentItem")


def resolve_cite(api: Api, cite: str) -> str:
    """Citation key -> item key: a q=everything search, then (fallback) a scan of every top-level item."""
    hits, _ = api.get(f"{LIB}/items", {"q": cite, "qmode": "everything", "limit": 50})
    keys = [it["key"] for it in hits if is_top_level(it) and (it.get("data") or {}).get("citationKey") == cite]
    if not keys:
        log(f"citation key {cite!r}: search found nothing, scanning {LIB}/items/top")
        keys = [it["key"] for it in api.get_all(f"{LIB}/items/top") if (it.get("data") or {}).get("citationKey") == cite]
    if not keys:
        raise Stop("cite_not_found", 1, "No item carries this citationKey (case matters); look the paper up by DOI or title instead.", cite=cite)
    if len(keys) > 1:
        raise Stop("cite_ambiguous", 1, "Several items carry this citationKey; pass --key with the right one.", cite=cite, keys=keys)
    return keys[0]


def line(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def flat(item: dict) -> dict:
    """The API object's data with key and version in front."""
    return {"key": item.get("key"), "version": item.get("version"), **(item.get("data") or {})}


# --- subcommands -------------------------------------------------------------


def cmd_items(api: Api, args) -> int:
    keys = list(args.key or [])
    for cite in args.cite or []:
        keys.append(resolve_cite(api, cite))
    params: dict = {}
    if args.q:
        params["q"] = args.q
        if args.qmode:
            params["qmode"] = args.qmode
    if args.since is not None:
        params["since"] = args.since
    base = f"{LIB}/collections/{args.collection}/items" if args.collection else f"{LIB}/items"
    if keys:
        # Explicit keys are wanted whatever their level, so no /top here; the local API also returns the
        # children of a requested key, hence the filter.
        items: list = []
        for i in range(0, len(keys), KEY_CHUNK):
            chunk = keys[i:i + KEY_CHUNK]
            items.extend(it for it in api.get_all(base, {**params, "itemKey": ",".join(chunk)}) if it.get("key") in chunk)
        missing = [k for k in keys if k not in {it.get("key") for it in items}]
        if missing:
            print(f"not in the library: {', '.join(missing)}", file=sys.stderr)
    else:
        items = api.get_all(base if args.all else base + "/top", params, limit=args.limit)
    if args.limit is not None:
        items = items[:args.limit]
    for it in items:
        line(flat(it))
    return 0


def cmd_item(api: Api, args) -> int:
    item, _ = api.get(f"{LIB}/items/{args.key}", allow_404=True)
    if not isinstance(item, dict):
        raise Stop("not_found", 1, "No item with that key; find it with `items --q` or --cite.", key=args.key)
    line(flat(item))
    return 0


def cmd_children(api: Api, args) -> int:
    # The local API answers /items/<missing>/children with the whole library; keep only real children.
    children = api.get_all(f"{LIB}/items/{args.key}/children")
    for child in children:
        if (child.get("data") or {}).get("parentItem") == args.key:
            line(flat(child))
    return 0


def cmd_collections(api: Api, args) -> int:
    cols = api.get_all(f"{LIB}/collections")
    if not args.tree:
        for c in cols:
            line(flat(c))
        return 0
    live = {c["key"]: c for c in cols if not (c.get("data") or {}).get("deleted")}
    children: dict = {}
    for key, c in live.items():
        parent = (c.get("data") or {}).get("parentCollection") or None
        if parent and parent not in live:
            log(f"collection {key} skipped: its parent {parent} is in the trash or missing")
            continue
        children.setdefault(parent, []).append(key)

    def walk(parent, prefix: str) -> None:
        for key in sorted(children.get(parent, []), key=lambda k: (live[k]["data"].get("name") or "").casefold()):
            path = f"{prefix}/{live[key]['data'].get('name', key)}" if prefix else live[key]["data"].get("name", key)
            line({**flat(live[key]), "path": path})
            walk(key, path)

    walk(None, "")
    return 0


def cmd_tags(api: Api, args) -> int:
    for t in api.get_all(f"{LIB}/tags"):
        meta = t.get("meta") or {}
        count = meta.get("numItems", 0)
        if count >= args.min_count:
            line({"tag": t.get("tag"), "type": meta.get("type", 0), "count": count})
    return 0


def cmd_schema(api: Api, args) -> int:
    schema, _ = api.get("/api/schema")
    line(schema)
    return 0


# --- main --------------------------------------------------------------------


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Read the Zotero library through the local API (GET only, no key) and print JSONL.",
        epilog="Examples:\n"
               "  uv run read_library.py items --collection 9EYXTC2I --limit 20\n"
               "  uv run read_library.py items --cite liuProgressiveResidualLearning2022\n"
               "  uv run read_library.py items --q 'residual learning' --qmode everything\n"
               "  uv run read_library.py collections --tree\n"
               "  uv run read_library.py tags --min-count 3\n"
               "Exit 0; 1 = not_found / cite_not_found / cite_ambiguous; 2 = zotero_unreachable / local_api_disabled / api_error.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s; proxies are bypassed)")
    p.add_argument("-v", "--verbose", action="store_true", help="log each request to stderr")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    s = sub.add_parser("items", help="list items (top-level by default)")
    s.add_argument("--top", action="store_true", help="top-level items only (the default)")
    s.add_argument("--all", action="store_true", help="also attachments and notes")
    s.add_argument("--collection", metavar="KEY", help="only items in this collection")
    s.add_argument("--key", action="append", metavar="KEY", help="one item key (repeatable)")
    s.add_argument("--cite", action="append", metavar="CITE", help="one citation key (repeatable)")
    s.add_argument("--q", metavar="TEXT", help="search text (Zotero quick search)")
    s.add_argument("--qmode", choices=("titleCreatorYear", "everything", "fields"), help="quick-search mode for --q (default: Zotero's)")
    s.add_argument("--since", type=int, metavar="VERSION", help="only items changed after this library version")
    s.add_argument("--limit", type=int, metavar="N", help="at most N items in total")
    s.set_defaults(func=cmd_items)

    s = sub.add_parser("item", help="one item by key")
    s.add_argument("key", metavar="KEY")
    s.set_defaults(func=cmd_item)

    s = sub.add_parser("children", help="the attachments and notes of one item")
    s.add_argument("key", metavar="KEY")
    s.set_defaults(func=cmd_children)

    s = sub.add_parser("collections", help="all collections")
    s.add_argument("--tree", action="store_true", help="parents first, with `path`; collections in the trash left out")
    s.set_defaults(func=cmd_collections)

    s = sub.add_parser("tags", help="all tags with their item counts")
    s.add_argument("--min-count", type=int, default=0, metavar="N", help="only tags on at least N items")
    s.set_defaults(func=cmd_tags)

    s = sub.add_parser("schema", help="the Zotero schema (item types, fields, CSL mappings)")
    s.set_defaults(func=cmd_schema)

    args = p.parse_args(argv)
    if args.command == "items":
        if args.top and args.all:
            p.error("--top and --all exclude each other")
        if args.limit is not None and args.limit < 1:
            p.error("--limit must be at least 1")
    return args


def main(argv=None) -> int:
    global VERBOSE
    args = parse_args(argv)
    VERBOSE = args.verbose
    try:
        return args.func(Api(args.base_url), args)
    except Stop as stop:
        out = {"code": stop.code, **stop.extra}
        if stop.hint:
            out["hint"] = stop.hint
        print(f"{stop.code}: {json.dumps(stop.extra, ensure_ascii=False)}", file=sys.stderr)
        line(out)
        return stop.exit_code


if __name__ == "__main__":
    sys.exit(main())
