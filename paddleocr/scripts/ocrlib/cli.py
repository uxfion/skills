"""The skeleton every script shares: its parser and help, what it reads after the options, how it prints its lines
and stops with a code.

stdout carries data only. A command on things (documents, parses) prints one compact JSON object per thing as it
handles it: {input or folder, code, ...}; `hint` appears only when the code is neither ok nor skipped; a skip is
always `code: skipped` with a `reason` word.
  exit 0  everything done or skipped; stderr holds no more than progress
  exit 1  something is the agent's to act on (a line's code says what); a command over several things ends stderr
          with {"summary": {total, ok, skipped, failed}}
  exit 2  the command cannot go on (no tool environment, no server, a lock, a list it cannot read, a usage error);
          stderr's last line is {code, hint, ...}. A command over several things keeps the lines printed before, and
          each thing not done is `code: not_run`.
A reader that closes the pipe early (`| head`) ends the printing, not the work: the rest goes nowhere and the exit
code is the same.

Copied from paper-to-zotero/scripts/p2zlib/cli.py at 8b0a0cd without the Zotero parts (--base-url, items named by key
or citation key, change lists, the loops over items and records) and the helpers no script here calls; each skill
keeps its own copy, so neither depends on the other being installed. Its own: paths() reads a `-` list by the JSON
field that names the thing and passes on the lines that report a skip or a failure upstream (as p2z's names() does),
run() puts the thing's head on the line, and Parser.error takes a hint.
"""
import argparse
import json
import os
import sys
from pathlib import Path

OK, ACT, CANNOT = 0, 1, 2
PROG_ENV = "OCR_PROG"   # the words typed before the script's own: ocr.py sets it ("ocr.py", "ocr.py parse")


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


def outcome(line):
    code = line.get("code")
    return "ok" if code == "ok" else "skipped" if code == "skipped" else "failed"


def tidy(line):
    """Drop a hint from a line whose code is ok or skipped."""
    if outcome(line) != "failed":
        line.pop("hint", None)
    return line


class Lines:
    """The lines of a loop over things, printed as they come. add(head, fn) runs fn() -> fields as that thing's line
    {head..., code, fields...} (the head wins over a field of its name), or the line of the Stop it raised; put(line)
    prints a line made elsewhere. After a Stop with exit 2 the thing it stopped on and every later one is `not_run`.
    finish() -> the exit code, after the summary (exit 1) or the stop (exit 2) on stderr."""

    def __init__(self):
        self.counts = {"total": 0, "ok": 0, "skipped": 0, "failed": 0}
        self.stopped = None

    def put(self, line):
        self.counts["total"] += 1
        self.counts[outcome(line)] += 1
        emit(line)
        return line

    def add(self, head, fn):
        if self.stopped is not None:
            return self.put({**head, "code": "not_run"})
        try:
            fields = dict(fn())
            line = tidy({**head, "code": fields.pop("code", "ok"), **{k: v for k, v in fields.items() if k not in head}})
        except Stop as stop:
            if stop.exit == CANNOT:
                self.stopped = stop
                return self.put({**head, "code": "not_run"})
            line = stop.line(**head)
        return self.put(line)

    def stop(self, stop):
        """What the loop needs is gone: what is left is not_run."""
        self.stopped = self.stopped or stop

    def finish(self):
        if self.stopped is not None:
            emit(self.stopped.line(), sys.stderr)
            return self.stopped.exit
        if self.counts["failed"]:
            emit({"summary": self.counts}, sys.stderr)
            return ACT
        return OK


def run(fn, stream=None, **head):
    """Call fn() -> exit code. A Stop that reaches here is the line about the one thing the command handles, `head`
    first: exit 2 -> stderr (the command could not go on); otherwise stdout, or `stream` (stderr for a command whose
    stdout is text for a reader)."""
    try:
        return fn()
    except Stop as stop:
        emit(stop.line(**head), sys.stderr if stop.exit == CANNOT else stream)
        return stop.exit


# ---- parsing --------------------------------------------------------------------------------------------------

class Parser(argparse.ArgumentParser):
    def error(self, message, hint=None):
        """A usage error: the usage line, then {code: usage, detail, hint} as stderr's last line; exit 2."""
        self.print_usage(sys.stderr)
        emit({"code": "usage", "detail": message, "hint": hint or f"See {self.prog} -h."}, sys.stderr)
        raise SystemExit(CANNOT)


def prog(sub=None):
    """The command as the user typed it: ocr.py's words (PROG_ENV) or this script's name, then the script's command."""
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


# ---- what comes after the options ------------------------------------------------------------------------------

def stdin_lines():
    return [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]


def paths(values, field):
    """The paths named after the options -> [path, or a line passed on]. `-` reads a list from stdin: a line is a
    path, or one of our own JSON lines, which names its path by `field`. A JSON line without it is passed on as it is
    (a dict in the list) when its code reports a skip or a failure upstream (any code but ok); any other stops the
    command (exit 2). An empty list is nothing to do."""
    out = []
    for value in values:
        if value != "-":
            out.append(value)
            continue
        for n, line in enumerate(stdin_lines(), 1):
            if not line.startswith("{"):
                out.append(line)
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                obj = None
            if isinstance(obj, dict) and isinstance(obj.get(field), str) and obj[field].strip():
                out.append(obj[field].strip())
            elif isinstance(obj, dict) and isinstance(obj.get("code"), str) and obj["code"] != "ok":
                out.append(obj)
            else:
                raise Stop("invalid_list", exit=CANNOT, line=n, detail=line[:200],
                           hint=f"A list holds one path a line, or a JSON line with `{field}` (what parse and "
                                f"p2z.py package take print). Nothing was done.")
    return out
