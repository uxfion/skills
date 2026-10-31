# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/check_note.py: when a paper note's question tree counts as read through."""
import importlib.util
import json
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_note.py"
spec = importlib.util.spec_from_file_location("check_note", SCRIPT)
check_note = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_note)

OPEN = """---
parent: ziegler2024tcace
---
# 论文笔记

[待答]

## Q1 这篇论文试图解决什么问题？ [已答]

回答。

## Q3 论文如何解决这个问题？ [已答]

### Q3.1 推理时也要真值 mask 吗？ [论文没有说明]

### Q3.2 对比方法也给了 mask 吗？ [等 Q4] → Q4.1

## Q4 论文做了哪些实验？ [进行中]

```
## Q9 not a heading, inside code [待答]
```

## Q5 有什么可以进一步探索的点？

## 用在哪里
"""


class CheckNote(unittest.TestCase):
    def test_open_nodes_a_missing_status_and_the_summary(self):
        out = check_note.check(OPEN)
        self.assertEqual(out["code"], "open")
        self.assertEqual([(o["line"], o["status"]) for o in out["open"]], [(16, "等 Q4"), (18, "进行中")])
        self.assertEqual([o["heading"] for o in out["no_status"]], ["Q5 有什么可以进一步探索的点？"])
        self.assertFalse(out["summary_written"])

    def test_read_through(self):
        done = (OPEN.replace("[待答]\n\n## Q1", "一句话：用增强前的平扫预测增强后的影像。\n\n## Q1")
                .replace("[等 Q4] → Q4.1", "[已答]").replace("[进行中]", "[已答]")
                .replace("进一步探索的点？\n", "进一步探索的点？ [要看别处]\n"))
        self.assertEqual(check_note.check(done), {"code": "complete", "open": [], "no_status": [], "summary_written": True})

    def test_the_command(self):
        note = Path(tempfile.mkdtemp(prefix="paper-read-")) / "a.note.md"
        note.write_text(OPEN, encoding="utf-8")
        done = subprocess.run([shutil.which("uv"), "run", "--quiet", "--script", str(SCRIPT), str(note)],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual((done.returncode, json.loads(done.stdout)["code"]), (1, "open"), done.stderr)
        done = subprocess.run([shutil.which("uv"), "run", "--quiet", "--script", str(SCRIPT), str(note) + ".gone"],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 2)


if __name__ == "__main__":
    unittest.main()
