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
from typing import Callable, Dict, List, Optional, Set, Tuple


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
        learned_edges_path: Optional[Path] = None,
        prefix_weights_path: Optional[Path] = None,
    ):
        graph = json.loads(Path(graph_path).read_text())
        self.rng = random.Random(rng_seed)
        self.config = config or PlannerConfig()
        self.mode = self.config.mode if self.config.mode in {"strict", "balanced", "explore"} else "strict"
        self.novelty_provider = novelty_provider or (lambda _api: 0.0)
        self.learned_edges_path = learned_edges_path
        self.prefix_weights_path = prefix_weights_path
        self._learned_edges_mtime_ns: int = -1
        self._prefix_weights_mtime_ns: int = -1
        self.prefix_weights: Dict[str, float] = {}

        self.nodes: List[str] = [str(n.get("id")) for n in graph.get("nodes", []) if isinstance(n, dict) and n.get("id")]
        self.nodes = sorted(_uniq(self.nodes))

        self.required_types_hard: Dict[str, Set[str]] = {api: set() for api in self.nodes}
        self.required_types_soft: Dict[str, Set[str]] = {api: set() for api in self.nodes}
        self.required_types_soft_conf: Dict[str, Dict[str, float]] = {api: {} for api in self.nodes}
        self.invalidates_in_hard: Dict[str, Set[str]] = {api: set() for api in self.nodes}
        self.incoming_edges: Dict[str, List[Tuple[str, str, float, str, bool]]] = {api: [] for api in self.nodes}

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
                self.required_types_soft[dst] = set()
                self.required_types_soft_conf[dst] = {}
                self.invalidates_in_hard[dst] = set()
            if rel == "producer_consumer" and hard:
                self.required_types_hard[dst].add(obj_t)
            elif rel == "producer_consumer" and not hard:
                self.required_types_soft[dst].add(obj_t)
                prev = self.required_types_soft_conf[dst].get(obj_t, 0.0)
                self.required_types_soft_conf[dst][obj_t] = max(prev, float(e.get("confidence") or 0.0))
            if rel == "invalidates_before_use" and hard:
                self.invalidates_in_hard[dst].add(obj_t)
            try:
                conf = float(e.get("confidence", 0.0))
            except Exception:
                conf = 0.0
            self._merge_incoming_edge(dst, src, obj_t, conf, rel, hard)

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
            for fn in obj.get("weak_producers", []):
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

    def _merge_incoming_edge(self, dst: str, src: str, obj_t: str, conf: float, rel: str, hard: bool) -> None:
        if not src or not dst or dst not in self.incoming_edges:
            return
        rows = self.incoming_edges[dst]
        for i, (s, o, c, r, h) in enumerate(rows):
            if s == src and o == obj_t and r == rel and h == hard:
                if conf > c:
                    rows[i] = (s, o, conf, r, h)
                return
        rows.append((src, obj_t, conf, rel, hard))

    def _reload_learned_edges(self) -> None:
        path = self.learned_edges_path
        if not path:
            return
        try:
            st = path.stat()
        except Exception:
            return
        if st.st_mtime_ns == self._learned_edges_mtime_ns:
            return
        self._learned_edges_mtime_ns = st.st_mtime_ns
        try:
            raw = json.loads(path.read_text())
        except Exception:
            return
        rows = raw.get("edges")
        if not isinstance(rows, list):
            rows = raw.get("learned_edges")
        if not isinstance(rows, list):
            return
        for e in rows:
            if not isinstance(e, dict):
                continue
            src = str(e.get("src") or "")
            dst = str(e.get("dst") or "")
            if not src or not dst or dst not in self.required_types_soft:
                continue
            rel = str(e.get("relation") or "producer_consumer")
            if rel != "producer_consumer":
                continue
            try:
                conf = float(e.get("confidence", 0.0))
            except Exception:
                conf = 0.0
            if conf <= 0.0:
                continue
            obj_t = str(e.get("object_type") or "")
            if obj_t:
                self.required_types_soft[dst].add(obj_t)
                prev = self.required_types_soft_conf[dst].get(obj_t, 0.0)
                self.required_types_soft_conf[dst][obj_t] = max(prev, conf)
            self._merge_incoming_edge(dst, src, obj_t, conf, rel, False)

    def _reload_prefix_weights(self) -> None:
        path = self.prefix_weights_path
        if not path:
            return
        try:
            st = path.stat()
        except Exception:
            return
        if st.st_mtime_ns == self._prefix_weights_mtime_ns:
            return
        self._prefix_weights_mtime_ns = st.st_mtime_ns
        try:
            raw = json.loads(path.read_text())
        except Exception:
            return

        weights_src = raw
        if isinstance(raw, dict) and isinstance(raw.get("weights"), dict):
            weights_src = raw.get("weights")
        if not isinstance(weights_src, dict):
            return
        parsed: Dict[str, float] = {}
        for k, v in weights_src.items():
            if not isinstance(k, str):
                continue
            try:
                w = float(v)
            except Exception:
                continue
            if w > 0.0:
                parsed[k] = w
        self.prefix_weights = parsed

    def _reload_online_signals(self) -> None:
        self._reload_learned_edges()
        self._reload_prefix_weights()

    def _has_live(self, state: PlannerState, obj_t: str) -> bool:
        return bool(state.live_handles.get(obj_t))

    def _hard_filter(self, state: PlannerState, api: str) -> bool:
        if self.mode == "explore":
            return True

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
        for src, _obj_t, conf, rel, _hard in self.incoming_edges.get(api, []):
            if src in seen:
                if rel == "producer_consumer":
                    score += conf
                elif rel == "invalidates_before_use" and not self.config.misuse_mode:
                    # Penalize sequencing a likely invalidated consumer after deleter.
                    score -= conf

        # Balanced mode: apply soft dependency penalty when producer type is not live.
        if self.mode == "balanced":
            for obj_t in self.required_types_soft.get(api, set()):
                if not self._has_live(state, obj_t):
                    score -= float(self.required_types_soft_conf.get(api, {}).get(obj_t, 0.6))

        # Coverage novelty signal (external).
        score += max(0.0, float(self.novelty_provider(api)))

        # Optional prefix continuation bias from online feedback.
        if self.prefix_weights:
            candidate = state.seq + [api]
            max_k = min(4, len(candidate))
            for k in range(2, max_k + 1):
                key = ",".join(candidate[:k])
                score += float(self.prefix_weights.get(key, 0.0))

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

        if self.mode == "explore":
            scored = [(self._score(state, api), api) for api in cands]
            min_score = min(s for s, _ in scored)
            # Shift all scores positive and sample proportionally for exploration.
            weights = [max(0.001, (s - min_score) + 0.001) for s, _ in scored]
            return self.rng.choices([api for _, api in scored], weights=weights, k=1)[0]

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
        self._reload_online_signals()
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
