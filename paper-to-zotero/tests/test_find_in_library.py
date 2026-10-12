# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/find_in_library.py against a minimal local-API mock (items search, item, children, collections)."""

import http.server
import json
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "find_in_library.py"
LIB = "/api/users/0"

A, ATT, B, C, D, E, F = "AAAAAAA1", "AAAAATT1", "BBBBBBB1", "CCCCCCC1", "DDDDDDD1", "EEEEEEE1", "FFFFFFF1"
ITEMS = {
    A: {"key": A, "version": 894, "data": {
        "key": A, "version": 894, "itemType": "journalArticle",
        "title": "Progressive Residual Learning With Memory Upgrade for Ultrasound Image Blind Super-Resolution",
        "date": "2022-09", "DOI": "10.1109/JBHI.2022.3142076", "url": "https://doi.org/10.1109/JBHI.2022.3142076",
        "citationKey": "liuProgressiveResidualLearning2022", "collections": ["C1AAAAAA"], "tags": [{"tag": "JBHI", "type": 0}],
        "dateAdded": "2024-03-01T08:00:00Z"}},
    ATT: {"key": ATT, "version": 892, "data": {
        "key": ATT, "version": 892, "itemType": "attachment", "parentItem": A, "title": "PDF", "linkMode": "imported_url",
        "contentType": "application/pdf", "filename": "liu.pdf", "md5": "abc123"}},
    B: {"key": B, "version": 10, "data": {
        "key": B, "version": 10, "itemType": "preprint", "title": "Denoising Diffusion Probabilistic Models", "date": "2020",
        "DOI": "", "archiveID": "arXiv:2006.11239", "url": "https://arxiv.org/abs/2006.11239v2", "citationKey": "ho2020denoising",
        "collections": [], "tags": [], "dateAdded": "2025-01-02T03:04:05Z"}},
    C: {"key": C, "version": 11, "data": {
        "key": C, "version": 11, "itemType": "conferencePaper", "title": "Deep Residual Learning for Image Recognition",
        "date": "2016", "DOI": "", "url": "", "citationKey": "dupkey", "collections": [], "tags": [],
        "dateAdded": "2026-10-12T09:00:00Z"}},
    D: {"key": D, "version": 12, "data": {
        "key": D, "version": 12, "itemType": "journalArticle", "title": "Something Else Entirely", "date": "2019",
        "DOI": "", "citationKey": "dupkey", "collections": [], "tags": []}},
    E: {"key": E, "version": 13, "data": {
        "key": E, "version": 13, "itemType": "journalArticle", "title": "Deep Residual Learning for Image Recognition: Extended",
        "date": "2017", "DOI": "", "citationKey": "", "collections": [], "tags": []}},
    F: {"key": F, "version": 14, "data": {
        "key": F, "version": 14, "itemType": "preprint", "title": "Pair Paper Title", "date": "2024",
        "DOI": "10.48550/arXiv.2401.00001", "archiveID": "arXiv:2401.00001", "url": "https://arxiv.org/abs/2401.00001",
        "citationKey": "pair2024preprint", "collections": [], "tags": [], "dateAdded": "2024-01-05T00:00:00Z"}},
}
COLLECTIONS = [
    {"key": "C1AAAAAA", "version": 1, "data": {"key": "C1AAAAAA", "name": "医疗图像", "parentCollection": False}},
    {"key": "C2AAAAAA", "version": 2, "data": {"key": "C2AAAAAA", "name": "超声挑战赛", "parentCollection": "C1AAAAAA"}},
]


class Handler(http.server.BaseHTTPRequestHandler):
    requests = []
    search_sees_citekey = True

    def log_message(self, *a):
        pass

    def send_json(self, obj, status=200, total=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if total is not None:
            self.send_header("Total-Results", str(total))
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def paginate(self, rows, q):
        start, limit = int(q.get("start", ["0"])[0]), int(q.get("limit", ["25"])[0])
        self.send_json(rows[start:start + limit], total=len(rows))

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        path, q = url.path, urllib.parse.parse_qs(url.query)
        Handler.requests.append((path, {k: v[0] for k, v in q.items()}))
        parts = path.split("/")
        if path == f"{LIB}/collections":
            return self.paginate(COLLECTIONS, q)
        if len(parts) == 7 and parts[6] == "children":
            key = parts[5]
            rows = [it for it in ITEMS.values() if it["data"].get("parentItem") == key] if key in ITEMS else list(ITEMS.values())
            return self.paginate(rows, q)
        if len(parts) == 6 and parts[5] != "top":
            it = ITEMS.get(parts[5])
            return self.send_json(it) if it else self.send_json("Not found", 404)
        rows = list(ITEMS.values())
        if path.endswith("/top"):
            rows = [it for it in rows if not it["data"].get("parentItem")]
        if "q" in q:
            needle = q["q"][0].casefold()
            mode = q.get("qmode", ["titleCreatorYear"])[0]

            def hay(it):
                d = it["data"]
                if mode == "everything":
                    keys = [k for k in d if k != "citationKey" or Handler.search_sees_citekey]
                elif mode == "fields":
                    keys = ["title", "DOI", "archiveID", "url", "extra"]
                else:
                    keys = ["title", "date"]
                return [d[k] for k in keys if isinstance(d.get(k), str)]

            rows = [it for it in rows if any(needle in h.casefold() for h in hay(it))]
        return self.paginate(rows, q)


class FindInLibraryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        Handler.requests.clear()
        Handler.search_sees_citekey = True
        self.tmp = Path(tempfile.mkdtemp())

    def run_script(self, *args, stdin=None, base=None):
        return subprocess.run([sys.executable, str(SCRIPT), "--base-url", base or self.base, *args],
                              input=stdin, capture_output=True, text=True)

    def lines(self, text):
        return [json.loads(ln) for ln in text.splitlines() if ln.strip()]

    def write(self, name, obj):
        path = self.tmp / name
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    # --- v1 single lookups --------------------------------------------------------

    def test_v1_doi_found_with_citation_key_and_md5(self):
        proc = self.run_script("--doi", "https://doi.org/10.1109/JBHI.2022.3142076")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["code"], "found")
        match = out["matches"][0]
        self.assertEqual(match["key"], A)
        self.assertEqual(match["citationKey"], "liuProgressiveResidualLearning2022")
        self.assertEqual(match["attachments"][0]["md5"], "abc123")
        self.assertEqual(match["collections"], ["医疗图像"])
        self.assertEqual(out["searched"][0]["qmode"], "fields")

    def test_v1_not_found_arxiv_and_near(self):
        proc = self.run_script("--doi", "10.9999/nothing")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["code"], "not_found")
        proc = self.run_script("--arxiv", "2006.11239v3")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["matches"][0]["key"], B)
        proc = self.run_script("--title", "Something Else")
        self.assertEqual(proc.returncode, 1)
        out = json.loads(proc.stdout)
        self.assertEqual(out["code"], "near_match")
        self.assertEqual(out["near_matches"][0]["key"], D)

    # --- --key / --cite ----------------------------------------------------------

    def test_key_lookup(self):
        proc = self.run_script("--key", A)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual((out["code"], out["key"], out["citationKey"]), ("found", A, "liuProgressiveResidualLearning2022"))
        self.assertEqual(out["numAttachments"], 1)
        proc = self.run_script("--key", "GONE1234")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["code"], "not_found")

    def test_cite_search_hit_then_fallback_scan(self):
        proc = self.run_script("--cite", "ho2020denoising")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["key"], B)
        self.assertEqual(Handler.requests[0], (f"{LIB}/items", {"q": "ho2020denoising", "qmode": "everything", "limit": "50"}))
        self.assertFalse(any(p == f"{LIB}/items/top" for p, _ in Handler.requests))

        Handler.search_sees_citekey = False
        Handler.requests.clear()
        proc = self.run_script("--cite", "ho2020denoising")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["key"], B)
        self.assertTrue(any(p == f"{LIB}/items/top" for p, _ in Handler.requests), "fell back to the scan")

    def test_cite_not_found_and_ambiguous(self):
        proc = self.run_script("--cite", "nobody")
        self.assertEqual(proc.returncode, 1)
        out = json.loads(proc.stdout)
        self.assertEqual((out["code"], out["cite"]), ("cite_not_found", "nobody"))
        proc = self.run_script("--cite", "dupkey")
        self.assertEqual(proc.returncode, 1)
        out = json.loads(proc.stdout)
        self.assertEqual(out["code"], "cite_ambiguous")
        self.assertEqual(out["keys"], [C, D])

    def test_single_excludes_stream_flags(self):
        self.assertEqual(self.run_script("--key", A, "-i").returncode, 2)
        self.assertEqual(self.run_script("-i").returncode, 2)

    # --- record stream -----------------------------------------------------------

    def records(self):
        return [
            self.write("r1.json", {"slug": "r1", "item": {"itemType": "journalArticle", "DOI": "10.1109/JBHI.2022.3142076", "title": "Progressive"}}),
            self.write("r2.json", {"slug": "r2", "item": {"itemType": "conferencePaper", "DOI": "10.1109/CVPR.2016.90",
                                                          "title": "Deep Residual Learning for Image Recognition"}}),
            self.write("r3.json", {"slug": "r3", "item": {"itemType": "preprint", "archiveID": "arXiv:2006.11239", "title": "DDPM"}}),
            self.write("r4.json", {"slug": "r4", "item": {"itemType": "journalArticle", "title": "Something Else"}}),
            self.write("r5.json", {"slug": "r5", "item": {"itemType": "journalArticle", "title": "Nothing like this at all"}}),
            self.write("r6.json", {"slug": "r6", "id": "10.1/none"}),
        ]

    def test_stream_dedupe_to_stdout(self):
        paths = self.records()
        proc = self.run_script(*map(str, paths))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        rows = self.lines(proc.stdout)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["found"]["key"], A)
        self.assertEqual(rows[0]["found"]["code"], "found")
        self.assertEqual(rows[0]["found"]["citationKey"], "liuProgressiveResidualLearning2022")
        self.assertEqual(rows[0]["found"]["collections"], ["C1AAAAAA"])
        self.assertEqual(rows[0]["found"]["attachments"][0]["md5"], "abc123")
        self.assertTrue(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", rows[0]["found"]["checked_at"]))
        self.assertEqual((rows[0]["found"]["matched_by"], rows[0]["found"]["dateAdded"], rows[0]["found"]["date"]),
                         ("doi", "2024-03-01T08:00:00Z", "2022-09"))
        self.assertEqual(rows[1]["found"]["key"], C, "DOI miss, then exact title")
        self.assertEqual((rows[1]["found"]["matched_by"], rows[1]["found"]["dateAdded"]), ("title", "2026-10-12T09:00:00Z"))
        self.assertEqual(rows[2]["found"]["key"], B, "arXiv id from archiveID")
        self.assertEqual(rows[2]["found"]["matched_by"], "arxiv")
        self.assertEqual((rows[3]["found"]["code"], rows[3]["found"]["key"]), ("near_match", D))
        self.assertNotIn("matched_by", rows[3]["found"], "near_match is told apart by its code")
        self.assertEqual(rows[3]["found"]["dateAdded"], "", "an item without dateAdded gives an empty string")
        self.assertNotIn("readback", rows[0])
        self.assertNotIn("found", rows[4], "not_found leaves the record untouched")
        self.assertEqual(rows[4], {"slug": "r5", "item": {"itemType": "journalArticle", "title": "Nothing like this at all"}})
        self.assertNotIn("found", rows[5])
        self.assertEqual(self.lines(proc.stderr)[-1], {"summary": {"total": 6, "ok": 5, "skipped": 0, "failed": 1}})
        self.assertNotIn("found", json.loads(paths[0].read_text()), "files untouched without -i")

    def test_stream_in_place_and_skip(self):
        paths = self.records()
        before = paths[4].read_text()
        proc = self.run_script("-i", *map(str, paths))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        rows = self.lines(proc.stdout)
        self.assertEqual([(r["slug"], r["code"]) for r in rows[:-1]],
                         [("r1", "found"), ("r2", "found"), ("r3", "found"), ("r4", "near_match"), ("r5", "not_found"), ("r6", "no_item")])
        self.assertEqual((rows[0]["key"], rows[0]["matched_by"]), (A, "doi"))
        self.assertEqual(rows[-1]["summary"], {"total": 6, "ok": 5, "skipped": 0, "failed": 1})
        self.assertEqual(json.loads(paths[0].read_text())["found"]["key"], A)
        self.assertEqual(paths[4].read_text(), before, "not_found record not rewritten")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), [f"r{i}.json" for i in range(1, 7)], "no temp files")

        proc = self.run_script("-i", str(paths[0]), str(paths[4]))
        self.assertEqual(proc.returncode, 0)
        rows = self.lines(proc.stdout)
        self.assertEqual((rows[0]["code"], rows[0]["key"]), ("skipped", A))
        self.assertEqual(rows[1]["code"], "not_found")
        self.assertEqual(rows[2]["summary"], {"total": 2, "ok": 1, "skipped": 1, "failed": 0})

    def test_readback(self):
        s1 = self.write("s1.json", {"slug": "s1", "saved": {"key": A, "version": 1}})
        s2 = self.write("s2.json", {"slug": "s2", "found": {"key": "GONE1234"}, "citationKey": "gone"})
        s3 = self.write("s3.json", {"slug": "s3", "found": {"key": A, "matched_by": "doi"}, "citationKey": "userkey"})
        proc = self.run_script("-i", "--readback", str(s1), str(s2), str(s3))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        rows = self.lines(proc.stdout)
        self.assertEqual([(r["slug"], r["code"]) for r in rows[:-1]], [("s1", "found"), ("s2", "missing_in_library"), ("s3", "found")])
        self.assertEqual(rows[-1]["summary"], {"total": 3, "ok": 2, "skipped": 0, "failed": 1})
        r1 = json.loads(s1.read_text())
        self.assertNotIn("found", r1, "an item created this run is not `found` (B#3)")
        self.assertEqual((r1["readback"]["key"], r1["readback"]["version"]), (A, 894))
        self.assertEqual((r1["readback"]["dateAdded"], r1["readback"]["date"]), ("2024-03-01T08:00:00Z", "2022-09"))
        self.assertEqual(r1["readback"]["attachments"][0]["md5"], "abc123")
        self.assertNotIn("matched_by", r1["readback"])
        self.assertEqual(r1["citationKey"], "liuProgressiveResidualLearning2022")
        self.assertEqual(r1["saved"], {"key": A, "version": 1}, "saved untouched")
        r2 = json.loads(s2.read_text())
        self.assertEqual(r2["found"], {"key": "GONE1234"}, "found left alone on 404")
        self.assertNotIn("readback", r2)
        self.assertTrue(r2["blocker"].startswith("missing_in_library: item GONE1234"))
        r3 = json.loads(s3.read_text())
        self.assertEqual(r3["found"], {"key": A, "matched_by": "doi"}, "found is never overwritten by --readback")
        self.assertEqual(r3["citationKey"], "userkey", "the given key stays on the record")
        self.assertEqual(r3["readback"]["citationKey"], "liuProgressiveResidualLearning2022", "readback carries the library's key")
        self.assertIn("userkey", proc.stderr)

    def test_readback_404_drops_stale_readback_only(self):
        rec = {"slug": "s4", "saved": {"key": "GONE5678", "version": 3}, "found": {"key": "GONE5678", "matched_by": "title"},
               "readback": {"key": "GONE5678", "version": 3, "attachments": []}}
        path = self.write("s4.json", rec)
        proc = self.run_script("-i", "--readback", str(path))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.lines(proc.stdout)[0], {"slug": "s4", "code": "missing_in_library", "key": "GONE5678"})
        after = json.loads(path.read_text())
        self.assertNotIn("readback", after)
        self.assertEqual((after["saved"], after["found"]), (rec["saved"], rec["found"]))
        self.assertIn("GONE5678", after["blocker"])

    def test_readback_from_stdin_to_stdout(self):
        proc = self.run_script("--readback", stdin=json.dumps({"slug": "x", "saved": {"key": B, "version": 1}}))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        row = self.lines(proc.stdout)[0]
        self.assertEqual((row["readback"]["key"], row["readback"]["citationKey"]), (B, "ho2020denoising"))
        self.assertNotIn("found", row)

    def test_stream_stdin_for_duplicate_check(self):
        """create_item pipes its pending records in and reads found.matched_by / found.dateAdded from stdout."""
        recs = [{"slug": "a", "item": {"DOI": "10.1109/JBHI.2022.3142076", "title": "x"}},
                {"slug": "b", "item": {"archiveID": "arXiv:2006.11239v2", "title": "y"}},
                {"slug": "c", "item": {"title": "Deep Residual Learning for Image Recognition"}},
                {"slug": "d", "item": {"title": "Nothing like this at all"}}]
        proc = self.run_script(stdin="\n".join(json.dumps(r) for r in recs) + "\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = self.lines(proc.stdout)
        self.assertEqual([r["slug"] for r in rows], ["a", "b", "c", "d"], "stdout is one record per line, nothing else")
        self.assertEqual([(r["found"]["matched_by"], r["found"]["dateAdded"]) for r in rows[:3]],
                         [("doi", "2024-03-01T08:00:00Z"), ("arxiv", "2025-01-02T03:04:05Z"), ("title", "2026-10-12T09:00:00Z")])
        self.assertNotIn("found", rows[3])
        self.assertEqual(self.lines(proc.stderr)[-1], {"summary": {"total": 4, "ok": 4, "skipped": 0, "failed": 0}})

    # --- preprint / published pair and distinct_from -------------------------------

    def stream(self, *recs):
        proc = self.run_script(stdin="\n".join(json.dumps(r) for r in recs) + "\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return self.lines(proc.stdout)

    def test_published_record_hitting_only_the_preprint_is_a_near_match(self):
        published = {"slug": "pub", "item": {"itemType": "journalArticle", "DOI": "10.1000/pub.1", "title": "Pair Paper Title",
                                            "extra": "arXiv: 2401.00001"}}
        row = self.stream(published)[0]
        self.assertEqual((row["found"]["code"], row["found"]["key"], row["found"]["matched_by"]), ("near_match", F, "arxiv"))
        self.assertEqual(row["found"]["reason"],
                         "preprint/published pair: the library item matched by arXiv id only; the record's DOI is 10.1000/pub.1")
        self.assertEqual(row["found"]["dateAdded"], "2024-01-05T00:00:00Z")

        path = self.write("pub.json", published)
        proc = self.run_script("-i", str(path))
        summary = self.lines(proc.stdout)[0]
        self.assertEqual((summary["code"], summary["matched_by"]), ("near_match", "arxiv"))
        self.assertIn("ask the user", summary["hint"])

    def test_same_title_with_another_doi_is_a_near_match(self):
        """The library's preprint (10.48550 DOI) has the published record's exact title: not a plain found."""
        published = {"slug": "pub", "item": {"itemType": "journalArticle", "DOI": "10.1000/pub.2", "title": "Pair Paper Title"}}
        no_doi = {"slug": "ddpm", "item": {"itemType": "conferencePaper", "DOI": "10.1000/ddpm",
                                           "title": "Denoising Diffusion Probabilistic Models"}}
        r = self.run_script(stdin="\n".join(json.dumps(x) for x in (published, no_doi)))
        out = [json.loads(line) for line in r.stdout.splitlines()]
        self.assertEqual((out[0]["found"]["code"], out[0]["found"]["key"]), ("near_match", F))
        self.assertIn("same title, different DOI", out[0]["found"]["reason"])
        self.assertNotIn("matched_by", out[0]["found"])
        # a library item without a DOI of its own is still trusted on the exact title
        self.assertEqual((out[1]["found"]["code"], out[1]["found"]["matched_by"], out[1]["found"]["key"]), ("found", "title", B))

    def test_arxiv_only_records_keep_found(self):
        bare = {"slug": "pre", "item": {"itemType": "preprint", "archiveID": "arXiv:2401.00001", "title": "x"}}
        arxiv_doi = {"slug": "pre2", "item": {"itemType": "preprint", "DOI": "10.48550/arXiv.2401.00001v2", "title": "x"}}
        rows = self.stream(bare, arxiv_doi)
        for row in rows:
            self.assertEqual((row["found"]["code"], row["found"]["key"], row["found"]["matched_by"]), ("found", F, "arxiv"), row["slug"])
            self.assertNotIn("reason", row["found"])

    def test_distinct_from_drops_keys_at_every_tier(self):
        # DOI hit excluded -> title tier (exact match on another item).
        r1 = {"slug": "r1", "distinct_from": [A],
              "item": {"DOI": "10.1109/JBHI.2022.3142076", "title": "Deep Residual Learning for Image Recognition"}}
        # Exact title excluded -> the near match that is left.
        r2 = {"slug": "r2", "distinct_from": [C], "item": {"title": "Deep Residual Learning for Image Recognition"}}
        # Exact and near title hits all excluded -> not found.
        r3 = {"slug": "r3", "distinct_from": [C, E], "item": {"title": "Deep Residual Learning for Image Recognition"}}
        # DOI hit excluded, arXiv hit with the record's own DOI -> pair.
        r4 = {"slug": "r4", "distinct_from": [A], "item": {"DOI": "10.1109/JBHI.2022.3142076", "archiveID": "arXiv:2401.00001",
                                                            "title": "Pair Paper Title"}}
        # arXiv hit excluded -> title tier.
        r5 = {"slug": "r5", "distinct_from": [F], "item": {"archiveID": "arXiv:2401.00001", "title": "Something Else Entirely"}}
        # A single key as a string is accepted too.
        r6 = {"slug": "r6", "distinct_from": A, "item": {"DOI": "10.1109/JBHI.2022.3142076", "title": "Nothing like this at all"}}
        rows = {r["slug"]: r for r in self.stream(r1, r2, r3, r4, r5, r6)}
        self.assertEqual((rows["r1"]["found"]["key"], rows["r1"]["found"]["matched_by"]), (C, "title"))
        self.assertEqual((rows["r2"]["found"]["code"], rows["r2"]["found"]["key"]), ("near_match", E))
        self.assertNotIn("found", rows["r3"])
        self.assertEqual((rows["r4"]["found"]["code"], rows["r4"]["found"]["key"], rows["r4"]["found"]["matched_by"]),
                         ("near_match", F, "arxiv"))
        self.assertEqual((rows["r5"]["found"]["key"], rows["r5"]["found"]["matched_by"]), (D, "title"))
        self.assertNotIn("found", rows["r6"])
        self.assertEqual(rows["r1"]["distinct_from"], [A], "the record keeps its list")

    def test_stdin_forms_and_no_records(self):
        rec = {"slug": "x", "item": {"DOI": "10.1109/JBHI.2022.3142076"}}
        proc = self.run_script(stdin=json.dumps(rec))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.lines(proc.stdout)[0]["found"]["key"], A)
        proc = self.run_script(stdin=json.dumps([rec, rec]))
        self.assertEqual(len(self.lines(proc.stdout)), 2)
        proc = self.run_script(stdin=json.dumps(rec) + "\n" + json.dumps(rec) + "\n")
        self.assertEqual(len(self.lines(proc.stdout)), 2)
        proc = self.run_script(stdin="")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["code"], "no_records")

    def test_cannot_check(self):
        proc = self.run_script("--key", A, base="http://127.0.0.1:9")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "zotero_unreachable")
        proc = self.run_script(str(self.write("r.json", {"slug": "r", "item": {"title": "x"}})), base="http://127.0.0.1:9")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
