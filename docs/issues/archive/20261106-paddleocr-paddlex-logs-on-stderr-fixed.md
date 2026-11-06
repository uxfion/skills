# paddleocr：解析成功时，PaddleX 的例行日志落在标准错误上

> **已解决（2026-11-06）**：`parse.py` 在 `from paddleocr import PaddleOCRVL` 之后、建管线之前调 PaddleX 自己的 `paddlex.utils.logging.setup_logging("WARNING")`（它在 import 时把级别设成 INFO，所以要在那之后；级别对整个进程有效，后加载的第二个版面模型也安静了）；设了 PaddleX 自己的 `PADDLE_PDX_DEBUG` 时不动。警告和错误照旧出来。实测：退出 0 时标准错误只剩 `[paddleocr]` 开头的行，解析结果和改前一样。更正下面一处事实：那四行是两个模型的 `Creating model`，加上版面模型和第二个版面模型（PP-DocLayout_plus-L）各一行 `Model files already exist`。

- 来源：主 agent，2026-11-06，paddleocr 改 Unix 约定后的 GPU 实测（spec `20261106-paddleocr-unix-conventions-spec.md` 第 11 节）。用户没有提。
- 状态：open。

## 经过

- **跑的什么。** `ocr.py parse <PDF> -o <dir>/`，模型要加载的那几次（实测第 2、3、5 项）。
- **看到什么。** 退出 0，标准错误里除了 `[paddleocr]`、`[vllm-serve]` 的进度，还有 PaddleX 的四行，带 ANSI 颜色、没有前缀：版面模型和 VL 模型各一对 `Creating model: (…)`、`Model files already exist. Using cached files. To redownload, please delete the directory manually: …`。改造前的 `parse.py` 也一样。
- **为什么不顺。** 原则 §3：标准错误只留读的人需要、标准输出装不下的东西（几分钟的进度、影响结果的警告），做完时没有例行日志。这四行两样都不是；agent 照规矩"标准错误留着看"，每次都得认一遍哪些是噪音。

## 建议

在 `parse.py` 里，加载模型前把 PaddleX 的日志级别降到只出警告（它自己的 logger，或它认的环境变量，查 PaddleX 源码确认），进度和警告照旧。改完实测：一次真解析，退出 0 时标准错误只剩 `[paddleocr]`、`[vllm-serve]` 开头的行。
