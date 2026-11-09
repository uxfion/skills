# Installing and troubleshooting PaddleOCR-VL

`ocr.py parse` runs inside the `paddleocr` uv tool environment, which needs the GPU build of PaddlePaddle on an NVIDIA GPU. Check what is there first:

```bash
paddleocr --version          # paddleocr 3.x
uv tool list | grep -A2 '^paddleocr'
```

## Install

Installing is a multi-GB download that takes over ten minutes: tell the user, and go ahead (it is a uv tool). The command that works (2026-10, PaddleOCR 3.7, the PaddleOCR-VL docs ask for PaddlePaddle ≥ 3.2.1):

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

Verify the GPU build, then parse one page end to end:

```bash
uv run --no-project --python "$(uv tool dir)/paddleocr/bin/python" - <<'PY'
import paddle
paddle.utils.run_check()      # "PaddlePaddle works well on 1 GPU."
PY
ocr.py parse <a PDF> --pages 1 -o <scratch dir>/
```

## poppler-utils

Settling checks a parse against the PDF's text layer and page images with `pdftotext` and `pdftoppm` from poppler-utils. `command -v pdftotext pdftoppm` shows whether they are there. They are a system package — `sudo apt install poppler-utils`, on macOS `brew install poppler` — so the user installs it or approves the install.

## A parse that hangs

Symptom (seen 2026-10 under WSL2 with an RTX 50-series GPU): layout detection finishes, the VL model loads (GPU memory jumps to about 11 GB), then nothing — no page line on stderr for minutes, one CPU core busy, GPU utilisation at 1–2 %. A stack dump shows the VL worker thread inside `cudaLaunchKernel → cuLibraryGetModule`.

Cause: CUDA's lazy module loading (the default since CUDA 12.3, which can deadlock). The fix is `CUDA_MODULE_LOADING=EAGER` before CUDA initialises. `ocr.py parse` sets it for itself; anything else that calls PaddleOCR needs it too:

```bash
CUDA_MODULE_LOADING=EAGER paddleocr doc_parser -i <file> --save_path <dir>
```

In Python, set `os.environ["CUDA_MODULE_LOADING"] = "EAGER"` before `import paddleocr` — set later, it is silently ignored.

A hang with EAGER already set is a different problem: [PaddleOCR #17693](https://github.com/PaddlePaddle/PaddleOCR/issues/17693) reports an allocator loop (repeated `ioctl` under `strace`) answered with `FLAGS_allocator_strategy=naive_best_fit` — untested here.

Harmless on WSL: `libcuda.so: cannot open shared object file` (WSL keeps it in `/usr/lib/wsl/lib`), `No ccache found`, and a `Non compatible API` notice.

## Which CUDA libraries load

The tool environment ships its own CUDA runtime, cuBLAS and cuDNN (the `nvidia-*-cu12` wheels; CUDA 12.9 for the cu129 build). A system CUDA toolkit on `LD_LIBRARY_PATH` (`/usr/local/cuda-*/lib64`, often exported in `~/.bashrc` and inherited by agents started from that shell) is searched first: Paddle then loads the toolkit's `libcudart` and a second `libcublas` beside the bundled one (seen 2026-10: 12.8 beside 12.9, same output). `ocr.py parse` drops every `LD_LIBRARY_PATH` directory holding a `libcudart.so*` before it re-executes into the tool environment, so it runs on the bundled set (an environment without a bundled runtime keeps the path as it is). A direct call needs the same, set before the process starts:

```bash
env -u LD_LIBRARY_PATH CUDA_MODULE_LOADING=EAGER paddleocr doc_parser -i <file> --save_path <dir>
```

To see what a running parse has loaded: `grep -o '/[^ ]*lib\(cudart\|cublas\|cudnn\)[^ ]*' /proc/<pid>/maps | sort -u`.

## vLLM server (fast parsing)

The native backend decodes one layout block at a time (PaddleX fixes its batch size at 1), with the GPU mostly idle. A vLLM server batches the blocks of many pages, with the same weights and, block by block, the same output up to small decoding differences (2026-10, RTX 5090 D: nine papers, 225 pages, 2,489 s native → 109 s).

The server comes from the **vllm-serve** skill, this machine's shared vLLM backend: install it beside this one (`npx skills add uxfion/skills --skill vllm-serve -g`) and the vLLM its [install guide](../../vllm-serve/references/install.md) describes; `ocr.py parse` then uses it (`parse -h`: `VLLM_SERVE` for a vllm-serve installed elsewhere). `--vl-server URL` takes any vLLM server serving PaddleOCR-VL-1.6.

vLLM lives in an environment of its own, never in the `paddleocr` tool: vLLM's binaries are tied to one PyTorch build, and that PyTorch and PaddlePaddle pin different versions of the same `nvidia-*` CUDA packages (cu129 Paddle 3.2.1 against PyTorch 2.8.0: `nvidia-cufile-cu12` 1.14 vs 1.13). The PaddleOCR-VL docs (inference service, installed "in a virtual environment") and vLLM's PaddleOCR-VL recipe ("separate venvs for vllm and paddlepaddle") say the same.

### When the server holds a parse up

- Quiet for minutes after `[paddleocr] asking vllm-serve …`: the server is starting, and the `[vllm-serve]` line below it names its log. Judge it as vllm-serve's SKILL.md says for an `up` that has not returned (*When `up` says more*), with its `serve.py`. Judged stuck: `serve.py down paddleocr-vl`; under `--backend auto` the parse then goes native. Then find the cause as that skill says for `server_failed`, before the next parse starts the server again.
- `[vllm-serve] the last start … failed` on stderr: a start failed earlier; find its cause the same way.
- `port_busy` in the reason on stderr: something else holds port 8118, a profile named there or a server started by hand, often PaddleOCR-VL's own. If `curl --noproxy '*' http://127.0.0.1:8118/v1/models` lists PaddleOCR-VL-1.6, pass `--vl-server http://127.0.0.1:8118/v1`; otherwise tell the user.
