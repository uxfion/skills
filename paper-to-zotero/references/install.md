# Setting up

Read when `ready.py` reports something missing. Each piece below says what needs it and how it is put in place; settings in the user's own programs are the user's to approve. Fetching (poppler, OpenCLI and Chrome, the institution's login) is paper-fetch's: its own `references/install.md`.

## The skill itself

The scripts share one library, `scripts/p2zlib/`, a subdirectory the skill installs with it (`npx skills add` copies the whole folder). After installing or updating, `uv run scripts/p2z.py --help` lists every command; an error naming `p2zlib` means the folder came without it — install the skill again. The sibling skills each operation needs, and what happens without them, are in SKILL.md, *Sibling skills*: install them beside this one the same way.

## Zotero

Zotero 10 or newer, running, with the local API on: Settings → Advanced → "Allow other applications on this computer to communicate with Zotero" (`local_api_disabled` otherwise). The write key comes from `p2z.py ready --authorize`: Zotero shows a dialog and the user must click **Always Allow** ("Allow" gives a single-use key). Tell the user before running it.

## The config file

`~/.config/paper-to-zotero/config.json` (`$PAPER_TO_ZOTERO_CONFIG` points elsewhere, for tests), mode 600, outside any repository, holds the write key:

```json
{"zotero": {"key": "…", "serverID": "…", "created": "…"}, "automatic_tags": false}
```

`p2z.py ready --authorize` writes the key and keeps any other field. `automatic_tags` is the user's: `true` gives drafted items the source's own keywords as automatic tags (references/tagging.md); absent or `false`, none. An older version kept the OpenAlex key and the institution's proxy and discovery page here too; paper-fetch reads them from its own config now, and `ready` names them under `config.moved` while they remain. `ready.py` warns when others can read the file.
