#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Print a project paper index's heading line for each paper, from Zotero: the line is generated, never typed.

The papers are citation keys or item keys; - reads a list from stdin: a value a line, or paper-to-zotero's JSON lines
by their `key` (else `cite`), so `p2z.py search ... | pr.py heading -` needs no field picked out. A line reporting a
skip or a failure upstream is passed on as it is; an empty list does nothing.

The line is `## <citation key> · <title> · <common names>（<venues> <year>）` (references/notes.md):
  - common names from the paper's aka/ tags, venues from its venue/ tags, each kind sorted by name and joined
    by " / ": choosing among them is not the script's to do;
  - the year is the four-digit year in the item's date, which Zotero holds as typed ("2026-03", "6/2016");
  - a paper without an aka/ tag has no common-name part, which is the usual case: print it as it is.

stdout: one JSON line per paper, in the order named, each paper once.
  ok         {cite, code, heading}: cite is the paper's citation key, whichever key named it
  any other  paper-to-zotero's own line for a name that is not one item: {item, code: not_found | ambiguous, keys?,
             hint}
  not_run    {item, code}: paper-to-zotero could not go on
Exit 0 = every paper has its heading; 1 = some has not, then stderr's last line is {"summary": {total, failed}};
2 = cannot go on (Zotero not running, a list it cannot read, a usage error): stderr's last line is {code, hint}.

Examples:
  pr.py heading xiaoTCACE2026 heDeepResidualLearning2016 | jq -r 'select(.code=="ok").heading'
  p2z.py search T-CACE | pr.py heading -
"""
import re
import sys

from prlib import cli

YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def tag_values(item, prefix):
    return sorted(t["tag"][len(prefix):].strip() for t in item.get("tags", []) if t.get("tag", "").startswith(prefix))


def heading(item, cite):
    line = f"## {cite} · {item.get('title') or ''}".rstrip()
    names = tag_values(item, "aka/")
    if names:
        line += " · " + " / ".join(names)
    year = YEAR.search(item.get("date") or "")
    where = " ".join(x for x in (" / ".join(tag_values(item, "venue/")), year and year.group()) if x)
    return f"{line}（{where}）" if where else line


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("papers", nargs="*", metavar="PAPER", help="a citation key or item key; - reads a list from stdin")
    args = cli.parse(p, argv)
    if not args.papers:
        p.error("name the papers: citation keys or item keys, or - to read a list from stdin")

    def run():
        named = cli.names(args.papers)
        values = list(dict.fromkeys(n.value for n in named if n.line is None))
        lines, stop = [], None
        if values:
            try:
                lines = cli.sibling(cli.P2Z, "items", *values, step="items")[0]
            except cli.Stop as s:
                stop = s
        items = {}   # (field, value) -> the item line it names
        for line in lines:
            if "itemType" in line:
                items[("key", line["key"])] = line
                items.setdefault(("cite", line.get("citationKey")), line)
        failures = {line["item"]: line for line in lines if "itemType" not in line and "item" in line}
        total = failed = 0
        done = set()   # each paper once: by its key once resolved, else by the name
        for name in named:
            if name.line is not None:
                line = name.line
            else:
                fields = (name.field,) if name.field else ("key", "cite")
                item = next((items[(f, name.value)] for f in fields if (f, name.value) in items), None)
                once = item["key"] if item else name.value
                if once in done:
                    continue
                done.add(once)
                if stop is not None:
                    line = {"item": name.value, "code": "not_run"}
                elif item is None:
                    line = failures.get(name.value) or {"item": name.value, "code": "not_found",
                                                        "hint": "paper-to-zotero's items printed no line for it."}
                else:
                    cite = item.get("citationKey") or item["key"]
                    line = {"cite": cite, "code": "ok", "heading": heading(item, cite)}
            total += 1
            failed += line.get("code") not in ("ok", "skipped")
            cli.emit(line)
        if stop is not None:
            cli.emit(stop.line(), sys.stderr)
            return cli.CANNOT
        if failed:
            cli.emit({"summary": {"total": total, "failed": failed}}, sys.stderr)
            return cli.ACT
        return cli.OK

    return cli.run(run)


if __name__ == "__main__":
    sys.exit(main())
