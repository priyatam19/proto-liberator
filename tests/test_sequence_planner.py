#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from sequence_planner import PlannerConfig, PlannerState, SequencePlanner  # noqa: E402


def _graph_fixture() -> dict:
    # Minimal lifecycle:
    #   create_obj produces Obj
    #   use_obj consumes Obj
    #   delete_obj deletes Obj
    return {
        "nodes": [
            {"id": "create_obj"},
            {"id": "use_obj"},
            {"id": "delete_obj"},
        ],
        "inter_edges": [
            {
                "src": "create_obj",
                "dst": "use_obj",
                "relation": "producer_consumer",
                "object_type": "Obj",
                "hardness": "hard",
                "confidence": 0.95,
            },
            {
                "src": "delete_obj",
                "dst": "use_obj",
                "relation": "invalidates_before_use",
                "object_type": "Obj",
                "hardness": "hard",
                "confidence": 0.9,
            },
        ],
        "object_catalog": [
            {
                "object_type": "Obj",
                "producers": ["create_obj"],
                "weak_producers": [],
                "consumers": ["use_obj", "delete_obj"],
                "deleters": ["delete_obj"],
            }
        ],
    }


def _mode_graph_fixture() -> dict:
    # consume needs hard type H and has soft preference for type S.
    return {
        "nodes": [
            {"id": "produce_h"},
            {"id": "produce_s"},
            {"id": "consume"},
            {"id": "delete_h"},
        ],
        "inter_edges": [
            {
                "src": "produce_h",
                "dst": "consume",
                "relation": "producer_consumer",
                "object_type": "H",
                "hardness": "hard",
                "confidence": 0.95,
            },
            {
                "src": "produce_s",
                "dst": "consume",
                "relation": "producer_consumer",
                "object_type": "S",
                "hardness": "soft",
                "confidence": 0.6,
            },
            {
                "src": "delete_h",
                "dst": "consume",
                "relation": "invalidates_before_use",
                "object_type": "H",
                "hardness": "hard",
                "confidence": 0.9,
            },
        ],
        "object_catalog": [
            {
                "object_type": "H",
                "producers": ["produce_h"],
                "weak_producers": [],
                "consumers": ["consume", "delete_h"],
                "deleters": ["delete_h"],
            },
            {
                "object_type": "S",
                "producers": [],
                "weak_producers": ["produce_s"],
                "consumers": ["consume"],
                "deleters": [],
            },
        ],
    }


class TestSequencePlanner(unittest.TestCase):
    def _planner(self) -> SequencePlanner:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(_graph_fixture(), tmp)
            path = Path(tmp.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return SequencePlanner(graph_path=path, rng_seed=0, config=PlannerConfig(mode="strict"))

    def test_strict_blocks_consumer_without_live_handle(self):
        planner = self._planner()
        state = PlannerState()
        self.assertFalse(planner._hard_filter(state, "use_obj"))
        self.assertTrue(planner._hard_filter(state, "create_obj"))

    def test_delete_then_use_requires_recreate(self):
        planner = self._planner()
        state = PlannerState()
        planner.apply_api(state, "create_obj")
        self.assertTrue(planner._hard_filter(state, "use_obj"))
        planner.apply_api(state, "delete_obj")
        self.assertFalse(planner._hard_filter(state, "use_obj"))
        planner.apply_api(state, "create_obj")
        self.assertTrue(planner._hard_filter(state, "use_obj"))

    def test_novelty_provider_biases_selection(self):
        graph = {
            "nodes": [{"id": "A"}, {"id": "B"}],
            "inter_edges": [],
            "object_catalog": [],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(graph, tmp)
            path = Path(tmp.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        planner = SequencePlanner(
            graph_path=path,
            rng_seed=0,
            config=PlannerConfig(mode="strict"),
            novelty_provider=lambda api: 10.0 if api == "B" else 0.0,
        )
        state = PlannerState()
        picked = planner.select_next(state)
        self.assertEqual(picked, "B")

    def test_explore_mode_does_not_hard_block(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(_graph_fixture(), tmp)
            path = Path(tmp.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        planner = SequencePlanner(graph_path=path, rng_seed=0, config=PlannerConfig(mode="explore"))
        state = PlannerState()
        cands = planner._candidate_apis(state)
        self.assertIn("use_obj", cands)

    def test_balanced_mode_penalizes_missing_soft_dependency(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(_mode_graph_fixture(), tmp)
            path = Path(tmp.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        strict = SequencePlanner(graph_path=path, rng_seed=0, config=PlannerConfig(mode="strict"))
        balanced = SequencePlanner(graph_path=path, rng_seed=0, config=PlannerConfig(mode="balanced"))

        state = PlannerState()
        strict.apply_api(state, "produce_h")
        score_strict = strict._score(state, "consume")
        score_balanced = balanced._score(state, "consume")

        self.assertLess(score_balanced, score_strict)

    def test_invalidates_edge_penalizes_score(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(_mode_graph_fixture(), tmp)
            path = Path(tmp.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        planner = SequencePlanner(graph_path=path, rng_seed=0, config=PlannerConfig(mode="strict"))
        state = PlannerState()
        planner.apply_api(state, "produce_h")
        before_delete = planner._score(state, "consume")
        planner.apply_api(state, "delete_h")
        after_delete = planner._score(state, "consume")
        self.assertLess(after_delete, before_delete)

    def test_merges_learned_soft_edges_on_plan(self):
        graph = {
            "nodes": [{"id": "A"}, {"id": "B"}],
            "inter_edges": [],
            "object_catalog": [],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as gtmp:
            json.dump(graph, gtmp)
            graph_path = Path(gtmp.name)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as ltmp:
            json.dump(
                {
                    "edges": [
                        {
                            "src": "A",
                            "dst": "B",
                            "relation": "producer_consumer",
                            "hardness": "soft",
                            "confidence": 0.9,
                        }
                    ]
                },
                ltmp,
            )
            learned_path = Path(ltmp.name)
        self.addCleanup(lambda: graph_path.unlink(missing_ok=True))
        self.addCleanup(lambda: learned_path.unlink(missing_ok=True))

        planner = SequencePlanner(
            graph_path=graph_path,
            rng_seed=0,
            config=PlannerConfig(mode="strict"),
            novelty_provider=lambda _api: 0.0,
            learned_edges_path=learned_path,
        )
        seq = planner.plan_sequence(max_len=2, prefix=["A"])
        self.assertEqual(seq[:2], ["A", "B"])

    def test_applies_prefix_weights_on_plan(self):
        graph = {
            "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
            "inter_edges": [],
            "object_catalog": [],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as gtmp:
            json.dump(graph, gtmp)
            graph_path = Path(gtmp.name)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as ptmp:
            json.dump({"weights": {"A,B": 2.0, "A,C": 0.1}}, ptmp)
            prefix_path = Path(ptmp.name)
        self.addCleanup(lambda: graph_path.unlink(missing_ok=True))
        self.addCleanup(lambda: prefix_path.unlink(missing_ok=True))

        planner = SequencePlanner(
            graph_path=graph_path,
            rng_seed=0,
            config=PlannerConfig(mode="strict"),
            novelty_provider=lambda _api: 0.0,
            prefix_weights_path=prefix_path,
        )
        seq = planner.plan_sequence(max_len=2, prefix=["A"])
        self.assertEqual(seq[:2], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
