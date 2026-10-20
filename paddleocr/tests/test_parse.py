# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "opencv-python-headless", "pypdfium2"]
# ///
"""Tests for scripts/parse.py: page ranges, input resolution, the raw record of a page, the backend and the start-up
path (no GPU needed). Checks, figures and the record have their own tests."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "parse.py"
spec = importlib.util.spec_from_file_location("parse", SCRIPT)
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


class PageRanges(unittest.TestCase):
    def test_all_pages_by_default(self):
        self.assertEqual(P.parse_pages(None, 3), [1, 2, 3])

    def test_ranges_lists_and_open_end(self):
        self.assertEqual(P.parse_pages("1-3,8", 10), [1, 2, 3, 8])
        self.assertEqual(P.parse_pages("9-", 11), [9, 10, 11])
        self.assertEqual(P.parse_pages("2,2,1", 5), [1, 2])

    def test_clipped_to_page_count(self):
        self.assertEqual(P.parse_pages("4-99", 5), [4, 5])

    def test_bad_ranges(self):
        for bad in ("0", "3-1", "a", "1-2-3", "7"):
            with self.assertRaises(ValueError, msg=bad):
                P.parse_pages(bad, 5)

    def test_natural_order(self):
        names = ["p10.png", "p2.png", "p1.png"]
        self.assertEqual(sorted(names, key=P.natural_key), ["p1.png", "p2.png", "p10.png"])


class Inputs(unittest.TestCase):
    def test_not_found(self):
        self.assertEqual(P.resolve_input("/no/such/file.pdf", None)["error"], "not_found")

    def test_unsupported_file_and_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            txt = Path(d) / "notes.txt"
            txt.write_text("x")
            self.assertEqual(P.resolve_input(str(txt), None)["error"], "unsupported_input")
            empty = Path(d) / "empty"
            empty.mkdir()
            self.assertEqual(P.resolve_input(str(empty), None)["error"], "unsupported_input")

    def test_image_directory_is_one_document(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("page10.png", "page2.png", "page1.jpg", "readme.md"):
                (Path(d) / name).write_bytes(b"")
            doc = P.resolve_input(d, "2-3")
            self.assertEqual(doc["kind"], "images")
            self.assertEqual([f.name for f in doc["files"]], ["page1.jpg", "page2.png", "page10.png"])
            self.assertEqual((doc["page_count"], doc["pages"]), (3, [2, 3]))
            self.assertEqual(P.resolve_input(d, "5")["error"], "bad_pages")


class RawPage(unittest.TestCase):
    def test_blocks_as_the_model_gave_them(self):
        res = SimpleNamespace(json={"res": {"width": 1224, "height": 1584, "parsing_res_list": [
            {"block_label": "header", "block_content": "Journal", "block_bbox": [76, 45, 146, 68], "block_id": 0,
             "group_id": 0, "block_polygon_points": [[76, 45], [146, 45], [146, 68], [76, 68]]},
            {"block_label": "text", "block_content": "", "block_bbox": [607, 1302, 1126, 1424], "block_id": 1,
             "group_id": 0, "block_polygon_points": [[607, 1302], [1126, 1310], [1126, 1424], [607, 1424]]}]}})
        info, blocks = P.raw_page(res, 4, 2.0, [["image", 0.91, 1, 2, 3, 4]], False)
        self.assertEqual(info, {"page": 4, "image_size": [1224, 1584], "scale": 2.0, "layout": [["image", 0.91, 1, 2, 3, 4]]})
        self.assertEqual(blocks[0], {"id": "p4-0", "label": "header", "box": [76, 45, 146, 68], "text": "Journal"})
        self.assertEqual((blocks[1]["group"], len(blocks[1]["polygon"])), ("p4-0", 4))

    def test_without_layout_boxes_and_photo(self):
        res = SimpleNamespace(json={"res": {"width": 10, "height": 20, "parsing_res_list": []}})
        info, blocks = P.raw_page(res, 1, 1.0, None, True)
        self.assertEqual((info, blocks), ({"page": 1, "image_size": [10, 20], "scale": 1.0, "photo": True}, []))


class Stored(unittest.TestCase):
    def test_current_record(self):
        args = SimpleNamespace(charts=False, figure_text=False, photo=False)
        doc = {"sha": "abc", "pages": [1, 2]}
        old = {"format": 3, "source": {"sha256": "abc", "pages": [1, 2]}, "run": {"options": P.options_of(args)}}
        self.assertTrue(P.current(old, doc, args))
        self.assertFalse(P.current({**old, "format": 2}, doc, args))
        self.assertFalse(P.current(old, {**doc, "pages": [1]}, args))
        self.assertFalse(P.current(old, doc, SimpleNamespace(charts=True, figure_text=False, photo=False)))

    def test_older_format_moved_aside(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "paper"
            folder.mkdir()
            (folder / "paper.md").write_text("fixed by hand")
            moved = P.archive(folder)
            self.assertEqual((moved.name, (moved / "paper.md").read_text(), folder.exists()), ("paper.format2", "fixed by hand", False))


class LibraryPath(unittest.TestCase):
    def test_toolkit_directories_are_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            toolkit, other = Path(d) / "cuda-12.8" / "lib64", Path(d) / "wsl"
            toolkit.mkdir(parents=True)
            other.mkdir()
            (toolkit / "libcudart.so.12.8.90").write_bytes(b"")
            (other / "libcuda.so.1").write_bytes(b"")
            self.assertEqual(P.without_cuda_toolkit(f"{toolkit}:{other}::{toolkit}"), f"{other}:")
            self.assertIsNone(P.without_cuda_toolkit(f"{toolkit}:{toolkit}:"))
            self.assertEqual(P.without_cuda_toolkit(f"{other}:/no/such/dir"), f"{other}:/no/such/dir")


class Backend(unittest.TestCase):
    def test_choice(self):
        serve = "/skills/vllm-serve/scripts/serve.py"
        self.assertEqual(P.choose_backend("auto", None, serve)[0], "vllm")
        self.assertEqual(P.choose_backend("auto", None, None)[0], "native")
        self.assertEqual(P.choose_backend("native", None, serve)[0], "native")
        self.assertEqual(P.choose_backend("vllm", None, serve)[0], "vllm")
        self.assertEqual(P.choose_backend("auto", "http://127.0.0.1:8118/v1", None)[0], "server")

    def test_served_model_name_read_from_the_server(self):
        # 2026-10: a server started as `vllm serve PaddlePaddle/PaddleOCR-VL-1.6` answered 404 to the client's
        # default name PaddleOCR-VL-1.6-0.9B; --vl-server now passes the name the server lists
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class Models(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200 if self.path == "/v1/models" else 404)
                self.end_headers()
                self.wfile.write(json.dumps({"data": [{"id": "PaddlePaddle/PaddleOCR-VL-1.6"}]}).encode())

            def log_message(self, *a):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Models)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/v1"
            self.assertEqual(P.served_models(url), ["PaddlePaddle/PaddleOCR-VL-1.6"])
            self.assertEqual(P.served_models(url + "x"), None)
        finally:
            server.shutdown()

    def test_vllm_serve_found(self):
        old = os.environ.pop("VLLM_SERVE", None)
        try:
            beside = SCRIPT.resolve().parents[2] / "vllm-serve" / "scripts" / "serve.py"
            self.assertEqual(P.find_serve(), str(beside) if beside.exists() else None)
            os.environ["VLLM_SERVE"] = "/somewhere/serve.py"
            self.assertEqual(P.find_serve(), "/somewhere/serve.py")
        finally:
            os.environ.pop("VLLM_SERVE", None)
            if old is not None:
                os.environ["VLLM_SERVE"] = old


class StartUp(unittest.TestCase):
    def test_missing_tool_environment(self):
        env = dict(os.environ, PADDLEOCR_PYTHON="/no/such/python")
        out = subprocess.run([sys.executable, str(SCRIPT), "x.pdf", "-o", "out"], capture_output=True, text=True, env=env)
        if out.returncode == 0 or '"paddleocr_missing"' not in out.stdout:
            try:
                import paddleocr  # noqa: F401 - running inside the tool environment itself
                self.skipTest("paddleocr importable here")
            except ImportError:
                pass
        self.assertEqual(out.returncode, 2)
        self.assertEqual(json.loads(out.stdout)["error"], "paddleocr_missing")


if __name__ == "__main__":
    unittest.main()
