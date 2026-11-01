#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Run paper-fetch's commands: `pf.py <command> [args...]` runs scripts/<command>.py.

`pf.py --help` (or no arguments) lists every command with the first line of its docstring. A script runs through
`uv run --script`, so its own PEP 723 dependencies load, and its exit code is passed through; an unknown command
exits 2 with the list. Copied from paper-to-zotero/scripts/p2z.py (commit 90cecdf) without its compound commands.
"""
import ast
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SELF = Path(__file__).name


def command(script, *args):
    """The command line that runs scripts/<script>.py: through uv, which loads the script's own dependencies."""
    return ["uv", "run", "--quiet", "--script", str(HERE / f"{script}.py"), *args]


def scripts():
    return sorted(p.stem for p in HERE.glob("*.py") if p.name != SELF)


def usage(stream):
    def first_line(name):
        doc = ast.get_docstring(ast.parse((HERE / f"{name}.py").read_text(encoding="utf-8"))) or ""
        return doc.strip().splitlines()[0] if doc.strip() else "(no docstring)"

    listing = {name: first_line(name) for name in scripts()}
    width = max(map(len, listing), default=0) + 2
    print(f"usage: {SELF} <command> [args...]   (each command takes --help)\n\ncommands:", file=stream)
    for name in sorted(listing):
        print(f"  {name:<{width}}{listing[name]}", file=stream)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        usage(sys.stdout)
        return 0
    if argv[0] not in scripts():
        print(f"{SELF}: unknown command {argv[0]!r}\n", file=sys.stderr)
        usage(sys.stderr)
        return 2
    os.execvp("uv", command(argv[0], *argv[1:]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
