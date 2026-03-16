#!/usr/bin/env python3
"""
Aggregate per-process API stats into a novelty + online-learning signal.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


def _to_non_negative_int(value: object) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
    except Exception:
        return 0
    return n if n > 0 else 0


def _to_non_negative_float(value: object) -> float:
    try:
        n = float(value)  # type: ignore[arg-type]
    except Exception:
        return 0.0
    return n if n > 0.0 else 0.0


def load_stats(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_api_rows(path: Path) -> List[dict]:
    rows = load_stats(path).get("apis")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _merge_api_rows_from_obj(obj: dict, merged: Dict[str, dict]) -> None:
    rows = obj.get("apis")
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        if not name:
            continue
        entry = merged.setdefault(
            name,
            {"name": name, "seen": 0, "executed": 0, "skipped": 0},
        )
        entry["seen"] += _to_non_negative_int(row.get("seen"))
        entry["executed"] += _to_non_negative_int(row.get("executed"))
        entry["skipped"] += _to_non_negative_int(row.get("skipped"))


def _merge_pair_rows_from_obj(
    obj: dict,
    merged: Dict[Tuple[str, str], int],
    *,
    field_name: str = "pairs",
) -> None:
    rows = obj.get(field_name)
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            src = str(row.get("src") or "")
            dst = str(row.get("dst") or "")
            if not src or not dst:
                continue
            count = _to_non_negative_int(row.get("count"))
            if count <= 0:
                continue
            merged[(src, dst)] = merged.get((src, dst), 0) + count
        return

    # Backward-compatible alternative: {"A,B": 10, ...}
    if isinstance(rows, dict):
        for key, value in rows.items():
            if not isinstance(key, str):
                continue
            if "," not in key:
                continue
            src, dst = [x.strip() for x in key.split(",", 1)]
            if not src or not dst:
                continue
            count = _to_non_negative_int(value)
            if count <= 0:
                continue
            merged[(src, dst)] = merged.get((src, dst), 0) + count


def _merge_prefix_rows_from_obj(
    obj: dict,
    merged: Dict[str, int],
    *,
    field_name: str = "prefixes",
) -> None:
    rows = obj.get(field_name)
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            seq = str(row.get("seq") or row.get("prefix") or "")
            if not seq:
                continue
            count = _to_non_negative_int(row.get("count"))
            if count <= 0:
                continue
            merged[seq] = merged.get(seq, 0) + count
        return

    # Backward-compatible alternative: {"A,B": 3, "A,B,C": 1, ...}
    if isinstance(rows, dict):
        for key, value in rows.items():
            if not isinstance(key, str):
                continue
            seq = key.strip()
            if not seq:
                continue
            count = _to_non_negative_int(value)
            if count <= 0:
                continue
            merged[seq] = merged.get(seq, 0) + count


def merge_api_rows(paths: Iterable[Path]) -> List[dict]:
    merged: Dict[str, dict] = {}
    for path in paths:
        _merge_api_rows_from_obj(load_stats(path), merged)
    return [merged[name] for name in sorted(merged.keys())]


def novelty_from_counts(*, seen: int, executed: int, skipped: int) -> float:
    # Keep formula aligned with seed_generator.build_novelty_scores(apis format).
    base = 1.0 / (1.0 + float(max(0, executed)))
    seen_f = float(max(0, seen))
    skipped_f = float(max(0, skipped))
    skip_penalty = min(0.5, skipped_f / (seen_f + 1.0))
    return max(0.0, base - (0.3 * skip_penalty))


def _prefix_weights_from_counts(prefix_counts: Dict[str, int], *, min_prefix_count: int) -> Dict[str, float]:
    filtered = {k: v for k, v in prefix_counts.items() if v >= min_prefix_count}
    if not filtered:
        return {}
    max_count = max(filtered.values())
    if max_count <= 0:
        return {}
    out: Dict[str, float] = {}
    for key in sorted(filtered.keys()):
        out[key] = round(float(filtered[key]) / float(max_count), 6)
    return out


def _learned_edges_from_pairs(
    pair_counts: Dict[Tuple[str, str], int],
    *,
    api_novelty: Dict[str, float],
    min_pair_count: int,
) -> List[dict]:
    eligible = [(src, dst, c) for (src, dst), c in pair_counts.items() if c >= min_pair_count]
    if not eligible:
        return []
    max_count = max(c for _, _, c in eligible)
    if max_count <= 0:
        return []
    out: List[dict] = []
    for src, dst, count in eligible:
        base = float(count) / float(max_count)
        novelty_boost = min(0.15, _to_non_negative_float(api_novelty.get(dst, 0.0)) * 0.3)
        confidence = min(0.95, 0.35 + (0.6 * base) + novelty_boost)
        out.append(
            {
                "src": src,
                "dst": dst,
                "relation": "producer_consumer",
                "hardness": "soft",
                "confidence": round(confidence, 6),
                "count": int(count),
            }
        )
    out.sort(key=lambda e: (-float(e.get("confidence", 0.0)), -int(e.get("count", 0)), str(e.get("src")), str(e.get("dst"))))
    return out


def build_feedback_signal(
    paths: Iterable[Path],
    *,
    min_pair_count: int = 2,
    min_prefix_count: int = 2,
) -> dict:
    source_paths = list(paths)
    merged_apis: Dict[str, dict] = {}
    merged_pairs: Dict[Tuple[str, str], int] = {}
    merged_coverage_pairs: Dict[Tuple[str, str], int] = {}
    merged_prefixes: Dict[str, int] = {}
    merged_coverage_prefixes: Dict[str, int] = {}

    for path in source_paths:
        obj = load_stats(path)
        if not obj:
            continue
        _merge_api_rows_from_obj(obj, merged_apis)
        _merge_pair_rows_from_obj(obj, merged_pairs, field_name="pairs")
        _merge_pair_rows_from_obj(obj, merged_coverage_pairs, field_name="coverage_pairs")
        _merge_prefix_rows_from_obj(obj, merged_prefixes, field_name="prefixes")
        _merge_prefix_rows_from_obj(obj, merged_coverage_prefixes, field_name="coverage_prefixes")

    rows = [merged_apis[name] for name in sorted(merged_apis.keys())]
    api_novelty: Dict[str, float] = {}
    total_seen = 0
    total_executed = 0
    total_skipped = 0

    for row in rows:
        name = str(row.get("name") or "")
        if not name:
            continue
        seen = _to_non_negative_int(row.get("seen"))
        executed = _to_non_negative_int(row.get("executed"))
        skipped = _to_non_negative_int(row.get("skipped"))
        api_novelty[name] = novelty_from_counts(seen=seen, executed=executed, skipped=skipped)
        total_seen += seen
        total_executed += executed
        total_skipped += skipped

    pair_rows: List[dict] = []
    for (src, dst), count in sorted(merged_pairs.items()):
        pair_rows.append({"src": src, "dst": dst, "count": int(count)})

    coverage_pair_rows: List[dict] = []
    for (src, dst), count in sorted(merged_coverage_pairs.items()):
        coverage_pair_rows.append({"src": src, "dst": dst, "count": int(count)})

    prefix_rows: List[dict] = []
    for key in sorted(merged_prefixes.keys()):
        prefix_rows.append({"seq": key, "count": int(merged_prefixes[key])})

    coverage_prefix_rows: List[dict] = []
    for key in sorted(merged_coverage_prefixes.keys()):
        coverage_prefix_rows.append({"seq": key, "count": int(merged_coverage_prefixes[key])})

    pair_source = "coverage_pairs" if merged_coverage_pairs else "pairs"
    learning_pairs = merged_coverage_pairs if merged_coverage_pairs else merged_pairs

    if merged_coverage_prefixes:
        learning_prefixes = dict(merged_coverage_prefixes)
        prefix_source = "coverage_prefixes"
    elif merged_prefixes:
        learning_prefixes = dict(merged_prefixes)
        prefix_source = "prefixes"
    else:
        # If harness didn't emit prefixes yet, derive simple 2-API prefixes from the selected pair signal.
        learning_prefixes = {}
        for (src, dst), count in learning_pairs.items():
            key = f"{src},{dst}"
            learning_prefixes[key] = learning_prefixes.get(key, 0) + int(count)
        prefix_source = f"derived_from_{pair_source}" if learning_prefixes else "none"

    prefix_weights = _prefix_weights_from_counts(learning_prefixes, min_prefix_count=min_prefix_count)
    learned_edges = _learned_edges_from_pairs(learning_pairs, api_novelty=api_novelty, min_pair_count=min_pair_count)

    return {
        "apis": rows,
        "pairs": pair_rows,
        "coverage_pairs": coverage_pair_rows,
        "prefixes": prefix_rows,
        "coverage_prefixes": coverage_prefix_rows,
        "api_novelty": api_novelty,
        "prefix_weights": prefix_weights,
        "learned_edges": learned_edges,
        "meta": {
            "input_files": len(source_paths),
            "api_count": len(rows),
            "pair_count": len(pair_rows),
            "coverage_pair_count": len(coverage_pair_rows),
            "learning_pair_count": len(learning_pairs),
            "prefix_count": len(prefix_rows),
            "coverage_prefix_count": len(coverage_prefix_rows),
            "learning_prefix_count": len(learning_prefixes),
            "total_seen": total_seen,
            "total_executed": total_executed,
            "total_skipped": total_skipped,
            "pair_signal_source": pair_source,
            "prefix_signal_source": prefix_source,
            "generated_at_unix": int(time.time()),
            "min_pair_count": int(min_pair_count),
            "min_prefix_count": int(min_prefix_count),
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge proto-liberator api_stats.*.json and compute novelty/online-learning signals",
    )
    parser.add_argument(
        "--input-dir",
        default="api_stats",
        help="Directory containing per-process api_stats files (default: api_stats)",
    )
    parser.add_argument(
        "--pattern",
        default="api_stats.*.json",
        help="Glob pattern for per-process files (default: api_stats.*.json)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Main novelty output JSON path (default: <input-dir>/api_stats.json)",
    )
    parser.add_argument(
        "--learned-edges-out",
        default=None,
        help="Learned edges output JSON path (default: sibling learned_edges.json)",
    )
    parser.add_argument(
        "--prefix-weights-out",
        default=None,
        help="Prefix weights output JSON path (default: sibling prefix_weights.json)",
    )
    parser.add_argument(
        "--min-pair-count",
        type=int,
        default=2,
        help="Minimum pair count to emit learned edge (default: 2)",
    )
    parser.add_argument(
        "--min-prefix-count",
        type=int,
        default=2,
        help="Minimum prefix count to emit prefix weight (default: 2)",
    )
    args = parser.parse_args(argv)

    input_dir = Path(args.input_dir)
    input_paths = sorted(input_dir.glob(args.pattern))
    signal = build_feedback_signal(
        input_paths,
        min_pair_count=max(1, int(args.min_pair_count)),
        min_prefix_count=max(1, int(args.min_prefix_count)),
    )

    output_path = Path(args.output) if args.output else (input_dir / "api_stats.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(signal, indent=2, sort_keys=True) + "\n")

    learned_edges_path = Path(args.learned_edges_out) if args.learned_edges_out else output_path.with_name("learned_edges.json")
    learned_edges_path.parent.mkdir(parents=True, exist_ok=True)
    learned_edges_path.write_text(
        json.dumps(
            {
                "edges": signal.get("learned_edges", []),
                "meta": signal.get("meta", {}),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    prefix_weights_path = Path(args.prefix_weights_out) if args.prefix_weights_out else output_path.with_name("prefix_weights.json")
    prefix_weights_path.parent.mkdir(parents=True, exist_ok=True)
    prefix_weights_path.write_text(
        json.dumps(
            {
                "weights": signal.get("prefix_weights", {}),
                "meta": signal.get("meta", {}),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    print(
        f"Merged {len(input_paths)} files -> {output_path} "
        f"(apis={signal['meta']['api_count']} pairs={signal['meta']['pair_count']} prefixes={signal['meta']['prefix_count']})\n"
        f"  learned_edges: {learned_edges_path}\n"
        f"  prefix_weights: {prefix_weights_path}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
