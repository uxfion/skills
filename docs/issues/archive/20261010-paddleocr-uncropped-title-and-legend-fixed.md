# paddleocr：图注分标题和说明两段时，`uncropped_figure` 误报

已修（2026-10-10）：`uncropped_figures` 按图号把同一页的两段图注配成一张图，`CHECK` 升到 4，见末节。

2026-10-10。用户问合图效果，听完前两批的结果后说：「可以再找一批，测试一下」。

## 第三批留出复验

从研究项目又挑了 8 篇前两批和调规则都没用过的论文（副本）。用已安装的 skill（aa55044）、vLLM 后端重新解析：

- 期刊和版式：Nature、Nature Medicine、Science、Scientific Reports、npj Digital Medicine、CVPR、CHI（ACM）、TACL。
- 规模：151 页，文字层里有 81 张带图注的图。
- 核对方式：18 张框图拼板逐页看过，27 张合成图的裁剪文件逐张看过。

| 论文 | 期刊 | 完整 / 带图注的图 | 问题 |
| --- | --- | --- | --- |
| bansal 2021 | CHI | 9 / 9 | |
| brodeur 2026 | Science 预印本 | 7 / 7 | 7 条 `uncropped_figure` 误报，见下 |
| gadd 2026 | npj Digital Medicine | 7 / 8 | Fig. 6 拆成两块 |
| gupta 2023 | CVPR | 9 / 9 | |
| hager 2024 | Nature Medicine | 14 / 14 | |
| hollmann 2025 | Nature | 10 / 10 | |
| liu 2024 | TACL | 15 / 16 | Fig. 6 是纯文字示例图，没有裁剪图；告警正确 |
| vela 2022 | Scientific Reports | 8 / 8 | |

合计 79 / 81 完整（97.5%）。没有一处错合，也没有一处把图注或正文裁进图里。非图区域：期刊 logo、CC 许可徽标，共 3 处。

不算不完整、但要记下的小毛病：
- brodeur Fig. 2：“A. …” 小标题离图 32 px，超出扩边的两行范围，留在裁剪外面。
- vela Fig. 3、4、7：图内的分组标签条（如 “Strange attractors and chaos”）留在裁剪外面，或被切掉一半。其中一条被 VL 标成了页眉。
- 有几处坐标轴标签或图例贴着 VL 框的边。

gadd Fig. 6 是整页的信息图，自上而下分三部分：
- 病例面板：文字加 6 个小图标；
- 预训练模型的曲线网格；
- 微调模型的一行三图。

plus-L 只框出了最下面一行。图注兜底时，6 个小图标也找到同一条图注，几块并起来的框盖住了病例面板里的小标题（“Demographics:”“Diagnoses”，VL 标成了 `paragraph_title`），整组不合。根子是 VL 把图里的文字标成了标题，属于 spec 3.7 的局限，合图规则不改。即使只合下面两块，病例面板也进不了裁剪；SKILL.md 第 3 步已写明，任务用到这类图时由 agent 自己裁。

## 问题：标题、说明两段图注

brodeur 的每张图：
- 上方是标题 “Figure 1. Performance of …”；
- 下方是说明 “Figure 1: Barplot showing …”。

两段都被认成图注。`uncropped_figures` 把裁剪图配给下方最近的说明，上方的标题就没有配上裁剪图。结果 7 张图报了 7 条告警，全是误报。这种版式在 Science、Cell 一类期刊里常见。

告警的准确率：
- 这一批：8 条里 1 条属实。
- 三批合计：30 篇 20 条，8 条属实。

## 改法

只改检查，不动合图：配完裁剪图后，剩下的图注如果和同一页上已配上的某条图注编号相同，就是同一张图的另一段，不报。

- 编号连同前缀一起比较。“Extended Data Fig. 1” 和 “Fig. 1” 不算同一张。
- 同一页上，两张不同的图不会同号，所以这条规则漏不掉真缺的图。
- `CHECK` 升到 4，旧解析下次跳过时重新检查，误报随之消失。

实测：
- 三批共 30 篇、391 条图注，新旧两版检查对比：告警从 20 条降到 13 条。去掉的正是 brodeur 那 7 条，其余 29 篇一条没变。
- 剩下的 13 条里 8 条属实：6 张文字示例图、1 张被读成表格的图、liu Fig. 6。另外 5 条是误报：一份附图图注清单、一句以 “Figure 2.” 开头的正文。
- brodeur 和 liu 的旧解析用新版重跑：都标了 `rechecked`，brodeur 告警清零，liu 那条真告警保留。
- 73 个单元测试通过，新增一条覆盖“标题在上、说明在下”和 “Extended Data Fig.” 前缀。
