# vllm-serve：在共享的多卡远程服务器上部署大模型（Qwen3.8-27B，两台主机）

2026-10-29 至 10-30，另一个项目把 Qwen3.8-27B（BF16，权重 55.6 GB，混合注意力：64 层里 48 层是 gated-delta-net 线性注意力）部署成一个固定的自部署后端。调用方是 Claude Code 无头模式（`claude -p`），走 vLLM 的 Anthropic Messages 接口；2026-10-30 该项目决定改用开源的 pi agent，接口可能换成 OpenAI 兼容的 Chat Completions（第 15 条因此取决于调用方）。每个会话多轮、带工具调用，上下文 4–7 万 token（另一类任务最长 16 万），每轮 `max_tokens` 32000，同时跑 12–40 个会话。

用到两台多人共用的服务器，下文称主机 A、主机 B：

| | 主机 A | 主机 B |
|---|---|---|
| GPU | 8× H200 143 GB（只有部分空闲） | 2× RTX PRO 6000 Blackwell 96 GB（都在跑别人的训练） |
| 驱动 | 575.57（CUDA 12.9） | 595.99（CUDA 13.2） |
| 软件 | vLLM 0.32.0，torch 2.13.0，flashinfer 0.7.0.post1 | 同左 |

两台主机上都没法直接用 skill：下面每一条都在该项目里写了补救，放在 `20261029-vllm-serve-remote-multi-gpu-reference/`（git 忽略，里面有真实主机名），那里的 README 列出了每个文件对应哪一条。

用户的要求（2026-10-30）：「另外我是希望将你这几次的经验或者教训或者部署的思路，优化给uxfion/skills ……这样，之后就可以参考这个vllm skills快速部署了，而不用再另外适配了。……具体差异化的东西可以放项目的文档里，但通用的东西，就放到skills中，这样谁上来都能快速用。」「全面更新那张issue吧，我在uxfion/skills的项目里优化它」「然后profiles是不是也应该新增一个，因为我们用了qwen3.8-27B」。

优先级（用户，2026-10-30）：这张 issue 是该项目本地部署的两项前置任务之一（另一项是换开源 harness），两项都解决之前，该项目的本地模型实验暂停：「2. 解决 VLLM 部署问题：我们在部署 VLLM 的过程中遇到了很多问题，我记得你已经把相关问题提交到了 Skills 的 issue 中。」「应该把这两个问题全部解决以后，我们再去做下一步。不然的话，前面做的再多工作也是徒劳，后面也会被推翻。」

调优的原则（用户，2026-10-30）：「如果是那种小众的我觉得就不用做了，大众的，实现起来比较简单，就做一下，像flashattn一样」「另外我说的也要提到，大众的，简单的，优化起来快的，就优先，小众的调优就没必要了。」「我们也不是刻意去调优，只不过一些简单的调优，就可以顺手做一下」。也就是：模型卡和官方菜谱推荐的、引擎自带的、一个开关就能打开的优化（FlashAttention、FlashInfer、前缀缓存、模型自带的 MTP 头）顺手做，并在真实负载上简单确认一下有效；外挂草稿模型、手调 batch 和 chunk 大小、performance-mode 这类细调不做；会改变数值的选项（FP8 KV cache、量化权重）不放进需要和以前结果比较的运行里。调优参考应当按这个原则来写。

怎么处理这些条目（用户，2026-10-30，在本仓库开始优化时）：「开始调研。你自己审，然后从顶层设计，要优雅、高效，另外不能修修补补，要整体思维最优解。然后你自己优化，无人值守。」「别人提的要求不一定非要去实现的，你要有自己的判断……对我们这个skill有用的，能让其更好用的，更优雅的，更能快速使用的，朝着好的方向发展的等，都是可以采纳的。另外尽量不要修修补补，要从根源上解决问题，从顶层设计，全面的设计，要优雅、高效、便利。同时你在优化的时候要调用writing for agents skill。」也就是说，下面的“方向”只是建议，每一条都按对 skill 是否有用来取舍。

## 进展（2026-10-30）

设计和实现：[20261030-vllm-serve-shared-machines-spec.md](../specs/20261030-vllm-serve-shared-machines-spec.md)，第 4 节逐条写了怎么处理（采纳、换做法、不做）。skill 已改，测试通过，本机按新文档从零演练了一遍（新根目录、vLLM 0.32.0、`paddleocr-vl` 起服务和 paddleocr 实际解析）。还差两台共享服务器上的实测：经 ssh 在远程机器上写文件、起服务被 Claude Code 的自动权限分类拦下，等用户决定是放行还是自己跑。实测前不关这张 issue；要核对的点在 spec 第 7 节末尾。

## 按 design-principles 自查（2026-10-30、31，没拍板）

用户：「在你问我问题之前，你先全局地看一下那个 design principle……然后你看一下我们这个 vLLM serve 里面有没有问题。然后再问我一些问题，因为我觉得你之前是没有按照我这个思路来的」；10-31：「我那个 principle 又更新了，你需要再看一遍，然后再过一下，然后再问我问题」。对照 `docs/design-principles.md`（10-31 版，`56bd02a`：“General and simple, never patched”——不为没人遇到过的问题预先造机制，遇到新问题先看通用机制是否已覆盖，否则从根上重切；一个工作项由一个 subagent 从脚本停下处带到底）查出的问题，处理方向都还没拍板：

1. 为没遇到过的问题预造的机制（§3）：评审后加的几处都是假设出来的问题——`--api-key` 时的健康检查、启动前试绑端口、CUDA 12 环境去掉 `CUDA_HOME` 那一支、`idle_minutes = 0` 表示不自停、`CUDA_DEVICE_ORDER=PCI_BUS_ID`（只在混插不同型号的卡时才有差别）、日志里摘“第一条错误行”的正则。真遇到过的只有：慢启动被期限杀掉、`up` 不报 profile 改过、停不了别的登录的服务、只看第一张卡、权重不认版本、`status` 看不到负载。
2. 脚本越过了“确定”的边界（§1）：日志 10 分钟没动就判定卡死并停掉服务——“没动”不等于“卡死”，而“卡死”本身还没遇到过。遇到过的问题（期限杀掉慢启动）从根上的解法是不设期限：等到服务应答或进程退出。
3. 健康检查可以更简单（§3）：用 vLLM 的 `/health`，“端口上是不是我们的服务”由自己的状态文件判断；`/v1/models` 核对模型名、“另一个模型占着端口”那一支都能删。
4. 交接没写进流程（§1）：SKILL.md 在每个停下来的地方没写清谁接手、带什么、拿回什么、接着运行哪条命令；按新原则，一个部署（一台机器上的一个模型服务）是一个工作项，由谁从头带到底也要定。
5. 不该等用户的地方在等用户（§1）：install.md 要求装 vLLM 前等用户点头；它是 uv 包，告诉用户即可。
6. 流程（§2）：动手前只让 advisor 审了 spec，没做三个视角的独立评审；新 agent 视角的评审是写完才做的，之后的修改正是第 1 条的来源。
7. 能写成检查的规则还写在文档里（§3）：“部署 profile 要和被继承的 profile 同名，否则要有自己的端口”可以变成脚本检查：两个 profile 用同一个端口时直接报出。
8. 一个意思写了两处（§3、§4）：SKILL.md 复述了 `--help` 里的输出字段和错误码含义；SKILL.md 和 shared-machines.md 都讲了“本次启动和 profile 的分工”。
9. 公开仓库里有个人的值（§4）：shared-machines.md 的例子和本 issue 里写着用户服务器上的真实目录（`/data/.tmp` 等），应换成占位符。
10. SKILL.md 的改动没按 §4 的流程逐条给用户看原文和修改建议。
11. 该用户定的决定由我定了（§5）：profile 的 env 优先于调用方环境、版本钉 0.32.0、删掉显存预检，都写进了 spec 当作已定。
12. 大众优化没顺手做（tuning 原则）：`VLLM_USE_FLASHINFER_SAMPLER=0` 的理由是 pip 工具包编不了采样器；有了 `vllm download-kernels` 后这个理由可能不成立了，需实测。

**已定（2026-10-31）——启动时怎么等：方案 A。** `up` 不设计时，等到服务应答或进程退出为止；进程退出时报 `server_failed`，附日志路径和末尾，不再摘“第一条错误行”；慢不慢、卡没卡、为什么失败由 agent 看日志判断（日志长就派 sonnet subagent 读），改好再 `up`。用户：「A 但是有一些必要的你还是要考虑的，不要过度防御性，你懂我意思吧。有一些基本上都会遇到的，或者本身就该考虑的，你就应该考虑进去。」

按这句话重新分第 1 条（我的分法，没拍板）：
- 留下——本身就该考虑或几乎都会遇到：访问本机服务不走代理（有代理的机器上必遇，本机就是一台）；`CUDA_DEVICE_ORDER=PCI_BUS_ID`（文档让 agent 按 `nvidia-smi` 的编号选卡，这一行让编号真的对得上）；CUDA 12 环境里同样不让系统的 CUDA 混进来（“一个环境一份 CUDA”这条既有规则的一部分，CUDA 12.9 的装法本来就在 install.md 里）；下载权重时把 hf 的进度输出给调用方（大模型经 ssh 下载必遇）。
- 删掉——防御想象出来的问题：启动前试绑端口（别的程序占着端口时 vLLM 自己会在日志里说“Address already in use”）；`idle_minutes = 0`（要长开就写个大数）；“第一条错误行”和 10 分钟计时（上一条已定）。
- 看下一个问题：`--api-key` 时的健康检查。若改用 `/health`，它自然就不用特殊处理。

**已定（2026-10-31）——就绪和归属：方案 A。** 就绪看 vLLM 的 `/health`（0.32 源码核对：不在 `--api-key` 保护的 `/v1`、`/v2`、`/inference`、`/cohere` 之内；引擎正常 200、死了 503；加载期间端口不应答）；归属看自己的状态文件（守护进程活着就是我们的）；端口上有应答却没有我们活着的状态 → `port_busy`，说明可能是手动起的服务或另一个用同一端口的 profile。删掉核对模型名和带密钥。行为变化：手动起在 profile 端口上的服务不再拿来共用。用户：「A」。

**一个部署由谁带到底：不另设机制（2026-10-31）。** 用户：「我一般用这些 skills 都是主动用的嘛，而且都是交给 Agent 去操作的……根据我们的 skills，去部署远程服务器上的一个 VLLM」。

**返工 spec（2026-10-31，预览稿）：** [20261031-vllm-serve-principles-rework-spec.md](../specs/20261031-vllm-serve-principles-rework-spec.md)。实现前做了两份独立评审（低级错误和技术正确性 14 条、原则和设计 15 条），处理见该 spec 第 6 节；最重的一处——“谁在跑、归谁”撑不住不计时的等待——从根上重切成“一次启动整个交给守护进程，活着看它拿着的运行锁”。

已核实、不再是问题：删掉显存预检所依据的事实（vLLM 本机实测 50 s 内报 “Free memory on device …” 并退出；0.32 默认比例 0.92 在主机 B 的 `--help` 里核对过）。

## 条目一览

| # | 问题 | 落到哪里 |
|---|---|---|
| 1 | 显存检查只看第一张卡 | serve.py |
| 2 | 两个启动期限太短；权重盘慢时加载很慢 | serve.py、install.md |
| 3 | CUDA 构建要按驱动选；Blackwell 上没有 FA3 | install.md |
| 4 | 所有文件都要放进用户指定的目录 | serve.py、SKILL.md |
| 5 | 只监听 127.0.0.1，局域网的客户端连不上 | serve.py |
| 6 | 选卡、和别人共用 GPU、数据并行还是张量并行 | serve.py、调优参考 |
| 7 | 混合模型单卡启动失败（`max_num_seqs` 超过 Mamba 缓存块数） | profile、调优参考 |
| 8 | 并发太高时 KV cache 占满，吞吐反而下降 | 调优参考 |
| 9 | 显存估算：每张卡要多大、能跑几个会话 | 调优参考 |
| 10 | 权重下载不认 revision；下载 CDN 不通；没有校验 | serve.py、install.md |
| 11 | uv 环境不能搬；PyPI 很慢时怎么办 | install.md |
| 12 | FlashInfer 预编译 kernel 缺失，首次启动要现编 | install.md |
| 13 | MTP 投机解码：菜谱里的版本说明已过时 | 调优参考、profile |
| 14 | `status` 看不到负载和速度 | serve.py |
| 15 | 调用方不传采样参数时用的是什么 | 调优参考 |
| 16 | 新增 profile：qwen38-27b | profiles/ |
| 17 | 共享服务器不给 root：只能用个人用户部署和管理 | serve.py、SKILL.md、install.md |

## 1. 显存检查只看第一张卡

- 来源：使用中发现 · 2026-10-29；10-30 补充
- 现场：主机 A 上 profile 的 `env` 设了 `CUDA_VISIBLE_DEVICES = "4,5"`；`check_gpu()` 取 `nvidia-smi --query-gpu=...` 输出的第一行，也就是 GPU 0（别人的训练占着 131 GB），误报 `gpu_busy`。主机 B 上两张卡都有别人的进程，张量并行 2：两张卡都要放得下各自那一份，`gpu_memory_utilization` 是按每张卡的总显存算的，所以由剩余显存最少的那张卡决定。
- 为什么：`nvidia-smi` 不认 `CUDA_VISIBLE_DEVICES`，函数也不读 profile 的 env。
- 方向：从 profile 读要用的卡（`env` 里的 `CUDA_VISIBLE_DEVICES`，或新增 `gpus` 键），传给 `nvidia-smi -i`，逐张检查，`gpu_busy` 的 `detail` 列出每张卡的情况。
- 补救：PATH 最前放一个 `nvidia-smi` 包装，固定加 `-i <卡号>`（参考目录 `nvidia-smi`、`serve.sh`）。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 2. 两个启动期限对大模型太短；权重盘慢时加载很慢

- 来源：使用中发现 · 2026-10-29；10-30 补充
- 现场：主机 A 的权重放在 99% 满的 btrfs 数据盘上，两个数据并行 rank 用 mmap 读 18 个分片花了 397–459 s（页缓存已预热时 405 s），再加约 80 s 的 torch.compile 和 CUDA graph。先是 `up` 的 `STARTUP_TIMEOUT = 300` 到期，把加载了一半的服务停掉；放宽后又撞上 vLLM 自己的 `VLLM_ENGINE_READY_TIMEOUT_S`（默认 600 s），API server 报 `TimeoutError: Timed out waiting for engine core processes to start`。主机 B（ext4）冷启动约 6 分钟：读权重 88–105 s、编译 20–30 s、CUDA graph 78 s，另外还有 FlashInfer 的现编和自动调优（第 12 条）。
- 为什么：`STARTUP_TIMEOUT` 写死在代码里；vLLM 的期限只能从环境变量放宽，SKILL.md 没提。mmap 加载在又慢又满的盘上是大量随机读。
- 方向：profile 增加 `startup_timeout` 键（默认 300），超过 600 s 时一并设 `VLLM_ENGINE_READY_TIMEOUT_S`；install.md 的“A server that does not start”补上这两个期限，以及盘慢时加 `--safetensors-load-strategy eager`（把每个分片顺序读进内存，只改读法、不改计算）。
- 补救：`serve_startup.py` 加载 serve.py 后改大 `STARTUP_TIMEOUT`（这个期限只在 `up` 里读，supervisor 仍是原文件）；profile 的 env 设 `VLLM_ENGINE_READY_TIMEOUT_S = "1800"`；profile 的 args 加 `--safetensors-load-strategy eager`。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 3. CUDA 构建要按驱动选；Blackwell 上没有 FA3

- 来源：使用中发现 · 2026-10-29；10-30 补充
- 现场 A（驱动 CUDA 12.9）：按 install.md 的写法 `uv tool install "vllm==0.32.0" --torch-backend cu129`，PyTorch 是 `2.13.0+cu129`，vLLM 本身却是 PyPI 上默认的 CUDA 13.0 构建，worker 启动报 `cudaHostGetDevicePointer failed: CUDA driver version is insufficient for CUDA runtime version`。环境里还多出一个 `nvidia/cu13`（nvcc 13），`own_cuda()` 会把 `CUDA_HOME` 指向它。
- 现场 B（驱动 CUDA 13.2，RTX PRO 6000 = sm_120）：install.md 现有的装法直接可用：`uv tool install "vllm==0.32.0" --torch-backend cu130 --with "cuda-toolkit[nvcc,nvvm,crt,cccl,nvjitlink]==13.0.3"`（7.8 GB，PyPI 约 24 MB/s 时约 10 分钟）。torch 的架构列表包含 sm_90、sm_100、sm_120；vLLM 自带的 FlashAttention 在 sm_120 上只有 FA2，FA3 只支持 Hopper（主机 A 用的是 FA3）。
- 为什么：`--torch-backend` 只决定 torch 系列包从哪个索引装；vLLM 0.32.0 的 CUDA 12.9 wheel 只在 GitHub release 的附件里（`vllm-0.32.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl`），不在 PyPI。
- 方向：install.md 写一张“驱动的 CUDA 版本 → 装法”表：13.x 用现有命令；12.9 用 `uv tool install "vllm @ <+cu129 wheel 的本地路径或 URL>" --torch-backend cu129`（这样装出一致的 12.9 栈：`cuda-toolkit==12.9.1`、`nvidia-cuda-nvcc-cu12`）。`own_cuda()` 目前只认 `nvidia/cu[0-9]*` 布局，cu12 的包放在 `nvidia/cuda_nvcc/`，要一并支持或写明。再加一句：显卡架构决定能用哪些注意力内核（FA3 只在 Hopper 上）。
- 补救：12.9 的 wheel 存在部署目录的 `wheels/` 下，从它安装。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 4. 所有文件都要放进用户指定的目录

- 来源：用户要求 · 2026-10-29、10-30
- 现场：共享服务器上只能写用户自己的目录，而且三台机器各不相同。主机 A：「以后h200上，就都放在这个路径下 /data/.tmp/，包括你现在的也迁移过去，这个目录是我自己用的」（根盘 97% 满）。主机 B：「所有东西都放在/home/.tmp下」。另一台：「……的存放位置就放在 /root/.tmp 下，记一下」，root 关闭后个人用户进不了 `/root`，改为「你先记一下……用/data/.tmp」（第 17 条）。serve.py 和它带起来的 uv、HF、vLLM、Triton、FlashInfer 默认写 `~/.cache`、`~/.local/state`、`~/.config`、`~/.local/share/uv`。共享服务器上的路径和文件里也不能出现个人名字。
- 为什么：skill 只有 XDG 变量这一个入口，而 uv、HF、vLLM、Triton 各自还有自己的变量。
- 方向：一个环境变量（例如 `VLLM_SERVE_ROOT`），serve.py 和 install.md 从它推出全部路径：`UV_TOOL_DIR`、`UV_TOOL_BIN_DIR`、`UV_CACHE_DIR`、`UV_PYTHON_INSTALL_DIR`、`HF_HOME`、`XDG_CACHE_HOME`、`XDG_STATE_HOME`、`XDG_CONFIG_HOME`、`VLLM_CACHE_ROOT`、`TRITON_CACHE_DIR`。SKILL.md 加一节“在共享或远程机器上”：把 skill 复制到目标机的根目录下，设好根目录，在目标机上运行（不需要 skill 自己去 ssh）；用之前先和用户确认路径。
- 补救：`env.sh` 导出上面这些变量，路径都从脚本所在目录推出；`serve.sh` 先 source 它；skill 复制到 `<root>/skill/`。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 5. 只监听 127.0.0.1，局域网的客户端连不上

- 来源：使用中发现 · 2026-10-29
- 现场：客户端在另一台机器上。先用 `ssh -L` 隧道；用户：「另外通过ip访问是可以访问到的，可以不用ssh隧道」「我说过可以直接用内网ip直接访问」。
- 为什么：serve.py 固定加 `--host 127.0.0.1`；`up` 报出的 url 也是 127.0.0.1，不是客户端真正要用的地址。
- 方向：profile 增加 `host` 键（默认 127.0.0.1）；`up` 报出客户端能用的 url；SKILL.md 提醒监听到局域网等于对内网开放，并写明 vLLM 0.32 默认不记录请求内容（除非加 `--enable-log-requests`），崩溃转储里只有请求 id 和长度（2026-10-29 的一次崩溃时核对过）。
- 补救：profile 的 args 末尾加 `--host 0.0.0.0`，排在 serve.py 自己那个之后，按 argparse 后者覆盖前者；serve.py 的健康检查仍走回环地址。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 6. 选卡、和别人共用 GPU、数据并行还是张量并行

- 来源：使用中发现与用户要求 · 2026-10-29、10-30
- 现场 A：卡会被别人拿走又放回。GPU 4、5 被别人的训练占了几个小时；有一次刚在 GPU 0–3 上启动，十几秒后另一个用户的任务就在这几张卡上重新起来了（同一个任务两次运行之间，卡会短暂显得空闲）。用户的规则：「如果有任何一张空出来，都可以用」「别人利用率不高的，我们也可以用」「然后显存也能放得下的那种」。
- 现场 B：两张卡都被别人的训练占着（利用率 97–100%，已用 22–33 GB）。用户：「就直接用两张卡吧，竞争」，于是用张量并行 2、每卡 0.60；后来：「卡1空出来了，只用卡1，腾出卡0，不要竞争了」。两卡和别人抢算力时的实测：总生成 200–330 token/s，每个会话 7.5–13 token/s；主机 A 上 12 个会话时总共约 600 token/s，每个会话约 50 token/s。
- 为什么：profile 把卡号、并行数和显存比例写死；`up` 碰到已在运行的服务时直接返回“在跑”，即使 profile 文件已经改过，也不提示。
- 方向：
  - `up <profile> --gpus <卡号列表|auto>`（或 profile 写默认值），选卡策略写进文档：空闲卡（多次采样都低于 1 GiB）；低利用率、显存放得下的共用卡；采样要隔一段时间看几次。
  - 并行方式：单卡放得下一份模型时用数据并行（每卡一份，不需要卡间通信）；放不下才用张量并行。张量并行数必须能整除注意力头数和线性注意力的 key 头数（Qwen3.8-27B：24 个注意力头、4 个 KV 头、16 个线性 key 头、48 个线性 value 头，所以可以是 2、4、8，不能是 3）。
  - 共用卡上的显存比例按剩余显存算，多卡时取最小值。
  - `up` 时如果正在运行的服务和 profile 文件不一致（记录启动时的 profile 哈希），返回 `profile_changed`。
- 补救：`up_on_free_gpus.sh` 从本机经 ssh 采样 3 次、每次隔 60 s：空闲卡给 0.88；共用卡的条件是利用率低于 30% 且剩余显存不少于 80 GiB，比例取（剩余 − 6 GiB）/ 总量；最多 4 张，数据并行；然后用 sed 改写 profile 的 GPU 列表、并行数和显存比例，再 `up`。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 7. 混合模型单卡启动失败：`max_num_seqs` 超过 Mamba 缓存块数

- 来源：使用中发现 · 2026-10-30
- 现场：主机 B 只用 GPU 1，比例 0.92，KV cache 32.56 GiB（522,750 token）。启动报 `ValueError: max_num_seqs (1024) exceeds available Mamba cache blocks (680). Each decode sequence requires one Mamba cache block, so CUDA graph capture cannot proceed. Please lower max_num_seqs`。开了前缀缓存时，vLLM 把 Mamba 缓存模式设为 `align`，并把注意力块调成 784 token，让两种页的大小相等。主机 A（每卡 108 万 token）和主机 B 两卡（92 万 token）都没碰到这个问题。日志片段在参考目录 `pro6000-1gpu-max-num-seqs-failure.log`。
- 为什么：vLLM 0.32 默认 `max_num_seqs` 是 1024，混合模型每个解码序列要占一个 Mamba 缓存块，显存小的卡块数不够。
- 方向：混合模型的 profile 显式设 `--max-num-seqs`（也正好用来控制并发，见第 8 条）；调优参考写明上限大约是 KV token 数 ÷ 块大小；serve.py 遇到这个报错时给出提示。
- 补救：profile 加 `--max-num-seqs 16` 后正常启动（2026-10-30 03:15、03:40），KV cache 548,888–570,413 token；调用方控制在约 12 个会话在途。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 8. 并发太高时 KV cache 占满，吞吐反而下降

- 来源：使用中发现 · 2026-10-30
- 现场：主机 B 两卡张量并行、每卡 0.60，KV cache 共 924k token。
  - 40 个会话同时开始：前 4 分钟几乎都在 prefill（1–2k token/s），之后总生成 270–330 token/s。
  - 跑到一半时有 32 个会话：KV 占用 95–100%，生成速度在 9–300 token/s 之间来回跳，平均约 110。抢占只有 3 次，主要损失来自前缀缓存被挤掉：每个新轮次都要把三五万 token 的上下文重新 prefill。
  - 减到 16 个会话：KV 约 51%，稳定在 200–210 token/s。
  - 主机 A 对照：28 个会话、两卡共 216 万 token，KV 38%，没有排队。
- 为什么：多轮 agent 会话的每个新轮次都依赖上一轮留下的前缀缓存；KV 一满，这些缓存先被挤掉，每轮都要整段重算。所以这类负载需要的余量比单次请求大得多。
- 方向：调优参考写明怎么定并发：让 KV 峰值保持在约 70% 以下，会话数 ≈ 0.7 × KV token 数 ÷ 每个会话实际占用的 token 数（这里 2.5–3.5 万，所有会话共享同一段系统提示，前缀命中约 50%）；用 `--max-num-seqs` 设上限；要看的指标是 `vllm:kv_cache_usage_perc`、`vllm:num_requests_waiting`、`vllm:num_preemptions_total`，以及日志里的 `Avg generation throughput` 行。
- 补救：调用方减少在途会话数（每臂 8 → 只留两臂）。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 9. 显存估算：每张卡要多大、能跑几个会话

- 来源：用户提问 · 2026-10-30（「最少显存需要多少」「单张显卡显存要多少，两张要多少（单张），拿5090 pro6000 h20 h200举例」「5090要至少几张」）
- 实测（Qwen3.8-27B，BF16，vLLM 0.32）：
  - 权重 50.1 GiB；张量并行 2 时每卡 25.15 GiB。
  - 运行开销：单卡约 6 GiB，张量并行 2 时每卡约 3.5 GiB（其中 CUDA graph 约 0.6 GiB）。
  - KV 每个 token 约 65 KiB（全模型；混合模型的 Mamba 页已算在里面）。
  - 启动时要求 KV 至少放得下一条 `max_model_len` 的上下文。
  - 菜谱写的 `vram_minimum_gb: 67`（权重 × 1.2）不够放 262k 上下文。
- agent 负载的上下文（495 次派发的统计）：一类任务中位数 3.8–4.6 万、95% 分位 5.4–5.9 万、最长 7.4 万；另一类中位数 8.9 万、95% 分位 12.4 万、最长 16.3 万。每轮还要加 3.2 万的输出，所以 `max_model_len` 前者 128k 够用，后者要 200k 以上。
- 每张卡至少要的显存（vLLM 最多用 92%）：

  | 场景 | 单卡 | 两卡（每张） |
  |---|---|---|
  | 1 个会话，上限 128k | ≈ 75 GB | ≈ 38 GB |
  | 1 个会话，上限 262k | ≈ 84 GB | ≈ 43 GB |
  | 8 个会话 | ≈ 80–84 GB | ≈ 41–43 GB |
  | 40 个会话 | ≈ 138 GB | ≈ 70 GB |

- 对应到显卡：RTX 5090（32 GB）至少要 4 张张量并行，2 张放不下，3 张切不开（第 6 条）；RTX PRO 6000 和 H20（96 GB）单卡约 20 个会话；H200（141 GB）单卡约 40 个会话。生成速度主要看显存带宽：PRO 6000 和 5090 约 1.8 TB/s，H20 约 4.0 TB/s，H200 约 4.8 TB/s。
- 方向：调优参考加一节“容量估算”：公式、怎么从启动日志读出这几个数（`Model loading took`、`Available KV cache memory`、`GPU KV cache size`、`Maximum concurrency`），以及如何按调用方的上下文长度定 `max_model_len`。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 10. 权重下载不认 revision；下载 CDN 不通；没有校验

- 来源：使用中发现 · 2026-10-29、10-30
- 现场：
  - 主机 A 连得上 huggingface.co，但连不上它的下载 CDN，`hf download` 一直停在 0 字节。改为把另一台机器 HF 缓存里的同一 revision 经本机用 `tar -ch` 流式拷过去（55.6 GB，约 10 分钟），按 HF 缓存布局（`snapshots/<revision>/` 加 `refs/main`）放好，让 vLLM 离线加载，再对 19 个 LFS 文件逐个核对 HF API 给出的 sha256。
  - 主机 B 直连 HF（带 hf_xet）约 34 MB/s。
- 为什么：`ensure_weights()` 执行 `hf download <model>`，不带 revision；`hub_cached()` 只要有任何一个 snapshot 就当作已缓存。profile 在 args 里用 `--revision` 固定版本时，预下载拿的是 main（可能是别的版本），而固定的那个版本可能从没被下载或核对过。
- 方向：profile 增加 `revision` 键，下载和 vLLM 都用它；可选一份 sha256 清单，下载后校验；install.md 写明下载 CDN 不通时的做法（从别的机器拷过来，按缓存布局放好）。
- 补救：权重在 `up` 之前手动下载或拷入，并校验。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 11. uv 环境不能搬；PyPI 很慢时怎么办

- 来源：使用中发现 · 2026-10-29
- 现场：主机 A 到 PyPI 约 1 MB/s，于是在另一台机器上用完全相同的绝对路径建好 uv 工具环境，再拷过去。之后要换根目录时，这个环境搬不动：脚本和 `pyvenv.cfg` 里都是绝对路径，只能在新路径下重建。用户：「uv环境直接重建不是更快吗」「而且移动不一定可用」「uv默认使用也都是有缓存的」。另外，在装了 miniconda 的机器上构建，环境会链到 miniconda 的 Python，要加 `UV_PYTHON_PREFERENCE=only-managed`。主机 B 上直接在原地装，约 10 分钟。
- 方向：install.md 写明：始终在最终的根目录下原地构建；目标机 PyPI 慢时，先预热根目录下的 uv 缓存，而不是拷整个环境；强制使用 uv 自己管理的 Python。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 12. FlashInfer 预编译 kernel 缺失，首次启动要现编

- 来源：使用中发现 · 2026-10-30
- 现场：主机 B 的启动日志：`FlashInfer's precompiled kernels are missing or do not match flashinfer-python 0.7.0.post1 (flashinfer-cubin not installed, flashinfer-jit-cache not installed). FlashInfer then downloads and compiles kernels at startup`，之后还有一段 `[Autotuner]`。首次启动因此变慢；编译结果留在根目录下的缓存里。
- 方向：install.md 的安装命令考虑加上与 flashinfer 同版本的 `flashinfer-cubin`（先确认该版本有发布），或至少写明首次启动的这段一次性开销。
- 状态：已落实（`vllm download-kernels`，本机实测），见 spec 第 4 节

## 13. MTP 投机解码：菜谱里的版本说明已过时

- 来源：调研 · 2026-10-30（用户：「另外，有什么优化可以做」「你去看一下vllm文档或者qwen的部署文档」）
- 现场：vllm-project/recipes 的 `models/Qwen/Qwen3.8-27B.yaml`（date_updated 2026-10-15）写着投机解码需要 gated-delta-net 的修复 vllm-project/vllm#51812 / #51674，“no released tag carries yet”。核对结果：两个 PR 分别在 2026-08-11、08-14 合并，都是 v0.32.0 tag 的祖先（`gh api repos/vllm-project/vllm/compare/v0.32.0...<sha>` 返回 `behind`，`ahead_by` 为 0）。菜谱的配置：默认 `{"method":"mtp","num_speculative_tokens":3}`，RTX PRO 6000 上用 5；短 prompt 上的接受率 92%（BF16）；这个 checkpoint 必须写明 `num_speculative_tokens`（深度只写在 `text_config` 里，省略时启动失败）。vLLM 文档：投机采样“theoretically lossless up to the precision limits of hardware numerics”，并发越高收益越小。
- 压测（2026-10-30，主机 B 的 GPU 1 单卡、0.92、`--max-num-seqs 16`；12 个并发请求，每个约 2.6 万 token 输入：共享约 1.5 万 token 前缀，加各自约 1 万 token；开思考、温度 1.0、每个输出 4000 token；文本取自 Python 标准库源码；脚本和原始结果在参考目录 `bench_decode.py`、`bench.jsonl`）：

  | 配置 | 总生成 token/s | 每个请求 token/s | 草稿接受率 | 每步接受的草稿数 |
  |---|---|---|---|---|
  | 不开投机解码 | 202 | 16.9 | — | — |
  | MTP，3 个草稿 token | 205 | 17.8 | 42% | 1.25 |
  | MTP，5 个草稿 token（菜谱给这张卡的值） | 198 | 17.9 | 31% | 1.52 |

  启动都正常（MTP 多约 30 s 的编译），没有抢占。结论：在这类负载上 MTP 没有收益，所以没开。菜谱的 92% 接受率是在短 prompt 上测的；长上下文、开思考、温度 1.0 随机采样时接受率只有 30–40%，并发 12 时多验证的 token 还要额外算力，抵消了剩下的收益。
- 方向：调优参考写两条通用做法。其一，菜谱里提到的 PR 或版本限制，先对照已安装的版本核实。其二，投机解码在真实负载上简单试一次（不开 vs 菜谱值）再决定，接受率看 `/metrics` 里的 `vllm:spec_decode_num_accepted_tokens_total` / `vllm:spec_decode_num_draft_tokens_total`；采样温度高、并发高时收益通常很小。按开头的原则，只比较不开和菜谱值两档，不扫参数。
- 状态：已落实（调优参考），见 spec 第 4 节

## 14. `status` 看不到负载和速度

- 来源：使用中发现 · 2026-10-30
- 现场：要判断速度和是否抖动，只能去翻服务日志里的 `Avg prompt throughput ... Avg generation throughput ... Running ... Waiting ... GPU KV cache usage ... Prefix cache hit rate` 行，或者自己去查 `/metrics`。用户反复问：「pro6000上的速度怎么样？」「现在是多少token/s 和h200差多少」。
- 方向：`status` 对每个在跑的服务加上：运行中和排队的请求数、KV 占用、前缀命中率、抢占次数、最近的生成速度（从 `/metrics` 读）。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 15. 调用方不传采样参数时用的是什么

- 来源：使用中发现 · 2026-10-29
- 现场：Claude Code 不传 temperature、top_p、top_k，也不传 seed，所以 vLLM 用 checkpoint 的 `generation_config.json`（Qwen3.8-27B：1.0 / 0.95 / 20）。同一输入重跑，结果不会逐字相同；vLLM 要逐字复现，得同时开 `VLLM_BATCH_INVARIANT=1` 并给每个请求固定 seed。
- 方向：调优参考或 profile 注释里写一句，免得使用者以为服务端在用自己设的采样参数。写成“调用方没传时”：Claude Code 不传，pi 这类 harness 可以逐请求设 temperature、top_p、top_k、seed。
- 状态：已落实（profile 注释、调优参考），见 spec 第 4 节

## 16. 新增 profile：qwen38-27b

- 来源：用户 · 2026-10-30：「然后profiles是不是也应该新增一个，因为我们用了qwen3.8-27B」
- 现场：该项目的两份 profile（参考目录 `qwen38-27b.h200-dp2.toml`、`qwen38-27b.pro6000-1gpu.toml`）里混着项目自己的东西：固定 revision、卡号、局域网监听、端口。通用的部分（菜谱给的参数、按显卡区分的要点）应该放进 skill 的 `profiles/`（SKILL.md 的约定：公开模型放这里），项目的部分留在项目那边。
- 草稿（主机 A 两卡数据并行、主机 B 两卡张量并行、主机 B 单卡加 `--max-num-seqs 16` 都实际跑过；单卡版用第 13 条的压测确认过）：

  ```toml
  # Qwen3.8-27B (BF16): 27B dense hybrid model, gated-delta-net linear attention on 48 of 64 layers, a built-in MTP
  # head, 262k native context.
  # Arguments: vllm-project/recipes models/Qwen/Qwen3.8-27B.yaml (date_updated 2026-10-15):
  #   --reasoning-parser qwen3 (every assistant turn opens with <think>); --enable-auto-tool-choice
  #   --tool-call-parser qwen3_coder; --language-model-only (text only: skips the vision tower, frees memory for KV);
  #   --max-model-len 262144 (native window).
  # --max-num-seqs 16: required on a 96 GB GPU, where vLLM 0.32's default 1024 exceeds the Mamba cache blocks (680 at
  #   0.92 of an RTX PRO 6000) and start-up fails; keep about 12 long multi-turn sessions in flight there (~550k-token
  #   KV cache) so their cached prefixes are not evicted. Raise it with the KV cache: ~32 on a 141 GB H200.
  # --safetensors-load-strategy eager: sequential reads; mmap took 400+ s for 52 GB on a nearly full disk.
  # Memory: 50.1 GiB weights + ~6 GiB runtime + ~65 KiB per KV token, so one GPU needs >= ~84 GB for a 262k context
  #   (RTX PRO 6000 / H20 96 GB: ~12-20 sessions; H200 141 GB: ~40). Smaller GPUs: tensor-parallel, whose size must
  #   divide the 16 linear-attention key heads (2, 4, 8): two RTX 5090s are too small, four fit.
  # Start-up: 2-7 min cold (FlashInfer JIT on the first start), hence the longer engine deadline.
  # Sampling: clients that send no temperature / top_p / top_k get generation_config.json's 1.0 / 0.95 / 20.
  # No speculative decoding: the built-in MTP head works on vLLM 0.32.0 ({"method":"mtp","num_speculative_tokens":N}),
  #   but on long thinking requests at temperature 1.0, 12 concurrent, it gave 202 -> 205 tok/s (3 drafts, 42% accepted)
  #   and 198 (5 drafts, 31%); try it where requests are short or near-greedy.
  model = "Qwen/Qwen3.8-27B"
  port = 8238
  gpu_memory_utilization = 0.92
  idle_minutes = 30
  args = ["--max-model-len", "262144", "--max-num-seqs", "16", "--reasoning-parser", "qwen3",
          "--enable-auto-tool-choice", "--tool-call-parser", "qwen3_coder", "--language-model-only",
          "--safetensors-load-strategy", "eager"]
  env = { VLLM_ENGINE_READY_TIMEOUT_S = "1800" }
  ```

- 留在项目里的部分：固定的 revision 和 sha256 清单、主机和根目录、卡号、`--host 0.0.0.0`、`--seed 0`、端口、空闲自停时间（该项目用 120 分钟）、为了实验可比性不开 FP8 KV cache。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 17. 共享服务器不给 root：只能用个人用户部署和管理

- 来源：用户要求与使用中发现 · 2026-10-30
- 现场：两台主机原先都以 root 部署。管理员关闭 root 之后（用户：「由于管理员设置，不允许使用root，所以只能使用个人用户」）：
  - 主机 B 上正在服务的 vLLM 是 root 启动的，个人用户停不了，只能等它空闲自停，或请用户用 root 停。按代码，个人用户的 `status` 会报它在跑（`alive()` 把 `PermissionError` 当作活着），`down` 则在 `os.kill(state["pid"], SIGTERM)` 上抛出没有捕获的 `PermissionError`。
  - 主机 A 系统里的 uv 是 snap 装的。用户：「另外由于我下错了uv，你需要卸载snap的版本，需要用curl -LsSf https://astral.sh/uv/install.sh | sh」。卸载 snap 要 root，由用户执行；个人用户用官方脚本把 uv 装进 `~/.local/bin`。
  - 非交互的 `ssh host cmd` 不读 shell 的 profile，PATH 里没有 `~/.local/bin`，脚本找不到 uv。
  - 部署目录和存放根目录归 root 所有，个人用户写不进去。要用户以 root 执行 `chown -R <login>:<login> <root>/<部署目录>`、`setfacl -m u:<login>:rwx <root>`；在 root 所有的路径下新建存放根目录也要 root。
  - 同一天主机 A 的登录用户又换了一次。新登录名下什么都没有，交出目录、装 uv 这两步都要重做。用户要求文档里不写用户名：「我觉得不应该记用户名，因为可能会变，但是我的ssh别名不会变」。
- 为什么：install.md 默认 uv 已经在 PATH 上；`down` 没考虑服务是别的用户启动的情况；SKILL.md 没说在共享机器上用哪个登录。
- 方向：
  - SKILL.md 的“在共享或远程机器上”一节（第 4 条）补充以下几点：
    - 用个人用户部署；哪个登录启动的服务，就由哪个登录管理。
    - 需要 root 的步骤（卸载系统包、`chown`、在 root 所有的路径下建目录）写成命令交给用户执行，执行完自己核对结果。
    - 换了登录以后，先把目录交给新登录，再重装用户空间的工具。
    - 文档和脚本里不写用户名，要用时用 `id -un` 现查。
  - install.md：uv 用官方安装脚本装进 `~/.local/bin`；脚本里显式把它加到 PATH 最前面。
  - serve.py：状态文件记下启动者（uid），`status` 显示出来；`down` 碰到别的用户启动的服务时返回 `not_owner`，说明服务属于谁、该由谁来停，不抛异常。
- 补救：项目的 `env.sh` 把 `$R/uv/bin:$HOME/.local/bin` 放到 PATH 最前面（参考目录 `env.sh`，2026-10-30 06:15 更新）；目录交接由用户以 root 执行；root 启动的那个服务等它空闲自停。
- 状态：已落实，见 spec 第 4 节；待主机实测

## 建议的落地方式

先写一份 spec，覆盖上面 17 条，按落点归成五块：serve.py（1、2、4、5、6、10、14、17）；SKILL.md 新增“在共享或远程机器上”一节（4、5、6、17）；install.md（2、3、10、11、12、17）；新增一份调优参考，例如 `references/tuning.md`（6、7、8、9、13、15）；新增 profile（16）。改完后，该项目的 `infra/vllm/` 会删掉，换成一份只写项目差异的部署文档。
