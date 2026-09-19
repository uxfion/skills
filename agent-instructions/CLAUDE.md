## Auto memory

The project root is the main worktree in a Git repository, the first entry of `git worktree list`, and the working directory otherwise. At session start, if `.memory/MEMORY.md` exists under that root and is not already loaded, read it and consult relevant memory files through its index.

If your memory directory is not that `.memory/`, check existing memories for a prior decision before asking whether to switch. Respect a recorded refusal unless the user changes it, and do not ask again for an already approved switch. If no decision exists, ask once at session start when the shared index exists, or otherwise when you first have a memory to save. Also ask whether to move existing memories if the current directory holds any and migration has not already been decided.

On agreement: create `.memory/`, merge `autoMemoryDirectory` with its absolute path into the project's effective `.claude/settings.local.json` (normally at the main worktree root), preserving other settings. Move memories only if agreed, merge both indexes if needed, and reconcile conflicting files without overwriting distinct facts. Use the shared directory for the rest of the session and verify that subsequent sessions load it. If the user declines, save that decision as a `project` memory in the current memory directory so you do not ask again.

If permissions block a memory update, request access through the available approval mechanism and retry if granted. If the update ultimately cannot be completed, including when approval is unavailable or denied, report what could not be saved and why. Apply this equally to automatic memory and explicit requests to remember; never silently skip a failed update or claim it succeeded.


## When executing Python code or managing Python environments or dependencies, always use `uv`.
Never invoke directly: `python` `python3` `pip` `pip3` `pip-tools` `poetry` `conda` `virtualenv` `python -c`.

- **Project** (`pyproject.toml`) — `uv add PKG`, `uv run script.py`
- **Standalone script** (reusable, has deps) — deps inline (PEP 723) via `uv add PKG --script x.py`, then `uv run x.py`
- **One-off** (no file) — `echo 'CODE' | uv run -`, or heredoc `uv run - <<'PY' … PY`  (never `python -c`)

Details → uv-python skill.

---
`hf` and `gh` cli are installed and authenticated. Use them within the scope of the current task’s authorization.

