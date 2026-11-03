# paddleocr：IEEE 下载水印让每页都报"缺数字"

- 来源 · 日期：2026-11-02，审 paper-read spec 时，技术审阅的 agent 在 T-CACE 的结构化包里发现（参考资料 `20261102-paper-to-zotero-note-front-matter-fields-reference/spec-review-technical.md` 第 13 条）。
- 现场：T-CACE（`xiaoTCACETimeConditionedAutoregressive2026`，Published-IEEE）的包有 14 处未整理的问题，其中 6 处是第 1、2、3、10、11、12 页的 `missing_numbers`，内容都是 `23,202`。来源是每页文字层里的 IEEE 下载水印"Downloaded on September 23,2026 at 16:44:56 UTC from IEEE Xplore"。页眉页脚只记在 record 里（paddleocr SKILL.md:72），水印却被当成正文缺的数字。
- 为什么要紧：
  - 从学校 IEEE Xplore 下载的 PDF 都带这种水印，每篇都会多出几处假问题。整理的 subagent 要逐条去看，白花工夫；
  - 真正要紧的问题被淹没。T-CACE 那 3 处 `unchecked_table` 恰好是全文仅有的三张表，主要数字都在里面。
- 方向（没拍板）：把出版商的下载水印也当页眉页脚处理，不算正文缺的数字。具体怎么认出水印，属于 paddleocr 的检查；拿不准的照旧报给整理的 subagent。
- 状态：open。按 vllm-serve、paddleocr 暂缓的约定（用户 2026-11-02），等它挡路或下次改 paddleocr 时一起做。
