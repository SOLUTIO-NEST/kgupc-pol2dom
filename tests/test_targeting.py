import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from kgupc_pol2dom.api import PolygonError, load_settings
from kgupc_pol2dom.cli import main
from kgupc_pol2dom.importer import import_contest
from kgupc_pol2dom.preparation import discover_config, prepare_contest
from kgupc_pol2dom.targeting import contest_id, resolve_target
import test_importer as fixtures


class LetteredPolygon(fixtures.FakePolygon):
    def request(self, method, **parameters):
        if method == "contest.problems":
            self.calls.append((method, parameters))
            return {"A": self.problem.copy()}
        return super().request(method, **parameters)


class TargetTests(unittest.TestCase):
    def test_url_uses_id_only_and_does_not_treat_ccid_as_pin(self):
        self.assertEqual(contest_id("https://polygon.codeforces.com/contest?contestId=52003&ccid=private"), "52003")
        self.assertEqual(contest_id("0052003"), "52003")
        for url in ("https://example.com/contest?contestId=42&ccid=private", "http://polygon.codeforces.com/contest?contestId=42",
                    "https://polygon.codeforces.com/contest?contestId=42&contestId=43",
                    "https://user:private@polygon.codeforces.com/contest?contestId=42",
                    "https://polygon.codeforces.com/api/problem.info?contestId=42", "0", True):
            with self.assertRaises(PolygonError) as raised:
                contest_id(url)
            self.assertNotIn("private", str(raised.exception))

    def test_dotenv_credentials_and_target_have_same_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = Path(temporary) / ".env"
            env.write_text('POLYGON_API_KEY=key\nPOLYGON_API_SECRET=secret\n'
                           'POLYGON_CONTEST_URL="https://polygon.codeforces.com/contest?contestId=42&ccid=private"\n')
            with patch.dict("os.environ", {}, clear=True), patch("kgupc_pol2dom.api.environment_value", return_value=None):
                settings = load_settings(env)
            self.assertEqual(resolve_target(settings), "42")
            self.assertNotIn("POLYGON_PIN", {k: v for k, v in settings.items() if v})
            with patch.dict("os.environ", {"POLYGON_CONTEST_URL": "43"}, clear=True):
                self.assertEqual(resolve_target(load_settings(env)), "43")

    def test_mismatched_env_and_import_config_fail_before_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.json"
            config.write_text(json.dumps({"schema": 1, "contestId": 2025, "problems": [
                {"letter": "A", "slug": "addition", "problemId": 42}]}))
            with patch("kgupc_pol2dom.api.load_settings", return_value={"POLYGON_CONTEST_URL": "2026"}), \
                 patch("kgupc_pol2dom.api.PolygonClient.from_settings") as client, redirect_stderr(io.StringIO()):
                self.assertEqual(main(["import-polygon", str(config), "--contest", temporary]), 1)
                client.assert_not_called()

    def test_prepare_blocks_git_directory_before_network_and_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / ".git").write_text("gitdir: elsewhere")
            output = repo / "build/2026"
            with patch("kgupc_pol2dom.api.load_settings", return_value={"POLYGON_CONTEST_URL": "2026"}), \
                 patch("kgupc_pol2dom.api.PolygonClient.from_settings") as client, redirect_stderr(io.StringIO()):
                self.assertEqual(main(["prepare", "--output", str(output)]), 1)
                client.assert_not_called()
            self.assertFalse(output.exists())

    def test_listing_works_with_only_env_target(self):
        client = LetteredPolygon()
        with patch("kgupc_pol2dom.api.load_settings", return_value={"POLYGON_CONTEST_URL": "52003"}), \
             patch("kgupc_pol2dom.api.PolygonClient.from_settings", return_value=client), \
             redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()):
            self.assertEqual(main(["polygon-list"]), 0)
        self.assertEqual(json.loads(output.getvalue())[0]["letter"], "A")
        self.assertEqual(client.calls, [("contest.problems", {"contestId": "52003"})])

    def test_auto_mapping_never_guesses_list_order(self):
        with self.assertRaisesRegex(PolygonError, "explicit import config"):
            discover_config(fixtures.FakePolygon(), "42")


class PreparationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "private/contest-5"
        self.client = LetteredPolygon()

    def test_create_and_update_from_url_selected_contest(self):
        prepare_contest(self.client, "5", self.output)
        config = json.loads((self.output / "polygon-import.json").read_text())
        self.assertEqual(config["contestId"], "5")
        self.assertEqual(config["problems"], [{"letter": "A", "slug": "parking-fee-system", "problemId": 42}])
        self.assertTrue((self.output / "toolkit.lock.json").is_file())
        self.assertEqual((self.output / "problems/A/statement-sections/korean/example.01").read_bytes(), b"1  2\r\n")
        prepare_contest(self.client, "5", self.output, replace=True)
        self.assertEqual(len(list((self.output / "build/polygon-backups").iterdir())), 1)

    def test_existing_workspace_cannot_change_contest(self):
        prepare_contest(self.client, "5", self.output)
        self.client.calls.clear()
        with self.assertRaisesRegex(PolygonError, "different Polygon contest"):
            prepare_contest(self.client, "6", self.output, replace=True)
        self.assertEqual(self.client.calls, [])

    def test_download_and_pdf_failures_do_not_publish_new_work_directory(self):
        self.client.failed_answer = True
        with self.assertRaises(PolygonError):
            prepare_contest(self.client, "5", self.output)
        self.assertFalse(self.output.exists())
        self.client.failed_answer = False
        with patch("kgupc_pol2dom.renderer.render_contest", side_effect=ValueError("bad TeX")):
            with self.assertRaisesRegex(ValueError, "bad TeX"):
                prepare_contest(self.client, "5", self.output, render=True)
        self.assertFalse(self.output.exists())

    def test_default_output_is_home_work_directory(self):
        with patch("kgupc_pol2dom.preparation.Path.home", return_value=self.root):
            result = prepare_contest(self.client, "5")
        self.assertEqual(result, self.root / "kgupc-work/contest-5")


class ArchiveBoundaryTests(unittest.TestCase):
    setUp = fixtures.ImportTests.setUp
    def test_import_rejects_git_without_an_archive_bypass(self):
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "outside every Git"):
            import_contest(self.client, self.config, self.contest, replace=True)
        self.assertEqual(self.client.calls, [])
        self.assertEqual((self.directory / "B/old.tex").read_bytes(), b"OLD B")

    def test_archive_command_is_not_available(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(["archive-import", "config.json", "--contest", str(self.contest)])
        self.assertEqual(raised.exception.code, 2)

    def test_import_rejects_wrong_destination_contest(self):
        (self.contest / "polygon-import.json").write_text(json.dumps({**self.config, "contestId": 99}))
        with self.assertRaisesRegex(PolygonError, "Destination belongs"):
            import_contest(self.client, self.config, self.contest, replace=True)
        self.assertEqual(self.client.calls, [])
        self.assertEqual((self.directory / "B/old.tex").read_bytes(), b"OLD B")


if __name__ == "__main__":
    unittest.main()
