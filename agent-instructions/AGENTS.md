## Auto memory

`.memory/` at the project root (the Git root, or the working directory outside Git) holds your notes for future sessions in this project. It complements AGENTS.md: the user writes instructions there; you write what you learn here. Other harnesses, including Claude Code and Codex, share these files, so follow the conventions below exactly. Memory is automatic and silent: create `.memory/` when you first save, and neither ask permission for nor announce memory work. If the store cannot be written, skip memory work; report only a failed explicit request. Do not open other projects' memories, keep a separate store, or commit `.memory/`.

### Remember

Save what a future session would need. Save a request or correction from the user as soon as it is made; save what you infer once it has settled, at the next natural point rather than at the end of the task. One memory per file, of one kind:

- `user`: the user's role, expertise, and working preferences
- `feedback`: corrections the user gave and approaches they confirmed
- `project`: ongoing work, deadlines, and decisions, with absolute dates
- `reference`: where to find information outside the project, such as an issue tracker or dashboard

Skip what the code already shows (architecture, file paths, debugging fixes), what AGENTS.md already says, secrets, session logs, and temporary progress. Update an existing memory rather than adding a duplicate; delete one that proves wrong. Not every session produces a memory. A rule the user wants every session belongs in AGENTS.md, added only when they ask.

### Files

`MEMORY.md` is the index; each memory is one topic file, `<type>_<topic>.md` in snake_case:

```text
.memory/
├── MEMORY.md            # index, one line per memory
├── user_role.md         # one memory
├── feedback_testing.md  # one memory
└── ...
```

A memory file starts with this frontmatter:

```yaml
---
name: <filename without .md>
description: <one line: what this remembers and when it applies>
metadata:
  type: user | feedback | project | reference
  modified: <ISO 8601 write time>
---
```

Set `modified` on every write and preserve metadata fields you do not recognize; other harnesses add their own. The body states the fact and its scope; `feedback` and `project` add `**Why:**` and `**How to apply:**` lines. Link related memories as `[[name]]`.

`MEMORY.md` has no frontmatter, one line per memory: `- [Short title](user_role.md) — when this memory is useful`. Keep it under 200 lines and 25 KB, Claude Code's index load limit.

### Recall

Read `MEMORY.md` at session start and again after compaction if it has left context. It maps what is stored where: consult it through the session and open a memory file when the task relates to it. Memories record what was true when written (`modified` dates each). Verify a path, flag, or command a memory names before relying on it; current instructions and verified facts take precedence.

### Maintain

Re-read a file before editing it; other sessions and harnesses change these files too. Add an index line when creating a file and remove it when deleting one. When a write would take the index past its limit, merge or drop stale entries until it fits; leave wider cleanup to an explicit request.



## When executing Python code or managing Python environments or dependencies, always use `uv`.
Never invoke directly: `python` `python3` `pip` `pip3` `pip-tools` `poetry` `conda` `virtualenv` `python -c`.

- **Project** (`pyproject.toml`) — `uv add PKG`, `uv run script.py`
- **Standalone script** (reusable, has deps) — deps inline (PEP 723) via `uv add PKG --script x.py`, then `uv run x.py`
- **One-off** (no file) — `echo 'CODE' | uv run -`, or heredoc `uv run - <<'PY' … PY`  (never `python -c`)

Details → uv-python skill.

---

`hf` and `gh` cli are installed and authenticated. Use them within the scope of the current task’s authorization.
