#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""List the empty fields of library items that paper-fetch's results can fill, as lines for update_item --batch.

  uv run scripts/fields_from_results.py <scratch>/paper-fetch/results/liu2022jbhi.json -o <scratch>/paper-to-zotero/fields.jsonl
  uv run scripts/update_item.py --batch <scratch>/paper-to-zotero/fields.jsonl --dry-run

Each RESULT (paper-fetch's result file, identified with --slug <citation key>) names its library item by citation
key: its `cite`, else its slug. The result is drafted into an item by draft_item.py's own conversion (Zotero's CSL
tables and draft_item's rules), and each drafted field goes to the library item's type under its own name or its
base field's (a conferencePaper's proceedingsTitle -> a journalArticle's publicationTitle). A field the
library item has empty and the draft has a value for is to fill; a value is never overwritten, and creators, tags,
collections, itemType and extra are never listed. Each item with something to fill gets one line in -o FILE: {cite,
set: {field: value}, from: the result's path}; update_item --batch writes them. Nothing is written to Zotero here.

stdout: one line per result {slug, cite?, key?, code, ...}, then {"summary": {total, ok, skipped, failed, batch,
lines}} (lines: how many FILE holds).
  fill             fields to fill (`fields`: their names; `warnings`: draft_item's, when it had any): a line in FILE
  skipped          reason nothing_to_fill: the library item has every field the draft could give it
  cite_not_found   no top-level item carries the citation key; cite_ambiguous: several do (`keys`)
  result_invalid   not a result with metadata (a stub: paper-fetch could not identify the paper), or not JSON
fill is an answer. Exit 0 = every result filled or skipped; 1 = some not; 2 = cannot check (zotero_unreachable,
local_api_disabled).
"""
import json
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
    p.add_argument("results", nargs="+", metavar="RESULT", help="paper-fetch's result files")
    p.add_argument("-o", "--out", required=True, metavar="FILE", help="where the update_item --batch lines go")
    cli.add_base_url(p)
    args = p.parse_args(argv)

    def go():
        results = [(Path(path), *read_result(path)) for path in args.results]
        zot = zotero.Zotero(args.base_url)
        cites = list(dict.fromkeys(res.get("cite") or res["slug"] for _, res, _ in results if res))
        hits = zot.resolve_cites(cites) if cites else {}
        rows = zot.items([keys[0] for keys in hits.values() if len(keys) == 1]) if hits else {}
        schema = zot.schema() if rows else {}
        types = zotero.types_of(schema)
        out, batch = cli.Lines(answers=("fill",)), []

        def line(path, res, cite):
            keys = hits[cite]
            if len(keys) != 1:
                raise zot.cite_failure(cite, keys)
            warnings = []
            draft, _ = draft_item.item_of(res, schema, warnings)
            sets = to_fill(draft, rows[keys[0]], types)
            if not sets:
                return cli.skipped("nothing_to_fill", key=keys[0])
            batch.append({"cite": cite, "set": sets, "from": str(path.absolute())})
            return {"code": "fill", "key": keys[0], "fields": list(sets), **({"warnings": warnings} if warnings else {})}

        for path, res, problem in results:
            if res is None:
                out.lines.append({"slug": path.stem, "code": "result_invalid", "path": str(path), "detail": problem,
                                  "hint": "Give paper-fetch's result files of identified papers."})
                continue
            cite = res.get("cite") or res["slug"]
            out.add({"slug": res["slug"], "cite": cite}, lambda: line(path, res, cite))
        target = Path(args.out).expanduser().absolute()
        target.parent.mkdir(parents=True, exist_ok=True)
        run.atomic_write(target, "".join(json.dumps(b, ensure_ascii=False) + "\n" for b in batch))
        return out.finish({"batch": str(target), "lines": len(batch)})

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
