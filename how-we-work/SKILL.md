---
name: how-we-work
description: "The user's shared working rules for their research projects: the common block synced into each project's AGENTS.md, and a reference per kind of work that a project reads straight from this skill's folder. Daily work in a project needs no invocation. Invoke when a project is to adopt these rules, when a common rule is to be changed or the projects reconciled, and when an issue is to be logged in the skills repository."
---

# How we work

One set of rules for how the user and their agents work on a project, kept here and nowhere else.

- `common.md` holds the **common block**. A project that uses it carries the block inside its `AGENTS.md`, between two marker comments, so that it is in context in every session.
- `references/` holds one file per kind of work or moment. The block names the moments and gives the installed path, so a project's agent reads a reference directly.
- `scripts/hww.py` keeps a project in step with the skill: `sync` brings the block up to date and puts the convention files in form, `add` makes a convention file. `hww.py -h` has the rest.

What only one project needs stays in that project: outside the block in its `AGENTS.md`, and in its `docs/conventions/`.

## The sync

A project runs it at the start of every session, as its block says. From any other place:

```sh
set -o pipefail; export PATH="<this skill's absolute path>/scripts:$PATH";
hww.py sync
```

Each line it prints says what it means and what to do. Two outcomes need more than their hint:

- **Exit 2, `older_common`**: this machine's install of the skill is behind the project's block. Reinstalling is yours to do (`npx skills update how-we-work -g`); say in a line that you did. Until then work from the block as it stands.
- **Exit 2, `unclosed_block` or `several_blocks`**: the markers are damaged: [references/adopting.md](references/adopting.md), *Damaged markers*.

## An issue in the skills repository

A project logs one for two things: a sentence of the block or of a reference that led you wrong, and a problem in one of the user's skills. Whether a rule of the project's should become a common rule is not a project's issue: the session of the skills repository reads the projects for that ([references/maintaining.md](references/maintaining.md), *Reconciling the projects*).

The repository's path on this machine is `skills_repo` in `~/.config/how-we-work/config.json`; where it is missing, ask the user for the path once and write it there. An issue is one file, `docs/issues/<YYYYMMDD>-<skill>-<topic>.md`, the topic starting with the name of the skill it concerns (`how-we-work` for a sentence of the block or of a reference). It holds what happened (what was run, what was seen, why it hurt), in which project, and the user's words with their date; the records reference has the fields. The repository is public: a host, a login, the institution, or a path that holds one, is written as the placeholder that repository's `AGENTS.md` gives, and nothing of a project's unpublished results goes in. Before opening one, look through that directory for an open issue on the same thing, and add this project's case to it. Logging the issue, that line of the config included, is the one thing a project's session writes outside its project; mention it to the user in a line.

## When a project is to adopt these rules

Only on the user's word naming the project. Read [references/adopting.md](references/adopting.md): by the project's state (new, under way, under way and unable to stop for it) it says what adoption is, what the user sees before anything changes, and what a session of the skills repository delivers when the user has it prepare the adoption first.

## Changing the common rules, and reconciling the projects

`common.md` and the references are edited only in the skills repository, on the user's word. A project gets a changed block at its next sync, and a changed reference once the skill is reinstalled on its machine. Before proposing or making a change, and before reading the projects for what they have learned, read [references/maintaining.md](references/maintaining.md).
