# No DOI record

Context for import.md, step 5 (`attach_file` answers `unchecked`).

paper-fetch could not identify the paper from a record — its result is a stub (`no_csl_record`, `page_unreachable`, `no_citation_meta`) — but the paper's PDF is in hand, filed as `cannot_judge`. Zotero's recognizer identifies a paper from its PDF, and `recognize` hands the file to it:

```bash
uv run scripts/p2z.py recognize <imp>/records/<slug>.json
```

The PDF goes through the connector into the collection selected in the user's Zotero window, and the item the recognizer makes lands there too. Its line per record:

- `recognized`: the record's `saved` names the item the recognizer made (`via: recognizer`), and the line holds the item's fields and the PDF's path. A judge compares the fields with the PDF's first page (title, authors, venue, year, DOI). What is wrong or missing, `update_item` sets from that page; `file_and_tag` files the item and tags it; then `save` as usual, which finds the PDF already attached.
- `not_recognized`: the recognizer found nothing, and the attachment this run sent is in the trash already. Write the record's `item` by hand from the PDF's first page (`p2z.py check_item --help` prints a skeleton), then `prepare` and `save`. `save` creates the item, but `attach_file` takes only files a check passed, so it answers `unchecked` again: the PDF goes to the user with its path (SKILL.md, *The scratch directory*).
- `recognizing`: the recognizer is still at work (Zotero offline retries it every minute): run `recognize` again later; nothing is sent twice.
- `in_library`: the library holds this very PDF already, nothing was sent. Under an item (`parent`): the paper is there, which the report says. `parent: null`: a stray standalone copy; once it is in the trash (`trash_item`, on the user's word), run `recognize` again.

Done when every stub record has its item in the library (`saved`) with the PDF attached, or is named in the report with what stopped it.
