# Installing and troubleshooting vLLM

`scripts/serve.py` runs the `vllm` executable of one uv tool environment (or `VLLM_SERVE_VLLM`). Check what is there first:

```bash
uv tool list | grep -A1 '^vllm'
```

## Install

vLLM gets a uv tool environment of its own, with its own CUDA: its binaries are compiled against one PyTorch build, and that PyTorch's `nvidia-*` CUDA packages collide with those of other GPU frameworks such as PaddlePaddle. Installing downloads several GB: say so to the user and wait for their go-ahead.

Pin the whole CUDA stack in the one install command — the vLLM version, its CUDA build, and the toolkit's compiler packages at the CUDA version PyTorch uses:

```bash
uv tool install "vllm==0.31.0" --torch-backend cu130 \
  --with "cuda-toolkit[nvcc,nvvm,crt,cccl,nvjitlink]==13.0.3"     # 2026-10: 7.8 GB
```

Every pin closes a gap that broke this install once (2026-10, vLLM 0.31.0, driver for CUDA 13.1):

- **`vllm==<version>`**: vLLM pins PyTorch, torchvision and torchaudio exactly, so the version fixes them all. Its release notes list the CUDA builds it ships (0.31.0: CUDA 13.0 by default, 12.9); take the newest one the driver supports (`nvidia-smi` shows the driver's CUDA version).
- **`--torch-backend cu<NNN>`, named**: `--torch-backend auto`, though vLLM's release notes suggest it, took PyTorch from `cu132` and torchaudio from `cu130` (torchaudio 2.11 has no `cu132` build), and every server died on import: "PyTorch and TorchAudio were compiled with different CUDA versions".
- **`cuda-toolkit[nvcc,…]==<PyTorch's toolkit version>`**: PyTorch pins the CUDA runtime (`Requires-Dist: cuda-toolkit[cublas,cudart,…]==13.0.3` in the cu130 build's metadata), while other dependencies pulled the compiler unpinned, at 13.4: a toolkit whose compiler and headers disagree, which fails any kernel build ("CUDA compiler and CUDA toolkit headers are incompatible"). Read the version from the installed PyTorch's metadata. `nvidia-nvjitlink` and `nvidia-cuda-nvdisasm` may come out newer; NVIDIA's metapackage allows that for nvJitLink, CUTLASS DSL asks for nvdisasm 13.3 or newer, and neither is the compiler.

To move to another vLLM, install from scratch with the new pins: `uv tool uninstall vllm`, delete `~/.cache/vllm` and `~/.cache/flashinfer` (kernels and builds made under the old toolkit), then the install command. `uv tool upgrade` takes no `--torch-backend` and would resolve PyTorch afresh.

## Verify

```bash
uv run --no-project --python "$(uv tool dir)/vllm/bin/python" - <<'PY'
import torch, torchaudio, torchvision, vllm
print(vllm.__version__, torch.__version__, torchvision.__version__, torchaudio.__version__, "CUDA", torch.version.cuda)
print(torch.cuda.get_device_name(), torch.cuda.get_device_capability())
PY
"$(uv tool dir)"/vllm/lib/python3*/site-packages/nvidia/cu*/bin/nvcc --version | tail -1
```

Then `uv run scripts/serve.py up paddleocr-vl`, one request through its client, `down`.

Done when PyTorch, torchvision and torchaudio carry the same `+cuNNN` build, nvcc reports the CUDA version PyTorch prints, the GPU is listed, and `up`'s JSON line has no `foreign_cuda`.

## What serve.py sets for every server

| Setting | Why (2026-10, WSL2, RTX 5090 D) |
| --- | --- |
| `CUDA_HOME` and `CUDA_PATH` → the environment's toolkit (`site-packages/nvidia/cu13`); `CUDA_LIB_PATH` → its `lib`; its `bin`, then the environment's `bin`, first on `PATH` | Libraries look for CUDA in these places, and the machine's system toolkit (`CUDA_HOME=/usr/local/cuda-12.8` from `~/.bashrc`) leaked in through them: FlashInfer preloads `$CUDA_LIB_PATH/libcudart.so.12`, `/usr/local/cuda/…` by default, and judged the GPU by `CUDA_HOME`'s nvcc 12.8. The environment's `bin` holds `ninja`, which FlashInfer's builds call. |
| `LD_LIBRARY_PATH` → a directory of unversioned names (`libcublas.so` → the environment's `libcublas.so.13`), then the toolkit's `lib`; system toolkit directories removed | FlashInfer's autotuner opens `libcublas.so` by its unversioned name; the pip toolkit ships only versioned files, so the system loader cache (`/etc/ld.so.conf.d/cuda-12-8.conf`) answered with the system cuBLAS 12.8. |
| `VLLM_USE_FLASHINFER_SAMPLER=0` | FlashInfer's sampler compiles its kernels on first use, and the pip toolkit cannot link them (no `lib64`, no `libcudart.so`, no `stubs/libcuda.so`: "cannot find -lcudart"). vLLM samples with PyTorch, which greedy decoding such as PaddleOCR's never misses. A profile that needs FlashInfer's sampler sets it to 1 in its `env`, and the environment gets FlashInfer's prebuilt kernels: `--with flashinfer-jit-cache==<flashinfer version>` from `https://flashinfer.ai/whl/cu130` (FlashInfer's install guide; the package pulls every GPU architecture's kernels, about 1.2 GB). |
| `VLLM_WSL2_ENABLE_PIN_MEMORY=1` | vLLM turns pinned memory off under WSL2 unless told. 0.28 then stopped with "UVA is not available"; 0.31 falls back to device memory and runs slower. |
| `CUDA_MODULE_LOADING` removed | Programs that run Paddle beside vLLM (paddleocr's `parse.py`) set it to `EAGER`; inherited by vLLM 0.28, it stalled the engine start at "Initializing a V1 LLM engine" for minutes. |
| `HF_HUB_OFFLINE=1` when the weights are cached | The server starts without asking the Hub. |

A server started by hand, outside `serve.py`, needs the same. Attention runs on vLLM's bundled FlashAttention 2 (FlashAttention 3 needs Hopper); no separate `flash-attn` or `xformers` package is needed.

## Timings

The first start of a profile after an install compiles and captures CUDA graphs (about 2 min); later starts take 25–50 s. The first `up` of a Hub model downloads it before that (PaddleOCR-VL-1.6: 1.8 GB).

## A server that does not start, or loads foreign CUDA

`status` names each profile's log; `server_failed` quotes its end.

- "PyTorch and TorchAudio were compiled with different CUDA versions": the install mixed CUDA builds. Install from scratch with a named `--torch-backend`.
- "CUDA compiler and CUDA toolkit headers are incompatible": the toolkit's compiler and runtime differ; the `cuda-toolkit[…]` pin is missing or does not match PyTorch's.
- "Ninja build failed" with "cannot find -lcudart": something turned FlashInfer's sampler on without its prebuilt kernels; see the table.
- A 400 from the server naming a request parameter: vLLM changed a default; the message names the flag that allows it. Add the flag to the profile with a comment saying why.
- "Free memory on device … is less than desired GPU memory utilization", or `gpu_busy`: other programs hold the GPU. Lower the profile's `gpu_memory_utilization` only as far as its comment allows, or wait for the GPU.
- Stuck at "Initializing a V1 LLM engine" for minutes: `CUDA_MODULE_LOADING=EAGER` reached a server started outside `serve.py`.
- `foreign_cuda` in `up`'s output: a library found a CUDA toolkit outside the environment. The dynamic loader names the culprit: start the server with `LD_DEBUG=files LD_DEBUG_OUTPUT=<prefix>` set for `serve.py up`, `down` it, and search the `<prefix>.*` files for the library's name followed by "dynamically loaded by" or "needed by".
