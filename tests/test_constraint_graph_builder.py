#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from constraint_graph_builder import _build_graph_for_apipass  # noqa: E402


class TestConstraintGraphBuilder(unittest.TestCase):
    def test_phase3_adds_clang_only_stub_and_synthetic_edge(self):
        with tempfile.TemporaryDirectory() as td:
            apipass = Path(td)
            conditions = [
                {
                    "function_name": "foo_consumer",
                    "param_0": {
                        "type_string": "%struct.x_t*",
                        "access_type_set": [
                            {"access": "read", "type_string": "%struct.x_t*"}
                        ],
                    },
                    "return": {"type_string": "void", "access_type_set": []},
                }
            ]
            (apipass / "conditions.json").write_text(json.dumps(conditions), encoding="utf-8")
            rows = [
                {
                    "function_name": "foo_consumer",
                    "return_info": {"type_clang": "void"},
                    "arguments_info": [{"type_clang": "x_t *"}],
                },
                {
                    "function_name": "foo_producer_stub",
                    "return_info": {"type_clang": "x_t *"},
                    "arguments_info": [],
                },
            ]
            (apipass / "apis_clang.json").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )

            res = _build_graph_for_apipass(apipass, library="demo")
            graph = json.loads(res.output_graph.read_text(encoding="utf-8"))

        node_ids = {n["id"] for n in graph["nodes"]}
        self.assertIn("foo_producer_stub", node_ids)
        self.assertEqual(graph["intra_constraints"]["foo_producer_stub"]["stub"], "phase3_clang_only")

        synth = [
            e
            for e in graph["inter_edges"]
            if e["src"] == "foo_producer_stub"
            and e["dst"] == "foo_consumer"
            and e["relation"] == "producer_consumer"
            and e["hardness"] == "soft"
            and abs(float(e["confidence"]) - 0.3) < 1e-9
        ]
        self.assertTrue(synth)

        self.assertGreaterEqual(int(graph["stats"].get("phase3_stub_nodes", 0)), 1)
        self.assertGreaterEqual(int(graph["stats"].get("phase3_synthetic_edges", 0)), 1)

    def test_emits_scalar_value_flow_edges_and_catalog(self):
        with tempfile.TemporaryDirectory() as td:
            apipass = Path(td)
            conditions = [
                {
                    "function_name": "open_fd",
                    "return": {
                        "type_string": "i32",
                        "access_type_set": [{"access": "create", "type_string": "i32"}],
                    },
                },
                {
                    "function_name": "read_fd",
                    "param_0": {
                        "type_string": "i32",
                        "access_type_set": [{"access": "read", "type_string": "i32"}],
                    },
                    "return": {"type_string": "i32"},
                },
                {
                    "function_name": "close_fd",
                    "param_0": {
                        "type_string": "i32",
                        "access_type_set": [{"access": "delete", "type_string": "i32"}],
                    },
                    "return": {"type_string": "i32"},
                },
            ]
            (apipass / "conditions.json").write_text(json.dumps(conditions), encoding="utf-8")
            (apipass / "apis_clang.json").write_text("", encoding="utf-8")

            res = _build_graph_for_apipass(apipass, library="demo")
            graph = json.loads(res.output_graph.read_text(encoding="utf-8"))

        scalar_edges = [
            e
            for e in graph["inter_edges"]
            if e["object_type"] == "scalar:int32"
            and e["relation"] == "producer_consumer"
            and e["src"] == "open_fd"
            and e["dst"] == "read_fd"
        ]
        self.assertTrue(scalar_edges)

        scalar_invalidates = [
            e
            for e in graph["inter_edges"]
            if e["object_type"] == "scalar:int32"
            and e["relation"] == "invalidates_before_use"
            and e["src"] == "close_fd"
            and e["dst"] == "read_fd"
        ]
        self.assertTrue(scalar_invalidates)

        scalar_catalog = [o for o in graph["object_catalog"] if o["object_type"] == "scalar:int32"]
        self.assertTrue(scalar_catalog)
        self.assertEqual(scalar_catalog[0].get("kind"), "scalar")
        self.assertIn("open_fd", scalar_catalog[0]["producers"])
        self.assertIn("read_fd", scalar_catalog[0]["consumers"])


if __name__ == "__main__":
    unittest.main()
