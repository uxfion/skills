---
name: vllm-serve
description: Runs models as OpenAI-compatible vLLM servers on a GPU machine — this one, or a shared or remote server reached over ssh — one shared vLLM install, one server per model profile, started on demand and stopped when idle. Use when a task or another skill needs a model server (the paddleocr skill's VL model is one), to see or stop running servers, to add a model, or to deploy one on a multi-GPU server shared with other people.
---

# vLLM serve

One vLLM installation (a uv tool) serves every model a machine runs; a vLLM server holds one model, so each model has a profile and its own server. A server starts when someone asks for it, is shared by everyone who asks while it runs, and stops by itself after a spell without requests, giving the GPUs back to other work.

Script paths are relative to this file's directory. `uv run scripts/serve.py --help` is the reference for commands, profile keys, output fields and error codes. No vLLM installed (`vllm_missing`), a server that will not start, or an upgrade → [references/install.md](references/install.md). A machine other people use, or one reached over ssh → [references/shared-machines.md](references/shared-machines.md), before the first install or `up` there.

## Use a server

```bash
uv run scripts/serve.py up <profile>     # one JSON line: {"profile", "url", "model", "started"}
CUDA_VISIBLE_DEVICES=4,5 uv run scripts/serve.py up <profile> -- --data-parallel-size 2    # GPUs and arguments for this start
```

Speak the OpenAI API at `url` with `model` as the model name. `up` returns at once when the server runs. Otherwise the first `up` of a profile downloads its weights, and a start takes from under a minute (a small model) to several (a 27B model, longest on the first start after an install), so call it in the background for anything interactive; it waits as long as the server keeps writing its log. Call `up` again before each new batch of work: a server you used an hour ago has stopped, and `up` resets its idle clock.

Arguments after `--` and the caller's environment shape this start only (a variable the profile's `env` sets stays the profile's). A choice that must hold at the next start, which another caller may trigger after an idle stop, belongs in a profile.

The line may carry more:

- `host`: the server listens beyond this machine; clients elsewhere use the machine's address and the url's port.
- `differs`: the server already running was started with other arguments or GPUs (shown) than this `up` asked for. It serves you as it is; `down` and `up` again to apply yours, once nobody is using it.
- `foreign_cuda`: the server loaded CUDA libraries from outside vLLM's environment; there should be none, so report it and see references/install.md.

Errors come as `{"error", "detail"}` with exit 2:

- `server_failed`: `detail` says whether the server exited or stopped writing its log, then gives the log's first error line and its end. "Free memory on device … is less than desired GPU memory utilization" means other programs hold the GPU: `status` shows whether an idle server of ours is one of them; otherwise report it to the user, since training jobs (theirs or other people's) come first, or choose other GPUs (references/shared-machines.md). Anything else → references/install.md.
- `download_failed`: the weights did not download; hf's own output, printed above it, says why → references/install.md (Weights).
- `port_busy`: another model answers on the profile's port, or another program holds it; `status`, `ss -ltnp` and the user decide.
- `not_permitted`: the server or a file belongs to another login, named in `detail`. That login stops it, or it stops by itself when idle.

## See and stop

```bash
uv run scripts/serve.py status            # each profile: running, url, owner, gpus, load, idle_for_minutes, log
uv run scripts/serve.py down <profile>    # or --all
```

`load` is read from the server's metrics every 30 s: requests running and waiting, KV cache usage, prefix-cache hit rate, preemptions, prompt and generated tokens per second. `nvidia-smi` shows everything else on the GPUs. A running server is shared: `down` cuts off whoever is using it. Stop one when the user wants the GPUs back, after `status` shows it idle.

## Add a model

1. Take the launch arguments from the model's vLLM recipe (`models/<org>/<model>.yaml` in vllm-project/recipes) and, where the program that will call the model ships its own server settings (PaddleX does for PaddleOCR-VL), from those; the caller's tuning wins. Recipes date: check their version notes against the installed vLLM. Size the server with [references/tuning.md](references/tuning.md).
2. Write `<name>.toml` with `model`, `port` (one no other profile uses) and `args`, plus `env` and `idle_minutes` (0: never stops by itself) when needed; every vLLM setting, `--gpu-memory-utilization` included, is a vLLM argument. A public model and what holds on any machine go in this skill's `profiles/`. A local checkpoint, anything personal, or one deployment's choices (GPUs, `--host`, `--revision`, a smaller GPU share beside training) go in `~/.config/vllm-serve/profiles/`, where `extends = "<profile>"` starts from a shipped profile and adds them.
3. `up` it, send one real request, check the answer, `down` it. Done when the answer is right, `up` reported no `foreign_cuda`, and the profile records where its arguments came from.

Profiles shipped here: `paddleocr-vl` (PaddleOCR-VL-1.6 on port 8118, for the paddleocr skill) and `qwen38-27b` (Qwen3.8-27B on port 8238; one GPU of 84 GB or more at vLLM's default 0.92 of it).
