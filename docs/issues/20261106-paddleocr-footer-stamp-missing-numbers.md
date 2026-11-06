# paddleocr：页脚下载戳在渲染时报 `missing_numbers`，重查时又自己消失

- 来源：2026-11-06 读论文（M2Trans，`niM2TransMultiModalRegularized2025`，IEEE 版），reader 报告。用户没有提。
- 状态：open。

## 经过

- **看到什么。** 包里 12 条 `missing_numbers`，每页一条，缺的都是 "21,202"：IEEE 的下载戳 "September 21,2026"。reader 没给结论，它们在 `ocr.py cut` 重跑检查时自己消失了。
- **为什么不顺。** 同一个包、同一份源文件，渲染时的检查和 `commit`/`cut` 时的重查，对页脚（running heads、页码、下载戳）的处理不一样，发现时有时无：agent 不知道该不该给结论，下一次 `render` 可能又冒出来。

## 待看

找出两条路径对页脚块的差别（渲染时用的文字层范围，和重查时用的），让它们一致；下载戳这类页脚文字本来就只在记录里，不该算正文缺的数字。
