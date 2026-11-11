# agent-instructions：Hermes 段的两件没定的事

- **来源 · 日期**：从 `archive/20260929-agent-instructions-reusable-memories-wontfix.md` 末尾“走 Auto memory 流程的两条”带出来 · 2026-11-10（那张单子当天归档，这两条不属于 how-we-work，单独留一张）。
- **背景**：全局指令的 Hermes 版是 `agent-instructions/HERMES.md`，它是 `AGENTS.md` 加开头的元数据和一段 Hermes 专有的话。全局指令由用户自己管，改 Auto memory 一节要照 `agent-instructions/auto-memory-update.md`。
- **用户原话**：无（两条在 2026-09-29 那张单子里是转述）。
- **现场**：
  1. Hermes 读不到网关工作目录以外项目的 `AGENTS.md`。当时用户的临时工作区里有一份待确认的草稿。
  2. 让 Hermes 把项目知识写进 `.memory/`。用户当时决定暂缓。
- **为什么要紧**：how-we-work 的通用块是靠项目的 `AGENTS.md` 进到上下文里的；Hermes 读不到的项目，这套规则在 Hermes 里就不生效。
- **方向**：两条都改 `HERMES.md` 的 Hermes 段，由用户决定做不做、什么时候做。没拍板。
- **状态**：open
