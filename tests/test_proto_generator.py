#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

sys.path.insert(0, str(SRC_DIR))

from proto_generator import ProtoGenerator  # noqa: E402


class TestProtoGenerator(unittest.TestCase):
    def test_minimal_golden(self):
        conditions = FIXTURES / "minimal_conditions.json"
        apis = FIXTURES / "minimal_apis_clang.jsonl"
        expected = (FIXTURES / "expected_minimal.proto").read_text()

        gen = ProtoGenerator(
            conditions_path=conditions,
            apis_path=apis,
            schema_mode="v1",
            max_calls_per_api=4,
            max_bytes_size=65536,
        )
        schema = gen.generate_schema("demo")
        actual = schema.serialize()

        self.assertEqual(actual.strip() + "\n", expected.strip() + "\n")

    def test_minimal_golden_v2(self):
        conditions = FIXTURES / "minimal_conditions.json"
        apis = FIXTURES / "minimal_apis_clang.jsonl"
        expected = (FIXTURES / "expected_minimal_v2.proto").read_text()

        gen = ProtoGenerator(
            conditions_path=conditions,
            apis_path=apis,
            schema_mode="v2",
            max_actions=64,
            max_calls_per_api=4,
            max_bytes_size=65536,
        )
        schema = gen.generate_schema("demo")
        actual = schema.serialize()

        self.assertEqual(actual.strip() + "\n", expected.strip() + "\n")

    def test_cjsonish_golden_v2(self):
        conditions = FIXTURES / "cjsonish_conditions.json"
        apis = FIXTURES / "minimal_apis_clang.jsonl"
        expected = (FIXTURES / "expected_cjsonish_v2.proto").read_text()

        gen = ProtoGenerator(
            conditions_path=conditions,
            apis_path=apis,
            schema_mode="v2",
            max_actions=64,
            max_calls_per_api=4,
            max_bytes_size=65536,
        )
        schema = gen.generate_schema("cjson")
        actual = schema.serialize()

        self.assertEqual(actual.strip() + "\n", expected.strip() + "\n")


if __name__ == "__main__":
    unittest.main()
