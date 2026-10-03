import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kgupc_toolkit import __version__
from kgupc_toolkit.resources import package_digest
from kgupc_pol2dom.api import PolygonError
from kgupc_pol2dom.importer import fetch_problem, import_contest, load_config


class FakePolygon:
    def __init__(self):
        self.calls = []
        self.problem = {"id": 42, "name": "parking-fee-system", "owner": "tester", "revision": 7,
                        "workingCopyRevision": 7, "modified": False}
        self.missing_language = False
        self.changed = False
        self.failed_answer = False

    def request(self, method, **parameters):
        self.calls.append((method, parameters))
        if method in ("problems.list", "contest.problems"):
            value = self.problem.copy()
            if self.changed and len([call for call in self.calls if call[0] == "problems.list"]) > 1:
                value["revision"] = 8
            return [value]
        if method == "problem.info":
            return {"timeLimit": 1000, "memoryLimit": 256, "inputFile": "", "outputFile": "", "interactive": False}
        if method == "problem.statements":
            return {} if self.missing_language else {"korean": {"name": "Title & test", "legend": "Story",
                        "input": "Input", "output": "Output", "notes": "Explanation"}}
        if method == "problem.tests":
            return [{"index": 1, "useInStatements": True, "inputBase64": base64.b64encode(b"1  2\r\n").decode()},
                    {"index": 2, "useInStatements": True, "inputForStatement": "", "outputForStatement": "DISPLAY\n"},
                    {"index": 3, "useInStatements": False}]
        if method == "problem.testAnswer":
            if self.failed_answer:
                raise PolygonError("Answer not generated")
            return b"3\r\n"
        if method == "problem.statementResources":
            return [{"name": "image.png"}]
        if method == "problem.viewStatementResource":
            return b"IMAGE-BYTES"
        raise AssertionError(method)


class ImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.contest = self.root / "2025"
        self.directory = self.contest / "problems"
        self.directory.mkdir(parents=True)
        (self.directory / "main.tex").write_text("DOCUMENT", encoding="utf-8")
        (self.directory / "A").mkdir()
        (self.directory / "A/handwritten.tex").write_bytes(b"KEEP A")
        (self.directory / "B").mkdir()
        (self.directory / "B/old.tex").write_bytes(b"OLD B")
        self.manifest = self.directory / "problem-list.tex"
        self.manifest.write_text("\\includeproblem{A}{handwritten.tex}\n\\includeproblem{B}{old.tex}\n", encoding="utf-8")
        lock = {"schema": 1, "version": __version__, "package_sha256": package_digest()}
        (self.contest / "toolkit.lock.json").write_text(json.dumps(lock), encoding="utf-8")
        self.entry = {"letter": "B", "problemId": 42, "slug": "parking-fee-system"}
        self.config = {"schema": 1, "contestId": 5, "language": "korean", "problems": [self.entry]}
        self.client = FakePolygon()

    def test_import_keeps_A_and_backs_up_selected_B(self):
        import_contest(self.client, self.config, self.contest, letters=["B"], replace=True)
        self.assertEqual((self.directory / "A/handwritten.tex").read_bytes(), b"KEEP A")
        sections = self.directory / "B/statement-sections/korean"
        self.assertEqual((sections / "example.01").read_bytes(), b"1  2\r\n")
        self.assertEqual((sections / "example.01.a").read_bytes(), b"3\r\n")
        self.assertEqual((sections / "example.02").read_bytes(), b"")
        self.assertEqual((sections / "example.02.a").read_bytes(), b"DISPLAY\n")
        self.assertEqual((sections / "image.png").read_bytes(), b"IMAGE-BYTES")
        self.assertIn("\\&", (sections / "name.tex").read_text(encoding="utf-8"))
        self.assertIn("handwritten.tex", self.manifest.read_text(encoding="utf-8"))
        backups = list((self.contest / "build/polygon-backups").glob("*/B/old.tex"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"OLD B")
        answer_calls = [parameters for method, parameters in self.client.calls if method == "problem.testAnswer"]
        self.assertEqual([p["testIndex"] for p in answer_calls], [1])
        self.assertNotIn("problem.testInput", [method for method, _ in self.client.calls])
        source = json.loads((self.directory / "B/polygon-source.json").read_text())
        self.assertEqual(source["revision"], 7)

    def test_failed_download_preserves_all_existing_files(self):
        self.client.failed_answer = True
        before = self.manifest.read_bytes()
        with self.assertRaisesRegex(PolygonError, "not generated"):
            import_contest(self.client, self.config, self.contest, replace=True)
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual((self.directory / "B/old.tex").read_bytes(), b"OLD B")

    def test_existing_problem_requires_explicit_replace(self):
        with self.assertRaisesRegex(ValueError, "--replace"):
            import_contest(self.client, self.config, self.contest)
        self.assertEqual((self.directory / "B/old.tex").read_bytes(), b"OLD B")

    def test_changed_revision_and_missing_language_are_rejected(self):
        self.client.changed = True
        with self.assertRaisesRegex(PolygonError, "changed during"):
            fetch_problem(self.client, self.entry, self.root / "first")
        self.client = FakePolygon()
        self.client.missing_language = True
        with self.assertRaisesRegex(PolygonError, "no korean"):
            fetch_problem(self.client, self.entry, self.root / "second")

    def test_drafts_require_working_copy_flag(self):
        self.client.problem["modified"] = True
        with self.assertRaisesRegex(PolygonError, "uncommitted"):
            fetch_problem(self.client, self.entry, self.root / "first")
        fetch_problem(self.client, self.entry, self.root / "second", working_copy=True)

    def test_failed_pdf_preview_preserves_existing_problem(self):
        with patch("kgupc_pol2dom.renderer.render_contest", side_effect=ValueError("bad TeX")):
            with self.assertRaisesRegex(ValueError, "bad TeX"):
                import_contest(self.client, self.config, self.contest, replace=True, render=True)
        self.assertEqual((self.directory / "B/old.tex").read_bytes(), b"OLD B")

    def test_publish_failure_restores_manifest_and_problem(self):
        from kgupc_pol2dom import importer
        copytree = importer.shutil.copytree
        def fail_new_source(source, destination):
            if "polygon-import-" in str(source):
                raise OSError("Cannot publish")
            return copytree(source, destination)
        before = self.manifest.read_bytes()
        with patch("kgupc_pol2dom.importer.shutil.copytree", side_effect=fail_new_source):
            with self.assertRaisesRegex(OSError, "Cannot publish"):
                import_contest(self.client, self.config, self.contest, replace=True)
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual((self.directory / "B/old.tex").read_bytes(), b"OLD B")

    def test_readonly_manifest_failure_restores_problem_without_rewriting_old_manifest(self):
        write_bytes = Path.write_bytes
        def readonly_manifest(path, data):
            if path == self.manifest:
                raise PermissionError("Read-only manifest")
            return write_bytes(path, data)
        with patch.object(Path, "replace", side_effect=PermissionError("Read-only manifest")), \
             patch.object(Path, "write_bytes", readonly_manifest):
            with self.assertRaises(PermissionError):
                import_contest(self.client, self.config, self.contest, replace=True)
        self.assertEqual((self.directory / "B/old.tex").read_bytes(), b"OLD B")

    def test_config_rejects_duplicate_letters_and_credentials(self):
        path = self.root / "import.json"
        path.write_text(json.dumps({**self.config, "problems": [self.entry, self.entry]}))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_config(path)
        path.write_text(json.dumps({**self.config, "apiKey": "private"}))
        with self.assertRaisesRegex(ValueError, "environment"):
            load_config(path)


if __name__ == "__main__":
    unittest.main()
