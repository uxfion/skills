# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/sources.py: which sources in a note become links, and the links taken off again."""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import sources  # noqa: E402

# The forms note-format.md tells the reader link, and those that do not, are what the code is held to.
DOC = (HERE.parent / "references" / "note-format.md").read_text(encoding="utf-8")
SPANS = {kind: re.findall(r"`([^`]+)`", re.search(rf"^- {kind}: (.*)$", DOC, re.M).group(1)) for kind in ("Linked", "Not linked")}

NOTE = """---
parent: xiaoTCACE2026
---
# 论文笔记 (Fig. 1)

T-CACE 一个模型同时做合成、分割和诊断（Fig. 1, p.2）。

读的版本：Published-IEEE (Table I, p.8)

## Q5 做了哪些实验？ Table III [已答]

1. 消融（Table III, p.11；Fig. 9, p.11）。见 Q5.4。Table I/II 和 Figs. 3–5 都在 p.8–9。

> "As shown in Table III, removing any module results in a decline" (Table III, p.11)
>
> 如 Table III 所示，去掉任一模块都会下降。

公式 $p.3 = Fig. 2$ 与 `Table 9` 不动，[p. 6](zotero://open-pdf/library/items/AAAAAAAA?page=6) 也不动；见 https://x.org/p.4。

<p style="color: red">Fig. 5 在 p.6</p>
<p>仍是 HTML 块，Fig. 6</p>

<span style="color: red">Fig. 7</span> 在 p.7（行内的 HTML 不算块）。

（Published-IEEE 删去了这段，原见 arXiv-v1 Fig. 4, p.5）这句在 Fig. 8。（更正 2026-11-04：原写"Table II, p.3"，按 Table II, p.8 改）

```
Fig. 10, p.12
```
"""


def linked(note):
    out = note.split("\n")
    for n, a, b, text, m in sorted(sources.tokens(note), key=lambda t: (t[0], t[1]), reverse=True):
        new = (sources.page_link("PDFKEY01", text, int(m.group("page"))) if m.group("page")
               else sources.annotation_link("PDFKEY01", text, "ANNOT001"))
        out[n - 1] = out[n - 1][:a] + new + out[n - 1][b:]
    return "\n".join(out)


class Tokens(unittest.TestCase):
    def test_the_forms_note_format_names(self):
        self.assertGreater(len(SPANS["Linked"]), 5)
        for form in SPANS["Linked"]:
            found = sources.tokens(form)
            self.assertEqual(len(found), 1, form)
            self.assertEqual(found[0][1], 0, form)
        for form in SPANS["Not linked"]:
            self.assertEqual(sources.tokens(form), [], form)

    def test_where_they_are_read(self):
        got = [(n, text) for n, _, _, text, _ in sources.tokens(NOTE)]
        self.assertEqual(got, [
            (6, "Fig. 1"), (6, "p.2"),                       # the summary is text; the title, front matter and 读的版本 not
            (12, "Table III"), (12, "p.11"), (12, "Fig. 9"), (12, "p.11"),
            (12, "Table I"), (12, "Figs. 3"), (12, "p.8–9"),  # of Table I/II and Figs. 3–5 the first alone
            (14, "Table III"), (14, "p.11"),                 # the source after a quotation, not its words
            (16, "Table III"),                               # its Chinese line
            (23, "Fig. 7"), (23, "p.7"),                     # inline HTML around it: text; an HTML block: not
            (25, "Fig. 8"), (25, "Table II"), (25, "p.8"),  # not the deletion mark, nor 原写"…"
        ])

    def test_keys_and_labels(self):
        keys = [sources.key_of(m) for *_, m in sources.tokens(
            "Fig. 9, Figure 9, Fig.9, Figs. 3, Table III, Tables I, Supplementary Fig. 3, Fig. S3, Supplementary Fig. S3, "
            "Extended Data Table 1, Fig. 2(b), Fig. 2b")]
        self.assertEqual(keys, ["fig:9"] * 3 + ["fig:3", "table:III", "table:I"] + ["fig:S3"] * 3
                         + ["table:ED1", "fig:2", "fig:2"])
        self.assertEqual([sources.label(k) for k in ("fig:9", "table:III", "fig:S3", "table:ED1")],
                         ["Fig. 9", "Table III", "Fig. S3", "Extended Data Table 1"])


class Strip(unittest.TestCase):
    def test_linked_then_stripped_is_the_note(self):
        self.assertNotEqual(linked(NOTE), NOTE)
        self.assertEqual(sources.strip(linked(NOTE)), NOTE)
        self.assertEqual(sources.tokens(linked(NOTE)), [])   # a linked token is not linked twice

    def test_only_its_own_links(self):
        kept = ("[p. 6](zotero://open-pdf/library/items/AAAAAAAA?page=6) "        # no token: a space after p.
                "[p.6](zotero://open-pdf/library/items/AAAAAAAA?page=7) "         # the page is not the token's
                "[Fig. 3](zotero://open-pdf/library/items/AAAAAAAA?page=3) "      # a figure to a page
                "[see Fig. 3](zotero://open-pdf/library/items/AAAAAAAA?annotation=BBBBBBBB) "
                "[p.6](https://example.org/?page=6)")
        self.assertEqual(sources.strip(kept), kept)
        html = ('<p>Fig. 3 <a href="zotero://open-pdf/library/items/OLDPDF01?annotation=BBBBBBBB" rel="noopener">Fig. 3</a>'
                ' <a href="zotero://open-pdf/library/items/OLDPDF01?page=4">p.4–5</a></p>')
        self.assertEqual(sources.strip(html), "<p>Fig. 3 Fig. 3 p.4–5</p>")   # any PDF's key: an older version's too


class Quotation(unittest.TestCase):
    def test_words_tail_and_unparsed(self):
        line = '> "the words" (Sec. 3, p.2) （已核对 p.2 · 2026-11-04）'
        start, end, tail = sources.quotation(line)
        self.assertEqual((line[start:end], tail), ("the words", " (Sec. 3, p.2) （已核对 p.2 · 2026-11-04）"))
        self.assertEqual(sources.quotation('> "cut off (p.2)')[1:], (None, None))
        self.assertIsNone(sources.quotation("> 中文译文"))


if __name__ == "__main__":
    unittest.main()
