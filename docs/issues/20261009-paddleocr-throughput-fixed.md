# paddleocr — 批量解析的吞吐与质量问题

> 2026-10-09 已解决，设计与实测见 [paddleocr v2 spec](../specs/20261009-paddleocr-v2-spec.md) 和 [vllm-serve spec](../specs/20261009-vllm-serve-spec.md)。1：VL 识别改由 vLLM 服务承担，服务来自新的 vllm-serve skill（本机统一的 vLLM 后端）；本条现场的 9 份 225 页从 2,489 s 降到约 100 s，输出与原生等价。方向里的 VL 批大小分组、多文档流水、跳过尾部无文字层页没有做（理由见 v2 spec §3.4），页 / 分钟已进摘要行。2：`repetition` 加词三元组去重率判据。3：新告警 `foreign_script`；`extra_text` 和页面检查加行内公式的“粘连”渲染，公式误报消失。4：比对前剥掉页边行号。已解析的文档不必重跑：跳过时自动按新核对重算 warnings。生效要在推送后重装 paddleocr 和 vllm-serve 两个 skill。

2026-10-09 在一个研究项目里批量解析论文 PDF 时攒下的问题。条目格式同其他 issue：来源 · 日期、现场、痛点、为什么、方向、状态。仓库公开：不写学校、个人路径。

---

### 1. 批量解析太慢：平均 11 秒一页，GPU 没吃满

- 来源：用户 + 使用 · 2026-10-09
- 用户原话：「OCR的解析怎么那么慢？你看看是哪里出问题，或者卡住了吗？有问题的话，你就在…docs/issues 中提issue，我会在另外的项目中优化它，优化完之后再交给你用。」
- 现场：RTX 5090 D（32 GB），WSL2，`parse.py` 原生后端。两次调用共 9 份 PDF（5 篇 Nature 系正文、2 份补充材料、1 篇 ICLR 投稿、1 篇 Nat Commun），225 页，合计 2,489 秒：
  - 平均 11.1 秒 / 页，约 5.4 页 / 分钟；模型加载 14–22 秒。
  - 按文档：纯文字补充材料 3.5–5.4 秒 / 页；图表多的正文 9–20 秒 / 页（Nat Commun 一篇 20.0，ICLR 投稿 15.6）。
  - stderr 的页进度每 8 页一跳，同一批 8 页的完成时间相同；一批从 28 秒（纯文字）到 145 秒（图表页）不等。
  - 解析进行中看过一次 `nvidia-smi`：显存 17.7 GB，利用率 45%。只有一次快照，“GPU 没吃满”是推断。
  - 没有卡住：每份文档都正常结束，`error` 为空。
- 痛点：项目要解析约 150 篇（估计 3,000 页以上），按这个速度要 9–10 小时，精读全卡在解析后面。
- 为什么（前两条有日志支持，其余是推断）：
  1. VL 识别走 Paddle 原生推理。`references/install.md` 已写明大批量应换 vLLM / SGLang 服务（`paddleocr genai_server` + `doc_parser --vl_rec_backend vllm-server`），但 `parse.py` 还不支持这条路。
  2. 每批 8 页、按批完成，批内最慢的一页（大表格、公式）决定整批时间，简单页被拖着等。
  3. 文档严格串行：上一份 PDF 全部完成，下一份的版面检测才开始，版面检测与 VL 识别没有跨文档流水。
  4. 不需要的页也在跑：Nature 系论文末尾 2–3 页图片版 Reporting Summary（无文字层）照样走完整流程。
- **根因（2026-10-09 实测确认）**：原生后端把 VL 识别的批大小锁死为 1。PaddleX 3.7.2 `inference/models/doc_vlm/constants.py`：`PADDLEOCR_VL_LOCAL_BATCH_SIZE = 1`；`predictor.py` 构造时只要 batch_size 大于它就降回 1，日志写 “Currently, the … local model only supports batch size of 1”。这条 warning 在 `parse.py` 的 stderr 里看不到。结果是版面检测切出的每个块（段落、标题、表格、公式）都单独做 batch=1 的自回归解码，全部串行。走 genai 服务时，客户端批大小是 8192（`PADDLEOCR_VL_GENAI_CLIENT_BATCH_SIZE`），由服务端连续批处理。
  - 每页耗时与每页块数成正比：纯文字补充材料每页 3.8 块、3.5 秒；正文每页 13–24 块、9–15 秒；平均每块约 0.6–0.7 秒，公式和长表格块更慢。
  - 单进程实测（4 页、63 块，解析 44 秒，加载 17 秒）：GPU 利用率平均 26%，最高 47%，从未达到 80%；功耗平均 119 W、最高 158 W（这张卡满载约 575 W）；Python 进程长期占满约 1 个 CPU 核。瓶颈在主机端逐 token 的生成循环，不在 GPU 算力。
  - 并发两个进程：GPU 利用率升到平均 61%，但显存用到 27.2 GB（共 32.6 GB），吞吐只多约 15%，有 OOM 风险，不能作为缓解办法。
- 方向：
  - **首选**：VL 识别改走 vLLM / SGLang 服务（`paddleocr genai_server --model_name PaddleOCR-VL-1.6-0.9B --backend vllm`，`PaddleOCRVL(vl_rec_backend="vllm-server", vl_rec_server_url=…)`），批处理与 CUDA graph 都由服务端负责。需要单独的环境；Blackwell（RTX 50）上的 vLLM / FlashAttention 兼容性要先验证。
  - `parse.py` 支持外部 VL 服务（`--vl-server URL`），或自动起一个 vLLM 服务、跑完关掉；附一份启动与验证说明。
  - 暴露 VL 的 batch size，或按页面复杂度分组成批，减少被最慢页拖住。
  - 多文档流水：解析第 N 份时预取第 N+1 份的版面检测。
  - 可选跳过尾部的无文字层表格页（Reporting Summary），默认关闭，在摘要里报告跳过了哪些页。
  - 每份文档的摘要行加上实际页 / 分钟，便于发现退化。
- 状态：fixed（vllm-serve 服务后端）

### 2. 作者行陷入循环，`repetition` 没报

- 来源：使用 · 2026-10-09
- 现场：一篇 Nat Commun 正文（11 页）。第 1 页作者行解析成 8,825 个字符，同一串作者名反复出现，相当于把 23 位作者重复了很多遍。摘要行只报了 `missing_text`（几个作者名缺失），没有 `repetition`。按文字层手工重建后才正常。
- 痛点：循环输出没被标出来，读的人看到 `missing_text` 会以为只是少了几个名字。
- 为什么（推断）：`repetition` 可能只检查短片段在单块内的重复，作者行里循环的单位是一长串名字。
- 方向：按“块长度远超文字层对应区域”的比例判重复；或对比块内 n-gram 的重复率。
- 状态：fixed（`repetition` 加词三元组去重率判据）

### 3. 编造的文字只在少数情况下被标出

- 来源：使用 · 2026-10-09
- 现场：一篇 ICLR 投稿第 6 页，一个含行内公式的段落开头被解析成 “Let $u_{j,1:N_j}$年第 $j$个signal messages…”：混进了原文没有的汉字，还丢了半句。这次报了 `extra_text`，但 `detail` 只给出英文词，看不出有汉字；另有一处（第 3 页）`extra_text` 实际是公式符号被拆开造成的误报。
- 痛点：真编造和公式误报混在同一个代码里，要逐条去看。
- 方向：单独检测“文字层里没有的字符集”（英文论文里出现 CJK 字符），作为独立警告；公式密集段的 `extra_text` / `missing_text` 降级或单列。
- 状态：fixed（`foreign_script`；`extra_text` 两种公式渲染都缺才报）

### 4. 带行号的稿件触发大量误报

- 来源：使用 · 2026-10-09
- 现场：ICLR 投稿（左侧行号 000–999+）与一份带行号的补充材料。补充材料第 3–11 页全部 `low_coverage`（73–78%）；ICLR 稿第 23–24 页 `table_mismatch` 的缺失词大多是行号（1189、1190…）。skill 文档说行号属于误报，但它们占了大部分警告。
- 痛点：真正的问题被淹没。
- 方向：比对前从文字层剔除行号列（按页左右边缘、单调递增的纯数字识别）。
- 状态：fixed（比对前剥掉页边行号）
