#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Answer a handoff: the one way an agent's conclusion reaches the run's directory.

HANDOFF is the handoff's file, <dir>/handoffs/<id>.json, the `path` fetch, claim and todo print. What each kind takes
(pflib/run.py, Handoffs):
  page          a verdict (run.VERDICTS): no_access, no_pdf, not_public, proxy_unconfigured, skipped_by_user — the
                paper goes on to its next route; blocked, gate_timeout — it waits on this route until the next pass.
                A page the agent got past needs no answer: hand it back with `pf.py fetch --start <url> --session …`,
                and the file that arrives closes it.
  file          accept [--label TITLE --why WHY] (filed, labelled when a title is given; --as when its name does not
                say the version) | refuse (not the paper: the paper goes on) | unknown (cannot tell: filed
                unconfirmed, the paper goes on, a confirmed file replaces it later)
  label         label --label TITLE --why WHY (the scheme: references/attachment-titles.md) | unknown
                (Unknown-<Source>, which leaves the paper going on to the wanted version)
  left          claim --slug S (the download is that paper's: its slug, or its citation key) | not_ours
  browser_down  resolved
Every answer is logged ({event: answer, id, slug, kind, answer, reason, by}) with what it did (accept, label, try),
and the paper's result brought in line with the log (as pf.py sync does). --reason says what the answer rests on.

One line per event written, the answer last, each with `code`: the event's result (an accept's claimed, a page
verdict's word), else ok.
Exit 0 = recorded; 1 = refused, its line on stdout (bad_answer, not_open, no_such_handoff, bad_label, no_label,
no_slug, file_not_found, no_such_file); 2 = a usage error.

Examples:
  pf.py answer <dir>/handoffs/he2020mask.1.json accept --reason "page 1: TPAMI 42(2), Mask R-CNN, He et al." --label Published-IEEE --why "page 1 header: vol. 42 no. 2"
  pf.py answer <dir>/handoffs/liu2022jbhi.2.json no_access --reason "the publisher page says the institution has no access"
"""
from pathlib import Path

from pflib import cli, paper, run

BY = ("agent", "paper_agent", "judge", "user")


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("handoff", metavar="HANDOFF", help="the handoff's file: <dir>/handoffs/<id>.json")
    p.add_argument("answer", metavar="ANSWER", help="what the kind takes (above)")
    p.add_argument("--reason", help="what the answer rests on")
    p.add_argument("--label", metavar="TITLE", help="file / label: the attachment title")
    p.add_argument("--why", help="with --label: what on the file or its page says so")
    p.add_argument("--slug", help="left: the paper the download is for, by its slug or citation key")
    p.add_argument("--as", dest="as_", choices=list(paper.KINDS),
                   help="file / left: the file's kind, when its name does not say")
    p.add_argument("--by", choices=BY, default="agent", help="who answers (default agent)")
    args = cli.parse(p, argv)
    if args.label and not args.why:
        p.error("--label needs --why")
    target = Path(args.handoff).absolute()
    work = run.Work(target.parent.parent)

    def go():
        events = run.answer(work, target.stem if target.suffix == ".json" else target.name, args.answer,
                            reason=args.reason, title=args.label, why=args.why, slug=args.slug, version=args.as_,
                            by=args.by)
        for event in events:
            cli.emit(event if "code" in event else {**event, "code": event.get("result") or "ok"})
        slug = events[-1].get("slug")
        if slug and (work.results / f"{slug}.json").is_file():
            run.settle(work, [run.read(work.results / f"{slug}.json")])
        return cli.OK

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
