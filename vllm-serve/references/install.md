# Installing and troubleshooting vLLM

`scripts/serve.py` runs the `vllm` executable of one uv tool environment (or `VLLM_SERVE_VLLM`). Check what is there first:

```bash
uv tool list | grep -A1 '^vllm'
```

## Install

vLLM gets a uv tool environment of its own, with its own CUDA: its binaries are compiled against one PyTorch build, and that PyTorch's `nvidia-*` CUDA packages collide with those of other GPU frameworks such as PaddlePaddle. Build it where it will run: the tool environment holds absolute paths and cannot be moved or copied. Installing downloads several GB: say so to the user and wait for their go-ahead.

Pin the whole stack in the one install command: Python, the vLLM version, its CUDA build, and the toolkit's compiler packages at the CUDA version PyTorch uses. The CUDA build follows the driver: `nvidia-smi` shows the newest CUDA it supports, and vLLM's release notes list the builds a version ships (0.32.0: CUDA 13.0, the one on PyPI, and 12.9). Take the newest the driver supports.

Driver for CUDA 13.0 or newer (R580+):

```bash
uv tool install --python 3.12 "vllm==0.32.0" --torch-backend cu130 \
  --with "cuda-toolkit[nvcc,nvvm,crt,cccl,nvjitlink]==13.0.3"     # 2026-10: 7.8 GB
```

Driver for CUDA 12.9 (R575): the `+cu129` build, a release asset that PyPI does not carry (`--torch-backend` picks PyTorch's build, never vLLM's, and alone gave a CUDA 13 vLLM beside a CUDA 12.9 PyTorch: "CUDA driver version is insufficient for CUDA runtime version"). PyPI has no CUDA 12 compiler, so there is no toolkit pin, and FlashInfer depends on the precompiled kernels below:

```bash
uv tool install --python 3.12 "vllm @ https://github.com/vllm-project/vllm/releases/download/v0.32.0/vllm-0.32.0%2Bcu129-cp38-abi3-manylinux_2_28_x86_64.whl" \
  --torch-backend cu129                                           # 2026-10, 8× H200, driver 575
```

Then, for either build:

```bash
vllm download-kernels       # FlashInfer's precompiled kernels; without them the first start compiles for minutes, or on CUDA 12.9 FlashInfer stays off
```

Every pin closes a gap that broke an install once (2026-10):

- **`--python 3.12`**: without it uv takes the newest Python it can get, 3.15 in 2026-10, which torchaudio 2.11 has no wheels for ("requirements are unsatisfiable"); both servers ran 3.12.
- **`vllm==<version>`**: vLLM pins PyTorch, torchvision and torchaudio exactly, so the version fixes them all.
- **`--torch-backend cu<NNN>`, named**: `--torch-backend auto`, though vLLM's release notes suggest it, took PyTorch from `cu132` and torchaudio from `cu130` (torchaudio 2.11 has no `cu132` build), and every server died on import: "PyTorch and TorchAudio were compiled with different CUDA versions".
- **`cuda-toolkit[nvcc,…]==<PyTorch's toolkit version>`**: PyTorch pins the CUDA runtime (`Requires-Dist: cuda-toolkit[cublas,cudart,…]==13.0.3` in the cu130 build's metadata), while other dependencies pulled the compiler unpinned, at 13.4: a toolkit whose compiler and headers disagree, which fails any kernel build ("CUDA compiler and CUDA toolkit headers are incompatible"). For another vLLM version, install it once without this pin, read PyTorch's own (`uv run --no-project --python "$(uv tool dir)/vllm/bin/python" - <<< 'import importlib.metadata as m; print([r for r in m.requires("torch") if "cuda-toolkit" in r])'`), then reinstall with the pin. `nvidia-nvjitlink` and `nvidia-cuda-nvdisasm` may come out newer; NVIDIA's metapackage allows that for nvJitLink, CUTLASS DSL asks for nvdisasm 13.3 or newer, and neither is the compiler.

uv takes the Python from a conda environment when one is active or first on `PATH`; `UV_PYTHON_PREFERENCE=only-managed` keeps the tool on a Python uv manages. On a slow network, warm the uv cache first (copy another machine's cache directory whole, or let one install fill it) and install as usual: the cache moves between machines, the tool environment does not.

To move to another vLLM, install from scratch with the new pins: `uv tool uninstall vllm`, delete `~/.cache/vllm` and `~/.cache/flashinfer` (kernels and builds made under the old toolkit), then the install command and `vllm download-kernels`. `uv tool upgrade` would resolve PyTorch afresh.

## Verify

```bash
uv run --no-project --python "$(uv tool dir)/vllm/bin/python" - <<'PY'
import torch, torchaudio, torchvision, vllm
print(vllm.__version__, torch.__version__, torchvision.__version__, torchaudio.__version__, "CUDA", torch.version.cuda)
print(torch.cuda.get_device_name(), torch.cuda.get_device_capability())
PY
```

Then `up` a profile, send one request through its client, `down`.

Done when PyTorch, torchvision and torchaudio carry the same `+cuNNN` build, the GPU is listed, and `up`'s JSON line has no `foreign_cuda`.

## Weights

The first `up` of a Hub model downloads it (`hf download`, at the profile's `--revision`) before the server starts, its progress on `up`'s stderr; `hf` itself is `$(uv tool dir)/vllm/bin/hf`. When huggingface.co answers but the download sits at 0 bytes, its download hosts are blocked: the default Xet path uses `cas-server.xethub.hf.co` and `transfer.xethub.hf.co`, and `HF_HUB_DISABLE_XET=1` switches to plain HTTP through a CDN host; try the other path. Otherwise copy the model from a machine that has it: the whole `hub/` directory of its Hugging Face cache (since huggingface_hub 1.32 the files link into a `blobs/` directory shared by all models), then check it with `hf cache verify <model> --revision <commit>`, which compares every file's sha256 with the Hub's and needs only huggingface.co.

## What serve.py sets for every server

| Setting | Why |
| --- | --- |
| `CUDA_HOME` and `CUDA_PATH` → the environment's toolkit (`site-packages/nvidia/cu13`); `CUDA_LIB_PATH` → its `lib`; its `bin`, then the environment's `bin`, first on `PATH` | Libraries look for CUDA in these places, and the machine's system toolkit leaked in through them (2026-10, WSL2, `CUDA_HOME=/usr/local/cuda-12.8` from `~/.bashrc`): FlashInfer preloads `$CUDA_LIB_PATH/libcudart.so.12`, `/usr/local/cuda/…` by default, and judged the GPU by `CUDA_HOME`'s nvcc 12.8. The environment's `bin` holds `ninja`, which FlashInfer's builds call. A CUDA 12.9 environment has no toolkit of its own: there `CUDA_HOME` and `CUDA_PATH` are removed and `CUDA_LIB_PATH` points at the environment's CUDA runtime. |
| `LD_LIBRARY_PATH` → a directory of unversioned names (`libcublas.so` → the environment's `libcublas.so.13`), then the toolkit's `lib`; system toolkit directories removed | FlashInfer's autotuner opens `libcublas.so` by its unversioned name; the pip toolkit ships only versioned files, so the system loader cache (`/etc/ld.so.conf.d/cuda-12-8.conf`) answered with the system cuBLAS 12.8. |
| `VLLM_USE_FLASHINFER_SAMPLER=0` | FlashInfer's sampler compiles its kernels on first use, and the pip toolkit cannot link them (no `lib64`, no `libcudart.so`, no `stubs/libcuda.so`: "cannot find -lcudart"). vLLM samples with PyTorch instead. A profile that wants FlashInfer's sampler sets it to 1 in its `env`, after `vllm download-kernels`. |
| `CUDA_DEVICE_ORDER=PCI_BUS_ID` | `CUDA_VISIBLE_DEVICES` numbers then mean `nvidia-smi`'s numbers; CUDA's own order puts the fastest GPU first. |
| `VLLM_ENGINE_READY_TIMEOUT_S=86400` | vLLM's own deadline (600 s, applied with data parallel) stopped a 52 GB load from a nearly full disk (2026-10); `up` watches the server's log instead. |
| `VLLM_WSL2_ENABLE_PIN_MEMORY=1` | vLLM turns pinned memory off under WSL2 unless told. 0.28 then stopped with "UVA is not available"; 0.31 falls back to device memory and runs slower. |
| `CUDA_MODULE_LOADING` removed | Programs that run Paddle beside vLLM (paddleocr's `parse.py`) set it to `EAGER`; inherited by vLLM 0.28, it stalled the engine start at "Initializing a V1 LLM engine" for minutes. |
| `HF_HUB_OFFLINE=1` when the weights are cached | The server starts without asking the Hub. |

The caller's environment and then the profile's `env` go over these. A server started by hand, outside `serve.py`, needs the same. vLLM picks the attention kernels for the GPU: FlashAttention 3 on Hopper only, FlashInfer on Blackwell data-centre GPUs (sm_100), FlashAttention 2 on RTX 50 / RTX PRO 6000 (sm_120), Ada and Ampere; nothing to install for it.

## Timings

The first start after an install compiles and captures CUDA graphs: about 2 minutes for a 1B model, 6 for a 27B one (2026-10, RTX PRO 6000, FlashInfer kernels compiled on the spot). Later starts reuse the compile cache: 25–50 s for the 1B model. Loading 55.6 GB of weights took 90–105 s from a fast disk and 400–460 s from a nearly full one.

## A server that does not start, or loads foreign CUDA

`status` names each profile's log; `server_failed` quotes its end.

- "CUDA driver version is insufficient for CUDA runtime version": the vLLM build is newer than the driver; install the build the driver supports.
- "PyTorch and TorchAudio were compiled with different CUDA versions": the install mixed CUDA builds. Install from scratch with a named `--torch-backend`.
- "CUDA compiler and CUDA toolkit headers are incompatible": the toolkit's compiler and runtime differ; the `cuda-toolkit[…]` pin is missing or does not match PyTorch's.
- "FlashInfer kernels are disabled", "precompiled kernels are missing", or "Ninja build failed" with "cannot find -lcudart": run `vllm download-kernels`.
- "Free memory on device … is less than desired GPU memory utilization": other programs hold the GPU. Lower `--gpu-memory-utilization` only as far as the profile's comment allows, choose other GPUs, or wait.
- "max_num_seqs (N) exceeds available Mamba cache blocks (M)": a hybrid model (Mamba or gated-delta-net layers) on a GPU whose KV cache holds fewer than N blocks; set `--max-num-seqs` at most M (references/tuning.md).
- `server_failed` saying the server wrote nothing to its log for 10 minutes: a hang, often the GPUs of a tensor-parallel group failing to connect, or a slow download of FlashInfer kernels on a first start (`vllm download-kernels` once).
- Weights loading slowly from a nearly full or network disk: `--safetensors-load-strategy eager` reads each file in order instead of through page faults (default `lazy`; vLLM prefetches by itself on NFS and Lustre).
- A 400 from the server naming a request parameter: vLLM changed a default; the message names the flag that allows it. Add the flag to the profile with a comment saying why.
- Stuck at "Initializing a V1 LLM engine" for minutes: `CUDA_MODULE_LOADING=EAGER` reached a server started outside `serve.py`.
- `foreign_cuda` in `up`'s output: a library found a CUDA toolkit outside the environment. The dynamic loader names the culprit: start the server with `LD_DEBUG=files LD_DEBUG_OUTPUT=<prefix>` set for `serve.py up`, `down` it, and search the `<prefix>.*` files for the library's name followed by "dynamically loaded by" or "needed by".
