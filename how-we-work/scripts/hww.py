#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""how-we-work: the common block of working rules, kept current in the project an agent works in.

Every word runs here, in hww.py; an unknown word exits 2 with this list.

Exit codes, every word: 0 done (stderr empty); 1 something is yours to act on: stdout's lines say what, and stderr
ends with {"summary": ...}; 2 the command cannot go on (no block markers, a missing file, a usage error): the
file is as it was, and stderr's last line is {code, hint, ...}.

Example:
  hww.py sync
"""
import argparse
import contextlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

SELF = Path(__file__).name
# word: (script, what it does). Every word runs here, in hww.py, so none has a script of its own.
WORDS = {
    "sync": (None, "bring the common block of a project's AGENTS.md up to date; list its rules waiting to be promoted"),
}
OK, ACT, CANNOT = 0, 1, 2
COMMON = Path(__file__).resolve().parent.parent / "common.md"
COMMON_ENV = "HOW_WE_WORK_COMMON"
# The two markers, as HTML comments. A begin marker may carry any text after `begin`, a note to the reader.
BEGIN = re.compile(rb"<!--[ \t]*how-we-work:begin\b.*?-->", re.S)
END = re.compile(rb"<!--[ \t]*how-we-work:end[ \t]*-->")
# The day the block last changed, in its begin marker: `rev 2026-11-10`, or `2026-11-10.2` for a further change that day.
REV = re.compile(rb"how-we-work:begin[ \t]+rev[ \t]+(\d{4})-(\d{2})-(\d{2})(?:\.(\d+))?")
# What an agent writes at an entry's end once it has judged it (the skill's SKILL.md gives the two forms).
MARK = re.compile(r"\((issue|judged)\b[^()]*\)\s*$")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.*)$")
TO_PROMOTE = ("待提升", "to promote")              # a `## ` heading holding either opens the section
ITEM = re.compile(r"^(?:[-*+]|\d+[.)])[ \t]+(.*)$")   # a list item starting in the line's first column
FENCE = re.compile(r"^(?:(`{3,})[^`]*|(~{3,}).*)$")   # a code fence opening in the line's first column

SYNC = """Bring the how-we-work block of a project's AGENTS.md up to date, and list the project's rules waiting to be promoted.

The block. In FILE and in the skill's common.md alike, the block runs from the comment
`<!-- how-we-work:begin ... -->` (any text may follow `begin`) through the comment `<!-- how-we-work:end -->`, both
included. sync replaces FILE's block with common.md's, byte for byte, markers included, so the note in the begin
marker comes from the skill as well. Every byte of FILE outside its block stays as it is, and what common.md holds
outside its own block stays in the skill. A block already equal to common.md's is left alone: FILE is not written.
The begin marker carries the day the block last changed (`rev 2026-11-10`, `rev 2026-11-10.2`). Where FILE's block
is of a later day than common.md's, this install of the skill is behind: sync writes nothing and exits 2.

sync never chooses where the block goes. For a project's first sync (the skill's references/adopting.md has what
comes before it), decide the place, put an empty pair there, and run sync:
  <!-- how-we-work:begin -->
  <!-- how-we-work:end -->
common.md is the one in the skill's directory, beside scripts/; HOW_WE_WORK_COMMON names another file.

To promote. In FILE outside its block (a rule for every task that the project holds), and in each
docs/conventions/*.md beside FILE, under a `## ` heading that holds "待提升" or "To promote", up to the next `# `
or `## ` heading, every list item starting in the first column is one entry, with the lines that continue it. Text
there outside a list item is not listed, and a fenced example starting in the first column is not read. sync judges
no entry: whether one holds beyond this project, or the common rules now cover it, is yours to judge.

stdout: one JSON line for the block, then one for each entry: FILE's own first, then the convention files in name
order.
  {code: "ok", file, block}                block: "updated" or "current"; with -n, an "updated" line adds
                                           dry_run: true and FILE is as it was
  {code: "to_promote", file, line, entry, mark}
                                           file: FILE or the convention file; line: where the item starts; entry: its
                                           text as written, without the list marker; mark: "issue" or "judged" when the
                                           entry ends in `(issue: ...)` or `(judged ...: stays)`, else null

Exit status: 0 = no entry waits: there is none, or each carries a mark and the block was already current; 1 = entries
wait to be judged, those whose mark is null, or all of them when the block was just updated: stderr ends with
{"summary": {to_promote, unjudged, files}}; 2 = cannot go on: FILE is as it was, and stderr's last line is
{code, hint, ...}, the code one of
  no_block                FILE holds no marker
  unclosed_block          a begin marker with no end marker after it, or an end marker alone
  several_blocks          more than one begin or end marker (one quoted in the text counts)
  file_not_found          FILE is not a file
  no_common, bad_common   the skill's common.md is missing, or does not hold exactly one block
  older_common            FILE's block is of a later day than the skill's: this install is behind
  write_failed            FILE could not be replaced by its new content: it is as it was
  usage                   the command line cannot be read

Examples:
  hww.py sync
  hww.py sync -n | jq -r 'select(.code == "to_promote") | "\\(.file):\\(.line)"'
"""


class Stop(Exception):
    """The command cannot go on: main() prints its line as stderr's last and exits 2."""

    def __init__(self, code, hint, **extra):
        super().__init__(code)
        self.line = {"code": code, **extra, "hint": hint}


# write and emit: copied from paper-read/scripts/prlib/cli.py at c0f7940; each skill keeps its own copy.
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


class Parser(argparse.ArgumentParser):
    def error(self, message):
        """A usage error: the usage line, then {code: usage, hint} as stderr's last line; exit 2."""
        self.print_usage(sys.stderr)
        emit({"code": "usage", "detail": message, "hint": f"See {self.prog} -h."}, sys.stderr)
        raise SystemExit(CANNOT)


def find_block(data):
    """((start, end) of the one block in `data`, None), or (None, why there is not exactly one). Either way with the
    lines the markers stand on, {begin: [...], end: [...]}."""
    begins, ends = list(BEGIN.finditer(data)), list(END.finditer(data))
    lines = {name: [data.count(b"\n", 0, m.start()) + 1 for m in found] for name, found in (("begin", begins), ("end", ends))}
    if not begins and not ends:
        return None, "no_block", lines
    if len(begins) > 1 or len(ends) > 1:
        return None, "several_blocks", lines
    if not begins or not ends or ends[0].start() < begins[0].end():
        return None, "unclosed_block", lines
    return (begins[0].start(), ends[0].end()), None, lines


HINTS = {
    "no_block": "This file has no how-we-work block. Unless the user asked for this project to adopt the rules, "
                "leave the file as it is. If they did, read the skill's references/adopting.md first: the user sees "
                "the accounting of the project's old rules before the block goes in. Then put an empty pair where "
                "the block belongs, `<!-- how-we-work:begin -->` and `<!-- how-we-work:end -->` each on its own "
                "line, and run sync again.",
    "unclosed_block": "A marker has no partner: `begin` and `end` give the lines the markers stand on. Read the file "
                      "there, restore one `<!-- how-we-work:begin -->` ... `<!-- how-we-work:end -->` pair around "
                      "the block, and run sync again.",
    "several_blocks": "More than one begin or end marker: `begin` and `end` give their lines. A file holds one block, "
                      "and a marker quoted in the text counts as one. Leave one pair, and run sync again.",
}


def rev(marker_data):
    """The day in a block's begin marker as a tuple to compare, or None where the marker carries none."""
    m = REV.search(marker_data)
    return tuple(int(g or 0) for g in m.groups()) if m else None


def rev_text(r):
    return f"{r[0]:04d}-{r[1]:02d}-{r[2]:02d}" + (f".{r[3]}" if r[3] else "")


def common_block():
    """The block of the skill's common.md, markers included."""
    path = Path(os.environ.get(COMMON_ENV) or COMMON)
    if not path.is_file():
        raise Stop("no_common", f"The skill's common.md is not there: the skill is installed incompletely. Nothing "
                                f"was written. ({COMMON_ENV} names another file.)", path=str(path))
    data = path.read_bytes()
    span, why, lines = find_block(data)
    if why:
        raise Stop("bad_common", "The skill's common.md must hold exactly one block, from its begin marker through "
                                 "its end marker. That is the skill's to fix. Nothing was written.",
                   path=str(path), detail=why, **lines)
    return data[span[0]:span[1]]


def to_promote(path, skip=None):
    """[(line number, text)]: the entries of a file's to-promote sections; `skip` is a (first, last) range of
    lines left out, the how-we-work block of the project's AGENTS.md. A fenced block that opens in the first column
    is an example, read neither for headings nor for items; a fence indented under an item is that item's text."""
    entries, current, inside, blank, fence = [], None, False, False, None
    for number, line in enumerate(path.read_bytes().decode("utf-8-sig", errors="replace").splitlines(), 1):
        if skip and skip[0] <= number <= skip[1]:
            current, inside, blank, fence = None, False, False, None   # the block opens with its own `# ` heading
            continue
        if fence:                         # inside a fenced example, up to a closing fence at least as long
            closing = line.rstrip()
            if len(closing) >= len(fence) and set(closing) == {fence[0]}:
                fence = None
            blank = False
            continue
        if opening := FENCE.match(line):
            fence, current, blank = opening.group(1) or opening.group(2), None, False
            continue
        heading, item = HEADING.match(line), ITEM.match(line)
        if heading:
            current = None
            if len(heading.group(1)) <= 2:
                inside = len(heading.group(1)) == 2 and any(t in heading.group(2).casefold() for t in TO_PROMOTE)
        elif inside and item:
            current = [item.group(1).rstrip()]
            entries.append((number, current))
        elif current is not None:
            if line.strip() and blank and not line[0].isspace():
                current = None            # a paragraph of its own after a blank line: no longer the item's
            else:
                current.append(line.rstrip())
        blank = not line.strip()
    return [(number, text) for number, lines in entries if (text := "\n".join(lines).rstrip())]


def replace(path, data):
    """`data` becomes the content of the file at `path`, or the file stays as it was: the bytes go to a temporary
    file beside it, which then takes its place. A symlink stays one: the file it names is the one replaced."""
    target = path.resolve()
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        with contextlib.suppress(OSError):        # a file system without modes
            shutil.copymode(target, tmp)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def sync(argv):
    first, _, rest = SYNC.strip().partition("\n")
    p = Parser(prog=f"{SELF} sync", description=first, epilog=rest.strip(),
               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-n", "--dry-run", action="store_true", help="say what would change, and write nothing")
    p.add_argument("file", metavar="FILE", nargs="?", default="AGENTS.md",
                   help="the project's AGENTS.md (default: AGENTS.md in the current directory)")
    args = p.parse_intermixed_args(argv)

    path = Path(args.file)
    if not path.is_file():
        raise Stop("file_not_found", "Name the project's AGENTS.md, or run sync in the project's root.", file=args.file)
    block = common_block()
    data = path.read_bytes()
    span, why, lines = find_block(data)
    if why:
        raise Stop(why, HINTS[why] + " Nothing was written.", file=args.file, **lines)
    have, mine = rev(data[span[0]:span[1]]), rev(block)
    if have and mine and have > mine:
        raise Stop("older_common", "This install of the skill is older than the block in FILE: reinstall the skill, "
                                   "then run sync again. Nothing was written.", file=args.file,
                   rev={"file": rev_text(have), "common": rev_text(mine)})
    done = {"code": "ok", "file": args.file, "block": "current"}
    if data[span[0]:span[1]] != block:
        done["block"] = "updated"
        if args.dry_run:
            done["dry_run"] = True
        else:
            try:
                replace(path, data[:span[0]] + block + data[span[1]:])
            except OSError as e:
                raise Stop("write_failed", "The file could not be replaced by its new content: `detail` says why. "
                                           "It is as it was.", file=args.file, detail=str(e))
    emit(done)

    # the project's own part of FILE first (the block's lines left out), then the convention files in name order
    now = path.read_bytes()
    span, why, _ = find_block(now)
    inside = None if why else (now[:span[0]].count(b"\n") + 1, now[:span[1]].count(b"\n") + 1)
    found = {args.file: to_promote(path, inside)}
    files = sorted((path.parent / "docs" / "conventions").glob("*.md"))
    found.update({str(f): to_promote(f) for f in files if f.is_file()})
    unjudged = 0
    for name, entries in found.items():
        for number, text in entries:
            mark = MARK.search(text)
            unjudged += mark is None
            emit({"code": "to_promote", "file": name, "line": number, "entry": text, "mark": mark and mark.group(1)})
    total = sum(map(len, found.values()))
    # marked entries wait for nothing, until the block changes: then each is judged against the new block
    if unjudged or (total and done["block"] == "updated"):
        emit({"summary": {"to_promote": total, "unjudged": unjudged,
                          "files": sum(1 for entries in found.values() if entries)}}, sys.stderr)
        return ACT
    return OK


WORD_RUNS = {"sync": sync}


def listing():
    width = max(map(len, WORDS)) + 2
    first, _, rest = __doc__.strip().partition("\n")
    words = "\n".join(f"  {word:<{width}}{text}" for word, (_, text) in WORDS.items())
    return f"usage: {SELF} WORD [options] [operands]   ({SELF} WORD -h for each)\n\n{first}\n\nwords:\n{words}\n\n{rest.strip()}\n"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    word = argv[0] if argv else None
    if word in ("-h", "--help"):
        write(listing())
        return OK
    if word not in WORDS:
        sys.stderr.write(listing())
        emit({"code": "usage", "detail": f"no word {word!r}" if word else "name a word", "hint": f"See {SELF} -h."},
             sys.stderr)
        return CANNOT
    try:
        return WORD_RUNS[word](argv[1:])
    except Stop as stop:
        emit(stop.line, sys.stderr)
        return CANNOT


if __name__ == "__main__":
    sys.exit(main())
