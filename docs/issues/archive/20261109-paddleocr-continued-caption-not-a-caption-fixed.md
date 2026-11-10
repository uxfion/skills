# paddleocr："Figure 4 (continued): …" 这种续页图注没被认成图注

> **已解决（2026-11-10）。** 跨页的图算一张图：整理数据包的 subagent 把每一部分都指到第一页的那段图注上（`ocr.py cut <图> --caption <第一页的图注>`，第一页的那部分也指一次），`ocr.py objects` 就给出一个编号，落在第一页。写在 `paddleocr/references/settle.md` 第 5 步；`objects` 原来会把两页的框并在一起算，改成只用第一页的部分（`scripts/doc.py`，测试在 `tests/test_objects.py`）。在 Pseudo-CEUS 的包上试过：Fig. 4 得到 `fig:4`，落在第 6 页。
>
> **没选的做法。** 让脚本认 `(continued)` 这个词、把带这个词的那段算续页：是往脚本里加关键词，`(cont.)`、`(续)`、Nature 的 `See next page for caption` 会接着加。用户 2026-11-10：「有一些通用的东西或者 Agent 能做的东西，那就让 Agent 去做」；「A′ 应该是更符合我们的设计原则的吧」。也没有改"被点名的图注不再配给别的图"这条规定来省掉第一页那一次点名：它是为另一种情况定的。
>
> **留下的。**
> - Nature 的 `See next page for caption` 用现成的 `--caption` 指到下一页的真图注就行，那次已经这样做了，不用改。
> - 表题被模型丢掉时没法补挂到表上，另开了 [20261109-paddleocr-lost-table-caption-cannot-be-named.md](../20261109-paddleocr-lost-table-caption-cannot-be-named.md)。
> - Pseudo-CEUS 库里的那个包还是旧做法（两段同号），下次整理或读到时照新做法指一遍，再 `pr.py put`。

- 来源：2026-11-09 精读那一轮，读论文的 subagent 整理 Pseudo-CEUS（`chenPseudoContrastEnhanced2025`，Published-RSNA）的包时报告。用户没有提。
- 状态：已解决。

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
