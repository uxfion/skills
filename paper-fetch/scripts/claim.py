#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The one way a file reaches a result: check it against the paper and act on the verdict.

  --file F --slug S          a file got for one result (a paper's agent hands over a file it downloaded itself):
                             checked against it; pass -> filed beside the result; certainly not the paper ->
                             <dir>/unverified/<slug>.file.<ext>; uncertain -> held there, with a `file` handoff for
                             the paper's agent (pf.py answer)
  --scan                     the new files in the browser's Downloads (newer than <dir>/.started, complete, a PDF),
                             whoever started them: each is checked against every result fetch was asked for and that
                             is not satisfied yet; passing for exactly one -> filed and gone from Downloads; else left
                             there (it may be the user's own), with a `left` handoff, and checked again only against
                             results wanted after that
  --watch                    --scan every few seconds until the directory goes or the process is stopped; run
                             it in the background while the browser is in use (its pid is kept in run.json)
  --sweep                    end of run: what this run left in Downloads (newer than .started), each with its md5 and
                             size; whether the library holds one is paper-to-zotero's to say (find_in_library --file)

--file consumes only this run's files: one in the directory or one of this run's downloads is moved; any other (a PDF
in Zotero's storage, the user's own) is copied and left where it was. An agent's answers — accepting a held file,
labelling one, claiming a left one — go through pf.py answer.

The file's name says its kind, the version it was wanted as (paper.KINDS): <slug>.pdf published, .accepted.pdf,
.preprint.pdf, .supplement.pdf, .html snapshot; --version names it, and is the version proposed for its attachment
title. What the file actually is goes into its label. A second file of one kind is numbered (<slug>.2.pdf); a file of
the same content as one beside the result is that file. Downloads is the folder ready.py found (run.json), or
--downloads DIR.

Every outcome is an event appended to <dir>/fetch.jsonl and printed: {event: claim, file, slug?, result: claimed |
refused | held | left, kind?, code? (the check's verdict), md5, source?, route?, proposal?, evidence?, handoff?, at}
(proposal and evidence: pflib/run.py); a left file also {why: unmatched | ambiguous | sweep, against?, matched?};
--sweep adds {size}, its file's path is `source`. --file folds the result it touched into its files when it ends
(settle.py); --scan and --watch only append events, and settle.py folds after them.
Exit 0 = done (--file: filed); 1 = --file not filed (refused, or held for the agent); 2 = cannot go on (no results/
in the directory, no .started, no Downloads folder, no pdftotext).

Examples:
  uv run scripts/claim.py --dir <dir> --watch                # in the background
  uv run scripts/claim.py --dir <dir> --file F --slug S
  uv run scripts/claim.py --dir <dir> --sweep
"""
import os
import time
from pathlib import Path

from pflib import cli, paper, run, verify

WATCH_SECONDS = 3.0
SETTLE_SECONDS = 0.5  # --scan: the second look, which tells a finished download from a growing one


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
    mode.add_argument("--file", metavar="F", help="a file got for --slug: check it and act on the verdict")
    mode.add_argument("--scan", action="store_true", help="claim the new files in Downloads once")
    mode.add_argument("--watch", action="store_true", help="--scan in a loop")
    mode.add_argument("--sweep", action="store_true", help="list what this run left in Downloads")
    p.add_argument("--slug", help="with --file: the result")
    p.add_argument("--version", choices=list(paper.KINDS), help="with --file: the file's kind")
    p.add_argument("--downloads", metavar="DIR", help="the browser's Downloads folder (default: run.json's)")
    args = p.parse_args(argv)
    if not (args.file or args.scan or args.watch or args.sweep):
        p.error("one of --file, --scan, --watch, --sweep is required")
    if args.file and not args.slug:
        p.error("--file names the result with --slug")
    work = run.Work(args.dir)

    def go():
        if not work.results.is_dir():
            raise cli.Stop("no_work_dir", exit=cli.CANNOT, hint="The directory has no results/: run ready.py first.")
        if args.file:
            verify.require_pdftotext()
            if not Path(args.file).is_file():
                raise cli.Stop("file_not_found", hint="No such file.", file=args.file)
            event = run.claim(work, args.file, args.slug, kind=args.version, source=str(Path(args.file).absolute()),
                              came={"given": args.version}, consume=work.owns(args.file))
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
