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
    def _write_scalar_slot_fixture(self, tmp: Path) -> tuple[Path, Path]:
        conditions = tmp / "conditions.json"
        apis = tmp / "apis_clang.jsonl"
        conditions.write_text(
            json.dumps(
                [
                    {
                        "function_name": "MakeVal",
                        "return": {
                            "type_string": "i32",
                            "access_type_set": [{"access": "create", "type_string": "i32"}],
                        },
                    },
                    {
                        "function_name": "ConsumeVal",
                        "param_0": {
                            "type_string": "i32",
                            "set_by": ["MakeVal:return"],
                            "access_type_set": [{"access": "read", "type_string": "i32"}],
                        },
                    },
                ]
            ),
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
        return conditions, apis

    def _write_scalar_edge_fixture(self, tmp: Path) -> tuple[Path, Path, Path]:
        conditions = tmp / "conditions.json"
        apis = tmp / "apis_clang.jsonl"
        graph = tmp / "constraint_graph.json"
        conditions.write_text(
            json.dumps(
                [
                    {
                        "function_name": "MakeVal",
                        "return": {"type_string": "i32"},
                    },
                    {
                        "function_name": "ConsumeVal",
                        "param_0": {
                            "type_string": "i32",
                            "access_type_set": [{"access": "read", "type_string": "i32"}],
                        },
                    },
                ]
            ),
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
        graph.write_text(
            json.dumps(
                {
                    "inter_edges": [
                        {
                            "src": "MakeVal",
                            "dst": "ConsumeVal",
                            "relation": "producer_consumer",
                            "object_type": "scalar:int32",
                            "hardness": "hard",
                            "confidence": 0.95,
                        }
                    ],
                    "intra_constraints": {},
                }
            ),
            encoding="utf-8",
        )
        return conditions, apis, graph

    def _write_scalar_edge_invalidation_fixture(self, tmp: Path) -> tuple[Path, Path, Path]:
        conditions = tmp / "conditions.json"
        apis = tmp / "apis_clang.jsonl"
        graph = tmp / "constraint_graph.json"
        conditions.write_text(
            json.dumps(
                [
                    {
                        "function_name": "OpenFd",
                        "return": {
                            "type_string": "i32",
                            "access_type_set": [{"access": "create", "type_string": "i32"}],
                        },
                    },
                    {
                        "function_name": "CloseFd",
                        "param_0": {
                            "type_string": "i32",
                            "set_by": ["OpenFd:return"],
                            "access_type_set": [{"access": "delete", "type_string": "i32"}],
                        },
                    },
                ]
            ),
            encoding="utf-8",
        )
        apis.write_text(
            "\n".join(
                [
                    '{"function_name":"OpenFd","return_info":{"type_clang":"int"},"arguments_info":[]}',
                    '{"function_name":"CloseFd","return_info":{"type_clang":"int"},"arguments_info":[{"type_clang":"int"}]}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        graph.write_text(
            json.dumps(
                {
                    "inter_edges": [
                        {
                            "src": "OpenFd",
                            "dst": "CloseFd",
                            "relation": "producer_consumer",
                            "object_type": "scalar:int32",
                            "hardness": "hard",
                            "confidence": 0.95,
                        },
                        {
                            "src": "CloseFd",
                            "dst": "OpenFd",
                            "relation": "invalidates_before_use",
                            "object_type": "scalar:int32",
                            "hardness": "hard",
                            "confidence": 0.9,
                        },
                    ],
                    "intra_constraints": {},
                }
            ),
            encoding="utf-8",
        )
        return conditions, apis, graph

    def _write_multi_handle_fixture(self, tmp: Path, *, symmetric: bool) -> tuple[Path, Path]:
        conditions = tmp / "conditions.json"
        apis = tmp / "apis_clang.jsonl"
        pair_param_0 = {
            "type_string": "%struct.node*",
            "set_by": ["param_1"],
            "access_type_set": [{"access": "read", "type_string": "%struct.node*"}],
        }
        pair_param_1 = {
            "type_string": "%struct.node*",
            "set_by": ["param_0"] if symmetric else [],
            "access_type_set": [{"access": "read", "type_string": "%struct.node*"}],
        }
        conditions.write_text(
            json.dumps(
                [
                    {
                        "function_name": "MakeNode",
                        "return": {
                            "type_string": "%struct.node*",
                            "access_type_set": [{"access": "create", "type_string": "%struct.node*"}],
                        },
                    },
                    {
                        "function_name": "PairOp",
                        "param_0": pair_param_0,
                        "param_1": pair_param_1,
                    },
                ]
            ),
            encoding="utf-8",
        )
        apis.write_text(
            "\n".join(
                [
                    '{"function_name":"MakeNode","return_info":{"type_clang":"struct node *"},"arguments_info":[]}',
                    '{"function_name":"PairOp","return_info":{"type_clang":"void"},"arguments_info":[{"type_clang":"struct node *"},{"type_clang":"struct node *"}]}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return conditions, apis

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
        self.assertRegex(text, r"handle_register_typed\(\d+,\s*\(void\*\)ret\)")

        # Legacy flat table should not be present.
        self.assertNotIn("static void *g_handles[MAX_HANDLES];", text)
        self.assertNotIn("static uint32_t g_handle_count = 0;", text)

    def test_v2_emits_scalar_slot_pool_and_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            out = tmp / "harness.c"
            conditions, apis = self._write_scalar_slot_fixture(tmp)

            proto.write_text('syntax = "proto2";\nmessage FuzzInput {}\n', encoding="utf-8")
            driver.write_text(json.dumps({"headers": []}), encoding="utf-8")

            gen = WrapperGenerator(
                proto,
                driver,
                conditions,
                apis_path=apis,
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

        self.assertIn("#define MAX_SCALAR_TYPES", text)
        self.assertIn("static int64_t g_scalars[MAX_SCALAR_TYPES][MAX_SCALAR_SLOTS];", text)
        self.assertIn("static uint32_t scalar_register_typed(uint32_t type_id, int64_t value, uint32_t producer_api_idx)", text)
        self.assertIn("static bool scalar_get_typed(", text)
        self.assertIn("params->has_param_0_slot ? params->param_0_slot : 0", text)
        self.assertIn("if (scalar_get_typed(", text)
        self.assertRegex(text, r"scalar_register_typed\(\d+,\s*\(int64_t\)ret,\s*\(uint32_t\)api_idx\)")

    def test_v2_uses_scalar_pool_from_constraint_edge_without_slot_field(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            out = tmp / "harness.c"
            conditions, apis, graph = self._write_scalar_edge_fixture(tmp)

            proto.write_text('syntax = "proto2";\nmessage FuzzInput {}\n', encoding="utf-8")
            driver.write_text(json.dumps({"headers": []}), encoding="utf-8")

            gen = WrapperGenerator(
                proto,
                driver,
                conditions,
                apis_path=apis,
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

        self.assertIn("if (scalar_get_typed(", text)
        self.assertIn("kAllowedScalarProducers_consume_val_0[] = { 1 }", text)
        self.assertRegex(
            text,
            r"scalar_get_typed\(\s*0,\s*requested_slot,\s*allow_stale,\s*kAllowedScalarProducers_consume_val_0",
        )
        self.assertIn("params->has_param_0_slot ? params->param_0_slot : 0", text)
        self.assertIn("PROTO_LIBERATOR_STRICT_SCALAR_DEPS", text)
        self.assertIn("strict_scalar_deps && true && !allow_stale", text)

    def test_v2_emits_scalar_invalidation_for_scalar_deleter(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            out = tmp / "harness.c"
            conditions, apis, graph = self._write_scalar_edge_invalidation_fixture(tmp)

            proto.write_text('syntax = "proto2";\nmessage FuzzInput {}\n', encoding="utf-8")
            driver.write_text(json.dumps({"headers": []}), encoding="utf-8")

            gen = WrapperGenerator(
                proto,
                driver,
                conditions,
                apis_path=apis,
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

        self.assertIn("scalar_invalidate_typed(", text)
        self.assertRegex(text, r"scalar_invalidate_typed\(\d+,\s*sel_scalar_0\)")

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
        self.assertIn("static void plb_cache_record_payload(", text)
        self.assertIn("static bool plb_try_apply_cached_params(", text)
        self.assertIn("static bool plb_reuse_cached_producer_args(", text)
        self.assertIn("PROTO_LIBERATOR_EFFECTIVE_ARG_REUSE", text)
        self.assertIn("PROTO_LIBERATOR_EFFECTIVE_ARG_REUSE_PCT", text)
        self.assertIn("effective_arg_cache", text)
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

    def test_lpm_records_effective_args_for_successful_producers(self):
        conditions = FIXTURES / "cjsonish_conditions.json"

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            out = tmp / "harness.cc"

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
                mutation_mode="lpm",
                max_actions=64,
                extra_headers=[],
                apipass_dir=None,
                harness_style="strict",
            )
            gen.generate(out)
            text = out.read_text(encoding="utf-8")

        self.assertIn("if (plb_handle_is_valid(ret))", text)
        self.assertIn("plb_cache_record_params(", text)
        self.assertIn("demo_fuzzer::Action::kCJsonParse", text)

    def test_v2_emits_post_call_guard_for_producer_like_return(self):
        conditions = FIXTURES / "cjsonish_conditions.json"

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
                            "cJSON_Parse": {
                                "return": {
                                    "llvm_type": "%struct.cJSON*",
                                    "object_type": "cJSON",
                                    "accesses": ["create"],
                                },
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

        self.assertIn("Constraint-graph post-call guards", text)
        self.assertIn("if (!allow_stale && ret == NULL)", text)
        self.assertIn("g_hard_constraint_redirected = true;", text)

    def test_lpm_emits_post_call_guard_for_producer_like_return(self):
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
                        "intra_constraints": {
                            "cJSON_Parse": {
                                "return": {
                                    "llvm_type": "%struct.cJSON*",
                                    "object_type": "cJSON",
                                    "accesses": ["create"],
                                },
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

        self.assertIn("Constraint-graph post-call guards", text)
        self.assertIn("if (!allow_stale && ret == NULL)", text)
        self.assertIn("g_hard_constraint_redirected = true;", text)

    def test_lpm_emits_scalar_slot_pool_and_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            out = tmp / "harness.cc"
            conditions, apis = self._write_scalar_slot_fixture(tmp)

            proto.write_text('syntax = "proto2";\nmessage FuzzInput {}\n', encoding="utf-8")
            driver.write_text(json.dumps({"headers": []}), encoding="utf-8")

            gen = WrapperGenerator(
                proto,
                driver,
                conditions,
                apis_path=apis,
                minimum_apis=None,
                package_name="demo_fuzzer",
                schema_mode="v2",
                mutation_mode="lpm",
                max_actions=64,
                extra_headers=[],
                apipass_dir=None,
                harness_style="strict",
            )
            gen.generate(out)
            text = out.read_text(encoding="utf-8")

        self.assertIn("enum ScalarTypeId", text)
        self.assertIn("static ScalarTable g_scalar_tables[ST__COUNT];", text)
        self.assertIn("static uint32_t scalar_register_typed(uint32_t type_id, int64_t value, uint32_t producer_api_idx)", text)
        self.assertIn("static bool scalar_get_typed(", text)
        self.assertIn("params.has_param_0_slot() ? params.param_0_slot() : 0", text)
        self.assertIn("scalars_reset();", text)
        self.assertRegex(text, r"scalar_register_typed\(\d+,\s*\(int64_t\)ret,\s*\(uint32_t\)api_idx\)")

    def test_lpm_flags_symmetric_same_type_set_by_as_unsafe_multi_handle(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            out = tmp / "harness.cc"
            conditions, apis = self._write_multi_handle_fixture(tmp, symmetric=True)

            proto.write_text('syntax = "proto2";\nmessage FuzzInput {}\n', encoding="utf-8")
            driver.write_text(json.dumps({"headers": []}), encoding="utf-8")

            gen = WrapperGenerator(
                proto,
                driver,
                conditions,
                apis_path=apis,
                minimum_apis=None,
                package_name="demo_fuzzer",
                schema_mode="v2",
                mutation_mode="lpm",
                max_actions=64,
                extra_headers=[],
                apipass_dir=None,
                harness_style="strict",
            )
            gen.generate(out)
            text = out.read_text(encoding="utf-8")

        self.assertIn("Multi-handle API without explicit handle-handle intra constraints.", text)
        self.assertIn("if (strict_multi_handle)", text)

    def test_lpm_allows_directional_same_type_set_by(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            out = tmp / "harness.cc"
            conditions, apis = self._write_multi_handle_fixture(tmp, symmetric=False)

            proto.write_text('syntax = "proto2";\nmessage FuzzInput {}\n', encoding="utf-8")
            driver.write_text(json.dumps({"headers": []}), encoding="utf-8")

            gen = WrapperGenerator(
                proto,
                driver,
                conditions,
                apis_path=apis,
                minimum_apis=None,
                package_name="demo_fuzzer",
                schema_mode="v2",
                mutation_mode="lpm",
                max_actions=64,
                extra_headers=[],
                apipass_dir=None,
                harness_style="strict",
            )
            gen.generate(out)
            text = out.read_text(encoding="utf-8")

        self.assertNotIn("Multi-handle API without explicit handle-handle intra constraints.", text)

    def test_v2_includes_phase3_stub_api_from_apis_clang(self):
        conditions = FIXTURES / "minimal_conditions.json"

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            proto = tmp / "demo.v2.proto"
            driver = tmp / "driver.meta.json"
            apis = tmp / "apis_clang.jsonl"
            out = tmp / "harness.c"

            proto.write_text('syntax = "proto2";\nmessage FuzzInput {}\n', encoding="utf-8")
            driver.write_text(json.dumps({"headers": []}), encoding="utf-8")
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

            gen = WrapperGenerator(
                proto,
                driver,
                conditions,
                apis_path=apis,
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

        self.assertIn("/* BarMissing */", text)
        self.assertIn("case demo_fuzzer_Action_bar_missing_tag:", text)
        self.assertIn("BarMissing(", text)


if __name__ == "__main__":
    unittest.main()
