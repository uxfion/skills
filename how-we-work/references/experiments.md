# Experiments

Read this before a run whose result a conclusion will rest on (training, a processing or evaluation batch, model calls that rate outputs or are themselves the conditions compared), before saying what a result shows, and before using upstream code, building an environment or touching a training server. It also covers what comes after a run: an incident, a defect found later, the step to the next run.

The common block in the project's `AGENTS.md` holds the principles this document applies (*Look, understand, then trust*; *When stuck, step back*; *State lives in files*; *Review before it counts*) and the guardrails it relies on (a small run before a full one, the announcement of a batch that spends at scale, patient data, caches, installs). This document is the practice under them: where it names a rule of the block, it adds only what experiments need. In one place the block hands its rule over to this document, which says so there (*On a training server*, installing). The project's own `docs/conventions/experiments.md` adds what only that project needs; the last section says what belongs there.

Three sections apply only in their case: *With an expert's reference*, *Validating a heuristic*, *On a training server*. Every experiment needs the rest.

## What an experiment leaves behind

Three readers come after you: the user, who decides from the result; a later session, which continues the work without your memory; and a supervisor, collaborator or reviewer, who asks how a number was obtained. An experiment is finished when each of them gets what they need from the files alone:

- **Trace**: what ran, from which code, on which data, under which condition.
- **Trust**: the outputs were looked at and understood, the result was compared with something, and the claim covers only what was checked.
- **Continue**: where it stopped, and the one command that resumes it.

## One line of work, one directory

An experiment line lives in `experiments/<YYYYMMDD>-<topic>/`, named when it starts: the date, then the gist of the line or of its main change, so that the folder list reads as a history. Pausing, resuming, repairing and repeating all happen in that directory. A smaller copy made to save cost, a "-clean" copy made after a fix, or a directory per draft splits one line over places that nobody can compare later. In one project a request to save cost was read as "open smaller copies" and produced many directories; by that project's notes, what the user had asked for was to let the running units finish and hold the rest back until cost allowed, all in the same experiment.

A new version of the method is a new line and gets a new directory. A repeat of the same condition is a new run in the same directory (*Run records*).

Inside it:

- `README.md`: written when the line starts, completed the day it finishes (form below).
- Its own environment (`pyproject.toml`, `uv.lock`) and, where it uses upstream code, its own copy of that code (next section).
- `runs/`: one record per run, in git (*Run records*).
- `outputs/`: everything the runs produce, one folder per run. Weights the experiment trained stay here too.
- `preview/`, where the line has process products for the user to look at (*Looking*).

Git holds the experiment's own code, the README, configs, lock files, run records, metrics and small manifests. Bulk outputs, weights and the experiment's copy of upstream code stay out of the project's git. Whether previews and other things rendered from patients may be versioned is decided by the common block's guardrail on patient data and the project's own text.

**The day a line finishes**, write the conclusion and the reflection back into its README and append one entry to `docs/experiment-log.md` (Hypothesis · Set-up · Result · Conclusion · Next), naming the directory; bring the line's node in `docs/exploration-tree.md` to its present state (or the place where the project tracks its directions). The log takes one entry per finished line; its heading format is in the records reference of this skill. What is learned later that limits or qualifies an entry is appended under it as a dated caveat. A statement in a README or in the log that turns out never to have held is a different case: the records reference (*Keeping records true*) says how it is corrected.

**The README.** One complete example. Everything in it is invented; the form is the point. The user reads this file, so it is in Chinese:

```markdown
# 20261015-seg-finetune

**目的。** 用户 2026-10-15：「<用户提出这条线时的原话>」。要回答的问题：在我们的数据上微调 <上游模型>，分割能不能好过现成权重。

**条件。**
- 上游代码：本目录里的副本 `<上游仓库>/`，提交 `3f2a9c1`；改动提交在副本自己的 git 里。
- 数据：`<数据集>/v2`，训练 41 例，留出 9 例（留出的病例没有参与过任何调参）。
- 环境：本目录的 `pyproject.toml` 和 `uv.lock`。
- 参数：`configs/finetune.yaml`。

**跑之前定下的。**
- 完成的标准：留出的 9 例逐例看过叠加图；指标只报看过的病例。
- 对照：同样的训练设置，不加载预训练权重（看预训练有没有用）。简单参照：现成权重直接推理。
- 判据：每组跑 <n> 个随机种子；比对照高出的幅度超过种子之间的波动，才算有用；不超过就写持平。

**偏离。** 2026-10-16：批大小从 8 降到 4（显存不够），对照组同样改了。

**两组之间其他的差别。** 对照组在另一张卡上跑（型号相同）。

**事故。** 2026-10-17：种子 2 在第 3 个存档点中断（服务器重启），同一条命令续跑，仍是同一次运行；`runs/20261016-2140.json` 的 `interruptions` 里记了中断的时间、原因和续跑的存档点。没有结果出自中断的那一段。

**结论。**（跑完当天补）按事先的判据是什么结果；哪些站住了；看过的范围是什么，哪些只是生成了没看。

**反思。** 改正了自己之前的哪个判断；计划为什么变了；现在最弱的一环是什么。
```

The headings are a starting set. A heading with nothing under it says `无`; add one when the experiment has something none of these holds. A known defect in the data goes in one marked line at the very top: what it is, what it affects, whether both arms are affected alike.

## Environment and upstream code

**Each experiment owns its environment.** Its directory has its own `pyproject.toml` and `uv.lock`, fixed once it has run; a small script carries its dependencies in a PEP 723 header. A new uv environment is built from the cache in seconds, so separate environments cost little and nothing shared can shift under a finished experiment. The user: 「你新建一个环境代价也不大啊，你只要确定了 pyproject.toml 就行了，其他都非常快」. For GPU software, pin every version in the first install (the framework, its CUDA build named explicitly, the packages that build needs), keep one CUDA build per environment, and change versions by building a fresh environment. An environment is rebuilt where it is needed, never moved or copied: it holds absolute paths (「uv环境直接重建不是更快吗」).

**Upstream code has two copies with two jobs.**

- `repos/<repo>/` is the reference copy: a full default clone, kept current with `git pull`, read-only as code: nothing runs there and no tracked file changes there. The pretrained weights its code expects are the one thing added to it (below). It is not pinned: 「Repos也不一定一定要去锁吧，为什么一定要锁定呢？它更新了，你也可以pull下来嘛」. The project's README registers each repository: source, what it is for, where its weights come from.
- An experiment that uses the code clones its own copy into its directory (`git clone ../../repos/<repo> <repo>`), checks out the commit it needs and names that commit in its README. This copy is the experiment's: change it as needed, commit the changes in the copy's own git, and leave it alone once the experiment is finished. The copy has its own git and stays out of the project's.

The user: 「repo 中留一份，experiment 留一份，experiment 那份可以自己改」; 「不要去动上游的东西」. The copy sits directly in the experiment directory, without an `upstream/` level between.

**Weights stay with the code that uses them.** Pretrained weights sit where their repository expects them (`checkpoints/` or the like), and an experiment's copy of the code reaches them without a second copy on disk (a hard link does it); weights an experiment trained stay in that experiment's directory. A separate folder for all weights was rejected: 「本身权重就是在 repos 里面或者在 experiment 里面，为什么你会单独把所有的权重放在一个位置呢？」

## Run records

Every run writes `runs/<YYYYMMDD-HHMM>.json`, committed. It holds checksums and settings, never data. An invented example:

```json
{
  "run": "20261016-2140",
  "status": "done",
  "started": "2026-10-16T21:40:12+08:00",
  "ended": "2026-10-17T03:05:48+08:00",
  "interruptions": [{"at": "2026-10-17T00:52:30+08:00", "why": "host restart", "resumed_from": "checkpoint 3"}],
  "command": "uv run train.py --config configs/finetune.yaml --seed 2",
  "repo_commit": "8c41d07",
  "repo_dirty": false,
  "upstream": {"<repo>": "3f2a9c1"},
  "config": "configs/finetune.yaml",
  "config_sha256": "<sha256>",
  "data": [{"path": "<dataset>/v2/train.manifest", "sha256": "<sha256>"}],
  "host": "<alias>",
  "gpu": "<model>, index 1",
  "not_done": {"mm_calibrated": false, "external_test": false},
  "outputs": "outputs/20261016-2140/"
}
```

The field names are a starting set: a project whose scripts already write run records keeps its own names. What must hold whatever the names, and why:

- **The commit in the record is the code that ran.** Commit before a run whose result will be reported or compared, however small the change (such a run is a milestone in the block's sense, so the edit does not wait for a later one); `repo_dirty` says when it was not so. A run without a record cannot be defended later: one project had to write an early run's model down as "presumed, no written evidence".
- **Whatever can change under a comparison is recorded per run**: the upstream commit, the config, the data by checksum, the host and GPU, and for model-call experiments the model snapshot, the effort setting and the harness version (one harness updated itself in the middle of a campaign, and the change could be dated only from file times). Data paths are written relative to the data root, which moves.
- **`not_done` states what this run did not do**, in fields a report can read, so that a later report does not present the undone as done.
- **`status` is one of `running`, `done`, `failed`, `interrupted`.** Failed and interrupted runs are kept and marked. A run resumed from its own checkpoint is the same run: its record keeps its name and its `outputs/` folder, goes back to `running`, and lists each interruption (when, why, the checkpoint it resumed from). `interrupted` is the final status only of a run that nobody resumed. An infrastructure failure (the host went down, a time limit set too low) is `interrupted`, never a failure of the method.
- **A finished run is never overwritten.** Redoing or repeating it is a new run in the same experiment directory: a new record under `runs/` and a new folder under `outputs/`. A derived dataset that several experiments share sits in a versioned directory, and changed data is a new version.
- **The data records its own facts too.** The common block's *State lives in files* asks for a fact to be recorded at the earliest moment it is in hand. In an experiment that moment is usually a processing step (an invented example: the physical scale of an image, written by the step that extracts the image, while the header that states it is still open), and the step writes it to a fixed place that later steps read.

**Training is resumable**: the same command, run again after a stop at any moment, carries on from the last checkpoint as if it had not stopped. Before the first full run, stop once at the first checkpoint and confirm that it resumes. The user, after a run was lost: 「你要记住，以后这种训练的都需要有断点续训」. A batch script works the same way: run again, it skips what is finished and says what it skipped. Where a run is many independent units (one per case, one per model call), each unit leaves its own small record.

## Before a run

A **costly run** below is one that would be expensive to repeat: hours of a card, money or the usage quota, an expert's or the user's time.

- **The base first.** What a costly run stands on (the data version, the definition of the target, the tool or deployment it runs through) is settled before the run goes from its small trial to full scale, and when the user asks for the full run while one of these is open, say what is open before starting. After a large batch of model runs on a base that then came into doubt, the user: 「应该把这两个问题全部解决以后，我们再去做下一步。不然的话，前面做的再多工作也是徒劳，后面也会被推翻。」 and of their own order 「我当时没有想清楚，就直接让你去跑了」. The same holds layer by layer: the data is seen to be right before training, the target before the model, the metric before the figure drawn from it. 「在训练前一定要把数据基础做好，你要是数据集做得很烂，再怎么训练也是差的」.
- **What will count is written before the result exists**, in the README (the example's 跑之前定下的): the done-when of the run, naming the observation that would show it false; the control and the simple references; the criterion that separates "helps" from "a tie". Committed before the run, the hash shows it predates the results. A step designed after seeing results is labelled as such (*What a result may claim*).
- **A small run before the full one** (the common block's guardrail), on real data: one unit end to end, then a few, then all, inside the same experiment directory. A configuration that has already run in that place needs no second small run.
- **The review before a costly run** (the common block: *Review before it counts*) reads the whole chain once more: prompts or configs, the flow, the scoring. Before one such run it found several defects, among them a run record that named the wrong prompt hash and a metric computed only over the cases that had a label.

## Looking

Looking is for understanding; a procedure followed without it has failed before. The user stopped a line of parameter tuning with: 「你要看图、理解图、反思问题，之前为什么画错，之前定义了什么，这样下次不会再犯这类问题」 and 「调参根本就解决不了根本上的问题，下次换一个病例，或者换一个视频你还是会犯，根本上的问题是你对这个问题的理解、认知，以及背后潜在的那些规则，还有包括医学知识」. So before the next parameter is changed, write down why the last result came out as it did; when you cannot, that is the next thing to find out.

- **Look at the intermediates before a batch.** Before a step runs over everything, render its intermediate results (crop boxes, seed boxes, mask overlays, contact sheets) and look at them yourself: 「注意在处理图片的时候要先预览看一下效果确定没问题再处理，而不是一味的执行，注意观察处理的中间状态，视觉评估」.
- **The diagnosis is yours.** When outputs look wrong, work out from the images what is wrong and act: 「你自己看图就好了，你能看图的啊」. A list of failure types for the user to point at hands back a job they gave you. When the user's eye and the numbers disagree, check the evaluation itself first (inputs, reference, alignment), and say what you see, including when it does not support them.
- **Failures are grouped before they are fixed.** With a small sample, look at the failures first and group them: a kind that recurs is repaired in the general flow; the cases left over, which share no cause, get per-case parameters written into the config, and the general flow stays as it is. 「数量比较少，你可以针对特定的视频使用agent视觉定位然后特调」.
- **Process products go where the user can see them** while the work is still moving: the experiment's `preview/` folder (numbered step folders, input beside result, a short README saying what each step shows), so that they can steer early. 「我希望看到你过程中的产物，这样我好把控方向。如果有问题的话，我会及时出来纠正你」.

## With an expert's reference

This section holds only where the project works against a domain expert's reference: their annotations, drawings or statements.

**An expert's statement outranks your own reading.** When what an expert said or drew disagrees with what you see in the data, the first hypothesis is that your definition is wrong. In one project an expert's remark was recorded as "does not hold on this data"; methods were then built and validated against the agent's own definition for months, until the expert's drawings showed that the definition had been wrong from the start. The user: 「老师是经验非常丰富的超声影像科医生，他的勾画应该是准确的」; 「老师勾画的基本上就是金标准了」. Fixing criteria in advance and testing blind guard against tuning, and they do not guard against a wrong definition.

- **Before a method is built around a domain definition** (where a boundary lies, which structure is which, what counts as a finding), get a few examples from the expert and align to them; keep a part of the expert's annotations unseen as the blind test.
- **When expert input surprises you, or a result disagrees with it**, check in this order: your own conversion and annotation pipeline, then domain knowledge, then accept it. 「你要去查证一下，是不是我们在转化过程中或者在标注过程中的问题，还是说它本身就是对的」; 「符合医学常识吗？」.
- **The expert's time is the scarcest resource.** A domain question goes first to your own knowledge and your reading of the data, then to guidelines and the literature, and to the expert last, as three or four prepared cases: 「实在不确定，最后最后一步，你就找出这三四例，我发给他，让他确认」. After a second annotation request was drafted: 「为什么又要请求勾画一次？老师，他没有那么多时间」. What only the expert or the data provider can settle is put on the list of questions for them early; tuning around such a question does not answer it. The form of the page of questions is in the reports reference of this skill.

How an expert's reference is read in one field (what to look at first, what explains where a line lies) is that project's own knowledge and lives in its convention file.

## What a result may claim

A conclusion says what was checked, and stops there.

- **"This ingredient helps" rests on a control**: a run with only that ingredient removed and everything else the same, beside a few simple references (examples: the trivial baseline, the input passed through unchanged, the order shuffled). In one project the first model's "the extra input helps" was levelled by a control with the same loss and without that input. The references also guard each metric: when a result is better than expected, or two methods come out identical, look for a mechanical cause before reporting it.
- **A difference smaller than the run-to-run spread is a tie.** A stochastic pipeline is not read from one run: measure the spread over seeds or repeats and write the tie rule beforehand (three per arm was one project's practice; the number is not the user's). In one project the verdicts whose interval had excluded zero all came from the single most favourable run.
- **Candidates are compared along one path**: the same cases, display, scale and scoring. Every difference between the arms other than the intended one is written down the moment it is found and carried into the README and the report.
- **Candidates are chosen by the user's statement of the task.** A proxy target you set yourself may guide a search; it does not decide between candidates. In one project a stand-in task had become the selection metric, and the user had to recall the task twice: 「注意我们最初始的任务是图像增强」.
- **One set of data in several roles is checked role by role**: choosing the target, selecting the model, scoring, and any "ground truth" made the same way as the training target. The user asked it unprompted: 「还有之前有提到说训练集和实际勾画的提取的信号是同一批，会不会有问题」.
- **A negative says what it negates** (the practice under the common block's sentence on negative results). Name what was tested and on which dimension it failed; one failed probe rules out that probe; a negative obtained with a cheap stand-in is "inconclusive". In one project a single blanket "fail" buried several real findings until the verdict was reopened.
- **What was added after seeing results is labelled post hoc** and reported apart from what was fixed in advance; it does not revise earlier conclusions. A tie by the advance criterion is written as a tie.
- **Picked cases show how a method works, not how often.** With a small sample give counts, not percentages. Which cases are shown to the user is in the reports reference of this skill.
- **A check is named for what it checks** ("locally stable", not "registration passed"), and **a plan is not a result**: what has not run is not written as a finding, and where only part was looked at, the text says which part.
- **A method found in a survey is tried on our data** before it is recommended or dismissed: 「你肯定要实测新找到的比较好的方法」.

## Validating a heuristic

A heuristic (a threshold, a scoring rule, an automatic QC, a selection rule) is known to work only on the cases it was shaped on, so it is validated on cases it never touched, by a grader who cannot tell what you hope for. One thing has a fixed order; the rest must hold however the work is arranged.

- **Frozen before any held-out result is seen.** This is the one order: the code, the thresholds and the severity definitions are committed first, so the hash predates the results.
- **Tested on data it was not shaped on.** A held-out set that has been looked at is spent, and the next validation needs new data; cases looked at while debugging are locked out of it.
- **Graded blind, with controls.** Known-good and known-bad items are hidden among the real ones; a grader that passes a known-bad item is not trusted on the rest. The graders' raw marks are reported beside your own summary of them.
- **Your own eyes on what a decision rests on**: the few items the decision turns on, and a sample of the items that passed.

While the heuristic is still being shaped on development data, each stage ends with the question whether a better approach exists.

All of this guards against tuning toward the answer you hope for. It does not show that the definition being tested is the right one (*With an expert's reference*).

## When something turns out wrong

- **An incident during a run is repaired in place**, in the same directory: mark the affected cases and results, and put a dated line at the top of the affected experiment's README (the example's 事故). **In a comparison, every unit runs under one condition**: when a repair changes what the units see, results from before it and from after it are not put into one comparison. The earlier units are rerun from the repaired state, or kept apart and marked; a rerun that costs is the user's decision (next bullet). A change that is not a repair (a setting, a limit) waits for the next run and is noted for it.
- **A defect found later is first measured.** List each earlier conclusion it touches and say which stand and which change; do the analysis that needs no rerun before deciding on one; rerunning at cost is the user's decision. Several data defects in a row cost one project no experiment this way; the user: 「这样之前跑的实验结果也不用废弃了」. A conclusion that the defect shows never held is then corrected wherever it was written, as the records reference of this skill says (*Keeping records true*).
- **A flaw in a shared step reopens the verdicts that passed through it** (the common block, *Look, understand, then trust*), the negative ones first. After one display bug was repaired the user asked: 「之前探索出来的其他信号呢，是不是有些一样遇到这个问题，导致渲染的不好，然后被排除。你自己全部检查一遍，再渲染，防止漏了。」 A family of signals rejected long before turned out to be among the best.

## From one run to the next

A run that ends is half the work: 「你不能运行完就结束了，要评估，要分析，总结反思再改进，有问题再查文献搜索，改进点迭代」. After each run: look at sampled outputs before the numbers, write the verdict and its reasoning, bring the line's node in `docs/exploration-tree.md` to its present state, then choose the next step across all open directions and add the choice to the tree's 选择记录.

- **One group of related parameters per round**, old and new on the same cases; with several changed at once nobody can say which one moved the result.
- **An untried sibling direction comes before a third refinement of the same branch.**
- **When part works and part fails, go on with what works and park the rest**, recording what would reopen it: 「失败的可以暂缓，先把成功的案例血管3d重建出来」.
- **When a line has stopped paying, say so first**, with the numbers, propose closing it with a short summary, and say in the same message what the main line still lacks. Stopping a direction is the user's decision; parking a failing part is yours.

## On a training server

Which servers are the project's, their aliases, storage roots and hardware are project facts and live in the project's `docs/servers.md` (form at the end of this section). What holds on all of them:

**Choosing where to run.** Judge by the time to the result, counting set-up and transfer: a job goes to a server when that brings the result sooner, and only what the server speeds up is moved. The user's example of a job long enough to move, an example and not a threshold: 「比方说3个小时以上」. When throughput is unknown, time a few representative steps first. Prove the job on a small run before the full one; where the local machine cannot run it, the small run is on the server too.

**Reaching the host.**

- Connect by the SSH alias and nothing else. The alias carries the login, and logins change while aliases stay: 「servers.md，我觉得不应该记用户名，因为可能会变，但是我的ssh别名不会变」. Keep user names out of documents and scripts; when a command needs the name, read it at that moment (`ssh <alias> id -un`).
- A failed check of a host or a service is not yet a fact about it: it is retried (three tries at most, as the common block says) before "the host is down" is reported. One short timeout was once reported as "the host is offline": 「为什么你说连不上网，我可以用啊」.

**Where things go on the host.**

- Each host has one storage root that is the home of all the user's projects there; a project keeps its files in `<storage-root>/<project>/`, one directory per experiment line under it (`<storage-root>/<project>/<the experiment's directory name>/`) beside what its runs share (the data, an environment several runs use), and nothing in the login's home or in system paths. A host with no storage root on record: ask before creating anything.
- **Use the caches that are there; create none** (the common block's guardrail). The storage root's environment (where it has an `env.sh`, source it before each command, `ssh <alias> '. <storage-root>/env.sh && …'`, since a non-interactive ssh loads no shell profile) points uv, Hugging Face and the compile caches at one shared place, so every project downloads once. How such a root is set up is in the vllm-serve skill's reference on shared machines. A cache directory made inside one project was the mistake each time: 「这里有，为什么新建」; 「直接用默认的uv缓存路径就好了，而且会快一点，有缓存」; 「我用共享的服务器都是放在某个路径的.tmp下的，我希望对我这台机器上的所有的项目都共享」. The same holds on the local machine (「为什么你要另起炉灶搞一套？」).
- Keep the tools' defaults and set a variable only for a real special case: 「保持默认的不可以吗，如果要有特殊，单独设置不就好了」. A changed default is one more thing to rule out when something breaks.
- Nothing on a shared server carries the user's identity: 「记得不要出现我的信息」. That covers paths and file contents and the git author, so no `.git/` directory is sent (the project's, or that of an upstream copy) and nothing is sent that the run does not need; after each transfer, search what was sent, file names and file contents, for the user's identifiers (their name, their login names, their email address), and read the search's output to its last line.
- **Installing.** The common block's guardrail on installs leaves the training server to this document. The rule here: a tool the work needs is installed in user space under the storage root, with the tool's own installer (uv from its install script: 「需要用curl -LsSf https://astral.sh/uv/install.sh | sh」), and environments are built in place there: this is part of running on the server and needs no yes. A system package, or anything that needs sudo, is never installed on a server. A step that does need root (the ownership of a directory after a login change, for example) is the user's to run: write the exact commands, they run them in their own root terminal, and you verify the result. 「你可以告诉我命令，我来帮你，我这边自己终端登录的是root」.

**GPUs.** Read `nvidia-smi` (with the process owners) before every start. Other people's jobs come first, and so do the user's jobs from other projects: take idle GPUs and leave every process you did not start. A GPU between two runs of its owner's job looks idle for a moment, so sample it a few times a minute apart. Sharing a busy GPU is the user's call for that run, and they may withdraw it: 「就直接用两张卡吧，竞争」, later 「卡1空出来了，只用卡1，腾出卡0，不要竞争了」.

**Launching.** Say what runs, where and for how long, as the common block asks. Start it detached, so that it outlives the session, with its log in a file. What the run needs to keep going (a driver script, a queue file) lives in the project or under the storage root (the common block's guardrail on files a later step needs): a session restart once deleted the driver of a running campaign. Write the set-up down as it happens (the exact commands, the lock file, the GPU, where outputs go), in the experiment's README or run record, so that the run can be started again from the notes. A batch that will run with nobody watching confirms that what it depends on really answers before it dispatches, and carries a written stop rule (an invented example: stop everything when two of the first ten units fail).

**Watching.** A long job is watched in the background, about once an hour, and only problems are reported; the foreground stays on the main line. 「监控不要放在前台，放在后台好了，前台我们有主线的研究开发任务。」; 「你后台每个小时检查一次好了。如果有问题的话，向我汇报。」 A problem is whatever changes what the user or you would do: the job died, the loss is NaN or diverging, nothing has advanced since the last check, the disk is filling, someone else's job has taken the card. It is raised as the common block says of an anomaly in a run: at once, with a proposed handling.

**Fetching back, checking, cleaning.** When the job ends, in this order:

1. **Fetch** everything needed back to the local machine in one go: code changes, configs, logs, outputs, weights, into the experiment's directory in the project. 「所有在外部服务器上训练的，训练完毕后都要及时取回本机，代码、权重等包括所有内容，因为训练服务器不是我一个人在用，而且硬盘上的文件会被定期清除」. The project is the one home: 「因为我们主项目都是在这边，就不要有太多的衍生物或者分叉版本，这样的话管起来非常糟糕。训练完毕后，全部内容就取回我们这个项目目录，然后整理归档记录好」.
2. **Check** it locally: checksums of the weights against the remote, and a local run that shows the result works (an inference, an evaluation step). A matching size or an exit code of 0 is not the check.
3. **Clean** the server, as a separate step after the check: 「确定所有内容都保存在本地且能推理后，再清除训练服务器上的内容」. Remove what this run put there (its own directory under the project's, its processes) and nothing else. What other runs of the project still use (the data, a shared environment, another run's directory) stays until the last of them is fetched and checked; `<storage-root>/<project>/` itself goes only when no row of `docs/servers.md` names anything in it. A project still in development may say in its own file that it keeps data, weights and environments on the server for the coming experiments (「我们这个项目由于还在开发阶段，后面还有逐渐改动，新增…只需要及时取回本机就可以了。记住。」); fetching and checking happen all the same, since the local copy is the real one.

Done when the local check has passed, the project's `docs/servers.md` shows what is still on the host (or the row is gone), and the experiment's run record has its final status.

**The project's `docs/servers.md`**, in this form:

```markdown
## Hosts

| Alias | Storage root | Hardware | Network and tools | Notes |
|---|---|---|---|---|
| `<alias>` | `<storage-root>` (user, <date>: 「<原话>」) | <GPUs, memory, cores> | <what is reachable and how fast, which tools are installed> (<date>) | <who else uses it, which GPUs are usually busy, free disk> (<date>) |

## What lives on the hosts

| Host | Directory | What it is |
|---|---|---|
| `<alias>` | `<storage-root>/<project>/20261015-seg-finetune/` | run 20261016-2140: code, env, outputs (until fetched and checked) |
```

A row is added to the second table when a run or a deployment first creates something on a host, and removed when it has been fetched, checked and deleted. Entries about a host's state (free disk, speeds, which GPUs are usually busy) carry their date.

## What the project's own file holds

`docs/conventions/experiments.md` in the project, under the two headings the common block's *How a rule grows* works with, `## This project only` and `## To promote`; the entry format is in the records reference of this skill. Typically:

- the Python version and the framework build its hardware needs, with the reason;
- its data: where it lives, its versions, which cases are held out, what its honest limits are;
- its expert references, the domain definitions aligned to them, and how such a reference is read in its field;
- whether it keeps things on a server while in development (which servers are its training servers is in its `docs/servers.md`);
- facts about the local machine that bite when forgotten: where its SSH configuration comes from, its memory limit for heavy jobs, tools that differ from the usual.
