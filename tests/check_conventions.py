# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The conventions check: each skill's commands against docs/design-principles.md §3, The Unix/Linux philosophy.

  uv run tests/check_conventions.py          # run while developing; it is not installed with any skill

One copy for the repo, every skill at once. A skill not yet brought over to the conventions is in NOT_YET and
skipped: take it off the list when it is. The letters come from the principles' table, not from here.
  static   each script opens with the uv shebang and is executable in git; the entry's word table names existing
           scripts and every script has a word; no string in the code names a script file, `uv run` or a removed
           option
  help     every word's -h (each subcommand's too), run with no service and no config: exit 0, the usage line under
           the typed name, exit codes and an example; only the table's letters; no option taking several values;
           --collection only where it selects
  runtime  against the skill's fake service: a command that does every thing quietly leaves stderr empty; one whose
           output passes the pipe buffer, cut by `| head -1`, still leaves stderr empty and keeps its exit status, and
           a writer cut off so still writes every item; a service that does not answer is exit 2, stderr's last line
           {code, hint}

What differs from skill to skill comes from the skill's own tests/conventions_fixture.py (paper-to-zotero's is the example):
  HELP_ENV          the environment every -h runs in: no config, each service at a port nothing listens on
  REMOVED, SELECTS  long names dropped in the conversion {name: words still allowed it}; words where --collection
                    selects (both optional)
  env(tmp)          a context manager: starts the fake service, yields the environment the cases run in
  quiet(tmp), reader(tmp), writer(tmp), no_service(tmp)
                    each a {"run": a shell line as an agent types it, after the PATH statement}; quiet may add
                    "lines", the stdout line count; writer adds "written", a function true once every item is written,
                    or writer is a string saying why the skill has no command that writes many things; no_service adds
                    "code", the code on stderr's last line
The fixture imports at the top: it is loaded on its own and what it imported is put away again, so two skills'
helpers.py never meet.
"""
import concurrent.futures
import functools
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOT_YET = {"paper-fetch", "paper-read", "paddleocr", "vllm-serve"}
SKILLS = sorted(p.parent.name for p in ROOT.glob("*/SKILL.md") if (p.parent / "scripts").is_dir()
                and p.parent.name not in NOT_YET)
SHEBANG = "#!/usr/bin/env -S uv run --quiet --script"
UV = shutil.which("uv")



@functools.cache
def fixture(skill):
    """The skill's tests/conventions_fixture.py, with its tests/ first on sys.path while it loads; the repo modules it
    imported are then taken out of sys.modules and the path restored."""
    path = ROOT / skill / "tests" / "conventions_fixture.py"
    assert path.is_file(), f"{skill}: no tests/conventions_fixture.py"
    saved, before = list(sys.path), set(sys.modules)
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(f"conventions_fixture_{skill.replace('-', '_')}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = saved
        for name in set(sys.modules) - before:
            if str(getattr(sys.modules[name], "__file__", None) or "").startswith(str(ROOT)):
                del sys.modules[name]


def letters():
    """{letter: its long form or None}, from the table in the principles."""
    text = (ROOT / "docs" / "design-principles.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\s*\| `-(\w)` \|\s*(?:`(--[\w-]+)`)?\s*\|", text, re.M)
    assert rows, "no letter table found in docs/design-principles.md"
    return {letter: long or None for letter, long in rows}


def scripts(skill):
    return sorted(p for p in (ROOT / skill / "scripts").glob("*.py"))


def entry_of(skill):
    """The entry: the one script holding the word table (WORDS)."""
    found = [p for p in scripts(skill) if re.search(r"^WORDS = \{", p.read_text(encoding="utf-8"), re.M)]
    assert len(found) == 1, f"{skill}: one entry with a WORDS table, found {[p.name for p in found]}"
    return found[0]


def words_of(entry):
    """{word: script stem or None}, read from the table's literal."""
    import ast
    tree = ast.parse(entry.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "WORDS" for t in node.targets):
            return {k: v[0] for k, v in ast.literal_eval(node.value).items()}
    raise AssertionError(f"{entry}: no WORDS")


def run(*argv, env=None, timeout=120, shell=False):
    # an entry hands its typed name to the script in <X>_PROG: none may leak in from the shell running the check
    environ = {k: v for k, v in {**os.environ, **(env or {})}.items() if not k.endswith("_PROG")}
    return subprocess.run(argv[0] if shell else [UV, "run", "--quiet", "--script", *map(str, argv)], shell=shell,
                          capture_output=True, text=True, env=environ, timeout=timeout,
                          executable="/bin/bash" if shell else None)


def shell(skill, line, env):
    """A line as an agent types it: the PATH statement first, then the line, in bash."""
    return run(f'set -o pipefail; export PATH="{ROOT / skill / "scripts"}:$PATH"; {line}', env=env, shell=True)


def helps(skill):
    """{(word, sub or None): the CompletedProcess of `<entry> <word> [sub] -h`}, every subcommand included."""
    entry, bare = entry_of(skill), fixture(skill).HELP_ENV
    words = list(words_of(entry))
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        top = dict(zip(words, pool.map(lambda w: run(entry, w, "-h", env=bare), words)))
        subs = [(w, line.split()[0]) for w, done in top.items() if "\ncommands:\n" in done.stdout
                for line in done.stdout.split("\ncommands:\n", 1)[1].split("\n\n", 1)[0].splitlines()]
        deeper = dict(zip(subs, pool.map(lambda ws: run(entry, *ws, "-h", env=bare), subs)))
    return entry, {**{(w, None): d for w, d in top.items() if (w, None) not in {(s[0], None) for s in subs}}, **deeper}


def options(help_text):
    """[(short or None, long or None, takes several values)] from the help's options section."""
    out, section = [], help_text.split("\noptions:\n", 1)[1] if "\noptions:\n" in help_text else ""
    for line in section.splitlines():
        if not line.startswith("  -"):
            if line and not line.startswith(" "):
                break
            continue
        head = re.split(r"\s{2,}", line.strip(), maxsplit=1)[0]
        short = re.search(r"(?<![\w-])-(\w)\b(?!-)", head)
        long = re.search(r"--[\w-]+", head)
        out.append((short and short.group(1), long and long.group(0), "...]" in head))
    return out


class Static(unittest.TestCase):
    def test_shebang_and_executable(self):
        for skill in SKILLS:
            modes = {}
            for line in subprocess.run(["git", "ls-files", "-s", f"{skill}/scripts"], cwd=ROOT, capture_output=True,
                                       text=True).stdout.splitlines():
                mode, _, _, path = line.split(maxsplit=3)
                if Path(path).parent.name == "scripts":
                    modes[Path(path).name] = mode
            for script in scripts(skill):
                with self.subTest(script=f"{skill}/{script.name}"):
                    self.assertEqual(script.read_text(encoding="utf-8").splitlines()[0], SHEBANG)
                    self.assertEqual(modes.get(script.name), "100755", "executable in git: git update-index --chmod=+x")

    def test_word_table_and_scripts_match(self):
        for skill in SKILLS:
            entry = entry_of(skill)
            named = {s for s in words_of(entry).values() if s}
            stems = {p.stem for p in scripts(skill) if p != entry}
            self.assertEqual(named - stems, set(), f"{skill}: words naming no script")
            self.assertEqual(stems - named, set(), f"{skill}: scripts without a word")

    def test_strings_name_no_script_file_runner_or_removed_option(self):
        import ast
        for skill in SKILLS:
            names = {p.stem for p in scripts(skill)} - {entry_of(skill).stem}
            # no other script: nothing to name (an empty alternation would match any x.py)
            files = re.compile(r"\b(" + "|".join(map(re.escape, sorted(names))) + r")\.py\b") if names else None
            removed = getattr(fixture(skill), "REMOVED", {})
            words = {s: w for w, s in words_of(entry_of(skill)).items() if s}
            for path in scripts(skill) + sorted((ROOT / skill / "scripts").glob("*/*.py")):
                word = words.get(path.stem)
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                        continue
                    with self.subTest(file=f"{skill}/{path.relative_to(ROOT / skill)}", line=node.lineno):
                        self.assertIsNone(files and files.search(node.value), "a script file named where the word belongs")
                        self.assertNotIn("uv run scripts/", node.value)
                        for name, allowed in removed.items():
                            if word not in allowed and re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", node.value):
                                self.fail(f"{name} was removed")


class Help(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = letters()
        cls.pages = {skill: helps(skill) for skill in SKILLS}

    def test_every_word_has_a_man_page(self):
        for skill, (entry, pages) in self.pages.items():
            for (word, sub), done in pages.items():
                typed = " ".join(x for x in (entry.name, word, sub) if x)
                with self.subTest(command=typed):
                    self.assertEqual((done.returncode, done.stderr), (0, ""), "-h needs no service and no config")
                    self.assertTrue(done.stdout.startswith(f"usage: {typed}"), done.stdout[:80])
                    self.assertRegex(done.stdout, r"\bExit\b|\bexit\b", "its exit codes")
                    self.assertRegex(done.stdout, r"Examples?:", "an example or two")

    def test_options_by_convention(self):
        for skill, (entry, pages) in self.pages.items():
            for (word, sub), done in pages.items():
                command = " ".join(x for x in (word, sub) if x)
                for short, long, several in options(done.stdout):
                    with self.subTest(command=command, option=short or long):
                        self.assertFalse(several, "an option takes one value, repeated for more")
                        if short:
                            self.assertIn(short, self.table, "a letter outside the principles' table")
                            if self.table[short]:
                                self.assertIn(long, (None, self.table[short]), "the letter's long form is the table's")
                        if long == "--collection":
                            self.assertIn(command, getattr(fixture(skill), "SELECTS", set()),
                                          "--collection selects; replacing is --set-")


class Runtime(unittest.TestCase):
    def test_against_the_fake_service(self):
        for skill in SKILLS:
            with self.subTest(skill=skill):   # one skill's broken fixture does not stop the next
                cases = fixture(skill)
                with tempfile.TemporaryDirectory() as tmp, cases.env(Path(tmp)) as env:
                    self.check(skill, cases, Path(tmp), env)

    def check(self, skill, cases, tmp, env):
        with self.subTest(skill=skill, case="every thing done: stderr empty"):
            case = cases.quiet(tmp)
            done = shell(skill, case["run"], env)
            self.assertEqual((done.returncode, done.stderr), (0, ""), done.stderr)
            if "lines" in case:
                self.assertEqual(len(done.stdout.splitlines()), case["lines"], done.stdout[-500:])

        with self.subTest(skill=skill, case="a reader cut off by head: quiet, its status kept"):
            line = cases.reader(tmp)["run"]
            whole = shell(skill, line, env)
            self.assertEqual(whole.returncode, 0, whole.stderr)
            self.assertGreater(len(whole.stdout.encode()), 64 * 1024, "its output passes the pipe buffer")
            done = shell(skill, f"{line} | head -1", env)
            self.assertEqual((done.returncode, done.stderr, len(done.stdout.splitlines())), (0, "", 1), done.stderr)

        with self.subTest(skill=skill, case="a writer cut off by head: every item still written"):
            if isinstance(cases.writer, str):
                self.skipTest(cases.writer)
            case = cases.writer(tmp)
            done = shell(skill, f"{case['run']} | head -1", env)
            self.assertEqual((done.returncode, done.stderr, len(done.stdout.splitlines())), (0, "", 1), done.stderr)
            self.assertTrue(case["written"](), "every item written")

        with self.subTest(skill=skill, case="no service: exit 2, why on stderr's last line"):
            case = cases.no_service(tmp)
            done = shell(skill, case["run"], env)
            self.assertEqual(done.returncode, 2, done.stderr)
            self.assertEqual(json.loads(done.stderr.splitlines()[-1])["code"], case["code"])


if __name__ == "__main__":
    unittest.main()
