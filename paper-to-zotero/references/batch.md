# Several papers

Read before step 0 when the request covers two or more papers — a list, a .bib, a search result, "these three". One paper is a batch of one; nothing here contradicts the steps, it only says how they run over many records at once.

## The records are the state

Every paper is one file, `<work>/records/<slug>.json`, and every script is a filter over records: paths in (glob them), the updated record out, `-i` to write it back in place. What a record contains says how far its paper got — `item` drafted, `found` in the library, `saved` created, `file` in hand, `pdf` checked, `attach` uploaded, `blocker` waiting on someone. There is no other state file: when in doubt, `find_in_library.py --readback -i <work>/records/*.json` refreshes every record from Zotero, and `report.py` turns the records into the table you report.

```bash
uv run scripts/doi_to_item.py --ids ids.txt --out-dir <work>/records       # one record per identifier; `id<TAB>citation key` per line
uv run scripts/find_in_library.py -i <work>/records/*.json                # found ones get record.found
uv run scripts/check_item.py -i <work>/records/*.json
# … edit each record's item, tags, collection (in parallel, see below) …
uv run scripts/create_item.py -i <work>/records/*.json --collection <key>  # skips found/saved; ≤50 per POST
# … PDFs one by one into records/<slug>.pdf, record.file set …
uv run scripts/check_pdf.py -i <work>/records/*.json
uv run scripts/attach_file.py -i <work>/records/*.json                    # skips md5_ok
uv run scripts/find_in_library.py --readback -i <work>/records/*.json && uv run scripts/report.py <work>/records/*.json
```

Author keywords and abstracts usually turn up on the article page, i.e. after `create_item.py` has run: add them to the item with `file_and_tag.py --cite <key> --add-tags-file …` and `update_item.py --cite <key> --patch …` (and to the record, so it stays the truth of the run). A paper the library already holds with a file needs nothing from `attach_file.py`; it reports `skipped`. A citation key you gave that differs from the library's stays in the record — the report marks the difference — and is only pinned onto the existing item when the user says so.

Every script skips what is already done and reports it as `skipped`, so the same command line is also the recovery: after an interruption, a crash or a "继续", run it again. With `-i` the scripts print one summary line per record, not the record — read those, not the files.

A .bib or .ris the user has is a list source, not something to import as is: `doi_to_item.py --bib ref.bib` takes each entry's DOI (else arXiv id, else title) as the identifier and its citation key as the slug and `citationKey`, so the created items carry the keys the manuscript cites.

## Ask once, then run

Pin all papers first (step 1 for each), then put every question in one message: candidates to choose between, preprint-or-published pairs, destinations for papers the user did not place. Scope the user has already set — destination, version preference, what may be renamed or removed — holds for the whole run; ask again only about a paper it does not cover. Nobody to ask → `tmp` and say so in the report.

## What runs in parallel

Pinning, drafting, abstracts and tags touch only metadata services — split them over subagents (at most five). Fetching PDFs does not: one `p2z` session, one paper at a time, so only one gate ever waits on the user and a login passed once serves every paper on that site. A subagent that hits a gate alerts the main conversation with `SendMessage` (the Gate rule) — it has no other way to reach the user's screen.

## Sites, gates and blockers

Keep `<work>/sites.json`: `{"<host>": "ok" | "no_subscription" | "gate_pending"}`. A site the user declared unsubscribed is not asked to log in again this run; its papers take the no-PDF branch. A gate that times out stops the papers on that site — the next one would hit the same page — while other sites and the metadata work continue. Write the record's `blocker` (page, time, what is missing) for every paper left waiting; the report lists them, and the work directory stays until they are resolved or the user drops them.

## Report

`report.py` prints the table (citation key, title, year, item key, collections, tags, PDF / snapshot / —, blocker) and the counts, all from the read-back — never from the run log or from memory. Add the per-paper details that matter (substitutions, sources named, gates hit) and the **skill notes**: what this skill lacked, got wrong or made you work around. One-off code you wrote lives in `<work>/scratch/`; it is residue like everything else in the work directory.
