# Importing papers

From what the user gives to Zotero items with their PDFs, filed and tagged, and nothing left behind. The paper-fetch skill identifies each paper and gets its files; this skill chooses the version, drafts the item, saves and attaches, and reports. Two or more papers — a list, a .bib, search results — read [batch.md](batch.md) before step 0.

**The directory**, `<imp>` (SKILL.md, *The scratch directory*), holds `<imp>/fetch/`, paper-fetch's directory for this import — a result file per paper, `fetch/results/<slug>.json`, with its files beside it — and `<imp>/records/`, this skill's record per paper under the same slug. A record points at its result (`fetched`) and holds the item to create and what you decided about it (`scripts/p2zlib/run.py` documents both); you change the record, never the result. The slug is the citation key the user brought — the item will carry it — else `<surname><year><first title word>`.

## 0. Ready

Read `../paper-fetch/SKILL.md` now (no such file → stop, as SKILL.md's *Sibling skills* says): this file names its sections, and its `pf.py` runs on this skill's PATH (SKILL.md, *Calling*).

```bash
p2z.py ready <imp>
pf.py ready <imp>/fetch
pf.py watch <imp>/fetch                    # in the background, the whole run
```

This skill's `ready` lists `leftovers` when an earlier run of this task left `<imp>`: carry on from its records and results, and delete nothing in it unasked, since a PDF that never reached Zotero belongs to the user. `prepare` (step 3) redoes the records of an earlier version of this skill, keeping every answer their handoffs hold.

paper-fetch's `ready` and its watcher: as its *Ready* says.

Done when both `ready`s report `ok` and the watcher runs.

## 1. Identify the papers

paper-fetch's *Identify a paper*, writing into `<imp>/fetch`:

```bash
pf.py identify <DOI | arXiv id | paper page> [--slug <citation key>] -o <imp>/fetch/
p2z.py ids refs.bib | pf.py identify -o <imp>/fetch/ -
```

A .bib or .ris is a list source, never a file to import as it is. `ids` reads a .bib into one `<DOI, else arXiv id><TAB><citation key>` line per entry (a .ris you list in the same form yourself); an entry with neither comes out as `title:…`, which `identify` answers with `needs_pinning` — find its DOI or arXiv id as *Identify a paper* says, then identify it with its key.

Done when every paper has a result with metadata, or is a stub — a DOI without a CSL record, a page that refused — which goes to [no-doi-record.md](no-doi-record.md) once its PDF is in hand.

## 2. Choose the version

The rule is this skill's: **the published version comes first**, unless the user asked for the preprint. It is chosen now, before any record is drafted, so the item is drafted once. A conference paper later extended into a journal article is two papers, two items: the version chosen is this paper's. Confirming a candidate from a preprint's `versions.published` and redrafting the result to it is paper-fetch's *Identify a paper* (`pf.py redraft <DOI | paper page> <result>`); the preprint stays in the result's `versions.preprint`, and drafting takes from it what the published record lacks. No published version, or the user wants the preprint → the preprint it is: tell paper-fetch first, `pf.py identify --wanted preprint <its arXiv id> -o <imp>/fetch/`, since a result that still wants the published version looks for it again on every pass; then its record gets `keep_preprint` with the reason in step 3. The same goes for a preprint kept after drafting (step 3's `published_versions`).

Done when every preprint result is redrafted, or has `wanted: preprint` and its reason to stay.

## 3. Draft the record

```bash
p2z.py draft <imp>/fetch/results/*.json
p2z.py prepare <imp>/records/*.json
```

`draft` makes each record and its `item` from the result's metadata, by Zotero's own CSL tables and the few rules its `-h` lists. `prepare` fills in what the library has (`found`, `near_matches`) and what Zotero will do with the fields (`checks`), skipping a block that is up to date, so run it again after every change. Its line per record lists under `decide` what is still open; the paragraphs below say who settles each. You change only your fields (`item`, `tags`, `collection`, `citationKey`, `keep_preprint`, `accepted`, `blocker`); the blocks are the scripts', the answers on library candidates live in their handoffs, and the curated tags in each paper's tags file.

**What the library already has** (`found`). With a PDF of the paper, of any version (`found.attachments[].version`: `published`, `accepted`, `preprint`, or `unknown` — a title outside the scheme, its version not checked: say so in your answer): report the citation key and stop — unless the request asks for something the item lacks (the published version when only a preprint or accepted manuscript is attached, a tidy, a note), which continues at the step that provides it; look at an `unknown` file only when the request names a version. With no attachment, or only a snapshot or a linked URL: continue from step 4 and attach to that item; a snapshot a new PDF replaces goes into the report's attachments to clean.

**Library candidates** (`same_paper`). Only a DOI or an arXiv id confirms an item, and only when one item carries it; every item a quick search for the title finds is a candidate, and so is each of several items carrying the paper's identifier (`matched_by` on the candidate: the library holds the paper more than once). The open ones wait in a handoff file, `<imp>/handoffs/<slug>.<n>.json`, with the evidence of both sides, and go to same-paper judges (SKILL.md, *Handoffs*; their brief is [same-paper-judge.md](same-paper-judge.md)): each dispatch fills in `<imp>` and its handoffs, the paths `prepare` printed with `waiting_on: judge`. What comes back is an answer per candidate in each handoff: `prepare` again lists none of them as `waiting_on: judge`. A `pair` or `unknown` waits on the user (`waiting_on: user`): it goes into the run's one message of questions with both items' evidence — for a pair, this paper filed in that item (`same`) or in an item of its own (`distinct`) — and the user's word is recorded with `p2z.py answer <handoff> same|distinct --key K --reason "<the user's words>" --by user`, which stands over the judge's answer. The files go to the item answered `same`, and until a candidate is settled, to no item.

**Tags.** Every paper whose item this run creates gets its curated tags ([tagging.md](tagging.md)) in its own tags file, `<imp>/tags/<slug>.json`, written only by whoever tags it; `save` creates the item with them and the record's automatic `tags`, and nothing for a paper without its tags file (`untagged`). `prepare` lists `tags` for every paper not confirmed in the library, a paper with candidates still open included, so tagging runs beside the judges; a tags file written for a paper then answered `same` goes unused. A few papers you tag yourself by tagging.md; for more, tagging subagents (SKILL.md, *Handoffs*): `p2z.py tags > <imp>/scratch/library-tags.jsonl` once, then each dispatch fills in `<imp>` and its record paths, those `prepare` lists under `tags`. What comes back is a tags file per paper and the new tags in their reports; `prepare` lists `tags` for no paper once every file is there.

**`published_versions`**: the item is still the preprint while its result lists published versions — step 2's choice, unmade. Made after drafting: `pf.py redraft`, then `p2z.py draft --redraft <result>` drafts the item again and keeps your other fields; or write `keep_preprint`.

**Checks and warnings** (`checks`, `warnings`): what Zotero will do with a field (`mapped:publicationTitle`: stored as `proceedingsTitle`; `missing_minimum:date`) and what drafting noticed. Revise the item, or accept the effect: copy the flag or the warning, as `prepare` printed it, into the record's `accepted`.

**`unanswered`**: sources that did not answer; run `prepare` again later (for versions, `pf.py identify` the paper again). A source that stays silent is accepted by adding `unanswered:<source>` to the record's `accepted`.

**Revise `item`.** A value without a source stays out.
- Item type: a `bookSection` from a proceedings volume is usually a `conferencePaper` (paper-fetch already makes LNCS-style chapters conference papers when Crossref names the series). The result's `warnings` naming a possible erratum or correction notice: make sure the DOI is the paper's own.
- Abstract and PMID: identify filled them from Europe PMC and OpenAlex where the DOI record had none (the result's warnings say from which, and when the two differ: then read both and keep the paper's). Still empty: the article page, else the abstract stays empty.
- Identifier: the item describes the version of record — never where a copy can be downloaded (the file is the attachment, and copies are found again from the DOI):
  - Published with a DOI (IEEE for CVPR/ICCV, Springer for ECCV/MICCAI, ACL's own): that `DOI`, and `url` `https://doi.org/<DOI>`. NeurIPS 2022–2025 (`10.52202`, the printed proceedings' DOI, which leads to their sales page): the `DOI` too, and `url` the paper's NeurIPS page.
  - Published without a DOI (NeurIPS up to 2021, ICML/PMLR, ICLR and TMLR on OpenReview): `url` the venue's own page for the paper — for OpenReview the forum page, not the PDF.
  - Only a preprint: item type `preprint`, `repository` the server, the server's DOI (`10.48550/arXiv.<id>` for arXiv) and its abstract page as `url`, `archiveID` `arXiv:<id>`. Only on OpenReview (rejected, a workshop): the arXiv version if there is one, else a preprint with `repository` OpenReview.
  - Other versions only as identifiers in `extra`: `arXiv: <id>` whenever an arXiv version exists.

**Destination.** The user named a collection → its path from the tree `ready` printed (ambiguous or missing → list candidate paths and ask); several are fine. No collection named → suggest one from the paper's topic and ask, in the same message as any candidate question. No suggestion possible, or nobody to ask → the collection `tmp` (`p2z.py mkcol tmp` once if absent) and say so in the report. Put the path (or paths, or keys) in the record's `collection`.

Done when `prepare` has run on the final records and lists nothing under `decide` but candidates waiting on the user, who has them in the run's one message, `tags` the tagging subagents are still writing, and `unanswered` sources asked again; the abstract is filled or confirmed absent, and every record has a `collection`.

## 4. Get the files

A record whose item the library already holds with a PDF of the paper needs no file. The results of the rest go to paper-fetch's *Get the file: the chain* — `locate`, then `fetch` pass by pass, every file through `claim` and labelled there:

```bash
pf.py locate <imp>/fetch/results/<slug>.json …
pf.py fetch --pass N <imp>/fetch/results/<slug>.json …
```

Between passes, step 5 saves what is in hand. Before paper-fetch's last pass, the user is told and the run waits: each record still without its file gets a `blocker` saying what it waits for ("last pass with the user: institutional login"), and the report goes out.

Done when paper-fetch's chain is done for every result handed to it, and `pf.py sync <imp>/fetch/results/*.json` has folded the watcher's late arrivals into the results.

## 5. Save and attach

```bash
p2z.py save <imp>/records/*.json
```

Run it after every pass of step 4: it skips what is done, and `no_file_yet` is not a failure. On its lines (each step's code under `steps`):
- `possible_duplicate`: an item came into the library since `prepare`; its handoff goes to same-paper judges as in step 3.
- `untagged`: the paper's tags file is not written yet (step 3), so no item was created; `save` again once it is.
- `readback_mismatch` from `create`: the item exists but a tag or a collection did not stick; `p2z.py tag <citation key> --add-tag … --add-collection …` sets it right.
- `unsettled` or `file_changed`: `pf.py sync <imp>/fetch/results/*.json`, then `save` again.
- `unchecked`: a stub's PDF, which paper-fetch had nothing to check against; [no-doi-record.md](no-doi-record.md) identifies the paper from it.
- Any other failure creates nothing: run that step alone on the record (`p2z.py create <record>` or `p2z.py attach <record>`) for its hint, fix the record as it says and rerun — a rerun is always safe, a run cut off mid-POST included. A file that still cannot be attached goes to the user with its path.

`save` keeps step codes only. Check new items with `p2z.py lint <their keys>`: a `citation_key` finding with `problem: tex_special` carries the suggestion that `create` alone would print as `citation_key_hint`. Ask the user before setting it with `p2z.py update <key> --set citationKey=<suggested>`. If a result has files missing from the record's `attach`, run `p2z.py attach <record>` alone for their names and hints, including `unchecked` files mixed with attached ones; handle those by no-doi-record.md.

Then the structured packages of the PDFs this run attached, which the paddleocr skill parses (SKILL.md, *Sibling skills*): `p2z.py package take <their items' keys> --missing -o <imp>/structured/ | ocr.py parse -o <imp>/structured/ -` in the background, then `p2z.py package put <imp>/structured/*/`. Their findings stay open: a paper is settled when a task first reads it. A PDF left without its package (no GPU, a failed parse) is archived all the same: name it in the report, and the next reader makes it.

Done when every record's item is in the library (`saved.key`, or `found` confirmed), every file the result passed is in the record's `attach`, and every PDF attached has its package or is named in the report as without one.

## 6. Read back and report

```bash
p2z.py report <imp>/records/*.json
```

The report reads every item from the library as it is now and prints the table, with each item's attachment titles, and the sections that apply (`p2z.py report -h` lists them); attachments to clean wait for the user's word before `p2z.py trash`, suggested renames before `p2z.py update`. Add to it:
- `zotero://select/library/items/<key>` links, and the collection path (in `tmp`: ask the user to file it later);
- items the library holds more than once (a handoff's candidates carrying the paper's identifier, `matched_by`): suggest merging them (organize.md, *Duplicate items*), which waits for the user's word;
- substitutions — an item built through the recognizer, fields left empty for lack of a source, fields `checks` said would be mapped or moved to Extra, fields set against a source other than the DOI record, with that source named;
- paper-fetch's part (its *Report*): the gates hit, the hosts left alone, the sources a 429 stopped, and the residue in one line;
- **skill notes** — anything either skill lacked, got wrong or made you work around, for the user to decide whether to change it.

Done when the report is in the conversation: every paper's row read from the library, every section that applies, and the additions above.

## 7. Clear residue

paper-fetch's *Residue* first: stop the watcher, close the sessions it names, and sweep Downloads — `pf.py downloads <imp>/fetch | jq -r .source | p2z.py have -` lists what this run left there and says which the library holds; delete those this run downloaded and the library holds, and name the rest in the report (a file the user downloaded for themselves is theirs). Then delete `<imp>`: Zotero holds its own copy of every attached file. Delete only what this run created, and a file only after its `attach`: a file that did not reach Zotero is a deliverable, handed over with its path. Every exit path ends here; a wait for the user is a pause, not an exit — a record with a `blocker` keeps the tab, the session and `<imp>` until the run resumes or the user drops it.

Done when Downloads holds no file of this run, `<imp>` is gone, every paper-fetch session's close has answered "tab lease released", and anything you could not remove is named in the report with its location.
