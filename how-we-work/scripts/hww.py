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
  hww.py add rules
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
    "sync": (None, "bring the common block of a project's AGENTS.md up to date; keep its convention files and its rules file in form"),
    "add": (None, "make the project's convention file for one kind of work, or its rules file, in the form sync keeps"),
}
OK, ACT, CANNOT = 0, 1, 2
COMMON = Path(__file__).resolve().parent.parent / "common.md"
COMMON_ENV = "HOW_WE_WORK_COMMON"
# A convention file adds to one reference of the skill and carries its name. Three references take none: two are
# about the skill itself, and project-rules says where a project's own rules go.
REFERENCES = Path(__file__).resolve().parent.parent / "references"
NOT_KINDS = {"adopting", "maintaining", "project-rules"}
CONVENTIONS = Path("docs") / "conventions"
# The line under a convention file's title. It is the script's piece of the file: add writes it, sync writes it where
# it is missing and brings a former wording of it up to date.
REFERENCE_LINE = ("Read `~/.agents/skills/how-we-work/references/{kind}.md` first; this file adds to it, and holds "
                  "for this project where the two differ. It holds how this kind of work is done here; what the "
                  "thing the project builds must be stands in the project's rules file (`docs/rules.md`).")
FORMER_REFERENCE_LINES = ("Read `~/.agents/skills/how-we-work/references/{kind}.md` first; this file adds to it, and "
                          "holds for this project where the two differ.",)
# The project's rules file: what the thing the project builds must be, and rules for kinds of work no reference
# covers. add makes it under this name; a project that keeps its rules in a file of another name puts the marker
# pair there, and sync fills it wherever in docs/ it stands.
RULES = "rules"
RULES_FILE = Path("docs") / "rules.md"
# The projects that carry the block, for the skills repository's session to read: sync adds the one it runs in.
CONFIG = Path.home() / ".config" / "how-we-work" / "config.json"
CONFIG_ENV = "HOW_WE_WORK_CONFIG"
# The two markers, as HTML comments. A begin marker may carry any text after `begin`, a note to the reader.
BEGIN = re.compile(rb"<!--[ \t]*how-we-work:begin\b.*?-->", re.S)
END = re.compile(rb"<!--[ \t]*how-we-work:end[ \t]*-->")
# The day the block last changed, in its begin marker: `rev 2026-11-10`, or `2026-11-10.2` for a further change that day.
REV = re.compile(rb"how-we-work:begin[ \t]+rev[ \t]+(\d{4})-(\d{2})-(\d{2})(?:\.(\d+))?")
# In the rules file, the script's lines: what the file holds, when it is read, and one line for each kind of work
# that has a convention file, from the `description` in the head of that kind's reference. add writes them, sync
# keeps them current.
LIST_OPEN = "<!-- how-we-work:rules — the script's lines, rewritten by `hww.py sync`; write below the end marker -->"
LIST_CLOSE = "<!-- how-we-work:rules-end -->"
LIST = re.compile(r"<!--[ \t]*how-we-work:rules\b.*?-->.*?<!--[ \t]*how-we-work:rules-end[ \t]*-->", re.S)
HEADING = re.compile(r"^(#{1,6})[ \t]+(.*)$")
FENCE = re.compile(r"^(?:(`{3,})[^`]*|(~{3,}).*)$")   # a code fence opening in the line's first column

SYNC = """Bring the how-we-work block of a project's AGENTS.md up to date, and keep its convention files and its rules file in form.

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

Convention files. Each docs/conventions/*.md beside FILE adds to one reference of the skill and carries its name
(`hww.py add -h` lists them). Under its title it holds the line that sends the reader to that reference first; the
line is the script's: sync writes it where it is missing, and replaces a former wording of it. A file named for no
reference is listed, for you to move what it holds.

The rules file. docs/rules.md holds the project's own rules. It opens with the script's lines, between the two
comments `<!-- how-we-work:rules ... -->` and `<!-- how-we-work:rules-end -->`: what the file holds, when it is
read, and one line for each kind of work that has a convention file, with what the head of its reference says.
sync rewrites them where they are out of date, in docs/rules.md and in any other docs/*.md that carries the pair
(a project that keeps its rules under another name places the pair there once). It prints the file's `## `
headings at every sync. sync reads no entry, here or in a convention file: what a rule says, and where it
belongs, is not the script's to judge.

The list of projects. sync adds the project it runs in to `projects` in ~/.config/how-we-work/config.json, the
list the skills repository's session reads the projects from; HOW_WE_WORK_CONFIG names another file.

A project's AGENTS.md holds its title and the block, nothing else: what only the project needs stands in its
rules file, its convention files and its documents. sync reports the lines it finds outside the block and moves
none.

stdout: one JSON line for the block, one for what stands outside it, then one for each convention file sync wrote
to or could not place, in name order, then the lines of each rules file.
  {code: "ok", file, block}                block: "updated" or "current". An "updated" line carries a hint, and
                                           with -n it adds dry_run: true and FILE is as it was. registered: true
                                           when the project was added to the list just now
  {code: "outside", file, lines, hint}     FILE holds more outside its block than a title: the numbers of
                                           those lines, printed at every sync while there are any
  {code: "convention", file, wrote}        wrote: "reference_line"; with -n, dry_run: true and nothing was written
  {code: "convention", file, problems, hint}
                                           problems: ["unknown_kind"]
  {code: "rules", file, wrote, hint}       wrote: "list", the script's lines; with -n, dry_run: true
  {code: "rules", file, headings, hint}    the file's `## ` headings, what its rules are about: printed at every
                                           sync while it has any

Exit status: 0 = the block is current or was brought up to date, and every convention file is named for a
reference; 1 = a convention file is named for none: stderr ends with {"summary": {conventions}}; 2 = cannot go on:
FILE is as it was, and stderr's last line is {code, hint, ...}, the code one of
  no_block                FILE holds no marker
  unclosed_block          a begin marker with no end marker after it, or an end marker alone
  several_blocks          more than one begin or end marker (one quoted in the text counts)
  file_not_found          FILE is not a file
  no_common, bad_common   the skill's common.md is missing, or does not hold exactly one block
  older_common            FILE's block is of a later day than the skill's: this install is behind
  write_failed            a file could not be replaced by its new content: it is as it was
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
                "leave the file as it is. If they did, read the skill's references/adopting.md first: where the "
                "project has rules of its own, the user sees their accounting before the block goes in. Then put an empty pair where "
                "the block belongs, `<!-- how-we-work:begin -->` and `<!-- how-we-work:end -->` each on its own "
                "line, and run sync again.",
    "unclosed_block": "A marker has no partner: `begin` and `end` give the lines the markers stand on. Read the file "
                      "there, restore one `<!-- how-we-work:begin -->` ... `<!-- how-we-work:end -->` pair around "
                      "the block, and run sync again.",
    "several_blocks": "More than one begin or end marker: `begin` and `end` give their lines. A file holds one block, "
                      "and a marker quoted in the text counts as one. Leave one pair, and run sync again.",
}


def outside(data, span):
    """The numbers of the lines of an AGENTS.md that stand outside its block and are neither blank nor its title
    (the first `# ` heading): a project's AGENTS.md holds nothing else."""
    found, titled, at = [], False, 0
    for number, line in enumerate(data.decode("utf-8-sig", errors="replace").splitlines(keepends=True), 1):
        start, at = at, at + len(line.encode("utf-8", errors="replace"))
        if span[0] <= start < span[1] or not line.strip():
            continue
        if not titled and line.startswith("# "):
            titled = True
            continue
        found.append(number)
    return found


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


def has_reference_line(path):
    """Whether a convention file holds its reference line before its first `## ` heading."""
    expected, fence = REFERENCE_LINE.format(kind=path.stem), None
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
            return False                  # the line stands before the first `## ` heading
        if line.strip() == expected:
            return True
    return False


def with_reference_line(data, kind):
    """A convention file's bytes with its reference line: a former wording of the line replaced where it stands,
    otherwise the line put under the title, or at the top where the file opens with no `# ` title. The file's own
    line ending is kept."""
    nl = b"\r\n" if b"\r\n" in data else b"\n"
    line = REFERENCE_LINE.format(kind=kind).encode()
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    body = data[len(bom):]
    rows = body.split(nl)
    for former in FORMER_REFERENCE_LINES:
        old = former.format(kind=kind).encode()
        for i, row in enumerate(rows):
            if row.strip() == old:
                rows[i] = line
                return bom + nl.join(rows)
    first, sep, rest = body.partition(nl)
    if first.startswith(b"# "):
        return bom + first + nl + nl + line + nl + (rest if rest.startswith(nl) or not rest else nl + rest)
    return bom + line + nl + (nl + body if body else b"")


def head(path):
    """The head of a reference: the `key: value` lines between its two `---` lines, a quoted value read as JSON."""
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    fields = {}
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            key, sep, value = line.partition(":")
            value = value.strip()
            if sep and value:
                with contextlib.suppress(ValueError):
                    value = json.loads(value) if value.startswith('"') else value
                fields[key.strip()] = value
    return fields


def kind_rows():
    """One line for each kind of work that has a convention file, with what the head of its reference says."""
    rows = []
    for kind in kinds():
        description = head(REFERENCES / f"{kind}.md").get("description")
        rows.append(f"- `{kind}`: {description}" if isinstance(description, str) else f"- `{kind}`")
    return rows


def list_lines(nl="\n"):
    """The script's lines of a rules file: what it holds, when it is read, and the kinds of work that have a
    convention file."""
    return nl.join([LIST_OPEN,
                    "What the thing this project builds must be, and how it is designed and changed; after that, "
                    "rules for kinds of work that have no reference. Read it whole before designing or changing what "
                    "the project builds. It holds over a convention file on the same matter.", "",
                    "A rule about how one of these kinds of work is done here stands in `docs/conventions/<name>.md`:",
                    "", *kind_rows(), "",
                    "Nothing of the project's stands in `AGENTS.md`. A fact stands in the project's documents, or "
                    "with the rules of the kind of work that needs it.",
                    LIST_CLOSE])


def with_list_lines(data):
    """A rules file with the script's lines as they now read: replaced where the two markers are, put under the
    title (or on top, where there is none) where they are not. None when they already read so."""
    nl = "\r\n" if b"\r\n" in data else "\n"
    text, lines = data.decode("utf-8", errors="surrogateescape"), list_lines(nl)
    if found := LIST.search(text):
        new = text[:found.start()] + lines + text[found.end():]
    else:
        first, sep, rest = text.partition(nl)
        at = len(first) + len(sep) if first.startswith("# ") else 0
        new = text[:at] + (nl if at else "") + lines + nl + ("" if text[at:].startswith(nl) or not text[at:] else nl) + text[at:]
    return None if new == text else new.encode("utf-8", errors="surrogateescape")


def headings(data):
    """The `## ` headings of a rules file, a fenced example left out: what its rules are about."""
    found, fence = [], None
    for line in data.decode("utf-8-sig", errors="replace").splitlines():
        if fence:
            closing = line.rstrip()
            if len(closing) >= len(fence) and set(closing) == {fence[0]}:
                fence = None
            continue
        if opening := FENCE.match(line):
            fence = opening.group(1) or opening.group(2)
            continue
        heading = HEADING.match(line)
        if heading and len(heading.group(1)) == 2:
            found.append(heading.group(2).strip())
    return found


def register(project):
    """Add a project's path to `projects` in the config, the list the skills repository's session reads. True when
    it was added just now; a config that cannot be read or written is left as it is."""
    path = Path(os.environ.get(CONFIG_ENV) or CONFIG)
    try:
        config = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if not isinstance(config, dict):
            return False
        projects = config.setdefault("projects", [])
        if not isinstance(projects, list) or str(project) in projects:
            return False
        projects.append(str(project))
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            replace(path, (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode())
        else:
            path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return True
    except (OSError, ValueError):
        return False


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
    if done["block"] == "updated":
        done["hint"] = ("The block changed: read it again from the file, since the copy in your context is the old "
                        "one. A subagent started from your context has the old copy too.")
    if not args.dry_run and register(path.resolve().parent):
        done["registered"] = True
    emit(done)
    if done["block"] == "updated" and not args.dry_run:       # the numbers are those of the file as it now stands
        data, span = data[:span[0]] + block + data[span[1]:], (span[0], span[0] + len(block))
    if own := outside(data, span):
        emit({"code": "outside", "file": args.file, "lines": own,
              "hint": "AGENTS.md holds the project's title and the block, nothing else. These lines stand outside "
                      "the block: add nothing there. Each belongs in the rules file, a convention file or one of the "
                      "project's documents (the project-rules reference, *Which file*); where each goes is the "
                      "user's to approve, and the skills repository's session moves them with the user."})

    known, unplaced = kinds(), 0
    for f in sorted((path.parent / CONVENTIONS).glob("*.md")):
        if not f.is_file():
            continue
        if f.stem not in known:
            unplaced += 1
            emit({"code": "convention", "file": str(f), "problems": ["unknown_kind"],
                  "hint": f"A convention file is named for a reference of the skill ({', '.join(known)}). Move what "
                          f"this one holds to the places the block's *How a rule grows* gives (the project-rules "
                          f"reference has examples): how one of those kinds of work is done here into that kind's file "
                          f"(`{SELF} add KIND` makes it), any other rule into the rules file (`{SELF} add {RULES}`). "
                          f"Then remove the file: its content has moved, so that is part of the move and yours to do."})
        elif not has_reference_line(f):
            if not args.dry_run:
                try:
                    replace(f, with_reference_line(f.read_bytes(), f.stem))
                except OSError as e:
                    raise Stop("write_failed", "A convention file could not be written: `detail` says why. It is as "
                                               "it was.", file=str(f), detail=str(e))
            emit({"code": "convention", "file": str(f), "wrote": "reference_line", **({"dry_run": True} if args.dry_run else {})})

    docs = path.parent / RULES_FILE.parent
    for f in sorted(docs.glob("*.md")):
        if not f.is_file():
            continue
        data = f.read_bytes()
        if f.name != RULES_FILE.name and not LIST.search(data.decode("utf-8", errors="replace")):
            continue                      # a rules file is docs/rules.md, or the file that carries the marker pair
        if (new := with_list_lines(data)) is not None:
            if not args.dry_run:
                try:
                    replace(f, new)
                except OSError as e:
                    raise Stop("write_failed", "The rules file could not be written: `detail` says why. It is as it "
                                               "was.", file=str(f), detail=str(e))
            data = new
            emit({"code": "rules", "file": str(f), "wrote": "list", **({"dry_run": True} if args.dry_run else {}),
                  "hint": "The list that opens this file was brought up to date: a rule under one of its headings "
                          "that one of the listed kinds now covers moves to that kind's convention file."})
        if found := headings(data):
            emit({"code": "rules", "file": str(f), "headings": found,
                  "hint": "This project's own rules. Read the file whole before designing or changing what the "
                          "project builds; before work of a kind one of these headings names, read that section."})
    if unplaced:
        emit({"summary": {"conventions": unplaced}}, sys.stderr)
        return ACT
    return OK


ADD = """Make the project's convention file for one kind of work, docs/conventions/KIND.md, or its rules file, docs/rules.md.

A convention file holds how one kind of work is done in this project, and carries the name of the reference it
adds to. add writes it in the form sync keeps: a title and the line that sends the reader to the reference first;
the entries under it are yours to write. `rules` makes the project's rules file instead: what the thing the project
builds must be, and rules for kinds of work that have no reference; it opens with the script's lines, which list
the kinds below. A file that is already there is left as it is. Run it in the project's root, where AGENTS.md is.

KIND is `rules`, or the name of a reference that takes a convention file:
{kinds}

stdout: one JSON line, {{code: "ok", file, created}}; created is false when the file was already there, and with -n
the line adds dry_run: true and nothing is written.

Exit status: 0 = the file is there; 2 = cannot go on: nothing was written, and stderr's last line is
{{code, hint, ...}}, the code one of
  unknown_kind            KIND is none of the names above: `kinds` lists them
  file_not_found          no AGENTS.md in the current directory: this is not a project's root
  write_failed            the file could not be written
  usage                   the command line cannot be read

Examples:
  hww.py add experiments
  hww.py add rules
"""


def add(argv):
    known = kinds()
    first, _, rest = ADD.format(kinds="\n".join("  " + row[2:] for row in kind_rows())).strip().partition("\n")
    p = Parser(prog=f"{SELF} add", description=first, epilog=rest.strip(),
               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-n", "--dry-run", action="store_true", help="say what would be made, and write nothing")
    p.add_argument("kind", metavar="KIND", help="`rules`, or the kind of work by the name of its reference")
    args = p.parse_intermixed_args(argv)

    if args.kind != RULES and args.kind not in known:
        raise Stop("unknown_kind", "A convention file adds to a reference of the skill and carries its name: `kinds` "
                                   f"lists them. A rule none of them covers goes into the rules file (`{SELF} add "
                                   f"{RULES}`). Nothing was written.", kind=args.kind, kinds=known)
    if not Path("AGENTS.md").is_file():
        raise Stop("file_not_found", "Run add in the project's root, where AGENTS.md is. Nothing was written.",
                   file="AGENTS.md")
    path = RULES_FILE if args.kind == RULES else CONVENTIONS / f"{args.kind}.md"
    done = {"code": "ok", "file": str(path), "created": not path.exists()}
    if done["created"]:
        if args.dry_run:
            done["dry_run"] = True
        else:
            title = args.kind.replace("-", " ").capitalize()
            text = f"# {title}: this project\n\n" + (
                f"{list_lines()}\n" if args.kind == RULES else f"{REFERENCE_LINE.format(kind=args.kind)}\n")
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
