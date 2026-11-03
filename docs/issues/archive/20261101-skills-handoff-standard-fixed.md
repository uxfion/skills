# skills：脚本、agent、用户之间的交接写法不一，从 agent 出发的交接常缺输入文件和收回答复的命令

> **已完成（2026-11-01）**：按 spec `docs/specs/20261101-skills-handoff-standard-spec.md` 在 paper-fetch、paper-to-zotero 落地（实施中的修正和真实验证见 spec §13），用户验收后关闭。vllm-serve、paddleocr 的部分在它们各自的 issue，paper-read 的部分在 `20261028-paper-to-zotero-paper-notes-fixed.md`，三张 issue 文末附了各自的审查条目原文。

- 来源 · 日期：用户 · 2026-11-01。修页面候选（`archive/20261101-paper-fetch-page-candidates-other-papers-fixed.md`）时，用户问各 skill 的交接文档有没有写好，由此展开。
- 用户原话（按时间）：
  - 「另外我想了解一下，整个相关 skill 的交接文档有没有写好？以下流程是否都已经设计好了：1. 什么时候脚本处理不了，怎么交接给 sub agent 这一层？2. sub agent 处理完后，怎么交接给脚本或者 main agent？」，接着「也不说按照以下流程吧，就是按照合理的流程，不是严格按照我说的流程」。
  - 「我的意思是，不同角色（脚本、Agent、用户）这三者在信息流转的过程中，无论是提示词、交接的文档，还是传递的数据，是否都是合理的？然后在 design principle 里面有没有相关的体现？」
  - 「对，每一次交接都要写清楚对象以及任务，还有要求、产物等等一切有必要的内容或文件……我觉得也不用全部通用吧，但是至少要描述清楚，当然，如果能设计得通用一点、标准一点，然后在标准之下，因为针对不同的任务，也会有不同的方向或不同的差异……如果方向对，或者值得那么做，值得去标准化一部分，我会给每个人定制化一部分。如果方便的话，并且对我们整个项目有益的话，我觉得可以做。跟我讨论一下」
  - 「具体的细节你需要根据设计原则以及 writing for agent以及mattpocock/skills，里的设计思路、设计原则、顶层设计等等，一切比较全面、比较顶层、比较优雅的思路以及设计方案，去过一遍」
  - 「不能一下子拍板拍死。然后你自己再综合考量一下再决定，不要那么快，我说什么就直接决定什么」
- 参考资料（关闭时已删）：`mattpocock-findings.md`（mattpocock/skills 的做法，要点在 spec §2）和 `audit.md`（五个 skill 的 73 处交接；PF-、PZ- 条目已按 spec §6、§7 处理，PR-、VS-、PO- 条目原文搬进了 paper-notes、vllm-serve、paddleocr 三张 issue）。
- 状态：已完成（2026-11-01），用户验收后关闭。

## 已经做了的（2026-11-01）

- 设计原则加了几条，用户都同意了（合进提交 `1b6cbb6`）：
  - §1：三种角色之间、两个方向的每一处交接都要设计，按接手的那一方（subagent、主 agent 或用户）来写；
  - §1：状态存在文件里，不靠对话记着；每样东西只有一个写入者；做不完的一方要交回；只看本地文件的 judge 最多 10 个同时；
  - §3：多处共用一个样子时，共用的部分定一次，其余按任务定制；
  - §5：用户的话是方向，不是定稿；讲方案时说明它和原则的关系。
- 设计原则整理了一遍，用户的原话挪到 `docs/design-principles-sources.md`。

## 审查发现（简）

- **写得好的**（可作样板）：paper-fetch 的 paper agent brief（PF-9）、paddleocr 的 settle brief（PO-4：brief 是一个按路径交给 subagent 的文件）、验证码交给用户（PF-16）、p2z 查重的 judge（PZ-6，差一点）。
- **缺口**，按接手的 agent 要猜多少排：
  1. identify 派的浏览器 agent（PF-7）：只写了"照 paper agent 的 brief"，没有会话名、存哪个文件、完成条件和回报；
  2. identify 的两类 judge（PF-5、PF-6）：输入只在主对话的输出里，没有能给的答复，也没有记下答复的命令；
  3. 识别器之后的 judge（PZ-13）：没有 brief，没有产物格式，`update_item` 谁跑散在三处；
  4. 打标签的 subagent（PZ-9、PZ-18）：没有模型、输入文件、输出路径；导入时直接改主 agent 也在改的记录文件；
  5. 整理时的 judge（PZ-17）：lint 的行怎么分、`<n>` 谁定、`unknown` 交给谁没写；
  6. paper-read 的 reader（PR-4、PR-5）：要核对题目但 brief 里没有题目，没有写入范围、回报格式和退回的办法；
  7. 跨轮的 paper agent（PF-15、PF-18）：恢复时消息里写什么没说；
  8. 给库里文件定标签的 judge（PF-12c、PF-20）：没指给它结果文件，被拒的库内 PDF 不报。
- **矛盾**：reader 用 opus 对原则"用会话本身的模型"；`taker` 在记录里写死、SKILL.md 按情况指派；`--slug <citation key>` 对 paper-fetch 的 slug；judge 必看两页图、图要装了 `pdftoppm` 才有；vllm-serve 和 paddleocr 对安装要不要等用户说法相反；reader 核对的题目 brief 里没有；p2z 的 `[--key K]` 对 `answer.py` 必须带 key；p2z 记录格式说明对 `answer.py` 的写法；subagent 上限两种算法；`discovery_template` 的搜索步骤 SKILL.md 没写；paper-read 等 `unchanged`、脚本打印 `skipped`。
- **规律**：从脚本出发的交接普遍写得好（有记录、有命令、有能检查的完成条件）；从 agent 出发的普遍弱（没有记录，输入不落盘，答复没命令收回）。同一类交接"便宜的 subagent 判断本地文件"在五个 skill 里有五种写法。§6 的规矩（写入文件夹、只派一层、不碰 git、完成条件）只有 paper-fetch 的上网 agent 写全了。恢复同一个 subagent 只在一处提到，没说消息写什么；Codex 的对应写法不全。

## 范围

已定（2026-11-01，用户选 A）：只改 paper-fetch、paper-to-zotero；paper-read 的交接放进它自己的设计里；vllm-serve 和 paddleocr 的问题记在 `audit.md`，留给那边的会话按同一标准改。
