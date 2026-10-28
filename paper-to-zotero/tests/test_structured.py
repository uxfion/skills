# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/structured.py against the fake Zotero: take, parse (simulated), put, edit, put again."""
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from helpers import call, config_file, load
from fake_zotero import FakeZotero

structured, read_library, trash_item = load("structured"), load("read_library"), load("trash_item")
ITEM, PUB, PRE = "ITEM0001", "ATTPUB01", "ATTPRE01"
CITE = "smithPaper2024"
PUB_PDF, PRE_PDF = b"%PDF-1.4 published\n%%EOF\n", b"%PDF-1.4 preprint\n%%EOF\n"
PDF_NAME = "Smith 等 - 2024 - Paper.pdf"


class Structured(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()
        cls.config = config_file()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        z = self.zot
        z.reset()
        z.add_item(ITEM, itemType="journalArticle", title="Paper", citationKey=CITE)
        for key, title, body in ((PUB, "Published-IEEE", PUB_PDF), (PRE, "Preprint-arXiv-v1", PRE_PDF)):
            z.add_item(key, itemType="attachment", parentItem=ITEM, title=title, linkMode="imported_url",
                       contentType="application/pdf", filename=PDF_NAME, md5=hashlib.md5(body).hexdigest())
            z.files[key] = z.store_file(key, PDF_NAME, body)
        tmp = tempfile.TemporaryDirectory(prefix="p2z-structured-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def run_(self, module, *argv):
        url = ["--base-url", self.zot.base_url]
        return call(module, *(url + list(argv) if module is not trash_item else list(argv) + url), config=self.config)

    def take(self, name, *argv):
        return self.run_(structured, "take", "--cite", CITE, "--to", self.tmp / name, *argv)

    def parse(self, folder, body=PUB_PDF):
        """What paddleocr's parse leaves: <stem>/<stem>.md, .json (source.sha256), imgs/, and its lock file."""
        (folder / "imgs").mkdir(parents=True)
        (folder / f"{folder.name}.md").write_text("<!-- page 1 -->\n# Paper\n", encoding="utf-8")
        (folder / f"{folder.name}.json").write_text(json.dumps({"source": {"sha256": hashlib.sha256(body).hexdigest()}}))
        (folder / "imgs" / "p1-2.png").write_bytes(b"\x89PNG fake")
        (folder / ".lock").write_text("1 0")

    def packages(self):
        return [it["data"] for it in self.zot.items.values()
                if it["data"].get("contentType") == "application/zip" and not it["data"].get("deleted")]

    def test_take_parse_put_edit_put(self):
        r = self.take("a")
        stem = f"{CITE}.Published-IEEE"
        line = r.lines[0]
        self.assertEqual((r.code, line["code"], line["title"], line["package"]), (0, "ok", "Published-IEEE", None), r)
        self.assertEqual(Path(line["input"]).resolve().read_bytes(), PUB_PDF, "the link points at the best PDF")
        folder = self.tmp / "a" / stem
        self.parse(folder)

        r = self.run_(structured, "put", folder)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)
        [pkg] = self.packages()
        self.assertEqual((pkg["title"], pkg["filename"], pkg["parentItem"]),
                         ("Published-IEEE", "Smith 等 - 2024 - Paper.zip", ITEM), "same title and name as the PDF")
        with zipfile.ZipFile(self.zot.files[pkg["key"]]) as zf:
            self.assertEqual(sorted(zf.namelist()), ["Published-IEEE/Published-IEEE.json", "Published-IEEE/Published-IEEE.md",
                                                     "Published-IEEE/imgs/p1-2.png"], "no lock file; named after the title")
        self.assertEqual(self.run_(structured, "put", folder).lines[0]["reason"], "already_current")

        rows = {row["attachment_title"]: row["package"] for row in self.run_(read_library, "pdf", "--cite", CITE).lines}
        self.assertEqual(rows, {"Published-IEEE": pkg["key"], "Preprint-arXiv-v1": None})

        r = self.take("b")
        again = self.tmp / "b" / stem
        self.assertEqual((r.lines[0]["package"], (again / f"{stem}.md").read_text(encoding="utf-8")),
                         (pkg["key"], "<!-- page 1 -->\n# Paper\n"), "unzipped under take's stem")
        self.take("c")
        (again / f"{stem}.md").write_text("<!-- page 1 -->\n# Paper, settled\n", encoding="utf-8")
        r = self.run_(structured, "put", again)
        self.assertEqual((r.code, r.lines[0]["replaced"]), (0, [pkg["key"]]), r)
        self.assertTrue(self.zot.data(pkg["key"]).get("deleted"), "the replaced package went to the trash")

        late = self.tmp / "c" / stem
        (late / f"{stem}.md").write_text("<!-- page 1 -->\n# Paper, other edit\n", encoding="utf-8")
        self.assertEqual(self.run_(structured, "put", late).lines[0]["code"], "changed_since_take")

        renamed = self.zot.data(PUB)["filename"] = "Smith et al. - 2024 - Paper.pdf"
        latest = self.packages()[0]
        self.take("e")
        r = self.run_(structured, "put", self.tmp / "e" / stem)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["replaced"]), ("ok", [latest["key"]]), r)
        [pkg] = self.packages()
        self.assertEqual((pkg["filename"], pkg["md5"]), (renamed.replace(".pdf", ".zip"), latest["md5"]),
                         "a renamed PDF: the same zip again, under its new name")

        r = self.run_(structured, "take", "--missing", "--to", self.tmp / "d")
        self.assertEqual([(x["title"], x["package"]) for x in r.lines[:-1]], [("Preprint-arXiv-v1", None)])
        pre = self.tmp / "d" / f"{CITE}.Preprint-arXiv-v1"
        self.parse(pre, body=PUB_PDF)
        self.assertEqual(self.run_(structured, "put", pre).lines[0]["code"], "source_mismatch")

        r = self.run_(trash_item, "--key", PUB)
        self.assertEqual([p["code"] for p in r.lines[0]["packages"]], ["ok"], "the PDF takes its package along")
        self.assertEqual(self.packages(), [])


if __name__ == "__main__":
    unittest.main()
