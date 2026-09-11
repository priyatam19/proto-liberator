#!/usr/bin/env python3
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import run_all
from run_all import _target_libs_for_profile


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class TestRunAll(unittest.TestCase):
    def test_profile_archive_discovery_supports_pie_naming(self):
        with tempfile.TemporaryDirectory() as td:
            lib_dir = Path(td)
            regular = lib_dir / "libminijail.pie.a"
            profile = lib_dir / "libminijail_profile.pie.a"
            regular.touch()
            profile.touch()

            self.assertEqual(_target_libs_for_profile([str(regular)]), [str(profile)])

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

    def test_saved_campaign_sources_replace_generated_files_silently(self):
        conditions = FIXTURES / "minimal_conditions.json"
        apis = FIXTURES / "minimal_apis_clang.jsonl"

        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            out_dir = temp_dir / "output"
            saved_dir = temp_dir / "saved"
            saved_dir.mkdir()
            saved_proto = saved_dir / "demo.v2.proto"
            saved_harness = saved_dir / "harness.cc"
            saved_proto.write_text('syntax = "proto3";\n// saved proto\n')
            saved_harness.write_text("// saved harness\n")

            argv = [
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
            ]
            output = io.StringIO()
            with (
                mock.patch.dict(
                    os.environ,
                    {"PROTO_LIBERATOR_GENERATED_HARNESS_DIR": str(saved_dir)},
                ),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(run_all, "_run"),
                redirect_stdout(output),
            ):
                self.assertEqual(run_all.main(), 0)

            self.assertEqual((out_dir / "demo.v2.proto").read_bytes(), saved_proto.read_bytes())
            self.assertEqual((out_dir / "harness.cc").read_bytes(), saved_harness.read_bytes())
            self.assertNotIn(str(saved_dir), output.getvalue())

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
