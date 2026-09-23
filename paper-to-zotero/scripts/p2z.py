# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Run one paper-to-zotero script by name: `p2z.py <command> [args...]` is `<command>.py` from this directory.

`p2z.py --help` (or no arguments) lists every script here with the first line
of its docstring. The script runs with the same interpreter as the dispatcher
and its exit code is passed through; an unknown command exits 2 with the list.
"""
import ast
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SELF = Path(__file__).name


def commands():
    """{name: first docstring line} for every other *.py in this directory."""
    out = {}
    for script in sorted(HERE.glob("*.py")):
        if script.name == SELF:
            continue
        try:
            doc = ast.get_docstring(ast.parse(script.read_text(encoding="utf-8"))) or ""
        except (OSError, SyntaxError):
            doc = ""
        out[script.stem] = doc.strip().splitlines()[0] if doc.strip() else "(no docstring)"
    return out


def usage(stream):
    listing = commands()
    width = max((len(name) for name in listing), default=0) + 2
    print(f"usage: {SELF} <command> [args...]   (each command takes --help)\n\ncommands:", file=stream)
    for name, line in listing.items():
        print(f"  {name:<{width}}{line}", file=stream)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        usage(sys.stdout)
        return 0
    name = argv[0]
    if name not in commands():
        print(f"{SELF}: unknown command {name!r}\n", file=sys.stderr)
        usage(sys.stderr)
        return 2
    os.execv(sys.executable, [sys.executable, str(HERE / f"{name}.py"), *argv[1:]])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
