# paddleocr：检查漏掉单词级的误读

已解决（2026-11-09，用户选「A」）：新命令 `ocr.py diff <folder>` 逐块比对解析文字和框内的文字层，列出一到三个词的差异，交给整理的 agent 判断。它不算 finding，也不卡完成条件。settle.md §3 原有的接缝抽查（每页最后一块、每栏第一行）保留，`diff` 作为补充：接缝抽查管跨栏接错和栏首整行乱码，`diff` 管单词读错，两者互相看不见对方的那类错。
- **为什么现有检查抓不到**：`missing_text` 要连续 8 个三词组对不上才报，一个词读错最多影响 3 个三词组，所以是设计上的盲区。
- **去噪只用确定的规则**：复合词拆分（拼起来完全相同）、本块行内公式里的词和算子名（`\min`）、HTML 实体、文字层把帽子符号印成单独字母；不设模糊阈值。"一到三个词"的上限沿用 11-05 两个 agent 实际用过的做法。
- **实测**：先在 5 个包上调规则（Lambe、Wang 两篇没整理过，SonoWorld、UIV-US、FSCG 三篇已整理过），已知的 10 处真错全部列出，如 satisficing 读成 satisfying、diagnosticians 读成 diagnostics、表格方法名 STP-BCR 读成 STP-OCR。规则冻结后，换 3 个没看过的包（Bertalanic 2026、Chen 2025、Esteva 2021）检验：共 82 行，约三成是真错，如 instantiating 读成 differentiating、MMLU 读成 MMLI、AI 读成 Al；其余多为表格里合并单元格的顺序差异。拿不去噪的逐页比对做对照，没有漏掉真错。
- **拒答句式不单独设代码**：SonoWorld 那句"作为 AI 语言模型……"已经被 `foreign_script` 加 `extra_text` 抓到。
- **顺带改的**：生成 Markdown 时把行内公式写成紧贴的 `$x$`（版式 render=5），JSON 里的原值不动。PaddleOCR 原样输出 `$ x $`，进了 Zotero 笔记只是普通文字，读者原来每抄一个公式都要手工去空格。
- **顺带修的库**（2026-11-09，用户授权修 skill 时顺手修库）：Lambe 2016、Wang 2024、Huang 2026 三个包里核实过的 15 处读错，按 PDF 文字层和页面图改正、`ocr.py commit` 记录，再 `p2z.py package put` 放回 Zotero。另外发现分词把表格单元格里的字面 `\n` 连同后面的词当成 LaTeX 命令抹掉（Lambe 表格的 Graber、Ilgen），已在 9aaba82 修正。

- 来源：2026-11-05 全流程试用，三个只看 skill 文档的读论文 agent 在整理（settle）结构化包时报告。用户没有提。
- 状态：fixed（2026-11-09）。

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
