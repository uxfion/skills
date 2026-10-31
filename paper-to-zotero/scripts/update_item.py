#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Change fields of existing Zotero items through the local API: one --set / --patch for every item named, or a batch.

Items: --key and --cite (the top-level item carrying that citationKey), each taking --patch, then --set (the later
wins); or --batch FILE, JSON lines, an entry per item: {"key" | "cite", "set": {field: value}}. Any other key of an
entry is a note for people (the listers write from, why, by) and is ignored. Entries run in the file's order, each on
the item as it is then. For each item: read it; merge the fields into its data; check the names against the item
type's schema (a base name such as publicationTitle goes to the type's own field, proceedingsTitle on a
conferencePaper, as Zotero does); PATCH only what differs, with its version; read it back. On an item-type change
Zotero keeps each field the new type has under its own or its base field's name and moves the rest to Extra:
`fields_to_extra` says which. Tags and collections are file_and_tag.py's, the trash is trash_item.py's: both are
refused here. A PDF's new title goes to its structured package too, and a new citationKey or title renames the
packages' files in place (`packages`). titles_from_labels.py and fields_from_results.py write batch files.

stdout: one line per item (a batch: per entry), then {"summary": {total, ok, skipped, failed}}. A written item: {key,
cite?, code, changes {field: {from, to}}, mapped_fields, fields_to_extra, applied, normalized, version_before,
version_after, retried, extra?}; --dry-run: {key, cite?, code, changes, mapped_fields, fields_to_extra, version}.
`normalized` holds the fields Zotero stored otherwise than sent ({sent, now}); an Extra line it moved into the field
of that name ("PMID: 1" -> PMID) shows as normalized.extra.moved_to_fields, a success: set that field itself next
time. `extra` is an Extra that Zotero changed on its own (a type change).
  ok                  written and read back (--dry-run: planned, nothing written)
  skipped             reason unchanged: the item holds every value already
  refused_property    tags, collections, relations, deleted, key, version, dates, parentItem, note, attachment internals
  invalid_patch_file  --patch is not a non-empty JSON object of field: value
  invalid_field       not a field of the (new) item type nor a base name of one (`valid_fields`); or a value that is
                      not a string (creators is a list)
  invalid_item_type   --set itemType names no item type, the item is a note or an annotation, or an attachment's
                      type would change
  invalid_creators    not a list of {creatorType, lastName[, firstName]} or {creatorType, name} with a creatorType
                      the item type has (`problems`)
  not_found           no item with that key
  cite_not_found      no top-level item carries the citationKey; cite_ambiguous: several do (`keys`), pass --key
  version_conflict    the item changed twice while it was being written; wait, then rerun
  write_denied        the library is not editable; write_failed: the local API rejected the write (status, detail)
  readback_mismatch   the write was accepted, but a field still shows its old value (`mismatch`)
  not_run             Zotero stopped answering before this item (summary.stopped says why)
refused_property, invalid_patch_file and a value that is not a string are found before Zotero is asked: one line,
nothing done. In a batch they are invalid_batch, one line naming each bad entry by its line number (`detail`), as is
a line that is not a JSON object {key | cite, set: {field: value}} or a file without entries: nothing done.
Exit 0 = every item ok or skipped, 1 = some item not, 2 = cannot check (zotero_unreachable, local_api_disabled,
no_key, key_rejected, server_mismatch).

Examples:
  uv run scripts/update_item.py --key ABCD1234 --set date=2023 --set DOI=10.1109/CVPR52729.2023.00194 --dry-run
  uv run scripts/update_item.py --key ABCD1234 --set itemType=conferencePaper \\
      --set "publicationTitle=2023 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)" --set pages=1952-1961
  uv run scripts/update_item.py --key ABCD1234 --patch fix.json      # {"creators": [...], "extra": "arXiv: 2205.07680"}
  uv run scripts/update_item.py --cite liu2022progressive --set citationKey=liu2022progressive
  uv run scripts/update_item.py --batch titles.jsonl --dry-run       # {"key": "ATTACH01", "set": {"title": "Published-IEEE"}}
"""
import json
from pathlib import Path

from p2zlib import cli, paper, zotero

# JSON properties that are not fields to set here, and why.
REFUSED = {
    "key": "Zotero's own", "version": "Zotero's own", "dateAdded": "Zotero's own", "dateModified": "Zotero's own",
    "tags": "file_and_tag.py", "collections": "file_and_tag.py", "relations": "not supported here",
    "deleted": "moving to the trash is trash_item.py's job, after the user has confirmed the list", "parentItem": "not supported here",
    "linkMode": "attachment internals", "contentType": "attachment internals", "charset": "attachment internals",
    "filename": "attachment internals", "md5": "attachment internals", "mtime": "attachment internals",
    "path": "attachment internals", "note": "notes are not edited here",
}
NOT_EDITED = ("note", "annotation")
HINT_CREATORS = ('creators is a list of {"creatorType", "lastName"[, "firstName"]} or {"creatorType", "name"}, '
                 "with a creatorType the item type has.")


def read_patch(name):
    path = Path(name).expanduser()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise cli.Stop("invalid_patch_file", hint="--patch names a JSON file holding an object of field: value.",
                       patch_file=str(path), detail=str(e)) from None
    if not isinstance(raw, dict) or not raw:
        raise cli.Stop("invalid_patch_file", hint="The patch file holds a non-empty JSON object of field: value.",
                       patch_file=str(path))
    return raw


def checked(sets):
    """{field: value} with each value a string, stripped (creators a list): a refused name or a value that is not a
    string stops here."""
    out = {}
    for field, value in sets.items():
        field = field.strip()
        if field in REFUSED:
            raise cli.Stop("refused_property", hint=f"{field!r} is not set here: {REFUSED[field]}.", field=field)
        if field != "creators":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                value = str(value)
            if not isinstance(value, str):
                raise cli.Stop("invalid_field", hint="Field values are strings (creators is a list).", field=field,
                               value=value)
            value = value.strip()
        out[field] = value
    return out


def read_batch(name):
    """--batch FILE -> [{key, cite, sets}], each entry checked as --set is; invalid_batch naming every bad entry."""
    path = Path(name).expanduser()
    found, problems = cli.batch_entries(path)
    entries = []
    for b in found:
        sets = b["entry"].get("set")
        if not isinstance(sets, dict) or not sets:
            problems.append(f'{b["where"]}: "set" is a non-empty object of field: value')
            continue
        try:
            entries.append({"key": b["key"], "cite": b["cite"], "sets": checked(sets)})
        except cli.Stop as stop:
            problems.append(f"{b['where']}: {stop.code} {stop.extra['field']!r}: {stop.hint}")
    if problems:
        raise invalid_batch(path, problems)
    return entries


def invalid_batch(path, problems):
    return cli.Stop("invalid_batch", hint='--batch holds JSON lines, an entry per item: {"key" | "cite", "set": {field: '
                                          'value}}. Fix the file, then rerun; nothing was done.',
                    batch_file=str(path), detail=problems)


def check(p, args):
    """The batch's entries as args.entries, or --patch, then --set, as args.sets {field: value}: refused names and
    values that are not strings stop here."""
    if args.batch:
        args.entries = read_batch(args.batch)
        return
    if not args.set and not args.patch:
        p.error("give --set FIELD=VALUE and/or --patch FILE, or --batch FILE")
    pairs = [s.partition("=") for s in args.set]
    bad = ["".join(t) for t in pairs if not t[1] or not t[0].strip()]
    if bad:
        p.error(f"--set takes FIELD=VALUE (an empty VALUE clears the field): {', '.join(bad)}")
    args.sets = checked({**(read_patch(args.patch) if args.patch else {}), **{f.strip(): v for f, _, v in pairs}})


def plan(item, sets, types):
    """What to PATCH so the item holds `sets` -> (body, {changes, mapped_fields, fields_to_extra}); body {} when
    nothing differs."""
    d = zotero.data(item)
    old_type = d.get("itemType")
    if old_type in NOT_EDITED or old_type not in types:
        raise cli.Stop("invalid_item_type", item_type=old_type,
                       hint="Regular items and attachment titles are edited here; notes and annotations are not.")
    new_type = sets.get("itemType", old_type)
    if new_type not in types:
        raise cli.Stop("invalid_item_type", hint="No such item type; read_library.py schema lists them.", item_type=new_type,
                       item_types=sorted(types))
    if new_type != old_type and (old_type == "attachment" or new_type in ("attachment", *NOT_EDITED)):
        raise cli.Stop("invalid_item_type", from_type=old_type, to_type=new_type,
                       hint="An attachment stays an attachment; a regular item does not become an attachment or a note.")
    old, new = types[old_type], types[new_type]
    body, changes, mapped, invalid = {}, {}, {}, []
    if new_type != old_type:
        body["itemType"], changes["itemType"] = new_type, {"from": old_type, "to": new_type}
    for field, value in sets.items():
        if field == "itemType":
            continue
        if field == "creators":
            problems = paper.creator_problems(value, new["creator_types"])
            if problems:
                raise cli.Stop("invalid_creators", hint=HINT_CREATORS, problems=problems,
                               creator_types=sorted(new["creator_types"]))
            own, value, before = field, [{k: str(v).strip() for k, v in c.items()} for c in value], d.get("creators") or []
        else:
            own = zotero.own_field(new, field)
            if own is None:
                invalid.append(field)
                continue
            if own != field:
                mapped[field] = own
            before = d.get(own, "")
        if value != before:
            body[own], changes[own] = value, {"from": before, "to": value}
    if invalid:
        raise cli.Stop("invalid_field", invalid_fields=invalid, valid_fields=sorted(new["fields"] | set(new["by_base"])),
                       hint=f"Not fields of {new_type}, nor base names it maps: use one of valid_fields, or put the value in extra.")
    # A type change keeps a field the new type has under its own or its base field's name; Zotero moves the rest to Extra.
    to_extra = {}
    if new_type != old_type:
        to_extra = {f: v for f, v in d.items() if v and f in old["fields"]
                    and not (zotero.own_field(new, f) or zotero.own_field(new, old["base_of"].get(f, f)))}
    return body, {"changes": changes, "mapped_fields": mapped, "fields_to_extra": to_extra}


def readback(sent, changes, now):
    """Per field sent: applied (read back as sent), normalized {sent, now} (Zotero stored something else) or
    mismatch {sent, now} (it still shows the old value)."""
    applied, normalized, mismatch = [], {}, {}
    for f, value in sent.items():
        got = now.get(f, [] if f == "creators" else "")
        moved = moved_to_fields(value, got, now) if f == "extra" else {}
        if got == value:
            applied.append(f)
        elif moved and [ln for ln in value.splitlines() if ln not in moved] == got.splitlines():
            normalized[f] = {"sent": value, "now": got, "moved_to_fields": moved}
        elif got == changes[f]["from"]:
            mismatch[f] = {"sent": value, "now": got}
        else:
            normalized[f] = {"sent": value, "now": got}
    return applied, normalized, mismatch


def moved_to_fields(sent, now, after_data):
    """Lines of the Extra we sent that Zotero moved into the field of that name ("PMID: 1" -> PMID): {line: field}.
    Zotero does this on save when the item type has the field and it is empty, so the Extra read back lacks them."""
    if not isinstance(sent, str) or not isinstance(now, str):
        return {}
    kept, fields, out = set(now.splitlines()), {k.casefold(): k for k in after_data}, {}
    for line in sent.splitlines():
        name, sep, value = line.partition(":")
        field = fields.get(name.strip().casefold())
        if line not in kept and sep and field and field != "extra" and str(after_data.get(field)).strip() == value.strip():
            out[line] = field
    return out


def process(zot, key, sets, dry_run):
    types, planned = zot.item_types(), {}

    def body_of(item):
        body, planned["info"] = plan(item, sets, types)
        return body or None

    item = zot.item(key)
    if item is None:
        raise cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND)
    if dry_run:
        if not body_of(item):
            return cli.skipped("unchanged", version=item.get("version"))
        return cli.ok(**planned["info"], version=item.get("version"), dry_run=True)
    d = zotero.data(item)
    parent = d.get("parentItem") if paper.is_pdf(d) else key
    following = zot.packages(parent, d.get("title")) if paper.is_pdf(d) and parent else []
    item, sent, retried = zot.update(key, body_of, item)
    if sent is None:
        return cli.skipped("unchanged", version=item.get("version"), retried=retried)
    if "title" in sent:
        for c in following:
            zot.retitle(c["key"], sent["title"])
    renamed = zot.name_packages(parent) if "citationKey" in sent or (following and "title" in sent) else []
    after = zot.item(key)
    if after is None:
        raise cli.Stop("not_found", hint="The item disappeared after the write.")
    applied, normalized, mismatch = readback(sent, planned["info"]["changes"], zotero.data(after))
    line = {**planned["info"], "applied": applied, "normalized": normalized, "version_before": item.get("version"),
            "version_after": after.get("version"), "retried": retried, **({"packages": renamed} if renamed else {})}
    extra_before, extra_after = zotero.data(item).get("extra") or "", zotero.data(after).get("extra") or ""
    if "extra" not in sent and extra_after != extra_before:
        line["extra"] = {"from": extra_before, "to": extra_after}
    if mismatch:
        raise cli.Stop("readback_mismatch", hint="The write was accepted, but these fields still show their old value; "
                       "look at the item in Zotero.", mismatch=mismatch, **line)
    return cli.ok(**line)


def targets(zot, args):
    """[(key, cite, sets, failure)] in the order handled: the items --key / --cite name, each with args.sets (an item
    named twice once), or the batch's entries in the file's order (every citation key resolved at once)."""
    if not args.batch:
        return [(key, cite, args.sets, failure) for key, cite, failure in zot.targets(args.key, args.cite)]
    cites = list(dict.fromkeys(e["cite"] for e in args.entries if e["cite"]))
    hits, out = zot.resolve_cites(cites) if cites else {}, []
    for e in args.entries:
        keys = hits[e["cite"]] if e["cite"] else [e["key"]]
        failure = zot.cite_failure(e["cite"], keys) if len(keys) != 1 else None
        out.append((None if failure else keys[0], e["cite"], e["sets"], failure))
    return out


def main(argv=None):
    p = cli.parser(__doc__)
    cli.add_targets(p)
    p.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE",
                   help="a field to set (repeatable); an empty VALUE clears it; FIELD may be itemType, or a base name "
                        "such as publicationTitle")
    p.add_argument("--patch", metavar="FILE", help="a JSON object of field: value, for creators (a list) and multi-line "
                                                   "values such as extra; --set wins over it")
    p.add_argument("--batch", metavar="FILE", help='JSON lines, an entry per item: {"key" | "cite", "set": {field: value}}')
    p.add_argument("--dry-run", action="store_true", help="show what would be written; write nothing")
    cli.add_base_url(p)
    args = cli.targets_of(p, p.parse_args(argv), required=False)
    if args.batch and (args.key or args.cite or args.set or args.patch):
        p.error("--batch names the items and their fields in the file: leave out --key, --cite, --set and --patch")
    if not args.batch and not (args.key or args.cite):
        p.error("name the items with --key and/or --cite, or pass --batch")

    def loop():
        check(p, args)  # before Zotero is asked
        zot = zotero.Zotero(args.base_url)
        if not args.dry_run:
            zot.write_headers()
        out = cli.Lines()
        for key, cite, sets, failure in targets(zot, args):
            if failure is not None:
                out.lines.append(failure.line(**cli.head(key, cite)))
            else:
                out.add(cli.head(key, cite), lambda: process(zot, key, sets, args.dry_run))
        return out.finish({"dry_run": True} if args.dry_run else None)

    return cli.run(loop)


if __name__ == "__main__":
    raise SystemExit(main())
