# paper-to-zotero：`--title` 一个名字两个意思

- 来源：2026-11-05，paper-read 的 Unix 改造设计稿顺带指出，主 agent 对照代码核实。用户没有提。
- 状态：open。

## 经过

- `p2z.py package take --title T`（`scripts/structured.py:303`）：挑附件标题是 T 的那份 PDF（如 `Preprint-arXiv-v7`）。
- `p2z.py note take --title T`（`scripts/note.py:411`）：只取第一行是 T 的笔记。
- 原则 §3 *Options by convention* 写着"一个长名字全系统只有一个意思"。这两处同名不同义，是 Unix 约定样板实现时漏掉的，约定检查也没查这一条。
- paper-read 改造后的 `pr.py take --title` 会沿用 `package take` 的意思（PDF 的附件标题），这样三处里有两处一致，`note take` 那处就更显得不一样。

## 建议

- 两个意思里改掉一个的名字。附件标题这个意思用得更多：paper-read 的 `take` 要用它，`p2z.py pdf` 列出的也是附件标题。所以改 `note take` 的，比如 `--note-title`；或者干脆不要这个选项，笔记按自己的 key 取就行，`note take` 本来就收笔记 key。
- 约定检查补一条：各命令帮助里同一个长名字，说明的意思要一致。这条不容易机器判断，至少可以把同名的长选项列出来，交给人看。
