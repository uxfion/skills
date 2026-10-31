# Organize existing items

The second entry: the user asks for tags or collections to be tidied, a field fixed, duplicates merged, a structure built, a note attached, or a collection exported as BibTeX. Every command runs as `uv run scripts/p2z.py <command> …`.

## A tidy: check, judge, confirm, write, read back

A request to tidy a collection (整理) runs these steps, working in `<scratch>/tidy/`; a single fix the user names starts at step 3. The collection 主题笔记 holds paper-read's topic notes: a tidy leaves it and its notes as they are.

1. **Check.** `uv run scripts/p2z.py lint_items --collection <key> [--recursive] > <scratch>/tidy/lint.jsonl` reads the whole library once and lists each item in scope that has a problem, each problem a fact with its evidence (`--help` lists the codes). Done when the summary line is in hand.
2. **Look up what is missing** with paper-fetch (SKILL.md, *Sibling skills*), for the judges to read:
   - `missing_doi`: per item, `uv run ../paper-fetch/scripts/pf.py identify --search "<title>" --author <surname> > <scratch>/tidy/search/<key>.jsonl` (Crossref's top five, unfiltered);
   - `missing_abstract` on an item with a DOI: `printf '<DOI>\t<citation key>\n' … | uv run ../paper-fetch/scripts/pf.py identify -o <scratch>/tidy/fetch`, then `uv run scripts/p2z.py fields_from_results <scratch>/tidy/fetch/results/*.json -o <scratch>/tidy/fill.jsonl` — the item's empty fields from its DOI record, nothing overwritten.

   Done when every `missing_doi` item has its search file and `fields_from_results` has run over every `missing_abstract` item with a DOI.
3. **Judge.** Lint's lines go to judges (SKILL.md, *Handoffs*; here a case is one item), reading only `<scratch>/tidy/`. The brief: for every problem of every item, a change or "leave", with the reason — a `duplicate_of` by title is the same paper, another one, or a preprint/published pair (the user's call); a url that is not the DOI's is a copy to replace, or the venue's own page the item keeps (NeurIPS 2022–2025, OpenReview: references/import.md step 3); swapped journal fields; which search candidate is the item's DOI (none is fine: ICML and ICLR issue none). It writes its changes as batch lines, `<scratch>/tidy/changes.<n>.jsonl` for `update_item --batch` (`{key | cite, set: {…}}`) and `tags.<n>.jsonl` for `file_and_tag --batch`, and reports one line per item, "leave" with its reason included. What it cannot settle it answers "unknown", for you to look at. A DOI a judge chose then goes through step 2's `missing_abstract` line, so the item's empty fields join `fill.jsonl`.
4. **Confirm.** One list for the user: the judges' changes and the fill lines (the `--dry-run` outputs of the commands that will write them), the merges and the trash (below), and what is left alone and why. Wait for the user's word.
5. **Write.** Fields: `update_item --batch <file>`; tags and collections: `file_and_tag --batch <file>`; duplicates: `merge_items`; the trash: `trash_item`.
6. **Read back.** Run step 1 again on the same scope. Done when every problem the user approved fixing is gone from it, and the report names what was left alone and why — a pair judged two papers is listed again by the next tidy, and left again.

## Reading the library

`read_library` is the generic read — JSON lines, paginated for you:

```bash
uv run scripts/p2z.py read_library collections --tree            # keys, names, paths ("/" between names)
uv run scripts/p2z.py read_library tags --min-count 2            # the existing vocabulary
uv run scripts/p2z.py read_library items --collection <key>      # every top-level item in a collection
uv run scripts/p2z.py read_library items --cite <citation key>   # one item, as the API returns it
uv run scripts/p2z.py read_library children --cite <citation key> # its attachments (content type, md5) and notes
uv run scripts/p2z.py read_library pdf --cite <citation key>     # where its PDFs are on disk, with their versions, best first
```

## Structured packages

Every PDF has its package (SKILL.md, *Reading a library paper*); `read_library pdf` shows it as `package`. To make the missing ones, or to bring them all up to date after the paddleocr skill changed: `structured take --missing -o <dir>` (or `--every`), with no item named for the whole library; parse the links with the paddleocr skill, `-o <dir>`, in background calls of about a hundred; then `structured put <dir>/*/`, which skips a folder the parse left unchanged. `trash_item`, `merge_items` and `update_item` carry a PDF's package along with it (trashed, moved, retitled, renamed after the citation key); after citation keys changed in Zotero itself, `structured names` renames the packages' files in place.

## Tidying tags and collections

Take one collection at a time. Draft per item what [tagging.md](tagging.md) prescribes — automatic tags kept, curated tags to add, tags proposed for removal, pre-scheme manual tags to rename when the user has released them, a collection change if any — as `file_and_tag --batch` lines in `<scratch>/tidy/tags.jsonl`, and show the change list. For many items, tagging subagents (about 20 items each) draft their shares from each item's title, abstract, venue and tags — the common name an abstract gives its model included — and you merge them:

```bash
uv run scripts/p2z.py file_and_tag --batch <scratch>/tidy/tags.jsonl --dry-run
```

An entry's `tags` is the item's *complete* target set: include the automatic tags you are keeping, or the command removes them. An item that only needs something added, removed or taken out of one collection takes `add_tags` / `remove_tags` / `add_collection` / `remove_collection`, which leave the rest as it is (`--help` has the command-line forms). Run it without `--dry-run` once the user confirms. The first batch calibrates the scheme with the user; later batches follow it. What to remove or merge: tagging.md, *Tidying existing items*. An item whose metadata is broken (no date, venue or DOI) goes on the list for a field fix; a tag batch changes only tags and collections.

## Fixing fields

```bash
uv run scripts/p2z.py update_item --cite <key> --set itemType=conferencePaper --set "publicationTitle=…" --set date=2023 --dry-run
```

A paper without a DOI gets the identifier import.md step 3 asks for — often the DOI exists (a CVF copy of a CVPR paper, a Springer chapter), and paper-fetch's `pf.py identify --search` (*A tidy*, step 2) finds it by title and first author. Show the dry-run, write on the user's word, and name the source of every value you set against the DOI record (the PDF's author list, a corrected date). Tags and collections are `file_and_tag`'s; the trash has its own section below.

## Attachment titles

Every PDF and snapshot is titled `<Version>-<Source>-<detail>`, and which of a paper's files an item keeps follows from those titles (references/attachment-titles.md). Files that came in another way — the Zotero Connector, Zotero's "Find Available PDF", an older run of this skill — carry titles outside the scheme ("PDF", "Full Text PDF", "Preprint (arXiv)"), and those say nothing about the version. What a file is, paper-fetch settles (SKILL.md, *Sibling skills*); this skill lists the files and writes the titles back. Renaming them:

1. **List.** `lint_items` over the scope: each `nonstandard_title` comes with its evidence (the attachment's url and its site, the item's DOI); `label_clash` names files under one title (`same_file`: the same md5 twice, or two files); `superseded` a file another from the same source replaces.
2. **Label by paper-fetch**, every file in one directory, `<scratch>/paper-fetch/label`, as its *Label files you already have* says: `identify` all the items at once, with the citation key as the key (an item without a DOI or arXiv id by its url; a stub still takes its files), then `pf.py claim --dir <scratch>/paper-fetch/label --file <the attachment's stored file> --slug <citation key>` per file (`read_library pdf --cite …` gives the path; the file is copied, never moved); its judges settle every label. A snapshot needs no file check: `Snapshot-<the site of the page it saved>`.
3. **Titles from the labels.** `uv run scripts/p2z.py titles_from_labels <scratch>/paper-fetch/label -o <scratch>/titles.jsonl` finds each labelled file's attachment by its md5 and writes a batch line where the title differs; add a line per snapshot to rename. A file whose version stayed unknown is titled `Unknown-<Source>` when its source is known.
4. **Show the list** to the user: `update_item --batch <scratch>/titles.jsonl --dry-run` (per attachment the item's citation key, the old title, the new one, the reason and who settled it, carried in the lines); beside it the `label_clash` and `superseded` findings, each with the file you would trash.
5. **Write** on the user's word: `update_item --batch <scratch>/titles.jsonl` (a PDF's structured package is retitled with it), the trash per the next section. Then run step 1 again on the same scope: done when every title the user approved is in place and the findings left are the ones the user chose to keep. Delete paper-fetch's directory once the titles are written.

## The trash

Superseded attachments (a file another from the same source replaces, a snapshot standing in for a PDF that is now attached), duplicate items the user agreed to drop, stray attachments: list them first — `trash_item --cite <key> --dry-run` (or `--key` for an attachment) shows item type, title and parent — and move them only after the user has confirmed the list. The trash is a 30-day undo: `--restore` brings an item back, and Zotero deletes for good what has sat in the trash longer (its `trashAutoEmptyDays` setting, 30 by default; unchanged on this user's Zotero, 2026-10-18). Nothing here empties the trash. So what goes there is what the user would not miss: for a duplicate, `merge_items` first carries over everything it holds.

## Duplicate items

Two items for one paper (`duplicate_of` by DOI or arXiv id; by title alone, read both first, and a preprint/published pair is the user's call before any of this): choose the one to keep — the fuller one, usually with the published version's DOI and PDF — and show the user the plan:

```bash
uv run scripts/p2z.py merge_items --keep <key> --drop <key> --dry-run
```

For each of its `conflicts` (left as the kept item has them), say which value you would choose and why; `update_item` sets it on the user's word. On the user's word, run the merge without `--dry-run`, then trash the dropped item with the `trash_item` line it prints, after showing that `--dry-run` too. Zotero's own "Merge Items" keeps the master's fields only and brings the other item's collections along (`tmp` included, 2026-09); `merge_items` loses nothing and adds nothing.

## Building structure

`make_collection --name "<name>" --parent <key>` creates a collection the user asked for, once: a rerun answers `skipped` (`exists`) with its key, so a structure can be declared repeatedly. Only structure the user named is built: a single import invents no collections, and `tmp` is the only one created unasked.

## Notes

Outside Zotero a note is one Markdown file: a front matter that names the note and where it belongs, then the note, with whatever Markdown cannot say kept as HTML in place, so a file put back unedited leaves the note as it was. Work on notes in the scratch directory:

```bash
uv run scripts/p2z.py note take --cite <key> -o <scratch>/notes/      # a file per child note; --title T picks one, --note K a standalone one
uv run scripts/p2z.py note put <scratch>/notes/*.note.md -i            # back into Zotero; -i writes the new version into the file
```

- Edit between take and put and leave `key` and `version` as take wrote them. `version_conflict`: the note changed in Zotero after the take (the user edited it) — take it again into the same directory and redo your change there.
- A new note is a file without `key`: `parent: <citation key>` makes it a child note; `collections:` and `related:` (citation keys) a standalone one, related both ways.
- Raw HTML blocks stand on their own lines with a blank line around them. Inline code stays out of links and bold: the editor drops the link or the bold when it saves. A heading holds no math in the editor, so a `$…$` there stays its TeX text.
- `note list --q <words>` finds notes by their text.

Use notes for what the user asked you to keep with a paper — page numbers, quoted passages, what you verified — and name the attachment the claims rest on. The user's own notes change only when they ask. Notes carry no tags: a tag on a note would sit in the tag selector beside the papers' tags.

## Exporting BibTeX

```bash
uv run scripts/p2z.py export_bib --collection <key> -o ref.bib      # or --cite k1,k2 …, or record paths
```

Keys are the items' `citationKey`s, so a manuscript that cites them compiles unchanged; the stderr summary names items without a key, with a shared key, or with a key holding a TeX-special character (and the key without it) — fix those with `update_item --set citationKey=…` on the user's word. The .bib is a derived file: regenerate it rather than editing it, and tell the user that Better BibTeX's auto-export can keep it current without an agent.
