# paddleocr v2 — VL 服务后端与核对改进（2026-10-09）

> 来源：[20261009-paddleocr-throughput.md](../issues/20261009-paddleocr-throughput.md) 的 4 条。v1 的设计见 [20261006-paddleocr-spec.md](20261006-paddleocr-spec.md)；本 spec 只写改动，没提到的部分（输出布局、Markdown/JSON 格式、跳过规则、其余核对）照旧。

## 1. 目标

- **吞吐**：批量解析从平均 11 秒 / 页降到 1–2 秒 / 页，约 150 篇（3,000 页以上）从 9–10 小时降到 1 小时以内；不改 agent 的用法（仍是一条命令，多篇一次传入）。
- **核对**：issue 2–4 的漏报和误报——作者行循环、编造的汉字、行内公式和行号引起的误报——在 issue 现场的 9 份文档上消失或单独标出，测试集上不新增误报。

## 2. 关键事实（2026-10-09 实测 / 读源码）

| 事实 | 依据 |
| --- | --- |
| 原生后端的 VL 批大小锁死为 1：`PADDLEOCR_VL_LOCAL_BATCH_SIZE = 1`；走 genai 服务时客户端批大小 8192、并发 200（`genai_config.max_concurrency`） | PaddleX 3.7.2 `doc_vlm/constants.py`、`common/genai.py` |
| 流水线 `use_queues: True`：版面检测按 8 页一批，与 VL 识别重叠；服务后端下一批页面的全部块并发发给服务 | `PaddleOCR-VL-1.6.yaml`、`paddleocr_vl/pipeline.py` |
| `paddleocr genai_server` 本质是带固定参数的 `vllm serve`：`--served-model-name PaddleOCR-VL-1.6-0.9B --trust-remote-code --chat-template <paddlex 包内 jinja> --gpu-memory-utilization 0.5 --max-model-len 16384 --max-num-batched-tokens 131072 --api-server-count 4`；vLLM ≥ 0.11.1 原生支持该架构 | `paddlex/inference/genai/backends/vllm.py`、`configs/paddleocr_vl_09b.py`、`models/__init__.py` |
| 模型目录 `~/.paddlex/official_models/PaddleOCR-VL-1.6` 是 HF 格式（safetensors + config），vLLM 可直接加载；`official_models["PaddleOCR-VL-1.6-0.9B"]` 返回该路径（缺失时下载，提示走 stderr）。目录里的 `chat_template.jinja` 与 PaddleX 包内的逐字相同（`import paddlex.inference.genai` 在没有 genai 插件时会报错，所以用目录里这份） | 实测 |
| 服务后端的客户端不传模型名时按流水线配置请求 `PaddleOCR-VL-1.6-0.9B`（vLLM 配方也提醒这一点；`vllm serve PaddlePaddle/PaddleOCR-VL-1.6` 的模型名是 HF id，会 404），所以 parse.py 总是显式传 `vl_rec_api_model_name`，`--vl-server` 时从 `/v1/models` 读；对 vLLM 服务用 `temperature 0`（贪心），并传图像像素上下限，SGLang 等其他服务的请求参数不同，所以 `--vl-server` 只承诺 vLLM | `common/genai.py`、`doc_vlm/predictor.py` |
| 本机 vLLM 0.28.0（torch 2.13 + cu130，借 mineru 工具环境）在 RTX 5090 D / WSL2 上要两个环境变量才能起：`VLLM_WSL2_ENABLE_PIN_MEMORY=1`（否则 V2 runner 报 `UVA is not available`）、`VLLM_USE_FLASHINFER_SAMPLER=0`（否则 FlashInfer 采样 JIT 报 `requires GPUs with sm75 or higher`）。FlashAttention 2 正常 | 实测，两次失败后第三次成功 |
| 启动到就绪约 50 秒（torch.compile 缓存已热；首次多约 10 秒），显存约 14 GB（0.5 × 32 GB 的上限内） | 实测 |
| **速度**：LDM 12 页 206 s → 16.9 s（12×）；SDEdit 33 页 266 s → 13.3 s（20×）；两者版面加载约 6 s。服务后端期间 GPU 利用率平均 25%，瓶颈已不在 VL | 同一份 parse.py，只换后端 |
| **质量**：两种后端的块数、标签完全一致；块文字逐字相同 94%（LDM 235/249）和 98%（SDEdit 445/456），其余是解码细节（`\mathrm`/`\text`、一个单位拆成单独一列）。LDM 丢列的表两种后端都错、都被 `table_mismatch` 报出；`min_coverage` 相同 | 逐块 diff |
| issue 现场 9 份文档的 JSON 和源 PDF 都在，离线重跑 `check_document` 能逐条复现原 warnings | 复核脚本 |
| 作者行循环块：8,857 字符、765 个词只有 36 个不同，词三元组去重率 6%；全部语料（约 50 篇、4,457 个 ≥20 三元组的非表格块）中其次最低是 56%（图注） | 实测 |
| shao（ICLR 投稿）16 条 `missing_text` 里 12 条、`extra_text` 2 条中的 1 条，来自行内公式：文字层把下标粘到字母上（`Tp (ak )`、`DKL (qn ‖pn )`），解析结果是 LaTeX，两边切出的词对不上 | 逐条对照 |
| 行号：页边一列纯数字，x 基本固定（右对齐，2 位与 3 位数中心差 5 px），自上而下逐行 +1，每页 50 个以上（补充材料 88、89…；ICLR 稿 1188、1189…）。补充材料 9 页 `low_coverage` 73–78%：每行行首插一个数，毁掉约 1/5 的三元组；ICLR 稿的 `table_mismatch` 是表格框跨进了行号列 | 实测 |

## 3. VL 后端

### 3.1 选择

```
uv run scripts/parse.py INPUT ... -o OUTDIR [--backend auto|vllm|native] [--vl-server URL]
```

- `--vl-server URL`：用一个已经在跑的 vLLM 服务（模型名由客户端向服务查询）。启动前 `GET URL/models` 探活，不通就 `{"error": "vl_server_unreachable"}`，退出码 2。
- `--backend vllm`：向 vllm-serve 要 VL 模型的服务（`serve.py up paddleocr-vl`）；找不到 vllm-serve 或它给不出服务，`vl_server_failed`（附 vllm-serve 的错误），退出码 2。
- `--backend native`：原生后端，即 v1 的行为。
- `--backend auto`（默认）：找得到 vllm-serve、且待解析（扣掉 `up_to_date` 跳过的）总页数 ≥ 8 时，同 `vllm`；否则原生。要不到服务时不退出：stderr 打一行原因，退回原生继续。8 页是盈亏点：冷启动服务约 50–60 s，原生约 11 s / 页，服务约 1–1.5 s / 页；服务已在跑时这笔开销没有，所以不足 8 页时先问一下 vllm-serve（`serve.py status`，约 1 s），在跑就照样用它（实现时补上：1 页的解析原生要 15 s）。

后端不进 `options`（两者输出等价），已有的原生解析结果不会因此重做；JSON 的 `parser.backend` 记 `native` 或 `vllm-server`，摘要行加 `backend` 和 `pages_per_minute`（issue 1 方向 6）。stderr 在加载时打一行 `[paddleocr] VL backend: …`（为什么选它；原生时提示装 vllm-serve 能快约 10 倍），补上 issue 里“看不到批大小 warning”的盲区。

### 3.2 服务从 vllm-serve 来

用户决定（2026-10-09）：vLLM 单独成环境，并作为本机统一后端，不只为 paddleocr——设计见 [20261009-vllm-serve-spec.md](20261009-vllm-serve-spec.md)。paddleocr 因此不自己起停 vLLM，只做三件事：

- 找 vllm-serve：`VLLM_SERVE`（serve.py 路径），否则同级 skill 目录（先解析 `__file__` 的软链接，再找 `../vllm-serve/scripts/serve.py`）。
- `uv run serve.py up paddleocr-vl`，从输出的 JSON 拿 `url` 和 `model`；流水线用 `vl_rec_backend="vllm-server"`、`vl_rec_server_url`，并显式传 `vl_rec_api_model_name`（vLLM 配方的要求）。客户端构造时要向服务要模型名，所以服务就绪后才建流水线。
- 跑完不停服务：vllm-serve 让多方共用并在空闲后自己停。

不装进 paddleocr 环境的依据：vLLM 文档（二进制绑定一种 PyTorch 构建，要新环境）、PaddleOCR-VL 文档（推理服务装在单独的虚拟环境）、vLLM 的 PaddleOCR-VL 配方（“separate venvs for vllm and paddlepaddle”），以及 uv 解析：cu129 的 Paddle 3.2.1 与 PyTorch 2.8.0 钉了不同版本的同名 `nvidia-*` 包，无解。

### 3.3 起服务的细节（在 vllm-serve 里）

服务参数、WSL2 的修正、去掉 `CUDA_MODULE_LOADING`（parse.py 为 Paddle 设的 EAGER 让 vLLM 卡在引擎初始化 3 分钟以上，实测）、`LD_LIBRARY_PATH`、模型下载、显存检查、空闲退出，都由 vllm-serve 负责，见它的 spec。`api-server-count` 不用 PaddleX 的 4：实测 225 页 1 个和 4 个 API 进程都是 109 s，瓶颈在客户端（版面检测与后处理）。

### 3.4 不做

- **VL 批大小 / 按页面复杂度分组**：服务端连续批处理已经解决，原生后端的 1 是 PaddleX 写死的。
- **多文档流水**：服务后端下单篇已经 1 s / 页量级、GPU 未吃满，跨文档预取的收益不值它的复杂度；以后如果 3,000 页仍嫌慢再看。
- **跳过尾部无文字层页（Reporting Summary）**：`--pages` 已经能做，交给 agent 判断；服务后端下这几页只多几秒。

## 4. 核对改进

### 4.1 行号（issue 4）

`layer_chars` 取出每页文字层后去掉行号（它知道页宽；纯函数 `line_number_chars` 单独测试）：纯数字（≤ 4 位）的词按 x 聚类（±12 px），只看落在页宽左右各 20% 以内的类（实测两种稿件在 11% 和 13%），类内按 y 排序，取值逐个 +1、y 递增、连续 ≥ 10 个的段视为行号，把这些字符换成空白（与 `layer_chars` 里空白字符的写法一致）。所有检查都在去掉行号后的文字层上做。页边限制让表格里逐行 +1 的序号列不被误删。SKILL.md 的误报清单里删掉“行号”。

### 4.2 行内公式的“粘连”渲染（issue 3 后半）

解析侧的行内公式现在要么原样切词（LaTeX 字母被拆开，单字母丢掉），要么整段删掉；文字层却是字母粘着下标（`Tp`、`ak`、`DKL`）。加一种渲染：在 `$…$` 内删空白、`_ ^ { }`，样式命令（`\mathcal \mathrm \mathbf \mathit \text \operatorname \hat \bar \tilde \boldsymbol …`）直接删，其余命令换成空格（关系符、希腊字母——文字层里的希腊字母本来就被丢弃）。

- 页面检查：解析侧的词流从两条（保留、删除行内公式）变成三条，加上粘连渲染；任一条里有的三元组都算找到。只会更宽松。
- `extra_text`：三个候选在全部语料上比较后定一个——(a) 现状，删掉行内公式；(b) 改用粘连渲染；(c) 两种渲染下都缺的才报。标准：issue 现场的误报（shao 第 3 页，`H_{k+1}` 粘连后是 `hk 1`，对上文字层的 `Hk+1`）消失，真编造（截图测试里那种续写、shao 第 6 页、zhang 第 17 页）仍报。

### 4.3 编造的文字（issue 3 前半）：`foreign_script`

有文字层的页上，`extra_text` 检查范围内的块（框内文字层字符 ≥ 20），出现文字层（本页及前后一页）里没有的 CJK 汉字、假名或谚文字符时，报 `foreign_script`，带 `block`、`region` 和每处前后 20 字的片段（如 “…u_{j,1:N_j} $年第 $ j $个signal…”）。中文论文里的汉字在文字层里有，不报。SKILL.md 归入“Invented”。

### 4.4 循环（issue 2）

`repetition` 加一条判据：非表格、非公式块的词三元组 ≥ 30 个、去重率 < 30% 时也报（实测正常块最低 56%，循环块 6%）。`detail` 写字符数和去重率；`repetition` 改为带 `block` 字段（于是 PDF 有 `region`），与其他单块告警一致。原来的短片段正则保留。

### 4.5 旧结果重新核对

`up_to_date` 跳过时返回的是 JSON 里存的旧 warnings，核对改进到不了已经解析过的文档（研究项目的 150 篇、issue 现场的 9 份）。所以核对单独记版本：JSON 加 `parser.check`（从 2 起；v1 的 JSON 没有这个字段，视为 1），与 `FORMAT` 分开。跳过时如果 `check` 比当前旧，就用 JSON 里的 blocks、`pages[].width/height` 和输入的 PDF 重跑 `check_document`（秒级，不用 GPU），改写 JSON 的 `pages` 覆盖率、`warnings` 和 `parser.check`；Markdown 不动（agent 的修正在里面）。摘要行照常是 `skipped: up_to_date`，另带 `rechecked: true` 和新 warnings。`FORMAT` 不变：输出结构没变，不必重新解析。

`region` 的换算从 `process` 里抽成函数，解析和重新核对共用。

## 5. 文件改动

- `scripts/parse.py`：§3、§4；docstring 补选项、`backend`、新告警码和错误码。
- `tests/test_parse.py`：行号剥离（含页内序号列不动）、粘连渲染、`foreign_script`、循环判据、vllm-serve 的查找、`auto` 的页数门槛、旧 `check` 版本触发重新核对（纯函数，不起 GPU）。
- `SKILL.md`：第 1 步的速度说明改为按后端写；告警清单加 `foreign_script`、删“行号”误报。
- `references/install.md`：“Many documents”一节改为“vLLM server”：为什么快、为什么 vLLM 必须单独成环境、装 vllm-serve。

## 6. 验证

1. 单元测试全过。
2. 离线复核：issue 现场 9 份 + diffusion 项目 31 份 + 测试集，逐条对比新旧 warnings，人工判断每条消失或新增的真假。
3. 重新核对：对 issue 现场 9 份的 JSON 副本不加 `--force` 再跑一次，确认走的是重新核对、warnings 与离线复核一致、Markdown 未变。
4. 端到端：装好 vllm-serve 和 `uv tool install vllm` 后，`auto` 跑测试集（LDM、SDEdit）和 issue 现场 9 份，记录速度、显存、告警，与先前 vLLM 0.28 的结果对比；`--vl-server` 和 `--backend native` 各跑一次；两个 parse.py 同时跑只用一个服务。
5. 装到全局后（推送后）再跑一页冒烟。

## 7. 实现记录（2026-10-09）

- **extra_text 三个候选**（§4.2）：在 35 份有源 PDF 的语料上比较。(b) 只用粘连渲染新增十几条误报（ORCID 的 `id` 上标、算法框和矩阵里的变量）；(c) 两种渲染下都缺才报，正好去掉 shao 第 3 页的公式误报，保留第 6 页的编造和 zhang 第 17 页的误读（StratifAI 读成 stratifal）。用 (c)。
- **离线复核全部语料**，新旧对比：`missing_text` 43 → 16、`low_coverage` 11 → 0、`missing_numbers` 16 → 15，消失的每条都逐一看过——行内公式粘连（shao 12 条、wang 4 条、另外 6 篇各 1–3 条）、行号（补充材料 9 页 `low_coverage`、ICLR 稿两张表的行号）、一个代码清单的行号（lin 第 3 页的“18”，同样该去）。新增：xu 第 1 页 `repetition`（作者行循环）、shao 第 6 页 `foreign_script`。ICLR 稿第 24 页的 `table_mismatch` 去掉行号后仍有 317/416 个词缺失，是真丢内容。
- **端到端，第一版**（parse.py 自己起停 vLLM，`PADDLEOCR_VLLM` 指向 mineru 的 vLLM 0.28；后来按 §3.2 改由 vllm-serve 提供服务）：LDM + SDEdit 45 页 70 s（起服务与加载 43 s，LDM 58 页 / 分钟、SDEdit 178 页 / 分钟），显存峰值 24.8 GB（含其他程序约 4 GB）。issue 现场 9 份 225 页走 `--vl-server`：109 s（原生 2,489 s），作者行循环在 vLLM 下同样出现，被 `repetition` 报出。parse.py 被 SIGKILL 或 SIGTERM 后，服务都在 2 s 内退出，显存回到基线。
- **重新核对**：对 issue 现场 9 份 JSON 的副本不加 `--force` 重跑，5.6 s 完成，warnings 与离线复核一致，Markdown 逐字节不变，再跑一次不再重复核对。
- 第一次端到端时服务 300 s 未就绪、按设计退回原生——原因是继承了 `CUDA_MODULE_LOADING=EAGER`，见 §3.3。
- **改由 vllm-serve 提供服务**（§3.2，用户决定 vLLM 作为本机统一后端）：parse.py 删掉自己起停 vLLM 的代码，`auto` 调 `serve.py up paddleocr-vl`，并显式传模型名（vLLM 0.31 的服务以 HF id 为模型名，客户端默认名会 404）；`--vl-server` 从 `/v1/models` 读模型名。vLLM 0.31 上 issue 现场 225 页约 95–110 s，与原生逐块对比和 0.28 时一致；数字和调优见 [vllm-serve spec](20261009-vllm-serve-spec.md) §7。
- **服务在跑时小解析也用它**：1 页的解析，服务没起时走原生（总 30 s），服务在跑时直接用（总 17 s）。
