#!/usr/bin/env python3
import sys
import tempfile
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

    def test_field_numbering_includes_scalar_slot_for_set_by_scalar(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            conditions = tmp / "conditions.json"
            conditions.write_text(
                """[
  {
    "function_name": "ConsumeVal",
    "param_0": {
      "type_string": "i32",
      "set_by": ["MakeVal:return"],
      "access_type_set": [{"access": "read", "type_string": "i32"}]
    }
  }
]
""",
                encoding="utf-8",
            )
            gen = SeedGenerator(conditions_path=conditions, rng_seed=0)
            entry = gen.func_entries["ConsumeVal"]
            fields = gen._field_numbers_for_entry(entry)

        self.assertEqual(fields.get("param_0"), 1)
        self.assertEqual(fields.get("param_0_slot"), 2)
        self.assertEqual(fields.get("skip_dependency_check"), 3)

    def test_action_encodes_scalar_slot_override(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            conditions = tmp / "conditions.json"
            conditions.write_text(
                """[
  {
    "function_name": "ConsumeVal",
    "param_0": {
      "type_string": "i32",
      "set_by": ["MakeVal:return"],
      "access_type_set": [{"access": "read", "type_string": "i32"}]
    }
  }
]
""",
                encoding="utf-8",
            )
            gen = SeedGenerator(conditions_path=conditions, rng_seed=0)
            variant = gen.action_for_function("ConsumeVal", scalar_slot_overrides={0: 1})

        # param_0_slot is field #2 => varint key 0x10, value 0x01
        self.assertIn(bytes([0x10, 0x01]), variant.params_bytes)

    def test_scalar_slot_metadata_infers_producer_consumer_key(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            conditions = tmp / "conditions.json"
            conditions.write_text(
                """[
  {
    "function_name": "MakeVal",
    "return": {
      "type_string": "i32",
      "access_type_set": [{"access": "create", "type_string": "i32"}]
    }
  },
  {
    "function_name": "ConsumeVal",
    "param_0": {
      "type_string": "i32",
      "set_by": ["MakeVal:return"],
      "access_type_set": [{"access": "read", "type_string": "i32"}]
    }
  }
]
""",
                encoding="utf-8",
            )
            gen = SeedGenerator(conditions_path=conditions, rng_seed=0)

        self.assertEqual(gen.scalar_return_key_by_function.get("MakeVal"), "scalar:int32")
        self.assertEqual(gen.scalar_slot_params_by_function.get("ConsumeVal"), [(0, "scalar:int32")])


if __name__ == "__main__":
    unittest.main()
