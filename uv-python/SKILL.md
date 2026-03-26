---
name: uv-python
description: Use uv exclusively for all Python package management, environment setup, and script execution. Trigger whenever the user installs/removes Python packages, runs Python scripts, manages dependencies, creates Python projects, or mentions python/pip/poetry/conda/pip-tools.
---

# Python Package Management with uv

Use `uv` exclusively. Never use pip, pip-tools, poetry, virtualenv or conda for dependency management.

## Project (has `pyproject.toml` or `requirements.txt`)

- Init new project: `uv init`
- Add dep: `uv add <package>`
- Remove dep: `uv remove <package>`
- Sync env: `uv sync`
- Run script: `uv run <script>.py`

## Standalone Script (outside a project, or temporary use but need keep the file)

Use PEP 723 inline metadata to declare dependencies inside the script:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
# ]
# ///
```

- Or add dep: `uv add <package> --script <script>.py`
- Or remove dep: `uv remove <package> --script <script>.py`
- Run: `uv run <script>.py`

## One-Off Code (no file saved, temporary execution)

```bash
uv run - <<'EOF'
<script>
EOF
```

## Other Commands

- Run a tool temporarily: `uvx <tool>`
- Install a tool globally: `uv tool install <tool>`
- Run with specific Python version: uv run --python 3.10 <script>.py
