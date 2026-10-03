import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from kgupc_pol2dom.api import load_settings
from kgupc_pol2dom.domjudge import DOMjudgeClient, DOMjudgeError, MissingProblem, NoRedirect, api_url, target_contest


class DOMjudgeTests(unittest.TestCase):
    def test_server_root_and_api_urls_preserve_installation_prefix(self):
        for value in ("https://judge.test/domjudge", "https://judge.test/domjudge/api/", "https://judge.test/domjudge/api/v4/"):
            self.assertEqual(api_url(value), "https://judge.test/domjudge/api/v4")
        for value in ("https://admin:secret@judge.test", "https://judge.test?password=secret", "ftp://judge.test", ""):
            with self.assertRaises(DOMjudgeError):
                api_url(value)

    def test_multipart_has_zip_update_id_and_basic_auth(self):
        client = DOMjudgeClient("https://judge.test/domjudge", "admin", "secret")
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "A.zip"
            package.write_bytes(b"PK\x03\x04binary\x00data")
            response = io.BytesIO(b'{"problem_id": 17}')
            with patch.object(client.opener, "open", return_value=response) as transport:
                self.assertEqual(client.upload("test-spring", package, problem_id=17), {"problem_id": 17})
            request = transport.call_args.args[0]
            self.assertEqual(request.full_url, "https://judge.test/domjudge/api/v4/contests/test-spring/problems")
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(request.get_header("Authorization"), "Basic " + base64.b64encode(b"admin:secret").decode())
            self.assertIn(b'name="zip"; filename="problem.zip"', request.data)
            self.assertIn(package.read_bytes(), request.data)
            self.assertIn(b'name="problem"\r\n\r\n17', request.data)
            self.assertNotIn(b"secret", request.data)

    def test_errors_do_not_expose_server_body_or_credentials(self):
        client = DOMjudgeClient("https://judge.test", "admin", "secret")
        error = HTTPError("https://judge.test", 403, "secret", {}, io.BytesIO(b"password=secret"))
        with patch.object(client.opener, "open", side_effect=error):
            with self.assertRaisesRegex(DOMjudgeError, "HTTP 403") as caught:
                client.contests()
        self.assertNotIn("secret", str(caught.exception))
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test"))

    def test_dotenv_dom_settings_and_process_priority(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text('DOMJUDGE_URL=https://judge.test\nDOMJUDGE_USERNAME=admin\nDOMJUDGE_PASSWORD="s#ecret"\nDOMJUDGE_CONTEST_ID=test\n')
            with patch.dict("os.environ", {"DOMJUDGE_CONTEST_ID": "process-test"}, clear=True):
                settings = load_settings(path)
            self.assertEqual(settings["DOMJUDGE_PASSWORD"], "s#ecret")
            self.assertEqual(target_contest(settings), "process-test")

    def test_unlink_uses_contest_scoped_delete_and_accepts_204(self):
        client = DOMjudgeClient('https://judge.test', 'admin', 'secret')
        with patch.object(client.opener, 'open', return_value=io.BytesIO(b'')) as transport:
            self.assertIsNone(client.unlink('demo', 'old-problem'))
        request = transport.call_args.args[0]
        self.assertEqual(request.get_method(), 'DELETE')
        self.assertEqual(request.full_url, 'https://judge.test/api/v4/contests/demo/problems/old-problem')

    def test_sync_creates_only_when_the_specific_external_id_is_missing(self):
        client = DOMjudgeClient('https://judge.test', 'admin', 'secret')
        with patch.object(client, 'upload', side_effect=[MissingProblem('missing'), {'problem_id': 'stable'}]) as upload:
            client.sync_problem('demo', Path('A.zip'), 'stable')
        self.assertEqual(upload.call_args_list[0].kwargs, {'problem_id': 'stable'})
        self.assertEqual(upload.call_args_list[1].kwargs, {})
        with patch.object(client, 'upload', side_effect=DOMjudgeError('HTTP 400: invalid ZIP')) as upload:
            with self.assertRaises(DOMjudgeError):
                client.sync_problem('demo', Path('A.zip'), 'stable')
        self.assertEqual(upload.call_count, 1)

    def test_missing_problem_error_is_distinguished_without_echoing_other_bodies(self):
        client = DOMjudgeClient('https://judge.test', 'admin', 'secret')
        body = json.dumps({'message': "Specified 'problem' does not exist."}).encode()
        error = HTTPError('https://judge.test', 400, '', {}, io.BytesIO(body))
        with patch.object(client.opener, 'open', side_effect=error):
            with self.assertRaises(MissingProblem):
                client.request('/contests/demo/problems', data=b'upload')


if __name__ == "__main__":
    unittest.main()
