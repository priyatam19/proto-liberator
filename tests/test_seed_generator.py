#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

sys.path.insert(0, str(SRC_DIR))

from seed_generator import SeedGenerator  # noqa: E402


class TestSeedGenerator(unittest.TestCase):
    def test_wire_seed_minimal_one_action(self):
        conditions = FIXTURES / "minimal_conditions.json"
        gen = SeedGenerator(conditions_path=conditions, rng_seed=0)

        # minimal fixture has only "Foo"
        variant = gen.action_for_function("Foo")
        data = gen.encode_fuzz_input([variant], global_seed=0)

        # Expected wire:
        # global_seed = 0 -> 08 00
        # actions (field 2) -> 12 <len>
        # Action.oneof Foo tag=1 -> 0A 00 (empty params)
        expected = bytes([0x08, 0x00, 0x12, 0x02, 0x0A, 0x00])
        self.assertEqual(data, expected)


if __name__ == "__main__":
    unittest.main()

