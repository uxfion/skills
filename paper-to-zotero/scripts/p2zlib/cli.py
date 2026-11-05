"""The skeleton every script shares: its parser and help, what it reads after the options, how it prints its lines
and stops with a code.

stdout carries data only. A script on things (items, records) prints one compact JSON object per thing as it handles
it: {key or slug, code, ...}; `hint` appears only when the code is neither ok nor skipped (nor one of the script's
answers); a skip is always `code: skipped` with a `reason` word.
  exit 0  everything done or skipped; stderr stays empty
  exit 1  something is the agent's to act on (a line's code says what); stderr's last line is {"summary": {total, ok,
          skipped, failed}}
  exit 2  the command cannot go on (Zotero not running, no key, input it cannot read, a usage error); stderr's last
          line is {code, hint, ...}. The lines printed before stand; each thing not done is `code: not_run`.
A script whose lines answer a question (p2z.py have: found, not_found) names those codes as its `answers`: they
count as ok, so the answer is in the code and not in the exit status. A reader that closes the pipe early (`| head`)
ends the printing, not the work: the rest goes nowhere and the exit code is the same.
"""
import argparse
import json
import os
import re
import sys
from collections import namedtuple
from pathlib import Path

OK, ACT, CANNOT = 0, 1, 2
KEY_RE = re.compile(r"^[A-Z0-9]{8}$")
PROG_ENV = "P2Z_PROG"   # the words typed before the script's own: p2z.py sets it ("p2z.py", "p2z.py tag")
BASE_URL_ENV = "PAPER_TO_ZOTERO_BASE_URL"
PATH_ENDINGS = (".json", ".jsonl", ".pdf", ".bib", ".md")

# An item as named after the options: a bare value is checked as a key and as a citation key; a value taken from one
# of our own JSON lines only as the field it came from ("key" or "cite").
Name = namedtuple("Name", "value field")


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

    def put(self, line):
        self.counts["total"] += 1
        self.counts[outcome(line, self.answers)] += 1
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
        """Zotero (or what the loop needs) is gone: what is left is not_run."""
        self.stopped = self.stopped or stop

    def finish(self):
        if self.stopped is not None:
            emit(self.stopped.line(), sys.stderr)
            return self.stopped.exit
        if self.counts["failed"]:
            emit({"summary": self.counts}, sys.stderr)
            return ACT
        return OK


def summarize(total, failed, stopped=None, problems=()):
    """The end of a command whose stdout is not one line per thing (a document, a read's rows): each problem a JSON
    line on stderr, then, as Lines.finish, the stop (exit 2) or {"summary": {total, failed}} (exit 1) -> the exit code."""
    for line in problems:
        emit(line, sys.stderr)
    if stopped is not None:
        emit(stopped.line(), sys.stderr)
        return stopped.exit
    if failed:
        emit({"summary": {"total": total, "failed": failed}}, sys.stderr)
        return ACT
    return OK


def finish(lines, answers=()):
    """Print lines made all at once -> the exit code, as Lines.finish."""
    out = Lines(answers)
    for line in lines:
        out.put(line)
    return out.finish()


def run(fn, stream=None):
    """Call fn() -> exit code. A Stop that reaches here: exit 2 -> its line on stderr (the command could not go on);
    otherwise it is the line about the one thing the command handles -> stdout, or `stream` (stderr for a command
    whose stdout is a document)."""
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
    """The command as the user typed it: p2z.py's words (PROG_ENV) or this script's name, then the script's command."""
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


def add_base_url(p):
    """--base-url, its default from env PAPER_TO_ZOTERO_BASE_URL (p2z.py's prepare and save set it) or Zotero's."""
    from . import zotero
    p.add_argument("--base-url", default=os.environ.get(BASE_URL_ENV) or zotero.DEFAULT_BASE_URL,
                   help="Zotero's local API (default: %(default)s)")


def add_dry_run(p, help="show what would be written; write nothing"):
    p.add_argument("-n", "--dry-run", action="store_true", help=help)


def add_items(p, help="an item: its key or citation key; - reads a list from stdin"):
    p.add_argument("items", nargs="*", metavar="ITEM", help=help)


def output(p, value, count):
    """Where -o sends `count` outputs -> (path or None for stdout, is_dir). No -o: stdout, one output only; an
    existing directory, or a path ending in "/": that directory, made if absent; anything else: one file. Misuse is
    a usage error (exit 2)."""
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


# ---- what comes after the options ------------------------------------------------------------------------------

def stdin_lines():
    return [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]


def names(values):
    """The items named after the options -> [Name]. `-` reads a list from stdin: a line is a value, or one of our own
    JSON lines, which names its item by `key`, else by `cite`; a JSON line naming neither stops the command. An empty
    list is no item: the command does nothing and exits 0. Nothing written after the options is the caller's to refuse
    (a usage error), and never the whole library."""
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
                raise Stop("invalid_list", exit=CANNOT, line=n, detail=line[:200],
                           hint="A list holds one item a line: a key or citation key, or a JSON line with `key` or "
                                "`cite` (what search, items and pdf print). Nothing was done.")
            out.append(Name(obj[field].strip(), field))
    return out


def head(name, key=None):
    """The start of an item's line: {key[, cite]} once resolved (cite: the value named it by its citation key), or
    {item: the value} when it named no single item."""
    if key is None:
        return {"item": name.value}
    return {"key": key, **({"cite": name.value} if name.value != key else {})}


def paths(values):
    """The paths named after the options, `-` read from stdin as a list of paths, one a line."""
    out = []
    for value in values:
        out += stdin_lines() if value == "-" else [value]
    return out


def looks_like_path(value):
    """For a command that takes files or other things: a value with a "/" or a file's ending is a path."""
    return "/" in value or value.lower().endswith(PATH_ENDINGS)


def document(value):
    """The text of a file, or of stdin for `-`; a file that is not there -> file_not_found."""
    if value == "-":
        return sys.stdin.read()
    try:
        return Path(value).expanduser().read_text(encoding="utf-8")
    except FileNotFoundError:
        raise Stop("file_not_found", hint="No such file.", path=value) from None
    except (OSError, UnicodeDecodeError) as e:
        raise Stop("file_unreadable", hint="The file cannot be read as UTF-8 text.", path=value, detail=str(e)) from None


def changes(sources):
    """A change list (update and tag without change options; fill and retitle print one): JSON lines from files or
    `-`, one per item, naming it by "key" or by "cite", blank lines skipped -> [{where, key, cite, entry}]; the script
    checks the rest of each entry. A line that is not such an object, or an item line (one carrying itemType or
    version: change options take what to change from those), stops the command: nothing is done. An empty list is no
    change (fill found nothing to fill): the command does nothing and exits 0."""
    entries, problems, item_lines = [], [], []
    for source in sources:
        try:
            text = document(source)
        except Stop as stop:
            problems.append(f"{source}: {stop.code}")
            continue
        for n, raw in enumerate(text.splitlines(), 1):
            if not raw.strip():
                continue
            where = f"{'stdin' if source == '-' else source} line {n}"
            try:
                e = json.loads(raw)
            except ValueError as err:
                problems.append(f"{where}: not JSON ({err})")
                continue
            if not isinstance(e, dict):
                problems.append(f'{where}: a change is an object naming its item by "key" or "cite"')
                continue
            if "itemType" in e or "version" in e:
                item_lines.append(where)
                continue
            key, cite = e.get("key"), e.get("cite")
            where += f" (key {key})" if "key" in e else f" (cite {cite})" if "cite" in e else ""
            if ("key" in e) == ("cite" in e):
                problems.append(f'{where}: name the item by "key" or by "cite", one of them')
            elif "key" in e and not (isinstance(key, str) and KEY_RE.match(key)):
                problems.append(f'{where}: "key" is an 8-character item key')
            elif "cite" in e and not (isinstance(cite, str) and cite.strip()):
                problems.append(f'{where}: "cite" is a citation key')
            else:
                entries.append({"where": where, "key": key if "key" in e else None,
                                "cite": cite.strip() if "cite" in e else None, "entry": e})
    if item_lines:
        raise Stop("item_line", exit=CANNOT, lines=item_lines,
                   hint="These are item lines (search, items print them), not changes: pass the items with the "
                        "change as an option (--set, --add-tag, ...). Nothing was done.")
    return entries, problems


# ---- the loops --------------------------------------------------------------------------------------------------

def resolved(zot, named, out, once=True):
    """(index, name, key) for each name in turn that is one item (zot.resolve); a name that is not prints its line on
    `out`, and once Zotero is gone (out.stopped) every name left is not_run. once: an item named twice comes once."""
    seen = set()
    for i, name in enumerate(named):
        if out.stopped is not None:
            out.put({**head(name), "code": "not_run"})
            continue
        try:
            key = zot.resolve(name)
        except Stop as stop:
            if stop.exit == CANNOT:
                out.stop(stop)
                out.put({**head(name), "code": "not_run"})
            else:
                out.put(stop.line(**head(name)))
            continue
        if not (once and key in seen):
            seen.add(key)
            yield i, name, key


def main_items(doc, process, argv=None, *, configure=None, check=None):
    """The loop over the items named after the options: process(zot, item key, args) -> one line's fields.

    configure(p) adds the script's own arguments; check(p, args) reads and checks them before Zotero is asked
    (p.error for a usage error, a Stop for bad input: nothing done). Before the first item the server id and the key
    are checked, except with -n, which writes nothing."""
    from . import zotero
    p = parser(doc)
    add_items(p)
    add_dry_run(p)
    if configure:
        configure(p)
    add_base_url(p)
    args = parse(p, argv)

    def loop():
        if not args.items:
            p.error("name the items: keys or citation keys, or - to read a list from stdin")
        named = names(args.items)
        if check:
            check(p, args)
        zot = zotero.Zotero(args.base_url)
        if not args.dry_run:
            zot.write_headers()
        out = Lines()
        for _, name, key in resolved(zot, named, out):
            out.add(head(name, key), lambda: process(zot, key, args))
        return out.finish()

    return run(loop)


def main_records(doc, process, argv=None, *, configure=None, check=None, setup=None, zotero=False, dry_run=False,
                 all_valid=False, answers=()):
    """records_parser(), then each_record() over the records named. configure(p) adds the script's own arguments;
    check(p, args) reads and checks them first (p.error for a usage error, a Stop for bad input)."""
    p = records_parser(doc, zotero=zotero, dry_run=dry_run)
    if configure:
        configure(p)
    args = parse(p, argv)

    def loop():
        if check:
            check(p, args)
        return each_record(p, args, process, setup=setup, all_valid=all_valid, answers=answers)

    return run(loop)


def records_parser(doc, *, zotero=False, dry_run=False):
    """The parser a script on record files starts from: the record paths, -n (dry_run), --base-url (zotero)."""
    p = parser(doc)
    p.add_argument("records", nargs="*", metavar="RECORD",
                   help="record files: <scratch>/paper-to-zotero/records/*.json; - reads their paths from stdin")
    if dry_run:
        add_dry_run(p)
    if zotero:
        add_base_url(p)
    return p


def each_record(p, args, process, *, setup=None, all_valid=False, answers=()):
    """The loop over the records named (paths, `-` read as a list of paths): process(rec, ctx) -> one line's fields;
    a record it changed is written back, after a Stop too (not with -n). ctx is setup(args, records) when
    given, else args. -> the exit code.

    A file that is not a record is its own failed line; with all_valid (a script that writes the library) any such
    file stops the run before anything is done: the records are not_run."""
    from . import run as work
    if not args.records:
        p.error("name the record files: <scratch>/paper-to-zotero/records/*.json, or - to read their paths from stdin")
    named = paths(args.records)
    entries = []
    for path in named:
        try:
            entries.append(work.read(path))
        except Stop as stop:
            entries.append(stop.line(slug=Path(path).stem))
    recs = [e for e in entries if isinstance(e, work.Record)]
    if all_valid and len(recs) != len(entries):
        return finish([e if not isinstance(e, work.Record) else {"slug": e.slug, "code": "not_run"} for e in entries])
    dry_run = getattr(args, "dry_run", False)
    out = Lines(answers)
    try:
        ctx = setup(args, recs) if setup else args
    except Stop as stop:
        if stop.exit != CANNOT:
            raise
        out.stop(stop)
        ctx = None

    def step(rec):
        try:
            return process(rec, ctx)
        finally:
            if rec.changed() and not dry_run:
                try:
                    rec.save()
                except OSError as err:
                    raise Stop("write_failed", path=str(rec.path), detail=str(err),
                               hint="The record file could not be rewritten; what was written to Zotero stands.") from None

    for e in entries:
        if isinstance(e, work.Record):
            out.add({"slug": e.slug}, lambda: step(e))
        else:
            out.put(e)
    return out.finish()
