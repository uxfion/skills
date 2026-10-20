# paper-to-zotero efficiency review (2026-10-20)

Read-only subagent review at `c528750`, kept as written. Not verified line by line; the spec marks what the main session checked. The test timings were measured; the network costs are estimates.

Scope: scripts/, tests/, SKILL.md, references/batch.md, v3 spec §5.2. Production costs are for a batch of about 50 papers.

**Measured locally:**
- a script starts in 70–100 ms;
- `uv run` adds about 10 ms;
- `p2z.py` dispatch adds about 150 ms;
- the test suite: 325 tests, about 199 s file by file.

Every test points at an ephemeral 127.0.0.1 mock or a closed port. No call touched Zotero or the network. Network costs below are estimates and say so.

Production findings come first, largest win first; tests have their own section.

## 1. fetch.py starts a full Downloads scan for each record and each wait tick (largest win)
- **Where:** `fetch.py:183` `arrived()` and `:239` `scan_downloads()` start `claim.py --scan` as a subprocess:
  - before every record in http/page routes, up to 3× per record;
  - every 1 s in `wait_for_file` (`:244`): about 26 spawns per refused page;
  - every 10 s in `wait_at_gate`.
- **What each scan does (`claim.py:253-288`):**
  - re-reads `fetch.jsonl`;
  - for each file newer than `.started`, computes the **md5 of the whole file before checking for `%PDF-`** (`:261` runs before `:264`), so any big non-PDF download is fully hashed on every scan;
  - **sleeps 0.2 s per PDF** (`:266`);
  - **re-reads all record files once per file** (`:272` is inside the loop);
  - spawns `check_pdf --match` for each candidate.
- **The watcher does the same:** `claim --watch` repeats all of this every 3 s for the whole run, on drvfs, even when nothing changed.
- **Cost:** with k leftover PDFs in Downloads, every scan sleeps 0.2·k s and hashes k files. Across a batch's 150–400 fetch-side scans, k = 5 is about 2–7 min of sleep, plus idle CPU and I/O from the watcher. The watcher and fetch.py also check the same new file twice and race to file it.
- **Cheaper:** a scan function in the shared pipeline module that keeps state between ticks:
  - snapshot Downloads by `(name, size, mtime_ns)` and act only on what changed;
  - check the header first, and hash only a PDF that is about to be matched;
  - treat "same size on two ticks" as stable, instead of sleeping;
  - re-read records only when `records/` changed.

  fetch.py then just stats `records/<slug>.*`, and runs the scan in-process when no watcher runs.
- **Spec decision needed:** how fetch knows a watcher is running (a pidfile in `<work>/`, or keep `--downloads` as the "scan yourself" flag).
- **Visible behaviour:** none. A file may land up to one tick later.

## 2. page_route runs its two waits one after the other
- **Where:** `fetch.py:440-451`. After a refused in-page fetch it waits `DOWNLOAD_WAIT` (25 s) for a download, and only then checks the mark and polls pdf.js for up to `VIEWER_WAIT` (20 s).
- **Cost:**
  - a pdf.js viewer that is already ready is read only after a pointless 25 s;
  - a navigation to a login page takes up to 45 s before `stopped`;
  - about 20–25 s per such paper, so 4–8 min per pass at 10–20 stops.
- **Cheaper:** one loop with one 25 s deadline that checks both the file (a stat) and the viewer or mark each second, and ends on the first decisive signal. Stopping even earlier on a non-viewer page would be judging the page, which is the agent's job; leave it out.
- **Owner:** fetch, using the pipeline module's file check.
- **Visible behaviour:** none, only faster.

## 3. Pacing lasts only one process, and each script defines its own
- **Where:** separate tables in `doi_to_item.py:254`, `fulltext_links.py:80`, `fetch.py:88` and `lint_items.py:141`. "429 stops the host for the rest of the run" really means for the rest of the process: `STOPPED`/`LAST_CALL` are module-level.
- **Problems:**
  - fetch's 15 s institution gap resets on every rerun. The agent reruns after every `stopped`, so the gap across reruns is just the agent's own latency.
  - `fetch.py:296` http_route logs `http_429` and keeps hitting the same host.
  - arxiv.org PDFs get fetch's default 1 s, while export.arxiv.org gets 3 s.
  - Crossref's 1 s is duplicated, and no request sends `mailto`, so Crossref's polite pool is never used.
- **Cheaper:** one host table and one pacer in a shared domain module, persisted in `<work>/pace.json` (last request time and 429 stops, under a file lock). Every call reads it, so reruns honour it. Add `mailto` from config (a placeholder in the repo).
- **Cost:** none; this makes the deliberate pacing actually hold.
- **Visible behaviour:** yes. Reruns wait out the remaining gap, and a 429 holds across calls.

## 4. Library reads one at a time where `itemKey=` (up to 50) would do
- **Per-record GETs:**
  - `find_in_library.py:694` (`--readback`): GET item plus GET children per record (`:346`, `:399`);
  - `attach_file.py:383,394,440`: three GETs per record;
  - `file_and_tag.py:487`: one GET per batch entry;
  - `create_item.py:458`: a readback GET when the POST answer lacks fields;
  - `trash_item` `process`: three GETs per key.
- **Parents one at a time:** `find_in_library.py:298-303` GETs one parent per child hit. A new paper's title search falls back to `qmode=everything` (`:443`), whose hits are mostly the full text of PDFs that cite it. That is K sequential GETs, and K grows with how well-cited the paper is.
- **Proposal:** batched listings. `export_bib` and `read_library` already batch with `itemKey`.
- **Verify before building:** the readback redesign rests on a code comment, not a tested behaviour: `read_library.py:193-194` says `items?itemKey=…` also returns the children of the keys asked for. The same file notes that `/items/<missing>/children` returns the whole library, so the local API has quirks. Confirm on Zotero 10.
- **Repeated lookup:** `create_item.py:664` re-runs the whole lookup as a subprocess. The re-check itself is deliberate, but it could be skipped when the library's `Last-Modified-Version` (one cheap GET) equals a version stamped at the step-2 lookup.
- **Attachment objects:** `attach_file.py:426` POSTs one per file; one POST could carry up to 50. Uploads stay per file.
- **Cost:** about 150–250 of roughly 300–400 local requests per batch, i.e. tens of seconds. The md5 docstring measures 1–2 s per 100-row page.
- **Owner:** shared Zotero module (`get_many`, `children_of`).
- **Visible behaviour:** none, apart from a new lookup-version field in the record.

## 5. External APIs: batching and cross-host overlap (estimates)
- **Batching (per public docs; confirm the limits):**
  - Europe PMC (`fulltext_links.py:331`): `DOI:"a" OR DOI:"b"…` could replace one search per DOI;
  - Crossref (`crossref_work`, `doi_to_item.py:392`, used at `:429` and `:1204`): `filter=doi:A,doi:B` could replace one GET per DOI;
  - OpenAlex (`:313`): `filter=doi:a|b`. However, its docstring says a single-DOI lookup is free with a key; list queries may cost credits, so check pricing first.
- **Keep:** doi.org CSL, one request per DOI.
- **Overlap:** OpenAlex and Europe PMC are different hosts, so run them concurrently, each with its own pacer. That roughly halves `fulltext_links` and fits batch.md's one-caller-per-service rule.
- **Connection reuse:** urllib opens a new connection through the proxy for every request (CONNECT plus TLS). Keep-alive might save 0.3–1 s on each of about 250 requests; measure first.
- **Visible behaviour:** none.

## 6. Browser bytes travel in 1 MB base64 chunks
- **Where:** `fetch.py:90,344`. Each chunk is a separate `opencli browser eval` process.
- **Cost:** about 8 evals for a 5 MB PDF, roughly 2–4 s (estimate); 2–3 min over 50 browser-fetched PDFs.
- **Cheaper:** a bigger CHUNK. First check whether 1 MB is a limit of the extension transport; if so it is deliberate.
- **Owner:** fetch/browser. **Visible behaviour:** none.

## 7. The Zotero schema is fetched again and again
- **Where:**
  - `check_item.py:188`: `/api/itemTypes`, then for each item type the full `/api/schema` plus `itemTypeFields` and `itemTypeCreatorTypes`, which repeat what the schema holds;
  - `doi_to_item.py:371`: once per call, and each `--redraft` is a separate call;
  - `update_item.py:226` and `merge_items`: once per call.
- **Cost:** if `check_item -i` runs per record, as SKILL.md step 2 shows, plus per-record redrafts, that is about 100–200 full-schema GETs per batch. Run once over the glob, it is 1 + one per item type.
- **Cheaper:** `<work>/scratch/schema.json` for the run (ready.py clears it), owned by the shared Zotero module.
- **Visible behaviour:** none.

## 8. The same file is extracted and hashed several times
- **pdftotext and pdfinfo:** they run in `claim --file` (fetch spawns claim, which spawns check_pdf: two interpreter starts) and again in step 4's `check_pdf -i`. A "left" file is re-extracted every time it is re-matched.
- **md5:** computed in claim `:261`, check_pdf `:378`, attach_file twice on the same bytes (`:380`, `:618`), and in `find_in_library --md5`.
- **Cost:** about 5–20 s per batch, plus the spawns.
- **Cheaper:** an extraction cache in `scratch/`, keyed by `(size, mtime)` → md5 → pages, with claim calling `check_pdf.extract/judge` in-process. Claim still must not write records (that rule prevents write collisions).
- **Concurrency is safe here:** local CPU only, so a small thread pool over 50 files works.
- **Visible behaviour:** none.

## 9. Whole-library scans
- **The cite-key fallback:** about 7 copies of `resolve_cite` (e.g. `find_in_library.py:307`, `attach_file.py:209`, `read_library.py:150`) scan all of `/items/top` (10–40 s) when the `q=everything` search misses, e.g. for one mistyped key. Only `file_and_tag` and `trash_item` share one scan across several keys.
- **`lint_items.py:247`:** reads the whole library on every call. That is deliberate (duplicates are found across the library), but organizing reruns it after each fix.
- **`report.py:383`:** pages through all tags to count a few names.
- **Cheaper:** a `scratch/` snapshot refreshed with `items?since=<version>` (SKILL.md already uses `since`), plus one shared resolver (search, one shared fallback, a cite→key cache). Whether permanent deletions show up in `since` is unverified, so allow a full refresh.
- **Visible behaviour:** a snapshot can go stale if the user edits the library mid-run. Post-write readback must stay live, because the report comes from it.

## Other points from the brief
- **Per-call setup (point 1):**
  - one `GET /api/` and one config read per writer call cost tens of ms; keep both (deliberate, see the end);
  - the collection tree: `create_item` caches one GET per distinct collection per call; `report` and `find_in_library` single mode re-read the tree. Small; no action.
- **Small fixes:**
  - `p2z.py:21` parses all 21 scripts' ASTs on every dispatch (+150 ms per call). Check that the file exists instead, and parse only for `--help`.
  - `ready.py:329` starts powershell.exe on every call (1–3 s).
- **Record I/O (point 4):** every script reads all records once per call and writes back only the ones that changed. The one offender is claim's per-file re-read (§1).
- **Long-lived objects (point 8):** none seen. The watcher is the only long-lived process, and it keeps nothing between ticks, which is exactly §1's problem.
- **Subprocess vs import (point 3):**
  - create_item → find_in_library: once per call;
  - attach_file → check_pdf: once per call;
  - claim → check_pdf: once per file;
  - fetch → claim: once per file plus once per tick (this dominates);
  - claim → find_in_library: once per run (`--sweep`).

  Importing is cheaper and simpler, and drops the JSON-over-stdout re-parsing. It reverses v3 §5.2 ("only through subprocess"); keep the timeouts the subprocess boundary used to provide.

## Deliberate costs that must stay
- One `GET /api/` per write call: the live server id catches a Zotero restart.
- The config re-read per call (the user edits it mid-run).
- The 3 s watcher interval, the 10 s gate polling and the 5 min gate wait. drvfs gives no inotify for files written from the Windows side, so polling is right; just make each tick cheap.
- The host spacing: doi.org 0.5 s, Crossref 1 s, arXiv API 3 s, OpenAlex 0.1 s, Europe PMC 0.2 s, medRxiv/bioRxiv 10 s, institution 15 s, Scholar once a minute.
- One request at a time per host, and one browser driver.
- The duplicate check before posting.
- The once-per-run `--md5` sweep.
- No parallel local-API calls: Zotero serializes writes.

## Tests (measured)
- **Port 9 hangs on this WSL:** a request to `127.0.0.1:9` hangs until the timeout (12.6 s measured, against 0.1 s on a port bound then released). Five tests use it: `test_find_in_library:487/496/499`, `test_check_item:181` and `test_read_library:287`. Together they take about 85 s, 43% of the suite: find_in_library 46.6 s, read_library 30.2 s (`ReadLibraryTest.test_unreachable_and_disabled` alone: 30.8 s), check_item 14.4 s. There are five separate `closed_port` helpers, and `test_doi_to_item` already warns about port 9. One shared helper fixes this, with no behaviour change.
- **Script spawns:** about 420 at roughly 0.1–0.15 s each, about 50–60 s in all. create_item spawns twice per stream call, and each file builds its own fake server (15 different `Handler`s). A shared FakeZotero with tests calling `main(argv)` in-process would cut this to seconds. Keep a few subprocess smoke tests per script for the shebang, exit codes and stdout shape.
- **Sleeps:** about 15–20 s in all, cut by a pace override or injectable clock from the shared pacer:
  - fetch's `DOWNLOAD_WAIT` 2 s and `VIEWER_WAIT` 1 s per refused route, plus the 1 s pace on 127.0.0.1;
  - doi_to_item pacing is keyed on the real host names, so its tests sleep 0.5–3 s with no override;
  - about 3 s of authorize waits in ready.
- **Run files in parallel:** they already use ephemeral ports and temp dirs, so wall time drops to about the longest file.
