#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Change lines for the empty fields of library items that paper-fetch's results can fill: a change list for p2z.py update.

Each result (paper-fetch's result file, identified with --slug <citation key>) names its library item by citation
key: its `cite`, else its slug. The result is drafted into an item by p2z.py draft's own conversion (Zotero's CSL
tables and draft's rules), and each drafted field goes to the library item's type under its own name or its base
field's (a conferencePaper's proceedingsTitle -> a journalArticle's publicationTitle). A field the library item has
empty and the draft has a value for is to fill; a value is never overwritten, and creators, tags, collections,
itemType and extra are never listed. Nothing is written to Zotero here.

The result files follow the options (- reads their paths from stdin). stdout (or -o FILE): one change line per
item with something to fill, {key, set: {field: value}, from: the result's path, warnings?: draft's}; a result
whose item has every field gets none. Exit 0 = every result read; 1 = a result is not one with metadata
(result_invalid: a stub, paper-fetch could not identify the paper, or not JSON) or names no one item (not_found,
ambiguous), each a JSON line on stderr {slug, code, ...}, then {"summary": {total, failed}} last; 2 = cannot check
(zotero_unreachable, local_api_disabled), then stderr's last line is {code, hint}.

Examples:
  p2z.py fill <scratch>/paper-fetch/results/*.json | p2z.py update -n -
  p2z.py fill <scratch>/paper-fetch/results/liu2022jbhi.json -o <scratch>/paper-to-zotero/fields.jsonl
"""
import json
import sys
from pathlib import Path

import draft_item
from p2zlib import cli, run, zotero

NEVER = {"creators", "tags", "collections", "relations", "itemType", "extra"}


def read_result(path):
    try:
        res = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, str(e)
    if not isinstance(res, dict) or not isinstance(res.get("csl"), dict) or not res.get("slug"):
        return None, "no metadata: identify the paper first (paper-fetch's identify; its warnings say what failed)"
    return res, None


def to_fill(draft, have, types):
    """The draft's values for the fields the library item has empty -> {field: value}, in the library type's names."""
    d, drafted = zotero.data(have), types[draft["itemType"]]
    t, out = types[d.get("itemType")], {}
    for field, value in draft.items():
        if field in NEVER or not isinstance(value, str) or not value.strip():
            continue
        own = zotero.own_field(t, field) or zotero.own_field(t, drafted["base_of"].get(field, field))
        if own and own not in out and not str(d.get(own) or "").strip():
            out[own] = value
    return out


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("results", nargs="*", metavar="RESULT", help="paper-fetch's result files; - reads their paths from stdin")
    p.add_argument("-o", "--output", metavar="FILE", help="write the change lines here instead of stdout")
    cli.add_base_url(p)
    args = cli.parse(p, argv)
    if not args.results:
        p.error("name the result files, or - to read their paths from stdin")
    paths = cli.paths(args.results)

    def go():
        results = [(Path(path), *read_result(path)) for path in paths]
        zot, problems, keys = zotero.Zotero(args.base_url), [], {}
        for path, res, problem in results:
            if res is None:
                problems.append({"slug": path.stem, "code": "result_invalid", "path": str(path), "detail": problem,
                                 "hint": "Give paper-fetch's result files of identified papers."})
                continue
            cite = res.get("cite") or res["slug"]
            try:
                keys[path] = zot.resolve(cli.Name(cite, "cite"))
            except cli.Stop as stop:
                if stop.exit == cli.CANNOT:
                    raise
                problems.append(stop.line(slug=res["slug"], cite=cite))
        rows = zot.items(list(dict.fromkeys(keys.values()))) if keys else {}
        schema = zot.schema() if rows else {}
        types, changes = zotero.types_of(schema), []
        for path, res, _ in results:
            if path in keys and keys[path] in rows:
                warnings = []
                draft, _ = draft_item.item_of(res, schema, warnings)
                sets = to_fill(draft, rows[keys[path]], types)
                if sets:
                    changes.append({"key": keys[path], "set": sets, "from": str(path.absolute()),
                                    **({"warnings": warnings} if warnings else {})})
        text = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in changes)
        if args.output:
            target = Path(args.output).expanduser().absolute()
            target.parent.mkdir(parents=True, exist_ok=True)
            run.atomic_write(target, text)
        else:
            cli.write(text)
        return cli.summarize(len(results), len(problems), problems=problems)

    return cli.run(go, sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
