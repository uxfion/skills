<!-- literal * and *x* -->
---
schema: 9
---
评分用 4\*5 网格，\*不是\*强调

<!-- literal _ and __x__ -->
---
schema: 9
---
\_\_init\_\_ 方法、snake_case_name 与 \_前导下划线

<!-- para starts '1. ' -->
---
schema: 9
---
1\. 这一段以数字加点开头，但不是列表

<!-- para starts '# ' -->
---
schema: 9
---
\# 不是标题

<!-- para starts '- ' -->
---
schema: 9
---
\- 不是列表项

<!-- literal <b> and &amp;amp; -->
---
schema: 9
---
HTML 标签 \<b> 的说明，以及 \&amp; 实体

<!-- literal [x](y) -->
---
schema: 9
---
[1\](见下) 不是链接

<!-- literal backtick -->
---
schema: 9
---
用 \` 包裹代码

<!-- literal $5 and $10 -->
---
schema: 9
---
成本 \$5 和 \$10 美元

<!-- literal backslashes -->
---
schema: 9
---
路径 C:\Users\name\\\* 和 \\(x\\)

<!-- literal ~~x~~ -->
---
schema: 9
---
~~不是删除线~~

<!-- hard break -->
---
schema: 9
---
第一行\
第二行

<!-- nbsp / double space -->
---
schema: 9
---
A &nbsp;B 和 C D

<!-- two lists in a row -->
---
schema: 9
---
- A

* B

<!-- loose item (2 paras) -->
---
schema: 9
---
- 段一

  段二
- 项二

<!-- ol start=3 -->
---
schema: 9
---
3. 第三
4. 第四

<!-- list inside quote -->
---
schema: 9
---
> 引文
> - 引文中的列表

<!-- table without header -->
---
schema: 9
---
<table>
<tbody>
<tr>
<td>
<p>a</p>
</td>
<td>
<p>b</p>
</td>
</tr>
<tr>
<td>
<p>c</p>
</td>
<td>
<p>d</p>
</td>
</tr>
</tbody>
</table>

<!-- table cell with | -->
---
schema: 9
---
| 列\|1 | 列2 |
| --- | --- |
| x\|y | z |

<!-- bold link, bold+italic -->
---
schema: 9
---
**[粗体链接](zotero://select/library/items/ABCD1234)** 和 ***粗斜体***

<!-- em before CJK -->
---
schema: 9
---
*注：*斜体后接中文，**“引号”**后接中文

<!-- heading with code -->
---
schema: 9
---
## Q5 带 `code` 的标题 [已答]

<!-- code block -->
---
schema: 9
---
```
def f(x):
    return x * 2
```

<!-- u, strike, sub, sup -->
---
schema: 9
---
<u>下划线</u>、<span style="text-decoration: line-through">删除线</span>、H<sub>2</sub>O、x<sup>2</sup>

<!-- colour, highlight -->
---
schema: 9
---
<span style="color: #ff2020">红色</span> 和 <span class="highlight" data-annotation="%7B%22k%22%3A1%7D">高亮</span>

<!-- embedded image -->
---
schema: 9
---
<img alt="" width="400" height="300" data-attachment-key="IMG12345">

<!-- empty paragraph -->
---
schema: 9
---
前

<p></p>

后

<!-- math with * and _ -->
---
schema: 9
---
$a*b_{i}^*$ 与 $x\_1$
