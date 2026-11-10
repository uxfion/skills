# paddleocr：表题被模型丢掉后，没法补挂到表上

- 来源：2026-11-09 精读那一轮，读论文的 subagent 整理 Pseudo-CEUS（`chenPseudoContrastEnhanced2025`，Published-RSNA）的包时报告。用户没有提。从续页图注那张 issue（[archive/20261109-paddleocr-continued-caption-not-a-caption-fixed.md](archive/20261109-paddleocr-continued-caption-not-a-caption-fixed.md)）拆出，2026-11-10。
- 状态：open，没讨论。

## 经过

- **看到什么。** 模型把 Table 1、Table 2 的表题丢了。subagent 照 PDF 把表题补回 Markdown，但只能补成一段普通文字，挂不到表上；`ocr.py objects` 认不出这两张表，`pr.py put` 报 `not_in_package`，笔记里的 Table 1、Table 2 保留成普通文字，没有链接。
- **和图的差别。** 图有 `ocr.py cut <图> --caption <块>` 能点名图注；表没有对应的办法。
- **实际影响。** 只碰到过这一篇的两张表；影响的是笔记里这两张表的跳转，表的内容和数字不受影响。

## 待看

先数一下库里的包有多少张表没有表题（规模），再定值不值得给表加点名的办法，还是这类表就保留成普通文字。
