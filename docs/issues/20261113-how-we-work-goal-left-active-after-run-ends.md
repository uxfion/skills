# how-we-work：用户结束无人值守后，`/goal` 还挂着

- 来源 · 日期：hc_deduction 项目的会话，2026-11-13。
- 涉及的文字：`references/unattended.md`，*Keeping the run alive* 表里 `/goal` 一行。它写了开始时由用户设 `/goal`、给出整行让用户粘贴，没写结束时怎么撤。common block 的 *Unattended runs* 只写了「only their word ends it」。

## 现场

- 开始无人值守时，用户粘贴了 reference 给的那行 `/goal …`。结束条件 (a) 是"对话里出现用户结束这一轮的话"。
- 17:05（北京）用户说：「我已经在线了，可以关闭无人值守了」。main agent 照 reference 做了：把目标文档第一行改成"已结束"，然后先汇报。
- 之后每一轮结束时，后台都还有本地任务在跑：两个 shell 等待任务（等实验队列跑完再关远端的模型服务），有时还有 subagent。`/goal` 的规则是，一轮结束时只要还有后台任务或 subagent 没回来，就先不判定。所以它一直没判，四十多分钟里一直显示 active。harness 提示过一次：「evaluation has been deferred for 31 min because background work is still running」。
- 用户问：「我有一个问题，为什么我已经说了关闭无人值守，goal还在」（2026-11-13）。

## 文档里怎么说（https://code.claude.com/docs/en/goal）

- 条件满足时会自己清掉：「The goal clears automatically once the condition is met …」。
- 用户手动撤：「Run `/goal clear` to remove an active goal before it resolves」（`stop`、`off`、`reset`、`none`、`cancel` 都可以），`/clear` 也会一并清掉。
- 文档没写 Claude 自己怎么撤 goal；判定器「does not call tools」。

## 为什么要改

结束一轮靠的是用户那句话，但 goal 什么时候清掉，取决于后台任务什么时候都结束。一轮刚结束时，常常还有等待任务在等远端作业，比如跑完后关服务、让出卡。这时 goal 就会挂很久。用户看到的是：自己已经说了结束，界面还显示在跑。

## 建议

在 *Keeping the run alive* 的 `/goal` 一行，或 *When the user is back* 里，加一句：用户说出结束的话后，回复里说明目标文档已标为结束；还在跑的后台任务会让 `/goal` 晚一些才判定，请用户输入 `/goal clear` 立即撤掉，agent 自己撤不了。

- 状态：open
