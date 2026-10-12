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
                    {"field": "publisher"}, {"field": "place"}, {"field": "series"}, {"field": "ISBN"}, {"field": "ISSN"},
                    {"field": "libraryCatalog"}, {"field": "extra"}],
         "creatorTypes": [{"creatorType": "author", "primary": True}, {"creatorType": "editor"}, {"creatorType": "contributor"}]},
        {"itemType": "bookSection",
         "fields": [{"field": "title"}, {"field": "abstractNote"}, {"field": "bookTitle", "baseField": "publicationTitle"},
                    {"field": "series"}, {"field": "date"}, {"field": "publisher"}, {"field": "place"}, {"field": "pages"},
                    {"field": "ISBN"}, {"field": "DOI"}, {"field": "url"}, {"field": "ISSN"}, {"field": "libraryCatalog"},
                    {"field": "extra"}],
         "creatorTypes": [{"creatorType": "author", "primary": True}, {"creatorType": "editor"}, {"creatorType": "contributor"}]},
        {"itemType": "preprint",
         "fields": [{"field": "title"}, {"field": "abstractNote"}, {"field": "repository", "baseField": "publisher"},
                    {"field": "archiveID", "baseField": "number"}, {"field": "date"}, {"field": "DOI"}, {"field": "url"},
                    {"field": "libraryCatalog"}, {"field": "extra"}],
         "creatorTypes": [{"creatorType": "author", "primary": True}, {"creatorType": "contributor"}]},
    ],
    "csl": {
        "types": {"article-journal": ["journalArticle"], "paper-conference": ["conferencePaper"], "article": ["preprint"],
                  "chapter": ["bookSection"]},
        "fields": {
            "text": {"title": ["title"], "container-title": ["publicationTitle"], "volume": ["volume"], "issue": ["issue"],
                     "page": ["pages"], "DOI": ["DOI"], "URL": ["url"], "ISSN": ["ISSN"], "abstract": ["abstractNote"],
                     "publisher": ["publisher"], "event-title": ["conferenceName"], "publisher-place": ["place"]},
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
    # round 1 of v3: subtitle, arXiv categories, erratum signals, LNCS
    "10.1001/jama.2023.4855": {
        "type": "journal-article", "source": "Crossref", "title": "Randomized Trials vs Real-world Evidence",
        "subtitle": ["How Can Both Inform Decision-making?"], "author": [{"family": "Fang", "given": "Lee"}],
        "issued": {"date-parts": [[2023, 4]]}, "container-title": "JAMA", "page": "1645-1646", "DOI": "10.1001/jama.2023.4855",
        "abstract": "x"},
    "10.48550/arXiv.2105.05537": {
        "type": "article", "title": "Swin-Unet: Unet-like Pure Transformer for Medical Image Segmentation",
        "author": [{"family": "Cao", "given": "Hu"}], "issued": {"date-parts": [[2021]]}, "DOI": "10.48550/ARXIV.2105.05537",
        "publisher": "arXiv", "abstract": "x",
        "categories": ["Image and Video Processing (eess.IV)", "Computer Vision and Pattern Recognition (cs.CV)",
                       "FOS: Electrical engineering, electronic engineering, information engineering",
                       "FOS: Electrical engineering, electronic engineering, information engineering",
                       "Machine Learning (stat.ML)", "Quantum Physics (quant-ph)", "Something New (zz.AB)",
                       "Computer Vision and Pattern Recognition (cs.CV)", "FOS: Computer and information sciences"]},
    "10.1001/jama.erratum": {
        "type": "journal-article", "source": "Crossref", "title": "Error in Author Name", "issued": {"date-parts": [[2026, 9]]},
        "container-title": "JAMA", "page": "804", "DOI": "10.1001/jama.erratum"},
    "10.1007/978-3-319-24574-4_28": {
        "type": "book-chapter", "source": "Crossref", "title": "U-Net: Convolutional Networks for Biomedical Image Segmentation",
        "subtitle": [], "author": [{"family": "Ronneberger", "given": "Olaf"}], "issued": {"date-parts": [[2015]]},
        "container-title": "Lecture Notes in Computer Science", "ISSN": ["0302-9743", "1611-3349"],
        "ISBN": ["9783319245737", "9783319245744"], "page": "234-241", "publisher": "Springer International Publishing",
        "publisher-location": "Cham", "DOI": "10.1007/978-3-319-24574-4_28", "abstract": "x"},
    "10.1007/other-series": {
        "type": "book-chapter", "source": "Crossref", "title": "A Chapter In Some Series", "author": [{"family": "Roe", "given": "Ann"}],
        "issued": {"date-parts": [[2020]]}, "container-title": "Some Book Series", "ISSN": ["1234-5678"], "page": "1-10",
        "DOI": "10.1007/other-series", "abstract": "x"},
    "10.1007/crossref-down": {
        "type": "book-chapter", "source": "Crossref", "title": "A Chapter Whose Crossref Record Fails",
        "author": [{"family": "Poe", "given": "Al"}], "issued": {"date-parts": [[2020]]},
        "container-title": "Lecture Notes in Computer Science", "ISSN": ["0302-9743"], "page": "1-10",
        "DOI": "10.1007/crossref-down", "abstract": "x"},
}
# Crossref REST stand-in (CROSSREF_BASE_URL): DOI -> container-title; a DOI missing here answers 500.
CROSSREF = {
    "10.1007/978-3-319-24574-4_28": ["Lecture Notes in Computer Science",
                                     "Medical Image Computing and Computer-Assisted Intervention \u2013 MICCAI 2015"],
    "10.1007/other-series": ["Some Book Series", "A Volume of Some Book Series"],
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
    requests = []

    def log_message(self, *a):
        pass

    def send(self, status, ctype, body):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(url.path)
        Handler.requests.append((path, dict(urllib.parse.parse_qsl(url.query))))
        if path.startswith("/works/"):
            doi = path[len("/works/"):]
            if doi in CROSSREF:
                body = {"status": "ok", "message-type": "work", "message": {"DOI": doi, "container-title": CROSSREF[doi]}}
                return self.send(200, "application/json", json.dumps(body).encode())
            return self.send(500, "text/plain", b"upstream error")
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
        cls.env = {**env, "DOI_BASE_URL": cls.base, "CROSSREF_BASE_URL": cls.base, "no_proxy": "127.0.0.1,localhost",
                   "PAPER_TO_ZOTERO_CONFIG": str(Path(tempfile.mkdtemp()) / "no-config.json")}
        spec = importlib.util.spec_from_file_location("doi_to_item", SCRIPT)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        Handler.requests.clear()

    def run_script(self, *args, stdin=None, base=None, env=None):
        return subprocess.run([sys.executable, str(SCRIPT), "--base-url", base or self.base, *args],
                              input=stdin, capture_output=True, text=True, env={**self.env, **(env or {})})

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

    # --- v3 round 1: subtitle ---------------------------------------------------

    def test_subtitle_appended(self):
        add = self.mod.add_subtitle
        self.assertEqual(add("Randomized Trials vs Real-world Evidence", ["How Can Both Inform Decision-making?"]),
                         "Randomized Trials vs Real-world Evidence: How Can Both Inform Decision-making?")
        self.assertEqual(add("Main", "Sub Part"), "Main: Sub Part", "a string subtitle works too")
        self.assertEqual(add("Main: Sub Part", ["sub part"]), "Main: Sub Part", "already ends with it")
        self.assertEqual(add("Main \u2014 Sub-Part", ["Sub Part"]), "Main \u2014 Sub-Part", "punctuation does not matter")
        self.assertEqual(add("Does It Work?", ["A <i>Trial</i>"]), "Does It Work? A Trial")
        self.assertEqual(add("Ends With Colon:", ["Sub"]), "Ends With Colon: Sub")
        self.assertEqual(add("Main", []), "Main")
        self.assertEqual(add("Main", ["", "Second"]), "Main: Second", "first non-empty subtitle")
        self.assertEqual(add("Main", None), "Main")

        proc = self.run_script("--doi", "10.1001/jama.2023.4855")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.lines(proc.stdout)[0]["item"]["title"],
                         "Randomized Trials vs Real-world Evidence: How Can Both Inform Decision-making?")

    # --- arXiv categories --------------------------------------------------------

    def test_arxiv_category_mapping(self):
        tags = self.mod.arxiv_category_tags
        self.assertEqual(tags(["Machine Learning (cs.LG)", "Machine Learning (stat.ML)", "FOS: Computer and information sciences",
                               "FOS: Computer and information sciences"]),
                         ["Computer Science - Machine Learning", "Statistics - Machine Learning"])
        self.assertEqual(tags(["Image and Video Processing (eess.IV)", "Statistics Theory (math.ST)", "Medical Physics (physics.med-ph)",
                               "Quantitative Methods (q-bio.QM)", "Computational Finance (q-fin.CP)", "Econometrics (econ.EM)",
                               "Strongly Correlated Electrons (cond-mat.str-el)", "Astrophysics of Galaxies (astro-ph.GA)"]),
                         ["Electrical Engineering and Systems Science - Image and Video Processing", "Mathematics - Statistics Theory",
                          "Physics - Medical Physics", "Quantitative Biology - Quantitative Methods",
                          "Quantitative Finance - Computational Finance", "Economics - Econometrics",
                          "Condensed Matter - Strongly Correlated Electrons", "Astrophysics - Astrophysics of Galaxies"])
        self.assertEqual(tags(["Quantum Physics (quant-ph)", "High Energy Physics - Theory (hep-th)"]),
                         ["Quantum Physics", "High Energy Physics - Theory"], "single-archive categories: the name alone")
        self.assertEqual(tags(["Something New (zz.AB)", "no code at all"]), ["Something New (zz.AB)", "no code at all"],
                         "unknown archive / unparseable: DataCite's wording kept")
        self.assertEqual(tags(None), [])
        self.assertEqual(tags("Machine Learning (cs.LG)"), ["Computer Science - Machine Learning"])

    def test_arxiv_categories_become_type1_tags(self):
        expected = [{"tag": t, "type": 1} for t in (
            "Electrical Engineering and Systems Science - Image and Video Processing",
            "Computer Science - Computer Vision and Pattern Recognition", "Statistics - Machine Learning", "Quantum Physics",
            "Something New (zz.AB)")]
        proc = self.run_script("--doi", "arXiv:2105.05537")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rec = self.lines(proc.stdout)[0]
        self.assertEqual(rec["tags"], expected)
        self.assertNotIn("tags", rec["item"], "stream mode: tags live on the record")
        self.assertNotIn("categories", rec["item"])

        # Existing tags are never overwritten; an empty list counts as none yet.
        proc = self.run_script(stdin=json.dumps({"id": "2105.05537", "tags": [{"tag": "mine", "type": 0}]}))
        self.assertEqual(self.lines(proc.stdout)[0]["tags"], [{"tag": "mine", "type": 0}])
        proc = self.run_script(stdin=json.dumps({"id": "2105.05537", "tags": []}))
        self.assertEqual(self.lines(proc.stdout)[0]["tags"], expected)

        # Only arXiv records: a Crossref DOI gets no tags.
        proc = self.run_script("--doi", "10.1109/CVPR.2016.90")
        self.assertNotIn("tags", self.lines(proc.stdout)[0])

        # v1 single mode has no record: the item carries them.
        out = self.tmp / "item.json"
        proc = self.run_script("--doi", "2105.05537", "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(out.read_text())["tags"], expected)

    # --- erratum warnings --------------------------------------------------------

    def test_erratum_signals(self):
        sig = self.mod.erratum_signals
        authors = [{"family": "A", "given": "B"}]
        self.assertEqual(sig({"title": "Correction to: Deep Nets", "author": authors, "page": "1-12"}, "journalArticle"),
                         ["title starts with 'Correction'"])
        self.assertEqual(sig({"title": "Author Correction: Diagnostics", "author": authors, "article-number": "52"}, "journalArticle"),
                         ["title starts with 'Author Correction'"])
        self.assertEqual(sig({"title": "RETRACTED: A Study", "author": authors}, "journalArticle"), ["title starts with 'RETRACTED'"])
        for t in ("Erratum", "Corrigendum to \u201cX\u201d", "Corrections to \u201cY\u201d", "Retraction Note: Z"):
            self.assertTrue(sig({"title": t, "author": authors}, "journalArticle"), t)
        self.assertEqual(sig({"title": "Correctional Facilities and Health", "author": authors, "page": "1-9"}, "journalArticle"), [])
        self.assertEqual(sig({"title": "Error in Author Name", "page": "804"}, "journalArticle"), ["no authors", "single page '804'"])
        self.assertEqual(sig({"title": "Notice", "author": authors, "page": "E1"}, "journalArticle"), ["single page 'E1'"])
        self.assertEqual(sig({"title": "Notice", "author": authors, "page": "457\u2013457"}, "journalArticle"), ["single page '457\u2013457'"])
        # Article numbers and e-page ranges are ordinary papers.
        for page, extra in (("104336", {"article-number": "104336"}), ("e0360436", {}), ("e2640040", {}), ("e563-e595", {}),
                            ("234-241", {})):
            self.assertEqual(sig({"title": "A Paper", "author": authors, "page": page, **extra}, "journalArticle"), [], page)
        # Page and author signals only for article-like types; titles for every type.
        self.assertEqual(sig({"title": "Edited Volume", "page": "1"}, "book"), [])
        self.assertEqual(sig({"title": "Erratum", "author": authors}, "preprint"), ["title starts with 'Erratum'"])

    def test_erratum_warning_in_record(self):
        proc = self.run_script("--doi", "10.1001/jama.erratum", "--doi", "10.1109/JBHI.2022.3142076")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        erratum, paper = self.lines(proc.stdout)
        notes = [w for w in erratum["warnings"] if w.startswith("possible erratum")]
        self.assertEqual(len(notes), 1)
        self.assertIn("no authors; single page '804'", notes[0])
        self.assertFalse(any(w.startswith("possible erratum") for w in paper.get("warnings", [])))

    # --- LNCS via Crossref -------------------------------------------------------

    def test_lncs_chapter_becomes_conference_paper(self):
        proc = self.run_script("--doi", "10.1007/978-3-319-24574-4_28")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rec = self.lines(proc.stdout)[0]
        item = rec["item"]
        self.assertEqual(item["itemType"], "conferencePaper")
        self.assertEqual(item["proceedingsTitle"], "Medical Image Computing and Computer-Assisted Intervention \u2013 MICCAI 2015")
        self.assertEqual(item["series"], "Lecture Notes in Computer Science")
        self.assertEqual(item["title"], "U-Net: Convolutional Networks for Biomedical Image Segmentation", "subtitle [] adds nothing")
        self.assertEqual((item["pages"], item["ISBN"], item["ISSN"]), ("234-241", "9783319245737, 9783319245744", "0302-9743, 1611-3349"))
        self.assertEqual((item["publisher"], item["place"]), ("Springer International Publishing", "Cham"))
        self.assertFalse(any("probably the series name" in w for w in rec["warnings"]))
        self.assertTrue(any("proceedings series 'Lecture Notes in Computer Science'" in w for w in rec["warnings"]))
        self.assertIn(("/works/10.1007/978-3-319-24574-4_28", {}), Handler.requests, "no config -> no mailto")
        self.assertEqual(sum(1 for p, _ in Handler.requests if p.startswith("/works/")), 1, "one Crossref call")

    def test_lncs_mailto_only_from_config(self):
        cfg = self.tmp / "config.json"
        cfg.write_text(json.dumps({"contact_email": "someone@example.org"}))
        proc = self.run_script("--doi", "10.1007/978-3-319-24574-4_28", env={"PAPER_TO_ZOTERO_CONFIG": str(cfg)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(("/works/10.1007/978-3-319-24574-4_28", {"mailto": "someone@example.org"}), Handler.requests)
        self.assertNotIn("someone@example.org", proc.stdout + proc.stderr, "the address is never printed")

        Handler.requests.clear()
        cfg.write_text(json.dumps({"institution": {}}))
        self.run_script("--doi", "10.1007/978-3-319-24574-4_28", env={"PAPER_TO_ZOTERO_CONFIG": str(cfg)})
        self.assertIn(("/works/10.1007/978-3-319-24574-4_28", {}), Handler.requests)

    def test_lncs_fallbacks_stay_book_section(self):
        proc = self.run_script("--doi", "10.1007/other-series", "--doi", "10.1007/crossref-down")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        other, down = self.lines(proc.stdout)
        self.assertEqual((other["item"]["itemType"], other["item"]["bookTitle"]), ("bookSection", "Some Book Series"))
        self.assertTrue(any("probably the series name" in w and '"A Volume of Some Book Series"' in w for w in other["warnings"]))
        self.assertEqual((down["item"]["itemType"], down["item"]["bookTitle"]), ("bookSection", "Lecture Notes in Computer Science"))
        self.assertTrue(any("probably the series name" in w and "Crossref lookup failed: HTTP 500" in w for w in down["warnings"]))

        # Crossref unreachable: same as now, plus the reason; no failure code.
        proc = self.run_script("--doi", "10.1007/978-3-319-24574-4_28", env={"CROSSREF_BASE_URL": "http://127.0.0.1:9"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rec = self.lines(proc.stdout)[0]
        self.assertNotIn("code", rec)
        self.assertEqual(rec["item"]["itemType"], "bookSection")
        self.assertTrue(any("Crossref lookup failed: network error" in w for w in rec["warnings"]))

    def test_no_crossref_call_for_journal_articles(self):
        self.run_script("--doi", "10.1109/JBHI.2022.3142076")
        self.assertFalse(any(p.startswith("/works/") for p, _ in Handler.requests))

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
