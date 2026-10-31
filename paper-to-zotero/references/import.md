# Importing papers

From what the user gives to Zotero items with their PDFs, filed and tagged, and nothing left behind. The paper-fetch skill identifies each paper and gets its files; this skill chooses the version, drafts the item, saves and attaches, and reports. Two or more papers — a list, a .bib, search results — read [batch.md](batch.md) before step 0.

**The directory** is `<scratch>/paper-to-zotero/` (SKILL.md, *The scratch directory*), below as `<imp>`. In it, `<imp>/fetch/` is paper-fetch's directory for this import — a result file per paper, `fetch/results/<slug>.json`, with its files beside it — and `<imp>/records/` holds this skill's record per paper, under the same slug. A record points at its result (`fetched`) and holds the item to create and what you decided about it (`scripts/p2zlib/run.py` documents both); you change the record, never the result. The slug is the citation key the user brought — the item will carry it — else `<surname><year><first title word>`.

## 0. Ready

Read `../paper-fetch/SKILL.md` now (no such file → stop, as SKILL.md's *Sibling skills* says): this file names its sections, and its scripts run as `uv run ../paper-fetch/scripts/pf.py <command>`.

```bash
uv run scripts/p2z.py ready --dir <imp>
uv run ../paper-fetch/scripts/pf.py ready --dir <imp>/fetch
uv run ../paper-fetch/scripts/pf.py claim --dir <imp>/fetch --watch      # in the background, the whole run
```

Act on what this skill's `ready` reports:
- `no_key`: tell the user first that Zotero will show an authorization dialog and ask them to click **Always Allow**, then run again with `--authorize`.
- `config.moved`: settings paper-fetch now reads from its own config: once the user has used the new version, remind them these can be removed — on their word.
- `leftovers`: an earlier run of this task left `<imp>`: carry on from its records and results, and delete nothing in it unasked, since a PDF that never reached Zotero belongs to the user. `old_format` records are redone by `prepare` (step 3).

paper-fetch's `ready` and its watcher: as its *Ready* says.

Done when both `ready`s report `ok` and the watcher runs.

## 1. Identify the papers

paper-fetch's *Identify a paper*, writing into `<imp>/fetch`:

```bash
uv run ../paper-fetch/scripts/pf.py identify <DOI | arXiv id | paper page> [--slug <citation key>] -o <imp>/fetch
uv run scripts/p2z.py read_bib refs.bib | uv run ../paper-fetch/scripts/pf.py identify -o <imp>/fetch
```

A .bib or .ris is a list source, never a file to import as it is. `read_bib` reads a .bib into one `<DOI, else arXiv id><TAB><citation key>` line per entry (a .ris you list in the same form yourself); an entry with neither comes out as `title:…`, which `identify` answers with `needs_pinning` — find its DOI or arXiv id as *Identify a paper* says, then identify it with its key.

Done when every paper has a result with metadata, or is a stub — a DOI without a CSL record, a page that refused — which goes to [no-doi-record.md](no-doi-record.md) once its PDF is in hand.

## 2. Choose the version

The rule is this skill's: **the published version comes first**, unless the user asked for the preprint. It is chosen now, before any record is drafted, so the item is drafted once. A conference paper later extended into a journal article is two papers, two items: the version chosen is this paper's. Confirming a candidate from a preprint's `versions.published` and redrafting the result to it is paper-fetch's *Identify a paper* (`pf.py identify --redraft <DOI | paper page> <result>`); the preprint stays in the result's `versions.preprint`, and drafting takes from it what the published record lacks. No published version, or the user wants the preprint → the preprint it is, and its record gets `keep_preprint` with the reason in step 3.

Done when every preprint result is redrafted or has its reason to stay.

## 3. Draft the record

```bash
uv run scripts/p2z.py draft_item <imp>/fetch/results/*.json
uv run scripts/p2z.py prepare <imp>/records/*.json
```

`draft_item` makes each record and its `item` from the result's metadata, by Zotero's own CSL tables and the few rules its `--help` lists. `prepare` fills in what the library has (`found`, `near_matches`) and what Zotero will do with the fields (`checks`), skipping a block that is up to date, so run it again after every change. Its line per record lists under `decide` what is still open; the paragraphs below say who settles each. You change only your fields (`item`, `tags`, `collection`, `citationKey`, `same_as`, `distinct_from`, `keep_preprint`, `accepted`, `blocker`), and `p2z.py answer` writes `same_as` and `distinct_from` for a judge; the blocks are the scripts'.

**What the library already has** (`found`). With a PDF of the paper, of any version (`found.attachments[].version`: `published`, `accepted`, `preprint`, or `unknown` — a title outside the scheme, its version not checked: say so in your answer): report the citation key and stop — unless the request asks for something the item lacks (the published version when only a preprint or accepted manuscript is attached, a tidy, a note), which continues at the step that provides it; look at an `unknown` file only when the request names a version. With no attachment, or only a snapshot or a linked URL: continue from step 4 and attach to that item; a snapshot a new PDF replaces goes into the report's attachments to clean.

**Library candidates** (`same_paper`). Only a DOI or an arXiv id confirms an item; every item a quick search for the title finds is a candidate. The open ones wait in a handoff file, `<imp>/handoffs/<slug>.<n>.json`, with the evidence of both sides — title, year, first author, DOI, arXiv id, item type, venue, attachment titles, title similarity — and go to judges (SKILL.md, *Handoffs*), reading the handoff files alone. The brief, per candidate of each handoff: `same` (this paper, in another item), `distinct` (another paper — a journal extension of a conference paper is another paper), `pair` (this paper's preprint or published version, as its own item) or `unknown` (the evidence leaves it open), recorded with `uv run scripts/p2z.py answer <handoff> <answer> [--key K] --reason "<what on both sides says so>" --by judge` (`distinct` without `--key` settles every candidate still open); the judge reports one line per handoff. Then `prepare` again. A `pair` or `unknown` waits on the user (`waiting_on: user`): it goes into the run's one message of questions with both items' evidence, and the user's word is recorded the same way, `--by user`.

**Several items with the paper's DOI** (`duplicates`): the library holds the paper twice. Write the key of the one to keep — the fuller one — in `same_as`: the files go to that item, and until then to neither. Suggest merging the two (organize.md, *Duplicate items*), which waits for the user's word.

**`published_versions`**: the item is still the preprint while its result lists published versions — step 2's choice, unmade. Made after drafting: `identify --redraft`, then `draft_item --redraft <result>` drafts the item again and keeps your other fields; or write `keep_preprint`.

**Checks and warnings** (`checks`, `warnings`): what Zotero will do with a field (`mapped:publicationTitle`: stored as `proceedingsTitle`; `missing_minimum:date`) and what drafting noticed. Revise the item, or accept the effect: copy the flag or the warning, as `prepare` printed it, into the record's `accepted`.

**`unanswered`**: sources that did not answer; run `prepare` again later (for versions, `pf.py identify` the paper again).

**Revise `item`.** A value without a source stays out.
- Item type: a `bookSection` from a proceedings volume is usually a `conferencePaper` (paper-fetch already makes LNCS-style chapters conference papers when Crossref names the series). The result's `warnings` naming a possible erratum or correction notice: make sure the DOI is the paper's own.
- Abstract and PMID: identify filled them from Europe PMC and OpenAlex where the DOI record had none (the result's warnings say from which, and when the two differ: then read both and keep the paper's). Still empty: the article page, else the abstract stays empty.
- Identifier: the item describes the version of record — never where a copy can be downloaded (the file is the attachment, and copies are found again from the DOI):
  - Published with a DOI (IEEE for CVPR/ICCV, Springer for ECCV/MICCAI, ACL's own): that `DOI`, and `url` `https://doi.org/<DOI>`. NeurIPS 2022–2025 (`10.52202`, the printed proceedings' DOI, which leads to their sales page): the `DOI` too, and `url` the paper's NeurIPS page.
  - Published without a DOI (NeurIPS up to 2021, ICML/PMLR, ICLR and TMLR on OpenReview): `url` the venue's own page for the paper — for OpenReview the forum page, not the PDF.
  - Only a preprint: item type `preprint`, `repository` the server, the server's DOI (`10.48550/arXiv.<id>` for arXiv) and its abstract page as `url`, `archiveID` `arXiv:<id>`. Only on OpenReview (rejected, a workshop): the arXiv version if there is one, else a preprint with `repository` OpenReview.
  - Other versions only as identifiers in `extra`: `arXiv: <id>` whenever an arXiv version exists.
- Tags (`[{"tag", "type"}]`): your curated tags, chosen per [tagging.md](tagging.md), as type 0, beside any automatic ones `draft_item` added.

**Destination.** The user named a collection → its key from the tree `ready` printed (ambiguous or missing → list candidate paths and ask); several are fine. No collection named → suggest one from the paper's topic and ask, in the same message as any candidate question. No suggestion possible, or nobody to ask → the collection `tmp` (`p2z.py make_collection --name tmp` once if absent) and say so in the report. Put the key (or keys) in the record's `collection`.

Done when `prepare` has run on the final records and lists nothing under `decide` but candidates waiting on the user, who has them in the run's one message, and `unanswered` sources asked again; the abstract is filled or confirmed absent, `tags` is written, and every record has a `collection`.

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

Run it after every pass of step 4: it skips what is done, and `no_file_yet` is not a failure. `create_item` looks the paper up once more before it posts and creates nothing for a paper the library holds; `attach_file` attaches every file the result's check let through — every version of the paper and any supplement, each under its label — to the item. On its lines:
- `possible_duplicate`: an item came into the library since `prepare`; its handoff goes to judges as in step 3.
- `readback_mismatch` from `create_item`: the item exists but a tag or a collection did not stick; `p2z.py file_and_tag --cite …` sets it right.
- `citation_key_hint`: the key holds a character TeX treats specially (`^`, `_`, `&` …), so `\cite{}` would break on it; ask the user, then `p2z.py update_item --key <key> --set citationKey=<suggested>`.
- `unsettled` or `file_changed`: `pf.py settle --dir <imp>/fetch`, then `save` again.
- `unchecked` (or `unchecked` names on an `ok` line): a stub's PDF, which paper-fetch had nothing to check against; [no-doi-record.md](no-doi-record.md) identifies the paper from it.
- `unconfirmed` names: files attached although their agent could not tell they are the paper's; the report lists them for the user.
- `suggested_title`: a file the item had already keeps its own title; the report suggests the rename, which waits for the user.
- Any other failure creates nothing: fix the record as its hint says and rerun — a rerun is always safe, a run cut off mid-POST included. A file that still cannot be attached goes to the user with its path.

Then the structured packages of the PDFs this run attached, which the paddleocr skill parses (SKILL.md, *Sibling skills*): `uv run scripts/p2z.py structured take --key <their items' keys> --missing -o <imp>/structured`, one parse of the links it printed with the paddleocr skill (`-o <imp>/structured`, in the background), then `structured put <imp>/structured/*/`. Their findings stay open: a paper is settled when a task first reads it. A PDF left without its package (no GPU, a failed parse) is archived all the same: name it in the report, and the next reader makes it.

Done when every record's item is in the library (`saved.key`, or `found` confirmed), every file the result passed is in the record's `attach`, and every PDF attached has its package or is named in the report as without one.

## 6. Read back and report

```bash
uv run scripts/p2z.py report <imp>/records/*.json
```

The report reads every item from the library as it is now and prints the table, with each item's attachment titles, and the sections that apply (`report --help` lists them); attachments to clean wait for the user's word before `trash_item`, suggested renames before `update_item`. Add to it:
- `zotero://select/library/items/<key>` links, and the collection path (in `tmp`: ask the user to file it later);
- substitutions — an item built through the recognizer, fields left empty for lack of a source, fields `checks` said would be mapped or moved to Extra, fields set against a source other than the DOI record, with that source named;
- paper-fetch's part (its *Report*): the gates hit, the hosts left alone, the sources a 429 stopped, and the residue in one line;
- **skill notes** — anything either skill lacked, got wrong or made you work around, for the user to decide whether to change it.

Done when the report is in the conversation: every paper's row read from the library, every section that applies, and the additions above.

## 7. Clear residue

paper-fetch's *Residue* first: stop the watcher, close its sessions (`pf` and every `pf-<slug>`), and sweep Downloads — `pf.py claim --dir <imp>/fetch --sweep` lists what this run left there, `p2z.py find_in_library --file <those files>` says which the library holds; delete those this run downloaded and the library holds, and name the rest in the report (a file the user downloaded for themselves is theirs). Then delete `<imp>`: Zotero holds its own copy of every attached file. Delete only what this run created, and a file only after its `attach`: a file that did not reach Zotero is a deliverable, handed over with its path. Every exit path ends here; a wait for the user is a pause, not an exit — a record with a `blocker` keeps the tab, the session and `<imp>` until the run resumes or the user drops it.

Done when Downloads holds no file of this run, `<imp>` is gone, every paper-fetch session's close has answered "tab lease released", and anything you could not remove is named in the report with its location.
