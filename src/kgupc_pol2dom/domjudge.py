"""DOMjudge v4 API client. Credentials stay in memory and are never logged."""

import base64
import json
from pathlib import Path
import re
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class DOMjudgeError(ValueError):
    pass


class MissingProblem(DOMjudgeError):
    """The requested external problem ID does not yet exist on the server."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not forward Basic credentials or uploaded ZIPs to another URL.


def api_url(value):
    try:
        url = urlsplit(value or "")
        valid = (url.scheme in ("https", "http") and url.hostname and url.port != 0
                 and url.username is None and url.password is None and not url.query and not url.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise DOMjudgeError("Set DOMJUDGE_URL to the server URL without credentials, query or fragment")
    path = url.path.rstrip("/")
    if path.endswith("/api"):
        path += "/v4"
    elif not path.endswith("/api/v4"):
        path += "/api/v4"
    return urlunsplit((url.scheme, url.netloc, path, "", ""))


class DOMjudgeClient:
    def __init__(self, url, username, password, *, timeout=120):
        self.url = api_url(url)
        if not username or not password or ":" in username:
            raise DOMjudgeError("Set DOMJUDGE_USERNAME and DOMJUDGE_PASSWORD to an admin account")
        self._username, self._password = username, password
        self.timeout = timeout
        self.opener = build_opener(NoRedirect())

    @classmethod
    def from_settings(cls, settings):
        return cls(settings.get("DOMJUDGE_URL"), settings.get("DOMJUDGE_USERNAME"), settings.get("DOMJUDGE_PASSWORD"))

    def request(self, path, *, data=None, content_type=None, method=None):
        token = base64.b64encode(f"{self._username}:{self._password}".encode()).decode("ascii")
        headers = {"Authorization": f"Basic {token}", "Accept": "application/json",
                   "User-Agent": "kgupc-pol2dom/0.1.0"}
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(self.url + path, headers=headers, data=data, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                payload = response.read(16 * 1024 * 1024 + 1)
        except HTTPError as error:
            if error.code == 400:
                body = None
                try:
                    body = json.loads(error.read(65536))
                except (ValueError, UnicodeDecodeError):
                    pass
                if isinstance(body, dict) and body.get("message") == "Specified 'problem' does not exist.":
                    raise MissingProblem("DOMjudge problem ID does not exist") from None
            explanations = {401: "check username and password", 403: "admin permission or an unlocked contest is required",
                            404: "check server URL and contest ID", 413: "increase server ZIP upload size limits"}
            # Server error bodies may repeat credentials, request data, or private paths.
            raise DOMjudgeError(f"DOMjudge HTTP {error.code}: " + explanations.get(error.code, "request rejected; check server logs")) from None
        except (URLError, TimeoutError, OSError):
            raise DOMjudgeError("DOMjudge connection failed; check URL, TLS and network. An upload may have completed; check the contest before retrying.") from None
        if len(payload) > 16 * 1024 * 1024:
            raise DOMjudgeError("DOMjudge response exceeds 16 MiB")
        if not payload and method == "DELETE":
            return None
        try:
            return json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            raise DOMjudgeError("DOMjudge returned non-JSON data; check the /api/v4 URL") from None

    def contests(self):
        result = self.request("/contests")
        if not isinstance(result, list):
            raise DOMjudgeError("DOMjudge returned an invalid contest list")
        return result

    def contest(self, target):
        result = self.request("/contests/" + quote(target, safe=""))
        if not isinstance(result, dict) or str(result.get("id")) != target:
            raise DOMjudgeError("DOMjudge contest ID does not match the configured target")
        return result

    def problems(self, target):
        result = self.request("/contests/" + quote(target, safe="") + "/problems")
        if not isinstance(result, list):
            raise DOMjudgeError("DOMjudge returned an invalid problem list")
        return result

    def upload(self, target, package, *, problem_id=None):
        boundary = "kgupc-" + uuid.uuid4().hex
        parts = []
        if problem_id is not None:
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", str(problem_id)):
                raise DOMjudgeError("Invalid DOMjudge update problem ID")
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="problem"\r\n\r\n{problem_id}\r\n'.encode())
        parts.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="zip"; filename="problem.zip"\r\nContent-Type: application/zip\r\n\r\n'.encode(),
                      Path(package).read_bytes(), f'\r\n--{boundary}--\r\n'.encode()])
        result = self.request("/contests/" + quote(target, safe="") + "/problems", data=b"".join(parts),
                              content_type="multipart/form-data; boundary=" + boundary)
        if not isinstance(result, dict) or result.get("problem_id") is None:
            raise DOMjudgeError("DOMjudge upload response has no problem_id; inspect the contest before retrying")
        return result

    def sync_problem(self, target, package, external_id):
        # Updating by deterministic ID also finds previously unlinked problems.
        # Only the specific missing-ID response permits creating a new problem.
        try:
            return self.upload(target, package, problem_id=external_id)
        except MissingProblem:
            return self.upload(target, package)

    def unlink(self, target, problem_id):
        return self.request("/contests/" + quote(target, safe="") + "/problems/" + quote(str(problem_id), safe=""), method="DELETE")


def target_contest(settings):
    value = (settings.get("DOMJUDGE_CONTEST_ID") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise DOMjudgeError("Set DOMJUDGE_CONTEST_ID to the target contest's API ID (see domjudge-list)")
    return value
