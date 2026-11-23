# Rules: this project

<!-- how-we-work:rules — the script's lines, rewritten by `hww.py sync`; write below the end marker -->
What the thing this project builds must be, and how it is designed and changed; after that, rules for kinds of work that have no reference. Read it whole before designing or changing what the project builds. It holds over a convention file on the same matter.

A rule about how one of these kinds of work is done here stands in `docs/conventions/<name>.md`:

- `experiments`: Planning, running and reading experiments: a run a conclusion rests on, upstream code, environments, the training servers, and what follows a run (an incident, a defect found later, the next run). The project's file holds what its experiments need: its Python and framework build, its data and held-out cases, its checks and approvals before a run, its expert references, the facts of its machines that bite when forgotten. How a result is shown to someone belongs to `reports`; what the method or the product itself must be belongs to the project's rules file.
- `layout`: Where files and directories live and what they are called, and what holds when one is moved, replaced, archived or deleted. The project's file holds each place where its map differs from the default, with the reason. What an entry of a record looks like belongs to `records`.
- `literature`: Finding what others have published (papers, models and weights, code, datasets, the field's guidelines), and importing, reading, recording and citing a paper. The project's file holds its Zotero collection, its directions and the fields next to them, and the venues that count in its field.
- `papers`: Writing and changing a manuscript, its figures and tables, a cover letter and a response to reviewers. The project's file holds how it runs its paper: the journal and template, how it compiles, the order of its revision, its change log, its practice for figures, tables and letters.
- `records`: What an entry of each record holds and how a record stays current: decisions, the to-do list, issues, specs, what others said, the experiment log. The project's file holds where it changes a record's format, with the reason. Where a record lives belongs to `layout`; how a rule of the project's own is written belongs to `project-rules`.
- `reports`: Showing results to someone: any page that presents the work (a report, a group-meeting page, a talk, a Word file, a page of questions) and the figures and comparison tables in it. The project's file holds the terms of its field, its display pipeline and its own places. A manuscript belongs to `papers`.
- `subagents`: Sending a subagent: how many at once, on which model, what the brief holds, what is checked when it returns. The project's file holds the project's own limits: a lower cap, a runner its work must go through.
- `unattended`: An unattended run: its goal document, what is done ahead and what is reported, notifying the user, keeping the run alive. The project's file holds what this project does not start unattended, and what its runs need to keep going.
- `with-the-user`: Putting a design or several decisions to the user, and reading how far something they said reaches. The project's file holds what the user set for this project alone on how things are put to them.

Nothing of the project's stands in `AGENTS.md`. A fact stands in the project's documents, or with the rules of the kind of work that needs it.
<!-- how-we-work:rules-end -->

## Before work on a skill

- Read `docs/design-principles.md` before designing, changing, running or testing a skill.
- The how-we-work block in `AGENTS.md` and the references it points to are the installed skill's, synced here as in any project, with the installed `hww.py`. The `how-we-work/` directory of this tree is the version under development: it governs nothing until it is pushed and reinstalled, and it is read as the thing being changed. After a release, run the sync here as well.

## Writing a skill

- In a `SKILL.md`, use paths relative to the skill directory — never agent-specific ones (e.g. `.claude/skills/`).
- Every script a skill's docs or its entry run, the entry itself included, opens with `#!/usr/bin/env -S uv run --quiet --script`, then its PEP 723 block, `dependencies = []` when there are none: the block is what keeps uv out of the caller's project, so `--no-project` adds nothing, and `--quiet` keeps uv's install lines off stderr. Each is executable in git: the docs reach the entry through PATH (`docs/design-principles.md` §3, *The Unix/Linux philosophy*), and the other scripts sit on that same PATH. Since this checkout has `core.fileMode` off, `git update-index --chmod=+x` sets the bit.
- After changing a skill's commands — options, operands, output, help — or the letter table in `docs/design-principles.md` §3, run the conventions check from the repo root, `uv run tests/check_conventions.py`: it holds every skill not on its `NOT_YET` list to that section, *The Unix/Linux philosophy*; take a skill off the list once it is brought over.
- When adding or removing a skill, update the list in README.md.

## The repository is public

- The repo is public. Institution and personal values in committed files are placeholders: `<institution>`, `<proxy-domain>` (a proxied host is the host with dots as dashes, then `.<proxy-domain>`: `ieeexplore-ieee-org.<proxy-domain>`), `<sso-host>`, `<discovery-host>`, `<accountid>`, `<email>`, `<user>`; the real values live in local config outside the repo. The scan before a push covers everything the push publishes: files and commit messages.

## The global instruction sources

- The global instruction sources are `agent-instructions/CLAUDE.md`, `AGENTS.md` and `HERMES.md`; once a change to them is confirmed, sync the global copies (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.hermes/skills/agent-instructions/SKILL.md`). `HERMES.md` is `AGENTS.md` plus frontmatter and one `**In Hermes**` paragraph after the first Auto memory paragraph: after any change to `AGENTS.md`, regenerate it so that removing those two leaves `AGENTS.md` byte for byte. Change the Auto memory section only per `agent-instructions/auto-memory-update.md`.
- `agent-instructions/references/` is a checksummed source archive — don't edit it.

## Records

- An issue's topic starts with the skill's name.
