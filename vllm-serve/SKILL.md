---
name: vllm-serve
description: Runs models as OpenAI-compatible vLLM servers on this machine's GPUs or on a server reached over ssh, each started on demand and stopped when idle. Use when a task or another skill needs a model server (the paddleocr skill's VL model is one), to see or stop running servers, to add a model, or to deploy one on a GPU server shared with other people.
---

# vLLM serve

One vLLM installation (a uv tool) serves every model a machine runs, each through a profile and a server of its own: started when someone asks for it, shared by everyone who asks while it runs, and stopped after a spell without requests, giving the GPUs back. Installing or upgrading vLLM, and a server that will not start → [references/install.md](references/install.md). A machine other people use, or one reached over ssh → [references/shared-machines.md](references/shared-machines.md), before the first install or `up` there.

**Calling.** Start every shell call with this statement, filled in with this file's absolute directory, then the commands: `set -o pipefail; export PATH="<this directory>/scripts:$PATH";` — `serve.py <word> …` is then found from anywhere in the call, your working directory stays where it is, and a failure anywhere in a pipe sets the call's exit code. `serve.py -h` lists the words and the profile keys; `serve.py <word> -h` is each word's reference: its lines' fields, its exit codes. stdout is data, one JSON line per profile; a line reporting a problem carries a `hint`, the next step. Keep stderr: a start's progress, the warning that the last start failed, and on exit 2 a last line `{code, detail, hint}` saying why nothing was tried.

## Use a server

```bash
serve.py up <profile>
CUDA_VISIBLE_DEVICES=4,5 serve.py up <profile> --data-parallel-size 2    # GPUs and vLLM arguments for this start
```

Speak the OpenAI API at `url` with `model` as the model name. `up` waits until the server answers or the start fails: the first `up` of a profile downloads its weights, and a start takes from one or two minutes (a small model) to several (a 27B model, longest on the first start after an install), so call it in the background for anything interactive. Call `up` again before each new batch of work: a server you used an hour ago has stopped, and `up` resets its idle clock. Arguments and environment passed to `up` shape this start only; a choice that must hold at the next start, which another caller may trigger after an idle stop, belongs in a profile.

### When `up` says more

What to do beyond each line's `hint`:

- `differs`: use the server as it runs; to start it as you asked, `down` it once `status` shows it idle, then `up`.
- `foreign_cuda`: report it to the user and fix it per install.md; then `down` and `up`, until `up` shows none.
- `server_failed`: read the log named in `detail`. A long log goes to a background subagent on a cheap model (Claude Code `model: "sonnet"`, Codex `luna`), sent with:

  ```text
  You are reading a vLLM server's log for the vllm-serve skill. The log: <its path; on a server, the ssh command that prints it>. Read all of it, then <vllm-serve's directory>/references/install.md, section "A server that does not start, or loads foreign CUDA". Reply with the log lines that give the cause, verbatim, and the entry of that section they match, or "no entry"; when no line gives a cause, "no cause" and the log's last 30 lines. Done when every traceback in the log is accounted for in your reply. Write no files, send no subagents, no git. If you cannot read the log, say what you tried.
  ```

  Find the lines it quotes in the log before you act on them; then act on the entry, and `up`. No entry matches: work from the cause lines, then tell the user the cause and the fix, as a dated hint for install.md.
- `the last start of <profile> failed` on `up`'s stderr, or `"failed": true` in a stopped profile's `last` in `status`: read that start's log, named there, as for `server_failed`. After `up`'s warning a new start is already under way: while the cause is still there, `down` it and fix that first.
- `port_busy`:
  - A profile of ours serving the model you need, where you need it: `up` that profile instead.
  - Another profile of ours, idle and no deployment others use (one shows a `host` and a long `stops_after_minutes`): `down` it, then `up`. Two profiles meant to run together: give the deployment profile a port of its own, then `up`.
  - Another program: the hint's command finds it, and `ps -o user= -p <pid>` its login (no pid shown: another login's).
  - Stopping a server someone uses, or one the user started by hand, is the user's call.
- `not_permitted` on `up`'s stderr: a state file is another login's; it goes to the user for `chown -R`, then `up`.

An `up` in the background that has not returned: `status <profile>` gives the phase, the log shows whether the start moves (a download's progress, the step it has reached), and `nvidia-smi` whether the server's GPU memory still grows. It is stuck when none of these has moved for well past the longest phase in install.md's Timings and "A start that goes quiet": `down` it, and handle the `server_failed` the waiting `up` returns.

## See and stop

```bash
serve.py status <profile>    # every profile without one
serve.py down <profile>      # several at once; -a: all of them
serve.py status | jq -c 'select(.phase == "running" and .idle_for_minutes >= 30)' | serve.py down -    # the idle ones
```

`nvidia-smi` shows what else holds the GPUs. Stop a server when the user wants the GPUs back, once `status` shows it idle. A broken profile file makes `status` exit 1, and under `pipefail` the idle-stopping pipeline with it, after that pipeline has stopped every server it lists.

## Add a model

1. Take the launch arguments from the model's vLLM recipe (`models/<org>/<model>.yaml` in vllm-project/recipes) and, where the program that will call the model ships its own server settings (PaddleX does for PaddleOCR-VL), from those; the caller's tuning wins. Recipes date: check their version notes against the installed vLLM. Size the server with [references/tuning.md](references/tuning.md).
2. Write `<name>.toml` with the keys `serve.py -h` lists, at a `port` no other profile uses. A public model and what holds on any machine go in this skill's `profiles/`; a local checkpoint, anything personal, or one deployment's choices (GPUs, `--host`, `--revision`, a smaller GPU share beside training) in `~/.config/vllm-serve/profiles/`, where `extends = "<profile>"` starts from a shipped profile and adds them.
3. `up` it, send one real request, check the answer, `down` it. Done when the answer is right, `up` reported no `foreign_cuda`, and the profile opens with comments on what it serves, where its arguments came from and how it was sized, as the shipped ones in `profiles/` do.
