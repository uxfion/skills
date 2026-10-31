> 部分被 [20261031-vllm-serve-principles-rework-spec.md](20261031-vllm-serve-principles-rework-spec.md) 取代：启动等待、下载时机、`up` 判断端口上是谁的做法、`idle_minutes = 0`，以及 3.5 末尾的三处（带密钥、试绑端口、“第一条错误行”）。

# vllm-serve：共享服务器与远程部署（2026-10-30）

> 来源：[20261029-vllm-serve-remote-multi-gpu-fixed.md](../issues/archive/20261029-vllm-serve-remote-multi-gpu-fixed.md)（另一个项目在两台共享服务器上部署 Qwen3.8-27B 时记下的 17 条）。用户：「之后就可以参考这个vllm skills快速部署了，而不用再另外适配了」「具体差异化的东西可以放项目的文档里，但通用的东西，就放到skills中」。优化时的要求：「别人提的要求不一定非要去实现的，你要有自己的判断」「尽量不要修修补补，要从根源上解决问题，从顶层设计」「你现在是一个 Agent，你有自主性的，调用这个skill的agent都是有自主性的……脚本不能做的事情，就交给agent去自己做」，无人值守。
> 原 spec：[20261009-vllm-serve-spec.md](20261009-vllm-serve-spec.md)（一份安装、每个模型一个 profile、按需启动、多方共用、空闲自停），这些不变。

## 1. 目标

- 拿到 skill 的 agent，在任何一台 GPU 机器上都能很快起好服务：本机、多人共用的服务器、ssh 过去的远程机器都一样，不用再写适配脚本。
- 通用的东西进 skill（脚本、文档、模型 profile），部署方只留差异：一个几行的 profile，加一个环境文件。
- 分工清楚：脚本只做每台机器都一样的确定性的事——起停、共用、空闲自停、等它就绪、报出状态；随机器而变的判断——文件放哪、用哪几张卡、装哪个 CUDA 构建、下载不通怎么办、怎么调优——交给 agent，skill 给原则和带日期的提示。
- 只用 vLLM 自己的参数和环境变量作词汇，不另造键和语法：agent 本来就懂 vLLM，脚本从参数里读它需要的值，两边不会写岔。
- 衡量标准：skill 变短、变好用，而不是条目逐条打勾。

## 2. 依据（2026-10-30 调研与实测，vLLM 0.32.0）

| 事实 | 来源 |
| --- | --- |
| 加载期间端口没在监听（连接被拒），`/health`、`/v1/models` 都无应答，直到引擎就绪 | vLLM 源码 v0.32.0 |
| `VLLM_ENGINE_READY_TIMEOUT_S`（默认 600 s）只在数据并行 > 1 时限制加载（每个 API server 等各自的引擎）；数据并行为 1 时启动器不设期限。其他计时器（握手、协调器、NCCL）不限制加载 | 同上，`core_client.py`、`engine/utils.py` |
| 显存检查 vLLM 自己做：启动时某张卡的空闲显存低于 `--gpu-memory-utilization`（按每张卡，默认 0.92）× 总量就报错退出，报错写明卡号、空闲量和要求量 | 同上 |
| 数据并行：一个 `vllm serve --data-parallel-size N` 在一个端口后面做负载均衡；第 r 个副本用 `CUDA_VISIBLE_DEVICES` 里第 [r·t, (r+1)·t) 个卡（t 为张量并行数）；数字卡号按 `nvidia-smi` 的编号理解 | 同上；nvitop 文档 |
| `max_num_seqs` 默认：显存 ≥ 70 GiB（非 A100）的卡上 1024，否则 256；混合模型每个解码序列占一个 Mamba 块，vLLM 不会自动调低，块不够就启动失败 | 同上，`compilation.py:1503` |
| `/metrics`：计数器带 `_total`（`vllm:request_success_total`、`vllm:prompt_tokens_total`、`vllm:generation_tokens_total`、`vllm:prefix_cache_queries_total`、`vllm:prefix_cache_hits_total`、`vllm:num_preemptions_total`），量表不带（`vllm:num_requests_running`、`vllm:num_requests_waiting`、`vllm:kv_cache_usage_perc`，0–1）；每条带 `engine` 标签（数据并行的副本号），0.31 到 0.32 只增不改 | 同上 |
| `--host` 默认监听所有网卡；重复写时后者生效；默认不记录请求内容（`--enable-log-requests` 才记参数，提示词只在 DEBUG） | 同上 |
| `--generation-config auto`（默认）：调用方没传的采样参数取模型的 `generation_config.json` | 同上 |
| `--safetensors-load-strategy`：lazy（默认，NFS/Lustre 上自动预读）/ eager / prefetch / torchao | 同上 |
| 离线时完整 40 位提交号的 `--revision` 直接对应缓存里的 `snapshots/<提交号>` | 同上；huggingface_hub |
| `hf download --revision <提交号>` 不写 `refs/main`；下载只核对大小；`hf cache verify <repo> --revision <提交号>` 核对 sha256（huggingface_hub ≥ 1.1）；1.32 起文件链接指向缓存根下共享的 `blobs/`，只拷一个模型目录会断链 | huggingface_hub 源码与文档（本机 2.1.1） |
| PyPI 上的 vLLM 0.32.0 是 CUDA 13.0 构建（驱动 ≥ R580）；另一个构建 `+cu129` 只在 GitHub release 附件和 `https://wheels.vllm.ai/0.32.0/cu129`；`--torch-backend` 只换 torch 系列，不换 vllm 本身 | vLLM release、install 文档；uv |
| PyPI 没有 CUDA 12 的 nvcc（`nvidia-cuda-nvcc-cu12` 只有 ptxas 等），cu129 环境里 FlashInfer 编不了 kernel，只能用预编译包；vLLM 0.32 新增 `vllm download-kernels`，装上 FlashInfer 的预编译 kernel（`flashinfer-cubin` 0.7.0.post1 只在 flashinfer.ai/whl） | PyPI；vLLM 源码；主机 B 实测 `--help` |
| 注意力后端：FA3 只在 Hopper；sm_100 首选 FlashInfer；sm_120（RTX 5090、RTX PRO 6000）、sm_89、sm_80 用 FA2 | vLLM 源码 |
| 工具写文件的位置各有各的变量，且有几个不认 XDG：FlashInfer（`FLASHINFER_WORKSPACE_BASE`，默认在家目录）、tvm-ffi、CUDA 的 `~/.nv/ComputeCache`、torch 在 `/tmp/torchinductor_<登录名>`；项目的 env.sh 漏了这几个 | nvitop 等调研；各工具源码 |
| uv：官方安装脚本加 `UV_UNMANAGED_INSTALL=<目录>` 只写那个目录；uv 工具环境不能搬（绝对路径），要在原地建；conda 的 Python 会被优先选中，`UV_PYTHON_PREFERENCE=only-managed` 挡住 | uv 源码与文档 |
| 现成工具：llama-swap（常驻代理，卡写死在配置里）、production-stack / SkyPilot / GPUStack（要 Kubernetes、Docker 或 sudo）都替代不了 serve.py；nvitop 适合给人看卡（显示进程的用户）；vLLM 0.32 没有读 `/metrics` 的命令 | 调研（reuse-survey） |

## 3. 设计

### 3.1 profile：vLLM 参数是唯一的词汇

profile 的键只剩 serve.py 自己的概念：`model`（模型和对外名字）、`port`（这个服务的地址）、`idle_minutes`、`args`（vLLM 参数）、`env`，加一个 `extends`。其余 vLLM 的设置都写成 vLLM 参数，serve.py 需要哪个就从最终参数里读（同一个参数写了多次，后面的生效，和 vLLM 一致）：

- `--host`：决定健康检查走哪个地址、是否对外；没写时 serve.py 补 `--host 127.0.0.1`（vLLM 的默认是所有网卡）。
- `--revision`：决定下载哪个版本、判断是否已缓存。

serve.py 自己加在最后的只有它必须掌握的：`--served-model-name <model>`、`--port <port>`。原来的 `gpu_memory_utilization` 键并入参数（`--gpu-memory-utilization`，不写就是 vLLM 的默认 0.92）。

`extends = "<另一个 profile 名>"`：先取那个 profile，再用本文件覆盖：普通键直接覆盖，`args` 接在后面（后者生效，所以本文件可以改写任何参数），`env` 合并。可以继承同名的 profile（本地 `qwen38-27b.toml` 继承 skill 里的 `qwen38-27b`）。这是“通用在 skill、差异在部署方”的唯一机制。例：

```toml
# <根目录>/.config/vllm-serve/profiles/qwen38-27b.toml —— 部署方的全部内容
extends = "qwen38-27b"
idle_minutes = 120
args = ["--revision", "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0", "--host", "0.0.0.0", "--max-num-seqs", "16", "--seed", "0"]
env = { CUDA_VISIBLE_DEVICES = "1" }
```

`up <profile> -- <vLLM 参数>`：只对这一次启动追加参数，排在 profile 的参数后面，所以能改写它们。调用方的环境变量（例如 `CUDA_VISIBLE_DEVICES`）也传给服务，但 profile 的 `env` 设了的变量以 profile 为准：`--` 后的参数是有意敲的，环境却可能是顺带继承的——共享机器上，调度器或系统设置带着的 `CUDA_VISIBLE_DEVICES` 不能把部署挪到别人在训练的卡上（独立评审指出，实现中改回）。agent 临时选了卡：`CUDA_VISIBLE_DEVICES=4,5 serve.py up qwen38-27b -- --data-parallel-size 2`。规则：要在服务空闲自停之后还有效的选择（下一次由别的调用方 `up`），写进部署方 profile 的 `env`、`args`；调用方的环境和 `--` 后的参数只管这一次启动。

`up` 输出的 `url` 始终是本机回环地址（机器上的调用方直接用）；监听超出回环时，另加 `host`（绑定的地址），远程调用方用它自己知道的这台机器的地址拼出 URL——不猜网卡。

### 3.2 卡：vLLM 自己查，agent 自己挑

- 删掉 serve.py 的显存预检和 `gpu_busy`。issue 第 1 条的误报来自这个预检模仿 vLLM、却只看第一张卡；vLLM 0.32 自己在启动后几秒内按实际用到的每张卡检查，报错写明是哪张卡、空闲多少、要多少，会出现在 `server_failed` 的日志末尾里。少一份重复判断，也就不会再和 vLLM 判断得不一样。
- serve.py 给每个服务设 `CUDA_DEVICE_ORDER=PCI_BUS_ID`，让 `CUDA_VISIBLE_DEVICES` 里的数字和 `nvidia-smi` 的编号一致（CUDA 默认按速度排序，多种卡混插时会对不上）。
- 用哪几张卡、数据并行还是张量并行、共用卡给多少显存，是 agent 的判断，原则写在 `references/shared-machines.md`：一份模型放得下单卡就数据并行；张量并行数要整除注意力头数；共用的卡隔一段时间看几次再定；比例按最少的那张卡的空闲显存算。看卡用 `nvidia-smi`（`uvx nvitop` 还能看到进程属于哪个用户），不另做命令。

### 3.3 启动：看进度，不看钟

`up` 等服务就绪时不再用固定期限（原来 300 s）。只要守护进程活着、日志在增长，就继续等；日志 10 分钟不动才算卡住（10 分钟是我定的数，比实测最长的静默阶段长得多），停掉并报 `server_failed`，`detail` 写明是“进程退出”还是“日志 10 分钟没动”，后者可能只是没装预编译 kernel 时在慢网上下载。慢盘上读 52 GB 权重要七八分钟、第一次启动要现编 kernel，都在持续写日志；真正卡死（比如张量并行初始化挂住）时日志不再动。vLLM 自己的 `VLLM_ENGINE_READY_TIMEOUT_S` 由 serve.py 调到很大，交给这条规则判断。另一个 `up` 碰到正在启动的服务时也按同一规则等。

### 3.4 权重：认版本

- 下载：`hf download <model> --revision <参数里的版本>`。
- 判断已缓存：写了提交号就看 `snapshots/<提交号>`；写了分支或标签就看 `refs/<名字>`；没写就看 `refs/main`（离线加载 `main` 时 vLLM 需要它，只有某个快照不够）。
- `hf` 的进度和报错直接输出到 `up` 的 stderr，失败时 `download_failed` 指向它（原来被丢弃，ssh 过去看不到下载进度）。
- 校验和下载不通（只连得上 huggingface.co、连不上下载 CDN）交给 agent：文档提示 `hf cache verify`、整个缓存一起拷（共享的 `blobs/`）。不做 sha256 清单键：只有从别处拷缓存时才需要，而 `hf cache verify` 已经能做。

### 3.5 运行中的服务

- 守护进程本来每 30 s 读一次 `/metrics` 判断空闲；顺带算出负载写进状态文件：运行和排队的请求数、KV 占用（数据并行取最大的那个副本）、前缀命中率、抢占次数、最近 30 s 的输入和生成 token/s。`status` 直接读状态，不用等。
- 状态文件记下启动者（登录名）、`CUDA_VISIBLE_DEVICES`、启动命令和环境；`status` 显示启动者和卡。
- `up` 碰到已在运行的服务，而这次要启动的命令或卡和它不一样（profile 改过、换了卡、加了参数），照样返回这个服务，并附 `differs`，列出运行中的值；要生效就先 `down`。不报错，免得打断只想要个服务的调用方（paddleocr）。
- 碰到别的登录启动的服务或别人的文件（`down` 停不了、状态目录写不进），统一报 `not_permitted`，写明属于谁、该由谁处理，不再抛异常。
- `idle_minutes = 0`：不自己停。局域网上的客户端调不了 `up`，空闲自停后要有人经 ssh 再 `up`，或者让服务一直开着；由用户选。`status` 里已空闲多久改叫 `idle_for_minutes`，免得和 profile 的键混淆。

评审后补上的几处根因（独立的“新 agent”评审，实现中）：

- serve.py 访问自己机器上的服务（健康检查、`/metrics`）一律不走代理：`http_proxy` 设了而 `no_proxy` 没盖住 127.0.0.1 时，健康的服务会被当成没起来，忙着的服务会被当成空闲停掉。
- 服务用 `--api-key`（或 `VLLM_API_KEY`）保护 `/v1` 时，健康检查带上它；局域网上的服务常要这个。
- `port_busy` 包括“别的程序占着端口”：启动前按 vLLM 的方式（`SO_REUSEADDR`）试绑一次端口，而不是等 vLLM 报“地址已被占用”再当成 `server_failed`。
- `server_failed` 带上日志里第一条 Python 错误行：vLLM 的根因在结尾那串 traceback 上面，只给最后 20 行常常看不到。
- CUDA 12 环境里没有工具包时，去掉调用方带来的 `CUDA_HOME`、`CUDA_PATH`，`CUDA_LIB_PATH` 指向环境自己的 CUDA runtime：系统工具包照样不能混进来。

### 3.6 文件放哪：原则交给 agent

skill 不带固定的环境脚本。`references/shared-machines.md` 写原则：用户指定一个根目录，部署写的一切都落在里面；根目录里留一个环境文件，之后的会话 source 它就进入同一个环境；skill 也拷进根目录，在目标机上运行（agent 负责 ssh，serve.py 不管）。带日期的提示：把 `HOME` 指到根目录，一次就盖住所有工具，包括逐个列变量时漏掉的 FlashInfer、CUDA 的 `~/.nv` 和 Triton；登录环境里已经设了的各工具变量（`UV_CACHE_DIR`、`HF_HOME`、`XDG_*`）比 `HOME` 优先，要在环境文件里清掉；`TMPDIR` 不动——vLLM 的 IPC socket 放在那里，路径超过 107 个字符服务就起不来（这两条都是本机演练时实测撞到的）。uv 也装进根目录（`UV_UNMANAGED_INSTALL`），换了登录只要把根目录交给新登录，不用重装。shared-machines.md 写成首次部署的步骤（每步一条命令）加上原则。serve.py 不需要知道根目录：它本来就从环境（`XDG_*`、`HF_HOME`、家目录）找自己的文件。

登录与权限：用个人登录；要 root 的步骤（卸系统包、`chown`、在 root 的目录下建目录）写成命令交给用户执行，再自己核对；文档、脚本、路径里不写登录名，要用时 `id -un` 现查。

### 3.7 安装

install.md 改成按驱动选构建，并钉住 Python（`--python 3.12`：只用 uv 自己的 Python 时它会取最新的 3.15，torchaudio 2.11 没有对应的包，实测装不上）：`nvidia-smi` 报的 CUDA 版本 ≥ 13.0 用 PyPI 上的默认构建（现有命令，版本改为 0.32.0）；12.9 用 `+cu129` 构建（release 附件或 wheels.vllm.ai 的索引）配 `--torch-backend cu129`；装完运行 `vllm download-kernels`（cu129 上没有它 FlashInfer 用不了，cu130 上省掉第一次启动的现编）。显卡架构决定注意力后端（FA3 只在 Hopper）。补上：在最终位置原地建环境、PyPI 慢时先预热 uv 缓存、`only-managed`；权重下载不通时的做法；排障加上混合模型的 `max_num_seqs`、慢盘用 `--safetensors-load-strategy eager`。

### 3.8 调优参考 `references/tuning.md`

按用户定的原则写：模型卡和官方菜谱推荐、引擎自带、一个开关就能打开的优化顺手做，并在真实负载上简单确认；外挂草稿模型、手调 batch 和 chunk 这类细调不做；会改变数值的选项（FP8 KV cache、量化）不放进要和以前结果比较的运行。内容是通用方法，Qwen3.8-27B 的实测作例子：容量估算（权重 + 运行开销 + 每 token 的 KV，从启动日志哪几行读）；按调用方的上下文定 `--max-model-len`；并发怎么定（多轮会话靠前缀缓存，KV 峰值留余量，`--max-num-seqs` 设上限，看哪几个指标）；混合模型的 `max_num_seqs` 上限；单卡放得下就数据并行；投机解码先核对菜谱的版本说明，再在真实负载上比较“不开”和“菜谱值”两档；采样参数默认从哪来。

### 3.9 新 profile `qwen38-27b`

只放通用的：菜谱参数（`--reasoning-parser qwen3`、`--enable-auto-tool-choice --tool-call-parser qwen3_coder`、`--language-model-only`、`--max-model-len 262144`）和 `--max-num-seqs 256`——vLLM 在 96 GB 卡上默认 1024，超过单卡 Mamba 块数（680）会起不来；256 是 vLLM 给小卡的默认，在单卡放得下整个上下文的配置下都起得来。为长多轮会话收紧并发（96 GB 卡上 16）、固定版本、局域网监听、卡号、慢盘的读法都属于部署方。注释写出处、显存要求、MTP 实测为什么没开、采样默认值。`idle_minutes = 30`：这个模型冷启动 2–7 分钟，比 10 分钟的默认更值得留着；部署方按调用节奏再改。

### 3.10 不做

- 自动选卡（项目的 `up_on_free_gpus.sh`）：选卡标准随机器和用户而变（空闲阈值、利用率、要不要共用），交给 agent 按原则判断。
- `startup_timeout`、`host`、`revision`、`gpus` 键和 `--gpus` 选项：分别被“看进度”和“读 vLLM 参数”取代。
- 混合模型 `max_num_seqs` 报错时 serve.py 给提示：vLLM 的报错已写明“Please lower max_num_seqs”，`server_failed` 带着日志末尾；写进排障和调优参考。
- sha256 清单键：见 3.4。
- 状态命令里列出每张卡：`nvidia-smi` / `nvitop` 已经做得更好。

## 4. issue 条目的处理

| # | 处理 |
| --- | --- |
| 1 显存检查只看第一张卡 | 换做法：删掉预检，交给 vLLM；`CUDA_DEVICE_ORDER=PCI_BUS_ID`（3.2） |
| 2 启动期限 | 换做法：看进度（3.3）；慢盘读法写进 install.md |
| 3 CUDA 构建按驱动选 | 采纳：install.md（3.7） |
| 4 文件放进指定目录 | 换做法：原则交给 agent，不带固定脚本（3.6） |
| 5 只监听 127.0.0.1 | 换做法：`--host` 写进参数，serve.py 照着做（3.1） |
| 6 选卡、共用、DP/TP | 换做法：原则交给 agent（3.2）；profile 改过时 `differs`（3.5） |
| 7 混合模型 `max_num_seqs` | 采纳：profile 设 256（3.9），调优参考讲上限；不做专门提示 |
| 8 KV 占满吞吐下降 | 采纳：调优参考；`status` 显示 KV、排队、抢占（3.5） |
| 9 显存估算 | 采纳：调优参考 |
| 10 revision、CDN、校验 | 部分采纳：认版本（3.4）；CDN 和校验写进文档 |
| 11 uv 环境不能搬 | 采纳：install.md |
| 12 FlashInfer 现编 | 采纳：`vllm download-kernels`（3.7） |
| 13 MTP | 采纳：调优参考的通用做法；profile 注释 |
| 14 `status` 看不到负载 | 采纳（3.5） |
| 15 采样参数从哪来 | 采纳：profile 注释和调优参考 |
| 16 新 profile | 采纳，只放通用部分（3.9） |
| 17 不给 root | 采纳：`not_permitted`、启动者（3.5）；登录和根目录的原则（3.6） |

## 5. 文件

```
vllm-serve/
├── SKILL.md                      用法；新增一段指向共享机器的参考
├── scripts/serve.py              3.1–3.5
├── profiles/paddleocr-vl.toml    显存比例并入 args
├── profiles/qwen38-27b.toml      新增
├── references/install.md         按驱动选构建、download-kernels、权重、排障
├── references/shared-machines.md 新增：根目录、登录、选卡、局域网、拷 skill
├── references/tuning.md          新增：调优参考
└── tests/test_serve.py           extends、追加参数、看进度、版本、负载、differs、权限
```

README 的 vllm-serve 一行改为提到共享和远程机器。

## 6. 验证（计划）

1. 测试（不需要 GPU）：用替身 vllm 覆盖 extends 合并、追加参数和环境的传递、`--host` 与 url、看进度等待（一直写日志的慢启动成功，日志停住的失败）、按版本判断缓存、负载写进状态、`differs`、`not_permitted`。
2. 本机：`paddleocr-vl` 起服务、发一个请求、`status`、`down`（本机 vLLM 0.31.0）。
3. 主机 B（2× RTX PRO 6000，CUDA 13.2 驱动）：按 shared-machines.md 从零建一个新的根目录（uv 进根目录、vLLM 0.32.0 cu130 原地装、`vllm download-kernels`、权重拷进来后 `hf cache verify`），部署方 profile 继承 `qwen38-27b`；单卡起、从本机经局域网发请求、并发时看 `status` 的负载、`down`；再两卡数据并行起一次。
   数据并行时核对 `/metrics`：有请求在跑时读三次，`vllm:num_requests_running` 是否覆盖两个副本（`engine` 标签都在）。若只有一个 API 进程的计数，空闲判断会误停忙着的服务，要在 serve.py 里固定 `--api-server-count 1` 或另想办法，并改本 spec。
4. 主机 A（8× H200，CUDA 12.9 驱动，其他卡有人在用，系统装着 CUDA 13.1）：用已有的 vLLM 环境在空闲卡上起一次，确认卡号、共用机器上的行为，以及 `foreign_cuda` 为空——cu129 环境里没有 nvcc，`own_cuda()` 找不到环境自己的工具包，FlashInfer 可能从 `/usr/local/cuda` 预加载系统的 cudart；若有，把 `CUDA_LIB_PATH` 指到环境的 `nvidia/cuda_runtime/lib`，写进 3.7。cu129 的装法做一次依赖解析（调研时已用 `uv pip compile` 解析通过；主机 A 当时装的是下载下来的同一个 wheel）。

做完时：issue 关闭，归档；本 spec 补实现记录后冻结。

## 7. 实现记录（2026-10-30）

- **代码**：serve.py 按 3.1–3.5 重写，494 行变成 683 行：删掉显存预检和固定期限，加上 extends、读参数、看进度、负载、权限和评审后的几处；换来的是项目那边的 env.sh、serve.sh、serve_startup.py、nvidia-smi 包装和选卡脚本都不再需要。测试 16 个，全部通过：extends 合并与校验（含同名继承、循环、旧键报错）、参数读取与 `--host`、CUDA 环境（含 CUDA 12 无工具包）、按版本判断缓存、负载与空闲、完整的起停（追加参数和 `CUDA_VISIBLE_DEVICES` 传到服务、`differs`、局域网监听加 API key、慢启动成功、日志停住失败、别的程序占端口、启动报错取第一条错误行、别的登录的服务），所有起停测试都在设了失效代理的环境里跑。
- **本机演练**（RTX 5090 D，WSL2，驱动 CUDA 13.x）：按 shared-machines.md 在一个新根目录里从零做了一遍：环境文件只换 `HOME`；uv 用 `UV_UNMANAGED_INSTALL` 装进根目录；`uv tool install --python 3.12 "vllm==0.32.0" --torch-backend cu130 --with "cuda-toolkit[…]==13.0.3"` 约 2 分钟；`vllm download-kernels` 在 uv 工具环境里可用（它自己调 `uv pip install`），装了 FlashInfer 的 cubin 和各架构 jit-cache，经本机代理约 15 分钟；`up paddleocr-vl` 下载权重到根目录、首次启动 2 分 29 秒，一张图的 OCR 结果逐字正确，`status` 显示启动者和负载，`foreign_cuda` 为空，没有“预编译 kernel 缺失”的警告；paddleocr 的 parse.py 用 `--vl-server` 接这个 0.32 服务解析一页（标题、段落、表格），`checks=ok`、覆盖率 1.0。所以 install.md 的版本改为 0.32.0；本机日常用的 vLLM 仍是 0.31.0，没动。新 serve.py 也按 paddleocr 平时的路走了一遍：本机的 vLLM 0.31.0、原来的 HF 缓存（有 `refs/main`，没有重新下载），parse.py 经 `VLLM_SERVE` 找到它、解析同一页通过，`status`、`down` 正常，paddleocr 自己的测试通过。
- **演练撞到的三处**，都已写进文档：只用 uv 的 Python 时取到 3.15 装不上（钉 `--python 3.12`）；登录环境里的 `UV_CACHE_DIR` 让下载落到根目录外（清掉各工具变量）；`TMPDIR` 放进长路径的根目录后 vLLM 的 IPC socket 超长（`TMPDIR` 不动）。最后一处正是新的 `server_failed`“第一条错误行”直接报出来的。
- **独立评审**（一个没看过对话的 agent，读 skill 走两个场景）：24 条。采纳的根因修改见 3.5 末尾和 3.1；文档按它补了首次部署的步骤、根目录的确切位置、部署 profile 要和被继承的同名、局域网地址和防火墙、`HOME` 换掉后的凭据、远程客户端调不了 `up`；删掉了重复的数字（profile 注释只留模型的要点，实测数字在 tuning.md）和重复的说法（并行方式只在 tuning.md）。没采纳：在 serve.py 里认特定的报错并给提示（取第一条错误行已够，且是通用的）。
- **没做的验证**：两台共享服务器上的实测（第 6 节第 3、4 条）。经 ssh 在远程机器上写文件、起服务被 Claude Code 的自动权限分类拦下（“Remote Shell Writes”），按规矩没有绕过，留给用户决定。还没在真机上确认的：数据并行时 `/metrics` 是否覆盖所有副本（影响空闲判断和负载）；CUDA 12.9 环境（主机 A）里 `foreign_cuda` 为空；多卡、局域网访问、`hf cache verify` 拷来的权重。
