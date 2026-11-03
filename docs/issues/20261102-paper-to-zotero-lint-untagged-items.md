# paper-to-zotero：lint_items 不报没有手打标签的论文

- 来源 · 日期：2026-11-02，从 [archive/20261102-paper-to-zotero-untagged-old-items-fixed.md](archive/20261102-paper-to-zotero-untagged-old-items-fixed.md) 拆出来。用户先发现：「我发现一个问题aka/MINIM 这篇没找到tag，是什么情况」，又问：「要找出为什么没有打这个标签？是之前就没有整理，还是什么情况？」
- 现场：
  - 库里有 95 篇论文一个手打标签都没有，最早的是 2024-10 进库的。2026-11-02 已经全部补打。
  - skill 只给自己导入的新论文打标签（import.md:58），`lint_items` 不查标签，库的待办里也没列这一项，所以一年多都没人发现。
- 为什么要紧：用户用 Zotero Connector 直接存的论文不经过 skill，进库时就没有标签，以后还会出现。用户在标签栏按前缀找论文，这些论文找不到。
- 方向（没拍板）：`lint_items` 加一个问题代码（比如 `untagged`）：顶层的论文条目没有任何手打标签就报出来。整理流程照常把它交给打标签的 subagent。
- 状态：open。
