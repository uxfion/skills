#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Wait at a gate: look at the record's file and the browser's current tab every 10 seconds, and nothing else.

It ends on whichever comes first:
  arrived   the record's file is there (the watcher filed it, or this wait while no watcher runs; whoever downloaded it)
  passed    the page shows --until (text, or a CSS selector), or without --until its url or title changed
  timeout   --timeout seconds (default 300) went by
It records nothing: after a timeout the agent writes its conclusion with fetch.py --verdict gate_timeout. --file-only
leaves the page alone (the last pass, with the user at it). It navigates nowhere; the session is run.json's. A login
from another window changes nothing in this tab: the user's word, or the file, ends that wait.

stdout: one line {slug, code, url?, title?}. Exit 0 = arrived or passed; 1 = timeout.

Example:
  uv run scripts/wait.py <work>/records/<slug>.json --until "Access provided by"
"""
import time
from pathlib import Path

from p2zlib import cli, run
from p2zlib.browser import Browser

STEP = 10.0


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("record", metavar="RECORD")
    p.add_argument("--until", metavar="TEXT", help="text or CSS selector only the page past the gate shows")
    p.add_argument("--timeout", type=float, default=300.0, metavar="SECONDS", help="(default: %(default)s)")
    p.add_argument("--file-only", action="store_true", help="wait for the file alone; the page is not read")
    args = p.parse_args(argv)

    def go():
        rec = run.read(args.record)
        work = run.Work.of(rec.path)
        b, first = Browser(work.settings().get("session") or "p2z"), None
        dl = work.settings().get("downloads")
        scanner = run.Scanner(work, dl) if dl and Path(dl).is_dir() else None
        deadline = time.monotonic() + args.timeout
        while True:
            if scanner and not run.watcher_alive(work):  # no watcher: this wait files a download itself
                scanner.scan()
            got = work.file_of(rec.slug)
            if got:
                cli.emit({"slug": rec.slug, "code": "arrived", "file": got.name})
                return cli.OK
            if not args.file_only:
                page = b.watch(args.until)
                seen = (page.get("href"), page.get("title"))
                if page and (page.get("found") or (not args.until and first is not None and seen != first)):
                    cli.emit({"slug": rec.slug, "code": "passed", "url": seen[0], "title": seen[1]})
                    return cli.OK
                first = first or (seen if page else None)
            left = deadline - time.monotonic()
            if left <= 0:
                cli.emit({"slug": rec.slug, "code": "timeout", "waited": args.timeout,
                          "hint": "Leave this tab to the user, open a new tab, record fetch.py --verdict gate_timeout and "
                                  "take the paper's next route."})
                return cli.ACT
            time.sleep(min(STEP, left))

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
