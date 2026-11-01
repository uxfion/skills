"""The skeleton every script shares: how it stops with a code, prints its lines, reads its arguments and loops.

stdout carries JSON only, one compact object per line: one per thing handled ({key or slug, code, ...}), then
{"summary": {...}} when a script handles several. `hint` appears only when the code is neither ok nor skipped (nor
one of the script's answers); a skip is always `code: skipped` with a `reason` word. Exit 0 = everything done or
skipped, 1 = something is the agent's to act on, 2 = cannot check (Zotero not running, no key, ...).

A script whose lines answer a question names those codes as its `answers`: they count as ok, so the answer is in
the code and not in the exit status.

Copied from paper-to-zotero/scripts/p2zlib/cli.py (commit 90cecdf) without the Zotero parts (--base-url, --key and
--cite targets, the loop over items); each skill keeps its own copy, so neither depends on the other being installed.
"""
import argparse
import json
import sys

OK, ACT, CANNOT = 0, 1, 2


class Stop(Exception):
    """A result code carried out of any depth; the loop or main() turns it into one line and an exit code."""

    def __init__(self, code, *, exit=ACT, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit, self.hint, self.extra = code, exit, hint, extra

    def line(self, **head):
        """{head..., code, extra..., hint?}; the head (the key or slug the line is about) wins over an extra of its name."""
        extra = {k: v for k, v in self.extra.items() if k not in head}
        return {**head, "code": self.code, **extra, **({"hint": self.hint} if self.hint else {})}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def emit(obj, stream=None):
    print(json.dumps(obj, ensure_ascii=False), file=stream or sys.stdout, flush=True)


def ok(**fields):
    return {"code": "ok", **fields}


def skipped(reason, **fields):
    return {"code": "skipped", "reason": reason, **fields}


def outcome(line, answers=()):
    code = line.get("code")
    return "ok" if code == "ok" or code in answers else "skipped" if code == "skipped" else "failed"


def output(p, value, count):
    """Where -o/--out sends `count` outputs -> (path or None for stdout, is_dir). No -o: stdout, one output only; an
    existing directory, or a path ending in "/": that directory, made if absent; anything else: one file. Misuse is
    a usage error (exit 2)."""
    from pathlib import Path
    if value is None:
        if count > 1:
            p.error(f"{count} outputs need -o DIR/ (stdout takes one)")
        return None, False
    path = Path(value).expanduser()
    if value.endswith("/") or path.is_dir():
        path.mkdir(parents=True, exist_ok=True)
        return path, True
    if count > 1:
        p.error(f"-o {value} names one file, for {count} outputs: give a directory, ending in /")
    return path, False


def parser(doc, **kwargs):
    """An ArgumentParser whose --help is the module docstring: its first line, then the rest as the epilog."""
    first, _, rest = (doc or "").strip().partition("\n")
    return argparse.ArgumentParser(description=first, epilog=rest.strip() or None,
                                   formatter_class=argparse.RawDescriptionHelpFormatter, **kwargs)


def split(values):
    out = []
    for v in values or []:
        out += [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(out))


def finish(lines, *, stopped=None, extra=None, answers=()):
    """Print the lines, then the summary; return the exit code."""
    counts = {"total": len(lines), "ok": 0, "skipped": 0, "failed": 0}
    for line in lines:
        counts[outcome(line, answers)] += 1
        emit(line)
    counts.update(extra or {})
    if stopped is not None:
        counts["stopped"] = stopped.code
        log(f"stopped early: {stopped.code}" + (f" - {stopped.hint}" if stopped.hint else ""))
    emit({"summary": counts})
    if stopped is not None:
        return stopped.exit
    return ACT if counts["failed"] else OK


class Lines:
    """The lines of a loop over things, one per thing: add(head, fn) runs fn() -> fields as that thing's line {head...,
    code, fields...} (the head wins over a field of its name), or the line of the Stop it raised. After a Stop with
    exit 2 every later thing is `not_run`. finish() prints them and the summary -> the exit code."""

    def __init__(self, answers=()):
        self.lines, self.stopped, self.answers = [], None, answers

    def add(self, head, fn):
        if self.stopped is not None:
            line = {**head, "code": "not_run"}
        else:
            try:
                fields = dict(fn())
                line = tidy({**head, "code": fields.pop("code", "ok"), **{k: v for k, v in fields.items() if k not in head}},
                            self.answers)
            except Stop as stop:
                if stop.exit == CANNOT:
                    self.stopped = stop
                line = stop.line(**head)
        self.lines.append(line)
        return line

    def finish(self, extra=None):
        return finish(self.lines, stopped=self.stopped, extra=extra, answers=self.answers)


def run(fn, stream=None):
    """Call fn() -> exit code; a Stop that reaches here becomes one line on `stream` (stdout by default)."""
    try:
        return fn()
    except Stop as stop:
        emit(stop.line(), stream)
        return stop.exit


def main_results(doc, process, argv=None, *, configure=None, check=None, setup=None, dry_run=False, answers=()):
    """results_parser(), then each_result() over the result files named. configure(p) adds the script's own
    arguments; check(p, args) reads and checks them first (p.error for a usage error, a Stop for bad input)."""
    p = results_parser(doc, dry_run=dry_run)
    if configure:
        configure(p)
    args = p.parse_args(argv)

    def loop():
        if check:
            check(p, args)
        return each_result(args, process, setup=setup, answers=answers)

    return run(loop)


def results_parser(doc, *, dry_run=False):
    """The parser a script on result files starts from: the result paths, --dry-run (dry_run)."""
    p = parser(doc)
    p.add_argument("results", nargs="*", metavar="RESULT", help="result files: <dir>/results/<slug>.json")
    if dry_run:
        p.add_argument("--dry-run", action="store_true", help="show what would be written; write nothing")
    return p


def each_result(args, process, *, setup=None, answers=()):
    """The loop over args.results: process(res, ctx) -> one line's fields. ctx is setup(args, results) when given, else
    args. -> the exit code. A file that is not a result is its own failed line. A Stop with exit 2 ends the loop: the
    results not yet handled are `not_run`. Nothing is written back here: a result file has its own writers."""
    from pathlib import Path

    from . import run as work
    if not args.results:
        raise Stop("no_results", hint="Pass the result files: <dir>/results/<slug>.json.")
    entries = []
    for path in args.results:
        try:
            entries.append(work.read(path))
        except Stop as stop:
            entries.append(stop.line(slug=Path(path).stem))
    ctx = setup(args, [e for e in entries if isinstance(e, work.Result)]) if setup else args
    out = Lines(answers)
    for e in entries:
        if isinstance(e, work.Result):
            out.add({"slug": e.slug}, lambda: process(e, ctx))
        else:
            out.lines.append(e)
    return out.finish({"dry_run": True} if getattr(args, "dry_run", False) else None)


def tidy(line, answers=()):
    """Drop a hint from a line whose code is ok, skipped or an answer."""
    if outcome(line, answers) != "failed":
        line.pop("hint", None)
    return line
