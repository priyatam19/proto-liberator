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


if __name__ == "__main__":
    unittest.main()
