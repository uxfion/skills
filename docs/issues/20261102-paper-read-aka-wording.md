# paper-read：spec 里转述的 `aka/` 规则过时了

- 来源 · 日期：用户 · 2026-11-02。p2z 那边刚放宽了 `aka/` 的规则（[archive/20261102-paper-to-zotero-untagged-old-items-fixed.md](archive/20261102-paper-to-zotero-untagged-old-items-fixed.md)，提交 `e50575a`），用户：「那边的这种说法，你建一个issue说一下吧」。
- tagging.md 现在的规则：说起这个词，业内都知道指的是这篇论文，就打 `aka/`，不管它指的是模型、指标、方法还是数据集（例如 `aka/SSIM`、`aka/Temperature scaling`、`aka/GAN`、`aka/ImageNet`）。用户原话：「实际上，我就是想要有一个 AKA 的概念，就是这篇论文又叫什么，提出的论文模型或者什么东西，大家都称它为什么，或者行业内的惯称、统称，或者说是我们说到哪个词，大家都知道是哪篇论文。」
- paper-read 这边过时的说法：
  - spec `docs/specs/20261102-paper-read-notes-spec.md` 第 230 行：「简称可有可无：论文自己提出了带名字的模型，或者业内用这个名字称呼它，才有 `aka/` 标签（tagging.md）。」只说"带名字的模型"，是旧规则的范围。
  - 同一份 spec 第 297 行：「没有 `aka/` 标签：标题行里不写简称，照样打印。这是常态，不报、不补打（用户 2026-11-02：「不要强制加上去，你可以不加的」）。」
    - 用户那句话说的是：本来就没有名字的论文，不要硬加。"不补打"是读过头了。
    - 像 T-CACE 这样有自己的名字、却没打标签的，是漏打。
    - 用户另外授权过：读论文时发现库里的标签有问题，可以直接改，改完在报告里列出（记忆 authorization-scope，2026-11-02）。
  - 论文笔记 issue `20261028-paper-to-zotero-paper-notes.md` 第 71 条也是旧说法（"可有可无，不补打"）。那是讨论记录，不用改，但 spec 是照它写的。
  - `paper-read/references/notes.md:24`（"Most papers have no common name"）和 `index_heading.py` 只读标签、不判断该不该打，不用改。
- 为什么要紧：spec 是实现 paper-read 时照着写的依据。按旧说法写进 skill，读论文的 agent 遇到有名字却没标签的论文，会当成常态放过去，项目索引的标题行就少了简称。
- 方向（没拍板，由改 paper-read 的会话定）：
  - 第 230 行不在 spec 里转述规则，只写"按 tagging.md"；
  - 第 297 行：没有 `aka/` 标签，照样打印；读论文时如果发现这篇其实有业内通称，按授权补上，在报告里列出。
- 状态：open。
