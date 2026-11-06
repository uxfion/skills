# Organize existing items

The second entry: the user asks for tags or collections to be tidied, a field fixed, duplicates merged, a structure built, a note attached, or a collection exported as BibTeX.

## A tidy: check, judge, confirm, write, read back

A request to tidy a collection (整理) runs these steps, working in `<scratch>/tidy/`; a single fix the user names starts at step 3. The collection 主题笔记 holds paper-read's topic notes: a tidy leaves it and its notes as they are.

1. **Check.** `p2z.py lint --collection <path> [-r] > <scratch>/tidy/lint.jsonl` reads the whole library once and lists each item in scope that has a problem, each problem a fact with its evidence (`-h` lists the codes). Done when it has exited: 0, nothing to tidy; 1, with its summary as stderr's last line.
2. **Look up what is missing** with paper-fetch (SKILL.md, *Sibling skills*), for the judges to read:
   - `missing_doi`: per item, `pf.py identify --search "<title>" --author <surname> > <scratch>/tidy/search/<key>.jsonl` (Crossref's top five, unfiltered);
   - `missing_abstract` on an item with a DOI: `printf '<DOI>\t<citation key>\n' … | pf.py identify -o <scratch>/tidy/fetch`, then `p2z.py fill <scratch>/tidy/fetch/results/*.json > <scratch>/tidy/fill.jsonl` — the item's empty fields from its DOI record, nothing overwritten.

   Done when every `missing_doi` item has its search file and `fill` has run over every `missing_abstract` item with a DOI.
3. **Judge.** Lint's lines go to tidy judges (SKILL.md, *Handoffs*; their brief is [tidy-judge.md](tidy-judge.md)), a case being one item: split `lint.jsonl` into shares of about 20 lines, `<scratch>/tidy/lint.<n>.jsonl`, and fill in `<scratch>` and `<n>`. What comes back, in `<scratch>/tidy/`: `verdicts.<n>.jsonl`, a verdict per problem (change, leave or unknown, with the reason), and the change lists `changes.<n>.jsonl` and `tags.<n>.jsonl`. Check that every problem but `untagged` and those about attachment files (*Tidying tags and collections* and *Attachment titles* below take those) has its verdict, and run the dry runs; an `unknown` is yours to look at, and what turns on the user goes into step 4's list. A DOI a judge chose then goes through step 2's `missing_abstract` line, so the item's empty fields join `fill.jsonl`.
4. **Confirm.** One list for the user: the judges' changes and the fill lines (the `-n` outputs of the commands that will write them), the merges and the trash (below), and the leaves, grouped, each with its reason. Wait for the user's word.
5. **Write.** Fields: `p2z.py update <file>`; tags and collections: `p2z.py tag <file>`; duplicates: `p2z.py merge`; the trash: `p2z.py trash`.
6. **Read back.** Run step 1 again on the same scope. Done when every problem the user approved fixing is gone from it, and the report groups what was left alone, with why. A leave is kept nowhere beyond this run's verdicts: the next tidy lists the problem and judges it again, a pair judged two papers too.

## Reading the library

JSON lines, each word's `-h` with examples: `p2z.py collections` (keys, names, paths), `tags` (the vocabulary, `--min-count`), `items` (by name, or `--collection <path>`, `--tag`), `search <words>` (what Zotero's search box finds), `children` (attachments and notes), `pdf` (where an item's PDFs are on disk, best version first).

## Structured packages

Every PDF has its package (SKILL.md, *Reading a library paper*); `p2z.py pdf` shows it as `package`. To make the missing ones, or to bring them all up to date after the paddleocr skill changed: `p2z.py package take --missing -o <dir>/` (or `--every`), with no item named for the whole library; parse the links with the paddleocr skill, `-o <dir>`, in background calls of about a hundred; then `p2z.py package put <dir>/*/`, which skips a folder the parse left unchanged. `trash`, `merge` and `update` carry a PDF's package along with it (trashed, moved, retitled, renamed after the citation key); after citation keys changed in Zotero itself, `p2z.py package names` renames the packages' files in place.

## Tidying tags and collections

Take one collection at a time. Draft per item what [tagging.md](tagging.md) prescribes — automatic tags kept, curated tags to add, tags proposed for removal, pre-scheme manual tags to rename when the user has released them, a collection change if any — as change lines for `p2z.py tag` in `<scratch>/tidy/tags.jsonl`, and show the change list. The items a tidy's lint reports `untagged` are tagged this way, read with `p2z.py items <their keys>`. For many items, tagging subagents (SKILL.md, *Handoffs*; tagging.md is their brief): put `p2z.py items --collection <path>` in shares of about 20 items, `<scratch>/tidy/items.<n>.jsonl`, and `p2z.py tags` in `<scratch>/tidy/library-tags.jsonl`, and fill in `<scratch>` and `<n>`. Each writes `<scratch>/tidy/tags.<n>.jsonl` and reports the new tags; you merge the shares (`cat <scratch>/tidy/tags.*.jsonl > <scratch>/tidy/tags.jsonl`):

```bash
p2z.py tag -n <scratch>/tidy/tags.jsonl
```

An entry's `tags` is the item's *complete* target set: include the automatic tags you are keeping, or the command removes them. An item that only needs something added, removed or taken out of one collection takes `add_tags` / `remove_tags` / `add_collection` / `remove_collection`, which leave the rest as it is (`-h` has the option forms: `--add-tag`, `--remove-collection` …). Run it without `-n` once the user confirms. The first batch calibrates the scheme with the user; later batches follow it. What to remove or merge: tagging.md, *Tidying existing items*. An item whose metadata is broken (no date, venue or DOI) goes on the list for a field fix; a tag batch changes only tags and collections.

## Fixing fields

```bash
p2z.py update -n <citation key> --set itemType=conferencePaper --set "publicationTitle=…" --set date=2023
```

A paper without a DOI gets the identifier import.md step 3 asks for — often the DOI exists (a CVF copy of a CVPR paper, a Springer chapter), and paper-fetch's `pf.py identify --search` (*A tidy*, step 2) finds it by title and first author. Show the dry-run, write on the user's word, and name the source of every value you set against the DOI record (the PDF's author list, a corrected date). Tags and collections are `p2z.py tag`'s; the trash has its own section below.

## Attachment titles

Every PDF and snapshot is titled `<Version>-<Source>-<detail>`, and which of a paper's files an item keeps follows from those titles (references/attachment-titles.md). Files that came in another way — the Zotero Connector, Zotero's "Find Available PDF", an older run of this skill — carry titles outside the scheme ("PDF", "Full Text PDF", "Preprint (arXiv)"), and those say nothing about the version. What a file is, paper-fetch settles (SKILL.md, *Sibling skills*); this skill lists the files and writes the titles back. Renaming them:

1. **List.** `p2z.py lint` over the scope: each `nonstandard_title` comes with its evidence (the attachment's url and its site, the item's DOI); `label_clash` names files under one title (`same_file`: the same md5 twice, or two files); `superseded` a file another from the same source replaces.
2. **Label by paper-fetch**, every file in one directory, `<scratch>/paper-fetch/label`, as its *Label files you already have* says: `identify` all the items at once, with the citation key as the key (an item without a DOI or arXiv id by its url; a stub still takes its files), then `pf.py claim --dir <scratch>/paper-fetch/label --file <the attachment's stored file> --slug <slug>` per file, `<slug>` the result's slug, the citation key in file-safe form, as `identify` printed it (`p2z.py pdf <citation key>` gives the path; the file is copied, never moved); its judges settle every label. A snapshot needs no file check: `Snapshot-<the site of the page it saved>`.
3. **Titles from the labels.** `p2z.py retitle <scratch>/paper-fetch/label > <scratch>/titles.jsonl` finds each labelled file's attachment by its md5 and writes a change line where the title differs; add a line per snapshot to rename. A file whose version stayed unknown is titled `Unknown-<Source>` when its source is known. A `not_filed` line on stderr is a file of the paper that paper-fetch gave no label, its `why` saying so: `refused` (not the paper), `held` (still waiting on an agent: its judges are not done) or `withdrawn` (set aside for a confirmed copy). A refused file that names a library attachment (`key`) means that item holds a file that is not its paper's.
4. **Show the list** to the user: `p2z.py update -n <scratch>/titles.jsonl` (per attachment the item's citation key, the old title, the new one, the reason and who settled it, carried in the lines); beside it the `label_clash` and `superseded` findings, each with the file you would trash, and every `not_filed` attachment, for the user to decide.
5. **Write** on the user's word: `p2z.py update <scratch>/titles.jsonl` (a PDF's structured package is retitled with it), the trash per the next section. Then run step 1 again on the same scope: done when every title the user approved is in place and the findings left are the ones the user chose to keep. Delete paper-fetch's directory once the titles are written.

## The trash

Superseded attachments (a file another from the same source replaces, a snapshot standing in for a PDF that is now attached), duplicate items the user agreed to drop, stray attachments: list them first — `p2z.py trash -n <citation key>` (an attachment by its key) shows item type, title and parent — and move them only after the user has confirmed the list. The trash is a 30-day undo: `--restore` brings an item back, and Zotero deletes for good what has sat in the trash longer (its `trashAutoEmptyDays` setting, 30 by default; unchanged on this user's Zotero, 2026-10-18). Nothing here empties the trash. So what goes there is what the user would not miss: for a duplicate, `p2z.py merge` first carries over everything it holds.

## Duplicate items

Two items for one paper (`duplicate_of` by DOI or arXiv id; by title alone, read both first, and a preprint/published pair is the user's call before any of this): choose the one to keep — the fuller one, usually with the published version's DOI and PDF — and show the user the plan:

```bash
p2z.py merge -n <the duplicate> --into <the item that stays>
```

For each of its `conflicts` (left as the kept item has them), say which value you would choose and why; `p2z.py update` sets it on the user's word. On the user's word, run the merge without `-n`, then trash the dropped item with the `p2z.py trash -n` line it prints (`next`), and without `-n` once the user saw that too. Zotero's own "Merge Items" keeps the master's fields only and brings the other item's collections along (`tmp` included, 2026-09); `p2z.py merge` loses nothing and adds nothing.

## Building structure

`p2z.py mkcol "<parent's path>/<name>"` creates a collection the user asked for, once: a rerun answers `skipped` (`exists`) with its key, so a structure can be declared repeatedly. Only structure the user named is built: a single import invents no collections, and `tmp` is the only one created unasked.

## Notes

Outside Zotero a note is one Markdown file: a front matter that names the note and where it belongs, then the note, with whatever Markdown cannot say kept as HTML in place, so a file put back unedited leaves the note as it was. Work on notes in the scratch directory:

```bash
p2z.py note take <citation key> -o <scratch>/notes/   # a file per child note; a note's own key, that note
p2z.py note put <scratch>/notes/*.note.md -i           # back into Zotero; -i writes the new version into the file
```

- Edit between take and put and leave `key` and `version` as take wrote them. `version_conflict`: the note changed in Zotero after the take (the user edited it) — take it again into the same directory and redo your change there.
- A new note is a file without `key`: `parent: <citation key>` makes it a child note; `collections:` and `related:` (citation keys) a standalone one, related both ways. Zotero keeps no other front-matter field, so `put` refuses one (`bad_front_matter`): what it would say goes in the note's text.
- Raw HTML blocks stand on their own lines with a blank line around them. Inline code stays out of links and bold: the editor drops the link or the bold when it saves. A heading holds no math in the editor, so a `$…$` there stays its TeX text.
- `p2z.py note search "<words>"` finds notes by their text.

Use notes for what the user asked you to keep with a paper — page numbers, quoted passages, what you verified — and name the attachment the claims rest on. The user's own notes change only when they ask. Notes carry no tags: a tag on a note would sit in the tag selector beside the papers' tags.

## Exporting BibTeX

```bash
p2z.py export --collection <path> -o ref.bib      # or citation keys, or record paths
```

Keys are the items' `citationKey`s, so a manuscript that cites them compiles unchanged; on exit 1 the stderr summary names items without a key, with a shared key, or with a key holding a TeX-special character (and the key without it) — fix those with `p2z.py update <key> --set citationKey=…` on the user's word. The .bib is a derived file: regenerate it rather than editing it, and tell the user that Better BibTeX's auto-export can keep it current without an agent.
