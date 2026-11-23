# 待办

要做的事和它在等什么。格式见 how-we-work 的 records 参考 *To-do*：每项一行，编号 `B<n>` 递增；状态 ☐ 未开始 · ⏳ 进行中 · ✅ 完成 · ⏸ 暂缓 · ❓ 等人 · ↗ 移到别处（写明去向）。用户的事项带原话，main agent 加的写明来源。这个仓库是公开的：项目只写名字，不写本机路径。

| # | 日期 | 用户原话 / 来源 | 事项 | 状态 | 何时提醒 / 下一步 |
|---|---|---|---|---|---|
| B1 | 2026-11-17 | main agent：内存盘两张 issue（`20261113-how-we-work-ram-root-and-incremental-fetch.md`、`20261113-vllm-serve-ram-disk-root.md`）的文字已改，没发布 | 发布：推送、`npx skills update -g`、在本仓库和清单上的各项目跑 sync；然后在 hc_deduction 里清掉被新参考盖过的：`docs/conventions/experiments.md` 内存盘那条，`docs/servers.md` 里的通用部分，以及那里错的 `loginctl show-logind`（应为 `loginctl show-session -p RemoveIPC`）；清之前确认那边没有会话在跑；推送前按 `AGENTS.md` 扫一遍要推出去的提交（从 `7232ae3` 起，文件和提交信息）；最后关两张 issue | ✅ 2026-11-23 | 余量定成至少留 1/4（D20261123-13），已发布、重装；hc_deduction 里抄的旧内容已清（`899cd5b`）；两张 issue 归档 |
| B2 | 2026-11-17 | 用户：「不要再连Pro 6000了，你刚才没有连Pro 6000吧？这台已经被撤回了」 | hc_deduction、diffusion、ceus 的 `docs/servers.md` 还把 pro6000 列为可用的服务器：标成已撤回 | ✅ 2026-11-23 | ceus（`b0b1dd16`）和 hc_deduction（`61da211`）的 `docs/servers.md` 标了已撤回、不要连；diffusion 早已标好 |
| B3 | 2026-11-23 | 用户：「块外什么都不放. 就只维护通用块就行了.」 | 项目自己的规则放哪：`AGENTS.md` 只有标题和通用块，规则进 `docs/rules.md` 或约定文件。spec `docs/specs/20261123-how-we-work-project-rules-spec.md`，决定 D20261123-1 到 -10 | ✅ 2026-11-23 | 已发布（rev 2026-11-23），五个项目和本仓库的块外都清空了（D20261123-10）。留在各项目里的：约定文件旧条目后面的原话，改到哪条搬哪条 |
