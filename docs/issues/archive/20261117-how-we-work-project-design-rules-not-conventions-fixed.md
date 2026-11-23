> 已解决（2026-11-23）：项目自己的规则有了位置。`AGENTS.md` 只有标题和通用块；规则进规则文件 `docs/rules.md`（接替 `conventions/other.md`，已有的 `guideline.md`、`design-principles.md` 保留原名）或约定文件。设计在 `docs/specs/20261123-how-we-work-project-rules-spec.md`，决定 D20261123-1 到 -9，通用块 rev 2026-11-23（提交 `379f987`）。留下的：发布和各项目块外的清理，在待办 B3。参考材料（规则文字各版草稿、两轮盲测、审阅发现）在 git 不跟踪的 `archive/20261123/20261117-how-we-work-project-design-rules-not-conventions-reference/`。

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

## skills 仓库的讨论（2026-11-23）

和两张 `20261123-how-we-work-agents-md-*` 并成一件事谈。出处放哪已定（D20261123-1）。

- main agent 把这类文件叫「项目自己的设计文档」，用户纠正：「"设计文档"你这里的设计文档是不是表达得不对？理论上，如果你看一下全部的项目，不应该是设计文档吧？应该是一个规则文档吧？我不是很确定，我说的话也不一定正确，你去评估一下.」「因为项目本身的东西和规则rule这一套还是不太一样的。rule是控制项目的更高一层的。」main agent 看了五个项目里的这类文件（本仓库 `docs/design-principles.md`，network `docs/guideline.md`，hc 的 `agent/policies/` 和 `docs/task/`，ceus、diffusion 挤在 `AGENTS.md` 里的那几节）：都是任何设计和改动要先过的规则；「设计」在 how-we-work 里已有所指（`docs/specs/`）。改叫「项目的规则文档」。
- 用户接着要求分清它和 `AGENTS.md`、`conventions/`：「另外有一点，我希望你去分清楚项目的规则文档和其他那几个 agents.md，包括 conventions 这些。要区分一下，因为我感觉很容易搞混掉，你就会放错位置」。分法在谈，没拍板。

- 分法、默认名、判断规则写在哪、原话清到哪一层，已定：D20261123-2、-3、-4。
- main agent 准备写各文件开头时，拿 ceus 现有的 `docs/conventions/experiments.md` 检验 D20261123-2 的最后一问，发现按字面问（「这句话」换到别的项目还说不说得通）会放错：那份文件里的「固定的检查面板」「各训练入口的批准关卡」都只有 ceus 才有，按字面要搬进规则文档，可它们讲的是实验怎么做，做实验时要和实验参考一起读。提议把这一问改成问「这条规则讲的那类事」别的项目有没有（实验、报告、写代码、放文件：有，进 `conventions/`；配置怎么设计、交付的图必须怎样、skill 怎么设计：只有这个项目有，进规则文档）。没拍板。

- 用户对「那类事」的提议没有点头，要求重新梳理（2026-11-23）：「你刚才说的那一点，我怎么感觉又陷入到了 rules 和 convenience 之间的争抢当中了，就不确定怎么判断了呢？但是我感觉你刚才说的「每个候选目标都要在固定的 9 个病例上看过再报指标」「各训练入口要哪个批准文件」是关于实验部分的，那应该是放在 experiments 下面的，这就让我质疑了 rules 到底应该放什么.你再去重申一下，重新看一下我们之前讨论的，我记得你好像分清楚过.因为你现在自己必须要梳理清楚，你这样才能规范别人、判断得清楚。你自己搞不灵清，后面就会一团糟糕的.又回到了刚才那个问题，你全面的梳理一下。现在 conventions 下的文件、others 以及rules之间到底是什么关系？你可以多拿几个样本去测试一下，因为我们现在有很多项目，前期我们在设计规范规则怎么工作的时候，一定要做充分、做好，不然的话后面是一团糟糕的。」
- main agent 把 ceus、diffusion、hc 三个项目约定文件的全部条目（约 80 条）和五个项目里没有参考管的规则（network 的 guideline、本仓库的设计原则、hc 的 policies、ceus 和 diffusion 挤在 `AGENTS.md` 里的方法约束）过了一遍。看到的：约定文件的条目几乎都只属于那个项目，但都明确挂在某一份参考上，没有放哪的疑问；没有参考管的规则几乎全是项目自己的事，够得上「通用的一类活、只是没参考」的只有一两条代码写法。提议：`other.md` 和规则文档是同一格，并成 `docs/rules.md`；分界改成「这件事 how-we-work 有没有参考管」。没拍板。

- `other.md` 改名成 `docs/rules.md` 已定（D20261123-5），用户加了一条：它是高优先级的文件，判断也要跟着看。main agent 提了「先问它约束的是不是这个项目做的东西本身，是就进 `rules.md`；两边都沾的归 `rules.md`」。用户（2026-11-23）：「但我现在有一个担心点，就是你判断的第三点：问了以后，是不是会全部进 rules 而不进 conventions？你整体要考虑得全面一点」。main agent 拿三个项目的 80 条约定条目试了这一问：layout 28 条、records 9 条、reports 10 条都能被说成「约束项目做出来的东西」（目录、记录、报告页），共 47 条有被吸进 `rules.md` 的风险，担心成立。改提：先对照各参考开头写明的「项目文件收什么」这份清单，对上的进 `conventions/`（80 条里 75 条留在原处），其余的规则全部进 `rules.md`；优先级不靠先问谁来体现，靠 `AGENTS.md` 里的指针、冲突时以它为准、改它要用户点头。没拍板。

- 用户要求把两者怎么配合想清楚（2026-11-23）：「你需要协调好 rules 和 conventions 如何工作。因为之前我们只有 conventions，是按照流程一个个文件读下来，最后一个到 others；现在 others 变成了 rules，整套流程或者说它们两个之间的协作方式可能会发生变化」。main agent 提的配合方式：两者由不同的时刻触发，不再是一串读到最后；`docs/rules.md` 在设计或改动项目做的东西之前整份读，触发写进通用块的 *When to read what*，文件不叫默认名的项目在 `AGENTS.md` 块外写一行；约定文件照旧，做那类活时跟着参考读；两个时刻都到了先读 `rules.md`；写规则时读 skill 的 `rules` 参考（接替 `other` 参考，放四步判断和例子）。没拍板。

- 用户要求从顶层整体设计并写 spec（2026-11-23）：「你全面地从顶层按照我们的设计原则，还有 writing for agent 这些东西全部设计一遍，然后写好对应的 spec」。之前还问了降级、升级、优先级和冲突：「还有包括 Agents.md 通用快是怎么降的，也就是各个流程或者协同工作的方式.我现在担心的点是，因为你说了一个优先级嘛，有些东西全记到 rules 里面去了，实际在用的时候根本就不会放到约定文件里面或者怎么样子」。
- 做了什么：写出规则文字的草稿；两轮盲测（各两个互不相通的 subagent，只凭文字分拣真实条目，44 条和 37 条）；一个 subagent 审设计，17 条发现全部核对后采纳。spec：`docs/specs/20261123-how-we-work-project-rules-spec.md`，待用户定的在它的第九节。材料在本 issue 的参考文件夹。

- 2026-11-23，用户说可以开始后，main agent 照 spec 第十节改了脚本、参考和测试（在工作区，没提交），把通用块 *How a rule grows* 的措辞给用户看了两版。用户都不满意：「你觉得这样合适吗？根据 Writing for an agent 来看一下还有我们的设计原则」；「我还是觉得不满意，特别是你为什么每次都要提到打印密钥？就感觉很奇怪。我建议你从全局再设计一遍，根据设计原则和 Writing for Agents。我感觉你这次没有抓住重点。你需要停下来思考，不要着急一味的去解决，去修修补补。有没有更好更聪明的解法，如果方案（包括你提出的）像是在绕路，先指出更根本的思路。」
- main agent 停下来重想后提的更根本的思路（没拍板）：一直在回答「哪些规则够格进 `AGENTS.md` 块外」，每个判据都抽象，只举得出密钥一个例子。更根本的做法是去掉这一步：`AGENTS.md` 块外不放规则条目，它是让 agent 看清这个项目的地方，只有固定的四样（项目是什么；这里的危险；和通用块不同的地方；什么时候读什么）。规则只有两个家：规则文件和约定文件。五个项目现有的块外内容都能落进这四样或搬去那两个家。

- 用户对「块外不放规则，只放四样」的回应（2026-11-23），是倾向，不是决定：「A 另外我有一点担心，块外这个是不是根本就没有必要？A和我刚才的那个担心点，都是我的一个倾向，不是最终决定，和我讨论」。

- **状态**：已解决