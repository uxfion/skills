# paddleocr：页面框和纸张框不一致的 PDF 上，`doc.py show` 给的 pdftotext 命令读错位置

- 来源：2026-11-04 做出处链接时，一个旁路 agent 提醒、用户转过来：「测试时顺带发现 paddleocr 的一个旧问题：在页面有偏移的 PDF 上，`doc.py` 给 agent 的 pdftotext 命令会读错位置。主 agent 没有把它记成 issue。」「可以让主 agent 给 paddleocr 记一张 issue，以后再修。」
- 状态：open。

## 核实过的事实（2026-11-04）

- PaddleOCR 按 PDF 的页面框（cropbox）渲染页面，包里的框和 `doc.py show` 打印的框都是从页面框的左上角量的；`show` 自己读出的文字层（pdfium，算上了页面框）是对的。
- `show` 打印给 agent 照着跑的 `pdftotext -layout -f N -l N -x X -y Y -W W -H H` 直接用这组坐标。poppler 24.02 的 `pdftotext` 截区域时 `-x -y` 从纸张框（mediabox）的左上角量，**加 `-cropbox` 也一样**（`-cropbox` 只改 `-bbox` 的输出）。实测：纸张框 (0,0,612,792)、页面框 (9,18,603,774) 的合成 PDF 上，按页面框坐标截不到字，按纸张框坐标才截到，两种都和 `-cropbox` 无关。所以旁路提醒里"加上 `-cropbox`"修不好这条命令。
- 只有页面框和纸张框不一致的 PDF 受影响。库里 889 份 PDF 有 4 份：Contreras Ortiz 2012（Ultrasound image enhancement）、Balocco 2014（Standardized evaluation methodology）、Li 2021（A Review of the Deep Learning Methods for…）各偏 8.5 pt，大约一行字；Jiang 2024 只差 0.3 pt，可以不管。旁路提醒举的 stein 2008 不受影响：它的两个框一样，都是 (9,9,594,792)。
- 模块文档里那句 "Boxes given and shown are in source units: PDF points (as pdftotext -x -y -W -H takes them)" 在这几份 PDF 上也不成立：agent 用 `pdftotext -bbox` 量出坐标再传给 `figure --box`，框会偏同样一截。
- 出处链接用的 `doc.py objects` 不受影响：它按页面框换算到 PDF 的坐标，stein 的框实测位置对。

## 后果

agent 整理这几份 PDF 的包时，照 `show` 给的命令截文字会偏一行左右，可能核对错行；拿 pdftotext 量的坐标去重切图会裁偏。

## 修的方向

`show` 打印命令时给 `-x -y` 加上页面框相对纸张框的偏移（左边差、上边差），模块文档那句随之改准；`figure --box` 收到的坐标同理说明是从哪个框量的。
