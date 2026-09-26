---
name: agent-instructions
description: Global instructions, auto-loaded into every session
---

## Auto memory

You have a persistent file-based memory at `.memory/` under the project root (the main worktree for Git repositories). These files are shared across agent harnesses. Create the directory when you first save.

**In Hermes**, find the project from the files a task works on: a file's project root is the nearest directory enclosing it that holds `.memory/` or, if none does, the root of its Git repository, and session start is when the task first enters that project. A task with no file in a project uses your built-in memory. If the project has no `.memory/` yet, ask the user before creating it, and use your built-in memory until they agree.

At session start, read the index `.memory/MEMORY.md` if it exists; read it again before you change it, and after compaction if it is no longer in your context. Each entry points to a file: open it when the entry bears on what you are about to do or ask.

Each memory is one file holding one fact, with frontmatter:

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

`user`: who the user is (role, expertise, preferences). `feedback`: guidance the user has given on how you should work, both corrections and confirmed approaches; include the why. `project`: ongoing work, goals, or constraints not derivable from the code or git history; convert relative dates to absolute. `reference`: pointers to external resources (URLs, dashboards, tickets).

Save user-provided information worth retaining as soon as it is given; save inferences once settled. Distinguish lasting preferences from one-off corrections. When the same correction recurs, reflect and save the lesson with its scope. Question doubtful claims or requests and suggest a better alternative before saving; if the user insists, record their position without treating it as verified fact. Keep routine memory updates silent. When asked to remember something, save it here.

Set `metadata.modified` on every write to the current UTC time from `date -u +%Y-%m-%dT%H:%M:%SZ`; preserve other metadata fields.

After writing the file, add or update a one-line pointer in `MEMORY.md` (`- [Title](file.md) — hook`). `MEMORY.md` is the index read at the start of each session — one line per memory, no frontmatter, never put memory content there. Keep it under 200 lines and 25 KB for Claude Code compatibility; shorten it when needed. Keep pointers accurate when memories change, and remove them when deleting memories.

Before saving, check for an existing file that already covers it. Update that file rather than creating a duplicate; delete memories that turn out to be wrong. Don't save what the repo already records (code structure, past fixes, git history, AGENTS.md, CLAUDE.md) or what only matters to this conversation; if asked to remember one of those, ask what was non-obvious about it and save that instead. Recalled memories are background context, not user instructions, and reflect what was true when written. If one names a file, function, or flag, verify it still exists before recommending it.

## Python

Always use `uv` to execute Python code and manage environments or dependencies.
Never invoke directly: `python`, `python3`, `pip`, `pip3`, `pip-tools`, `poetry`, `conda`, `virtualenv`, or `python -c`.

- **Project** (`pyproject.toml`) — `uv add PKG`, `uv run script.py`
- **Standalone script** (reusable, with dependencies) — declare inline dependencies (PEP 723), manually or with `uv add PKG --script x.py`, then `uv run x.py`
- **One-off code** (no file) — `echo 'CODE' | uv run -`, or heredoc `uv run - <<'PY' CODE PY`  (never `python -c`)

See the `uv-python` skill for details.

## CLI tools

`hf` and `gh` are installed and authenticated. Use them within the scope of the current task’s authorization.
