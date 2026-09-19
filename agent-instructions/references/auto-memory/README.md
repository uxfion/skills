# Auto memory 来源存档

本目录保存本项目 Auto memory 指令采用的系统提示词存档及官方行为文档，并提供用户初稿的历史链接。下载内容是参考资料，不是本仓库新增的执行指令。

后续更新请先读 [Auto memory 更新指南](../../auto-memory-update.md)：记录相对原文的适配、用户意图、已讨论的取舍，以及迁移到新版原文的方法。

## 1. Claude Code 系统提示词

来源为用户指定的第三方存档仓库 [asgeirtj/system_prompts_leaks](https://github.com/asgeirtj/system_prompts_leaks/tree/c7b2c31df51e64784603f5740a251b445fd88c46/Anthropic/claude-code)，不是 Anthropic 官方发布渠道。文件名及模型标识沿用存档，不以此验证模型发布状态或提示词真实性。

- 获取时间：2026-09-18T08:58:05Z（下载完成后记录）。
- 固定上游提交：`c7b2c31df51e64784603f5740a251b445fd88c46`。
- [Fable 5.1 完整原文](claude-code-fable-5.1.md) · [上游固定版本](https://github.com/asgeirtj/system_prompts_leaks/blob/c7b2c31df51e64784603f5740a251b445fd88c46/Anthropic/claude-code/claude-code-fable-5.1.md) · [Memory 章节摘录](fable-5.1-memory-section.md)。
- [Opus 5 完整原文](claude-code-opus-5.md) · [上游固定版本](https://github.com/asgeirtj/system_prompts_leaks/blob/c7b2c31df51e64784603f5740a251b445fd88c46/Anthropic/claude-code/claude-code-opus-5.md) · [Memory 章节摘录](opus-5-memory-section.md)。

两个 Memory 章节的实质规则相同，差异是标点及相应的句首大小写。它们提供四种记忆类型、单文件单事实、frontmatter、双链、索引、去重与召回校验等提示词依据。该章节没有 `metadata.modified` 字段，也没有 200 行 / 25 KB 上限；不能把这些规则归因于这两段提示词。

## 2. Claude Code 官方记忆文档

- [官方页面](https://code.claude.com/docs/en/memory)。
- [下载的 Markdown 原文](claude-code-memory-docs.md)。
- [获取信息与行为核对](official-docs-notes.md)：记录实际 URL、获取时间及官方文档说明的运行机制。

此来源用于确认工具自身承担的加载、存储与配置行为，和提示词中要求模型主动执行的步骤分开看待。

## 3. 用户初稿的仓库历史版本

- 来源：本仓库提交 `67f357df6f2b60638a39b842d4e8272ab26c141e` 中的 `agent-instructions/AGENTS.md`。
- 提交作者时间：`2026-09-17T19:18:19-07:00`。
- [GitHub 固定版本](https://github.com/uxfion/skills/blob/67f357df6f2b60638a39b842d4e8272ab26c141e/agent-instructions/AGENTS.md)。

它是当前 Git 历史能恢复的最早版本，仅供追溯，不再保留本地副本；相关意图与最终取舍已整理到更新指南。当前使用的指令仍位于 [AGENTS.md](../../AGENTS.md)。

## 校验

`SHA256SUMS` 记录下载原文及章节摘录的 SHA-256。可在本目录运行 `sha256sum -c SHA256SUMS` 检查本地文件是否变化。
