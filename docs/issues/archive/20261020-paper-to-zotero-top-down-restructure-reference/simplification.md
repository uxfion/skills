# paper-to-zotero: simplification review (2026-10-20)

Read-only subagent review at `c528750`, kept as written. Not verified line by line; the spec marks what the main session checked.

Scope: all 21 scripts, the tests, SKILL.md and references/. Nothing was edited. Legend: **D** = named in SKILL.md or references/*.md, **S** = only called as a subprocess by another script, **T** = only in tests, **–** = nowhere. One caveat: SKILL.md:8 says each script's `--help` is the reference for its flags, so every flag is documented in a loose sense. I still made a call on each one. Findings are ordered by size of win.

## 1. Single modes. None is in the docs except `find_in_library --cite`

About 290 script lines, 70 lines of argparse mode checks and 210 test lines (measured with ast).

| script:line | single mode | how it differs from the stream mode | call |
|---|---|---|---|
| doi_to_item.py:1453 | `--doi --out` (22 + 1688-1694) | puts the arXiv tags in `item.tags` (1462). That is the only reason create_item.py:628 has an `item.tags` fallback | drop; keep `fetch_and_map` |
| create_item.py:482 | `--item --tags-file --out` (77 + 804-817) | **no duplicate check**, no citationKey, and `saved.json` uses `item_key` where records use `key` | drop |
| attach_file.py:667 | `--key/--cite --file --url --filename --accept` (57 + 723-738) | checks the file with a check_pdf `--match` subprocess (360), where stream mode checks the record's `pdf.md5` (621). `--accept` duplicates `pdf_accepted` | drop the CLI; keep `attach_one` for the structured-package flow |
| check_pdf.py:767 | `--item --pdf` (16 + 808-814) | its own exit rules | drop; keep `judge()` |
| check_item.py:403 | `--item` (32) | SKILL uses only the `--help` skeleton | drop |
| find_in_library.py:471 | `--doi/--arxiv/--title` (46), T | exit codes are inverted (found = 1) | drop |
| find_in_library.py:519 | `--key/--cite`, D (organize.md) | prints a second item shape, `describe()` (366: collection paths, numAttachments), next to `readback()` (387) | make it a record of one (below) |

**One code path.** `find_in_library --cite K` is just `--readback` run on an in-memory record `{"found": {"key": K}}`, printing the refreshed block. That deletes `describe` and `collection_paths` (39 lines) and leaves one item shape. Any single flag the spec keeps should work the same way: it builds a record and calls the same `process(rec, ctx)`. No `run_single` should remain anywhere. The flags disappear from the CLI, so this is visible.

## 2. Modes that only scripts use, and the stdin/stdout record stream

This depends on the shared modules the issue already plans, so the spec has to sequence it after them.

- `check_pdf --match` (743) is used only by claim.py:166 and attach_file.py:360. `find_in_library --md5` (539) is used only by claim.py:297. The stdin stream into find_in_library is used only by create_item.py:654. `claim --version/--source/--via` are used only by fetch.py:228.
- With imports from the same directory, these become function calls. That removes the subprocess plumbing, the JSON re-parsing and the exit-code translation (create_item `look_up` 24 lines, attach `check_against_item` 13, claim `match` 15, the sweep subprocess). It also removes the separate exit rules of `--match`.
- After that, nothing reads records from stdin or writes whole records to stdout:
  - The stdin parser accepts three shapes and is repeated in 8 scripts.
  - Without `-i`, results go to two places: records to stdout and summaries to stderr. Only check_pdf, create_item, attach_file and fulltext_links print the per-record summaries to stderr; find_in_library, check_item and doi_to_item don't.
  - The docs only ever use `-i` with paths.
- **Call:** record paths in, always written back. `-i` stays accepted and does nothing. Keep `claim --file --slug`, which publishers.md documents. Output without `-i` changes, so this is visible.

## 3. "The field exists, so it's done" forces escape flags, and `links` has two writers

- doi_to_item `--candidates/--refresh/--no-candidates` (T only) exist because `published_candidates` is written even when one of its sources failed (1209). The documented recovery is to rerun the same command, and that rerun then skips the record for good (`has_item`/`has_candidates`).
- fulltext_links `--refresh/--sources` (T only) exist for the same reason (434).
- **Rule for the spec:** a script writes its block only when it is complete. A partial answer leaves the field absent, so a plain rerun retries it. This removes 5 flags, `wants_candidates` (1597-1610), the rewrite of skipped lines to ok (1650-1653) and the checks at 1688-1691.
- **`links` has two writers.** A page-form redraft writes `links` (doi_to_item.py:1408). SKILL.md:75 then says to rerun fulltext_links, but fulltext_links.py:434 skips the record because it already has links. Result: an ICLR/PMLR paper redrafted from its page never gets its arXiv link, so chain step 5 (`--via http --version preprint`) logs `no_link` for it.
- **Fix:** fulltext_links is the only writer of `links`. The redraft only clears the field. If the venue PDF link matters, it becomes a fourth fulltext_links source that uses the shared `page_meta`.

## 4. A `found` that is only a near match is read as a real match

- `found` is also written when the match is only a near match (`found.code == "near_match"`). Four readers ignore that code:
  - claim.py:105 `library_has_pdf` reads its attachments, so the record is left out of Downloads matching.
  - report.py:200 `library_state` shows the near match's collections and tags as the paper's.
  - attach_file.py:558 `item_key_of` uses its key.
  - export_bib.py:264 uses its key.
- **The attach_file case is the dangerous one.** SKILL step 4 runs `attach_file.py -i` right after create_item. A record that create_item failed as `possible_duplicate` still has `found.key`, so the PDF is uploaded onto the near-match item, which can be the preprint or a correction notice.
- **Fix:** `found` holds only a confirmed match. Near matches go into their own field, and the agent promotes one by writing `found: {"key": K}`, as SKILL already describes. This removes `candidates_of` and the `near_match` branches in create_item (583-603, 692) and collapses three result branches in find_in_library. The record schema changes, so this is visible.

## 5. `saved` has two shapes, `attach` has two shapes

- create_item.py:725 writes `saved` as `{key, version, created_at}`. find_in_library `--readback` (703) rewrites it into the full readback shape. report.py:203 guesses which shape it has by looking for `attachments`/`tags`.
- **Fix:** write the readback shape at creation. The POST response already carries `data` (create_item.py:454). Keep the two names `saved` and `found`: "created by this run" matters for undo and for the new-tags section.
- `attach` is written in two shapes by the same script (attach_file.py:631 vs :639). The `already_attached` shape has no `version`, so report.py:333 treats a preprint file as the published version.
- `attach.md5_ok` is always `true` whenever `attach` is written. Keep the name only because SKILL.md:129 uses it as the done test.

## 6. Inside scripts, biggest first

**Docstring repeated in the epilog, and version history in code**
- The module docstring and the `EPILOG` restate the same rules in doi_to_item (6-84 / 187-227), check_pdf (6-81 / 170-196, plus `HINTS`), create_item (6-45 / 72-101) and fulltext_links (6-57 / 117-126); about 120 lines. Use `__doc__` as the help text, as lint_items.py:234 and merge_items.py:225 already do. Keep check_item's `SKELETON`, which SKILL.md:194 relies on.
- References to version history: "v1" in 13 places, `B#3`/`B#4`, and "spec §4.4", "§6", "3.2" (doi_to_item:50, 252, 1176, 1346; find_in_library:692; attach_file:377, 559; check_item:33, 44; create_item:8, 480). Most go with the single modes; delete the rest.

**doi_to_item.py**
- Input handling (1477-1594): entries carry `given_key`/`no_identifier` flags. `process_entry` is 61 lines with 7 exits. The slug is assigned in 5 places through `unique_slug(slug_for(...))`, backed by three dicts (`seen`/`used`/`existing`, 1626). Turn every input into a record at collection time and assign the slug once, at save.
- There are five input sources; the stdin one (identifier lines or records) goes per §2.
- `run_redraft` (1345, 83 lines) has a `done()` closure, a third output path and `sys.exit(2 if … else out)` (1392). Make it `process()` with a different source for the item.
- `build_item` (595, 138 lines) is a list of independent rules. Split it into small rule functions; low priority, nothing visible changes.
- In `published_candidates`, `redraft` always equals `doi` (1168), and `source` sits next to `sources`, which appears only when there are two or more (1169). Drop `redraft` and always use the `sources` list.

**find_in_library.py**
- Five modes share one parser (828-858), and their exit codes contradict each other: single lookups give found = 1, `--key` gives found = 0, the stream gives found = 0.
- `process_record` (688) is 100 lines. The readback branch (690-716) is really its own mode and should be its own function. The pair, near and found outcomes (758-786) each build `found` plus a summary line; one helper can do all three.
- `lookup_doi` (407) and `lookup_arxiv` (422) are copy-paste of each other. Make one `lookup_id(matcher, why)`.

**create_item.py**
- `run_single` duplicates `prepare_record` plus `post_pending`.
- `readback` (451) returns a 6-tuple, and each mode uses half of it. Return a dict.
- `--collection` as a default for records (791) is T only; SKILL.md:92 requires the record's own `collection`. Drop it.

**attach_file.py**
- `attach_one` (375) has 13 parameters; the `verify` callback and `filename_arg` exist only to serve two modes.
- The file is resolved four ways (591-612): the record's `file`, then `--file`, then the files named after the record, then a skip when the library already has an attachment. Nothing writes `file`, and batch.md says files are not record fields. Keep only the files named after the record.
- The aliases `--pdf` and `--pdf-url` (708, 711) are used nowhere, not even in tests. The `--url` fallback (613) is dead in practice, since check_item requires a DOI or url. `--title` is T only.

**check_pdf.py**
- Three modes (825-833), each with its own loader and exit rules (747).
- `--pdf` (647) is T only.
- `--alt-title` (802): the help says the title is "added to each record's alt_titles", but line 719 never saves it.
- `--file-version` becomes a function argument once claim imports `judge`.

**file_and_tag.py**
- `run_single` (348, a PATCH plus a retry on 412) and `run_batch` (480, POST in chunks) are two write paths for one diff. Make the single-item flags build a batch of one; single mode's output becomes the batch shape. Visible.

**fetch.py**
- `--session` (654) and ready.py's `--session` (470, "only echoed back") appear nowhere in the docs; SKILL fixes the session as `p2z`. Drop both.
- `--current` (653) has no docs and no test. Drop.
- `--version unknown` (650): fulltext_links emits `unknown` links (repository copies, PMC links when Europe PMC didn't answer), but no step of the chain ever fetches them. That is a gap: either step 1 includes them, or the choice goes.
- Five timing env vars (89-96) exist only for tests. Keep them, defined in one place.

**Small items**
- read_library: `items --top` (346) does nothing (it is the default), and `item KEY` (358) is the same as `items --key KEY`. Drop one of each.
- report: `--no-resolve` (523) is redundant, because collection paths already fall back to keys when the API fails (125).
- `lint_items --only` (T), `claim --interval` (–) and `fulltext_links --sources` (T) can go.
- Flags that take several values follow three conventions: `--key A B` (lint 238, trash 306), `--key A --key B` with commas allowed (read_library 349, export_bib 370), and one value only (update_item, note, file_and_tag). Pick one: repeatable, commas allowed.
- Exit-code mismatches: fulltext_links.py:142 exits 1 through `SystemExit(str)` for `bad_config`, while its docstring says 2 and other scripts call the same thing `config_unreadable`. lint_items.py:276 exits 2 for `collection_not_found`, where every other script exits 1.

## 7. Flags against the docs

| script | D | S | T only | – | call |
|---|---|---|---|---|---|
| attach_file | -i | | --key --cite --file --url --filename --title --accept --dry-run | --pdf --pdf-url | keep -i and --dry-run |
| check_item | -i, --help skeleton | | --item | | drop --item |
| check_pdf | -i | --match, --file-version | --item --pdf --alt-title | | -i only |
| claim | --work --watch --sweep --scan --downloads --file --slug | --version --source --via | | --interval | drop --interval |
| create_item | -i | | --item --tags-file --out --collection --dry-run | | keep -i and --dry-run |
| doi_to_item | --doi --ids --bib --out-dir --redraft -i, paths | | --out --candidates --no-candidates --refresh, stdin | | drop the T set |
| export_bib | --collection --cite --out, paths | | --key --recursive, stdin | | drop stdin |
| fetch | --via (all 5) --pass --version (accepted, preprint) --start --downloads --verdict --wait --until --for --window | | --timeout | --session --current, `unknown` | drop the – set |
| file_and_tag | --key --cite --batch --dry-run --add-* --remove-collection | | --collection --tags-file | | keep |
| find_in_library | -i --readback --cite | --md5, stdin | --doi --arxiv --title --key | -v | §1, §2 |
| fulltext_links | -i | | --sources --refresh | | drop both |
| lint_items | --collection --recursive --crossref | | --key --cite --only | | drop --only |
| read_library | items --q --cite --collection, pdf, children, collections --tree, tags --min-count | | items --key --all --limit --since --tag, schema | items --top --qmode, `item` | drop --top and `item` |
| ready | --work --authorize | | --downloads --timeout --session | | drop --session |
| report | --work, paths | | --json --no-resolve, stdin | | drop --no-resolve |
| make_collection, merge_items, note, trash_item, update_item | documented set | | make_collection --dry-run; note --key --text --dry-run | | keep |
| all scripts | | | --base-url, `*_BASE_URL` and `PAPER_TO_ZOTERO_*` env vars | | keep as test seams |

## 8. Tests

**Go with the dropped modes**
- The SingleMode classes in test_attach_file (185-257) and test_create_item (196-246, 495).
- `test_v1_*` in test_doi_to_item, test_check_item and test_find_in_library.
- Six tests that only check single and stream flags reject each other: test_create_item:446, test_check_item:112, test_find_in_library:204, test_doi_to_item:338, test_attach_file:434, test_check_pdf:414. About 210 lines in all.
- `--match` (test_check_pdf:386-419) and `--md5` (test_find_in_library:430-490), about 85 lines, become function tests.
- Stdin-format tests in 9 files, about 160 lines.
- test_doi_to_item:695 (`--candidates`) and test_fulltext_links:252 (`--refresh`) change.

**The same scenario in several files**
- citation key found by search, then the scan fallback: test_note:262-292, test_read_library:217, test_trash_item:239, test_find_in_library:179-203, test_file_and_tag:217-256, test_export_bib:182-196.
- cannot-check / unreachable: about 14 files.
- write in place, then rerun: 7 files (test_check_item:131, test_attach_file:277, test_check_pdf:174, test_create_item:281, test_find_in_library:249, test_doi_to_item:380, test_fulltext_links:264).
- 412 handling: 5 files (create, file_and_tag, merge, note, trash).
- paging and chunks of 50: 4 files.
- "key never printed": 2 files.

Test each of these once against the shared module, and keep one smoke test per script.

## (a) Proposed script skeleton

```python
#!/usr/bin/env -S uv run --script
# /// script ... dependencies = [] ///
"""<one-line purpose>.

<help: what it reads, the one block it writes, its codes, its exit codes>"""
import sys, p2zlib as p2z                 # same-directory shared module

def process(rec, ctx):                    # the script's one job
    if rec.get("links") is not None:      # the field exists = done (written only when complete)
        return p2z.skipped("has_links")
    links = ...                           # raise p2z.Stop(code, hint, **extra) on failure
    rec["links"] = links                  # the one field this script owns
    return p2z.ok(links=len(links))

def main():
    args = p2z.parser(__doc__, records=True).parse_args()   # RECORD paths, -i (no-op), --base-url
    sys.exit(p2z.run_records(args.records, process, p2z.Context(args)))
```

- `run_records` loads each path (a bad file gives `record_invalid` for that record only). It catches `Stop` per record; an exit-2 `Stop` ends the run and marks the rest `not_run`. It writes changed records back atomically, prints the lines and the summary, and returns 0, 1 or 2.
- Scripts that act on library items use `parser(__doc__, items=True)` (repeatable `--key/--cite`, one resolver) and `run_items(targets, process, ctx)` with the same lines, summary and exit codes. The one-object scripts (ready, make_collection, merge_items, note, update_item) are `run_items` with one target.
- A flag that names one paper builds a record in memory and runs the same `process`.

## (b) Proposed output convention

- stdout carries JSON only. The two exceptions are report (Markdown) and export_bib (BibTeX), whose JSON goes to stderr. Otherwise stderr is human diagnostics only.
- One compact JSON line per unit (record, item or file), then `{"summary": {total, ok, skipped, failed[, stopped][, dry_run]}}`, also when there is only one unit. Drop `indent=2`: the agent gets one format to parse, at the cost of less readable raw output.
- Each line is `{slug | key [, cite], code, …}`. `hint` appears exactly when the code is not `ok` or `skipped`. A skip is `code: skipped` plus a `reason` token: never prose (find_in_library.py:716), never a field path (attach_file.py:588), and never a status skipped with code `exists` (create_item.py:690).
- One table of codes:
  - environment: zotero_unreachable, local_api_disabled, no_key, key_rejected, server_mismatch, config_unreadable, api_error;
  - input: record_invalid, no_records;
  - lookup: not_found, cite_not_found, cite_ambiguous;
  - write: version_conflict, write_denied, readback_mismatch.

  This replaces today's synonyms: item_not_found / not_found; invalid_record / invalid_json / unreadable / input_invalid / record_not_found; no_id / no_identifier / invalid_identifier; unexpected_response / api_error; bad_config.
- Exit 0 = every unit ok or skipped. 1 = some unit needs the agent. 2 = cannot check. An answer such as found vs not found, or matched vs not matched, is a code and never an exit status.
- Name things one way: `key` for the 8-character item key (never `item_key`), `cite` for a citation key echoed from the input, `citationKey` for the library's value (never read_library's `cite` for that).
- Leave fetch.jsonl's `event`/`result` as they are; SKILL.md:45 greps for them.

## (c) Who writes which record field

| field | written by | issue → call |
|---|---|---|
| slug | doi_to_item | always equals the file stem. check_pdf:650 and attach_file:594 find files by the stem, claim:100 and fetch:178 by `slug`, so there are two truths. Derive it from the path |
| id | doi_to_item | input identity; keep |
| citationKey | doi_to_item (--ids/--bib), agent, find_in_library --readback (copies the library's, 712) | keep it as the wanted key; drop the readback copy, since the library's key is in saved/found |
| item | doi_to_item, agent | keep |
| tags | doi_to_item (arXiv categories), agent | drop create_item's `item.tags` fallback |
| collection | agent | either a string or a list; read it always as a list |
| warnings | doi_to_item | keep |
| code / hint / detail | doi_to_item on failure (1551-1575) | only doi_to_item:1601 reads them; drop, the summary line has them |
| published_candidates | doi_to_item | write only when complete; drop `redraft`; always `sources` |
| alt_titles | doi_to_item --redraft, agent | keep (check_pdf's flag doesn't save to it) |
| found | find_in_library, create_item (copy), agent (`{key}`) | confirmed matches only; near matches in their own field (§4) |
| distinct_from | agent | string or list; read as a list |
| links | fulltext_links, doi_to_item page redraft | one writer (§3) |
| checks | check_item | keep |
| pdf | check_pdf (cleared by redraft) | keep |
| pdf_accepted | agent | keep (replaces `--accept`) |
| saved | create_item, find_in_library --readback | one shape from creation on (§5) |
| attach | attach_file (two shapes) | one shape; `md5_ok` is always true |
| blocker | agent, find_in_library (missing_in_library) | keep |
| file | **nothing** (read by check_pdf:643 and attach_file:591) | drop |
| checked_at / attached_at | each script with its block | nobody reads them; can go |
