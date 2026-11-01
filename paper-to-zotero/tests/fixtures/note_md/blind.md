<!-- hard break then block markers -->
---
schema: 9
---
第一行\
\- 像列表\
\# 像标题\
\> 像引用\
1\. 像有序列表\
\+ 像加号列表\
\===

<!-- paragraph-start markers, set 2 -->
---
schema: 9
---
\+ 加号开头

\* 星号开头

1\) 括号编号

\---

\*\*\*

\`\`\`不是代码块

\[1]: https://doi.org/10.1000/xyz

<!-- text that looks like HTML or autolinks -->
---
schema: 9
---
标签 \<div>块\</div> 与 \<br>

\<!-- 不是注释 -->

见 \<https://example.com> 或 \<a@b.com>

\<div class="x">行首的标签

若 a\<b and c>d，则 p < 0.05

<!-- heading closing hashes and literal stars -->
---
schema: 9
---
## C# 与 F# \#

### #标签 开头

## 1. 引言

#### Q2.1 是否需要 \*预训练\*？ 【已答】

##### 五级标题 [论文没有说明]

###### 六级 \###

<!-- list item text that looks like block syntax -->
---
schema: 9
---
- 2024\. 年度总结
- \- 破折号开头
- \# 不是标题
- \> 不是引用
- \+ 不是子项
- \---
- 1\) 括号编号

1. 1\. 已带编号的文本

<!-- quote text that looks like syntax -->
---
schema: 9
---
> \> 看起来像嵌套引用
>
> \- 看起来像列表
>
> \## 看起来像标题

<!-- literal dollars near math -->
---
schema: 9
---
预算 \$5，公式 $x+1$，再加 \$10。

\$\$ 不是公式 \$\$

价格$p$与 US\$ 汇率

<!-- math next to digits -->
---
schema: 9
---
网格大小为 3$\times$3，误差 $<5\%$。

<!-- math content with lt, amp and pipes -->
---
schema: 9
---
条件 $a < b \;\&\; |c| > d$ 成立

$$\begin{aligned}
f(x) &= |x| \\
g(x) &= x_1 * x_2
\end{aligned}$$

<!-- backslashes before breaks and at ends -->
---
schema: 9
---
目录 C:\temp\\\
下一行

行尾反斜杠\\

转义样子 \\\* 与 \\\_ 与 \\\ 与 \\\`

<!-- CJK punctuation at bold edges -->
---
schema: 9
---
这是**「重点」**内容，**（括号）**后文，*《书名》*之后。

<!-- adjacent and overlapping bold and italic -->
---
schema: 9
---
**粗**_斜_相邻；交叠：**粗_粗斜_**_斜_。

<!-- space at the inner edge of a mark -->
---
schema: 9
---
注意<strong>重点 </strong>后文，前文<em> 斜体</em>收尾。

<!-- bold covering part of a link -->
---
schema: 9
---
见 [原文 **第 3 节** 附录](https://example.com/paper)。

<!-- colour, background and link nesting -->
---
schema: 9
---
<span style="color: #05a2ef">[蓝色链接](https://example.com)</span>，**<span style="color: #ff2020">红色粗体</span>**，**<span style="background-color: #ffd40080">[高亮粗体链接](zotero://select/library/items/46GUJFLD)</span>**

<span style="color: rgb(255, 32, 32)">重存后的红色</span>与<span style="background-color: rgba(255, 212, 0, 0.5)">黄色背景</span>

<!-- colour span split by partial bold -->
---
schema: 9
---
**<span style="color: #ff2020">红色加粗</span>**<span style="color: #ff2020">只红色</span>普通

<!-- underline, strike, sub, sup with inner marks -->
---
schema: 9
---
***<u>粗斜下划线</u>***，*<span style="text-decoration: line-through">斜体删除</span>*，<u style="text-decoration-color: #ff2020;">红色下划线</u>，H<sub>2</sub>O 与 E=mc<sup>2</sup>

<!-- emphasis between a letter and inline HTML -->
---
schema: 9
---
下标 x<em><sub>i</sub></em> 与 这是<strong><span style="color: #ff2020">红色粗体</span></strong>的文字

<!-- marks across hard breaks -->
---
schema: 9
---
**第一行\
第二行**，*斜体行尾*\
下一行

<!-- code spans with backticks and spaces -->
---
schema: 9
---
反引号 ``a`b``、包裹 `` `x` ``、前后空格 `x `、路径 `C:\temp\`、标签 `<div> &&`、变量 `$HOME`

<!-- link destinations and titles -->
---
schema: 9
---
[带标题](https://example.com/?a=1&b=2 "他说 \"好\"")、[括号网址](https://en.wikipedia.org/wiki/Mean_(statistics))、[不配对括号](<https://example.com/a(b>)、[[1]](zotero://open-pdf/library/items/9QS63MA8?page=6&annotation=ABCD1234)、[特殊_字符\*文本](https://example.com/x_y*z)

<!-- links markdown-it cannot write -->
---
schema: 9
---
[中文网址](https://zh.wikipedia.org/wiki/均值)、[本地 PDF](file:///D:/Papers/chung2023.pdf)、[带空格的网址](<https://example.com/a b>)

<!-- typed double spaces and nbsp -->
---
schema: 9
---
两个 &nbsp;空格，三个 &nbsp; 空格，行尾 &nbsp;

&nbsp;开头两个空格

代码 `a  b` 与粘贴来的&nbsp;不换行空格

<!-- code block with nbsp indentation and a tab -->
---
schema: 9
---
```
def f(x):
    if x:  # 两个空格
        return 1

	return 0
```

<!-- code block containing a fence -->
---
schema: 9
---
````
```python
print("hi")
```
````

<!-- code block with bold inside -->
---
schema: 9
---
<pre>x = compute(a, b)
<strong>y = x * 2</strong> &nbsp;# 关键行</pre>

<!-- entity-like text -->
---
schema: 9
---
字面实体 \&nbsp; \&#123; &copy 与 AT&T，引号 "直" 与 “弯”

<!-- hard breaks at the edges -->
---
schema: 9
---
结尾换行<br>

<br>开头换行

连续\
\
两次

<br>

<!-- hard breaks in heading, item and cell -->
---
schema: 9
---
## 标题第一行<br>标题第二行

- 项第一行\
  项第二行
- 有子项\
  的项
  - 子项

| 列 |
| --- |
| 格第一行<br>格第二行 |

<!-- ordered list with wide markers -->
---
schema: 9
---
9. 第九项
   - 子项甲
10. 第十项
    - 子项乙

<!-- four-level mixed nesting with start numbers -->
---
schema: 9
---
- 一级

  3. 二级第三
     - 三级
       1. 四级一
       2. 四级二
  4. 二级第四

<!-- items with several blocks -->
---
schema: 9
---
- 第一段

  第二段
  - 子项

  子列表之后的段落
- 带代码的项
  ```
  x = 1
  ```
- 带公式的项
  $$E=mc^2$$
- 带引文的项
  > 引文内容

<!-- item whose first block is not a paragraph -->
---
schema: 9
---
- - 只有子列表的项
- ### 项里的标题
- > 项里只有引文
- ```
  只有代码
  ```

<!-- empty items and an empty to-do -->
---
schema: 9
---
- 有内容
-
- [ ]

1.
2. 二

<!-- to-do lookalikes -->
---
schema: 9
---
- [x] **已完成**的任务
- [X] 大写 X
- [ ]无空格
- [ ] 父任务
  - [x] 子任务

1. [ ] 有序列表里的方框

[x] 段落开头的方框

<!-- two ordered lists in a row -->
---
schema: 9
---
1. 甲

2) 乙

<!-- hr inside an item, then a list of the other type -->
---
schema: 9
---
- 分隔线之前
  ***

  分隔线之后

1. 紧接着的有序列表

<!-- quote in list in quote -->
---
schema: 9
---
> 外层引文
>
> 5. 第五条
>    > 条目里的引文
>    > - 引文里的列表

<!-- two quotes in a row and a nested quote -->
---
schema: 9
---
> 第一段引文

> 第二段引文
> > 嵌套引文
>
> 回到外层

<!-- empty quote, heading and code block -->
---
schema: 9
---
>

##

```
```

后文

<!-- table cells with formatting, math and empty cells -->
---
schema: 9
---
| **指标** |  | 公式 |
| --- | --- | --- |
| *SSIM* `ssim()` |  | $\frac{a}{b}$ |
| [p. 6](zotero://open-pdf/library/items/9QS63MA8?page=6) | <span style="color: #ff2020">红</span> | p < 0.05 |

<!-- pipes and backslashes in cells -->
---
schema: 9
---
| 写法 | 含义 |
| --- | --- |
| `a\|b` | $\|x\|$ 的绝对值 |
| [链接\|文本](https://example.com) | C:\temp\\ |
| - 不是列表 | # 不是标题 |

<!-- header-only and single-column tables -->
---
schema: 9
---
| 只有表头 | 第二列 |
| --- | --- |

| 单列 |
| --- |
| 甲 |

<!-- table with a list and display math in cells -->
---
schema: 9
---
<table>
<tbody>
<tr>
<th>
<p>方法</p>
</th>
<th>
<p>要点</p>
</th>
</tr>
<tr>
<td>
<p>GAN</p>
</td>
<td>
<p>两点：</p>
<ul>
<li>
成对训练
</li>
<li>
易产生伪影
</li>
</ul>
</td>
</tr>
<tr>
<td>
<p>扩散</p>
</td>
<td>
<pre class="math">$$x_{t-1}=f(x_t)$$</pre>
</td>
</tr>
</tbody>
</table>

<!-- merged and coloured cells -->
---
schema: 9
---
<table>
<tbody>
<tr>
<th colspan="2">
<p>合并表头</p>
</th>
</tr>
<tr>
<td style="background-color: rgba(255, 212, 0, 0.5);">
<p>黄底</p>
</td>
<td>
<p>普通</p>
</td>
</tr>
</tbody>
</table>

<!-- header column instead of header row -->
---
schema: 9
---
<table>
<tbody>
<tr>
<th>
<p>项目</p>
</th>
<td>
<p>值</p>
</td>
</tr>
<tr>
<th>
<p>SSIM</p>
</th>
<td>
<p>0.88</p>
</td>
</tr>
</tbody>
</table>

<!-- tables in a quote and a list item -->
---
schema: 9
---
> 引文中的表：
>
> | a | b |
> | --- | --- |
> | 1 | 2 |

- 列表中的表：

  | x |
  | --- |
  | 3 |

<!-- Zotero objects in table cells -->
---
schema: 9
---
| 来源 | 摘录 |
| --- | --- |
| <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 6</span>)</span> | <span class="highlight" data-annotation="%7B%22attachmentURI%22%3A%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F9QS63MA8%22%2C%22annotationKey%22%3A%22HL5A7B2C%22%2C%22color%22%3A%22%23ffd400%22%2C%22pageLabel%22%3A%226%22%2C%22position%22%3A%7B%22pageIndex%22%3A5%2C%22rects%22%3A%5B%5B72.024%2C400.11%2C300.2%2C412.3%5D%5D%7D%2C%22citationItem%22%3A%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%7D">“Seven of the 96 lesions \| were not synthesized”</span> |
| <img alt="" width="240" height="135" data-attachment-key="IMGK3Y7Q" data-annotation="%7B%22attachmentURI%22%3A%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F9QS63MA8%22%2C%22annotationKey%22%3A%22IMGK3Y7Q%22%2C%22color%22%3A%22%23ffd400%22%2C%22pageLabel%22%3A%224%22%2C%22position%22%3A%7B%22pageIndex%22%3A3%2C%22rects%22%3A%5B%5B55.4%2C312.7%2C540.1%2C620.9%5D%5D%7D%2C%22citationItem%22%3A%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%224%22%7D%7D"> | [相关笔记](zotero://note/u/NT4KX9QA/) |

<!-- annotation paragraph: highlight, citation, comment -->
---
schema: 9
---
<span class="highlight" data-annotation="%7B%22attachmentURI%22%3A%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F9QS63MA8%22%2C%22annotationKey%22%3A%22HL5A7B2C%22%2C%22color%22%3A%22%23ffd400%22%2C%22pageLabel%22%3A%226%22%2C%22position%22%3A%7B%22pageIndex%22%3A5%2C%22rects%22%3A%5B%5B72.024%2C400.11%2C300.2%2C412.3%5D%5D%7D%2C%22citationItem%22%3A%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%7D">“Seven of the 96 lesions were not synthesized, mostly those smaller than 5 mm.”</span> <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 6</span>)</span> 小病灶是失败主因，\*需要\*复核。

<!-- highlight with marks and special characters inside -->
---
schema: 9
---
<span class="highlight" data-annotation="%7B%22attachmentURI%22%3A%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F9QS63MA8%22%2C%22annotationKey%22%3A%22HL9C3D4E%22%2C%22color%22%3A%22%23ff6666%22%2C%22pageLabel%22%3A%225%22%2C%22position%22%3A%7B%22pageIndex%22%3A4%2C%22rects%22%3A%5B%5B56.7%2C210.4%2C288.9%2C221.6%5D%2C%5B56.7%2C198.2%2C140.3%2C209.4%5D%5D%7D%2C%22citationItem%22%3A%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%225%22%7D%7D">“the **p**-value was <0.05 for n_1 * n_2 [12], costing \$5”</span>

<!-- multi-item citation in a heading and before a full stop -->
---
schema: 9
---
## 相关工作 <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%2C%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F7KQ2MZ3X%22%5D%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 6</span>; <span class="citation-item">Kim, 2021</span>)</span>

两项研究都用了成对数据<span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F7KQ2MZ3X%22%5D%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Kim, 2021</span>)</span>。

<!-- citation and note links in list items -->
---
schema: 9
---
- 见 <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 6</span>)</span>
- 笔记链接 [方法对比](zotero://note/u/NT4KX9QA/)
  - **[群组笔记第 12 行](zotero://note/g/2468135/GRPN0TE1/?line=12)**

<!-- underline annotation (schema 10) -->
---
schema: 10
---
<span class="underline" data-annotation="%7B%22attachmentURI%22%3A%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F9QS63MA8%22%2C%22annotationKey%22%3A%22UL2B6N8M%22%2C%22color%22%3A%22%232ea8e5%22%2C%22pageLabel%22%3A%227%22%2C%22position%22%3A%7B%22pageIndex%22%3A6%2C%22rects%22%3A%5B%5B72.3%2C350.6%2C301.4%2C361.8%5D%5D%7D%2C%22citationItem%22%3A%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%227%22%7D%7D">“diffusion models are slow at inference”</span> <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%227%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 7</span>)</span>

<!-- image annotation, break, citation -->
---
schema: 9
---
<img alt="" width="486" height="275" data-attachment-key="IMGK3Y7Q" data-annotation="%7B%22attachmentURI%22%3A%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F9QS63MA8%22%2C%22annotationKey%22%3A%22IMGK3Y7Q%22%2C%22color%22%3A%22%23ffd400%22%2C%22pageLabel%22%3A%224%22%2C%22position%22%3A%7B%22pageIndex%22%3A3%2C%22rects%22%3A%5B%5B55.4%2C312.7%2C540.1%2C620.9%5D%5D%7D%2C%22citationItem%22%3A%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%224%22%7D%7D">\
<span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%224%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 4</span>)</span> 图 2：合成结果对比

- <img alt="" data-attachment-key="IMGP8W2E">

<!-- wrapper with citation metadata -->
---
schema: 9
citation-items: %5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22itemData%22%3A%7B%22id%22%3A%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%2C%22type%22%3A%22article-journal%22%2C%22title%22%3A%22Synthesizing%20contrast-enhanced%20breast%20MRI%20from%20non-contrast%20sequences%22%2C%22container-title%22%3A%22Radiology%22%2C%22author%22%3A%5B%7B%22family%22%3A%22Chung%22%2C%22given%22%3A%22Minji%22%7D%2C%7B%22family%22%3A%22Lee%22%2C%22given%22%3A%22Sora%22%7D%5D%2C%22issued%22%3A%7B%22date-parts%22%3A%5B%5B%222023%22%5D%5D%7D%7D%7D%5D
---
## 摘录

<span class="highlight" data-annotation="%7B%22attachmentURI%22%3A%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F9QS63MA8%22%2C%22annotationKey%22%3A%22HL5A7B2C%22%2C%22color%22%3A%22%23ffd400%22%2C%22pageLabel%22%3A%226%22%2C%22position%22%3A%7B%22pageIndex%22%3A5%2C%22rects%22%3A%5B%5B72.024%2C400.11%2C300.2%2C412.3%5D%5D%7D%2C%22citationItem%22%3A%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%7D">“Seven of the 96 lesions were not synthesized”</span> <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 6</span>)</span>

<!-- highlight in a quote and a list item -->
---
schema: 9
---
> <span class="highlight" data-annotation="%7B%22attachmentURI%22%3A%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F9QS63MA8%22%2C%22annotationKey%22%3A%22HLQ7R8S9%22%2C%22color%22%3A%22%235fb236%22%2C%22pageLabel%22%3A%226%22%2C%22position%22%3A%7B%22pageIndex%22%3A5%2C%22rects%22%3A%5B%5B310.5%2C500.2%2C420.8%2C511.4%5D%5D%7D%2C%22citationItem%22%3A%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%7D">“lesions smaller than 5 mm”</span>

- <span class="highlight" data-annotation="%7B%22attachmentURI%22%3A%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F9QS63MA8%22%2C%22annotationKey%22%3A%22HLQ7R8S9%22%2C%22color%22%3A%22%235fb236%22%2C%22pageLabel%22%3A%226%22%2C%22position%22%3A%7B%22pageIndex%22%3A5%2C%22rects%22%3A%5B%5B310.5%2C500.2%2C420.8%2C511.4%5D%5D%7D%2C%22citationItem%22%3A%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%7D">“lesions smaller than 5 mm”</span> 是关键限制

<!-- indented paragraphs and heading with marks -->
---
schema: 9
---
<p style="padding-left: 40px" data-indent="1">缩进一级：<strong>推理时</strong>不需要 mask，见 <a href="zotero://open-pdf/library/items/9QS63MA8?page=6" rel="noopener noreferrer nofollow">p. 6</a>。</p>

<p style="padding-left: 80px" data-indent="2">缩进两级，含 <span class="math">$x_1$</span> 与 *星号*</p>

<h3 style="padding-left: 40px" data-indent="1">缩进的标题 <code>code</code></h3>

<!-- aligned paragraphs and headings -->
---
schema: 9
---
<h2 style="text-align: center">居中标题 <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F7KQ2MZ3X%22%5D%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Kim, 2021</span>)</span></h2>

<p style="text-align: right">—— 右对齐的署名，<em>斜体</em></p>

<p style="text-align: center;padding-left: 40px" data-indent="1">居中且缩进</p>

<p style="text-align: justify">两端对齐的段落。</p>

<!-- direction and id attributes -->
---
schema: 9
---
<p dir="rtl">نص عربي قصير</p>

<p style="padding-right: 40px" dir="rtl" data-indent="1">فقرة مزاحة</p>

<h3 id="methods">带 id 的标题</h3>

<ul dir="rtl">
<li>
عنصر
</li>
</ul>

<!-- attribute blocks inside quote and list -->
---
schema: 9
---
> 普通引文
>
> <p style="padding-left: 40px" data-indent="1">引文里缩进的段落</p>

- <p style="text-align: center">列表项里居中的段落</p>

  - 子项

<!-- hr at the edges and after a heading -->
---
schema: 9
---
***

## 标题

***

段落

***

<!-- display math and code in a quote -->
---
schema: 9
---
> 公式：
> $$a^2+b^2=c^2$$
>
> ```
> print("引文中的代码")
> ```

<!-- heading with marks and a status marker -->
---
schema: 9
---
## **粗体标题** 与 *斜体* <span style="color: #ff2020">红色</span> 【已答】

<!-- realistic paper note, mixed -->
---
schema: 9
---
# Chung 2023 笔记

**一句话：**平扫序列合成增强 T1，*SSIM* 0.88 <span class="citation" data-citation="%7B%22citationItems%22%3A%5B%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%5D%2C%22properties%22%3A%7B%7D%7D">(<span class="citation-item">Chung et al., 2023, p. 6</span>)</span>。

## Q1 方法是否需要 mask？ 【论文没有说明】

- 训练：用病灶 mask 加权损失 $\lambda=0.5$
  - <span class="highlight" data-annotation="%7B%22attachmentURI%22%3A%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F9QS63MA8%22%2C%22annotationKey%22%3A%22HLQ7R8S9%22%2C%22color%22%3A%22%235fb236%22%2C%22pageLabel%22%3A%226%22%2C%22position%22%3A%7B%22pageIndex%22%3A5%2C%22rects%22%3A%5B%5B310.5%2C500.2%2C420.8%2C511.4%5D%5D%7D%2C%22citationItem%22%3A%7B%22uris%22%3A%5B%22http%3A%2F%2Fzotero.org%2Fusers%2Flocal%2FAbCdEfGh%2Fitems%2F46GUJFLD%22%5D%2C%22locator%22%3A%226%22%7D%7D">“lesions smaller than 5 mm”</span> 合成失败
  - [ ] 核对补充材料 S2
- 推理：<span style="color: #ff2020">未交代</span>

<p style="padding-left: 40px" data-indent="1">我的推测：推理时<strong>不需要</strong>。</p>

***

相关笔记：[方法对比](zotero://note/u/NT4KX9QA/) · 原文 [p. 6](zotero://open-pdf/library/items/9QS63MA8?page=6)
