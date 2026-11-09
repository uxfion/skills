# paddleocr：表格比对不把公式拼回去，表头带下标的表都会误报

- 来源：2026-11-09 精读那一轮，读论文的 subagent 整理 MIRAGE（`borghesiMIRAGEMultiscaleLesionInformed2026`，arXiv v1）的包时报告。用户没有提。
- 状态：open。

## 经过

- **跑的什么。** `ocr.py render` 后包里有 3 条 `table_mismatch`（p4-12 的 Table 1、p6-2 的 Table 2、p6-4 的 Table 3）。subagent 对照 PDF 逐格核对。
- **看到什么。**
  - 3 条报的都是同一件事：文字层把下标和正文粘成一个词（`SSIMtum`、`AUROCC`），包里的表写成公式（`$\mathrm{SSIM}_{tum}$`），两边的词对不上。数字和格子其实都对。
  - 真正的错没被报出来：Table 1 丢了 22 个表示显著性的 `∗`；Table 2 的表头 `SSIM_tum` 被读成了 `SSIM_lum`。subagent 是逐格看图才发现的。
  - 同一篇里 Eq. (2) 读成了乱码（`\cap^{\prime}`），也没有任何检查报出来。
- **原因（subagent 读代码的判断，未核实）。** `paddleocr/scripts/ocrlib/checks.py` 的 table_mismatch（约 466 行）对包里的表分词时没有经过 `glue_math`；正文的检查（`missing_text`、`diff`）是会把公式拼回去再比的。
- **为什么不顺。** 误报让每张带下标的表都要人工逐格核一遍，真正的错反而淹在里面；报的地方和错的地方不是同一处，检查起不到指路的作用。

## 待看

table_mismatch 分词前，先像正文检查那样把公式拼回去（`glue_math`），再在 MIRAGE 这 3 张表上看误报是否消失、两处真错（丢的 `∗`、`SSIM_lum`）能不能报出来。公式乱码没有检查，另看要不要、能不能查。
