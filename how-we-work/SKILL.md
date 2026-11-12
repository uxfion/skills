---
name: how-we-work
description: "The user's shared working rules for their research projects — the common block synced into each project's AGENTS.md, and one reference per kind of work. Use in a project whose AGENTS.md carries the how-we-work block: at the start of a session (sync), before an experiment or a run on a training server, a report, a literature search, a manuscript, a new directory or record, and when the user switches on an unattended run (无人值守). Use also when the user asks for a project to adopt these rules, and when a common rule is to be changed."
---

# How we work

One set of rules for how the user and their agents work on a project, kept here and nowhere else. A project that uses it carries the **common block** (`common.md`) inside its `AGENTS.md`, between two marker comments, so that it is in context in every session; the block points back here for the reference that goes with each kind of work. What only one project needs stays in that project: outside the block in its `AGENTS.md`, and in its `docs/conventions/<kind>.md`.

## At the start of a session: sync

Run in the project's root, with this skill's `scripts/` on the PATH:

```sh
set -o pipefail; export PATH="<this skill's absolute path>/scripts:$PATH";
hww.py sync
```

It replaces the block in `AGENTS.md`, markers included, with the block of `common.md`, and prints one JSON line for the block and one for each entry under `## To promote` (or `## 待提升`) in the project's own part of `AGENTS.md` and in its `docs/conventions/*.md`. Who takes over; the first two rows can both apply to one run:

| The script | You |
|---|---|
| The block's line says `updated` | Read the block again from the file: the copy in your context was loaded before the sync. A subagent that starts from your context gets that old copy, so its brief says what changed |
| Exit 1: `to_promote` lines whose `mark` is null, or the block was just updated | Judge each entry against the bar in [references/maintaining.md](references/maintaining.md), *What earns a line*. One the common rules now cover: delete it from the project's file. One that passes the bar: log an issue in the skills repository (below) and write `(issue: <its file name>)` at the entry's end. One that already names its issue: look for that file in the skills repository. Still in `docs/issues/`: leave the entry. In `docs/issues/archive/` as `-fixed`: the common rules have it now, delete the entry. As `-wontfix`: it is this project's rule, see the next case. One that fails the bar because it is this project's own: move it under `## This project only`, with the reason as its `Why here only`. The rest, which you cannot place yet, stay, each with `(judged <YYYY-MM-DD>: stays)` written at its end; such an entry is judged again only when the block's line says `updated` or the project has shown something new about it. Each `to_promote` line carries `mark`: `issue` or `judged` for an entry that ends in `(issue: …)` or `(judged …: stays)`, null for one not yet judged. The sync exits 1 only while some entry has no mark, or when the block was just updated and entries remain; otherwise marked entries are listed and the exit is 0. |
| Exit 2, `no_block` | The project does not carry the block. Leave it as it is, unless the user has asked for it to adopt these rules (below) |
| Exit 2, `unclosed_block` or `several_blocks` | The markers are damaged: [references/adopting.md](references/adopting.md), *Damaged markers* |
| Exit 2, `older_common` | This machine's install of the skill is behind the project's block. Reinstall the skill and sync again; until then work from the block as it stands |
| Exit 2, another code | The line's `hint` says what to do: `file_not_found` (no `AGENTS.md` here: the wrong directory, or a project that does not carry the block), `no_common` or `bad_common` (the skill itself is incomplete: tell the user), `write_failed` (`AGENTS.md` could not be written and is as it was: the line's `detail` says why) |

## An issue in the skills repository

The common rules change only there. Its path on this machine is `skills_repo` in `~/.config/how-we-work/config.json`; where the file is missing, ask the user for the path once and write it there. An issue is one file, `docs/issues/<YYYYMMDD>-<skill>-<topic>.md`, the topic starting with the name of the skill it concerns (`how-we-work` for a common rule, or for a sentence of the block or of a reference), as that repository's root `AGENTS.md` describes: what happened (what was run, what was seen, why it hurt), in which project, the user's words with their date; and, for a rule to promote, the rule you propose and the text it would change ([references/maintaining.md](references/maintaining.md), *How a rule is proposed*). The repository is public: a host, a login, the institution, or a path that holds one, is written as the placeholder its `AGENTS.md` gives. Before opening one, look through that directory for an open issue that already proposes the same rule, and add this project's case to it instead, so that the cases behind one rule stand together when it is judged. Look through `docs/issues/archive/` too, for one that proposed it and was turned down (`-wontfix`): then open none unless this project brings a case the old issue did not have, and write `(judged <YYYY-MM-DD>: stays; turned down in <its file name>)` at the entry's end. Writing this one file is the standing exception to "write only inside this project"; mention it to the user in a line.

## Before a kind of work

Read the reference, then the project's `docs/conventions/<kind>.md` if it has one. The block's *Kinds of work* says when each applies.

| Kind | Read |
|---|---|
| Experiments | [references/experiments.md](references/experiments.md) |
| Reports | [references/reports.md](references/reports.md) |
| Literature | [references/literature.md](references/literature.md) |
| Papers | [references/papers.md](references/papers.md), and *The outward document* in the reports reference |
| Layout | [references/layout.md](references/layout.md) |
| Records | [references/records.md](references/records.md) |
| An unattended run: at the switch, and on resuming one after a compaction or a restart | [references/unattended.md](references/unattended.md) |

## When a project is to adopt these rules

Only on the user's word naming the project. Read [references/adopting.md](references/adopting.md): by the project's state (new, under way, under way and unable to stop for it) it says what adoption is, what the user sees before anything changes, and what a session of the skills repository delivers when the user has it prepare the adoption first.

## Changing the common rules

`common.md` and the references are edited only in the skills repository, on the user's word, by the review loop for rule text; a project picks the change up at its next sync. Before proposing or making such a change, read [references/maintaining.md](references/maintaining.md).
