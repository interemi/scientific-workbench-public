import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK_FIXTURES = ROOT / "skills/scientific-data-notebooks/fixtures"


def load_fixture(name: str):
    path = NOTEBOOK_FIXTURES / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"exact_cli_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class ExactCLIOptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cross_domain = load_fixture("cross_domain_data_workbench")
        cls.duckdb = load_fixture("duckdb_workbench")
        cls.notebook = load_fixture("notebook_workbench")

    def parse(self, module, arguments):
        with patch.object(sys, "argv", [module.__file__, *arguments]):
            return module.parse_args()

    def assert_rejects_abbreviation(self, module, arguments, option):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                self.parse(module, arguments)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn(f"unrecognized arguments: {option}", stderr.getvalue())

    def test_cross_domain_and_duckdb_reject_abbreviated_sql(self):
        self.assert_rejects_abbreviation(
            self.cross_domain,
            ["input.csv", "--sq", "SELECT 1", "--output-dir", "/tmp/run"],
            "--sq",
        )
        self.assert_rejects_abbreviation(
            self.duckdb,
            ["input.csv", "--sq", "SELECT 1"],
            "--sq",
        )
        self.assert_rejects_abbreviation(
            self.cross_domain,
            ["input.csv", "--sq=SELECT 1", "--output-dir", "/tmp/run"],
            "--sq=SELECT 1",
        )
        self.assert_rejects_abbreviation(
            self.duckdb,
            ["input.csv", "--sq=SELECT 1"],
            "--sq=SELECT 1",
        )

        cross_domain = self.parse(
            self.cross_domain,
            ["input.csv", "--sql", "SELECT 1", "--output-dir", "/tmp/run"],
        )
        duckdb = self.parse(self.duckdb, ["input.csv", "--sql", "SELECT 1"])
        self.assertEqual(cross_domain.sql, "SELECT 1")
        self.assertEqual(duckdb.sql, "SELECT 1")

        duckdb_equals = self.parse(self.duckdb, ["input.csv", "--sql=SELECT 1"])
        self.assertEqual(duckdb_equals.sql, "SELECT 1")

    def test_notebook_rejects_abbreviated_replacement(self):
        arguments = [
            "execute-copy",
            "input.ipynb",
            "--output-dir",
            "/tmp/run",
            "--trust-notebook-code",
            "--replace-t",
            "TOKEN",
            "print('unsafe')",
        ]
        self.assert_rejects_abbreviation(self.notebook, arguments, "--replace-t")

        equals_arguments = arguments.copy()
        equals_arguments[5:7] = ["--replace-t=TOKEN"]
        self.assert_rejects_abbreviation(
            self.notebook, equals_arguments, "--replace-t=TOKEN"
        )

        exact = arguments.copy()
        exact[5] = "--replace-text"
        parsed = self.parse(self.notebook, exact)
        self.assertEqual(parsed.replace_text, [["TOKEN", "print('unsafe')"]])

        safe_file = self.parse(
            self.notebook,
            [
                "execute-copy",
                "input.ipynb",
                "--output-dir",
                "/tmp/run",
                "--trust-notebook-code",
                "--append-code-file",
                "reviewed.py",
            ],
        )
        self.assertEqual(safe_file.append_code_file, ["reviewed.py"])


if __name__ == "__main__":
    unittest.main()
