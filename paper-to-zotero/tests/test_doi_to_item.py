# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/doi_to_item.py: a doi.org stand-in and a schema mock on one http.server (DOI_BASE_URL + --base-url)."""

import http.server
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "doi_to_item.py"

SCHEMA = {
    "version": 44,
    "itemTypes": [
        {"itemType": "journalArticle",
         "fields": [{"field": f} for f in ("title", "abstractNote", "publicationTitle", "volume", "issue", "pages", "date",
                                            "DOI", "ISSN", "url", "libraryCatalog", "extra")],
         "creatorTypes": [{"creatorType": "author", "primary": True}, {"creatorType": "editor"}, {"creatorType": "contributor"}]},
        {"itemType": "conferencePaper",
         "fields": [{"field": "title"}, {"field": "abstractNote"}, {"field": "proceedingsTitle", "baseField": "publicationTitle"},
                    {"field": "conferenceName"}, {"field": "date"}, {"field": "DOI"}, {"field": "url"}, {"field": "pages"},
                    {"field": "publisher"}, {"field": "place"}, {"field": "libraryCatalog"}, {"field": "extra"}],
         "creatorTypes": [{"creatorType": "author", "primary": True}, {"creatorType": "editor"}, {"creatorType": "contributor"}]},
        {"itemType": "preprint",
         "fields": [{"field": "title"}, {"field": "abstractNote"}, {"field": "repository", "baseField": "publisher"},
                    {"field": "archiveID", "baseField": "number"}, {"field": "date"}, {"field": "DOI"}, {"field": "url"},
                    {"field": "libraryCatalog"}, {"field": "extra"}],
         "creatorTypes": [{"creatorType": "author", "primary": True}, {"creatorType": "contributor"}]},
    ],
    "csl": {
        "types": {"article-journal": ["journalArticle"], "paper-conference": ["conferencePaper"], "article": ["preprint"]},
        "fields": {
            "text": {"title": ["title"], "container-title": ["publicationTitle"], "volume": ["volume"], "issue": ["issue"],
                     "page": ["pages"], "DOI": ["DOI"], "URL": ["url"], "ISSN": ["ISSN"], "abstract": ["abstractNote"],
                     "publisher": ["publisher"], "event-title": ["conferenceName"]},
            "date": {"issued": "date", "accessed": "accessDate"},
        },
        "names": {"author": "author", "editor": "editor"},
    },
}

CSL = {
    "10.1109/JBHI.2022.3142076": {
        "type": "journal-article", "source": "Crossref",
        "title": "Progressive Residual Learning With Memory Upgrade for Ultrasound Image Blind Super-Resolution",
        "author": [{"family": "Liu", "given": "Heng"}, {"family": "Liu", "given": "Jianyong"}],
        "issued": {"date-parts": [[2022, 9]]}, "container-title": "IEEE Journal of Biomedical and Health Informatics",
        "volume": "26", "issue": "9", "page": "4593-4604", "DOI": "10.1109/JBHI.2022.3142076",
        "URL": "http://dx.doi.org/10.1109/JBHI.2022.3142076", "ISSN": ["2168-2194"], "abstract": "<jats:p>Ultrasound.</jats:p>"},
    "10.1109/CVPR.2016.90": {
        "type": "proceedings-article", "source": "Crossref", "title": "Deep Residual Learning for Image Recognition",
        "author": [{"family": "He", "given": "Kaiming"}], "issued": {"date-parts": [[2016, 6]]},
        "container-title": "2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)",
        "event-title": "2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)",
        "DOI": "10.1109/CVPR.2016.90", "abstract": "Deeper networks."},
    "10.48550/arXiv.2006.11239": {
        "type": "article", "title": "Denoising Diffusion Probabilistic Models", "author": [{"family": "Ho", "given": "Jonathan"}],
        "issued": {"date-parts": [[2020]]}, "DOI": "10.48550/ARXIV.2006.11239", "publisher": "arXiv", "abstract": "We present."},
    "10.9999/twin": {
        "type": "journal-article", "source": "Crossref", "title": "Progressive Twin Paper",
        "author": [{"family": "Liu", "given": "Wei"}], "issued": {"date-parts": [[2022]]}, "container-title": "J",
        "DOI": "10.9999/twin", "abstract": "x"},
}

BIB = """\
@comment{this is ignored}
@string{ieee = "IEEE"}
@article{liuJBHI2022,
  title = {Progressive {Residual} Learning},
  author = {Liu, Heng},
  doi = {https://doi.org/10.1109/JBHI.2022.3142076},
  year = 2022
}
@misc{ho2020ddpm,
  title = "Denoising Diffusion Probabilistic Models",
  eprint = {2006.11239},
  archivePrefix = {arXiv},
  primaryClass = {cs.LG}
}
@inproceedings{he2016resnet,
  Title = {Deep Residual Learning for Image Recognition},
  booktitle = {CVPR},
  URL = {https://arxiv.org/abs/1512.03385v1}
}
@book{knuth1984,
  title = {The {TeX}book: A {Nested {Brace}} Title},
  publisher = ieee # " Press",
  note = "quoted with {braces, and} a comma"
}
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, status, ctype, body):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path == "/api/schema":
            return self.send(200, "application/json", json.dumps(SCHEMA).encode())
        doi = path.lstrip("/")
        if doi in CSL:
            return self.send(200, "application/vnd.citationstyles.csl+json", json.dumps(CSL[doi]).encode())
        if doi == "10.9999/html":
            return self.send(200, "text/html", b"<html>landing page</html>")
        self.send(404, "text/plain", b"DOI not found")


class DoiToItemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        env = {k: v for k, v in os.environ.items() if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
        cls.env = {**env, "DOI_BASE_URL": cls.base, "no_proxy": "127.0.0.1,localhost"}
        spec = importlib.util.spec_from_file_location("doi_to_item", SCRIPT)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def run_script(self, *args, stdin=None, base=None):
        return subprocess.run([sys.executable, str(SCRIPT), "--base-url", base or self.base, *args],
                              input=stdin, capture_output=True, text=True, env=self.env)

    def lines(self, text):
        """JSON lines only; the script's GET logs on stderr are skipped."""
        return [json.loads(ln) for ln in text.splitlines() if ln.startswith(("{", "["))]

    # --- v1 -------------------------------------------------------------------

    def test_v1_single_mode_unchanged(self):
        out = self.tmp / "item.json"
        proc = self.run_script("--doi", "10.1109/JBHI.2022.3142076", "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["code"], "ok")
        self.assertEqual(report["out"], str(out))
        self.assertEqual(report["itemType"], "journalArticle")
        item = json.loads(out.read_text())
        self.assertEqual(item["DOI"], "10.1109/JBHI.2022.3142076")
        self.assertEqual(item["creators"][0]["lastName"], "Liu")
        self.assertEqual(item["libraryCatalog"], "DOI.org (Crossref)")
        self.assertNotIn("slug", item)

    def test_v1_not_found(self):
        proc = self.run_script("--doi", "10.9999/missing", "--out", str(self.tmp / "x.json"))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["code"], "not_found")

    def test_out_needs_exactly_one_doi(self):
        proc = self.run_script("--doi", "10.1109/CVPR.2016.90", "--doi", "10.9999/twin", "--out", str(self.tmp / "x.json"))
        self.assertEqual(proc.returncode, 2)
        proc = self.run_script("-i")
        self.assertEqual(proc.returncode, 2)

    # --- stream: inputs ---------------------------------------------------------

    def test_repeated_doi_to_jsonl(self):
        proc = self.run_script("--doi", "10.1109/JBHI.2022.3142076", "--doi", "arXiv:2006.11239")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = self.lines(proc.stdout)
        self.assertEqual([r["slug"] for r in rows], ["liu2022progressive", "ho2020denoising"])
        self.assertEqual(rows[0]["id"], "10.1109/JBHI.2022.3142076")
        self.assertEqual(rows[1]["item"]["itemType"], "preprint")
        self.assertEqual(rows[1]["item"]["archiveID"], "arXiv:2006.11239")
        self.assertNotIn("code", rows[0])
        summary = self.lines(proc.stderr)[-1]
        self.assertEqual(summary, {"summary": {"total": 2, "ok": 2, "skipped": 0, "failed": 0}})

    def test_stdin_identifier_lines_and_records(self):
        proc = self.run_script(stdin="# list\n10.1109/CVPR.2016.90\tresnet\n\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        row = self.lines(proc.stdout)[0]
        self.assertEqual((row["slug"], row["citationKey"]), ("resnet", "resnet"))
        self.assertEqual(row["item"]["itemType"], "conferencePaper")
        self.assertEqual(row["item"]["proceedingsTitle"], "2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)")

        proc = self.run_script(stdin='{"id": "10.1109/CVPR.2016.90", "slug": "mine", "tags": [{"tag": "x", "type": 0}]}\n')
        row = self.lines(proc.stdout)[0]
        self.assertEqual(row["slug"], "mine")
        self.assertEqual(row["tags"], [{"tag": "x", "type": 0}])
        self.assertIn("item", row)

        proc = self.run_script(stdin='[{"id": "10.1109/CVPR.2016.90"}, {"id": "10.9999/twin"}]')
        self.assertEqual([r["slug"] for r in self.lines(proc.stdout)], ["he2016deep", "liu2022progressive"])

    def test_empty_stdin_is_no_records(self):
        proc = self.run_script(stdin="")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["code"], "no_records")

    def test_record_paths_in_place(self):
        path = self.tmp / "r1.json"
        path.write_text(json.dumps({"slug": "resnet", "id": "10.1109/CVPR.2016.90", "tags": [{"tag": "x", "type": 0}]}))
        proc = self.run_script("-i", str(path))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = self.lines(proc.stdout)
        self.assertEqual(rows[0]["slug"], "resnet")
        self.assertEqual(rows[0]["code"], "ok")
        self.assertEqual(rows[-1]["summary"], {"total": 1, "ok": 1, "skipped": 0, "failed": 0})
        text = path.read_text()
        rec = json.loads(text)
        self.assertEqual(rec["item"]["title"], "Deep Residual Learning for Image Recognition")
        self.assertEqual(rec["tags"], [{"tag": "x", "type": 0}])
        self.assertTrue(text.endswith("}\n") and "\n  " in text, "indent=2 with trailing newline")
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["r1.json"], "no temp files left")

        proc = self.run_script("-i", str(path))
        self.assertEqual(proc.returncode, 0)
        rows = self.lines(proc.stdout)
        self.assertEqual((rows[0]["code"], rows[0]["reason"]), ("skipped", "has_item"))
        self.assertEqual(json.loads(path.read_text()), rec, "unchanged on rerun")

    # --- stream: --ids / --out-dir --------------------------------------------

    def test_ids_file_out_dir_and_rerun(self):
        ids = self.tmp / "ids.txt"
        ids.write_text("# comment\n10.1109/JBHI.2022.3142076\tliu2022jbhi\n\n10.1109/CVPR.2016.90\n10.9999/missing\tghost2020\n")
        out = self.tmp / "records"
        proc = self.run_script("--ids", str(ids), "--out-dir", str(out))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        rows = self.lines(proc.stdout)
        self.assertEqual([(r["slug"], r["code"]) for r in rows[:-1]],
                         [("liu2022jbhi", "ok"), ("he2016deep", "ok"), ("ghost2020", "not_found")])
        self.assertEqual(rows[0]["file"], "liu2022jbhi.json")
        self.assertEqual(rows[-1]["summary"], {"total": 3, "ok": 2, "skipped": 0, "failed": 1})
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["ghost2020.json", "he2016deep.json", "liu2022jbhi.json"])
        liu = json.loads((out / "liu2022jbhi.json").read_text())
        self.assertEqual(liu["citationKey"], "liu2022jbhi")
        self.assertEqual(liu["item"]["itemType"], "journalArticle")
        ghost = json.loads((out / "ghost2020.json").read_text())
        self.assertEqual(ghost["code"], "not_found")
        self.assertEqual(ghost["id"], "10.9999/missing")
        self.assertNotIn("item", ghost)

        # A rerun keeps existing records (even edited ones) and retries only the failed stub.
        liu["note"] = "mine"
        (out / "liu2022jbhi.json").write_text(json.dumps(liu))
        proc = self.run_script("--ids", str(ids), "--out-dir", str(out))
        self.assertEqual(proc.returncode, 1)
        rows = self.lines(proc.stdout)
        self.assertEqual([(r["slug"], r["code"]) for r in rows[:-1]],
                         [("liu2022jbhi", "skipped"), ("he2016deep", "skipped"), ("ghost2020", "not_found")])
        self.assertEqual(rows[0]["reason"], "exists")
        self.assertEqual(rows[-1]["summary"], {"total": 3, "ok": 0, "skipped": 2, "failed": 1})
        self.assertEqual(json.loads((out / "liu2022jbhi.json").read_text())["note"], "mine")

    def test_failure_isolation_and_codes(self):
        proc = self.run_script("--doi", "10.9999/missing", "--doi", "10.9999/html", "--doi", "not-an-id", "--doi", "10.1109/CVPR.2016.90")
        self.assertEqual(proc.returncode, 1)
        rows = self.lines(proc.stdout)
        self.assertEqual([r.get("code") for r in rows], ["not_found", "no_csl_record", "invalid_identifier", None])
        self.assertEqual(rows[0]["slug"], "109999missing")
        self.assertEqual(rows[3]["item"]["title"], "Deep Residual Learning for Image Recognition")
        self.assertEqual(self.lines(proc.stderr)[-1]["summary"]["failed"], 3)

    def test_slug_collisions_and_duplicates(self):
        proc = self.run_script("--doi", "10.1109/JBHI.2022.3142076", "--doi", "10.9999/twin", "--doi", "doi:10.1109/JBHI.2022.3142076")
        rows = self.lines(proc.stdout)
        self.assertEqual([r["slug"] for r in rows], ["liu2022progressive", "liu2022progressive-2", "liu2022progressive"])
        self.assertEqual(self.lines(proc.stderr)[-1]["summary"], {"total": 3, "ok": 2, "skipped": 1, "failed": 0})

    def test_zotero_unreachable_is_exit_2(self):
        proc = self.run_script("--doi", "10.1109/CVPR.2016.90", base="http://127.0.0.1:9")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "zotero_unreachable")

    # --- --bib -------------------------------------------------------------------

    def test_bib_parser(self):
        entries = list(self.mod.parse_bib(BIB))
        self.assertEqual([(t, k) for t, k, _ in entries],
                         [("article", "liuJBHI2022"), ("misc", "ho2020ddpm"), ("inproceedings", "he2016resnet"), ("book", "knuth1984")])
        liu, ho, he, knuth = (f for _, _, f in entries)
        self.assertEqual(liu["title"], "Progressive Residual Learning")
        self.assertEqual(liu["year"], "2022")
        self.assertEqual(self.mod.bib_identifier(liu), "10.1109/JBHI.2022.3142076")
        self.assertEqual(self.mod.bib_identifier(ho), "arXiv:2006.11239")
        self.assertEqual(he["title"], "Deep Residual Learning for Image Recognition", "field names are case-insensitive")
        self.assertEqual(self.mod.bib_identifier(he), "arXiv:1512.03385v1")
        self.assertEqual(knuth["title"], "The TeXbook: A Nested Brace Title")
        self.assertEqual(knuth["publisher"], "ieee Press")
        self.assertEqual(knuth["note"], "quoted with braces, and a comma")
        self.assertIsNone(self.mod.bib_identifier(knuth))

    def test_bib_stream(self):
        bib = self.tmp / "refs.bib"
        bib.write_text(BIB, encoding="utf-8")
        out = self.tmp / "records"
        proc = self.run_script("--bib", str(bib), "--out-dir", str(out))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        rows = self.lines(proc.stdout)
        self.assertEqual([(r["slug"], r["code"]) for r in rows[:-1]],
                         [("liuJBHI2022", "ok"), ("ho2020ddpm", "ok"), ("he2016resnet", "not_found"), ("knuth1984", "no_identifier")])
        knuth = json.loads((out / "knuth1984.json").read_text())
        self.assertEqual(knuth["id"], "The TeXbook: A Nested Brace Title")
        self.assertEqual(knuth["citationKey"], "knuth1984")
        self.assertEqual(knuth["code"], "no_identifier")
        ho = json.loads((out / "ho2020ddpm.json").read_text())
        self.assertEqual(ho["id"], "arXiv:2006.11239")
        self.assertEqual(ho["item"]["itemType"], "preprint")

    def test_derive_slug(self):
        self.assertEqual(self.mod.derive_slug({"creators": [{"lastName": "Müller-Lé"}], "date": "2021-03", "title": "On a New Way"}), "mullerle2021")
        self.assertEqual(self.mod.derive_slug({"creators": [{"name": "Ada Lovelace"}], "date": "1843", "title": "Notes upon the memoir"}), "lovelace1843notes")
        self.assertEqual(self.mod.derive_slug({}), "")


if __name__ == "__main__":
    unittest.main()
