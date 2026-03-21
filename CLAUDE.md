# CLAUDE.md

This file provides guidance for AI agents working with code in this repository.

## Overview

This is a collection of Claude Code skills (reusable automation modules). Each skill lives in its own directory with a `SKILL.md` frontmatter file that defines trigger conditions and usage instructions.

## Project Structure

- Each skill is a self-contained directory (e.g., `sub2api-usage/`, `uv-python/`)
- `SKILL.md` in each directory defines the skill's name, trigger description, and usage guide
- Skills use PEP 723 inline script metadata for dependencies — no `pyproject.toml` or `requirements.txt`

## Running Scripts

All Python scripts use `uv run` exclusively. Never use pip, poetry, or conda.

```bash
# Run a standalone script (dependencies declared inline via PEP 723)
uv run <script>.py

# Example: fetch Sub2API usage data
uv run sub2api-usage/scripts/fetch_usage.py
uv run sub2api-usage/scripts/fetch_usage.py --report
```

## Skills

### sub2api-usage
Queries Sub2API for token usage, costs, and rate limits. Requires `SUB2API_URL`, `SUB2API_ADMIN_KEY`, and `SUB2API_USER_ID` in `sub2api-usage/.env`. Main script outputs JSON; `--report` mode compares against a saved snapshot for delta reporting. Delta is only valid within the same day — cross-day snapshots yield `delta: null` with a `delta_note` explanation.

### uv-python
Reference skill documenting `uv` commands for Python package management and script execution. Contains only a `SKILL.md` with no scripts.

## Conventions

- Environment variables are loaded from a `.env` file in the skill's root directory
- `.env` files are gitignored — never commit them
- `snapshot.json` (used by sub2api-usage for delta reports) is also gitignored
- Scripts output structured JSON for agent consumption; human-readable formatting goes in `test/` scripts
- SKILL.md should use paths relative to the skill directory — never hardcode agent-specific paths (e.g., `.claude/skills/`)
