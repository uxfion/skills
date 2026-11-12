---
name: other
description: "Rules for a kind of work that has no reference of its own, each under a heading that names the kind. The project's file holds such rules of the project's, and opens with the list of the kinds that do have a file."
trigger: "before work of a kind that the sync lists from the project's `docs/conventions/other.md`, and before writing down a rule for a kind of work that has no reference."
---

# Other kinds of work

This reference and the project's `docs/conventions/other.md` take the rules whose kind of work has no reference yet; in `AGENTS.md` every turn would carry them.

## The project's file

`hww.py add other` makes it, and the sync keeps its opening current: between two marker comments, one line for each kind of work that has a file of its own, with that reference's `description`. Below them the project's entries stand under `## ` headings, one per kind of work.

**Following it.** The sync prints the file's headings at the start of a session. When the work turns to one of those kinds, read that heading's section.

**Writing into it.**

- **Read every line of the opening list first.** A rule one of those descriptions covers goes into that kind's file (`hww.py add <name>` makes it), and a rule for every task into `AGENTS.md` outside the block. This file takes what is left.
- **Every entry stands under a `## ` heading that names its kind of work** (`## Code`, `## Notebooks`), the name you would give a reference for it. Read the headings the file has before making one: a rule joins the heading it belongs to. An entry has the form the records reference gives for a convention file.
