#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from feedback_aggregator import build_feedback_signal, main as feedback_main  # noqa: E402


class TestFeedbackAggregator(unittest.TestCase):
    def test_build_feedback_signal_merges_stats_and_novelty(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p1 = root / "api_stats.100.json"
            p2 = root / "api_stats.101.json"
            p1.write_text(
                json.dumps(
                    {
                        "apis": [
                            {"name": "A", "seen": 10, "executed": 1, "skipped": 0},
                            {"name": "B", "seen": 10, "executed": 8, "skipped": 2},
                        ],
                        "pairs": [{"src": "A", "dst": "B", "count": 3}],
                        "prefixes": [{"seq": "A,B", "count": 2}],
                    }
                )
            )
            p2.write_text(
                json.dumps(
                    {
                        "apis": [
                            {"name": "A", "seen": 6, "executed": 0, "skipped": 1},
                            {"name": "B", "seen": 4, "executed": 3, "skipped": 1},
                        ],
                        "pairs": [{"src": "A", "dst": "B", "count": 2}],
                        "prefixes": [{"seq": "A,B", "count": 3}],
                    }
                )
            )

            signal = build_feedback_signal([p1, p2])
            rows = {row["name"]: row for row in signal["apis"]}

            self.assertEqual(rows["A"]["seen"], 16)
            self.assertEqual(rows["A"]["executed"], 1)
            self.assertEqual(rows["A"]["skipped"], 1)
            self.assertEqual(rows["B"]["seen"], 14)
            self.assertEqual(rows["B"]["executed"], 11)
            self.assertEqual(rows["B"]["skipped"], 3)

            self.assertGreater(signal["api_novelty"]["A"], signal["api_novelty"]["B"])
            self.assertEqual(signal["meta"]["input_files"], 2)
            self.assertEqual(signal["meta"]["api_count"], 2)
            self.assertEqual(signal["meta"]["pair_count"], 1)
            self.assertEqual(signal["meta"]["prefix_count"], 1)
            self.assertEqual(signal["pairs"][0]["count"], 5)
            self.assertIn("A,B", signal["prefix_weights"])
            self.assertEqual(signal["learned_edges"][0]["src"], "A")
            self.assertEqual(signal["learned_edges"][0]["dst"], "B")
            self.assertEqual(signal["meta"]["pair_signal_source"], "pairs")

    def test_prefers_coverage_conditioned_pairs_when_present(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p1 = root / "api_stats.100.json"
            p1.write_text(
                json.dumps(
                    {
                        "apis": [
                            {"name": "A", "seen": 10, "executed": 10, "skipped": 0},
                            {"name": "B", "seen": 10, "executed": 10, "skipped": 0},
                            {"name": "C", "seen": 2, "executed": 1, "skipped": 0},
                            {"name": "D", "seen": 2, "executed": 1, "skipped": 0},
                        ],
                        "pairs": [
                            {"src": "A", "dst": "B", "count": 40},
                            {"src": "C", "dst": "D", "count": 1},
                        ],
                        "coverage_pairs": [
                            {"src": "C", "dst": "D", "count": 4},
                        ],
                        "coverage_prefixes": [
                            {"seq": "C,D", "count": 4},
                        ],
                    }
                )
            )

            signal = build_feedback_signal([p1], min_pair_count=1, min_prefix_count=1)
            self.assertEqual(signal["meta"]["pair_signal_source"], "coverage_pairs")
            self.assertEqual(signal["meta"]["prefix_signal_source"], "coverage_prefixes")
            self.assertEqual(signal["meta"]["coverage_pair_count"], 1)
            self.assertEqual(signal["learned_edges"][0]["src"], "C")
            self.assertEqual(signal["learned_edges"][0]["dst"], "D")
            self.assertIn("C,D", signal["prefix_weights"])
            self.assertNotIn("A,B", signal["prefix_weights"])

    def test_main_writes_default_api_stats_json(self):
        with tempfile.TemporaryDirectory() as td:
            stats_dir = Path(td) / "api_stats"
            stats_dir.mkdir(parents=True, exist_ok=True)
            (stats_dir / "api_stats.200.json").write_text(
                json.dumps({"apis": [{"name": "Only", "seen": 1, "executed": 0, "skipped": 0}]})
            )
            (stats_dir / "ignore_me.json").write_text(json.dumps({"apis": []}))

            rc = feedback_main(["--input-dir", str(stats_dir)])
            self.assertEqual(rc, 0)

            output_path = stats_dir / "api_stats.json"
            learned_edges_path = stats_dir / "learned_edges.json"
            prefix_weights_path = stats_dir / "prefix_weights.json"
            self.assertTrue(output_path.exists())
            self.assertTrue(learned_edges_path.exists())
            self.assertTrue(prefix_weights_path.exists())
            merged = json.loads(output_path.read_text())
            learned = json.loads(learned_edges_path.read_text())
            weights = json.loads(prefix_weights_path.read_text())
            self.assertIn("api_novelty", merged)
            self.assertIn("Only", merged["api_novelty"])
            self.assertEqual(merged["meta"]["input_files"], 1)
            self.assertIn("edges", learned)
            self.assertIn("weights", weights)


if __name__ == "__main__":
    unittest.main()
