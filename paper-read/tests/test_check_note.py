# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for pr.py check (scripts/check_note.py): when a paper note may go into Zotero, after any change and after a
read-through."""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_note.py"
sys.path.insert(0, str(SCRIPT.parent))   # its prlib
spec = importlib.util.spec_from_file_location("check_note", SCRIPT)
check_note = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_note)

# Half read: line numbers are counted by hand.
HALF = """---
parent: xiaoTCACE2026
key: NOTE1234
---
# 论文笔记

[待答]

读的版本：T-CACE (JBHI 2026)

## Q1 这篇论文要解决什么问题，为什么重要？这是哪类论文？ [已答]

回答。

## Q3 论文如何解决这个问题？ [已答]

### Q3.1 推理时也要输入肿瘤 mask 吗？ [论文没有说明]

### Q3.2 对比方法也给了 mask 吗？ [等 Q5] → Q5.1

## Q5 做了哪些实验？ [进行中]

```
## Q9 not a heading, inside code [待答]
```

## Q7 有什么可以进一步探索的点？

## 用在哪里
"""

# The same note as it was taken: Q2 and Q3.3 were there and the change lost them.
TAKEN = HALF.replace("## Q3 论文", "## Q2 之前的工作怎么做，缺在哪里？ [待答]\n\n## Q3 论文").replace(
    "### Q3.2", "### Q3.3 用了几个中心的数据？ [待答]\n\n### Q3.2")

FULL = """---
parent: xiaoTCACE2026
key: NOTE1234
---
# 论文笔记

用平扫 MRI 和肿瘤 mask 生成多期增强 MRI，同时分割和分类病灶。

读的版本：T-CACE (JBHI 2026)

## Q1 这篇论文要解决什么问题，为什么重要？这是哪类论文？ [已答]
## Q2 之前的工作怎么做，缺在哪里？ [已答]
## Q3 论文如何解决这个问题？ [已答]
- **核心机制**：时间条件的自回归解码。
### Q3.1 推理时也要输入肿瘤 mask 吗？ [论文没有说明]
## Q4 创新点是什么？ [已答]
## Q5 做了哪些实验？ [已答]
- **数据和划分**：两个中心。
- **对比方法**：五个。
- **指标**：PSNR、SSIM、Dice。
- **主要数字**：PSNR 28.41。
- **代码和数据**：代码公开，数据不公开。
## Q6 结论站得住吗？ [已答]
- **证据和范围**：只在肝脏 MRI 上。
- **提升从哪来**：消融表。
- **统计**：论文没有说明。
- **前后矛盾**：没有发现。
- **假设和局限**：要有 mask；没有 mask 的病例上会失败。
- **更好的验证**：外部中心。
## Q7 有什么可以进一步探索的点？ [要看别处]
## Q8 总结一下论文的主要内容 [已答]
## Q9 有什么启发？ [已答]
- **可借鉴**：期相 token。
- **可吸取的**：要外部验证。
- **前沿概念**：自回归增强。
- **和别的论文的联系**：没有。
- **思路与灵感**：时间条件。
- **头脑风暴**：没有值得留下的想法。
"""


class CheckNote(unittest.TestCase):
    def test_the_fixed_items_are_note_format_s(self):
        doc = (SCRIPT.parent.parent / "references" / "note-format.md").read_text(encoding="utf-8")
        for q, n in (("Q3", 3), ("Q5", 5), ("Q6", 6), ("Q9", 9)):
            block = re.search(rf"^{n}\. .*?(?=^\d+\. |^[^\s\d]|\Z)", doc, re.S | re.M).group(0)
            self.assertEqual(tuple(re.findall(r"^ +- \*\*(.+?)\*\*", block, re.M)), check_note.ITEMS[q], q)

    def test_a_half_read_note_is_open(self):
        out = check_note.check(HALF, taken=TAKEN)
        self.assertEqual(out["code"], "open")
        self.assertEqual([(o["line"], o["state"]) for o in out["open"]], [(19, "等 Q5"), (21, "进行中")])
        self.assertEqual(out["no_state"], [{"line": 27, "heading": "Q7 有什么可以进一步探索的点？"}])
        self.assertEqual(out["missing_numbers"], ["Q2", "Q3.3"])
        self.assertEqual(out["version"], "T-CACE (JBHI 2026)")
        self.assertFalse(out["summary_written"])

    def test_a_read_through(self):
        self.assertEqual(check_note.check(FULL, taken=FULL, full=True), {
            "code": "complete", "questions": 10, "open": [], "no_state": [], "math_in_heading": [], "missing_numbers": [], "version": "T-CACE (JBHI 2026)",
            "summary_written": True, "missing_trunk": [], "missing_items": []})
        cut = FULL.replace("- **统计**：论文没有说明。\n", "").replace("## Q8 总结一下论文的主要内容 [已答]\n", "")
        out = check_note.check(cut, full=True)
        self.assertEqual((out["code"], out["missing_trunk"], out["missing_items"]), ("open", ["Q8"], ["Q6 统计"]))
        # a bold word under another question does not count for Q6
        moved = cut.replace("[要看别处]\n", "[要看别处]\n- **统计**：放错了地方。\n")
        self.assertEqual(check_note.check(moved, full=True)["missing_items"], ["Q6 统计"])
        # a note written before Q9 existed: exactly Q9 and the two later fixed items are missing
        older = FULL.split("## Q9")[0].replace("- **核心机制**：时间条件的自回归解码。\n", "").replace("- **更好的验证**：外部中心。\n", "")
        out = check_note.check(older, full=True)
        self.assertEqual((out["code"], out["missing_trunk"]), ("open", ["Q9"]))
        self.assertEqual(out["missing_items"], ["Q3 核心机制", "Q6 更好的验证"] + [f"Q9 {w}" for w in check_note.ITEMS["Q9"]])

    def test_a_looked_up_answer(self):
        bare = ("---\nkey: NOTE1234\nparent: xiaoTCACE2026\n---\n# 论文笔记\n\n读的版本：T-CACE (JBHI 2026)\n\n"
                "### Q3.1 推理时也要输入肿瘤 mask 吗？ [论文没有说明]\n\n方法部分只写了训练。\n")
        self.assertEqual(check_note.check(bare)["code"], "complete")
        out = check_note.check(bare, full=True)
        self.assertEqual((out["code"], out["missing_trunk"]), ("open", [f"Q{i}" for i in range(1, 10)]))
        self.assertEqual(check_note.check(bare.replace("读的版本：T-CACE (JBHI 2026)\n\n", ""))["code"], "open")
        # TeX in a heading does not come back from Zotero as a heading (T-CACE, 2026-11-02); Unicode does
        tex = bare.replace("推理时也要输入肿瘤 mask 吗？", "逐期输出 $\\hat{y}_i^{cls}$ 和 $f_\\theta$ 怎么来？")
        self.assertEqual(check_note.check(tex)["math_in_heading"],
                         [{"line": 9, "heading": "Q3.1 逐期输出 $\\hat{y}_i^{cls}$ 和 $f_\\theta$ 怎么来？ [论文没有说明]"}])
        self.assertEqual(check_note.check(tex.replace("$\\hat{y}_i^{cls}$ 和 $f_\\theta$", "ŷᵢ 和 fθ"))["code"], "complete")
        # such a heading comes back from Zotero as HTML: still a question, still flagged
        html = tex.replace("### Q3.1 逐期输出 $\\hat{y}_i^{cls}$ 和 $f_\\theta$ 怎么来？ [论文没有说明]",
                           "<h3>Q3.1 逐期输出 $\\hat{y}_i^{cls}$ 和 $f_\\theta$ 怎么来？ [论文没有说明]</h3>")
        out = check_note.check(html)
        self.assertEqual((out["questions"], out["math_in_heading"][0]["line"]), (1, 9))
        # a lookup that found nothing to write back leaves a note with no question: not to be put
        empty = bare.split("\n\n### Q3.1")[0] + "\n"
        self.assertEqual((check_note.check(empty)["code"], check_note.check(empty)["questions"]), ("open", 0))

    def test_the_command(self):
        scratch = Path(tempfile.mkdtemp(prefix="paper-read-"))
        note = scratch / "xiaoTCACE2026.T-CACE (JBHI 2026).note.md"
        note.write_text(FULL, encoding="utf-8")
        Path(f"{note}.taken").write_text(TAKEN, encoding="utf-8")

        def run(*args):
            done = subprocess.run([shutil.which("uv"), "run", "--quiet", "--script", str(SCRIPT), *args],
                                  capture_output=True, text=True, timeout=120)
            return done.returncode, done.stdout, done.stderr

        code, stdout, err = run("--full", str(note))  # the .taken beside the note
        self.assertEqual((code, json.loads(stdout)["missing_numbers"]), (1, ["Q3.2", "Q3.3"]), err)
        Path(f"{note}.taken").write_text(FULL, encoding="utf-8")
        code, stdout, err = run(str(note), "--full")
        self.assertEqual((code, json.loads(stdout)["code"], err), (0, "complete", ""))
        for gone in (str(note) + ".gone", str(scratch), "-"):   # not a file: the line about it, on stdout
            code, stdout, err = run(gone)
            self.assertEqual((code, json.loads(stdout)["file"], json.loads(stdout)["code"], err),
                             (1, gone, "file_not_found", ""))
        self.assertEqual(run(str(note), "--taken", str(note))[0], 2)   # a usage error
        shutil.rmtree(scratch)


if __name__ == "__main__":
    unittest.main()
