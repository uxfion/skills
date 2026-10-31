# Identify only

Read when a caller wants which paper it is and what is known about it, and no file: a citation to complete, a list to check against Crossref, a .bib to key, a library item whose DOI is missing.

```bash
uv run scripts/pf.py identify -o <dir> <ids...>                 # or stdin: `id[<TAB>key]` per line
uv run scripts/pf.py identify --search "<title>" --author <surname>   # Crossref's top five; writes nothing
```

- Read the result files, not the lines: `csl` (CSL-JSON in CSL's own vocabulary, `source` the catalogue it came from; the abstract, PMID and PMCID from OpenAlex and Europe PMC where doi.org gave none), `ids`, `cite` (the key as given), `wanted`, `record_of`, `versions`, `alt_titles`, `warnings` (an erratum-like title, a date taken from another field, a sales-page DOI, where an abstract came from). `scripts/pflib/run.py` documents every field. identify writes no author keywords.
- A `title:` line is `needs_pinning`: a title is pinned by hand (SKILL.md, *Identify a paper*), and `--search` is one way.
- `--search` lists Crossref's top five in its own order, with authors, the title's similarity and `first_author_differs`: which one is the paper is a judge's call or yours — confirm the title and first author before identifying its DOI.
- `versions.incomplete` and `enrichment.incomplete` name sources that did not answer; identifying the same id again asks them again, and what they gave before stays meanwhile (the files already got stay too).
- `page_unreachable`: the page refuses plain HTTP. A browser agent saves its HTML into `<dir>/scratch/`; `identify --redraft <page url> <result> --html <file>` reads it through the same parser.
- `slug_taken`: the key's slug names another paper's result in that directory — give another key, or another directory.

No `ready`, no watcher and no browser are needed (but for an unreachable page): everything here is metadata over plain HTTP, paced per host through the machine's pace file (`~/.cache/paper-fetch/pace.json`).
