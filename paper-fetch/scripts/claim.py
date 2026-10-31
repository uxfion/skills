#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The one way a file reaches a result: check it against the paper, then file it beside the result; and its label.

  --file F --slug S          a file got for one result: checked against it; passing -> filed, failing -> moved to
                             <dir>/unverified/<slug>.file.<ext> for the agent to look at
  --accept F --slug S --reason R
                             a file the check refused that the agent read and judged to be the paper: filed
                             unchecked, its md5 and the reason logged (paper-to-zotero attaches the result's files)
  --label TITLE --why WHY --slug S [--file NAME] [--by agent | subagent | browser_agent]
                             the attachment title the agent gives one of the result's files (NAME, or its path;
                             default the paper's own file, not a supplement), with why; the scheme is
                             references/attachment-titles.md, and a title outside it is bad_label
  --scan                     the new files in the browser's Downloads (newer than <dir>/.started, complete, a PDF),
                             whoever started them: each is checked against every result a route was tried for and
                             that has no file yet; one match -> filed and gone from Downloads, none or several -> left
                             there (it may be the user's own), checked again only against results wanted after that
  --watch                    --scan every few seconds until the directory goes or the process is stopped; run
                             it in the background while the browser is in use (its pid is kept in run.json)
  --sweep                    end of run: what this run left in Downloads (newer than .started), each with its md5 and
                             size; whether the library holds one is paper-to-zotero's to say (find_in_library --file)

--file and --accept consume only this run's files: one in the directory or one of this run's downloads is moved; any
other (a PDF in Zotero's storage, the user's own) is copied and left where it was.

The file's name says its kind, the version it was wanted as (paper.KINDS): <slug>.pdf published, .accepted.pdf,
.preprint.pdf, .supplement.pdf, .html snapshot; --version names it, and is the version proposed for its attachment
title. What the file actually is goes into its label (--label). Filing is first come, first served: a result that
has the paper's file already sends another to <dir>/stray/ (a supplement has a place of its own beside it, one
per result). Downloads is the folder ready.py found (run.json), or
--downloads DIR.

Every outcome is an event appended to <dir>/fetch.jsonl and printed: {event: claim | accept, file, slug?,
result: claimed | stray | unverified | left, kind?, code? (the check's verdict), md5, source?, route?, proposal?,
evidence?, at} (proposal and evidence: pflib/run.py); a left file also {why: unmatched | ambiguous | sweep,
against?, matched?}; --sweep adds {size}, its file's path is `source`. --label: {event: label, slug, file, title,
why, by, at}. --file, --accept and --label fold the result they touched into its file when they end (settle.py);
--scan and --watch only append events, and settle.py folds after them.
Exit 0 = done (--file / --accept: filed); 1 = --file / --accept not filed (unverified, stray), or --label refused
(bad_label, no_such_file); 2 = cannot go on (no results/ in the directory, no .started, no Downloads folder, no
pdftotext).

Examples:
  uv run scripts/claim.py --dir <dir> --watch                # in the background
  uv run scripts/claim.py --dir <dir> --file F --slug S
  uv run scripts/claim.py --dir <dir> --accept <dir>/unverified/S.file.pdf --slug S --reason "title page is a scan"
  uv run scripts/claim.py --dir <dir> --label Accepted-arXiv-v3 --why "v3's comment: Accepted at CVPR 2024" --slug S
  uv run scripts/claim.py --dir <dir> --sweep
"""
import os
import time
from pathlib import Path

from pflib import cli, paper, run, verify

WATCH_SECONDS = 3.0
SETTLE_SECONDS = 0.5  # --scan: the second look, which tells a finished download from a growing one
BY = ("agent", "subagent", "browser_agent")


def downloads(work, given):
    path = Path(given or work.settings().get("downloads") or "").expanduser()
    if not (given or work.settings().get("downloads")):
        raise cli.Stop("no_downloads", exit=cli.CANNOT,
                       hint="ready.py records the Downloads folder; or pass --downloads DIR.")
    if not path.is_dir():
        raise cli.Stop("no_downloads", exit=cli.CANNOT, hint="The Downloads folder does not exist.",
                       downloads=str(path))
    return path


def sweep(work, dl):
    for f in run.new_downloads(work, dl):
        cli.emit(work.append({"event": "claim", "file": f.name, "result": "left", "why": "sweep",
                              "md5": run.md5_of(f), "size": f.stat().st_size, "source": str(f)}))


def fold(work, slug):
    """Write the result's files and outcome from the log (settle.py's fold, for the one result touched)."""
    run.settle(work, [run.read(work.results / f"{slug}.json")])


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("--dir", required=True, metavar="DIR", help="paper-fetch's directory (<dir>/results/<slug>.json)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--accept", metavar="F",
                      help="a file the check refused, judged to be the paper: file it (--reason)")
    mode.add_argument("--label", metavar="TITLE", help="the attachment title of one of the result's files (--why)")
    mode.add_argument("--scan", action="store_true", help="claim the new files in Downloads once")
    mode.add_argument("--watch", action="store_true", help="--scan in a loop")
    mode.add_argument("--sweep", action="store_true", help="list what this run left in Downloads")
    p.add_argument("--file", metavar="F", help="a file got for --slug: check it and file it; with --label: the "
                   "result's file the title is for (its name or path; default the paper's own)")
    p.add_argument("--slug", help="with --file / --accept / --label: the result")
    p.add_argument("--reason", help="with --accept: why the file is the paper")
    p.add_argument("--why", help="with --label: what on the file or its page says so")
    p.add_argument("--by", choices=BY, default="agent", help="with --label: who read it (default agent)")
    p.add_argument("--version", choices=list(paper.KINDS), help="with --file / --accept: the file's kind")
    p.add_argument("--downloads", metavar="DIR", help="the browser's Downloads folder (default: run.json's)")
    args = p.parse_args(argv)
    filing, labelling = args.file is not None, args.label is not None
    if not (filing or labelling or args.accept is not None or args.scan or args.watch or args.sweep):
        p.error("one of --file, --accept, --label, --scan, --watch, --sweep is required")
    if filing and not labelling and (args.accept is not None or args.scan or args.watch or args.sweep):
        p.error("--file goes alone, or with --label")
    if (filing or labelling or args.accept is not None) and not args.slug:
        p.error("--file, --accept and --label name the result with --slug")
    if args.accept is not None and not args.reason:
        p.error("--accept needs --reason")
    if labelling and not args.why:
        p.error("--label needs --why")
    work = run.Work(args.dir)

    def go():
        if not work.results.is_dir():
            raise cli.Stop("no_work_dir", exit=cli.CANNOT, hint="The directory has no results/: run ready.py first.")
        if labelling:
            event = run.label(work, args.slug, args.label, args.why, by=args.by,
                              file=Path(args.file).name if filing else None)
            cli.emit(event)
            fold(work, args.slug)
            return cli.OK
        if filing or args.accept is not None:
            if filing:
                verify.require_pdftotext()
                if not Path(args.file).is_file():
                    raise cli.Stop("file_not_found", hint="No such file.", file=args.file)
                event = run.claim(work, args.file, args.slug, kind=args.version, source=str(Path(args.file).absolute()),
                                  came={"given": args.version}, consume=work.owns(args.file))
            else:
                event = run.accept(work, args.accept, args.slug, args.reason, kind=args.version,
                                   consume=work.owns(args.accept))
            cli.emit(event)
            fold(work, args.slug)
            return cli.OK if event["result"] == "claimed" else cli.ACT
        dl = downloads(work, args.downloads)
        if args.sweep:
            sweep(work, dl)
            return cli.OK
        verify.require_pdftotext()
        if args.watch:
            work.set(watcher=os.getpid())
        scanner = run.Scanner(work, dl)
        scanner.scan()  # the first look: every file seen once, judged complete or not on the next
        try:
            while True:
                time.sleep(SETTLE_SECONDS if args.scan else WATCH_SECONDS)
                for event in scanner.scan():
                    cli.emit(event)
                if args.scan or not work.results.is_dir():
                    break
        except KeyboardInterrupt:
            pass
        finally:
            if args.watch and work.root.is_dir() and work.settings().get("watcher") == os.getpid():
                work.set(watcher=None)
        return cli.OK

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
