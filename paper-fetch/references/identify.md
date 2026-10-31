# Identify only

Read when a caller wants which paper it is and what is known about it, and no file: a citation to complete, a list to check against Crossref, a .bib to key, a library item whose DOI is missing.

```bash
uv run scripts/pf.py identify -o <dir> <ids...>                 # or stdin: `id[<TAB>slug]` per line
uv run scripts/pf.py identify --search "<title>" --author <surname>   # Crossref's candidates; writes nothing
```

- Read the result files, not the lines: `csl` (CSL-JSON in CSL's own vocabulary, `source` the catalogue it came from), `ids`, `record_of`, `versions`, `alt_titles`, `warnings` (an erratum-like title, a date taken from another field, a sales-page DOI). `scripts/pflib/run.py` documents every field.
- A `title:` line is `needs_pinning`: a title is pinned by hand (SKILL.md, *Identify a paper*), and `--search` is one way.
- A candidate from `--search` is a candidate: confirm the title and first author before identifying its DOI.
- `versions.incomplete` names sources that did not answer; identifying the same id again asks again (the files already got stay).
- `slug_taken`: the slug names another paper's result in that directory — give another slug, or another directory.

No `ready`, no watcher and no browser are needed: everything here is metadata over plain HTTP, paced per host through the machine's pace file (`~/.cache/paper-fetch/pace.json`).
