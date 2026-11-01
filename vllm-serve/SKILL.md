---
name: vllm-serve
description: Runs models as OpenAI-compatible vLLM servers on this machine's GPUs or on a server reached over ssh, each started on demand and stopped when idle. Use when a task or another skill needs a model server (the paddleocr skill's VL model is one), to see or stop running servers, to add a model, or to deploy one on a GPU server shared with other people.
---

# vLLM serve

One vLLM installation (a uv tool) serves every model a machine runs; a vLLM server holds one model, so each model has a profile and its own server. A server starts when someone asks for it, is shared by everyone who asks while it runs, and stops by itself after a spell without requests, giving the GPUs back to other work.

Script paths are relative to this file's directory. `uv run scripts/serve.py --help` is the reference for commands, profile keys, output fields and error codes. Installing or upgrading vLLM, and a server that will not start → [references/install.md](references/install.md). A machine other people use, or one reached over ssh → [references/shared-machines.md](references/shared-machines.md), before the first install or `up` there.

## Use a server

```bash
uv run scripts/serve.py up <profile>     # one JSON line: {"profile", "url", "model", "started"}
CUDA_VISIBLE_DEVICES=4,5 uv run scripts/serve.py up <profile> -- --data-parallel-size 2    # GPUs and arguments for this start
```

Speak the OpenAI API at `url` with `model` as the model name. `up` returns at once when the server runs. Otherwise it waits until the server answers or the start fails. The first `up` of a profile downloads its weights, and a start takes from one or two minutes (a small model) to several (a 27B model, longest on the first start after an install), so call it in the background for anything interactive. Call `up` again before each new batch of work: a server you used an hour ago has stopped, and `up` resets its idle clock.

Arguments after `--` and the caller's environment shape this start only (a variable the profile's `env` sets stays the profile's). A choice that must hold at the next start, which another caller may trigger after an idle stop, belongs in a profile.

### When `up` says more

What to do on each extra field and each error (`{"error", "detail"}`, exit 2):

- `host`: clients on other machines reach the server at this machine's address and the url's port.
- `differs`: the server runs as shown there; use it as it is. To start it as you asked, `down` it once `status` shows it idle, then `up`.
- `foreign_cuda`: report it to the user and fix it per install.md; then `down` and `up`, until `up` shows none.
- `server_failed`: read the log named in `detail`. A long log goes to a background subagent on a cheap model (Claude Code `sonnet`, Codex `luna`), briefed with the log's path (on a server, with the `ssh` command that reads it) and install.md's section "A server that does not start, or loads foreign CUDA"; it returns the lines that give the cause and the entry they match, if any. Act on the entry, then `up`. No entry matches: work from the cause lines, then tell the user the cause and the fix, as a dated hint for install.md.
- `the last start of <profile> failed` on `up`'s stderr, or `"failed": true` in a stopped profile's `last` in `status`: the previous start ended in a failure that may have gone unseen, a hang or a crash while serving. Read its log, named there, as for `server_failed`; the new start is already under way, so while the cause is still there, `down` it and fix that first.
- `port_busy`: `detail` names what holds the port.
  - A profile of ours serving the model you need, where you need it: `up` that profile instead.
  - Another profile of ours, idle (`status`) and no deployment others use (one shows a `host` and a long `stops_after_minutes`): `down` it, then `up`. Two profiles meant to run together: give the deployment profile a port of its own, then `up`.
  - Another program: `ss -ltnp | grep :<port>` gives its pid and `ps -o user= -p <pid>` its login (no pid shown: another login's).
  - Stopping a server someone uses, or one the user started by hand, is the user's call.
- `not_permitted`: `detail` names the login. That login stops the server, or it stops by itself once idle; a file of root's goes to the user for `chown`. Then `up`.
- `vllm_missing`: install vLLM per install.md, then `up`.
- `unknown_profile`, also as an `error` line in `status`: fix the profile as `detail` says, then `up`.

An `up` in the background that has not returned: `status` gives the phase, the log shows whether the start moves (a download's progress, the step it has reached), and `nvidia-smi` whether the server's GPU memory still grows. It is stuck when none of these has moved for well past the longest phase in install.md's Timings and "A start that goes quiet": `down` it, and handle the `server_failed` the waiting `up` returns. A vLLM that has not answered 30 minutes after its start is stopped by serve.py, with the same `server_failed`.

## See and stop

```bash
uv run scripts/serve.py status            # each profile: phase, url, owner, gpus, load, idle_for_minutes, last, log
uv run scripts/serve.py down <profile>    # or --all
```

`load` is read from the server's metrics every 30 s: requests running and waiting, KV cache usage, prefix-cache hit rate, preemptions, prompt and generated tokens per second. `nvidia-smi` shows everything else on the GPUs. A running server is shared: `down` cuts off whoever is using it. Stop one when the user wants the GPUs back, after `status` shows it idle.

## Add a model

1. Take the launch arguments from the model's vLLM recipe (`models/<org>/<model>.yaml` in vllm-project/recipes) and, where the program that will call the model ships its own server settings (PaddleX does for PaddleOCR-VL), from those; the caller's tuning wins. Recipes date: check their version notes against the installed vLLM. Size the server with [references/tuning.md](references/tuning.md).
2. Write `<name>.toml` with `model`, `port` (one no other profile uses) and `args`, plus `env` and `idle_minutes` (above 0; a large number keeps a server up) when needed; every vLLM setting, `--gpu-memory-utilization` included, is a vLLM argument. A public model and what holds on any machine go in this skill's `profiles/`. A local checkpoint, anything personal, or one deployment's choices (GPUs, `--host`, `--revision`, a smaller GPU share beside training) go in `~/.config/vllm-serve/profiles/`, where `extends = "<profile>"` starts from a shipped profile and adds them.
3. `up` it, send one real request, check the answer, `down` it. Done when the answer is right, `up` reported no `foreign_cuda`, and the profile records where its arguments came from.

The shipped profiles are in `profiles/`, each opening with comments on what it serves and how it was sized.
