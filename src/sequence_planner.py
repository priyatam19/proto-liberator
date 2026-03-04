#!/usr/bin/env python3
"""
Constraint-graph-based API sequence planner.

This planner is intentionally independent from protobuf encoding details.
It only plans API name sequences from graph + runtime state.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set


@dataclass
class PlannerState:
    live_handles: Dict[str, List[int]] = field(default_factory=dict)
    invalidated: Set[int] = field(default_factory=set)
    seq: List[str] = field(default_factory=list)
    next_slot_id: int = 1


@dataclass(frozen=True)
class PlannerConfig:
    mode: str = "strict"  # strict|balanced|explore
    misuse_mode: bool = False


def _uniq(seq: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in seq:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


class SequencePlanner:
    def __init__(
        self,
        *,
        graph_path: Path,
        rng_seed: int = 0,
        config: Optional[PlannerConfig] = None,
        novelty_provider: Optional[Callable[[str], float]] = None,
    ):
        graph = json.loads(Path(graph_path).read_text())
        self.rng = random.Random(rng_seed)
        self.config = config or PlannerConfig()
        self.novelty_provider = novelty_provider or (lambda _api: 0.0)

        self.nodes: List[str] = [str(n.get("id")) for n in graph.get("nodes", []) if isinstance(n, dict) and n.get("id")]
        self.nodes = sorted(_uniq(self.nodes))

        self.required_types_hard: Dict[str, Set[str]] = {api: set() for api in self.nodes}
        self.invalidates_in_hard: Dict[str, Set[str]] = {api: set() for api in self.nodes}

        for e in graph.get("inter_edges", []):
            if not isinstance(e, dict):
                continue
            src = str(e.get("src") or "")
            dst = str(e.get("dst") or "")
            rel = str(e.get("relation") or "")
            hard = str(e.get("hardness") or "") == "hard"
            obj_t = str(e.get("object_type") or "")
            if not src or not dst or not obj_t:
                continue
            if dst not in self.required_types_hard:
                self.required_types_hard[dst] = set()
                self.invalidates_in_hard[dst] = set()
            if rel == "producer_consumer" and hard:
                self.required_types_hard[dst].add(obj_t)
            if rel == "invalidates_before_use" and hard:
                self.invalidates_in_hard[dst].add(obj_t)

        # Role map from object catalog.
        self.produced_types_by_api: Dict[str, Set[str]] = {api: set() for api in self.nodes}
        self.deleted_types_by_api: Dict[str, Set[str]] = {api: set() for api in self.nodes}
        self.consumed_types_by_api: Dict[str, Set[str]] = {api: set() for api in self.nodes}
        for obj in graph.get("object_catalog", []):
            if not isinstance(obj, dict):
                continue
            obj_t = str(obj.get("object_type") or "")
            if not obj_t:
                continue
            for fn in obj.get("producers", []):
                fns = str(fn)
                if fns in self.produced_types_by_api:
                    self.produced_types_by_api[fns].add(obj_t)
            for fn in obj.get("deleters", []):
                fns = str(fn)
                if fns in self.deleted_types_by_api:
                    self.deleted_types_by_api[fns].add(obj_t)
            for fn in obj.get("consumers", []):
                fns = str(fn)
                if fns in self.consumed_types_by_api:
                    self.consumed_types_by_api[fns].add(obj_t)

        # Incoming edge weights for scoring.
        self.incoming_conf: Dict[str, List[tuple[str, str, float]]] = {api: [] for api in self.nodes}
        for e in graph.get("inter_edges", []):
            if not isinstance(e, dict):
                continue
            src = str(e.get("src") or "")
            dst = str(e.get("dst") or "")
            obj_t = str(e.get("object_type") or "")
            try:
                conf = float(e.get("confidence", 0.0))
            except Exception:
                conf = 0.0
            if src and dst and dst in self.incoming_conf:
                self.incoming_conf[dst].append((src, obj_t, conf))

    def _has_live(self, state: PlannerState, obj_t: str) -> bool:
        return bool(state.live_handles.get(obj_t))

    def _hard_filter(self, state: PlannerState, api: str) -> bool:
        # Require live handles for all hard producer_consumer dependencies.
        for obj_t in self.required_types_hard.get(api, set()):
            if not self._has_live(state, obj_t):
                return False

        # If delete occurred, do not consume invalidated-only object in strict mode.
        if not self.config.misuse_mode:
            for obj_t in self.invalidates_in_hard.get(api, set()):
                if obj_t in self.consumed_types_by_api.get(api, set()) and not self._has_live(state, obj_t):
                    return False
        return True

    def _score(self, state: PlannerState, api: str) -> float:
        score = 0.0

        # Confidence-weighted score for relations connected to already-seen APIs.
        seen = set(state.seq)
        for src, _obj_t, conf in self.incoming_conf.get(api, []):
            if src in seen:
                score += conf

        # Coverage novelty signal (external).
        score += max(0.0, float(self.novelty_provider(api)))

        # Diversity penalty for immediate revisits.
        if state.seq and state.seq[-1] == api:
            score -= 2.0
        if len(state.seq) >= 2 and state.seq[-2] == api:
            score -= 1.0
        return score

    def _candidate_apis(self, state: PlannerState) -> List[str]:
        cands: List[str] = []
        for api in self.nodes:
            if self._hard_filter(state, api):
                cands.append(api)
        return cands

    def select_next(self, state: PlannerState) -> Optional[str]:
        cands = self._candidate_apis(state)
        if not cands:
            return None

        scored = [(self._score(state, api), api) for api in cands]
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        top_score = scored[0][0]
        top = [api for s, api in scored if abs(s - top_score) < 1e-9]
        return self.rng.choice(top)

    def apply_api(self, state: PlannerState, api: str) -> None:
        state.seq.append(api)

        # Produce new handles for produced object types.
        for obj_t in self.produced_types_by_api.get(api, set()):
            slot = state.next_slot_id
            state.next_slot_id += 1
            state.live_handles.setdefault(obj_t, []).append(slot)

        # Delete/invalidate one live handle per deleted object type.
        for obj_t in self.deleted_types_by_api.get(api, set()):
            pool = state.live_handles.get(obj_t, [])
            if pool:
                slot = pool.pop()
                state.invalidated.add(slot)
            state.live_handles[obj_t] = pool

    def plan_sequence(self, *, max_len: int, prefix: Optional[List[str]] = None) -> List[str]:
        state = PlannerState()
        prefix = prefix or []
        for fn in prefix:
            if fn in self.nodes:
                self.apply_api(state, fn)

        while len(state.seq) < max_len:
            nxt = self.select_next(state)
            if not nxt:
                break
            self.apply_api(state, nxt)
        return state.seq
