"""The skeleton paper-read's scripts share: the parser and help, what comes after the options, how a line is printed
and a command stops with a code, and how the sibling skills' entries are run.

stdout carries data only: take, check and put print one JSON object about the one thing they handle, heading
one line per paper, quotes one line per quotation still to check; `hint` appears only when the code is not ok,
skipped or one of the command's answers.
  exit 0  done; stderr stays empty
  exit 1  the thing handled is the agent's to act on: its line's code says what (heading, over several papers, then
          ends stderr with {"summary": {total, failed}}; quotes with {"summary": {total, ok, checked, open}})
  exit 2  the command cannot go on (a usage error, a list it cannot read, Zotero not running, no pdftotext); stderr's
          last line is {code, hint, ...}
A reader that closes the pipe early (`| head`) ends the printing, not the work: the exit code is the same.

Copied from paper-to-zotero/scripts/p2zlib/cli.py at 8b0a0cd: the exit codes, Stop, write, emit, run, Parser, prog,
parser, parse, stdin_lines, names and document; each skill keeps its own copy. paper-read's own: run() puts the
thing's name first in its line, document() reads files only, and sibling() runs paper-to-zotero's and paddleocr's
entries.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

OK, ACT, CANNOT = 0, 1, 2
PROG_ENV = "PR_PROG"   # the words typed before the script's own: pr.py sets it ("pr.py take")
SKILLS = Path(__file__).resolve().parents[3]   # the directory the skills are installed in, side by side
P2Z = os.environ.get("PAPER_READ_P2Z") or str(SKILLS / "paper-to-zotero" / "scripts" / "p2z.py")
OCR = os.environ.get("PAPER_READ_OCR") or str(SKILLS / "paddleocr" / "scripts" / "ocr.py")

# A paper as named after the options: a bare value, or a value taken from one of our own JSON lines (`field`: "key" or
# "cite"). `line`: a JSON line from a `-` list that names no paper but reports a skip or a failure upstream, passed on
# as it is (value and field None).
Name = namedtuple("Name", "value field line", defaults=(None,))


class Stop(Exception):
    """A result code carried out of any depth; run() turns it into one line and an exit code."""

    def __init__(self, code, *, exit=ACT, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit, self.hint, self.extra = code, exit, hint, extra

    def line(self, **head):
        """{head..., code, extra..., hint?}; the head (the thing the line is about) wins over an extra of its name."""
        extra = {k: v for k, v in self.extra.items() if k not in head}
        return {**head, "code": self.code, **extra, **({"hint": self.hint} if self.hint else {})}


# ---- printing -------------------------------------------------------------------------------------------------

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


def run(fn, **head):
    """Call fn() -> exit code. A Stop that reaches here: exit 2 -> its line on stderr (the command could not go on);
    otherwise it is the line about the one thing the command handles, `head` (that thing's name) first, on stdout."""
    try:
        return fn()
    except Stop as stop:
        if stop.exit == CANNOT:
            emit(stop.line(), sys.stderr)
        else:
            emit(stop.line(**head))
        return stop.exit


# ---- parsing --------------------------------------------------------------------------------------------------

class Parser(argparse.ArgumentParser):
    def error(self, message):
        """A usage error: the usage line, then {code: usage, hint} as stderr's last line; exit 2."""
        self.print_usage(sys.stderr)
        emit({"code": "usage", "detail": message, "hint": f"See {self.prog} -h."}, sys.stderr)
        raise SystemExit(CANNOT)


def prog():
    """The command as the user typed it: pr.py's words (PROG_ENV), or this script's name."""
    return os.environ.get(PROG_ENV) or Path(sys.argv[0]).name


def parser(doc):
    """A parser whose -h is the docstring: its first line, the options, then the rest (output, exit codes, examples).
    Options and operands may come in any order (parse())."""
    first, _, rest = (doc or "").strip().partition("\n")
    return Parser(prog=prog(), description=first, epilog=rest.strip() or None,
                  formatter_class=argparse.RawDescriptionHelpFormatter)


def parse(p, argv):
    return p.parse_intermixed_args(argv)


# ---- what comes after the options ------------------------------------------------------------------------------

def stdin_lines():
    return [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]


def names(values):
    """The papers named after the options -> [Name]. `-` reads a list from stdin: a line is a value, or one of our own
    JSON lines, which names its paper by `key`, else by `cite`. A JSON line naming neither is passed on as it is
    (Name.line) when its code reports a skip or a failure upstream (any code but ok); any other stops the command. An
    empty list is no paper: the command does nothing and exits 0."""
    out = []
    for value in values:
        if value != "-":
            out.append(Name(value.strip(), None))
            continue
        for n, line in enumerate(stdin_lines(), 1):
            if not line.startswith("{"):
                out.append(Name(line, None))
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                obj = None
            field = next((f for f in ("key", "cite") if isinstance(obj, dict) and isinstance(obj.get(f), str)
                          and obj[f].strip()), None)
            if field is None:
                if isinstance(obj, dict) and isinstance(obj.get("code"), str) and obj["code"] != "ok":
                    out.append(Name(None, None, obj))
                    continue
                raise Stop("invalid_list", exit=CANNOT, line=n, detail=line[:200],
                           hint="A list holds one paper a line: a key or citation key, or a JSON line with `key` or "
                                "`cite` (what p2z.py search, items and pdf print). Nothing was done.")
            out.append(Name(obj[field].strip(), field))
    return out


def document(value, missing="No such file.", **extra):
    """The text of the file `value`. Not a file (absent, a directory, `-`: no command here reads stdin for a file) ->
    file_not_found with the hint `missing`; not UTF-8 text -> file_unreadable. `extra` goes into the line."""
    path = Path(value).expanduser()
    if not path.is_file():
        raise Stop("file_not_found", hint=missing, **extra)
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise Stop("file_unreadable", hint="The file cannot be read as UTF-8 text.", detail=str(e), **extra) from None


# ---- the sibling skills -----------------------------------------------------------------------------------------

def sibling(entry, *args, step=None):
    """Run a sibling skill's entry (P2Z, OCR) by its path, through uv -> (its JSON lines, its exit code, its stderr).
    With `step` (the command run, "package take"), a sibling that could not go on stops this command too: an exit 2,
    or a failure that printed no line, raises Stop exit 2 with the {code, hint, ...} its stderr ended with, plus step."""
    done = subprocess.run(["uv", "run", "--quiet", "--script", str(entry), *map(str, args)], capture_output=True,
                          text=True)
    lines = []
    for raw in done.stdout.splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        if isinstance(line, dict):
            lines.append(line)
    if step and (done.returncode not in (OK, ACT) or (done.returncode and not lines)):
        last = (done.stderr.strip().splitlines() or [""])[-1]
        try:
            why = json.loads(last)
        except ValueError:
            why = None
        if not (isinstance(why, dict) and why.get("code")):
            why = {"code": "step_failed", "detail": last or f"exit {done.returncode}",
                   "hint": f"{Path(entry).name} {step} stopped without saying why; run it alone to see."}
        extra = {k: v for k, v in why.items() if k not in ("code", "hint", "exit", "step")}
        raise Stop(why["code"], exit=CANNOT, hint=why.get("hint"), step=step, **extra)
    return lines, done.returncode, done.stderr
