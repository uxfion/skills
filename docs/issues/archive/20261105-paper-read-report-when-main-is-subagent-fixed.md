# paper-read：主 agent 本身是 subagent 时，reader 的报告没地方存

> **已解决（2026-11-06）**：SKILL.md *Read a paper* 第 2 步加一句：由 subagent 跑这个流程时，它自己就是 reader，照 reading.md 读，再拿自己的结果从第 3 步接着走，原本存成 `report.md` 的内容留在它的回复里。主对话照旧把 reader 的回复存成 `report.md`。2026-11-06 起主 agent 读论文时自己当主 agent、每篇派一个 reader，碰不到这个问题。

- 来源：2026-11-05 全流程试用，三个读论文 agent 都碰到了。用户没有提。
- 状态：open。

## 经过

- **怎么跑的。** 主 agent 派了三个 subagent，每个照 paper-read 读一篇。它们自己就是 subagent，不能再派 reader（原则 §6，*One level deep*），所以 reader 的活由自己做，主 agent 那几步也是自己做。
- **看到什么。** *Read a paper* 第 4 步让主 agent 把 reader 的回复存成 `<scratch>/report.md`。三个 agent 写这个文件时，都被 Claude Code 拒了："Subagents should return findings as text, not write report files"。三个都只好把报告写进自己的回复。
- **为什么不顺。** 只要 paper-read 不是在主对话里跑，而是由 subagent 跑（比如项目里的主 agent 把"读这篇"交给一个 subagent），`report.md` 就存不下来，第 4 步"照 report.md 一条条处理"也就没有了依托。三个 agent 还都不确定，reader 和主 agent 是同一个人时，第 4 步该怎么走。

## 待看

- 报告不一定要落成文件：第 4 步可以写成"reader 的回复，存成文件或者就留在对话里"；或者换个不叫 report 的文件名，比如笔记旁边的 `reading-notes.md`，不过 Claude Code 的这条规则是按什么判断的，要先查清楚。
- 写一句：自己既是 reader 又是主 agent 时，第 2 到第 4 步怎么合并着走。
