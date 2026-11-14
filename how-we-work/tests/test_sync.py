# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for hww.py sync, each run through the entry as an agent runs it: uv run how-we-work/tests/test_sync.py

The skill's own common.md is not used: every run names a small one of the test's through HOW_WE_WORK_COMMON. The
expected bytes and lines are written by hand.
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ENTRY = Path(__file__).resolve().parent.parent / "scripts" / "hww.py"
REFERENCES = ENTRY.parent.parent / "references"

# The block as the skill holds it, and a common.md around it: the note above the block and the line below stay in the skill.
BLOCK = ("<!-- how-we-work:begin — synced from the skill; do not edit inside this block. -->\n"
         "\n# How we work\n\n- Ask one question at a time. 一次一个问题。\n\n"
         "<!-- how-we-work:end -->").encode()
COMMON = b"<!-- Draft 3: a note for whoever maintains the skill. -->\n\n" + BLOCK + b"\nA line after the block.\n"
EMPTY_PAIR = b"<!-- how-we-work:begin -->\n<!-- how-we-work:end -->"
REFERENCE_LINE = ("Read `~/.agents/skills/how-we-work/references/{kind}.md` first; this file adds to it, and holds "
                  "for this project where the two differ.")
OLD = 1_600_000_000   # a modification time long past: a write would move it


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="hww-"))
        self.common = self.dir / "common.md"
        self.common.write_bytes(COMMON)
        self.project = self.dir / "project"
        self.project.mkdir()
        self.file = self.project / "AGENTS.md"

    def run_entry(self, *argv, cwd=None, common=None, whole=False):
        """(exit status, stdout's lines, stderr). The block's line comes without its `hint` and `registered`, which one
        test reads with whole=True."""
        # the list of projects goes to a file of the test's, never to the real config
        env = {**os.environ, "HOW_WE_WORK_COMMON": str(common or self.common),
               "HOW_WE_WORK_CONFIG": str(self.dir / "config" / "config.json")}
        done = subprocess.run(["uv", "run", "--quiet", "--script", str(ENTRY), *map(str, argv)], capture_output=True,
                              text=True, env=env, cwd=cwd)
        lines = [json.loads(line) for line in done.stdout.splitlines()]
        if not whole:
            lines = [{k: v for k, v in line.items() if k not in ("hint", "registered")} if line.get("code") == "ok" and "block" in line else line
                     for line in lines]
        return done.returncode, lines, done.stderr

    def put(self, data):
        """The project's AGENTS.md with these bytes, last modified long ago."""
        self.file.write_bytes(data)
        os.utime(self.file, (OLD, OLD))

    def untouched(self, data):
        return self.file.read_bytes() == data and self.file.stat().st_mtime == OLD


class Sync(Base):
    def test_first_sync_fills_the_empty_pair_and_a_second_run_writes_nothing(self):
        before, after = b"# Project\n\nIts goal.\n\n", b"\n\n## This project's own rules\n\n- Figures in English.\n"
        self.put(before + EMPTY_PAIR + after)
        # a convention file whose to-promote section holds no entry: nothing waits
        conventions = self.project / "docs" / "conventions"
        conventions.mkdir(parents=True)
        (conventions / "reports.md").write_text("# Reports: this project\n\n" + REFERENCE_LINE.format(kind="reports") + "\n\n"
                                                "## This project only\n\n- **A rule.** Why here only: x.\n\n"
                                                "## To promote (待提升)\n\nNothing yet.\n", encoding="utf-8")

        status, lines, err = self.run_entry("sync", self.file, whole=True)
        self.assertEqual((status, {k: v for k, v in lines[0].items() if k != "hint"}, len(lines), err),
                         (0, {"code": "ok", "file": str(self.file), "block": "updated", "registered": True}, 1, ""))
        self.assertIn("read it again", lines[0]["hint"])
        self.assertEqual(self.file.read_bytes(), before + BLOCK + after)

        os.utime(self.file, (OLD, OLD))
        # FILE left out: AGENTS.md of the current directory
        self.assertEqual(self.run_entry("sync", cwd=self.project),
                         (0, [{"code": "ok", "file": "AGENTS.md", "block": "current"}], ""))
        self.assertTrue(self.untouched(before + BLOCK + after), "a current block is not written again")

    def test_bytes_outside_the_block_stay_with_crlf_and_no_final_newline(self):
        before = "# 项目\r\n\r\ntext before \r\n".encode()
        stale = b"<!-- how-we-work:begin an older note -->\r\n# How we work\r\n\r\n- A rule since dropped.\r\n<!-- how-we-work:end -->"
        after = b"\r\n\r\n## Own rules\r\n- one\r\nlast line, no newline after it"
        self.put(before + stale + after)
        self.assertEqual(self.run_entry("sync", self.file)[:2],
                         (0, [{"code": "ok", "file": str(self.file), "block": "updated"}]))
        self.assertEqual(self.file.read_bytes(), before + BLOCK + after)

        # the end marker as the file's last bytes: no newline is added
        self.put(b"intro\n" + EMPTY_PAIR)
        self.assertEqual(self.run_entry("sync", self.file)[0], 0)
        self.assertEqual(self.file.read_bytes(), b"intro\n" + BLOCK)
        os.utime(self.file, (OLD, OLD))
        self.assertEqual(self.run_entry("sync", self.file)[:2],
                         (0, [{"code": "ok", "file": str(self.file), "block": "current"}]))
        self.assertTrue(self.untouched(b"intro\n" + BLOCK))

    def test_dry_run_writes_nothing(self):
        stale = b"top\n" + EMPTY_PAIR + b"\nbottom\n"
        self.put(stale)
        for argv in (("sync", "-n", self.file), ("sync", self.file, "--dry-run")):
            self.assertEqual(self.run_entry(*argv),
                             (0, [{"code": "ok", "file": str(self.file), "block": "updated", "dry_run": True}], ""))
            self.assertTrue(self.untouched(stale))
        # nothing to change and nothing waiting: the one line, and no more
        self.put(b"top\n" + BLOCK + b"\nbottom\n")
        self.assertEqual(self.run_entry("sync", "-n", self.file),
                         (0, [{"code": "ok", "file": str(self.file), "block": "current"}], ""))
        self.assertTrue(self.untouched(b"top\n" + BLOCK + b"\nbottom\n"))

    def test_cannot_go_on_exits_2_with_code_and_hint_and_writes_nothing(self):
        begin, end = b"<!-- how-we-work:begin -->\n", b"<!-- how-we-work:end -->\n"
        cases = [   # the file's bytes, the code, the lines its begin and end markers stand on
            (b"# Project\n\nNo marker here.\n", "no_block", [], []),
            (b"# Project\n" + begin + b"text\n", "unclosed_block", [2], []),
            (b"# Project\n" + end + b"text\n" + begin, "unclosed_block", [4], [2]),
            (b"a\n" + begin + end + b"b\n" + begin + end, "several_blocks", [2, 5], [3, 6]),
        ]
        for data, code, begins, ends in cases:
            with self.subTest(code=code, begins=begins):
                self.put(data)
                status, lines, err = self.run_entry("sync", self.file)
                last = json.loads(err.splitlines()[-1])
                self.assertEqual((status, lines), (2, []))
                self.assertEqual((last["code"], last["file"], last["begin"], last["end"]), (code, str(self.file), begins, ends))
                self.assertTrue(last["hint"])
                self.assertTrue(self.untouched(data))

        good = b"top\n" + EMPTY_PAIR + b"\n"
        self.put(good)
        no_block = self.dir / "no-block.md"
        no_block.write_bytes(b"# How we work\n\nNo markers in the skill's own file.\n")
        others = [   # the arguments, the common.md, the code
            (("sync", self.project / "nothing.md"), None, "file_not_found"),
            (("sync", self.file), self.dir / "no-common.md", "no_common"),
            (("sync", self.file), no_block, "bad_common"),
            (("sync", "--no-such-option", self.file), None, "usage"),
            (("sync", self.file, self.file), None, "usage"),
            (("push", self.file), None, "usage"),
            ((), None, "usage"),
        ]
        for argv, common, code in others:
            with self.subTest(code=code, argv=argv[:1]):
                status, lines, err = self.run_entry(*argv, common=common)
                last = json.loads(err.splitlines()[-1])
                self.assertEqual((status, lines, last["code"]), (2, [], code))
                self.assertTrue(last["hint"])
                self.assertTrue(self.untouched(good))
        # an unknown word is answered with the list of words, which -h prints too
        self.assertIn("\n  sync  ", self.run_entry("push")[2])
        done = subprocess.run(["uv", "run", "--quiet", "--script", str(ENTRY), "-h"], capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertIn("\n  sync  ", done.stdout)

    def test_a_convention_file_gets_its_reference_line_and_one_named_for_no_reference_is_listed(self):
        self.put(b"# Project\n\n" + BLOCK + b"\n\n## To promote\n\n- **An entry in the project's own part: not the script's to read.**\n")
        conventions = self.project / "docs" / "conventions"
        conventions.mkdir(parents=True)
        line = REFERENCE_LINE.format(kind="experiments")
        # in form already, CRLF and a title in Chinese: left as it is
        in_form = ("# 实验：本项目\r\n\r\n" + line + "\r\n\r\n## To promote\r\n\r\n- **图例放右上角。**\r\n").encode()
        (conventions / "experiments.md").write_bytes(in_form)
        # the line only inside a fenced example and after the first `## ` heading: missing, written under the title
        reports = ("# Reports: this project\n\n```markdown\n" + REFERENCE_LINE.format(kind="reports") + "\n```\n\n"
                   "## Later\n\n" + REFERENCE_LINE.format(kind="reports") + "\n")
        (conventions / "reports.md").write_text(reports, encoding="utf-8")
        # another kind's line does not serve; CRLF is kept; no title: the line goes on top
        (conventions / "layout.md").write_bytes(("# Layout: this project\r\n\r\n" + line + "\r\n").encode())
        (conventions / "records.md").write_text("- **An entry and no title.**\n", encoding="utf-8")
        # a topic of the project's own, and a reference that is no kind of work: listed, never written to
        (conventions / "servers.md").write_text("# Servers\n\n- **One GPU box.**\n", encoding="utf-8")
        (conventions / "adopting.md").write_text("# Adopting\n", encoding="utf-8")
        (conventions / "notes.txt").write_text("not a convention file\n", encoding="utf-8")

        def lines_of(lines):
            return [(Path(l["file"]).name, l.get("wrote") or l["problems"]) for l in lines[1:]]
        expected = [("adopting.md", ["unknown_kind"]), ("layout.md", "reference_line"), ("records.md", "reference_line"),
                    ("reports.md", "reference_line"), ("servers.md", ["unknown_kind"])]
        summary = [{"summary": {"conventions": 2}}]

        status, lines, err = self.run_entry("sync", "-n", self.file)       # -n says it and writes nothing
        self.assertEqual((status, lines_of(lines), [json.loads(l) for l in err.splitlines()]), (1, expected, summary))
        self.assertTrue(all(l.get("dry_run") for l in lines[1:] if "wrote" in l))
        self.assertEqual((conventions / "reports.md").read_text(encoding="utf-8"), reports)
        self.assertFalse((self.dir / "config").exists(), "-n registers nothing")

        status, lines, err = self.run_entry("sync", self.file, whole=True)
        self.assertEqual((status, lines_of(lines), [json.loads(l) for l in err.splitlines()]), (1, expected, summary))
        self.assertEqual(lines[0], {"code": "ok", "file": str(self.file), "block": "current", "registered": True})
        self.assertEqual((conventions / "experiments.md").read_bytes(), in_form)
        self.assertEqual((conventions / "reports.md").read_text(encoding="utf-8"),
                         "# Reports: this project\n\n" + REFERENCE_LINE.format(kind="reports") + "\n\n" + reports.split("\n\n", 1)[1])
        self.assertEqual((conventions / "layout.md").read_bytes(),
                         ("# Layout: this project\r\n\r\n" + REFERENCE_LINE.format(kind="layout") + "\r\n\r\n" + line + "\r\n").encode())
        self.assertEqual((conventions / "records.md").read_text(encoding="utf-8"),
                         REFERENCE_LINE.format(kind="records") + "\n\n- **An entry and no title.**\n")
        self.assertEqual((conventions / "servers.md").read_text(encoding="utf-8"), "# Servers\n\n- **One GPU box.**\n")
        # the project is on the list the skills repository's session reads, once
        config = json.loads((self.dir / "config" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config, {"projects": [str(self.project.resolve())]})

        # a second run writes nothing more; the two files named for no reference still wait
        status, lines, err = self.run_entry("sync", self.file)
        self.assertEqual((status, lines[0], lines_of(lines)),
                         (1, {"code": "ok", "file": str(self.file), "block": "current"},
                          [("adopting.md", ["unknown_kind"]), ("servers.md", ["unknown_kind"])]))
        for name in ("servers.md", "adopting.md"):
            (conventions / name).unlink()
        self.assertEqual(self.run_entry("sync", self.file), (0, [{"code": "ok", "file": str(self.file), "block": "current"}], ""))
        self.assertEqual(json.loads((self.dir / "config" / "config.json").read_text(encoding="utf-8")), config)

    def test_an_install_behind_the_projects_block_writes_nothing(self):
        def block(day):
            return (f"<!-- how-we-work:begin rev {day} \u2014 synced from the skill. -->\n\n# How we work\n\n"
                    f"- The rules of {day}.\n\n<!-- how-we-work:end -->").encode()
        older, newer = self.dir / "older.md", self.dir / "newer.md"
        older.write_bytes(block("2026-11-10") + b"\n")
        newer.write_bytes(block("2026-11-10.2") + b"\n")
        project = b"# Project\n\n" + block("2026-11-10.2") + b"\n"
        self.put(project)
        code, out, err = self.run_entry("sync", self.file, common=older)
        last = json.loads(err.strip().splitlines()[-1])
        self.assertEqual((code, out, last["code"], last["rev"]), (2, [], "older_common", {"file": "2026-11-10.2", "common": "2026-11-10"}))
        self.assertTrue(self.untouched(project))
        self.put(b"# Project\n\n" + block("2026-11-10") + b"\n")      # the other direction is an ordinary update
        code, out, _ = self.run_entry("sync", self.file, common=newer)
        self.assertEqual((code, out[0]["block"]), (0, "updated"))
        self.assertIn(b"rev 2026-11-10.2", self.file.read_bytes())

    @unittest.skipIf(os.geteuid() == 0, "root writes through a read-only directory")
    def test_a_file_that_cannot_be_replaced_is_as_it_was(self):
        stale = b"# Project\n\n" + EMPTY_PAIR + b"\n"
        self.put(stale)
        os.chmod(self.project, 0o555)
        try:
            code, out, err = self.run_entry("sync", self.file)
        finally:
            os.chmod(self.project, 0o755)
        last = json.loads(err.strip().splitlines()[-1])
        self.assertEqual((code, out, last["code"]), (2, [], "write_failed"))
        self.assertTrue(last["detail"])
        self.assertTrue(self.untouched(stale))
        self.assertEqual([f.name for f in self.project.iterdir()], ["AGENTS.md"])



class Add(Base):
    """hww.py add makes a convention file that sync finds in form, and only for a kind the skill has a reference for."""

    def test_add_makes_a_file_in_form_once_and_refuses_a_kind_without_a_reference(self):
        self.put(b"# Project\n\n" + BLOCK + b"\n")
        made = self.project / "docs" / "conventions" / "experiments.md"
        text = ("# Experiments: this project\n\n" + REFERENCE_LINE.format(kind="experiments") + "\n"
        )

        code, out, err = self.run_entry("add", "-n", "experiments", cwd=self.project)
        self.assertEqual((code, out, err, made.exists()),
                         (0, [{"code": "ok", "file": "docs/conventions/experiments.md", "created": True, "dry_run": True}], "", False))
        self.assertEqual(self.run_entry("add", "experiments", cwd=self.project),
                         (0, [{"code": "ok", "file": "docs/conventions/experiments.md", "created": True}], ""))
        self.assertEqual(made.read_text(encoding="utf-8"), text)
        # sync finds it in form: one line, nothing waits
        self.assertEqual(self.run_entry("sync", cwd=self.project), (0, [{"code": "ok", "file": "AGENTS.md", "block": "current"}], ""))

        # a file that is there is left as it is, entries and all
        made.write_text(text + "\n- **A rule.** From: 2026-11-12.\n", encoding="utf-8")
        kept = made.read_bytes()
        self.assertEqual(self.run_entry("add", "experiments", cwd=self.project)[:2],
                         (0, [{"code": "ok", "file": "docs/conventions/experiments.md", "created": False}]))
        self.assertEqual(made.read_bytes(), kept)

        # a new topic of the project's is no kind of work: nothing is made
        code, out, err = self.run_entry("add", "our-new-topic", cwd=self.project)
        last = json.loads(err.strip().splitlines()[-1])
        self.assertEqual((code, out, last["code"]), (2, [], "unknown_kind"))
        self.assertIn("experiments", last["kinds"])
        self.assertNotIn("adopting", last["kinds"])
        self.assertEqual(sorted(f.name for f in made.parent.iterdir()), ["experiments.md"])

        # outside a project's root nothing is made either
        code, out, err = self.run_entry("add", "reports", cwd=self.dir)
        self.assertEqual((code, out, json.loads(err.strip().splitlines()[-1])["code"]), (2, [], "file_not_found"))
        self.assertFalse((self.dir / "docs").exists())


class Other(Base):
    """other.md is the convention file for kinds of work that have no reference. It opens with the script's lines,
    one for each kind that has a file; sync keeps them current and leaves what stands below them alone."""

    def test_add_writes_the_list_of_kinds_and_sync_brings_a_stale_one_up_to_date(self):
        self.put(b"# Project\n\n" + BLOCK + b"\n")
        made = self.project / "docs" / "conventions" / "other.md"
        self.assertEqual(self.run_entry("add", "other", cwd=self.project),
                         (0, [{"code": "ok", "file": "docs/conventions/other.md", "created": True}], ""))
        text = made.read_text(encoding="utf-8")
        opening, _, rest = text.partition("<!-- how-we-work:kinds ")
        self.assertEqual(opening, "# Other: this project\n\n" + REFERENCE_LINE.format(kind="other") + "\n\n")
        listed = re.findall(r"^- `([a-z-]+)`: \S", rest, re.M)
        self.assertEqual(listed, sorted(f.stem for f in REFERENCES.glob("*.md") if f.stem not in ("adopting", "maintaining", "other")))
        self.assertTrue(text.endswith("<!-- how-we-work:kinds-end -->\n"))
        # in form as made, with no entry yet: sync writes nothing and has nothing to name
        self.assertEqual(self.run_entry("sync", cwd=self.project), (0, [{"code": "ok", "file": "AGENTS.md", "block": "current"}], ""))
        # with entries, every sync names their headings, the kinds of work to read the file for
        read = {"code": "convention", "file": "docs/conventions/other.md", "headings": ["Code"]}

        # an entry of the project's below the list, and a list from an older skill: sync rewrites the list alone
        entry = "\n## Code\n\n- **A rule.** From: 2026-11-13.\n"
        stale = re.sub(r"^- `reports`: .*\n", "", text, flags=re.M).replace("- `layout`: ", "- `layout`: An older sentence. ") + entry
        made.write_text(stale, encoding="utf-8")
        code, out, err = self.run_entry("sync", "-n", cwd=self.project)
        self.assertEqual((code, [{k: v for k, v in line.items() if k != "hint"} for line in out], err, made.read_text(encoding="utf-8")),
                         (0, [{"code": "ok", "file": "AGENTS.md", "block": "current"},
                              {"code": "convention", "file": "docs/conventions/other.md", "wrote": "kinds", "dry_run": True}, read], "", stale))
        code, out, err = self.run_entry("sync", cwd=self.project)
        self.assertEqual((code, out[1]["wrote"], {k: v for k, v in out[2].items() if k != "hint"}, err), (0, "kinds", read, ""))
        self.assertIn("move an entry", out[1]["hint"])
        self.assertEqual(made.read_text(encoding="utf-8"), text + entry)

        # a hand-made other.md with neither line gets both, and keeps its entry
        made.write_text("# Other\n" + entry, encoding="utf-8")
        code, out, _ = self.run_entry("sync", cwd=self.project)
        self.assertEqual((code, [line.get("wrote") or line.get("headings") for line in out[1:]]), (0, ["reference_line", "kinds", ["Code"]]))
        self.assertEqual(made.read_text(encoding="utf-8"), text.replace("# Other: this project", "# Other") + entry)


class Heads(unittest.TestCase):
    """The head of each reference a project may add to is the one place its `description` and its `trigger` are
    written. The line of the common block's *When to read what* is that trigger, word for word."""

    def test_each_kind_has_a_head_and_the_block_carries_its_trigger(self):
        common = (ENTRY.parent.parent / "common.md").read_text(encoding="utf-8")
        for path in sorted(REFERENCES.glob("*.md")):
            if path.stem in ("adopting", "maintaining"):
                continue
            with self.subTest(reference=path.name):
                lines = path.read_text(encoding="utf-8").splitlines()
                self.assertEqual(lines[0], "---", "the reference opens with its head")
                fields = dict(line.split(": ", 1) for line in lines[1:lines.index("---", 1)])
                self.assertEqual(list(fields), ["name", "description", "trigger"])
                self.assertEqual(fields["name"], path.stem, "the name is the file's name")
                description, trigger = json.loads(fields["description"]), json.loads(fields["trigger"])
                self.assertTrue(description.strip() and trigger.strip())
                title = path.stem.replace("-", " ").capitalize()
                line = f"- **{title}** (`{path.stem}`): {trigger}"
                self.assertIn("\n" + line + "\n", common,
                              f"common.md's *When to read what* does not carry this trigger: its line should read\n{line}")


class Rev(unittest.TestCase):
    """The begin marker of common.md carries the day the block last changed, and the sync trusts it to tell an older
    install from a newer block. This pair is the block's text as it stood at that rev: a change to the text that
    leaves the rev alone fails here."""
    REV, SHA256 = "2026-11-14", "a9bca1654514e4b1f1bde40d3a2dc571f5d954b2b8a6fea81bc1cd48ab789f99"

    def test_the_rev_moves_whenever_the_block_changes(self):
        data = (ENTRY.parent.parent / "common.md").read_bytes()
        m = re.search(rb"<!--[ \t]*how-we-work:begin[ \t]+rev[ \t]+(\S+)[^>]*-->(.*?)<!--[ \t]*how-we-work:end[ \t]*-->", data, re.S)
        self.assertIsNotNone(m, "common.md's begin marker carries no rev")
        rev, sha = m.group(1).decode(), hashlib.sha256(m.group(2)).hexdigest()
        if sha != self.SHA256:
            self.assertNotEqual(rev, self.REV, "common.md's block changed and its rev did not: move the rev in the begin "
                                               "marker to today (a second change on one day: <day>.2), then record the "
                                               "new pair here")
            self.fail(f"common.md is at rev {rev} with new text: record REV, SHA256 = {rev!r}, {sha!r} here")
        self.assertEqual(rev, self.REV, "the rev moved and the block's text did not: record the new REV here")


if __name__ == "__main__":
    unittest.main()
