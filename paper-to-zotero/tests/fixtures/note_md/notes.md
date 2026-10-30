<!-- editor-saved paper note -->
---
schema: 9
---
# 论文笔记

一句话概括：用 3D U-Net 从 5 个平扫乳腺 MRI 序列合成增强 T1（**无需造影剂**），在 96 例外部测试中 *SSIM* 达到 $0.88$；代码见 `synth_t1.py`，论文见 [Chung 2023](zotero://select/library/items/46GUJFLD)。

## Q1 这篇论文试图解决什么问题？ [已答]

钆造影剂有肾源性系统纤维化风险，作者想用平扫序列直接预测增强后的 T1 图像（[p. 1](zotero://open-pdf/library/items/9QS63MA8?page=1)）。

第二段答案：问题被表述为图像到图像的回归，而不是分割。

**结论：**作者认为平扫序列已包含足够的增强信息。

## Q2 有哪些相关研究？ [已答]

- 基于 GAN 的方法
  - Pix2Pix：成对训练，**易产生伪影**
    - 三级嵌套：PatchGAN 判别器只看局部 $70\times70$ 块
  - CycleGAN：不需要成对数据
- 基于扩散模型的方法
  - DDPM 变体，推理慢

1. 先读方法部分
2. 再核对 Table 2

## Q3 论文如何解决这个问题？ [已答]

### Q3.1 推理时也要真值 mask 吗？ [论文没有说明]

论文只在训练时使用病灶 mask，推理阶段是否需要没有交代。

### Q3.2 损失函数是什么？ [已答]

前向加噪写作 $\hat{x}_0 = x_t - \epsilon_\theta(x_t, t)$，总损失为：

$$\mathcal{L} = \mathbb{E}\lVert \epsilon - \epsilon_\theta(x_t, t) \rVert_2^2$$

#### Q3.2.1 权重怎么选？ [论文没有说明]

只说"经验设定"，见 <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 6</span>)</span>。

## Q4 论文做了哪些实验？ [已答]

**结果**：96 例中 7 例病灶合成失败（[p. 6](zotero://open-pdf/library/items/9QS63MA8?page=6&annotation=ABCD1234)），差异显著（p<0.05）。

> "Seven of the 96 lesions were not synthesized, mostly those smaller than 5 mm."
>
> 96 个病灶中有 7 个未能合成，多数小于 5 mm。

| 指标 | 值 | 备注 |
| --- | --- | --- |
| SSIM | 0.88 | 越高越好 |
| PSNR | 28.1 dB | `dB` 为单位 |

## 待办

- [ ] 复现 Table 2 的 SSIM
- [x] 读完方法部分

## 用在哪里

- project-a
  - 当作 基线方案的上限参考：notes/lit-review.md §2.3 · 2026-09

`inline code` 和 *斜体*，以及 <特殊字符> & "引号"，DOI 见 [https://doi.org/10.1148/radiol.2023220000](https://doi.org/10.1148/radiol.2023220000)。

<!-- Better Notes import -->
---
schema: 9
---
# 论文笔记

一句话概括：用 3D U-Net 从 5 个平扫乳腺 MRI 序列合成增强 T1（**无需造影剂**），在 96 例外部测试中 *SSIM* 达到 $0.88$；代码见 `synth_t1.py`，论文见 [Chung 2023](zotero://select/library/items/46GUJFLD)。

## Q1 这篇论文试图解决什么问题？ [已答]

钆造影剂有肾源性系统纤维化风险，作者想用平扫序列直接预测增强后的 T1 图像（[p. 1](zotero://open-pdf/library/items/9QS63MA8?page=1)）。

第二段答案：问题被表述为图像到图像的回归，而不是分割。

**结论：**作者认为平扫序列已包含足够的增强信息。

## Q2 有哪些相关研究？ [已答]

- <span>基于 GAN 的方法</span>
  - <span>Pix2Pix：成对训练，</span>**易产生伪影**
    - <span>三级嵌套：PatchGAN 判别器只看局部</span>$70\times70$<span>块</span>
  - <span>CycleGAN：不需要成对数据</span>
- <span>基于扩散模型的方法</span>
  - <span>DDPM 变体，推理慢</span>

1. <span>先读方法部分</span>
2. <span>再核对 Table 2</span>

## Q3 论文如何解决这个问题？ [已答]

### Q3.1 推理时也要真值 mask 吗？ [论文没有说明]

论文只在训练时使用病灶 mask，推理阶段是否需要没有交代。

### Q3.2 损失函数是什么？ [已答]

前向加噪写作 $\hat{x}_0 = x_t - \epsilon_\theta(x_t, t)$，总损失为：

$$\mathcal{L} = \mathbb{E}\lVert \epsilon - \epsilon_\theta(x_t, t) \rVert_2^2$$

#### Q3.2.1 权重怎么选？ [论文没有说明]

只说"经验设定"，见 <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 6</span>)</span>。

## Q4 论文做了哪些实验？ [已答]

**结果**：96 例中 7 例病灶合成失败（[p. 6](zotero://open-pdf/library/items/9QS63MA8?page=6&annotation=ABCD1234)），差异显著（p<0.05）。

> "Seven of the 96 lesions were not synthesized, mostly those smaller than 5 mm."
>
> 96 个病灶中有 7 个未能合成，多数小于 5 mm。

| 指标 | 值 | 备注 |
| --- | --- | --- |
| <span>SSIM</span> | <span>0.88</span> | <span>越高越好</span> |
| <span>PSNR</span> | <span>28.1 dB</span> | `dB`<span>为单位</span> |

## 待办

<ul class="contains-task-list">
<li class="task-list-item">[ ] <span> </span><span>复现 Table 2 的 SSIM</span></li>
<li class="task-list-item">[x] <span> </span><span>读完方法部分</span></li>
</ul>

## 用在哪里

- <span>project-a</span>
  - <span>当作 基线方案的上限参考：notes/lit-review.md §2.3 · 2026-09</span>

`inline code` 和 *斜体*，以及 <特殊字符> & "引号"，DOI 见 [https://doi.org/10.1148/radiol.2023220000](https://doi.org/10.1148/radiol.2023220000)。

<!-- plain HTML, never saved -->
# 论文笔记

一句话概括：用 3D U-Net 从 5 个平扫乳腺 MRI 序列合成增强 T1（<strong>无需造影剂</strong>），在 96 例外部测试中 <em>SSIM</em> 达到 <span class="math">\$0.88\$</span>；代码见 <code>synth_t1.py</code>，论文见 <a href="zotero://select/library/items/46GUJFLD" target="_blank">Chung 2023</a>。

## Q1 这篇论文试图解决什么问题？ [已答]

钆造影剂有肾源性系统纤维化风险，作者想用平扫序列直接预测增强后的 T1 图像（[p. 1](zotero://open-pdf/library/items/9QS63MA8?page=1)）。

第二段答案：问题被表述为图像到图像的回归，而不是分割。

**结论：**作者认为平扫序列已包含足够的增强信息。

## Q2 有哪些相关研究？ [已答]

- 基于 GAN 的方法
  - Pix2Pix：成对训练，**易产生伪影**
    - 三级嵌套：PatchGAN 判别器只看局部 $70\times70$ 块
  - CycleGAN：不需要成对数据
- 基于扩散模型的方法
  - DDPM 变体，推理慢

1. 先读方法部分
2. 再核对 Table 2

## Q3 论文如何解决这个问题？ [已答]

### Q3.1 推理时也要真值 mask 吗？ [论文没有说明]

论文只在训练时使用病灶 mask，推理阶段是否需要没有交代。

### Q3.2 损失函数是什么？ [已答]

前向加噪写作 $\hat{x}_0 = x_t - \epsilon_\theta(x_t, t)$，总损失为：

$$
\mathcal{L} = \mathbb{E}\lVert \epsilon - \epsilon_\theta(x_t, t) \rVert_2^2
$$

#### Q3.2.1 权重怎么选？ [论文没有说明]

只说"经验设定"，见 <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 6</span>)</span>。

## Q4 论文做了哪些实验？ [已答]

**结果**：96 例中 7 例病灶合成失败（[p. 6](zotero://open-pdf/library/items/9QS63MA8?page=6&annotation=ABCD1234)），差异显著（p<0.05）。

> "Seven of the 96 lesions were not synthesized, mostly those smaller than 5 mm."
>
> 96 个病灶中有 7 个未能合成，多数小于 5 mm。

<table>
<thead>
<tr><th style="text-align: left">指标</th><th>值</th><th>备注</th></tr>
</thead>
<tbody>
<tr><td>SSIM</td><td>0.88</td><td>越高越好</td></tr>
<tr><td>PSNR</td><td>28.1 dB</td><td><code>dB</code> 为单位</td></tr>
</tbody>
</table>

## 待办

- [ ] 复现 Table 2 的 SSIM
- [x] 读完方法部分

## 用在哪里

- project-a
  - 当作 基线方案的上限参考：notes/lit-review.md §2.3 · 2026-09

`inline code` 和 *斜体*，以及 <特殊字符> & "引号"，DOI 见 [https://doi.org/10.1148/radiol.2023220000](https://doi.org/10.1148/radiol.2023220000)。

<!-- raw HTML sent, unsaved -->
# 论文笔记

一句话概括：用 3D U-Net 从 5 个平扫乳腺 MRI 序列合成增强 T1（**无需造影剂**），在 96 例外部测试中 *SSIM* 达到 $0.88$；代码见 `synth_t1.py`，论文见 [Chung 2023](zotero://select/library/items/46GUJFLD)。

## Q1 这篇论文试图解决什么问题？ [已答]

钆造影剂有肾源性系统纤维化风险，作者想用平扫序列直接预测增强后的 T1 图像（[p. 1](zotero://open-pdf/library/items/9QS63MA8?page=1)）。

第二段答案：问题被表述为图像到图像的回归，而不是分割。

**结论：**作者认为平扫序列已包含足够的增强信息。

## Q2 有哪些相关研究？ [已答]

- 基于 GAN 的方法
  - Pix2Pix：成对训练，**易产生伪影**
    - 三级嵌套：PatchGAN 判别器只看局部 $70\times70$ 块
  - CycleGAN：不需要成对数据
- 基于扩散模型的方法
  - DDPM 变体，推理慢

1. 先读方法部分
2. 再核对 Table 2

## Q3 论文如何解决这个问题？ [已答]

### Q3.1 推理时也要真值 mask 吗？ [论文没有说明]

论文只在训练时使用病灶 mask，推理阶段是否需要没有交代。

### Q3.2 损失函数是什么？ [已答]

前向加噪写作 $\hat{x}_0 = x_t - \epsilon_\theta(x_t, t)$，总损失为：

$$\mathcal{L} = \mathbb{E}\lVert \epsilon - \epsilon_\theta(x_t, t) \rVert_2^2$$

#### Q3.2.1 权重怎么选？ [论文没有说明]

只说"经验设定"，见 <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 6</span>)</span>。

## Q4 论文做了哪些实验？ [已答]

**结果**：96 例中 7 例病灶合成失败（[p. 6](zotero://open-pdf/library/items/9QS63MA8?page=6&annotation=ABCD1234)），差异显著（p<0.05）。

> "Seven of the 96 lesions were not synthesized, mostly those smaller than 5 mm."
>
> 96 个病灶中有 7 个未能合成，多数小于 5 mm。

| 指标 | 值 | 备注 |
| --- | --- | --- |
| SSIM | 0.88 | 越高越好 |
| PSNR | 28.1 dB | `dB` 为单位 |

## 待办

- [ ] 复现 Table 2 的 SSIM
- [x] 读完方法部分

## 用在哪里

- project-a
  - 当作 基线方案的上限参考：notes/lit-review.md §2.3 · 2026-09

`inline code` 和 *斜体*，以及 <特殊字符> & "引号"，DOI 见 [https://doi.org/10.1148/radiol.2023220000](https://doi.org/10.1148/radiol.2023220000)。

<!-- edited by the user -->
---
schema: 9
---
# 论文笔记

一句话概括：用 3D U-Net 从 5 个平扫乳腺 MRI 序列合成增强 T1（**无需造影剂**），在 96 例外部测试中 *SSIM* 达到 $0.88$；代码见 `synth_t1.py`，论文见 [Chung 2023](zotero://select/library/items/46GUJFLD)。

## Q1 这篇论文试图解决什么问题？ [已答]

钆造影剂有肾源性系统纤维化风险，作者想用平扫序列直接预测增强后的 T1 图像（[p. 1](zotero://open-pdf/library/items/9QS63MA8?page=1)）。

第二段答案：问题被表述为<span style="color: #ff2020">图像到图像的回归</span>，而不是<span style="background-color: #ffd40080">分割</span>。

**结论：**作者认为平扫序列已包含足够的增强信息。

## Q2 有哪些相关研究？ [已答]

- 基于 GAN 的方法
  - Pix2Pix：成对训练，**易产生伪影**
    - 三级嵌套：PatchGAN 判别器只看局部 $70\times70$ 块
  - CycleGAN：不需要成对数据
- 基于扩散模型的方法
  - DDPM 变体，推理慢

1. 先读方法部分
2. 再核对 Table 2

## Q3 论文如何解决这个问题？ [已答]

### Q3.1 推理时也要真值 mask 吗？ [论文没有说明]

论文只在训练时使用病灶 mask，推理阶段是否需要没有交代。

<p style="padding-left: 40px" data-indent="1">我缩进的一段：<strong>推理时</strong>或许不需要。</p>

### Q3.2 损失函数是什么？ [已答]

前向加噪写作 $\hat{x}_0 = x_t - \epsilon_\theta(x_t, t)$，总损失为：

$$\mathcal{L} = \mathbb{E}\lVert \epsilon - \epsilon_\theta(x_t, t) \rVert_2^2$$

#### Q3.2.1 权重怎么选？ [论文没有说明]

只说"经验设定"，见 <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 6</span>)</span>。

## Q4 论文做了哪些实验？ [已答]

**结果**：96 例中 7 例病灶合成失败（[p. 6](zotero://open-pdf/library/items/9QS63MA8?page=6&annotation=ABCD1234)），差异显著（p<0.05）。

> "Seven of the 96 lesions were not synthesized, mostly those smaller than 5 mm."
>
> 96 个病灶中有 7 个未能合成，多数小于 5 mm。

<span class="highlight" data-annotation="%7B%22attachmentURI%22%3A%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F9QS63MA8%22%2C%22annotationKey%22%3A%22ABCD1234%22%2C%22color%22%3A%22%23ffd400%22%2C%22pageLabel%22%3A%226%22%2C%22position%22%3A%7B%22pageIndex%22%3A5%2C%22rects%22%3A%5B%5B72%2C400%2C300%2C412%5D%5D%7D%7D">“Seven of the 96 lesions were not synthesized”</span> <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 6</span>)</span>

| 指标 | 值 | 备注 |
| --- | --- | --- |
| SSIM | 0.88 | 越高越好 |
| PSNR | 28.1 dB | `dB` 为单位 |

## 待办

- [ ] 复现 Table 2 的 SSIM
- [x] 读完方法部分

## 用在哪里

- project-a
  - 当作 基线方案的上限参考：notes/lit-review.md §2.3 · 2026-09

`inline code` 和 *斜体*，以及 <特殊字符> & "引号"，DOI 见 [https://doi.org/10.1148/radiol.2023220000](https://doi.org/10.1148/radiol.2023220000)。

<!-- test note as sent -->
# 论文笔记（测试，可删）

一句话概括：用 3D U-Net 从 5 个平扫乳腺 MRI 序列合成增强 T1；96 例中 7 例病灶合成失败。

## 问题树

- Q1 这篇论文试图解决什么问题？ [已答]
- Q3 论文如何解决这个问题？ [已答]
  - Q3.1 推理时也要真值 mask 吗？ [论文没有说明]

## Q4 论文做了哪些实验？

**结果**：96 例中 7 例病灶合成失败（[p. 6](zotero://open-pdf/library/items/9QS63MA8?page=6)），论文见 [Chung 2023](zotero://select/library/items/46GUJFLD)。

> "placeholder original sentence for this test"（原文，测试占位）
>
> 测试用的占位译文

| 指标 | 值 |
| --- | --- |
| SSIM | 0.88 |

## 用在哪里

- project-a
  - 当作 基线方案的上限参考：测试 · notes/lit-review.md §2.3 · 2026-09

`inline code` 和 *斜体*，以及 <特殊字符> & "引号"

<!-- test note after the user's edit -->
---
schema: 9
---
# 论文笔记（测试，可删）

一句话概括：用 3D U-Net 从 5 个平扫乳腺 MRI 序列合成增强 T1；96 例中 7 例病灶合成失败。

## 问题树

- Q1 这篇论文试图解决什么问题？ [已答]
- Q3 论文如何解决这个问题？ [已答]
  - Q3.1 推理时也要真值 mask 吗？ [论文没有说明]

## Q4 论文做了哪些实验？

**结果**：96 例中 7 例病灶合成失败（[p. 6](zotero://open-pdf/library/items/9QS63MA8?page=6)），论文见 [Chung 2023](zotero://select/library/items/46GUJFLD)。

> "placeholder original sentence for this test"（原文，测试占位）
>
> 测试用的占位译文

| 指标 | 值 |
| --- | --- |
| SSIM | 0.88 |

## 用在哪里

- project-a
  - 当作 基线方案的上限参考：测试 · notes/lit-review.md §2.3 · 2026-09

`inline code` 和 *斜体*，以及 <特殊字符> & "引号"

<p></p>

- [ ] 这是我加的
