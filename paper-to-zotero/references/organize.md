# Organize existing items

The second entry: the user asks for tags or collections to be tidied, a field fixed, a structure built, a note attached, or a collection exported as BibTeX. Nothing here touches the import steps; the scripts are the same family, and every one of them takes `--cite <citation key>` wherever it takes `--key`.

## Reading the library

`read_library.py` is the generic read — JSON Lines, paginated for you:

```bash
uv run scripts/read_library.py collections --tree            # keys, names, paths
uv run scripts/read_library.py tags --min-count 2            # the existing vocabulary
uv run scripts/read_library.py items --collection <key>      # every top-level item in a collection
uv run scripts/read_library.py items --cite <citation key>   # one item, as the API returns it
uv run scripts/read_library.py children <item key>           # attachments and notes
```

`find_in_library.py --cite <key>` gives the same item with its attachments (content type, MD5), collection paths and tags — the shape the import steps use.

## Tidying tags and collections

Take one collection at a time. Draft per item what [tagging.md](tagging.md) prescribes — source keywords kept, curated tags to add, tags proposed for removal, pre-scheme manual tags to rename when the user has released them, a collection change if any — into `changes.json` and show the change list:

```bash
uv run scripts/file_and_tag.py --batch changes.json --dry-run
```

An entry's `tags` is the item's *complete* target set (include the source keywords you are keeping, or the script removes them); `collection` replaces the item's collections. An item that only needs something *added* takes `add_tags` / `add_collection` instead, which leave the rest as it is (single item: `--add-tags-file` / `--add-collection`). Only after the user confirms, run it without `--dry-run`. The first batch calibrates the scheme with the user; later batches follow it. An item whose metadata is broken (no date, venue or DOI) is noted for a field fix, not repaired in a tag batch.

## Fixing fields

```bash
uv run scripts/update_item.py --cite <key> --set itemType=conferencePaper --set "publicationTitle=…" --set date=2023 --dry-run
```

Base names such as `publicationTitle` are mapped to the type's own field; on a type change the plan lists the fields Zotero will move to Extra; the result shows any value Zotero normalized. Show the dry-run, write on the user's word, name the source of every value you set against the DOI record (the PDF's author list, a corrected date). Tags and collections stay with `file_and_tag.py`; the trash is the user's own act — nothing here deletes.

## Building structure

`make_collection.py --name "<name>" --parent <key>` creates a collection the user asked for and returns the existing one when it is already there (same name under the same parent), so a structure can be declared repeatedly without duplicates. Only structure the user named: a single import never invents collections, and `tmp` is the only one created unasked.

## Notes

`note.py --cite <key> --file note.md --marker <name>` attaches a child note (a small Markdown subset becomes Zotero's HTML) and, run again with the same marker, updates that note instead of adding another. Use it for evidence the user asked you to keep with the paper — page numbers, quoted passages, what you verified — and keep the user's own notes untouched. What a note claims about a paper's content rests on the attachment you read, so name it.

## Exporting BibTeX

```bash
uv run scripts/export_bib.py --collection <key> --out ref.bib      # or --cite k1 --cite k2 …, or record paths
```

Keys are the items' `citationKey`s, so a manuscript that cites them compiles unchanged; the stderr summary names items without a key or with duplicate keys — fix those with `update_item.py --set citationKey=…` on the user's word. The .bib is a derived file: regenerate it rather than editing it, and tell the user that Better BibTeX's auto-export can keep it current without an agent.
