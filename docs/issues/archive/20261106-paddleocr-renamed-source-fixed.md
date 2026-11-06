# paddleocr：Zotero 改了 PDF 的文件名后，包找不到源文件，commit 不声不响地跳过检查

> **已解决（2026-11-06）**：源文件不在记录的路径上、又没给 `--source` 时，`ocr.py` 到解析目录旁边找记录里的 `file`（`p2z.py package take`、`pr.py take` 就把 PDF 放在那里），sha256 和记录的一致才用。都找不到、而记录又写着路径时，`commit` 在标准错误上警告一行：改动照记，但没对照源文件检查，要检查就带 `--source`。测试：改名后的源文件在旁边能找到，字节不同的不认。

- 来源：主 agent，2026-11-06，UNSB（`kimUnpairedImagetoImageTranslation2024`）的试读，reader 报告，主 agent 读代码核实。用户没有提。

## 经过

- **看到什么。** 包记录里的源路径是 `…/storage/BDLCU8ZD/Kim 等 - 2024 - Unpaired Image-to-Image Translation via Neural Schrödinger Bridge.pdf`，Zotero 后来按用户改的英文模板把文件改名成 "Kim et al. - 2024 …"。reader 修了 p5 的漏字后 `ocr.py commit`，那条 finding 不消失：没有源文件，检查没重跑，也没有任何提示。之后每次调用都得带 `--source <pdf>`。
- **为什么不顺。** 库里的包大多是改模板之前生成的，读每一篇都会碰上；而 PDF 其实就在包旁边（take 放的），文件名和哈希都在记录里。没有提示的跳过，让 reader 以为修得不对。
