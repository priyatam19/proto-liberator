#!/usr/bin/env python3
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class TestRunAll(unittest.TestCase):
    def test_dry_run_v2(self):
        out_dir = REPO_ROOT / "tests" / "output_orch"
        conditions = FIXTURES / "minimal_conditions.json"
        apis = FIXTURES / "minimal_apis_clang.jsonl"

        proc = subprocess.run(
            [
                sys.executable,
                str(SRC_DIR / "run_all.py"),
                "--library",
                "demo",
                "--conditions",
                str(conditions),
                "--apis",
                str(apis),
                "--out-dir",
                str(out_dir),
                "--schema-mode",
                "v2",
                "--dry-run",
                "--generate-seeds",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=True,
        )

        self.assertIn("proto_generator.py", proc.stdout)
        self.assertIn("wrapper_generator.py", proc.stdout)
        self.assertIn("--schema-mode v2", proc.stdout)
        self.assertIn("seed_generator.py", proc.stdout)


if __name__ == "__main__":
    unittest.main()

