# Keeping the notes

What happens to a paper note after its reading: projects record their use of it, topic notes tie papers together, corrections keep it right. Every change goes through paper-to-zotero: `note take` into `<scratch>`, edit the file, `note put -i` (references/organize.md of that skill, *Notes*).

## Used in

The note's last section, `## 用在哪里`, says which projects use the paper and how, so that a project starting out can search the notes and see what is known and where a paper was used. A project's own reasoning stays in the project; here is one line per decision, pointing there.
- One item per project: its name at the first level; under it, one line per use it still has. A project that changes its use rewrites its own lines; how it got there stays in its own files and history.
- Every line is a decision, used or turned down, written the same way: `<decision>: <reason> · <where in the project> · <date>`. The reason is a sentence that stands on its own: its half about the paper names the point (the details and pages are in the questions above), its half about the project names the project's condition.

```markdown
## 用在哪里

- project-a
  - 用作对比基线：结构和本项目最接近，代码公开（Q3、Q5） · `decisions.md#baseline` · 2026-10-30
  - 没采用它的损失函数：只在成对数据上训练过（Q4.2），本项目只有非成对数据 · `decisions.md#loss` · 2026-10-30
```

Write the line after the project's decision is written in the project, and only your own project's lines.

## Topic notes

What several papers say together on one topic (which IQA metrics agree with radiologists, how methods handle unpaired data) is a topic note: a standalone note, one per topic, in the collection `主题笔记` and nowhere else; that collection holds topic notes only, and a tidy of the library leaves it alone. The note is related both ways to every paper it covers:

```markdown
---
collections: <key of 主题笔记>
related: <citation key>,<citation key>
---
# <the topic>
```

Every claim in it points to the paper note it comes from (citation key, question); a claim no paper note holds yet goes into that paper's note first. How a topic note is organized beyond that: 待定.

## Corrections

Before changing a note, read it whole. Every change rests on the paper's own text, with its version and page; what someone else wrote stays unless the text proves it wrong, and then the reason is written where it was. A project's question that turns out to be about the paper goes under the question it belongs to, as in references/reading.md.

A correction that changes what a project's line in *用在哪里* rests on leaves that line to its project: add at its end `（待重看：<what changed> · <date>）`, and name it in your report to the user, who knows which projects are still running and whether to send one back. That project's agent, reading the note next, judges again, rewrites its line and removes the mark.

Two agents writing one note do not overwrite each other: `note put` refuses when the note changed since it was taken (`version_conflict`); take it again and redo the change there.

## The library's older notes

What becomes of the notes the library held before this skill — the user's own, and earlier agents' — is 待定 (the paper-notes design, open point 5, kept with the skills' sources). Until then they are read as they are and changed only on the user's word.
