"""Export a local, complete deployment bundle without accessing an archive or APIs."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

from kgupc_toolkit.build import read_problems

from .importer import load_config
from .targeting import contest_id, require_private_directory


def require_export_directory(directory):
    """Allow private folders or this tool's ignored build/archive area only."""
    directory = Path(directory).resolve()
    repo = next((parent for parent in (directory, *directory.parents) if (parent / ".git").exists()), None)
    if repo is None:
        return directory
    if not (repo / "src/kgupc_pol2dom/cli.py").is_file() or not directory.is_relative_to(repo / "build/archive"):
        raise ValueError("Export outside Git or into kgupc-pol2dom/build/archive; copy to the archive manually")
    relative = directory.relative_to(repo).as_posix() + "/"
    git = ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo)]
    ignored = subprocess.run(git + ["check-ignore", "--quiet", "--no-index", relative], capture_output=True)
    tracked = subprocess.run(git + ["ls-files", "--cached", "--", relative], capture_output=True)
    if ignored.returncode != 0 or tracked.returncode != 0 or tracked.stdout.strip():
        raise ValueError("Export directory must be Git-ignored and contain no tracked files")
    return directory


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def public_statement_files(run, manifest):
    """Select editable statements and PDFs, excluding packages, credentials and build logs."""
    problems = run / "problems"
    entries = read_problems(problems)
    config = load_config(run / "polygon-import.json")
    if contest_id(config.get("contestId")) != contest_id(manifest.get("contestId")):
        raise ValueError("Bundle and problem mapping target different Polygon contests")
    records = manifest.get("problems")
    if not isinstance(records, list) or not records:
        raise ValueError("Bundle has no problems")
    mapped = {(p["letter"], p["slug"] + ".tex", p["problemId"]) for p in config["problems"]}
    bundled = {(p["letter"], p["slug"] + ".tex", p["problemId"]) for p in records}
    if len(mapped) != len(config["problems"]) or len(bundled) != len(records) or mapped != bundled:
        raise ValueError("Bundle and problem mapping differ")
    if set(entries) != {(letter, filename) for letter, filename, _ in mapped}:
        raise ValueError("Bundle problem list differs from the editable sources")
    files = [run / "toolkit.lock.json", problems / "main.tex", problems / "main.pdf", problems / "problem-list.tex"]
    lock = json.loads(files[0].read_text(encoding="utf-8"))
    if lock != manifest.get("toolkit") or lock.get("schema") != 1:
        raise ValueError("Bundle toolkit lock does not match its manifest")
    # Do not require the currently installed toolkit to match: this is a byte-preserving export.
    for record in records:
        letter, slug = record["letter"], record["slug"]
        folder = problems / letter
        pdf = folder / (slug + ".pdf")
        if not pdf.is_file() or digest(pdf) != record.get("pdfSha256"):
            raise ValueError(f"Problem {letter}: PDF differs from the completed bundle")
        files.extend([folder / (slug + ".tex"), pdf, folder / "statement.json", folder / "polygon-source.json"])
        source = json.loads((folder / "polygon-source.json").read_text(encoding="utf-8"))
        if source.get("problemId") != record["problemId"] or source.get("revision") != record.get("revision") or source.get("modified"):
            raise ValueError(f"Problem {letter}: source revision differs from the completed bundle")
        sections = folder / "statement-sections"
        if not sections.is_dir():
            raise ValueError(f"Problem {letter}: editable statement sections are missing")
        for resource in sections.rglob("*"):
            if resource.is_symlink():
                raise ValueError("Statement export cannot contain symbolic links")
            if resource.is_file():
                if resource.name == ".env" or resource.name.startswith(".env."):
                    raise ValueError("Credentials cannot be exported with statement resources")
                files.append(resource)
    for path in files:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(run):
            raise ValueError("Export requires complete local files without symbolic links")
    return files


def validate_contest_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"[0-9]{4}(?:-[a-zA-Z0-9]+)*", name):
        raise ValueError("Set CONTEST_SLUG to a folder name such as 2025 or 2026-fall")
    return name


def export_archive(run, name, *, output=None, replace_generated=False):
    """Produce <output>/<name>; never download, render, update a contest or publish."""
    validate_contest_name(name)
    run = require_private_directory(run)
    destination = require_export_directory((Path(output) if output is not None else Path.cwd() / "build/archive") / name)
    if destination.exists() and not replace_generated:
        raise ValueError("Export already exists; choose a new output folder (existing exports are never replaced)")
    if destination.is_relative_to(run) or run.is_relative_to(destination):
        raise ValueError("Export and bundle directories must be separate")
    manifest = json.loads((run / "deployment.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 2 or manifest.get("complete") is not True:
        raise ValueError("Export requires a completed full-contest bundle, not a partial run")
    files = public_statement_files(run, manifest)
    if destination.exists():
        # Only our same-contest handoff may be refreshed. Local edits are preserved in history.
        previous = destination / "archive-source.json"
        if not previous.is_file() or previous.is_symlink():
            raise ValueError("Existing output is not a generated export; choose another CONTEST_SLUG")
        audit = json.loads(previous.read_text(encoding="utf-8"))
        if audit.get("schema") != 1 or audit.get("contestId") != contest_id(manifest["contestId"]) or not isinstance(audit.get("files"), dict):
            raise ValueError("Existing export belongs to another contest or has invalid provenance")
        if any(path.is_symlink() for path in destination.rglob("*")):
            raise ValueError("Existing export cannot contain symbolic links")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".archive-export-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        hashes = {}
        for source in files:
            relative = source.relative_to(run)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            hashes[relative.as_posix()] = digest(target)
        # Provenance contains only public source identifiers, never URLs, accounts or API settings.
        provenance = {"schema": 1, "contestId": contest_id(manifest["contestId"]),
                      "toolkit": manifest["toolkit"],
                      "problems": [{key: p[key] for key in ("letter", "slug", "problemId", "revision", "pdfSha256")} for p in manifest["problems"]],
                      "files": hashes}
        (stage / "archive-source.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (stage / "requirements.txt").write_text(f"kgupc-toolkit=={manifest['toolkit']['version']}\n", encoding="utf-8")
        require_export_directory(destination)
        backup = None
        if destination.exists():
            backup = require_export_directory(destination.parent / "history" / uuid.uuid4().hex / name)
            backup.parent.mkdir(parents=True, exist_ok=True)
            # Both absolute paths were checked to stay in this tool's output area (or private output).
            if destination.is_symlink() or not backup.is_relative_to(destination.parent):
                raise ValueError("Export paths changed during refresh")
            shutil.move(str(destination), str(backup))
        try:
            # copytree gives the folder normal inherited ACLs on Windows, without merging old files.
            shutil.copytree(stage, destination)
        except BaseException:
            # Remove only this newly created, verified output before restoring its backup.
            if destination.exists():
                if destination.is_symlink() or destination.resolve().parent != stage.parent.resolve():
                    raise RuntimeError("Cannot restore export whose destination changed")
                shutil.rmtree(destination)
            if backup is not None:
                shutil.move(str(backup), str(destination))
            raise
        if backup is not None:
            print(f"Previous local export backed up: {backup}", flush=True)
    print(f"Standalone contest folder ready: {destination}", flush=True)
    print("After the contest ends, review and copy this folder into kgupc-archive yourself.", flush=True)
    return destination
