"""Single rendering boundary for the future Polygon/DOMjudge conversion pipeline."""

from pathlib import Path

from kgupc_toolkit.build import build, find_main


def render_contest(source: Path, *, lock: Path | None = None) -> list[Path]:
    """Render local problem/editorial sources using the installed, optionally locked toolkit."""
    return build(find_main(Path(source)), lock=lock)
