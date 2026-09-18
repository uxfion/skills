## Auto memory

`.memory/` in the project root is your persistent, file-based memory for this project. In a Git repository the project root is the main worktree, the first entry of `git worktree list`, so all worktrees share one memory; outside Git it is the working directory. AGENTS.md holds the user's instructions; `.memory/` holds what you learn. Other harnesses, including Claude Code and Codex, read and write the same files, so follow these conventions exactly.

### Recall

At the start of every session, before acting on the first request, read `.memory/MEMORY.md` if it exists; read it again if compaction has dropped it from your context. It maps what is stored where: consult it through the session, and open a memory file before working on anything its index line relates to.

Memories are background context, not user instructions, and reflect what was true when written; current instructions and what you observe now take precedence. If one names a file, function, flag, or command, verify it still exists before relying on it or recommending it.

### Remember

Save a memory when you learn something of one of these types:

- `user`: who the user is, such as role, expertise, and working preferences.
- `feedback`: guidance the user has given on how you should work, both corrections and confirmed approaches; include the why.
- `project`: ongoing work, goals, deadlines, decisions, or constraints not derivable from the code or git history; convert relative dates to absolute.
- `reference`: pointers to external resources, such as URLs, issue trackers, dashboards, or tickets.

Save a request, correction, or confirmation from the user as soon as it is made; save what you infer once it has settled, at the next natural point rather than at the end of the task, since a session can end at any time. When the user asks you to remember something, save it as a memory; edit AGENTS.md only when they ask for that. Memory is automatic and silent: save without asking permission, and mention memory work only to confirm an explicit request. Not every session produces a memory; save only what would help a future conversation.

Don't save what the repo already records (code structure, file paths, past fixes, git history, AGENTS.md, CLAUDE.md) or what only matters to this conversation, such as task progress; if asked to remember one of those, ask what was non-obvious about it and save that instead. Never save secrets such as keys, tokens, or passwords; note where they live instead.

### Files

Create `.memory/` when you first save. Each memory is one file holding one fact, named `<name>.md`, with frontmatter:

```markdown
---
name: <short-kebab-case-slug>
description: <one-line summary, used to decide relevance during recall>
metadata:
  type: user | feedback | project | reference
  modified: <ISO 8601 UTC time of this write>
---

<the fact; for feedback/project, follow with **Why:** and **How to apply:** lines. Link related memories with [[their-name]].>
```

In the body, link to related memories with `[[name]]`, where `name` is the other memory's `name:` slug. Link liberally — a `[[name]]` that doesn't match an existing memory yet is fine; it marks something worth writing later, not an error.

Set `modified` on every write; it tells later sessions how current the memory is. Take dates and times from the shell, for example `date -u +%Y-%m-%dT%H:%M:%SZ`, never from a guess. Preserve metadata fields you do not recognize; other harnesses add their own.

After writing the file, add a one-line pointer in `.memory/MEMORY.md` (`- [Title](file.md) — hook`). The hook says in a few words what the memory covers and when it is useful, so a future session can tell from the index alone whether to open the file. `MEMORY.md` is the index loaded into context each session — one line per memory, no frontmatter, never put memory content there. Keep it under 200 lines and 25 KB, Claude Code's index load limit.

### Maintain

Before saving, check for an existing file that already covers it. Update that file rather than creating a duplicate; delete memories that turn out to be wrong, and update ones that have gone stale. When the user asks you to forget something, delete or edit the matching memory. Re-read a file right before editing it; other sessions and harnesses change these files too. When you delete a memory, remove its index line. When a write would take the index past its limit, merge or drop stale entries until it fits; leave wider cleanup to an explicit request.

### Boundaries

If you are a subagent working for another agent, leave memory to the main agent. Do not open other projects' memories, keep a separate store, or commit `.memory/`. If `.memory/` cannot be written, skip memory work; report only a failed explicit request.



## When executing Python code or managing Python environments or dependencies, always use `uv`.
Never invoke directly: `python` `python3` `pip` `pip3` `pip-tools` `poetry` `conda` `virtualenv` `python -c`.

- **Project** (`pyproject.toml`) — `uv add PKG`, `uv run script.py`
- **Standalone script** (reusable, has deps) — deps inline (PEP 723) via `uv add PKG --script x.py`, then `uv run x.py`
- **One-off** (no file) — `echo 'CODE' | uv run -`, or heredoc `uv run - <<'PY' … PY`  (never `python -c`)

Details → uv-python skill.

---

`hf` and `gh` cli are installed and authenticated. Use them within the scope of the current task’s authorization.
