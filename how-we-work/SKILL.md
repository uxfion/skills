---
name: how-we-work
description: "The user's shared working rules for their research projects — the common block synced into each project's AGENTS.md, and one reference per kind of work. Use in a project whose AGENTS.md carries the how-we-work block: at the start of a session (sync), before an experiment or a run on a training server, a report, a literature search, a manuscript, a new directory or record, a design or decisions put to the user, a subagent sent, and when the user switches on an unattended run (无人值守). Use also when the user asks for a project to adopt these rules, and when a common rule is to be changed."
---

# How we work

One set of rules for how the user and their agents work on a project, kept here and nowhere else. A project that uses it carries the **common block** (`common.md`) inside its `AGENTS.md`, between two marker comments, so that it is in context in every session; the block points back here for the reference that goes with each kind of work. What only one project needs stays in that project: outside the block in its `AGENTS.md`, and in its `docs/conventions/<kind>.md`.

## At the start of a session: sync

Run in the project's root, with this skill's `scripts/` on the PATH:

```sh
set -o pipefail; export PATH="<this skill's absolute path>/scripts:$PATH";
hww.py sync
```

It replaces the block in `AGENTS.md`, markers included, with the block of `common.md`, checks the form of the project's convention files, and prints one JSON line for the block and one for each convention file that is not in form. Who takes over:

| The script | You |
|---|---|
| The block's line says `updated` | Read the block again from the file: the copy in your context was loaded before the sync. A subagent that starts from your context gets that old copy, so its brief says what changed. Then read the project's own part of `AGENTS.md` and its convention files once against the new block: an entry that the block or a reference now states is deleted, because the project's text outranks the block and an old copy would override the newer rule. An entry that departs from a common rule on purpose stays, saying which rule and why |
| Exit 1, a `convention` line: a file in `docs/conventions/` is not in form | Put right what its `problems` names, as its `hint` says: the name of a reference of this skill, and the line that sends the reader to the reference first. A new convention file is made by `hww.py add <kind>`, never by hand |
| Exit 2, `no_block` | The project does not carry the block. Leave it as it is, unless the user has asked for it to adopt these rules (below) |
| Exit 2, `unclosed_block` or `several_blocks` | The markers are damaged: [references/adopting.md](references/adopting.md), *Damaged markers* |
| Exit 2, `older_common` | This machine's install of the skill is behind the project's block. Reinstall the skill and sync again; until then work from the block as it stands |
| Exit 2, another code | The line's `hint` says what to do: `file_not_found` (no `AGENTS.md` here: the wrong directory, or a project that does not carry the block), `no_common` or `bad_common` (the skill itself is incomplete: tell the user), `write_failed` (`AGENTS.md` could not be written and is as it was: the line's `detail` says why) |

## An issue in the skills repository

A project logs one for two things: a sentence of the block or of a reference that led you wrong, and a problem in one of the user's skills. Whether a rule of the project's should become a common rule is not a project's issue: the session of the skills repository reads the projects for that ([references/maintaining.md](references/maintaining.md), *Reconciling the projects*).

The repository's path on this machine is `skills_repo` in `~/.config/how-we-work/config.json`; where the file is missing, ask the user for the path once and write it there. An issue is one file, `docs/issues/<YYYYMMDD>-<skill>-<topic>.md`, the topic starting with the name of the skill it concerns (`how-we-work` for a sentence of the block or of a reference), as that repository's root `AGENTS.md` describes: what happened (what was run, what was seen, why it hurt), in which project, the user's words with their date. The repository is public: a host, a login, the institution, or a path that holds one, is written as the placeholder its `AGENTS.md` gives, and nothing of a project's unpublished results goes in. Before opening one, look through that directory for an open issue on the same thing, and add this project's case to it. Writing this one file is the standing exception to "write only inside this project"; mention it to the user in a line.

## Before a kind of work

Read the reference, then the project's `docs/conventions/<kind>.md` if it has one. The block's *When to read what* says when each applies.

| Kind | Read |
|---|---|
| Experiments | [references/experiments.md](references/experiments.md) |
| Reports | [references/reports.md](references/reports.md) |
| Literature | [references/literature.md](references/literature.md) |
| Papers | [references/papers.md](references/papers.md), and *The outward document* in the reports reference |
| Layout | [references/layout.md](references/layout.md) |
| Records | [references/records.md](references/records.md) |
| A design, or several decisions, going to the user | [references/with-the-user.md](references/with-the-user.md) |
| Sending a subagent | [references/subagents.md](references/subagents.md) |
| An unattended run: at the switch, and on resuming one after a compaction or a restart | [references/unattended.md](references/unattended.md) |

## When a project is to adopt these rules

Only on the user's word naming the project. Read [references/adopting.md](references/adopting.md): by the project's state (new, under way, under way and unable to stop for it) it says what adoption is, what the user sees before anything changes, and what a session of the skills repository delivers when the user has it prepare the adoption first.

## Changing the common rules

`common.md` and the references are edited only in the skills repository, on the user's word, by the review loop for rule text; a project picks the change up at its next sync. Before proposing or making such a change, read [references/maintaining.md](references/maintaining.md). What the projects have learned reaches the common rules by the reading that reference describes (*Reconciling the projects*).
