# paper-to-zotero：导入时每个附件的网址都写成条目的网址，不是文件实际下载的地方

- 来源：2026-11-09 精读那一轮，读论文的 subagent 读 DualTrack（`wilsonDualTrackSensorless3D2025`）时在回报里指出，主 agent 读代码核实。用户没有提。
- 状态：open。

## 经过

- **看到什么。** DualTrack 是 ASMUS 2025 的会议论文（有 Springer DOI），学校没有订阅，库里只挂了 arXiv v2 的 PDF（附件 X7DU7ZUI，标题 Preprint-arXiv-v2）。这份附件的 `url` 却是 `https://doi.org/10.1007/978-3-032-06329-8_1`，也就是正式版。导入记录里，paper-fetch 的结果写着这份文件实际是从 `https://arxiv.org/pdf/2509.09530v2` 下载的。
- **原因。** `paper-to-zotero/scripts/attach_file.py` 第 115 行对所有要挂的文件只取一个网址：条目的 `url`，没有就用条目的 DOI。文件自己的下载地址没有用上。这一行从 2026-10-13 的 v3 起就是这样。
- **影响。** 凡是条目有 DOI、挂的却是预印本或别处来源的文件，附件网址都指向正式版。在 Zotero 里点这份附件的网址，会以为它就是正式版；以后按附件网址判断来源的工具或 agent 也会判错。库里这样的附件有多少还没数（同一天看到 UIV-US 的 Accepted-MICCAI 附件也是 DOI 网址，来源待查）。
- **当场处理。** DualTrack 这一份已用 `p2z.py update --set url=https://arxiv.org/pdf/2509.09530v2 X7DU7ZUI` 改回实际下载地址。

## 待看

`attach` 用 paper-fetch 结果里这份文件自己的下载地址（按设计原则"事实在最早拿到时记下"：下载那一刻最清楚）。改完后，库里已有的附件要不要按记录补正，补正哪些，等数出来再定（lint 可以加一条：附件标题是 Preprint，网址却是 DOI）。
