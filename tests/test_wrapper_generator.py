#!/usr/bin/env python3
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

sys.path.insert(0, str(SRC_DIR))

from wrapper_generator import WrapperGenerator  # noqa: E402


class TestWrapperGenerator(unittest.TestCase):
    def test_v2_emits_typed_handle_table_and_calls(self):
        conditions = FIXTURES / "cjsonish_conditions.json"

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            out = tmp / "harness.c"

            # wrapper_generator only uses proto path stem for header naming.
            proto.write_text('syntax = "proto2";\nmessage FuzzInput {}\n', encoding="utf-8")
            driver.write_text(json.dumps({"headers": []}), encoding="utf-8")

            gen = WrapperGenerator(
                proto,
                driver,
                conditions,
                apis_path=None,
                minimum_apis=None,
                package_name="demo_fuzzer",
                schema_mode="v2",
                mutation_mode="nanopb",
                max_actions=64,
                extra_headers=[],
                apipass_dir=None,
                harness_style="strict",
            )
            gen.generate(out)

            text = out.read_text(encoding="utf-8")

        # Typed table declarations are emitted.
        self.assertIn("#define MAX_HANDLE_TYPES", text)
        self.assertIn("static void *g_handles[MAX_HANDLE_TYPES][MAX_HANDLES];", text)
        self.assertIn("static uint32_t g_handle_count[MAX_HANDLE_TYPES];", text)

        # Typed helper functions are emitted.
        self.assertIn("static uint32_t handle_register_typed(uint32_t type_id, void *ptr)", text)
        self.assertIn("static void *handle_get_typed(uint32_t type_id, uint32_t requested", text)
        self.assertIn("static void handle_invalidate_typed(uint32_t type_id, uint32_t selected)", text)

        # API call-sites use typed helpers with rendered numeric type_id.
        self.assertRegex(text, r"handle_get_typed\(\d+,\s*hid,\s*allow_stale,\s*&selected\)")
        self.assertRegex(text, r"handle_register_typed\(\d+,\s*\(void\*\)result\)")

        # Legacy flat table should not be present.
        self.assertNotIn("static void *g_handles[MAX_HANDLES];", text)
        self.assertNotIn("static uint32_t g_handle_count = 0;", text)

    def test_v2_emits_set_by_guard_from_constraint_graph(self):
        conditions = FIXTURES / "minimal_conditions.json"

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            out = tmp / "harness.c"
            graph = tmp / "constraint_graph.json"

            proto.write_text('syntax = "proto2";\nmessage FuzzInput {}\n', encoding="utf-8")
            driver.write_text(json.dumps({"headers": []}), encoding="utf-8")
            graph.write_text(
                json.dumps(
                    {
                        "intra_constraints": {
                            "Foo": {
                                "params": {
                                    "param_1": {
                                        "set_by": ["param_0"],
                                        "len_depends_on": "",
                                    }
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            gen = WrapperGenerator(
                proto,
                driver,
                conditions,
                apis_path=None,
                minimum_apis=None,
                package_name="demo_fuzzer",
                schema_mode="v2",
                mutation_mode="nanopb",
                max_actions=64,
                extra_headers=[],
                apipass_dir=None,
                constraint_graph_path=graph,
                harness_style="strict",
            )
            gen.generate(out)
            text = out.read_text(encoding="utf-8")

        self.assertIn("Constraint-graph pre-call guards", text)
        self.assertIn("if (!allow_stale && arg0 == NULL)", text)
        self.assertIn("void *_repair = handle_get_typed(", text)
        self.assertIn("arg0 = (", text)
        self.assertIn("g_hard_constraint_redirected = true;", text)

    def test_v2_emits_redirect_flag_wiring(self):
        conditions = FIXTURES / "cjsonish_conditions.json"

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            out = tmp / "harness.c"

            proto.write_text('syntax = "proto2";\nmessage FuzzInput {}\n', encoding="utf-8")
            driver.write_text(json.dumps({"headers": []}), encoding="utf-8")

            gen = WrapperGenerator(
                proto,
                driver,
                conditions,
                apis_path=None,
                minimum_apis=None,
                package_name="demo_fuzzer",
                schema_mode="v2",
                mutation_mode="nanopb",
                max_actions=64,
                extra_headers=[],
                apipass_dir=None,
                harness_style="strict",
            )
            gen.generate(out)
            text = out.read_text(encoding="utf-8")

        self.assertIn("static bool g_hard_constraint_redirected = false;", text)
        self.assertIn("g_hard_constraint_redirected = false;", text)
        self.assertIn('fprintf(stderr, "PLB_CONSTRAINT_REDIRECTED=1\\n");', text)

    def test_lpm_emits_repair_guards_and_redirect_wiring(self):
        conditions = FIXTURES / "minimal_conditions.json"

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            out = tmp / "harness.cc"
            graph = tmp / "constraint_graph.json"

            proto.write_text('syntax = "proto2";\nmessage FuzzInput {}\n', encoding="utf-8")
            driver.write_text(json.dumps({"headers": []}), encoding="utf-8")
            graph.write_text(
                json.dumps(
                    {
                        "intra_constraints": {
                            "Foo": {
                                "params": {
                                    "param_1": {
                                        "set_by": ["param_0"],
                                        "len_depends_on": "",
                                    }
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            gen = WrapperGenerator(
                proto,
                driver,
                conditions,
                apis_path=None,
                minimum_apis=None,
                package_name="demo_fuzzer",
                schema_mode="v2",
                mutation_mode="lpm",
                max_actions=64,
                extra_headers=[],
                apipass_dir=None,
                constraint_graph_path=graph,
                harness_style="strict",
            )
            gen.generate(out)
            text = out.read_text(encoding="utf-8")

        self.assertIn("handle_get_typed(", text)
        self.assertIn("g_hard_constraint_redirected = false;", text)
        self.assertIn("g_hard_constraint_redirected = true;", text)
        self.assertIn('std::fprintf(stderr, "PLB_CONSTRAINT_REDIRECTED=1\\n");', text)
        self.assertIn("extern \"C\" size_t LLVMFuzzerCustomMutator(", text)
        self.assertIn("protobuf_mutator::libfuzzer::CustomProtoMutator(", text)
        self.assertIn("static int plb_produced_type(int case_id)", text)
        self.assertIn("static std::vector<int> plb_required_types(int case_id)", text)
        self.assertIn("static bool plb_make_producer(", text)
        self.assertIn("static int plb_repair_sequence(", text)
        self.assertIn("static bool plb_enforce_hard_validity(", text)
        self.assertIn("PROTO_LIBERATOR_ENFORCE_HARD_VALIDITY", text)
        self.assertIn("PROTO_LIBERATOR_ENFORCE_HARD_MAX_INSERTS", text)
        self.assertIn("PROTO_LIBERATOR_MUTATOR_MISUSE_MODE", text)

    def test_lpm_graph_extend_uses_only_producer_consumer_edges(self):
        conditions = FIXTURES / "cjsonish_conditions.json"

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            out = tmp / "harness.cc"
            graph = tmp / "constraint_graph.json"

            proto.write_text('syntax = "proto2";\nmessage FuzzInput {}\n', encoding="utf-8")
            driver.write_text(json.dumps({"headers": []}), encoding="utf-8")
            graph.write_text(
                json.dumps(
                    {
                        "inter_edges": [
                            {
                                "src": "cJSON_Parse",
                                "dst": "cJSON_PrintUnformatted",
                                "relation": "producer_consumer",
                                "object_type": "cJSON",
                                "confidence": 0.95,
                            },
                            {
                                "src": "cJSON_Delete",
                                "dst": "cJSON_PrintUnformatted",
                                "relation": "invalidates_before_use",
                                "object_type": "cJSON",
                                "confidence": 0.99,
                            },
                        ],
                        "intra_constraints": {},
                    }
                ),
                encoding="utf-8",
            )

            gen = WrapperGenerator(
                proto,
                driver,
                conditions,
                apis_path=None,
                minimum_apis=None,
                package_name="demo_fuzzer",
                schema_mode="v2",
                mutation_mode="lpm",
                max_actions=64,
                extra_headers=[],
                apipass_dir=None,
                constraint_graph_path=graph,
                harness_style="strict",
            )
            gen.generate(out)
            text = out.read_text(encoding="utf-8")

        start = text.index("static const PlbEdge kGraphEdges[] = {")
        end = text.index("static const int kGraphEdgesCount", start)
        edges_block = text[start:end]
        self.assertIn("kCJsonParse", edges_block)
        self.assertIn("kCJsonPrintUnformatted", edges_block)
        self.assertNotIn("kCJsonDelete", edges_block)


if __name__ == "__main__":
    unittest.main()
