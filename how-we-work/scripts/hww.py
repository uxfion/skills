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

Examples:
  hww.py sync
  hww.py add experiments
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
    "sync": (None, "bring the common block of a project's AGENTS.md up to date; check the form of its convention files"),
    "add": (None, "make the project's convention file for one kind of work, in the form sync checks"),
}
OK, ACT, CANNOT = 0, 1, 2
COMMON = Path(__file__).resolve().parent.parent / "common.md"
COMMON_ENV = "HOW_WE_WORK_COMMON"
# A convention file adds to one reference of the skill and carries its name. Two references are about the skill
# itself and take none.
REFERENCES = Path(__file__).resolve().parent.parent / "references"
NOT_KINDS = {"adopting", "maintaining"}
CONVENTIONS = Path("docs") / "conventions"
REFERENCE_LINE = "Read the how-we-work skill's {kind} reference first (invoke the skill); this file only adds to it."
# The two markers, as HTML comments. A begin marker may carry any text after `begin`, a note to the reader.
BEGIN = re.compile(rb"<!--[ \t]*how-we-work:begin\b.*?-->", re.S)
END = re.compile(rb"<!--[ \t]*how-we-work:end[ \t]*-->")
# The day the block last changed, in its begin marker: `rev 2026-11-10`, or `2026-11-10.2` for a further change that day.
REV = re.compile(rb"how-we-work:begin[ \t]+rev[ \t]+(\d{4})-(\d{2})-(\d{2})(?:\.(\d+))?")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.*)$")
FENCE = re.compile(r"^(?:(`{3,})[^`]*|(~{3,}).*)$")   # a code fence opening in the line's first column

SYNC = """Bring the how-we-work block of a project's AGENTS.md up to date, and check the form of its convention files.

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

Convention files. Each docs/conventions/*.md beside FILE adds to one reference of the skill and is checked for its
form: its name is that reference's (`hww.py add -h` lists them), and before its first `## ` heading it holds the
line that sends the reader to the reference first. `hww.py add KIND` makes a file in this form. A file that is not
in it is listed, for you to put right. sync reads no entry: what a rule says, and whether it holds beyond this
project, is not the script's to judge.

stdout: one JSON line for the block, then one for each convention file that is not in form, in name order.
  {code: "ok", file, block}                block: "updated" or "current"; with -n, an "updated" line adds
                                           dry_run: true and FILE is as it was
  {code: "convention", file, problems, hint}
                                           problems: unknown_kind, no_reference_line, or both

Exit status: 0 = the block is current or was brought up to date, and every convention file is in form; 1 = a
convention file is not in form: stderr ends with {"summary": {conventions}}; 2 = cannot go on: FILE is as it was,
and stderr's last line is {code, hint, ...}, the code one of
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
  hww.py sync -n | jq -r 'select(.code == "convention") | .file'
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


def kinds():
    """The kinds of work a project may keep a convention file for: the skill's references, by name."""
    return sorted(f.stem for f in REFERENCES.glob("*.md") if f.stem not in NOT_KINDS)


def convention_problems(path, known):
    """What keeps a convention file from being in form, as a list of names; empty when it is."""
    reference_line, fence = False, None
    expected = REFERENCE_LINE.format(kind=path.stem)
    for line in path.read_bytes().decode("utf-8-sig", errors="replace").splitlines():
        if fence:                         # a fenced example is not the file's own text
            closing = line.rstrip()
            if len(closing) >= len(fence) and set(closing) == {fence[0]}:
                fence = None
            continue
        if opening := FENCE.match(line):
            fence = opening.group(1) or opening.group(2)
            continue
        heading = HEADING.match(line)
        if heading and len(heading.group(1)) == 2:
            break                         # the line stands before the first `## ` heading
        if line.strip() == expected:
            reference_line = True
            break
    return [name for name, ok in (("unknown_kind", path.stem in known), ("no_reference_line", reference_line))
            if not ok]


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

    known, out_of_form = kinds(), 0
    for f in sorted((path.parent / CONVENTIONS).glob("*.md")):
        if f.is_file() and (problems := convention_problems(f, known)):
            out_of_form += 1
            emit({"code": "convention", "file": str(f), "problems": problems,
                  "hint": f"A convention file is named for a reference of the skill ({', '.join(known)}) and holds "
                          f"the line `{REFERENCE_LINE.format(kind='<its name>')}` before its first `## ` heading. Put "
                          f"right what `problems` names; what a file of an unknown kind holds moves to the kind it "
                          f"belongs to, or, a rule for every task, to AGENTS.md outside the block. `{SELF} add KIND` "
                          f"makes a file in form."})
    if out_of_form:
        emit({"summary": {"conventions": out_of_form}}, sys.stderr)
        return ACT
    return OK


ADD = """Make the project's convention file for one kind of work: docs/conventions/KIND.md, in the current directory.

A convention file holds what this project adds to one reference of the skill, and carries that reference's name.
add writes it in the form sync checks: a title and the line that sends the reader to the reference first; the
entries under it are yours to write. A file that is already there is left as it is. Run it in the project's root,
where AGENTS.md is.

KIND is one of: {kinds}

stdout: one JSON line, {{code: "ok", file, created}}; created is false when the file was already there, and with -n
the line adds dry_run: true and nothing is written.

Exit status: 0 = the file is there; 2 = cannot go on: nothing was written, and stderr's last line is
{{code, hint, ...}}, the code one of
  unknown_kind            KIND is no reference of the skill: `kinds` lists them
  file_not_found          no AGENTS.md in the current directory: this is not a project's root
  write_failed            the file could not be written
  usage                   the command line cannot be read

Example:
  hww.py add experiments
"""


def add(argv):
    known = kinds()
    first, _, rest = ADD.format(kinds=", ".join(known)).strip().partition("\n")
    p = Parser(prog=f"{SELF} add", description=first, epilog=rest.strip(),
               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-n", "--dry-run", action="store_true", help="say what would be made, and write nothing")
    p.add_argument("kind", metavar="KIND", help="the kind of work, by the name of its reference")
    args = p.parse_intermixed_args(argv)

    if args.kind not in known:
        raise Stop("unknown_kind", "A convention file adds to a reference of the skill and carries its name: `kinds` "
                                   "lists them. What belongs to no kind of work is a rule for every task (AGENTS.md, "
                                   "outside the block) or a fact for the project's own documents. Nothing was written.",
                   kind=args.kind, kinds=known)
    if not Path("AGENTS.md").is_file():
        raise Stop("file_not_found", "Run add in the project's root, where AGENTS.md is. Nothing was written.",
                   file="AGENTS.md")
    path = CONVENTIONS / f"{args.kind}.md"
    done = {"code": "ok", "file": str(path), "created": not path.exists()}
    if done["created"]:
        if args.dry_run:
            done["dry_run"] = True
        else:
            title = args.kind.replace("-", " ").capitalize()
            text = f"# {title}: this project\n\n{REFERENCE_LINE.format(kind=args.kind)}\n"
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="")
            except OSError as e:
                raise Stop("write_failed", "The file could not be written: `detail` says why.", file=str(path),
                           detail=str(e))
    emit(done)
    return OK


WORD_RUNS = {"sync": sync, "add": add}


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
