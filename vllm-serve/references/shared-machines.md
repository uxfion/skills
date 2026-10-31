# Shared and remote machines

A GPU server that other people use, reached over ssh with a personal login and no root. serve.py works the same there; what changes is where files go, which login runs things, which GPUs you take and who reaches the server. Those are judgement calls made with the user: the principles below come with what held on two such servers (8× H200, 2× RTX PRO 6000) in 2026-10 as dated hints.

## First deployment

1. Agree on the place with the user and make a `vllm-serve` directory there: the root. A root already there from an earlier deployment is used as it is: go on at step 6. Everything the deployment writes stays under it (uv and its Python, vLLM, the Hugging Face cache, every compile cache, serve.py's profiles, state and logs): shared servers often have a nearly full system disk, and other people's space is off limits.
2. Write `<root>/env.sh` and source it before every command on that machine, `ssh <host> '. <root>/env.sh && …'`, since non-interactive ssh reads no shell profile. Pointing `HOME` at the root moves every tool's files there at once, including those that ignore the XDG variables (FlashInfer's kernels, CUDA's `~/.nv/ComputeCache`, Triton's `~/.triton`):

   ```sh
   R=<root>                         # the directory agreed on
   export HOME=$R PATH=$R/bin:$R/.local/bin:$PATH UV_PYTHON_PREFERENCE=only-managed
   unset XDG_CACHE_HOME XDG_CONFIG_HOME XDG_DATA_HOME XDG_STATE_HOME XDG_BIN_HOME \
         UV_CACHE_DIR UV_TOOL_DIR UV_TOOL_BIN_DIR UV_PYTHON_INSTALL_DIR HF_HOME HF_HUB_CACHE
   ```

   A tool's own variable, already set in the login's environment, beats `HOME` (2026-10: an inherited `UV_CACHE_DIR` sent uv's downloads outside the root): look through `env` there and unset whatever points elsewhere. Leave `TMPDIR` alone: vLLM puts its IPC sockets there, and a socket path longer than 107 characters stops the server (2026-10). The login's own credentials are then out of sight: a gated model needs `HF_TOKEN` in `env.sh`, and `gh` or `git` run from the machine you work on.
3. Install uv into the root, which writes nothing outside it: `curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL=<root>/bin sh`.
4. Copy this skill's directory to `<root>/skill/` (`rsync -a <skill>/ <host>:<root>/skill/`). The skill stays installed on the machine you work from; serve.py runs beside the GPUs from this copy, reached over ssh: `ssh <host> '. <root>/env.sh && uv run <root>/skill/scripts/serve.py status'`. When the skill changes, refresh the copy the same way, after stopping its servers with the old copy (`down --all`, once `status` shows them idle): a newer serve.py may not recognise servers an older one started (2026-10-31: the run lock).
5. Install vLLM per [install.md](install.md), with `env.sh` sourced. Its check with a server is step 6, on the GPUs chosen there.
6. Choose the GPUs, write the deployment profile, `up` it, and check it from a client, as the sections below say. Run that `up` in the background: a large model's first start downloads its weights first, with the progress in the profile's log (`status` names it). Leave the server running: a deployment stays up after the check.

Done when a client on the network gets the model list from the server's address (Who reaches the server), and `status` shows the server on the chosen GPUs.

## Logins

- Work as the personal login; the root is that login's. Another login gets `not_permitted` there, naming the owner, for the root's files and for the servers the owner started, which still stop by themselves when idle.
- Steps that need root (removing a system package, `chown`, a directory under a root-owned path) go to the user as exact commands; check the result yourself afterwards.
- What you write (`env.sh`, profiles, notes) names no login, so the root can pass to another login: the user hands it over (`chown -R <login>: <root>`, as root), and nothing needs reinstalling.

## Which GPUs

- Look several times, a minute or so apart, before choosing: `nvidia-smi` lists memory, utilisation and processes per GPU, `ps -o user= -p <pid>` names a process's login, and `uvx nvitop` shows both at once. Between two runs of someone's job its GPUs look free for a moment (2026-10: another user's job took back four "free" H200s seconds after a start).
- Take GPUs nobody uses. A GPU another job uses lightly may be shared when the model fits in its free memory and the user agrees; whenever unsure, ask.
- How many, and data or tensor parallel: [tuning.md](tuning.md) (Parallel layout).
- `--gpu-memory-utilization` is a share of each GPU's total memory, and vLLM wants that much free on every GPU it uses: on shared GPUs, (free memory − a few GB) ÷ total, for the fullest of them.
- Name them in `CUDA_VISIBLE_DEVICES` by nvidia-smi's numbers.

## The deployment profile

Name it after the profile it extends, so that it takes that profile's place: `<root>/.config/vllm-serve/profiles/qwen38-27b.toml` (`HOME` being the root). Two profiles on one port cannot run at once, and `up` names the other in `port_busy`. Its comments say why each choice was made:

```toml
# qwen38-27b for <project>: GPU 1 (GPU 0 runs another user's training); LAN clients; weights pinned for comparable runs.
extends = "qwen38-27b"
idle_minutes = 120
args = ["--revision", "<40-character commit>", "--host", "0.0.0.0", "--max-num-seqs", "16"]
env = { CUDA_VISIBLE_DEVICES = "1" }
```

A full commit hash in `--revision` pins the weights: serve.py downloads that revision, and vLLM loads it offline. After a start without one, `<root>/.cache/huggingface/hub/models--<org>--<name>/refs/main` holds the commit it got.

## Who reaches the server

- `--host 0.0.0.0` lets other machines reach the server at this machine's address (`hostname -I`) and the profile's port, and `up` then reports `host`. Everyone on that network can use it unless `--api-key <key>` (or `VLLM_API_KEY` in the profile's env) guards it: the user decides. vLLM 0.32 logs no request content unless given `--enable-log-requests`.
- Check from a client on that network: `curl --noproxy '*' http://<address>:<port>/v1/models`. Refused there while it answers on the server: a firewall, which only root opens.
- Clients on other machines cannot `up`. After an idle stop the next batch needs one, `ssh <host> '. <root>/env.sh && uv run <root>/skill/scripts/serve.py up <profile>'`, run by the client or by you; or a large `idle_minutes` (100000 is ten weeks) keeps the server until `down`. The user chooses, since a running server holds its GPUs.
- A server outlives the ssh session that started it, at any phase; if `up` was cut off, the next `up` waits for the same start. A start that hangs with nobody watching gives the GPUs back 30 minutes after vLLM started, and the next `up` there, or `status`, says that it failed.
