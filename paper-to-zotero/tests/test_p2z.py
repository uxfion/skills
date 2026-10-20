# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/p2z.py: the dispatcher, and prepare then save over records against the fakes."""
import ast
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import config_file
from fake_web import FakeWeb, location
from fake_zotero import FakeZotero

from p2zlib import run as work_run

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
P2Z = SCRIPTS / "p2z.py"


def run(*args, timeout=60):
    return subprocess.run([sys.executable, str(P2Z), *args], capture_output=True, text=True, timeout=timeout)


def first_doc_line(script):
    doc = ast.get_docstring(ast.parse(script.read_text(encoding="utf-8"))) or ""
    return doc.strip().splitlines()[0] if doc.strip() else ""


class P2zTest(unittest.TestCase):
    def test_help_lists_every_script_but_itself(self):
        done = run("--help")
        self.assertEqual(done.returncode, 0, done.stderr)
        names = [line.split()[0] for line in done.stdout.splitlines() if line.startswith("  ")]
        expected = sorted([p.stem for p in SCRIPTS.glob("*.py") if p.name != "p2z.py"] + ["prepare", "save"])
        self.assertEqual(names, expected)
        self.assertNotIn("p2z", names)
        self.assertIn(first_doc_line(SCRIPTS / "ready.py"), done.stdout)
        self.assertIn(first_doc_line(SCRIPTS / "file_and_tag.py"), done.stdout)

    def test_no_args_is_help(self):
        done = run()
        self.assertEqual(done.returncode, 0)
        self.assertIn("commands:", done.stdout)
        self.assertIn("ready", done.stdout)

    def test_unknown_command(self):
        done = run("nope", "--flag")
        self.assertEqual(done.returncode, 2)
        self.assertEqual(done.stdout, "")
        self.assertIn("unknown command 'nope'", done.stderr)
        self.assertIn("  ready", done.stderr)

    def test_path_tricks_are_not_commands(self):
        for name in ("../scripts/ready", "/etc/passwd", "ready.py", ""):
            done = run(name)
            self.assertEqual(done.returncode, 2, name)
            self.assertEqual(done.stdout, "", name)

    def test_dispatch_passes_args_through(self):
        done = run("ready", "--help")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(done.stdout.startswith("usage: ready.py"), done.stdout[:80])

    def test_exit_code_is_propagated(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        tmp = Path(tempfile.mkdtemp(prefix="p2z-dispatch-"))
        try:
            env = dict(os.environ, HOME=str(tmp), PAPER_TO_ZOTERO_CONFIG=str(tmp / "config.json"))
            done = subprocess.run([sys.executable, str(P2Z), "ready", "--base-url", f"http://127.0.0.1:{port}",
                                   "--work", str(tmp / "work"), "--downloads", str(tmp)],
                                  capture_output=True, text=True, env=env, timeout=60)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn('"code": "zotero_unreachable"', done.stdout)

    def test_one_sentence_docstrings(self):
        for name in ("ready.py", "p2z.py"):
            line = first_doc_line(SCRIPTS / name)
            self.assertTrue(line.endswith("."), f"{name}: first docstring line must be one sentence: {line!r}")
            self.assertLess(len(line), 140, name)


class PrepareAndSave(unittest.TestCase):
    def test_the_main_line(self):
        zot, web = FakeZotero(), FakeWeb()
        self.addCleanup(zot.close)
        self.addCleanup(web.close)
        zot.add_collection("COLL0001", "Inbox")
        zot.add_item("LIKE0001", itemType="journalArticle", title="Paper Near Something")
        web.openalex("10.1000/new.1", [location("https://repo.example/new.pdf", None, "publishedVersion")])
        web.crossref("10.1000/pub.9", type="proceedings-article", title="Reflexion: Language Agents with Verbal Reinforcement",
                     container_title="NeurIPS", issued={"date-parts": [[2023]]})
        web.arxiv("2303.11366", "Reflexion: Language Agents with Verbal Reinforcement", comment="NeurIPS 2023")
        work = work_run.Work(tempfile.mkdtemp(prefix="p2z-main-"))
        work.records.mkdir()
        author = [{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"}]
        for slug, item in (("new", {"itemType": "journalArticle", "title": "A New Paper", "DOI": "10.1000/new.1", "date": "2024"}),
                           ("dup", {"itemType": "journalArticle", "title": "Paper Near Something", "date": "2024"}),
                           ("pre", {"itemType": "preprint", "title": "Reflexion: Language Agents with Verbal Reinforcement",
                                    "archiveID": "arXiv:2303.11366", "date": "2023"})):
            (work.records / f"{slug}.json").write_text(json.dumps({"item": {**item, "creators": author}, "collection": "COLL0001",
                                                                   "tags": ["method/x"]}))
        records = [str(work.records / f"{s}.json") for s in ("new", "dup", "pre")]
        env = {**os.environ, **web.env(), "PAPER_TO_ZOTERO_CONFIG": str(config_file()), "PATH": os.environ["PATH"]}

        def p2z(*argv):
            done = subprocess.run([sys.executable, str(P2Z), *argv, "--base-url", zot.base_url, *records], capture_output=True,
                                  text=True, env=env, timeout=120)
            return done.returncode, [json.loads(line) for line in done.stdout.splitlines()]

        code, lines = p2z("prepare")
        self.assertEqual(code, 1, lines)
        by = {line["slug"]: line for line in lines[:-1]}
        self.assertEqual(set(by["new"]["steps"]), {"doi_to_item", "find_in_library", "fulltext_links", "check_item"})
        self.assertEqual((by["new"]["steps"]["fulltext_links"], by["new"]["steps"]["doi_to_item"]), ("ok", "skipped: not_preprint"))
        self.assertEqual(by["dup"]["decide"][0], {"near_matches": ["LIKE0001"]})
        self.assertIn({"published_candidates": 1}, by["pre"]["decide"])
        self.assertEqual(work_run.read(records[0])["links"]["items"][0]["url"], "https://repo.example/new.pdf")
        code, again = p2z("prepare")
        self.assertTrue(all(v.startswith("skipped") for v in again[0]["steps"].values()), again[0])
        pre = work_run.read(records[2])
        pre["keep_preprint"] = "the user wants the preprint"
        pre.save()
        code, lines = p2z("save")
        by = {line["slug"]: line for line in lines[:-1]}
        self.assertEqual((by["new"]["steps"], by["pre"]["code"]),
                         ({"create_item": "ok", "attach_file": "skipped: no_file_yet"}, "decide"), lines)
        self.assertEqual(by["dup"]["steps"]["create_item"], "possible_duplicate")
        self.assertIn({"failed": "create_item"}, by["dup"]["decide"])
        self.assertNotIn({"published_candidates": 1}, by["pre"]["decide"], "keep_preprint settles it")
        self.assertEqual(lines[-1]["summary"]["decide"], 3)


if __name__ == "__main__":
    unittest.main()
