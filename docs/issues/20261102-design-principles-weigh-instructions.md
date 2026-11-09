# design-principles：§5「用户的话是方向」补三处，反馈三分按点内拆分

- 来源 · 日期：用户另一个研究项目（下称"该项目"）的会话，2026-11-02 记录。
- 背景：
  - 当时在该项目里移植本仓库、hc_deduction、ceus 的项目规范，设计见该项目的 `docs/specs/20261102-project-conventions-spec.md`。
  - main agent 给用户看了一份 `AGENTS.md` 简版。用户提了四点意见，main agent 没有先判断，直接全部改进了文件。
  - 用户纠正后，该项目的 `AGENTS.md` 加了"先判断再改"和"反馈按点内拆分"两条规则。用户随后让 main agent 对照本仓库 `docs/design-principles.md` §5。
- 用户原话：
  - 「我觉得你的步骤不应该是，我说什么你就直接改。你应该确认一下，觉得合理你再改；如果有问题的话，你应该跟我讨论。这点和你记忆中的，我之前提到的，我说的都是比较方向性的，不一定是准确的，你要有自己独立的思维能力」
  - 「那 3 类不是说整体就这么分，而是每个点都可能包含这 3 类。所以你要注意区分一下，不要直接把整体给拒绝了」
  - 「Skills那边要改动什么？如果要改动的话，也是新建一个issue去做给那边新加一条issue」
- 现场：
  - §5 现在的写法："Before acting, work out the outcome the user actually wants, weigh their method against the evidence and the alternatives, keep what holds, say where you differ and why, then put the options to the user."
  - 该项目写进 `AGENTS.md` 的两条：
    - "Where it holds, carry it out and say in a line why it holds; where you doubt it or see a more fundamental way, bring the evidence and discuss before changing anything. A correction is new evidence for one case: re-weigh what it changes and keep what it leaves standing, rather than swinging to the opposite."
    - "Triage feedback part by part: one point can hold parts to adopt, parts to reshape and parts to decline, so split it before judging, and never reject a whole point for one weak part."
- 为什么要紧：
  1. **照字面每条指示都要"把选项交给用户"**：合理的小事也来回问。这和用户 2026-11-01 的「这种简单的问题，就没必要按照问问题的流程全部讲清楚吧」冲突。用户这次给的分法是：合理的直接做，并说明理由；有疑问的先讨论。
  2. **"被纠正后倒向另一个极端"只写在记忆里**：这条失败模式（obeying, then flipping）在 `.memory/own-judgement.md`，原则正文没有。
  3. **没有要求照做时说明理由**：用户要能看到 agent 判断过。
  4. **反馈三分没写清按什么单位分**：`.memory/own-judgement.md` 的 Feedback 一段写的是"triage each point"，容易被读成整点采纳或整点拒绝。
- 方向（没拍板）：
  - 改写 §5 "The user's words are direction" 一段，补上第 1–3 点，措辞可参照该项目的那两条。
  - 把 `.memory/own-judgement.md` 的 Feedback 一段改成按点内拆分。
  - 这几条要不要上升到全局指令，归到 `docs/issues/20260929-agent-instructions-reusable-memories.md` 的主题 3"何时自己定、何时问、怎么问"一起决定。
- 状态：open。
