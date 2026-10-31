# Setting up

Read when `ready.py` reports something missing. Each piece below says what needs it and how it is put in place; system packages and settings in the user's own programs are the user's to approve.

## The skill itself

The scripts share one library, `scripts/pflib/`, a subdirectory the skill installs with it (`npx skills add` copies the whole folder). After installing or updating, `uv run scripts/pf.py --help` lists every command; an error naming `pflib` means the folder came without it — install the skill again.

## poppler-utils (required)

Every file is checked with `pdftotext` and `pdfinfo` before it is filed; without them nothing can be checked, so nothing is filed (`no_pdftotext`, from `ready` and from every script that checks a file). It is a system package: show the user the command and run it on their word.

```bash
sudo apt install poppler-utils      # Debian / Ubuntu / WSL
brew install poppler                # macOS
```

`command -v pdftotext pdfinfo` confirms it.

## OpenCLI and Chrome

Fetching drives the user's own Chrome — headed, signed in to their library — through OpenCLI: a CLI, a local daemon, and the Browser Bridge extension in Chrome. A direct request comes first everywhere; the browser takes what needs the user's login or a human check. `ready` reports `opencli` (path, version, extension connected) and the issues `opencli doctor` names.

- **OpenCLI 2.x.** The scripts call `opencli browser <command> --session <name>` and read its `{"ok", "data"}` results, which OpenCLI 1.x does not have: there every browser step fails. Install or upgrade it the way it was installed — `npm install -g @jackwener/opencli@latest`, `bun add -g @jackwener/opencli@latest`, or the OpenCLI app (opencli.info) — a system tool, so show the user the command and run it on their word. The `opencli-usage` skill covers the details.
- **After an upgrade**, `opencli daemon restart` (doctor: "Stale daemon"). The Chrome extension is updated apart from the CLI, by the user: from the Chrome Web Store, or by hand from the OpenCLI releases (doctor: "Extension update available").
- **The `opencli-usage` and `opencli-browser` skills** come from `jackwener/opencli` and describe the installed CLI only when updated with it: `skills update -g`. `opencli skills read opencli-browser -f plain` prints the one bundled with the CLI, to compare.
- **Chrome's downloads.** Every file reaches the run through Chrome's download folder. Two Chrome settings are the user's to set (automation cannot open `chrome://` pages): PDFs download rather than open, and no Save As prompt — references/publishers.md, first section. `ready` finds the folder (on WSL, the Windows user's Downloads) and writes it to `run.json` as `downloads`; `ready --downloads DIR` names another. The watcher files only what lands there.

## The config file

One file holds every setting and secret: `~/.config/paper-fetch/config.json` (`$PAPER_FETCH_CONFIG` points elsewhere, for tests), mode 600, outside any repository. Every field is optional; a missing one turns its feature off, and `ready.py` says which are set without printing any value.

```json
{
  "openalex_key": "…",
  "institution": {"proxy": "<proxy-domain>", "discovery": "<discovery-url>"}
}
```

- `openalex_key` — the user's OpenAlex API key (openalex.org, free): `fulltext_links.py` sends it with each lookup, which makes single-DOI lookups free of the daily budget. Without it the lookups run unkeyed.
- `institution.proxy` — the domain of the institution's EZproxy-style proxy, so that pages behind it are recognised (`fetch.py`) and links under it are marked as needing the browser.
- `institution.discovery` — the library's discovery search page (a Primo search URL with its `vid`): `fetch`'s discovery route searches titles there. `ready` asks for it (`ask_user`) when it is missing.

Write the file with `chmod 600`; `ready.py` warns when others can read it.
