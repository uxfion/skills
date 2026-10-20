# Setting up

Read when `ready.py` reports something missing. Each piece below says what needs it and how it is put in place; system packages and settings in the user's own programs are the user's to approve.

## Zotero

Zotero 10 or newer, running, with the local API on: Settings → Advanced → "Allow other applications on this computer to communicate with Zotero" (`local_api_disabled` otherwise). The write key comes from `ready.py --authorize`: Zotero shows a dialog and the user must click **Always Allow** ("Allow" gives a single-use key). Tell the user before running it. The key is stored in the config file below.

## poppler-utils (required)

`check_pdf.py` reads PDFs with `pdftotext` and `pdfinfo`; without them nothing can be checked, so nothing is attached (`no_pdftotext` from `ready.py`, `no_extractor` from `check_pdf.py`). It is a system package: show the user the command and run it on their word.

```bash
sudo apt install poppler-utils      # Debian / Ubuntu / WSL
brew install poppler                # macOS
```

`command -v pdftotext pdfinfo` confirms it.

## OpenCLI and Chrome

Fetching from publisher pages drives the user's own Chrome through OpenCLI and its bridge extension: the `opencli-usage` skill covers installing and checking it. Chrome must be set to download PDFs rather than show them (references/publishers.md, first section).

## The config file

One file holds every setting and secret: `~/.config/paper-to-zotero/config.json` (`$PAPER_TO_ZOTERO_CONFIG` points elsewhere, for tests), mode 600, outside any repository. Every field is optional; a missing one turns its feature off, and `ready.py` says which are set without printing any value.

```json
{
  "zotero": {"key": "…", "serverID": "…"},
  "openalex_key": "…",
  "institution": {"proxy": "<proxy-domain>", "discovery": "<discovery-url>"}
}
```

- `zotero` — written by `ready.py --authorize`; the write scripts read nothing else.
- `openalex_key` — the user's OpenAlex API key (openalex.org, free): `fulltext_links.py` sends it with each lookup, which makes single-DOI lookups free of the daily budget. Without it the lookups run unkeyed.
- `institution.proxy` — the domain of the institution's EZproxy-style proxy, so that pages behind it are recognised (`fetch.py`, `lint_items.py`) and links under it are marked as needing the browser.
- `institution.discovery` — the library's discovery search page (a Primo search URL with its `vid`): `fetch.py --via discovery` searches titles there. `ready.py` asks for it (`ask_user`) when it is missing.

Write the file with `chmod 600`; `ready.py` warns when others can read it.
