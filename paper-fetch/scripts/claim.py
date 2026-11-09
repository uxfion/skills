#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""How files reach results: claim, scan, watch and downloads, each its own word of pf.py."""
import os
import time
from pathlib import Path

from pflib import cli, paper, run, verify

WATCH_SECONDS = 3.0
SETTLE_SECONDS = 0.5  # scan: the second look, which tells a finished download from a growing one

DOWNLOAD_LINES = """Each file is checked against every result fetch was asked for and that is not satisfied yet:
passing for exactly one -> filed beside it and gone from Downloads; else left there (it may be the user's own), with a
`left` handoff, and checked again only against results wanted after that. Only new files count: newer than <dir>/.started,
complete, a PDF. The Downloads folder is the one pf.py ready recorded in <dir>/run.json.

One line per file filed or left, the event it appended to <dir>/fetch.jsonl: {event: claim, file, slug?, result:
claimed | left, kind?, code (the check's verdict; left: left), md5, source, ..., why?: unmatched | ambiguous,
against?, matched?, handoff?, at}. The results are not changed: pf.py sync brings them in line with the log.
Exit 0; 1 = <dir> is no run's directory (no_work_dir: no results/; no_started: no .started, pf.py ready makes it),
its line on stdout; 2 = no Downloads folder, or no pdftotext, then stderr's last line is {code, hint}."""


def run_dir(value):
    """The run's directory named after the options -> Work; one without results/ or .started -> its line, exit 1."""
    work = run.Work(value)
    if not work.results.is_dir():
        raise cli.Stop("no_work_dir", dir=str(work.root), hint="No results/ there: name the run's directory.")
    if not work.started.exists():
        raise cli.Stop("no_started", dir=str(work.root), hint="No .started there: pf.py ready <dir> makes it.")
    return work


def downloads_dir(work):
    dl = work.settings().get("downloads")
    if not dl:
        raise cli.Stop("no_downloads", exit=cli.CANNOT, hint="run.json names no Downloads folder: pf.py ready <dir> "
                                                             "records it (pf.py ready -h).")
    path = Path(dl).expanduser()
    if not path.is_dir():
        raise cli.Stop("no_downloads", exit=cli.CANNOT, downloads=str(path),
                       hint="The Downloads folder run.json names does not exist: pf.py ready <dir> names another.")
    return path


def dir_parser(fn, sub):
    p = cli.parser(fn.__doc__, sub=sub)
    p.add_argument("dir", nargs="?", metavar="DIR", help="the run's directory, as pf.py ready made it")
    return p


def claim_main(argv):
    """Check files against a result and file each by the verdict: the one way a file reaches a result.

The operand ending in .json is the result; the others are the files, in any order; - reads their paths, a path a
line or our JSON lines by `source` (downloads and claim print it). Each file is checked against the paper: pass ->
filed beside the result; certainly not the paper -> <dir>/unverified/; uncertain -> held there, with a `file` handoff
(pf.py answer; who takes it: SKILL.md, Handoffs). A file of this run (in <dir>, or one of this run's downloads) is
moved; any other (a PDF in Zotero's storage, the user's own) is copied and left where it was.

A file's name says its kind, the version it was wanted as: <slug>.pdf published, .accepted.pdf, .preprint.pdf,
.supplement.pdf, .html snapshot; --as names it, and is the version proposed for its attachment title. What the file
actually is goes into its label. A second file of one kind is numbered (<slug>.2.pdf); a file of the same content as
one beside the result is that file. When it ends, the result's files and outcome are brought in line with the log
(as pf.py sync does).

One line per file as it is checked, the event appended to <dir>/fetch.jsonl: {event: claim, file, slug, result:
claimed | refused | held, kind, code (the check's verdict), md5, source, proposal, evidence, handoff?, at}; a file
that is not there: {file, code: file_not_found}.
Exit 0 = every file filed; 1 = not (refused, held for an agent, not there), then stderr's last line is {"summary":
{total, ok, skipped, failed}}, or the result is not one (result_invalid: its line, no file touched); 2 = no
pdftotext, then each file is not_run and stderr's last line is {code, hint}.

Examples:
  pf.py claim ~/Downloads/x.pdf <dir>/results/liu2022jbhi.json
  pf.py claim --as accepted <dir>/results/liu2022jbhi.json <dir>/scratch/manuscript.pdf
"""
    p = cli.parser(claim_main.__doc__, sub="claim")
    p.usage = f"{p.prog} [-h] [--as KIND] FILE... RESULT"
    p.add_argument("operands", nargs="*", metavar="FILE... RESULT",
                   help="the files, - reading their paths from stdin, and the result: <dir>/results/<slug>.json")
    p.add_argument("--as", dest="as_", choices=list(paper.KINDS), help="the files' kind, when their names do not say")
    args = cli.parse(p, argv)
    result, files = cli.split_result(p, args.operands)
    if not files:
        p.error("name the files to claim, or - to read their paths from stdin")

    def go():
        try:
            res = run.read(result)
        except cli.Stop as stop:
            cli.emit(stop.line(slug=Path(result).stem))
            return cli.ACT
        work, out, checked = res.work, cli.Lines(), False
        named = cli.paths(files, field="source")
        if any(isinstance(f, str) for f in named):
            try:
                verify.require_pdftotext()
            except cli.Stop as stop:
                out.stop(stop)
        for f in named:
            if isinstance(f, dict):
                out.put(f)
            elif out.stopped is not None:
                out.put({"file": f, "code": "not_run"})
            elif not Path(f).is_file():
                out.put({"file": f, "code": "file_not_found", "hint": "No such file."})
            else:
                event = run.claim(work, f, res.slug, kind=args.as_, source=str(Path(f).absolute()),
                                  came={"given": args.as_}, consume=work.owns(f))
                out.put(event, "ok" if event["result"] == "claimed" else "failed")
                checked = True
        if checked:
            run.settle(work, [run.read(res.path)])
        return out.finish()

    return cli.run(go)


def scan_main(argv):
    return look(argv, scan_main, "scan", once=True)


scan_main.__doc__ = f"""File the new downloads once: each checked against the results still waiting for their file.

{DOWNLOAD_LINES}

Example:
  pf.py scan <dir>
"""


def watch_main(argv):
    return look(argv, watch_main, "watch", once=False)


watch_main.__doc__ = f"""File new downloads as they land, until stopped: one per run, in the background; wait is one paper's.

It looks every few seconds until <dir> goes or the process is stopped, and keeps its pid in <dir>/run.json, where
fetch and wait see it running and leave Downloads to it.

{DOWNLOAD_LINES}

Example:
  pf.py watch <dir>        # in the background, the whole run
"""


def look(argv, fn, sub, once):
    p = dir_parser(fn, sub)
    args = cli.parse(p, argv)
    if not args.dir:
        p.error("name the run's directory")

    def go():
        work = run_dir(args.dir)
        dl = downloads_dir(work)
        verify.require_pdftotext()
        if not once:
            work.set(watcher=os.getpid())
        scanner = run.Scanner(work, dl)
        scanner.scan()  # the first look: every file seen once, judged complete or not on the next
        try:
            while True:
                time.sleep(SETTLE_SECONDS if once else WATCH_SECONDS)
                for event in scanner.scan():
                    cli.emit(event if "code" in event else {**event, "code": event["result"]})
                if once or not work.results.is_dir():
                    break
        except KeyboardInterrupt:
            pass
        finally:
            if not once and work.root.is_dir() and work.settings().get("watcher") == os.getpid():
                work.set(watcher=None)
        return cli.OK

    return cli.run(go)


def downloads_main(argv):
    """The files this run left in Downloads, each with its md5 and size: read-only.

The files newer than <dir>/.started in the Downloads folder pf.py ready recorded: at the end of a run, what is still
there. Whether a caller's library holds one is the caller's to say (p2z.py have -). One line per file, oldest first:
{event: claim, file, result: left, why: sweep, md5, size, source: its full path, at}; nothing is logged.
Exit 0, files or none (count them with wc -l); 1 = <dir> is no run's directory (no_work_dir, no_started), its line on
stdout; 2 = no Downloads folder, then stderr's last line is {code, hint}.

Examples:
  pf.py downloads <dir> | wc -l
  pf.py downloads <imp>/fetch | jq -r .source | p2z.py have -
"""
    p = dir_parser(downloads_main, "downloads")
    args = cli.parse(p, argv)
    if not args.dir:
        p.error("name the run's directory")

    def go():
        work = run_dir(args.dir)
        for f in run.new_downloads(work, downloads_dir(work)):
            cli.emit({"event": "claim", "file": f.name, "result": "left", "why": "sweep", "md5": run.md5_of(f),
                      "size": f.stat().st_size, "source": str(f), "at": run.now_iso()})
        return cli.OK

    return cli.run(go)


COMMANDS = {"claim": claim_main, "scan": scan_main, "watch": watch_main, "downloads": downloads_main}


def main(argv=None):
    name, rest = cli.subcommand(__doc__, COMMANDS, argv)
    return COMMANDS[name](rest)


if __name__ == "__main__":
    raise SystemExit(main())
