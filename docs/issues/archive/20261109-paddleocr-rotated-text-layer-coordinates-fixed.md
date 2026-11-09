# paddleocr：旋转 PDF 的块文字层没有按页面旋转换算坐标

已解决：`paddleocr/scripts/doc.py`、`ocrlib/checks.py`、`ocrlib/figures.py` 的文字层坐标转换；验证见 `paddleocr/tests/test_objects.py`。

- 来源：2026-11-09 修 crop-box 区域命令时，subagent 指出旧边界，主 agent 用合成 PDF 核实。
- 状态：fixed（2026-11-09）。

## 现场与证据

使用 `paddleocr/tests/test_objects.py` 的 `ShowRegion` 场景：MediaBox 为 `(20,30,632,822)`，CropBox 为 `(61,77,573,769)`，PDF 用户坐标 `(150,650)` 放 `TARGET`，`(150,600)` 放干扰文字 `LOWER`。Poppler 的 `-bbox -cropbox` 给出渲染页面中的目标框，再调用 `doc.show`。

- 未旋转时，show 直接展示的文字层和打印的区域命令都取得 `TARGET`。
- 页面 `/Rotate` 为 90、180、270 时，修正后的区域命令均取得 `TARGET`，但 show 直接展示的文字层仍为 `(none)`；直接定义和从父节点继承 MediaBox 两种情况相同。
- 原因：`show` 把渲染页面中的框加上裁剪框原点后，直接交给 PDFium `get_text_bounded`；后者使用未旋转的 PDF 用户坐标。其他文字层核对函数是否受相同问题影响还需分别核实。

## 影响与下一步

旋转页上，调用方可能把错误的空结果当成没有文字层。当前可执行 show 打印的 pdftotext 命令，并对照页面图像。

后续先明确渲染坐标到 PDF 用户坐标的转换及调用范围，再修正；现有图表链接对旋转页不给矩形，不应无意改变该行为。这里不预先决定共用 helper 或新的检测规则。

## 修复（2026-11-09）

用户同意修复工具的通用错误：「那就修复吧」。单篇论文的内容核对仍由读者在实际阅读时做。

- 复用已安装 pypdfium2 的 `PdfPosConv`，使用记录的实际图像尺寸；页面自身的旋转及页面框继承由 PDFium 处理，额外旋转为 0。
- 同因影响共四处：show 的区域文字、图检查的区域文字回调、文字检查的字符中心、图检查的字体字符中心。区域取字共用 `checks.bounded_text`，字符位置使用原生正向转换；未增加检测规则。
- `checks.VERSION` 6 → 7，`figures.VERSION` 2 → 3，使旧包能识别检查版本变化；仅同步合成 fixture 的版本字段。旧包按现有提示在使用时重新处理／核对，本轮没有重跑库内 OCR。
- `objects` 对旋转页不提供图表矩形的现有行为保留。

## 验证

- 扩展已有区域回归：普通页面、非零纸张原点及不对称裁剪的四种旋转，加 MediaBox 继承，共 9 个场景。Poppler 独立取得目标框；show 内嵌文字与打印命令均取得 `TARGET`，两种字符中心均落入对应单词框。
- 补充离线探针核对了非整数原点、1.7 倍图像，以及两个页面框都继承的情况。原生接口在图像像素边界取整；本机 2 倍图像的往返误差最大 0.192 PDF 点，低于半个图像像素。
- paddleocr：objects 4、checks 47、figures 44、doc 60、parse 24 项测试完成，其中 doc 的 2 项需 OCR 引擎而跳过；paper-read 6/6 个测试文件通过。
- 根目录约定检查通过（6 项，2 项不适用的批量写入断管检查跳过）；独立审阅通过；`git diff --check` 通过。
