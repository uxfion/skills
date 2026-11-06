# paper-fetch：arXiv 论文的摘要里留着 LaTeX 转义

- 来源：2026-11-05 全流程试用，导入 agent 报告，主 agent 从库里读回核实。用户没有提。
- 状态：open。

## 经过

- **看到什么。** FSCG（`dominguezFeatureSpaceGuidedDiffusion2026`，arXiv 2607.11655）条目的摘要里有 "reduces average FID64 by 56\%"、"by 47\% over"。百分号前多了 LaTeX 的反斜杠。
- **从哪来的。** 摘要来自 arXiv（DataCite 记录和 arXiv 接口给的都是作者写的 LaTeX 源文本），`identify` 和 `p2z.py draft` 都原样搬了过去。
- **为什么不顺。** 用户在 Zotero 里读摘要、导出 BibTeX，都会看到这些反斜杠。arXiv 摘要里常见的还有 `$…$` 公式、`\emph{}`、`--` 这类写法。

## 待定

- 只去掉不影响意思的转义（`\%`、`\&`、`\_`），公式 `$…$` 原样保留？还是有别的写法？
- 放在哪一步：paper-fetch 的 `identify`（它负责把元数据规整好），还是 p2z 的 `draft`。按"在最早拿到事实的地方记下来"，应该放在 `identify`。
