# Altitude review: paper-to-zotero (2026-10-20)

Read-only subagent review at `c528750`, kept as written. Not verified line by line; the spec marks what the main session checked.

Read-only review. I edited nothing and did not contact Zotero. Findings are ordered by how much they matter to the restructure. "Visible" means the change would show in commands, output or docs.

### 1. fetch.py only looks for a PDF link in one meta tag, and each kind of page has its own code (Q1, the IEEE case)
- `fetch.py:99-100`: `INFO_JS` reads only `citation_pdf_url`. When it is missing, `page_route` stops with `no_pdf_link` (`:419-422`).
- The discovery route is a scraper for Primo, one vendor's discovery system:
  - `RESULTS_JS :121-123` (`a[href*="fulldisplay"]`);
  - `LINKS_JS :124-127` (`/^Get PDF/i`, `uresolver`);
  - `discovery_route :483-533`.
- `viewer_route :536-549` is the last rung of the same ladder, offered as a separate route.
- **Wrong depth:** one job — find this page's PDF links and get the bytes — is written three times, once per kind of page.
- **General change:** one `pdf_links(tab)` function that returns ranked candidates using signals any page can carry:
  - `citation_pdf_url`;
  - `link[rel=alternate][type=application/pdf]`;
  - the `src` of an `iframe`, `embed` or `object`, and a pdf.js viewer in any frame;
  - anchors whose text or aria-label says PDF ("PDF", "Download PDF", "View PDF", "Get PDF"), or whose path ends in `.pdf` or has a `/pdf/` segment — same site first, purchase/buy links left out.
- Each candidate goes down the existing ladder: in-page fetch → open it as a click would → download or read the viewer. If that lands on an HTML page, collect candidates there once more (depth 2).
- This is safe because every file still goes through `claim.py`. The check is the guard, not the selector.
- IEEE then falls out: the anchor `stamp.jsp` ("PDF") lands on an HTML viewer page, and the depth-2 pass finds the iframe `getPDF.jsp`.
- The same function also covers discovery's "Get PDF" anchors and `--via viewer` / `--current` (resolve the current tab).
- What stays vendor-specific: Primo's result selector `fulldisplay` and its search URL. Either name them in the config next to `institution.discovery`, or move the search into an OpenCLI adapter (orchestrate, don't absorb).
- Visible: `no_pdf_link` fires less often; `--via viewer` becomes an option. publishers.md's "Getting the bytes" section and IEEE recipe (`:89`) shrink to facts.

### 2. The chain's unit, the route, has no name in code (try-key patch, versions lost)
- SKILL.md:98-102 lists five routes. fetch.py exposes them as combinations of `--via`, `--version` and `--start`.
- `tried()` (`fetch.py:191-208`) builds a try's identity from pass, via, version (for http only) and "not a `--start` run". Commit `7341bbe` patched this ("each http version and each --start page is its own try").
- Two problems that come from this:
  - **Unknown-version links are never fetched.** fulltext_links labels repository copies, unlabelled OpenAlex links and PMC (when Europe PMC is silent) as `unknown` (`fulltext_links.py:24-33`), but no route walks them: `unknown` appears only in fetch's `--version` choices (`:650`). If one were walked, fetch would pass `--version unknown` to claim, whose choices exclude it (`claim.py:56,330`); claim exits 2 and the run fails with `claim_failed`.
  - **PMC author manuscripts get filed as published.** SKILL.md:98 sends PMC through `--via page --start <url>`. `page_route` passes version `None` (`fetch.py:431,449`), so claim falls back to check_pdf's guess from the file name (`check_pdf.py:420-428`) and files the manuscript as `<slug>.pdf`. fulltext_links knew the link's version; the route that fetches it drops it.
- **General change:** fetch runs named routes, each with a list of candidate links `{url, version}`:
  - `open`: links of version published, then unknown;
  - `publisher`: doi.org;
  - `discovery`;
  - `accepted`;
  - `preprint`;
  - `snapshot`.
- Each candidate is tried over plain HTTP first and in the browser when the answer is not a PDF. That makes `needs_browser` an optimisation, not a requirement.
- A try is (slug, pass, route). `--start` adds a candidate to a route instead of being an untracked special case. The version travels with the candidate into claim.
- Visible: yes. `--via`/`--version` can stay as aliases.

### 3. A file's version is defined in seven places, with different vocabularies
- File-name suffixes: `fetch.py:83`, `claim.py:54-56,111-114`, `check_pdf.py:109-112`, `attach_file.py:69-71`, `report.py:68`.
- Attachment titles: `attach_file.py:72-73`. It writes "Preprint (arXiv)" for every preprint, bioRxiv and medRxiv included.
- Re-derived from attachment titles, two different ways:
  - `report.py:69-72`: a regex that includes Chinese words;
  - `read_library.py:239-242`: a title prefix.
  - So these two disagree on whether an attachment is the preprint.
- `fulltext_links.py:81` has `unknown` but no supplement or snapshot; claim has the reverse.
- **General change:** one `versions` table (version, file suffix, attachment title, rank) in a shared module. Writers and readers both use it.
- The structured package then becomes one more row (role `package`), not an eighth copy. Not visible.

### 4. The "is this file the paper" verdict is computed, dropped and recomputed; acceptance has two paths
- claim runs check_pdf (`claim.py:166-180`), but scripts that fetch never write records, so the verdict lands only in `fetch.jsonl`.
- Step 4 therefore runs `check_pdf -i` again (SKILL.md:121), so attach_file can find `pdf.code` with the md5 (`attach_file.py:619-626`).
- attach_file's single mode runs check_pdf itself (`:360-372, :676-685`) and has `--accept`, where records use `pdf_accepted`.
- Manual acceptance (SKILL.md:108) is four hand steps: move, rename, re-check, edit the record.
- **General change:** record the verdict once, keyed by md5 (claim's event already carries md5 and code).
  - attach_file, in both modes, accepts a file when a passing verdict or an acceptance exists for that md5, and otherwise runs the check now.
  - One acceptance mechanism, e.g. `claim.py --accept FILE --slug S --reason R`, which also files the file.
  - Visible: one fewer step-4 command, and no manual move.
- Inside check_pdf:
  - The erratum and supplement heading markers (`:125-131`) override a pass, so they earn their place as living lists.
  - `DENIAL_RE` (`:135-138`) only acts after path A has failed (`judge :557`). It mostly relabels `title_not_found`, and it is a third copy of the gate markers in publishers.md and SKILL.md's Gate rule.
  - `doi_to_item ERRATUM_TITLE :160` checks the same erratum fact again at draft time. It should call check_pdf's marker function.
  - Keep check_pdf as the single owner of "not this paper".

### 5. "Same paper" and "already has the PDF" are each written several times
- Identifier extraction:
  - `find_in_library.py:255-280`; its `matches_doi :228` also checks a doi.org url;
  - `lint_items.py:107-123`, which skips the url;
  - `fulltext_links.py:198-217`;
  - `doi_to_item arxiv_id_of :1016`;
  - `check_pdf doi_key :433`.
- Title rules differ:
  - find_in_library: containment plus subtitle split (`:437-464`);
  - lint_items: exact normalized title of 12 characters or more (`:186-191`).
- `create_item` delegates to find_in_library, which is the right shape; lint_items has its own copy.
- "Has a PDF" is decided three ways: `claim.py:105-108`, `report.py:293`, and `attach_file.py:604-610` (where any attachment counts). SKILL.md:77 also teaches it in prose (`contentType`/`linkMode`).
- **General change:** an `identity` module with `identifiers(item)`, `same_paper(a, b) → doi | arxiv | title | contains`, and `has_pdf(attachments)`.
  - find_in_library and lint_items both use it; lint keeps its one-read library index.
  - `found` carries `has_pdf` and the attachment versions.
  - Visible: lint finds title near-matches it misses today.

### 6. Host, proxy and "URL of record" knowledge sits in four tables with three definitions
- **"Is this a proxy host":**
  - fetch reads `institution.proxy` from the config and maps hosts (`fetch.py:360-375`); fulltext_links also reads the config (`:293`);
  - `attach_file.py:326` hard-codes `.idm.oclc.org|ezproxy` and ignores the config;
  - `lint_items.py:66` adds `webvpn`.
  - attach_file refuses a proxied URL instead of un-proxying it, although fetch already knows the mapping.
- **Host tables:**
  - `NEEDS_BROWSER` (`fulltext_links.py:86-104`): its `False` entries change nothing, since unknown hosts are tried over HTTP first anyway;
  - `FIXED_VERSION` (`:105`);
  - `COPY_HOSTS` (`lint:63-65`);
  - `PACE` (`fetch.py:88`): the 10 s medRxiv/bioRxiv gap is keyed on the host before the redirect. `page_route` paces `doi.org` (`:410-411`), and the http route skips medRxiv links (`needs_browser`), so the gap almost never applies where it was meant to.
- **"URL of record":** `doi_to_item:707-716` (plus `SALES_PAGE_DOI :120`), `lint:216-225`, `attach_file url_of :567-576`, SKILL.md:83-86.
  - The user's rule (F#17) is general: with a DOI, the url is `https://doi.org/<DOI>`; for 10.52202 it is the NeurIPS page.
  - lint narrows this to a host list, so a url on the publisher's own page escapes `url_not_record`.
- **General change:** a `hosts` module with:
  - `unproxy(url)` from the config: attach_file stores the un-proxied URL, and lint flags any proxy host;
  - `record_url(item)`, written by doi_to_item, compared by lint, used by attach_file;
  - one small table for the host facts that remain;
  - pacing keyed on the host actually reached.
  - Visible: lint flags more; attach_file normalises instead of refusing.

### 7. Run-wide settings are passed on every call, and pacing limits are left to the docs
- `ready.py` resolves the Downloads folder (`:341-361, :508`) but saves nothing.
- Every fetch and claim call needs `--downloads` (SKILL.md:50); the session name `p2z` is a default in each script.
- Pacing and 429 state live inside each process (fetch, fulltext_links, doi_to_item, lint's Crossref), so `batch.md:41` has to forbid running bulk scripts in parallel or from subagents.
- **General change:** `ready.py` writes `<work>/run.json` (downloads folder, session), and a shared pacer keeps each host's last-request and blocked-until times in the work directory under a file lock. The batch.md rule then becomes a property of the code.
- Visible: `--downloads` becomes optional, and parallel callers become safe.

### 8. fetch.py does six jobs; waiting is tied to logging; verdicts have no owner
- fetch.py holds five routes, plus `--wait` (`:581-613`) and `--verdict` (`:673-676`).
- `--for file` (`:661`, first-batch issue #4) exists only because the gate wait logs `gate_timeout` when it times out and ends when the page changes.
- **General change:** a separate `wait.py` that waits for the record's file and, optionally, a page condition (`--until`, or "page changed"), and never logs. The agent records `--verdict gate_timeout` like any other conclusion. `--for` disappears.
- The verdict list should live in one place and be checked by `--verdict`. Today publishers.md's table has five, SKILL.md:106 ends its list with "…", and report.py prints whatever it finds.
- Visible: the last-pass and Gate text in SKILL.md change.

### 9. Judgement written as rules, or one decision with two owners
- **Model names as tags:** lint's `name_not_tagged` (`:56-61, :226-229`, first-batch #6) is a regex standing in for the tagging judgement that tagging.md gives the agent; it has 71 hits awaiting review. Turn it into evidence the agent asks for, or drop it.
- **Citation-key validity has no single owner:**
  - create_item checks TeX-special characters, at creation only (`:64, :471-477`, first-batch #2);
  - export_bib checks missing and duplicate keys, but not TeX characters;
  - lint checks neither.
  - Fix: one `citekey_problems()` used by lint and export_bib; create_item reports its result.
- **Item type of LNCS chapters:** doi_to_item converts them (`PROCEEDINGS_SERIES :130`), while SKILL.md:80 tells the agent to revise the item type. That is fine as a stated general fact, but the doc should name one owner.
- **Discovery picking results:** it picks by title similarity ≥ 0.9 (`fetch.py:458-461, :505-506`). That is search-and-pick in code, but acceptable because claim verifies the file. Keep it.
- **Redraft from a page:** `page_unreachable` (`doi_to_item:1268-1290`) makes the agent re-type fields read in the browser. The same parser could read the HTML that `fetch --via snapshot --current` already captures (`--redraft --html FILE`).
  - There are three citation-meta readers: fetch `INFO_JS`, check_pdf `HtmlText :296`, doi_to_item `CitationMeta :1243`. They should become one `page_meta(html)`.

### 10. Writes are split across scripts by item property
- `update_item.py`'s `REFUSED` table (`:61-69`) sends some properties to file_and_tag or trash_item.
- update_item, file_and_tag, trash_item, merge_items and note each repeat the same sequence: GET → diff → PATCH with version → retry once on 412 → read back.
- **General change:** one `patch_item(key, changes)` in the Zotero module. Keep the CLI verbs; trash stays separate because it needs the user's yes. Not visible.

### Q4: where SKILL.md and the references work around the code, and where they disagree
**Workarounds a better script boundary would remove:**
- The step-2 reading of `found` (SKILL.md:77) → finding 5.
- PMC through `--start` (SKILL.md:98) → finding 2.
- The step-4 `check_pdf -i` and the manual acceptance (SKILL.md:108, 121) → finding 4.
- `--downloads` on every call → finding 7.
- The `--wait` / `--for` / `--until` combinations → finding 8.
- The step-3 list of file names "those names exactly" (SKILL.md:106): rerunning fetch already tells whether the file has arrived.
- *No DOI record* (SKILL.md:184-196) is a raw connector curl plus version polling at the top level of SKILL.md. Script it (`recognize.py <pdf>` → parent key) or move it to a reference.

**Where the docs and the code disagree:**
- SKILL.md:10 says every script that takes `--key` also takes `--cite`. `read_library item` and `children` take a positional key only (`read_library.py:356-362`); merge_items' `--keep`/`--drop` accept either. One argument type that accepts a key or a citation key, as merge_items' resolve does, would make the statement true everywhere.
- SKILL.md:127 calls the published attachment's title "published"; the code writes "PDF".
- Docs say "never a proxy host"; the code only matches a regex (finding 6).
- fetch's docstring says medRxiv is paced at 10 s (finding 6).

### Q5: the structured package — what it can reuse
**Reusable as it is:**
- `trash_item` works on any key, attachments included.
- `upload_file`'s 3-step upload and the md5 check against existing child attachments (`attach_file.py:281-313, :397-406`).
- `find_in_library`'s description of a found item's attachments (key, content type, md5).
- `note.py`'s marker upsert — find the child with this marker, then create or update it — is exactly the "refresh the package" shape.
- `resolve_cite`, once it is a single function.

**Too specialised today:**
- **`attach_file`:**
  - accepts only a PDF or HTML file (`:332-345`);
  - verifies through check_pdf or `pdf_accepted` (`:619-626, :676-685`);
  - requires a web `--url` (`:318-329, :730`);
  - always creates `linkMode: imported_url` (`:422`);
  - takes the attachment title from the file name's version (`:353-357`);
  - in stream mode, reads import-record fields.
  - Split it into a generic `attach(item, file, content_type, title, link_mode, url=None)` with policies on top: the paper-file policy (a check_pdf verdict), and the package policy (its `source.sha256` matches an attached PDF).
  - Add `--replaces <attachment key>`: attach the new file, then trash the old one. The spec has to state the authorization rule for trashing a derived copy.
- **`read_library pdf`:** PDFs only, ranked by title (`:239-273`), and no md5 in the output.
  - Make it `attachments --cite X [--role pdf|package]` returning {key, role/version, md5, path, exists}.
  - The spec must decide which side changes for the hash: either the package side re-hashes the PDF on disk (the path is already there; keeps paddleocr Zotero-agnostic), or paddleocr also records md5.
- **"Which PDF the package follows"** (open point 3 in the package issue) must be the same function as the version ranking in finding 3. The same goes for recognising a package attachment.
- **The records pipeline** (`records/<slug>.json`, the work directory) is specific to import. The shared modules need item-level functions, not only record filters, or the package flow cannot use them.

### Q6: the open issues
- **IEEE PDF link: fold it in.** It is the acceptance test for finding 1. Close it when IEEE (and ideally an ACM or Wiley page) goes through without a stop; publishers.md:89's manual recipe becomes a fact.
- **Manuscript collections: out of scope.** It is a library policy waiting on the user (「先这样放着不要动」), with no code mechanism to fix. The spec should record it as untouched and name its future home: an organize.md principle on project versus topic collections. The restructure must not add assumptions about collection structure; `tmp` stays a stated convention.

### Top level: how the code should be cut
Stages, the artifact each produces, and who does it:
1. **Identify:** the user's words → an identifier. Agent, with papers-cool, OpenCLI and Crossref.
2. **Draft:** identifier or page HTML → `record.item`, warnings, published-version candidates. `doi_to_item` using the shared `page_meta`; the agent revises.
3. **Preview:** item → `checks`. `check_item`.
4. **Resolve against the library:** record → `found {key, has_pdf, versions}` or `near_match`. `find_in_library` on `identity`; the agent decides near matches.
5. **Locate copies:** record → `links [{url, version}]`. `fulltext_links`.
6. **Obtain:** route plus candidates → bytes. `fetch` (`pdf_links` and the ladder); `wait` separate; the agent at stops.
7. **Verify and file:** bytes → a verdict keyed by md5 and `records/<slug>.<version>`. `claim` calling `check_pdf`; the agent accepts uncertain files.
8. **Persist:** record → item key; file plus verdict → attachment. `create_item`, and `attach_file` on the generic `attach`.
9. **Read back and report:** `find_in_library --readback`, `report`.

Shared modules:
- `zotero`: API client, key, item reference (key or citation key), paging, children, `patch_item`, `attach`;
- `records`: load, save, stream, outcomes, `run.json`;
- `identity`;
- `versions`;
- `hosts`: unproxy, `record_url`, host facts, the shared pacer;
- `browser`: the opencli wrapper, `pdf_links`, `page_meta`.

The organize scripts and the structured-package flow sit on `zotero`, `identity` and `versions`, not on `records`.
