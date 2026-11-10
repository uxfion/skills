# paper-read：读论文的 subagent 换着参数反复请求同一个网址

- 来源：2026-11-09 试读 MIRAGE（`borghesiMIRAGEMultiscaleLesionInformed2026`），读论文的 subagent 自己在报告里写的。用户没有提。
- 状态：open。

## 经过

- **做了什么。** 为了回答"挑战赛隐藏测试集上的成绩"，它请求 grand-challenge 排行榜的 JSON 接口 6 次，每次隔 5–10 秒，换着分页、排序、搜索参数。服务器不理这些参数，每次都返回同一页。之后它改用浏览器读了一次。
- **同一时间段。** Semantic Scholar 的接口返回 429，arXiv 的接口回"Rate exceeded"。当时另一个读论文的 subagent（han 2024）也在查这两个服务的引用。
- **为什么要紧。** 网站把本机发出的所有请求算作同一个人，限流和封禁也落在用户的 IP 和学校账号上。reading.md 的 *Rules* 只要求"一次一个请求、同一站点隔几秒"，碰到 bot 检查、403、429 就停；接口没报错、只是不理参数时，没有说该停。
- **已经处理的一半。** 两个 subagent 同时查引用服务：随第一期改动（spec `20261109-paper-read-deep-reading-spec.md`），标了重要、要查后续引用的论文一次只派一个。

## 要定的

- reading.md 的 *Rules* 要不要加一句：请求失败，或者返回的不是要的东西，就不要换着参数再试。改的是规则，按规则改动的流程走。
