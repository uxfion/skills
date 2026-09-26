# Auto memory update guide

This guide governs every change to the Auto memory instructions of Claude Code, Codex and Hermes, which share one memory convention: `.memory/` under each project root. It records how the harnesses divide the work, the exact current text, the user's intent and the trade-offs already settled, so the next change need not replay past conversations. It is maintenance background, never loaded into a session, and covers only the Auto memory sections, not the Python and CLI rules beside them. Read the next two sections first; the rest is reference. The user's own words are quoted in Chinese, verbatim.

Current live text: Codex uses [AGENTS.md](AGENTS.md), Hermes uses [HERMES.md](HERMES.md) generated from it, Claude Code uses the Auto memory section of [CLAUDE.md](CLAUDE.md). The Codex text is adapted from the [Fable 5.1 Memory excerpt](references/auto-memory/fable-5.1-memory-section.md); its first version confirmed by the user is commit `238b36a37cad7808383e7ee0b7acc5ebaa409009` (2026-09-19). The exact text below reproduces the current version; when the upstream text changes, adapt by intent rather than replaying mechanically.

## How the harnesses divide the work

All three harnesses share the `.memory/` under each project root. Their instructions differ on purpose; before changing anything, work out why they differ.

| Harness | Source file → global location | Memory mechanism | What this repo adds |
| --- | --- | --- | --- |
| Claude Code | `CLAUDE.md` → `~/.claude/CLAUDE.md` | Native auto memory: the harness injects the Memory prompt, loads the index at session start and stamps `modified` on writes; by default it stores memory in one central place outside the project | Only switches the storage to the project's `.memory/`, moving the old memories there; see "The Claude Code storage switch" below |
| Codex | `AGENTS.md` → `~/.codex/AGENTS.md` | Native memory deliberately switched off (the user finds it poor); the Auto memory section makes it replicate Claude Code's auto memory | Changes 1–7 to the Fable 5.1 original; Codex is launched in a project and creates `.memory/` on first save |
| Hermes | `HERMES.md` → `~/.hermes/skills/agent-instructions/SKILL.md`, added to `skills.auto_load` | No project concept: on messaging platforms its working directory is fixed at the home directory, and one session moves freely between workspaces; it also has its own built-in memory | The full `AGENTS.md` plus one paragraph; see "The Hermes adaptation" below |

The user, 2026-09-26: 「我就是要codex原生记忆关的，因为它那个不好用，然后就去复刻 Claude Code，但是 Claude Code Auto memory是存在一个统一的位置的，没有存在项目下面……Hermes为什么要单独来呢？是因为他没有一个项目的概念」. So "ask the user before creating `.memory/`" belongs to Hermes alone; Claude Code's one question is the storage switch; Codex does not ask.

## How to update

Two things start an update: a new upstream Memory text, a new model release included (e.g. Opus 5.5 on 2026-09-22); or a change the user asks for in one harness's text, which then has to reach the others: 「我可能改了一处地方，让你对某一处地方进行了修正，然后对应的各种 harness 之间也要同步」. Both follow the same steps; only step 2 differs.

1. **Read this guide and the three source files.** This file records intent; `AGENTS.md`, `HERMES.md` and `CLAUDE.md` are the live text; Git keeps the history. Never paste this background into a global prompt.
2. **Pin down the change.**
   - *Upstream*: fetch the text the user names and pin its revision. Prefer the prompt archive and official docs the user names; do not reverse-engineer the installed Claude Code binary. Keep the old base, then compare old upstream, new upstream and the current adaptation, staying on the Memory section and re-checking the official mechanisms it touches: first see what upstream actually changed, then judge item by item whether each adaptation is still needed. Rules the new version already covers are not added again; new features are not copied to Codex or Hermes automatically.
   - *User request*: start from the user's words. Work out the intent behind them and which text they touch, and keep the words verbatim for this guide.
3. **Check against the harness.** `AGENTS.md` and the Hermes paragraph give Codex and Hermes what Claude Code does natively: make one table with the user's columns 机制 | 参考 harness 细节 | 依据 | 现状 | 修改意见 (mechanism | what Claude Code does | evidence: observed, system prompt or docs | how the current text covers it | proposed change), write 无 in any empty cell, and fill only what Codex and Hermes genuinely lack. `CLAUDE.md` serves Claude Code itself: check only the Claude Code facts a clause depends on, without the table.
4. **Draft and discuss one change at a time.** Keep the adaptations and preferences still needed, in the structure and wording of the current base, adding as little process as possible. For each change, show the user the original and the proposed text and say what is added, changed or removed and why; change it after discussion, and do not re-ask background already settled.
5. **Carry each settled change across the harnesses.** Whichever file it started in, ask whether the other harnesses have the same need. Where they do, apply it in their own terms, since the texts differ on purpose; where they do not, tell the user why, so each difference stays deliberate.
6. **Check the execution cost.** Does the final text read only what is needed, save promptly, avoid duplicate writes, ask only on real doubt? Has a native mechanism been turned into an extra duty? Do not trade clarity for the shortest wording; no dedicated test or audit framework is needed.
7. **Finish the repo, record, then sync.** Keep a Git baseline to roll back to and do not overwrite other uncommitted work; during discussion change only the repo copies. Once `AGENTS.md` is final, regenerate `HERMES.md` (the check is in the root `AGENTS.md`) and confirm the Hermes paragraph still fits the paragraphs around it. Record the outcome here: the harness's section gets the exact new text, the intent with the user's words, and why it is written that way; options not taken go to the rejected table; changed facts are updated, in the source index too; no log of every edit. After the user's final confirmation, sync the global copies that changed: `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.hermes/skills/agent-instructions/SKILL.md` (changing Hermes needs the user's consent item by item and takes effect in a new session).

A prompt to hand to the next model (drafted 2026-09-26 to replace the user's earlier prompt, which covered only upstream updates; the user may reword it):

> 请按 `agent-instructions/auto-memory-update.md` 更新 Auto memory 指令。触发可能是上游出了新的 Memory 原文，也可能是我要改某个 harness 的某处文本。上游更新时，先比较存档的旧原文、新原文和当前适配；我提出修改时，先弄清我的意图和它涉及哪段文本。Codex 的 `AGENTS.md` 和 Hermes 的段落要对照 Claude Code 的实际机制逐项核对，只补真正缺的；Claude Code 的 `CLAUDE.md` 只管存储切换，不要扩大到它的原生记忆管理。保持精简、干练、优雅且执行高效。每处改动逐条给我看原文和修改建议，讨论确认后再改；改定后检查其他 harness 是否需要同步，把意图记进指南，最后再同步全局。

## Goals and principles

The body began as the user's draft from the official docs; the user then chose Claude Code's tuned Memory prompt as the base, keeping what was useful from the docs and the draft, to give Codex automatic memory, and since 2026-09-26 the same body also serves Hermes. The original's tuning is kept by default; this is a design choice, not a claim that performance tests proved the original best.

- **Concise, crisp, elegant, efficient in execution.** Do not grow the rules blindly, and do not add process for every hypothetical edge case. Efficient execution means remembering promptly, reading on demand, avoiding duplicate writes and pointless questions, not merely fewer words.
- **Fill real gaps.** Separate what the prompt asks of the model from what the harness already does; add only the steps a harness lacking that mechanism is missing. Judge what is missing against what Claude Code actually does for the model: its system prompt, the reminders and refusals seen in a session, the official docs, marking which were observed and which are only documented. Not every mechanism in the docs has to become prompt text.
- **Fill only the side that lacks the mechanism.** Claude Code's memory runs on its native mechanism, and `CLAUDE.md` only handles the storage switch; sharing files does not mean adding the same compensating rules there. Codex and Hermes share the body of `AGENTS.md`; Hermes adds one paragraph. A rule that holds for one harness is not generalised to the others.
- **Keep the intent, not the old wording.** Additions the new version already covers are merged or removed; do not restore something because an old draft had it, and do not keep rewriting a clear rule to save a few words.

## Changes to the Fable 5.1 original (`AGENTS.md`, shared by Codex and Hermes)

### 1. Storage location and sharing across harnesses

The original names Claude Code's private directory, guarantees it exists and says to write with the `Write` tool. The adaptation uses `.memory/` under the project root, created on first save, and says in neutral terms that it is shared across harnesses.

Replace all text of the original's first paragraph before `Each memory is one file…` with the following standalone paragraph; keep `Each memory…` and the template after it as a new paragraph:

```text
You have a persistent file-based memory at `.memory/` under the project root (the main worktree for Git repositories). These files are shared across agent harnesses. Create the directory when you first save.
```

This adapts the text to how the memory is actually shared. Do not copy the original's personal absolute path, its assumption that the directory exists, or the `Write` tool name; Codex uses its own file tools and needs no separate tool-call lesson in the prompt.

`the main worktree for Git repositories` is not in the Fable Memory original; it makes linked worktrees share memory with the main worktree, matching the sharing behaviour the official docs described at the time. The user worried that worktree instructions would get complicated and agreed to keep this qualifier while dropping operational detail such as `git worktree list`. Do not expand it into a path-discovery procedure; before removing it, consider whether memory would split into several stores.

### 2. Reading the index explicitly, recall on demand

The original says the index is loaded every session, which the Claude Code harness does. The adaptation gives Codex and Hermes the read at session start, the re-reads before changing it and after compaction, and reading on demand while working. Insert between the storage paragraph and the `Each memory…` paragraph:

```text
At session start, read the index `.memory/MEMORY.md` if it exists; read it again before you change it, and after compaction if it is no longer in your context. Each entry points to a file: open it when the entry bears on what you are about to do or ask.
```

Change 5 also turns `loaded into context each session` into `read at the start of each session`, so a step the model must take is not described as automatic platform behaviour. This does not ask for scanning all memories on every task or re-reading unconditionally after every compaction. If Codex later does these steps natively, reconsider whether they are still needed.

Adjusted 2026-09-26. The original sentence: ``At session start, read `MEMORY.md` if it exists; read it again after compaction if it has left context. Use the index to find and read relevant memory files as you work. All memory paths below are relative to that directory.`` Four changes, each grounded in a mechanism Claude Code provides and Codex and Hermes lack:

- **Path**: `that directory` could point back to `.memory/` or to the project root. Once `HERMES.md` inserted the Hermes paragraph between the first and second paragraphs, the nearest directory became the project root, and the sentence just before was about Hermes's built-in memory (whose file is also called `MEMORY.md`). Now the first use names `.memory/MEMORY.md` directly and calls it the index.
- **Re-read before changing**: Claude Code's Edit/Write tools refuse to write a file not read first and report when someone else changed it; Codex and Hermes have no such guard. The memory is shared by several harnesses, and writing back a stale index wholesale drops entries someone else just added.
- **When to open memory files**: Claude Code loads the index automatically, and its system prompt anticipates harness recall that picks relevant memories. Without these, "relevant … as you work" is too broad: the model reads the index and then works from defaults. Now a file is opened when its entry bears on what the model is about to do or ask; entries whose hook already settles the matter need not be opened.
- **Wording**: in `if it has left context`, "left" means departed, but it can be read as "remaining" or as the NLP term *left context*; it is now `if it is no longer in your context`.

To reproduce the historical base `238b36a`, use the original sentence.

### 3. When to save, independent judgement, scope

Kept from the draft: save user information worth keeping promptly, save inferences once settled, keep routine updates silent, save here when asked to remember. The user also stressed:

- What the user provides can be wrong or unreasonable; "please remember" is no reason to stop judging. On a doubtful point, name the problem and suggest a better option first; if the user insists, record it as the user's position, not as verified fact.
- One correction may concern only this answer or behaviour and must not turn into a permanent rule automatically. An explicit lasting request need not wait for a second time either.
- The same correction recurring (twice or more) should trigger reflection and prompt saving of the lesson, with its scope.

Insert after the four memory types and before the index paragraph:

```text
Save user-provided information worth retaining as soon as it is given; save inferences once settled. Distinguish lasting preferences from one-off corrections. When the same correction recurs, reflect and save the lesson with its scope. Question doubtful claims or requests and suggest a better alternative before saving; if the user insists, record their position without treating it as verified fact. Keep routine memory updates silent. When asked to remember something, save it here.
```

This does not require investigating, asking about or verifying everything on each save; only doubtful content is questioned. The original `feedback` type already covers corrections and confirmations; no new category is needed.

### 4. Timestamp and metadata

Add one line after `metadata.type` in the template, indented two spaces like `type`:

```text
  modified: <ISO 8601 UTC time of this write>
```

Insert after the when-to-save paragraph and before the index paragraph:

```text
Set `metadata.modified` on every write to the current UTC time from `date -u +%Y-%m-%dT%H:%M:%SZ`; preserve other metadata fields.
```

Three sources meet here: the original supplies the `metadata.type` template; the official docs snapshot says the Claude Code harness writes an ISO 8601 `modified`, and the official changelog records `Added an ISO modified timestamp to memory file frontmatter` in 2.1.214, matching the docs (the earlier 2.1.75 has `Added last-modified timestamps to memory files`, without mentioning frontmatter); the draft used `metadata.modified`, and that convention is kept. The harness, not the model following a prompt, writes the timestamp, so this rule need not be added to Claude Code's `CLAUDE.md`. Neither the docs nor the changelog require this nesting or UTC, and the Fable Memory section has no time field. Do not call this project's convention the official complete format.

Observed on 2026-09-19 in Claude Code v2.1.278: when the harness writes a memory file with frontmatter, the timestamp lands in `metadata.modified` (UTC, millisecond precision, e.g. `2026-09-19T14:00:32.271Z`), alongside `metadata.node_type` and `metadata.originSessionId`. The project's nesting therefore matches the harness's actual behaviour, and `preserve other metadata fields` is what keeps those fields; Codex's second-precision `date -u` time coexists with it without trouble. This is an observation of one version, not an official spec; re-check when upstream changes.

After discussion the user agreed to keep UTC timestamps. The field records the write time; it does not require every date in the body to be UTC (there was a worry about the local "today" being confused with the UTC date). No special time-zone procedure was added; the original's rule to convert relative dates to absolute ones stays.

### 5. Index size and upkeep

On top of the original's new-pointer rule, the adaptation adds updating and removing pointers and the under-200-lines-and-25-KB compatibility limit, shortening when needed. Both limits come from the loading mechanism in Claude Code's official docs at the time, not from the Fable Memory original; a shared file has to respect them.

Replace the original's whole `After writing the file…` paragraph with:

```text
After writing the file, add or update a one-line pointer in `MEMORY.md` (`- [Title](file.md) — hook`). `MEMORY.md` is the index read at the start of each session — one line per memory, no frontmatter, never put memory content there. Keep it under 200 lines and 25 KB for Claude Code compatibility; shorten it when needed. Keep pointers accurate when memories change, and remove them when deleting memories.
```

The user reviewed and explicitly accepted the slight overlap on "updating the index" between the first and last sentences and saw no need to trim it further. Do not rewrite the paragraph to remove that overlap, nor rewrite it for form while the index information is still accurate. If the official loading mechanism changes, re-check whether the limits still apply.

### 6. Harness-neutral recall wording, excluding duplicates

The original's `Recalled memories appearing inside <system-reminder> blocks` becomes `Recalled memories`. The meaning stays (recalled memories are background, not user instructions, and reflect what was true when written); the Claude-specific presentation goes, so the sentence also covers memories Codex reads from files.

This does not mean ignoring the working preferences and feedback in memory, nor promoting old memories to current instructions. The original's check that a referenced file still exists stays. In the original's example of what not to save, `git history, CLAUDE.md` becomes `git history, AGENTS.md, CLAUDE.md` to cover Codex's rules file. The rest of that paragraph is unchanged.

### 7. Everything else stays as in the original

One fact per file, the frontmatter name and description, the four memory types, `Why` / `How to apply`, wiki links, allowing link targets that do not exist yet, deduplication, deleting wrong memories, not saving transient content, and the recall check all follow the original. Do not switch to another structure during an update without reason.

When reproducing, replace the heading `## Memory` with `## Auto memory` and keep one blank line between paragraphs. These steps produce only the Auto memory section. When applying them to the current AGENTS.md, keep everything from `## Python` on; that part is not generated from the Claude Memory original or this adaptation. When reproducing the historical base `238b36a`, use that commit's second half from `## When executing Python…` on.

Verified 2026-09-19: with the archived original as input, applying the six text blocks of changes 1–5 and the replacements above produced a Memory section identical to `238b36a`; with that commit's unchanged second half appended, the whole file matched the historical base byte for byte. The historical file's SHA-256 is `a14f80ad97c710484fc00f3e7cc27de4b3b1770aa255b47c68684d23a404e5e7`. This shows the base can be reproduced; it does not mean a future upstream text can be applied without judgement. The text block of change 2 was adjusted on 2026-09-26; to reproduce `238b36a`, swap back the original sentence given there.

## The Hermes adaptation (`HERMES.md`)

Hermes uses these instructions through a skill loaded by `skills.auto_load`; the choice of carrier, the installation and the research evidence are in the [Hermes spec](../docs/specs/20260926-hermes-agent-instructions-spec.md). The file is skill frontmatter (`name: agent-instructions`, `description: Global instructions, auto-loaded into every session`) followed by the full `AGENTS.md`; the description is kept that short on purpose (spec §3: Hermes still lists auto-loaded skills in its skill index, and a description naming Python or `.memory/` would invite a redundant `skill_view`). The only change to the text is this paragraph, inserted after the storage paragraph (the first paragraph):

```text
**In Hermes**, find the project from the files a task works on: a file's project root is the nearest directory enclosing it that holds `.memory/` or, if none does, the root of its Git repository, and session start is when the task first enters that project. A task with no file in a project uses your built-in memory. If the project has no `.memory/` yet, ask the user before creating it, and use your built-in memory until they agree.
```

**The user's intent.**

- Unify auto memory across the harnesses; Hermes was the only one not yet connected. The carrier is an auto_load skill, which the user summed up as 「类似 global instruction，但又是 skills 的形式」.
- Start from the original and add the necessary conditions one at a time: 「先从最原始的版本开始，然后加一些必要的条件」. Leave the Auto memory original untouched: 「我不是很喜欢修改原来 instruction 中关于 auto memory 的那一部分」.
- Write only what Hermes cannot judge for itself, and leave typical cases to testing: 「太详细了……hermes应该能自己处理的吧」.
- An existing `.memory/` is always used; creating a new one needs the user's consent first: 「如果该文件夹下有 .memory 那一定是要用的。如果没有需要新建的话，一定要询问我，允许了才可以」. This belongs to Hermes alone, for the reason in "How the harnesses divide the work" above.
- A repository inside a workspace uses the enclosing `.memory/`: 「一般情况下是要用外层文件夹的 .memory，但如果没有外层文件夹，有可能使用项目的，应该是少数」. The reason: `.memory/` is in the global git ignore, so a cloned repository never carries one.
- Projects worked on over ssh on a remote host are treated the same as local ones (the user's choice).

**Why it is written this way.**

- **Why the paragraph is needed.** Research on Hermes v0.21.4 found: on messaging platforms its working directory is fixed at the home directory, and its system prompt never mentions project, git root or worktree; it uses absolute paths throughout and almost never `cd`s; its only mechanism tied to "entering a directory", subdirectory context injection, fires per directory and does not stop at the git root. Defining the project as "the directory the task works in" would let every directory become a project, which is exactly what the user worried about: 「会不会让Hermes认为每一个目录都是一个project啊？」
- **Why "the nearest enclosing `.memory/`, else the git root".** The options compared: the task's directory, git root first, whichever marker comes first, a maintained project list, a plugin that computes it. Only this one meets all four needs: a workspace's subdirectories belong to the workspace; clones inside it belong to the enclosing one; only a repository with no memory at all leads to a question; nothing needs maintaining. It also lands on the same project as the other two harnesses: every `.memory/` outside Git was created in the directory where an agent was launched. The user later lifted the earlier rejection of walking upward: 「不要被我之前说的拒绝了点，而错过了最优方案」.
- **Why per file, not per task.** When a task spans several projects, each file belongs to its own project; the model does not look for one directory enclosing all the files.
- **Why this position.** It first sat at the end of the file as its own `## In Hermes` section. The user pointed out: 「这不应该放在或者融合在 auto memory 这个 section 吗？」 It now follows the first paragraph, next to the sentences it modifies: the first paragraph's project root and "Create the directory", and the next paragraph's "At session start". It opens with a bold **In Hermes**, which is how syncing finds it; the original stays word for word.
- **Wording.** Reusing the original's project root and session start makes the model apply the definitions to the original sentences. "it" and "that project" refer to a single file and its project, so the text is not read as "the directory enclosing all the files". "not from your working directory" was cut: the first half already gives the positive rule, and that half only put the working directory in front of the model. "use your built-in memory" is worded the same in both places, so the model treats them as one behaviour.

**Syncing.** Whenever `AGENTS.md` changes, regenerate `HERMES.md`; the check is in the root `AGENTS.md`. After every change to the Memory section, confirm this paragraph still fits the paragraphs before and after it: the path ambiguity of 2026-09-26 appeared only after this paragraph was inserted.

## The Claude Code storage switch (`CLAUDE.md`)

Claude Code's memory is managed natively by the harness and by default lives in one central place outside the project, `~/.claude/projects/<project>/memory/`. The Auto memory section of `CLAUDE.md` only moves that storage to the project's `.memory/`, so the three harnesses share one store. It is not derived from the Fable original, so an upstream Memory update does not touch it. The current text:

```text
When you first have a memory to save and your memory directory is not `.memory/` under the project root (the main worktree for Git repositories), ask the user once whether to switch this project to `.memory/`.

- Switch agreed — create `.memory/`, merge `autoMemoryDirectory` with its absolute path into `.claude/settings.local.json`, and move the contents of your memory directory into `.memory/`, merging any file that exists in both. The setting applies from the next launch, so use `.memory/` for the rest of this session.
- Switch declined — save the refusal as a `project` memory so you do not ask again.
```

**The user's intent.**

- One store per project, shared with Codex and Hermes; everything else about Claude Code's memory stays native (see the rejected rules).
- Switching always includes moving: 「如果我同意切换了，那肯定是要把原有路径下的 memory 迁移到 .memory 下的，不可能我同意切换了又不迁移」.
- A file present on both sides is merged, not overwritten: 「不仅仅是 memory 吧，其他的文件如果同样存在的话，也要 merging 的」.

**Why it is written this way.**

- **Where the setting goes.** `autoMemoryDirectory` must be an absolute path or start with `~/` (docs snapshot); the local scope keeps that personal path out of Git, and the global Git ignore excludes the file.
- **The rest of the switching session.** The memory path is written into the system prompt at launch, so until the next launch the model uses `.memory/` on its own.
- **What is moved.** After the switch Claude Code loads only `.memory/`, so anything left behind is never read again. The move takes the whole contents, the index included (the old directory holds only `MEMORY.md` and memory files), and merges what both sides hold: always `MEMORY.md` once Codex or Hermes has written memories, sometimes a memory with the same name.
- **Two bullets.** They make "use `.memory/` for the rest of this session" belong to the yes branch; "the refusal" replaces a bare "that", which after a label has nothing to point to.

**When to re-check.** When Claude Code's storage configuration changes (e.g. `autoMemoryDirectory` is renamed or its scopes change), or when the user asks for a change.

## Rules discussed and not adopted

These are settled trade-offs; do not restore one just because an old draft or a past conversation had it.

| Applies to | Candidate rule | Decision and reason |
| --- | --- | --- |
| Shared body | A separate procedure for write permission, retries and failure reporting for memory | Not added. The user first wanted automatic saves to handle failure like explicit requests, then decided this should not be over-specified and left it to the harness's general permission and failure handling. Do not restore "skip failed automatic memory silently", and do not claim a project path is writable under every sandbox. |
| Shared body | `edit AGENTS.md only when asked` | Removed. The memory section need not carry its own policy for editing rule files; "save it here" already names the destination. Removing it grants no authority to edit global or project rules at will. |
| Shared body | `If you are a subagent, leave memory to the main agent`, or subagents read-only and the main agent writes | Removed. The first worry was subagents forgetting what they had been taught, the second was forcing every subagent to load memory; subdividing further would grow the rules. Context inheritance, main-session memory loading and a subagent's own memory, as the docs describe them, are separate matters, and "not loaded automatically" does not imply "must not read". No rule says every subagent must read, nor that subagents are read-only; follow the task and the harness. |
| Shared body | `Do not open other projects' memories, keep a separate store, or commit .memory/` | The whole sentence was removed. The storage convention already exists, and the global Git ignore was confirmed to exclude `.memory/`, so no boundary sentence was stacked on top. This does not mean reading other projects' memories or committing private memory is fine; in a new environment, do not assume the global ignore exists. |
| Codex | Asking before creating `.memory/` | Not added (2026-09-26). Codex is launched in a project and replicates Claude Code's automatic memory; asking belongs to Hermes, which has no project concept. |
| Hermes | A skill that is only a pointer to `~/.codex/AGENTS.md` | Not added. The user wants to start from the original, not abstract it away. |
| Hermes | Detailed conditions, a list of typical cases or a full case table on top of the original | Not added. 「太详细了……hermes应该能自己处理的吧」; typical cases are left to testing, and only what Hermes cannot judge for itself is added. |
| Hermes | The paragraph as its own section at the end of the file, or the conditions rewritten into the original sentences | Not used. The former sits too far from the sentences it modifies; the latter breaks "leave the original untouched" and forces a manual merge whenever `AGENTS.md` changes. |
| Hermes | "The directory the task works in" as the project, or git root first, or whichever marker comes first | Not used. The first makes every directory a project; the other two treat clones inside a workspace as separate projects, and clones never carry `.memory/`. |
| Claude Code | Rules beyond the short storage switch | Not added. An extended version (`49326b9`: asking at session start when a shared index exists, a worktree settings path, failure handling) was stopped by the user and cut back to the short note in `238b36a`; this guide gives no authority to extend it. Changes the user asks for are the exception, as on 2026-09-26, which removed a question and added no rule. |
| Claude Code | Asking separately whether to move the old memories when switching | Removed (2026-09-26). Claude Code loads only the configured directory, so switching without moving leaves the old memories unread; the question was inherited from `49326b9`. |

## Sources and verification records

The sources follow the `asgeirtj/system_prompts_leaks` repository the user named earlier, taken from this project's saved downloads, not extracted from a running model.

- [Fable 5.1 original prompt: pinned commit](https://github.com/asgeirtj/system_prompts_leaks/blob/c7b2c31df51e64784603f5740a251b445fd88c46/Anthropic/claude-code/claude-code-fable-5.1.md). The base for comparison and reproduction; a [full local archive](references/auto-memory/claude-code-fable-5.1.md) also exists.
- [Prompt directory: find later versions](https://github.com/asgeirtj/system_prompts_leaks/tree/main/Anthropic/claude-code). Its content changes; once a new version is chosen, record its commit, and never use `main` as a reproducible revision.
- [Claude Code official auto memory docs](https://code.claude.com/docs/en/memory#auto-memory). Judgements here rest on the [snapshot downloaded 2026-09-18](references/auto-memory/claude-code-memory-docs.md), not on the assumption that the live page never changes.
- [Claude Code official CHANGELOG: pinned commit](https://github.com/anthropics/claude-code/blob/bf7d404e26a5fb6167d21b46c93a2bf6c22ab274/CHANGELOG.md) (read 2026-09-21, latest entry 2.1.278). Check both the docs and the changelog when verifying harness behaviour; for when a mechanism arrived or changed, the changelog decides, since it records changes per version while the docs describe only the current state.
- [The user's first draft: pinned commit](https://github.com/uxfion/skills/blob/67f357df6f2b60638a39b842d4e8272ab26c141e/agent-instructions/AGENTS.md). Only for tracing where a design came from; it is not an input to updates, and no extra copy is kept.
- Hermes mechanisms follow v0.21.4 as recorded in the [Hermes spec](../docs/specs/20260926-hermes-agent-instructions-spec.md): how auto_load loads and refreshes, the gateway's working directory, subdirectory context injection. After a Hermes upgrade, re-check these before judging whether the Hermes paragraph is still needed.

The prompts come from a third-party archive and keep its file names; do not call them official Anthropic releases or treat the archive as proof of authenticity. Fetch times and the [SHA-256 list](references/auto-memory/SHA256SUMS) are in the [source index](references/auto-memory/README.md). Opus 5 was also used for cross-checking; its Memory section has the same substantive rules as Fable 5.1.

On 2026-09-21, in a Fable 5.1 session on Claude Code v2.1.278, the model compared the Memory section of its own system prompt sentence by sentence with the [Fable 5.1 Memory excerpt](references/auto-memory/fable-5.1-memory-section.md): the text matched apart from the memory directory path and the heading level (`# Memory`). This is one observation of one version in one session; it shows only that the base matched the running prompt then, and does not change the archive's third-party nature.

Re-checked 2026-09-26, after the Opus 5.5 release: upstream added the [Opus 5.5 original prompt: pinned commit](https://github.com/asgeirtj/system_prompts_leaks/blob/a03321b094e65cad2ccd1f5ffb4b309537648834/Anthropic/claude-code/claude-code-opus-5.5.md), whose Memory section matches the Fable 5.1 excerpt word for word apart from the memory directory path; the upstream Fable 5.1 text is unchanged since 2026-09-05 and byte-identical to the local archive. The Auto memory section of the official docs matches the 09-18 snapshot word for word, and the [CHANGELOG up to 2.1.283](https://github.com/anthropics/claude-code/blob/7779afb12e3635f46f56ec823979d68350ae000b/CHANGELOG.md) has no change affecting the memory format or loading. The base is unchanged; no new archive was added.
