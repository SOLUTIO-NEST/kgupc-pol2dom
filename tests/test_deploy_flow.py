import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
import unittest

import test_archive_export as fixtures
from kgupc_pol2dom.cli import main
from test_deployment import FakeDOMjudge


class DeployFlowTests(unittest.TestCase):
    setUp = fixtures.ArchiveExportTests.setUp
    save_manifest = fixtures.ArchiveExportTests.save_manifest

    def settings(self):
        return {"POLYGON_CONTEST_URL": "5", "DOMJUDGE_CONTEST_ID": "test", "CONTEST_SLUG": "2026-fall"}

    def test_full_deploy_builds_handoff_before_upload_and_refreshes_same_folder(self):
        destination = self.root / "build/archive/2026-fall"
        checks = []
        def upload(client, settings, run):
            self.assertEqual(run, self.run)
            self.assertEqual((destination / "problems/main.tex").read_bytes(), (self.run / "problems/main.tex").read_bytes())
            self.assertFalse((destination / "domjudge-packages").exists())
            checks.append(True)
        with patch("kgupc_pol2dom.api.load_settings", return_value=self.settings()), \
             patch("kgupc_pol2dom.domjudge.DOMjudgeClient.from_settings", return_value=FakeDOMjudge()), \
             patch("kgupc_pol2dom.api.PolygonClient.from_settings"), \
             patch("kgupc_pol2dom.deployment.build_bundle", return_value=self.run), \
             patch("kgupc_pol2dom.archive_export.Path.cwd", return_value=self.root), \
             patch("kgupc_pol2dom.deployment.upload_bundle", side_effect=upload), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["deploy", "--build-packages"]), 0)
            (self.run / "problems/main.tex").write_text("NEXT SOURCE", encoding="utf-8")
            self.assertEqual(main(["deploy", "--build-packages"]), 0)
        self.assertEqual(len(checks), 2)
        self.assertEqual(len(list((self.root / "build/archive/history").glob("*/2026-fall/archive-source.json"))), 1)

    def test_bundle_creates_handoff_without_domjudge_auth_or_writes(self):
        with patch("kgupc_pol2dom.api.load_settings", return_value=self.settings()), \
             patch("kgupc_pol2dom.domjudge.DOMjudgeClient.from_settings") as dom, \
             patch("kgupc_pol2dom.api.PolygonClient.from_settings"), \
             patch("kgupc_pol2dom.deployment.build_bundle", return_value=self.run), \
             patch("kgupc_pol2dom.archive_export.Path.cwd", return_value=self.root), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["bundle"]), 0)
        dom.assert_not_called()
        self.assertTrue((self.root / "build/archive/2026-fall/problems/main.pdf").is_file())

    def test_missing_slug_rejected_before_download_or_domjudge_access(self):
        with patch("kgupc_pol2dom.api.load_settings", return_value={"POLYGON_CONTEST_URL": "5"}), \
             patch("kgupc_pol2dom.domjudge.DOMjudgeClient.from_settings") as dom, \
             patch("kgupc_pol2dom.api.PolygonClient.from_settings") as polygon, redirect_stderr(io.StringIO()):
            self.assertEqual(main(["deploy"]), 1)
        dom.assert_not_called()
        polygon.assert_not_called()

    def test_partial_deploy_preserves_existing_full_handoff(self):
        destination = self.root / "build/archive/2026-fall"
        destination.mkdir(parents=True)
        (destination / "keep.txt").write_bytes(b"KEEP FULL CONTEST")
        with patch("kgupc_pol2dom.api.load_settings", return_value=self.settings()), \
             patch("kgupc_pol2dom.domjudge.DOMjudgeClient.from_settings", return_value=FakeDOMjudge()), \
             patch("kgupc_pol2dom.api.PolygonClient.from_settings"), \
             patch("kgupc_pol2dom.deployment.build_bundle", return_value=self.run), \
             patch("kgupc_pol2dom.deployment.upload_bundle") as upload, \
             patch("kgupc_pol2dom.archive_export.export_archive") as export, redirect_stdout(io.StringIO()):
            self.assertEqual(main(["deploy", "--letters", "A"]), 0)
        export.assert_not_called()
        upload.assert_called_once()
        self.assertEqual((destination / "keep.txt").read_bytes(), b"KEEP FULL CONTEST")

    def test_export_failure_stops_before_domjudge_problem_mutations(self):
        with patch("kgupc_pol2dom.api.load_settings", return_value=self.settings()), \
             patch("kgupc_pol2dom.domjudge.DOMjudgeClient.from_settings", return_value=FakeDOMjudge()), \
             patch("kgupc_pol2dom.api.PolygonClient.from_settings"), \
             patch("kgupc_pol2dom.deployment.build_bundle", return_value=self.run), \
             patch("kgupc_pol2dom.archive_export.Path.cwd", return_value=self.root), \
             patch("kgupc_pol2dom.archive_export.export_archive", side_effect=ValueError("cannot export")), \
             patch("kgupc_pol2dom.deployment.upload_bundle") as upload, redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["deploy"]), 1)
        upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
