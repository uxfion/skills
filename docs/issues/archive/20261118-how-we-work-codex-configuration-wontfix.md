> 已关闭（2026-11-23）：调研的结论是保留现有设计，不改。它复现的一个毛病（`sync -n` 遇到旧块时提示「块已经变了，去重读」，其实什么都没写）并进了 `docs/issues/archive/20261117-how-we-work-sync-register-silent-and-undocumented-fixed.md`。逐文件复核里其余的观察没有开 issue，留在参考材料里。参考材料（官方文档原文、逐文件复核、讨论稿）在 git 不跟踪的 `archive/20261123/20261118-how-we-work-codex-configuration-reference/`。

# 对照 OpenAI 官方建议，HWW 需要大改吗？

**结论：建议保留 HWW 的整体设计。** 这次审阅了 HWW 的入口、公共规则、全部 12 份参考、同步脚本和测试。发现了几处具体问题，但现有证据不足以说明整套规则让 Codex 普遍变慢、反复追问，或做不好研究工作。以下是 2026-11-18 的调研判断，供讨论。

## 为什么建议保留

官方建议把长期有效的工作约定写下来，让用户不用每次重说；实验、写作等专门任务在用到时再读相应材料。HWW 已经按这个思路组织。你还明确要求，一旦某份参考确实适用，就要读全。这来自三个项目的实际教训：agent 只搜关键词，漏掉了影响结果的要求。精简要保住这个效果。[官方原文](../../../archive/20261123/20261118-how-we-work-codex-configuration-reference/rethinking-skills-and-prompts-for-gpt-6-astra.md) · [当时的决定](../decisions/202611.md#d20261114-4--参考要不要读全改报告时要不要每轮重读)

## 这次用起来，究竟哪里出了问题？

你问的是「我们 HWW 这个 skills，根据我刚才发你的那些官方文档，有没有大的问题？还是说没有大的问题，只是一些细节的东西？」我先漏读了材料，后来又让你判断要不要拆论文写作参考，却一直没给出整体判断。HWW 已经写了先讲全局、给出自己的判断、有决定要做时一次问一个。这次我没有照做。把同样的话再写进全局 AGENTS.md，缺少能改善结果的依据。

有一个值得保留的观察：改论文里的一句话，也可能要读到组会网页怎么排版。这个例子说明两份参考的适用范围有重叠。它到底有没有造成明显等待、漏项或返工，这次没有测出来。等有真实任务可比较时，再看改一处规则是否确实有用。目前没有充分理由拆文件。[逐文件复核及其他具体问题](../../../archive/20261123/20261118-how-we-work-codex-configuration-reference/hww-review.md)

两件已说清的事也从通用改动建议中撤下。旧配置放进 archive 是你对那批文件的一次要求。此次只读调研限制的是仓库里的改动；正式运行 HWW 同步返回了 `current`，仓库文件没有被它改写。

## 对另外两个常用配置的判断

- **agent-instructions**：建议保留现有的共享记忆约定和 Python 执行示例。它们解决了不同客户端共用项目记忆、执行临时代码时容易绕开 uv 这两个实际问题。GPT-6.2 的四段官方提示词可用来检查答复质量，现有证据不足以支持把全文再复制进去。[官方示例](../../../archive/20261123/20261118-how-we-work-codex-configuration-reference/gpt-6.2-astra.md)
- **uv-python**：只看到一处优先值得验证的小问题。用户问“pip 是什么意思”时，技能描述里“提到 pip 就触发”的写法也可能让 Codex 加载整份说明。可以用这句话和“帮我跑这段 Python”作对照，实际发生误触发时再收窄描述。

**本轮建议**是继续使用现有配置。以后若同一种问题反复出现，或一次就造成了明确损失，再拿具体任务来讨论该改哪条。官方也给出了验证办法：在同一仓库快照和同一模型上，拿同一个请求只改一条规则，看交付是否更好、用户是否少返工。[官方验证示例](../../../archive/20261123/20261118-how-we-work-codex-configuration-reference/maintaining-software-with-the-gpt-6-family.md)

[官方文档原文索引](../../../archive/20261123/20261118-how-we-work-codex-configuration-reference/README.md) · [此前讨论过的候选建议](../../../archive/20261123/20261118-how-we-work-codex-configuration-reference/discussion-draft.md)
