> 不改（2026-11-23）：用户 2026-11-18 说明那批旧配置进 archive 是当次的要求，不是通用规则：「我只面向当时场景就这么一次，我想要进 archive」。`layout` 参考不改。「丢弃」不等于删除这一点通用块已有：删除不是本任务创建的东西归用户定。

# how-we-work：git 跟踪的文件被"在 git 里删除"，用户期望进 archive

- **来源 · 日期**：`Hub/network` 项目的会话 · 2026-11-17。
- **涉及的文字**：`references/layout.md` 的 *Replacing and deleting*：「What git tracks is changed or removed in git. Its history is the old version」；以及「What git cannot bring back goes to `archive/<YYYYMMDD>/`」。

## 经过

- 用户要求新写一份 Surge 配置，说旧的不要用：「之前的旧的东西都丢弃掉。不要用旧的。」
- main agent 把"丢弃"当成删除，对 git 跟踪的旧配置（`surge/my.conf`、`my_remote.conf`、`Default.conf`、`old/`）直接用了 `git rm`。理由是上面那句：git 跟踪的东西在 git 里删，旧版本在历史里。没有先问，也没有放进 archive。
- 这批文件是旧配置，不是本任务创建的，按通用块应由用户决定删不删。
- 用户在同步文件夹里看到文件没了。

## 用户原话（2026-11-17）

- 「你这个删除是放到archive里了吗？」
- 「为什么我看到直接被删掉了」
- 「你不要瞎搞乱删，」
- 「我们都规定好的，而且这种东西就不应该删啊，我们原则和规则都规定的很清楚，你怎么就删掉了」
- 文件放回后，用户选择移进 archive（「B」）。

## 为什么要紧

- 用户看的是文件夹（这个项目还会同步到 Synology），不看 git 历史。在用户眼里，"在 git 里删除"就等于凭空消失；archive 才是他认可的回收站（layout 参考里引的原话：「需要迁移或者删除或者重构等找不回旧版本的东西都可以放在archive」）。
- "git 跟踪就在 git 里删"这句话，给 agent 提供了一条不进 archive 的删除路径。

## 可能的改法（由用户定）

- layout 的 *Replacing and deleting* 改成：用户的文件被拿掉时，不管 git 是否跟踪，都先放进 `archive/<日期>/`，写好 INDEX。
- 并在通用块里强调："丢弃""不用"不等于删除，删除前要用户明说。
