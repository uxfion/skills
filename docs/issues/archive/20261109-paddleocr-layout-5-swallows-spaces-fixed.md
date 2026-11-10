# paddleocr：版式 5 收紧行内公式时，会把两个公式之间正文两边的空格吞掉

> **已解决（2026-11-09）**：新增 Markdown 版式 6，按顺序给 `$` 配对，只收紧两侧都有空格的那一对（`0373daf`）；版式号加进 `versions()`，旧版式渲染的文件夹下次 `ocr.py parse` 时会重新渲染。见下面「修法」「验证」。

- 来源：2026-11-09 精读那一轮，读论文的 subagent 整理 MIRAGE（`borghesiMIRAGEMultiscaleLesionInformed2026`）的包时报告；同一轮 TISA 的 subagent 也碰上了，主 agent 存包前又在 athreya 的包里看到。用户没有提。
- 状态：已解决（见上）。

## 经过

- **是什么。** 同日早些时候（`ff62265`，随 `cb294cc` 推送并重装）加了版式 5：行内公式写成 `$x$`，不再是 PaddleOCR 给的 `$ x $`，这样 Zotero 笔记才认得出是公式。收紧用的是一条正则 `\$[ \t]+(…)[ \t]+\$`。
- **看到什么。** 一段里已经有紧贴的公式时，正则会把前一个公式的右 `$` 和后一个公式的左 `$` 当成一对，吞掉中间正文两边的空格：
  - `$x$ and returns $\hat{y}$` → `$x$and returns$\hat{y}$`（MIRAGE）；
  - `loss term: $ \lambda_{adv}=1 $ for adversarial loss, $ … $` → `loss term:$\lambda_{adv}=1$for adversarial loss,$…$`（athreya，已存进 Zotero 的包）。
- **影响。**
  - 渲染出来的 Markdown 错了，记录（JSON）本身没错：重新渲染就能恢复。
  - 例外：agent 在版式 5 下改过的段落，`commit` 把带错的整段当成改动记进了记录，重新渲染也还原不了。这一轮只有 ALADYNOULLI 的两段（p15-12 和下一段），已手工补回空格、记录在案。
  - 这个 bug 不会把词弄丢，只吞空格，所以按词比对的检查（`missing_text`、`diff`）都看不出来。

## 修法

- **版式 6**（`paddleocr/scripts/doc.py` 的 `hug_math`）：按行把 `$` 从左到右两两配对，只收紧两侧都有空格的那一对；一行里 `$` 是单数个就原样不动（`$5 and $10` 这种钱数照旧）。
- **版式 5 原样保留**：`commit` 按 Markdown 第一行写的版式重新渲染再比对，所以已有的版式 5 文件必须还能原样读回。要是直接改版式 5，正在读论文的 subagent 手里那些文件里没碰过、却被弄坏的段落，会被误记成它们的改动。
- **版式号加进 `versions()`**：原来判断"代码变了、要重新处理"只看 refine、checks、figures、conventions 四项，版式变了不会重新渲染。加上 `render` 以后，旧版式渲染的文件夹下次 `ocr.py parse` 时会按记录重新渲染（不用 GPU，改动和判定都保留），`ocr.py findings` 也会提示。今天以前的记录都没有这一项，所以第一次碰到时都会重新渲染一次。

## 验证

- 测试：`paddleocr/tests/test_doc.py` 的 `test_tight_math_keeps_the_words_between_from_layout_6`（新版式不吞空格，旧版式的文件仍能原样读回）；paddleocr 五个测试文件全过，约定检查通过。
- 真实数据：今天存进 Zotero 的 10 个包，分别用版式 4（不收紧）、5、6 渲染，把公式换成占位符后比较周围的文字和空格。版式 5 有 6 个包、共 29 行和版式 4 不同；版式 6 是 0 行。
- 这 10 个包都已用版式 6 重新渲染，存回 Zotero。

## 剩下的

- 别的项目在这期间用装好的旧版本解析过的文件夹：重装后下次 `ocr.py parse` 会自动重新渲染。其中 agent 在版式 5 下改过的段落如果带了错，重新渲染去不掉，只能在整理那篇时，按 settle.md 的通读对照 PDF 看出来再改。
