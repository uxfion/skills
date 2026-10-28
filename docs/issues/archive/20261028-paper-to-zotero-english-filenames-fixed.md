# paper-to-zotero：PDF 和结构化包的文件名里出现中文"等""和"

> 已解决（2026-10-28）：
> - **PDF**：文件名交给 Zotero 管。用户换成了英文模板，Zotero 同条目里后加、它没改到的 6 份，用 `Zotero.rename_file` 在原地改名。p2z 自己起的名字和模板一致：英文，标题截到 100 个字符。
> - **结构化包**：改叫 `<引用键>.<标题>`（`zotero.package_stem`），不再照抄 PDF 的文件名。全库 832 个包都重新打包，读回检查都对。
> - **"包跟着 PDF 走"**：回收站、合并条目、改标题三种情况都已处理。
> - **代码**：`99915ec`、`06672ca`。

- 来源：用户 · 2026-10-28，结构化包补全全库时，用户看到 CycleGAN 的包叫 `Zhu 等 - 2017 - ….zip`
- 用户原话：「因为我非常不喜欢 等 和 这种，本身其他论文名，作者都是英文的，突然冒出个中文。zotero中能设置这个吗？我希望统一成英文的。全是中文突然出现个中文非常变扭。」
- 状态：已解决（2026-10-28）

## 现场

- **数量**：库里 832 份 PDF 的文件名中，126 份写"等"（`Zhu 等 - 2017 - Unpaired Image-to-Image ….pdf`），7 份写"和"（`Goyal和Bengio - 2022 - ….pdf`），其余写 `et al.`/`and`。
- **"等""和"的来源**：PDF 是 Zotero 自己存的（2024-10 到 2026-09）。Zotero 的默认文件名模板 `{{ firstCreator suffix=" - " }}{{ year suffix=" - " }}{{ title truncate="100" }}` 里，`firstCreator` 随界面语言变；zh-CN 下 `general.etAl=等`、`general.and=和`（Zotero 源码 `chrome/locale/zh-CN/zotero/zotero.properties`）。用户的 prefs.js 没有改过模板。
- **原来的模板，要恢复时用**：用户 2026-10-28 从 Zotero 的文件名模板框里抄出来的，就是默认模板，原样如下。要恢复，把它粘回"配置文件重命名…"里的"文件名模板"框，再让 Zotero 重命名现有文件。用户：「原来是这样的，你保存一下，需要时可以恢复」。

  ```
  {{ firstCreator suffix=" - " }}{{ year suffix=" - " }}{{ title truncate="100" }}
  ```
- **英文的来源**：PDF 是 p2z 用本地 API 上传的（2026-09 起）。Zotero 不给 API 上传的文件改名，文件名由 p2z 自己起（`zotero.default_filename`，英文）。
- **结构化包**：zip 照抄它那份 PDF 的文件名，所以也跟着带中文。

## 用户改完模板后的检查（2026-10-28）

用户换了新模板，并让 Zotero 重命名了现有文件。读回全库：
- **PDF**：Zotero 改了 248 份。其中 127 份原来带"等""和"；另外 121 份是 p2z 存的英文名，只是标题截得比 Zotero 长（p2z 的 `FILENAME_TITLE_MAX = 120`，Zotero 模板是 `truncate="100"`），Zotero 按 100 个字符重截。
- **还剩 6 份 PDF 带"等"**，都在有两份 PDF 的条目里，这次每个条目只改了其中一份（文档："Additional attachments on an item that already has one are not renamed"）。是：`liEnhancingAdaptingClinic2024` 的 Published-IEEE、`shamsolmoaliImageSynthesisAdversarial2021` 的 Published-Elsevier、`liReviewDeepLearning2021` 的 Published-Elsevier-in_press、`liuPerceptionConsistencyUltrasound2023` 的 Published-EBSCO、`zhuUnpairedImagetoImageTranslation2017` 的 Published-CVF、`sahariaPaletteImagetoImageDiffusion2022` 的 Preprint-arXiv-v2。用户在 Zotero 里右键这几个附件，选"按上级元数据重命名文件"就能改。这几份由用户改，不由 p2z 改：p2z 改文件名只能重新上传，会换掉附件，附件上的批注也会跟着丢。
- **结构化包**：125 个 zip 还带"等"（Zotero 不改 zip），按下面第 2 条由 p2z 改。
- **补全全库**：用户改名时补全还在跑。之前 `take` 做的软链接指向旧文件名，所以有几份解析失败（`parse_failed`）；补全跑完后重跑一遍，只会处理还没有包的。

**剩下 6 份 PDF 由我改了**（2026-10-28）。用户：「你不可以改吗？不需要使用标准件改，你直接写程序或者操作api不行吗」。照 Zotero 自己的"按上级元数据重命名文件"来做。它在源码里（`item.js` 的 `renameAttachmentFile` → `relinkAttachmentFile`）就两步：改存储里的文件名，再把附件的 `attachmentPath` 设成 `storage:<新名>`，不上传，所以附件、key 和批注都保留。一次性脚本照做：先在存储里改文件名，再用本地 API PATCH 附件的 `filename`（`fromJSON` → `attachmentFilename` 的 setter，等于设 `attachmentPath`），PATCH 失败就把文件名改回去。新名字取同条目里 Zotero 已改好的那一份，两份的条目信息相同，模板给出的名字也相同。6 份读回都对：`filename` 是新名字，文件在新路径，md5 没变。然后把文件名和 PDF 对不上的 234 个包（125 个带"等"，其余是 PDF 的标题被 Zotero 截到 100 个字符）取出来，再 put 回去：内容不变，按新名字重新上传，旧的进回收站。结果：重传 234 个，另有 5 个本来就对、跳过。读回全库：832 份 PDF、832 个包，文件名里都没有中文，也没有缺包的 PDF。还有 2 个包的名字和 PDF 差一个空格：PDF 的文件名里有两个连续空格，`attach` 的 `clean_filename` 把它们并成了一个。

**用户问到整体设计**（2026-10-28）：「我们的 skills 应该没有修修补补吧？而且是比较优雅地融合进原有的系统，是以一个整体的思路设计的吧？」我的回答：整体是一个概念、一个脚本，只在原流程里加了两步；但有两处缝。
- **zip 的文件名照抄 PDF 的文件名**：PDF 的文件名归 Zotero 管，zip 迟早会和它对不上。今天加的重传分支和 `replacing` 参数就是在下游补洞。
- **"包跟着 PDF 走"少了改标题这一种**。

用户接着问：「那既然这样的话，要不要带上引用的键值啊？你从全局帮我考虑一下，和我讨论」。提议（待用户定）：
- Zotero 里的标题仍和 PDF 相同；
- 文件名、zip 里的文件夹、取出来的临时文件夹统一用 `<引用键>.<标题>`，离开 Zotero 也认得出是哪篇；
- 现有 832 个 zip 在原地改名；
- 删掉重传分支和 `replacing`；
- 改标题也让包跟着走，三种操作共用一个函数。

**定下来的**（2026-10-28）：分隔符用点，用户问「为什么要用 . 这是常用行为吗？」，比过点、下划线、空格-短横三种写法后说「用.」。zip 里的文件夹也改名，用户：「zip 里的文件夹也改，也就是重新打一下包」。实现如下：
- **名字只在一处定义**：`zotero.package_stem`，规则是 `<引用键>.<标题>`。zip 的文件名、zip 里的文件夹和 md/json、`take` 解压出的临时文件夹，都用这个名字。Zotero 里的标题仍然等于 PDF 的标题。
- **原地改名**：`Zotero.rename_file`，照 Zotero 自己的改法：先改存储里的文件名，再 PATCH `filename`。`put` 里按新名字重传的分支和 `attach` 的 `replacing` 参数都删了。
- **包跟着 PDF 走**：三处共用 `Zotero.packages` 和 `name_packages`。`trash_item` 先找到 PDF 的包，再和 PDF 一起移进回收站。`merge_items` 搬完后，按留下那个条目的引用键给包改名。`update_item` 改 PDF 标题时，包的标题跟着改；改了标题或引用键，包的文件名也跟着改。
- **`structured names`**：在原地把包的文件名改对，用于在 Zotero 里直接改了引用键的情况。
- **重新打包**：832 个包取出来再放回去，内容按新名字重新打包、重新上传，旧的进回收站。全部成功。读回检查：832 份 PDF 对应 832 个包，一一对应，名字都是 `<引用键>.<标题>.zip`，PDF 和 zip 的文件名里都没有中文。

## 方向

1. **改 Zotero 的文件名模板**，换成不随界面语言变的写法（用户在 Zotero 里操作：设置 → 常规 → 文件重命名 → 配置文件重命名…）。保存后 Zotero 会问"是否要重命名你的文库中的现有文件以匹配新设置？"，选"预览修改…"，确认后点"重命名文件"。模板用文档里的条件语法（Zotero ≥ 7.0.16 支持 `authorsCount > 2`）：

   ```
   {{ if {{ authorsCount > 2 }} }}{{ authors max="1" suffix=" et al. - " }}{{ elseif {{ authorsCount > 0 }} }}{{ authors join=" and " suffix=" - " }}{{ elseif {{ editorsCount > 2 }} }}{{ editors max="1" suffix=" et al. - " }}{{ else }}{{ editors join=" and " suffix=" - " }}{{ endif }}{{ year suffix=" - " }}{{ title truncate="100" }}
   ```

   结果和默认模板一样，只是固定用英文：一位作者写姓，两位写 `A and B`，三位及以上写 `A et al.`；没有作者时用编者。`authors` 默认只取姓（`attachments.js` 的 `commonCreators`：`name = 'family'`）。
2. **结构化包由 p2z 改名**。Zotero 只会重命名 PDF、EPUB、图片、音频、视频（`fileRenaming.ftl` 的"Rename files of these types"），zip 不在其中。改法：`structured put` 发现包的内容没变、文件名却和它的 PDF 对不上时，用新文件名重新上传，旧的进回收站。等全库补全跑完再改代码，免得影响正在跑的批次；改完，把文件名对不上的包取出来，再 put 回去。
3. **p2z 起的文件名和 Zotero 模板对齐**：标题截到 100 个字符（`FILENAME_TITLE_MAX`），作者那段本来就是英文的 `et al.`/`and`。这样 p2z 存进来的文件，Zotero 就不会再改它的名字。
4. **以后**：Zotero 8 起，PDF 的文件名会随条目信息自动同步，zip 不会跟着变。下次 put 那个包时，第 2 条会顺带改过来。
