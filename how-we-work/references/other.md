---
name: other
description: "Rules for a kind of work that has no reference of its own, each under a heading that names the kind. The project's file holds such rules of the project's, and opens with the list of the kinds that do have a file."
trigger: "before work of a kind that the sync lists from the project's `docs/conventions/other.md`, and before writing down a rule for a kind of work that has no reference."
---

# Other kinds of work

A rule for one kind of work stands in the file read when that work begins: the reference of its kind, and in a project `docs/conventions/<name>.md` of the same name. This reference and the project's `docs/conventions/other.md` take the rules whose kind of work has no reference yet, so that they need not stand in `AGENTS.md`, where every turn would carry them.

## The project's file

`hww.py add other` makes it, and the sync keeps its opening current: between two marker comments, one line for each kind of work that has a file of its own, with that reference's `description`. Below them the project's entries stand under `## ` headings, one per kind of work.

**Following it.** At the start of a session the sync prints the file's headings and nothing else. When the work turns to one of those kinds, read that heading's section then.

**Writing into it.**

- **First look for the rule's kind in the opening list.** A rule one of those descriptions covers goes into that kind's file (`hww.py add <name>` makes it), and a rule for every task into `AGENTS.md` outside the block. This file takes what is left.
- **Every entry stands under a `## ` heading that names its kind of work** (`## Code`, `## Notebooks`), the name you would give a reference for it. Before making a heading, read the ones the file has: a rule joins the heading it belongs to. An entry has the form the records reference gives for a convention file.
- **When the sync says the list changed**, a kind may have gained a file of its own, or a description may now cover more: read the headings below the list, and move an entry that now belongs to one of the listed files.

## From here to a reference of its own

A heading that gathers several rules, or that stands in two projects, is the evidence that its kind of work deserves a reference. The session of the skills repository sees it when it reconciles the projects (the maintaining reference) and puts it to the user. Once the reference exists, the entries move to the project's file of that name.

## The common rules

None yet. A rule that holds in every project, for a kind of work without a reference, stands below under a heading that names the kind.
