# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for hww.py sync, each run through the entry as an agent runs it: uv run how-we-work/tests/test_sync.py

The skill's own common.md is not used: every run names a small one of the test's through HOW_WE_WORK_COMMON. The
expected bytes and lines are written by hand.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ENTRY = Path(__file__).resolve().parent.parent / "scripts" / "hww.py"

# The block as the skill holds it, and a common.md around it: the note above the block and the line below stay in the skill.
BLOCK = ("<!-- how-we-work:begin — synced from the skill; do not edit inside this block. -->\n"
         "\n# How we work\n\n- Ask one question at a time. 一次一个问题。\n\n"
         "<!-- how-we-work:end -->").encode()
COMMON = b"<!-- Draft 3: a note for whoever maintains the skill. -->\n\n" + BLOCK + b"\nA line after the block.\n"
EMPTY_PAIR = b"<!-- how-we-work:begin -->\n<!-- how-we-work:end -->"
OLD = 1_600_000_000   # a modification time long past: a write would move it


class Sync(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="hww-"))
        self.common = self.dir / "common.md"
        self.common.write_bytes(COMMON)
        self.project = self.dir / "project"
        self.project.mkdir()
        self.file = self.project / "AGENTS.md"

    def run_entry(self, *argv, cwd=None, common=None):
        env = {**os.environ, "HOW_WE_WORK_COMMON": str(common or self.common)}
        done = subprocess.run(["uv", "run", "--quiet", "--script", str(ENTRY), *map(str, argv)], capture_output=True,
                              text=True, env=env, cwd=cwd)
        return done.returncode, [json.loads(line) for line in done.stdout.splitlines()], done.stderr

    def put(self, data):
        """The project's AGENTS.md with these bytes, last modified long ago."""
        self.file.write_bytes(data)
        os.utime(self.file, (OLD, OLD))

    def untouched(self, data):
        return self.file.read_bytes() == data and self.file.stat().st_mtime == OLD

    def test_first_sync_fills_the_empty_pair_and_a_second_run_writes_nothing(self):
        before, after = b"# Project\n\nIts goal.\n\n", b"\n\n## This project's own rules\n\n- Figures in English.\n"
        self.put(before + EMPTY_PAIR + after)
        # a convention file whose to-promote section holds no entry: nothing waits
        conventions = self.project / "docs" / "conventions"
        conventions.mkdir(parents=True)
        (conventions / "reports.md").write_text("# Reports\n\n## This project only\n\n- **A rule.** Why here only: x.\n\n"
                                                "## To promote (待提升)\n\nNothing yet.\n", encoding="utf-8")

        self.assertEqual(self.run_entry("sync", self.file),
                         (0, [{"code": "ok", "file": str(self.file), "block": "updated"}], ""))
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

    def test_a_rule_to_promote_in_the_projects_own_part_of_agents_md_is_listed_and_the_block_is_not_read(self):
        # the block itself holds a `## To promote` heading with an item: it is the skill's text, never an entry
        block = (b"<!-- how-we-work:begin -->\n\n## To promote\n\n- inside the block: not an entry\n\n"
                 b"<!-- how-we-work:end -->")
        common = self.dir / "common-with-heading.md"
        common.write_bytes(block + b"\n")
        self.put(b"# Project\n\n## To promote\n\n- **Above the block.**\n\n" + EMPTY_PAIR
                 + b"\n\n- a list after the block, under no heading: not an entry\n\n## This project only\n\n- **Uses server A.**\n\n"
                 b"## To promote\n\n- **State a collision before editing.** From: 2026-10-09\n")
        code, out, err = self.run_entry("sync", self.file, common=common)
        self.assertEqual(code, 1)
        self.assertEqual(out[0], {"code": "ok", "file": str(self.file), "block": "updated"})
        text = self.file.read_bytes().decode().splitlines()
        line = text.index("- **State a collision before editing.** From: 2026-10-09") + 1
        self.assertEqual(out[1:], [{"code": "to_promote", "file": str(self.file), "line": 5, "entry": "**Above the block.**",
                                    "mark": None},
                                   {"code": "to_promote", "file": str(self.file), "line": line,
                                    "entry": "**State a collision before editing.** From: 2026-10-09", "mark": None}])
        self.assertEqual(json.loads(err.strip().splitlines()[-1]),
                         {"summary": {"to_promote": 2, "unjudged": 2, "files": 1}})

    def test_entries_to_promote_are_listed_and_exit_1(self):
        self.put(b"# Project\n\n" + EMPTY_PAIR + b"\n")
        conventions = self.project / "docs" / "conventions"
        conventions.mkdir(parents=True)
        # the heading in Chinese; CRLF line endings
        (conventions / "experiments.md").write_bytes((
            "# 实验：本项目\r\n"                                        # 1
            "\r\n"
            "## 本项目专有\r\n"                                         # 3
            "\r\n"
            "- **只用 A 服务器。** 为什么只属于这里：数据在那。\r\n"    # 5
            "\r\n"
            "## 待提升\r\n"                                             # 7
            "\r\n"
            "- **图例放右上角。** From: 2026-11-10 「以后图例放右上角」\r\n"   # 9
            "- **每个实验一个文件夹。**\r\n"                            # 10
            "  From: the first runs,\r\n"
            "  which got mixed up.\r\n"
            "\r\n"
            "## 其他\r\n"                                               # 14
            "\r\n"
            "- 不在待提升一节里。\r\n").encode())
        # the heading in English, with what an entry may hold: a nested list, a lazy line, a paragraph of its own
        (conventions / "reports.md").write_text(
            "# Reports: this project\n"                    # 1
            "\n"
            "## To promote\n"                              # 3
            "\n"
            "A sentence that is no list item.\n"           # 5
            "\n"
            "1. **Numbers carry their unit.**\n"           # 7
            "   - also in tables\n"
            "a line that continues it\n"
            "\n"
            "    kept: indented under the item\n"          # 11
            "\n"
            "A paragraph of its own, not the item's.\n"    # 13
            "\n"
            "### Figures\n"                                # 15
            "\n"
            "* **Axis labels in English.**\n"              # 17
            "\n"
            "# Another part\n"                             # 19
            "\n"
            "- not under the heading any more\n", encoding="utf-8")
        # fenced examples: one opening in the first column is not read, its heading and its item included; one
        # indented under an item is that item's text
        (conventions / "layout.md").write_text(
            "# Layout: this project\n"                              # 1
            "\n"
            "## To promote\n"                                       # 3
            "\n"
            "The form of an entry, as an example:\n"                # 5
            "\n"
            "```markdown\n"                                         # 7
            "## This project only\n"
            "\n"
            "- **<the rule, one sentence>.** From: <the date>.\n"   # 10
            "```\n"
            "\n"
            "- **An archive folder has an index.** Its form:\n"     # 13
            "\n"
            "  ```markdown\n"                                       # 15
            "  | What | Where it was |\n"
            "  ```\n"
            "- **Scratch files stay out of git.**\n"                # 18
            "~~~\n"
            "- not an entry: a second fenced example, in tildes\n"  # 20
            "~~~\n", encoding="utf-8")
        # no such heading: nothing listed from it
        (conventions / "servers.md").write_text("# Servers\n\n## This project only\n\n- **One GPU box.** Why here only: x.\n",
                                                encoding="utf-8")
        (conventions / "notes.txt").write_text("## To promote\n\n- not a convention file\n", encoding="utf-8")

        experiments, layout, reports = (str(conventions / name) for name in ("experiments.md", "layout.md", "reports.md"))
        entries = [
            {"code": "to_promote", "file": experiments, "line": 9,
             "entry": "**图例放右上角。** From: 2026-11-10 「以后图例放右上角」"},
            {"code": "to_promote", "file": experiments, "line": 10,
             "entry": "**每个实验一个文件夹。**\n  From: the first runs,\n  which got mixed up."},
            {"code": "to_promote", "file": layout, "line": 13,
             "entry": "**An archive folder has an index.** Its form:\n\n  ```markdown\n  | What | Where it was |\n  ```"},
            {"code": "to_promote", "file": layout, "line": 18, "entry": "**Scratch files stay out of git.**"},
            {"code": "to_promote", "file": reports, "line": 7,
             "entry": "**Numbers carry their unit.**\n   - also in tables\na line that continues it\n\n"
                      "    kept: indented under the item"},
            {"code": "to_promote", "file": reports, "line": 17, "entry": "**Axis labels in English.**"},
        ]
        entries = [{**entry, "mark": None} for entry in entries]      # none of them judged yet
        summary = {"summary": {"to_promote": 6, "unjudged": 6, "files": 3}}

        status, lines, err = self.run_entry("sync", self.file)
        self.assertEqual((status, lines), (1, [{"code": "ok", "file": str(self.file), "block": "updated"}, *entries]))
        self.assertEqual([json.loads(line) for line in err.splitlines()], [summary])
        self.assertEqual(self.file.read_bytes(), b"# Project\n\n" + BLOCK + b"\n")

        # the entries wait until an agent has dealt with them: listed again, with -n as well, the block now current
        os.utime(self.file, (OLD, OLD))
        for argv in (("sync", self.file), ("sync", "-n", self.file)):
            status, lines, err = self.run_entry(*argv)
            self.assertEqual((status, lines), (1, [{"code": "ok", "file": str(self.file), "block": "current"}, *entries]))
            self.assertEqual(json.loads(err.splitlines()[-1]), summary)
        self.assertTrue(self.untouched(b"# Project\n\n" + BLOCK + b"\n"))


    def test_judged_entries_wait_only_when_the_block_changes(self):
        own = (b"\n\n## To promote\n\n- **Kept here for now.** (judged 2026-11-10: stays)\n"
               b"- **Proposed.** From: 2026-11-10 (issue: 20261110-how-we-work-legend.md)\n")
        self.put(b"# Project\n\n" + EMPTY_PAIR + own)
        code, out, err = self.run_entry("sync", self.file)        # the block was just written: every entry is judged anew
        self.assertEqual((code, out[0]["block"], [o["mark"] for o in out[1:]]), (1, "updated", ["judged", "issue"]))
        self.assertEqual(json.loads(err.strip().splitlines()[-1]), {"summary": {"to_promote": 2, "unjudged": 0, "files": 1}})
        code, out, err = self.run_entry("sync", self.file)        # current block, every entry marked: nothing waits
        self.assertEqual((code, out[0]["block"], len(out), err), (0, "current", 3, ""))
        self.file.write_bytes(self.file.read_bytes() + b"- **New today.**\n")
        code, out, err = self.run_entry("sync", self.file)
        self.assertEqual((code, [o["mark"] for o in out[1:]]), (1, ["judged", "issue", None]))
        self.assertEqual(json.loads(err.strip().splitlines()[-1]), {"summary": {"to_promote": 3, "unjudged": 1, "files": 1}})

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


if __name__ == "__main__":
    unittest.main()
