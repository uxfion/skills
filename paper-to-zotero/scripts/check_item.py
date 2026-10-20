#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Preview what Zotero's local API will do with each record's item before it is created: the record's `checks`.

Zotero (Item.fromJSON, non-strict mode, used by the local API and the connector) rejects only an unknown itemType;
everything else is silently reshaped. The report says so per field, so the agent can fix the item or accept the
effect knowingly:
  ok_fields              stored as given (also the specially handled keys: tags, collections, extra, ...)
  mapped                 a base field this type stores under another name (publicationTitle -> proceedingsTitle)
  to_extra               a Zotero field this type does not have, or an unknown key with a string value: Zotero
                         appends it to Extra as "key: value"
  dropped_or_rewritten   an unknown key with a non-string value (discarded), a non-string value on a known field,
                         a creatorType the type does not allow (rewritten to the primary one), a creator without
                         creatorType or name (the whole item is rejected), attachment- or note-only keys
  missing_minimum        this skill's floor for a paper: title, creators, date, DOI or url, a venue field
Behaviour verified against Zotero 10.0.3 (Item.fromJSON, Item.setField, Item.setCreator, Creators.cleanData). The
schema is read from Zotero once a run (kept in <work>/scratch/schema.json).

Records: the files given. `checks` is computed again only when it is not done (absent, or the item changed since);
each line says why (`reason`). stdout: one line per record {slug, code, reason?, itemType, mapped?, to_extra?,
dropped_or_rewritten?, missing_minimum?}, then {"summary"}.
  ok                  the item goes in as written
  needs_attention     see the lists; fix the item, or accept the effect and say so in the report
  unknown_item_type   Zotero rejects the item (`suggestions`: the closest types)
  no_item             the record has no `item` (draft it with doi_to_item.py)
  skipped             reason done: `checks` is up to date (`checks`: its code)
Exit 0 = every record ok or done, 1 = some record is not, 2 = cannot check (zotero_unreachable, local_api_disabled).

A minimal item:
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
}

Example:
  uv run scripts/check_item.py <work>/records/*.json
"""
import difflib
import re

from p2zlib import cli, paper, run, zotero

# Keys Item.fromJSON handles outside the field table; fine on any item.
SPECIAL_KEYS = {"key", "version", "itemType", "dateAdded", "dateModified", "collections", "tags", "relations", "extra",
                "deleted", "inPublications"}
# Setters that throw unless the item is an attachment.
ATTACHMENT_ONLY_KEYS = {"linkMode", "contentType", "charset", "filename", "path"}
# Silently ignored unless the item is a note, attachment or annotation.
CHILD_ONLY_KEYS = {"note", "parentItem", "md5", "mtime"}
# Venue fields this skill accepts as the paper's outlet.
VENUE_FIELDS = {"publicationTitle", "proceedingsTitle", "bookTitle", "repository", "university", "institution", "publisher"}
HINT = ("Fix the item (see mapped, to_extra, dropped_or_rewritten, missing_minimum) or accept these effects knowingly "
        "before it is created.")


def is_empty(value):
    return value is None or (isinstance(value, str) and not value.strip())


def type_facts(schema):
    """zotero.types_of(schema), plus every field and creator type of any type."""
    types = zotero.types_of(schema)
    all_fields = {f for t in types.values() for f in t["fields"] | set(t["by_base"])}
    all_creators = {c for t in types.values() for c in t["creator_types"]}
    return types, all_fields, all_creators


def check_creators(item, ts, item_type, report, all_creators):
    """Creator problems into the report; returns the number of usable creators."""
    creators = item.get("creators")
    if creators is None:
        return 0
    if not isinstance(creators, list):
        report["dropped_or_rewritten"].append({"field": "creators", "reason": "must be a list of creator objects"})
        return 0
    valid = ", ".join(ts["creator_types"])
    usable = 0
    for i, c in enumerate(creators):
        where = f"creators[{i}]"
        if not isinstance(c, dict):
            report["dropped_or_rewritten"].append({"field": where, "reason": "must be an object"})
            continue
        # Creators.cleanData / Item.setCreator throw on these; the local API then fails the whole item (400).
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
            known = "not valid for" if ctype in all_creators else "not a Zotero creator type for"
            report["dropped_or_rewritten"].append({"field": f"{where}.creatorType",
                                                   "reason": f"'{ctype}' is {known} {item_type}; Zotero rewrites it to "
                                                             f"'{ts['primary']}' (valid: {valid})"})
        usable += 1
    return usable


def check_fields(item, ts, item_type, report, all_fields):
    """Classify every key; returns the field values as they will be stored."""
    effective = {}
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
                    {"field": key, "reason": f"rejected: can only be set on attachment items, not {item_type}"})
            continue
        if key in CHILD_ONLY_KEYS:
            if item_type in paper.CHILD_TYPES:
                report["ok_fields"].append(key)
            else:
                report["dropped_or_rewritten"].append(
                    {"field": key, "reason": f"ignored on {item_type}; only notes, attachments and annotations use it"})
            continue
        if key not in all_fields:
            if isinstance(value, str):
                report["to_extra"].append({"field": key, "reason": f"unknown field; Zotero stores it in Extra as '{key}: ...'"})
            else:
                report["dropped_or_rewritten"].append(
                    {"field": key, "reason": f"unknown field with a {type(value).__name__} value is discarded"})
            continue
        if isinstance(value, bool) or (value is not None and not isinstance(value, (str, int, float))):
            report["dropped_or_rewritten"].append(
                {"field": key, "reason": f"value is a {type(value).__name__}; Zotero does not validate it, use a string"})
            continue
        if isinstance(value, (int, float)):
            report["dropped_or_rewritten"].append(
                {"field": key, "reason": f"number; Zotero stores it as the string '{value}', use a string"})
            value = str(value)
        if key in ts["fields"]:
            target = key
            report["ok_fields"].append(key)
        elif key in ts["by_base"]:
            target = ts["by_base"][key]
            report["mapped"].append({"from": key, "to": target})
        else:
            report["to_extra"].append({"field": key, "reason": f"valid Zotero field but not for {item_type}; Zotero stores it in Extra"})
            continue
        if is_empty(value):
            report["empty_fields"].append(key)
        else:
            effective[target] = value
    return effective


def check_minimum(effective, usable_creators, ts, report):
    present = lambda field: not is_empty(effective.get(field))
    base_of = {v: k for k, v in ts["by_base"].items()}
    missing = []
    if not (present("title") or present(ts["by_base"].get("title", ""))):
        missing.append("title")
    if usable_creators == 0:
        missing.append("creators")
    if not (present("date") or present(ts["by_base"].get("date", ""))):
        missing.append("date")
    if not (present("DOI") or re.search(r"(?im)^DOI:\s*\S+", effective.get("extra", "")) or present("url")):
        missing.append("DOI or url")
    venue = {f for f in ts["fields"] if f in VENUE_FIELDS or base_of.get(f) in ("publicationTitle", "publisher")}
    if venue and not any(present(f) for f in venue):
        missing.append("venue (one of: " + ", ".join(sorted(venue)) + ")")
    report["missing_minimum"] = missing


def check_one(item, facts):
    """The report on one item: code ok | needs_attention | unknown_item_type."""
    types, all_fields, all_creators = facts
    item_type = item.get("itemType")
    if not isinstance(item_type, str) or item_type not in types:
        shown = item_type if isinstance(item_type, str) else None
        return {"code": "unknown_item_type", "itemType": shown,
                "suggestions": difflib.get_close_matches(shown or "", list(types), n=3, cutoff=0.5) if shown else []}
    ts = types[item_type]
    report = {"code": "ok", "itemType": item_type, "ok_fields": [], "mapped": [], "to_extra": [], "dropped_or_rewritten": [],
              "empty_fields": [], "missing_minimum": []}
    usable = check_creators(item, ts, item_type, report, all_creators)
    if isinstance(item.get("creators"), list):
        report["ok_fields"].append("creators")
    check_minimum(check_fields(item, ts, item_type, report, all_fields), usable, ts, report)
    if any(report[k] for k in ("mapped", "to_extra", "dropped_or_rewritten", "missing_minimum")):
        report["code"] = "needs_attention"
    return report


def setup(args, records):
    return {"zot": zotero.Zotero(args.base_url), "facts": None}


def process(rec, ctx):
    if not rec.item:
        return {"code": "no_item", "hint": run.HINT_NO_ITEM}
    due = run.due(rec, "checks")
    if due is None:
        return cli.skipped("done", checks=rec["checks"]["code"])
    if ctx["facts"] is None:
        ctx["facts"] = type_facts(ctx["zot"].schema(cache=rec.work.schema_file))
    report = run.stamp(rec, "checks", check_one(rec.item, ctx["facts"]))
    line = {"code": report["code"], "reason": due, "itemType": report.get("itemType")}
    line.update({k: report[k] for k in ("suggestions", "mapped", "to_extra", "dropped_or_rewritten", "missing_minimum") if report.get(k)})
    if report["code"] == "unknown_item_type":
        line["hint"] = "Zotero rejects this item: set itemType to one it knows (see suggestions), then run again."
    elif report["code"] != "ok":
        line["hint"] = HINT
    return line


def main(argv=None):
    return cli.main_records(__doc__, process, argv, setup=setup, zotero=True, dry_run=True)


if __name__ == "__main__":
    raise SystemExit(main())
