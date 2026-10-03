import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from kgupc_pol2dom.api import PolygonClient, PolygonError
from kgupc_pol2dom.deployment import build_bundle, convert_package, external_problem_id, extract_package, ready_package, sha256, upload_bundle, upload_lock
from kgupc_pol2dom.domjudge import DOMjudgeError
from kgupc_pol2dom.preparation import write_json
from test_targeting import LetteredPolygon


XML = '''<problem short-name="parking-fee-system" revision="7">
<names><name language="korean" value="Test title"/></names>
<judging input-file="" output-file=""><testset name="tests">
<time-limit>1000</time-limit><memory-limit>268435456</memory-limit>
<input-path-pattern>tests/%02d</input-path-pattern><answer-path-pattern>tests/%02d.a</answer-path-pattern>
<tests><test method="manual" sample="true"/><test method="manual" sample="false"/></tests>
</testset></judging>
<assets><checker name="std::wcmp.cpp"><source path="files/check.cpp"/></checker>
<validator><source path="files/validator.cpp"/></validator>
<solutions><solution tag="main"><source path="solutions/main.cpp" type="cpp.g++17"/></solution></solutions></assets>
<files><resources><file path="files/testlib.h"/></resources></files></problem>'''


def polygon_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in {"problem.xml": XML.encode(), "tests/01": b"1  2\r\n", "tests/01.a": b"3\r\n",
                              "tests/02": b"4 5\n", "tests/02.a": b"9\n", "files/check.cpp": b'#include "testlib.h"\n',
                              "files/validator.cpp": b'#include "testlib.h"\n', "files/testlib.h": b"POLYGON INPUT VALIDATOR HEADER",
                              "solutions/main.cpp": b"int main() { return 0; }\n"}.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class PackagePolygon(LetteredPolygon):
    def request(self, method, **parameters):
        if method == "problem.packages":
            return [{"id": 12, "revision": 7, "type": "linux", "state": "READY"}]
        if method == "problem.package":
            return polygon_zip()
        return super().request(method, **parameters)


class FakeDOMjudge:
    url = "https://judge.test/api/v4"

    def __init__(self):
        self.remote = []
        self.calls = []
        self.fail = False
        self.removals = []

    def contest(self, target):
        return {"id": target}

    def problems(self, target):
        return self.remote[:]

    def upload(self, target, path, *, problem_id=None):
        self.calls.append((Path(path).stem, problem_id))
        if self.fail:
            raise DOMjudgeError("test connection failure")
        if not any(p['id'] == problem_id for p in self.remote):
            self.remote.append({"id": problem_id, "label": Path(path).stem})
        return {"problem_id": problem_id, "messages": []}

    def sync_problem(self, target, path, external_id):
        return self.upload(target, path, problem_id=external_id)

    def unlink(self, target, problem_id):
        self.removals.append((target, str(problem_id)))
        self.remote = [p for p in self.remote if str(p['id']) != str(problem_id)]


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name) / "private"
        self.run = self.output / "runs/test-run"
        self.run.mkdir(parents=True)

    def manifest(self, letters=("A",)):
        packages = self.run / "domjudge-packages"
        packages.mkdir(exist_ok=True)
        records = []
        for index, letter in enumerate(letters):
            package = packages / (letter + ".zip")
            package.write_bytes(b"ZIP " + letter.encode())
            records.append({"letter": letter, "problemId": 42 + index, "revision": 7,
                            "domLabel": letter, "externalId": external_problem_id('test', '5', 42 + index),
                            "zip": f"domjudge-packages/{letter}.zip", "sha256": sha256(package)})
        write_json(self.run / "deployment.json", {"schema": 2, "contestId": "5", "domjudgeContestId": "test", "complete": True, "problems": records})
        return {"POLYGON_CONTEST_URL": "https://polygon.codeforces.com/contest?contestId=5", "DOMJUDGE_CONTEST_ID": "test"}

    def test_converter_preserves_judge_bytes_samples_checker_and_korean_pdf(self):
        package = self.run / "polygon.zip"
        package.write_bytes(polygon_zip())
        pdf = self.run / "A.pdf"
        pdf.write_bytes(b"%PDF-TEST-KOREAN")
        output = self.run / "A.zip"
        counts = convert_package(package, output, pdf, {"letter": "A", "problemId": 42, "slug": "parking-fee-system"}, "korean", "tests", 7)
        self.assertEqual(counts["testCount"], 2)
        self.assertEqual(counts["sampleCount"], 1)
        self.assertEqual(counts["solutionCount"], 1)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read("data/sample/01.in"), b"1  2\r\n")
            self.assertEqual(archive.read("data/secret/02.ans"), b"9\n")
            self.assertEqual(archive.read("problem_statement/problem.pdf"), pdf.read_bytes())
            self.assertIn("output_validators/checker/testlib.h", archive.namelist())
            self.assertNotEqual(archive.read("output_validators/checker/testlib.h"), b"POLYGON INPUT VALIDATOR HEADER")
            self.assertEqual(archive.read("input_validators/validator/testlib.h"), b"POLYGON INPUT VALIDATOR HEADER")

    def test_converter_reads_mixed_verdict_jury_source_as_utf8_on_windows(self):
        package = self.run / 'polygon.zip'
        source = b'// ' + '\ud55c\uae00 \uc8fc\uc11d'.encode('utf-8') + b'\nint main() { return 0; }\n'
        with zipfile.ZipFile(io.BytesIO(polygon_zip())) as original, zipfile.ZipFile(package, 'w') as archive:
            for name in original.namelist():
                content = original.read(name)
                if name == 'problem.xml':
                    content = content.replace(b'tag="main"', b'tag="rejected"')
                if name == 'solutions/main.cpp':
                    content = source
                archive.writestr(name, content)
        pdf = self.run / 'A.pdf'
        pdf.write_bytes(b'%PDF UTF8')
        output = self.run / 'A.zip'
        convert_package(package, output, pdf, {'letter': 'A', 'problemId': 42, 'slug': 'parking-fee-system'}, 'korean', 'tests', 7)
        with zipfile.ZipFile(output) as archive:
            converted = archive.read('submissions/mixed/main.cpp')
            self.assertTrue(converted.replace(b'\r\n', b'\n').startswith(source))
            self.assertIn(b'@EXPECTED_RESULTS@', converted)

    def test_pipeline_stages_all_results_before_upload_and_preserves_latest_on_failure(self):
        output = self.output / "bundle"
        client = PackagePolygon()
        def render(source, *, lock):
            source.with_suffix(".pdf").write_bytes(b"%PDF combined")
            (source.parent / "A/parking-fee-system.pdf").write_bytes(b"%PDF Korean")
        with patch("kgupc_pol2dom.deployment.render_contest", side_effect=render):
            run = build_bundle(client, "5", output, dom_contest='test')
        manifest = json.loads((run / "deployment.json").read_text())
        self.assertEqual(manifest["problems"][0]["testCount"], 2)
        pointer = (output / "latest.json").read_bytes()
        client.problem["revision"] = 8
        with self.assertRaisesRegex(PolygonError, "no READY"):
            build_bundle(client, "5", output, dom_contest='test')
        self.assertEqual((output / "latest.json").read_bytes(), pointer)

    def test_stale_package_is_rejected_instead_of_mixing_revisions(self):
        with self.assertRaisesRegex(PolygonError, "revision 8"):
            ready_package(PackagePolygon(), 42, 8)

    def test_package_build_requires_explicit_opt_in(self):
        client = PolygonClient("key", "secret", interval=0)
        with patch("kgupc_pol2dom.api.urlopen") as transport:
            with self.assertRaisesRegex(PolygonError, "read-only"):
                client.request("problem.buildPackage", problemId=42, full=True)
            transport.assert_not_called()

    def test_full_package_build_includes_required_verification_and_waits_for_ready(self):
        from unittest.mock import Mock
        client = Mock()
        ready = {"id": 20, "revision": 7, "type": "linux", "state": "READY"}
        def request(method, **parameters):
            if method == "problem.packages":
                return [] if not client.built else [ready]
            if method == "problem.buildPackage":
                self.assertEqual(parameters, {"problemId": 42, "full": True, "verify": True})
                client.built = True
            if method == "problems.list":
                return [{"id": 42, "revision": 7, "modified": False}]
        client.built = False
        client.request.side_effect = request
        with patch("kgupc_pol2dom.deployment.time.sleep"):
            self.assertEqual(ready_package(client, 42, 7, build_packages=True), ready)

    def test_zip_paths_cannot_escape_extraction(self):
        package = self.run / "bad.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("../outside.txt", b"bad")
        with self.assertRaisesRegex(ValueError, "Unsafe path"):
            extract_package(package, self.run / "extracted", "parking-fee-system", "tests")

    def test_sync_reuses_stable_ids_and_reapplies_source_content(self):
        settings = self.manifest()
        dom = FakeDOMjudge()
        upload_bundle(dom, settings, self.run)
        upload_bundle(dom, settings, self.run)
        expected_id = external_problem_id('test', '5', 42)
        self.assertEqual(dom.calls, [("A", expected_id), ("A", expected_id)])
        self.assertEqual(len(dom.remote), 1)
        path = self.run / "domjudge-packages/A.zip"
        path.write_bytes(b"UPDATED ZIP")
        manifest = json.loads((self.run / "deployment.json").read_text())
        manifest["problems"][0]["sha256"] = sha256(path)
        write_json(self.run / "deployment.json", manifest)
        upload_bundle(dom, settings, self.run)
        self.assertEqual(dom.calls[-1], ("A", expected_id))

    def test_import_message_counts_and_jury_warning_do_not_expose_server_text(self):
        settings = self.manifest()
        dom = FakeDOMjudge()
        original = dom.upload
        def upload(*args, **options):
            result = original(*args, **options)
            result['messages'] = {'info': ['saved', 'statement imported'],
                                  'warning': ['No jury solutions added: must associate team with your user first.',
                                              'password=private-value'], 'danger': []}
            return result
        output = io.StringIO()
        with patch.object(dom, 'upload', side_effect=upload), patch('sys.stdout', output):
            upload_bundle(dom, settings, self.run)
        self.assertIn('info=2, warning=2, danger=0', output.getvalue())
        self.assertIn('associate the upload account with a team', output.getvalue())
        self.assertNotIn('private-value', output.getvalue())

    def test_sync_replaces_conflicting_labels_and_prunes_unrelated_contest_problems(self):
        settings = self.manifest(("A", "B"))
        dom = FakeDOMjudge()
        dom.remote = [{"label": "B", "id": "old-example"}, {'label': 'KGUPC2025-X', 'id': 'old-prefix'}]
        upload_bundle(dom, settings, self.run)
        self.assertEqual({p['label'] for p in dom.remote}, {'A', 'B'})
        self.assertEqual(dom.removals, [('test', 'old-example'), ('test', 'old-prefix')])

    def test_changed_zip_stops_before_any_upload_or_removal(self):
        settings = self.manifest(("A", "B"))
        dom = FakeDOMjudge()
        dom.remote = [{'label': 'A', 'id': 'old-example'}]
        (self.run / "domjudge-packages/B.zip").write_bytes(b"TAMPERED")
        with self.assertRaisesRegex(ValueError, "changed"):
            upload_bundle(dom, settings, self.run)
        self.assertEqual(dom.calls, [])
        self.assertEqual(dom.removals, [])

    def test_partial_upload_keeps_receipt_and_can_resume(self):
        settings = self.manifest(("A", "B"))
        dom = FakeDOMjudge()
        original = dom.upload
        def upload(target, path, **options):
            dom.fail = Path(path).stem == "B"
            return original(target, path, **options)
        with patch.object(dom, "upload", side_effect=upload):
            with self.assertRaises(DOMjudgeError):
                upload_bundle(dom, settings, self.run)
        receipt = json.loads((self.output / "domjudge-receipt.json").read_text())
        self.assertEqual(set(receipt["problems"]), {"A"})
        dom.fail = False
        upload_bundle(dom, settings, self.run)
        self.assertEqual([call[0] for call in dom.calls], ["A", "B", "A", "B"])

    def test_bundle_target_cannot_be_changed_at_upload_time(self):
        settings = self.manifest()
        dom = FakeDOMjudge()
        upload_bundle(dom, settings, self.run)
        settings["DOMJUDGE_CONTEST_ID"] = "other"
        with self.assertRaisesRegex(DOMjudgeError, "another DOMjudge contest"):
            upload_bundle(dom, settings, self.run)
        settings["DOMJUDGE_CONTEST_ID"] = "test"
        settings["POLYGON_CONTEST_URL"] = "https://polygon.codeforces.com/contest?contestId=6"
        with self.assertRaisesRegex(PolygonError, "mismatch"):
            upload_bundle(dom, settings, self.run)

    def test_missing_local_receipt_does_not_create_duplicate_problems(self):
        settings = self.manifest()
        dom = FakeDOMjudge()
        upload_bundle(dom, settings, self.run)
        (self.output / 'domjudge-receipt.json').unlink()
        upload_bundle(dom, settings, self.run)
        self.assertEqual(len(dom.remote), 1)
        self.assertEqual(dom.calls[0][1], dom.calls[1][1])

    def test_concurrent_upload_is_rejected(self):
        settings = self.manifest()
        dom = FakeDOMjudge()
        with upload_lock(self.output):
            with self.assertRaisesRegex(DOMjudgeError, "Another DOMjudge upload"):
                upload_bundle(dom, settings, self.run)
        self.assertEqual(dom.calls, [])

    def test_partial_selection_preserves_unselected_letters(self):
        settings = self.manifest()
        manifest = json.loads((self.run / 'deployment.json').read_text())
        manifest['complete'] = False
        write_json(self.run / 'deployment.json', manifest)
        dom = FakeDOMjudge()
        dom.remote = [{'id': 'unselected-B', 'label': 'B'}]
        upload_bundle(dom, settings, self.run)
        self.assertEqual({p['label'] for p in dom.remote}, {'A', 'B'})
        self.assertEqual(dom.removals, [])

    def test_letter_reassignment_keeps_source_ids_without_duplicates(self):
        settings = self.manifest(('A', 'B'))
        dom = FakeDOMjudge()
        dom.remote = [{'id': external_problem_id('test', '5', 42), 'label': 'B'},
                      {'id': external_problem_id('test', '5', 43), 'label': 'A'}]
        upload_bundle(dom, settings, self.run)
        self.assertEqual({p['id']: p['label'] for p in dom.remote},
                         {external_problem_id('test', '5', 42): 'A', external_problem_id('test', '5', 43): 'B'})

    def test_obsolete_problems_are_preserved_until_all_uploads_succeed(self):
        settings = self.manifest()
        dom = FakeDOMjudge()
        dom.remote = [{'id': 'obsolete', 'label': 'Z'}]
        dom.fail = True
        with self.assertRaises(DOMjudgeError):
            upload_bundle(dom, settings, self.run)
        self.assertEqual(dom.remote, [{'id': 'obsolete', 'label': 'Z'}])
        self.assertEqual(dom.removals, [])

    def test_old_prefixed_bundles_are_rejected_before_remote_mutation(self):
        settings = self.manifest()
        manifest = json.loads((self.run / 'deployment.json').read_text())
        manifest['schema'] = 1
        write_json(self.run / 'deployment.json', manifest)
        dom = FakeDOMjudge()
        with self.assertRaisesRegex(ValueError, 'Regenerate'):
            upload_bundle(dom, settings, self.run)
        self.assertEqual(dom.calls, [])
        self.assertEqual(dom.removals, [])

    def test_identity_is_independent_of_letter_and_work_directory(self):
        settings = self.manifest()
        dom = FakeDOMjudge()
        upload_bundle(dom, settings, self.run)
        import shutil
        other = self.output / 'other-workspace/runs/new-run'
        shutil.copytree(self.run, other)
        upload_bundle(dom, settings, other)
        self.assertEqual(len(dom.remote), 1)
        self.assertEqual(dom.calls[0][1], dom.calls[1][1])
        self.assertNotEqual(external_problem_id('other', '5', 42), external_problem_id('test', '5', 42))

    def test_bundle_rejects_git_directory_before_polygon_requests(self):
        (self.output / ".git").mkdir()
        client = PackagePolygon()
        with self.assertRaisesRegex(ValueError, "Git working tree"):
            build_bundle(client, "5", self.output / "inside")
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
