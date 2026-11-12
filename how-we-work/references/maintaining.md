# Maintaining the common rules

Read this in the skills repository, before proposing or making a change to `common.md` or to a reference of this skill. It also says how what the projects have learned reaches the common rules (*Reconciling the projects*).

## What earns a line

A rule enters the common rules when it states a principle, or a standing practice of how the user and their agents work that would hold in any of their projects. The user: 「并不是所有的决定或者很细的内容都要加进这个 howwework 里面，里面加入的内容一般都是比较常用、经常提起的。像一些针对项目或者很细节的内容，我觉得没有必要」. The bar in one line: a rule each new project should not have to learn again.

How often the user has said something is evidence, not the test. A remark is weighed by the principle behind it, the first time and the fifth alike: 「也不是说我第二次提到你就马上记，你也是根据它背后的原则规则来的」. Often that principle is already in the rules, and what the case shows is a sentence that does not reach far enough; then that sentence is widened where it stands, and no rule is added.

Rules come from what went well as much as from corrections. A way of working that the user found good, or that plainly made the work faster, may be written down: 「有些用得好的，我觉得还不错的，挺满意的，能提高效率的，你可以记」. Record what was done and what made it work, so that it can be done again.

What stays out, and where it lives instead:

- A lesson about one project's data, method or tools stays in that project (its convention file or its memory), however costly it was. It is proposed for the common rules when it turns out to rest on something that holds beyond that project.
- A practice of one project stays in that project's convention file.
- What a tool was once seen to do in one project's work goes to the memory of the project that saw it. What the harness, or a tool that this kind of work uses in every project, was seen to do may stand in a reference as a dated hint the agent judges (the unattended reference's table, the reports reference's hint on the style block).
- A decision the user made to settle one case is recorded in its issue and goes no further. An answer to a question you asked is not by itself a rule.

Length is no measure, in either direction: 「篇幅不是问题啊……只要能把原则、规则讲清楚就好了」. What the current model already does unprompted is proposed for deletion at a tidy.

A statement the user made for one moment is not a rule. Before writing one down, check its breadth against their words: a sentence said under a momentary constraint (a usage limit just hit, one deadline) is for that moment.

## Reconciling the projects

How a project's rule becomes a common rule. From inside one project nobody can tell whether a rule holds in the others, so a project's agent does not judge it: this repository's session reads the projects and brings what it finds to the user. Adoption was the first such reading of a project; this is the same reading, done again.

- **When.** On the user's word. Offer it when a release is about to be synced into the projects.
- **What is read.** For each project that carries the block (their paths are `projects` in `~/.config/how-we-work/config.json`): its `.memory/`, its `AGENTS.md` outside the block, its `docs/conventions/`. Read-only, and by the main agent itself: a project holds a few dozen entries, which is not work for subagents.
- **What comes out is the exceptions,** never a table of every entry:

  | Seen | Done |
  |---|---|
  | A rule in a project's files that would hold in any project; the same rule standing in two projects is the best evidence. Also an entry in a project's memory that carries the user's words stated as holding from now on | Put to the user (*How a rule is proposed*). On their yes it enters the block, or the reference of the same kind, and the entries it came from are listed for deletion |
  | An entry the common rules already state, or have overtaken | Listed for the project to delete: the project's text outranks the block, so an old copy would override the newer rule |
  | A lesson in a project's memory that has proved itself | Named to the project's session, which promotes it into the project's files |
  | A rule that is the project's own | Left |

- **What the user turns down or puts off** is recorded in this repository's `docs/decisions/`, so that the next reading does not ask again. Nothing is marked in the project.
- **Changes in a project are its own session's**: give the user a short prompt to paste there. On the user's word to make them from here, first check that no session is running in that project.
- **Notes about a project** made while reading stay in a git-ignored place. This repository is public: what enters its tracked files is the general rule and the user's words.
- **A rule that reads as design thinking** is not written into `docs/design-principles.md` from here; it is proposed to the user by that document's own procedure.
- **Many entries in a project's `AGENTS.md` that share a kind of work no reference covers** are the sign that a reference is missing: say so.

## How a rule is proposed

From the user's words, not from the previous draft: list their sentences in order, with dates and where they were said; then the rule distilled from them; then the cases behind it. Say what the text says now on the point, and what you left out. The user's words and what you add are marked apart.

Before a change is shown: read the present text sentence by sentence with a Chinese rendering and name the defect exactly; look for double readings in every copy the text lands in (the block reaches every project); fix at the point of use, not with a sentence added beside it; and have the draft reviewed, by the advisor where the session has one, otherwise by yourself.

Each change is shown to the user one place per message and lands only on their yes: where it is, the original, the proposal, the Chinese of each, the changed words marked, the reason, then the options. A new rules document is first presented as a whole, by what it covers and where it departs from what the user has said or seen; after that, each change to it is shown this way. One decision that touches several places is asked once, with its places listed.

## How to word it so that it holds

Rules written here before failed in ways that repeat:

- **Two rules that pull against each other are written to the same concreteness.** A long, formatted rule about how to ask outweighs half a sentence saying "decide the routine yourself".
- **Scope is written as a kind, not as a list of occasions.** A list fails at the first case outside it.
- **Key words are written as something the other side can see.** "Background" becomes the file, the place, the present text, the user's words; "an example" becomes what the user will actually look at; "the user agrees" names what they agreed to.
- **A practice is written whole in one place, with one complete example.** A rule assembled from successive corrections holds only in its last-corrected part, and agents copy the example more than the clause.
- **An existing sentence that pushes the wrong way is changed where it stands**; a new sentence beside it does not outweigh it.
- **A correction is evidence about the case it names.** It changes that rule and leaves the rest standing; it does not call for a new rule each time.

## Where a rule's history is kept

The issue that carried the rule holds the user's words, dated, and the decision; when it closes it is archived by the repository's own rule, and the archive is the record of why a line is there. A candidate that was not taken is noted in its issue with the reason, so that it is not proposed again unchanged.

## After a change

A change to `common.md` reaches a project at its next sync. After a sync that updated the block, the project's agent reads its own entries against the new block and deletes what the block now states (the skill's `SKILL.md`). The public repository is scanned before a push, as its `AGENTS.md` says; the user's sentences quoted in these files are about how to work and stay whole, with two things kept out before a commit: anything that would locate the user's institution, and any credential. The user's bar: 「只要不是那种直接能定位到学校的，或者说一些凭证信息，应该是无所谓的吧」. A change to `common.md` moves the `rev` in its begin marker to the day of the change (`rev <YYYY-MM-DD>`, or `<YYYY-MM-DD>.<n>` for a further change on the same day). The skill's test fails while the block's text has changed and the `rev` has not.
