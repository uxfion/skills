# how-we-work：项目本身的设计准则被通用块归进了 `docs/conventions/`

- **来源 · 日期**：`Hub/network` 项目的会话 · 2026-11-17。
- **涉及的文字**：`common.md` 的 *Documents and memory* → *How a rule grows*。原句是：「A rule for one kind of work, with the facts that work needs, stands in `docs/conventions/<name>.md` … Where the kind has no reference, the file is `docs/conventions/other.md` … The project's other facts (its servers, its datasets) stay in its documents.」

## 背景

`network` 是用户的代理配置项目，有 mihomo 和 Surge 两份配置，共用一套设计。用户让 main agent 把散在 spec、决策、`AGENTS.md` 和记忆里的设计原则集中成一份 Guideline。这些原则包括：两份配置怎么对应、规则源怎么选、规则顺序、DNS 要求。

main agent 读通用块后，把它们当成"某一类工作（代理配置）的规则"，又因为 skill 里没有对应的参考文档，就提议放进 `docs/conventions/other.md`，用一个小标题。用户否定了这个提议。

## 用户原话（2026-11-17）

- 「我建议你是维护一份Guideline，这样好统一行为，如果后面有更新的方式或者更优的方式，也可以快速去统一」
- 「Guideline应该就放在docs下面，不用放到conventions下面的吧？这是属于我们这个项目专属的」
- 「这是我们整个仓库的重中之重啊，你为什么还放到 convention 下面？这是工作流或者 HWW 相关的东西」

## 现场

- 最后放在 `docs/guideline.md`。项目 `AGENTS.md` 在块外加了一条指针，并写明这是有意偏离块的默认放法，引了用户原话，免得以后的会话照着块把它搬回去。
- 通用块里能装下"项目的设计核心"的只有 `docs/conventions/<name>.md` 这一处。另一句「The project's other facts … stay in its documents」说的是事实（服务器、数据集），不是设计规则。所以 agent 按块的字面意思，会把项目的设计规则当成"工作约定"。

## 为什么要紧

- `docs/conventions/` 在用户的理解里装的是工作流的约定（和 how-we-work 相关的那些），项目的设计准则是另一类东西。混在一起，用户找不到核心文件；`other.md` 由 sync 管着格式，也不适合放项目的核心文件。
- 别的项目也会有自己的设计核心：实验方案的原则、论文的立论。agent 照块的字面放，会再犯同样的错。

## 可能的改法（由用户定）

在 *How a rule grows* 里分开两类东西：

- 怎么干活的约定，放 `docs/conventions/`；
- 项目本身的设计规则和准则，放项目自己的文档（比如 `docs/<名>.md`），在 `AGENTS.md` 的块外用一条指针指过去。
