# REUSE review: paper-to-zotero (2026-10-20)

Read-only subagent review at `c528750`, kept as written. Not verified line by line; the spec marks what the main session checked.

Scope: all 21 scripts and 21 test files. Method: I printed every variant of each shared name, deduplicated by AST, and grepped for the same logic under other names. Paths below are under `paper-to-zotero/`.

## 0. Three constraints that break tests on day one (decide these first)

1. **`p2z.py` globs `scripts/*.py` as its command list** (`p2z.py:21-32`). `tests/test_p2z.py:37` checks that every `*.py` there is listed, and `:82` checks that each has a one-sentence docstring. A shared `zotero.py` placed next to the scripts would become a bogus command. **Recommendation: a subpackage, `scripts/p2zlib/`.** The glob does not recurse, so neither p2z nor its tests change, and `from p2zlib import zotero` works because the running script's directory is on `sys.path`. Do not name it `p2z/`: it would shadow `p2z.py`. The alternative is an `_` prefix plus a skip in p2z and test_p2z.
2. **8 tests load scripts with `importlib.spec_from_file_location`**: `test_doi_to_item.py:293`, `test_fetch.py:319,382`, `test_fulltext_links.py:119`, `test_note.py:28`, `test_read_library.py:25`, `test_ready.py:416`, `test_update_item.py:14`. That puts nothing on `sys.path`, so `import p2zlib` would fail. The shared test helper must insert `scripts/`. Subprocess-based tests are unaffected.
3. **`Stop` has two signatures.**
   - `claim.py:59`, `fetch.py:132` and `lint_items.py:71` use `Stop(code, hint, **extra)` and always exit 2.
   - 13 scripts use `Stop(code, exit_code=1, hint=None, **extra)`.
   - Ported as is, the first group would silently bind the hint to `exit_code`. The shared `Stop` should make `exit` and `hint` keyword-only.
   - `doi_to_item.Failure` (230) has the second shape and can simply become `Stop`.

## 1. Zotero access

**1a. HTTP client.** Variants:
- `Api`, 8 forms: attach_file:110, create_item:136, file_and_tag:71, merge_items:57, read_library:70, ready:107, report:96, plus one shared by export_bib:77, make_collection:65, note:88, trash_item:89, update_item:95.
- `LocalApi`: check_item:106, find_in_library:127.
- Inlined clients: `lint_items.get` 77, `ready.get` 140, `doi_to_item.fetch_schema` 371.

They differ in:
- **Body encoding.** bytes+str: attach_file. str only: file_and_tag, ready. Dict/list only: the shared form. merge and create JSON-encode any non-None body.
- **Timeouts.** 120 s default; create 30 s (POST 60); ready 30; report 5; read_library and lint 30; find, check and fetch_schema 15.
- **Exceptions.**
  - `Stop zotero_unreachable 2`, with the hint "Start Zotero" or "ask the user (never restart it)".
  - create: `Unreachable`.
  - ready: a separate `RequestTimeout`, needed for the authorize dialog.
  - check/find: `ApiError(code, detail, hint, exit_code)`.
  - report: a raw `OSError`, deliberately soft — collection names are optional.
  - lint: a two-argument `Stop`.
- **Logging.** read_library and find_in_library log every GET, but only with `-v`; create logs `/api/` only.

**Canonical:** read_library's `Api` (GET with params, `allow_404`, `location()` for the `file://` redirect, a `get_all` that honours `Total-Results`, `Link rel=next` and a short page) combined with attach_file's `request()` body handling. Sketch:

```
zotero.Client(base_url, timeout=120)
  .request(method, path, body=None, headers=None, timeout=None) -> (status, headers, bytes)
      raises Unreachable(Stop); Timeout(Unreachable)
  .get(path, params=None, allow_404=False)
  .get_all(path, params=None, limit=None)
  .location(path)
```

ready catches `Timeout`; report catches `ZoteroError`, which keeps its soft mode. The timeout is set per call.

**1b. Status → result code: one rule, vocabulary diverging today.**
- `check_common` has 3 forms. attach_file:141 and five others check 403, 401 and 412. export_bib:104 checks only 403. merge_items:86 drops the extras.
- `get_json` has 4 forms: attach:270 takes a `not_found` tuple; export, make and note at 112/147/170 return None on 404; merge:121 has `allow_404`; fulltext_links:161 is a separate external client.
- `get_list` has 4 identical copies: attach:193, file_and_tag:268, trash:182, update:187.
- `get_item` has 3 forms: file_and_tag:258/update:177, note:293, trash:171. Only trash checks `item.key == key`.

Divergences to settle:
- **Any 403** counts as `local_api_disabled` in LocalApi, lint, `ready.get` and fetch_schema. `check_common` requires "not enabled" in the body.
- Other 403s on writes produce three codes: `write_denied` (file_and_tag:388, update, trash, note:313, make:212), `files_not_editable` (attach:290) and `library_not_editable` (create:436).
- A bad reply is `unexpected_response` in 24 uses (exit 1, or 2 in ready and create), `api_error` exit 1 in merge, and `api_error` exit 2 in LocalApi and read_library.
- **412 on a POST** always means `server_mismatch` in create:421. `check_common` and note:354 require "server-id" in the body.
- Synonyms: `not_found`/`item_not_found`; `create_failed`/`attachment_create_failed`/`write_failed`/`patch_failed`; `invalid_record`/`record_invalid`/`input_invalid`; `collection_invalid`/`invalid_collection`; `tags_invalid`/`invalid_tags_file`.

**Pick:**
- 403 with "not enabled" → `local_api_disabled`, exit 2. Any other 403 → `write_denied`, exit 1.
- 412 with "server-id" → `server_mismatch`, exit 2. Any other 412 → `version_conflict`.
- Everything else → `unexpected_response`, with the exit code as a caller parameter so each script keeps its current exit semantics.

Visible change: codes are renamed in check_item, find_in_library, read_library, merge_items and create. SKILL.md and the references need updating to match.

**1c. Server id + key + config.**
- `live_server_id`, 3 forms: attach:155 (×6), create:333 and ready:151, plus `merge.server_id_of` 96.
- `load_key`, 3 forms: attach:169 (×6), create:361 (extras `stored_server_id`, `server_id`), merge:104 (no extras, config path inlined).
- `config_path` ×8, inlined 3 more times: merge:106, fetch:170, fulltext_links:136. Also `ready.read_config` 165.
- `write_headers`: 2 forms. attach:189 has no version; the others take `If-Unmodified-Since-Version`.

Divergences:
- A 200 reply with no server id gives `zotero_unreachable` in most scripts; create gives `no_server_id` with a "Zotero 10+" hint.
- A broken config gives `config_unreadable` exit 2 (load_key, ready). fulltext_links:141 raises `SystemExit` with JSON `bad_config`, so it goes to stderr with exit 1. fetch:172 silently uses `{}`.

**Pick:** `config.read(strict=True)`, `config.zotero_key(server_id)` with the union of extras (never the key itself), and `zotero.Session(client)`, which does the `/api/` check, loads the key and builds the write headers. The other scripts get create's `no_server_id`. fetch's soft read becomes `strict=False`.

**1d. Paging: 11 loops.**
- `read_library.Api.get_all` 120, `find_in_library.LocalApi.get_all` 177 (silently returns a partial list on a non-list page), `lint_items.get_all` 91 (also partial).
- `get_pages`: export_bib:125, note:183.
- `make.list_collections` 160, `report.collection_paths` 115, `ready.collection_tree` 420, `merge` 243.
- Inline in `resolve_cite`/`find_cites`: attach:215, file_and_tag:296, trash:209, update.
- `find_in_library.run_md5` 559.

Canonical: read_library's version, which raises on a non-list page.

**1e. Citation key → item key.**
- `resolve_cite`, 6 forms: attach:209/update:203, export:143, file_and_tag:308, find:307, note:201, read:150.
- Batch forms: `trash.resolve_cites` 198 and `file_and_tag.find_cites` 284, which do one fallback scan for every miss.
- `merge.resolve` 131 lacks the `is_top` filter and the `/items/top` fallback scan, so a citation key the search misses is `cite_not_found` there only.
- Hints differ in every copy.

**Canonical:** `find_cites` → `zotero.find_cites(client, cites) -> {cite: [keys]}`, with `resolve_cite(client, cite)` raising `cite_not_found`/`cite_ambiguous` on top of it. This is also the next feature's lookup.

**1f. Children and attachments.**
- Filtered on `parentItem == key`: find:346, read:219/253, note:298. This guards against the local API answering a missing key with the whole library (`read_library.py:218`).
- Unfiltered and unpaged: attach:394, merge:241. Harmless today because both fetch the parent first.

Canonical: `children(client, key, item_type=None)`, filtered and paged. A projection of `find.attachments_of` (345) becomes `attachment_summary()`.

**1g. Collection tree: 7 builders.**
- find:323 (`" / "`, includes trashed collections)
- lint main:253 (`" / "`, recursion depth ≤ 20, includes trashed)
- report:112 (`"/"`, skips trashed)
- ready:418 (`"/"`, skips trashed, sorted)
- make:160+177 (`"/"`)
- read:276 (walks from the root, skips orphans)
- export:212+221 (children map for `--recursive`); lint:278 does the same with a fixed-point loop

The existence check for a collection is written twice: `create.check_collection` 385 (single, cached in 557) and `file_and_tag.check_collections` 319 (all-or-nothing).

**Pick:** `zotero.collections(client) -> {key: {name, parent, deleted}}`, plus `path(key)`, `descendants(key)` and `check_live(keys)`, with `"/"` as separator and trashed collections excluded. Visible: find_in_library's `found.collections` and lint's output change separator.

**1h. Schema.**
- check_item:188 makes 3 GETs: `/schema`, `/itemTypeFields` and `/itemTypeCreatorTypes`.
- update:226 builds all types from `/schema`.
- `doi_to_item.fetch_schema` 371 + `TypeFields` 542, which resolves base fields.
- merge:157 maps field → base field.

The base-field mapping exists 4 times. Non-field key sets: check_item 66/71/73, `update.REFUSED` 61, `merge.NOT_FIELDS` 46, `create.check_item` 203 + `NOT_PARENT_TYPES` 65, which duplicates `CHILD_TYPES`. `CHILD_TYPES` itself appears 7 times in 2 orderings.

Pick: `zotero.Schema(json).type(t) -> {fields, base_to_field, creator_types, primary}`, plus `own_field()`, in a domain module `items.py`.

**1i. Writes.**
- **Versioned PATCH, retry once on 412 after re-reading and re-planning, then read back**: file_and_tag:370, update:360, trash:257, note:348. merge `write` 214 does not retry.
  → `zotero.patch_versioned(client, sess, key, plan(item) -> patch|None) -> (before, after, retried)`.
- **Parsing a POST `/items` reply per index (successful/unchanged/failed)**: attach:426, create post_pending 699, file_and_tag:515, note:369, make:209.
  → `post_objects(objs, chunk=50)`.
- Upload in 3 steps: `attach.upload_file` 281, the only copy.

## 2. Record pipeline

**2a. Readers: two families plus 4 others.**
- **Strict** (any bad file aborts the run with `record_invalid`/`no_records`), built on `parse_stream`, a `raw_decode` loop: attach:461/480, check_pdf:576/595, create:232/252, `fetch.load` 620.
- **Tolerant** (`{path, record, orig, error}`; a bad file becomes one failed line), built on `read_json_records`, which tries `json.loads` on the whole text and then line by line: check_item:421/445, find:602/626, `doi.load_record_files` 766 + 741, `fulltext.load_entries` 395 + 372 (3 forms).
- `parse_records` export:162/report:162 is the `raw_decode` loop plus glob expansion and an `isatty` check.
- `claim.records_of` 83 skips bad files silently.

The tolerant parser cannot read concatenated pretty-printed objects (`cat records/*.json`).

**Pick:**
- One `records.load(paths, *, globs=False)` on the `raw_decode` loop, always returning entries with an `error` field. This is a fix for the tolerant family.
- Write scripts call `records.require_valid(entries)` before any write, which keeps their "nothing was done" guarantee.

**2b. Atomic write: 6 copies.**
- With the umask/chmod fix: `write_record` check:468, find:649, doi:785.
- Without it, so rewritten records end up mode 0600: `save_record` attach:501, check_pdf:616, create:274, and `fulltext.write_record` 415.

Canonical includes the chmod. This is a visible fix.

**2c. Outcome/results and stream skeleton.**
- `Outcome`: attach:516, check_pdf:671, create:289.
- `write_results`, 5 forms:
  - Outcome-based: attach:531, create:304, check_pdf:686. These catch `OSError` on write-back as `write_failed`, log a per-record summary to stderr, and stop early (`stopped`) with that exit code.
  - Dict-based: check:487, find:668. These compare against `orig`, let `OSError` crash, and log nothing per record.
  - doi:804, with a `quiet` mode for `--out-dir`.
- check_pdf's counts lack `skipped`.
- `run_stream` has 6 forms (attach:645, check_item:507, check_pdf:728, create:740, doi:1613, find:790). Exit-2 handling differs:
  - attach and create fail the rest of the records and still print them.
  - check_pdf re-raises, so no per-record lines are printed.
  - check and find let `ApiError` escape `main`, losing every result.
  - doi lets `Failure` → `emit` exit.

**Pick:** the Outcome form, plus a `changed` flag that falls back to comparing against `orig`, plus `quiet`. `records.run_stream(entries, fn, in_place)` owns the exit-2 rule from attach and create.

**2d. Record accessors.**
- `slug_of`, 2 forms: attach:454 (×3) and claim:96/fetch:261, which crashes when path is None.
- The `rec.get("item") if isinstance(...)` idiom ×8.
- The item key (`saved.key`, else `found.key`): `attach.item_key_of` 558, export:264, find:690, `report.library_state` 200.
- `library_has_pdf`: claim:105 and report:293. They differ: report ignores `linkMode`.

**2e. Work directory, file naming and versions.**
- `STEM_FILES` ×5: attach:69, check_pdf:112, claim:54, fetch:83, report:68.
- `NAME_VERSIONS` ×2: attach:70, check_pdf:110.
- `VERSIONS`: check_pdf:109 and claim:56; fulltext:81 is different (adds `unknown`, lacks supplement/snapshot).
- Version → name: `claim.target_name` 111. Version → attachment title: `attach.VERSION_TITLES` 72 / `title_for` 353.
- Attachment title → version is parsed back twice, differently: `read.version_rank` 239 (prefix match) and `report.VERSION_WORDS` 69 (regex search, includes Chinese words), plus `file_kind` 185.
- `file_of(slug)`: claim:100, fetch:177, attach:594 inline, check_pdf:650 inline, report:288.
- `fetch.jsonl` is appended in claim:117 and fetch:216, and read in fetch:191, claim:236 and report:272.

**Pick:** `workdir.py` with one version table `{version: (suffix, attachment title, title pattern, rank)}`, plus `version_of(path)`, `file_name()`, `file_of()`, `attachment_version()`, `append_event()` and `read_events()`.

## 3. CLI skeleton

- **`emit`, 7 forms, with three hint rules:**
  - hint only when exit ≠ 0: the majority;
  - hint whenever code ≠ "ok": doi:301;
  - hint always: create:120.
  - export:64 and report:87 print one line to stderr, because stdout carries the payload.
  - check and find (154/466) print a dict and return the exit code, and also print `code: detail` to stderr.
  - claim:356, fetch:692, lint:250 and merge:287 hand-print.
  - Pick: the majority hint rule, with `stream` and `indent` as parameters. Visible change only for hints on success in doi and create.
- **`log`**: unconditional in 15 scripts, `-v`-gated in find:110 and read:57. Pick: a module flag defaulting to on.
- **`text`**: limit 400, or 300 in create:128. **`now_iso`**: ×8, identical.
- **`__main__` wrapper**: ×11. **`DEFAULT_BASE_URL`**: ×16, plus a 17th hard-coded at claim:335.
- **`--key`/`--cite` forms all differ:** single (attach, file_and_tag, note, update, find), `append` (export, read), `nargs="+"` (lint), `extend` + comma (trash:306 + `split_values` 289; `export.split_keys` 205 duplicates it).

Pick: `cli.add_item_selector(parser, many)`, which accepts repeated flags, several values after one flag, and comma-separated values. That is a superset of today's forms, so nothing breaks. Also `cli.main(fn)`.

## 4. Domain rules

**Identifiers: 6 parsers.**
- `find.identifiers_of` 255 (with `normalize_doi` 201, `normalize_arxiv` 207, `matches_*` 228/239)
- `lint.identifiers` 107
- `fulltext.identifiers` 198 + `strip_doi` 192
- `doi.parse_identifier` 314, `arxiv_id_of` 1016, `bib_identifier` 943
- `check_pdf.doi_key` 433
- `check_item:351` inline

`ARXIV_ID` ×4. Where they disagree:
- fulltext validates the `10.\d{4,9}/` shape; find does not.
- find matches doi.org URLs in `data.url`; lint does not, so find_in_library and lint_items disagree on which items are duplicates.
- The arXiv id in Extra is matched anchored (fulltext, doi) or unanchored (find, lint).

Pick: one `ids.identifiers(item)` built on find's rules plus the DOI shape check.

**Titles.**
- NFKC casefold, alphanumerics only, ×4: find:196, lint:103, doi `comparable` 477, check_pdf `normalize` 228.
- `doi.clean` 976 is the NFKD form used for slugs.
- `fetch.same_title` 458 is ASCII-only, so a CJK title never matches.
- Similarity is computed 3 ways (doi:1048 `autojunk=False`; fetch and lint:167 use the default), all with a 0.9 threshold.

**Tags.**
- `create.normalize_tags` 175: a duplicate is an error; a bool type is rejected.
- `file_and_tag` 155: the last duplicate wins with a log line; `True` is accepted as type 1.
- `report.tag_names` 373 accepts `"0"`. Also `create` 446 and `file_and_tag.tag_map` 215.
- Pick: dedupe keeping the last, with a warning; reject bool.

**Creators.**
- `check_creators`: check_item:221 reports problems, update:282 raises. The rules are the same but phrased differently.
- First author: `check_pdf.first_author_surname` 238, `attach.first_creator` 237, `doi.derive_slug` 983, lint:151.

**HTML meta parsing**: `check_pdf.HtmlText` 296 + charset sniffing at 338, and `doi.CitationMeta` 1243 + charset at 1281.

**External HTTP pacing: 4 pacers.**
- `doi.http_get` 272 (module globals, stops a host on 429)
- `fulltext.get_json` 161 (a context dict)
- `lint.Crossref` 141 (fixed 1 s; Crossref URL hard-coded with no env override, so it cannot be tested)
- `fetch.Run.pace` 255

`retry_after`: doi:259 reads the header as seconds or an HTTP date; ready:238 reads it as an integer, then the body, with a default of 15. `USER_AGENT` ×3, `BROWSER_UA` ×2. `host_of` 146 / `url_host` 227 / `report.host` 298 (not lowercased).

**Small duplicates**: md5 in claim:73, find:531, check_pdf:378, and attach twice per file (380, 618). Windows → WSL path in read:226 and ready:329.

## 5. Scripts calling scripts

| Call site | Calls | Timeout |
|---|---|---|
| attach:364 | `check_pdf --match` (record on stdin) | 180 s |
| claim:168 | `check_pdf --match` | 300 s |
| claim:297 | `find_in_library --md5` | 300 s |
| create:664 | `find_in_library` stream | 600 s |
| fetch:228 | `claim --file` | 600 s |
| fetch:241 | `claim --scan` | — |

Every caller re-parses stdout with its own rules ("lines starting with `{`", `returncode >= 2`, row counts that must match). fetch's `scan_downloads` runs `claim --scan` before every record (183) and **every second** inside `wait_for_file` (245).

**Proposal:**
- `check_pdf.match(path, records, version=None) -> (matched, codes, file_version)` and `check_pdf.check(path, item)`.
- `find_in_library.look_up(client, records)` and `by_md5(client, paths)`.
- `claim.scan(work, downloads)` and `claim.claim_file(...)`.

These become importable functions and the CLIs stay as thin wrappers. fetch → claim may keep a process boundary if the spec wants the watcher and fetch to share only the `O_APPEND` log; otherwise import it too.

None of this changes visible flags or outputs. create's "the duplicate check never depends on the agent" guarantee (create_item.py:26) holds either way. `lint.problems_of`'s duplicate index should reuse `ids.identifiers` and the title key.

## 6. Tests

**Zotero fakes**, about 950 lines across 14 files, with four storage shapes (flat data; `{key, version, data}`; `{version, data}`; data only):

| Fake | Endpoints | Special behaviour |
|---|---|---|
| attach:35 | `/api/`, item, children (404 when missing), POST items, POST `/file` (authorize/exists/register, md5 checked), POST `/upload/{k}` → 201 | — |
| create:34 | collections (paged, `Total-Results`), collection, item, children, items and top with q/qmode emulation | 401 on key, 412 on server id; `REJECT` title, `thin_response`, `drop_collection(s)`, `post_status`, `search_status`; also serves the find_in_library subprocess |
| file_and_tag:39 | collection, items/top q (`search_sees_citekey`), item; PATCH with version → 412; POST batch update with per-object 412 | — |
| trash:47 | top (excludes trashed), PATCH `deleted` | `bump_before_patch`, `trash_meanwhile`, `ignore_patch`, `patch_status`; `meta.numChildren` |
| merge:53 | `/schema`, unpaged collections, children; PATCH | version +100; a bad key → 412 rather than 401 |
| note:34 | items q, top and children (paged), POST note | `fail_patch_once`; call log with headers |
| make:24 | collections (paged), POST collection | — |
| export:22 | `collections/{k}/items/top`, `itemKey`, `format=bibtex` (text/plain) | logs URL length |
| find:58 | qmode emulation, children (missing key → whole library) | `Total-Results` |
| read:67 | `/schema`, tags, `/file` → 302 `file://`, `itemKey` (brings children), `since`, `Link rel=next` | `disabled` → 403 |
| check_item:36 | `/itemTypes`, `/itemTypeFields`, `/itemTypeCreatorTypes`, `/schema` | 403 |
| lint:59 | items, collections | default page limit 100 |
| report:27 | collections, tags | — |
| ready:48 | `/api/` (status override, `Zotero-API-Version`), collections, `/local/authorize` with scripted replies including sleep | — |

**One shared `tests/fake_zotero.py` must support:**
- the `handle(method, path, query, body, headers)` style of note, make and export, with a call log;
- storage `key → {version, meta, data}` with a `row()` builder, plus collections, tags, schema and files;
- all routes above, q/qmode emulation, `itemKey`, `since`, `itemType` and `bibtex` filters, paging (default 25, `Total-Results`, `Link`), the children quirk, the 302 file redirect, the 3-step upload, POST create and update by index, versioned PATCH and trash;
- authentication (401 on key, 412 on server id), the 403 "disabled" state, and scripted authorize replies;
- named fault hooks: route status override, bump / fail-once, ignore write, thin reply, drop collections, reject by predicate.

The non-Zotero fakes stay separate but share the handler plumbing: doi_to_item:234 (doi.org, Crossref, arXiv, pages; it also serves `/api/schema`), fulltext:77 and fetch:106.

**Duplicated test helpers:**
- `closed_port` ×7: attach:28, create:27, lint:20, trash:25, claim:28, doi:215, ready `free_port` 115.
- `run_script` ×19. Key-leak assertions are inconsistent: file_and_tag:153 and ready:167 check on every call; attach, create, make, note and trash check in one test; merge never checks. The shared runner should always check.
- `lines()` ×12; config writing ×8; poppler stubs in 5 variants (check_pdf:29, claim:47, fetch:151, attach:232, ready:130); fake PDF bytes in claim:24 and fetch:27; server start/stop boilerplate ×17; module loaders ×8 (see §0.2).
- Together these are about 455 lines.

## 7. Module map

| Module | Lines | Contents |
|---|---|---|
| `p2zlib/cli.py` | ~90 | `Stop(code, *, exit=1, hint=None, **extra)`; `log`/verbosity; `emit(code, exit, hint, stream, indent)`; `text`; `now_iso`; `main(fn)`; `add_base_url`; `add_item_selector`; `add_records` |
| `p2zlib/config.py` | ~60 | `path()`, `read(strict)`, `zotero_key(server_id)`, `save_zotero_key` (ready), `institution()` |
| `p2zlib/zotero.py` | ~450 | constants; `Client`; `Unreachable`/`Timeout`; status rules; `Session`; `get_all`; `item`; `children`; `search`; `find_cites`/`resolve_cite`; `collections`/`path`/`descendants`/`check_live`; `Schema`; `patch_versioned`; `post_objects`; `create_collection`; `create_attachment`; `upload_file`; `set_deleted`; `file_location` |
| `p2zlib/records.py` | ~200 | `load`, `require_valid`, `save_atomic`, `Outcome`, `write_results`, `run_stream`, `slug_of`, `item_of`, `item_key_of`, `library_state` |
| `p2zlib/workdir.py` | ~120 | version table, file naming, `file_of`, `attachment_version`, event log, `started_at` |
| `p2zlib/ids.py` | ~150 | arXiv/DOI parse and normalise, `identifiers`, `matches_*`, `title_key`, `slug_key`, `fold`, `similarity`, creator name helpers |
| `p2zlib/items.py` | ~100 | `normalize_tags`, `tag_map`, `check_creators -> problems`, non-field key sets |
| `p2zlib/web.py` | ~130 | `Pacer` (intervals, 429 stop, both `retry_after` forms), `get`, user agents, `host_of`, HTML meta parser + charset decode |
| `p2zlib/host.py` | ~40 | `is_wsl`, `to_local_path`, `command_output` |
| `tests/fake_zotero.py` | ~350 | the shared fake |
| `tests/helpers.py` | ~100 | `closed_port`, `run_script` (always checks for a leaked key), `lines`, `write_config`, `poppler_stub`, `fake_pdf`, `load_script` (adds `scripts/`), `ExternalServer` |

**Rough savings.**
- **Scripts: about 1.8–2.1k of 11.8k lines.** Computed as the AST sum of all copies minus one canonical copy for each group: Zotero ~800, records ~450, CLI ~220, citation keys ~85. Differently-named builders (collections, ids, schema) add about 220. Inline loops add about 450: paging ×11, PATCH-retry ×4, POST parsing ×5, subprocess glue ×6. From that, take off what the union adds back.
- **Tests: about 0.9k.** About 950 lines of fakes become ~350 shared plus each test's own fixtures, and about 455 lines of helpers become ~100.

**The structured-package feature on these modules:**
- Attach a zip: `zotero.create_attachment` + `upload_file` (from attach:420/281), with `default_filename` moved into `items.py`.
- Move the old attachment to the trash: `zotero.set_deleted` (the trash:244 loop through `patch_versioned`), picking the attachment with `workdir.attachment_version` and the report:348 rules.
- Look up by citation key: `zotero.resolve_cite` (from `find_cites`).
- Find a library PDF on disk: `zotero.children` + `file_location` (read:105) + `host.to_local_path` (read:226) + the version table's rank instead of `version_rank`.
