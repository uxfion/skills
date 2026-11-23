# how-we-work：规定 `AGENTS.md` 的条目带用户原话，和 writing-for-agents 相悖

- **来源 · 日期**：`Hub/network` 项目的会话，按 writing-for-agents 精简 `AGENTS.md` 时用户提出 · 2026-11-23。
- **背景**：network 项目 `AGENTS.md` 通用块之外的 6 条，每条都以 `From:` 加一串用户原话结尾。精简时用户指出：原话本身就不该进 `AGENTS.md`，不论这条规则是从对话、记忆还是别的文件提炼来的。
- **用户原话**（2026-11-23，语音输入，「Waiting for agents」按意思改成 writing for agents）：「另外有一点，我说的一些话，你觉得有必要进到 agentsMD 里面吗？我感觉我说的话都不应该记到 agentsMD 的」「要根据writing for agents来的」「而且就算本身是有其他地方提炼出来的，从记忆或者从其他地方，那这点确实是HWW那边的问题，本身agents.md 按照writing for agents，我说的是不应该放的吧。你可以记个issue」
- **现场**：
  - `references/records.md:217`：`AGENTS.md` 通用块之外和 `docs/conventions/` 的条目格式是「- **<the rule, one sentence>.** From: <the date, and the user's words in 「」 or the case>.」。
  - `references/records.md:196`：「A sentence or two of the user's stays in the entry's `From:`」，更长的对话才放 `docs/rules-sources.md`。
  - `common.md:112`（How a rule grows）：规则从 `.memory/` 搬进项目文件，「An entry in the user's own words you write」。记忆条目本来就带原话和 Why，搬进 `AGENTS.md` 时原话一起进去了。
  - writing-for-agents：常驻上下文的每个词每轮都要付出；只在部分情况下用到的材料放到指针后面。agent 照规则本身去做，原话只在规则管到哪里说不清时才查。
- **为什么要紧**：`AGENTS.md` 每轮都在上下文里。原话不改变 agent 的做法，却占位置、冲淡规则。
- **方向**：`AGENTS.md` 的条目只写规则；出处（日期、原话、决策编号）一律放 `docs/rules-sources.md`，`AGENTS.md` 里一行指向它；`common.md:112` 和 records 的条目格式跟着改。`docs/conventions/` 要不要同样处理：它只在某类工作时才读，推测代价小一些，待定。没拍板。network 项目 2026-11-23 的做法（用户选的，`docs/rules-sources.md` 先不建，「先不建立 rules-sources吧，等skills那边仓库的issue看吧」）：`AGENTS.md` 只留规则、不带出处，原来只记在 `AGENTS.md` 里的原话写进它的决策记录 D20261123-2，等这个 issue 定了再搬。
- **skills 仓库的讨论（2026-11-23）**：这张和 `20261123-how-we-work-agents-md-facts-vs-rules.md`、`20261117-how-we-work-project-design-rules-not-conventions.md` 并成一件事谈（`AGENTS.md` 通用块之外放什么）。main agent 先提了只改三处文字的方案，并问约定文件要不要同样去掉出处（A 两处一样 / B 只改 `AGENTS.md` / C 约定文件留证据指针），用户没有选，说的是：
  - 「因为那边的 Agents.md 是按照那边的想法来的，所以我希望你全面地去设计一下，看如何避免这个问题。」
  - 「我感觉 Agents.md 就不应该出现原话这种东西，这本身就不符合 writing for agents 的原则。因为 agents.md 每次对话都会被载入进上下文，这些很关键，只有非常至关重要的东西才会放到agents里面。同时我相信他也要保持简洁高效。一些冗余或者不必要的东西肯定是不应该放进去的。」
  - 「我现在需要你全面地考虑一下我们 HWW 的架构，然后设计一个最优的方案。另外，我感觉如果 sources 本身会记到其他地方，你可能要全面地评估一下，按照设计原则，然后再跟我讨论一下。我不希望是一个修修补补的状态，我希望整个系统是优雅的、最高效的」
  
  所以 network 那次精简不当模板；出处记在哪要整体评估后再和用户讨论。方案没拍板。
- **设计**：和另外两张并成一件事，写在 `docs/specs/20261123-how-we-work-project-rules-spec.md`（2026-11-23，等用户说可以开始改）；决定 D20261123-1 到 -6。
- **状态**：open
