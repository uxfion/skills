# skills：整套系统对接 Unix 哲学

- 来源：用户 · 2026-11-04。讨论库里搜索结果太长时（见 [archive/20261104-paper-to-zotero-search-output-compact-wontfix.md](archive/20261104-paper-to-zotero-search-output-compact-wontfix.md)），用户先问：「或者你有没有办法能通过 Linux 的那种概念理论，像管道服务，grep/rg 那样支持」，「那有没有可能通过外部工具去调用呢？因为Unix的哲学就是通过各种工具、接工具或者管道或者数据流去传递嘛」；然后：「我倒是想把这整套系统都和UNIX哲学给对接好,这样的话也方便使用，因为现在我感觉还是用 Python 的思维多一点，但实际上我更喜欢 UNIX 哲学,包括以其他数据流的方式，它的管道符，还有它使用的各种键值，以及简称之类的」；又说明范围：「短选项，标准选项,反正就是一切涉及到UNIX的哲学，Linux那套操作逻辑…我还是挺欣赏 UNIX、Linux 那一套操作逻辑或者展现形式，还有它的文件base的思路，可能还不止，就是它的一整套系统」。
- 状态：open。设计都已定（下面「已定」），spec 是 [docs/specs/20261104-skills-unix-conventions-spec.md](../specs/20261104-skills-unix-conventions-spec.md)，经三路审阅和 advisor；规则文字已改进 `docs/design-principles.md` §3 *The Unix/Linux philosophy*，新命令从第一版设计起照它做。p2z 样板已实现（2026-11-05）：p2z、paper-read、paper-fetch 的测试和根目录的约定检查全过，真库只读验收通过；实现时的修正记在 spec 第 9 节。删扫全库前的核对：921 个引用键全部按默认快速搜索精确命中，0 歧义。实现已提交（`1e81c30`），真写入验收 2026-11-05 通过（spec 第 9 节末尾），spec 已冻结。下一步：推送后三个 skill 一起重装；用户用一阵后重跑 `usage.py`，再定铺开。

## 目标

把 5 个 skill 的命令改成 Unix 的用法：管道和数据流，惯例的长短选项，要处理的东西写在命令后面，以文件为本；代码照旧是 Python（原则：Python inside, Unix outside）。

- 范围是一遍约定整理：不动流程，不重新设计，输出的内容不变（一行一个 JSON，字段照旧）。用户：「原有不合理的那些写法尽量改掉，然后改成 UNIX 哲学的」「我们这次有点类似重构的思想，就是把以前那些不合理的、不符合 UNIX 哲学的，尽量全部改掉」「同时不丢失原有的核心功能」。
- 好不好用以整个 skill 来比。用户：「我说的"全局"指的是针对我们这个项目，或者针对某一个 skill 的全面比较最优解，而不是说针对某一个脚本去调到最优」。
- 节奏：先做样板，用一阵，没问题再铺到其余 skill。用户：「我们可以逐步来嘛，优化起来试验一下，用一段时间看有没有问题。基本上没问题的话，我们在后面全部铺开」。
- 给 agent 用的和给人用的是同一份，默认输出不分两种模式。用户：「这里的人和 Agent 应该没有区别的」。
- 讨论中用户一度怀疑这张 issue 是否合适（「如果都是通过 Python 去操作，是否会更简单呢？」）。结论：agent 在 shell 里干活，命令一行就是一件事，全用 Python 每件事都要现写代码，更复杂；绕是主 agent 一块一块地问、又把范围扩到流程造成的。

## 已定（2026-11-04）

1. **样板是整个 p2z**：25 个命令一起换成新约定，p2z 的全部文档、paper-read 里调 p2z 的地方一起改；用一阵，再做 paper-fetch、paper-read、paddleocr、vllm-serve。只做读库的话，`p2z.py` 下会新旧两种写法并存，写入那一侧（空跑、批量、汇总、导入记录）也验证不到；25 个脚本里 22 个的选项和输出走共用的 `cli.py`，量主要在 `cli.py`、短词表和文档里。
2. **旧写法一次换掉**，不留别名。
3. **每个 skill 一个入口，下面是短词**，像 papis、pubs、git：`p2z.py search POCUS | p2z.py pdf -`，`p2z.py tag -n …`，`p2z.py -h` 列出全部。入口里一张"短词 → 脚本"的表，脚本文件不改名；`prepare`、`save` 照旧在入口里。不同 skill 的入口名不同，两个 skill 可以写在同一行命令里。讨论时说的是"短动词"，读库那几个用名词更好懂（`items`、`tags`，像 `git tag`），所以叫"短词"；用户：「可以的，反正你用合适的词」，用哪个词由主 agent 定，写在 spec 的短词表里。（先定过"直接调脚本、删掉 `p2z.py`"，查了现成工具后改了：papis 23 个命令、pubs 15 个，都是一个入口加单词的短词，见参考资料 `existing-tools.md`。）
4. **PATH 用的时候带上**，不写进 `~/.bashrc`，不装进系统目录，脚本不改名。用户：「你直接增加啊一个临时的PATH环境变量不就好了」；「PATH 写进 ~/.bashrc我觉得还是不合适，如果skills被卸载了呢」「我觉得还是用的时候带上是否会更好」。每次调用开头单独一句 `set -o pipefail; export PATH="<skill 目录>/scripts:$PATH";`，后面整条管道都找得到；`pipefail` 让管道前面的失败带到整行的退出码上，`export` 漏了分号会当场报错，不会只对第一个命令生效（spec 审阅后加的，用户选 A）；不再 `cd` 到 skill 目录，不再写 `uv run`。2026-11-04 实测：装好的 skill 里脚本带 uv 开头和可执行位，这样能直接跑，标准输入也能穿过入口。
5. **要处理的东西写在命令后面，`-` 从标准输入读**：替掉 `--key`、`--cite`、`merge_items` 的 `--keep`/`--drop`（`merge 并掉的 --into 留下的`：两条角色不同，留下的单独点出，写反了也不会把它扔进回收站；用户选 A）、paper-fetch 的 `--file`；批量的 `--batch 文件` 换成文件写在后面或 `-`。`-` 读到的一行可以是一个值，也可以是我们自己输出的 JSON 行，取其中标识那样东西的字段（条目是 `key`）：`p2z.py search POCUS | p2z.py pdf -`，中间不用挑字段。全系统通用。
6. **搜索词写在命令后面**：`search 词`，替掉 `--q`（`-q` 按惯例是"安静"）；照样能按集合、标签、库版本筛，三种模式都留（默认、`--all-fields`、`--everything`，照 Zotero 界面的叫法；`--fields` 会读成"挑输出字段"，spec 审阅后改的）。
7. **选项照惯例**：`-n, --dry-run`；`-f, --force`；`-r, --recursive`；`-a, --all`；输出一律 `-o, --output`（现在全系统有 9 个脚本写成 `--out`，p2z 里 7 个）；`-i` 原地写回照旧。`--version` 只表示打印程序版本，paper-fetch 拿它表示论文版本的改名 `--as`（名字是主 agent 起的）。不加 `-v`、`-q`、`-V`（没有命令需要）。全系统一个字母一个意思：`--tag` 不配 `-t`（note_md 的 `-t, --to` 是 pandoc 的写法），`--collection` 不配 `-c`（`grep -c`、`uniq -c` 是计数）。
8. **指定集合的地方 key 和路径都认**（选项、导入记录和改动清单里的集合、`mkcol 上级/新名字` 的上级；`--parent` 并进了 `mkcol` 的写法）：`--collection 自然图像/Diffusion`；只写名字也行，重名（本库顶层和 `自然图像` 下各有一个 `Diffusion`）就报错、列出各条路径、退出码 1。省掉真项目里每次先查 key 的那一步（`--collection` 在真项目里敲过 23 次）。
9. **标准输出只放数据**：连不上 Zotero 这类整命令报错写在标准错误最后一行；脚本末尾的 `{"summary"}` 只在没全做完时写到标准错误，全做完时不打（"汇总写标准错误"和"成功时不出声"原来互相顶着，spec 审阅后按"没有话就不说"解开）；每条记录自己的状态和提示留在那一行里。
10. **成功时不出声**：脚本开头加 `--quiet`；管道被下游关掉后不再打印、不报错，命令照常做完，退出码照实。
11. **帮助统一成 man 页的样子**：用法行、做什么、选项、退出码、例子。
12. **规则文字**（用户同意）：spec 第 1 节里必须遵守的规矩并进 `docs/design-principles.md` §3 *The Unix/Linux philosophy*，成为所有 skill 共用的唯一出处；§4 *Skill text* 的例子改成入口加短词；AGENTS.md 的脚本那条加 `--quiet`、可执行位改成必须；README 改成指向原则；出处文件记了用户的原话。约定检查放在哪、怎么跑，实现时写进 AGENTS.md。
13. **不另立共用代码，靠约定、检查和样板**（2026-11-05，用户同意）。p2z 里和具体服务无关、各 skill 都能用的代码约 220 行：`p2zlib/cli.py` 里 186 行，入口里约 30 行。整块用得上的只有 paper-fetch，它改造时本来就是拷一份；paper-read、paddleocr、vllm-serve 现在每个的命令行代码粗数十几到四十几行，各自只用得上几十行。各 skill 一致靠的是约定（原则 §3）和约定检查，检查按命令的行为验，不看代码是不是同一份；另立共用源文件、加拷贝一致的检查、每次改完同步几份，代价比省下的多。做法：p2z 的代码当样板，改造某个 skill 时拷它需要的部分，自己写它自己的部分。哪天同一处修改真要在几份拷贝里反复做，再抽。用户：「其实我觉得这套共用的东西，你完全可以以怎样的形式给抽象出来，就像我们design principle 里面那个交付标准还是什么东西，好像也是类似的思想。就是共用的东西我们可以一起约定好、规范好，然后每个 skill 定制化的东西，你再独立去定制嘛」；「这个工作有没有必要做，就是它共用的代码多吗？如果共用代码少的话，我感觉没必要」；「对，我也是想着，如果共用的少的话，我们就在 design principle 里面或者在哪个地方把它规范好，或者把设计理念讲好，这样的话，每个区实现的时候都是按照同一套思路」。原则不改（用户同意）：这个理念原则 §3 里已有，*A standard where cases share a shape, the rest per case*、*Cut where it pays*、*Small, independent, pure-Python scripts* 三条就推得出；哪个 skill 当样板、拷哪些文件，是这次铺开的做法，记在下面一节。

## 铺开到其余 skill 时（p2z 样板的经验，2026-11-05）

每个 skill 照同一套做：

1. **先写调用的前后对照**：这个 skill 最常见的几种用法，改前怎么敲、改后怎么敲（像 spec 第 0 节），短词、写在命令后面的东西、`-` 读什么，从这里一次定下，再定细节。
2. **先在真服务上量，再定做法**。p2z 这次量出四件和设想不同的事，都改了 spec（第 9 节）：`itemKey` 找不到回收站里的条目；整库一次读要约 40 秒；默认的快速搜索就能按引用键命中；9 号端口在 WSL 里会挂到超时。
3. **假服务先改成和真的一样**：假 Zotero 不带 `limit` 时只给 25 条，"一次读完"的测试白白通过。
4. **从 p2z 拷需要的部分**（`p2zlib/cli.py`、`p2z.py`），自己写"一样东西"指什么、名字怎么解析、服务报什么错。先改共用的那层和一个样例脚本，其余照样例改，测试跟着每个脚本一起改。
5. **整条管道测**：`-` 读到空清单（没有要做的事）和后面什么都没写（用法错误）、`pipefail`、写库的命令被 `head` 截断后仍做完。范围看后面写没写东西，不看清单空不空：p2z 这次就查出 `package names` 读到空清单会去改整个库。
6. **调用方同一遍改**：别的 skill 里调它的地方，连同那边测试里的假替身（如 paper-read 的 `fake_p2z.py`）；推送后几个 skill 一起重装。
7. **约定检查**：把这个 skill 从 `NOT_YET` 拿掉；运行时那几条，第二个 skill 加入时改成读各 skill 自己的假服务和示例命令。
8. **行数目标文档和脚本分开算**：说明从文档搬进 `-h`，文档变短、帮助变长。
9. **批量替换**：每处先断言原文正好出现一次，换完再 grep 一遍误伤（这次误伤过同名的 `p2zlib/note_md.py`）。
10. **原则里的进度已拿掉**（2026-11-05，用户选 A）：原则 §3 *The Unix/Linux philosophy* 最后一句原为 "Existing commands are brought over one skill at a time, paper-to-zotero first."，改成 "Existing commands are brought over a whole skill at a time."：整个 skill 一次改过来是规则，留下；哪个先改是进度，归这张 issue 和约定检查的 `NOT_YET`。用户：「我说的是项目层面的那种具体的代码或者进度之类的」。

## 现状（2026-11-04 盘点）

- 5 个 skill、48 条命令（p2z 25、paper-fetch 11、paper-read 6、paddleocr 5、vllm-serve 1）；脚本约 1.8 万行，测试约 1.3 万行，SKILL.md 和参考文档约 2,200 行。
- 长选项 118 个，短选项只有 12 个，几乎都是 `-o`。只有 10 个脚本能从标准输入读；批量输入多半靠 `--batch 文件`。近 30 个脚本在标准输出末尾加一行 `{"summary": …}`。
- 调用都是先 `cd` 到 skill 目录再 `uv run scripts/<script>.py …`；跨 skill 是 `uv run ../paper-fetch/scripts/pf.py …`。
- 已经合 Unix 习惯的：一行一个 JSON 对象；退出码 0/1/2；`-i` 原地写回；少数命令认 `-`；配置在 `~/.config/<skill>/`，环境变量可以覆盖。
- 输出接 `head` 这类提前收工的命令时，p2z 的脚本在标准错误打出一整段 BrokenPipeError，退出码 120（`p2zlib/cli.py` 的 `emit`，所有 p2z 脚本共用；实测 `read_library.py tags | head -1`）。
- uv 平时不往标准错误打东西，但带依赖的脚本第一次跑会打一行 `Installed 1 package`；`uv run --quiet` 就没有了，依赖装不上和脚本自己的报错照样会打（实测）。44 个脚本开头都是 `uv run --script`，没带 `--quiet`。
- agent 爱把标准错误丢掉：真项目里 45 条不重复的 `read_library` 命令行，27 条加了 `2>/dev/null`，其中 22 条后面还接着管道。文档里一处都没有，是 agent 自己的习惯。报错挪到标准错误以后这样一丢，agent 只看到空结果（侧边 agent 提出）；现在报错写在标准输出里也挡不住，一接 `grep`、`jq` 就被滤掉了。
- 使用统计（`usage.md`）大多出自 p2z 11-01 改版（95cea41）之前：真项目会话在 10-19 到 11-02 之间，排在前面的 `check_pdf`（28 次）、`doi_to_item`（14 次）改版时已删。`read_library` 改版前后一样；现在的导入流程（`prepare`、`save`）在真项目里几乎没跑过。
- 真项目里各选项被敲的次数（同一来源）：`--key` 40、`--cite` 34、`--dir` 33、`--collection` 23、`--out` 22、`--file` 20、`--dry-run` 14、`--batch` 10、`--limit` 10、`--all` 7、`--q` 5、`--version` 4、`--recursive` 4、`--force` 1；`-o` 93。
- 查现成工具（`existing-tools.md`，关键几条本机验证过）：这台机器是 Zotero 10.0.7，本地 API 不带 `limit` 一次返回全部（921 条），默认的快速搜索能按引用键和条目 key 精确命中，`/file/view/url` 直接给文件地址；Better BibTeX 遇到重复引用键默默取第一个，pyzotero 的命令行没有引用键寻址和 PDF 路径，都不替换我们的读库。

## 为什么值得做

- 用户喜欢、用着顺手。
- 这些命令主要是 agent 在用，Unix 的习惯是模型最熟悉的：`-n` 是空跑、`-` 是标准输入、标准输出只放数据，不读 `--help` 也能猜对。2026-11-04 主 agent 把管道接在 heredoc 脚本前面丢了数据，就是 Python 写法和 Unix 习惯拧着的一例。

## 做法和风险

- 2026-10 的 v3 逐处打补丁，脚本从 7.5k 行涨到 15.4k 行，用户：「我觉得现在一切都乱套了」。所以先定全系统的约定，再拿 p2z 做样板，改完 skill 要更短、更好用。
- 顺序：spec（全系统约定 + p2z 样板）→ 几路审阅和 advisor → 用户看过、点头 → 实施 → 用一阵 → 逐个 skill 铺开。
- 写进 `docs/design-principles.md`、AGENTS.md 的是规则层面的改动，先和用户讨论、确认再改。

## 参考资料

`20261104-skills-unix-conventions-reference/`，git 不跟踪：`inventory.md`（每个命令的盘点）、`conventions.md`（Unix 约定的出处摘录）、`taoup-ch10s05.html`、`usage.md` 和 `usage.py`（各命令在真项目里的使用统计）、`existing-tools.md`（现成工具调研）、`principle-draft.md`。
