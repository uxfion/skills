# No DOI record

Context for import.md, step 5 (`attach_file` answers `unchecked`).

paper-fetch could not identify the paper from a record — its result is a stub (`no_csl_record`, `page_unreachable`, `no_citation_meta`) — but the paper's PDF is in hand, filed as `cannot_judge`. Zotero's recognizer identifies a paper from its PDF, and `recognize` hands the file to it:

```bash
uv run scripts/p2z.py recognize <imp>/records/<slug>.json
```

It sends the PDF through the connector under its label title — into the collection selected in the user's Zotero window — and waits for the recognizer (`--wait`, 60 s by default). Its line per record:

- `recognized`: the record's `saved` names the item the recognizer made (`via: recognizer`), and the line holds the item's fields and the PDF's path. A judge compares the fields with the PDF's first page (title, authors, venue, year, DOI). What is wrong or missing, `update_item` sets from that page; `file_and_tag` files the item and tags it (it landed where the window was); then `save` as usual, which finds the PDF already attached.
- `not_recognized`: the recognizer found nothing, and the attachment this run sent is in the trash already. Write the record's `item` by hand from the PDF's first page (`p2z.py check_item --help` prints a skeleton), then `prepare` and `save`.
- `recognizing`: the recognizer is still at work (Zotero offline retries it every minute): run `recognize` again later; nothing is sent twice.
- `in_library`: the library holds this very PDF already, under the item the line names: the paper is there, which the report says.

Done when every stub record has its item in the library (`saved`) with the PDF attached, or is named in the report with what stopped it.
