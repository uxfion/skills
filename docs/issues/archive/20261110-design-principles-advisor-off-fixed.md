# design-principles：关掉 advisor 以后，流程里"advisor 审"那几步怎么办

> **已解决（2026-11-10）。** 规则改成：会话里有 advisor 就交给它审，没有就由主 agent 自己查，节点和顺序不变。改在 `docs/design-principles.md` §2.3 和 §4 两处，用户原话记在 `docs/design-principles-sources.md` §2；主 agent 的记忆同步改了。
>
> 留下的事：
> - **用户的开关。** 用 `/advisor` 手动开关，选择会存成默认值，对之后所有会话和项目生效。主模型用 Opus 5.5 时开，切回 Fable 时要再关一次。
> - **别的项目。** 另一个项目的 `AGENTS.md` 有一条写死的 "Advisor where a mistake is expensive"；`hc_deduction`、`wx` 的记忆里有 `consult-advisor-on-key-decisions` 的旧副本（`ideas` 的那份已经带条件）。在那些项目里干活、碰到这一步时照这里的写法改。

- 来源：用户 · 2026-11-10，会话结束前：「我下一个新的对话就会用 fable 5.2，所以没必要看 advisor 了。你看一下我们流程里面，如果我把 advisor 关闭掉，流程正常能用吗？」
- 状态：已解决。用户过目后于 2026-11-10 `/advisor off`：「OK，我已经关了，你关掉吧」。

## 查到的

- **skill 里没有。** 各 skill 的 SKILL.md、references、脚本、已安装的 skill，以及全局说明，都没提 advisor，也没有 hook 依赖它：关掉不影响 skill 运行。
- **写死 advisor 的文字**：设计原则 3 处（§2.3 *Review before building*、§4 开头、§4 *Changing instruction text*）；主 agent 的记忆 4 条（`consult-advisor-on-key-decisions`、`instruction-wording-workflow`、`own-judgement`、`lean-tests`）；open issue `20261109-paper-read-reader-retries-a-web-endpoint` 里一句「要先过 advisor」。
- **开关是账号级的**：关掉对所有项目生效，见上面"别的项目"。
- **同模型时它给的是什么。** advisor 用的就是 Fable 5.2。主模型也是 Fable 5.2 时，"更强的模型"这一层没了，剩下的是换一个审阅者的角度把整段对话重读一遍。
- **花费**（本仓库 2026-10-09 到 11-10 的会话记录）：有用量记录的调用 186 次，约每天 9 次；每次把整段对话重读一遍、不走缓存，输入中位数 32 万 token，等待中位数 99 秒，合计 5.3 小时。
- **价值的证据只在"弱配强"一边。** 186 次里 185 次是 Opus 5.5 主模型配 Fable advisor，它挑出过真问题：2026-10-29 指出主 agent 说错两处、漏三处；2026-11-09 拦下一处会放松"先给用户看方案"的措辞；2026-11-10 拦下把没发表的稿件细节写进公开仓库。同模型的调用只有 1 次，说明不了什么。官方文档允许同模型配对，没有给同模型的效果数据。

## 定了的（2026-11-10）

- 用户：「我觉得现在就索性关掉了，但是我又希望如果我用 Opus 5.5 主模型，advisor fable 还是有用的」；「如果开的话，我就直接用斜杠命令 /advisor」；「如果advisor开了，你就交给advisor审查；如果没有开，你就自己查就行了」。
- 做法：规则不再写死工具。有 advisor 的会话照旧交给它审；没有的会话，同样的节点、同样的顺序，由主 agent 自己查（改规则仍是先写出原句和新句、查过再改）。新的或重做的设计在两种会话里都有 §2.3 的独立审阅者。
- 没选的：关掉后每次另派一个审阅 subagent 顶替 advisor（每次要写 brief，比 advisor 还费事）；文字不改、让 agent 自己跳过（文字会指向一个不存在的工具）。
