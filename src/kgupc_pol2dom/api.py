"""Signed Polygon API client; package builds require explicit opt-in."""

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SETTING_NAMES = (
    "POLYGON_API_KEY", "POLYGON_API_SECRET", "POLYGON_PIN", "POLYGON_CONTEST_URL",
    "DOMJUDGE_URL", "DOMJUDGE_USERNAME", "DOMJUDGE_PASSWORD", "DOMJUDGE_CONTEST_ID",
    "CONTEST_TITLE", "CONTEST_DATE", "CONTEST_AUTHOR", "CONTEST_SLUG",
)

class PolygonError(ValueError):
    pass


def environment_value(name):
    value = os.environ.get(name)
    if value or os.name != "nt":
        return value
    # Read newly saved Windows user variables without restarting the IDE/agent.
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as registry:
            value, kind = winreg.QueryValueEx(registry, name)
            return value if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) else None
    except OSError:
        return None


def read_env_file(path):
    """Read simple dotenv assignments without executing or interpolating values."""
    values = {}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
        if not match:
            raise PolygonError(f"Invalid .env assignment at line {number}")
        name, value = match.groups()
        if value.startswith(('"', "'")):
            quote = value[0]
            closing = value.find(quote, 1)
            if closing == -1 or (value[closing + 1:].strip() and not value[closing + 1:].lstrip().startswith("#")):
                raise PolygonError(f"Invalid .env quotation at line {number}")
            value = value[1:closing]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        if name in SETTING_NAMES:
            values[name] = value
    return values


def load_settings(env_file=None):
    """Use the same configuration precedence for credentials and contest targeting."""
    path = Path(env_file) if env_file is not None else Path.cwd() / ".env"
    values = read_env_file(path) if env_file is not None or path.is_file() else {}
    result = {}
    for name in SETTING_NAMES:
        # Empty presentation values intentionally clear a date/author, rather than fall back.
        if name.startswith("CONTEST_") and name in os.environ:
            result[name] = os.environ[name]
        elif name.startswith("CONTEST_") and name in values:
            result[name] = values[name]
        else:
            result[name] = os.environ.get(name) or values.get(name) or environment_value(name)
    return result


class PolygonClient:
    BASE_URL = "https://polygon.codeforces.com/api/"
    METHODS = {
        "contest.problems", "problems.list", "problem.info", "problem.statements",
        "problem.tests", "problem.testInput", "problem.testAnswer",
        "problem.statementResources", "problem.viewStatementResource",
        "problem.packages", "problem.package",
    }

    def __init__(self, key, secret, *, pin=None, timeout=30, interval=1.0, allow_package_builds=False):
        if not key or not secret:
            raise PolygonError("Set POLYGON_API_KEY and POLYGON_API_SECRET locally")
        self._key, self._secret, self._pin = key, secret, pin
        self.timeout, self.interval = timeout, interval
        self._last_request = None
        self.allow_package_builds = allow_package_builds

    @classmethod
    def from_environment(cls, env_file=None):
        return cls.from_settings(load_settings(env_file))

    @classmethod
    def from_settings(cls, values, **options):
        return cls(values.get("POLYGON_API_KEY"), values.get("POLYGON_API_SECRET"), pin=values.get("POLYGON_PIN"), **options)

    def _parameters(self, method, parameters):
        values = {key: str(value).lower() if isinstance(value, bool) else str(value)
                  for key, value in parameters.items()}
        if any(key in values for key in ("apiKey", "apiSig", "time")):
            raise PolygonError("Authentication parameters are managed by the client")
        values.update(apiKey=self._key, time=str(int(time.time())))
        if self._pin:
            values["pin"] = self._pin
        nonce = secrets.token_hex(3)
        # Polygon signs raw sorted parameter values, then HTTP form-encodes them.
        canonical = "&".join(f"{key}={value}" for key, value in sorted(values.items()))
        signature = hashlib.sha512(f"{nonce}/{method}?{canonical}#{self._secret}".encode()).hexdigest()
        values["apiSig"] = nonce + signature
        return values

    def _comment(self, value):
        result = str(value)
        for private in (self._key, self._secret, self._pin):
            if private:
                result = result.replace(private, "[redacted]")
        return result[:500]

    def request(self, method, *, binary=False, **parameters):
        if method not in self.METHODS and not (method == "problem.buildPackage" and self.allow_package_builds):
            raise PolygonError(f"Unsupported read-only method: {method}")
        values = self._parameters(method, parameters)
        if self._last_request is not None:
            time.sleep(max(0, self.interval - (time.monotonic() - self._last_request)))
        self._last_request = time.monotonic()
        request = Request(self.BASE_URL + method, data=urlencode(values).encode("ascii"),
                          headers={"User-Agent": "kgupc-pol2dom/0.1.0",
                                   "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                limit = (512 if method == "problem.package" else 32) * 1024 * 1024
                data = response.read(limit + 1)
                content_type = response.headers.get("Content-Type", "")
        except HTTPError as error:
            message = f"HTTP {error.code}"
            try:
                payload = json.loads(error.read(65536))
                message += ": " + self._comment(payload.get("comment", "Request failed"))
            except (ValueError, AttributeError):
                pass
            raise PolygonError(f"Polygon {method}: {message}") from None
        except (URLError, TimeoutError, OSError):
            raise PolygonError(f"Polygon {method}: connection failed; check network and retry") from None
        if len(data) > limit:
            raise PolygonError(f"Polygon {method}: response exceeds {limit // (1024 * 1024)} MiB")
        if binary:
            # These methods normally return exact file bytes, including whitespace.
            if "application/json" in content_type.lower():
                try:
                    payload = json.loads(data)
                    if isinstance(payload, dict) and payload.get("status") == "FAILED":
                        raise PolygonError(f"Polygon {method}: {self._comment(payload.get('comment'))}")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            return data
        try:
            payload = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            raise PolygonError(f"Polygon {method}: expected a JSON response") from None
        if not isinstance(payload, dict) or payload.get("status") != "OK":
            comment = payload.get("comment", "Request failed") if isinstance(payload, dict) else "Invalid response"
            raise PolygonError(f"Polygon {method}: {self._comment(comment)}")
        return payload.get("result")
