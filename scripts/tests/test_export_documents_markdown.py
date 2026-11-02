"""Exercise the exporter against a real HTTP boundary without application data."""

import contextlib
import hashlib
import importlib.util
import io
import json
import secrets
import stat
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

SCRIPT = Path(__file__).resolve().parents[1] / "export_documents_markdown.py"
SPEC = importlib.util.spec_from_file_location("export_documents_markdown", SCRIPT)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "export"
        self.token = secrets.token_urlsafe(32)
        self.routes = {}
        self.requests = []
        case = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                case.requests.append(self.path)
                if self.headers.get("Authorization") != f"Bearer {case.token}":
                    self.send_response(401)
                    self.end_headers()
                    return
                status, content_type, body = case.routes.get(self.path, (404, "text/plain", "missing"))
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                if status == 302:
                    self.send_header("Location", body)
                self.end_headers()
                self.wfile.write(body.encode())

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.json_route("/api/v1/workspaces/organizations?page=1&page_size=25", [], False)
        self.json_route("/api/v1/documents/search?page=1&page_size=100", [], False)
        self.json_route("/api/v1/workspaces/msp/content-graph/documents?kind=document&page=1&page_size=100", [], False)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def json_route(self, path, results, more):
        self.routes[path] = (200, "application/json", json.dumps({"results": results, "has_more": more}))

    def run_export(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", {"TEKDOCS_API_TOKEN": self.token}):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = exporter.main(["--url", self.url, "--output", str(self.output)])
        self.assertNotIn(self.token, out.getvalue() + err.getvalue())
        return code

    def test_mixed_documents_pagination_and_private_collision_safe_files(self):
        legacy, native, content, org = (str(uuid4()) for _ in range(4))
        self.json_route("/api/v1/workspaces/organizations?page=1&page_size=25", [{"id": org}], True)
        self.json_route("/api/v1/workspaces/organizations?page=2&page_size=25", [], False)
        self.json_route("/api/v1/documents/search?page=1&page_size=100", [
            {"id": legacy, "title": "../Same title", "content_authority": "legacy"}], True)
        self.json_route("/api/v1/documents/search?page=2&page_size=100", [
            {"id": native, "content_id": content, "title": "../Same title", "content_authority": "repository"}], False)
        self.json_route(f"/api/v1/workspaces/organizations/{org}/documents/search?page=1&page_size=100", [], False)
        self.json_route(
            f"/api/v1/workspaces/organizations/{org}/content-graph/documents?kind=document&page=1&page_size=100",
            [], False,
        )
        text = "# Example\n\nReadable text — with a resolved shared block.\n"
        self.routes[f"/api/v1/documents/{legacy}/export?export_format=md"] = (200, "text/markdown; charset=utf-8", text)
        self.routes[f"/api/v1/workspaces/msp/content-graph/documents/{content}"] = (
            200, "application/json", json.dumps({"markdown": text, "findings": []}))
        self.assertEqual(self.run_export(), 0)
        index = json.loads((self.output / "index.json").read_text())
        self.assertTrue(index["complete"])
        self.assertEqual(len(index["documents"]), 2)
        self.assertEqual(len(list(self.output.glob("*.md"))), 2)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        for entry in index["documents"]:
            path = self.output / entry["file"]
            self.assertEqual(path.read_text(), text)
            self.assertEqual(entry["sha256"], hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.parent, self.output)

    def test_graph_inventory_finds_native_document_missing_from_older_search(self):
        legacy, native, content = (str(uuid4()) for _ in range(3))
        self.json_route("/api/v1/documents/search?page=1&page_size=100", [
            {"id": legacy, "content_id": content, "title": "Same title", "content_authority": "legacy"}], False)
        self.json_route("/api/v1/workspaces/msp/content-graph/documents?kind=document&page=1&page_size=100", [
            {"id": content, "kind": "document", "title": "Same title", "repository_native": False},
            {"id": native, "kind": "document", "title": "Same title", "repository_native": True}], False)
        self.routes[f"/api/v1/documents/{legacy}/export?export_format=md"] = (200, "text/markdown", "Older text\n")
        self.routes[f"/api/v1/workspaces/msp/content-graph/documents/{native}"] = (
            200, "application/json", json.dumps({"markdown": "Native text\n", "findings": []}))
        self.assertEqual(self.run_export(), 0)
        index = json.loads((self.output / "index.json").read_text())
        self.assertEqual(len(index["documents"]), 2)
        self.assertEqual({p.read_text() for p in self.output.glob("*.md")}, {"Older text\n", "Native text\n"})
        self.assertEqual(len(list(self.output.glob("*.md"))), 2)

    def test_partial_failure_keeps_success_and_records_empty_document(self):
        first, second = str(uuid4()), str(uuid4())
        self.json_route("/api/v1/documents/search?page=1&page_size=100", [
            {"id": value, "title": "Example", "content_authority": "legacy"} for value in (first, second)], False)
        self.routes[f"/api/v1/documents/{first}/export?export_format=md"] = (200, "text/markdown", "")
        self.routes[f"/api/v1/documents/{second}/export?export_format=md"] = (409, "text/plain", "private response")
        self.assertEqual(self.run_export(), 1)
        index_text = (self.output / "index.json").read_text()
        index = json.loads(index_text)
        self.assertFalse(index["complete"])
        self.assertTrue(index["documents"][0]["empty"])
        self.assertEqual(len(list(self.output.glob("*.md"))), 1)
        self.assertIn("HTTP 409", index["failures"][0]["error"])
        self.assertNotIn("private response", index_text)

    def test_archived_shadow_is_not_exported_as_a_native_document(self):
        shadow = str(uuid4())
        self.json_route("/api/v1/workspaces/msp/content-graph/documents?kind=document&page=1&page_size=100", [
            {"id": shadow, "kind": "document", "title": "Archived", "repository_native": False}], False)
        self.assertEqual(self.run_export(), 0)
        self.assertEqual(list(self.output.glob("*.md")), [])

    def test_unclassified_graph_entry_cannot_report_complete_export(self):
        self.json_route("/api/v1/workspaces/msp/content-graph/documents?kind=document&page=1&page_size=100", [
            {"id": str(uuid4()), "kind": "document", "title": "Unknown ownership"}], False)
        self.assertEqual(self.run_export(), 1)
        self.assertFalse(json.loads((self.output / "index.json").read_text())["complete"])

    def test_missing_inventory_page_and_stale_index_fail_visibly(self):
        path = "/api/v1/workspaces/msp/content-graph/documents?kind=document&page=1&page_size=100"
        self.routes[path] = (200, "application/json", json.dumps({
            "results": [], "has_more": False, "count": 1,
        }))
        self.assertEqual(self.run_export(), 1)
        index = json.loads((self.output / "index.json").read_text())
        self.assertIn("count does not match", index["failures"][0]["error"])

    def test_stale_repository_index_cannot_report_complete_export(self):
        path = "/api/v1/workspaces/msp/content-graph/documents?kind=document&page=1&page_size=100"
        self.routes[path] = (200, "application/json", json.dumps({
            "results": [], "has_more": False, "accepted_commit": "new", "indexed_commit": "old",
        }))
        self.assertEqual(self.run_export(), 1)
        self.assertFalse(json.loads((self.output / "index.json").read_text())["complete"])

    def test_promoted_document_uses_editable_export_instead_of_unresolved_keys(self):
        doc, content = str(uuid4()), str(uuid4())
        self.json_route("/api/v1/documents/search?page=1&page_size=100", [
            {"id": doc, "content_id": content, "title": "Promoted", "content_authority": "repository"}], False)
        self.routes[f"/api/v1/documents/{doc}/export?export_format=md"] = (
            200, "text/markdown", "# Resolved export\n")
        self.assertEqual(self.run_export(), 0)
        self.assertNotIn(f"/api/v1/workspaces/msp/content-graph/documents/{content}", self.requests)
        self.assertEqual(next(self.output.glob("*.md")).read_text(), "# Resolved export\n")

    def test_discovery_denial_does_not_claim_complete_export(self):
        self.routes["/api/v1/workspaces/organizations?page=1&page_size=25"] = (403, "text/plain", "private")
        self.assertEqual(self.run_export(), 1)
        self.assertFalse(json.loads((self.output / "index.json").read_text())["complete"])

    def test_redirect_is_never_followed(self):
        self.routes["/api/v1/workspaces/organizations?page=1&page_size=25"] = (302, "text/plain", self.url + "/stolen")
        self.assertEqual(self.run_export(), 1)
        self.assertNotIn("/stolen", self.requests)

    def test_existing_directory_is_not_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "index.json"
        sentinel.write_text("original")
        self.assertEqual(self.run_export(), 1)
        self.assertEqual(sentinel.read_text(), "original")
        self.assertEqual(self.requests, [])

    def test_html_login_page_is_a_failure_not_markdown(self):
        doc = str(uuid4())
        self.json_route("/api/v1/documents/search?page=1&page_size=100", [
            {"id": doc, "title": "Example", "content_authority": "legacy"}], False)
        self.routes[f"/api/v1/documents/{doc}/export?export_format=md"] = (200, "text/html", "Login")
        self.assertEqual(self.run_export(), 1)
        self.assertEqual(list(self.output.glob("*.md")), [])

    def test_remote_http_and_embedded_credentials_are_rejected(self):
        for url in ("http://example.com", "https://user:password@example.com", "https://example.com/path"):
            with self.assertRaises(exporter.ExportError):
                exporter.Client(url, self.token)


if __name__ == "__main__":
    unittest.main()
