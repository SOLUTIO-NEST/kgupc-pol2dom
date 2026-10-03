"""Select a Polygon contest without storing private links in generated manifests."""

from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from .api import PolygonError


def contest_id(value):
    if type(value) is int and value > 0:
        return str(value)
    if not isinstance(value, str):
        raise PolygonError("Expected a Polygon contest ID or HTTPS contest URL")
    value = value.strip()
    if re.fullmatch(r"[0-9]+", value) and int(value) > 0:
        return str(int(value))
    try:
        url = urlsplit(value)
        query = parse_qs(url.query, keep_blank_values=True)
        ids = query.get("contestId", [])
        valid = (url.scheme == "https" and url.hostname == "polygon.codeforces.com"
                 and url.port in (None, 443) and url.username is None and url.password is None
                 and url.path in ("/contest", "/contest/") and len(ids) == 1
                 and re.fullmatch(r"[0-9]+", ids[0]) and int(ids[0]) > 0)
    except ValueError:
        valid = False
    if not valid:
        # Never echo a URL: ccid may grant access to a private contest.
        raise PolygonError("Use an HTTPS polygon.codeforces.com/contest URL with exactly one positive contestId")
    return str(int(ids[0]))


def resolve_target(settings, *, explicit=None, configured=None):
    candidates = [contest_id(value) for value in
                  (settings.get("POLYGON_CONTEST_URL"), explicit, configured) if value is not None and value != ""]
    if not candidates:
        raise PolygonError("Set POLYGON_CONTEST_URL in .env to select the contest")
    if len(set(candidates)) != 1:
        raise PolygonError("Contest target mismatch between .env, command and import config; no files were changed")
    return candidates[0]


def require_private_directory(directory):
    directory = Path(directory).resolve()
    if any((parent / ".git").exists() for parent in (directory, *directory.parents)):
        raise ValueError("Preparation output must be outside every Git working tree. "
                         "Use export-archive to create a separate handoff folder, then copy it manually.")
    return directory
