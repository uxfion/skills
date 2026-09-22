---
name: paper-to-zotero
description: Imports one paper into Zotero as an item with its PDF attached, filed in a collection and tagged, starting from a title, keywords, DOI, arXiv id, or URL; on request, organizes the existing library's tags and collections. Use when the user wants a paper added to Zotero (把论文/文献导入 Zotero) — also when they do not mention the PDF — or wants their Zotero tags/collections tidied (整理 Zotero 标签/分类). A .bib/.ris file the user already has goes through the zotero skill instead.
---

# Paper to Zotero

From what the user gives — a title, keywords, a DOI, an arXiv id, a URL — to one Zotero item with its PDF attached, filed in a collection, tagged, and nothing left behind. One paper at a time; a list is the steps once per paper. Script paths below are relative to this file's directory: `cd` there at the start of every shell call rather than trusting the current directory.

A request to add a paper is the authorization to write to the library, however politely it is phrased. A question about what is possible gets an answer, not a write. Writes go through Zotero's local API with a key stored outside the repo; step 0 obtains it when it is missing.

## Instruments

- `zotero` skill — the library side: `status`, `collections` (keys and parents, for choosing a collection), `tags` (the existing vocabulary). Its docs say `python3 <plugin-root>/…`; run its helper as `uv run <zotero skill dir>/scripts/zotero.py collections`. Starting Zotero and enabling its local API is the user's job: skip that skill's `enable --restart`, which cannot reach Zotero here and kills every process whose command line contains "zotero", including these scripts.
- `opencli-usage` skill — the web side: discover adapters at run time (`opencli list -f json` is large; filter it). Adapters seen in 2026-09: API-type `arxiv`, `openalex`, `semanticscholar` (answers 429 without an API key — one 429 means skip it), `pubmed` (abstract, author keywords, PMID for journal articles), `dblp`, `openreview`, `hf paper`; browser-type `google-scholar` (the user's habitual search), `cnki`, `wanfang`. Behind a proxy every `opencli` call prints a harmless `UNDICI-EHPA` warning on stderr; send stderr to `/dev/null`.
- `opencli-browser` skill — the user's real, logged-in Chrome: `browser <session> open / state / click / wait / close`, `web read --url`.
- `pdf` skill — reading a PDF's first page when `check_pdf.py` finds no text layer.
- `papers-cool-search` skill (optional) — papers.cool search, category and venue listings as JSON, for step 1.

Read [references/publishers.md](references/publishers.md) before the first visit to a publisher site, and [references/tagging.md](references/tagging.md) before choosing tags.

## Steps

### 0. Ready

Zotero is running and answers on the local API; the write key exists:

```bash
uv run scripts/authorize_local_api.py
```

A missing key makes Zotero show an authorization dialog: tell the user first, ask them to click **Always Allow**, then run it. Create the work directory — `<scratchpad>/paper-to-zotero/` when the harness gives you a scratchpad, else `${TMPDIR:-/tmp}/paper-to-zotero/` — and use the browser session name `p2z`. Every temporary file of the run (saved tag lists, `web read` output, downloads) goes in there and leaves with it. Leftovers from an earlier run are reported, not deleted — a PDF that never reached Zotero belongs to the user.

Done when the script reports `ok` and the work directory exists.

### 1. Pin the paper

Treat the user's words as a draft: typos, partial titles and loose keywords are normal, so reformulate and search again before concluding anything. Search along the ladder in *Reaching a page* below: metadata APIs and API-type adapters first, `google-scholar` and other browser-type adapters next, `opencli browser` last.

A journal or conference title is usually pinned in one Crossref call:

```bash
curl -s "https://api.crossref.org/works?query.bibliographic=<title words>&rows=3&select=DOI,title,container-title,issued,author"
```

For an arXiv-style title, `papers.cool` is a fast first stop. With the `papers-cool-search` skill installed, its helper returns JSON and keeps to the site's polite budget:

```bash
uv run <papers-cool-search dir>/scripts/papers_cool_fetch.py search "<3-6 title words>" --show 5   # --branch arxiv|venue
```

Without it, `curl` the same routes: `https://papers.cool/arxiv/search?query=…&show=5` (arXiv papers with id, date, abstract) and `https://papers.cool/venue/search?query=…` (accepted papers of the major ML conferences from about 2021 on — CVPR, ICLR, NeurIPS, MICCAI 2024–25 — whose `Subject` line gives `VENUE.YEAR - track`). Search has no title weighting, so confirm the title yourself; the site carries no DOI and does not index author names; an older paper or a journal article is confirmed elsewhere.

Several plausible candidates, or none you would stake the library on: show the top few (title, authors, year, venue) and let the user choose. Prefer the published version unless the user asked for the preprint.

Done when one paper is pinned by a DOI or arXiv id (failing both, its landing-page URL), every distinguishing word of the request matches it, and no other result fits equally well.

### 2. Library and destination

```bash
uv run scripts/find_in_library.py --doi 10.1109/CVPR.2016.90   # or --arxiv 2006.11239 / --title "…"
```

`found` with an attachment: report the key and stop (the user may still ask for re-filing or tags). `found` without a PDF attachment: continue from step 4 and attach to that key. A preprint/published pair counts as found — ask the user. `not_found` with `hits > 0` under `qmode: everything` means other items merely mention those words in their full text or references — not a match.

Destination: the user named a collection → pick its key from `zotero collections` (ambiguous or missing → list candidate paths and ask). No collection named → suggest one from the paper's topic and ask, in the same message as any candidate question. No suggestion possible, or nobody to ask → the collection `tmp` (create it once through the local API if absent) and say so in the report.

Done when the paper is absent (or the existing key is known) and the destination is one collection key.

### 3. Draft the item and its tags

```bash
uv run scripts/doi_to_item.py --doi 10.1109/CVPR.2016.90 --out item.json
uv run scripts/check_item.py --item item.json
```

Revise the draft: the item type (LNCS/MICCAI/ECCV chapters arrive as `bookSection` and are usually `conferencePaper`; a NeurIPS/ICLR paper drafted from its arXiv DOI takes the venue fields from its landing page, with the arXiv id in `extra`); the abstract, from `openalex work` / `pubmed search` + `pubmed article <pmid> --full-abstract` (journal articles) / `semanticscholar paper` / `hf paper` before opening the article page; fields that only the article page has. A value without a source stays out; a PMID from PubMed goes into `extra` as `PMID: <n>`.

Tags go in `tags.json` as `[{"tag": …, "type": 0|1}]`: the source's own keywords — the **author keywords** from the article page, PubMed or OpenAlex, and arXiv categories from `arxiv paper`; not MeSH terms, not IEEE index terms — as type 1, your curated tags per [references/tagging.md](references/tagging.md) as type 0, chosen against the existing vocabulary from `zotero tags`.

No DOI record at all (`no_csl_record`, old papers, pages that ignore content negotiation): see *No DOI record* under Rules.

Done when `check_item.py` reports `ok` (or every item it flags is an accepted mapping), the abstract is filled or confirmed absent, and `tags.json` is written.

### 4. Get the PDF

Open repositories — sites that hand a plain HTTP client the PDF (arXiv, CVF Open Access, OpenReview, PMLR) — are downloaded directly into the work directory. A download that is not a PDF means the site is not open; take the publisher route.

Publisher sites are real navigation in the user's Chrome, in a foreground window:

```bash
opencli browser p2z open "https://doi.org/10.1109/CVPR.2016.90" --window foreground
# … reach the article page, click its PDF button …
opencli browser p2z wait download Residual --timeout 120000     # a substring of the expected filename or URL
```

`wait download` returns the new file's Windows path; convert it with `wslpath` and move the file into the work directory. A viewer page instead of a download: navigate to the embedded PDF's URL. A login, CAPTCHA or other obstacle: the gate rule below. An article page that shows the institution's logo *and* a banner "<institution> does not subscribe to this content" (ScienceDirect; URL rewritten to `/abs/`, only "Purchase PDF" offered) is not a gate but a missing subscription: do not click purchase; take the no-PDF branch below.

```bash
uv run scripts/check_pdf.py --item item.json --pdf work/paper.pdf
```

`title_not_found` or `no_text_layer`: read the excerpt (or the first page with the `pdf` skill) and decide yourself; say in the report that you did.

Done when a PDF of this paper is in the work directory. No PDF even after the gate — the page offers purchase and no institutional access (no "Access provided by", the sign-in entry leads nowhere new): stop there; a legitimate open copy exists (arXiv, the OpenAlex open-access URL) → attach it and say so; none → **still save the item**, and attach a snapshot of the article page instead, as the Zotero connector would: save the loaded page from the browser (`opencli browser p2z eval "document.documentElement.outerHTML"` into `work/page.html`) and attach it with `attach_file.py --file work/page.html --url <canonical page>` — Zotero indexes its text, so the abstract and keywords become searchable. Say in the report that the PDF is missing because the institution has no access; the user adds the file later with `attach_file.py --key`. Never try to get around the paywall.

### 5. Save, file, tag, attach

```bash
uv run scripts/create_item.py --item item.json --collection <collection key> --tags-file tags.json --out saved.json
uv run scripts/attach_file.py --key <item_key from saved.json> --file work/paper.pdf --url "https://ieeexplore.ieee.org/document/…"
```

`--url` is the canonical page the file came from (fall back to `https://doi.org/<DOI>`), never a proxy hostname. `create_item.py` failing creates nothing: fix `item.json` and rerun — except `post_incomplete` (the connection broke mid-request): check with `find_in_library.py` before creating again. `readback_mismatch` means the item exists but a tag or the collection did not stick: `file_and_tag.py --key` sets it right. `attach_file.py` failing after the item exists: rerun it with the same key — it reuses a half-made attachment and never duplicates a file — and if it still fails, hand the PDF to the user with its path.

Done when `create_item.py` reports `filed: true` and `tags_ok: true`, and `attach_file.py` reports `md5_ok: true` for the PDF — or for the page snapshot when there is no PDF.

### 6. Clear residue

Delete the work directory (Zotero holds its own copy of the PDF or snapshot), close the `p2z` session, and check that the Downloads folder holds nothing this run produced. Delete only what this run created, and the PDF only after `md5_ok: true`. Every exit path ends here.

Done when the work directory is gone, `opencli browser p2z close` has answered "tab lease released" (there is no session listing to check), the Downloads folder has no file from the last half hour that this run produced (`find <Downloads> -maxdepth 1 -mmin -30`, plus no `.crdownload`), and anything you could not remove is named in the report with its location.

### 7. Report

Title, authors, year, venue; `item_key`, attachment key, `zotero://select/library/items/<key>`; the collection path (in `tmp`: ask the user to file it later); tags — source keywords kept, curated tags added, which of them are new to the library; substitutions (preprint PDF, a PDF accepted on your own reading, an item built through the recognizer fallback, fields left empty for lack of a source, fields `check_item.py` said would be mapped or moved to Extra); residue in one line; publisher notes worth adding to `references/publishers.md`, for the user to decide.

## Rules

### Reaching a page

Fall back instead of stopping: a blocked request, a verification page or an empty result is a reason to take the next rung, never to give up.

1. Direct access — metadata APIs (doi.org, Crossref, OpenAlex, arXiv), web fetch.
2. OpenCLI adapters, discovered at run time. An API-type adapter (`browser: false`) is still a direct request and fails the same way when blocked; when it does, `opencli web read --url …` reads the page inside the user's Chrome with their cookies, and `opencli browser` lets you work the page yourself.
3. A browser-type adapter (`browser: true`) that fails was already in the real browser, so it was most likely blocked: reopen the same page with `opencli browser … --window foreground` — a verification or login page is a gate; a normal page means the adapter broke, so read it yourself.

Retry a transient error once; a 403 or a verification page goes straight to the next rung. Publisher hosts and Google Scholar start at rung 2. Files a tool writes on the way (`web read` output) go into the work directory and leave with it.

### Gate

A gate is anything the user can pass and you cannot: institutional login, CAPTCHA ("Are you a robot?", "verify you are human"), an authorization prompt, a purchase page whose institutional sign-in you have already clicked, Chrome or the OpenCLI extension not running, a Save As dialog, Zotero's authorization dialog. The user is present and can help — use that. Recognise a gate by its markers, not by waiting to see what happens: page title "请稍候…" / "Just a moment…" / "Are you a robot?", `input[name=cf-turnstile-response]`, `#captcha-box`, a login form, "Get access". Read `state` (URL and title) after **every** navigation or click on a publisher site, because a gate is an unexpected page, not an error. The moment a marker shows, alert first — before any further `wait`, `state` or "let me check again", even when the widget says it has verified and is waiting — then watch it; it may pass by itself, and the alert cost nothing. Record every gate you hit (page, time, what you were doing) for the report.

Wait at the gate: keep the tab open in a foreground window and **alert the user** — a push notification when the harness has one (load it if it is deferred), and when you are a subagent a `SendMessage` to the main conversation with the same one line, because only the main conversation reaches the user's screen; the alert is never skipped for lack of a tool — saying which page is waiting and what to do; a line in your own output is not seen by someone looking at the browser. *Then* wait up to 5 minutes:

```bash
opencli browser p2z wait text "Access provided by" --timeout 300000   # any text or selector that only the passed gate shows
```

When no such marker exists, poll `opencli browser p2z state` every 15 seconds inside one long shell call. Passed: continue where you stopped. Not passed after 5 minutes: keep the tab, report which page is waiting, and ask the user to say "继续" — which resumes at the step you left, not from step 0. Login state lives in the user's Chrome, so a tab that closes meanwhile still opens logged in; the gate only returns when the user was away or their session expired.

### No DOI record

`doi_to_item.py` reports `no_csl_record`, or the paper has no identifier, but the PDF is in hand: let Zotero's recognizer identify it. Note the library version (`Last-Modified-Version` of `GET /api/users/0/items?limit=1`), send the PDF through the connector — one request, no key:

```bash
curl -s -X POST http://127.0.0.1:23119/connector/saveStandaloneAttachment \
  -H "Content-Type: application/pdf" -H "X-Metadata: {\"sessionID\":\"$(uuidgen)\",\"title\":\"paper.pdf\",\"url\":\"<source url>\"}" \
  --data-binary @work/paper.pdf
```

Within a minute a parent item appears (`GET /api/users/0/items?since=<version>`); revise it and finish with `file_and_tag.py` (it landed in whatever collection Zotero had selected). No parent after a minute: move the standalone attachment to the trash (`PATCH … {"deleted": 1}`) and write `item.json` by hand (`check_item.py --help` prints a skeleton), then steps 5–7 as usual.

### Residue

Residue is the work directory, the `p2z` session, and anything in Downloads this run produced. Success removes all of it. A PDF that did not reach Zotero is a deliverable — hand it over with its path. Changes to existing items (organizing, tag removal) are shown to the user as a list first and written after confirmation.

## Several papers

Pin all of them first and ask every question in one message (candidates, destinations), then run steps 2–7 per paper. One paper failing — no PDF, a save error — does not stop the others; a gate that times out does, because the next paper would hit the same page. Report as a table plus the per-paper details that matter.

## Organize

The second entry: the user asks for their tags or collections to be tidied. Read the items (local API `GET /api/users/0/items/top` or the `zotero` skill), take one collection at a time, and draft per item what [references/tagging.md](references/tagging.md) prescribes — source keywords to keep, curated tags to add, tags proposed for removal, a collection change if any. The `tags` list in a change is the item's *complete* target set: include the source keywords you are keeping, or the script will remove them. Write the batch to `changes.json` and show the change list:

```bash
uv run scripts/file_and_tag.py --batch changes.json --dry-run
```

Only after the user confirms, run it without `--dry-run`. The first batch calibrates the scheme with the user; later batches follow it.

## Limits

- `attach_file.py` names the file itself (Zotero does not rename API uploads); the user can "Rename File from Parent Metadata" in Zotero at any time.
- Zotero's PDF recognizer runs only for files sent through the connector, never for local-API uploads.
- Collections are not created, except `tmp`.
