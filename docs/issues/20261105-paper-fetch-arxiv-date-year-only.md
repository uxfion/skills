# paper-fetch：arXiv 论文的日期只有年份，arXiv 接口里的完整日期没用上

- 来源：主 agent，2026-11-05，p2z Unix 约定样板的真写入验收（spec `20261104-skills-unix-conventions-spec.md` 第 9 节）。用户没有提，是导入时碰到的。
- 状态：open。

## 经过

- **跑的什么。** `pf.py identify 2611.05206 -o <imp>/fetch`（UltraDiff，*Diffusion Plug-in Priors for Self-Supervised Ultrasound Video Restoration*，只有预印本）。
- **看到什么。** result 的 `csl.issued` 只有 `2026`，警告 `date is year-only`；`p2z.py draft` 照此起草，条目的 `date` 是 `2026`。`prepare` 的 `decide` 里不列这条：result 自己的警告留给 agent 去读（import.md 第 3 步），这本身没错。
- **为什么不顺。** 日期来自 arXiv DOI 的 DataCite 记录，那里只有年份；而同一次 `identify` 已经请求过 `export.arxiv.org/api/query`（日志里有），那里有 `published`（v1 提交时间，这篇是 2026-11-03T16:55:01Z）和 `updated`（v2，2026-11-04）。主 agent 只好再查一次 arXiv 接口，手动把条目日期改成 `2026-11-03`。每篇只有预印本的论文都会这样。
- **又碰到两次（同日全流程试用）。** 导入 agent 导入的 FSCG（arXiv 2607.11655，v1 是 2026-07-13）和 SonoWorld（arXiv 2610.19327，v1 是 2026-10-14），条目的日期都只有 `2026`。agent 报告了这件事，但没有手动去补。可见光靠 agent 自己读 result 的警告去补，补不全。

## 建议

DOI 记录的日期只到年份、而 arXiv 接口给了 `published` 时，`identify` 用 `published` 的日期补全 `issued`，并在警告里写明出处。要定的一点：预印本条目用 v1 的提交日（`published`），还是最新版的日期（`updated`）。主 agent 这次用的是 v1 提交日。
