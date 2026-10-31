# paper-to-zotero 越长越臃肿：查文献、取全文、读论文应该拆成独立的 skill，p2z 只管 Zotero 这一层

- 来源：用户 · 2026-10-29。在设计论文笔记的读法时提出，那张 issue 是 [20261028-paper-to-zotero-paper-notes.md](20261028-paper-to-zotero-paper-notes.md)。当时问题树刚定下来（那张 issue 的已定 28），用户说「A。 先不要在问了。有个设计上的非常重要的问题」，接着说了下面这段话。
- 参考资料：`20261029-paper-to-zotero-split-reference/`，git 不跟踪。里面放 Zotero 和 Better Notes 对外接口的调研。笔记格式、Better Notes 源码、实测结果放在论文笔记那张 issue 的参考资料文件夹里。
- 状态：open，按 spec `docs/specs/20261030-paper-to-zotero-split-spec.md` 改造中。§10 第 0 到 5 步已完成（2026-10-30）：存基线、笔记转换、paper-fetch、p2z 改成读结果文件、改说法、paper-read 的框架；待验证 2（真编辑器核对）已做完。§11 的验证和 code-review 都做完了。剩第 6 步收尾：README 已更新，推送和重装等用户发话。
- 和论文笔记那张 issue 的关系：读论文的流程、问题树和笔记格式，原来都打算放进 p2z（那张 issue 的"分工"一节）。如果按这张 issue 拆分，它们就归新的读论文 skill，p2z 只负责把笔记存进 Zotero、再取出来。

## 用户原话

「我现在觉得很多东西都被塞到了p2z中，实际上不应该，包括现在的读论文的方式，这些都应该独立出去，去维护的，而不是现在无脑地塞进现有的 p2z skill，它仅限于操作zotero这一层。我甚至觉得之前查文献的那些东西都应该独立出去形成新的skill。现在它越长越臃肿了，就应该是把各个功能独立开来，而且这些功能都是可以在其他地方用的。而且独立出去更好维护，p2z如果要用的话，引用对应skills就行了。」

## p2z 现在装了什么（2026-10-29 查的）

- **大小**：SKILL.md 33k 字符，references 7 个文件共 66k 字符，脚本 23 个、加上 `p2zlib` 共约 8.7k 行。
- **按功能分，有五块**：
  1. **操作 Zotero 库**：`read_library`、`find_in_library`、`check_item`、`create_item`、`attach_file`、`file_and_tag`、`make_collection`、`update_item`、`merge_items`、`trash_item`、`lint_items`、`export_bib`、`note`、`structured`（结构化包的 take/put），以及 `p2zlib/zotero.py`。参考文件有 `organize.md`、`tagging.md`、`attachment-titles.md`。
  2. **认出论文、拿到元数据**，即"查文献"的前一半：步骤 1"Pin the paper"、步骤 2"Draft the record"、`doi_to_item`（DOI/arXiv 转元数据，查正式发表版），参考文件 `no-doi-record.md`；Instruments 里的 opencli 适配器（openalex、arxiv、semanticscholar、dblp……）和 `papers-cool-search`。
  3. **取全文**，即"查文献"的后一半：步骤 3"Get the file: the chain"、`fulltext_links`、`fetch`、`claim`、`check_pdf`、`wait`、`p2zlib/{browser,web,verify}.py`；Rules 里的"Reaching a page""Gate""Agents you send"，参考文件 `publishers.md`（26k）。
  4. **读论文**：SKILL.md 里的"Reading a library paper"一节，结构化包的取用（调 paddleocr），以及正在设计的论文笔记读法。
  5. **一次导入的运行机制**：`ready`、`report`、`p2z.py`、`p2zlib/{run,cli,config,paper}.py`、`batch.md`、`install.md`。
- 这些违背了 `skill-design-conductor-principle` 的第 2 条"Orchestrate, don't absorb"：别的事情应该交给别的 skill，p2z 却把它们都揽到了自己身上。

## 讨论记录（用户原话逐字）

1. 用户提出拆分（见上面的原话）。
2. 我列了 p2z 现在的五块，提议拆成四个：认论文、取全文、读论文、p2z。我开了这张 issue。用户在这时插话：「你先不要做，你应该先跟我讨论，在做的」。之后我在磁盘上没有再改任何东西，直到讨论定下来。
3. 用户：「writing for agents里也有相关的设计理念吧」。我引了 writing-for-agents 讲 sprawl、按调用拆、共享参考放一处的三段，仍然推荐四个。
4. 用户：「你现在就属于我说什么就是什么的阶段，你没有独立全面的真正思考过这个问题背后的逻辑。现在也不能拆太多，一些东西本身就应该是p2z的。包括怎么attach file，添加笔记等。读文章形成笔记肯定是独立的一个。笔记操作是交给p2z的。去找文献的pdf应该也是一个。你需要全面思考设计一下，不要我说什么就是什么，你要有独立的思维能力，探索后再和我讨论」
5. 我去看了代码，见下面"调研"。我收回了单独的"认论文"，改成三个，并问认论文的那一半放在哪边。
6. 用户：「我还是看不太清楚，到底怎么分的，给我预览一下，会有哪几个skills，负责什么内容」。我给了一张三个 skill 加 paddleocr 的预览。
7. 用户：「你自己拟定一个skill名然后给我看」。我拟了 `paper-fetch` 和 `paper-reading`，`paper-to-zotero` 不改名。
8. 用户：「我想知道，现在的 fetch 和 reading 会不会不一样，因为有一个加了 ing」。我按仓库里"对象 + 动词原形"的格式（`vllm-serve`、`papers-cool-search`），改成 `paper-read`。
9. 用户：「然后给我预览一下每一个 skills 的职责是否划清了」。我列了每个 skill 负责什么、交出什么、不做什么，以及九处边界上的划法。
10. 用户：「你自己根据 writing for agent 设计原则还有之前就已经探索过的mattpocock/skills设计理念，再全局过一遍，看是否合适，是否优雅、合理、高效」。我用五个检验过了一遍：删除测试、真接缝要有两个以上使用者、按调用拆、知识放一处、变化快慢。结论是三分法站得住，另提了四处改动（见"已定"的 5 到 8）。
11. 用户：「你自己给fable advisor过一下」。advisor 认为划分和四处改动都站得住，指出我说错的两处和漏掉的三处（见"已定"9 到 11、"待验证"1）。
12. 用户：「没什么讨论的，就这样吧。但是你需要跟我讲一下，简略一点，就是每一个技能的职责范围是什么？就是要取到什么东西，或者管什么东西。你给我预览一下」
13. 用户：「另外我还有一个问题：skill 之间你是怎么传递信息的？比方说 paper fetch 和 paper to Zotero 之间用什么格式传？」我答：skill 之间不直接对话，由 agent 先跑一个 skill，再把它写下的文件路径交给下一个；交接的是磁盘上的文件。paper-fetch 每篇论文写一个 JSON（字段见已定 9，元数据用 CSL）和 PDF，p2z 读它，再写自己的记录。p2z 和 paper-read 之间已经是这个做法：`structured take` 交出结构化包和 `<stem>.zotero.json`，paper-read 交回笔记的 Markdown 文件，由 `note --file` 存进 Zotero。没拍板。
14. 用户：「我想了解一下，这个工作目录是指我的项目的工作目录，还是说你的临时工作的scratchpad」。我答：是 agent 的临时目录。p2z 现在的 `ready` 也是这样，有 scratchpad 就用 `<scratchpad>/paper-to-zotero`，没有就用 `${TMPDIR:-/tmp}/paper-to-zotero`，任务结束时在第 6 步清掉。拆分以后照旧：交接的文件都放在临时目录里，不进项目。最后留下来的只有 Zotero 里的东西（条目、PDF、结构化包、笔记），项目里只留它自己的决定。
15. 用户：「可以，这就合理了。因为我感觉你之前就没有讲清楚，用了一个工作目录，就让人误导了」，接着说：「这个也肯定要在 issue 里面提到的呀。不然的话，你老是说"工作目录"，别的 Agent 拿到就可能会想当然地把它视作项目的目录了。issue里有写吗？」当时只写在第 14 条里，"已定"里没有。补成已定 11。
16. 用户：「你这边记录完就回到我们刚才那个split issue上面吧」。我去查"待验证 1"中不用写库的部分，结果见"待验证"一节。问用户选哪个方案。
17. 用户：「路二。之后别再用这种路x的表达了，很奇怪，要么就123 ABC 方案x」。定为已定 12。issue 里我自己写的"路一""路二"，改成"方案 A""方案 B"。
18. 我问配置怎么分，给了三个方案：
    - A：每个 skill 一个自己的文件；
    - B：paper-fetch 也去读 p2z 的文件；
    - C：换一个中立的共用文件。
    我推荐 A。用户：「A」。定为已定 13。
19. 我说了 p2z 笔记命令打算补的四样：读回成 Markdown、写两层列表、建独立笔记并设"相关"、按正文搜。然后问先写拆分的 spec，还是先把论文笔记的问题定完。我推荐方案 1，现在就写。用户：「1 . 有一个问题啊，刚才你提到的，我不太懂 Zotero 里面的笔记是用什么格式保存的，怎么用，你需要去查清楚。还有，我知道有一个叫做 Better Notes的插件，而且我也已经安装了。」
    - 我查到用户装的插件是 Better Notes for Zotero 3.3.3，另外还有 Better BibTeX 9.0.71、Zoplicate 5.1.1、Translate for Zotero 2.4.8、Ethereal Style 6.0.99。
    - 笔记的存储格式，2026-10-28 已经查过，见 `20261028-paper-to-zotero-paper-notes-reference/zotero-notes.md`。
    - Better Notes 当时只凭记忆写了一句，这次另派一个 agent 去查，结果写进同一个参考资料文件夹的 `better-notes.md`。
    - 定为已定 14：先写拆分的 spec。写之前先把笔记格式和 Better Notes 查清楚，因为 p2z 的笔记命令要按查到的情况来定。
20. 我先用库里两条真实笔记讲了存储格式：一条是用户在编辑器里写的，外面包着 `<div data-schema-version="9">`；一条是 agent 经接口写的，是裸 HTML。用户：「具体关于 Zotero 里面笔记相关的内容，所有的信息内容是怎么存的，以及有哪些限制，你都需要查清楚。然后markdown具体怎么转换的？因为我看到 Better Notes 里面是有一个从 Markdown 导入的，它有没有相关的api等，这些都需要前期去调研清楚，你才能进行下一步」
    - 我另派一个 agent 补 Zotero 本身的空缺：数据库怎么存、同步服务器的清洗、图片、编辑器打开和保存外来 HTML 时的行为、Zotero 自己的 Markdown 粘贴和复制。结果写进 `zotero-notes-storage.md`。
    - Better Notes 由先派的那个 agent 查，结果写进 `better-notes.md`。
    - 两份都回来、我合成以后，才进入下一步。
21. 用户：「对，你也可以自己去新建一个笔记条目，然后查一下」。我在 `tmp` 分类（`RIBA5MZJ`）建了一条独立测试笔记，key 是 `JXD7NQZI`，标签 `p2z-note-test`，第一行写"论文笔记（测试，可删）"。HTML 里放了：
    - h1 和 h2；
    - 两层列表；
    - 加粗、斜体、行内代码；
    - 指向 Chung 2023 PDF 第 6 页的 `zotero://open-pdf` 链接，以及 `zotero://select` 链接；
    - 引用块、表格、特殊字符。
    本地 API 读回来，除了末尾的换行被去掉，和写进去的一字不差（版本 13562）。条目 JSON 里没有笔记的标题字段。接下来要用户在编辑器里打开它、改一个字，看编辑器保存时怎么改写。测完移进回收站。
22. 用户在我建测试笔记时插话：「我不理解，你之前开发之前都不去做一些详尽的调研的吗？」我答：笔记这块没有。`note` 命令是 2026-09-23 做的，当时只测了一件事：标记行的几种写法，本地 API 会不会原样存回。脚本注释里写的"编辑器只保留自己的 schema"是推断，从没实测过。v3 和 10 月的重构都把它标成"不变"，没人再看过。10-28 为论文笔记做的调研是第一次全面看，但 Better Notes 只凭记忆写了一句"不要依赖它"，写库测试也都推到了"拍板以后"。这一轮我又在调研之前，先提了笔记命令要补什么。已记进记忆：动手设计之前，先把要碰的东西从源码查全，包括用户装的插件，最后做一次真实的写库测试。
23. 用户在编辑器里打开了测试笔记，加了一条待办"这是我加的"，发来两张截图，并说：「Better Notes没有啥……我也没用过，所以不太清楚其他的功能。你看一下调研的那个 subagent，看有没有什么东西吧」。读回来的结果见参考资料 `note-roundtrip-test.md`。要点：
    - 编辑器保存时套上了 `<div data-schema-version="9">`；
    - `<li>文字</li>` 变成 `<li>\n文字\n</li>`；
    - 下面挂着子列表的 `<li>`，文字被包进 `<p>`；
    - 表格单元格里的文字也被包进 `<p>`；
    - 链接被加上 `rel="noopener noreferrer nofollow"`，`zotero://` 的地址保留；
    - 标题、段落、加粗、斜体、代码、引用块、转义字符都没变；
    - 待办存成 `<li>[ ] 这是我加的</li>`。

    显示上，两层列表、表格、引用块、链接都正常，Better Notes 在左边显示了按标题生成的大纲。
24. 用户发来笔记编辑器"…"菜单的截图，问：「我甚至看到了这个，我不知道这个是 Better Note 里面的功能，还是本身 Zotero 自带的」。我在 Better Notes 3.3.3 的 xpi 里搜了每个菜单项的中文字串，它的 `locale/zh-CN/BetterNotes-addon.ftl` 里有：打开笔记到新标签页、打开笔记到 BN 新窗口、在文库中显示、以 Markdown 编辑、导出当前笔记、插入模板、更新模板生成内容、复制行、复制节、更新关联笔记。"在文献库中显示"和"在单独窗口编辑"不在里面，按排除法是 Zotero 自带的；没有在 Zotero 程序包里找到原字串，Windows 上没在 Program Files 里找到 Zotero 的安装目录。
25. Better Notes 的调研回来了，见参考资料 `better-notes.md`。对设计有影响的几点：
    - 它的接口 `Zotero.BetterNotes.api`，包括 `md2note`、`note2md`，都只能在 Zotero 里面用 JavaScript 调，没有 HTTP 接口，外面的 agent 调不到；
    - Markdown 同步不适合给 agent 当镜像：只在 Zotero 窗口在前台时导入，导入后会按它自己的写法重写文件，冲突时弹合并窗口，登记表按本机条目 ID 存在 prefs 里；
    - 打开笔记不会改它，只有用户操作时它才写；
    - 用户用"以 Markdown 编辑"或"从 Markdown 文件导入"时，它会用自己的写法重写笔记 HTML：`li` 里套 `<span>`，一个 `li` 里的多段合成一段，schema 版本定为 9；
    - 笔记之间的链接写在 HTML 里，格式是 `zotero://note/u/<KEY>/`。它为链接建一个只在本机的索引，但新建笔记时不建，只在笔记被修改时建，而且 3 秒内只处理第一个和最后一个；Zotero 自己打不开这种链接；
    - 大纲只显示 h1 到 h6，写成嵌套列表的问题树不会出现在大纲里；
    - 待办是普通 `<li>`，文字以 `[ ] ` 开头，和第 23 条的测试一致。
26. 用户：「你去查了 Betternote，是没有对应的 API 可以给外面调用的是吧？因为我想着，如果 betternote 有接口或者有程序或者有一个入口，我们就能少写很多东西，而且能复用别人的，这样效率也会更高一点。另外有一点问题，你看"树"用哪种形式记录比较好一点？因为是树形的结构嘛，我看到有一个关系图，这是什么？」
    - **Better Notes 没有对外接口**：它的 `src/` 里没有注册任何 HTTP 端点。
    - **但有一个通用入口**：Better BibTeX 的作者 retorquere 发布了 Zotero Debug Bridge 插件，3.0.1 版。它在本地 API 的端口上开一个 `POST http://127.0.0.1:23119/debug-bridge/execute`，凭 Zotero 设置里的 `extensions.zotero.debug-bridge.token` 作 Bearer token，在 Zotero 里面执行传进去的 JavaScript。
      - 它支持 Zotero 7 到 12，源码在 `retorquere/zotero-better-bibtex` 的 `test/fixtures/debug-bridge`，2026-09 还有提交。
      - 已经有人基于它做了 Python SDK `Xp-speit2018/zotero-bridge`，能调 Zotero 自己的"按标识符添加"和"查找可用 PDF"，也能加笔记。
      - 有了它，就能从外面调 `Zotero.BetterNotes.api` 和 Zotero 自己的功能。
      - 代价是：本机任何拿到 token 的程序，都能在 Zotero 里执行任意代码；还要多装、多依赖一个插件。
      - 这会牵动已定 12（CSL 转条目），以及 p2z 的不少设计。我先只读它的源码查清楚，装不装由用户定。
    - **关系图**：Better Notes 画的是笔记之间的 `zotero://note` 链接，就是一条笔记和链向它、它链出的那些笔记。数据来自它的链接索引，只画笔记到笔记的链接。测试笔记没有链接，所以图上只有一个点。它画的不是一条笔记内部的结构。
    - **树怎么记**，我提了三个方案：
      - A：列表放在最前面当目录（即已定 28），回答写在下面的标题里；
      - B：标题本身就是树，问题按层级用 `##`、`###`、`####`，状态写在标题末尾，回答写在标题下面，不另写列表；
      - C：两样都要。

      我推荐 B，没拍板。
27. 用户：「你也可以去派subagent 查一下，Zotero 有没有这种对外的接口，或者 betternote 有没有这种对外的接口，直接 web search 就行了，这种都应该在确定方案之前做好详细的调研的」。我派了两个 subagent 并行去查，可以用网页搜索，结果放进这张 issue 的参考资料文件夹 `20261029-paper-to-zotero-split-reference/`：
    - `zotero-external-interfaces.md`：Zotero 的所有对外接口，包括 Debug Bridge、MCP 服务、translation-server 等；
    - `better-notes-external.md`：Better Notes 能不能从外面用，以及 Zotero 外面现成的笔记 HTML 和 Markdown 转换工具。

    查清之前不再提方案，树用哪种形式也一并暂缓。
28. 用户：「B . 另外装这个Zotero Debug Bridge插件完全可以，而且能便利化很多。或者你再查一下有没有更好的方案，其实，如果原作者就是他的话，我们倒真可以用起来，我只是以防万一有更好的选项让你去查一下」。定为已定 15、16。论文笔记那张 issue 的已定 28 和"问题树"一节已经跟着改了。
29. 用户：「能复用就尽量复用，我的原则。我们避免去造这种复杂的轮子，能用起来就用别人的，而且本身 Zotero 的插件系统就是比较完善的」。定为已定 17。
30. 查 Zotero 笔记存储和限制的调研回来了，见论文笔记那张 issue 参考资料里的 `zotero-notes-storage.md`。用户：「https://zotero-chinese.com/ 我一般找插件都是在这个网页上」。我让查对外接口的那个 agent 把这个站的插件列表也查一遍：找能让外面程序调用的插件，以及处理笔记、Markdown 的插件，每个都对照它的 GitHub 仓库核实。只交给这一个 agent，免得两个 agent 同时访问同一个网站。
31. Better Notes 对外使用的调研回来了，见 `better-notes-external.md`。要点：
    - 没有对外接口，也没有计划做；
    - 有 6 个项目在 Zotero 里面跑代码、另开出口来用它，只用到最简单的 `md2html` 和 `html2md`；
    - Zotero 外面的现成工具都只能单向转换；
    - 它建议用 Python 库自己搭转换。

    用户：「另外我在zotero-chinese.com找到了推荐的这两个项目：https://github.com/54yyyu/zotero-mcp https://github.com/yilewang/llm-for-zotero」。我把这两个转给查对外接口的那个 agent，要它读源码深查：怎么连 Zotero、提供哪些操作（尤其笔记的读写和转换）、能不能用于 Zotero 10 和 WSL、装些什么、维护情况、风险、我们能复用哪些。
32. 对外接口的调研回来了，见 `zotero-external-interfaces.md`。四份调研合起来的结论（我的综合，没拍板）：
    - **从外面调不到 Zotero 自己的"按标识符添加"和"查找可用 PDF"**：本地 API（Zotero 10 起能写）能写条目、分类、标签、笔记 HTML、上传文件，但不跑 translator；connector 只有间接的路，而且会改用户窗口里的选中项。
    - **要复用 Zotero 自己的功能，就得在 Zotero 里面跑代码**，也就是装一个桥接插件。可选的有：
      - Debug Bridge 3.0.1：Better BibTeX 作者做的，本来是测试工具；收到什么代码就执行什么；发布版靠 Zotero 10.0.6 的一个兼容层加载，没实测；
      - Zotero JS Bridge 1.14（Sum-su）：作为产品来做，有只读开关、可单独关掉某个端点、写入默认先试运行，作者在 10.0.2 上验证过；只有一个作者，2 颗星；
      - 一些大的功能插件，比如 llm-for-zotero：能调 `Translate.Search`，但也对外开放执行 JS 和 shell，笔记转换会把多层列表压平。
    - **另一条路是 translation-server**（独立的 Node 服务，跑 Zotero 的 translator）：不找 PDF，用不上桌面端的代理和 cookie，还得多跑一个服务。
    - **笔记的 HTML 终归要我们自己生成**：Zotero 没有服务端的 Markdown 导入，`setNote` 存什么就是什么。可复用的部件有：
      - Markdown 转笔记：54yyyu/zotero-mcp 的 `note_html.py`（MIT 许可，基于 markdown-it-py，保留 Zotero 自己的属性和 `zotero://` 链接）；
      - 笔记转 Markdown：Zotero 自带的 "Note Markdown" 导出 translator（基于 turndown 和 GFM），有了桥接就能调。
    - **会被牵动的已定**：已定 12（在 p2z 里按 schema 对照表转 CSL）。有了桥接，可以直接让 Zotero 的 translator 从标识符建条目。paper-fetch 仍然要负责认出是哪篇论文（把题目变成 DOI 或 arXiv 号），以及走学校登录、出版商页面的下载；Zotero 的 `addAvailableFile` 可以作为它找 PDF 的一条路。
    - 先问用户第一件事：用哪个桥接插件。
33. 我推荐装 Debug Bridge，并让 Zotero 的 translator 来建条目。用户：「也不是说所有的东西都要复用，像translator，就是建条目，查DOI还有信息这些，完全是你自己用脚本或者你自己agent处理的会更优的，拿到的信息也更全，而且能检查。你自己要评估一下的。不要以为的认为我说的话就是金标准，我只是给你一个建议，后面还是需要和你讨论、权衡利弊，并决定出一个比较好的方案的。你是否懂我的意思，自己调研一下，并与我讨论」。接着：「你这个问题遇到很多次了，你总结反思一下，并更新记忆」「而且查元信息本身agent就比zotero做的好，你调研一下，如果做的好的，我们肯定是要保留的，不会用那个差的方案。」「其他的功能也是这样，你记一下，下次别犯了，这个原则」。
    - **我的反思**：把用户的建议和自己记忆里的规则当成绝对标准，被纠正时又跳到另一个极端，然后用原则把结果包装成"有道理"的样子。这一次我也没去看自己的旧记录：第一版 spec（`docs/specs/20260921-paper-to-zotero-spec.md` §3.5、§3.6）早就比较过 Zotero 的识别器和我们的元数据流程，结论是"对本 skill 的正常路径没有增益"。
    - **已更新记忆**：`own-judgement`（先权衡再提议的六步，被纠正时重新权衡，不翻转）；`skill-design-conductor-principle`（新的第 2 条：复用靠逐项比较，我们的更好就留我们的）。
    - **改定已定 17**，并撤回第 32 条里"有了桥接就让 translator 建条目、推翻已定 12"的说法。已定 12 照旧。
    - 我另派一个 agent 用证据比较两边：元数据这一块，是我们的流程好还是 Zotero 的 translator 好；顺带比较找 PDF 这一块，是我们的取全文链好还是 Zotero 的"查找可用 PDF"好。结果写进 `metadata-and-pdf-comparison.md`。比较回来之前，桥接装不装先不定。
34. 比较回来了，见 `metadata-and-pdf-comparison.md`。比较用了三类证据：Zotero 源码、用户库里的统计、6 篇论文的同篇对比。结论（agent 的判断，我认同）：
    - **元数据：留我们的。** 只给一个 DOI 时，两边的结果差不多。agent 的那几步补上了 Zotero 做不到的：
      - 摘要：我们建的 727 条里 719 条有摘要，Zotero 的 DOI 路径在抽查的 4 个 DOI 上一条摘要都没给；
      - PubMed 号：170 条；
      - 按题目查到正式发表版：Zotero 的 arXiv translator 有 21 篇留着没处理，其中 5 篇 arXiv 自己的备注里已经写了被录用，它仍然留作预印本；
      - 写库前能预览、能查重，过程全在我们手里。

      **Zotero 更好的地方**，这几条要搬进我们的代码，不依赖 Zotero：
      - LNCS 论文的论文集标题：10 月 7 日到 10 日建的 7 条，把丛书名当成了论文集标题，脚本后来修了，但 lint 查不出这 7 条；
      - arXiv 预印本的日期：我们 78 条里 68 条只有年份，Zotero 给完整日期；
      - 几个小字段：期刊缩写、会议地点、论文集 ISBN、LNCS 卷号。

      **作者关键词是我们流程自己没做到**：规则要求收集，727 条里只有 47 条有。Zotero 存 IEEE Xplore、ScienceDirect 网页时每条都有。
    - **找 PDF：留我们的链，不加 Zotero 的"查找可用 PDF"。** 它在这台机器上没有学校登录那条路，只能拿到开放获取的版本；它不核对文件是不是这篇；它按 Unpaywall 的说法标版本，16 次里只对了 2 次；还得装桥接才能调。它的开放获取来源 Unpaywall，我们已经经 OpenAlex 用上了。值得借鉴的是它对 ScienceDirect、PMC、MDPI 这些站的处理办法，可以写进 `publishers.md`。
    - **桥接只剩一个可能的用处**：把笔记转回 Markdown，即 Zotero 自带的 Note Markdown。下一个问题是装不装。
35. 我问桥接装不装，给了两个方案：
    - A：先不装，笔记读回 Markdown 在 Zotero 外面做；
    - B：现在就装 Debug Bridge，只用来调 Note Markdown。
    我推荐 A。用户：「可以。A吧。另外你要去调研一下现在比较好的markdown工具是哪个，要选型的。」定为已定 18。我另派一个 agent 做 Markdown 工具选型，结果写进 `markdown-tools.md`。库里那几处元数据问题和测试笔记，已经记进记忆 `zotero-library-todo`。
36. 选型回来了，见 `markdown-tools.md`，测试脚本和样例在 `mdtools/`。比较的办法是把候选工具真装上，拿我们的样例跑：调过的 28 个边界情况，另有 16 个没调过的。结论：
    - **写入（Markdown 转 HTML）**：用 markdown-it-py，配置和 Zotero 粘贴 Markdown 时一样，再加 `dollarmath`（公式）和 `mdit-py-cjk-friendly`（中文加粗紧挨"："时的问题），约 17 行配置。然后接一段我们自己移植的编辑器序列化代码 `editor_shape.py`，约 240 行。它写出的 HTML 和用户在 Zotero 里保存后的样子逐字节一致，以测试笔记那一对为准。
    - **读回（HTML 转 Markdown）**：先用同一段 `editor_shape.py`，把编辑器写法、我们没保存过的写法、Better Notes 写法、普通 HTML 都归成同一棵树，再用我们自己的 `walker.py`（约 155 行）转成 Markdown。
    - **现成库在读回上都输了**：
      - 调过的 28 个情况，walker 过了 28 个，markdownify 过了 11 个，html-to-markdown 过了 14 个；没调过的 16 个，三者分别过了 15、13、16 个。
      - 这两个库转义要么太多、要么会改坏内容，还会丢掉编辑器里的对象。
      - html2text 是 GPL 许可。pandoc 是 155 MB 的 GPL 程序，读回只得了 2/10。
      - mdformat 会改变意思，比如把 `**结论：**作者` 转义坏、给列表重新编号，所以不用它来规范化。读回本身就是规范化。
    - **合计**：我们自己的代码约 410 行。依赖全是纯 Python 的 MIT 包。还有约 15 行的缺口待补：
      - 外层的 `data-citation-items`；
      - 段落缩进、对齐，这一处现在会真丢数据；
      - 链接里的括号会被转码。
    - **含引文的笔记**不会稳定在一个样子：Zotero 第一次打开时会重新生成引文。
37. 我推荐方案 A，即 markdown-it-py 加 `editor_shape.py` 加 `walker.py`，约 410 行。用户：「我觉得不优雅，为什么拒绝掉了Pandoc」。我查了当时的测法：
    - 读回只用了 `pypandoc.convert_text(html, "gfm+tex_math_dollars-raw_html+raw_html", format="html", extra_args=["--wrap=none"])`，没用 Lua filter，也没预处理 Zotero 特有的写法；
    - 写入只在输出后用正则改了公式。

    pandoc 本来就靠 Lua filter 来处理这类特有写法，所以 2/10 测的是没配过的 pandoc，这样拒绝不公平。逐条看当时的拒绝理由：
    - 转义 `$`、`_`：因为 Zotero 的公式是 `<span class="math">$x$</span>` 里的普通文字，用 filter 把它变成 Math 就不会转义；
    - 有 `rel` 的链接变成裸 `<a>`：用 filter 去掉属性就好；
    - 转义 `[已答]`：可以改用全角的 `【已答】` 避开；
    - GPL：我们是把 pandoc 当外部程序调用，不受它约束；
    - 真正的代价只剩两样：155 MB 的二进制文件，以及要不要写成编辑器保存时的样子。

    我另派一个 agent 用同一套样例和边界情况，公平地重测"pandoc 加 Lua filter"，结果写进 `pandoc-retest.md`。
38. 用户：「还有什么方案」。我把可选的路按三个层次列出来，没拍板：
    - **要不要来回转换**：
      - (1) 来回转换：存 HTML，读回成 Markdown 让 agent 改，再写回去。这是现在的方向，要有读回器。
      - (2) 只转一次：读论文时写 Markdown，存进 Zotero 时转成 HTML，这是唯一一次转换。以后的改动按标题分节进行：agent 给一段 Markdown，脚本转成 HTML，换掉或追加到某个标题下面。agent 要看笔记时，直接看 HTML，或者看一份只读的粗略 Markdown，这份不写回。这样不需要读回器，也不需要模仿编辑器的写法；用户在 Zotero 里的改动也原样保留，因为不再整条重新生成。
      - (3) Markdown 是正本：Markdown 另存一份，比如作为附件，Zotero 里的 HTML 只是它生成的副本。用户在 Zotero 里一改，两边就冲突，要合并。不推荐。
    - **转换器用哪个**：自己的组合（markdown-it-py 加 `editor_shape` 加 walker）、pandoc 加 Lua filter（在重测）、两者混用（写入用 markdown-it-py，读回用 pandoc，或者反过来）。
    - **要不要模仿编辑器保存的样子**：要（约 240 行），或者不要（接受写回时的格式变动）。在 (2) 里这个问题自然就没了。

    我倾向 (2)，等用户的意见和 pandoc 的重测结果。
39. 用户：「如果我们只用md，而不用html的其他格式，是不是会更好些」。我的判断是会更好，但有两个前提：
    - **我们写进去的**只用 Markdown 能表达的元素：标题、段落、多层列表、加粗、斜体、行内代码、链接（包括 `zotero://`）、引用块、GFM 表格、`$…$` 公式、分隔线。待办写成列表项里的 `[ ] 文字`，Zotero 和 Better Notes 本来就是这么存的。
    - **用户在 Zotero 里加的**其他东西，比如颜色、高亮、下划线、缩进、引文、图片，我们控制不了。读回时把它们当原始 HTML 原样带着，CommonMark 允许夹带原始 HTML，写回时也就不会丢。

    这样读回只需要认一小组元素，转换器选哪个都容易。它和方案 (2) 不冲突，可以一起用。我已经让在重测 pandoc 的 agent 加测这个"子集加原样透传"的情形。没拍板。
40. 用户：「另外你去看一下better note使用的什么方案」。答案在 `better-notes.md` §4，源码是 v3.3.3 的 `src/extras/convert.ts`、`src/utils/convert.ts`：
    - 它用 JavaScript 的 unified 生态做语法树转换，两个方向都是：
      - Markdown 转笔记：remark-parse 加 remark-gfm 加 remark-math，然后 remark-rehype，打开 `allowDangerousHtml`，原始 HTML 原样通过；最后是它自己的 rehype2note，做几处整理；
      - 笔记转 Markdown：先解析 HTML，再经 rehype-remark，用自己写的处理函数，最后 remark-stringify，带 GFM 和公式。
    - Zotero 特有的东西，比如引文、笔记链接、图片、高亮，它都写成原始 HTML，带上 `ztype` 标记，导入时再按标记还原。
    - 这正是"Markdown 子集加原样透传"的做法。在 Python 里对应的，是 pandoc 加 Lua filter：pandoc 也是先转成语法树再输出，filter 就相当于它的处理函数。
    - 它也不追求写出编辑器保存时的样子：转出来的 HTML 是它自己的写法，比如 `li` 里套 `<span>`、链接不带 `rel`，存进去以后由编辑器在用户下次改动时再整理。
41. 用户：「或者直接用html？我其实想不太好怎么规划，请帮我全面梳理设计一下。」我按一条笔记经过的五个时刻来梳理：
    1. 读论文的 subagent 写出它；
    2. 存进 Zotero；
    3. 项目的 agent 读它；
    4. 项目的 agent 改它；
    5. 用户在 Zotero 里改它。

    比较了四个方案：
    - A：从头到尾都用 HTML；
    - B：用 Markdown 写、存成 HTML，以后按节改；
    - C：Markdown 子集加原样透传，来回转换，就是 Better Notes 的做法；
    - D：整条来回转换，就是那 410 行。

    我推荐 A，没拍板：
    - **格式**：笔记从头到尾就是 Zotero 编辑器那一小组元素写成的 HTML。"只用 Markdown 子集"这条纪律原样保留，换成"只用编辑器支持的那组 HTML 元素"，由一个校验器把关。
    - **命令**：p2z 的 `note take` 把笔记取到临时目录 `<scratchpad>/<引用键>.<标题>.note.html`，旁边放一个 `.zotero.json` 记版本；agent 用普通的读写文件工具来看、来改；`note put` 先校验，再带版本号写回，取出之后用户改过的话就拒绝，要重新取。这套就是 `structured take/put` 的做法，加上 `note.py` 已有的按标记定位、带版本号写入。去掉的是 Markdown 转换，新增的是校验器，约 60 行。
    - **校验器检查**：
      - 只用编辑器支持的元素和属性；
      - 标签成对；
      - 第一行是 `<h1>`，因为标题取第一行；
      - 每个块前面换行，因为 Better Notes 按换行切分。
    - **代价**：HTML 读起来、写起来都比 Markdown 重，diff 也更乱。agent 维护一条一万多字的 HTML 笔记、改来改去会不会出错，还没试过。

    改定前要先试一条真笔记：用 T-CACE，让读论文的 subagent 写 HTML，然后校验、存进 Zotero，用户在 Zotero 里改一次，agent 再改一次，看会不会出问题。以后要是读 HTML 太费 token，可以加一个只读的 Markdown 视图，从不写回，所以来回转换的那些问题不会回来。这一条现在不做。

    A 会改动两条已定：
    - 论文笔记那张 issue 的已定 29，笔记文件 `.note.md` 改成 `.note.html`；
    - 这张 issue 的已定 1 和 9，原来写的是"paper-read 交出笔记 Markdown"，改成交出 HTML。
42. 用户：「我不太想全用html，因为本来我的文献材料产出也都是md，而且html有点重，要不要用better notes那种透传的方案，这样的话html的信息是否能保留」。用户倾向不全用 HTML，但还没定。我答，方案 C（Markdown 子集加原样透传）下，HTML 里的信息分三类处理：
    - **Markdown 能表达的**：标题、段落、列表、加粗、斜体、代码、链接、引用块、表格、公式、分隔线、待办文字。这些转成 Markdown、再转回去，内容不变，只是标签的写法可能换一种。比如编辑器保存时在 `li` 里加的 `<p>`、链接上的 `rel`，转回去以后会是我们的写法，但意思一样。
    - **Markdown 表达不了的元素**：颜色、高亮、下划线、上下标、引文、PDF 批注高亮、图片。这些作为原始 HTML 原样留在 Markdown 里，转回去时原样放回，一个字不改，Better Notes 的 `ztype` 就是这个做法。
    - **Markdown 能表达、但带了 Markdown 放不下的属性的块**：比如加了缩进或居中的段落。整块作为原始 HTML 留着，不转成 Markdown，否则属性会丢。这是第一次选型时找出的那处"真会丢数据"的地方。

    剩下的问题：
    - 引文里的文字 Zotero 打开时会重新生成，不会丢，但每次可能不一样；
    - 用户改过、agent 又整条写回的笔记，标签写法会变回我们的写法，内容不变。

    命令照 `structured take/put` 的样子做：
    - `note take` 把笔记转成 `<scratchpad>/<引用键>.<标题>.note.md`，旁边放 `.zotero.json` 记版本；
    - agent 改 Markdown；
    - `note put` 转回 HTML，带版本号写回；取出之后用户改过就拒绝。

    转换工具等 pandoc 重测的"子集加透传"结果再定：pandoc 加 filter，或者我们自己写一个只认这一小组元素的读回器。
43. 用户：「我还没确定，需要跟我权衡利弊」。我在第 42 条里写了"方案 A 就此放下"，这是替用户下了决定，已改成"倾向不全用 HTML，但还没定"。下一步和用户一起权衡 A 和 C，还要等 pandoc 重测的结果，没拍板。
44. 我列了 A 和 C 的利弊对照，倾向 C，前提是转换层要小、要稳。用户：「对啊，现在的markdown，比方说github上的readme.md不都是支持html的吗」。我答：
    - 透传是 CommonMark 和 GFM 规范本身允许的，有 HTML 块和行内 HTML 两种，不是取巧；
    - GitHub 不显示某些标签，是它出于安全自己过滤的，和 Markdown 无关；
    - markdown-it-py 打开 `html=True`，或者 pandoc 打开 `raw_html`，都原生支持透传；
    - 要注意两点：原样保留的 HTML 块里不能有空行，因为空行会结束一个 HTML 块；行内 HTML 里的文字仍按 Markdown 解析，要转义。

    这让 C 更站得住，没拍板，等 pandoc 重测。
45. 用户：「那难道就没有开源的方案或者工具去做透传版的相互转化吗，你去搜索一下，看有没有比较好用的，或者stars高的」。我另派一个 agent 去搜，不限语言：
    - JS：turndown 的 `keep()`，unified 的 rehype-remark，后者就是 Better Notes 用的；
    - Go：html-to-markdown v2；
    - Rust：htmd；
    - Python 里有"保留未知标签"选项的库；
    - 声称能无损来回转换的项目。

    排在前面的 3 到 5 个，直接拿我们的样例实测。测透传时，在编辑器存过的笔记里加颜色、高亮、下划线、引文、图片、缩进段落、居中段落，看来回一次后是否原样还在。另外测子集元素对不对、来回是否稳定，以及那 44 个边界情况。pandoc 交给另一个 agent，这里不测。结果写进 `passthrough-tools.md`。
46. pandoc 的公平重测回来了，见 `pandoc-retest.md` 和 `pandoc-retest/`。
    - **pandoc 配好以后**：用 pandoc 自己的 `markdown` 写法，加一个自己处理转义的 filter，得 10/10，调过的 28 个过了 28 个，没调过的 16 个过了 16 个。第一次选型的组合是 28 和 15。它更好的地方：
      - 链接里带括号也不出错；
      - 中文软换行处理得更好；
      - 写成编辑器保存的样子只要约 48 行，原来要 237 行。
    - **但它仍然不是首选**：
      - PyPI 上的 pandoc 是 3.9，有两个会丢字的转义 bug，分别在 3.10 和 3.13 才修好，还没有更新的包；
      - `**结论：**作者` 这种写法只有 pandoc 自己的 `markdown` 写法能解析对，而这种写法不是 CommonMark；
      - 它读 HTML 时会悄悄丢掉待办框、没有 `src` 的图片、段落属性（比如缩进）、`data-` 开头的属性，每样都得先预处理；
      - 包有 155 MB，GPL 许可，每次调用约 25 毫秒。
    - **最省的是"子集加透传"**：markdown-it-py 加一个 138 行的读回器，不要 `editor_shape.py`。
      - 模拟用户加的颜色、高亮、缩进，4 处全部保住；两套完整方案都把缩进丢了；
      - 编辑器存过的写法和没存过的写法，读回来都和原来的 `note.md` 逐字节一样；
      - 边界情况 28 和 16 全过。不过这个读回器是在知道全部 44 个情况之后才写的，16 个那一组不算盲测；
      - Better Notes 的待办能对上，靠的是一个还没证实的假设：编辑器会把 `<input>` 复选框转成 `[ ] ` 文字。
    - **`【已答】`**：避开了全部 `\[ \]` 转义，7 个标题全对。样例里剩下的转义只有 `p\<0.05` 和 `\<特殊字符\>`。
47. 我列了方案 1 到 5（全 HTML；Markdown 加透传，用我们 138 行的读写；用 pandoc；用现成的透传工具，待测；410 行的完整来回，已排除）。用户：「GitHub 的 Markdown就没有开源的方案吗」。我答：
    - GitHub 用的是它自己开源的 cmark-gfm（C 写的，CommonMark 参考实现的分支），Python 里是 `cmarkgfm`；
    - 它只管 Markdown 转 HTML。GitHub 从不需要把 HTML 转回 Markdown，所以没有读回这一半；
    - 写入这一半，第一次选型实测它 13 项过 10 项，输给 markdown-it-py：没有公式支持，`$…$` 里的 `_` 变斜体；`- [ ]` 变成编辑器会丢掉的 `<input>`；中文加粗失败；不能插入自己的处理；
    - Zotero 自己粘贴 Markdown 用的就是 markdown-it。
48. 用户：「那写入定下来markdown-it-py。读回呢」。定为已定 19。读回这一半，透传工具的实测表已出（agent 的最终报告写进 `passthrough-tools.md`）。同一套样例，9 个工具 20 种配置：
    - **默认配置下，所有现成工具把用户加的 9 处格式全丢了（0/9）**。它们的目标是把任意网页变成好看的 Markdown，表达不了的就扔掉；
    - 配置好、再加上我们自己写的转义，最好的两个是 JS 的：unified（rehype-remark，Better Notes 用的就是它），关键写法 11 项过 10 项，调过的边界 28 个过 25 个（无表头表格、代码块、空段落），约 60 行 JS；turndown 是 10/11、24/28，约 54 行 JS。两个都要 Node 和约 20 个 npm 包，Python 里起 Node 子进程调用。本机已有 Node v24；
    - Python 现成库里最好的 html-to-markdown，9 处格式只原样保住 3 处，28 个过 15 个；Go 的 html-to-markdown 23/28，Rust 的 htmd 22/28；showdown、lute、htmlarkdown 更差；
    - 我们 138 行里的 129 行读回器：9/9、11/11、28/28、16/16，只用 Python 标准库。16 个那一组不算盲测；
    - **关键一块是转义**：判断一个字符在这个位置会不会被当成语法。没有一个现成工具做对，要么到处加反斜杠（`snake\_case`、`\[已答\]`），要么不加，字面文字就变成了格式。所以用现成工具也省不掉我们自己的代码，只是挪到 JS 里，还多一门语言和一串依赖。

    我按已定 17 比较，推荐用自己的读回器，采用前补两项检查：一是盲测，另派 agent 不看读回器代码，按编辑器的 schema 新写一批边界情况，只跑一次；二是 Better Notes 的待办框，先读编辑器源码看 `<input>` 会被存成什么，源码看不清再请用户在测试笔记里点一下。盲测如果暴露出很多问题，修起来变成打补丁，就换 unified。等用户定。
49. 用户：「因为我想着，我们现在都是用python去做的，如果突然加个js会不会非常奇怪」。我答，会有代价，但要分清代价在哪：
    - 调用别的语言写的工具，把它当黑盒命令用，本身不奇怪。opencli 就是 Node 写的，p2z 一直在调它；pandoc 是 Haskell 写的；
    - 方案 2 的代价是我们得自己写约 60 行 JS（配置加转义），要自己维护。这样一个 skill 里我们自己的代码就分在两门语言里：两套依赖管理（uv 和 npm），装 skill 多一步 `npm install`，Python 要起 Node 子进程传数据，出了错两边都要查，另一台机器也得装 Node；
    - 这一层代价让方案 1 更站得住，但它只是加分项，不是决定项：如果 unified 明显比我们好，多一个 Node 依赖也值得，就像 opencli。现在是它本来就不比我们好。
    - 这改了第 48 条的退路。不用 JS 之后，盲测出问题不再自动换 unified。零散的几处问题就修读回器；如果显示读回器的思路本身有问题，就回来重新讨论。pandoc 带 Lua filter 和 155 MB 的二进制，同样是第二门语言，Python 现成库又差太多。
50. 用户：「可以，自己写吧，另外，自己写的读回器，是不是可以参考better notes里的」。定为已定 20。我去看了 Better Notes v3.3.3 的源码（AGPL-3.0），答：可以参考，但只取知识和样例，不抄代码。
    - **待办框这项检查，读源码就有了答案，不用用户点**：`src/extras/editor/taskList.ts` L27-35 写明，勾选状态存成普通 `<li>` 里的 `[ ] ` 或 `[x] ` 文字，复选框只是显示出来的样子，因为编辑器的 schema 里列表项没有属性。这和测试笔记 `JXD7NQZI` 实测存下的 `<li>[ ] 文字</li>` 一致，也和我们写入器的输出一致。`<input>` 只会出现在 Better Notes 从 Markdown 文件导入、还没被编辑器重存的笔记里（`convert.ts` 不处理待办），编辑器重存时会丢掉它。读回器加一行，把 `<input type="checkbox">` 转成 `[ ] ` 文字就够了。
    - **要参考的**：
      - **它的测试样例**：`test/utils/note.ts`，大约 240 行真实的笔记 HTML，加上它期望的 Markdown，由 `export.spec.ts`、`import.spec.ts` 断言。这是别人写的、读回器的作者没见过的样例，正好拿来做盲测的一部分。只放在 git 忽略的参考文件夹里，在本地测，不进仓库；
      - **它认得的 Zotero 对象清单**：引文看 `data-citation`，笔记链接是 `zotero://note/u/KEY/`（结尾要有斜杠），图片看 `data-attachment-key`，批注高亮，公式是 `span.math` 和 `pre.math`，删除线是 `line-through` 的 span。拿来核对读回器原样保留的那组元素有没有漏；
      - **它记下的已知损失**，当作边界情况：一个列表项里两段会被并成一段；列表里的行内公式旁边会多出空格；没有表头的表格；代码块的语言会丢。
    - **不参考的**：
      - 它的 Markdown 写法（`*   ` 列表、缩进 4 格、松散列表）和到处加反斜杠的转义。实测比我们的差，写法也已经由已定 19 定了；
      - 它把引文改写成 `ztype` 标记、导入时再从 `data-citation` 重新生成的做法。这是为了让人在 Obsidian 里手改文件，我们原样保留 HTML，更简单，也不丢东西；
      - 它的 unified 流水线，第 49 条已经排除。
    - **盲测**用两份样例：Better Notes 的样例，加上一个不看读回器代码的 agent 按编辑器 schema 新写的一批。
51. 透传工具的最终报告回来了，见 `passthrough-tools.md` 和 `passthrough/`。结论和第 48 条的表一致：
    - 默认配置下没有一个能用：turndown、unified、Go 的 html-to-markdown、htmd、Python 的 html-to-markdown，都把 9 处用户加的格式全丢了；showdown 把整条笔记当成一个 HTML 块，什么也没转；
    - 配置好以后，有四个能保住全部 9 处，来回一次就稳定，但没有一个能达到子集读回器的 28/28 和 16/16。它们都会给没表头的表格补出一个表头，也会丢掉空段落；
    - 只有 turndown 和 unified 能换上我们自己的转义；
    - 省不下代码，还多一套运行环境：Node，3 到 117 个 npm 包；
    - htmd-py 是唯一能在 Python 进程里跑的，但它的转义不能配，有三处会丢字，Python 绑定才 0.1.2 版。
    - 报告建议给子集读回器补两项：把这次新做的透传样例和"未知元素"检查加进它的测试，它现在两项都过；以后 agent 要是写带围栏的代码块，就把第一次选型里"去掉 `<pre>` 结尾换行"那条规则放进写入器。
52. 用户：「不用担心许可证，这些都是我自用的，不会商业化，也不会被别人使用，自用的完全不用担心」。以后选工具、借代码和样例，许可证都不算一条考虑。第 50 条和已定 20 里"因为 AGPL 不抄代码"的理由改掉了。不搬 Better Notes 的代码，原因是技术上的：它的转换写在 unified 的语法树上，是 TS，搬不进我们的 Python 读回器。能直接借的是它的规则，比如认笔记链接的正则；还有它的测试样例，以后可以作为读回器的回归测试放进仓库。我提了一句：仓库是公开的，AGPL 管的是分发，不管商业不商业；实际风险很低，按用户说的不考虑。
53. 盲测回来了（2026-10-30）。写样例的 agent 没看过读回器，写了 64 个新样例，加上 Better Notes 的测试样例。读回器没改，只跑了一次。脚本在 `blind-eval/eval_blind.py`，逐条分类在 `blind-eval/triage.md`。
    - **跑之前我定了两处约定**，期望结果按这两处改了，原件留作 `*.orig.md`：
      - 笔记链接 `zotero://note/…` 在编辑器里就是普通的 `<a>`，所以读成 Markdown 链接；
      - 最外层的 `<div data-schema-version … data-citation-items …>` 不进 Markdown，由 `note take` 存进旁边的 sidecar 文件，`note put` 时放回去。
    - **分数**：Markdown 和期望逐字一致 33/64；来回一次不变 49/64；读两次结果一样 53/64。Better Notes 的样例来回不变，但 Markdown 和期望不一样。之前的 28/28 和 16/16 是过拟合的结果。
    - **判断**：思路站得住，实现过拟合了。结构上的东西全都没出错：最外层 div、嵌套列表、表格、各种 Zotero 对象的透传。出问题的全是 CommonMark 里能一条条列出来的具体规则，有 13 类、约 16 个样例真的丢了内容或结构：
      - 段首的 `[1]: 网址` 被当成链接定义，整行消失；
      - 标题结尾的 ` #` 被当成闭合符号，被吃掉；
      - 加粗和斜体相邻或交叠时写坏；
      - 格式边缘的空格丢了；
      - 链接标题里的引号没转义；
      - 中文、空格网址被写入器改了编码，`file:` 链接被拒；
      - 连续空格和不换行空格被合并；
      - 起始号不是 1 的有序子列表并进上一段；
      - 两个相邻的有序列表并成一个；
      - 原样保留的 HTML 块后面紧跟 Markdown 时，Markdown 被吞进 HTML 块；
      - 引用或列表里的多行 `$$` 公式，被 dollarmath 插件的一个 bug 写坏。
    - **转义恰恰是弱点**。之前说"按位置转义"是我们比现成工具强的地方，这次两头都出了错：该转义的没转义（`[1]:`、结尾的 `#`、引号），不该转义的转了（`C:\\temp`，表格里的 `\-`，句中的 `\*`）。要照规范重写，而不是一处一处补。
    - **还有两处约定没覆盖到**：代码块读回成 `<pre>` 加一串 `&nbsp;`，硬换行读回成 `<br>`。原来 138 行版本的子集里没有这两样。
    - **裁判也没核实过**：判断"来回不变"用的是第一次选型时写的仿编辑器程序。它会改动 64 个输入里的 12 个，已经发现一处误判失败（span 里的链接没补 `rel`）和一处误判通过（列表的 `dir` 属性两边都丢了）。另外旧的 44 个样例里，有 3 个并不是编辑器真实存下的样子。整套测试除了那一条测试笔记，从来没碰过真的编辑器。所以 49/64 只能说是"按我们仿的编辑器算"。

    我的提议，等用户定：
    1. 兜底：每个顶层块读成 Markdown 后，用写入器写回再读一遍，不一样就把这一块原样保留成 HTML。最坏只是这一块显示成 HTML，不丢内容。13 类里能兜住 10 类，下一轮发现的同类问题也兜得住。代价是读回器要调用 markdown-it-py，不再"只用标准库"；markdown-it-py 本来就是写入要用的。
    2. 兜不住的 3 类都和空白有关，单独处理：不换行空格和连续空格写成 `&nbsp;`；边缘带空格的加粗、斜体保留成 HTML 标签。不换行空格是正文内容，不是格式。
    3. 照 CommonMark 规范重写转义。
    4. 补上代码块和硬换行。
    5. 用真编辑器核对（见待验证 2）。
    6. 修完另派 agent 写一批新样例，再盲测一次。

    这不挡 spec：spec 写的是设计，也就是子集加透传、按块兜底、约定补上代码块和硬换行、最外层 div 进 sidecar。读回器修到什么程度是实现的事。
54. 用户：「那和以前使用现有的项目的读回器方案测一下，因为你之前评估的不准，那应该要重新选的」。我同意：之前的比较是拿我们调过的样例比的，对我们自己的读回器偏心，所以要用同一套盲测样例重比。这套样例对所有读回器都是新的。我让做透传工具调研的那个 agent 接着做，它的测试架子都在。
    - **参加比较的**：`passthrough-tools.md` 里所有配好的方案，配置原样冻结；我们的子集读回器（没修过的原版）；pandoc 子集读回器加 `escape.lua`；第一次选型的 walker 加 `editor_shape`；markdownify 和 Python 的 html-to-markdown 配好的版本。写入一律用 markdown-it-py。
    - **每个读回器跑两种**：原样；加上按块兜底。按块兜底就是第 53 条提议里的第 1 条，它不挑工具，谁都能套。
    - **排名看三项**：会不会丢内容；读两次是否一样；Markdown 的质量，也就是该写成 Markdown 的有没有留成 HTML、有没有多余的反斜杠。和期望逐字一致这一项只作参考，因为期望是按我们自己约定的写法写的，对别的工具不公平。
    - **裁判**：除了现有的仿编辑器程序，能做到的话，再用 Zotero 编辑器真实的 schema 源码在 Node 里搭一个裁判，只在测试里用，不进 skill。两个裁判判得不一样的地方单独列出来。
    - 每个方案只跑一次，看过结果后再改的，单独标"调过"。
55. 重新比较的结果回来了，见 `reselect-blind.md` 和 `passthrough/blind/`。13 个读回器，每个跑"原样"和"按块兜底"两种，两个裁判各判一遍，样例只读一次，什么都没调。
    - **新裁判**：直接用 Zotero 笔记编辑器自己的 schema 代码（zotero/note-editor@acec74d），在 Node 里跑，只用于测试。我们唯一一次实测的 Zotero 保存，它逐字节复现。它和旧的仿编辑器程序判得不一样的地方，全是旧程序已知的毛病：漏判 `dir`、`id`、对齐、缩进丢失，误判 span 里链接的 `rel`。以后测试用它当裁判。
    - **原样用，没有一个能用**：64 个里丢 15 到 51 个。最少的是我们的子集读回器（15），其次 unified（20、22）、htmd（23）、turndown（24）、第一次选型的 walker（26）。
    - **加上按块兜底，每个都只丢 1 到 2 个**。所以决定"丢不丢"的主要是兜底机制，读回器的差别主要体现在 Markdown 写得好不好。
    - **最好的是子集读回器加兜底**：只丢 1 个（"两个相邻的有序列表"，所有读回器都丢，是兜底机制的缺口）；读两次一致 63/64；127 个块里只有 16 个退回成 HTML，别的读回器是 23 到 82 个；多出来的 HTML 标签 72 个，别的是 101 到 253 个；纯 Python，不加依赖。
    - **第二是 unified 加兜底**：也只丢 1 个，但退回 HTML 的块多（23 到 26），多出的标签 122 到 125 个，还要 Node 和 117 个 npm 包。
    - **兜底用什么来判断"对不上"**：
      - 用新裁判最准，但 skill 运行时就要带上 Node 和 jsdom；
      - 用旧的仿编辑器程序，多丢 1 个（`dir`/`id`）；
      - 只看"读两次是否一样"，子集读回器丢 5 个：13、14（格式和链接边缘的空格）、23（连续空格）、36（相邻列表）、59（`dir`/`id`）。别的读回器这样判要丢 9 到 36 个，因为它们丢内容多半是"稳定地丢"，只有裁判看得出来。子集读回器丢的多半读两次就不一样，自检抓得住。
    - **兜底机制自己要补两处**：相邻的同类列表要换分隔符，或者合成一块读；一块非空的内容读成空 Markdown 时要退回 HTML。另外，写入器写围栏代码块时，`<pre>` 结尾会多一个换行，要用第一次选型那条规则去掉。
56. 用户：「那就是还是我们原来的方案，然后加兜底」。定为已定 21。下一个问题：兜底时靠什么判断"这一块对不上"。
57. 我给了兜底判断的三个选项：A 纯 Python 自检（读两次一样、看得见的文字一字不差，加两条通用规则）；B 旧的仿编辑器程序；C 编辑器源码做的新裁判，运行时带 Node。我推荐 A。用户：「但是，你需要全面地设计一下，要把这个东西写得优雅一点，就是把它抽象成一个脚本，然后就可以相互转换」。我把转换整体设计成 p2z 里的一个双向脚本，A 放在里面当兜底，设计见下一条回复，等用户看。
58. 用户（我写设计时插话）：「Skills 本来就只用纯 Python 的，我从来没有想要引入过 Node。」所以选项 C 不成立。skill 的代码和它在仓库里的测试都只用 Python。用编辑器源码做的 Node 裁判，只作为这次设计用的量具，留在 git 忽略的参考文件夹里，不进 skill，也不进仓库测试。skill 调用的外部命令行工具（比如 OpenCLI）是工具，不算 skill 代码。
59. 我给出转换脚本的整体设计（`note_md.py`，见那条回复），问用户整体这样设计可不可以。用户先说了只用 Python 的原因：「因为 UV 这一套对于包管理、像命令行一样的脚本调用，这些都管理得很好。而且它还有包内脚本的包管理，可以直接运行。我就不喜欢在外面再去加什么东西，只要一个 UV 就可以解决」。对设计的影响：markdown-it-py 和两个插件写进脚本的 PEP 723 块，由 uv 取，不再像第一次选型提议的那样把插件代码拷进仓库。
60. 用户：「不对，我觉得调用方式还是要再抽象出来，有点类似 Linux 的设计理念，可以支持管道或者参数。你不要太草率，Linux 的设计理念我记得我们这个项目中之前也提到过」，接着说：「而且你现在这么写 to-md 或者 to-html 有点怪怪的吧」。项目里之前定过：p2z v2 spec（`docs/specs/20260923-paper-to-zotero-v2-spec.md`）已定 5「接口按 Unix 方式」，脚本是过滤器，管道让循环消失；§3.3 的约定是输入用路径，没给路径就读 stdin，输出到 stdout，诊断写 stderr，`-i` 写回原文件。现在的 `note.py` 是用 `--file`/`--text` 给内容，不是这个样子，正好借这次改过来。`structured take` 仍然写进目录，因为结构化包是一个文件夹，不是一条流。草稿在 `note-cli-draft.md`。我的提议（等用户定，一次问一个）：
    - 转换脚本 `note_md.py` 做成过滤器：`note_md.py [文件]` 把笔记转成 Markdown，`note_md.py -r [文件]` 反过来，和 `xxd -r` 一个路数；不给文件就读 stdin，结果写到 stdout。方向不用格式名来叫；
    - 一条笔记就是一份 Markdown，开头用 front matter 写上 key、parent、version 和最外层 div 的属性。这样一条管道就能把整条笔记带过去：`note.py get … > x.md`，改完 `note.py put x.md`。代价是版本号和那串很长的 citation-items 会出现在 agent 读、改的文件里，而且 front matter 由两个脚本一起写。另一个做法是 sidecar，元数据不进正文，但管道就断了；
    - 下一个问题：`note.py get` 一次取多条时，用什么形式输出（按 §3.3 每条一行 JSONL，带 `md` 字段；还是像 `structured take` 那样写进目录）。
61. 用户：「另外我有一个问题，为什么在项目根目录下会有 local API 这些东西啊？乱放啊？」查清了：2026-10-29 10:21，调研 Zotero 对外接口的 agent 要比较各版本的 `server_localAPI.js`，执行的是 `cd <scratchpad>/zotero; for t in …; gh api … > localAPI_$t.js`。那个目录不存在，`cd` 失败了，`;` 让后面的循环接着在项目根目录跑，四个文件就落在了根目录。内容已经写进 `zotero-external-interfaces.md`，文件本身随时能从 GitHub 重取，所以删掉了。教训记进记忆：派 agent 时让它先建好要写的目录、用 `&&` 串起来；agent 结束后我跑一次 `git status`，清掉它留下的东西。
62. 用户：「当然，除了 Linux 那种也要写，比如输入输出、指定一个地址之类的。就不要只写这个，你应该清楚的，考虑得全面一点。B。你觉得是Note MD好还是HTML MD好？」用户选了 B：方向用 `-t md|note` 指定。我推荐的是 A，用户定了 B，照 B 做，记成已定 22。我把命令行补全了：
    - **`note_md.py -t md|note [输入…] [-o 输出]`**，`-t` 必须给；
    - 输入：不给路径，或者给 `-`，就读 stdin；也可以给一个或多个路径；
    - 输出：
      - 不给 `-o` 就写到 stdout，这时只能有一个输入，因为几条笔记拼成一条流没有意义，给了多个会报用法错误；
      - `-o 文件`：一个输入，写进这个文件；
      - `-o 目录/`：每个输入写成 `目录/<原文件名>.md` 或 `.html`；
    - front matter：`-t md` 把最外层 div 的属性写进 front matter；`-t note` 从 front matter 读回来，重建最外层 div；别的键原样不动，留给 `note.py`；
    - stderr：平时什么都不写；有块被自检退回 HTML 时，每块写一行，说明是哪一块；
    - 退出码：0 成功；1 有输入读不了或转不了，其余的照转；2 用法错误；
    - 一律 UTF-8；`note.py` 直接 import `to_md(html)` 和 `to_note(md)` 两个函数；
    - **`note.py` 照同一套约定**：`note.py take (--cite C | --key K) [--marker M] [-o 输出]` 一条笔记写到 stdout 或 `-o 文件`，多条用 `-o 目录/`，每条一个 `<cite>.<title>.note.md`。不用 JSONL，因为 Markdown 塞进 JSON 字符串以后 agent 没法读。`note.py put [输入…] [--dry-run] [-i]` 从路径或 stdin 读，key、parent、version 从 front matter 取；版本对不上就拒绝写；`-i` 把新的版本号写回文件的 front matter。动词沿用 `structured` 的 take/put；
    - **p2z 里输出选项的名字要统一**：`-t/--to` 现在在 `structured take` 里指目录，到这里指格式，会让人弄混。spec 里统一成：`-o/--out` 指输出写到哪里（文件或目录），`-t/--to` 只指格式。`structured take --to DIR` 和 `doi_to_item --out-dir` 都改成 `-o`。
    - **名字**：我推荐 `note_md`，`-t` 的值也用 `note` 而不是 `html`。原因：它只认 Zotero 笔记的 HTML，也就是最外层 div、编辑器的写法、引文和公式的标记，并不是通用的 HTML 转换器；叫 html，会让人以为随便一个网页都能转。`note` 也和 p2z 里的 `note.py`、Better Notes 的 `md2note`/`note2md` 叫法一致。等用户定。
63. 用户：「这样比较优雅了是吧？」我答，大体是，但还有一处不够优雅：front matter 由两个脚本一起写。改法是让 front matter 只在 `note_md` 一处读写：`to_md(html, meta)` 把 `meta` 字典和最外层 div 的属性一起写成 front matter；`to_note(md)` 返回 `(html, meta)`。`note.py` 只和字典打交道，不碰 front matter 的格式。那串 `citation-items` 照样保留，排在 front matter 最后：去掉它，在 Zotero 里删掉条目后引文会变成 `()`，就违反"不丢内容"这条保证了。另外说明：设计上优雅只是纸面上的，代码能不能写小，要等重写完、再盲测一次才知道。
64. 用户：「可以的。然后前置条件都已经处理完毕了吗？现在是根据 issue 去撰写 spec 是吧？」定为已定 23。我答：前置条件都处理完了，只剩两件不挡路的事：一是把论文笔记那张 issue 里归 p2z 的几条改归 paper-read，写 spec 时一起做；二是用真编辑器核对（待验证 2），放进 spec 的实现验证里。接着开始写 spec。
65. 写 spec 前派了一个 agent 清点 p2z 的代码，结果在 `inventory.md`（commit `ae09458`）：23 个脚本里，13 个留 p2z，4 个归 paper-fetch，6 个要拆；`p2zlib` 的 9 个文件里，1 个留 p2z，3 个归 paper-fetch，4 个要拆，1 个两边各带一份。改动设计的两点：
    - doi.org 给的 CSL 用的是 Crossref 的词，比如类型是 `journal-article`，不是 CSL 的 `article-journal`。所以 paper-fetch 要先把 CSL 规范成 CSL 自己的词，再交给 p2z。另外，`build_item` 本来就在查 schema 的对照表，已定 12 要换掉的只是对照表管不到的那些规则，没有"三四百行"那么多；
    - 交接是双向的：取哪个版本的全文，取决于 p2z 选哪个版本作为条目。spec 定成三步：paper-fetch 先 `identify`，p2z 选版本，agent 再把选定的那份结果文件交给取全文的脚本。paper-fetch 从不读 p2z 的记录。
    spec 初稿是 `docs/specs/20261030-paper-to-zotero-split-spec.md`。三个审阅 agent 同时在看，分别看忠于决定、技术对错、新 agent 能不能照着做，之后再给 advisor 看。
66. 三份审阅回来，spec 改成第二版。主要改动：
    - **自检改成比结构**：只比"看得见的文字"抓不住带加粗的 `<pre>` 写成围栏、表头列的 `<th>` 变成 `<td>`、属性被丢。现在改成把写回的 HTML 和原块规范成一棵树（标签、属性、文字）再比；
    - **退回的 HTML 不能有空行**：类型 6 的 HTML 块遇到空行就结束，退回的块写出后也要再验一次；
    - **结果文件只由两个前台命令写**：`identify` 写元数据，新写的 `settle` 把 `fetch.jsonl` 的事件汇总进去。后台监视器只追加事件，避免互相覆盖；
    - **选正式版用 `identify --redraft` 原地重认**，`draft_item --redraft` 重新生成条目。`record_of` 字段说明这份 CSL 描述的是哪个版本，"强制成 preprint"只看它；
    - **结果文件放进 `results/`**，不和过程文件混在一起；
    - **新依赖要能加载**：转换代码放进 `p2zlib/note_md.py`；`p2z.py`、`run_all.py` 改用 `uv run --script`；版本钉死；
    - **补全了命令行**：补上了 `identify`、`draft_item`、`read_bib`、`settle`、`claim --label`、`find_in_library --file` 的接口；
    - **拆分不改行为**：Zotero 做得更好的元数据改进挪到 §13，以后单独做；
    - **其他修正**：front matter 的格式写死，不是 YAML；正文的分隔线写 `***`；去掉全角【已答】那句，转义规则本身不会转义 `[已答]`；整理文库时不动"主题笔记"分类；共用代码的清单从 `inventory.md` 写进 spec；没有 DOI 的论文仍经 connector 存，作为已定 18 之外的现有例外。
67. advisor 审了第二版，补了四处：
    - 结构比对的规范化本身就是一个很小的编辑器模型，和没选的方案 B 是同一类，只是规则少得多。spec 里写明了这一点，也写明了它出错时往哪边错：规则太松会漏掉真丢的东西，太严只会让某块多退回 HTML。所以拿不准时宁可严。这一点要跟用户说清楚；
    - `take` 遇到同一个 key 的同名文件，直接覆盖，因为 `version_conflict` 之后重新取到同一个目录是正常做法；
    - 忘了跑 `settle` 时，`attach_file` 报 `unsettled`，不会悄悄一个文件都不挂；
    - `read_bib` 遇到没有编号的条目，输出 `title:` 开头的一行，`identify` 报 `needs_pinning`；核对 schema 时，要查规范 CSL 用到的全部键。
68. 我把 spec 第二版的整体和"新加的清单"给用户看过以后，用户说：「你自己审一遍吧，看有什么低级错误，或者顶层设计上的不优雅」。自审找出五处低级错误、两处顶层设计，都已改进 spec，记在 spec 的 §14。最要紧的一处：`claim --file` 会删掉交给它的文件，原来那样写，给库里的 PDF 定标签时会删掉 Zotero 存储里的原件。顶层设计的两处：选版本挪到建记录之前，条目只生成一次；`fetch`、`claim`、`wait` 结束时自己汇总，`settle` 不再是一个容易忘的步骤。

69. 用户：「可以开始。另外你需要注意，你要有自己的判断，有自己独立的思维能力，不是一味的认定为事实，要懂得反思，有思考的能力，对我们这个skill有用的，能让其更好用的，更优雅的，更能快速使用的，朝着好的方向发展的等，都是可以采纳的。另外尽量不要修修补补，要从根源上解决问题，从顶层设计，全面的设计，要优雅、高效、便利。同时你在优化的时候要调用writing for agents skill。开启无人值守。」中途又说：「你自己向前推进，朝着好用、高效、优雅的方向发展。」「关键节点你需要停下来思考，不要着急一味的去解决，去修修补补，从不同角度看待问题，当前方案是否是最优的？有没有更好更聪明的解法」。我从 §10 第 0 步做起。
70. 第 0 步存基线（spec §10、`baseline/README.md`）。取 IEEE 那篇时，代理的登录页被我当成了只有用户能过的关口，推送提醒后等到超时。用户：「这个你自己点击，这个问题之前遇到过的，在p2z中肯定也提到过」。p2z 的 `publishers.md` 确实写了：发现系统的 Sign in 走学校的单点登录，会话还在就直接登上，我没先读它。第 2 遍时会话已经在，同一条路直接下到了 PDF。这件事和路上看到的另两处，记成三张 issue：`20261030-paper-to-zotero-proxy-login-not-a-gate`、`-short-title-cannot-judge`、`-cvf-link-missing`。
71. 第 1 步笔记转换做完（spec §5.3、§5.6 已按实现改过）。在关键处停下来想过、比 spec 原稿更好的几处：
    - **模型按编辑器的存法建**：段落内容是一串带标记集合的文字段，不是嵌套的树。这样 `<strong><em>` 和 `<em><strong>`、被加粗切开的链接都算相同，而且读回器从模型写 Markdown，"稳定"由构造保证，不靠事后检查；
    - **退回 HTML 的范围尽量小**：段落先试 `*`、再试 `_`、再试 HTML 标签，单元格放进单列表格里检，一处加粗写不成只让那一段用标签；
    - **公式规则自己写**，替换插件那条，修好了列表和引用里的多行公式；
    - **没有外层 div 的笔记不再被套上一个**，读出写回不变。

    100 个样例全部"结构不变"且"稳定"；14 个样例里有块退回 HTML，都是 Markdown 说不了的东西。补充的 7 条整篇笔记抓出两个真 bug（显示公式没过自检；没有外层 div 的笔记被套上一个），都已从根上改掉。`note.py` 换成 take/put/list，`put` 用同一个模型判断"没改"；用新的 `note put` 把 79 个样例拼成一条测试笔记放进了 `tmp`（key `8KAG38U2`），读回一致，再 put 一次报 `unchanged`。

72. 第 2 步 paper-fetch 做完（`6ea7d15`、`65b12ee`、`3fe066e`、`384f301`）。顺序是 advisor 建议的：先定接口（`pflib/run.py`：结果文件、汇总、标签事件），用 `check_pdf` 做样板，`identify` 自己写，其余四个脚本（fulltext_links、fetch+wait、claim、ready）派四个 subagent 照接口并行移植，再由我统一检查。移植中发现一处设计漏洞：监视器原定只认有 `try` 事件的论文，但 `fetch` 一条路试完才记 `try`，试第一条路时下载的文件、第一条路就停在验证页的论文都对不上。subagent 在两个脚本里各写了一份绕过的代码；我改从根上解决：`fetch` 每一遍开始时给要取的论文各记一个 `pass` 事件，监视器认 `pass`、`try`、`stop` 三种，绕过的代码删掉。验收：三篇基线论文 `identify` 出来的字段和基线条目对得上；拿基线的三个 PDF 跑 `claim --file`，核对结果、版本、md5 都一样，原件留在原处。两项配置已拷进 `~/.config/paper-fetch/config.json`。
73. 待验证 2 的真编辑器核对。我请用户打开测试笔记时只给了 key，用户：「你需要注意一点，我在zotero界面是看不到 8KAG38U2 这个名字的，他不是显示在界面中的，我只能看到标题"p2z note_md 真编辑器核对（测试，可删）"，你下次要注意了。我已经修改了一些内容。」以后叫用户在 Zotero 里找东西，说窗口里看得见的标题（已记进记忆）。取回来比对的结果：
    - 存回来的那版读出写回"结构不变"且"稳定"；
    - 和送进去的相比，差别要么是用户改的（加字、删字、后半篇加粗），要么是编辑器自己的规范化：样式重写（十六进制颜色改成 `rgb()`、末尾补分号）、链接加 `rel`、标记换了先后、列表项里的空白；退回 HTML 的那张合并着色的表格，单元格的背景色被编辑器拷到了文字上。没有一处是 note_md 丢的；
    - 要改转换器的只有一处：编辑器的标题不收公式（note-editor 的 `nodes.js`，heading 的内容里没有 `math_inline`），标题里有公式，它就从公式处把标题劈成标题加一段。样例的标题 "literal $5 and $10" 没转义，被读成了公式，才暴露出来。问题树的问题就是标题，带公式的问题会被劈开。改法：写入时标题里的 `$…$` 留作 TeX 文字；读回时标题里的 `$` 不加反斜杠，原样写回；
    - 同一处还看出 `dollarmath` 默认把 "$5 and $10" 读成公式，论文笔记里写训练成本时会碰上。改成 `allow_space=False`：`$` 要紧贴公式，金额就不误认。原想按 pandoc 再禁止数字紧挨 `$`，但盲测样例 "3$\times$3" 这种论文笔记里常见的写法会因此不算公式，所以数字照旧可以紧挨。
74. 第 3、4 步做完（`a5440e0`、`dce5021`、`ceb329c`、`50ebb76` 和文档的提交）。顺序照 advisor 的建议：先写新的（`draft_item`、`read_bib`、`find_in_library --file`、`titles.py` 的副本和防走样测试），用基线核对；再改记录格式，`prepare`、`save`、`attach_file`、`report` 一起换成读结果文件，再核对；最后删搬走的代码。核对结果：`draft_item` 对三篇基线论文生成的条目和基线逐字段一致；用基线的三份 PDF 在假 Zotero 上挂附件，标题和 md5 和基线一致。比 spec 原稿多想了一步、改了的几处（都记进了 spec）：
    - `attach` 改成列表，每个文件一项。结果文件里一篇论文可以有正文和补充材料，原来的单个对象装不下；
    - 导入的全部步骤放进 `import.md`，SKILL.md 只留各项操作共用的部分，不把一条流程切成两处；
    - `ready` 给了 `--dir` 才建目录，整理文库用不着；配置里还留着搬走的两项时，`config.moved` 会列出来，到时提醒用户删；
    - `report` 去掉"残留"和"停下与门禁"两节，前者归 paper-fetch 清理，后者已在结果文件的 `outcome.stop` 里；
    - `lint_items` 和 `zotero.attach` 里只为取全文服务的部分（Crossref 查 DOI、读 PDF 摘录、`verify` 钩子）一并删了，代理网址只按通用写法认。

    advisor 审完又抓出两处，都已改（`0661b77`）：库里条目本来就有 PDF 的论文不交给 paper-fetch，它的结果文件就永远没汇总，`save` 每次都会报 `unsettled`，现在跳过并注明 `library_has_pdf`；paper-fetch 判断不了的文件被悄悄略过，结果说"拿到了"、`save` 却说"还没文件"，现在报 `unchecked` 并给出接收的步骤。之后按 spec §11 跑了 dry-run 那一半的端到端对照，和基线一致；真写进库那一半留到收尾时问用户。
75. 第 5 步搭好 paper-read 的框架（`744c353`）。§11 的"整理"只读对照也做了：拆分前后在"医疗图像"分类上的 `export_bib`、`read_library`、`lint_items` 输出一致。最后按 §11 跑 code-review，两路：编码规范、spec。改了的：四处逻辑问题（接收已归档的文件被挪进 stray/、再认一次会把重认过的正式版改回预印本、后给的引用键被丢掉、库里同一篇的第二个文件没地方定标签），重复的 `host_of`，文档里重复的段落和缺的完成标准，`export_bib -o`、`note put` 的 `action`、几处遮蔽和复用的变量名、过长的文档行，拷来的代码注明出处。有意不改的、实现时定的，都记在 spec §11 末尾。
76. 我问 §11 真写进库那一半做不做，给了 A 现在做、B 等下次真导入时顺便、C 不做，推荐 B。用户：「A」。照做：三个条目真建进 `tmp`、挂上 PDF，读回和基线逐项一致，然后移进回收站。回收站里这三条（Mask R-CNN、Squeeze-and-Excitation Networks、Array programming with NumPy）等用户清空。
77. 用户问：「Paper to zotero 里面有提到需要哪些 skills 吗？就是依赖关系」。查下来是有，但散在 import.md、install.md、SKILL.md 好几处，没有一张集中的表，而且漏了整理文库对 paper-fetch 的依赖（按版本改附件名、查 DOI），README 也没写依赖。我提议每个 SKILL.md 开头放一张兄弟 skill 表，别处指过去，README 注明依赖。用户：「可以，改吧」。已改，spec §8 记了。
78. 接着补了两样拆分收尾的检验。一是两个 skill 之间结果文件格式的契约测试（`f99ae48`）：paper-fetch 用自己的脚本生成三份典型结果存成样例，p2z 读样例建条目、挂附件、汇报；改一个字段名两边都会失败。做样例时发现 paper-fetch 把补充材料当成第二个文件挪进 stray/，已改。二是真上网的导入，用户：「你直接真实测试吧」。按 `import.md` 全程导入 AlphaFold 和 UNet++，两篇都在开放获取那一步拿到，标签、条目、附件读回都对，之后移进回收站。没测到要学校登录的那条路。

## 调研（2026-10-29，看的是代码）

- **记录文件里每一块只由一个脚本写**：`item`、`published_candidates` 由 `doi_to_item` 写；`links`、`fetch.jsonl`、`label` 由取全文那边写；`found`、`checks`、`saved`、`attach` 由 Zotero 那边写。拆分的缝在数据里本来就有。
- **挂附件背着取全文那边的知识**：`attach_file` 挂附件前，用 `verify.check` 再核对一遍 PDF，用 `web.unproxy` 去掉代理前缀；`lint_items` 会查 Crossref，读 PDF 前两页。
- **配置**：一个文件里放着三样东西，归三个主人。`zotero` 归 p2z；`openalex_key` 归认论文和取全文；`institution` 归取全文。
- **issue 历史**：p2z 前后 13 张 issue，6 张在取全文这边，3 张在 Zotero 这边，4 张是整个 skill 的。取全文变得最快。
- **`doi_to_item`**：971 行，同时用 `web` 和 `zotero`。把元数据写成 Zotero 条目的那部分大约三四百行（`build_item`、`build_creators`、`item_from_page` 等），不是 `check_item` 已经在做的事。`check_item` 只是预览 Zotero 会怎么处理一份写好的条目。
- **SKILL.md**：3.3 万字符里，约 2 万是认论文、取全文和上网规则（步骤 1 到 3、Reaching a page、Gate、Agents you send、Instruments）。

## 已定

1. **拆成三个 skill，加上已有的 paddleocr**（第 4、5、12 条）：
   - **`paper-fetch`**：从一篇论文到手上有 PDF。它认出是哪篇论文，查元数据和有哪些版本，找全文、下载（开放获取、出版商、学校登录、用户的浏览器、验证页），核对 PDF 是不是这篇、是哪个版本，给出版本标签。上网的一切规则都归它。它不碰 Zotero。
   - **`paper-to-zotero`**：Zotero 里的一切。查库、建条目、挂附件、分类标签、改字段、合并、删除、整理、导出 bib；存取笔记；存取结构化包。导入时由它编排 paper-fetch 和 paddleocr。它不上网。
   - **`paper-read`**：从 PDF 到论文笔记。它通过 p2z 取 PDF 和结构化包，缺包时调 paddleocr；派用 opus 的 subagent 按问题树读；定笔记的格式（问题清单、问题树、"用在哪里"、"待重看"、主题笔记）；写好的笔记交给 p2z 存。
2. **认论文不单独成 skill，并进 `paper-fetch`**（第 5 条）：按删除测试，它离开取全文就没有自己独立的一摊事，核对 PDF 也离不开它。
3. **名字**（第 7、8 条）：`paper-fetch`、`paper-read`，`paper-to-zotero` 不改。格式是"对象 + 动词原形"。
4. **边界**（第 9 条）：
   - 核对 PDF、判断版本、附件标题的规则、去代理前缀，归 paper-fetch。p2z 直接用它给的标签当附件标题。用户自己拖进来的 PDF，p2z 交给 paper-fetch 核对。
   - 预印本和正式版选哪个作为条目，归 p2z。
   - 笔记：存取归 p2z，内容和格式归 paper-read。
   - 结构化包：存取归 p2z，解析归 paddleocr，谁发现缺包谁调。
   - 按主题找论文，三个都不管，交给 papers-cool-search 或 Google Scholar。
   - paper-read 要拿补充材料时交给 paper-fetch，看代码仓库用 `gh`。
   - 库里没有的 PDF 也要先导入，因为笔记的家在 Zotero。
5. **交接靠交付物，不共写一个文件**（第 10 条之改动 1）：paper-fetch 交出它自己的结果文件，p2z 只读不改，另写自己的记录。
6. **每个 skill 的 SKILL.md 开头先放操作目录，分支放进参考文件**（第 10 条之改动 2；第 11 条把它扩到 paper-fetch）：p2z 的导入流程放进 `references/import.md`；paper-fetch 的只认论文、批量多轮、验证页也这样放。
7. **防止 skill 之间调用失灵**（第 10 条之改动 3，第 11 条补了查找规则）：
   - 第 0 步检查要用的兄弟 skill 在不在，在自己目录旁边找，找不到就停下，说出要加载的名字；
   - 交接只靠文件，拿不到就停下；
   - 调用处用对方的名字。
8. **小的共用代码各带一份，注明出处，不做共享库**（第 10 条之改动 4）：先例是 mattpocock 的 `pr`，它的 CREDITS.md 写着「a hard dependency would break standalone installs」。
9. **交接清单**（第 11 条）：paper-fetch 的结果文件里要有这些：
   - 论文的各种编号；
   - 元数据（CSL 格式）；
   - 论文还用过的其他标题；
   - 找到了哪些版本，预印本和正式版成对给出；
   - 每个文件，连同它的版本、来源、细节和定下的标签；
   - 证据；
   - 去掉代理前缀的网址；
   - 提醒。
   选哪个版本作为条目，留给 p2z。
10. **要接受的代价**（第 10 条）：
    - `paper-read` 还管"记录项目用了这篇"，这一点靠描述写清；
    - 常驻上下文的描述从一段变成三段；
    - 库里没有的 PDF 要先导入。
11. **所有中间文件都放在 agent 的临时目录里，不放进项目**（第 14、15 条）：
    - **放在哪**：当前会话有 scratchpad 就用 scratchpad，没有就用系统临时目录 `${TMPDIR:-/tmp}`。
    - **放什么**：一次导入的文件放在 `<scratchpad>/paper-to-zotero/` 下，包括 paper-fetch 的结果文件和 PDF、p2z 自己的记录。paper-read 取出的结构化包放在 `<scratchpad>/<引用键>.<标题>/`，笔记文件放在它旁边，即 `<scratchpad>/<引用键>.<标题>.note.md`（论文笔记那张 issue 的已定 29）。
    - **用完清掉**：任务结束就清。例外是下到了却没能进 Zotero 的 PDF，先报告给用户，不直接删。
    - **留下来的东西**只在 Zotero 里：条目、PDF、结构化包、笔记。项目里只留项目自己的决定。
    - **写 spec 和 skill 时**一律说"临时目录"（英文 scratch directory），并给出路径，不单说"工作目录"（work directory）。别的 agent 读到"工作目录"，很可能当成项目的目录。
12. **CSL 转 Zotero 条目，用 Zotero schema 里的对照表，在 p2z 里转**（第 17 条，方案 B）。p2z 运行时读 `csl.types`、`csl.fields`、`csl.names`，按表转换，不写死对照表；然后照旧先 `check_item` 预览、再 `create_item` 经本地 API 建条目。不走 connector 导入，因为它会动用户的 Zotero 窗口，导入后还要补设分类、标签和引用键。
13. **每个 skill 有自己的配置文件**（第 18 条，方案 A）：
    - p2z 留着 `~/.config/paper-to-zotero/config.json`，里面只剩 Zotero 的写入 key 和 serverID；
    - paper-fetch 新建 `~/.config/paper-fetch/config.json`，放 openalex 的 key 和学校的代理、发现系统；
    - 现有的那两项，改造时搬过去一次；
    - paper-read 不需要配置；
    - 改造完要更新记忆 `paper-access-environment.md` 里关于配置位置的那句。
14. **现在就写拆分的 spec**（第 19 条，方案 1）：paper-read 先只写框架，读法指向论文笔记那张 issue。写之前先查清 Zotero 笔记的格式和 Better Notes。
15. **问题树就是笔记的标题结构**（第 26、28 条，方案 B）：主干问题用 `##`，子问题用 `###`，再往下用 `####`；状态写在标题末尾，回答写在标题下面，不另写列表。这改掉了论文笔记那张 issue 原来的已定 28。
16. **可以装 Zotero Debug Bridge**（第 28 条）：用户同意装，因为它由 Better BibTeX 的作者发布，能省很多事。先等 `zotero-external-interfaces.md` 的调研回来，看有没有更好的选项，再定用哪一个。
17. **复用靠逐项比较：现成的不比我们差才用，我们的更好就留我们的**（第 29 条；第 33 条改定）：Zotero 的功能和插件生态比较完善，是首先要看的地方，但每一块都要和我们自己的脚本、agent 的做法比一比。比的是用户真正在乎的几点：信息全不全、写库前能不能检查、出了错能不能看清、简单不简单、维护起来累不累、有什么风险。比如查元数据：agent 把几个来源拼起来，写库前还能预览，比 translator 好，所以留着我们的。spec 里每个部件都要写明这次比较的结论。
18. **先不装桥接插件**（第 35 条，方案 A）：三个 skill 都只走本地 API。笔记读回 Markdown 也在 Zotero 外面做。选哪个 Markdown 工具，要先调研、比较（`markdown-tools.md`）再定。以后真有功能非在 Zotero 里面跑不可，再按已定 17 比较，决定要不要装。已定 16（"可以装 Debug Bridge"）就此搁置。
19. **写入用 markdown-it-py**（第 47、48 条，用户定）：commonmark 加表格、dollarmath、中文加粗修正，打开 `html=True` 透传原始 HTML。写入器用 Markdown，也就是笔记按 Markdown 写（第 41 条的方案 C），不全用 HTML。读回用什么还没定。
20. **读回用我们自己写的 Python 读回器**（第 48 到 50 条，方案 1）：只把写入器认得的那一小组写法转回 Markdown，其余原样保留成 HTML，只用标准库。参考 Better Notes 的是知识、识别规则和测试样例；它的转换代码是 TS 写在 unified 的语法树上，和我们的 Python 读回器搬不到一起，所以不搬代码。许可证不作考虑（第 52 条）。采用前做盲测（第 50 条）。
21. **读回用子集读回器，加按块兜底**（第 53 到 56 条）：每个顶层块读成 Markdown，判断对不上的块原样保留成 HTML。这是在同一套盲测样例上和 12 个别的读回器重新比较后选的（`reselect-blind.md`）。兜底机制要补两处：相邻的同类列表、非空块读成空 Markdown。skill 和它的测试只用 Python（第 58 条）；用编辑器 schema 代码做的 Node 裁判只是这次设计的量具，留在参考文件夹里。盲测样例留作不调参的检验集。运行时靠什么判断"对不上"，见第 57 条以后。
22. **转换方向用 `-t md|note` 指定**（第 60 到 62 条，方案 B）：和 pandoc 的 `-t` 一样。命令行同时支持管道和参数，约定照 p2z v2 spec 的 §3.3。
23. **转换脚本叫 `note_md.py`，front matter 只在它一处读写**（第 62 到 64 条）：`-t md|note`；`to_md(html, meta)` 和 `to_note(md) -> (html, meta)`；`note.py` 只处理 `meta` 字典。`note.py take/put` 和 `note_md.py` 用同一套输入输出约定。p2z 的输出选项统一成 `-o/--out`，`-t/--to` 只表示格式。

## 待验证（写 spec 之前）

1. **能不能让 Zotero 自己把元数据转成条目**（第 11 条）。2026-10-29 查了源码和用户本机的 schema，没有写库，找到两个方案：
   - **方案 A：connector 导入**。`/connector/import` 收下任意文本，用 Zotero 自己的导入 translator 转成条目，第一个认得它的 translator 生效。CSL JSON 走的是 `ZU.itemFromCSLJSON`。出处是 zotero/zotero 的 `chrome/content/zotero/xpcom/server/server_connector.js`，以及 zotero/translators 的 `CSL JSON.js`。代价：
     - 条目会落进用户 Zotero 窗口里当时选中的那个分类（`getSaveTarget()`），窗口还会跳去选中新条目；
     - 想改分类和标签，要用 `/connector/updateSession`。它会再切换用户窗口里的选中项，只能设一个分类（`setCollections([collection.id])`），还会换掉手动加的标签（`saveSession.js`）。所以导入之后，还得用本地 API 重新设分类和标签，并把条目从误落的分类里移出来；
     - `itemFromCSLJSON` 不处理引用键，要事后另设；
     - 导入是直接写库，`check_item` 那种写库前的预览就没有了；
     - 导入的返回里有没有条目的 key，还要实测。
   - **方案 B：用 Zotero schema 里的 CSL 对照表，在 p2z 里转**。用户本机 Zotero 的 schema（`read_library schema`，版本 44）里有 `csl.types`、`csl.fields.text`、`csl.fields.date`、`csl.names` 四张表，例如：
     - `paper-conference` 对 `conferencePaper`，`article` 对 `preprint`；
     - `citation-key` 对 `citationKey`，`container-title` 对 `publicationTitle`，`issued` 对 `date`。

     p2z 读这几张表，就能把 CSL 转成 Zotero 条目 JSON，然后照旧走 `check_item` 预览，再由 `create_item` 经本地 API 建条目。对照表是 Zotero 自己的，运行时读取，不用写死在代码里；也不碰用户的窗口；引用键直接对上。`doi_to_item` 里那三四百行手写的转换，大部分可以换成按表转换。剩下的特殊情况：疑似勘误的提醒、从网页 meta 补字段，属于认论文，归 paper-fetch，写进它结果文件里的 `warnings` 和 `metadata`；arXiv 分类标签是怎么打标签的问题，归 p2z。
   - 用户选了方案 B（第 17 条，已定 12）。
2. **用真的 Zotero 编辑器核对读回器**（第 53 条）：2026-10-30 做完，结果见第 73 条。做法：用 `note put` 把 79 个样例（去掉了引用库里条目的引文、批注、图片）拼成一条测试笔记"p2z note_md 真编辑器核对（测试，可删）"，用户在 Zotero 里打开、改了几处，再 `note take` 回来，按模型和送进去的比对。测试笔记已移进回收站，送进去和存回来的两版在参考文件夹的 `realeditor/`。

## 待定（之后一件一件来）

1. ~~p2z 的笔记命令要补哪些操作~~：已定 23。
2. ~~论文笔记那张 issue 里写着"p2z 负责论文笔记格式、读论文流程"的几条，改归到 paper-read~~：2026-10-30 改完，见那张 issue 的"分工"一节。
3. 写 spec（2026-10-30 开始），然后改造。
