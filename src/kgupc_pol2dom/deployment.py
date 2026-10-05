"""Create complete DOMjudge ZIPs from one committed Polygon revision per problem."""

from datetime import datetime, timezone
from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile

from kgupc_toolkit import __version__
from kgupc_toolkit.resources import package_digest

from .api import PolygonError
from .domjudge import DOMjudgeError, target_contest
from .importer import fetch_problem
from .preparation import main_document, discover_config, write_json
from .metadata import validate_metadata
from .renderer import render_contest
from .targeting import contest_id, require_private_directory


def sha256(path):
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(file.read()).hexdigest()


def current_problem(client, problem_id):
    values = client.request("problems.list", id=problem_id)
    problem = next((value for value in values if value.get("id") == problem_id), None)
    if problem is None or problem.get("modified"):
        raise PolygonError(f"Problem {problem_id}: commit all changes in Polygon before deployment")
    if type(problem.get("revision")) is not int:
        raise PolygonError(f"Problem {problem_id}: missing committed revision")
    return problem


def ready_package(client, problem_id, revision, *, build_packages=False, wait_seconds=600):
    def matching():
        packages = client.request("problem.packages", problemId=problem_id)
        if not isinstance(packages, list):
            raise PolygonError("Invalid Polygon package list")
        return [p for p in packages if p.get("revision") == revision and p.get("type") == "linux"]

    packages = matching()
    ready = [p for p in packages if p.get("state") == "READY"]
    if ready:
        return max(ready, key=lambda p: p["id"])
    if not build_packages:
        raise PolygonError(f"Problem {problem_id}: no READY Linux Full package for revision {revision}. "
                           "Build a Full package in Polygon, or run with --build-packages")
    client.request("problem.buildPackage", problemId=problem_id, full=True, verify=True)
    print(f"Waiting for Polygon Full package: {problem_id}, revision {revision}", flush=True)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(5)
        if current_problem(client, problem_id)["revision"] != revision:
            raise PolygonError("Polygon revision changed while building its package; retry")
        packages = matching()
        ready = [p for p in packages if p.get("state") == "READY"]
        if ready:
            return max(ready, key=lambda p: p["id"])
        # Failed Full builds may expose only a standard entry; inspect that too.
        all_packages = client.request("problem.packages", problemId=problem_id)
        latest = max((p for p in all_packages if p.get("revision") == revision),
                     key=lambda p: p["id"], default={})
        if latest.get("state") == "FAILED":
            raise PolygonError(f"Problem {problem_id}: Polygon package build failed; inspect Packages in Polygon")
    raise PolygonError(f"Problem {problem_id}: package build timed out; inspect Polygon and retry")


def safe_path(value):
    path = PurePosixPath(value)
    if not value or "\\" in value or ":" in value or path.is_absolute() or ".." in path.parts:
        raise ValueError("Unsafe path in Polygon package")
    return path


def extract_package(package, destination, slug, testset):
    seen = set()
    with zipfile.ZipFile(package) as archive:
        if sum(item.file_size for item in archive.infolist()) > 2 * 1024 ** 3:
            raise ValueError("Polygon package exceeds 2 GiB uncompressed")
        for item in archive.infolist():
            safe_path(item.filename)
            canonical = item.filename.rstrip("/").casefold()
            if canonical in seen or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("Polygon package contains duplicate paths or symbolic links")
            seen.add(canonical)
        archive.extractall(destination)
    descriptor = destination / "problem.xml"
    data = descriptor.read_bytes()
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("Unsupported XML entities in Polygon package")
    problem = ET.fromstring(data)
    if problem.tag != "problem" or problem.get("short-name") != slug:
        raise ValueError("Polygon package problem name does not match the selected problem")
    for element in problem.iter():
        if "path" in element.attrib:
            safe_path(element.attrib["path"])
    judging = problem.find("judging")
    if judging is None or judging.get("run-count", "1") != "1" or problem.find("assets/interactor") is not None:
        raise ValueError("This deployment currently supports single-pass non-interactive problems only")
    if judging.get("input-file", "") or judging.get("output-file", ""):
        raise ValueError("DOMjudge deployment requires standard input/output")
    sets = [item for item in judging.findall("testset") if item.get("name") == testset]
    if len(sets) != 1 or not sets[0].findall("tests/test"):
        raise ValueError("Missing or empty selected testset in Polygon Full package")
    for field in ("input-path-pattern", "answer-path-pattern"):
        safe_path(sets[0].findtext(field) or "")
    return problem, sets[0]


def convert_package(package, output, pdf, entry, language, testset, revision):
    import yaml

    with tempfile.TemporaryDirectory(prefix="convert-", dir=output.parent) as temporary:
        extracted = Path(temporary)
        problem, tests = extract_package(package, extracted, entry["slug"], testset)
        if problem.get("revision") is not None and int(problem.get("revision")) != revision:
            raise ValueError("Polygon ZIP revision differs from its API metadata")
        try:
            # Keep original judge data. Display-only examples belong exclusively in the PDF.
            # Classify samples ourselves: p2d 0.4.0 treats sample="false" as true.
            # p2d reads jury sources using Python's default encoding. Isolate it in
            # UTF-8 mode so Korean comments and multiple expected verdicts work on Windows.
            subprocess.run([sys.executable, "-X", "utf8", "-m", "kgupc_pol2dom.converter",
                            str(extracted), str(output), entry.get("domLabel", entry["letter"]),
                            entry.get("externalId", f"kgupc-{entry['problemId']}"), language, testset], check=True)
        except subprocess.CalledProcessError:
            raise ValueError(f"Problem {entry['letter']}: p2d conversion failed; inspect the converter output") from None
        with zipfile.ZipFile(output) as archive:
            contents = {item.filename: (item, archive.read(item)) for item in archive.infolist() if not item.is_dir()}
        input_pattern = tests.findtext("input-path-pattern")
        answer_pattern = tests.findtext("answer-path-pattern")
        inputs = [name for name in contents if name.startswith("data/") and name.endswith(".in")]
        test_list = tests.findall("tests/test")
        if len(inputs) != len(test_list):
            raise ValueError("Converted test count differs from Polygon")
        for index, test in enumerate(test_list, 1):
            for extension, pattern in (("in", input_pattern), ("ans", answer_pattern)):
                name = f"data/secret/{index:02d}.{extension}"
                expected = (extracted / safe_path(pattern % index)).read_bytes()
                if name not in contents or contents[name][1] != expected:
                    raise ValueError(f"Judge test {index} differs from the original Polygon bytes")
                if test.get("sample", "false").lower() == "true":
                    item, content = contents.pop(name)
                    new_name = name.replace("/secret/", "/sample/")
                    item.filename = new_name
                    contents[new_name] = item, content
            description = f"data/secret/{index:02d}.desc"
            if test.get("sample", "false").lower() == "true" and description in contents:
                item, content = contents.pop(description)
                item.filename = description.replace("/secret/", "/sample/")
                contents[item.filename] = item, content
        # Each Java jury solution needs its own directory: otherwise multiple
        # Main.java files in the same verdict group would overwrite each other.
        for filename in list(contents):
            if not filename.startswith("submissions/") or not filename.endswith(".java"):
                continue
            path = PurePosixPath(filename)
            destination = str(path.parent / path.stem / "Main.java")
            if destination in contents:
                raise ValueError("Java jury solution destination collision")
            item, content = contents.pop(filename)
            if item is not None:
                item.filename = destination
            contents[destination] = item, content
        metadata = yaml.safe_load(contents["problem.yaml"][1])
        name = problem.find(f"names/name[@language='{language}']")
        if name is None or not name.get("value"):
            raise ValueError("Polygon package lacks the selected statement language name")
        metadata["name"] = name.get("value")
        contents["problem.yaml"] = (None, yaml.safe_dump(metadata, allow_unicode=True).encode("utf-8"))
        # Retain the input validator for package verification tools, when present.
        validator = problem.find("assets/validator/source")
        header_destinations = ["output_validators/checker"]
        if validator is not None:
            source = extracted / safe_path(validator.get("path", ""))
            contents["input_validators/validator/" + source.name] = (None, source.read_bytes())
            header_destinations.append("input_validators/validator")
        for resource in problem.findall("files/resources/file"):
            source = extracted / safe_path(resource.get("path", ""))
            if source.suffix.lower() not in (".h", ".hpp"):
                continue
            for folder in header_destinations:
                # p2d's DOMjudge-compatible testlib.h must take precedence for checkers.
                filename = folder + "/" + source.name
                if filename not in contents:
                    contents[filename] = (None, source.read_bytes())
        contents["problem_statement/problem.pdf"] = (None, pdf.read_bytes())
        pending = output.with_suffix(".pending.zip")
        with zipfile.ZipFile(pending, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for filename, (item, content) in sorted(contents.items()):
                archive.writestr(item or filename, content)
        pending.replace(output)
        return {"testCount": len(test_list), "sampleCount": sum(test.get("sample", "false").lower() == "true" for test in test_list),
                "validation": metadata.get("validation"), "solutionCount": sum(name.startswith("submissions/") for name in contents)}


def external_problem_id(dom_contest, polygon_contest, problem_id):
    target_contest({"DOMJUDGE_CONTEST_ID": dom_contest})
    value = f"polygon-{dom_contest}-{contest_id(polygon_contest)}-{problem_id}"
    if type(problem_id) is not int or problem_id <= 0 or len(value) > 200:
        raise ValueError("Invalid source problem or DOMjudge contest ID")
    return value


def build_bundle(client, target, output=None, *, letters=None, language="korean", testset="tests", build_packages=False, dom_contest=None,
                 metadata=None):
    metadata = validate_metadata(metadata)
    document = main_document(metadata)
    target = contest_id(target)
    output = require_private_directory(output or Path.home() / "kgupc-work" / f"deploy-{target}")
    marker = output / "polygon-target.json"
    target_contest({"DOMJUDGE_CONTEST_ID": dom_contest})
    if output.exists() and any(output.iterdir()):
        if not marker.is_file() or json.loads(marker.read_text())["contestId"] != target:
            raise ValueError("Deployment directory belongs to another contest or has no target marker")
    config = discover_config(client, target, language=language, testset=testset)
    entries = config["problems"]
    all_ids = {item["problemId"] for item in entries}
    if letters:
        if set(letters) - {item["letter"] for item in entries}:
            raise ValueError("Selected letters are missing from Polygon")
        entries = [item for item in entries if item["letter"] in set(letters)]
    output.mkdir(parents=True, exist_ok=True)
    workspace = json.loads(marker.read_text()) if marker.exists() else {"schema": 1, "contestId": target}
    workspace.pop("workspaceId", None)
    write_json(marker, workspace)
    runs = output / "runs"
    runs.mkdir(exist_ok=True)
    run = runs / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
    run.mkdir()
    problems = run / "problems"
    problems.mkdir()
    (problems / "main.tex").write_text(document, encoding="utf-8", newline="\n")
    (problems / "problem-list.tex").write_text("".join(f"\\includeproblem{{{e['letter']}}}{{{e['slug']}.tex}}\n" for e in entries), encoding="utf-8")
    write_json(run / "toolkit.lock.json", {"schema": 1, "version": __version__, "package_sha256": package_digest()})
    write_json(run / "polygon-import.json", {**config, "problems": entries})
    downloads, packages = run / "polygon-packages", run / "domjudge-packages"
    downloads.mkdir()
    packages.mkdir()
    records = []
    for entry in entries:
        print(f"Fetching {entry['letter']}: Polygon {entry['problemId']}", flush=True)
        before = current_problem(client, entry["problemId"])
        revision = before["revision"]
        package = ready_package(client, entry["problemId"], revision, build_packages=build_packages)
        download = downloads / (entry["letter"] + ".zip")
        download.write_bytes(client.request("problem.package", binary=True, problemId=entry["problemId"], packageId=package["id"], type="linux"))
        fetch_problem(client, entry, problems / entry["letter"], language=language, testset=testset)
        provenance = json.loads((problems / entry["letter"] / "polygon-source.json").read_text())
        after = current_problem(client, entry["problemId"])
        if provenance["revision"] != revision or after["revision"] != revision:
            raise PolygonError("Polygon problem changed between package and statement downloads; retry")
        records.append({**entry, "domLabel": entry["letter"], "externalId": external_problem_id(dom_contest, target, entry["problemId"]),
                        "revision": revision, "packageId": package["id"], "polygonSha256": sha256(download)})
    render_contest(problems / "main.tex", lock=run / "toolkit.lock.json")
    for record in records:
        letter = record["letter"]
        pdf = problems / letter / (record["slug"] + ".pdf")
        package = packages / (letter + ".zip")
        counts = convert_package(downloads / (letter + ".zip"), package, pdf, record, language, testset, record["revision"])
        record.update(counts, zip=f"domjudge-packages/{letter}.zip", sha256=sha256(package), pdfSha256=sha256(pdf))
    manifest = {"schema": 2, "contestId": target, "domjudgeContestId": dom_contest,
                "contestMetadata": metadata,
                "complete": {item["problemId"] for item in entries} == all_ids, "language": language, "testset": testset,
                "toolkit": json.loads((run / "toolkit.lock.json").read_text()), "converter": "p2d==0.4.0", "problems": records}
    write_json(run / "deployment.json", manifest)
    write_json(output / "latest.json", {"schema": 1, "run": run.name})
    print(f"DOMjudge bundle ready: {run / 'deployment.json'}", flush=True)
    return run


@contextmanager
def upload_lock(directory):
    """Serialize remote writes and release automatically on exit or process death."""
    with (directory / ".domjudge-upload.lock").open("a+b") as file:
        if file.tell() == 0:
            file.write(b"\0")
            file.flush()
        file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            raise DOMjudgeError("Another DOMjudge upload is running for this workspace; retry after it finishes") from None
        try:
            yield
        finally:
            file.seek(0)
            if os.name == "nt":
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def upload_bundle(client, settings, run):
    run = require_private_directory(run)
    with upload_lock(run.parent.parent):
        return _upload_bundle(client, settings, run)


def _upload_bundle(client, settings, run):
    run = require_private_directory(run)
    target = target_contest(settings)
    manifest = json.loads((run / "deployment.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 2:
        raise ValueError("Regenerate this bundle with the current sync format before uploading")
    from .targeting import resolve_target
    resolve_target(settings, configured=manifest["contestId"])
    if manifest.get("domjudgeContestId") != target:
        raise DOMjudgeError("Bundle targets another DOMjudge contest; regenerate for the configured contest")
    if type(manifest.get("complete")) is not bool or not manifest.get("problems"):
        raise ValueError("Deployment must contain a nonempty, explicitly scoped problem list")
    receipt_file = run.parent.parent / "domjudge-receipt.json"
    receipt = {"schema": 2, "url": client.url, "contestId": target, "polygonContestId": manifest["contestId"], "problems": {}}
    client.contest(target)
    desired = {}
    # Complete all validation before changing any contest association.
    for problem in manifest["problems"]:
        if not re.fullmatch(r"[A-Z]+", problem["letter"]):
            raise ValueError("Invalid deployment letter")
        expected_id = external_problem_id(target, manifest["contestId"], problem["problemId"])
        if problem.get("domLabel") != problem["letter"] or problem.get("externalId") != expected_id:
            raise ValueError("Bundle must use Polygon letters and stable source problem IDs")
        if problem["letter"] in desired or expected_id in desired.values():
            raise ValueError("Duplicate problem letter or source ID in deployment")
        desired[problem["letter"]] = expected_id
        package = run / safe_path(problem["zip"])
        if sha256(package) != problem["sha256"]:
            raise ValueError("DOMjudge ZIP changed after bundle creation; regenerate the bundle")
    wanted_ids = set(desired.values())
    # Resolve label conflicts first, including changed Polygon letter assignments.
    # Only associations in the configured contest are removed; global problems are retained.
    for remote in client.problems(target):
        remote_id = str(remote["id"])
        label = remote["label"]
        if ((label in desired and desired[label] != remote_id)
                or (remote_id in wanted_ids and desired.get(label) != remote_id)):
            client.unlink(target, remote_id)
            print(f"DOMjudge: removed conflicting contest problem {label}", flush=True)
    for problem in manifest["problems"]:
        letter = problem["letter"]
        result = client.sync_problem(target, run / problem["zip"], problem["externalId"])
        remote = next((item for item in client.problems(target) if str(item["id"]) == problem["externalId"]), None)
        if remote is None or remote.get("label") != letter:
            raise DOMjudgeError(f"DOMjudge {letter}: source problem ID or Polygon letter was not applied; inspect the server")
        if "test_data_count" in remote and remote["test_data_count"] != problem.get("testCount"):
            raise DOMjudgeError(f"DOMjudge {letter}: server test count differs from the Polygon package")
        receipt["problems"][letter] = {"problemId": str(result["problem_id"]), "apiId": str(remote["id"]), "label": letter,
                                        "polygonProblemId": problem["problemId"], "revision": problem["revision"], "sha256": problem["sha256"]}
        pending = receipt_file.with_suffix(".pending.json")
        write_json(pending, receipt)
        pending.replace(receipt_file)
        print(f"DOMjudge {letter}: uploaded ({result['problem_id']})", flush=True)
        messages = result.get("messages")
        if isinstance(messages, dict):
            # Count individual messages, not severity groups. Do not echo arbitrary server text.
            counts = {severity: len(messages.get(severity, [])) if isinstance(messages.get(severity), list) else 0
                      for severity in ("info", "warning", "danger")}
            print("  Server import messages: " + ", ".join(f"{key}={value}" for key, value in counts.items()), flush=True)
            warnings = messages.get("warning", [])
            if isinstance(warnings, list) and any("must associate team with your user" in str(value) for value in warnings):
                print("  Jury solutions were not submitted: associate the upload account with a team in DOMjudge.", flush=True)
                print("  Teams: create a jury test team and add it to the target contest; Users: select that team for the upload account.", flush=True)
                print("  Keep the admin role. Activate the contest (it need not start), check judgehosts, then upload again.", flush=True)
            if counts["warning"] or counts["danger"]:
                print("  Inspect the jury interface for import warnings.", flush=True)
        elif messages:
            print("  Inspect the jury interface for import messages.", flush=True)
    # Remove leftovers only after every desired problem was registered successfully.
    if manifest["complete"]:
        for remote in client.problems(target):
            if str(remote["id"]) not in wanted_ids:
                client.unlink(target, remote["id"])
                print(f"DOMjudge: removed contest problem {remote['label']} absent from Polygon", flush=True)
    actual = {str(item["id"]): item["label"] for item in client.problems(target)}
    if any(actual.get(problem_id) != letter for letter, problem_id in desired.items()):
        raise DOMjudgeError("DOMjudge problem list does not match the requested Polygon problems")
    if manifest["complete"] and set(actual) != wanted_ids:
        raise DOMjudgeError("DOMjudge contest still contains problems absent from Polygon")
    print("DOMjudge sync complete: " + ", ".join(desired), flush=True)
    print("Upload complete does not confirm judging: check Submissions and Judging Verifier for expected verdicts.", flush=True)
    return receipt
