import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs

from kgupc_pol2dom.api import PolygonClient, PolygonError, read_env_file


class Response(io.BytesIO):
    def __init__(self, content, content_type="application/json"):
        super().__init__(content)
        self.headers = {"Content-Type": content_type}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = PolygonClient("test-key", "test-secret", interval=0)

    def test_signed_post_matches_fixed_sha512_vector(self):
        response = Response(b'{"status":"OK","result":{"timeLimit":1000}}')
        with patch("kgupc_pol2dom.api.time.time", return_value=1700000000), \
             patch("kgupc_pol2dom.api.secrets.token_hex", return_value="abcdef"), \
             patch("kgupc_pol2dom.api.urlopen", return_value=response) as transport:
            self.assertEqual(self.client.request("problem.info", problemId=42), {"timeLimit": 1000})
        request = transport.call_args.args[0]
        self.assertEqual(request.full_url, "https://polygon.codeforces.com/api/problem.info")
        self.assertEqual(request.get_method(), "POST")
        parameters = parse_qs(request.data.decode("ascii"))
        self.assertEqual(parameters["apiSig"], ["abcdef16c3c2b3dcf3adc6c0374b35e3a52e066d564b31f5c2e952b6457ccf239d12cdd70dc490451acd511567fcff43d44d6364580f7e90a088116f4cacc082e7ef66"])
        self.assertNotIn("test-secret", request.data.decode("ascii"))

    def test_binary_preserves_crlf_spaces_and_empty_response(self):
        for data in (b"1  2\r\n\r\n", b"", b'{"status":"OK"}\n'):
            with patch("kgupc_pol2dom.api.urlopen", return_value=Response(data, "text/plain")):
                self.assertEqual(self.client.request("problem.testInput", binary=True, problemId=42), data)

    def test_api_and_http_errors_redact_credentials(self):
        message = "invalid test-key test-secret"
        payload = json.dumps({"status": "FAILED", "comment": message}).encode()
        with patch("kgupc_pol2dom.api.urlopen", return_value=Response(payload)):
            with self.assertRaises(PolygonError) as raised:
                self.client.request("problem.info", problemId=42)
        self.assertNotIn("test-secret", str(raised.exception))
        with patch("kgupc_pol2dom.api.urlopen", side_effect=HTTPError("https://polygon.codeforces.com", 403,
                                                                     "Forbidden", {}, io.BytesIO(payload))):
            with self.assertRaisesRegex(PolygonError, "HTTP 403") as raised:
                self.client.request("problem.info", problemId=42)
        self.assertNotIn("test-key", str(raised.exception))

    def test_binary_api_error_does_not_become_sample_text(self):
        with patch("kgupc_pol2dom.api.urlopen", return_value=Response(b'{"status":"FAILED","comment":"not generated"}')):
            with self.assertRaisesRegex(PolygonError, "not generated"):
                self.client.request("problem.testAnswer", binary=True, problemId=42)

    def test_mutating_methods_are_never_sent(self):
        with patch("kgupc_pol2dom.api.urlopen") as transport:
            with self.assertRaisesRegex(PolygonError, "read-only"):
                self.client.request("problem.saveStatement", problemId=42)
            transport.assert_not_called()

    def test_dotenv_quotes_comments_and_process_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text('# comment\nexport POLYGON_API_KEY = "file-key" # comment\n'
                            "POLYGON_API_SECRET='file-secret'\nPOLYGON_PIN=42 # comment\nOTHER=ignored\n",
                            encoding="utf-8")
            self.assertEqual(read_env_file(path), {"POLYGON_API_KEY": "file-key",
                                                   "POLYGON_API_SECRET": "file-secret", "POLYGON_PIN": "42"})
            with patch.dict("os.environ", {"POLYGON_API_KEY": "process-key"}, clear=True):
                client = PolygonClient.from_environment(path)
                self.assertEqual(client._key, "process-key")
                self.assertEqual(client._secret, "file-secret")

    def test_dotenv_parse_error_does_not_print_credential_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text('POLYGON_API_SECRET="private-secret', encoding="utf-8")
            with self.assertRaisesRegex(PolygonError, "line 1") as raised:
                read_env_file(path)
            self.assertNotIn("private-secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
