---
name: project-rules
description: "A rule of the project's own: which of its two files it goes to (the rules file or a convention file), how an entry and its source are written, how the rules file is kept, and how a rule moves. It has no project file of its own."
trigger: "before writing down, moving or removing a rule of the project's own."
---

# A rule of the project's own: where it goes and how it is written

A project's `AGENTS.md` holds its title and the common block, and nothing of the project's. It is in context every turn, and nothing a project needs has to be: each of its rules is needed at a moment, and stands in the file that is read at that moment.

| File | Read | Holds |
|---|---|---|
| `docs/conventions/<name>.md` | With the reference of that name, when that kind of work begins | How one kind of work that has a reference is done in this project, with the facts that work needs. `hww.py add <name>` makes the file |
| The rules file, `docs/rules.md` | Whole, before designing or changing what the project builds; by section, before work of a kind one of its headings names | Every other rule: what the thing the project builds must be and how it is designed and changed, under headings that name the subject; after those, rules for a kind of work no reference covers, under headings that name the kind |

What is no rule stands in the project's documents (*What stands in neither*, below).

## Which file

The examples are invented: a project that builds a model marking disease on photos of leaves, and a service that scores them.

A convention file holds how the work is done: which cases an experiment is checked on, which approval a run needs, how the split is made, where a folder stays, how a report's panels are labelled. However specific to this project such a rule is, it goes with its kind of work, since that is when it is read. The list at the top of the rules file says what each kind covers; `hww.py add -h` prints the same list.

The rules file holds what the thing itself must be, whoever builds it and however: what the method may use, what the product may read, what a configuration must never do; and how that thing is designed and changed. The two meet in experiments, where the work is what builds the thing:

- Convention: "Every model is looked at on the twelve fixed photos before a score is reported." / Rules file: "A mask is drawn from the photo alone, never from the lab result."
- Convention: "The split is by plot." / Rules file: "The model reads nothing recorded after the photo was taken."

Where the project does differently from the common block, the entry goes to the convention file of the kind that part of the block belongs to, and says which rule it changes and why: a record kept in another place, to `docs/conventions/layout.md`; a decision that is the agent's here, to `docs/conventions/with-the-user.md`.

Sort by what the sentence is about, not by where a sentence like it stands now. A sentence that holds two things is split; a short fact that only explains a rule stays with the rule. When you cannot tell, ask the user in one line.

## What stands in neither

The writing-for-agents skill has the tests (the environment as a source of truth, sediment, no-ops); read it first when many rules are sorted at once, at an adoption or a reconciliation. These are what fills a rules document that nobody prunes:

- *A copy of what the agent can look up*: commands, the directory map, the architecture. The code, the configs and the README are the source; a copy goes stale. Keep only what no file confesses: the reason behind a choice, the trap.
- *How things stand now*: what the project is, which machine runs what, what is paused, what was found. It belongs to the document of its kind: `README.md`; `docs/goal.md` for what the project is to deliver; `docs/todo.md`; the project's findings; an issue for a known defect. A fact one kind of work needs every time (a machine's memory limit, the held-out plots) stands with that kind's rules.
- *Where a rule came from*: the date, the user's words, a decision's id. They change nothing the agent does; they go to the sources file.
- *What is already said*: by the block, a reference, the user's global instructions, or what the model does unasked. A second copy only gains a chance to disagree.

## An entry

One bullet per rule: the rule in a sentence, then, where the reader needs it to apply the rule, its reason or its reach in your own words.

```markdown
- **Photos from the two greenhouse cameras are scored apart from the field photos.** Their white balance differs, and a pooled score hides it.
```

A convention file's name and the line under its title are the script's: `hww.py add <name>` makes the file and refuses a name that is no reference of the skill, and the sync writes the line where it is missing and lists a file named for no reference.

An older convention file may carry the headings `## This project only` and `## To promote`, or `From:` after its entries. The headings may stay; a `From:` moves to the sources file when its entry is next touched.

## Sources: `docs/rules-sources.md`

The one home of where the project's rules came from, kept in Chinese.

Grouped by the file the rule stands in; one bullet per source: the rule's first words, the date, the scene, the user's words in 「」. Where a decision or an issue already holds the exchange, the bullet gives its id. A rule nobody said says who proposed it and from which case. A bullet is appended when the user approves or changes a rule, and when a rule moves its bullets move with it. The words behind the common rules are kept with this skill, not in the project.

The file is read to check where a rule came from or how far it was meant to reach; the rule text is what is followed.

## The rules file

`hww.py add rules` makes `docs/rules.md`. The lines between its two marker comments are the script's: what the file holds, when it is read, and the kinds of work that have a convention file. Below them the project's rules stand under `## ` headings, and the sync prints the file's name and its headings at the start of every session.

A project that already keeps its rules in a file of another name keeps the file and the name: the same marker pair, placed there once on the user's yes, makes it the project's rules file for the sync.

It is the user's file: a rewording, a merge or a removal there is shown to them first (the one exception: an entry that a common rule now states is removed at a reconciliation, as the maintaining reference says). When a better way is found, the rule changes first, on their yes, and then the thing is brought in line. Where the rules file and a convention file speak of the same matter, one of the two entries is misplaced or out of date: the rules file holds until that one is removed.

A new rules file is in English, as the other files agents read are; a change is shown to the user with its Chinese. An existing one keeps its language.

## Moving a rule

A rule has one home, and when it moves it leaves the old one: from the rules file into a convention file when a new reference covers its heading (the sync says so). A move changes no rule and is reported in a line.

Whether a rule would hold in other projects is not judged in the project: the skills repository's session reads the projects and brings what it finds to the user.
