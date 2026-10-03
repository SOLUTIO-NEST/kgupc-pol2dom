import base64
import json
import tempfile
import unittest
from pathlib import Path

from kgupc_pol2dom.polygon import export_statement, select_examples


class PolygonExportTests(unittest.TestCase):
    def test_selection_order_and_display_overrides(self):
        tests = [{"index": 7, "useInStatements": True},
                 {"index": 1, "useInStatements": False},
                 {"index": 2, "useInStatements": True,
                  "inputForStatement": "shown input\n", "outputForStatement": "shown output\n"}]
        inputs = {1: b"hidden", 2: b"raw input", 7: b"generated"}
        answers = {1: b"hidden answer", 2: b"raw answer", 7: b"generated answer"}
        self.assertEqual(select_examples(tests, inputs, answers),
                         [(b"shown input\n", b"shown output\n"), (b"generated", b"generated answer")])
        self.assertEqual(inputs[2], b"raw input")

    def test_empty_display_override_is_not_replaced(self):
        tests = [{"index": 1, "useInStatements": True,
                  "inputForStatement": "", "outputForStatement": ""}]
        self.assertEqual(select_examples(tests, {1: b"raw"}, {1: b"answer"}), [(b"", b"")])

    def test_exact_base64_input_is_used_instead_of_lossy_text(self):
        value = b"1  2\r\nliteral_#%{}\r\n"
        tests = [{"index": 1, "useInStatements": True, "input": "lossy",
                  "inputBase64": base64.b64encode(value).decode("ascii")}]
        self.assertEqual(select_examples(tests, {}, {1: b"3\n"}), [(value, b"3\n")])

    def test_missing_generated_answer_fails(self):
        with self.assertRaisesRegex(ValueError, "generated answer"):
            select_examples([{"index": 1, "useInStatements": True}], {1: b"input"}, {})

    def test_exported_files_have_polygon_shape_and_preserve_existing_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "A"
            wrapper = export_statement(destination, letter="A", slug="test", language="korean",
                                       info={"timeLimit": 1000, "memoryLimit": 256},
                                       statement={"name": "A & B", "legend": "Story", "input": "Input",
                                                  "output": "Output", "tutorial": "SECRET-SOLUTION"},
                                       tests=[{"index": 1, "useInStatements": True}],
                                       inputs={1: b"1947\n"}, answers={1: b"KGU AI CSE\n"})
            sections = destination / "statement-sections/korean"
            self.assertEqual((sections / "example.01").read_bytes(), b"1947\n")
            self.assertEqual((sections / "name.tex").read_text(encoding="utf-8"), r"A \& B")
            self.assertEqual(json.loads((destination / "statement.json").read_text())["timeLimit"], 1000)
            self.assertIn("polygonstatement", wrapper.read_text())
            with self.assertRaisesRegex(ValueError, "existing sources"):
                export_statement(destination, letter="A", slug="test", language="korean", info={},
                                 statement={}, tests=[], inputs={}, answers={})
