# paper-fetch：2026-11-10 试跑里看到的三处（都没核实原因）

> **已解决（2026-11-10）。** 三处都看了代码，两处修了，一处不改。
>
> 1. **补充材料被当成正文收下：修了。** 核对里本来有"首页像补充材料"的检查，但只看标题**之前**的那段文字；这份文件以论文标题开头，"ELECTRONIC SUPPLEMENTARY MATERIAL" 在标题下面一行，所以没查到。现在标题下面紧接的几行也看（`paper-fetch/scripts/pflib/verify.py`）。查到的文件不再直接收下，而是留给 agent 看。在库里全部 895 个 PDF 的首页上验证：862 个正文（Published、Accepted、Preprint）新旧都是 0 个被标；4 个补充材料里旧的查到 2 个，新的 4 个都查到，其中一个不是照着改的那份。
> 2. **同一个文件的重复下载：修了。** 监听碰到和本次已收下的文件 md5 相同的下载，直接略过，不再开 `left` 交接；它留在下载目录里，由收尾的清点列出（`pflib/run.py` 的 `Scanner.scan`）。
> 3. **附件网址记成阅读器页面的地址：不改。** 三个 skill 里没有代码读附件网址（见 [20261109-paper-to-zotero-attachment-url-is-the-item-url-fixed.md](20261109-paper-to-zotero-attachment-url-is-the-item-url-fixed.md)），阅读器地址也确实是文件被读出来的地方；要换成 `docview/<id>/fulltextPDF` 得给各家数据库的阅读器各写一条规则。

- 来源：2026-11-10 用户在场的试跑（三篇缺 PDF 的库内论文），主 agent 从结果文件和事件记录里看到的。用户没有单独提。
- 状态：已解决。

1. **补充材料被建议成正式版正文。** Eur Radiol 那篇没权限的页面上，唯一的 PDF 链接是补充材料（链接文字 "ELECTRONIC SUPPLEMENTARY MATERIAL (download PDF)"，文件第一页第二行也是这句）。`fetch` 取了它，核对通过，建议的标题是 `Published-Springer`。后面定标签的 judge 没有被提示，自己认出来标成了 `Supplement-Springer`，脚本随后也不再认为这篇已拿到、接着找正文。所以结果没错，错的只是建议；文件名里的版本仍是 published（`<slug>.pdf`）。
2. **同一个文件的重复下载被当成认不出是哪篇。** ProQuest 那份 PDF 被 Chrome 下载了两份（`document.pdf`、`Ultrasound-based_liver_trackin.pdf`），和已经收下的那份 md5 相同。监听只拿它们去比还在等文件的论文，都对不上，各开了一个 `left` 交接。md5 相同是脚本自己就能确定的事。
3. **附件网址记的是阅读器页面。** ProQuest 那份的 `url` 是 `…/pdfjs/web/viewer.html?file=…`，不是 PDF 的地址（`…/docview/<id>/fulltextPDF`）。paper-to-zotero 现在把结果里的这个地址原样写成附件网址。
