# AGENTS.md

Personal agent skills plus the source files for global agent instructions. See README.md for the layout.

- In a `SKILL.md`, use paths relative to the skill directory — never agent-specific ones (e.g. `.claude/skills/`).
- When adding or removing a skill, update the list in README.md.
- The global instruction sources are `agent-instructions/CLAUDE.md` and `agent-instructions/AGENTS.md`; once a change to them is confirmed, sync the global copies (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`). Change the Auto memory section only per `agent-instructions/auto-memory-update.md`.
- `agent-instructions/references/` is a checksummed source archive — don't edit it.
