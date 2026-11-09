# paddleocr：旋转 PDF 的块文字层没有按页面旋转换算坐标

- 来源：2026-11-09 修 crop-box 区域命令时，subagent 指出旧边界，主 agent 用合成 PDF 核实。
- 状态：open；本轮只修打印给调用方的 pdftotext 区域命令，此处另行处理。

## 现场与证据

使用 `paddleocr/tests/test_objects.py` 的 `ShowRegion` 场景：MediaBox 为 `(20,30,632,822)`，CropBox 为 `(61,77,573,769)`，PDF 用户坐标 `(150,650)` 放 `TARGET`，`(150,600)` 放干扰文字 `LOWER`。Poppler 的 `-bbox -cropbox` 给出渲染页面中的目标框，再调用 `doc.show`。

- 未旋转时，show 直接展示的文字层和打印的区域命令都取得 `TARGET`。
- 页面 `/Rotate` 为 90、180、270 时，修正后的区域命令均取得 `TARGET`，但 show 直接展示的文字层仍为 `(none)`；直接定义和从父节点继承 MediaBox 两种情况相同。
- 原因：`show` 把渲染页面中的框加上裁剪框原点后，直接交给 PDFium `get_text_bounded`；后者使用未旋转的 PDF 用户坐标。其他文字层核对函数是否受相同问题影响还需分别核实。

## 影响与下一步

旋转页上，调用方可能把错误的空结果当成没有文字层。当前可执行 show 打印的 pdftotext 命令，并对照页面图像。

后续先明确渲染坐标到 PDF 用户坐标的转换及调用范围，再修正；现有图表链接对旋转页不给矩形，不应无意改变该行为。这里不预先决定共用 helper 或新的检测规则。
