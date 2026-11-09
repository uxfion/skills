# paddleocr："Figure 4 (continued): …" 这种续页图注没被认成图注

- 来源：2026-11-09 精读那一轮，读论文的 subagent 整理 Pseudo-CEUS（`chenPseudoContrastEnhanced2025`，Published-RSNA）的包时报告。用户没有提。
- 状态：open。

## 经过

- **看到什么。** 第 7 页的图注 `Figure 4 (continued): (C) For the liver dataset and the breast dataset, …` 被模型读成普通文字块（p7-11），不是 `figure_title`。所以第 7 页那部分图（Figure 4 的 C 栏）配不上编号，笔记里的 Figure 4 链接只会落到第 6 页的 A、B 栏。
- **怎么解决的。** subagent 用 `ocr.py cut <包> … --caption p7-11` 点名这段是那张图的图注，C 栏才拿到 "Figure 4" 的编号。A、B 栏配 p6-18。
- **为什么不顺。** 期刊里一张图跨页、续页图注写 "(continued)" 很常见（RSNA、Radiology 系列都这样）。现在只有读论文的 subagent 整理时自己发现、手动点名，才能补上。

## 待看

paddleocr 的 papers.md 和图注识别，要不要把 "Figure N (continued)" 当成第 N 张图的另一部分图注；同一编号的两段图注，`ocr.py objects` 怎么给笔记里的 "Figure 4" 定框（框住两页，还是只框第一页）。

## 存笔记时的结果（同日）

`pr.py put` 的 `unmatched` 里，这篇有三处是包的问题：

- **Fig. 4**（`not_in_package`）：用 `--caption p7-11` 点名之后，包里有 p6-18、p7-11 两段 "Figure 4" 图注。`ocr.py objects` 碰到两段同号图注就不给编号（`key` 为 null），笔记里的 Fig. 4 反而一个都链不上了。所以光会点名还不够：同一编号的两段图注，要能合成一张跨页的图。
- **Table 1、Table 2**（`not_in_package`）：模型把这两张表的表题丢了，subagent 照 PDF 补了回来，但只能补成一段普通文字，挂不到表上，`objects` 认不出这两张表。图有 `cut --caption` 能点名，表还没有对应的办法（待查）。

这三处现在都是普通文字，按 `put` 的提示保留。修好后，重新渲染这个包、再 `pr.py put` 一次，就能补上链接。

## 又一种写法（同日，ALADYNOULLI，Nature）

Nature 的跨页图把图注放在下一页，图下只印一行 `Extended Data Fig. 1 | See next page for caption.`。这篇的文字层里词之间没有空格：`ExtendedDataFig.1|See next page for caption.`、`ExtendedDataFig.10|…`，识别不出来，ED Fig. 1、ED Fig. 10 没有编号。读论文的 subagent 用 `--caption` 把它们指到下一页的真图注（p23-1、p33-1）上。同一篇的 `Fig.5| See next page` 能正常配对。
