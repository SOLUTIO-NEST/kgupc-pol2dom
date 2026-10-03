import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kgupc_pol2dom.api import load_settings
from kgupc_pol2dom.cli import main
from kgupc_pol2dom.deployment import build_bundle
from kgupc_pol2dom.metadata import metadata_from_settings
from kgupc_pol2dom.preparation import main_document, prepare_contest
from test_deployment import PackagePolygon
from test_targeting import LetteredPolygon


class MetadataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.metadata = {"title": "KGUPC 2027 Spring (Beginner)", "date": "2027-04-29", "author": "Solutio in Kyonggi Univ."}

    def test_dotenv_precedence_and_empty_date(self):
        env = self.root / ".env"
        env.write_text('CONTEST_TITLE="KGUPC 2027 Spring (Beginner)"\nCONTEST_DATE=\nCONTEST_AUTHOR="SOLUTIO & KGU"\n', encoding="utf-8")
        with patch.dict("os.environ", {"CONTEST_TITLE": "KGUPC 2028"}, clear=True), \
             patch("kgupc_pol2dom.api.environment_value", return_value="old"):
            metadata = metadata_from_settings(load_settings(env))
        self.assertEqual(metadata, {"title": "KGUPC 2028", "date": "", "author": "SOLUTIO & KGU"})

    def test_cover_and_header_escape_plain_text(self):
        content = main_document({"title": r"KGUPC_2027 & 50% #1 {test} $x$ \input{private}", "date": "2027-04-29"})
        self.assertIn(r"\title{KGUPC\_2027 \& 50\% \#1 \{test\} \$x\$ \textbackslash{}input\{private\}}", content)
        self.assertIn(r"\date{2027-04-29}", content)
        self.assertIn(r"\renewcommand{\contestname}{KGUPC\_2027 \&", content)

    def test_invalid_dates_fail_before_requests_or_writes(self):
        for value in ("2027-02-29", "2027/04/29", "20270429", "2027-4-29"):
            client = LetteredPolygon()
            with self.assertRaisesRegex(ValueError, "CONTEST_DATE"):
                prepare_contest(client, "5", self.root / "invalid", metadata={"date": value})
            self.assertEqual(client.calls, [])
            self.assertFalse((self.root / "invalid").exists())

    def test_prepare_cli_reads_metadata_without_dom_settings(self):
        output = self.root / "prepared"
        settings = {"POLYGON_CONTEST_URL": "5", "CONTEST_TITLE": self.metadata["title"], "CONTEST_DATE": self.metadata["date"]}
        with patch("kgupc_pol2dom.api.load_settings", return_value=settings), \
             patch("kgupc_pol2dom.api.PolygonClient.from_settings", return_value=LetteredPolygon()), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["prepare", "--output", str(output)]), 0)
        document = (output / "problems/main.tex").read_text(encoding="utf-8")
        self.assertIn(r"\title{KGUPC 2027 Spring (Beginner)}", document)
        self.assertIn(r"\date{2027-04-29}", document)

    def test_prepare_refresh_preserves_other_local_edits_and_backs_up_cover(self):
        output = self.root / "prepared"
        with redirect_stdout(io.StringIO()):
            prepare_contest(LetteredPolygon(), "5", output, metadata=self.metadata)
            main_tex = output / "problems/main.tex"
            original = main_tex.read_text(encoding="utf-8") + "% local cover comment\n"
            main_tex.write_text(original, encoding="utf-8")
            prepare_contest(LetteredPolygon(), "5", output, replace=True, metadata={"date": ""})
        document = main_tex.read_text(encoding="utf-8")
        self.assertIn(r"\date{}", document)
        self.assertIn(r"\title{KGUPC 2027 Spring (Beginner)}", document)
        self.assertTrue(document.endswith("% local cover comment\n"))
        backup = next((output / "build/polygon-backups").glob("*/main.tex"))
        self.assertEqual(backup.read_text(encoding="utf-8"), original)

    def test_failed_preview_preserves_cover(self):
        output = self.root / "prepared"
        with redirect_stdout(io.StringIO()):
            prepare_contest(LetteredPolygon(), "5", output)
        original = (output / "problems/main.tex").read_bytes()
        with patch("kgupc_pol2dom.renderer.render_contest", side_effect=ValueError("bad TeX")), \
             redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "bad TeX"):
            prepare_contest(LetteredPolygon(), "5", output, replace=True, render=True, metadata=self.metadata)
        self.assertEqual((output / "problems/main.tex").read_bytes(), original)

    def test_bundle_records_metadata_without_changing_identity(self):
        def render(source, *, lock):
            document = source.read_text(encoding="utf-8")
            self.assertIn(r"\title{KGUPC 2027 Spring (Beginner)}", document)
            self.assertIn(r"\date{2027-04-29}", document)
            source.with_suffix(".pdf").write_bytes(b"%PDF combined")
            (source.parent / "A/parking-fee-system.pdf").write_bytes(b"%PDF Korean")
        with patch("kgupc_pol2dom.deployment.render_contest", side_effect=render), redirect_stdout(io.StringIO()):
            run = build_bundle(PackagePolygon(), "5", self.root / "deployment", dom_contest="test", metadata=self.metadata)
        manifest = json.loads((run / "deployment.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["contestMetadata"], self.metadata)
        self.assertEqual(manifest["problems"][0]["externalId"], "polygon-test-5-42")

    def test_bad_cli_metadata_is_rejected_before_network(self):
        with patch("kgupc_pol2dom.api.load_settings", return_value={"CONTEST_DATE": "invalid"}), \
             patch("kgupc_pol2dom.api.PolygonClient.from_settings") as polygon, redirect_stderr(io.StringIO()):
            self.assertEqual(main(["bundle"]), 1)
        polygon.assert_not_called()


if __name__ == "__main__":
    unittest.main()
