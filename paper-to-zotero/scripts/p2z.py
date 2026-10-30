#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Run paper-to-zotero's commands: `p2z.py <command> [args...]` runs scripts/<command>.py; prepare and save run several.

`p2z.py --help` (or no arguments) lists every command with the first line of its docstring. A script runs with the
`uv run --script`, so its own PEP 723 dependencies load, and its exit code is passed through; an unknown command
exits 2 with the list.

Two commands run several scripts over the same record files, one after the other, and print one line per record:
  prepare RECORD...   fill the blocks computed from a record: doi_to_item (a preprint's published versions),
                      find_in_library (found, near_matches), fulltext_links (links), check_item (checks). Each script
                      skips a block that is done, so after any change to a record run prepare again.
  save RECORD...      create_item, then attach_file: the item, then its file. Each skips what it has done, so save can
                      run after every pass of fetch.
Each line: {slug, code: decide | failed | ok, decide?: [what is the agent's to settle], failed?: [the scripts whose
line for it is not done], steps: {script: its code}}. `decide` comes from the record itself: near matches (write
same_as, or add the key to distinct_from), published versions of a preprint not settled (redraft, or write
keep_preprint with the reason), checks that are not ok, sources that did not answer (prepare again later). Then
{"summary"}. --dry-run and --base-url go
to every script. Exit 0 = nothing to settle; 1 = something is; 2 = a script could not go on (the next steps did not
run).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from p2zlib import cli, run

HERE = Path(__file__).resolve().parent
SELF = Path(__file__).name
STEPS = {"prepare": ("doi_to_item", "find_in_library", "fulltext_links", "check_item"),
         "save": ("create_item", "attach_file")}


def command(script, *args):
    """The command line that runs scripts/<script>.py: through uv, which loads the script's own dependencies."""
    return ["uv", "run", "--quiet", "--script", str(HERE / f"{script}.py"), *args]


def scripts():
    return sorted(p.stem for p in HERE.glob("*.py") if p.name != SELF)


def usage(stream):
    import ast

    def first_line(name):
        doc = ast.get_docstring(ast.parse((HERE / f"{name}.py").read_text(encoding="utf-8"))) or ""
        return doc.strip().splitlines()[0] if doc.strip() else "(no docstring)"

    listing = {**{name: first_line(name) for name in scripts()},
               **{name: f"runs {', '.join(steps)} over the records" for name, steps in STEPS.items()}}
    width = max(map(len, listing)) + 2
    print(f"usage: {SELF} <command> [args...]   (each command takes --help)\n\ncommands:", file=stream)
    for name in sorted(listing):
        print(f"  {name:<{width}}{listing[name]}", file=stream)


def decisions(rec):
    """What the record leaves for the agent to settle, read from the record itself."""
    block = lambda name: rec.get(name) if isinstance(rec.get(name), dict) else {}  # noqa: E731
    out = []
    if rec.get("near_matches") and block("found").get("code") != "found":
        out.append({"near_matches": [m.get("key") for m in rec["near_matches"] if isinstance(m, dict)]})
    if block("published_candidates").get("items") and not rec.get("keep_preprint"):  # the block is a preprint's only
        out.append({"published_candidates": len(block("published_candidates")["items"])})
    if block("checks") and block("checks").get("code") != "ok":
        out.append({"checks": block("checks").get("code")})
    unanswered = sorted({s for name in run.PREPARED for s in block(name).get("incomplete") or []})
    if unanswered:
        out.append({"unanswered": unanswered})
    return out


def compound(name, argv):
    """Run the command's scripts in turn over the records -> the exit code."""
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    env, args = dict(os.environ), list(argv)
    if "--base-url" in args:  # every script takes it from the environment: not every one talks to Zotero
        i = args.index("--base-url")
        env["PAPER_TO_ZOTERO_BASE_URL"] = args[i + 1]
        del args[i:i + 2]
    paths = [a for a in args if a.endswith(".json")]
    steps, stopped = {Path(p).stem: {} for p in paths}, None
    for script in STEPS[name]:
        done = subprocess.run(command(script, *args), capture_output=True, text=True, env=env)
        sys.stderr.write(done.stderr)
        for raw in done.stdout.splitlines():
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            slug = line.get("slug") if isinstance(line, dict) else None
            if slug in steps:
                code = line.get("code")
                steps[slug][script] = f"skipped: {line.get('reason')}" if code == "skipped" else code
                if "hint" in line:  # a script gives a hint only on a line that is not done (cli.tidy)
                    steps[slug].setdefault("_failed", []).append(script)
        for slug, got in steps.items():
            if script not in got and done.returncode:  # the script ended without a line for it
                got[script] = f"exit {done.returncode}"
                got.setdefault("_failed", []).append(script)
        if done.returncode == 2:
            stopped = script
            break
    lines = []
    for path in paths:
        slug = Path(path).stem
        try:
            settle = decisions(run.read(path))
        except cli.Stop as stop:
            lines.append(stop.line(slug=slug))
            continue
        failed = steps[slug].pop("_failed", [])
        lines.append({"slug": slug, "code": "decide" if settle else "failed" if failed else "ok",
                      **({"decide": settle} if settle else {}), **({"failed": failed} if failed else {}), "steps": steps[slug]})
    counts = {"total": len(lines), "ok": sum(1 for x in lines if x["code"] == "ok"),
              "decide": sum(1 for x in lines if x["code"] == "decide"),
              "failed": sum(1 for x in lines if x["code"] not in ("ok", "decide"))}
    for line in lines + [{"summary": {**counts, **({"stopped": stopped} if stopped else {})}}]:
        print(json.dumps(line, ensure_ascii=False))
    return 2 if stopped else 1 if counts["decide"] or counts["failed"] else 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        usage(sys.stdout)
        return 0
    name = argv[0]
    if name in STEPS:
        return compound(name, argv[1:])
    if name not in scripts():
        print(f"{SELF}: unknown command {name!r}\n", file=sys.stderr)
        usage(sys.stderr)
        return 2
    os.execvp("uv", command(name, *argv[1:]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
