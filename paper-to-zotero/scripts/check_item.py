# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Preview what Zotero's local API will do with an item.json before it is written.

Zotero (Item.fromJSON, non-strict mode, used by the local API and the
connector) is lenient: it rejects only an unknown itemType. Everything
else is silently reshaped, and this script reports that per key so the
agent can fix item.json or accept the effect knowingly:

- ok_fields: stored as given (also the specially handled keys such as
  tags, collections, extra).
- mapped: a base field that this type stores under another name
  (publicationTitle -> proceedingsTitle for conferencePaper).
- to_extra: a valid Zotero field that this type does not have, or an
  unknown key with a string value; Zotero appends it to Extra as
  "key: value".
- dropped_or_rewritten: an unknown key with a non-string value
  (discarded), a non-string value on a known field (numbers become
  strings, anything else is unchecked), a creatorType unknown or not
  valid for the type (rewritten to the primary type), a creator without
  creatorType or name (the whole item is rejected), attachment-only keys
  on a regular item (rejected) or note-only keys (ignored).
- missing_minimum: this skill's own floor for a paper record: title,
  creators, date, DOI or url, and a venue field valid for the type.

Behaviour verified against Zotero 10.0.3 (Item.fromJSON, Item.setField,
Item.setCreator, Creators.cleanData). Only GET requests are made (item
types, fields, creator types, schema).
Exit codes: 0 = ok; 1 = needs_attention / unknown_item_type / invalid_json
/ item_unreadable (the agent decides); 2 = cannot check (Zotero
unreachable, local API disabled, API error).
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
TIMEOUT = 15

# Keys Item.fromJSON handles outside the field table; fine on any item.
SPECIAL_KEYS = {
    "key", "version", "itemType", "dateAdded", "dateModified", "collections",
    "tags", "relations", "extra", "deleted", "inPublications",
}
# Setters that throw unless the item is an attachment.
ATTACHMENT_ONLY_KEYS = {"linkMode", "contentType", "charset", "filename", "path"}
# Silently ignored unless the item is a note, attachment or annotation.
CHILD_ONLY_KEYS = {"note", "parentItem", "md5", "mtime"}
CHILD_TYPES = {"attachment", "note", "annotation"}
# Venue fields this skill accepts as the paper's outlet.
VENUE_FIELDS = {
    "publicationTitle", "proceedingsTitle", "bookTitle", "repository",
    "university", "institution", "publisher",
}

SKELETON = """\
{
  "itemType": "journalArticle",
  "title": "Paper title",
  "creators": [
    {"creatorType": "author", "firstName": "Ada", "lastName": "Lovelace"},
    {"creatorType": "author", "name": "Single-field name"}
  ],
  "date": "2024-03-01",
  "DOI": "10.1000/example.2024.1",
  "url": "https://doi.org/10.1000/example.2024.1",
  "publicationTitle": "Journal Name",
  "abstractNote": "Abstract text.",
  "extra": ""
}"""


class ApiError(Exception):
    def __init__(self, code: str, detail: str, hint: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.hint = hint


class LocalApi:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        # Bypass any proxy from the environment; the API is on localhost.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(self, path: str, params: dict | None = None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=TIMEOUT) as resp:
                status, body = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise ApiError(
                "zotero_unreachable",
                f"{self.base_url}: {getattr(e, 'reason', e)}",
                "Zotero does not answer. Ask the user to start Zotero (never restart it "
                "from here), then rerun.",
            ) from None
        text = body.decode("utf-8", errors="replace")
        if status == 403:
            raise ApiError(
                "local_api_disabled",
                text.strip() or "403",
                "Zotero's local API is off. Ask the user to enable it in Zotero "
                "Settings > Advanced > 'Allow other applications on this computer to "
                "communicate with Zotero', then rerun.",
            )
        if status != 200:
            raise ApiError(
                "api_error",
                f"GET {path} -> {status} {text.strip()[:200]}",
                "Unexpected response from the local API; check Zotero and rerun.",
            )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise ApiError(
                "api_error",
                f"GET {path}: response is not JSON",
                "Unexpected response from the local API; check Zotero and rerun.",
            ) from None


def emit(obj: dict, exit_code: int) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    return exit_code


def is_empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def load_item(path: Path):
    """Return (item, None) or (None, error output)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return None, {
            "code": "item_unreadable",
            "detail": f"{path}: {e}",
            "hint": "Point --item at the item.json written for this paper (UTF-8), then rerun.",
        }
    try:
        item = json.loads(text)
    except json.JSONDecodeError as e:
        detail = f"{path}: line {e.lineno} column {e.colno}: {e.msg}"
    else:
        if isinstance(item, dict):
            return item, None
        detail = f"{path}: top level must be one JSON object, not {type(item).__name__}"
    return None, {
        "code": "invalid_json",
        "detail": detail,
        "hint": "Fix item.json so it holds one JSON object, then rerun.",
    }


def type_schema(api: LocalApi, item_type: str) -> dict:
    """Field and creator-type facts for one item type, from the live API."""
    schema = api.get("/api/schema")
    all_fields: set[str] = set()
    all_creator_types: set[str] = set()
    base_to_field: dict[str, str] = {}
    primary = "author"
    for t in schema.get("itemTypes", []):
        for f in t.get("fields", []):
            all_fields.add(f["field"])
            if "baseField" in f:
                all_fields.add(f["baseField"])
        for c in t.get("creatorTypes", []):
            all_creator_types.add(c["creatorType"])
        if t.get("itemType") == item_type:
            for f in t.get("fields", []):
                if "baseField" in f:
                    base_to_field[f["baseField"]] = f["field"]
            for c in t.get("creatorTypes", []):
                if c.get("primary"):
                    primary = c["creatorType"]
    fields = [f["field"] for f in api.get("/api/itemTypeFields", {"itemType": item_type})]
    creator_types = [c["creatorType"] for c in api.get("/api/itemTypeCreatorTypes", {"itemType": item_type})]
    return {
        "fields": set(fields),
        "base_to_field": base_to_field,
        "creator_types": creator_types,
        "primary_creator_type": primary,
        "all_fields": all_fields,
        "all_creator_types": all_creator_types,
    }


def check_creators(item: dict, ts: dict, item_type: str, report: dict) -> int:
    """Append creator problems to the report; return the number of usable creators."""
    creators = item.get("creators")
    if creators is None:
        return 0
    if not isinstance(creators, list):
        report["dropped_or_rewritten"].append(
            {"field": "creators", "reason": "must be a list of creator objects"}
        )
        return 0
    valid = ", ".join(ts["creator_types"])
    usable = 0
    for i, c in enumerate(creators):
        where = f"creators[{i}]"
        if not isinstance(c, dict):
            report["dropped_or_rewritten"].append({"field": where, "reason": "must be an object"})
            continue
        # Creators.cleanData / Item.setCreator throw on these; the local API then
        # reports the whole item as failed (400).
        rejected = None
        if "name" in c and ("firstName" in c or "lastName" in c):
            rejected = "use either 'name' or 'firstName'/'lastName', not both"
        elif "name" not in c and "lastName" not in c:
            rejected = "a creator needs 'name' or 'lastName'"
        elif any(k in c and c[k] is not None and not isinstance(c[k], str) for k in ("name", "firstName", "lastName")):
            rejected = "name parts must be strings"
        elif is_empty(c.get("creatorType")):
            rejected = f"creatorType is missing; add one (valid for {item_type}: {valid})"
        if rejected:
            report["dropped_or_rewritten"].append({"field": where, "reason": "rejected: " + rejected})
            continue
        ctype = c["creatorType"]
        if ctype not in ts["creator_types"]:
            known = "not valid for" if ctype in ts["all_creator_types"] else "not a Zotero creator type for"
            report["dropped_or_rewritten"].append(
                {
                    "field": f"{where}.creatorType",
                    "reason": f"'{ctype}' is {known} {item_type}; Zotero rewrites it to "
                    f"'{ts['primary_creator_type']}' (valid: {valid})",
                }
            )
        usable += 1
    return usable


def check_fields(item: dict, ts: dict, item_type: str, report: dict) -> dict[str, str]:
    """Classify every key; return the effective field values after mapping."""
    effective: dict[str, str] = {}
    for key, value in item.items():
        if key == "creators":
            continue
        if key in SPECIAL_KEYS:
            report["ok_fields"].append(key)
            if key == "extra" and isinstance(value, str):
                effective["extra"] = value
            continue
        if key in ATTACHMENT_ONLY_KEYS:
            if item_type == "attachment":
                report["ok_fields"].append(key)
            else:
                report["dropped_or_rewritten"].append(
                    {"field": key, "reason": f"rejected: can only be set on attachment items, not {item_type}"}
                )
            continue
        if key in CHILD_ONLY_KEYS:
            if item_type in CHILD_TYPES:
                report["ok_fields"].append(key)
            else:
                report["dropped_or_rewritten"].append(
                    {"field": key, "reason": f"ignored on {item_type}; only notes, attachments and annotations use it"}
                )
            continue
        if key not in ts["all_fields"]:
            if isinstance(value, str):
                report["to_extra"].append(
                    {"field": key, "reason": f"unknown field; Zotero stores it in Extra as '{key}: ...'"}
                )
            else:
                report["dropped_or_rewritten"].append(
                    {"field": key, "reason": f"unknown field with a {type(value).__name__} value is discarded"}
                )
            continue
        # Known Zotero field from here on.
        if isinstance(value, bool) or (value is not None and not isinstance(value, (str, int, float))):
            report["dropped_or_rewritten"].append(
                {
                    "field": key,
                    "reason": f"value is a {type(value).__name__}; Zotero does not validate it, use a string",
                }
            )
            continue
        if isinstance(value, (int, float)):
            report["dropped_or_rewritten"].append(
                {"field": key, "reason": f"number; Zotero stores it as the string '{value}', use a string"}
            )
            value = str(value)
        if key in ts["fields"]:
            target = key
            report["ok_fields"].append(key)
        elif key in ts["base_to_field"]:
            target = ts["base_to_field"][key]
            report["mapped"].append({"from": key, "to": target})
        else:
            report["to_extra"].append(
                {"field": key, "reason": f"valid Zotero field but not for {item_type}; Zotero stores it in Extra"}
            )
            continue
        if is_empty(value):
            report["empty_fields"].append(key)
        else:
            effective[target] = value
    return effective


def check_minimum(effective: dict[str, str], usable_creators: int, ts: dict, report: dict) -> None:
    def present(field: str) -> bool:
        return not is_empty(effective.get(field))

    base_of = {v: k for k, v in ts["base_to_field"].items()}

    def present_base(base: str) -> bool:
        return present(base) or present(ts["base_to_field"].get(base, ""))

    missing = []
    if not present_base("title"):
        missing.append("title")
    if usable_creators == 0:
        missing.append("creators")
    if not present_base("date"):
        missing.append("date")
    doi_in_extra = bool(re.search(r"(?im)^DOI:\s*\S+", effective.get("extra", "")))
    if not (present("DOI") or doi_in_extra or present("url")):
        missing.append("DOI or url")
    venue = {f for f in ts["fields"] if f in VENUE_FIELDS or base_of.get(f) in ("publicationTitle", "publisher")}
    if venue and not any(present(f) for f in venue):
        missing.append("venue (one of: " + ", ".join(sorted(venue)) + ")")
    report["missing_minimum"] = missing


def run(args: argparse.Namespace) -> int:
    item, err = load_item(Path(args.item))
    if err:
        return emit(err, 1)

    api = LocalApi(args.base_url)
    item_types = [t["itemType"] for t in api.get("/api/itemTypes")]
    item_type = item.get("itemType")
    if not isinstance(item_type, str) or item_type not in item_types:
        shown = item_type if isinstance(item_type, str) else None
        suggestions = difflib.get_close_matches(shown or "", item_types, n=3, cutoff=0.5) if shown else []
        return emit(
            {
                "code": "unknown_item_type",
                "itemType": shown,
                "suggestions": suggestions,
                "hint": "The local API rejects this with 400. Set itemType to a Zotero type"
                + (f" (closest: {', '.join(suggestions)})" if suggestions else "")
                + ", then rerun.",
            },
            1,
        )

    ts = type_schema(api, item_type)
    report: dict = {
        "code": "ok",
        "itemType": item_type,
        "ok_fields": [],
        "mapped": [],
        "to_extra": [],
        "dropped_or_rewritten": [],
        "empty_fields": [],
        "missing_minimum": [],
    }
    usable = check_creators(item, ts, item_type, report)
    if "creators" in item and isinstance(item["creators"], list):
        report["ok_fields"].append("creators")
    effective = check_fields(item, ts, item_type, report)
    check_minimum(effective, usable, ts, report)

    if report["mapped"] or report["to_extra"] or report["dropped_or_rewritten"] or report["missing_minimum"]:
        report["code"] = "needs_attention"
        report["hint"] = (
            "Fix item.json (see mapped, to_extra, dropped_or_rewritten, missing_minimum) "
            "or accept these effects knowingly before saving."
        )
        return emit(report, 1)
    return emit(report, 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview what Zotero's local API will do with an item.json (read-only). "
        "Prints one JSON object: code ok (exit 0); needs_attention / unknown_item_type / "
        "invalid_json / item_unreadable (exit 1); zotero_unreachable / local_api_disabled / "
        "api_error (exit 2).",
        epilog="Minimal item.json:\n" + SKELETON + "\n\n"
        "Example:\n  uv run check_item.py --item item.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--item", required=True, help="path to the item JSON (one object, Zotero Web API v3 shape)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"local API base URL (default {DEFAULT_BASE_URL})")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except ApiError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        return emit({"code": e.code, "detail": e.detail, "hint": e.hint}, 2)


if __name__ == "__main__":
    sys.exit(main())
