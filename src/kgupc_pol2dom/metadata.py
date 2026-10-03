"""Contest presentation settings are plain text, independent of API identifiers."""

from datetime import date
import re


DEFAULTS = {"title": "KGUPC", "author": "Solutio in Kyonggi Univ.", "date": ""}
SETTINGS = {"title": "CONTEST_TITLE", "author": "CONTEST_AUTHOR", "date": "CONTEST_DATE"}


def validate_metadata(metadata=None):
    metadata = metadata or {}
    result = {**DEFAULTS, **metadata}
    if set(result) != set(DEFAULTS):
        raise ValueError("Unknown contest presentation field")
    for field, value in result.items():
        if not isinstance(value, str) or any(ord(character) < 32 for character in value):
            raise ValueError(f"{SETTINGS[field]} must be single-line plain text")
        result[field] = value.strip()
    if not result["title"]:
        raise ValueError("CONTEST_TITLE must not be empty")
    if result["date"]:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", result["date"]):
            raise ValueError("CONTEST_DATE must use YYYY-MM-DD or be empty")
        try:
            date.fromisoformat(result["date"])
        except ValueError:
            raise ValueError("CONTEST_DATE must be a valid calendar date") from None
    return result


def metadata_from_settings(settings):
    configured = {field: settings[name] for field, name in SETTINGS.items() if settings.get(name) is not None}
    validated = validate_metadata(configured)
    return {field: validated[field] for field in configured}


def tex_text(value):
    escapes = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "&": r"\&",
               "%": r"\%", "#": r"\#", "_": r"\_", "$": r"\$",
               "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(escapes.get(character, character) for character in value)


def update_main_metadata(content, metadata):
    """Change only explicitly configured fields; keep other local cover edits."""
    normalized = validate_metadata(metadata)
    commands = {"title": (r"\title", r"\renewcommand{\contestname}"),
                "author": (r"\author",), "date": (r"\date",)}
    for field in metadata:
        for command in commands[field]:
            pattern = re.compile(r"^" + re.escape(command) + r"\{[^\r\n]*\}[^\r\n]*$", re.M)
            if len(pattern.findall(content)) != 1:
                raise ValueError(f"Cannot update {SETTINGS[field]}: main.tex needs one standalone {command} line")
            content = pattern.sub(lambda _: command + "{" + tex_text(normalized[field]) + "}", content)
    return content
