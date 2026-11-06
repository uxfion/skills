# paddleocr：检查漏掉单词级的误读

- 来源：2026-11-05 全流程试用，三个只看 skill 文档的读论文 agent 在整理（settle）结构化包时报告。用户没有提。
- 状态：open。

## 经过

- **SonoWorld**（arXiv 2610.19327，24 页）：模型给的文字里有几处单词级错误，`checks.py` 都没标出来：
  - 凭空多出两个 "the"；
  - 参考文献作者 "Sanskar" 读成 "Sanskrit"；
  - "action grounding" 读成 "action-grounding"；
  - 第 16 页 "Two" 读成 "1wo"；
  - 几处行内公式乱码。

  这几处覆盖率都正常，所以检查看不出来。agent 临时写了个逐页 diff，一遍就把它们全找了出来，同时带出约 60 处误报，比如小型大写字母、带连字符的复合词、表头顺序，很快就能分完。diff 的做法：包里的文字对 `pdftotext`，做 Unicode 规范化，去掉注释、公式和 HTML，接上行末连字符，转小写，只取两个字母以上的词，用 Python 的 `difflib` 比，只打印 1 到 3 个词的变化。
- **第 7 页的小节标题被换成了一句中文的"作为 AI 语言模型……"**：这是视觉语言模型的拒答。`foreign_script` 加 `extra_text` 抓到了，但这类拒答句式能认出来，值得单独一个代码，或者在 papers.md 里写一句。
- **MICCAI 那篇（UIV-US）**：settle.md §3 已经列出的几类错误也没被标出：表头单元格拆开（"Seg" / "& Cls"）、信封符号读成 "(2)"、保留了行末连字符、页末凭空多一个句号、`\bar` 写成 `\hat`。不过真正丢了单元格的那处，`table_mismatch` 抓到了。
- **FSCG**：`table_mismatch` 把文字层里粘连的下标（`DiTICCV’23`）当成不一致。改对以后这条还是开着，只能手动判 `ok`。papers.md 已经写了这类误报。

## 为什么不顺

检查是 settle 的起点。漏掉的错误，只有读的 agent 自己逐页对照才能发现，这次是两个 agent 各自想办法找出来的。查不出来的话，错字就会进到笔记的引文和数字里。

## 待看

- 把逐页单词 diff 做进 `checks.py`，作为一类低置信度的 finding；或者写进 settle.md §3，作为要做的一步。误报多，适合交给 agent 判断，不适合脚本直接定（原则 §1，*The boundary is the script's certainty*）。
- 拒答句式要不要单独一个代码。
