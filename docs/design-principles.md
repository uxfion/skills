# Design principles

How the skills and instructions in this repo are designed, built, run and decided with the user. Read it before designing, changing, running or testing a skill, writing any document, or putting a design decision to the user. The document grows from the user's words. When the user repeats a point or corrects a mistake and their words carry a design idea or a top-level principle, the agent, unprompted, restates their words in order, distills the core point in formal language at the place it belongs here, and asks whether to add it. On a yes, the principle goes into its section and the user's words into the appendix at the end, which is only for checking where a principle came from or settling a doubt about it. Ideas taken from mattpocock/skills (studied 2026-10-29, every skill read) are marked *(mattpocock)*.

## 1. Who does what

A skill's work is split three ways, by what the work needs.

- **Scripts** do what is the same every time and certain: request, download, file, compare identifiers, record, wait, report. They are small, independent and cheap to run again — scaffolding.
- **Agents** do what differs from case to case, is uncertain or is new: a page a script cannot get past, a file it cannot judge, two records that may be one paper, a site behaving in a way not met before. An agent is autonomous: it looks (a page's elements through `opencli browser state` / `find`, a file's pages as images), explores and acts toward the goal, and it can be relied on. The jobs in the middle of a flow — searching, picking candidates, fixing keywords, asking when something is ambiguous, judging uncertain cases — are written as prompt, not code.
- **The user** does only what only they can: type a password, pass a CAPTCHA, make a decision. Every step on the way there, the clicks to a login page included, is the agent's.

### The boundary is the script's certainty

A script settles a case only when nothing is left to judge: the same bytes as a settled file, an identifier that matches, the host's own words stating the fact in text a script can read. Everywhere else it detects that it is unsure — its check fails or abstains, two independent methods disagree — stops, and hands the case over with its evidence. Doubt of any kind counts as unsure: a fact half-stated, a mark that may be an image, nothing stated. Recall beats precision: a doubtful case sent to an agent costs one look, a wrong case settled by a script costs the result. A rule a script applies is first tried on a few real cases.

A script past its boundary shows as a matcher deciding the uncertain branch: a regex, a keyword list, a similarity threshold, a special case per site, an auto-accept rule on top. A growing list of such rules is the signal to switch to detect-and-delegate; the matcher is removed, not extended. When a handoff was missed, the fix is the handoff — never another matcher, never clicks coded into the script.

### Handoffs are part of the flow

At every point where a script stops, the SKILL.md says who takes over, with what brief, what comes back, and which script command records the answer; then the script resumes where it stopped. The flow carries the delegation, so the user never has to prompt for it.

- One work item — a paper — is carried by one subagent from the point where the script leaves it. The subagent keeps its own browser session (its own tab) and does every remaining step of that item: working pages, searching elsewhere, judging what it got, recording the answer. When a later pass comes back to the item, the same subagent is resumed, never replaced. It runs in the background on a cheap model (Claude Code `model: "sonnet"`, Codex `luna`), at most 5 at once, because bot checks can be strict. Local judgements that need no page, such as the label of a file already settled or a check of a parse, go to such a subagent in batches. This holds where a skill fans out many work items at once, such as a batch of papers; an agent that invokes a skill for its own task — a server it needs, a deployment it was asked for — carries that task itself and hands only small judgements, such as reading a long log, to such a subagent.
- Reading, research, synthesis and design go to subagents on the session's own model.
- What needs the user is brought to the front, with an alert.

### Undecided never blocks the deliverable

What an agent cannot settle either is recorded as unknown, and the run goes on: a file that passed the paper check is kept even when its version is undecided (`Unknown-<Source>`), and listed for a later look.

### Knowledge stays open

- Schemes, vocabularies and lists in a skill are starting points, and say so: the agent extends them for a new case (a tag, a venue, a dimension) and reports it, and what the user changes in conversation is the rule from then on. Each list, and each "only", is checked for whether it would stop an agent from doing the sensible new thing.
- What sites, publishers and tools were seen to do (where a publisher marks the version, which link holds the PDF) goes into references as dated hints the agent judges, never into recognition code: sites differ, pages of one site differ, markers change. The skill fixes definitions and vocabulary; recognising them is the agent's judgement, and where it is not confident, a background sonnet subagent looks.
- What varies by machine — where files go, which GPU, which build, how to recover a download — is principles plus dated hints for the calling agent, in the tool's own vocabulary (vLLM's arguments, not new keys); the script does only what is the same everywhere (start, stop, wait, report).

### Running a skill is following its flow

Every run, a test run included, follows the SKILL.md: at each stop, read the step for it and do it; a step left out is said in the same message. When a script fails and the cause is unknown, a subagent looks at the page's elements and acts; nobody routes around it in silence.

## 2. Designing and changing a skill

1. **Research the whole surface.** The tool's full behaviour, read in its source — how it stores data, its limits, what a round trip changes — with the plugins the user has installed (check the profile's extensions), ending in a real write test. Every external interface and existing tool, searched on the web by research subagents on the session's model, in parallel: reusing one may remove whole parts of the design. All of it before proposing commands or options.
2. **Design top-down.** The stages, the artifacts passed between them and who does each — script, agent or user — designed as a whole and written as a dated spec (root AGENTS.md has the rule).
3. **Review before building**: independent reviewers with distinct lenses — fidelity to the requirements, technical correctness against sources, usability for a fresh agent — on a tight budget, then the advisor.
4. **Stop and think at key points** — research back, design written, review back: is this the best solution, is there a smarter one?
5. **Small fixes the user agreed to** go straight into code and docs, without a spec round, written per §4.

## 3. What a good design looks like

- **General and simple, never patched.** The design is made top-down: one general mechanism solves a whole class of problems at its root, with as few mechanisms as do the job, and the whole is high in quality, elegant and efficient. It does not pre-build machinery for problems nobody has met, and it leaves out none of the basics: what nearly every run meets, and what doing the job right inherently includes, is in the design from the start. What stays out is defence against problems only imagined. When a run meets a new problem, the first question is whether the general mechanism already covers it; if not, the design is re-cut at the root so the new case falls inside it. A guard, flag, condition or special case added per issue is patchwork, and patchwork piles up into a skill nobody can follow. General methods win over rules tied to one field, journal or page, and a rule that earns its place is stated as a general fact. A redesign is measured by the skill getting shorter and easier to use, not by issues ticked off.
- **Facts recorded upstream.** When a later reader has to guess something, find the earliest moment the fact was in hand — not a later step of the same run — and record it there, in a fixed form: a PDF's version on the publisher's page, at download and at the first check, while the page's labels and the clicked link are still there; by save time only the file is left. A smarter guess downstream keeps growing exceptions.
- **Reuse decided by comparison, function by function.** An existing tool is taken where it does the job at least as well as our scripts and agent judgement; ours is kept where it is better, never traded for a worse one because that is reuse. The comparison weighs completeness of information, checkability before a write, control, simplicity, maintenance and risk. Licences are no criterion and stay out of comparisons unless the user raises them; a tool left aside gets a technical reason. The standing example is metadata: our agent combines doi.org, Crossref, arXiv, the article page and OpenAlex keywords, finds the published version and previews the item before writing, which beats Zotero's translators, each taking one source and writing directly (the first spec's finding, 2026-09-21 §3.6).
- **Orchestrate, don't absorb.** Skills call each other and other tools' own commands, adding only what those lack plus the task's context. In code too: a script calls the tool's own commands (`opencli browser get`, `find`, `extract`, `wait`, …) and writes only what the tool lacks (in paper-fetch: the PDF finder, the in-page request, the pdf.js viewer), since the tool is updated faster and covers more than a re-implementation. OpenCLI is the adapter layer: adapters are discovered at run time, `opencli browser` is the last fallback, and no skill binds itself to one adapter or CLI detail. A tool's `--help` and skill docs come before writing a helper; where they leave a behaviour open, its source (`gh`) is read rather than guessed or probed blind. Tools are kept current: an installed version behind its docs breaks the calls (OpenCLI 1.8.8 against its 2.x docs, 2026-10).
- **Cut where it pays** *(mattpocock: codebase-design, writing-for-agents)*. A module earns its place when deleting it would concentrate complexity, not just move it (the deletion test). A seam is real once two users stand on it; with one it is hypothetical. A separate skill earns its always-loaded description only when it is invoked on its own or another skill must reach it. Each piece of knowledge has one home. Parts that change at different speeds — site hints, definitions, code — sit apart.
- **Small, independent, pure-Python scripts.** One function each, coding only the deterministic gaps; the stable interface is the artifacts passed between them, so tools stay replaceable. Skill code, dependencies and tests are Python run by uv, dependencies in the script's PEP 723 block, never a library vendored to dodge one. Another runtime, Node/JS included, is never an option; a non-Python tool that is best on the merits enters only as an external CLI, like OpenCLI, or not at all, and which of the two is said. A measuring tool in another language for one design study may live in a git-ignored issue reference folder, outside the skill and its tests. Each skill installs on its own: a small helper two skills share is copied into each, its header naming the source and the commit — no shared library.
- **Checks that can fail.** Few strong end-to-end tests at each script's seam, each covering a whole behaviour, with expected values from a source independent of the code *(mattpocock: tdd)*. Every step of a flow ends on a done-when that is checkable, exhaustive and able to fail: it names the observation that would show it false *(mattpocock: to-tickets)*. A process rule an agent would otherwise be told in a sentence becomes a test or lint *(mattpocock: retro)*: a check on our own work, never a matcher for an uncertain branch.
- **Heuristics validated blind.** A heuristic component is explored in stages; after each, it is reviewed and the question asked whether a better approach exists. Before held-out results are seen, the code is frozen and the severity definitions and thresholds are written down with a checksum; it is tested on data it was not tuned on, and a spent test set needs new data. Grading is blind, by subagents, with hidden known-good and known-bad controls, plus your own audit of passed items and your own look at the few items a decision rests on; the graders' raw numbers go beside your tiers. The user sees every option and the recommended one before any code changes.

## 4. Writing for agents

The standard is the writing-for-agents skill *(mattpocock)*, and every document follows it, whoever reads it: what makes a text predictable for an agent makes it readable for the user. A design is written by it from the start; when the development is done, the skill is invoked once more for a full pass over everything the work wrote. The agent settles the wording itself, with the advisor's review, and reports the result in brief; instruction text below is the exception. Documents here include, but are not limited to: a SKILL.md and its references, a script's `--help` and the messages and log lines it prints, code and config comments, AGENTS.md, CLAUDE.md and the other global instructions, briefs, memory, and what the user reads (README, specs, issues, reports). The skill's levers, in short:
- **Context pointers.** An always-loaded line (a skill's description, an AGENTS.md line) names material and the condition to reach it; its wording decides whether the agent reaches it. Front-load the leading word; one trigger per branch.
- **Two loads.** Always-loaded text costs every turn; what only some branches need goes behind a pointer (progressive disclosure). A concept's definition, rules and caveats sit together.
- **Steps end on completion criteria**, clear enough to tell done from not done and demanding enough to force the legwork.
- **Leading words.** A concept the model already knows, repeated as a token, anchors behaviour in few words. State the target behaviour; a prohibition only as a hard guardrail, paired with the positive.
- **Pruning.** One meaning in one place; the environment (`--help`, config, layout) is the source of truth, not something to restate; a sentence the model obeys by default is deleted whole.

**Skill text** leaves out what other layers govern (examples simply use `uv run`). Each external CLI gets one labelled example, plus dated hints of practices established, with run-time discovery authoritative. It holds no personal facts: the repo is public, and root AGENTS.md has the placeholders. Principles like these, and a skill's way of reaching pages, are written into each skill's own prompt, not into the global instructions.

**Language by reader.** What agents read (SKILL.md and its references, AGENTS.md, briefs, memory) is English, quoting the user verbatim in Chinese; what the user reads (README, specs, issues, reports) is Chinese.

**Changing instruction text** — AGENTS.md and `agent-instructions/` — goes through a review loop, however small the change: read it sentence by sentence with a Chinese rendering and name the defect exactly; hunt double readings in every copy the text lands in; write from the user's points in their own words, not from the last draft; fix at the point of use, not with a patch sentence; have the advisor review the draft; show the user one change at a time, **原文** and **修改建议** verbatim with their Chinese, then the reason, and wait. The global instructions change only with the user's consent.

## 5. Deciding with the user

- **Facts are yours, decisions are the user's** *(mattpocock: grilling)*. What the environment can tell is looked up, through a subagent if need be; only decisions go to the user.
- **One question at a time, from the frontier.** The decisions form a tree; the frontier is every decision whose prerequisites are settled. Ask one frontier question, wait for the answer, then recompute: a settled decision pushes the frontier outward and unblocks the questions that hung on it, and a question that depends on one still open waits for a later round. (The method is the grilling skill's; grilling asks the whole frontier per round, the user's rule is one question per round.) The work is done when the frontier is empty and the user confirms the shared understanding.
- **Each question in the chat**, never in a dialog tool: the background it needs, the question, options labelled A/B/C (方案 A/B) each with a short example, the recommendation and why. A number or limit you propose is labelled yours.
- **A design is explained by example**, in the turn's final message: the overall idea in a few sentences, one concrete case walked through the flow, then the rough structure — in plain words, without internal vocabulary.
- **Decisions are written down as they settle**, in the issue; a proposal stays marked 没拍板 until the user agrees.

## 6. Briefing subagents

- **The brief is the contract** *(mattpocock: triage)*: the goal, the behaviour wanted rather than a procedure, a done-when, what is out of scope, what to come back with. Context goes by pointers (paths), not pasted content.
- **One level deep.** A subagent does the work itself and sends no agents of its own *(mattpocock: research, code-review — their best-documented failure)*.
- **Its report is a hypothesis, not evidence** *(mattpocock: code-review)*: what a decision rests on is checked before anything is built on it.
- **On the web, every agent is the user**: their IP, their Chrome, their institution's login, so a site that sees a crowd blocks the user. Each brief for an agent that touches a site carries the skill's lines for it: work by hand, one request at a time, seconds apart; at most 5 agents on the web at once. A challenge the user can pass goes to the user as a gate; the first other block — a bot check, 403 or 429 — ends that agent's work on that site for the run, reported. The work item waits on that route instead of moving to another: a block is a pause, not a verdict on the route.
- **Writes stay contained.** The brief names the folder the agent writes to, created first; no git add or commit; `git status` once it returns.
- **A redesign stays one design**: the shared interfaces and an exemplar are written first, by the main conversation; then independent modules are ported onto them in parallel.

## Appendix: the user's words

Verbatim, dated, by section, with the scene in a few words. For checking a principle's source or settling a doubt; the principles above are what to follow.

**§1 Who does what**
- 2026-09-21, a first draft that was one 400-line script hard-coding search, scoring and cleanup: 「中间层你完全可以通过你Agent本身的能力去做」
- 2026-10-12, a figure-grouping prototype tuned page by page fixed 5 figures and broke 3 on unseen papers: 「有没有可能能检测出可能出现问题无法确定，然后交给 agent 辅助解决。因为我感觉你越考虑得全越像修修补补打补丁」; on recall: 「宁可多做也不要漏掉」
- 2026-10-20, a signed-out discovery system, and I asked the user to find pages: 「这个流程不应该是你skill自己要做的吗？」, 「也不是要写死，你背后的agent应该自己去做的…用sonnet之类比较便宜的模型，去操作浏览器」, 「操作浏览器这类的操作都应该给便宜的模型」, 「claude code的话是sonnet，尽量避免使用opus模型，codex后面再补充，应该是luna模型」, 「对，应该是一个subagent一个完整的try」; Codex: 「codex用luna模型」
- 2026-10-21: 「如果脚本处理不好，就善于用subagent，准确率也会高很多」; 「这种用于浏览器操作、判断、检验等小任务/简单任务的subagent用sonnet模型就足够了，同时并行数量可以提高到10个」
- 2026-10-21, a spec that held back PDFs of undecided version: 「我们zotero的目标肯定是获得全文的pdf并存档……如果就是应为不确定版本而丢弃了pdf，就会因小失大了，不确定就标unknown」
- 2026-10-27, a rename plan that sent ~900 attachments to subagents: 「如果你通过脚本的方式能确定且有把握，那就 OK，不需要subagent介入；但是如果你没有那么十足的把握，就交给 Sonnet subagent」
- 2026-10-31, one agent per paper: 「一篇论文应该由一个 sub agent 去维护。具体来说，它也是一个 OpenCL 的 tab。如果出现问题，你就在上面操作浏览器或者去图书馆检索。也就是说，一篇论文对应一个流程，一个流程对应一个 sub agent。不要派多个 sub agent 去做多个操作。但是我说的也有可能不对，你需要跟我讨论一下」; on the cap: 「限流不是很担心，因为我们最多同时跑的时候会有限制嘛，最多是5篇论文同时…我觉得，有时候机器人限制或者人机验证限制比较严，应该就最多5个同时跑就好了」
- 2026-10-31, vllm-serve, on whether one subagent should carry each deployment: 「我一般用这些 skills 都是主动用的嘛，而且都是交给 Agent 去操作的。比方说，我在 PaddleOCR 里面需要用 VLLM server，它就自己去调用啊。在其他项目中，比方说要用 API 跑实验了，我也会在其他的 Agent 里面说明，根据我们的 skills，去部署远程服务器上的一个 VLLM」, then 「适用范围可以补一下」
- 2026-10-29, research agents sent on sonnet: 「为什么你派出去的是sonnet…这些简单的任务用sonnet subagent是没问题，但是你自己派出去的subagent默认应该是和harness的配置一样的，我没有设置，应该用的是和当前使用模型一致的吧」
- 2026-10-30, vllm-serve: 「你现在是一个 Agent，你有自主性的，调用这个skill的agent都是有自主性的……通过固定的脚本不一定好用，而且差异也很大……脚本不能做的事情，就交给agent去自己做」
- 2026-10-30, a paper-fetch test stopped on a library sign-in and no browser agent was sent: 「你可以自己点 login 还有登录，除非是需要我输入账号的这种情况」, 「如果你无法通过脚本解决，而且不知道怎么卡的话，先去了解一下页面上的元素，然后进行相关的操作，就自己去点击操作或者其他的一些动作。我当时记得跟你说过，对于这种浏览器的操作，用的是 Sonnet subagent」, 「出现问题，如果通过你的脚本解决不了，或者我们之前没有遇到过这种问题，你就应该去派 sub agent 去操作。我们之前有规划好的：脚本是去做那些繁琐的重复工作；对于差异化、不确定的东西，都应该交给 subagent 去完成。这样效率是最高的，而且不用写一大堆的匹配之类的。脚本是重复的工作、可复用的工作，像小手脚架一样。然后 A sub agent 是智能的东西，你可以依赖它。因为它是有自主性的，可以通过自己的探索去实现我们的目标」, 「你现在也不能修修补补，需要全面的顶层的设计。根据我们刚才说的那些思路。就是脚本和 agent 之间的差异，要合理分工的」
- Knowledge stays open — 2026-09-23, on a tag list written as "the vocabulary": 「这只是一个方向或者建议，新的论文进来，你可以新增 tag … 它是可以自行维护的或者新建的」, 「所规范的东西是可以随着 Agent、随着用户去变动的，不是死的」; 2026-10-21, on probes of a few library PDFs: 「不同的出版商，甚至不同的文章，可能都会不一样，你不要认为库里这几篇就把某个流程定死，而且出版商也有可能去更新标识之类的，你把握不是很大就交给subagent去判断」

- 2026-10-31, a block on a site: 「如果就因为人机验证或者限速等限制，你就直接转头去其他地方查了，那这个查询的记录不就没了吗？这条路径不就直接被你否定掉了吗？」; on coordinating agents: 「但是现在我们只有 5 个文献的 sub agent 同时去做，也不会碰到一堆限制。我觉得现在应该用方案 3，也就是最简单的方式去实现，后面碰到问题了再说」

**§2 Designing and changing a skill**
- 2026-09-21: 「你需要从顶层全局规划设计一下再开始执行」
- 2026-10-18: 「这些比较简单的问题可以直接改吧，不用spec这种复杂的流程吧，记得使用Writing for agents」
- 2026-10-29, note commands proposed before the round trips and the installed plugin were checked: 「我不理解，你之前开发之前都不去做一些详尽的调研的吗？」, 「直接 web search 就行了，这种都应该在确定方案之前做好详细的调研的」
- 2026-10-30: 「关键节点你需要停下来思考……当前方案是否是最优的？有没有更好更聪明的解法」

**§3 What a good design looks like**
- Patchwork — 2026-10-12, a review round that grew a skill from ~11.5k to ~19k lines with a guard per finding: 「我们并不崇尚复杂、多条件的、不断补充、东补一块西补一块的」; 2026-10-19: 「我整体希望一个比较通用的方法，而不是很专业、针对某一领域的或者修修补补的」; 2026-10-31, on keeping it simple without patching: 「不要从一开始就把系统做得很复杂，我感觉是没必要的」, then 「在整个设计的过程中，你不能修修补补。我最忌讳的就是修修补补，加了一堆条件或者修修补补的东西。如果能从顶层、从根源、从设计、从全局去解决，能用更优雅的方式去解决，那就用这种方式。我担心的点在于，你刚才说只会遇到问题找机制，又说从简单的起步。如果问题越多，你修补得也就越多，最后就会变成一个非常糟糕、修修补补的状态。这是我不希望看到的，我希望是从顶层、从全局观念去解决大部分问题的。整一套都是比较高质量、优雅、高效的，这才是我想要的东西」; 2026-10-31, vllm-serve, after hypothetical guards from a review were set to be dropped: 「A 但是有一些必要的你还是要考虑的，不要过度防御性，你懂我意思吧。有一些基本上都会遇到的，或者本身就该考虑的，你就应该考虑进去。」
- Upstream — 2026-10-20, a read-time guess of attachment versions refined case by case: 「我指的是一开始保存pdf的时候就应该分清楚，取好名字，因为在下载的时候，我们就清楚了它来自于哪里。规范命名，这个问题不就解决了吗？」, 「你在下游修修补补，改得要死，还是那一样的结果。你从上游根源上解决问题，那所有的一切都解决了吧」, 「pdf version是在出版商网页或者下载pdf以及初步检查的时候就能大致确定的，不要事后再去做，事后再做就缺了很多信息了」
- Reuse and orchestration — 2026-09-21: 「不要把 OpenCLI 或者 Zotero 里面的一些活给揽到自己身上」; 2026-10-20: 「能复用的尽量复用，不要重复造轮子，而且人家更新的很快也更完善」, 「记住这个原则」, 「你没有源码可以去获取啊，gh也有」; 2026-10-29, on Zotero plugins: 「能复用就尽量复用，我的原则。我们避免去造这种复杂的轮子，能用起来就用别人的，而且本身 Zotero 的插件系统就是比较完善的」; 2026-10-29, on swapping our metadata agent for Zotero's translators: 「查元信息本身agent就比zotero做的好…如果做的好的，我们肯定是要保留的，不会用那个差的方案」, 「其他的功能也是这样，你记一下，下次别犯了，这个原则」
- Licences — 2026-10-30, a reuse declined for AGPL: 「不用担心许可证，这些都是我自用的，不会商业化，也不会被别人使用，自用的完全不用担心」
- Pure Python — 2026-10-30, Node offered for the note reader: 「我们现在都是用python去做的，如果突然加个js会不会非常奇怪」, 「Skills 本来就只用纯 Python 的，我从来没有想要引入过 Node。」, 「因为 UV 这一套对于包管理、像命令行一样的脚本调用，这些都管理得很好。而且它还有包内脚本的包管理，可以直接运行。我就不喜欢在外面再去加什么东西，只要一个 UV 就可以解决」
- Cutting — 2026-10-29, on splitting paper-to-zotero: 「你自己根据 writing for agent 设计原则还有之前就已经探索过的mattpocock/skills设计理念，再全局过一遍，看是否合适，是否优雅、合理、高效」
- Tests — 2026-10-20: 「减少没必要的测试，专注于高质量实现和少数有效、高质量、高效的测试」, 「繁琐的冗余的没有必要的流程尽量减少……要优雅」
- Heuristics — 2026-10-12: 「在探索过程中完成一阶段要 review 并且反思…等到探索完成后，再给我简报各个方案和最优方案，让我审一遍，我确定没问题同意后再动手改」

**§4 Writing for agents**
- 2026-09-24: 「面向用户、需要用户真的自己去读的内容就用中文；面向 Agent 或者 harness、让 Agent 读的，要保持英文」
- 2026-09-26, the review loop: 「其实刚才那一套工作流其实是非常重要的，你需要总结一下，然后记下来」; 2026-10-20, four amended drafts: 「写得乱七八糟的…不要在原有的基础上改」; on showing changes: 「你一个一个问题问我然后要展现原本是什么，修改建议成什么」
- 2026-10-30: 「扩展到所有的项目，就是进入到 global instruction，还是需要谨慎考虑的，而且需要经得我的同意」
- 2026-10-31, vllm-serve's SKILL.md changes shown one at a time, after two of eight: 「我自己看不过来，你按照Writing for agent skill 里面的原则自己决定吧，然后后面统一都要调用 writing for agent skill 优化一遍」; then 「writing-for-agents skill实际上在对于任何面向agents的所有内容的时候都优化。一开始设计也是按照他的思路来，然后开发完成后再统一调用一遍全量优化」, 「不仅仅针对SKILL.md 和它的 references」, 「甚至包括global instruction里的内容，一个CLAUDE.md AGENTS.md 面向agent的文档，更应该遵守这个，另外我自己读的可能很少，同样也要遵守，所以几乎全部文档都应该遵守，这样写出来的也更可读，一切面向agent的东西，还有全部的文档，都要这样走这个流程」; on my first wording, a list of document kinds: 「你这样一个个列举会不会感觉很烦，可以写的大一点，也没关系」, then 「可以在后面加包括但不限于，并列上你刚才举例的，因为我怕有时候他不会认为这种场景，所以列出来还是保留吧，但是可以放在后面」

**§5 Deciding with the user**
- 2026-10-13, a redesign presented as a mechanism table with a line budget: 「这个好像不是我定的吧，没有这些具体的硬性规定，只需要你根据writing for agents来就行了… 像你讲的段机制这些，我根本就不了解。你应该讲实际的例子，比如应该怎么过之类的，或者说整体的设计思路、流程，或者是大致的结构… 需要我去判断决定了，你一条一条问我。」
- 2026-10-20, designing an open issue: 「注意，现在只是讨论阶段，还没有到实行阶段，所以一切都是只读的。另外，有一些补充信息，比如我跟你讨论过程中的补充信息、明确的方向或者一些做法，就应该及时补充进issue中。」
- 2026-10-29, after a two-question dialog: 「一个一个问题问我，不要用这种交互的形式。你需要直接在对话中讲清楚上下文背景还有问题，然后给出选项和推荐，为什么。另外，如果我觉得哪里不妥，我补充并和你讨论的」; on labels: 「之后别再用这种路x的表达了，很奇怪，要么就123 ABC 方案x」
- 2026-10-30: 「还有问问题的方式，要一个一个问」, citing grilling: "Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a later round, not this one."

**§6 Briefing subagents**
- 2026-09-21: 「如果有些任务是可以并行去做的，你可以并行几个subagent去完成，提高效率」
- 2026-10-12, after five subagents each grew their own mechanisms: 「不要派子agent，你直接在主agent上修改」; 2026-10-20, onto a fixed design: 「如果有模块可以并行做的就派发subagent并行做，提高效率」
- 2026-10-30, files an agent wrote into the repo root: 「为什么在项目根目录下会有 local API 这些东西啊？乱放啊？」

**About this document** — 2026-10-30: 「这个点我觉得你应该记到设计思路、设计理念里面了。因为我已经反复提过好多次了」, 「而且，我刚才说的这个设计理念，不仅仅是你一个 skill 用到的，而是所有的 skill 对于脚本和 Agent 之间的关系、如何相互协作以及边界。我说的这些重复的内容你都需要记录」, 「包括经常提到的 writing for agent 的设计思路与理念，还有以前说过的mattpocock/skills的设计理念」, 「其他项目暂时是不需要的，只是我们这个项目中需要」, 「因为我觉得你的 design principle 不应该是根据我的话去组织结构的。因为我的话有时候比较零散或者跳跃，你需要根据自己的形式，或者对我们这个文档的 principle 表达最顺的形式去展现」, 「我的当然也要记，但是是记在末尾的，是无关紧要的。只有去查证的时候，或者你不确定的时候，去看一眼。前面是放最重要的内容的。你不要因小失大」, 「当我经常提到或者纠正你的错误时，如果我的话中包含一些设计理念，或者比较顶层、抽象的内容，你需要：1. 组织语言，把我的话重新排版；2. 找到我说的核心点，组织成比较正式的语言；3. 问我要不要加入到 design principles 里面。这步“判断、组织、整理”的流程，我交给你来自动去做。」
