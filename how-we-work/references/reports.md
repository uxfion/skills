# Reports

Read this before making anything that shows results to someone: a report for the user and the group meeting; a document for people outside the project (a Word file, slides, a page for a talk, a page of questions for them); and the figures and comparison tables in these. A manuscript follows the papers reference of this skill together with *The outward document* below. What only one project needs (the terms of its field, its display pipeline, its own places) is in the project's `docs/conventions/reports.md`.

## First settle who reads it

There are two kinds, and their rules differ (the user's decision, 2026-11-10).

| | Internal report | Outward document |
|---|---|---|
| Reader | The user, and the group meeting the user presents to | Anyone who receives the work under the user's name: a hospital, people a supervisor passes it on to, the committee at a defence, the audience of a talk |
| What the reader does with it | Understands what happened, judges it, steers the next step | Takes the work as a finished whole |
| So it shows | Everything tried, failures included, and how far each claim reaches | The settled work, its results, and where it goes next |
| Form | Short sentences, tables, a verdict under every figure, the reach of each claim said where the claim is made | Connected prose in one voice, limits written as next steps, no trace of the working process |

The split exists because each form, applied to the other reader, produced what the user rejected. The internal form (a boundary column in every table, "what this report did not do" in the abstract, doubtful verdicts) was applied to a report for people outside, and the user read it as the report attacking itself: 「你这不是自己否定自己吗？」. The correction that followed, connected prose instead of lists, would in turn remove the tables and short lines of the internal reports the user rates best.

When a request does not say who will read the result, ask in one line. When the same results are needed for both readers, the outward document is written as its own document from those results: a new file in the folder of the report it draws on, while the internal report stays as it is.

## What both kinds share

### The structure is designed for this report's question

Before writing, design the structure and the line of argument from the question this report answers and from its reader: 「你要自己整理一下，设计一下结构，如何合理表述，然后再动手写」. An earlier report is a source of facts, never the outline, as the common block says of any old document: after the user pointed at an earlier report and the agent copied its shape, 「也不是一定要一样，你现在这个报告条理太不清晰了」. A case worth knowing: once, before an outward report was written, its outline was put in the chat in a few lines, and the user corrected its starting point there, before a page existed.

A report stands alone: 「全新的一次汇报，历史的那些东西我不会去看，只看我们现在做的这一份报告。所以，你要讲得全面一点」. It states the task and shows its input (the user, of a page that opened on results: 「一开始那个视频也要展现进去，因为我现在不清楚任务的输入是什么」), explains its terms, and carries its references.

### Text by hand, scripts for what is redone

The text and the page are written by hand. Scripts do only what may have to be redone: cutting and assembling figures, building tables, computing numbers. They sit beside the report, run under uv, and write their numbers to a file next to them. An HTML page itself is never the output of a script (a Word or PowerPoint file is built by a script from text written by hand and kept beside it): 「直接写html而不是用代码生成html，图表等你可以用代码运行得到。」 The user's reason is that the text of a report is the writer's own analysis and synthesis, which does not repeat: 「因为是你的分析归纳总结，不可重复」.

Every number in a report can be followed to a script and its output file, and the report says which.

### Results are seen at a glance

The user's standard: 「需要展现效果时，展现方式要更直观，让人一眼就能看出来，而不是放在不同的块上很难比较」. What must hold:

- **What is compared sits in one row.** For one case: input, result, reference, in that order. For methods: the same case and the same view, side by side. For many cases: one row per case, the same columns in every row.
- **One case, or one comparison group, fits one screen** (「而且一个案例尽量在一个HTML报告的滑动窗口里面。」). Use a full-width grid. Three layouts fail this and were each rejected: thumbnails (「缩略图我不可能再点进去的。」), one image per row so that a case takes several screens, and a single strip thousands of pixels wide. Secondary cases go into a fold, in the same layout.
- **Every image says what kind of thing it is:** observed data, a model's output, a candidate, a human-confirmed reference. The kinds keep separate labels, and an interactive element says whether it shows real data or a prediction.
- **The reference is shown, once per group.** A result without its reference cannot be judged (「另外展示的视频也要有一列是分割的标签叠加图，这样才有GT的参考」), and a reference drawn over every image hides the images (「也不是所有图都要上mask，你不觉得这样影响数据吗，增加分割图就可以，而不是叠加在所有图上」). So: one panel per group with the reference overlaid on the input, the other panels clean. A video carries a reference pane beside it.
- **The cases shown cover every category** the work covers: 「还需要在最后加入大量案例图，每种类型都要有。」
- **A video is shown as mp4,** which plays in the page and on the user's machine (「将其也一样转成mp4方便我查看」). Where the medium cannot play video or turn a 3D model (Word, PDF), show more stills: several frames, several views, several cuts.

### Every figure is looked at before its caption is written

Open each figure you place, and sample a few frames of each video, and write down what you see before writing the caption or the verdict: 「都要抽样几个做视觉评估的，不然都不知道对不对」. A judgement you made by looking is yours; in an internal report it is labelled as yours, not as an expert's reading.

### Figures

- **Text inside a figure is English by default** (the common block's rule): its script takes the language option, and a report gets Chinese figures when the user names Chinese for it. Inside means drawn into the image: axes, legends, annotations, labels. The caption and the body text around the figure are in the report's language.
- **A figure is drawn at its final size and print resolution by the script that draws it,** and stays as drawn: enlarging or resampling it later in the document tool is the repair the user objected to (「你这些图绘制的时候不就应该是输出600dpi的png了吗？为什么在操作word这边。」). The measure is that it looks clear on the page, not that nothing is lost. When every figure of one Word report was drawn at 600 dpi the file grew very large, and the user said 「也不是说完全无损，只要看上去比较清晰就可以了」 and, for that report, 「就留300dpi的就行了」. That number is the user's for one printed report: it gives the scale, and the measure decides.
- **In a report (an HTML page, a Word file) raster figures are saved as PNG:** 「另外，我们存图的时候都用PNG吧，因为JPG是被压缩过的」. The figure format of a manuscript is the manuscript's own matter.
- **A flow chart runs left to right:** 「流程图尽量不要竖着放，竖着放我一页不可能放得下，而且要滑页，根本就看不全，要横着放」. The user's test for any schematic or flow chart is that the figure alone tells the logic: 「看到图就能知道背后的逻辑和原理」.

### Comparison tables

The rule for a table that compares methods or runs by numbers is in the common block, and holds in the chat as in a file. This section is the form the block names.

- The header of each numeric column carries its direction: ↑ higher is better, ↓ lower is better.
- Ranks are per column, among the ranked rows: ¹ is the best in that column's direction, and the cell ranked ¹ is also bold.
- A reference row (the raw input, an upper bound) says in its first cell that it is a reference, and carries neither rank nor bold.

An invented example:

| Method | PSNR ↑ | LPIPS ↓ | Dice ↑ |
|---|---|---|---|
| Input (reference, not ranked) | 24.10 | 0.310 | 0.712 |
| Method A | 27.32³ | 0.214² | 0.846³ |
| Method B | 28.05² | 0.221³ | **0.871¹** |
| Ours | **28.91¹** | **0.187¹** | 0.866² |

What a result may claim, a result on a small sample included, is in the experiments reference of this skill.

### Words

- **Plain words, and every term of the project's field explained where it first appears,** all through the report: 「另外qc是什么，我都不清楚，解释这个名词，全程」; of reports in general, 「所有的报告都要求白底，学术导向，说人话」. The reader of an internal report knows machine learning and is not a specialist of the project's field, so machine-learning basics need no explaining and the field's terms do. Which field that is belongs to the project's own text.
- **A quoted English sentence** is copied as it is, with its Chinese on the line below.

### The folder is a package

A report lives at `reports/<YYYY-MM-DD>/<task>/` (the layout reference of this skill has the whole table of places). The folder can be handed to someone as it is: 「我希望html是可以单独拎出来的」.

- Every image and video the report shows is copied into the report's own `figures/`, grouped by task or case, and linked relatively, as files and not as base64 inside the page. A README in `figures/` says which path or script each file came from.
- A version derived from a report (a Word file, a talk page) lives in that report's folder, with its build script and a note on how it is built. The user turned down a separate folder for one: 「我觉得是不是也没必要新建一个文件夹，你就直接放在原来那个」.
- In git: the page, the scripts and small manifests. For images, videos and models made from patient data, the common block's guardrail on patient data holds.
- **A summary over a stretch of time** (before a group meeting) is a report like any other: its task folder is `reports/<the date it is written>/meeting-summary/`. It states the period it covers and uses its own copies of the figures. The dates of the work come from the records; a folder's date is not the date of its content.

## The internal report

The user reads an internal report to see what was done and decide what comes next, and presents from it at the group meeting. It therefore shows everything, and it marks how far each statement can be trusted. Its recurring word is the boundary (边界) of a result: what that result does not show.

### What must hold

- **The answer comes first.** The title is a question or a claim, and where there is a finding the title carries it with its number. The opening says in its first sentence where things stand.
- **The result is shown at the front.** Directly after the opening, one worked case runs from the input through the intermediate steps to the output and its reference, in one screen; the rest of the report explains it. Minutes before a group meeting the chosen result sat far down the report: 「既然能选出来，你就在报告里展现出来，而且要放在前面。」
- **A claim is worded no more strongly than its evidence, and its boundary is written where the claim is made.** The user approved the boundary being written clearly, in the form of the reports that did it best. There it stood in four places: one line under the subtitle for the report as a whole, a boundary column in the tables, a "cannot show" clause in the captions, and "not achieved" and "not done in this report" in the abstract. Use the places this report's claims need. A conclusion also carries its state; a starting vocabulary, to extend where a case needs another word: 已验证 / 部分验证 / 未实现 / 候选.
- **Every figure has a verdict.** A one-line judgement under each image, coloured green (usable), amber (doubtful) or red (not usable), and the group's conclusion in its last cell. What a look would show, the report says before the user has to.
- **Every direction tried is shown, the failed ones with real images, the reason and the next step:** 「记得在报告里也要记录不同方向的尝试及效果图，这样在汇报的时候才有说服力。」 Among the cases shown, each kind of failure has its case. A decision appears with the question it answered and the options that were weighed: 「把核心问题（需要考虑的点）列出来，还有方案，而不是就把决策直接按点列出来。这是组会报告」.
- **Cases picked for display are labelled as picked.** Only randomly drawn cases stand for the average, so when good cases are added the random ones stay: 「你再选几例比较好的补充上去吧，随机的6例也保留了。」
- **Short forms are right here:** tables, short labelled lines and lists, wherever they let the reader scan.
- **An open question in a report is evidence laid out for a decision; the question itself goes to the user in the chat,** the way the common block describes. Many lists of pending decisions were placed at the end of reports, across projects, and they went largely unanswered.

### The frame of a group-meeting report

The rules are the ones above. This table is what the internal reports the user rated best have contained, in the order they had it, and a report for the group meeting has this frame by default: the user asked for the style to be written down so as not to point at those reports again each time. Order the numbered sections for this report's argument, add what its question needs that is not here, and where you leave a part out, have a reason you could give.

| Part | What it held |
|---|---|
| Eyebrow (眉题) | One line in small grey type: topic · date · kind of report |
| Title, subtitle | The question or claim; one sentence of scope |
| Evidence boundary | One small line. It has named: which data, whether the same data also served to choose the method, what was not looked at, whose readings the judgements are, which script and output file the numbers come from |
| Abstract box | A bold first sentence with the state; two or three short lines; then "没做到的" and "本报告没有做什么" |
| Key numbers | Three or four large numbers, each with a line saying what it measures and where its limit is; a key change written large as "a → b". Numbers otherwise stood in tables, not in running text |
| Navigation | One row of anchors to the numbered sections |
| The worked case | One case from input to output, one screen |
| Numbered sections | Each heading a full sentence or a question, so that the headings alone tell the story. They have covered: why and what; data; method, with a flow chart; results over all cases; problems met and fixed, and the directions that failed; limits, checked against the scope in `docs/goal.md` plus this work's own |
| Closing | Where the report answered several questions, a table: question, answer, boundary. Then the open questions, each with its evidence, and the candidates for the next step, each with its reason |
| Files and reproduction | Scripts, the experiment folder, the git revision, the commit of any upstream code |

Full comparisons, secondary cases and extra videos went into `<details>`, so that the main argument read in one go.

### The look

The user asked that the look be described in words, so that it need not be pointed out again: 「不是把样式提取出来，而是口述出来，用人类的语言描述出来。」 One thing in it is the user's rule: the background is white, always (「一定是白色的，我就不喜欢黑色背景。」). The rest describes the reports the user named as the look they want; its numbers are measurements of those pages and give the scale, not targets.

It is a printable academic technical report, not a slide deck and not a product page. One restrained accent colour (a deep teal or steel blue) marks headings, rules and boxes; the rest is thin light-grey lines and space. The content is about 1180 to 1440 px wide, paragraphs at most about 1240 px, body text 16 to 17 px with line height 1.7 to 1.8. Callout boxes kept one meaning per colour: teal a decision, red a warning, amber a caution, blue information, green a lesson. A grid image opened its full-size file on click, and a key region had a pair of enlarged crops beside it. Folds and controls may disappear in print; the conclusions and the figures remain.

### One section, complete

An invented example: a page head with its style block, the opening, and one numbered section. The section goes: a paragraph saying why it matters, a table of what was done, why, and the boundary, the figures, a box with what the section taught. That is one way a section has gone, not a mould. The style block was rendered once, on 2026-11-10, with the build the CDN served that day.

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>换用边界损失后，14 例里 12 例的分割可直接使用</title>
<script src="https://cdn.tailwindcss.com"></script>
<style type="text/tailwindcss">
  @layer base {
    h1 { @apply mt-2 text-3xl font-semibold leading-snug; }
    h2 { @apply mt-12 border-b border-gray-200 pb-2 text-2xl font-semibold text-teal-800; }
    p  { @apply my-3; }
    table { @apply my-4 w-full border-collapse text-left; }
    th, td { @apply border border-gray-200 px-3 py-2 align-top; }
    th { @apply bg-gray-50 font-semibold; }
  }
  @layer components {
    .eyebrow  { @apply text-sm text-gray-500; }
    .subtitle { @apply text-lg text-gray-700; }
    .boundary { @apply text-sm text-gray-500; }
    .fig      { @apply my-4 grid gap-3; }
    .cols4    { @apply grid-cols-4; }
    .kind     { @apply mb-1 block text-xs text-gray-500; }
    .note     { @apply mt-1 text-sm text-gray-600; }
    .verdict  { @apply mt-1 text-sm; }
    .good     { @apply text-green-700; }
    .doubt    { @apply text-amber-700; }
    .bad      { @apply text-red-700; }
    .caption  { @apply text-sm text-gray-600; }
    .takeaway { @apply my-4 border-l-4 border-green-600 bg-green-50 px-4 py-2; }
  }
</style>
</head>
<body class="mx-auto max-w-screen-xl bg-white px-6 py-8 text-base leading-7 text-gray-900">

<p class="eyebrow">铸件气孔分割 · 2026-11-10 · 阶段报告</p>
<h1>换用边界损失后，14 例里 12 例的分割可直接使用</h1>
<p class="subtitle">范围：铝合金铸件表面照片里的气孔，不含裂纹。</p>
<p class="boundary">证据边界：14 例来自同一台相机，其中 6 例也用于挑选损失权重；判定是 agent 自己看图给出的，
  不是质检员的判定；数字出自 <code>eval_dice.py</code> → <code>eval/dice_per_case.json</code>。</p>

<h2 id="s2">2. 边界损失把漏分的小气孔从 5 例降到 2 例</h2>
<p>气孔（金属凝固时气体留下的小坑，照片上是一小块比周围暗的区域）越小越容易被整块漏掉，而小气孔正是最需要提示出来的。
  这一节看换损失以后漏分少了多少。</p>
<table>
  <tr><th>做了什么</th><th>为什么</th><th>边界</th></tr>
  <tr><td>把 Dice 损失换成 Dice + 边界损失，其余设置不变</td>
      <td>Dice 对小目标不敏感，漏掉一个小气孔几乎不扣分</td>
      <td>只在 14 例上比较，其中 6 例参与了调权重；不能说明换相机以后仍然成立</td></tr>
</table>
<div class="fig cols4">
  <figure><span class="kind">原始观测</span><img src="figures/case07/input.png" alt="case 07 input">
    <figcaption class="note">右上有一个约 0.8 mm 的小气孔</figcaption></figure>
  <figure><span class="kind">模型输出 · 旧</span><img src="figures/case07/dice_only.png" alt="case 07, Dice loss">
    <figcaption class="verdict bad">不可用：右上的小气孔整块漏掉</figcaption></figure>
  <figure><span class="kind">模型输出 · 新</span><img src="figures/case07/boundary.png" alt="case 07, boundary loss">
    <figcaption class="verdict good">可用：小气孔分出，边缘略偏外</figcaption></figure>
  <figure><span class="kind">人工标注（叠加在输入上）</span><img src="figures/case07/reference_overlay.png" alt="case 07 reference">
    <figcaption class="verdict good">这一组的结论：可用。新损失补上了漏分，边缘还差约一个像素</figcaption></figure>
</div>
<p class="caption">看什么：右上角的小气孔在第二格消失、在第三格出现。不能说明什么：这是挑选展示的一例，
  14 例的整体情况见下表。</p>
<div class="takeaway">启发：漏分来自损失函数，不是数据量；先改目标，再谈加数据。</div>

</body>
</html>
```

### Making the page

The user's standing choices for an internal report:

- **Tailwind and Mermaid from a CDN:** 「报告使用 CDN 上的 Tailwind 进行布局和样式设置，并使用 CDN 上的 Mermaid 来绘制图表，尤其适用于能够可靠地展现结构图/流程图/序列图的情况。」 Layout and style come from Tailwind (`https://cdn.tailwindcss.com`), with a few semantic classes of your own defined by `@apply` inside `<style type="text/tailwindcss">`, as in the example above.
- **Set no font family of your own** (no `font-family`, no `font:` shorthand); set sizes and line heights only. A named font that was missing on the user's machine fell back to one that is hard to read, and the user's answer was 「也不用刻意设置，就是它默认是什么字体」.

One thing the tools were seen to do, twice; judge it against what they do now.

- **A semantic class that carries a Tailwind utility's name breaks the page** (seen 2026-09-24; seen again 2026-11-10). `.grid{@apply grid …}` is a circular `@apply`: the CDN compiler drops the whole style block, base styles included, and every image stacks vertically at full size, which the user met as 「现在报告完全不可读」. The same goes for `.flex`, `.table`, `.hidden`, `.block`, `.container`. Names that have worked: `.fig` for an image grid, `.cols2`, `.cols3` and so on for its columns. A search of the style block for a class that applies its own name finds the fault before the user does.

## The outward document

An outward document presents the work as the user's own finished work to someone who was not there while it was done. A manuscript is the same kind of text; what is a manuscript's alone is in the papers reference of this skill.

### What must hold

- **It is one whole:** 「要是一份比较完善的报告，是一个整体，一份技术报告，而不是堆积的实验和尝试，是对外部展示的一份整体技术报告。」 It starts from what its reader asked for and from the project's goal, and shows the settled design and its results. The history of attempts, earlier versions and intermediate experiments stay in the project's records.
- **It argues in connected prose.** Paragraphs with topic sentences and transitions; a list, a numbered sequence or a bold label opening a paragraph only where the content is a list by nature (a table, the references, the panels of a figure). 「我看到很多bullet point和标号，感觉让人不是很舒服，很像AI产出的，必要时可以加，没必要的话，稍微避免一点，在论述的时候。」
- **It has one voice, the user's.** 「技术报告中不该出现我和你分离的这种情况，展现人都是我」. Whoever did a part while the work was done (a script, the agent, the user) is told as one author: 「这三方都是要统一成一个整体去叙述的」. The working process stays out of the content: how the agent checked its work, a working principle, an instruction of the user's, an experiment code, a version label, a file path. A step that is truly part of the method stays, told as the method's step. One case: a section that told how the agent had reviewed frames by eye, in the words of the working process, drew 「看图审查只是我在让你实现的过程中讲到的东西，这不应该呈现在技术报告中吧」; the figure stayed, and the section was retold as the method's quality control, describing what the method checks.
- **It stands behind itself.** A fact of scope is stated once, neutrally, where it belongs: how the evaluation was done in the evaluation section, limits in the outlook, each limit with the step that addresses it. Verdict words are neutral (良好 / 待复核). Every true fact is still there; it is placed and worded as part of the work. 「就感觉你在拆自己的台一样」 was said of disclaimers repeated through the abstract, the tables and the conclusion.
- **Results are shown generously and the examples are good ones:** 「结果展现要丰富一点，图多一点没事，就是要被人看到效果」, 「例子挑选比较好的」. The key technical points are explained until a first-time reader follows them. Picked examples show how the method works, not how often (the experiments reference of this skill, *What a result may claim*).
- **Length follows the content.** The user's measure is 「不要太长篇大论，也不要太简略，围绕着关键点，收放得当」; a page count mentioned on the way is a scale, as the common block says of any loosely given number (「17页就17页吧，页数没要求」).

After drafting, read the whole text once for tone, not only the passages that were flagged.

### The same evaluation, written for each reader

An invented example. On the left, the lines an internal report holds; on the right, the two paragraphs an outward document makes of the same facts.

| Internal report | Outward document |
|---|---|
| **评估**<br>· 14 例铸件照片，同一台相机；其中 6 例也用于挑选损失权重。<br>· 12/14 可直接使用；2 例各有一个 1 mm 以下的气孔仍漏分。<br>· 判定是 agent 对照标注自己看图给出的，不是质检员的判定；没有盲评。<br>· 本报告没有做：第二条产线的数据。<br>边界：不能说明换相机以后仍然成立。 | **4.2 评估**<br>评估使用 14 例铝合金铸件的表面照片，其中 6 例同时用于确定损失的权重，以同一位质检员的标注为参照，逐例对照检查分割结果。采用边界损失之后，12 例的分割可以直接用于后续测量（图 5）；其余 2 例中各有一个直径小于 1 mm 的气孔未被分出。小气孔最容易被漏掉，也最需要提示出来，因此下文的改进首先针对这一类。<br><br>**6 展望**<br>目前的数据来自同一条产线的同一台相机，评阅未采用盲法。下一步将纳入第二条产线的数据，并请两位质检员盲法评阅，以检验方法在不同相机上的表现；针对 1 mm 以下的气孔，将提高输入分辨率并补充这一类样本。 |

Every fact on the left is on the right: the six shared cases, the two misses, one camera, no blind reading. What changed is where each stands and how it is told. The lines became paragraphs. Who looked at the pictures is no longer said, because the document has one author. Each limit appears once, in the outlook, with the step that addresses it, and the boundary line that closed the internal block has no counterpart, since its content is in the outlook.

### By medium

- **Word and PowerPoint files** are built by a script kept in the report's folder, and checked in the application their readers will open them with. Nothing is installed for the check: installing another office suite to look at a Word file was refused (「windows上本来就有word啊」).
- **A page for a talk** carries fewer words and more to look at: 「展示的 HTML 字可以稍微少一点，但是关键的内容我们要讲清楚」, 「因为HTML会放到汇报演讲的时候去讲。」 It opens on the task's input, then the main figure, then results as figures, video and interaction; its structure is designed like any report's. It has to work where it is shown, so it may carry its own stylesheet and local copies of its libraries instead of the CDN ones.
- **Questions for people outside** (a supervisor, a clinician, a data provider) are gathered as they come up and, before the meeting, put on one page with pictures: 「医生数据方面的问题最好做成一个HTML这样既可以展现问题，又有图像」. The form that has been used: an overview table (the question, whom it is for, what it decides), then for each question why it is asked, what each answer would change, the evidence images, and fixed answers to choose from. Which questions are worth an expert's time, and what is tried before asking, is in the experiments reference of this skill. Like everything that goes to people outside, the page goes through the user (the common block).

## Checking and handing over

Before handing over: read the source through once, and open the figures you made.

Where a browser is already on the machine, headless included, open the HTML report in it and see that the layout holds: grids are grids, no table runs off the page, no diagram shows an error, no image is missing, a scripted control does what its label says. Fix what you find. Where there is none, say at hand-over that the page was not rendered. Install nothing for this, whatever the installer: 「卸载掉，没让你装。我自己会检查。」 Here this document is narrower than the common block's rule on installs. Whether the page reads well and looks good is the user's judgement. Both halves have their cases: the user was the first to see a broken page (every image stacked, a fallback font, a diagram's syntax error), and, before this was settled, the user objected when a browser tool was brought in and its system libraries installed to look at one (「你为什么要用playwright？」).

Then give the user the path; the report reaches them in the chat the way the common block has any long document reach them.

## After hand-over

- **A report the user has seen is a snapshot.** New findings go into a new report in a new task folder, and a reworked version is made as a new file while the old one stays (「你可以新建一份，原来的就不动了」). The exception is a report the user is still presenting from and wants extended: new material is appended as dated sections and what is there stays untouched (「现有报告现在就不要修改了，我觉得挺好的。有新的东西出来，你就追加进去」).
- **A report that a later one overtakes** stays as written and gets the dated line at its top that the common block gives any superseded document, naming the report that replaces it.
- **A statement in a report the user has seen that turns out never to have held** stays as written and is marked: a red box beside it says that it is wrong and links to the report that corrects it, a box at the top of the old report lists its corrections, and the new report says what it corrects. Everywhere else the false statement is taken out (the records reference of this skill, *Keeping records true*).
- **When the user asks for a change inside an old report,** the old content goes into a fold and the section opens with the date and the reason.
- **Each report gets a row in `reports/README.md`:** date, task, the question it answers, the core conclusion, the path. Where an index page stands over several reports (a day's `index.html`), it shows per task the question answered, the core finding, one or two typical images and a link into the report: 「你在index的时候也要放一两张典型的图，然后有个链接跳转过去。不然我怎么知道你具体哪个文件夹干了什么？」
