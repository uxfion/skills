# paper-fetch：2026-11-10 试跑里看到的三处（都没核实原因）

- 来源：2026-11-10 用户在场的试跑（三篇缺 PDF 的库内论文），主 agent 从结果文件和事件记录里看到的。用户没有单独提。
- 状态：open，三处都还没看代码，也没判断值不值得改。

1. **补充材料被建议成正式版正文。** Eur Radiol 那篇没权限的页面上，唯一的 PDF 链接是补充材料（链接文字 "ELECTRONIC SUPPLEMENTARY MATERIAL (download PDF)"，文件第一页第二行也是这句）。`fetch` 取了它，核对通过，建议的标题是 `Published-Springer`。后面定标签的 judge 没有被提示，自己认出来标成了 `Supplement-Springer`，脚本随后也不再认为这篇已拿到、接着找正文。所以结果没错，错的只是建议；文件名里的版本仍是 published（`<slug>.pdf`）。
2. **同一个文件的重复下载被当成认不出是哪篇。** ProQuest 那份 PDF 被 Chrome 下载了两份（`document.pdf`、`Ultrasound-based_liver_trackin.pdf`），和已经收下的那份 md5 相同。监听只拿它们去比还在等文件的论文，都对不上，各开了一个 `left` 交接。md5 相同是脚本自己就能确定的事。
3. **附件网址记的是阅读器页面。** ProQuest 那份的 `url` 是 `…/pdfjs/web/viewer.html?file=…`，不是 PDF 的地址（`…/docview/<id>/fulltextPDF`）。paper-to-zotero 现在把结果里的这个地址原样写成附件网址。
