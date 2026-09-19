# Agent Skills & Instructions

个人使用的 agent skills 和全局指令，支持 Claude Code、Codex 等 harness。

## 配置当前 harness

把下面这句话发给你的 agent：

> 请读取 https://github.com/uxfion/skills 的 README，按其中说明为我当前使用的 harness 配置全局指令，保留已有的无关配置。

| Harness | 本仓库源文件 | 默认全局目标 |
| --- | --- | --- |
| Codex | [agent-instructions/AGENTS.md](agent-instructions/AGENTS.md) | `~/.codex/AGENTS.md` |
| Claude Code | [agent-instructions/CLAUDE.md](agent-instructions/CLAUDE.md) | `~/.claude/CLAUDE.md` |

将对应文件合并到实际生效的全局指令中。确认 [uv-python](uv-python/SKILL.md) 已可用，缺失时按 [Skills](#skills) 安装；路径及 `hf`、`gh` 的安装与认证描述按本机情况适配。其他 skills 按需安装。

Claude Code 的 auto memory 由自身 harness 管理；AGENTS.md 的记忆规则用于补齐缺少该机制的 harness。共享记忆位于各项目的 `.memory/`，全局 Git ignore 应包含 `**/.memory/` 和 `**/.claude/settings.local.json`。

配置只使用表中的源文件；根目录 CLAUDE.md 是本仓库的项目说明，`references/` 是来源存档。

## Skills

- [uv-python](uv-python/SKILL.md) — 使用 uv 执行 Python、管理依赖和环境。
- [wx-cli](wx-cli/SKILL.md) — 通过 wx CLI 查询本地微信数据。

用 [skills CLI](https://www.skills.sh/docs) 安装，`npx` 可换成 `bunx`：

```bash
npx skills add uxfion/skills --skill uv-python -g   # -g 全局安装，省略则装到当前项目
npx skills add uxfion/skills --list                 # 只查看可用 skills
```

## 更新 Auto memory

上游提示词变化时，按 [Auto memory 更新指南](agent-instructions/auto-memory-update.md) 重新适配；日常配置无需读取来源存档。
