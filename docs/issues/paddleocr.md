# paddleocr

> 2026-10-06 记录。在一个临时工作目录的 Claude Code 会话里，把 PaddleOCR-VL 1.6 装成了 uv tool 并调通；下一步是在本仓库新建一个 skill，让所有 Agent 都能调用它。skill 名暂用 `paddleocr`，正式名称待定。
>
> 去向（2026-10-06）：名称定为 `paddleocr`，MinerU 暂不纳入；设计见 `docs/specs/20261006-paddleocr-spec.md`，实现在 `paddleocr/`。第 9 节里 skill 名称与范围、个人信息不进 SKILL.md、PDF 输入测试、分开计时这几项已在 spec 里处理；`.pth` 方案没有采用（脚本在进程内设置 EAGER）；`~/.claude/CLAUDE.md` 那一行不再需要；miniconda 解释器的风险仍然待办。

## 1. 需求

用户原话：

- 「然后我别的Agent如果要使用paddleocr的话，应该怎么去调用？」
- 「我可以在这个仓库里面新建一个 skills，这样的话所有的 Agent 都能用了。这个是我自己维护的skills。」
- 使用场景：「如果我只是解析文档呢？就是把图片或者 PDF 转化成结构化」

目标：任何 harness（Claude Code、Codex、Hermes…）里的 Agent 都能用本机的 PaddleOCR-VL，把图片或 PDF 解析成结构化结果（Markdown / JSON / DOCX），并且不会再碰到第 4 节的卡死问题。

## 2. 本机现状（2026-10-06）

| 项 | 值 |
| --- | --- |
| 系统 | WSL2，内核 `6.6.87.2-microsoft-standard-WSL2` |
| GPU | NVIDIA GeForce RTX 5090 D，32 GB，算力 12.0（sm_120，Blackwell） |
| 驱动 | 591.86，支持 CUDA 13.1 |
| uv | 0.12.23 |
| 工具环境 | `$(uv tool dir)/paddleocr/`，占用 8.2 GB |
| 命令入口 | `~/.local/bin/paddleocr`，只装了这一个可执行文件 |
| 解释器 | Python 3.12.9。uv 选中的是 `~/miniconda3/bin/python3.12`（见 `pyvenv.cfg` 里的 `home`），不是 uv 自己管理的 Python |
| 关键包 | paddleocr 3.7.0、paddlex 3.7.2、paddlepaddle-gpu 3.2.1（cu129）、python-docx 1.2.0、numpy 2.3.5、protobuf 7.36.2、`nvidia-*-cu12` 12.9.x、cuDNN 9.9.0.52 |
| 模型缓存 | `~/.paddlex/official_models/PP-DocLayoutV3`（126 MB）、`~/.paddlex/official_models/PaddleOCR-VL-1.6`（1.8 GB），第一次运行时自动下载 |
| 系统 CUDA | `/usr/local/cuda-12.8`，`~/.bashrc` 第 109 行把它加进了 `LD_LIBRARY_PATH` |
| 同机其他工具 | mineru 4.0.10（`uv tool install 'mineru[full]'`，独立环境，自带 vLLM 0.28.0 和 torch 2.13.0（CUDA 13）），同一天安装，还没测过 |

## 3. 安装过程

### 3.1 用户给的原始命令

```bash
uv tool install --python 3.12 \
  --with paddlepaddle \
  --with python-docx \
  'paddleocr[doc-parser]
```

用户要求：「由于我们是uv tool的形式安装，安装前和我确认才能行动。」

原命令有两个问题：

1. `paddlepaddle` 是 **CPU 版**。Blackwell 文档要求装 `paddlepaddle-gpu`，从 cu129 源下载。用 CPU 跑 VL 模型会非常慢。
2. 末尾的 `'paddleocr[doc-parser]` 少了右引号。

### 3.2 文档要求

出自 [PaddleOCR-VL NVIDIA Blackwell 文档](https://www.paddleocr.ai/latest/version3.x/pipeline_usage/PaddleOCR-VL-NVIDIA-Blackwell.html) 1.2 节：

- 驱动需支持 CUDA 12.9 或更高；Python 3.9–3.13。
- `python -m pip install paddlepaddle-gpu==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/`
- `python -m pip install -U "paddleocr[doc-parser]"`
- 原文要求：「请安装 3.2.1 及以上版本的飞桨框架」。

[PaddleOCR-VL 通用文档](https://www.paddleocr.ai/latest/version3.x/pipeline_usage/PaddleOCR-VL.html) 写的也是 3.2.1（普通 GPU 用 cu126 源），默认流水线版本是 `v1.6`。

### 3.3 版本选择

cu129 源上 cp312 / linux_x86_64 可用的版本有 3.2.1、3.2.2、3.3.0、3.3.1、3.4.0。3.2.1 和 3.4.0 都试解析过，均能通过。用户的决定是「安装 GPU 的版本就是他文档上推荐的」，因此装 **3.2.1**。

### 3.4 源的写法：为什么用 `--find-links`，而不是 `--index`

用户要求「它的源是要那个源，那我们的命令要做对应修改」。直接改成 `--index https://www.paddlepaddle.org.cn/packages/stable/cu129/` 时，试解析失败：

```
error: No solution found when resolving dependencies
  cause: Because there are no versions of paddleocr[doc-parser] and you require paddleocr[doc-parser], we can conclude that your requirements are unsatisfiable.
```

原因有两点：

- 这个源只托管 54 个包，除了 paddlepaddle-gpu，还有 numpy、pillow、protobuf、scipy、httpx、triton、`nvidia-*-cu12` 等。
- 请求它**没有**的包时（实测 `paddleocr/` 和一个随便编的包名），它返回 **HTTP 200 加空页面**，而不是 404。

uv 默认的 `first-index` 策略是「在第一个有这个包的源停下，只用这个源上的版本」（见 [uv 文档：Searching across multiple indexes](https://docs.astral.sh/uv/concepts/indexes/)）。于是 uv 认为 paddleocr 在 Paddle 源上「存在但一个版本都没有」，也就不会再去 PyPI 找。

改用 `--find-links` 指向 `…/cu129/paddlepaddle-gpu/`，就只有 paddlepaddle-gpu 从 Paddle 源下载，其余依赖照常走 PyPI。效果和文档里分两步执行 pip 一样。另一种可行写法是直接写 wheel 的 URL，`paddlepaddle-gpu @ https://paddle-whl.cdn.bcebos.com/stable/cu129/paddlepaddle-gpu/paddlepaddle_gpu-3.2.1-cp312-cp312-linux_x86_64.whl`，两种写法的解析结果完全相同（115 个包）。

### 3.5 最终命令

先只做解析、不安装，确认依赖能解开：

```bash
printf 'paddleocr[doc-parser]\npython-docx\npaddlepaddle-gpu==3.2.1\n' > reqs.txt
uv pip compile reqs.txt --python 3.12 --python-platform x86_64-unknown-linux-gnu \
  --find-links https://www.paddlepaddle.org.cn/packages/stable/cu129/paddlepaddle-gpu/
```

安装：

```bash
uv tool install --python 3.12 \
  --find-links https://www.paddlepaddle.org.cn/packages/stable/cu129/paddlepaddle-gpu/ \
  --with paddlepaddle-gpu==3.2.1 \
  --with python-docx \
  'paddleocr[doc-parser]'
```

- 用时超过 10 分钟，主要花在下载 Paddle GPU wheel 和 CUDA 库上。
- 安装后会建一个独立的虚拟环境，和 mineru 等其他 uv tool 互不影响。由于 uv 缓存和工具目录在不同文件系统上，没法建硬链接，文件都是完整复制。
- `uv-receipt.toml` 记下了 `find-links` 和 `--with` 参数，所以 `uv tool upgrade paddleocr` 会沿用它们。paddlepaddle-gpu 固定在 `==3.2.1`，升级时不会变。
- 卸载用 `uv tool uninstall paddleocr`，会删掉整个环境。
- paddleocr 3.7.0 还有一个 `doc2md` extra（含 python-docx、python-pptx、openpyxl、pylatexenc）。这次是用 `--with python-docx` 单独装的，`doc_parser` 照样输出了 `.docx`。

### 3.6 基础验证

- `paddleocr --version` 输出 `paddleocr 3.7.0`。
- `paddle.utils.run_check()` 输出 `PaddlePaddle works well on 1 GPU.`。另外，`paddle.version.cuda()` 为 12.9，`cudnn` 为 9.9.0，`is_compiled_with_cuda()` 为 True。

## 4. 问题：WSL2 下 VL 推理卡死（已解决：`CUDA_MODULE_LOADING=EAGER`）

### 4.1 现象

用官方示例图（`https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png`）执行 `paddleocr doc_parser -i <图> --save_path <目录>`：

- 版面检测完成，VL 模型也加载到了 GPU 上（显存从 3 GB 涨到约 11.6 GB）。
- 之后进程一直不结束：CPU 单核占用约 92–98%，GPU 利用率 1–2%，没有任何输出。
- 两次分别跑了约 9 分钟和约 7 分钟，都是手动终止的。

### 4.2 排查

`py-spy dump --native` 显示 VL 工作线程（`_worker_vlm`）卡在第一个 GPU 计算上：

```
cuLibraryGetModule (libcuda.so.1.1)
cudaLaunchKernel (libcudart.so…)
phi::EmbeddingKernel<phi::dtype::bfloat16, phi::GPUContext> (libphi_gpu.so)
embedding (paddle/nn/functional/input.py:336)
forward (paddlex/inference/models/doc_vlm/modeling/paddleocr_vl/_paddleocr_vl.py:668)
greedy_search (paddlex/inference/models/common/transformers/generation/utils.py:1284)
```

用 `py-spy record` 采样 20 秒，共 399 个样本，**全部**落在这次 `cudaLaunchKernel → cuLibraryGetModule` 调用里。也就是说，它是在一次 kernel 启动里空转，不是在慢慢推进。

已排除的原因：

| 假设 | 验证方法 | 结论 |
| --- | --- | --- |
| 系统 CUDA 12.8 运行时和 cu129 编译的包不匹配 | 默认环境加载的是 `/usr/local/cuda-12.8/.../libcudart.so.12.8.90`；改成 `LD_LIBRARY_PATH=/usr/lib/wsl/lib` 后，加载的是环境自带的 12.9 `libcudart.so.12` | 两种情况都卡死，**不是原因**（会话中曾误判为这个原因，后来更正了） |
| 缺少 sm_120 机器码，驱动在现场 JIT 编译 PTX | `cuobjdump --list-elf/--list-ptx`：`libphi_gpu.so`（666 MB）有 550 个 sm_120 cubin，`libphi_core.so`（798 MB）有 319 个，**两者都不含 PTX**；`~/.nv/ComputeCache` 一直是 3.3 MB，没有增长 | 不是原因 |
| embedding 算子本身有问题 | 用工具环境的 Python 写最小复现：bf16 embedding（103424×1024，和 VL 模型的词表一致）0.01 s，fp32 embedding 0.02 s，bf16 matmul 0.14 s；在子线程里跑 bf16 embedding 0.02 s。这几个测试跑的时候，卡死的流水线还占着 GPU | 不是原因，问题只出现在完整流水线里 |

### 4.3 修复与对照

每次运行都是处理一张示例图，用时包含加载模型；第一次跑通时还额外下载了可视化用的字体 `PingFang-SC-Regular.ttf`。

| 设置 | 结果 |
| --- | --- |
| 默认（CUDA 12.3 起默认就是延迟加载 GPU 模块） | 卡死 |
| 只设 `LD_LIBRARY_PATH=/usr/lib/wsl/lib` | 卡死 |
| `CUDA_MODULE_LOADING=EAGER`，同时 `LD_LIBRARY_PATH=/usr/lib/wsl/lib` | 跑通，36.9 s |
| **只设 `CUDA_MODULE_LOADING=EAGER`**，`LD_LIBRARY_PATH` 用默认值 | 跑通，33.4 s |
| 通过 `~/.bashrc` 函数调用（第 6 节），在新开的交互式 shell 里 | 跑通，32.5 s |
| 在 Python 进程里、`import paddle` 之前设 `os.environ["CUDA_MODULE_LOADING"] = "EAGER"`，再用 `runpy` 启动 `paddleocr` 入口，外部不设任何环境变量 | 跑通，31.6 s |

**结论**：必须设 `CUDA_MODULE_LOADING=EAGER`，而且只要这一个设置就够了。在进程内设置也有效，前提是在 CUDA 初始化之前，也就是 import paddle 之前。

### 4.4 原因推测（未证实）

[CUDA 编程指南的 Lazy Loading 一节](https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/lazy-loading.html)提到：从 CUDA 12.3 起延迟加载是默认行为，并且「A deadlock can occur if cross-kernel synchronization is required, but kernel execution has been serialized」，规避办法之一就是 `CUDA_MODULE_LOADING=EAGER`。

PaddleOCR-VL 流水线在单独的工作线程（`_worker_vlm`）里做 VL 识别，主线程通过队列等待结果，再加上 WSL2 半虚拟化驱动和体积巨大的 `libphi_gpu.so`，可能导致按需加载模块时一直等不到结果。这只是推测，没有进一步验证，也没有在原生 Linux 上对比过。

### 4.5 相关但不同的报告

[PaddleOCR #17693](https://github.com/PaddlePaddle/PaddleOCR/issues/17693)：PaddleOCR-VL 在 GPU 上无限卡住，`strace` 看到的是显存分配器反复调用 `ioctl`，给出的解决办法是 `FLAGS_allocator_strategy=naive_best_fit`。环境是原生 Ubuntu 加 RTX A2000，现象和本问题不同（本问题卡在 `cuLibraryGetModule`）。这个办法**没有测试过**，也没有采用。

## 5. `LD_LIBRARY_PATH`（可选，不是必需的）

`~/.bashrc` 第 109 行是 `export LD_LIBRARY_PATH=${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}`。在它的影响下：

- Paddle 会优先加载系统里的 CUDA 12.8 运行时，日志里显示 `Runtime API Version: 12.8`；
- 还会报 `libcuda.so: cannot open shared object file`。WSL 里的 `libcuda.so` 在 `/usr/lib/wsl/lib`，不在 `ldconfig` 缓存里（缓存里只有 `libcuda.so.1`）。

改成 `LD_LIBRARY_PATH=/usr/lib/wsl/lib` 后，Paddle 会加载环境自带的 12.9 运行时，警告也消失了。不过只设 EAGER 也能跑通，所以这一项只是让环境更干净。还要注意：`LD_LIBRARY_PATH` 只能在进程启动前设，进程里再改不起作用。

## 6. 本机已做的配置

经用户确认（「1 把LD_LIBRARY_PATH也加进去吧」），在 `~/.bashrc` 末尾加了：

```bash
# PaddleOCR (uv tool): WSL2 + RTX 5090 needs eager CUDA module loading, otherwise the VL model hangs
paddleocr() { CUDA_MODULE_LOADING=EAGER LD_LIBRARY_PATH=/usr/lib/wsl/lib command paddleocr "$@"; }
```

**这个函数对 Agent 不可靠**，原因有两个：

- `~/.bashrc` 第 6 行是 `[ -z "$PS1" ] && return`，非交互式 shell 一进来就直接退出，函数根本不会被定义。Codex、`subprocess`、cron 都属于这种情况。
- Claude Code 的 Bash 工具用的是自己保存的 shell 快照。我检查了 `~/.claude/shell-snapshots/` 里最新的快照，连用户的 `alias claude` 都没有，只有 harness 自己的辅助函数。所以也不能指望它带上这个函数。

## 7. 调用方式（skill 要教给 Agent 的内容）

命令行（已验证，PNG 输入）：

```bash
CUDA_MODULE_LOADING=EAGER paddleocr doc_parser -i <图片或PDF> --save_path <输出目录>
```

示例图的输出：

- `<名字>.md`：Markdown，图片以 `<img src="imgs/...">` 的形式引用；
- `<名字>_res.json`：`parsing_res_list` 里每个区域有 `block_label`（如 `doc_title`、`text`、`image`、`paragraph_title`、`vision_footnote`）、`block_content` 和 `block_bbox`；
- `<名字>.docx`；
- `<名字>_layout_det_res.png`：版面检测的标注图；
- `imgs/`：裁剪出的图片。

示例图共解析出 31 个区域。

`doc_parser` 中可能用得到的参数（来自 `paddleocr doc_parser --help`）：

- `--pipeline_version {v1,v1.5,v1.6}`
- `--vl_rec_backend {native,vllm-server,sglang-server,fastdeploy-server,mlx-vlm-server,llama-cpp-server}`
- `--vl_rec_server_url`
- `--device`（如 `gpu`、`gpu:0`）
- `--engine {paddle,paddle_static,paddle_dynamic,transformers,onnxruntime}`

Blackwell 文档 3.2 节特别提示客户端要指定 `device="gpu"`。本机不指定也跑在了 GPU 上，但 skill 里可以显式写上。

Python API：paddleocr 只装在工具环境里，要用 `$(uv tool dir)/paddleocr/bin/python` 这个解释器；并且必须在 `import paddle` / `paddleocr` **之前**设置 `os.environ["CUDA_MODULE_LOADING"] = "EAGER"`，放在 import 之后不会生效，也不会报错。文档示例用的是 `PaddleOCRVL()` 加 `.predict()`，本机还没直接测过，只测过用 runpy 调 CLI 入口。Agent 优先用命令行。

## 8. 推理方式：native 与 vLLM 服务（可选）

用户问过：「我看到文档里有提到Flash attention还有VLM这些需要设置吗？」「vLLM 服务是用来干什么的？」

- `doc_parser` = 版面检测（PP-DocLayoutV3）+ 对每个区域做 VL 识别（PaddleOCR-VL-1.6-0.9B），最后拼成 Markdown/JSON。
- vLLM 或 SGLang 服务**只替换 VL 识别这一步的推理引擎**（批量推理、CUDA Graph、FlashAttention 等），用的是同一套模型权重，输出相同。好处是速度快，而且服务常驻，模型只加载一次，多个客户端可以共用。
- **只做文档解析时，native 就够了**，不需要 vLLM，也不需要 FlashAttention。如果要批量处理大量页面，或者让其他程序常驻调用，再考虑上服务。
- 只有推理服务需要 FlashAttention。Blackwell 文档 3.1.2 节原文：「vLLM 和 SGLang 依赖 FlashAttention」。源码里 `paddlex/utils/deps.py:283` 检查服务能不能用时，在有 CUDA 的情况下会要求 `xformers` 和 `flash-attn` 都已安装。
- 安装服务依赖用的 `paddleocr install_genai_server_deps vllm`，实际执行的是 `paddlex --install genai-vllm-server`（`paddleocr/_cli.py:110-117`），靠 pip 安装。uv tool 环境里没有 pip，所以文档建议另建一个虚拟环境。
- 文档给出的 FlashAttention 预编译 wheel 示例是 `flash_attn-2.8.3+cu128torch2.8-cp310`（来自 [mjun0812/flash-attention-prebuild-wheels](https://github.com/mjun0812/flash-attention-prebuild-wheels)），和 cp312 环境对不上，到时需要另找匹配的版本。
- 启动服务：`paddleocr genai_server --model_name PaddleOCR-VL-1.6-0.9B --backend vllm --port 8118`。客户端调用：`paddleocr doc_parser --input demo.png --vl_rec_backend vllm-server --vl_rec_server_url http://localhost:8118/v1`。
- Docker 方案：`ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-genai-vllm-server:latest-nvidia-gpu-sm120`，完整流水线的镜像是 `…/paddleocr-vl:latest-nvidia-gpu-sm120`。本机 Docker 版本 29.5.2，`docker info` 里的 Runtimes 只有 `runc`，容器里能不能用 GPU 还没验证。

## 9. 待办与待决定

- [ ] **让所有调用方都自动带上 EAGER**（已提出，用户还没确认）：在工具环境的 site-packages 里放一个 `.pth` 启动文件，Python 每次启动时都会执行它，只影响 paddleocr 这一个环境。这样命令行和 Python API 都不用再手动设环境变量。
  ```
  # $(uv tool dir)/paddleocr/lib/python3.12/site-packages/zz_wsl_cuda_eager.pth
  import os; os.environ.setdefault("CUDA_MODULE_LOADING", "EAGER")
  ```
  进程内设置的效果已经验证过（第 4.3 节最后一行）。这个文件本身还没加过，也没测过。用 `--reinstall` 或 `--force` 重建环境后它会丢失；`uv tool upgrade` 会不会保留它，还没验证。
- [ ] skill 的名称和范围：是只管调用，还是连安装和验证也包括进去？要不要把同机的 mineru 也纳入同一个「文档解析」skill？
- [ ] 按本仓库的约定，个人环境信息（WSL、5090、本机路径）不写进 `SKILL.md`；EAGER 问题以「带日期的已知问题和排查提示」的形式写进 skill。
- [ ] 测试 PDF 输入，看多页 PDF 的输出文件怎么命名、怎么组织。这是用户的主要使用场景，目前只测过 PNG。
- [ ] 分开测量模型加载时间和单页推理时间，用来判断批量处理时值不值得上 vLLM 服务。
- [ ] 之前提议在 `~/.claude/CLAUDE.md` 的 CLI tools 一节加一行说明 paddleocr，还没做。skill 建好后可能就不需要了。
- [x] **skill 调用时混用两套 CUDA 库**（2026-10-06，用户问「skill调用的时候加载的cuda用的是哪个」）。Agent 的 shell 继承了 `~/.bashrc` 第 109 行导出的 `LD_LIBRARY_PATH`（非交互式 shell 虽然会在第 6 行退出，但变量来自启动 harness 的那个终端），`parse.py` 也没有改它。用已安装的 skill 解析一页，读取进程的 `/proc/<pid>/maps`：
  - 继承的 `LD_LIBRARY_PATH`：`libcudart.so.12.8.90`、`libcublas`/`libcublasLt` `12.8.4.1` 来自 `/usr/local/cuda-12.8`；同一个进程里还映射了环境自带的 `libcublas.so.12`（12.9.0.13）；cuDNN 是环境自带的 9.9.0.52。
  - 去掉 `LD_LIBRARY_PATH`：cudart 12.9.37、cublas/cublasLt 12.9.0.13、cuDNN 9.9.0.52，全部来自 `$(uv tool dir)/paddleocr/…/site-packages/nvidia/`。
  - 两种情况的 Markdown 逐字节相同，耗时 20 s 对 19 s；v1 的 110 页也是在混用的状态下跑的。目前没有出错，但同一个进程里有两份 `libcublas.so.12`，用哪一份取决于加载顺序。
  - 去向：用户要求「让它稳定用自带的 12.9」。工具环境自带 CUDA 运行时（`site-packages/nvidia/cuda_runtime`）时，`parse.py` 在 `execv` 之前从 `LD_LIBRARY_PATH` 里去掉含 `libcudart.so*` 的目录，一个都不剩时删掉这个变量（`LD_LIBRARY_PATH` 在 exec 时才会被读取，所以对新进程有效）；直接用工具环境的 Python 启动脚本时不处理。复测时用的是继承来的 `LD_LIBRARY_PATH`：进程里只剩环境自带的 12.9 那一套，Markdown 和修改前逐字节相同。`references/install.md` 新增「Which CUDA libraries load」一节，写了直接调 CLI 时的做法。
- [ ] 本机所有 uv tool（hf、markitdown、mineru、pdfplumber、paddleocr）的解释器都来自 miniconda。如果升级或删除 miniconda，这些工具都可能失效。可以考虑改用 `uv python` 管理的解释器重装（`--python-preference only-managed`）。

## 10. 参考资料

- [PaddleOCR-VL NVIDIA Blackwell 使用教程](https://www.paddleocr.ai/latest/version3.x/pipeline_usage/PaddleOCR-VL-NVIDIA-Blackwell.html)：1.2 节手动安装，3.1 节 VLM 推理服务，3.1.2 节 FlashAttention，3.2 节客户端用法
- [PaddleOCR-VL 使用教程](https://www.paddleocr.ai/latest/version3.x/pipeline_usage/PaddleOCR-VL.html)：版本要求、`pipeline_version`、native 推理、`install_genai_server_deps`
- Paddle cu129 源：<https://www.paddlepaddle.org.cn/packages/stable/cu129/paddlepaddle-gpu/>（wheel 实际托管在 `paddle-whl.cdn.bcebos.com`）
- [paddleocr（PyPI）](https://pypi.org/project/paddleocr/)：3.7.0 的 extras（`doc-parser`、`doc2md`、`all` 等）
- [uv 文档：Package indexes · Searching across multiple indexes](https://docs.astral.sh/uv/concepts/indexes/)：`first-index` 策略、flat index（`--find-links`）
- [CUDA Programming Guide · Lazy Loading](https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/lazy-loading.html)：`CUDA_MODULE_LOADING=LAZY/EAGER`，12.3 起默认延迟加载，存在死锁风险
- [PaddleOCR #17693](https://github.com/PaddlePaddle/PaddleOCR/issues/17693)：PaddleOCR-VL 在 GPU 上卡住（显存分配器问题，和本问题不同）
- [mjun0812/flash-attention-prebuild-wheels](https://github.com/mjun0812/flash-attention-prebuild-wheels)：FlashAttention 预编译 wheel
- 本机源码位置（工具环境内）：`paddleocr/_cli.py`（`install_genai_server_deps`、`genai_server`），`paddlex/utils/deps.py`（推理服务依赖检查），`paddlex/inference/pipelines/paddleocr_vl/pipeline.py`（VL 识别工作线程 `_worker_vlm`）
