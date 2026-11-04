# paddleocr：IEEE 下载水印让每页都报"缺数字"

> 已修（2026-11-04）。原因和下面"现场""方向"写的不一样：
> - **真正的原因**：模型每一页都把这行水印认成了页脚，检查也已经把页脚算进去了。误报来自切数字：
>   - 文字层写的是 `September 23,2026`（逗号后没空格），千分位数字的规则把它切成 `23,202` 和 `6`；
>   - 模型有几页写成 `23, 2026`（带空格），切出来是 `23` 和 `2026`，对不上；
>   - 检查拿前后三页一起比对。T-CACE 报出来的第 1–3、10–12 页，正好是前后三页的页脚都带空格的那几页。
> - **改了**（`scripts/checks.py`）：千分位数字的最后一组必须正好三位，后面不能再跟数字，`23,2026` 于是切成 `23` 和 `2026`；检查版本从 5 升到 6。测试 `tests/test_checks.py` 一条，在旧代码上失败。
> - **验证**：T-CACE 加上随机挑的 8 篇库里的 IEEE 正式版（库里共 61 篇），改前改后各跑一遍检查。消失的只有水印日期这一种，共 58 处，其余发现一处没变。8 篇里有 6 篇中招，有一篇 9 处发现全是它。
> - **没采纳**下面的方向：
>   - "把水印当页眉页脚处理"：它已经是页脚了；
>   - "认出出版商的水印"：那是按出版商写的匹配规则，违反设计原则 §1 *Knowledge stays open*。
> - **库里已有的包没有全部重算**：重算要把 832 个包重新上传一遍，只为这些误报，不值得。读论文的 subagent 第一次 `doc.py commit` 时，检查会按新规则重算，这些误报自然消失；在那之前，`prepare_note` 报的未整理问题数会偏多。下次 paddleocr 有要紧的改动时，再按 p2z organize.md *Structured packages* 一起重算。
> - 开工前用户把暂缓的条件确认为已满足：「1 2 一起做了，现在就做」。

- 来源 · 日期：2026-11-02，审 paper-read spec 时，技术审阅的 agent 在 T-CACE 的结构化包里发现（技术审阅报告第 13 条；报告原在 p2z issue [20261102-paper-to-zotero-note-front-matter-fields-fixed.md](20261102-paper-to-zotero-note-front-matter-fields-fixed.md) 的参考资料里，关闭时已删，要点都抄在下面）。
- 现场：T-CACE（`xiaoTCACETimeConditionedAutoregressive2026`，Published-IEEE）的包有 14 处未整理的问题，其中 6 处是第 1、2、3、10、11、12 页的 `missing_numbers`，内容都是 `23,202`。来源是每页文字层里的 IEEE 下载水印"Downloaded on September 23,2026 at 16:44:56 UTC from IEEE Xplore"。页眉页脚只记在 record 里（paddleocr SKILL.md:72），水印却被当成正文缺的数字。
- 为什么要紧：
  - 从学校 IEEE Xplore 下载的 PDF 都带这种水印，每篇都会多出几处假问题。整理的 subagent 要逐条去看，白花工夫；
  - 真正要紧的问题被淹没。T-CACE 那 3 处 `unchecked_table` 恰好是全文仅有的三张表，主要数字都在里面。
- 方向（没拍板）：把出版商的下载水印也当页眉页脚处理，不算正文缺的数字。具体怎么认出水印，属于 paddleocr 的检查；拿不准的照旧报给整理的 subagent。
- 状态：已修，见开头。
