# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/p2z.py, the dispatcher.

Run: uv run tests/test_p2z.py
"""
import ast
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
        expected = sorted(p.stem for p in SCRIPTS.glob("*.py") if p.name != "p2z.py")
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
            env = {k: v for k, v in os.environ.items() if k != "ZOTERO_LOCAL_API_KEY"}
            env["HOME"] = str(tmp)
            done = subprocess.run([sys.executable, str(P2Z), "ready", "--base-url", f"http://127.0.0.1:{port}",
                                   "--work", str(tmp / "work"), "--key-file", str(tmp / "key"), "--downloads", str(tmp)],
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


if __name__ == "__main__":
    unittest.main()
