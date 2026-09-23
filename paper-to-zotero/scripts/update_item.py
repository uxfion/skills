# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Change the fields of one existing Zotero item through the local write API.
The item is named by --key, or by --cite CITEKEY (resolved to the one item
carrying that citationKey; cite_not_found / cite_ambiguous otherwise).
GET the item -> merge --set / --patch into its data -> check the field names
against the item type's schema (a base name such as publicationTitle is mapped
to the type's own field, e.g. proceedingsTitle, as Zotero does) -> PATCH only
what differs, with If-Unmodified-Since-Version (one retry on 412) -> GET again
and report per field: applied (the read-back is what was sent) or normalized
(Zotero stored something else). On an item-type change Zotero keeps the fields
the new type has and moves the rest to Extra; the plan says which.
Tags and collections belong to file_and_tag.py, the trash to the user: both
are refused here.
stdout: exactly one JSON object with a stable `code` (`ok` on success);
diagnostics go to stderr. Exit 0 = done, 1 = not done (the agent decides),
2 = cannot check (Zotero unreachable, local API disabled, no key, key
rejected, key belongs to another Zotero instance).

Codes (exit):
  ok                  0  written and read back (see `normalized` for values Zotero changed), or nothing to change
  item_not_found      1  no item with that key
  cite_not_found      1  no item carries the --cite citationKey
  cite_ambiguous      1  several items carry it; `keys` lists them, pass --key
  refused_property    1  tags / collections / deleted / key / version / parentItem / dates / attachment internals
  invalid_item_type   1  --set itemType names no item type, or the item is a note / annotation
  invalid_field       1  not a field of the (new) item type and no base name maps to one; `valid_fields` lists them
  invalid_creators    1  creators is not a list of {creatorType, lastName[, firstName]} / {creatorType, name}
  invalid_patch_file  1  --patch is not a JSON object
  readback_mismatch   1  the PATCH was accepted but a field still shows its old value
  version_conflict    1  the item changed twice while writing; wait, then re-run
  write_denied        1  the library is not editable
  patch_failed        1  the local API rejected the patch; see body

Examples:
  uv run scripts/update_item.py --key ABCD1234 --set date=2023 --set DOI=10.1109/CVPR52729.2023.00194 --dry-run
  uv run scripts/update_item.py --key ABCD1234 --set itemType=conferencePaper \\
      --set "publicationTitle=2023 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)" --set pages=1952-1961
  uv run scripts/update_item.py --key ABCD1234 --patch fix.json      # {"creators": [...], "extra": "arXiv: 2205.07680"}
  uv run scripts/update_item.py --cite liu2022progressive --set citationKey=liu2022progressive
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
KEY_RE = re.compile(r"^[A-Z0-9]{8}$")
# JSON properties that are not fields to set here, and why.
REFUSED = {
    "key": "Zotero's own", "version": "Zotero's own", "dateAdded": "Zotero's own", "dateModified": "Zotero's own",
    "tags": "file_and_tag.py", "collections": "file_and_tag.py", "relations": "not supported here",
    "deleted": "the trash is the user's own act", "parentItem": "not supported here",
    "linkMode": "attachment internals", "contentType": "attachment internals", "charset": "attachment internals",
    "filename": "attachment internals", "md5": "attachment internals", "mtime": "attachment internals",
    "path": "attachment internals", "note": "notes are not edited here",
}


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


def resolve_cite(api, cite):
    """Item key for a citationKey: a q=everything search first (verified to hit on the local API, 2026-09-23),
    then a paged scan of /items/top as the fallback."""
    query = urllib.parse.urlencode({"q": cite, "qmode": "everything", "limit": 50})
    rows = get_list(api, f"{LIB}/items?{query}")
    hits = [r["key"] for r in rows if is_top(r) and (r.get("data") or {}).get("citationKey") == cite]
    if not hits:
        log(f"no search hit for citationKey {cite!r}; scanning /items/top (fallback)")
        start = 0
        while True:
            page = get_list(api, f"{LIB}/items/top?limit=100&start={start}")
            hits += [r["key"] for r in page if (r.get("data") or {}).get("citationKey") == cite]
            if len(page) < 100:
                break
            start += 100
    if not hits:
        raise Stop("cite_not_found", 1, "No item carries this citationKey; check it with read_library.py items --q, or pass --key.", cite=cite)
    if len(hits) > 1:
        raise Stop("cite_ambiguous", 1, "Several items carry this citationKey; pass --key for the one you mean.", cite=cite, keys=hits)
    log(f"citationKey {cite!r} -> item {hits[0]}")
    return hits[0]


def get_types(api):
    """Per item type: its fields, the base name -> own field map, and its creator types, from /api/schema."""
    status, _, body = api.request("GET", "/api/schema")
    check_common(status, body)
    if status != 200:
        raise Stop("unexpected_response", 1, "Could not read /api/schema.", status=status, body=text(body))
    types = {}
    for t in json.loads(body).get("itemTypes", []):
        fields, base_to_field = set(), {}
        for f in t.get("fields", []):
            fields.add(f["field"])
            if "baseField" in f:
                base_to_field[f["baseField"]] = f["field"]
        types[t["itemType"]] = {"fields": fields, "base_to_field": base_to_field,
                                "creator_types": {c["creatorType"] for c in t.get("creatorTypes", [])}}
    return types


def own_field(field, ts):
    """The type's own name for a field: itself, or the field its base name maps to; None when the type has neither."""
    if field in ts["fields"]:
        return field
    return ts["base_to_field"].get(field)


def parse_sets(args):
    """The --patch object, then --set FIELD=VALUE pairs (later wins), checked for refused names and value types."""
    sets = {}
    if args.patch:
        p = Path(args.patch).expanduser()
        if not p.is_file():
            raise Stop("invalid_patch_file", 1, "--patch names a JSON file holding an object of field: value.", patch_file=str(p))
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as e:
            raise Stop("invalid_patch_file", 1, "The patch file is not valid JSON.", patch_file=str(p), error=str(e))
        if not isinstance(raw, dict) or not raw:
            raise Stop("invalid_patch_file", 1, "The patch file is a non-empty JSON object of field: value.", patch_file=str(p))
        sets.update(raw)
    for s in args.set or []:
        field, sep, value = s.partition("=")
        if not sep or not field.strip():
            raise Stop("invalid_field", 1, "--set takes FIELD=VALUE; an empty VALUE clears the field.", argument=s)
        sets[field.strip()] = value
    for field, value in list(sets.items()):
        if field in REFUSED:
            raise Stop("refused_property", 1, f"'{field}' is not set here: {REFUSED[field]}.", field=field)
        if field == "creators":
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            sets[field] = str(value)
        elif not isinstance(value, str):
            raise Stop("invalid_field", 1, "Field values are strings (creators is a list).", field=field, value=value)
    return sets


def check_creators(creators, ts):
    hint = ("creators is a list of {\"creatorType\", \"lastName\"[, \"firstName\"]} or {\"creatorType\", \"name\"}; "
            "the creatorType must be one the item type allows.")
    if not isinstance(creators, list):
        raise Stop("invalid_creators", 1, hint, creators=creators)
    out = []
    for i, c in enumerate(creators):
        if not isinstance(c, dict) or c.get("creatorType") not in ts["creator_types"]:
            raise Stop("invalid_creators", 1, hint, index=i, creator=c, creator_types=sorted(ts["creator_types"]))
        names = set(c) - {"creatorType"}
        if names != {"name"} and not (names <= {"firstName", "lastName"} and "lastName" in names):
            raise Stop("invalid_creators", 1, hint, index=i, creator=c)
        out.append({k: str(v).strip() for k, v in c.items()})
    return out


def plan(item, sets, types):
    """Diff the requested values against the item; returns (patch, changes, mapped_fields, fields_to_extra)."""
    data = item.get("data") or {}
    cur_type = data.get("itemType")
    if cur_type in ("note", "annotation") or cur_type not in types:
        raise Stop("invalid_item_type", 1, "This script edits regular items and attachment titles; notes and annotations are left alone.",
                   item_key=item.get("key"), item_type=cur_type)
    new_type = sets.get("itemType", cur_type)
    if new_type not in types:
        raise Stop("invalid_item_type", 1, "No such item type; see /api/itemTypes.", item_type=new_type, item_types=sorted(types))
    if new_type != cur_type and (cur_type == "attachment" or new_type in ("attachment", "note", "annotation")):
        raise Stop("invalid_item_type", 1, "An attachment stays an attachment; a regular item does not become an attachment or a note.",
                   from_type=cur_type, to_type=new_type)
    ts = types[new_type]
    patch, changes, mapped, invalid = {}, {}, {}, []
    if new_type != cur_type:
        patch["itemType"] = new_type
        changes["itemType"] = {"from": cur_type, "to": new_type}
    for field, value in sets.items():
        if field == "itemType":
            continue
        if field == "creators":
            value = check_creators(value, ts)
            before = data.get("creators") or []
            if value != before:
                patch["creators"], changes["creators"] = value, {"from": before, "to": value}
            continue
        own = own_field(field, ts)
        if own is None:
            invalid.append(field)
            continue
        if own != field:
            mapped[field] = own
        value = value.strip()
        before = data.get(own, "")
        if value != before:
            patch[own], changes[own] = value, {"from": before, "to": value}
    if invalid:
        raise Stop("invalid_field", 1, f"Not fields of {new_type}, nor base names it maps: use one of valid_fields, or put the value in extra.",
                   invalid_fields=invalid, valid_fields=sorted(ts["fields"] | set(ts["base_to_field"])))
    # On a type change Zotero keeps a field the new type also has (by its name or base name) and moves the rest to Extra.
    to_extra = {}
    if new_type != cur_type:
        for f, v in data.items():
            if f in types[cur_type]["fields"] and v and f not in patch and own_field(f, ts) is None:
                to_extra[f] = v
    return patch, changes, mapped, to_extra


def run(api, args, api_key, server_id):
    sets = parse_sets(args)
    types = get_types(api)
    item = get_item(api, args.key)
    if item is None:
        raise Stop("item_not_found", 1, "No item with that key; check the key from find_in_library.py.", item_key=args.key)
    patch, changes, mapped, to_extra = plan(item, sets, types)
    if not patch:
        emit("ok", 0, item_key=args.key, unchanged=True, version=item.get("version"))
    if args.dry_run:
        emit("ok", 0, dry_run=True, item_key=args.key, unchanged=False, changes=changes, mapped_fields=mapped,
             fields_to_extra=to_extra, version=item.get("version"))

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
            patch, changes, mapped, to_extra = plan(item, sets, types)
            if not patch:
                emit("ok", 0, item_key=args.key, unchanged=True, retried=True, version=item.get("version"))
            continue
        if status == 412:
            raise Stop("version_conflict", 1, "The item keeps changing under us (Zotero sync or the user editing); wait, then re-run.",
                       item_key=args.key, status=status, body=text(body))
        if status == 403:
            raise Stop("write_denied", 1, "This library is not editable.", item_key=args.key, status=status, body=text(body))
        raise Stop("patch_failed", 1, "The local API rejected the patch; see body.", item_key=args.key, status=status,
                   body=text(body), patch=patch)

    after = get_item(api, args.key)
    if after is None:
        raise Stop("item_not_found", 1, "The item disappeared after patching.", item_key=args.key)
    before_data, after_data = item.get("data") or {}, after.get("data") or {}
    applied, normalized, mismatch = [], {}, {}
    for f, sent in patch.items():
        now = after_data.get(f, [] if f == "creators" else "")
        if now == sent:
            applied.append(f)
        elif now == changes[f]["from"]:
            mismatch[f] = {"sent": sent, "now": now}
        else:
            normalized[f] = {"sent": sent, "now": now}
    result = {"item_key": args.key, "unchanged": False, "changes": changes, "mapped_fields": mapped, "fields_to_extra": to_extra,
              "applied": applied, "normalized": normalized, "version_before": item.get("version"), "version_after": after.get("version"),
              "retried": retried}
    if "extra" not in patch and (after_data.get("extra") or "") != (before_data.get("extra") or ""):
        result["extra"] = {"from": before_data.get("extra") or "", "to": after_data.get("extra") or ""}
    if mismatch:
        raise Stop("readback_mismatch", 1, "The PATCH returned 204 but these fields still show their old value; inspect the item in Zotero.",
                   mismatch=mismatch, **result)
    emit("ok", 0, **result)


def parse_args():
    p = argparse.ArgumentParser(
        description="Change fields of one existing Zotero item via the local write API.",
        epilog="Only differing fields are written; re-runs are no-ops. Exit 0 = done; 1 = not done, see code/hint; "
               "2 = cannot check (zotero_unreachable, local_api_disabled, no_key, key_rejected, server_mismatch). "
               "Output is one JSON object on stdout.")
    who = p.add_mutually_exclusive_group(required=True)
    who.add_argument("--key", metavar="ITEMKEY", help="key of the item to change")
    who.add_argument("--cite", metavar="CITEKEY", help="the item's citationKey instead of its key "
                                                       "(cite_not_found / cite_ambiguous when it does not name exactly one item)")
    p.add_argument("--set", action="append", metavar="FIELD=VALUE",
                   help="a field to set (repeatable); an empty VALUE clears it; FIELD may be itemType; "
                        "a base name such as publicationTitle is mapped to the type's own field")
    p.add_argument("--patch", metavar="FIELDS.json",
                   help="a JSON object of field: value to set — for creators (a list) and multi-line values such as extra")
    p.add_argument("--dry-run", action="store_true", help="print the changes (per field: from, to), the base-name mappings "
                                                          "and the fields a type change moves to Extra; write nothing")
    p.add_argument("--key-file", default=DEFAULT_KEY_FILE, metavar="PATH",
                   help="JSON file holding the local API key (default: %(default)s); env ZOTERO_LOCAL_API_KEY overrides")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    args = p.parse_args()
    if not args.set and not args.patch:
        p.error("give --set FIELD=VALUE and/or --patch FIELDS.json")
    if args.key and not KEY_RE.match(args.key):
        p.error("--key is an 8-character item key")
    return args


def main():
    args = parse_args()
    api = Api(args.base_url)
    server_id = live_server_id(api)
    api_key = load_key(args.key_file, server_id)
    if args.cite:
        args.key = resolve_cite(api, args.cite)
    run(api, args, api_key, server_id)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
