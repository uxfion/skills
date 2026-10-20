#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Merge what one Zotero item holds into its duplicate, keeping one item whole; nothing is deleted.

--keep and --drop name the two items (an 8-character key or a citation key). The plan, shown by --dry-run and
carried out without it:
  fields        every field of the kept item's type (from /api/schema, matched across types by base field, so a
                journal's publicationTitle fills a conference paper's proceedingsTitle): a field the kept item
                leaves empty takes the dropped item's value (creators only when the kept item has none); `extra`
                takes the dropped item's lines it lacks; a field both fill differently is listed under `conflicts`
                and left as the kept item has it; a dropped value with no field in the kept type, `not_carried`
  collections   the union, without `tmp` (unless `tmp` is all there is)
  tags          the union
  attachments   the dropped item's PDFs whose md5 the kept item lacks, and its notes, move under the kept item
                (PATCH parentItem); its other attachments (snapshots, links, a PDF the kept item already has) stay
                and are listed under `left_with_drop`
The kept item is written in one PATCH with its version, each moved child in its own; then everything is read back.
The dropped item is left in place: the output ends with the trash_item.py line to run once the user confirms.

stdout: one JSON object {code, keep, drop, fields: {fill, conflicts, not_carried}, collections, tags, move,
left_with_drop, next, ...}. Codes: ok (exit 0; with --dry-run nothing written) | nothing_to_merge (0) |
not_found | cite_not_found | cite_ambiguous | same_item | not_top_level | trashed | version_conflict |
patch_failed | readback_mismatch (1) | zotero_unreachable | local_api_disabled | no_key | key_rejected |
server_mismatch | config_unreadable (2). The API key is never printed.

Examples:
  uv run scripts/merge_items.py --keep 9NB4JT94 --drop 3G7J5DN9 --dry-run   # show the plan to the user first
  uv run scripts/merge_items.py --keep goodfellow2014generative --drop 3G7J5DN9
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
NOT_FIELDS = {"key", "version", "itemType", "collections", "tags", "relations", "dateAdded", "dateModified",
              "deleted", "parentItem"}
SHOWN = 160  # characters of a long value shown in `conflicts`


class Stop(Exception):
    def __init__(self, code, exit_code=1, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit_code, self.hint, self.extra = code, exit_code, hint, extra


class Api:
    """Minimal client for the local API; bypasses any proxy from the environment."""

    def __init__(self, base_url, timeout=120):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, body=None, headers=None):
        h = {"Accept": "application/json", **(headers or {})}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise Stop("zotero_unreachable", 2, "Start Zotero, then retry; check --base-url if it is not the default.",
                       base_url=self.base, error=str(getattr(e, "reason", None) or e))


def text(body, limit=400):
    return body.decode("utf-8", errors="replace").strip()[:limit]


def check_common(status, body):
    msg = text(body)
    if status == 403 and "not enabled" in msg.lower():
        raise Stop("local_api_disabled", 2, "Ask the user to enable the local API in Zotero settings (Advanced).")
    if status == 401:
        raise Stop("key_rejected", 2, "The API key is not accepted by this Zotero; run ready.py --authorize again.")
    if status == 412 and "server-id" in msg.lower():
        raise Stop("server_mismatch", 2, "The key belongs to another Zotero instance; run ready.py --authorize again.")


def server_id_of(api):
    status, headers, body = api.request("GET", "/api/")
    check_common(status, body)
    if status != 200 or not headers.get("Zotero-Server-ID"):
        raise Stop("zotero_unreachable", 2, "The endpoint does not behave like Zotero's local API; check --base-url.")
    return headers["Zotero-Server-ID"]


def load_key(server_id):
    """The local API key from the config file's "zotero" block (ready.py --authorize writes it). Never printed."""
    path = Path(os.environ.get("PAPER_TO_ZOTERO_CONFIG") or Path.home() / ".config" / "paper-to-zotero" / "config.json")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        config = {}
    except (OSError, ValueError) as e:
        raise Stop("config_unreadable", 2, "The config file is unreadable; fix it, then retry.", error=str(e))
    zot = config.get("zotero") if isinstance(config, dict) and isinstance(config.get("zotero"), dict) else {}
    if not isinstance(zot.get("key"), str) or not zot["key"]:
        raise Stop("no_key", 2, "No local API key yet; run ready.py --authorize first.")
    if zot.get("serverID") and zot["serverID"] != server_id:
        raise Stop("server_mismatch", 2, "The key was issued by another Zotero instance; run ready.py --authorize again.")
    return zot["key"]


def get_json(api, path, allow_404=False):
    status, _, body = api.request("GET", path)
    check_common(status, body)
    if status == 404 and allow_404:
        return None
    if status != 200:
        raise Stop("api_error", 1, "Unexpected local API reply.", path=path, status=status, body=text(body))
    return json.loads(body)


def resolve(api, name):
    """An item key, or a citation key resolved to the one top-level item carrying it."""
    if KEY_RE.match(name):
        item = get_json(api, f"{LIB}/items/{name}", allow_404=True)
        if not item:
            raise Stop("not_found", 1, "No item with that key.", item=name)
        return item
    rows = get_json(api, f"{LIB}/items?" + urllib.parse.urlencode({"q": name, "qmode": "everything", "limit": 50}))
    hits = [r for r in rows if (r.get("data") or {}).get("citationKey") == name]
    if not hits:
        raise Stop("cite_not_found", 1, "No item carries this citation key; pass its item key.", cite=name)
    if len(hits) > 1:
        raise Stop("cite_ambiguous", 1, "Several items carry this citation key; pass the item key.", cite=name,
                   keys=[r["key"] for r in hits])
    return hits[0]


def empty(value):
    return value in (None, "", [], {})


def short(value):
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return s if len(s) <= SHOWN else s[:SHOWN] + "…"


def field_maps(schema):
    """{itemType: {field: base field or itself}} from /api/schema."""
    return {t["itemType"]: {f["field"]: f.get("baseField") or f["field"] for f in t.get("fields") or []}
            for t in schema.get("itemTypes") or []}


def plan_merge(keep, drop, keep_children, drop_children, tmp_keys, maps):
    k, d = keep["data"], drop["data"]
    keep_fields = maps.get(k.get("itemType")) or {f: f for f in k if f not in NOT_FIELDS}
    by_base = {}
    for field, base in (maps.get(d.get("itemType")) or {f: f for f in d if f not in NOT_FIELDS}).items():
        by_base[base] = field
    fill, conflicts, carried = {}, {}, set()
    for field, base in list(keep_fields.items()) + [("creators", "creators")]:
        source = by_base.get(base) or (field if field in d else None)
        if source is None or source not in d:
            continue
        carried.add(source)
        kv, dv = k.get(field), d[source]
        if field == "extra":
            have = [ln for ln in (kv or "").splitlines() if ln.strip()]
            add = [ln for ln in (dv or "").splitlines() if ln.strip() and ln not in have]
            if add:
                fill[field] = "\n".join(have + add)
        elif empty(kv) and not empty(dv):
            fill[field] = dv
        elif not empty(kv) and not empty(dv) and kv != dv:
            conflicts[field] = {"keep": short(kv), "drop": short(dv)}
    not_carried = sorted(f for f, v in d.items() if f not in NOT_FIELDS and f not in carried and not empty(v))
    union = list(dict.fromkeys((k.get("collections") or []) + (d.get("collections") or [])))
    collections = [c for c in union if c not in tmp_keys] or union
    tags, seen = list(k.get("tags") or []), {t.get("tag") for t in k.get("tags") or []}
    for t in d.get("tags") or []:
        if t.get("tag") not in seen:
            tags.append(t)
            seen.add(t.get("tag"))
    pdf = lambda c: c["data"].get("itemType") == "attachment" and c["data"].get("contentType") == "application/pdf"
    keep_md5 = {c["data"].get("md5") for c in keep_children if pdf(c)}
    move, left = [], []
    for c in drop_children:
        cd = c["data"]
        entry = {"key": c["key"], "itemType": cd.get("itemType"), "title": cd.get("title") or short(cd.get("note") or "")}
        if cd.get("itemType") == "note" or (pdf(c) and cd.get("md5") not in keep_md5):
            move.append(entry)
        else:
            left.append({**entry, "why": "the kept item has this PDF" if pdf(c) else "not a PDF or a note"})
    patch = dict(fill)
    if collections != (k.get("collections") or []):
        patch["collections"] = collections
    if len(tags) != len(k.get("tags") or []):
        patch["tags"] = tags
    return {"fields": {"fill": {f: short(v) for f, v in fill.items()}, "conflicts": conflicts, "not_carried": not_carried},
            "collections": {"before": k.get("collections") or [], "after": collections},
            "tags": {"added": [t.get("tag") for t in tags[len(k.get("tags") or []):]]},
            "move": move, "left_with_drop": left}, patch


def write(api, headers, key, version, body):
    status, _, resp = api.request("PATCH", f"{LIB}/items/{key}", body, {**headers, "If-Unmodified-Since-Version": str(version)})
    check_common(status, resp)
    if status == 412:
        raise Stop("version_conflict", 1, "The item changed while merging (Zotero sync or the user); re-run the dry run.",
                   item=key)
    if status != 204:
        raise Stop("patch_failed", 1, "The local API rejected the write; see body.", item=key, status=status, body=text(resp))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], epilog="\n".join(__doc__.splitlines()[2:]),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", required=True, metavar="KEY|CITEKEY", help="the item that stays and gains")
    ap.add_argument("--drop", required=True, metavar="KEY|CITEKEY", help="the duplicate whose information moves over")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; write nothing")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    args = ap.parse_args()
    api = Api(args.base_url)
    keep, drop = resolve(api, args.keep), resolve(api, args.drop)
    if keep["key"] == drop["key"]:
        raise Stop("same_item", 1, "--keep and --drop name the same item.", item=keep["key"])
    for item in (keep, drop):
        if item["data"].get("parentItem") or item["data"].get("itemType") in ("attachment", "note", "annotation"):
            raise Stop("not_top_level", 1, "Both must be top-level items.", item=item["key"])
        if item["data"].get("deleted"):
            raise Stop("trashed", 1, "That item is in the trash; restore it first or pick another.", item=item["key"])
    children = lambda key: [c for c in get_json(api, f"{LIB}/items/{key}/children") if not c["data"].get("deleted")]
    keep_children, drop_children = children(keep["key"]), children(drop["key"])
    collections, start = [], 0
    while True:
        page = get_json(api, f"{LIB}/collections?limit=100&start={start}")
        collections += page
        if len(page) < 100:
            break
        start += 100
    tmp_keys = {c["key"] for c in collections if (c.get("data") or {}).get("name") == "tmp"}
    plan, patch = plan_merge(keep, drop, keep_children, drop_children, tmp_keys, field_maps(get_json(api, "/api/schema")))
    head = {"keep": {"key": keep["key"], "title": keep["data"].get("title"), "citationKey": keep["data"].get("citationKey")},
            "drop": {"key": drop["key"], "title": drop["data"].get("title"), "citationKey": drop["data"].get("citationKey")}}
    nxt = f"uv run scripts/trash_item.py --key {drop['key']} --dry-run   # once the user confirms the drop"
    if not patch and not plan["move"]:
        print(json.dumps({"code": "nothing_to_merge", **head, **plan, "next": nxt}, ensure_ascii=False, indent=2))
        return 0
    if args.dry_run:
        print(json.dumps({"code": "ok", "dry_run": True, **head, **plan, "next": nxt}, ensure_ascii=False, indent=2))
        return 0
    server_id = server_id_of(api)
    headers = {"Zotero-API-Key": load_key(server_id), "Zotero-Server-ID": server_id}
    if patch:
        write(api, headers, keep["key"], keep["version"], patch)
    for c in plan["move"]:
        child = get_json(api, f"{LIB}/items/{c['key']}")
        write(api, headers, c["key"], child["version"], {"parentItem": keep["key"]})
    after = get_json(api, f"{LIB}/items/{keep['key']}")["data"]
    under = {c["key"] for c in children(keep["key"])}
    wrong = [f for f, v in patch.items() if f not in ("tags", "collections") and after.get(f) != v]
    if "collections" in patch and set(after.get("collections") or []) != set(patch["collections"]):
        wrong.append("collections")
    if "tags" in patch and {t.get("tag") for t in after.get("tags") or []} != {t.get("tag") for t in patch["tags"]}:
        wrong.append("tags")
    unmoved = [c["key"] for c in plan["move"] if c["key"] not in under]
    code = "readback_mismatch" if wrong or unmoved else "ok"
    print(json.dumps({"code": code, **head, **plan, "version": after.get("version"),
                      **({"wrong": wrong} if wrong else {}), **({"unmoved": unmoved} if unmoved else {}), "next": nxt},
                     ensure_ascii=False, indent=2))
    return 1 if code != "ok" else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Stop as stop:
        print(json.dumps({"code": stop.code, **stop.extra, **({"hint": stop.hint} if stop.hint else {})},
                         ensure_ascii=False, indent=2))
        sys.exit(stop.exit_code)
