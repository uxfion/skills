---
name: vllm-serve
description: Runs local models on this machine's GPU as OpenAI-compatible vLLM servers — one shared vLLM install, one server per model profile, started on demand and stopped when idle. Use when a task or another skill needs a local model server (the paddleocr skill's VL model is one), to see what holds the GPU or stop servers, or to add a model.
---

# vLLM serve

One vLLM installation (a uv tool) serves every model this machine runs locally; a vLLM server holds one model, so each model has a profile and its own server. A server starts when someone asks for it, is shared by everyone who asks while it runs, and stops by itself after a spell without requests, giving the GPU back to other work.

Script paths are relative to this file's directory. `uv run scripts/serve.py --help` is the reference for commands, profile keys, files and error codes. No vLLM installed (`vllm_missing`), a server that will not start, or an upgrade → [references/install.md](references/install.md).

## Use a server

```bash
uv run scripts/serve.py up <profile>     # one JSON line: {"profile", "url", "model", "started"}
```

Speak the OpenAI API at `url` with `model` as the model name. `up` returns at once when the server runs; otherwise the first `up` of a profile downloads its weights (minutes) and every start takes about a minute, so call it in the background for anything interactive. Call `up` again before each new batch of work: a server you used an hour ago has stopped, and `up` resets its idle clock.

A started server's line carries `foreign_cuda` when it loaded CUDA libraries from outside vLLM's environment; there should be none, so report it and see references/install.md. Errors come as `{"error", "detail"}` with exit 2:

- `gpu_busy`: other programs hold the GPU memory the profile needs; `detail` says how much is free. Report it to the user; their training jobs come first.
- `port_busy`: another model answers on the profile's port, likely a server started by hand; `status` and the user decide.
- `server_failed`: `detail` ends with the server's log. A start that once worked and now fails after a vLLM upgrade → references/install.md.

## See and stop

```bash
uv run scripts/serve.py status            # each profile: running, url, idle_minutes, log
uv run scripts/serve.py down <profile>    # or --all
```

A running server is shared: `down` cuts off whoever is using it. Stop one when the user wants the GPU back, after `status` shows it idle.

## Add a model

1. Take the launch arguments from the model's vLLM recipe (`models/<org>/<model>.yaml` in vllm-project/recipes) and, where the program that will call the model ships its own server settings (PaddleX does for PaddleOCR-VL), from those; the caller's tuning wins. Cite both in the profile.
2. Write `<name>.toml`: in this skill's `profiles/` for a public model, in `~/.config/vllm-serve/profiles/` for a local checkpoint or anything personal. Give it a port no other profile uses and a `gpu_memory_utilization` that leaves room for the profiles that run beside it and for training.
3. `up` it, send one real request, check the answer, `down` it. Done when the answer is right, `up` reported no `foreign_cuda`, and the profile records where its arguments came from.

Profiles shipped here: `paddleocr-vl` (PaddleOCR-VL-1.6 on port 8118, for the paddleocr skill).
