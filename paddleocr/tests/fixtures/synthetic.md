<!-- paddleocr render=3 source=synthetic.pdf sha256=00000000 pages=1-3,5/5 checks=skipped:no_source coverage=none figures=2 figures_checked=0 open=0 unresolved=0 body=bfda0ca6ad35 -->

<!-- page 1 -->

# A Synthetic Paper for Testing

Ann Author, Bob Writer

## Abstract
 We test a parser on pages it has never seen.
It reads them in order.

## 1 Introduction

The first paragraph runs across

the column break and continues on the right.

where E is energy:

$$  E = m c^{2}   \tag*{(1)}$$

Second paragraph after the formula, which cites Fig. 1 and Table 1.

* Corresponding author.

<!-- page 2 -->

<!-- figure p2-2 (Fig. 1) -->

a

![Fig. 1](imgs/p2-2.png)

b

Accuracy over time

<!-- end figure p2-2 -->

Fig. 1 | Two panels. a, An image. b, A chart of accuracy.

## 2 Results

Table 1. Scores of the models.

<table><tr><td>Model</td><td>Score</td></tr><tr><td>A</td><td>0.91</td></tr><tr><td>B</td><td>0.87</td></tr><tr><td>C <img alt="Image" src="imgs/p3-1-1.png"/></td><td>0.80</td></tr></table>

<!-- table p2-9 continues on page 3 -->

<!-- page 3 -->

Text after the table with a reference [1].

## References

[1] A. Author. A paper. 2025.

Algorithm 1 Search
1: for each node do
2:   expand it

arXiv:2601.00001v1 [cs.CL] 1 Jan 2026

<!-- page 5 -->

A page after a gap in the pages parsed.

Arrow indicates a better direction.

Best in bold.

1 Intro  
2 Methods

## References
[2] B. Writer. Another paper. 2024.

## 3 Discussion

![](imgs/p5-5.png)

A figure without a caption sits above this line.
