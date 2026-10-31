# Agent Skills & Instructions

个人使用的 agent skills 和全局指令，支持 Claude Code、Codex 等 harness。

## 配置当前 harness

把下面这句话发给你的 agent：

> 请读取 https://github.com/uxfion/skills 的 README，按其中说明为我当前使用的 harness 配置全局指令，保留已有的无关配置。

| Harness | 本仓库源文件 | 默认全局目标 |
| --- | --- | --- |
| Codex | [agent-instructions/AGENTS.md](agent-instructions/AGENTS.md) | `~/.codex/AGENTS.md` |
| Claude Code | [agent-instructions/CLAUDE.md](agent-instructions/CLAUDE.md) | `~/.claude/CLAUDE.md` |
| Hermes | [agent-instructions/HERMES.md](agent-instructions/HERMES.md) | 复制为 `~/.hermes/skills/agent-instructions/SKILL.md`，并加入 `skills.auto_load` |

将对应文件合并到实际生效的全局指令中。确认 [uv-python](uv-python/SKILL.md) 已可用，缺失时按 [Skills](#skills) 安装；路径及 `hf`、`gh` 的安装与认证描述按本机情况适配。其他 skills 按需安装。

Claude Code 的 auto memory 由自身 harness 管理；AGENTS.md 的记忆规则用于补齐缺少该机制的 harness。共享记忆位于各项目的 `.memory/`，全局 Git ignore 应包含 `**/.memory/` 和 `**/.claude/settings.local.json`。

配置只使用表中的源文件；根目录 AGENTS.md 是本仓库的项目说明，`references/` 是来源存档。

## Skills

- [paddleocr](paddleocr/SKILL.md) — 用本机 GPU 上的 PaddleOCR-VL 把文档的 PDF、截图或扫描件（论文、报告、幻灯片等）解析成 Markdown 和记录 JSON（阅读顺序、公式、表格、图、页码标记），对照 PDF 文字层核对，再由子代理核对修正，每处修改连同原因都记在 JSON 里；需先装 `paddleocr` uv tool（[安装](paddleocr/references/install.md)），再装 vllm-serve 可快十到二十倍。
- [paper-fetch](paper-fetch/SKILL.md) — 认出是哪篇论文（DOI、arXiv 号、CSL 元数据、预印本和正式版），再取全文：开放获取、经学校登录的出版商、图书馆发现系统或用户的浏览器，每个 PDF 都核对是不是这篇、标上是哪个版本；paper-to-zotero 导入时调用它，也能单独用。
- [paper-read](paper-read/SKILL.md) — 把 Zotero 库里的论文读成论文笔记：派一个读论文的子代理，按问题树一问一问地从 PDF 和结构化包里作答，读完检查再经 paper-to-zotero 存进 Zotero；也管笔记的"用在哪里"、主题笔记和更正。读法还在设计中，这一版是框架。
- [paper-to-zotero](paper-to-zotero/SKILL.md) — Zotero 里的一切：按题目 / DOI / arXiv 号 / 清单 / bib 导入论文（由 paper-fetch 认论文、取全文），归类、打标签；按 citation key 整理、修字段，笔记取出成 Markdown 再存回，导出 bib，取论文的结构化包和 PDF。
- [uv-python](uv-python/SKILL.md) — 使用 uv 执行 Python、管理依赖和环境。
- [vllm-serve](vllm-serve/SKILL.md) — 一台 GPU 机器上统一的 vLLM 后端（本机，或 ssh 过去、多人共用的服务器）：一份 vLLM 安装，每个模型一个 profile、一个服务，按需启动、多方共用、空闲自动退出；附共享服务器的部署原则和调优参考；需先装 `vllm` uv tool（[安装](vllm-serve/references/install.md)）。

用 [skills CLI](https://www.skills.sh/docs) 安装，`npx` 可换成 `bunx`：

```bash
npx skills add uxfion/skills --skill uv-python -g   # -g 全局安装，省略则装到当前项目
npx skills add uxfion/skills --list                 # 只查看可用 skills
```

各 skill 的脚本也能直接执行，如 `paddleocr/scripts/doc.py --help`：首行 shebang 交给 uv，按脚本内声明的依赖运行。skill 文档里统一写 `uv run scripts/…`，脚本没有可执行位时也能运行。

## 更新 Auto memory

上游提示词变化，或要修改任一 harness 的 Auto memory 指令时，按 [Auto memory 更新指南](agent-instructions/auto-memory-update.md) 进行，并同步到其他 harness；日常配置无需读取来源存档。
