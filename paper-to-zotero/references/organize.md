# Organize existing items

The second entry: the user asks for tags or collections to be tidied, a field fixed, duplicates merged, a structure built, a note attached, or a collection exported as BibTeX. Nothing here touches the import steps. Every command runs as `uv run scripts/p2z.py <command> …`; each command's `--help` has its flags, codes and output. Items are named by `--key` or `--cite <citation key>`, both repeatable or comma-separated. `trash_item`, `update_item`, `file_and_tag` and `note` print one JSON line per item, then a `{"summary"}` line; every command's exit 1 means something is yours to act on, 2 that Zotero could not be checked.

## A tidy: check, list, confirm, write, read back

A request to tidy a collection (整理) runs these five steps; a single fix the user names starts at step 2. The collection 主题笔记 holds paper-read's topic notes: a tidy leaves it and its notes as they are.

1. **Check.** `uv run scripts/p2z.py lint_items --collection <key> [--recursive]` reads the whole library once and lists each item of the collection that has a problem — duplicates anywhere in the library, stray webpages, attachment titles outside the scheme or clashing, a file another from the same source replaces, bad fields, a url that is not the version of record, a citation key that is missing, shared or holds a TeX-special character, a model name no tag carries (`--help` lists the codes). It reads only the library: for a `missing_doi`, paper-fetch's `identify --search "<title>" --author <surname>` looks the DOI up. Done when the summary line is in hand.
2. **List.** Turn the findings into one change list for the user: per item what you propose and why — the merge of a duplicate pair (below), the field fixes, the tags to add (references/tagging.md), what goes to the trash. A `patch` in a finding is mechanical and can go in as it is; every other code is yours to judge first — a venue that issues no DOI (ICML, ICLR) is expected under `missing_doi`, and a `duplicate_of` by title alone may be two papers. Done when every finding is in the list as a change or as left alone, with the reason.
3. **Confirm.** Show the list (the `--dry-run` outputs of the commands that will write it) and wait for the user's word on it; scope they grant holds for the rest of the task.
4. **Write.** Each change with its command: fields `update_item` (a `patch` goes in a file: `--patch FILE`), tags and collections `file_and_tag`, duplicates `merge_items`, the trash `trash_item`.
5. **Read back.** Run step 1 again on the same scope. Done when every problem the user approved fixing is gone from it, and the report names what was left alone and why.

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

Take one collection at a time. Draft per item what [tagging.md](tagging.md) prescribes — source keywords kept, curated tags to add, tags proposed for removal, pre-scheme manual tags to rename when the user has released them, a collection change if any — into `changes.json` and show the change list:

```bash
uv run scripts/p2z.py file_and_tag --batch changes.json --dry-run
```

An entry names its item by `key` or `cite`. Its `tags` is the item's *complete* target set (include the source keywords you are keeping, or the command removes them); `collection` replaces the item's collections. An item that only needs something *added* or taken out of one collection takes `add_tags` / `add_collection` / `remove_collection` instead, which leave the rest as it is (for items named on the command line: `--add-tags-file` / `--add-collection` / `--remove-collection`). Only after the user confirms, run it without `--dry-run`. The first batch calibrates the scheme with the user; later batches follow it. What to remove or merge: tagging.md, *Tidying existing items*. An item whose metadata is broken (no date, venue or DOI) is noted for a field fix, not repaired in a tag batch.

## Fixing fields

```bash
uv run scripts/p2z.py update_item --cite <key> --set itemType=conferencePaper --set "publicationTitle=…" --set date=2023 --dry-run
```

A paper without a DOI gets the identifier import.md step 3 asks for — often the DOI exists (a CVF copy of a CVPR paper, a Springer chapter), and paper-fetch's `identify --search` finds it by title and first author. Base names such as `publicationTitle` are mapped to the type's own field; on a type change the plan lists the fields Zotero will move to Extra; the result shows any value Zotero normalized. Zotero moves an Extra line it has a field for (`PMID: 38262200`) into that field when the field is empty: the result shows it under `normalized.extra.moved_to_fields`, which is a success — set such a field directly next time. Show the dry-run, write on the user's word, name the source of every value you set against the DOI record (the PDF's author list, a corrected date). Tags and collections stay with `file_and_tag`; the trash has its own section below.

## Attachment titles

Every PDF and snapshot is titled `<Version>-<Source>-<detail>`, and which of a paper's files an item keeps follows from those titles (references/attachment-titles.md). Files that came in another way — the Zotero Connector, Zotero's "Find Available PDF", an older run of this skill — carry titles outside the scheme ("PDF", "Full Text PDF", "Preprint (arXiv)"), and those say nothing about the version. What a file is, paper-fetch settles; this skill lists the files and writes the titles back. Renaming them:

1. **List.** `lint_items` over the scope: each `nonstandard_title` comes with its evidence (the attachment's url and its site, the item's DOI), `label_clash` names two files under one title, `superseded` a file another from the same source replaces.
2. **Label by paper-fetch.** Its *Label files you already have*: identify each item's paper by its DOI or arXiv id into a directory of its own (`-o <scratch>/paper-fetch/label`), then `claim --file` the attachment's stored file (`read_library pdf --cite …` gives its path; a file outside paper-fetch's directory is copied, never moved) and settle its label there — paper-fetch's rules for a file already in the library, its subagents for what is in doubt. A snapshot needs no file check: `Snapshot-<the site of the page it saved>`. Many files: paper-fetch's batch, by its rules.
3. **Unknown** for what is still undecided, with the source when that is known.
4. **Show the list** to the user: per attachment the item's citation key, the old title, the new one (the result's `files[].label.title`), the reason and who settled it; beside it the `label_clash` and `superseded` findings, each with the file you would trash.
5. **Write** on the user's word: `update_item --key <attachment> --set title=<new>` (a `--dry-run` first), the trash per the next section. Then run step 1 again on the same scope: done when every title the user approved is in place and the findings left are the ones the user chose to keep. Delete paper-fetch's directory once the titles are written.

## The trash

Superseded attachments (a file another from the same source replaces, a snapshot standing in for a PDF that is now attached), duplicate items the user agreed to drop, stray attachments: list them first — `trash_item --cite <key> --dry-run` (or `--key` for an attachment) shows item type, title and parent — and move them only after the user has confirmed the list. The trash is a 30-day undo: `--restore` brings an item back, and Zotero deletes for good what has sat in the trash longer (its `trashAutoEmptyDays` setting, 30 by default; unchanged on this user's Zotero, 2026-10-18). Nothing here empties the trash. So what goes there is what the user would not miss: for a duplicate, `merge_items` first carries over everything it holds.

## Duplicate items

Two items for one paper (`duplicate_of` by DOI or arXiv id; by title alone, read both first): choose the one to keep — the fuller one, usually with the published version's DOI and PDF — and show the user the plan:

```bash
uv run scripts/p2z.py merge_items --keep <key> --drop <key> --dry-run
```

It lists the fields the kept item will take from the other (empty ones only), the `conflicts` it leaves as they are (say which value you would choose and why; `update_item` sets it on the user's word), the collections and tags it adds, the PDFs and notes it moves under the kept item, and what stays with the dropped one. A preprint/published pair is the user's call before any of this. On the user's word, run it without `--dry-run`, then trash the dropped item with the `trash_item` line it prints, after showing that `--dry-run` too. Zotero's own "Merge Items" keeps the master's fields only and brings the other item's collections along (`tmp` included, 2026-09); `merge_items` loses nothing and adds nothing.

## Building structure

`make_collection --name "<name>" --parent <key>` creates a collection the user asked for; when it is already there (same name under the same parent) it answers `skipped` with `reason: exists` and its key, so a structure can be declared repeatedly without duplicates. Only structure the user named: a single import never invents collections, and `tmp` is the only one created unasked.

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

Use notes for what the user asked you to keep with a paper — page numbers, quoted passages, what you verified — and name the attachment the claims rest on. The user's own notes change only on their word. Notes carry no tags: a tag on a note would sit in the tag selector beside the papers' tags.

## Exporting BibTeX

```bash
uv run scripts/p2z.py export_bib --collection <key> --out ref.bib      # or --cite k1,k2 …, or record paths
```

Keys are the items' `citationKey`s, so a manuscript that cites them compiles unchanged; the stderr summary names items without a key, with a shared key, or with a key holding a TeX-special character (and the key without it) — fix those with `update_item --set citationKey=…` on the user's word. The .bib is a derived file: regenerate it rather than editing it, and tell the user that Better BibTeX's auto-export can keep it current without an agent.
