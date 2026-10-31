# No DOI record

Context for step 3 of [import.md](import.md).

paper-fetch could not identify the paper from a record (its result is a stub: `no_csl_record`, `page_unreachable`, `no_citation_meta`), or the paper has no identifier, but its PDF is in hand (paper-fetch filed it as `cannot_judge`, and you looked at it): let Zotero's recognizer identify it. Note the library version (`Last-Modified-Version` of `GET /api/users/0/items?limit=1`), send the PDF through the connector — one request, no key:

```bash
curl -s -X POST http://127.0.0.1:23119/connector/saveStandaloneAttachment \
  -H "Content-Type: application/pdf" -H "X-Metadata: {\"sessionID\":\"$(uuidgen)\",\"title\":\"paper.pdf\",\"url\":\"<source url>\"}" \
  --data-binary @<scratch>/paper-to-zotero/fetch/results/<slug>.pdf
```

Within a minute a parent item appears (`GET /api/users/0/items?since=<version>`); put its key into the record's `saved` (a record of your own, `<scratch>/paper-to-zotero/records/<slug>.json`, when `draft_item` had no metadata to make one from), revise it with `update_item` and finish with `file_and_tag` (it landed in whatever collection Zotero had selected). No parent after a minute: move the standalone attachment to the trash (`p2z.py trash_item --key`) and write the record's `item` by hand (`p2z.py check_item --help` prints a skeleton), then steps 5–7 as usual.
