# AGENTS.md

Personal agent skills plus the source files for global agent instructions. See README.md for the layout.

- In a `SKILL.md`, use paths relative to the skill directory — never agent-specific ones (e.g. `.claude/skills/`).
- When adding or removing a skill, update the list in README.md.
- Issue drafts live in `docs/issues/{skill}.md`: problems met while using a skill and the user's passing pain points, logged the moment they come up with enough of the scene (what was run, what was seen, why it hurt, the user's exact words) to reconstruct it later; they are triaged together into a spec or a skill change.
- Design specs live in `docs/specs/{YYYYMMDD}-{topic}-spec.md`, dated the day the design was settled. A spec is a snapshot: correct it while its implementation is in progress; once that is done it is frozen — a redesign gets a new dated spec, and the old one gains only a `Superseded by …` line at the top. For current behaviour, read the skill itself.
- The global instruction sources are `agent-instructions/CLAUDE.md`, `AGENTS.md` and `HERMES.md`; once a change to them is confirmed, sync the global copies (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.hermes/skills/agent-instructions/SKILL.md`). `HERMES.md` is `AGENTS.md` plus frontmatter and one `**In Hermes**` paragraph after the first Auto memory paragraph: after any change to `AGENTS.md`, regenerate it so that removing those two leaves `AGENTS.md` byte for byte. Change the Auto memory section only per `agent-instructions/auto-memory-update.md`.
- `agent-instructions/references/` is a checksummed source archive — don't edit it.
