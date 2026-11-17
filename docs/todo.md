# 待办

要做的事和它在等什么。格式见 how-we-work 的 records 参考 *To-do*：每项一行，编号 `B<n>` 递增；状态 ☐ 未开始 · ⏳ 进行中 · ✅ 完成 · ⏸ 暂缓 · ❓ 等人 · ↗ 移到别处（写明去向）。用户的事项带原话，main agent 加的写明来源。这个仓库是公开的：项目只写名字，不写本机路径。

| # | 日期 | 用户原话 / 来源 | 事项 | 状态 | 何时提醒 / 下一步 |
|---|---|---|---|---|---|
| B1 | 2026-11-17 | main agent：内存盘两张 issue（`20261113-how-we-work-ram-root-and-incremental-fetch.md`、`20261113-vllm-serve-ram-disk-root.md`）的文字已改，没发布 | 发布：推送、`npx skills update -g`、在本仓库和清单上的各项目跑 sync；然后在 hc_deduction 里清掉被新参考盖过的：`docs/conventions/experiments.md` 内存盘那条，`docs/servers.md` 里的通用部分，以及那里错的 `loginctl show-logind`（应为 `loginctl show-session -p RemoveIPC`）；清之前确认那边没有会话在跑；最后关两张 issue | ❓ 等用户说推送 | 下一张 how-we-work issue 做完时一起问要不要发布 |
