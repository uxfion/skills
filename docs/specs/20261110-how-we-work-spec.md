# how-we-work：设计（进行中）

状态：**进行中**。用户 2026-11-10 说可以开始写 spec；设计是和用户一个问题一个问题定下来的，定一条写一条。标 **已定** 的是用户说过的；标 **没拍板** 的是 main agent 的提议或还没问到的。issue：[`docs/issues/20261110-how-we-work.md`](../issues/20261110-how-we-work.md)（用户的原话和每个决定的经过）；要定的事的先后：issue 参考文件夹里的 `decision-tree-20261110.md`。

## 1. 要解决的问题

用户有几个比较大的科研项目。他和 agent 之间怎么配合（约定、偏好、规则、没明说的规矩）现在散在各项目里，各不相同；同一句话他要在每个项目重说。用户：「有些话我重复提到很多次，我觉得烦，那就大家约定一个 how we work 不就好了」。

做成之后要看到的：用户重复说过的话都在里面，而且管得住；在一个项目里纠正一次，别的项目也照做；开无人值守时不用再贴那一大段叮嘱。

范围（已定）：比较大、比较复杂的项目，主要是科研。小项目不用，不为它们设计。它不是 harness 的配置，也不是全局指令；全局指令由用户自己管。

## 2. 整体

how-we-work 是 skills 仓库里的一个 skill，只有一套（已定）。内容按"什么时候要读"分三层：

| 层 | 装什么 | 放在哪 | 谁写 |
|---|---|---|---|
| 通用块 | 每个任务都要的：原则、怎么和用户配合、无人值守、subagent、提交、文档和记忆、不能碰的线、开工时的同步 | skill 里一份；复制进每个项目 `AGENTS.md` 里一个有标记的块（已定） | 只有同步脚本写项目里的这一块 |
| 各类工作的约定 | 做那类事才读的：报告、实验、文献、服务器、写论文、issue 和决定的记法、目录怎么摆 | 只在 skill 里一份；通用块里各有一行指过去（已定，S1 选 A） | 在 skills 仓库里改，照规则文字的审法 |
| 项目自己的 | 目标、项目的事实、本项目和通用不同的地方 | 项目里，块的外面（已定） | 项目里的 agent 和用户 |

内容的切法照 zym 现在的分法（已定）：`AGENTS.md` 只放每个任务都要的；某类工作才用的在那类工作的文档里；项目的方向在 `docs/goal.md`；琐碎的在记忆里。底稿是 zym 的 `AGENTS.md` 和它的约定文档，但不照抄：按用户后来的话更新，补上说了没写的，改掉把 agent 带偏的写法。

## 2.5 skill 里的文件怎么摆，项目怎么够到它（用户 2026-11-10 认可：「对的，那就是这样」）

how-we-work 是以 skill 的形式安装和执行的（用户 2026-11-10：「因为我们后面是以 skill 的形式去安装执行的」）。各 harness 把 skill 装在不同的地方，所以项目的 `AGENTS.md` 里不能写 skill 的路径；本仓库的规矩也是 skill 里只用相对于 skill 目录的路径。

- **够到 skill 的办法是调用它**，不是按路径去读。writing-for-agents 的说法：留在上下文里、指向上下文外材料的那句话是"指针"，决定 agent 去不去读的是指针的措辞。这里有两层指针：项目 `AGENTS.md` 通用块里的"做某类工作之前，调用 how-we-work，读它那一类的参考"；和 skill 自己的 `description`（一直在上下文里，写清哪些情形触发）。
- **目录照本仓库别的 skill**：

  ```
  how-we-work/
    SKILL.md            很短：是什么；开工时的同步怎么跑；各类工作各读哪份参考（一张表）
    common.md           通用块的原件，同步脚本把它写进项目的 AGENTS.md（名字用户定的：common，和"项目自己的"成对）
    references/
      unattended.md  reports.md  experiments.md  literature.md  papers.md  layout.md  records.md
      adopting.md       一个项目接入时读：每条旧规则都要有去处
      maintaining.md    改通用规则时读：规则凭什么占一行、怎么提议、怎么写才管得住
    scripts/
      hww.py            唯一的入口（命令：sync），照设计原则 §3 的 Unix 约定
    tests/
  ```
- **项目自己的约定**在项目里：`docs/conventions/<类>.md`，分"本项目专有"和"待提升"两段。标题用英文写死：`## This project only`、`## To promote`（脚本也认 `## 待提升`）。项目 `AGENTS.md` 块外的部分也可以有一节 `## To promote`，放每个任务都用的、看着通用的规矩。
- **skills 仓库在哪**：各机器本地的 `~/.config/how-we-work/config.json` 里的 `skills_repo`；不进仓库。项目里的 agent 往那里记 issue（`docs/issues/<日期>-how-we-work-<主题>.md`），这是"只写本项目"唯一的常设例外。
- **现状（2026-11-10 无人值守结束时）**：`how-we-work/` 已在仓库里建出并经过最后一道通读检查（68 处，逐条记录在参考文件夹 `subagents/final-review-applied-20261110.md`）：`SKILL.md`、`common.md`、九份参考（experiments、reports、literature、papers、layout、records、unattended、adopting、maintaining）、`scripts/hww.py`、`tests/`。没有安装、没有提交、没有推送。之后以 `how-we-work/` 里的文件为准；参考文件夹 `drafts/` 里的是它们的来历。
- 草稿阶段各类参考暂时叫 `drafts/conventions/<类>.md`（在 issue 的参考文件夹里），建 skill 时改放 `references/`。

## 3. 一条规矩怎么从一个项目长进通用部分

已定的路：某个项目里冒出来 → 先进该项目的记忆或它自己的部分，当场生效 → 成立而且不是该项目专有的，回 skills 记 issue → 用户审 → 进通用部分 → 各项目取到。通用还是专有，看它是不是用户一贯的做法，不看最先在哪个项目说出来。门槛（用户 2026-11-10：「里面加入的内容一般都是比较常用、经常提起的」）：是原则，或者是放到用户哪个项目里都成立的一贯做法，才进通用；说过几次只是证据，看的是这句话背后的原则（用户：「也不是说我第二次提到你就马上记，你也是根据它背后的原则规则来的」），原则已经在规则里的，把那一句写得够得着，不另加规则；只和一个项目的数据、方法、工具有关的教训，一个项目的做法，工具某次的表现，留在项目里；用户为定一件具体的事做的决定不算规则。写在 `references/maintaining.md` 的 *What earns a line*。

为了不让通用的规矩沉在某个项目里（已定，A1）：

- **项目自己的约定文件分两段。** "本项目专有"：每条带一句为什么只属于这个项目。"待提升"：说不出这个理由的都放这里。
- **同步时列出来。** 同步脚本更新通用块时，把本项目"待提升"段里的条目列出来。成不成立由 agent 判断；成立的去 skills 记一张 issue，用户审。脚本只列，不判断。
- 提升通过后，项目里那一条由项目里的 agent 删；脚本指出"这条通用里已经有了"，自己不删。

## 4. 同步

- **每个项目自己取**（已定）：agent 在哪个项目工作，就在那个项目里运行同步，只写这个项目 `AGENTS.md` 的通用块。不从 skills 往别的项目推：一个会话只写自己所在的项目。
- **通用块里写明开工时做这件事**（已定，用户：「如果你不提到的话，它是不会想到去同步的」「在开始干活前，你要去做对应的同步,也不只是同步，就是你前面说的那些工作流」）：开始干活前运行同步；看它列出的"待提升"和"通用里已经有了"的条目，照第 3 节处理。
- **同步脚本的约定**（main agent 定的，照设计原则 §1 和 §3 的 Unix 约定；没拍板）。入口 `how-we-work/scripts/hww.py`，现在只有一个词 `sync`：

  ```
  hww.py sync [-n] [FILE]        FILE 默认是当前目录的 AGENTS.md
  ```

  - 块的标记：`<!-- how-we-work:begin … -->` 和 `<!-- how-we-work:end -->`。`common.md` 自己也带这对标记；脚本把项目文件里从 begin 标记到 end 标记的整块（连标记）换成 `common.md` 里的那一块，所以 begin 标记里"不要在块里改"的那句也来自 skill。标记之外一个字节都不动；写的时候先写临时文件再替换，出错退出时原文件是原样。`common.md` 相对脚本自己的位置找。
  - 文件里没有这对标记：脚本不猜该插在哪，退出 2，最后一行是一个 JSON `{code: "no_block", hint: …}`。第一次接入时由 agent 在 `AGENTS.md` 里放好这对空标记（放哪是判断，归 agent），再跑同步。
  - 之后读 FILE 自己在块外的部分（每个任务都用的规矩，项目也可以标成待提升）和项目的 `docs/conventions/*.md`，把每个文件里 `## 待提升`（或 `## To promote`）一节下的条目列出来；块里的内容不读。成不成立、通用里是不是已经有了，脚本不判断。
  - 输出（stdout 是数据，一行一个 JSON）：块的一行 `{code: "ok", file, block: "updated" | "current"}`；每个待提升的条目一行 `{code: "to_promote", file, line, entry}`（围栏代码块里的列表项不算）。
  - 退出状态：0 = 块是最新的（或刚更新完），没有待提升的条目；1 = 有待提升的条目等着处理（stderr 末尾一行小结）；2 = 做不下去（没有标记、文件不存在、`common.md` 找不到）。
  - `-n`：只说会怎么改，不写。块没变、也没有待提升的条目时，除了那一行 `current` 什么都不输出。
- 由此改了通用块里的一句：原来写"同步会列出通用里已经有了的条目"，这要判断，脚本做不了；改成同步只列待提升的条目，是否已被通用规则覆盖由 agent 看。

## 5. 无人值守

- **目标是项目的目标**（已定，用户说后面可能还改）。对话里定下的任务排第一，做到用户会去检查的终点；它做完、被挡住或在等待时不停下，从项目目标出发，挑自己能做、不挤主线、对项目最有好处的事接着做；每做完一段回头看方向。实际上一直跑到用户回来或额度用完。该停的只有一种：剩下的事都压在用户的一个决定上，先做很可能白做；这时把选项准备到只差用户一句话，停下并告诉他。
- **用户只说这一轮的任务和资源**，固定的叮嘱在通用块里，不用再贴（依据：用户自己存的提示词，每次重贴的是同一段）。
- **哪些事留给用户**（已定）。线按"等用户那一句话会不会浪费第二天"划：用户睡前开，早上回来只做决定；他说完一句话之后剩下的应该是很快的组装，不是再跑很久。
  - agent 做了、回来在简报里说明（做了什么、为什么、怎么撤）；用户说不可以的下次不再做：重装；能撤销的小的系统安装；在用户的训练服务器上训练，卡空了就放，没点名的也可以；一个选择有几个选项时都跑出来；论文和对外报告按最可能的几个版本各备草稿和图表；现有规则有更好的做法时，当晚先照更好的做。
  - 等用户：把文字写进规则文档；对外的东西用哪一版、发不发；发布；删除不是这一轮自己建的东西；大面积的卸载、删除、改配置；训练服务器之外的别的机器、别的项目、项目外的文件；大方向的改变（各条路先跑出来）。
  - 三处读法（用户确认）：先照更好的做法做，不包括"等用户"这张单子本身；科研项目推到私有远端 agent 视情况定，公开仓库等用户；病人数据放开的只是用户自己的训练服务器，第三方的 API 和服务仍等用户。
- **开开关的那一刻**（已定）：把"等用户"的事里能当场定的赶紧问掉（用哪些服务器等），问的同时先做不依赖回答的事。10 分钟没有回音就当用户不在：照上面那条线往前准备，他回来时把结果快速组装给他。
- **训练服务器**：训练完把需要的都取回本机并核对，服务器上清理干净。
- **靠什么不无声停下：`/goal`，先试一次再定**（用户选 A）。文档查到的事实（subagent 查的，2026-11-10，未实测）：
  - 文档只写了用户输入 `/goal <条件>`，没写 agent 能不能自己设；本次会话 agent 的工具里没有它。所以现在按"只有用户能设"来设计。
  - 判断的是一个小模型（默认 Haiku），只看对话，不跑命令、不读文件：agent 没在对话里说出来的，它看不到。条件最长 4000 字符。连着几轮没有工具调用，循环会停下、条件还留着。
  - 一轮结束时还有 subagent 或后台命令在跑，这一轮不判断；它们回来时是新的一轮。空闲时 30 分钟、1 小时、2 小时各来看一次，两次用户消息之间最多三次。
  - 撞到用量上限时暂停，额度恢复后接着做。这一点用户 2026-11-10 实际见到了：5 小时额度刷新后会话自己恢复了。
  - 和它等价的是设置里的 Stop hook（`type: "prompt"`）；skill 的 frontmatter 可以注册 hook，对 prompt 型是否可用文档没写。这是"用户只说一句开启无人值守"的可能做法，要实测。
  - 完成条件的草稿（没拍板，给用户看的是中文；判断模型读的是这段英文）：

    ```text
    Unattended run. This condition is NOT met, and work continues, unless the conversation shows one of these:
    (a) The user has sent a message that ends the unattended run (such as 停止无人值守, 关闭无人值守, 我在线了), or any message after the run began that asks Claude to stop.
    (b) Claude's latest message has a section titled "Nothing left without the user" that (1) lists every remaining piece of work toward the project's goal, (2) names for each the specific decision of the user's it hangs on and why doing it first would likely be wasted, (3) shows that the options for each decision are already prepared (drafts written, variants run), so the user's word leads to quick assembly and not to another long run, and (4) states that the project's goal document, to-do list and open issues were re-read in this turn and nothing else can be done.
    These are not reasons to stop: the task named in the conversation is finished; a report or a commit was written; Claude says what it will do next; a question for the user is pending (it is queued and other work goes on); a training run or a subagent is still running (Claude does other work, or waits for it); something needs an install, a reinstall or a long run that Claude may do and report afterwards.
    When the condition is not met, tell Claude: pick the next piece of work from the project's goal that you can do yourself, that does not crowd out the main line, and that helps the project most; after each stretch, check the direction before choosing the next.
    ```
  - 为了让判断模型看得到，agent 每一轮结束前在对话里说一行现状：刚做完什么、接下来做什么、给用户排了什么。
- **每次无人值守一份目标文档，放 `docs/goals/<日期>-<主题>.md`**（用户提的，已定）。用户说"开启无人值守"时 agent 写它，要全面：这一轮的任务和背景、理解的目标、资源、会往前做什么、哪些等用户、完成条件；之后的过程记录和给用户排的单子也写在这份里。它取代 zym 的 `docs/specs/<日期>-<主题>-plan.md`。`docs/goal.md` 仍是项目的方向。
- **用户输入一行 `/goal`**（已定的方向，写法待试）：agent 把整行备好放在代码块里，用户粘贴。这一行是"一句显式的提醒加文档路径"：完成条件的要点（上面那段，可再压短）写在行里，全文在文档里。原因：文档查不到 `@路径` 在 `/goal` 里会不会展开、展开后算不算条件；有用户报告只指向文件的 goal 空转九轮后被判做不成（未经官方确认）。第一次真实的无人值守时试：这一行的写法、`@路径` 有没有用、小模型有没有早放或空转。不好用就退到定时唤醒。
- **`/goal` 的细节不现在定**（用户）：没有 `/goal`，agent 照目标文档也能自己往前做，带上它只是多一层保险；确定的是目标文档里要写完成的目标。具体怎么设，真跑的时候再定。
- **完成的目标怎么写**（用户）：它常常不是一个实在的终点，而是跟着任务来的（去做哪些尝试、探到什么程度）。所以目标文档里写的是：用户回来时要看到什么（主线的结果、探过的路各自的结果和比较、备好的选项），哪些尝试算这一轮该做的，以及唯一该停的情况；不硬造一个数字指标。
- **停下时通知用户：用 Bark 推到手机**（用户选 A：只在真停下时通知，正常干活不打扰）。配置在仓库外：`~/.config/bark/config.json`，JSON，字段 `server_url`、`device_key`。它是 Bark 自己的配置，不属于 how-we-work，别的 skill 和脚本也读这一份（用户：「它应该就是一个 bark 的 config，这样的话其他地方也可以用」）；分组这类每次不同的参数由发送的一方自己给；真实的服务器地址和 key 只在这个文件里，仓库里只写 `<bark-server>`、`<device-key>`。发送是向 `<bark-server>/push` POST 一段 JSON（`device_key`、`title`、`body`、`group`），照 Bark 官方教程。
- 没拍板：由谁在什么时刻发通知（agent 停下前自己发，还是配成 harness 的 hook）；由 skill 注册 hook 来省掉粘贴 `/goal`（要实测）。
- **额度：主线优先**（用户选 A）。先保证主线能跑完这一夜，余量再给并行的 subagent；并行的事分成"今晚必须出的"和"有余量再做的"。并行的个数按用户定的上限（现在 8 个）。subagent 用会话自己的模型，只有小的机械活用便宜的模型，不为省额度降级。

## 6. 改规则文字时给用户看什么

已定（用户 2026-11-10）：原文、原文的中文、修改建议、修改建议的中文、理由；改了的地方在四段里都做标记，让他一眼找到。一次一处。

## 7. 语言和目录

- skill 里的文件（通用块、各类约定）用英文，引用户的原话用中文（main agent 按"按读者定语言"定的）。
- zym 的目录摆法算通用的，新项目照它（main agent 按"zym 约定文档里的内容默认通用"定的）。旧项目搬不搬：没拍板。

## 7.5 内容上用户定了的几件（2026-11-10，「照提议」）

1. 报告分两类：给用户自己和组会看的，给外人的，规矩不同（进报告的约定）。
2. 检查 HTML 报告：不装东西的前提下可以用机器上已有的浏览器自己看排版；效果交给用户看。
3. 写错的记录：过时的保留加说明；从来不成立的从文档和记忆里清掉，会话记录不动。
4. 提交的署名行：默认不带，项目自己的部分要求时才带（skills 仓库带）。
5. 提交是存档，不是用户的批准：没给他看过的可以先提交，是否审过另外记。
6. 用户在场时，往项目的训练服务器上放训练（含病人数据）、推到私有远端，也由 agent 定、事后说。

7. 论文里对自己方法有利的呈现（用户：「按照你建议的来」）。可以：几种都如实的呈现里选最有利的，弱点说一次、说得轻，没人问的局限不展开。不可以：伪造；为赢而调评价方式。先汇报、由用户定：重大的不利发现；论文写的和代码、数据实际做的对不上的地方。

通用块的草稿在 issue 参考文件夹的 `drafts/common.md`（第二版，经过一轮审查；用户：篇幅不是指标，讲清楚就好）。从块里挪到各类约定的内容记在 `drafts/moved-to-conventions.md`。

## 8. 还没问到的

各主题的内容（提问、汇报、记录、服务器、提交、写论文）里用户说过两种做法的地方；先接哪个项目；skills 仓库自己怎么接入（它的设计原则 §4–§6 和通用块说的是同一些事）；旧 issue `20260929-agent-instructions-reusable-memories-wontfix` 怎么关。

## 9. 对照设计原则

- 符合：脚本只做确定的事（按标记列出、写自己那一块），判断归 agent，决定归用户（§1）；状态在文件里（§1）；一块只有一个写的人（§1）；一条知识一个家（§3）；约束都有"没有它出过事"的来由（§4）。
- 还没做：动手前的审查（§2.3）；这个做法没在真实项目里试过，打算先在 zym 上试一轮。
