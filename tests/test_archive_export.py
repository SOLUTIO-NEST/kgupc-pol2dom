import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from kgupc_toolkit.build import read_problems
from kgupc_pol2dom.archive_export import export_archive, require_export_directory
from kgupc_pol2dom.cli import main
from kgupc_pol2dom.deployment import sha256
from kgupc_pol2dom.preparation import prepare_contest, write_json
from test_targeting import LetteredPolygon


class ArchiveExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = self.root / "private/final-run"
        with redirect_stdout(io.StringIO()):
            prepare_contest(LetteredPolygon(), "5", self.run)
        problem = self.run / "problems/A"
        (problem / "parking-fee-system.pdf").write_bytes(b"FINAL PDF")
        (self.run / "problems/main.pdf").write_bytes(b"COMBINED PDF")
        self.manifest = {"schema": 2, "complete": True, "contestId": "5",
                         "toolkit": json.loads((self.run / "toolkit.lock.json").read_text()),
                         "problems": [{"letter": "A", "slug": "parking-fee-system", "problemId": 42,
                                       "revision": 7, "pdfSha256": sha256(problem / "parking-fee-system.pdf")} ]}
        self.save_manifest()
        # These private files must never enter the handoff folder.
        (self.run / ".env").write_text("DO NOT EXPORT")
        (self.run / "domjudge-packages").mkdir()
        (self.run / "domjudge-packages/A.zip").write_bytes(b"SECRET TESTS")
        (self.run / "problems/build").mkdir(exist_ok=True)
        (self.run / "problems/build/toolkit-path.tex").write_text("PRIVATE ABSOLUTE PATH")
        (problem / "parking-fee-system.log").write_text("PRIVATE LOG")
        self.output = self.root / "handoff"

    def save_manifest(self):
        write_json(self.run / "deployment.json", self.manifest)

    def export(self):
        with redirect_stdout(io.StringIO()):
            return export_archive(self.run, "2026-fall", output=self.output)

    def test_export_preserves_sources_resources_examples_pdfs_and_lock(self):
        result = self.export()
        self.assertEqual(result, self.output / "2026-fall")
        self.assertEqual(read_problems(result / "problems"), [("A", "parking-fee-system.tex")])
        for name in ("toolkit.lock.json", "problems/main.tex", "problems/main.pdf", "problems/problem-list.tex",
                     "problems/A/statement.json", "problems/A/parking-fee-system.tex", "problems/A/parking-fee-system.pdf",
                     "problems/A/statement-sections/korean/legend.tex", "problems/A/statement-sections/korean/image.png",
                     "problems/A/statement-sections/korean/example.01", "problems/A/statement-sections/korean/example.01.a"):
            self.assertEqual((result / name).read_bytes(), (self.run / name).read_bytes(), name)
        self.assertFalse((result / ".env").exists())
        self.assertFalse((result / "domjudge-packages").exists())
        self.assertFalse((result / "problems/build").exists())
        self.assertFalse((result / "problems/A/parking-fee-system.log").exists())
        self.assertFalse((result / "polygon-import.json").exists())
        audit = json.loads((result / "archive-source.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["problems"][0]["revision"], 7)
        for name, expected in audit["files"].items():
            self.assertEqual(sha256(result / name), expected)

    def test_cli_export_is_offline_and_does_not_load_dotenv(self):
        with patch("kgupc_pol2dom.api.load_settings", side_effect=AssertionError("dotenv accessed")), \
             patch("kgupc_pol2dom.api.PolygonClient.from_settings", side_effect=AssertionError("Polygon accessed")), \
             patch("kgupc_pol2dom.renderer.render_contest", side_effect=AssertionError("PDF changed")), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(main(["export-archive", str(self.run), "--name", "2026-fall", "--output", str(self.output)]), 0)

    def test_partial_or_changed_bundle_is_not_exported(self):
        self.manifest["complete"] = False
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "full-contest"):
            self.export()
        self.manifest["complete"] = True
        self.save_manifest()
        (self.run / "problems/A/parking-fee-system.pdf").write_bytes(b"CHANGED")
        with self.assertRaisesRegex(ValueError, "PDF differs"):
            self.export()
        self.assertFalse(self.output.exists())

    def test_lock_and_revision_mismatches_are_not_exported(self):
        self.manifest["toolkit"] = {}
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "toolkit lock"):
            self.export()
        self.manifest["toolkit"] = json.loads((self.run / "toolkit.lock.json").read_text())
        self.manifest["problems"][0]["revision"] = 8
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "source revision"):
            self.export()
        self.assertFalse(self.output.exists())

    def test_existing_export_is_not_overwritten(self):
        result = self.export()
        (result / "problems/main.tex").write_text("OPERATOR EDIT")
        with self.assertRaisesRegex(ValueError, "never replaced"):
            self.export()
        self.assertEqual((result / "problems/main.tex").read_text(), "OPERATOR EDIT")

    def test_automatic_refresh_backs_up_local_edits_before_replacing(self):
        result = self.export()
        (result / "problems/main.tex").write_text("LOCAL EDIT")
        with redirect_stdout(io.StringIO()):
            updated = export_archive(self.run, "2026-fall", output=self.output, replace_generated=True)
        self.assertEqual(updated, result)
        self.assertEqual((result / "problems/main.tex").read_bytes(), (self.run / "problems/main.tex").read_bytes())
        backups = list((self.output / "history").glob("*/2026-fall/problems/main.tex"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "LOCAL EDIT")

    def test_refresh_copy_failure_restores_previous_export(self):
        result = self.export()
        (result / "problems/main.tex").write_text("LOCAL EDIT")
        copytree = shutil.copytree
        def failed_copy(source, target, **options):
            if Path(target) == result:
                result.mkdir()
                (result / "partial.txt").write_text("PARTIAL")
                raise OSError("copy failed")
            return copytree(source, target, **options)
        with patch("kgupc_pol2dom.archive_export.shutil.copytree", side_effect=failed_copy), self.assertRaisesRegex(OSError, "copy failed"):
            export_archive(self.run, "2026-fall", output=self.output, replace_generated=True)
        self.assertEqual((result / "problems/main.tex").read_text(), "LOCAL EDIT")
        self.assertFalse((result / "partial.txt").exists())

    def test_refresh_refuses_unowned_or_other_contest_folder(self):
        result = self.export()
        audit = json.loads((result / "archive-source.json").read_text())
        audit["contestId"] = "6"
        write_json(result / "archive-source.json", audit)
        with self.assertRaisesRegex(ValueError, "another contest"):
            export_archive(self.run, "2026-fall", output=self.output, replace_generated=True)
        (result / "archive-source.json").unlink()
        with self.assertRaisesRegex(ValueError, "not a generated export"):
            export_archive(self.run, "2026-fall", output=self.output, replace_generated=True)

    def test_missing_or_unsafe_sources_are_not_exported(self):
        for name in ("../2026", "2026/other", "2026_fall"):
            with self.assertRaisesRegex(ValueError, "folder name"):
                export_archive(self.run, name, output=self.output)
        (self.run / "problems/A/statement-sections/korean/.env").write_text("PRIVATE")
        with self.assertRaisesRegex(ValueError, "Credentials"):
            self.export()
        self.assertFalse(self.output.exists())

    def make_repo(self, *, pol=False, ignore=True):
        repo = self.root / ("tool-repo" if pol else "archive-repo")
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True, capture_output=True)
        if pol:
            (repo / "src/kgupc_pol2dom").mkdir(parents=True)
            (repo / "src/kgupc_pol2dom/cli.py").write_text("TOOL MARKER")
        (repo / ".gitignore").write_text("build/\n" if ignore else "")
        return repo

    def test_direct_archive_output_is_rejected_even_when_ignored(self):
        repo = self.make_repo()
        self.output = repo / "build/archive"
        with self.assertRaisesRegex(ValueError, "copy to the archive manually"):
            self.export()
        self.assertFalse(self.output.exists())

    def test_default_output_is_ignored_pol_build_and_requires_no_archive(self):
        repo = self.make_repo(pol=True)
        with patch("kgupc_pol2dom.archive_export.Path.cwd", return_value=repo), redirect_stdout(io.StringIO()):
            result = export_archive(self.run, "2026-fall")
        self.assertEqual(result, repo / "build/archive/2026-fall")
        self.assertEqual(subprocess.run(["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo),
                                        "check-ignore", "--quiet", str(result / "problems/main.tex")]).returncode, 0)

    def test_unignored_and_tracked_exports_are_rejected(self):
        repo = self.make_repo(pol=True, ignore=False)
        path = repo / "build/archive/2026-fall"
        with self.assertRaisesRegex(ValueError, "Git-ignored"):
            require_export_directory(path)
        (repo / ".gitignore").write_text("build/\n")
        path.mkdir(parents=True)
        (path / "old.tex").write_text("TRACKED")
        subprocess.run(["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "add", "-f", "build/archive"], check=True)
        with self.assertRaisesRegex(ValueError, "tracked"):
            require_export_directory(path)

    def test_export_can_be_copied_and_edited_without_pol2dom(self):
        result = self.export()
        copied = self.root / "offline-archive/2026-fall"
        shutil.copytree(result, copied)
        shutil.rmtree(self.run)
        self.assertEqual(read_problems(copied / "problems"), [("A", "parking-fee-system.tex")])
        legend = copied / "problems/A/statement-sections/korean/legend.tex"
        legend.write_text("Edited in archive", encoding="utf-8")
        self.assertEqual(legend.read_text(encoding="utf-8"), "Edited in archive")


if __name__ == "__main__":
    unittest.main()
