#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Identify papers without metadata from their PDF, with Zotero's recognizer: the record's `saved` and `recognize`.

A record here is one whose result (`fetched`) is a stub: paper-fetch found no metadata (no CSL) to check the file
against, and filed the PDF as cannot_judge (draft_item writes such a record: {"fetched": <the result's path>}). The
PDF sent is the stub's cannot_judge PDF that is not a supplement; of several, the first, the others named on the line
(`others`). It goes to Zotero as Zotero's browser connector saves a PDF (/connector/saveStandaloneAttachment), titled
with the file's label: a standalone attachment in the collection Zotero has selected, which Zotero's recognizer then
tries to identify. Its url, which Zotero requires and names the file after, is the file's url, else the result's
request as a DOI link or a web address, else the PDF's file:// address. The script finds the attachment by its md5,
then waits up to --wait seconds for the recognizer to finish (/connector/getRecognizedItem, as the browser connector
does). Once it has, the attachment's parent item is the answer (Zotero's own definition of the recognized item); only
that attachment is looked at, never what else the library gains meanwhile.
  - A parent: the record's saved is {key, version, citationKey, created_at, via: recognizer}. The recognizer renames
    the attachment's file and sets its title (to "PDF"): the title goes back to the label, the file keeps its new
    name. The line prints the item's fields and the PDF's path, for a judge to compare with the PDF's first page.
  - None: the attachment goes to the trash, and the agent writes the record's item by hand (check_item.py --help
    prints a skeleton).
  - Still recognizing after --wait seconds (Zotero's recognizer queued, or offline): nothing is trashed; a rerun waits
    on the same attachment.
The record's `recognize` block is this script's alone: {md5, title, url, sessionID, at, code: sent | recognized |
not_recognized, attachment?}. `sent` is written right before the PDF goes and stays until the recognizer is done: a
rerun finds that attachment by its md5 and waits again with the same sessionID (when Zotero has restarted since and no
longer knows it, the attachment's parent decides at once), or sends the PDF again when Zotero has no such attachment.
Before anything is sent, the library is searched for the PDF's md5: an attachment this record did not send stops it
(in_library).

stdout: one line per record {slug, code, ...}, then {"summary"}.
  recognized      the recognizer made the item: {key, item: its fields, pdf, attachment, retitled?: {from, to},
                  others?}. A judge checks item against the PDF's first page; the agent corrects it with update_item.py
                  and files and tags it with file_and_tag.py; fields that name another paper are set from the PDF's
                  first page the same way (the PDF is this paper's, whatever the recognizer matched)
  ok              --dry-run: what would be sent {pdf, title, url, others?, attachment?: the earlier run's, to wait
                  on}; nothing sent, nothing written
  skipped         reason saved (the record's item is in Zotero) | not_recognized (an earlier run's recognizer found
                  nothing: the agent writes the item by hand; to send the PDF again, remove the record's recognize)
  recognizing     the recognizer is not done after --wait seconds {attachment, pdf}: nothing trashed; rerun later
  not_recognized  the recognizer found nothing {attachment, pdf, canRecognize?: false when Zotero would not try}: the
                  attachment is in the trash; the agent writes the record's item by hand from check_item.py's skeleton
  not_a_stub      the result has metadata: draft_item.py drafts the item, p2z.py save attaches its files
  no_file         the stub has no PDF filed cannot_judge: paper-fetch has not got it yet
  file_changed    the PDF's md5 is not the one in the result: settle the result again, then rerun
  in_library      the PDF is in Zotero already {attachment, parent, parent_title, citationKey}; nothing sent. Under
                  `parent`, the paper is there, nothing to import; parent null, a stray standalone copy: once it is
                  in the trash (trash_item.py), rerun
  no_result | connector_failed | readback_mismatch | unexpected_response | not_found | write_denied |
  write_failed    see the hint
Exit 0 = every record recognized or skipped; 1 = not; 2 = cannot go on (Zotero not running, local API off, no key, the
key rejected, another Zotero than the key's).

Example:
  uv run scripts/recognize.py <scratch>/paper-to-zotero/records/<slug>.json
"""
import uuid

from p2zlib import cli, paper, run, zotero

WAIT = 60  # seconds the recognizer may take
NOT_FIELDS = ("key", "version", "dateAdded", "dateModified", "relations")


def configure(p):
    p.add_argument("--wait", type=float, default=WAIT, metavar="S",
                   help="seconds to wait for the recognizer (default %(default)s)")


def setup(args, records):
    zot = zotero.Zotero(args.base_url)
    if not args.dry_run:
        zot.write_headers()  # the server id and the key, before anything is sent
    return {"zot": zot, "args": args}


def the_pdf(res, path):
    """The stub's PDF -> (file entry, its path, [names of the other candidates]); no_file or file_changed."""
    files = [f for f in res.get("files") or [] if isinstance(f, dict) and f.get("check") == "cannot_judge"
             and str(f.get("name") or "").lower().endswith(".pdf") and f.get("kind") != "supplement"]
    if not files:
        raise cli.Stop("no_file", hint="The stub has no PDF filed cannot_judge: fetch it with paper-fetch, then rerun.")
    f, file = files[0], path.parent / files[0]["name"]
    try:
        md5 = run.md5_of(file)
    except OSError:
        md5 = None
    if md5 != f.get("md5"):
        raise cli.Stop("file_changed", file=str(file), hint="The file is not the one the result lists (gone, or changed "
                                                            "since): settle the result again, then rerun.")
    return f, file, [g["name"] for g in files[1:]]


def source_url(res, f, file):
    """The url Zotero stores on the attachment: the file's, else the request as a DOI link or a web address, else the
    file's own address."""
    given = str((res.get("request") or {}).get("given") or "").strip()
    doi = paper.normalize_doi(given)
    if f.get("url"):
        return f["url"]
    if doi:
        return f"https://doi.org/{doi}"
    return given if given.lower().startswith(("http://", "https://")) else file.absolute().as_uri()


def process(rec, ctx):
    saved = rec.get("saved") if isinstance(rec.get("saved"), dict) else {}
    if saved.get("key"):
        return cli.skipped("saved", key=saved["key"])
    block = rec.get("recognize") if isinstance(rec.get("recognize"), dict) else {}
    if block.get("code") == "not_recognized":
        return cli.skipped("not_recognized", attachment=block.get("attachment"))
    res, path = run.result_of(rec)
    if isinstance(res.get("csl"), dict):
        raise cli.Stop("not_a_stub", hint="The result has metadata: draft_item.py drafts the record's item, and p2z.py "
                                          "save creates it and attaches its files.")
    f, file, others = the_pdf(res, path)
    title = ((f.get("label") or {}).get("title") or "").strip() or paper.label_title("Unknown")
    url = source_url(res, f, file)
    zot, args = ctx["zot"], ctx["args"]
    held = zot.files_by_md5([f["md5"]]).get(f["md5"])
    if held and not (block.get("code") == "sent" and block.get("md5") == f["md5"] and block.get("sessionID")):
        raise cli.Stop("in_library", attachment=held["attachment"], parent=held["parent"], parent_title=held["title"],
                       citationKey=held["citationKey"],
                       hint="This PDF is in Zotero already, on the item `parent` (null: a standalone copy): the paper is "
                            "there, nothing to import, and nothing was sent. A stray standalone copy goes to the trash "
                            "(trash_item.py), then rerun.")
    more = {"others": others} if others else {}
    if args.dry_run:
        return {"code": "ok", "pdf": str(file), "title": title, "url": url,
                **({"attachment": held["attachment"]} if held else {}), **more}
    if held:  # this record's PDF, sent by an earlier run before the recognizer was done
        key, session, recognizable = held["attachment"], block["sessionID"], None
    else:
        session = uuid.uuid4().hex
        rec["recognize"] = {"md5": f["md5"], "title": title, "url": url, "sessionID": session, "at": run.now_iso(),
                            "code": "sent"}
        rec.save()
        try:
            recognizable = zot.save_standalone_attachment(file, title=title, url=url, session=session)
        except cli.Stop as stop:
            if stop.exit != cli.CANNOT:  # Zotero answered: it saved nothing
                rec.pop("recognize")
            raise
        held = zot.files_by_md5([f["md5"]]).get(f["md5"])
        if not held:
            raise cli.Stop("readback_mismatch", hint="Zotero took the PDF, but no attachment holds its md5: look in "
                                                     "Zotero's selected collection before rerunning.")
        key = held["attachment"]
    rec["recognize"]["attachment"] = key
    if not zot.recognizer_done(session, args.wait):
        return {"code": "recognizing", "attachment": key, "pdf": str(file), **more,
                "hint": f"Zotero's recognizer is not done after {args.wait:g} s (queued behind other files, or offline): "
                        "nothing was trashed; rerun later, it waits on the same attachment."}
    parent = zotero.data(zot.item(key)).get("parentItem")
    if not parent:
        zot.trash(key)
        rec["recognize"]["code"] = "not_recognized"
        return {"code": "not_recognized", "attachment": key, "pdf": str(file), **more,
                **({"canRecognize": False} if recognizable is False else {}),
                "hint": "Zotero's recognizer did not identify the PDF; its attachment is in the trash. Write the record's "
                        "item by hand (check_item.py --help prints a skeleton), then p2z.py prepare and save."}
    retitled = {}
    now = zotero.data(zot.item(key)).get("title")
    if now != title:
        zot.retitle(key, title)
        retitled = {"retitled": {"from": now, "to": title}}
    row = zot.item(parent)
    d = zotero.data(row)
    rec["saved"] = {"key": parent, "version": row.get("version"), "citationKey": d.get("citationKey") or None,
                    "created_at": run.now_iso(), "via": "recognizer"}
    rec["recognize"]["code"] = "recognized"
    return {"code": "recognized", "key": parent, "item": {k: v for k, v in d.items() if k not in NOT_FIELDS and v not in ("", [], {}, None)},
            "pdf": str(file), "attachment": key, **retitled, **more}


def main(argv=None):
    return cli.main_records(__doc__, process, argv, configure=configure, setup=setup, zotero=True, dry_run=True,
                            all_valid=True, answers=("recognized",))


if __name__ == "__main__":
    raise SystemExit(main())
