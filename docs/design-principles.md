# Design principles

How this repo's skills and instructions are designed, written, run and decided with the user. Read it before designing, changing, running or testing a skill, writing text for agents, or putting a design decision to the user. The principles are the user's, said many times; their words are quoted with the date, as the reason behind each. Ideas taken from [mattpocock/skills](https://github.com/mattpocock/skills) (studied 2026-10-29, every skill read) are marked *(mattpocock)*.

## 1. Scripts and agents

**Scripts are scaffolding.** A script does the tedious, repetitive, reusable work: the same steps every time, on facts it can be certain of — request, download, file, compare ids, record, wait, report. It is small, independent and cheap to run again.

**Agents are the intelligence.** Whatever differs from case to case, is uncertain or is new goes to an agent: a page a script cannot get past, a file it cannot judge, two records that may be one paper, a site behaving in a way not met before. A subagent is autonomous: it looks (a page's elements through `opencli browser state` / `find`, a file's pages as images), explores and acts toward the goal, and it can be relied on.

> 「脚本是去做那些繁琐的重复工作；对于差异化、不确定的东西，都应该交给 subagent 去完成。这样效率是最高的，而且不用写一大堆的匹配之类的。脚本是重复的工作、可复用的工作，像小手脚架一样。然后 A sub agent 是智能的东西，你可以依赖它。因为它是有自主性的，可以通过自己的探索去实现我们的目标」 (2026-10-30)

**The boundary is the script's certainty.** A script settles only what leaves nothing to judge: the same bytes, an id that matches, the host's own words stating the fact in text a script can read. Anywhere else it stops and hands over, carrying its evidence. Recall beats precision: a doubtful case sent to an agent costs one look, a wrong case settled by a script costs the result. A script past its boundary shows as a matcher deciding the uncertain branch — a regex, a keyword list, a similarity threshold, a special case per site; such a matcher is removed, not extended. The fix for a missed handoff is the handoff.

> 「有没有可能能检测出可能出现问题无法确定，然后交给 agent 辅助解决。因为我感觉你越考虑得全越像修修补补打补丁」 (2026-10-12) · 「如果你通过脚本的方式能确定且有把握，那就 OK，不需要subagent介入；但是如果你没有那么十足的把握，就交给 Sonnet subagent」 (2026-10-27)

**Every handoff is written into the skill.** At each point where a script stops, SKILL.md says who takes over, with what brief, what comes back, and which script command records the answer; then the script resumes where it stopped. The flow carries the delegation, so the user never has to prompt for it.

> 「这个流程不应该是你skill自己要做的吗？」 · 「也不是要写死，你背后的agent应该自己去做的…用sonnet之类比较便宜的模型，去操作浏览器」 (2026-10-20)

**Who takes over.**
- Browser work and small judgements — reading a page's state, clicking through a sign-in, judging what a file is, checking a parse: a background subagent on a cheap model (Claude Code `model: "sonnet"`, Codex `luna`), up to 10 in parallel. One subagent carries one try to its end: to the file, not to a URL halfway.
- Everything else — reading, research, synthesis, design: subagents on the session's own model.
- The user: only what only they can do — a password, a CAPTCHA, a choice — brought to the front with an alert. The clicks on the way there are the agent's.

> 「操作浏览器这类的操作都应该给便宜的模型」 · 「对，应该是一个subagent一个完整的try」 (2026-10-20) · 「如果脚本处理不好，就善于用subagent，准确率也会高很多」 (2026-10-21) · 「你可以自己点 login 还有登录，除非是需要我输入账号的这种情况」 (2026-10-30)

**Undecided never blocks the deliverable.** What an agent cannot settle either is recorded as unknown, and the run goes on: a file that passed the paper check is kept, with an `Unknown` version.

> 「如果就是应为不确定版本而丢弃了pdf，就会因小失大了，不确定就标unknown」 (2026-10-21)

**Knowledge stays open.** What sites, publishers and tools were seen to do goes into references as dated hints the agent judges, never into recognition code. Schemes, vocabularies and lists are starting points the agent extends and reports.

> 「不同的出版商，甚至不同的文章，可能都会不一样…你把握不是很大就交给subagent去判断」 (2026-10-21) · 「所规范的东西是可以随着 Agent、随着用户去变动的，不是死的」 (2026-09-23)

**Running a skill is following its flow — a test run included.** At every stop, read the SKILL.md step for it and do it; a step left out is said in the same message. When a script fails and the cause is unknown, a subagent looks at the page's elements and acts; nobody routes around it in silence.

> 「如果你无法通过脚本解决，而且不知道怎么卡的话，先去了解一下页面上的元素，然后进行相关的操作」 · 「出现问题，如果通过你的脚本解决不了，或者我们之前没有遇到过这种问题，你就应该去派 sub agent 去操作」 (2026-10-30)

## 2. Designing and changing a skill

1. **Research the whole surface first.** The tool's full behaviour from its source (how it stores data, its limits, what a round trip changes), the plugins the user has installed, every external interface and existing tool — web research through subagents on the session's model, in parallel — all before proposing commands or options. 「你之前开发之前都不去做一些详尽的调研的吗？」 (2026-10-29)
2. **Top-down, spec first.** The stages, the artifacts passed between them and who does each, script or agent, designed as a whole; a dated spec (root AGENTS.md has the rule), reviewed through independent lenses, then built. Small fixes the user agreed to go straight in. 「你需要从顶层全局规划设计一下再开始执行」 (2026-09-21) · 「你现在也不能修修补补，需要全面的顶层的设计」 (2026-10-30)
3. **Stop and think at key points** — research back, design written, review back: is this the best solution, is there a smarter one? 「关键节点你需要停下来思考……当前方案是否是最优的？有没有更好更聪明的解法」 (2026-10-30)
4. **General, never patchwork.** Solve a batch of problems at their root mechanism; a guard, flag or special case per issue is patchwork. A redesign is measured by the skill getting shorter and easier to use. A process rule an agent would otherwise be told in a sentence becomes a test or lint that can fail *(mattpocock: retro)* — a check on our own work, never a matcher for an uncertain branch (§1). 「我们并不崇尚复杂、多条件的、不断补充、东补一块西补一块的」 (2026-10-12)
5. **Fix upstream.** Record a fact at the earliest moment it is in hand — a PDF's version at download, on the publisher's page — so later readers stop guessing. 「你从上游根源上解决问题，那所有的一切都解决了吧」 (2026-10-20)
6. **Reuse by comparison; orchestrate.** Skills call each other and other tools' own commands, and write only what those lack. An existing tool is taken where it does the job at least as well; ours is kept where ours is better. Reasons are technical; licences are no criterion. A tool's behaviour is read from its source (`gh`), not guessed. 「能复用的尽量复用，不要重复造轮子，而且人家更新的很快也更完善」 (2026-10-20) · 「如果做的好的，我们肯定是要保留的，不会用那个差的方案」 (2026-10-29)
7. **Where to cut** *(mattpocock: codebase-design, writing-for-agents)*. A module earns its place when deleting it would concentrate complexity, not just move it (the deletion test). A seam is real once two users stand on it; with one it is hypothetical. A separate skill earns its always-loaded description only when it is invoked on its own or another skill must reach it. Each piece of knowledge has one home. Parts that change at different speeds — site hints, definitions, code — sit apart.
8. **Small independent scripts, pure Python through uv.** One function each, coding only the deterministic gaps; the stable interface is the artifacts passed between them. Each skill installs on its own: a small helper two skills share is copied into each, its header naming where it came from and the commit, never a shared library. Dependencies go in the PEP 723 block; a non-Python tool enters only as an external CLI. 「Skills 本来就只用纯 Python 的，我从来没有想要引入过 Node。」 (2026-10-30)
9. **Lean tests that can fail.** Few strong end-to-end tests at each script's seam, each covering a whole behaviour, expected values from a source independent of the code *(mattpocock: tdd)*. A heuristic is validated on data it was not tuned on, frozen first and graded blind. 「减少没必要的测试，专注于高质量实现和少数有效、高质量、高效的测试」 (2026-10-20)
10. **Every step ends on a done-when** that is checkable, exhaustive and able to fail: name the observation that would show it false *(mattpocock: to-tickets)*.

## 3. Writing for agents

The standard is the **writing-for-agents** skill *(mattpocock)*; read it before writing a SKILL.md, a reference, AGENTS.md or a brief. Its levers, in short:
- **Context pointers.** An always-loaded line (a skill's description, an AGENTS.md line) names material and the condition to reach it; its wording decides whether the agent reaches it. Front-load the leading word, one trigger per branch.
- **Two loads.** Always-loaded text costs every turn; what only some branches need goes behind a pointer (progressive disclosure). A concept's definition, rules and caveats sit together.
- **Steps end on completion criteria**, clear enough to tell done from not done and demanding enough to force the legwork.
- **Leading words.** A concept the model already knows, repeated as a token, anchors behaviour in few words. State the target behaviour; a prohibition only as a hard guardrail, paired with the positive.
- **Pruning.** One meaning in one place; the environment (`--help`, config, layout) is a source of truth, not something to restate; a sentence the model obeys by default is deleted whole.

**Language by reader.** What agents read (SKILL.md and its references, AGENTS.md, briefs, memory) is English, quoting the user verbatim in Chinese; what the user reads (README, specs, issues, reports) is Chinese.

**Changing instruction text** (AGENTS.md, `agent-instructions/`, a SKILL.md) goes through a review loop, however small the change: read it sentence by sentence with a Chinese rendering and name the defect exactly; hunt double readings in every copy the text lands in; write from the user's points in their own words, not from the last draft; fix at the point of use, not with a patch sentence; the advisor reviews the draft; show the user one change at a time, **原文** and **修改建议** verbatim with their Chinese, then the reason, and wait. Promoting anything into the global instructions is the user's decision.

## 4. Deciding with the user

**Facts are yours, decisions are the user's** *(mattpocock: grilling)*. Look up what the environment can tell — through a subagent if need be — and put only decisions to the user.

**One question at a time, from the frontier.** The decisions form a tree; the frontier is every decision whose prerequisites are settled. *(mattpocock: grilling)*: "Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a later round, not this one." grilling asks the whole frontier in one round; the user's rule is one question per round — ask one frontier question, wait for the answer, recompute. The work is done when the frontier is empty and the user confirms the shared understanding.

**Each question in the chat**, never in a dialog tool: the background it needs, the question, options labelled A/B/C (方案 A/B) each with a short example, the recommendation and why. A number or limit you propose is labelled yours. Decisions go into the issue as they settle; proposals stay marked 没拍板 until the user agrees.

> 「一个一个问题问我，不要用这种交互的形式。你需要直接在对话中讲清楚上下文背景还有问题，然后给出选项和推荐，为什么。另外，如果我觉得哪里不妥，我补充并和你讨论的」 (2026-10-29)

**Explain a design by example**, in the turn's final message: the overall idea in a few sentences, one concrete case walked through the flow, then the rough structure — in plain words, without internal vocabulary.

> 「你应该讲实际的例子，比如应该怎么过之类的，或者说整体的设计思路、流程，或者是大致的结构… 需要我去判断决定了，你一条一条问我。」 (2026-10-13)

## 5. Briefing subagents

- **The brief is the contract** *(mattpocock: triage)*: the goal, the behaviour wanted rather than a procedure, a done-when, what is out of scope, and what to come back with. Context goes by pointers (paths), not pasted content.
- **One level deep.** A subagent does the work itself and sends no agents of its own *(mattpocock: research, code-review: their best-documented failure)*.
- **Its report is a hypothesis, not evidence** *(mattpocock: code-review)*: what a decision rests on is checked before it is built on.
- **On the web, every agent is the user**: their IP, their Chrome, their institution's login, so a site that sees a crowd blocks the user. Each brief for an agent that touches a site carries the skill's lines for it: work by hand, one request at a time; one agent per site at a time, seconds apart; the first bot check, 403 or 429 ends the work on that site for the run, reported.
- **Writes stay contained.** The brief names the folder the agent writes to, created first; no git add or commit; `git status` once it returns.
- **A redesign stays one design**: the shared interfaces and an exemplar are written first, by the main conversation; then independent modules are ported onto them in parallel.
