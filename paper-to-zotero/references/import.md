# Importing papers

From what the user gives to Zotero items with their PDFs, filed and tagged, and nothing left behind. The paper-fetch skill identifies each paper and gets its file; this skill chooses the version, drafts the item, saves and attaches, and reports. Two or more papers — a list, a .bib, search results — read [batch.md](batch.md) before step 0.

**The directory** is `<scratch>/paper-to-zotero/` (SKILL.md, *The scratch directory*), below as `<imp>`. In it, `<imp>/fetch/` is paper-fetch's directory for this import — a result file per paper, `fetch/results/<slug>.json`, with its file beside it — and `<imp>/records/` holds this skill's record per paper, under the same slug. A record points at its result (`fetched`) and holds the item to create and what you decided about it (`scripts/p2zlib/run.py` documents both); you change the record, never the result. The slug is the citation key the user brought, else `<surname><year><first title word>`.

## 0. Ready

Read `../paper-fetch/SKILL.md` now (SKILL.md, *Sibling skills*: no such file → stop): this file names its sections, and its scripts run as `uv run ../paper-fetch/scripts/pf.py <command>`.

```bash
uv run scripts/p2z.py ready --dir <imp>
uv run ../paper-fetch/scripts/pf.py ready --dir <imp>/fetch
uv run ../paper-fetch/scripts/pf.py claim --dir <imp>/fetch --watch      # in the background, the whole run
```

This skill's `ready` checks Zotero and the write key, makes `<imp>/records/` and prints the collection tree. Act on what it reports:
- `no_key`: Zotero will show an authorization dialog — tell the user first, ask them to click **Always Allow**, then run again with `--authorize`.
- `config.moved`: settings an older version kept in this skill's config, which paper-fetch reads from its own now: remind the user, once they have used the new version, that they can be removed — on their word.
- `leftovers`: an earlier run of this task left `<imp>` — carry on from its records and results; nothing in it is deleted unasked, since a PDF that never reached Zotero belongs to the user. `old_format`: records an older version wrote; `prepare` (step 3) recomputes their blocks.

paper-fetch's `ready` and its watcher: as its *Ready* says.

Done when both `ready`s report `ok` and the watcher runs.

## 1. Identify the papers

paper-fetch's *Identify a paper*, writing into `<imp>/fetch`:

```bash
uv run ../paper-fetch/scripts/pf.py identify <DOI | arXiv id | paper page> [--slug <citation key>] -o <imp>/fetch
uv run scripts/p2z.py read_bib refs.bib | uv run ../paper-fetch/scripts/pf.py identify -o <imp>/fetch
```

A citation key the user brought is the slug: the item will carry it. A .bib or .ris is a list source, never a file to import as it is: `read_bib` gives each entry's DOI (else arXiv id) with its key; an entry with neither comes out as `title:…`, which `identify` answers with `needs_pinning` — find its DOI or arXiv id as *Identify a paper* says, then identify it with its key.

Done when every paper has a result with metadata (a stub — a DOI without a CSL record, a page that refused — goes to [no-doi-record.md](no-doi-record.md) once its PDF is in hand).

## 2. Choose the version

The rule is this skill's: **the published version comes first**, unless the user asked for the preprint, and it is chosen now, before any record is drafted, so the item is drafted once. A conference paper later extended into a journal article is two papers, two items: the version chosen is this paper's. Confirming a candidate from a preprint's `versions.published` and redrafting the result to it is paper-fetch's *Identify a paper* (`pf.py identify --redraft <DOI | paper page> <result>`); the preprint stays in the result's `versions.preprint`, and step 3 takes from it what the published record lacks. No published version, or the user wants the preprint → the preprint it is, and its record gets `keep_preprint` with the reason in step 3.

Done when every preprint result is redrafted or has its reason to stay.

## 3. Draft the record

```bash
uv run scripts/p2z.py draft_item <imp>/fetch/results/*.json
uv run scripts/p2z.py prepare <imp>/records/*.json
```

`draft_item` makes each record and its `item` from the result's metadata, by Zotero's own CSL tables and the few rules its `--help` lists (a preprint keeps its arXiv identity; a published version gains the preprint's abstract and authors where its record has none, and `arXiv: <id>` in `extra`; with automatic tags on, the source's own keywords become automatic tags: tagging.md). `prepare` fills what the library has (`found`, `near_matches`) and what Zotero will do with the fields (`checks`); a block that is up to date is skipped, so run it again after every change. Its line per record lists under `decide` what is still open and who settles it — the paragraphs below. You change only your fields (`item`, `tags`, `collection`, `citationKey`, `same_as`, `distinct_from`, `keep_preprint`, `accepted`, `blocker`); the blocks are the scripts', and `p2z.py answer` writes `same_as` and `distinct_from` for a judge.

**What the library already has** (`found`). With a PDF of the paper, of any version (`found.attachments[].version`: `published`, `accepted`, `preprint`, or `unknown` — a title outside the scheme, its version not checked: say so in your answer): report the citation key and stop — unless the request asks for something the item lacks (the published version when only a preprint or accepted manuscript is attached, a tidy, a note), which continues at the step that provides it; look at an `unknown` file only when the request names a version. With no attachment, or only a snapshot or a linked URL: continue from step 4 and attach to that item; a snapshot a new PDF replaces goes into the report's attachments to clean.

**Library candidates** (`same_paper`). Only a DOI or an arXiv id confirms an item. Every item a quick search for the title finds is a candidate, and the open ones wait in a handoff file, `<imp>/handoffs/<slug>.<n>.json`, with the evidence of both sides: title, year, first author, DOI, arXiv id, item type, venue, attachment titles, title similarity. They go to **judges**: background subagents on a cheap model (Claude Code `model: "sonnet"`), about 20 handoffs each, at most 5 at once, reading the files alone. The brief, per candidate of each handoff: `same` (this paper, in another item), `distinct` (another paper — a journal extension of a conference paper is another paper), `pair` (this paper's preprint or published version, as its own item) or `unknown` (the evidence leaves it open), recorded with `uv run scripts/p2z.py answer <handoff> <answer> [--key K] --reason "<what on both sides says so>" --by judge` (`distinct` without `--key` settles every candidate still open); it reports one line per handoff. Then `prepare` again. A `pair` or `unknown` waits on the user (`waiting_on: user`): it goes into the run's one message of questions with both items' evidence, and the user's word is recorded the same way, `--by user`.

**Several items with the paper's DOI** (`duplicates`): the library holds the paper twice. Write the key of the one to keep — the fuller one — in `same_as`, and suggest merging them (organize.md, *Duplicate items*), which waits for the user's word. Until then no file is attached to either.

**`published_versions`**: the item is still the preprint while its result lists published versions — step 2's choice, unmade. Made after drafting: `identify --redraft`, then `draft_item --redraft <result>` drafts the item again and keeps your other fields; or write `keep_preprint`.

**Checks and warnings** (`checks`, `warnings`): what Zotero will do with a field (`mapped:publicationTitle`: stored as `proceedingsTitle`; `missing_minimum:date`) and what drafting noticed. Revise the item, or accept the effect: copy the flag or the warning, as `prepare` printed it, into the record's `accepted`.

**Revise `item`.** A value without a source stays out.
- Item type: a `bookSection` from a proceedings volume is usually a `conferencePaper` (paper-fetch already makes LNCS-style chapters conference papers when Crossref names the series). The result's `warnings` naming a possible erratum or correction notice: make sure the DOI is the paper's own.
- Abstract and PMID: identify filled them from Europe PMC and OpenAlex where the DOI record had none (the result's warnings say from which, and when the two differ: then read both and keep the paper's). Still empty: the article page, else the abstract stays empty.
- Identifier: the item describes the version of record — never where a copy can be downloaded (the file is the attachment, and copies are found again from the DOI):
  - Published with a DOI (IEEE for CVPR/ICCV, Springer for ECCV/MICCAI, ACL's own): that `DOI`, and `url` `https://doi.org/<DOI>`. NeurIPS 2022–2025 (`10.52202`, the printed proceedings' DOI, which leads to their sales page): the `DOI` too, and `url` the paper's NeurIPS page.
  - Published without a DOI (NeurIPS up to 2021, ICML/PMLR, ICLR and TMLR on OpenReview): `url` the venue's own page for the paper — for OpenReview the forum page, not the PDF.
  - Only a preprint: item type `preprint`, `repository` the server, the server's DOI (`10.48550/arXiv.<id>` for arXiv) and its abstract page as `url`, `archiveID` `arXiv:<id>`. Only on OpenReview (rejected, a workshop): the arXiv version if there is one, else a preprint with `repository` OpenReview.
  - Other versions only as identifiers in `extra`: `arXiv: <id>` whenever an arXiv version exists.
- Tags (`[{"tag", "type"}]`): your curated tags per [tagging.md](tagging.md) as type 0, spelled like the existing tags from `p2z.py read_library tags`, beside any automatic ones `draft_item` added (only with automatic tags on). The authors' keywords (`csl.keyword`) and OpenAlex's (`enrichment.openalex_keywords`) are hints for choosing them.

**Destination.** The user named a collection → its key from the tree `ready` printed (ambiguous or missing → list candidate paths and ask); several are fine. No collection named → suggest one from the paper's topic and ask, in the same message as any candidate question. No suggestion possible, or nobody to ask → the collection `tmp` (`p2z.py make_collection --name tmp` once if absent) and say so in the report. Put the key (or keys) in the record's `collection`.

Done when `prepare` has run on the final records and lists nothing under `decide` but candidates waiting on the user, who has them in the run's one message; the abstract is filled or confirmed absent, `tags` is written, and every record has a `collection`.

## 4. Get the files

A record whose item the library already holds with a PDF of the paper needs no file. The results of the rest go to paper-fetch's *Get the file: the chain* — `fulltext_links`, then `fetch` pass by pass, every file through `claim` and labelled there:

```bash
uv run ../paper-fetch/scripts/pf.py fulltext_links <imp>/fetch/results/<slug>.json …
uv run ../paper-fetch/scripts/pf.py fetch --pass N <imp>/fetch/results/<slug>.json …
```

Between passes, step 5 saves what is in hand. Before paper-fetch's last pass, the user is told and the run waits: each record still without its file gets a `blocker` saying what it waits for ("last pass with the user: institutional login"), and the report goes out.

Done when paper-fetch's chain is done for every result handed to it, and `pf.py settle --dir <imp>/fetch` has folded the watcher's late arrivals into the results.

## 5. Save and attach

```bash
uv run scripts/p2z.py save <imp>/records/*.json     # create_item (item + collections + tags + citationKey), then attach_file
```

Run it after every pass of step 4: each step skips what is done (`saved`, an `attach` entry for this very file), and a record whose result has no file yet is `no_file_yet`, not a failure. `create_item` looks the paper up once more before it posts: `exists` (a DOI or arXiv hit) creates nothing, and the files go to that item (with `duplicates`, to the one in `same_as`); `possible_duplicate` (an item came into the library since `prepare`) names its handoff, which goes to a judge as in step 3. A failure creates nothing — fix the record and rerun; a run cut off mid-POST is safe to rerun too. `readback_mismatch`: the item exists but a tag or a collection did not stick; `p2z.py file_and_tag --cite …` sets it right. `citation_key_hint`: the key holds a character TeX treats specially (`^`, `_`, `&` …), so `\cite{}` would break on it; ask the user, then `p2z.py update_item --key <key> --set citationKey=<suggested>`.

`attach_file` attaches every file of the result whose check passed (`ok`, or `accepted` by a paper agent), every version of the paper and any supplement, each under its label (an unlabelled file came out of paper-fetch as `Unknown-<Source>`; a paper with no PDF anywhere gets its article page's snapshot, `Snapshot-<Source>`, and stays under 无法获取 in the report); a label settled later renames this run's attachment at the next `save`. An `unconfirmed` file (its agent could not tell it is the paper's) is attached all the same and named on the line; the report lists it for the user, and once paper-fetch withdraws it for a confirmed file, the report lists its attachment to clean. `unsettled`: the result was never folded — `pf.py settle --dir <imp>/fetch`, then `save` again; `file_changed`: the same. `library_has_pdf`: the item had a PDF of the paper and nothing was fetched for it. `unchecked` (or `unchecked` names on an `ok` line): a stub's files, which paper-fetch had nothing to check against — `references/no-doi-record.md` identifies the paper from the PDF. A file the item had already keeps its own title: the report suggests the rename, which waits for the user. The attachment's `url` is the item's canonical page (`item.url`, else `https://doi.org/<DOI>`). It reuses a half-made attachment and never duplicates a file; if it still fails, hand the file to the user with its path.

Then the structured packages of the PDFs this run attached, which the paddleocr skill parses (SKILL.md, *Sibling skills*): `uv run scripts/p2z.py structured take --key <their items' keys> --missing -o <imp>/structured`, one parse of the links it printed with the paddleocr skill (`-o <imp>/structured`, in the background), then `structured put <imp>/structured/*/`. Their findings stay open: a paper is settled when a task first reads it. A PDF left without its package (no GPU, a failed parse) is archived all the same: name it in the report, and the next reader makes it.

Done when every record's item is in the library (`saved.key`, or `found` confirmed), every file the result passed is in the record's `attach`, and every PDF attached has its package or is named in the report as without one.

## 6. Read back and report

```bash
uv run scripts/p2z.py report <imp>/records/*.json
```

The report reads every item from the library as it is now. It prints the table, with each item's attachment titles, and the sections that apply: 无法获取 (each result's outcome: what was tried, the last stop or answer), alternate versions, versions not settled, preprints kept and why, files a paper agent accepted, unconfirmed files, attachments to clean — the user confirms, then `trash_item` — suggested renames — the user confirms, then `update_item` — new tags. Add to it:
- `zotero://select/library/items/<key>` links, and the collection path (in `tmp`: ask the user to file it later);
- substitutions — an item built through the recognizer, fields left empty for lack of a source, fields `checks` said would be mapped or moved to Extra, fields set against a source other than the DOI record, with that source named;
- paper-fetch's part (its *Report*): the gates hit, the hosts left alone, the sources a 429 stopped, and the residue in one line;
- **skill notes** — anything either skill lacked, got wrong or made you work around, for the user to decide whether to change it.

Done when the report is in the conversation: every paper's row read from the library, every section that applies, and the additions above.

## 7. Clear residue

paper-fetch's *Residue* first: stop the watcher, close its sessions (`pf` and every `pf-<slug>`), and sweep Downloads — `pf.py claim --dir <imp>/fetch --sweep` lists what this run left there, `p2z.py find_in_library --file <those files>` says which the library holds; delete those this run downloaded and the library holds, and name the rest in the report (a file the user downloaded for themselves is theirs). Then delete `<imp>`: Zotero holds its own copy of every attached file. Delete only what this run created, and a file only after its `attach`: a file that did not reach Zotero is a deliverable, handed over with its path. Every exit path ends here; a wait for the user is a pause, not an exit — a record with a `blocker` keeps the tab, the session and `<imp>` until the run resumes or the user drops it.

Done when Downloads holds no file of this run, `<imp>` is gone, every paper-fetch session's close has answered "tab lease released", and anything you could not remove is named in the report with its location.
