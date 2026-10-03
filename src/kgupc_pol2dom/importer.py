"""Fetch Polygon statements and publish selected problems into an existing contest."""

import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import tempfile
import time
import uuid

from kgupc_toolkit.build import read_problems
from kgupc_toolkit.resources import verify_lock

from .api import PolygonError
from .polygon import export_statement
from .targeting import contest_id, require_private_directory


def contest_problems(client, contest_id):
    result = client.request("contest.problems", contestId=contest_id)
    # Some Polygon deployments return letter -> Problem; documentation describes a list.
    if isinstance(result, dict):
        return [{**problem, "letter": letter} for letter, problem in result.items()]
    if isinstance(result, list):
        return result
    raise PolygonError("Unexpected contest.problems result")


def load_config(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return validate_config(data)


def validate_config(data):
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("Expected an import config with schema=1")
    if any(key in data for key in ("apiKey", "apiSecret", "secret", "pin")):
        raise ValueError("Credentials belong in environment variables, not the import config")
    language, testset = data.get("language", "korean"), data.get("testset", "tests")
    if not isinstance(language, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*", language):
        raise ValueError("Invalid statement language")
    if not isinstance(testset, str) or not testset:
        raise ValueError("Invalid Polygon testset")
    entries = data.get("problems")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Config needs a non-empty problems list")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each problem mapping must be an object")
        letter, slug, problem_id = entry.get("letter"), entry.get("slug"), entry.get("problemId")
        if not isinstance(letter, str) or not re.fullmatch(r"[A-Z]+", letter) or letter in seen:
            raise ValueError("Invalid or duplicate contest letter")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", slug):
            raise ValueError(f"Invalid slug for {letter}")
        # null IDs are allowed in a planning config, but never in a selected import.
        if problem_id is not None and (type(problem_id) is not int or problem_id < 1):
            raise ValueError(f"Invalid Polygon problem ID for {letter}")
        seen.add(letter)
    return data


def fetch_problem(client, entry, destination, *, language="korean", testset="tests", working_copy=False):
    problem_id = entry["problemId"]
    available = client.request("problems.list", id=problem_id)
    before = next((problem for problem in available if problem["id"] == problem_id), None)
    if before is None:
        raise PolygonError(f"No access to Polygon problem {problem_id}")
    if before.get("modified") and not working_copy:
        raise PolygonError(f"Problem {problem_id} has uncommitted changes; commit in Polygon first or use --working-copy")
    info = client.request("problem.info", problemId=problem_id)
    statements = client.request("problem.statements", problemId=problem_id)
    if language not in statements:
        raise PolygonError(f"Problem {problem_id} has no {language} statement")
    tests = client.request("problem.tests", problemId=problem_id, testset=testset, noInputs=True)
    inputs, answers = {}, {}
    for test in tests:
        if test.get("useInStatements") is not True:
            continue
        index = test["index"]
        if test.get("inputForStatement") is None:
            if test.get("inputBase64") is not None:
                inputs[index] = base64.b64decode(test["inputBase64"], validate=True)
            else:
                inputs[index] = client.request("problem.testInput", binary=True, problemId=problem_id,
                                               testset=testset, testIndex=index)
        if test.get("outputForStatement") is None:
            answers[index] = client.request("problem.testAnswer", binary=True, problemId=problem_id,
                                            testset=testset, testIndex=index)
    resources = {}
    for resource in client.request("problem.statementResources", problemId=problem_id):
        name = resource["name"]
        if name in resources:
            raise PolygonError(f"Duplicate statement resource: {name}")
        resources[name] = client.request("problem.viewStatementResource", binary=True,
                                         problemId=problem_id, name=name)
    after = next((problem for problem in client.request("problems.list", id=problem_id)
                  if problem["id"] == problem_id), None)
    fields = ("revision", "workingCopyRevision", "modified")
    if after is None or any(before.get(key) != after.get(key) for key in fields):
        raise PolygonError(f"Problem {problem_id} changed during download; retry")
    wrapper = export_statement(destination, letter=entry["letter"], slug=entry["slug"],
                               language=language, info=info, statement=statements[language],
                               tests=tests, inputs=inputs, answers=answers, resources=resources)
    # TeX Workshop opens each section through the combined document.
    for section in (wrapper.parent / "statement-sections" / language).glob("*.tex"):
        section.write_text("% !TeX root = ../../../main.tex\n" + section.read_text(encoding="utf-8"),
                           encoding="utf-8", newline="\n")
    provenance = {"schema": 1, "problemId": problem_id, "owner": before.get("owner"),
                  "name": before.get("name"), "revision": before.get("revision"),
                  "workingCopyRevision": before.get("workingCopyRevision"),
                  "modified": bool(before.get("modified")), "language": language, "testset": testset,
                  "fetchedAt": datetime.now(timezone.utc).isoformat()}
    (wrapper.parent / "polygon-source.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
                                                        encoding="utf-8", newline="\n")
    return wrapper


def import_contest(client, config, contest, *, letters=None, replace=False, working_copy=False, render=False,
                   main_content=None):
    """Stage every download before replacing any selected problem. Keep backups in build/."""
    config = validate_config(config)
    contest = require_private_directory(contest)
    local_config = contest / "polygon-import.json"
    if local_config.is_file():
        local_target = load_config(local_config).get("contestId")
        if local_target is not None and (config.get("contestId") is None
                                        or contest_id(local_target) != contest_id(config["contestId"])):
            raise PolygonError("Destination belongs to a different Polygon contest; no files were changed")
    directory = contest / "problems"
    if not (directory / "main.tex").is_file():
        raise ValueError("Choose an existing contest with problems/main.tex")
    verify_lock(contest / "toolkit.lock.json")
    entries = config["problems"]
    if letters:
        wanted = set(letters)
        if wanted - {entry["letter"] for entry in entries}:
            raise ValueError("Selected letters are missing from the import config")
        entries = [entry for entry in entries if entry["letter"] in wanted]
    if not entries:
        raise ValueError("No problems selected")
    for entry in entries:
        if type(entry.get("problemId")) is not int or entry["problemId"] < 1:
            raise ValueError(f"Fill in the Polygon problemId for {entry['letter']}")
    if config.get("contestId") is not None:
        members = {problem["id"] for problem in contest_problems(client, config["contestId"])}
        if any(entry["problemId"] not in members for entry in entries):
            raise PolygonError("Selected problem IDs do not belong to this Polygon contest")
    registered = dict(read_problems(directory))
    for entry in entries:
        target = directory / entry["letter"]
        if target.is_symlink() or target.resolve().parent != directory.resolve():
            raise ValueError("Problem directory must stay inside this contest")
        if target.exists() and not replace:
            raise ValueError(f"{entry['letter']} already exists; use --replace to back it up and replace it")
        registered[entry["letter"]] = entry["slug"] + ".tex"
    build = contest / "build"
    build.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="polygon-import-", dir=build) as temporary:
        staging = Path(temporary) / "problems"
        staging.mkdir()
        selected = {entry["letter"] for entry in entries}
        # Render the complete final contest in isolation, including retained problems.
        # Never reuse the live document's intermediate files (IDE auto-build may be running).
        auxiliary = {".aux", ".xdv", ".log", ".fls", ".fdb_latexmk", ".toc", ".out", ".gz"}
        for child in directory.iterdir():
            if child.name in selected or child.name == "build":
                continue
            if child.is_dir():
                shutil.copytree(child, staging / child.name)
            elif child.name != "main.pdf" and child.suffix not in auxiliary:
                shutil.copyfile(child, staging / child.name)
        if main_content is not None:
            (staging / "main.tex").write_text(main_content, encoding="utf-8", newline="\n")
        for entry in entries:
            print(f"Fetching {entry['letter']}: Polygon {entry['problemId']}", flush=True)
            fetch_problem(client, entry, staging / entry["letter"],
                          language=config.get("language", "korean"), testset=config.get("testset", "tests"),
                          working_copy=working_copy)
        ordered = sorted(registered.items(), key=lambda item: (len(item[0]), item[0]))
        preview_list = "% !TeX root = main.tex\n" + "".join(
            f"\\includeproblem{{{letter}}}{{{filename}}}\n" for letter, filename in ordered)
        (staging / "problem-list.tex").write_text(preview_list, encoding="utf-8", newline="\n")
        # Validate sections and example pairs even when PDF compilation is not requested.
        from kgupc_toolkit.statements import prepare_statements
        prepare_statements(staging, ordered)
        if render:
            from .renderer import render_contest
            render_contest(staging / "main.tex", lock=contest / "toolkit.lock.json")
        manifest = directory / "problem-list.tex"
        previous = manifest.read_bytes()
        backup = build / "polygon-backups" / uuid.uuid4().hex
        backup.mkdir(parents=True)
        (backup / "problem-list.tex").write_bytes(previous)
        main = directory / "main.tex"
        previous_main = main.read_bytes() if main_content is not None else None
        if previous_main is not None:
            (backup / "main.tex").write_bytes(previous_main)
        moved = []
        try:
            for entry in entries:
                letter = entry["letter"]
                target = directory / letter
                old = backup / letter
                if target.exists():
                    shutil.move(str(target), str(old))
                moved.append((target, old))
                # copytree inherits the archive's ACL; moving out of TemporaryDirectory
                # would retain that private directory's restrictive Windows permissions.
                shutil.copytree(staging / letter, target)
            # Preserve existing registrations; only add/update selected entries.
            content = preview_list
            pending = directory / f".polygon-list-{uuid.uuid4().hex}.tex"
            pending.write_text(content, encoding="utf-8", newline="\n")
            pending.replace(manifest)
            if main_content is not None:
                pending_main = directory / f".polygon-main-{uuid.uuid4().hex}.tex"
                pending_main.write_text(main_content, encoding="utf-8", newline="\n")
                pending_main.replace(main)
        except BaseException:
            for target, old in reversed(moved):
                # Targets were checked above and must still stay inside the contest.
                if target.resolve().parent != directory.resolve() or target.is_symlink():
                    raise RuntimeError("Cannot restore a problem whose destination changed")
                if target.exists():
                    shutil.rmtree(target)
                if old.exists():
                    shutil.move(str(old), str(target))
            if manifest.read_bytes() != previous:
                manifest.write_bytes(previous)
            if previous_main is not None and main.read_bytes() != previous_main:
                main.write_bytes(previous_main)
            raise
        if render:
            # Publish completed PDFs atomically. No XeLaTeX process touches the live build/.
            # Retained problem sources remain unchanged; their PDFs use the same final context.
            outputs = [directory / "main.pdf"] + [
                (directory / letter / filename).with_suffix(".pdf") for letter, filename in ordered]
            for output in outputs:
                source = staging / output.relative_to(directory)
                pending_pdf = build / f"polygon-pdf-{uuid.uuid4().hex}.tmp"
                shutil.copyfile(source, pending_pdf)
                try:
                    for attempt in range(26):
                        try:
                            pending_pdf.replace(output)
                            break
                        except PermissionError:
                            if attempt == 25:
                                raise ValueError(f"Close the PDF viewer or wait for its build, then retry: {output}") from None
                            time.sleep(0.2)
                finally:
                    pending_pdf.unlink(missing_ok=True)
    print(f"Imported {', '.join(entry['letter'] for entry in entries)}; backup: {backup}", flush=True)
    if render:
        return outputs
    return [directory / entry["letter"] / (entry["slug"] + ".tex") for entry in entries]
