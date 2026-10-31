#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Answer a handoff: the one way an agent's conclusion reaches paper-fetch's directory.

  pf.py answer HANDOFF ANSWER [--reason R] [--label TITLE --why WHY] [--slug S] [--version V] [--by WHO]

HANDOFF is the handoff's file (<dir>/handoffs/<id>.json, as fetch, claim and todo print it), or its id with --dir.
What each kind takes (pflib/run.py, Handoffs):
  page          a verdict (run.VERDICTS): no_access, no_pdf, not_public, proxy_unconfigured, skipped_by_user — the
                paper goes on to its next route; blocked, gate_timeout — it waits on this route until the next pass.
                A page the agent got past needs no answer: hand it back with `fetch --start <url> --session …`, and
                the file that arrives closes it.
  file          accept [--label TITLE --why WHY] (filed, labelled when a title is given; --version when its name
                does not say the version) | refuse (not the paper: the paper goes on) | unknown (cannot tell: filed
                unconfirmed, the paper goes on, a confirmed file replaces it later)
  label         label --label TITLE --why WHY (the scheme: references/attachment-titles.md) | unknown
                (Unknown-<Source>, which leaves the paper going on to the wanted version)
  left          claim --slug S (the download is that paper's) | not_ours
  browser_down  resolved
Every answer is logged ({event: answer, id, slug, kind, answer, reason, by}) with what it did (accept, label, try),
printed, and the paper's result folded (settle.py). --reason says what the answer rests on.
Exit 0 = recorded; 1 = refused (bad_answer, not_open, no_such_handoff, bad_label, no_label, no_slug).

Examples:
  uv run scripts/answer.py <dir>/handoffs/he2020mask.1.json accept --reason "page 1: TPAMI 42(2), Mask R-CNN, He et al." --label Published-IEEE --why "page 1 header: vol. 42 no. 2"
  uv run scripts/answer.py <dir>/handoffs/liu2022jbhi.2.json no_access --reason "the publisher page says the institution has no access"
"""
from pathlib import Path

from pflib import cli, paper, run

BY = ("agent", "paper_agent", "judge", "user")


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("handoff", metavar="HANDOFF", help="the handoff's file, or its id with --dir")
    p.add_argument("answer", metavar="ANSWER", help="what the kind takes (above)")
    p.add_argument("--dir", metavar="DIR", help="paper-fetch's directory, when HANDOFF is an id")
    p.add_argument("--reason", help="what the answer rests on")
    p.add_argument("--label", metavar="TITLE", help="file / label: the attachment title")
    p.add_argument("--why", help="with --label: what on the file or its page says so")
    p.add_argument("--slug", help="left: the paper the download is for")
    p.add_argument("--version", choices=list(paper.KINDS), help="file / left: the file's kind, when its name does not say")
    p.add_argument("--by", choices=BY, default="agent", help="who answers (default agent)")
    args = p.parse_args(argv)
    target = Path(args.handoff)
    if target.suffix == ".json":
        work, hid = run.Work(target.absolute().parent.parent), target.stem
    elif args.dir:
        work, hid = run.Work(args.dir), args.handoff
    else:
        p.error("give the handoff's file, or its id with --dir")
    if args.label and not args.why:
        p.error("--label needs --why")

    def go():
        events = run.answer(work, hid, args.answer, reason=args.reason, title=args.label, why=args.why,
                            slug=args.slug, version=args.version, by=args.by)
        for event in events:
            cli.emit(event)
        slug = events[-1].get("slug")
        if slug and (work.results / f"{slug}.json").is_file():
            run.settle(work, [run.read(work.results / f"{slug}.json")])
        return cli.OK

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
