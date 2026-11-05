# paper-to-zotero：`tag -n` 的预览里集合只写 key，不写路径

- 来源：主 agent，2026-11-05，p2z Unix 约定样板的真写入验收（spec `20261104-skills-unix-conventions-spec.md` 第 9 节）。用户没有提，是给用户看预览时碰到的。
- 状态：open。

## 经过

- **跑的什么。** `p2z.py tag -n chenDiffusionPluginPriors2026 --add-collection 医疗图像 --remove-collection tmp`。
- **看到什么。** 预览行里是 `"collection": {"from": ["RIBA5MZJ"], "to": ["9EYXTC2I"]}`：命令行上写的是名字，预览里只剩 key。
- **为什么不顺。** 写库前的预览是给用户确认用的（SKILL.md *Authorization*，organize.md 第 4 步把 `-n` 的输出直接列给用户），用户在 Zotero 里认的是集合路径，不认 key。主 agent 得另跑 `p2z.py collections` 把 key 翻成路径再给用户看；一次整理批量改几十条时更麻烦。写库后的行一样只有 key。

## 建议

`tag` 和 `update` 的行里，集合在 key 旁边带上路径（如 `{"key": "9EYXTC2I", "path": "医疗图像"}`），预览和真写一样。`p2z` 已经为解析集合读过整棵树，不用多请求。
