"""The skeleton every script shares: its parser and help, what it reads after the options, how it prints its lines
and stops with a code.

stdout carries data only. A script on things (results, files, handoffs) prints one compact JSON object per thing as
it handles it: {slug or id or file, code, ...}; `hint` appears only when the code is neither ok nor skipped (nor one
of the script's answers); a skip is always `code: skipped` with a `reason` word.
  exit 0  everything done or skipped; stderr stays empty
  exit 1  something is the agent's to act on (a line's code says what); a script over several things ends stderr with
          {"summary": {total, ok, skipped, failed}}
  exit 2  the command cannot go on (no pdftotext, no opencli, a service that does not answer, a list it cannot read,
          a usage error); stderr's last line is {code, hint, ...}. A script over several things keeps the lines
          printed before, and each thing not done is `code: not_run`.
A script whose lines answer a question (check: the check's verdicts) names those codes as its `answers`: they count
as ok, so the answer is in the code and not in the exit status. A reader that closes the pipe early (`| head`) ends
the printing, not the work: the rest goes nowhere and the exit code is the same.

Copied from paper-to-zotero/scripts/p2zlib/cli.py at 8b0a0cd without the Zotero parts (--base-url, items named by
key or citation key, change lists, the loop over items) and the helpers no script here calls; each skill keeps its
own copy, so neither depends on the other being installed. Its own: a `-` list read by the JSON field that names the
thing (paths(), list_value()), the loop over results, and the result told from other operands by its .json.
"""
import argparse
import json
import os
import sys
from pathlib import Path

OK, ACT, CANNOT = 0, 1, 2
PROG_ENV = "PF_PROG"   # the words typed before the script's own: pf.py sets it ("pf.py", "pf.py locate")


class Stop(Exception):
    """A result code carried out of any depth; the loop or run() turns it into one line and an exit code."""

    def __init__(self, code, *, exit=ACT, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit, self.hint, self.extra = code, exit, hint, extra

    def line(self, **head):
        """{head..., code, extra..., hint?}; the head (the thing the line is about) wins over an extra of its name."""
        extra = {k: v for k, v in self.extra.items() if k not in head}
        return {**head, "code": self.code, **extra, **({"hint": self.hint} if self.hint else {})}


# ---- printing -------------------------------------------------------------------------------------------------

def log(msg):
    print(msg, file=sys.stderr, flush=True)


def write(text):
    """Text to stdout. Once the reader has closed the pipe, stdout goes to /dev/null and the work goes on."""
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except BrokenPipeError:
        try:
            fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(fd, sys.stdout.fileno())
            os.close(fd)
        except (OSError, ValueError):
            pass


def emit(obj, stream=None):
    """One JSON line: to stdout (write), or to `stream`."""
    text = json.dumps(obj, ensure_ascii=False) + "\n"
    if stream is None:
        write(text)
    else:
        stream.write(text)
        stream.flush()


def ok(**fields):
    return {"code": "ok", **fields}


def skipped(reason, **fields):
    return {"code": "skipped", "reason": reason, **fields}


def outcome(line, answers=()):
    code = line.get("code")
    return "ok" if code == "ok" or code in answers else "skipped" if code == "skipped" else "failed"


def tidy(line, answers=()):
    """Drop a hint from a line whose code is ok, skipped or an answer."""
    if outcome(line, answers) != "failed":
        line.pop("hint", None)
    return line


class Lines:
    """The lines of a loop over things, printed as they come. add(head, fn) runs fn() -> fields as that thing's line
    {head..., code, fields...} (the head wins over a field of its name), or the line of the Stop it raised; put(line)
    prints a line made elsewhere. After a Stop with exit 2 the thing it stopped on and every later one is `not_run`.
    finish() -> the exit code, after the summary (exit 1) or the stop (exit 2) on stderr."""

    def __init__(self, answers=()):
        self.counts = {"total": 0, "ok": 0, "skipped": 0, "failed": 0}
        self.stopped, self.answers = None, answers

    def put(self, line, kind=None):
        """Print a line, counted as `kind` (ok, skipped, failed) when its code alone does not say (a claim's code is
        the check's verdict, its result what was done)."""
        self.counts["total"] += 1
        self.counts[kind or outcome(line, self.answers)] += 1
        emit(line)
        return line

    def add(self, head, fn):
        if self.stopped is not None:
            return self.put({**head, "code": "not_run"})
        try:
            fields = dict(fn())
            line = tidy({**head, "code": fields.pop("code", "ok"), **{k: v for k, v in fields.items() if k not in head}},
                        self.answers)
        except Stop as stop:
            if stop.exit == CANNOT:
                self.stopped = stop
                return self.put({**head, "code": "not_run"})
            line = stop.line(**head)
        return self.put(line)

    def stop(self, stop):
        """What the loop needs is gone (pdftotext, the browser, a service): what is left is not_run."""
        self.stopped = self.stopped or stop

    def finish(self):
        if self.stopped is not None:
            emit(self.stopped.line(), sys.stderr)
            return self.stopped.exit
        if self.counts["failed"]:
            emit({"summary": self.counts}, sys.stderr)
            return ACT
        return OK


def run(fn, stream=None):
    """Call fn() -> exit code. A Stop that reaches here: exit 2 -> its line on stderr (the command could not go on);
    otherwise it is the line about the one thing the command handles -> stdout, or `stream`."""
    try:
        return fn()
    except Stop as stop:
        emit(stop.line(), sys.stderr if stop.exit == CANNOT else stream)
        return stop.exit


# ---- parsing --------------------------------------------------------------------------------------------------

class Parser(argparse.ArgumentParser):
    def error(self, message):
        """A usage error: the usage line, then {code: usage, hint} as stderr's last line; exit 2."""
        self.print_usage(sys.stderr)
        emit({"code": "usage", "detail": message, "hint": f"See {self.prog} -h."}, sys.stderr)
        raise SystemExit(CANNOT)


def prog(sub=None):
    """The command as the user typed it: pf.py's words (PROG_ENV) or this script's name, then the script's command."""
    name = os.environ.get(PROG_ENV) or Path(sys.argv[0]).name
    return f"{name} {sub}" if sub else name


def parser(doc, sub=None):
    """A parser whose -h is the docstring: its first line, the options, then the rest (output, exit codes, examples).
    Options and operands may come in any order (parse())."""
    first, _, rest = (doc or "").strip().partition("\n")
    return Parser(prog=prog(sub), description=first, epilog=rest.strip() or None,
                  formatter_class=argparse.RawDescriptionHelpFormatter)


def parse(p, argv):
    return p.parse_intermixed_args(argv)


def subcommand(doc, commands, argv):
    """A script with several commands, each its own parser: argv[0] names it -> (name, the rest). -h lists them."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in commands:
        return argv[0], argv[1:]
    first, _, rest = (doc or "").strip().partition("\n")
    width = max(map(len, commands)) + 2
    listing = "\n".join(f"  {name:<{width}}{(fn.__doc__ or '').strip().splitlines()[0]}" for name, fn in commands.items())
    text = f"usage: {prog()} COMMAND ...   ({prog()} COMMAND -h for each)\n\n{first}\n\ncommands:\n{listing}\n"
    if argv and argv[0] in ("-h", "--help"):
        write(text + (f"\n{rest.strip()}\n" if rest.strip() else ""))
        raise SystemExit(OK)
    sys.stderr.write(text)
    emit({"code": "usage", "detail": f"no command {argv[0]!r}" if argv else "name a command",
          "hint": f"See {prog()} -h."}, sys.stderr)
    raise SystemExit(CANNOT)


def add_dry_run(p, help="show what would be written; write nothing"):
    p.add_argument("-n", "--dry-run", action="store_true", help=help)


# ---- what comes after the options ------------------------------------------------------------------------------

def stdin_lines():
    return [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]


def list_value(line, n, field, hint):
    """One line of a `-` list -> (the value it names, None), or (None, the line) for one of our JSON lines without
    `field` that reports a skip or a failure upstream (any code but ok), to be passed on as it is. Any other JSON line
    without it (code ok, or none) makes the list unreadable: invalid_list, exit 2, nothing done."""
    if not line.startswith("{"):
        return line, None
    try:
        obj = json.loads(line)
    except ValueError:
        obj = None
    if isinstance(obj, dict):
        value = obj.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip(), None
        if isinstance(obj.get("code"), str) and obj["code"] != "ok":
            return None, obj
    raise Stop("invalid_list", exit=CANNOT, line=n, detail=line[:200], hint=hint)


def paths(values, field="path"):
    """The paths named after the options, in order -> [path, or a JSON line to pass on]. `-` reads a list of paths
    from stdin: a path a line, or one of our JSON lines by `field` (a result's `path`; a file's `source`), a line
    without it passed on or refused as list_value() says. A path named twice comes once. An empty list is no path:
    the command does nothing and exits 0."""
    hint = (f"A list holds one path a line, or a JSON line with `{field}` (what our commands print). Nothing was done.")
    out, seen = [], set()
    for value in values:
        items = [(value, None)] if value != "-" else [list_value(line, n, field, hint)
                                                       for n, line in enumerate(stdin_lines(), 1)]
        for path, passed in items:
            if passed is not None:
                out.append(passed)
                continue
            key = os.path.abspath(os.path.expanduser(path))
            if key not in seen:
                seen.add(key)
                out.append(path)
    return out


def split_result(p, operands):
    """A command on one result and other things (files to claim or check, redraft's target): the operand ending in
    .json is the result, wherever it stands -> (the result's path, [the others]). None, or two, is a usage error."""
    found = [i for i, v in enumerate(operands) if v.lower().endswith(".json")]
    if len(found) != 1:
        p.error(f"name one result, <dir>/results/<slug>.json ({len(found) or 'none'} given)")
    return operands[found[0]], [v for i, v in enumerate(operands) if i != found[0]]


# ---- the loop over results --------------------------------------------------------------------------------------

RESULTS_HELP = ("result files: <dir>/results/<slug>.json; - reads their paths from stdin, a path a line or our JSON "
                "lines by `path`")


def results_parser(doc, *, dry_run=False):
    """The parser a script on result files starts from: the result paths, -n (dry_run)."""
    p = parser(doc)
    p.add_argument("results", nargs="*", metavar="RESULT", help=RESULTS_HELP)
    if dry_run:
        add_dry_run(p)
    return p


def main_results(doc, process, argv=None, *, configure=None, setup=None, dry_run=False, answers=()):
    """results_parser(), then each_result() over the results named. configure(p) adds the script's own arguments."""
    p = results_parser(doc, dry_run=dry_run)
    if configure:
        configure(p)
    args = parse(p, argv)
    return run(lambda: each_result(p, args, process, setup=setup, answers=answers))


def each_result(p, args, process, *, setup=None, answers=()):
    """The loop over args.results (paths(): `-` read as a list): process(res, ctx) -> one line's fields. ctx is
    setup(args, results) when given, else args; a Stop with exit 2 from setup leaves every result not_run. -> the exit
    code. A file that is not a result is its own failed line, a line passed on from upstream goes out as it is.
    Nothing is written back here: a result file has its own writers."""
    from . import run as work
    if not args.results:
        p.error("name the result files: <dir>/results/*.json, or - to read their paths from stdin")
    entries = []
    for e in paths(args.results):
        try:
            entries.append(work.read(e) if isinstance(e, str) else e)
        except Stop as stop:
            entries.append(stop.line(slug=Path(e).stem))
    out = Lines(answers)
    ctx = args
    if setup:
        try:
            ctx = setup(args, [e for e in entries if isinstance(e, work.Result)])
        except Stop as stop:
            if stop.exit != CANNOT:
                raise
            out.stop(stop)
    for e in entries:
        if isinstance(e, work.Result):
            out.add({"slug": e.slug}, lambda: process(e, ctx))
        else:
            out.put(e)
    return out.finish()
