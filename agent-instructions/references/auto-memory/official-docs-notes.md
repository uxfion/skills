# Claude Code 官方 auto memory 文档

- 来源类型：Anthropic / Claude Code 官方产品文档，内容随产品更新。
- 原始页面：<https://code.claude.com/docs/en/memory>
- Markdown 下载地址及最终 URL：<https://code.claude.com/docs/en/memory.md>（无重定向）。
- 获取时间（shell UTC）：`2026-09-18T08:58:01Z`。
- HTTP：`200`；Content-Type：`text/markdown; charset=utf-8`。
- 本地原文：[claude-code-memory-docs.md](claude-code-memory-docs.md)，477 行、38,430 字节，未改写。
- SHA-256：`98c6d06ea754d557011393608849dfbe23eed8634edb3db318f77178b6ce0f1b`。

## 已核对的行为

- **内容与写入**：默认启用，记录 `user`、`feedback`、`project`、`reference`；跳过代码、Git 历史或 CLAUDE.md 已能提供的信息，并非每次会话都写入。[来源](https://code.claude.com/docs/en/memory#auto-memory)
- **路径与 worktree**：默认 `~/.claude/projects/<project>/memory/`；同仓库的 worktree 和子目录共享，默认仅本机保存；可用 `autoMemoryDirectory` 自定义绝对路径或 `~/` 路径。[来源](https://code.claude.com/docs/en/memory#storage-location)
- **加载与索引**：启动加载 `MEMORY.md` 的前 200 行或 25KB，以先到的限制为准；索引每条一行，主题文件按需读取。[来源](https://code.claude.com/docs/en/memory#how-it-works)
- **subagent**：普通子代理不加载主会话 auto memory；fork 继承父会话与系统提示词；配置 `memory` 的子代理使用独立目录。[来源](https://code.claude.com/docs/en/memory#how-it-works)
- **格式**：普通 Markdown，分类记在 frontmatter 的 `type`；已有 YAML frontmatter 的文件写入时增加 ISO 8601 `modified`（需 v2.1.214+）；不会给无 frontmatter 的文件补建 frontmatter。[来源](https://code.claude.com/docs/en/memory#how-it-works)

## 来源边界

这是本次获取的官方文档快照，不能证明过去某版本的行为。页面没有规定本项目采用的完整 YAML 模板、`metadata` 嵌套结构、wiki 链接或 `<name>.md` 命名约定；不要把这些本项目约定称为该文档的原始规范。
