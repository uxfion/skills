# Identify only

Read when a caller wants which paper it is and what is known about it, and no file: a citation to complete, a list to check against Crossref, a .bib to key, a library item whose DOI is missing.

```bash
pf.py identify -o <dir>/ <ids...>                 # or -: a list on stdin
pf.py search <title> --author <surname>           # Crossref's top five; writes nothing
```

The metadata is in the result files (`scripts/pflib/run.py` documents every field, `pf.py identify -h` where each comes from). Where a line stops short, and for a `search` candidate, SKILL.md's *Identify a paper* says who takes it.

Everything here is metadata over plain HTTP, so it needs no `ready`, watcher or browser, but for an unreachable page or a title only a browser finds.
