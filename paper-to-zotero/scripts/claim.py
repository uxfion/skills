#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The one way a file reaches a record: check it against the paper, then file it beside the record.

  --file F --slug S          a file got for one record: checked against it; passing -> filed, failing -> moved to
                             <work>/unverified/<slug>.file.<ext> for the agent to look at
  --accept F --slug S --reason R
                             a file the check refused that the agent read and judged to be the paper: filed
                             unchecked, its md5 and the reason logged (attach_file.py attaches it on that word)
  --scan                     the new files in the browser's Downloads (newer than <work>/.started, complete, a PDF),
                             whoever started them: each is checked against every record whose library item has no
                             PDF yet; one match -> filed and gone from Downloads, none or several -> left there
                             (it may be the user's own), checked again only against records drafted after that
  --watch                    --scan every few seconds until the work directory goes or the process is stopped; run
                             it in the background while the browser is in use (its pid is kept in run.json)
  --sweep                    end of run: what this run left in Downloads, each with whether the library holds it

The file's name says its kind (paper.KINDS): <slug>.pdf published, .accepted.pdf, .preprint.pdf, .supplement.pdf,
.html snapshot. --version names it; without, a published-looking file with arXiv's margin stamp on page 1 is a
preprint. Filing is first come, first served: a record that has its file already sends the copy to <work>/stray/.
Downloads is the folder ready.py found (run.json), or --downloads DIR.

Every outcome is an event appended to <work>/fetch.jsonl and printed: {event: claim | accept, file, slug?,
result: claimed | stray | unverified | left, kind?, code? (the check's verdict), md5, source?, at}; a left file also
{why: unmatched | ambiguous | sweep, against?, matched?}; --sweep adds {in_library, attachment?, citationKey?}.
Exit 0 = done (--file / --accept: filed); 1 = --file / --accept not filed (unverified, stray); 2 = cannot go on
(no work directory, no .started, no Downloads folder, no pdftotext, Zotero unreachable for --sweep).

Examples:
  uv run scripts/claim.py --work W --watch                # in the background
  uv run scripts/claim.py --work W --file F --slug S
  uv run scripts/claim.py --work W --accept W/unverified/S.file.pdf --slug S --reason "title page is a scan"
  uv run scripts/claim.py --work W --sweep
"""
import os
import time
from pathlib import Path

from p2zlib import cli, paper, run, verify, zotero

WATCH_SECONDS = 3.0


def downloads(work, given):
    path = Path(given or work.settings().get("downloads") or "").expanduser()
    if not (given or work.settings().get("downloads")):
        raise cli.Stop("no_downloads", exit=cli.CANNOT, hint="ready.py --work records the Downloads folder; or pass --downloads DIR.")
    if not path.is_dir():
        raise cli.Stop("no_downloads", exit=cli.CANNOT, hint="The Downloads folder does not exist.", downloads=str(path))
    return path


def sweep(work, dl, base_url):
    files = {f: run.md5_of(f) for f in run.new_downloads(work, dl)}
    held = zotero.Zotero(base_url).files_by_md5(list(files.values())) if files else {}
    for f, md5 in files.items():
        hit = held.get(md5) or {}
        cli.emit(work.append({"event": "claim", "file": f.name, "result": "left", "why": "sweep", "md5": md5, "source": str(f),
                          "in_library": bool(hit), "attachment": hit.get("attachment"), "citationKey": hit.get("citationKey")}))


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("--work", required=True, metavar="DIR", help="the work directory (ready.py --work)")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--file", metavar="F", help="a file got for --slug: check it and file it")
    mode.add_argument("--accept", metavar="F", help="a file the check refused, judged to be the paper: file it (--reason)")
    mode.add_argument("--scan", action="store_true", help="claim the new files in Downloads once")
    mode.add_argument("--watch", action="store_true", help="--scan in a loop")
    mode.add_argument("--sweep", action="store_true", help="list what this run left in Downloads")
    p.add_argument("--slug", help="with --file / --accept: the record")
    p.add_argument("--reason", help="with --accept: why the file is the paper")
    p.add_argument("--version", choices=list(paper.KINDS), help="with --file / --accept: the file's kind")
    p.add_argument("--downloads", metavar="DIR", help="the browser's Downloads folder (default: run.json's)")
    cli.add_base_url(p)
    args = p.parse_args(argv)
    if (args.file or args.accept) and not args.slug:
        p.error("--file and --accept name the record with --slug")
    if args.accept and not args.reason:
        p.error("--accept needs --reason")
    work = run.Work(args.work)

    def go():
        if not work.records.is_dir():
            raise cli.Stop("no_work_dir", exit=cli.CANNOT, hint="The work directory has no records/: run ready.py --work first.")
        if args.file or args.accept:
            if args.file:
                verify.require_pdftotext()
                if not Path(args.file).is_file():
                    raise cli.Stop("file_not_found", hint="No such file.", file=args.file)
                event = run.claim(work, args.file, args.slug, kind=args.version, source=str(Path(args.file).absolute()))
            else:
                event = run.accept(work, args.accept, args.slug, args.reason, kind=args.version)
            cli.emit(event)
            return cli.OK if event["result"] == "claimed" else cli.ACT
        dl = downloads(work, args.downloads)
        if args.sweep:
            sweep(work, dl, args.base_url)
            return cli.OK
        verify.require_pdftotext()
        if args.watch:
            work.set(watcher=os.getpid())
        try:
            while True:
                for event in run.scan_downloads(work, dl):
                    cli.emit(event)
                if args.scan or not work.records.is_dir():
                    break
                time.sleep(WATCH_SECONDS)
        except KeyboardInterrupt:
            pass
        finally:
            if args.watch and work.root.is_dir() and work.settings().get("watcher") == os.getpid():
                work.set(watcher=None)
        return cli.OK

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
