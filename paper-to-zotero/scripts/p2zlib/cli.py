"""The skeleton every script shares: how it stops with a code, prints its lines, reads its arguments and loops.

stdout carries JSON only, one compact object per line: one per thing handled ({key or slug, code, ...}), then
{"summary": {...}} when a script handles several. `hint` appears only when the code is neither ok nor skipped (nor
one of the script's answers); a skip is always `code: skipped` with a `reason` word. Exit 0 = everything done or
skipped, 1 = something is the agent's to act on, 2 = cannot check (Zotero not running, no key, ...).

A script whose lines answer a question (find_in_library: found, not_found) names those codes as its `answers`: they
count as ok, so the answer is in the code and not in the exit status.
"""
import argparse
import json
import re
import sys
from pathlib import Path

OK, ACT, CANNOT = 0, 1, 2
KEY_RE = re.compile(r"^[A-Z0-9]{8}$")


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


BASE_URL_ENV = "PAPER_TO_ZOTERO_BASE_URL"


def add_base_url(p):
    """--base-url, its default from env PAPER_TO_ZOTERO_BASE_URL (p2z.py sets it for the scripts it runs) or Zotero's."""
    import os

    from . import zotero
    p.add_argument("--base-url", default=os.environ.get(BASE_URL_ENV) or zotero.DEFAULT_BASE_URL,
                   help="Zotero's local API (default: %(default)s)")


def add_targets(p, what="item"):
    """--key and --cite: repeatable, several after one flag, or comma-separated."""
    p.add_argument("--key", nargs="+", action="extend", default=[], metavar="KEY", help=f"{what} key(s), 8 characters")
    p.add_argument("--cite", nargs="+", action="extend", default=[], metavar="CITE", help=f"citation key(s) of the {what}(s)")


def split(values):
    out = []
    for v in values or []:
        out += [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(out))


def targets_of(p, args, required=True):
    """The parsed --key / --cite values, split and checked; a parser error when none is given and one is required."""
    args.key, args.cite = split(args.key), split(args.cite)
    if required and not args.key and not args.cite:
        p.error("name the items with --key and/or --cite")
    bad = [k for k in args.key if not KEY_RE.match(k)]
    if bad:
        p.error(f"--key takes 8-character keys: {', '.join(bad)}")
    return args


def batch_entries(name):
    """A --batch file, one format for every script that writes in bulk (update_item, file_and_tag; titles_from_labels
    and fields_from_results write it): JSON lines, an object per line naming its item by "key" or by "cite", blank
    lines skipped -> ([{where, key, cite, entry}], [problems]); the script checks the rest of each entry."""
    try:
        text = Path(name).expanduser().read_text(encoding="utf-8")
    except OSError as e:
        return [], [f"{name}: {e.strerror or e}"]
    entries, problems = [], []
    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            e = json.loads(raw)
        except ValueError as err:
            problems.append(f"line {n}: not JSON ({err})")
            continue
        if not isinstance(e, dict):
            problems.append(f'line {n}: an entry is an object naming its item by "key" or "cite"')
            continue
        key, cite = e.get("key"), e.get("cite")
        where = f"line {n}" + (f" (key {key})" if "key" in e else f" (cite {cite})" if "cite" in e else "")
        if ("key" in e) == ("cite" in e):
            problems.append(f'{where}: name the item by "key" or by "cite", one of them')
        elif "key" in e and not (isinstance(key, str) and KEY_RE.match(key)):
            problems.append(f'{where}: "key" is an 8-character item key')
        elif "cite" in e and not (isinstance(cite, str) and cite.strip()):
            problems.append(f'{where}: "cite" is a citationKey')
        else:
            entries.append({"where": where, "key": key if "key" in e else None,
                            "cite": cite.strip() if "cite" in e else None, "entry": e})
    if not entries and not problems:
        problems.append("no entries")
    return entries, problems


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


def head(key=None, cite=None):
    """The start of an item's line: {key[, cite]}, or {cite} for a citation key that named no single item."""
    return {**({"key": key} if key else {}), **({"cite": cite} if cite else {})}


def main_items(doc, process, argv=None, *, configure=None, check=None):
    """The loop over items named by --key / --cite: process(zot, item key, args) -> one line's fields.

    configure(p) adds the script's own arguments; check(p, args) reads and checks them before Zotero is asked
    (p.error for a usage error, a Stop for bad input: one line, nothing done). Every citation key is resolved
    first (one shared fallback scan); an item named twice is handled once. Before the first item the server id and
    the key are checked, except with --dry-run, which writes nothing. A Stop with exit 2 ends the loop: the items
    not yet handled are `not_run`."""
    from . import zotero
    p = parser(doc)
    add_targets(p)
    p.add_argument("--dry-run", action="store_true", help="show what would be written; write nothing")
    if configure:
        configure(p)
    add_base_url(p)
    args = targets_of(p, p.parse_args(argv))

    def loop():
        if check:
            check(p, args)
        zot = zotero.Zotero(args.base_url)
        if not args.dry_run:
            zot.write_headers()
        out = Lines()
        for key, cite, failure in zot.targets(args.key, args.cite):
            if failure is not None:
                out.lines.append(failure.line(**head(key, cite)))
            else:
                out.add(head(key, cite), lambda: process(zot, key, args))
        return out.finish({"dry_run": True} if args.dry_run else None)

    return run(loop)


def main_records(doc, process, argv=None, *, configure=None, check=None, setup=None, zotero=False, dry_run=False,
                 all_valid=False, answers=()):
    """records_parser(), then each_record() over the records named. configure(p) adds the script's own arguments;
    check(p, args) reads and checks them first (p.error for a usage error, a Stop for bad input)."""
    p = records_parser(doc, zotero=zotero, dry_run=dry_run)
    if configure:
        configure(p)
    args = p.parse_args(argv)

    def loop():
        if check:
            check(p, args)
        return each_record(args, process, setup=setup, all_valid=all_valid, answers=answers)

    return run(loop)


def records_parser(doc, *, zotero=False, dry_run=False):
    """The parser a script on record files starts from: the record paths, --dry-run (dry_run), --base-url (zotero)."""
    p = parser(doc)
    p.add_argument("records", nargs="*", metavar="RECORD", help="record files: <scratch>/paper-to-zotero/records/*.json")
    if dry_run:
        p.add_argument("--dry-run", action="store_true", help="show what would be written; write nothing")
    if zotero:
        add_base_url(p)
    return p


def each_record(args, process, *, setup=None, all_valid=False, answers=()):
    """The loop over args.records: process(rec, ctx) -> one line's fields; a record it changed is written back
    (not with --dry-run). ctx is setup(args, records) when given, else args. -> the exit code.

    A file that is not a record is its own failed line; with all_valid (a script that writes the library) any such
    file stops the run before anything is done. A Stop with exit 2 ends the loop: the records not yet handled are
    `not_run`."""
    from pathlib import Path

    from . import run as work
    if not args.records:
        raise Stop("no_records", hint="Pass the record files: <scratch>/paper-to-zotero/records/*.json.")
    entries = []
    for path in args.records:
        try:
            entries.append(work.read(path))
        except Stop as stop:
            entries.append(stop.line(slug=Path(path).stem))
    recs = [e for e in entries if isinstance(e, work.Record)]
    if all_valid and len(recs) != len(entries):
        return finish([e for e in entries if not isinstance(e, work.Record)],
                      extra={"not_run": len(recs), "why": "a file is not a record; nothing was done"})
    ctx = setup(args, recs) if setup else args
    dry_run = getattr(args, "dry_run", False)
    out = Lines(answers)
    for e in entries:
        if not isinstance(e, work.Record):
            out.lines.append(e)
            continue
        out.add({"slug": e.slug}, lambda: process(e, ctx))
        if e.changed() and not dry_run:
            try:
                e.save()
            except OSError as err:
                out.lines[-1] = {"slug": e.slug, "code": "write_failed", "path": str(e.path), "detail": str(err),
                                 "hint": "The record file could not be rewritten; what was written to Zotero stands."}
    return out.finish({"dry_run": True} if dry_run else None)


def tidy(line, answers=()):
    """Drop a hint from a line whose code is ok, skipped or an answer."""
    if outcome(line, answers) != "failed":
        line.pop("hint", None)
    return line
