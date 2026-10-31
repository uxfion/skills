#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Attach each record's files to its Zotero item: the files paper-fetch got, as the record's result lists them; the
record's `attach`.

The item is the one this run created (saved.key), else the one the lookup confirmed (found.key); never a near match.
The files are those of the result (the record's `fetched`) whose check is ok, accepted or unconfirmed, every version
of the paper and any supplement, each under its label's title (Preprint-arXiv-v7, Accepted-CVF, Unknown-IEEE, ...),
which paper-fetch settled. An unconfirmed file (the agent could not tell it is the paper's) is attached all the same
and named on the line: the report lists it for the user, and paper-fetch withdraws it once a confirmed file comes. A
result without an `outcome` was never settled, and its `files` may lack a file that came: nothing is attached until
it is — unless the library item has a PDF of the paper already, and the result was never fetched for another. A
stub's file (check cannot_judge: paper-fetch had nothing to check it against) goes the connector path instead
(recognize.py); once the recognizer made the record's item from it (saved.via recognizer), it is that item's file. Each
file's md5 is compared with the result's before anything is uploaded. A child of the item already holding a file (same
md5) settles it without an upload and keeps its own title (`existing`: a title that differs from the label is the
report's to suggest, the user's to approve); an empty attachment left by a cut-off run is reused. A label settled
after this run attached the file renames that attachment on the next run. The source url is the item's url, else its
DOI link. `attach` is a list, an entry per file: {attachment, md5, title, filename, kind, url, at, existing?}; another
file later (another md5) is attached afresh.

stdout: one line per record {slug, code, reason?, status?, key?, files?: [{name, code, attachment?, title?,
renamed?: {from, to}, suggested_title?}], unconfirmed?: [names], unchecked?: [names]}, then {"summary"}.
  ok            a file attached, or renamed after its label (with --dry-run: would be; nothing written)
  skipped       reason no_file_yet (the result has no file to attach; `status` is its outcome's: got, waiting,
                not_got. Not a failure, so save can run after every pass) | attached (every file is in `attach` under
                its title, or the item had it: suggested_title when its title differs from the label's) |
                library_has_pdf (the item has a PDF of the paper, and the result was never fetched for another)
  unchecked     the result's only files are a stub's (`files`): Zotero's recognizer identifies the paper from its
                PDF (references/no-doi-record.md)
  unsettled     the result has no outcome: settle it (paper-fetch's pf.py settle), then rerun
  file_changed  a file's md5 is not the one in the result: settle the result again, then rerun
  no_result     the record names no result file (`fetched`), or it cannot be read: draft_item.py writes it
  no_item_key   the record has no item in Zotero yet (create_item; a possible duplicate is the agent's to settle)
  not_found | not_a_parent | unsupported_file | readback_mismatch | unexpected_response | write_denied |
  write_failed    see the hint
Exit 0 = every record attached or skipped; 1 = not; 2 = cannot go on (Zotero not running, local API off, no key, the
key rejected, another Zotero than the key's).

Example:
  uv run scripts/attach_file.py <scratch>/paper-to-zotero/records/*.json
"""
from pathlib import Path

from p2zlib import cli, paper, run, zotero

ATTACHABLE = ("ok", "accepted", "unconfirmed")
HINT_UNCHECKED = ("A stub's files: paper-fetch had no metadata to check them against. Zotero's recognizer identifies the "
                  "paper from its PDF: recognize.py (references/no-doi-record.md).")


def setup(args, records):
    zot = zotero.Zotero(args.base_url)
    if not args.dry_run:
        zot.write_headers()
    return {"zot": zot, "args": args}


def library_has_pdf(rec):
    """The library item this record found holds a PDF of the paper, of any version (a version not checked is still
    the paper's file)."""
    found = rec.get("found") if run.item_key(rec) and isinstance(rec.get("found"), dict) else {}
    return any(a.get("version") in paper.PAPER_VERSIONS and a.get("contentType") == "application/pdf"
               for a in found.get("attachments") or [] if isinstance(a, dict))


def wanted(res, path, recognized=False):
    """The result's files -> ([(file entry, path, title)] to attach, [names] of a stub's files, which no check
    passed). A title is paper-fetch's label, in the scheme: a judge's, checked when given, or settle's
    Unknown-<Source>. recognized: Zotero's recognizer made the item from the stub's own PDF (recognize.py), which
    is that item's file."""
    out, unchecked = [], []
    for f in res.get("files") or []:
        if not isinstance(f, dict):
            continue
        if f.get("check") not in ATTACHABLE and not (recognized and f.get("check") == "cannot_judge"):
            unchecked.append(f.get("name"))
            continue
        title = ((f.get("label") or {}).get("title") or "").strip()
        file = path.parent / f["name"]
        try:
            md5 = run.md5_of(file)
        except OSError:
            md5 = None
        if md5 != f.get("md5"):
            raise cli.Stop("file_changed", file=str(file), hint="The file is not the one the result lists (gone, or "
                                                                "changed since): settle the result again, then this again.")
        out.append((f, file, title))
    return out, unchecked


def process(rec, ctx):
    res, path = run.result_of(rec)
    if not isinstance(res.get("outcome"), dict):
        if library_has_pdf(rec):
            return cli.skipped("library_has_pdf", key=run.item_key(rec))
        raise cli.Stop("unsettled", hint="The result was never settled, so its files may lack one that came: run "
                                         "paper-fetch's pf.py settle on it, then this again.", result=str(path))
    saved = rec.get("saved") if isinstance(rec.get("saved"), dict) else {}
    files, unchecked = wanted(res, path, recognized=saved.get("via") == "recognizer")
    if not files:
        if unchecked:
            return {"code": "unchecked", "files": unchecked, "hint": HINT_UNCHECKED}
        return cli.skipped("no_file_yet", status=res["outcome"].get("status"))
    zot, dry_run = ctx["zot"], ctx["args"].dry_run
    attach = [a for a in rec.get("attach") or [] if isinstance(a, dict)] if isinstance(rec.get("attach"), list) else []
    url = rec.item.get("url") or (f"https://doi.org/{paper.doi_of(rec.item)}" if paper.doi_of(rec.item) else None)
    lines, key = [], None
    for f, file, title in files:
        entry = next((a for a in attach if a.get("md5") == f["md5"]), None)
        if entry and (entry.get("existing") or entry.get("title") == title):
            lines.append({"name": f["name"], "code": "skipped", "reason": "attached", "attachment": entry["attachment"],
                          "title": entry.get("title"), **({"suggested_title": title} if entry.get("title") != title else {})})
            continue
        if entry:  # this run's own attachment, labelled since: renamed without asking
            old = entry.get("title")
            if not dry_run:
                zot.retitle(entry["attachment"], title)
                entry.update(title=title, at=run.now_iso())
            lines.append({"name": f["name"], "code": "ok", "attachment": entry["attachment"], "title": title,
                          "renamed": {"from": old, "to": title}})
            continue
        key = key or run.item_key(rec)
        if key is None:
            raise cli.Stop("no_item_key", hint="The record has no item in Zotero yet: create_item.py (p2z.py save) makes "
                                               "it; a possible duplicate is settled with same_as or distinct_from first.")
        done = zot.attach(key, file, title=title, url=url, dry_run=dry_run)
        existing = done["code"] == "skipped"
        if existing or not done.get("dry_run"):
            attach.append({"attachment": done["attachment"], "md5": f["md5"], "title": done["title"], "filename": done["filename"],
                           "kind": f.get("kind"), "url": url, "at": run.now_iso(), **({"existing": True} if existing else {})})
        lines.append({"name": f["name"], "code": "skipped" if existing else "ok", **({"reason": done["reason"]} if existing else {}),
                      "attachment": done.get("attachment"), "title": done.get("title"),
                      **({"suggested_title": title} if existing and done.get("title") != title else {})})
    if attach:
        rec["attach"] = attach
    done = all(ln["code"] == "skipped" for ln in lines)
    unconfirmed = [f["name"] for f, _, _ in files if f.get("check") == "unconfirmed"]
    return {**(cli.skipped("attached") if done else {"code": "ok"}), **({"key": key} if key else {}), "files": lines,
            **({"unconfirmed": unconfirmed} if unconfirmed else {}), **({"unchecked": unchecked} if unchecked else {})}


def main(argv=None):
    return cli.main_records(__doc__, process, argv, setup=setup, zotero=True, dry_run=True, all_valid=True)


if __name__ == "__main__":
    raise SystemExit(main())
