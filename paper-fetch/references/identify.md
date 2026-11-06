# Identify only

Read when a caller wants which paper it is and what is known about it, and no file: a citation to complete, a list to check against Crossref, a .bib to key, a library item whose DOI is missing.

```bash
pf.py identify -o <dir>/ <ids...>                 # or - for a list on stdin: `id[<TAB>key]` per line
pf.py search <title> --author <surname>           # Crossref's top five; writes nothing
```

- The lines report what was done; the metadata is in the result files (`scripts/pflib/run.py` documents every field, `pf.py identify -h` where each comes from). Each line's code and hint say where identify stopped short; SKILL.md's *Identify a paper* says who takes a `needs_pinning` title, a `page_unreachable` page and a preprint's published versions.
- `search` lists Crossref's top five in its own order, with authors, the title's similarity and `first_author_differs`: which one is the paper is yours, or for several titles judges' (SKILL.md, *Identify a paper*) — confirm the title and first author before identifying its DOI.

No `ready`, no watcher and no browser are needed (but for an unreachable page, or a title only a browser finds): everything here is metadata over plain HTTP, paced per host through the machine's pace file (`~/.cache/paper-fetch/pace.json`).
