#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Wait at a gate: look at the result's file and the gate's tab every 10 seconds, and at the gate afresh every minute.

It ends on whichever comes first:
  arrived   the paper has its file (run.satisfied: the watcher filed it, or this wait while no watcher runs; whoever
            downloaded it)
  passed    seen: tab — the gate's tab shows --until (text, or a CSS selector), or without --until its url or title
            changed (the user passed it there); seen: fresh — the gate's address, opened afresh in a tab of the wait's
            own (session <session>-probe, closed at the end), shows --until or another title (the user signed in from
            another window, which leaves the gate's tab as it was): open the page again in the session and go on
  timeout   --timeout seconds (default 570: just under ten minutes, so that one shell call holds it) went by
It records nothing: after a timeout the paper's agent answers its page handoff gate_timeout (pf.py answer). --file-only
leaves the page alone (the last pass, with the user at it). It never navigates the gate's tab; the session is
--session (a paper's agent: pf-<slug>), else run.json's. When it ends it folds the result (and any other its scan of
Downloads filed a file for) into their files and outcome, as settle.py does.

stdout: one line {slug, code, seen?, url?, title?}. Exit 0 = arrived or passed; 1 = timeout.

Example:
  uv run scripts/wait.py <dir>/results/<slug>.json --until "Access provided by"
"""
import time
from pathlib import Path

from pflib import cli, run
from pflib.browser import Browser

STEP = 10.0
PROBE = 60.0  # seconds between fresh looks at the gate


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("result", metavar="RESULT", help="the result file: <dir>/results/<slug>.json")
    p.add_argument("--until", metavar="TEXT", help="text or CSS selector only the page past the gate shows")
    p.add_argument("--timeout", type=float, default=570.0, metavar="SECONDS", help="(default: %(default)s)")
    p.add_argument("--file-only", action="store_true", help="wait for the file alone; the page is not read")
    p.add_argument("--session", metavar="NAME", help="the opencli session whose tab is read (default run.json's)")
    args = p.parse_args(argv)

    def watch(res, work, filed):
        session = args.session or work.settings().get("session") or "pf"
        b, probe, first = Browser(session), Browser(f"{session}-probe"), None
        dl = work.settings().get("downloads")
        scanner = run.Scanner(work, dl) if dl and Path(dl).is_dir() else None
        deadline, next_look = time.monotonic() + args.timeout, time.monotonic() + PROBE
        try:
            while True:
                if scanner and not run.watcher_alive(work):  # no watcher: this wait files a download itself
                    filed.update(e["slug"] for e in scanner.scan() if e.get("slug"))
                if run.satisfied(work, res):
                    got = run.paper_file(work, res)
                    cli.emit({"slug": res.slug, "code": "arrived", "file": got.name if got else None})
                    return cli.OK
                if not args.file_only:
                    seen = (b.get("url"), b.get("title"))
                    if seen[0] and (b.shows(args.until) if args.until else first is not None and seen != first):
                        cli.emit({"slug": res.slug, "code": "passed", "seen": "tab", "url": seen[0], "title": seen[1]})
                        return cli.OK
                    first = first or (seen if seen[0] else None)
                    if first and time.monotonic() >= next_look:  # a login in another window leaves the tab as it was
                        next_look = time.monotonic() + PROBE
                        if probe.open(first[0]) is None:
                            fresh = (probe.get("url"), probe.get("title"))
                            if fresh[0] and (probe.shows(args.until) if args.until else fresh[1] != first[1]):
                                cli.emit({"slug": res.slug, "code": "passed", "seen": "fresh", "url": fresh[0],
                                          "title": fresh[1]})
                                return cli.OK
                left = deadline - time.monotonic()
                if left <= 0:
                    cli.emit({"slug": res.slug, "code": "timeout", "waited": args.timeout,
                              "hint": "Leave this tab to the user, answer the paper's page handoff gate_timeout (pf.py "
                                      "answer): the paper is tried again at the next pass."})
                    return cli.ACT
                time.sleep(min(STEP, left))
        finally:
            if probe.opened:
                probe.run("close")

    def go():
        res = run.read(args.result)
        work, filed = res.work, set()
        try:
            return watch(res, work, filed)
        finally:  # the result, and any other a scan filed a file for, say what came
            run.settle(work, [res] + [run.read(work.results / f"{s}.json") for s in sorted(filed - {res.slug})
                                      if (work.results / f"{s}.json").is_file()])

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
