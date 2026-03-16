#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
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

    def test_dry_run_v2_auto_feedback_signal(self):
        conditions = FIXTURES / "minimal_conditions.json"
        apis = FIXTURES / "minimal_apis_clang.jsonl"

        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "output_orch"
            api_stats_dir = out_dir / "api_stats"
            api_stats_dir.mkdir(parents=True, exist_ok=True)
            (api_stats_dir / "api_stats.1234.json").write_text(
                json.dumps({"apis": [{"name": "Foo", "seen": 10, "executed": 0, "skipped": 0}]})
            )

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

            self.assertIn("feedback_aggregator.py", proc.stdout)
            self.assertIn("--novelty-signal-json", proc.stdout)
            self.assertIn(str(api_stats_dir / "api_stats.json"), proc.stdout)

    def test_dry_run_fuzz_refreshes_feedback_signal(self):
        conditions = FIXTURES / "minimal_conditions.json"
        apis = FIXTURES / "minimal_apis_clang.jsonl"

        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "output_orch"
            api_stats_dir = out_dir / "api_stats"
            api_stats_dir.mkdir(parents=True, exist_ok=True)
            (api_stats_dir / "api_stats.1111.json").write_text(
                json.dumps({"apis": [{"name": "Foo", "seen": 1, "executed": 1, "skipped": 0}]})
            )

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
                    "--fuzz",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=True,
            )

            self.assertIn("feedback_aggregator.py", proc.stdout)
            self.assertIn("feedback signal refreshed", proc.stdout)
            self.assertIn("feedback refresh metrics:", proc.stdout)
            self.assertIn("apis=1", proc.stdout)
            self.assertIn("learned_edges=0", proc.stdout)
            self.assertIn("prefix_weights=0", proc.stdout)
            self.assertIn("feedback refresh outputs:", proc.stdout)
            self.assertIn(str(api_stats_dir / "api_stats.json"), proc.stdout)
            self.assertIn(str(api_stats_dir / "learned_edges.json"), proc.stdout)
            self.assertIn(str(api_stats_dir / "prefix_weights.json"), proc.stdout)
            self.assertIn("crash_classifier.py", proc.stdout)
            self.assertIn("crash classification summary:", proc.stdout)
            self.assertIn("constraint_misuse=0", proc.stdout)
            self.assertIn(str(out_dir / "crashes" / "summary.json"), proc.stdout)
            self.assertIn("crash_constraint_learner.py", proc.stdout)
            self.assertIn("crash learning summary:", proc.stdout)
            self.assertIn("constraints=0", proc.stdout)
            self.assertIn(str(out_dir / "crashes" / "crash_learned_constraints.json"), proc.stdout)

    def test_dry_run_timed_fuzz_runs_feedback_watchdog_and_reseeds(self):
        conditions = FIXTURES / "minimal_conditions.json"
        apis = FIXTURES / "minimal_apis_clang.jsonl"

        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "output_orch"
            api_stats_dir = out_dir / "api_stats"
            api_stats_dir.mkdir(parents=True, exist_ok=True)
            (api_stats_dir / "api_stats.2222.json").write_text(
                json.dumps({"apis": [{"name": "Foo", "seen": 3, "executed": 0, "skipped": 0}]})
            )

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
                    "--fuzz",
                    "--fuzz-duration",
                    "601",
                    "--feedback-refresh-sec",
                    "300",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=True,
            )

            self.assertIn("-max_total_time=300", proc.stdout)
            self.assertIn("-max_total_time=1", proc.stdout)
            self.assertGreaterEqual(proc.stdout.count("feedback_aggregator.py"), 3)
            self.assertIn("seed_generator.py", proc.stdout)
            self.assertIn("feedback reseed complete:", proc.stdout)


if __name__ == "__main__":
    unittest.main()
