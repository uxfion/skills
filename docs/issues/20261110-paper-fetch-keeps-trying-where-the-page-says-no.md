# paper-fetch：页面已经说明拿不到，还在继续试

- 来源：用户 · 2026-11-10，看着浏览器跑试跑时：
  - 「我发现你一直在重复」
  - 「而且既然这边因为没有 access 的话，你应该就走下一个流程啊」
  - 「没有，你重试那么多遍干什么？没有的话，就下一个流程了」
  - 主 agent 让 subagent"不许重开页面"之后：「也不是说不许重开吧，你重试几次，你明确知道是没有的话，你就不用再重试啊」
- 状态：open。规则文字（`paper-fetch/references/web-agent.md`）的改法等用户看过预览再定。

## 经过（同一次试跑里出现三次）

1. **脚本。** Eur Radiol 那篇经代理打开的页面写着 "Access this article / Buy Now"（学校没订阅）。`fetch` 认不出这句话，把页面上的 PDF 链接逐个试，每次隔 15 秒。
2. **JAMA 那篇的 paper agent。** PMC 页面上没有正文 PDF，它猜了一个 `/pdf/` 地址去请求（404），又去试 Europe PMC 的一个接口（被 Cloudflare 拦下）。web-agent.md 写着"只请求页面显示是这篇论文的链接"，它知道，还是猜了。
3. **Eur Radiol 那篇的 paper agent。** 在 Springer 的机构登录列表里把学校名字换着写法搜了六次；又对一个猜出来的 `/content/pdf/<doi>.pdf` 地址跑了 `fetch --start`，而页面已经显示没权限。

## 主 agent 找的原因

- 现有规则管的是"被拦了就停"（bot 检查、403、429），没有管"没报错、但页面已经说了没有"。上午给 paper-read 的 reading.md 加的那句是同一类缺口，只是加在了读论文的 subagent 那边。
- 配置里只有代理和发现系统的地址，没有学校在出版商登录列表里的名字，subagent 只能猜。这次核实了 Springer 的列表里没有这所学校，已写进 publishers.md。
- 用户要的界线：偶尔失败（超时、没加载出来）可以重试几次；已经明确知道没有的，不再试，走下一条路。
