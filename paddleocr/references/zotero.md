# A paper in Zotero

The user names a paper by title, author or citation key; `parse.py` needs its PDF's path. The `paper-to-zotero` skill reads the library (read-only here):

```bash
cd <paper-to-zotero skill dir>
uv run scripts/read_library.py items --q '<author surname or title words>'   # or --cite <citation key>
uv run scripts/read_library.py children <item key>
```

`items` prints whole records, abstracts included; a surname plus a title word narrows the search best. In `children`, take the attachment with `contentType: application/pdf` and note its key. The local API redirects that attachment to its file:

```bash
u=$(curl -s -o /dev/null -w '%{redirect_url}' http://127.0.0.1:23119/api/users/0/items/<attachment key>/file)
printf '%b\n' "${u//%/\\x}"        # percent-decoded file:// URL
```

Drop the prefix: `file://` before a Linux path (`/home/…`), `file:///` before a Windows one (`C:/…`), which `wslpath -u` turns into a WSL path. Zotero file names carry spaces and often non-ASCII characters, so quote the path. Parse the PDF where it is; the output goes to your `<outdir>`, never into Zotero's storage folder.
