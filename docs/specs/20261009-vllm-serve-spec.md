# vllm-serve — 本机统一的 vLLM 后端（2026-10-09）

> 来源：paddleocr v2（[20261009-paddleocr-v2-spec.md](20261009-paddleocr-v2-spec.md)）的 VL 服务后端。用户决定 vLLM 单独成环境，并作为本机统一后端：「需要考虑不仅仅只有 paddleocr 的需求，以后其他组件需要也接进来，一个 vllm」。用户 2026-10-09 认可本方案（名称 `vllm-serve`、模型取自 HF、安装 vLLM），并让顺便用 hf 下好模型。

## 1. 目标

- 本机只有**一份** vLLM 安装，所有需要本地模型服务的组件（paddleocr 是第一个）都通过它。
- 每个模型怎么起（参数、环境变量、显存预算）只写在一处；组件只拿 URL，不再各自内嵌 vLLM 参数。
- 多个调用方同时要同一个模型时共用一个实例，不再各起各的（两个 parse.py 各起一个服务会撑爆显存）。
- GPU 同时用于科研训练：服务按需启动、空闲自动退出，不常驻占显存。

## 2. 依据（2026-10-09 查文档 / 实测）

| 事实 | 依据 |
| --- | --- |
| vLLM 的预编译二进制与特定 PyTorch 版本和 CUDA 构建绑定，“even for the same PyTorch version with different building configurations”；建议全新环境，否则从源码编译 | vLLM 文档 installation/gpu.cuda（2026-10-08 版） |
| Paddle 与 vLLM 不能同环境：PaddleOCR 文档要求 VLM 服务单独环境（Blackwell 页 3.1.2、主文档“判定补充说明”）；vLLM 的 PaddleOCR-VL 配方也写 “Use separate venvs for vllm and paddlepaddle”；uv 解析两者的 nvidia-* 精确钉版本无解 | 各文档；uv dry-run |
| 一个 vLLM 服务进程只服务一个模型；多模型 = 多实例 + 一层路由 | vLLM FAQ |
| PaddleOCR-VL-1.6 的官方 vLLM 配方：`vllm serve PaddlePaddle/PaddleOCR-VL-1.6 --trust-remote-code --max-num-batched-tokens 16384 --no-enable-prefix-caching --mm-processor-cache-gb 0`（OCR 用不上前缀缓存和图像复用），vLLM ≥ 0.11.1；客户端要传 `vl_rec_api_model_name` 与服务端模型名一致 | vllm-project/recipes `models/PaddlePaddle/PaddleOCR-VL-1.6.yaml` |
| 安装：`uv pip install vllm --torch-backend=auto` 按驱动选 PyTorch 的 CUDA 构建；`uv tool install` 同样支持 `--torch-backend`（uv 0.12.23） | vLLM 文档；`uv tool install --help` |
| 空闲判断：`/metrics` 的 `vllm:num_requests_running`、`vllm:num_requests_waiting`（gauge）和 `vllm:request_success_total`（counter） | vLLM 文档 usage/metrics、design/metrics |
| 本机实测（vLLM 0.28，mineru 环境，仅作参考）：WSL2 需 `VLLM_WSL2_ENABLE_PIN_MEMORY=1`、`VLLM_USE_FLASHINFER_SAMPLER=0`，且不能继承 `CUDA_MODULE_LOADING=EAGER`；PaddleOCR-VL 起服务约 50 s；225 页 2,489 s → 109 s，输出与原生等价 | 本会话实测 |

PaddleOCR Blackwell 页把“直接用推理框架启动”标为它们未验证；统一后端只能走这条路（PaddleX 的 `genai_server` 插件钉死 vllm 0.10.2，不能给别的模型共用）。依据是 vLLM 官方配方加本机实测，装好后重新验证。

## 3. 设计

### 3.1 安装：一个 uv 工具环境

```bash
uv tool install "vllm==0.31.0" --torch-backend cu130 \
  --with "cuda-toolkit[nvcc,nvvm,crt,cccl,nvjitlink]==13.0.3"     # 7.8 GB
```

本机唯一的 vLLM。用户定的原则（2026-10-09）：「从一开始安装的时候就固定版本」「在前期安装的时候，就不要引入各种不同版本的 CUDA 等编译链」——vLLM 版本、它的 CUDA 构建、CUDA 工具包的编译器组件三者一起钉死，不用 `auto`。换版本时卸载、清 `~/.cache/vllm` 和 `~/.cache/flashinfer`，按新的三项全新安装；`uv tool upgrade` 不接受 `--torch-backend`。设计时写的 `--torch-backend auto` 实测会混装 CUDA 构建，见 §7。

服务只用环境自带的 CUDA：启动器把 `CUDA_HOME`/`CUDA_PATH`/`CUDA_LIB_PATH`/`PATH`/`LD_LIBRARY_PATH` 都指向环境里的工具包，`up` 在服务就绪后扫描它的进程，报出环境外的 CUDA 库（`foreign_cuda`，应为空）。

### 3.2 Profile：每个模型一个文件

`profiles/<name>.toml`，声明式，参数取自上游配方并注明出处：

```toml
model = "PaddlePaddle/PaddleOCR-VL-1.6"       # HF id；served name 与之相同
port = 8118                                    # 固定端口，外部程序也能直接连
gpu_memory_utilization = 0.2                   # 占总显存的比例（实测后定，见 §7）
idle_minutes = 10
args = ["--trust-remote-code", "--max-model-len", "16384", "--max-num-batched-tokens", "16384",
        "--no-enable-prefix-caching", "--mm-processor-cache-gb", "0", "--trust-request-mm-kwargs"]
```

参数的来源分两层：上游配方给出通用启动方式，组件自己的调优（PaddleX 为 PaddleOCR-VL 预置的参数）原则上优先——PaddleOCR 文档提醒过，直接用 vLLM 启动会丢掉这些预置参数。实测（§7）PaddleX 的大批量和配方的 16384 吞吐无差别，于是取省显存的一边；`--max-model-len 16384` 仍取 PaddleX 的，免得小显存卡因“上下文长于 KV cache”起不来。profile 里的注释记下每项的来源和实测。

机器级的修正（WSL2 的 pinned memory、去掉 `CUDA_MODULE_LOADING`、`LD_LIBRARY_PATH` 里的系统 CUDA 工具包目录、权重已缓存时 `HF_HUB_OFFLINE=1`）由启动器统一加，不写进 profile。

### 3.3 启动器 `scripts/serve.py`（PEP 723，无依赖）

- `up <profile>`：持有该 profile 的文件锁走完整个过程——健康检查 → （需要时）启动 → 等到 `/v1/models` 就绪 → 释放。第二个调用方在锁上等，拿到的一定是已就绪的服务，不会看到启动到一半的端口再起一个。启动前：模型不在 HF 缓存里就先用 vllm 环境自带的 `hf download` 下载（不计入就绪超时，首次约 2 GB）；检查空闲显存够不够（不够报 `gpu_busy` 并列出占用进程）。然后起一个脱离终端的守护进程，就绪超时 300 s，失败带日志末尾。输出一行 JSON：`{"url", "model", "started"}`。
- 守护进程：拉起 `vllm serve`，每 30 s 读 `/metrics`；连续 `idle_minutes` 没有运行中、排队中的请求且完成数不变 → 停掉 vLLM 后退出。vLLM 自己崩了也退出并清理状态。日志、状态在 `~/.local/state/vllm-serve/`。
- `down <profile> | --all`：立即停。`status`：各 profile 是否在跑、端口、空闲多久、显存。

### 3.4 接入方：只认 URL

- **paddleocr**：parse.py 删掉自己起停 vLLM 的代码（`VLLM_ARGS`、`start_vllm`、PDEATHSIG 等）。`--backend auto`：待解析 ≥ 8 页且找得到 vllm-serve（`VLLM_SERVE` 环境变量，或同级 skill 目录：先解析 `__file__` 的软链接——`~/.claude/skills/paddleocr` 链到 `~/.agents/skills/paddleocr`——再找 `../vllm-serve/scripts/serve.py`）→ `serve.py up paddleocr-vl` 拿 URL，`vl_rec_api_model_name` 用 profile 的模型名；跑完不停，交给空闲超时。`--vl-server URL` 保留；找不到或起不来 → 原生。`npx skills add --skill paddleocr` 只装一个 skill，所以 paddleocr 的 install.md 写明“要提速，再装 vllm-serve 并按它的 install.md 装 vLLM”。
- **以后的组件**：加一个 profile（参数取自上游配方，实测通过），组件用 `up` 拿 URL 或直接连固定端口。例如 MinerU 有 http-client 后端可以连外部服务，接入时再按它的文档核对。
- **路由层**：现在不做；每个 profile 一个固定端口已够用。等有组件需要“一个端口按模型名分发”时再加（vLLM FAQ 的建议）。

### 3.5 不做

- 常驻服务 / systemd：GPU 要留给训练，按需启动 + 空闲退出更合适。
- 同一进程多模型、LoRA 热切换：vLLM 不支持前者，后者暂无需求。

## 4. 文件

```
vllm-serve/
├── SKILL.md                 何时用、up/down/status、加 profile 的规矩（英文）
├── scripts/serve.py         启动器 + 守护进程
├── profiles/paddleocr-vl.toml
├── references/install.md    uv tool 安装、WSL2 修正、排障
└── tests/test_serve.py      profile 解析、空闲判断、命令拼装（不起 GPU）
```

README 的 skill 列表加一行；paddleocr 的 SKILL.md、install.md、parse.py 和 v2 spec §3 相应改写。

## 5. 用户的决定（2026-10-09）

- 名称 `vllm-serve`。
- 模型取自 HF 的 `PaddlePaddle/PaddleOCR-VL-1.6`（以后的 profile 都会是 HF id，统一后端不依赖 PaddleX 的路径）。实测它与 PaddleX 下载的那份权重和对话模板逐字节相同。
- 安装 vLLM。

## 6. 验证

1. 单元测试。
2. 装好后：先核对 `torch.version.cuda` 与所装 vLLM 轮子的 CUDA 构建一致（vLLM 二进制只认一种 PyTorch/CUDA 组合），再看 WSL2 的修正在 0.31 上是否仍需要；`up paddleocr-vl` 冷启动时间（含首次下载）；`gpu_memory_utilization`（0.3 / 0.5）和 `max-num-batched-tokens`（16384 / 131072）对 225 页吞吐的影响，定默认值。
3. 两个 parse.py 同时跑只起一个实例；空闲超时后退出、显存回到基线；杀掉守护进程 vLLM 跟着退出。
4. paddleocr 端到端：LDM、SDEdit、issue 现场 9 份，与 0.28 时的速度和输出对比。

## 7. 实现记录（2026-10-09）

- **安装**：`--torch-backend auto`（驱动报 CUDA 13.1）装出 PyTorch / torchvision `cu132` 和 torchaudio `cu130`（torchaudio 2.11 没有 `cu132` 构建），服务一导入就报 “PyTorch and TorchAudio were compiled with different CUDA versions”——正是 vLLM 文档说的构建不兼容。改 `--torch-backend cu130 --reinstall`（vLLM 文档列出的构建之一；缓存命中，25 s），三者统一，vLLM 自带的扩展链接 `libcudart.so.13`。安装从下载到完成约 14 分钟，环境 7.8 GB；模型用 `hf download` 36 s（1.8 GB）。
- **注意力**：语言模型和视觉编码器都选 FLASH_ATTN，FlashAttention 2（FA3 只支持 Hopper）；不需要单独的 `flash-attn`、`xformers`。FlashInfer 采样器在 0.28 上的报错，根因是 FlashInfer 用 `CUDA_HOME` 的 nvcc（本机 12.8）判断版本，对 SM 12.x 要求 ≥ 12.9；0.31 检测到后自动退回 PyTorch 采样器，所以去掉了 `VLLM_USE_FLASHINFER_SAMPLER=0`。
- **pinned memory**：关掉时 0.31 也能起（退回显存做 UVA 缓冲），从必需变成性能选项，保留。
- **0.31 的新默认**：拒绝请求里的 `mm_processor_kwargs`（PaddleX 客户端按块传像素上下限）→ profile 加 `--trust-request-mm-kwargs`；客户端不传模型名时请求 `PaddleOCR-VL-1.6-0.9B`，HF id 起的服务会 404 → parse.py 总是显式传模型名（vLLM 配方也提醒过）。
- **调优**（225 页，issue 现场 9 份）：显存比例 0.5 / 0.3 / 0.2、批 token 131072 / 16384、pinned memory 开 / 关，七组都在 95–110 s，默认配置重复一次 102.7 → 96.0 s，差异在噪声内；GPU 利用率约 50%，瓶颈在客户端。取 0.2 + 16384：显存峰值（含其他程序约 4 GB）从 25.2 GB 降到 17.7 GB，KV cache 仍有 20 万 token。热启动 25–50 s；新装后的第一次启动约 2 分钟（torch.compile 和 CUDA graph 首次生成）。
- **端到端**：parse.py `auto` 从零起服务，LDM + SDEdit 45 页 55 s（含起服务 29 s）；与原生逐块相同 236/249、445/456，块标签全一致。两个 parse.py 冷启动时同时跑，只起一个服务，都走服务后端；空闲 1 分钟的临时 profile 在解析结束 70 s 后自动退出，显存回到基线。`/metrics` 指标名在 0.31 上不变。
- **孤儿进程**：对运行中的守护进程 `kill -9`，vLLM（API 进程和 EngineCore）2 s 内随之退出（`PR_SET_PDEATHSIG`），显存回到基线，`status` 显示未运行，下一次 `up` 重新起服务。
- **系统 CUDA 混进服务**（用户问“为什么 vllm 没用 Python 的 cuda”后查出）：引擎进程除了环境里的 CUDA 13，还映射了系统 `/usr/local/cuda-12.8` 的 cudart 和 cuBLAS。用 `LD_DEBUG=files` 追到两处，都在 FlashInfer：导入时按 `CUDA_LIB_PATH`（默认 `/usr/local/cuda/targets/x86_64-linux/lib/`）预加载 `libcudart.so.12`；autotuner 按不带版本号的 `libcublas.so` 加载，pip 工具包只有带版本号的文件，于是系统加载缓存（`/etc/ld.so.conf.d/cuda-12-8.conf`）给了 12.8。另有 FlashInfer 用 `CUDA_HOME`（`~/.bashrc` 设为 12.8）的 nvcc 判断能否编译。修法在启动器里：`CUDA_HOME`/`CUDA_PATH`/`CUDA_LIB_PATH` 指向环境的 `nvidia/cu13`，它的 `bin` 和环境的 `bin`（有 `ninja`）放到 `PATH` 前面，`LD_LIBRARY_PATH` 前面放一个不带版本号名字的链接目录（`~/.local/state/vllm-serve/cuda-links/`）。之后两个进程都 0 个系统 CUDA 映射。
- **工具链不一致**：`CUDA_HOME` 指向环境后，FlashInfer 开始现场编译采样器，暴露出环境里 CUDA 13 拼凑：运行库 13.0（PyTorch cu130 经 `cuda-toolkit==13.0.3` 钉死），nvcc/nvvm/crt 13.4（别的依赖不钉版本拉来的），CCCL 的“编译器与头文件版本一致”检查直接报错。加 `cuda-toolkit[nvcc,nvvm,crt,cccl,nvjitlink]==13.0.3` 统一到 13.0；vLLM 0.31.0 发布说明列出的构建只有 CUDA 13.0（默认）和 12.9，torchaudio 2.11.0 也没有 cu132，所以 13.0 就是这版的上限。用户让删掉环境从零重装（钉版本，7 s，全部来自缓存），并清掉 `~/.cache/vllm`、`~/.cache/flashinfer`（里面有 13.4 nvcc 编译失败的半成品）。
- **FlashInfer 采样器默认关**：工具链统一后编译通过，链接失败（pip 工具包不是开发工具包：没有 `lib64`、`libcudart.so`、`stubs/libcuda.so`）。用户问 FlashInfer 有没有预编译版：有，`flashinfer-cubin`（全架构 1.5 GB）和 `flashinfer-jit-cache`（cu130，外壳包连带所有架构约 1.2 GB，其中 RTX 50 的 sm120f 178 MB）。PaddleOCR 是贪心解码，用不上 FlashInfer 采样器，所以启动器默认 `VLLM_USE_FLASHINFER_SAMPLER=0`；需要它的 profile 在 `env` 里打开并装预编译包。关掉后 225 页 98.7 s，与之前相同，显存峰值 18.4 GB。
