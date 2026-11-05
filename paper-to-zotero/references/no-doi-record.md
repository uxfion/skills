# No DOI record

Context for import.md, step 5 (`attach` answers `unchecked`).

paper-fetch could not identify the paper from a record — its result is a stub (`no_csl_record`, `page_unreachable`, `no_citation_meta`) — but the paper's PDF is in hand, filed as `cannot_judge`. Zotero's recognizer identifies a paper from its PDF, and `recognize` hands the file to it:

```bash
mkdir -p <imp>/recognize
p2z.py recognize <imp>/records/<slug>.json >> <imp>/recognize/recognize.jsonl
```

The PDF goes through the connector into the collection selected in the user's Zotero window, and the item the recognizer makes lands there too: the run's one message of questions says so (batch.md, *Ask once, then run*). Its line per record, appended to `recognize.jsonl` for the judges:

- `recognized`: the record's `saved` names the item the recognizer made (`via: recognizer`), and the line holds the item's fields and the PDF's path. Then:
  1. Recognizer judges (SKILL.md, *Handoffs*; their brief is [recognizer-judge.md](recognizer-judge.md)) compare the fields with the PDF's first page: each dispatch fills in `<imp>`, `<n>` and its items' keys. What comes back, in `<imp>/recognize/`: `verdicts.<n>.jsonl`, a verdict per item, and `changes.<n>.jsonl`, the fields to set from the page.
  2. Check that each item has its verdict, run `p2z.py update -n <imp>/recognize/changes.<n>.jsonl`, then without `-n`; an `unknown` is yours to settle from the page.
  3. The item's curated tags go into the paper's tags file, `<imp>/tags/<slug>.json` ([tagging.md](tagging.md)). `save` never creates this item, so this step is what tags it: `p2z.py tag <key> --set-collection <the record's collection> --add-tags-file <imp>/tags/<slug>.json` files it in its own collection, out of the one it landed in, and tags it (several collections: `--set-collection` once each).
  4. `save` as usual, which finds the PDF already attached.
- `not_recognized`: the recognizer found nothing, and the attachment this run sent is in the trash already. Write the record's `item` by hand from the PDF's first page (`p2z.py check -h` prints a skeleton), then `prepare`, the paper's tags file as for any paper (import.md step 3), and `save`: the item is made from this PDF, so `save` attaches it.
- `recognizing`: the recognizer is still at work (Zotero offline retries it every minute): run `recognize` again later; nothing is sent twice.
- `in_library`: the library holds this very PDF already, nothing was sent. Under an item (`parent`): the paper is there, which the report says. `parent: null`: a stray standalone copy; once it is in the trash (`p2z.py trash`, on the user's word), run `recognize` again.

Done when every stub record has its item in the library (`saved`) with the PDF attached, filed in its collection and tagged from its tags file, or is named in the report with what stopped it.
