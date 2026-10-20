#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Attach each record's file to its Zotero item: the record's `attach`.

The item is the one this run created (saved.key), else the one the lookup confirmed (found.key); never a near match.
The file is the record's own: <work>/records/<slug>.pdf, .accepted.pdf, .preprint.pdf, .supplement.pdf or .html;
its name gives its kind and the attachment's title (PDF, Accepted manuscript, Preprint (<server>: where the file came
from, by fetch.jsonl), Supplementary material, Snapshot). Before the upload the file is checked against the record (verify, as claim does), unless the
agent accepted this very file (claim.py --accept: its md5 in fetch.jsonl). A child of the item already holding the
file (same md5) settles it without an upload, and an empty attachment left by a cut-off run is reused. The source url
is the item's url (a proxied url turned back into the publisher's), else its DOI link. Then `attach: {attachment,
md5, kind, title, filename, url, at}`; another file later (another md5) is attached afresh.

stdout: one line per record {slug, code, key?, attachment?, kind?, title?}, then {"summary"}.
  ok          attached (with --dry-run: would be; nothing written)
  skipped     reason no_file_yet (fetch it first: not a failure, so save can run after every pass) | attached (this
              file is the record's `attach`) | already_attached (the item had it)
  no_item_key the record has no item in Zotero yet (create_item; a possible duplicate is the agent's to settle)
  not_verified the file does not pass the check against the record (`verdict`): fetch the right file, or accept
              this one with claim.py --accept
  not_found | not_a_parent | unsupported_file | readback_mismatch | unexpected_response | write_denied |
  write_failed    see the hint
Exit 0 = every record attached or skipped; 1 = not; 2 = cannot go on (Zotero not running, local API off, no key, the
key rejected, another Zotero than the key's, no pdftotext).

Example:
  uv run scripts/attach_file.py <work>/records/*.json
"""
from p2zlib import cli, config, paper, run, verify, web, zotero


def setup(args, records):
    zot = zotero.Zotero(args.base_url)
    if not args.dry_run:
        zot.write_headers()
    return {"zot": zot, "args": args, "proxy": config.institution()["proxy"], "cache": {}}


def process(rec, ctx):
    work, path = rec.work, rec.file()
    if path is None:
        return cli.skipped("no_file_yet")
    md5 = run.md5_of(path)
    if (rec.get("attach") or {}).get("md5") == md5:
        return cli.skipped("attached", attachment=rec["attach"]["attachment"])
    key = run.item_key(rec)
    if key is None:
        return {"code": "no_item_key", "hint": "The record has no item in Zotero yet: create_item.py (p2z.py save) makes it; "
                                               "a possible duplicate is settled with same_as or distinct_from first."}

    def check(parent):
        if run.accepted(work, rec.slug, md5):
            return
        verify.require_pdftotext()
        verdict = verify.check(path, rec, cache=ctx["cache"])
        if verdict["code"] not in verify.PASS_CODES:
            raise cli.Stop("not_verified", verdict=verdict["code"], hint=verify.HINTS.get(verdict["code"]) or
                           "The file does not pass the check; see check_pdf.py for the evidence.")

    url = rec.item.get("url") or (f"https://doi.org/{paper.doi_of(rec.item)}" if paper.doi_of(rec.item) else None)
    url = web.unproxy(url, ctx["proxy"]) if url else None
    came = next((e for e in reversed(work.events()) if e.get("event") in ("claim", "accept") and e.get("slug") == rec.slug
                 and e.get("md5") == md5), {})
    server = paper.preprint_server(came.get("source") or "")  # a preprint's title names where the file came from
    res = ctx["zot"].attach(key, path, url=url, server=server, verify=check, dry_run=ctx["args"].dry_run)
    line = {"key": key, **{k: res.get(k) for k in ("attachment", "kind", "title")}}
    if res["code"] == "skipped" or not res.get("dry_run"):
        rec["attach"] = {"attachment": res["attachment"], "md5": md5, "kind": res["kind"], "title": res["title"],
                         "filename": res["filename"], "url": url, "at": run.now_iso()}
    return {"code": res["code"], **({"reason": res["reason"]} if res.get("reason") else {}), **line}


def main(argv=None):
    return cli.main_records(__doc__, process, argv, setup=setup, zotero=True, dry_run=True, all_valid=True)


if __name__ == "__main__":
    raise SystemExit(main())
