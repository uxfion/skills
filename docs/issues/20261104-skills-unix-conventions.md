# skills：整套系统对接 Unix 哲学

- 来源：用户 · 2026-11-04。讨论库里搜索结果太长时（见 [archive/20261104-paper-to-zotero-search-output-compact-wontfix.md](archive/20261104-paper-to-zotero-search-output-compact-wontfix.md)），用户先问：「或者你有没有办法能通过 Linux 的那种概念理论，像管道服务，grep/rg 那样支持」，「那有没有可能通过外部工具去调用呢？因为Unix的哲学就是通过各种工具、接工具或者管道或者数据流去传递嘛」；然后：「我倒是想把这整套系统都和UNIX哲学给对接好,这样的话也方便使用，因为现在我感觉还是用 Python 的思维多一点，但实际上我更喜欢 UNIX 哲学,包括以其他数据流的方式，它的管道符，还有它使用的各种键值，以及简称之类的」；又说明范围：「短选项，标准选项,反正就是一切涉及到UNIX的哲学，Linux那套操作逻辑…我还是挺欣赏 UNIX、Linux 那一套操作逻辑或者展现形式，还有它的文件base的思路，可能还不止，就是它的一整套系统」。
- 状态：open。2026-11-04 用户确认后，原则写进了 `docs/design-principles.md` §3 *The Unix/Linux philosophy*（用户：「你先把我们刚才说的 UNIX 哲学记进 design principle 里面，防止下次增加新功能或者新增脚本时又没有加上…还不如从一开始设计的时候，我们就从 UNIX 哲学的角度去设计」），新命令从第一版设计起照它做。已有的命令还没动，按用户定的节奏：「我们可以逐步来嘛，优化起来试验一下，用一段时间看有没有问题。基本上没问题的话，我们在后面全部铺开」。
  - 出处里说"终端前的人"的地方，用户：「这里的人和 Agent 应该没有区别的」——给人用的和给 agent 用的是同一份，默认输出不按"人"和"机器"分两种模式设计。
  - 命令怎么直接敲：不装进系统目录。用户：「你直接增加啊一个临时的PATH环境变量不就好了，那不就直接可以用起来了吗？」「每个 skills 也可以有它自己不同的PATH变量呀,不就更便利了吗？」2026-11-04 实测可行：装好的 skill 里脚本都带 uv 开头和可执行位，`PATH="$HOME/.agents/skills/paper-to-zotero/scripts:$PATH" p2z.py read_library items --cite …` 直接取到了条目。每个 skill 只加自己的目录，还能避开同名脚本：`ready.py`、`answer.py` 在 paper-fetch 和 paper-to-zotero 里各有一个，全加进去就只跑得到排前面的那个。Claude Code 每次执行命令都是新开的 shell，PATH 要在每条命令里带上，或者在会话一级设好。
  - 还没定、要在试点里定的：简称（去掉 `.py`、更短的名字）；PATH 写在哪里、由谁设；默认输出的具体样子。
  - 下一步：试点。用户让先查各项目最常用、最值得做的（「你去我们每个项目中，查阅一下最经常用到的、最值得做的是哪一个」），只看 Claude Code 的记录；查的结果在参考资料 `usage.md`，建议先拿 p2z 的 `read_library` 试点，等用户点头。
- 参考资料（`20261104-skills-unix-conventions-reference/`，git 不跟踪）：每个命令的盘点、Unix 约定的出处。

## 要对接的

以 `docs/design-principles.md` §3 *The Unix/Linux philosophy* 为准。它比最初的设想改准了两处：每条记录自己的状态和提示留在那条记录里，只有不属于任何记录的（进度、警告、汇总）放标准错误；串起几个命令的脚本照 *Orchestrate, don't absorb* 做，不算违背。

## 现状（2026-11-04 粗盘）

- 5 个 skill、44 个脚本：长选项 118 个，短选项只有 12 个，几乎都是 `-o`。
- 只有 10 个脚本能从标准输入读；批量输入多半靠 `--batch 文件`。
- 27 个脚本在标准输出末尾加一行 `{"summary": …}`，数据和汇总混在一个流里。
- 调用都是 `uv run <skill>/scripts/<script>.py …`，不在 PATH 上，没有简称。
- skill 之间靠 Python 子进程拼接（如 paper-read 的 `put_note` 在 Python 里调 p2z 和 paddleocr），不是管道。
- 已经合 Unix 习惯的：一行一个 JSON 对象；退出码 0/1/2；`-i` 原地写回（像 `sed -i`）；少数命令认 `-` 代表标准输入；配置已经在 `~/.config/<skill>/`。

## 为什么值得做

- 用户喜欢、用着顺手。
- 这些命令主要是 agent 在用，Unix 的习惯是模型最熟悉的：`-n` 是空跑、`-` 是标准输入、标准输出只放数据，不读 `--help` 也能猜对，出错少。2026-11-04 主 agent 把管道接在 heredoc 脚本前面丢了数据，就是 Python 写法和 Unix 习惯拧着的一例。

## 做法和风险

- 会动 5 个 skill 的 44 个脚本，以及引用它们的文档、给 subagent 的说明和测试。2026-10 的 v3 第一次尝试逐处打补丁，脚本从 7.5k 行涨到 15.4k 行，用户：「我觉得现在一切都乱套了」。所以从上往下做：先定共用的约定，拿 p2z（用得最多）做样板，用户看过再推到其余几个。
- 顺序：盘点（每个命令对照上面几条）→ 约定的出处（POSIX、GNU、命令行指南这类原始资料）→ 设计和样板，拿给用户讨论 → spec → 实施。
- 写进 `docs/design-principles.md` 的部分是规则层面的改动，先和用户讨论、确认再改。
