#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Print a project paper index's heading line for each paper, from Zotero: the line is generated, never typed.

  uv run scripts/index_heading.py --cite <citation key> [<citation key> ...]

The line is `## <citation key> · <title> · <common names>（<venues> <year>）` (references/notes.md):
  - common names from the paper's aka/ tags, venues from its venue/ tags, every one of them in tag order, joined
    by " / ": choosing among them is not the script's to do;
  - the year is the four-digit year in the item's date, which Zotero holds as typed ("2026-03", "6/2016");
  - a paper without an aka/ tag has no common-name part, which is the usual case: print it as it is.

stdout: one JSON line per citation key, in the order given.
  ok      {cite, code, heading}
  other   paper-to-zotero's own line for a key it could not resolve (cite_not_found, cite_ambiguous, not_found)
Exit 0 = every key resolved; 1 = some did not; 2 = paper-to-zotero could not be run.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def p2z(*args):
    """Run a paper-to-zotero command; its JSON lines and exit code. PAPER_READ_P2Z points elsewhere (tests)."""
    script = os.environ.get("PAPER_READ_P2Z") or str(SKILL.parent / "paper-to-zotero" / "scripts" / "p2z.py")
    done = subprocess.run(["uv", "run", "--quiet", script, *args], capture_output=True, text=True)
    lines = []
    for line in done.stdout.splitlines():
        try:
            lines.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return lines, done.returncode, done.stderr


def tag_values(item, prefix):
    return sorted(t["tag"][len(prefix):].strip() for t in item.get("tags", []) if t.get("tag", "").startswith(prefix))


def heading(item):
    line = f"## {item.get('citationKey')} · {item.get('title') or ''}".rstrip()
    names = tag_values(item, "aka/")
    if names:
        line += " · " + " / ".join(names)
    year = YEAR.search(item.get("date") or "")
    where = " ".join(x for x in (" / ".join(tag_values(item, "venue/")), year and year.group()) if x)
    return f"{line}（{where}）" if where else line


def main(argv=None):
    first, _, rest = __doc__.strip().partition("\n")
    p = argparse.ArgumentParser(description=first, epilog=rest.strip(), formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cite", nargs="+", required=True, metavar="CITE", help="citation key(s)")
    args = p.parse_args(argv)
    cites = list(dict.fromkeys(args.cite))
    lines, code, err = p2z("read_library", "items", "--cite", *cites)
    if code >= 2:
        print(json.dumps({"code": "failed", "detail": err.strip() or lines}, ensure_ascii=False))
        return 2
    items = {l["citationKey"]: l for l in lines if "itemType" in l and l.get("citationKey")}
    failures = {l.get("cite"): l for l in lines if "itemType" not in l and l.get("code")}
    missing = False
    for cite in cites:
        if cite in items:
            print(json.dumps({"cite": cite, "code": "ok", "heading": heading(items[cite])}, ensure_ascii=False))
        else:
            missing = True
            print(json.dumps(failures.get(cite) or {"cite": cite, "code": "not_found"}, ensure_ascii=False))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
