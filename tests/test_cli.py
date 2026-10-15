from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def test_cli_matches_the_brief_sample(self) -> None:
        result = subprocess.run([sys.executable, "alerts.py", "sample/prices.csv", "sample/rules.json"], cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "2026-09-03 r1 INFY level below 1500\n")
        self.assertEqual(result.stderr, "")

    def test_cli_returns_clean_error_for_missing_required_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prices, rules = Path(directory) / "bad.csv", Path(directory) / "rules.json"
            prices.write_text("date,close\n2026-01-01,1\n", encoding="utf-8")
            rules.write_text("[]", encoding="utf-8")
            result = subprocess.run([sys.executable, "alerts.py", str(prices), str(rules)], cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("instrument", result.stderr)
