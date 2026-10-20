# paper-to-zotero 顶层重构：审查材料

> 2026-10-20，针对 [20261020-paper-to-zotero-top-down-restructure-fixed.md](../20261020-paper-to-zotero-top-down-restructure-fixed.md)。设计见 [20261020-paper-to-zotero-restructure-spec.md](../../../specs/20261020-paper-to-zotero-restructure-spec.md)。
>
> 用户的要求：「你先读一下20261020-paper-to-zotero-top-down-restructure.md 这张issue，然后调用/simplify ，review一遍，然后写优化重构spec」。
>
> 按 `/simplify` 的四个角度各派一个只读子代理审查整个 skill（21 个脚本、21 个测试文件、SKILL.md、references），不改代码。四份报告原样保存，英文，行号对应 `c528750`：
> - `reuse.md`：复用，同一机制的各个副本、写法上的分歧、共享模块的划分、测试里的假 Zotero；
> - `simplification.md`：简化，单条模式、没人用的开关、输出约定、记录字段归谁写；
> - `efficiency.md`：效率，重复的请求和扫描、限速、测试耗时（测试耗时是实测，其余是估计）；
> - `altitude.md`：层次，特例和补丁该落在哪一层、取全文的路线、结构化包能复用什么。
>
> 报告是子代理的结论，不等于事实。spec 里标"已核实"的几条是主会话对着代码确认过的；其余在实现时逐条核实。
