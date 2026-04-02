---
name: uv-python
description: Use uv exclusively for all Python package management, environment setup, and script execution. Trigger whenever the user installs/removes Python packages, runs Python scripts, manages dependencies, creates Python projects, or mentions python/python3/pip/pip3/poetry/conda/pip-tools/virtualenv.
---

# Use Python with uv

Use `uv` exclusively. Never use pip, pip3, pip-tools, poetry, virtualenv or conda for dependency management. Never use `python` or `python3` directly to run scripts.

## Choosing the Right Approach

| Scenario | Approach |
|----------|----------|
| Working in a directory with `pyproject.toml` | **Project** — use `uv add`, `uv run` |
| Reusable script that needs specific packages | **Standalone Script** — use PEP 723 inline metadata |
| Quick throwaway code, no file needed | **One-Off Code** — pipe to `uv run -` |

## Project (has `pyproject.toml`)

- Init new project: `uv init`
- Add dep: `uv add <package>`
- Add dep with extras: `uv add "package[extra]"`
- Add dev dep: `uv add --dev <package>`
- Remove dep: `uv remove <package>`
- Sync env: `uv sync`
- Run script: `uv run <script>.py`
- Run module: `uv run -m <module>`

## Standalone Script (reusable script outside a project)

Use PEP 723 inline metadata to declare dependencies inside the script:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
# ]
# ///
```

- Add dep via CLI: `uv add <package> --script <script>.py`
- Remove dep via CLI: `uv remove <package> --script <script>.py`
- Run: `uv run <script>.py`

## One-Off Code (no file saved, temporary execution)

Use instead of `python -c "code"`:

```bash
uv run - <<'EOF'
<script>
EOF
```

On Windows (PowerShell), use a temp file instead since heredoc is not supported:

```powershell
$code = @'
<script>
'@
$code | uv run -
```

## Other Commands

- Run with an extra package ad-hoc: `uv run --with <package> <script>.py`
- Run a tool temporarily: `uvx <tool>`
- Install a tool globally: `uv tool install <tool>`
- Run with specific Python version: `uv run --python 3.10 <script>.py`
- Install a specific Python version: `uv python install 3.12`
- Create a virtual environment: `uv venv`
- Install from requirements.txt: `uv pip install -r requirements.txt`
