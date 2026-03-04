#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

sys.path.insert(0, str(SRC_DIR))

from seed_generator import SeedGenerator, build_novelty_scores  # noqa: E402


class TestSeedGenerator(unittest.TestCase):
    def test_wire_seed_minimal_one_action(self):
        conditions = FIXTURES / "minimal_conditions.json"
        gen = SeedGenerator(conditions_path=conditions, rng_seed=0)

        # minimal fixture has only "Foo"
        variant = gen.action_for_function("Foo")
        data = gen.encode_fuzz_input([variant], global_seed=0)

        # Wire-level sanity:
        # - starts with global_seed field set to 0 (08 00)
        # - contains at least one actions field tag (0x12)
        self.assertTrue(data.startswith(bytes([0x08, 0x00])))
        self.assertIn(0x12, data)
        self.assertGreaterEqual(len(data), 6)

    def test_build_novelty_scores_from_api_stats(self):
        signal = {
            "apis": [
                {"name": "A", "seen": 10, "executed": 0, "skipped": 0},
                {"name": "B", "seen": 10, "executed": 9, "skipped": 1},
            ]
        }
        scores = build_novelty_scores(signal)
        self.assertIn("A", scores)
        self.assertIn("B", scores)
        self.assertGreater(scores["A"], scores["B"])


if __name__ == "__main__":
    unittest.main()
