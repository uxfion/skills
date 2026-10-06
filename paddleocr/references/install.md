# Installing and troubleshooting PaddleOCR-VL

`scripts/parse.py` runs inside the `paddleocr` uv tool environment, which needs the GPU build of PaddlePaddle on an NVIDIA GPU. Check what is there first:

```bash
paddleocr --version          # paddleocr 3.x
uv tool list | grep -A2 '^paddleocr'
```

## Install

Installing is a multi-GB download that takes over ten minutes: say so to the user and wait for their go-ahead. The command that works (2026-10, PaddleOCR 3.7, the PaddleOCR-VL docs ask for PaddlePaddle ≥ 3.2.1):

```bash
uv tool install --python 3.12 \
  --find-links https://www.paddlepaddle.org.cn/packages/stable/cu129/paddlepaddle-gpu/ \
  --with paddlepaddle-gpu==3.2.1 \
  --with python-docx \
  'paddleocr[doc-parser]'
```

- **The package directory follows the driver.** `cu129` serves drivers with CUDA 12.9 or newer and is the one the docs require for Blackwell (RTX 50); older GPUs can take `cu126`. Check `nvidia-smi` and the [PaddleOCR-VL usage guide](https://www.paddleocr.ai/latest/version3.x/pipeline_usage/PaddleOCR-VL.html) (Blackwell: [its own page](https://www.paddleocr.ai/latest/version3.x/pipeline_usage/PaddleOCR-VL-NVIDIA-Blackwell.html)). Plain `paddlepaddle` is the CPU build: the VL model on a CPU takes minutes per page.
- **`--find-links`, not `--index`.** The Paddle index answers HTTP 200 with an empty page for packages it does not host, so uv's default `first-index` strategy decides `paddleocr` exists there with no versions and never asks PyPI. As a flat link list it supplies only `paddlepaddle-gpu`; everything else comes from PyPI.
- `uv tool upgrade paddleocr` reuses the recorded `--find-links` and `--with` pins; `uv tool uninstall paddleocr` removes the whole environment.

Verify the GPU build, then parse one page end to end (the first parse downloads about 2 GB of models into `~/.paddlex/official_models/`):

```bash
uv run --no-project --python "$(uv tool dir)/paddleocr/bin/python" - <<'PY'
import paddle
paddle.utils.run_check()      # "PaddlePaddle works well on 1 GPU."
PY
uv run scripts/parse.py <a PDF> --pages 1 -o <scratch dir>
```

## A parse that hangs

Symptom (seen 2026-10 under WSL2 with an RTX 50-series GPU): layout detection finishes, the VL model loads (GPU memory jumps to about 11 GB), then nothing — no page line on stderr for minutes, one CPU core busy, GPU utilisation at 1–2 %. A stack dump shows the VL worker thread inside `cudaLaunchKernel → cuLibraryGetModule`.

Cause: CUDA's lazy module loading (the default since CUDA 12.3, which can deadlock). The fix is `CUDA_MODULE_LOADING=EAGER` before CUDA initialises. `parse.py` sets it for itself; anything else that calls PaddleOCR needs it too:

```bash
CUDA_MODULE_LOADING=EAGER paddleocr doc_parser -i <file> --save_path <dir>
```

In Python, set `os.environ["CUDA_MODULE_LOADING"] = "EAGER"` before `import paddleocr` — set later, it is silently ignored.

A hang with EAGER already set is a different problem: [PaddleOCR #17693](https://github.com/PaddlePaddle/PaddleOCR/issues/17693) reports an allocator loop (repeated `ioctl` under `strace`) answered with `FLAGS_allocator_strategy=naive_best_fit` — untested here.

Harmless on WSL: `libcuda.so: cannot open shared object file` (WSL keeps it in `/usr/lib/wsl/lib`), `No ccache found`, and a `Non compatible API` notice.

## Many documents

`parse.py` uses the native backend: one process, about 30 s to load, then roughly 15 s a page. For a large batch, or several programs sharing one loaded model, a vLLM or SGLang server can replace just the VL step (same weights, same output); it needs its own environment with FlashAttention. Setup is in the usage guide, section on inference services (`paddleocr genai_server`, `paddleocr doc_parser --vl_rec_backend vllm-server --vl_rec_server_url …`); `parse.py` does not drive one yet.
