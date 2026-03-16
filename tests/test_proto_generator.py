#!/usr/bin/env python3
import sys
import tempfile
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
        apis = FIXTURES / "cjsonish_apis_clang.jsonl"
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

    def test_phase3_stubs_include_clang_only_api(self):
        conditions = FIXTURES / "minimal_conditions.json"
        with tempfile.TemporaryDirectory() as td:
            apis = Path(td) / "apis_clang.jsonl"
            apis.write_text(
                "\n".join(
                    [
                        '{"function_name":"Foo","return_info":{"type_clang":"int"},"arguments_info":[{"type_clang":"struct bar *"},{"type_clang":"char *"}]}',
                        '{"function_name":"BarMissing","return_info":{"type_clang":"void"},"arguments_info":[{"type_clang":"int *"},{"type_clang":"char *"}]}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            gen = ProtoGenerator(
                conditions_path=conditions,
                apis_path=apis,
                schema_mode="v2",
                max_actions=64,
                max_calls_per_api=4,
                max_bytes_size=65536,
            )
            schema = gen.generate_schema("demo")
            text = schema.serialize()
            self.assertIn("message BarMissing_Params", text)
            self.assertIn("Phase 3 stub (clang-only API): generic bytes params.", text)
            self.assertIn("optional bytes param_0", text)
            self.assertIn("optional bytes param_1", text)
            self.assertIn("BarMissing_Params bar_missing", text)

    def test_emits_scalar_slot_for_set_by_scalar_param(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            conditions = tmp / "conditions.json"
            apis = tmp / "apis_clang.jsonl"
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
            apis.write_text(
                "\n".join(
                    [
                        '{"function_name":"MakeVal","return_info":{"type_clang":"int"},"arguments_info":[]}',
                        '{"function_name":"ConsumeVal","return_info":{"type_clang":"void"},"arguments_info":[{"type_clang":"int"}]}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            gen = ProtoGenerator(
                conditions_path=conditions,
                apis_path=apis,
                schema_mode="v2",
                max_actions=32,
            )
            schema = gen.generate_schema("demo")
            text = schema.serialize()

        self.assertIn("message ConsumeVal_Params", text)
        self.assertIn("optional int32 param_0 = 1;", text)
        self.assertIn("optional uint32 param_0_slot = 2;", text)


if __name__ == "__main__":
    unittest.main()
