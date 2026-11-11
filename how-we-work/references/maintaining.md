# Maintaining the common rules

Read this in the skills repository, before proposing or making a change to `common.md` or to a reference of this skill. A project session reaches this file to judge an entry to promote (*What earns a line*) and to prepare the issue that proposes it (*How a rule is proposed*).

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

A change to `common.md` reaches a project at its next sync. Where a change makes an entry in a project's `## To promote` redundant, that project's agent deletes the entry when the sync lists it. The public repository is scanned before a push, as its `AGENTS.md` says; the user's sentences quoted in these files are about how to work and stay whole, with two things kept out before a commit: anything that would locate the user's institution, and any credential. The user's bar: 「只要不是那种直接能定位到学校的，或者说一些凭证信息，应该是无所谓的吧」. A change to `common.md` moves the `rev` in its begin marker to the day of the change (`rev <YYYY-MM-DD>`, or `<YYYY-MM-DD>.<n>` for a further change on the same day). The skill's test fails while the block's text has changed and the `rev` has not.
