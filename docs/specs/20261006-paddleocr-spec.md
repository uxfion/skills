# paddleocr — 设计 spec（2026-10-06）

> 来源：`docs/issues/paddleocr.md`（本机安装、WSL2 卡死与 EAGER 修复、CLI 输出）。本 spec 写的是 skill 的设计；安装和排障的事实以 issue 为准，进入 skill 的部分放在 `references/install.md`。

## 1. 目标

用户原话：「我们主要用途是文献图片或者 pdf 的结构化，提取出所有的信息，让大语言模型能更好地阅读文献全文，而不是只能通过图片的方式读全文像 pdf skill 一样。」

任何 harness 里的 agent，拿到一篇论文的 PDF 或页面图片（截图、扫描件），都能得到：

- 一份**全文 Markdown**：阅读顺序正确（双栏也对），标题有层级，公式是 LaTeX（带编号），表格是 HTML（跨页表格合并），图片是裁好的文件加上图注，脚注保留，页码标记可以用来引用；
- 一份**块级 JSON**：每块带页码、类型、内容和坐标，供定位与核对使用；
- 一个**完整性核对**：有文字层的 PDF，用文字层核对解析结果有没有漏字。「提取出所有的信息」要能检查，不能靠感觉。

名称：`paddleocr`（用户 2026-10-06 选定；备选 `paper-to-markdown`、`paper-parse` 未采用）。同机的 MinerU 这次不纳入（用户选定「先不纳入」），以后可以作为第二引擎加进来。

## 2. 关键事实（2026-10-06 实测 / 读源码）

| 事实 | 依据 |
| --- | --- |
| CLI `paddleocr doc_parser` 处理 PDF 时**每页一组文件**（`<名>_<页>.md/_res.json/.docx/_layout_det_res.png`），不做跨页合并 | 源码 `perform_simple_inference`；实测 11 页 TMI 论文输出 44 个文件，外加 `imgs/` |
| 跨页表格合并、标题重新分级、整篇拼接，只有 Python API 的 `restructure_pages(merge_tables, relevel_titles, concatenate_pages)` 提供 | `paddleocr/_pipelines/paddleocr_vl.py`、`paddlex/.../paddleocr_vl/pipeline.py` |
| Markdown 默认丢掉 `number, footnote, header, header_image, footer, footer_image, aside_text`；JSON 保留全部块 | `PaddleOCR-VL-1.6.yaml` 的 `markdown_ignore_labels` |
| `show_formula_number=False`（默认）时，公式编号不进 Markdown；设为 True 时合并成 `\tag*{(n)}` | `MarkdownConverter.convert` |
| `pretty=True`（默认）用居中的 HTML 包裹文本、图片和表格；`pretty=False` 输出 `![](imgs/…)` 和去掉外壳的 `<table>` | `_build_handle_funcs_dict` |
| 图片文件名是 `imgs/img_in_<label>_box_<x1>_<y1>_<x2>_<y2>.jpg`，**不含页码**，多页时可能重名 | `construct_img_path` |
| PDF 按 zoom 2 渲染（letter 页 → 1224×1584） | `PDFReader`、实测 JSON 里的 width/height |
| `merge_layout_blocks` 把跨栏续写的段落并进前一块，后一块的 `block_content` 留空——空文本块是合并后留下的占位，**不是漏字** | 实测：第 3 页右栏顶部空块的文字层内容，出现在左栏末块结尾 |
| 图、图表块不做 OCR（`use_ocr_for_image_block=False`），内容为空 | 实测 |
| 性能：11 页用时 3:10（含加载模型），峰值 RSS 11 GB，显存约 12 GB；前 8 页一批完成 | `/usr/bin/time -v` |
| `uv run` 一个无依赖的 PEP 723 脚本，再 `os.execve` 到 `$(uv tool dir)/paddleocr/bin/python`，可行，额外开销约 1.5 s | 实测 |
| 出版社 PDF 的页脚带「Authorized licensed use limited to: <机构>」；它属于 `footer`，不进 Markdown | 实测 |
| Zotero 本地 API `GET /api/users/0/items/<附件 key>/file` 返回 302，`Location` 是 `file:///…` | 实测 |

## 3. 文件

```
paddleocr/
├── SKILL.md                 步骤与判断（英文）
├── scripts/parse.py         唯一的脚本：解析 + 写出 + 核对
├── references/install.md    安装 PaddleOCR-VL（uv tool、GPU 源、--find-links 原因）、验证、已知卡死
├── references/zotero.md     从 Zotero 条目找到 PDF 路径（借 paper-to-zotero 的 read_library.py 和本地 API）
└── tests/test_parse.py      纯函数的单元测试（不需要 GPU）
```

只有一个脚本：解析、写出和核对共用同一个进程里的结果和已打开的 PDF，拆开反而要多传一次中间文件。核对逻辑写成纯函数，可以单独测试。

## 4. `parse.py`

```
uv run scripts/parse.py INPUT [INPUT ...] -o OUTDIR [--pages 1-3,8] [--force]
                        [--keep-all] [--charts] [--figure-text] [--photo]
```

- **运行环境**：PEP 723、无依赖。`import paddleocr` 失败时，先设 `CUDA_MODULE_LOADING=EAGER`（`setdefault`，用户可覆盖），再 `execve` 到 paddleocr 工具环境的解释器；找解释器的顺序是 `PADDLEOCR_PYTHON`、`$(uv tool dir)/paddleocr/bin/python`、`paddleocr` 入口的 shebang。都找不到就输出 `paddleocr_missing`，指向 `references/install.md`。
- **INPUT**：每个 INPUT 是一份文档——PDF、单张图片，或一个装页面图片的目录（按自然序排成页）。多个 INPUT 在同一进程里处理，模型只加载一次。
- **`--pages`**：只解析 PDF 的部分页（用 pypdfium2 切出临时 PDF），输出里的页码仍是原文页码。
- **跳过**：`OUTDIR/<stem>/<stem>.json` 已存在，且源文件 sha256 和选项都相同，就跳过（`skipped: up_to_date`）；`--force` 强制重做。
- **流程**：`PaddleOCRVL(markdown_ignore_labels=…)` → `predict_iter` 逐页收集（每完成一页向 stderr 打一行进度）→ `restructure_pages(merge_tables=True, relevel_titles=True, concatenate_pages=False)` → 每页 `save_to_markdown(tmp, pretty=False, show_formula_number=True)` → 拼接、重命名图片 → 核对 → 写出。
- **选项**：`--keep-all` 让 Markdown 也保留页眉、页脚和页码；`--charts` 打开图表转表格（`use_chart_recognition`）；`--figure-text` 对图片块做 OCR；`--photo` 打开方向校正和去畸变（拍照、扫描件用）。默认值都按论文场景定：Markdown 去掉每页重复的噪声（页眉、页脚、页码），**保留脚注和侧栏**（arXiv 编号）。

### 4.1 输出

```
OUTDIR/<stem>/
├── <stem>.md      全文
├── <stem>.json    块级结构 + 核对结果
└── imgs/p<NN>_img_in_<label>_box_….jpg
```

Markdown：

```
<!-- source: <文件名> | pages 1-11 of 11 | PaddleOCR-VL-1.6 | 2026-10-06 -->

<!-- page 1 -->
# Title
…
<!-- page 2 -->
…
```

JSON：

```json
{
  "source": {"path": "…", "sha256": "…", "page_count": 11, "pages": [1, 2, 3]},
  "parser": {"pipeline": "PaddleOCR-VL-1.6", "paddleocr": "3.7.0", "format": 1, "options": {}},
  "pages": [{"page": 1, "coverage": 0.98, "width": 1224, "height": 1584}],
  "blocks": [{"id": 0, "page": 1, "label": "doc_title", "text": "…", "bbox": [0, 0, 0, 0], "level": 1,
              "image": "imgs/p01_….jpg", "merged_into": 8}],
  "warnings": [{"code": "missing_text", "page": 7, "detail": "缺失片段"}]
}
```

stdout 每份文档输出一行 JSON 摘要：路径、页数、各类块的数量、最低页覆盖率、warnings、用时（首份文档另带模型加载用时）；出错时输出 `error`。

### 4.2 核对（完整性）

文字层逐字符取出（pdfium，字符中心换算到页面图像像素），按词决定保留或排除（一个词的字符中心落在哪个框里）。

- **页面检查**排除公式框里的词；图框外扩 20 px（坐标轴刻度、图例常常落在图框外）和表格框里的词也排除，**但落在解析出的文本块框里的词一律保留**（图注、子图标题仍要检查）。表格交给下面单独的表格检查：文字层里表格的顺序（单元格、多行表头）不是阅读顺序。
  - `missing_text`：切词（NFKC；pdfium 把行尾连字符报成 U+FFFE，先接回；字母后面的行尾连字符也接回，数字后面的不接，「2023-\n2023」是区间；含希腊字母的词丢掉——文字层里的希腊字母是公式，解析结果写成 LaTeX），比较词三元组。解析侧取本页和前后一页的全部块，并同时取「保留行内公式字母」和「去掉行内公式」两条词流。连续 ≥8 个三元组缺失，记一条，附片段。只比词集合抓不到漏掉的句子。
  - `missing_numbers`：只取 ≥5 个词的文字层行里、两位以上或带小数点的数（短行是图例、刻度、公式编号），按多重集合比较；末位是上标的情况（「512²」在文字层里读成「5122」）不算缺失。
  - `low_coverage`：三元组命中率 <0.8 且三元组 ≥40 个。
- **表格检查** `table_mismatch`：表格框内的文字层词（多重集合）和该表（或它合并进去的表）的内容比较，缺失 ≥2 个且比例 >3% 时记一条，附缺失词、块 id 和 PDF 坐标区域（可以直接交给 `pdftotext -layout -x -y -W -H`）。框里没有文字层（表格是图片）的记 `unchecked_table`。
- `repetition`：表格以外的块里，10–200 字的片段连续重复 ≥5 次。
- `empty_page`：一页没有任何文本块（被合并走的占位块算有文本），并且也没有图。
- `no_text_layer`：扫描件、图片。

### 4.3 实现中补充的决定

- Markdown 里每页的 `footnote` 块挪到该页末尾：PaddleOCR 按版面顺序把第 1 页的脚注（收稿日期、作者单位）排在摘要中间，打断阅读。JSON 的块顺序与 Markdown 一致。
- 三个以上连续空行压成一个（`simplify_table` 会留下多余换行）。
- JSON 的 `parser.format` 记输出格式版本；跳过判断同时比对 sha256、选项和 format，脚本改了输出格式就递增 format，旧结果会重做。
- 合并占位块在 JSON 里带 `merged_into`（目标块的全局 id）：同页跨栏合并来自 PaddleOCR 的 `group_id`，跨页表格合并来自 `global_group_id`。

## 5. SKILL.md 的步骤

0. **Input**：PDF 或图片的路径。只有 Zotero 条目或 citation key 时，用 `paper-to-zotero` 的 `read_library.py children` 拿到附件 key，再从本地 API 的 `/file` 取路径。这是 skill 之间的组合，不写脚本。
1. **Parse**：一条命令；长文档放到后台跑；首次运行会下载约 2 GB 模型。Done = 每份文档都有摘要行，且没有 `error`。
2. **Check**：逐条处理 warnings。`low_coverage` → 看该页图像（`pdftoppm` 或 `pdf` skill）和 Markdown 里的对应段，确认漏了什么，用文字层补进 Markdown，并标注来源；`no_text_layer` → 抽查一到两页。Done = 每条 warning 都有着落（误报 / 已补 / 交代给用户）。
3. **Read**：读 `<stem>.md`；需要图的内容时看 `imgs/` 里的裁图；按页引用时用 `<!-- page N -->`；要坐标或类型时查 JSON。
4. **Hand over**：告诉用户输出路径、覆盖率，以及哪些内容是补的、哪些是看图读的。

已知问题以带日期的提示写入（WSL2 + Blackwell 卡死 → 脚本已设 EAGER；判断卡死的症状；空文本块是合并占位）；个人环境信息（机器、路径、学校）不写。

## 6. 验证与迭代

测试集取自用户的 Zotero 库（只读）：

| key | 类型 | 页数 | 用来测 |
| --- | --- | --- | --- |
| ZYP68IN4 | IEEE TMI 2025 | 11 | 双栏、跨栏合并、图表多 |
| XDY5YZWQ | MICCAI 2025（LNCS） | 11 | 单栏、Springer 版式 |
| QSK9XI7V | IEEE TUFFC 2020 | 15 | 公式密集 |
| HZQECSA8 | CVPR 2022（LDM） | 12 | 大表格、图多 |
| P42UUUJK | Nature Medicine 2025 | 26 | 期刊版式、Methods、长文 |
| KUFFN4BS | ICLR 2022（SDEdit） | 33 | 长附录、`--pages` |

外加图片输入：一张从 PDF 渲染出的页面 PNG，以及一个多张页面图片组成的目录。

- **v1**：按本 spec 实现，跑全部测试集，校准覆盖率阈值，人工抽查表格、公式和图注。
- **v2**：修复 v1 发现的问题，然后做 fresh-agent 演练：子代理只拿到 skill，完成「读这篇论文并回答具体问题」（表格里的数值、某个公式、某张图的结论），评估它是否走对步骤、答对问题。显存约 12 GB/进程，最多同时跑 2 个。
- **v3**：按演练反馈改写措辞，用 writing-for-agents 做一轮剪枝，advisor 终审。

## 7. 不做

- vLLM / SGLang 服务化：单篇论文用 native 就够了；批量需求出现再说（install.md 里留一行指针）。
- DOCX 输出、翻译、摘要：都是下游任务。
- 改装 paddleocr 工具环境（比如 issue §9 提到的 `.pth`）：脚本内设置 EAGER 已经覆盖 skill 的调用方。

## 8. 迭代记录

**v1（2026-10-06）**：按 §4 实现，测试集一次批量跑完——6 篇论文和 2 个图片输入，共 110 页，用时 20.5 分钟（模型已缓存时加载 7 s，每页 8–17 s），峰值 RSS 12 GB，全部成功。

核对器在这一轮里改了四次，每次都用测试集的结果对照文字层逐条判断真假：

| 发现 | 真 / 误报 | 处理 |
| --- | --- | --- |
| MICCAI 表 3 漏了 ASD 整列和 ResNet18/50 列；初版（只看连续缺失）**没报** | 真 | 加 `table_mismatch`、`missing_numbers` |
| LDM 表 3 漏了采样设置一列；另一张表丢了 hours/epoch 列，@512 的数值被标在 hours 表头下 | 真（张冠李戴，危害最大） | 同上 |
| LDM、Nature 各有一张表丢了表头行或子表标题（「Train:mixed \| test:real」） | 真 | 同上 |
| Nature 作者单位上标（15、9）被读成 ORCID 的 `^{ID}` | 真 | `missing_text` 能报 |
| Nature 第 15/16 页同一句重复 133 次（原文 4 次） | 真 | `repetition` 能报 |
| TUFFC 行内公式（νS = 2γS）报成 `missing_text` | 误报 | 丢掉含希腊字母的词 |
| 「2023-\n2023」被接成「20232023」；「[−15,5]」被切成「15,5」 | 误报 | 连字符只在字母后接；千分位只认三位一组 |
| 图例「DAS 0.00 dB」的一部分落在图框外 | 误报 | 数字只取长行 |
| LDM 「512²」读成「5122」；多行表头的文字层顺序 | 误报 | 上标容错；页面检查排除表格框 |
| Nature 复杂多面板图的图例、坐标轴 | 误报（仍有 2 条） | 图框外扩 20 px、按词判断；剩余的在 SKILL.md 里写明如何认出误报 |

结果：20 张有文字层的表格里 5 张丢了内容，全部报出；另有 6 张表在 PDF 里是图片，记 `unchecked_table`。图片输入（150 dpi 截图）的单位行丢了开头几个字母，同页 PDF 解析是对的——没有文字层时只能靠看图抽查。


**v2（2026-10-06）**：两个全新子代理只拿 SKILL.md 演练——A：从 Zotero 找 TUFFC 论文，回答 gCNR 定义（带编号）、表 I、结论；B：两页截图转结构化文本，回答作者单位、贡献、第 2 页的公式。演练和复核中发现：

| 发现 | 处理 |
| --- | --- |
| TUFFC 的 86 个公式编号里有 4 个没紧跟在公式后面（中间夹了一段文字，或一个公式带两个编号），PaddleOCR 只在编号紧跟公式时合并成 `\tag`，其余的从 Markdown 里**直接消失**；同一处引导句还被排到了公式后面 | `attach_formula_numbers`：按坐标把编号挂回同一行的公式；一个公式的多个编号在 Markdown 里合并成 `\tag*{(22), (23)}`，JSON 保留原块；位于公式正上方、同一栏的引导句挪回公式前 |
| 截图输入第 2 页末尾，句子在页尾被连字符截断，模型**编造了后半句**（「different different types of data sources…」）；所有检查都只查漏字，不查多字 | 加 `extra_text`：解析结果里有、文字层（本页及前后一页）里没有的连续词段。只查框内有文字层的块（框内没有文字层的是从图片里读出的字），不比数字（上标、脚注号两边写法不同），跳过页眉页脚侧栏。测试集 PDF 上零误报，注入的编造续写能报出。截图没有文字层，查不了，SKILL.md 改为提示先看每页最后一块 |
| B：第 2 步的工具只适用于 PDF；截图该怎么核对、修正的标记写什么、覆盖率为空时报什么、公式块叫什么标签、怎么知道模型是否已下载、进度行里的秒数是什么意思，都没写 | SKILL.md 补上；进度行改成「page N done (k/n, t s since this document started)」 |
| A：Fig. 9（方法 × 图像 × C/CNR/gCNR 的图格）被识别成表格，所有数值左移一列，gCNR 列整列为空；词都在，`table_mismatch` 不报 | 加 `table_empty_column`：有表头的列在每个整行里都是空的。不依赖文字层，扫描件也能查 |
| A：VLM 完全漏掉的公式编号没有任何信号 | 加 `formula_number_gap`：相邻页内编号序列出现断号 |
| A：零 warning 时 SKILL.md 没有任何核对要求，而答案恰好依赖式 (19) 和表 I | 第 3 步：「没有 warning 不等于已核实」——答案依赖的每个数字、公式（含编号）和表格单元格，都要在文字层或页面图像里确认并注明页码 |
| A：从作者/题名找到 Zotero 条目、在 `children` 里挑 PDF 附件、`file://` URL 的百分号解码和 `file:///C:/` 前缀，都要自己摸索 | 第 1 步的 Zotero 一条写全，解码一行命令实测可用 |
| A：摘要里的 `coverage` 其实是最低页覆盖率；进度行成批到达；补丁会被 `--force` 覆盖、JSON 不改，这些都没说 | 字段改名 `min_coverage`；第 1、2 步写明；输出格式版本 `FORMAT` 升到 2 |

两个演练的答案都正确：A 的式 (18)/(19)、表 I（190 个数，逐一对过文字层）、结论要点；B 的作者与单位对应、贡献、第 2 页无公式。两者都靠自己发现并修好了解析错误——v2 的改动就是让这些不再依赖 agent 的额外勤奋。

**v3（2026-10-06）**：第三个全新子代理 C 读 LDM（CVPR 版），问 Table 3 里 LDM-4-G 的各项和采样设置、Table 6 里 LDM-4 (KL, w/ attn) 一行每个数对应哪一列。解析报了 3 条 `table_mismatch`（正是问到的两张表，外加 Table 2 的标题行），C 按 SKILL.md 用 `pdftotext -layout` 套 `region` 重建了三张表，并和 300 dpi 截图逐格核对，答案全对。它的反馈：`pdftoppm` 的裁剪坐标是像素，要按 ×r/72 换算；100 dpi 看不清表格；修正标记放哪、重建表格的 HTML 怎么写没说；`read_library.py` 在哪没说；stderr 被 Paddle 日志淹没。处理：SKILL.md 第 2 步分「PDF / 图片」两种来源，写明 300 dpi 和换算、标记位置和表格写法；Zotero 一支挪到 `references/zotero.md`（只有部分任务会走）；脚本默认 `PYTHONWARNINGS=ignore`，进度行带 `[paddleocr]` 前缀；第 3 步的完成标准改为「答案依赖的每个数字、公式和表格单元格都在文字层或页面图像里确认过，并注明页码」。

