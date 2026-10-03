"""Export fetched Polygon API data into toolkit statement files (no network I/O)."""

import base64
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path


def select_examples(tests: Sequence[Mapping], inputs: Mapping[int, bytes],
                    answers: Mapping[int, bytes]) -> list[tuple[bytes, bytes]]:
    """Select statement tests and apply display overrides without changing judge data."""
    selected = [test for test in tests if test.get("useInStatements") is True]
    selected.sort(key=lambda test: test["index"])
    seen = set()
    examples = []
    for test in selected:
        index = test["index"]
        if type(index) is not int or index < 1 or index in seen:
            raise ValueError(f"Invalid or duplicate Polygon test index: {index}")
        seen.add(index)
        if test.get("inputForStatement") is not None:
            input_data = test["inputForStatement"].encode("utf-8")
        elif index in inputs:
            input_data = inputs[index]
        elif test.get("inputBase64") is not None:
            input_data = base64.b64decode(test["inputBase64"], validate=True)
        else:
            raise ValueError(f"Fetch exact input bytes for Polygon test {index}")
        if test.get("outputForStatement") is not None:
            output_data = test["outputForStatement"].encode("utf-8")
        elif index in answers:
            output_data = answers[index]
        else:
            raise ValueError(f"Fetch the generated answer for Polygon test {index}")
        for data in (input_data, output_data):
            if not isinstance(data, bytes):
                raise ValueError("Resolved test inputs and answers must be bytes")
            data.decode("utf-8-sig")  # Literal examples must be UTF-8 text.
        examples.append((input_data, output_data))
    return examples


def export_statement(destination: Path, *, letter: str, slug: str, language: str,
                     info: Mapping, statement: Mapping, tests: Sequence[Mapping],
                     inputs: Mapping[int, bytes], answers: Mapping[int, bytes],
                     resources: Mapping[str, bytes] | None = None) -> Path:
    """Export already-fetched API results into a NEW caller-owned problem directory.

    inputs/answers are exact bytes fetched with problem.testInput/testAnswer;
    verifyInputOutputForStatements remains Polygon's validator/checker responsibility.
    No credentials, downloads, submissions, or DOMjudge uploads happen here.
    """
    if not re.fullmatch(r"[A-Z]+", letter) or not re.fullmatch(r"[a-zA-Z0-9_-]+", slug):
        raise ValueError("Invalid contest letter or problem slug")
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*", language):
        raise ValueError("Invalid statement language")
    examples = select_examples(tests, inputs, answers)
    files = {}
    for key in ("name", "legend", "input", "output", "notes", "interaction", "scoring", "tutorial"):
        content = statement.get(key, "")
        if not isinstance(content, str):
            raise ValueError(f"Polygon statement {key} must be text")
        # API name is plain text; other fields are already TeX.
        if key == "name":
            escapes = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
                       "&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_",
                       "$": r"\$", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
            content = "".join(escapes.get(character, character) for character in content)
        files[f"{key}.tex"] = content.encode("utf-8")
    for number, (input_data, output_data) in enumerate(examples, 1):
        files[f"example.{number:02d}"] = input_data
        files[f"example.{number:02d}.a"] = output_data
    for name, data in (resources or {}).items():
        if Path(name).name != name or name in files or not name or any(c in name for c in "/\\:#%{}"):
            raise ValueError(f"Invalid or conflicting statement resource name: {name}")
        if not isinstance(data, bytes):
            raise ValueError("Statement resources must be bytes")
        files[name] = data
    destination = Path(destination).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("Choose a new or empty output directory; existing sources are preserved")
    metadata = {key: info.get(key) for key in ("timeLimit", "memoryLimit", "inputFile", "outputFile", "interactive")}
    metadata.update({"language": language, "sampleLayout": "auto"})
    sections = destination / "statement-sections" / language
    sections.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (sections / name).write_bytes(data)
    (destination / "statement.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8", newline="\n")
    wrapper = destination / f"{slug}.tex"
    wrapper.write_text(f"% !TeX root = ../main.tex\n\\polygonstatement{{{letter}}}{{statement-sections/{language}}}\n",
                       encoding="utf-8", newline="\n")
    return wrapper
