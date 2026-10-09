# paddleocr：一张主图被拆成很多小图

> 2026-10-07 记录 · 状态：fixed（2026-10-09）。用 plus-L 整图框加图注兜底，在解析后把拆开的图合回整张，旧解析就地升级。设计与实现记录见 [20261009-paddleocr-figure-groups-spec.md](../specs/20261009-paddleocr-figure-groups-spec.md)。直接从 PDF 取图的几种方法比较过，用户选了现方案，对比结果见末节，备查。
>
> 原是 [20261006-paddleocr-setup-fixed.md](20261006-paddleocr-setup-fixed.md) 第 9 节的一条，同日拆出来单独成 issue。

用户：「在实际用的时候，发现它会把一个主图分散得很小」。

原因出在版面检测：PP-DocLayoutV3 的 25 个类别里没有「整张图」这一级，多面板图的每个子图各出一个 `image`/`chart` 框，流水线按框裁图，所以 Markdown 里是一串小图，面板字母（a、b、c）则成了单独的 `figure_title` 块。单独跑版面模型确认过：TMI 第 7 页 Fig. 4 出了 9 个 chart 框，Fig. 6 出了 6 个，都没有包住整张图的框；把 `layout_merge_bboxes_mode` 改成 `large` 结果不变，因为它只处理互相包含的框。6 篇测试论文共 201 个图块，Nature 第 14 页的一张图被拆成 30 块，每块约占页面的 0.5%。

- 附带发现：TMI Fig. 5 的第一个面板，在流水线自己渲染的页面图上（pypdfium2，scale 2）版面模型没有检出；换成 pdftoppm 144 dpi 渲染，得分是 0.43（阈值 0.3）。这个面板在 Markdown 里直接丢了，也没有任何 warning。
- 用户追问（同日）：「你查一下，没有相关的issue吗？理论上一个大图，主图，框架图，都不应该被划分成小图」。查了 PaddleOCR 和 PaddleX 两个仓库的 issue：
  - 直接相关的只有 [PaddleOCR #18081](https://github.com/PaddlePaddle/PaddleOCR/issues/18081)（open，2026-07）：VL-1.5/1.6 把同一行并排的几张图拆成几个块，各占一行。回复的人（不是维护者）说，restructure 阶段对「同一水平行内的多图」没有做行内聚合，临时办法是拿到 JSON 后按 bbox 的 y 坐标重叠自行合并。目前没有官方修复。
  - [PaddleOCR #18215](https://github.com/PaddlePaddle/PaddleOCR/issues/18215)（open）列了 PP-DocLayoutV3 相对 V2 的一批漏检和阅读顺序问题，和上面那个漏掉的面板是同一类问题。
- 流水线有意不合并图块：`paddleocr_vl/pipeline.py` 调 `merge_blocks(..., non_merge_labels=image_labels + ["table"])`，而 chart 识别关闭时 `image_labels` 也包括 `chart`。`merge_layout_blocks` 只合并文字块。
- 这个问题不是 V3 才有的：在同样的三页上跑 PP-DocLayoutV2（VL 1.0 用的那一代），拆法几乎一样。TMI 第 7 页 V2 和 V3 都出了 18 个图块，Nature 第 14 页都是 30 个；V2 只是把 Fig. 5 的第一个面板和第二个合成了一个框（得分 0.34），所以没有漏掉它。
- 拆还是不拆，取决于图的构成。粗略统计 6 篇论文的约 73 张图：53 张是一张图，包括 LDM Fig. 3、SDEdit Fig. 2 这类单张的框架图；20 张被拆成 2 到 9 块。被拆的都是由几个分开的子图拼成的组图：一排或一格一格的面板、Nature 那种 a–f 多面板图，也包括 Nature Fig. 1 这种由 a、b、c 三个带边框的分块组成的框架图（拆成 3 块，每块本身完整）。
- 可选的修法：`parse.py` 在 Markdown 里把同一个图注上方相邻的图块合成一张图：取这些框的并集，横向扩到图注的宽度，纵向延到图注上沿，从页面图重新裁一张；JSON 保留原来的分块。横向扩到图注宽度，也能把 Fig. 5 漏掉的那个面板补回来。还没定。

## 2026-10-09 复核、调研与横向实测

用户：「你去确认一下这个 issue，然后查一下 PaddleOCR 上相关的 issue 或者在线文档，有没有解决办法或同样遇到类似问题的。另外因为我想知道，其他的方案（paddleocr系的其他方案）也是一样的会分割小图不能用吗？……理论上那种架构图、主图、展示图之类的不应该被拆分。然后也要看一下 MinerU 的效果」，并要求「找两三个典型的案例分别去测试一下，主图和展示图」。

测试用的仍是上面那 6 篇论文。各方法都按自己流水线的默认配置运行：paddleocr 3.7.0 / paddlex 3.7.2，MinerU 4.0.10（本机已装的 uv tool，模型取 HF 的 MinerU-4_models_torch 和 MinerU2.5-Pro-2605-1.2B），RTX 5090 D。

### 复核

当前 skill（VL-1.6，走 vLLM）重跑 6 篇，问题仍在：
- TMI 的 9 张图里有 4 张被拆开；
- Nature 有 13 组被拆开，Extended Data Fig. 1 拆成 30 块，图注被标成了正文；
- TMI Fig. 5 的第一个面板仍然漏检，也没有任何告警。

### 典型案例：每张图拆成几块

主图（框架、示意）和展示图（结果对比、多面板）各选 3 个。

| 案例 | VL-1.6（PP-DocLayoutV3） | VL 1.0（PP-DocLayoutV2） | PP-StructureV3（PP-DocLayout_plus-L） | MinerU basic / standard | MinerU advanced |
| --- | --- | --- | --- | --- | --- |
| 主图 LDM Fig. 3 | 1 | 1 | 1 | 1 | 1 |
| 主图 TMI Fig. 2（带 Step 1/2 小标题） | 1 | 2 | 2，在 Step 2 小标题处断开 | 2 | 2 |
| 主图 Nature Fig. 1（a/b/c 三个带边框的分块） | 3 | 3 | 1 | 3 | 1 |
| 展示图 TMI 第 7 页（Fig. 4/5/6 共 3 张） | 18，Fig. 5 漏一个面板 | 19 | 3，Fig. 5 完整 | 19 | 19 |
| 展示图 Nature Fig. 2（a/b/c，b 是 6 个柱状图） | 8 | 8 | 1 | 8 | 3（按 a/b/c） |
| 展示图 Nature Extended Data Fig. 1（6 组×5 张） | 30 | 30 | 1 | 30 | 5（按行） |

数字来自各方法实际输出的图块，每页都画框核对过。

- 只看版面模型、不套流水线配置时，结果会不一样：VL-1.6 流水线用阈值 0.3，并按类别合并框（image 用 union，chart 用 large），这样 TMI Fig. 2 是一整块；单独跑模型时，Step 2 那一行没有框。以下比较都按流水线自己的配置。
- MinerU basic 和 standard 的版面都来自 PP-DocLayoutV2，所以拆法与 VL 1.0 相同。standard 在原生 PDF 上只把公式交给 VLM 重识别。advanced 交给 VLM 划版面，带“多图块”容器；但它的分组是按面板字母或按行，TMI 第 7 页那种一排排的面板照样拆碎。
- PP-StructureV3 全文 6 篇：LDM 10 张图都完整；Nature 的图块从 87 降到 25，TMI 从 29 降到 14。仍拆开的有 TMI Fig. 3（6 块），以及 Nature 第 15、16 页的附图；没见到把两张不同的图并成一块。

### 其他质量（与拆图无关）

文字覆盖率：词三元组在 PDF 文字层里的召回 R 和精确度 P，用 `parse.py` 的分词。PDF 里图中的文字谁都不转写，所以 R 到不了 1，只适合横向比较。

| 原生 PDF 全文 | VL-1.6 | PP-StructureV3 | MinerU basic | MinerU standard | MinerU advanced |
| --- | --- | --- | --- | --- | --- |
| Nature | R .913 P .833 | R .821 P .778 | R .913 P .838 | R .914 P .840 | R .916 P .827 |
| TMI | R .801 P .926 | R .803 P .919 | R .859 P .933 | R .859 P .934 | R .928 P .913 |
| 其余 4 篇 | R .92–.97 | 比 VL-1.6 低 0.01–0.02 | 与 VL-1.6 持平 | 与 VL-1.6 持平 | 与 VL-1.6 持平 |

- MinerU 在原生 PDF 上直接取文字层（txt 模式），不做 OCR。
- 把 4 页渲染成 PNG（无文字层，测 OCR，覆盖首页、公式页、LDM 表格页、Nature 图文页），四种方法的 R 都在 0.75–0.93、P 在 0.87–0.99，互有高低，没有明显赢家。

速度（6 篇 108 页，含加载）：

| 方法 | 总耗时 | 其中加载 |
| --- | --- | --- |
| VL-1.6 + vLLM | 105 s | 冷启动 vLLM 服务和加载 42 s |
| PP-StructureV3 | 149 s | 约 18 s |
| MinerU basic | 46 s | 包含在内 |
| MinerU standard | 141 s | vLLM 引擎首次启动 84 s |
| MinerU advanced | 106 s | vLLM 引擎启动 22 s |

### 上游 issue 与文档

- 没有找到能把多面板图合成一张的参数，也没有相关的修复。`layout_merge_bboxes_mode` 的 large、small、union 只处理互相重叠或包含的框（文档：PaddleOCR-VL.en.md、layout_detection.en.md；可以写成按类别 id 的字典），并排的面板不会被合并。
- PaddleX v3.3.11 的 `merge_layout_blocks` 不处理图片：流水线 `merge_blocks(..., non_merge_labels=image_labels + ["table"])`。
- 25 类的 V2、V3，20 类的 plus-L，23 类的 PP-DocLayout-L，都没有“整张图”这一类。PP-DocBlockLayout 只有 `Region` 一类，只用来排阅读顺序（PaddleX #4365）；在测试页上，它的 Region 框住的是整页。
- [PaddleOCR #18081](https://github.com/PaddlePaddle/PaddleOCR/issues/18081)：仍 open。回复者 SISTMrL 是仓库协作者，原话：「目前对「同一水平行内的多图」没有做行内聚合。临时办法：拿到结构化 JSON 后，根据每个 image block 的 bbox y 坐标重叠情况自行做行内合并。」这是唯一接近官方的建议。
- [PaddleOCR #18215](https://github.com/PaddlePaddle/PaddleOCR/issues/18215)（V3 漏检）仍 open，没有维护者回复。
- MinerU 维护者在 #4008、#4163、#4335 里承认「子图切割为已知问题」，3.2 起用 VLM 缓解。#5031（open）是论文 Figure 3 被拆成 6 个 chart。
- 4.0.11 的更新说明里没有涉及版面或拆图的改动。
- 子代理只读代码时推断“换 PP-StructureV3 也没用，因为同样按框裁图”。实测推翻了这一点：确实按框裁，但 plus-L 一开始画的就是整图框。

### 修法候选（待定，先给用户看）

1. **借 plus-L 的整图框做分组**：在同一个 `paddleocr` 环境里多跑一个 PP-DocLayout_plus-L（PP-StructureV3 的配置，模型已在缓存），每页约 0.1–0.2 s。
   - 每个 plus-L 的 image/chart 框，如果罩住了 VL-1.6 的 2 个以上图块（连同面板字母），就在 Markdown 里合成一张图，从页面图按这个框重新裁出来；JSON 保留原分块，加 `merged_into`。
   - 这样也能把 Fig. 5 漏掉的面板补回来。
   - 局限：plus-L 的整图框靠 PP-StructureV3 配置里的 image 阈值 0.5 加 large 合并（内框被外框吃掉）。整图框得分不到 0.5 时，子图照样各自出来，例如 TMI Fig. 3 仍是 6 块；TMI Fig. 2 也在小标题处断开。所以这条是“多数图能完整”，不是根治；没合上的，再交给第 2 条兜底。
2. **几何合并**（#18081 的建议，也是上面原有的候选）：把同一个图注上方相邻的图块合并，横向扩到图注的宽度。
   - 不加模型。
   - 但图注在旁边、两张图并排、图注在上方的版式，都需要单独处理。
3. 不推荐的方向：
   - 整体换成 PP-StructureV3：图对了，但 Nature 的文字召回从 0.91 降到 0.82。
   - 换成 MinerU：basic 和 standard 一样拆碎；advanced 对展示图仍然拆碎。

## 2026-10-09 实现后：直接从 PDF 取图的方案对比与留出复验

用户在实现过程中提出两点：
- 「一方面你合并是一个方向，另一方面就直接从 PDF 里面提取出图像，例如pypdfium2等工具，这也不是一个方向吗？可以多测试一下，然后再比较方案，让我决定，这样更全面。要善于使用现成工具，自己去调研充分。」
- 「刚才有提到合图失败或者模型为空就会跳过什么的，你事后去调研一下」

### 实现中看图发现并已修的两处

- **Nature 的裁剪把图注吞了进去**（Fig. 1、2、6，Extended Data Fig. 2）。
  - 原因：通栏图注排成两栏，右半栏被标成 `figure_title`，被当成了图内小标题；向小标题扩边时，就把整段图注扩了进去。
  - 修法：图注同一行右边的块算作图注的续行，既是挡板，也不参与扩边；扩边后如果盖住挡板，这一块就不扩。
- **只用图注兜底时，TMI Fig. 4 被并进 Fig. 6**（模拟 plus-L 加载失败时发现）。
  - 原因：Fig. 4 是横跨整页的一排面板，图注只在左半边。右半边的面板越过它，找到了右栏 Fig. 6 的图注。
  - 修法：同一行的面板共用紧贴在这一行下方的图注。
  - 修后，只用图注兜底的结果逐页都落在有 plus-L 时的同一张图里，6 篇共 82 个图单元（有 plus-L 时 78）。

### 参与比较的方法

所有方法都在本机跑，没有上传任何 PDF。

| 方法 | 原理 | 许可 | 体积 | 速度 |
| --- | --- | --- | --- | --- |
| 现方案 | VL-1.6 的图块，加 plus-L 整图框和图注兜底分组 | Apache-2.0 | plus-L 125 MB | 分组每页约 0.1 s（解析另计） |
| PyMuPDF 图注锚定（B） | 以图注为锚，聚合 PDF 里的矢量绘图和位图；规则由子代理照着 6 篇调试篇写，约两小时 | AGPL-3.0 或 Artifex 商业许可 | 65 MB | 每页 0.03–0.06 s |
| pymupdf4llm 1.28.2 | 现成的取图功能 | AGPL-3.0 | 253 MB | 每页 0.2–0.4 s |
| docling 2.135.0 | heron 版面模型，CPU 推理 | MIT / Apache-2.0 | 2.3 GB | 每页约 0.55 s |
| pdffigures2（AI2） | 从 PDF 的文字和图形找图及图注 | Apache-2.0；需 JDK 17 | 构建 924 MB，运行 340 MB | 每页约 0.1 s（含 JVM 启动） |

`pdfimages` 只能导出 PDF 里嵌入的位图，用来判断“直接从 PDF 取图”行不行。
- 问题一：矢量图（多数曲线图、流程图）根本不在位图里。
- 问题二：一张图常由许多位图拼成，例如 TMI 第 7 页有 19 个，其中有透明蒙版，还有被切过的半张图。
- 结论：直接导出位图不能作为方案，必须按区域裁剪页面。

### 调试篇（6 篇，现方案的 78 个图单元已逐页核对）

| 方法 | 与核对结果一致 | 碎块 | 跨进另一张图 | 漏检 |
| --- | --- | --- | --- | --- |
| docling | 63 / 78 | 45 | 0 | 0 |
| pdffigures2 | 52 / 78 | 0 | 2 | 13（Nature 正文图漏掉，Extended Data 全部识别不出） |
| PyMuPDF B | 63 / 78 | 0 | 1 | 0 |

PyMuPDF B 是对着这 6 篇调出来的，但仍有 3 个框错了：
- TMI Fig. 5 的框跨进了 Fig. 6：一张位图的边界带着透明边；
- Nature Fig. 4 漏掉了第一行面板；
- TUFFC Fig. 9 的最后一行被截掉。

另外，它有两个框把页眉也框了进去。

现方案在调试篇上也有 3 处不完整，都出在 VL 的版面标签上，不在分组：
- Nature Extended Data Fig. 5：面板 b 的文字被标成了正文，没有进裁剪；
- TUFFC Fig. 9：被整个识别成表格；
- TMI Fig. 2：顶上的 “Step 1” 标题被截掉。

### 留出复验（8 篇，181 页，122 张带图注的图）

论文来自研究项目，没有参与调规则，覆盖的期刊和版式有：
- arXiv 单栏；
- Nature 正文和 Extended Data，含 Reporting Summary；
- ICLR、EMNLP；
- npj、iScience（Cell Press）、GigaScience、JAMIA。

全部 124 页，逐页把四种方法的框并排画出来看过。

PyMuPDF B 在带图注的图上，没看到一张不完整，所以拿它的框当参照，统计其他方法。下表中“非图区域”指框在图以外的东西，例如 logo、引用框、表单。

| 方法 | 完整 | 不完整 | 拆成两块 | 漏掉 | 非图区域 |
| --- | --- | --- | --- | --- | --- |
| 现方案 | 111 | 2 | 1 | 8 | 5 |
| docling | 102 | 2 | 2 | 16 | 41（多是 logo、ORCID 图标、“Check for updates”） |
| pdffigures2 | 105 | 3 | 0 | 14（Nature 那篇 15 张只找到 1 张） | 1 |
| pymupdf4llm | 50 | 10 | 26 | 36 | 28 |

PyMuPDF B 自己的问题：
- 没有图注的图形会被单独输出，8 篇共 40 个，例如提示词框、Takeaway 框、Reporting Summary 的表单、期刊 logo；
- 图注锚定本身决定了它只找带图注的图，图形摘要这类没有图注的图找不到。

现方案的 11 处问题，都来自 VL 的版面标签，没有一处是错合，也没有一处吞进图注或正文：
- 7 处是纯文字的“示例图”：提示词、模型输出示例（ICLR 论文 Figure 20–26、29 等）。VL 把它们标成了正文，没有生成裁剪，但文字已经转写在 Markdown 里。
- npj Fig. 3 是文字病例加图标：只裁到了图标那一行。
- JAMIA Fig. 2 是 12 张热图网格，被 VL 识别成表格，只剩一张。
- GigaScience Fig. 1 是四个面板的流程图，被拆成两块，第 4 个面板没有框进去。

### 「合图失败或模型为空」调研

| 情形 | 现在的行为 | 实测 |
| --- | --- | --- |
| plus-L 不在缓存，又连不上网 | 整次运行只用图注兜底，stderr 说明原因；`layout_model: null` | 空缓存且屏蔽网络：7 s 后报 “No available model hosting platforms detected”，退回图注兜底，正常结束 |
| plus-L 已在缓存，但断网 | 从缓存加载，正常分组 | 屏蔽网络：10 s 完成，`layout_model` 正常记录 |
| plus-L 在某一页推理出错 | 这一页只用图注兜底 | 未出现过 |
| 新解析时分组本身抛异常（裁图、改写） | 保留未分组的结果，不记 `parser.figures`；下次不加 `--force` 运行时自动补做 | 单元测试覆盖跳过路径 |
| 升级旧解析时抛异常 | 原样保留，摘要 `regroup` 写明原因；下次再试 | 同上 |
| `--photo` 的旧解析 | 不升级，摘要提示用 `--force` | — |

调研中发现两个缺口：
- `layout_model: null` 同时表示“加载失败”和“没有页需要它”，事后分不出来。
- 因加载失败只用图注兜底的解析，以后模型能用了也不会再升级：已记了 `parser.figures`，不会再触发。
  - 影响：图注兜底在调试篇上没有错合，但漏检的面板补不回来；Nature 的单元数是 14，而不是 12。

### 决定

用户看完对比，选了现方案：「由于我们想要更通用、智能的方法。所以用我们现在方案吧，其他的提取的方案可以在文档里提一嘴，之后要是我们的方案出现问题了可以找到参考。」

现方案不依赖 PDF 文字层，截图和扫描件同样适用；它在留出论文上的问题都来自 VL 的版面标签，已写进 spec 3.7 的局限。以后需要补救时，首选参考以图注为锚的 PDF 取图规则（改用 pypdfium2，避开 AGPL）。
