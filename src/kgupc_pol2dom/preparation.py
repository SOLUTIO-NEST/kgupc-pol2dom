"""Create a local contest work directory from the configured Polygon contest."""

import json
from pathlib import Path
import tempfile
import shutil

from kgupc_toolkit import __version__
from kgupc_toolkit.resources import package_digest

from .api import PolygonError
from .importer import contest_problems, fetch_problem, import_contest, load_config, validate_config
from .targeting import contest_id, require_private_directory
from .metadata import update_main_metadata


MAIN = r"""\documentclass[11pt]{article}
\input{build/toolkit-path.tex}
\input{\KGUPCToolkitRoot/latex/layouts/problem.tex}
\title{KGUPC}
\author{Solutio in Kyonggi Univ.}
\date{}
\renewcommand{\contestname}{KGUPC}
\renewcommand{\contentsname}{Contents}
\begin{document}
\problemsetfrontmatter
\input{problem-list.tex}
\checkselectedproblem
\end{document}
"""


def main_document(metadata=None):
    return update_main_metadata(MAIN, metadata or {})


def discover_config(client, target, *, language="korean", testset="tests"):
    problems = contest_problems(client, target)
    entries = []
    for problem in problems:
        # Never guess letters from API list order.
        if not isinstance(problem, dict) or not problem.get("letter"):
            raise PolygonError("Polygon did not provide contest letters; use an explicit import config")
        entries.append({"letter": problem["letter"], "problemId": problem.get("id"), "slug": problem.get("name")})
    config = validate_config({"schema": 1, "contestId": contest_id(target), "language": language,
                              "testset": testset, "problems": entries})
    if any(type(entry["problemId"]) is not int for entry in entries):
        raise PolygonError("Polygon returned a problem without an ID")
    config["problems"] = sorted(entries, key=lambda entry: (len(entry["letter"]), entry["letter"]))
    return config


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def prepare_contest(client, target, output=None, *, letters=None, replace=False, working_copy=False,
                    render=False, language="korean", testset="tests", metadata=None):
    document = main_document(metadata)
    target = contest_id(target)
    output = require_private_directory(output or Path.home() / "kgupc-work" / f"contest-{target}")
    config_path = output / "polygon-import.json"
    if output.exists():
        if not config_path.is_file():
            raise ValueError("Output already exists without a Polygon import config; choose another directory")
        old = load_config(config_path)
        if contest_id(old.get("contestId")) != target:
            raise PolygonError("Output belongs to a different Polygon contest; choose another directory")
    config = discover_config(client, target, language=language, testset=testset)
    entries = config["problems"]
    if letters:
        wanted = set(letters)
        if wanted - {entry["letter"] for entry in entries}:
            raise ValueError("Selected letters are missing from this Polygon contest")
        entries = [entry for entry in entries if entry["letter"] in wanted]
    if output.exists():
        existing = (output / "problems/main.tex").read_text(encoding="utf-8")
        updated = update_main_metadata(existing, metadata or {})
        import_contest(client, config, output, letters=letters, replace=replace,
                       working_copy=working_copy, render=render,
                       main_content=updated if updated != existing else None)
        write_json(config_path, config)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="kgupc-prepare-", dir=output.parent) as temporary:
            stage = Path(temporary)
            problems = stage / "problems"
            problems.mkdir()
            (problems / "main.tex").write_text(document, encoding="utf-8", newline="\n")
            write_json(stage / "toolkit.lock.json", {"schema": 1, "version": __version__,
                       "package_sha256": package_digest(), "repository": "https://github.com/SOLUTIO-NEST/kgupc-toolkit"})
            write_json(stage / "polygon-import.json", config)
            for entry in entries:
                print(f"Fetching {entry['letter']}: Polygon {entry['problemId']}", flush=True)
                fetch_problem(client, entry, problems / entry["letter"], language=language,
                              testset=testset, working_copy=working_copy)
            (problems / "problem-list.tex").write_text("% !TeX root = main.tex\n" + "".join(
                f"\\includeproblem{{{entry['letter']}}}{{{entry['slug']}.tex}}\n" for entry in entries),
                encoding="utf-8", newline="\n")
            from kgupc_toolkit.statements import prepare_statements
            prepare_statements(problems, [(entry["letter"], entry["slug"] + ".tex") for entry in entries])
            if render:
                from .renderer import render_contest
                render_contest(problems / "main.tex", lock=stage / "toolkit.lock.json")
            # Copy rather than move: preserve the destination's inherited Windows ACL.
            require_private_directory(output)
            shutil.copytree(stage, output)
    print(f"Local contest ready: {output}", flush=True)
    if render:
        print(f"Combined PDF: {output / 'problems/main.pdf'}", flush=True)
    return output
