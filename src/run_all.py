#!/usr/bin/env python3
"""
Orchestrator - run the proto-liberator pipeline end-to-end.

This script is intentionally conservative: it does not run libErator analysis.
Instead, it consumes libErator outputs (conditions/apis/driver meta) and:

  schema -> nanopb bindings -> harness -> (optional) seeds -> (optional) build -> (optional) fuzz

It supports both schema contracts:
  - v1: fixed-sequence harness (driver.meta api_sequence/api_multiset)
  - v2: dynamic dispatch “super harness” (Action.oneof + repeated actions)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class Cmd:
    argv: List[str]
    cwd: Optional[Path] = None
    env: Optional[dict] = None

    def to_shell(self) -> str:
        return " ".join(shlex.quote(a) for a in self.argv)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(cmd: Cmd, *, dry_run: bool) -> None:
    prefix = "[Orch:DRY]" if dry_run else "[Orch]"
    print(f"{prefix} {cmd.to_shell()}")
    if dry_run:
        return
    subprocess.check_call(
        cmd.argv,
        cwd=str(cmd.cwd) if cmd.cwd else None,
        env=cmd.env,
    )


def _write_json(path: Path, obj: object, *, dry_run: bool) -> None:
    if dry_run:
        print(f"[Orch:DRY] write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True))


def _resolve_python(python: str) -> str:
    return python or sys.executable


def _rewrite_flag_values_starting_with_dash(argv: List[str], *, flag: str) -> List[str]:
    """
    argparse treats tokens starting with '-' as new options, so `--flag -foo` is ambiguous.
    Rewrite `--flag -foo` into `--flag=-foo` for better UX when passing clang-style flags.
    """

    rewritten: List[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == flag and i + 1 < len(argv):
            value = argv[i + 1]
            if value.startswith("-") and not value.startswith("--") and value != "-":
                rewritten.append(f"{flag}={value}")
                i += 2
                continue
        rewritten.append(argv[i])
        i += 1
    return rewritten


def _target_libs_for_profile(target_libs: List[str]) -> List[str]:
    """
    llvm-cov only reports coverage for code compiled with:
      -fprofile-instr-generate -fcoverage-mapping

    If a target is linked as a prebuilt archive (.a), we cannot retroactively add
    coverage mapping to its already-compiled objects. Many libErator builds also
    provide LLVM bitcode next to the archive (e.g. libcjson.a.bc). When building
    the *_profile.bin, prefer that bitcode sibling so the library itself is
    instrumented and appears in coverage reports.
    """
    out: List[str] = []
    for p in target_libs:
        if p.endswith(".a"):
            # Prefer a dedicated coverage archive if available (e.g., libfoo_profile.a),
            # otherwise fall back to a bitcode sibling, then to the original archive.
            profile_variant = f"{p[:-2]}_profile.a"
            if os.path.exists(profile_variant):
                out.append(profile_variant)
                continue

            bc_variant = p + ".bc"
            if os.path.exists(bc_variant):
                out.append(bc_variant)
                continue

        out.append(p)
    return out


def _aggregate_feedback_signal_from_stats(
    *,
    out_dir: Path,
    src_dir: Path,
    python: str,
    dry_run: bool,
    causal_evidence_path: Optional[Path] = None,
) -> Optional[Path]:
    """
    Aggregate per-process API stats into a novelty signal JSON.
    """
    stats_dir = out_dir / "api_stats"
    if not stats_dir.exists():
        return None

    if not any(stats_dir.glob("api_stats.*.json")):
        return None

    output = (stats_dir / "api_stats.json").resolve()
    agg_argv: List[str] = [
        python,
        str(src_dir / "feedback_aggregator.py"),
        "--input-dir",
        str(stats_dir),
        "--output",
        str(output),
    ]
    if causal_evidence_path:
        agg_argv += ["--causal-evidence-json", str(causal_evidence_path)]
    _run(Cmd(agg_argv), dry_run=dry_run)
    return output


def _run_causal_edge_verifier(
    *,
    src_dir: Path,
    python: str,
    dry_run: bool,
    out_dir: Path,
    fuzzer_bin: Path,
    schema_proto: Path,
    conditions: Path,
    corpus_dir: Path,
    max_inputs: int,
    max_ablations_per_input: int,
    min_drop: int,
    timeout_sec: int,
    protoc_bin: str,
    proto_include_dirs: List[Path],
) -> Optional[Path]:
    if not corpus_dir.exists():
        return None
    if not any(corpus_dir.glob("*")):
        return None
    causal_out = (out_dir / "api_stats" / "causal_edges.json").resolve()
    verify_argv: List[str] = [
        python,
        str(src_dir / "causal_edge_verifier.py"),
        "--fuzzer-bin",
        str(fuzzer_bin),
        "--proto",
        str(schema_proto),
        "--conditions",
        str(conditions),
        "--corpus-dir",
        str(corpus_dir),
        "--output",
        str(causal_out),
        "--max-inputs",
        str(max(1, int(max_inputs))),
        "--max-ablations-per-input",
        str(max(1, int(max_ablations_per_input))),
        "--min-drop",
        str(max(1, int(min_drop))),
        "--timeout-sec",
        str(max(1, int(timeout_sec))),
        "--protoc-bin",
        str(protoc_bin),
    ]
    for inc in proto_include_dirs:
        verify_argv += ["--proto-include", str(inc)]
    _run(Cmd(verify_argv), dry_run=dry_run)
    return causal_out


def _safe_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return 0


def _feedback_refresh_metrics(
    *,
    stats_dir: Path,
    novelty_signal_path: Path,
) -> Dict[str, int]:
    """
    Read refresh metrics from aggregated files, with a dry-run fallback that
    computes the merged signal in-memory from api_stats.*.json inputs.
    """
    metrics: Dict[str, int] = {
        "api_count": 0,
        "pair_count": 0,
        "prefix_count": 0,
        "learned_edges": 0,
        "prefix_weights": 0,
    }

    loaded_any = False
    if novelty_signal_path.exists():
        try:
            novelty = json.loads(novelty_signal_path.read_text())
        except Exception:
            novelty = {}
        if isinstance(novelty, dict):
            meta = novelty.get("meta", {})
            if isinstance(meta, dict):
                metrics["api_count"] = _safe_int(meta.get("api_count"))
                metrics["pair_count"] = _safe_int(meta.get("pair_count"))
                metrics["prefix_count"] = _safe_int(meta.get("prefix_count"))
            edges = novelty.get("learned_edges")
            if isinstance(edges, list):
                metrics["learned_edges"] = len(edges)
            weights = novelty.get("prefix_weights")
            if isinstance(weights, dict):
                metrics["prefix_weights"] = len(weights)
            loaded_any = True

    learned_edges_path = stats_dir / "learned_edges.json"
    if learned_edges_path.exists():
        try:
            learned = json.loads(learned_edges_path.read_text())
        except Exception:
            learned = {}
        if isinstance(learned, dict):
            edges = learned.get("edges")
            if isinstance(edges, list):
                metrics["learned_edges"] = len(edges)
                loaded_any = True

    prefix_weights_path = stats_dir / "prefix_weights.json"
    if prefix_weights_path.exists():
        try:
            weights_json = json.loads(prefix_weights_path.read_text())
        except Exception:
            weights_json = {}
        if isinstance(weights_json, dict):
            weights = weights_json.get("weights")
            if isinstance(weights, dict):
                metrics["prefix_weights"] = len(weights)
                loaded_any = True

    if loaded_any:
        return metrics

    # Dry-run fallback: compute merged signal from existing per-process files.
    try:
        from feedback_aggregator import build_feedback_signal  # local import to avoid hard dependency at startup
    except Exception:
        return metrics

    inputs = sorted(stats_dir.glob("api_stats.*.json"))
    if not inputs:
        return metrics
    try:
        merged = build_feedback_signal(inputs)
    except Exception:
        return metrics
    if not isinstance(merged, dict):
        return metrics

    meta = merged.get("meta", {})
    if isinstance(meta, dict):
        metrics["api_count"] = _safe_int(meta.get("api_count"))
        metrics["pair_count"] = _safe_int(meta.get("pair_count"))
        metrics["prefix_count"] = _safe_int(meta.get("prefix_count"))
    edges = merged.get("learned_edges")
    if isinstance(edges, list):
        metrics["learned_edges"] = len(edges)
    weights = merged.get("prefix_weights")
    if isinstance(weights, dict):
        metrics["prefix_weights"] = len(weights)
    return metrics


def _crash_classification_metrics(
    *,
    summary_path: Path,
) -> Dict[str, int]:
    metrics: Dict[str, int] = {
        "total": 0,
        "genuine": 0,
        "constraint_misuse": 0,
    }
    if not summary_path.exists():
        return metrics
    try:
        summary = json.loads(summary_path.read_text())
    except Exception:
        return metrics
    if not isinstance(summary, dict):
        return metrics
    metrics["total"] = _safe_int(summary.get("total"))
    genuine = _safe_int(summary.get("genuine"))
    if genuine <= 0:
        genuine = _safe_int(summary.get("genuine_bug"))
    metrics["genuine"] = genuine
    metrics["constraint_misuse"] = _safe_int(summary.get("constraint_misuse"))
    return metrics


def _crash_learning_metrics(
    *,
    learned_constraints_path: Path,
) -> Dict[str, int]:
    metrics: Dict[str, int] = {
        "constraints": 0,
        "events": 0,
        "reproducible": 0,
        "input_crashes": 0,
    }
    if not learned_constraints_path.exists():
        return metrics
    try:
        payload = json.loads(learned_constraints_path.read_text())
    except Exception:
        return metrics
    if not isinstance(payload, dict):
        return metrics
    meta = payload.get("meta", {})
    if isinstance(meta, dict):
        metrics["constraints"] = _safe_int(meta.get("constraint_count"))
        metrics["events"] = _safe_int(meta.get("successful_shadow_mutations"))
        metrics["reproducible"] = _safe_int(meta.get("reproducible_crashes"))
        metrics["input_crashes"] = _safe_int(meta.get("input_crashes"))
    return metrics


def _crash_constraints_to_seed_constants(
    *,
    learned_constraints_path: Path,
) -> Dict[str, Dict[str, int]]:
    if not learned_constraints_path.exists():
        return {}
    try:
        payload = json.loads(learned_constraints_path.read_text())
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("constraints")
    if not isinstance(rows, list):
        return {}

    out: Dict[str, Dict[str, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        api = str(row.get("api") or "").strip()
        param = str(row.get("param") or "").strip()
        if not api or not param or not param.startswith("param_"):
            continue

        value: Optional[int] = None
        learnt_vals = row.get("learnt_vals")
        if isinstance(learnt_vals, list) and learnt_vals:
            ints: List[int] = []
            for v in learnt_vals:
                try:
                    ints.append(int(v))
                except Exception:
                    continue
            if ints:
                ints.sort()
                value = ints[len(ints) // 2]

        if value is None:
            ranges = row.get("ranges")
            if isinstance(ranges, list) and ranges:
                first = ranges[0] if isinstance(ranges[0], dict) else {}
                if isinstance(first, dict):
                    try:
                        lo = int(first.get("min"))
                        hi = int(first.get("max"))
                        if hi < lo:
                            lo, hi = hi, lo
                        value = lo + ((hi - lo) // 2)
                    except Exception:
                        value = None

        if value is None:
            continue
        out.setdefault(api, {})[param] = int(value)
    return out


def _auto_feedback_signal(
    *,
    novelty_signal_json: Optional[str],
    out_dir: Path,
    src_dir: Path,
    python: str,
    dry_run: bool,
) -> Optional[Path]:
    """
    Resolve novelty signal path for seed generation.

    Priority:
      1) explicit --novelty-signal-json
      2) auto-aggregate prior per-process api_stats.*.json in <out-dir>/api_stats
    """
    if novelty_signal_json:
        return Path(novelty_signal_json).resolve()

    return _aggregate_feedback_signal_from_stats(
        out_dir=out_dir,
        src_dir=src_dir,
        python=python,
        dry_run=dry_run,
        causal_evidence_path=None,
    )


def _build_seed_generator_argv(
    *,
    python: str,
    src_dir: Path,
    conditions: Path,
    seeds_dir: Path,
    num_seeds: int,
    seed_max_len: int,
    seed_rng: int,
    driver_meta_path: Path,
    minimum_apis: Optional[str],
    apipass_dir: Optional[str],
    seed_constants_json: Optional[str],
    novelty_signal_path: Optional[Path],
    selected_graph: Optional[Path],
    schedule_mode: str,
    misuse_mode: bool,
) -> List[str]:
    seed_argv: List[str] = [
        python,
        str(src_dir / "seed_generator.py"),
        "--conditions",
        str(conditions),
        "--output-dir",
        str(seeds_dir),
        "--num-seeds",
        str(num_seeds),
        "--max-len",
        str(seed_max_len),
        "--rng-seed",
        str(seed_rng),
        "--driver",
        str(driver_meta_path),
        "--mode",
        "wire",
    ]
    if minimum_apis:
        seed_argv += ["--minimum-apis", str(Path(minimum_apis).resolve())]
    if apipass_dir:
        seed_argv += ["--apipass-dir", str(Path(apipass_dir).resolve())]
    if seed_constants_json:
        seed_argv += ["--constants-json", str(Path(seed_constants_json).resolve())]
    if novelty_signal_path:
        seed_argv += ["--novelty-signal-json", str(novelty_signal_path)]
    if selected_graph:
        seed_argv += ["--constraint-graph", str(selected_graph)]
        seed_argv += ["--schedule-mode", schedule_mode]
        if misuse_mode:
            seed_argv += ["--misuse-mode"]
    return seed_argv


def _refresh_feedback_and_reseed(
    *,
    out_dir: Path,
    src_dir: Path,
    python: str,
    dry_run: bool,
    causal_evidence_path: Optional[Path],
    should_reseed: bool,
    seed_argv: Optional[List[str]],
) -> Optional[Path]:
    refreshed_signal = _aggregate_feedback_signal_from_stats(
        out_dir=out_dir,
        src_dir=src_dir,
        python=python,
        dry_run=dry_run,
        causal_evidence_path=causal_evidence_path,
    )
    if not refreshed_signal:
        return None
    stats_dir = out_dir / "api_stats"
    learned_edges_path = stats_dir / "learned_edges.json"
    prefix_weights_path = stats_dir / "prefix_weights.json"
    metrics = _feedback_refresh_metrics(
        stats_dir=stats_dir,
        novelty_signal_path=refreshed_signal,
    )
    print(f"[Orch] feedback signal refreshed: {refreshed_signal}")
    print(
        "[Orch] feedback refresh metrics: "
        f"apis={metrics['api_count']} "
        f"pairs={metrics['pair_count']} "
        f"prefixes={metrics['prefix_count']} "
        f"learned_edges={metrics['learned_edges']} "
        f"prefix_weights={metrics['prefix_weights']}"
    )
    print(
        "[Orch] feedback refresh outputs: "
        f"learned_edges={learned_edges_path} "
        f"prefix_weights={prefix_weights_path}"
    )
    if should_reseed and seed_argv:
        reseed_argv = list(seed_argv)
        reseed_argv += ["--novelty-signal-json", str(refreshed_signal)]
        _run(Cmd(reseed_argv), dry_run=dry_run)
        print(f"[Orch] feedback reseed complete: {refreshed_signal}")
    return refreshed_signal


def main() -> int:
    parser = argparse.ArgumentParser(description="Proto-libErator Orchestrator")

    parser.add_argument("--library", required=True, help="Library name (e.g., cjson)")
    parser.add_argument("--conditions", required=True, help="Path to libErator conditions.json")
    parser.add_argument("--apis", required=True, help="Path to libErator apis_clang.json (JSONL)")
    parser.add_argument(
        "--minimum-apis",
        default=None,
        help="Optional apis_minimized.txt (one function per line) to restrict schema/harness/seeds",
    )
    parser.add_argument(
        "--apipass-dir",
        default=None,
        help="Optional apipass directory (defaults to parent of conditions.json)",
    )
    parser.add_argument("--driver", help="Path to libErator driver.meta (required for v1; optional for v2)")
    parser.add_argument("--out-dir", required=True, help="Output directory (created if missing)")

    parser.add_argument("--schema-mode", choices=["v1", "v2"], default="v2", help="Schema contract version")
    parser.add_argument("--mutation-mode", choices=["nanopb", "lpm"], default="lpm", help="Mutation engine")
    parser.add_argument("--max-actions", type=int, default=64, help="(v2) max Action entries")
    parser.add_argument("--max-calls-per-api", type=int, default=4, help="(v1) max params per API")
    parser.add_argument("--max-bytes-size", type=int, default=65536, help="Nanopb max_size for bytes fields")

    parser.add_argument("--package", default=None, help="Protobuf package prefix for generated C structs")
    parser.add_argument("--header", action="append", default=[], help="Extra header include (repeatable)")
    parser.add_argument(
        "--harness-style",
        choices=["strict", "simple"],
        default="strict",
        help="Validation strictness for generated harness",
    )

    parser.add_argument("--python", default=None, help="Python interpreter for generator scripts")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them")

    parser.add_argument("--nanopb-dir", default=None, help="Path to nanopb checkout (default: external/nanopb)")

    parser.add_argument("--generate-seeds", action="store_true", help="(v2) Generate an initial seed corpus")
    parser.add_argument("--seeds-dir", default=None, help="Seed output dir (default: <out-dir>/corpus)")
    parser.add_argument("--num-seeds", type=int, default=64, help="(v2) number of seeds")
    parser.add_argument("--seed-max-len", type=int, default=16, help="(v2) max actions per seed")
    parser.add_argument("--seed-rng", type=int, default=0, help="(v2) deterministic RNG seed")
    parser.add_argument(
        "--constraint-graph",
        default=None,
        help="Optional constraint_graph.json to drive stateful sequence planning in seed generation",
    )
    parser.add_argument(
        "--schedule-mode",
        choices=["strict", "balanced", "explore"],
        default="strict",
        help="Planner mode for --constraint-graph",
    )
    parser.add_argument(
        "--misuse-mode",
        action="store_true",
        help="Allow explicit misuse-oriented planning when using --constraint-graph",
    )
    parser.add_argument(
        "--seed-constants-json",
        default=None,
        help="Optional JSON mapping function -> {field_name: value} for seed generation",
    )
    parser.add_argument(
        "--novelty-signal-json",
        default=None,
        help="Optional JSON signal (api_stats/coverage) used for planner novelty scoring",
    )

    parser.add_argument("--build", action="store_true", help="Compile a libFuzzer binary")
    parser.add_argument(
        "--build-profile",
        action="store_true",
        help="Compile a coverage-instrumented binary for llvm-cov (writes <out-dir>/<library>_profile.bin)",
    )
    parser.add_argument(
        "--profile-no-bitcode",
        action="store_true",
        help="Do not prefer `*.a.bc` when building *_profile.bin (useful when the bitcode requires unsupported CPU features).",
    )
    parser.add_argument("--fuzz", action="store_true", help="Run the fuzzer after build")
    parser.add_argument(
        "--verify-edges",
        dest="verify_edges",
        action="store_true",
        help="Run ablation-based causal edge verification on corpus and feed result into feedback aggregation (default: enabled)",
    )
    parser.add_argument(
        "--no-verify-edges",
        dest="verify_edges",
        action="store_false",
        help="Disable ablation-based causal edge verification",
    )
    parser.add_argument(
        "--edge-verify-max-inputs",
        type=int,
        default=32,
        help="Max corpus inputs used for causal edge verification (default: 32)",
    )
    parser.add_argument(
        "--edge-verify-max-ablations",
        type=int,
        default=4,
        help="Max ablations per input in causal edge verification (default: 4)",
    )
    parser.add_argument(
        "--edge-verify-min-drop",
        type=int,
        default=1,
        help="Minimum feature-count drop treated as causal support (default: 1)",
    )
    parser.add_argument(
        "--edge-verify-timeout-sec",
        type=int,
        default=15,
        help="Per-run timeout for causal edge verification (default: 15)",
    )
    parser.add_argument(
        "--edge-verify-protoc",
        default="protoc",
        help="protoc binary used by causal edge verification (default: protoc)",
    )
    parser.add_argument(
        "--classify-crashes",
        dest="classify_crashes",
        action="store_true",
        help="Classify crash artifacts into genuine vs constraint-misuse after fuzzing (default: enabled)",
    )
    parser.add_argument(
        "--no-classify-crashes",
        dest="classify_crashes",
        action="store_false",
        help="Disable post-fuzz crash classification",
    )
    parser.add_argument(
        "--crash-timeout-sec",
        type=int,
        default=20,
        help="Per-input replay timeout for crash classification (default: 20)",
    )
    parser.add_argument(
        "--learn-crash-constraints",
        dest="learn_crash_constraints",
        action="store_true",
        help="Learn parameter constraints from genuine crashes via shadow replays (default: enabled)",
    )
    parser.add_argument(
        "--no-learn-crash-constraints",
        dest="learn_crash_constraints",
        action="store_false",
        help="Disable post-fuzz crash-driven constraint learning",
    )
    parser.add_argument(
        "--crash-learn-max-crashes",
        type=int,
        default=16,
        help="Max genuine crashes to analyze in crash-constraint learner (default: 16)",
    )
    parser.add_argument(
        "--crash-learn-max-byte-flips",
        type=int,
        default=64,
        help="Max byte offsets tested per crash in crash-constraint learner (default: 64)",
    )
    parser.add_argument(
        "--crash-learn-min-evidence",
        type=int,
        default=1,
        help="Minimum evidence count to keep a learned crash constraint (default: 1)",
    )
    parser.add_argument(
        "--detect-leaks",
        action="store_true",
        help="Enable LeakSanitizer detection (default: disabled via -detect_leaks=0)",
    )
    parser.add_argument(
        "--fuzz-runs",
        type=int,
        default=100,
        help="libFuzzer -runs for non-duration fuzzing (default: 100)",
    )
    parser.add_argument(
        "--fuzz-duration",
        type=int,
        default=0,
        help="Timed fuzzing budget in seconds; if >0, run in feedback-refresh epochs",
    )
    parser.add_argument(
        "--feedback-refresh-sec",
        type=int,
        default=300,
        help="Feedback refresh period during timed fuzzing (default: 300 seconds)",
    )
    parser.add_argument(
        "--feedback-reseed",
        dest="feedback_reseed",
        action="store_true",
        help="Regenerate corpus seeds from refreshed novelty signal during fuzzing (default: enabled)",
    )
    parser.add_argument(
        "--no-feedback-reseed",
        dest="feedback_reseed",
        action="store_false",
        help="Disable periodic seed regeneration during fuzzing",
    )
    parser.add_argument("--clang", default="clang", help="clang path")
    parser.add_argument("--cc-arg", action="append", default=[], help="Extra clang args (repeatable)")
    parser.add_argument("--target-include", action="append", default=[], help="Add -I<dir> (repeatable)")
    parser.add_argument("--target-lib", action="append", default=[], help="Link a library/archive (repeatable)")
    parser.add_argument("--extra-src", action="append", default=[], help="Compile extra .c/.cc files (repeatable)")
    parser.add_argument(
        "--profile-extra-src",
        action="append",
        default=[],
        help="Compile extra sources into *_profile.bin only (repeatable)",
    )
    parser.add_argument(
        "--profile-keep-target-lib",
        action="store_true",
        help="Also link --target-lib into *_profile.bin (useful when --profile-extra-src does not replace the target)",
    )

    argv = sys.argv[1:]
    argv = _rewrite_flag_values_starting_with_dash(argv, flag="--cc-arg")
    parser.set_defaults(classify_crashes=True)
    parser.set_defaults(learn_crash_constraints=True)
    parser.set_defaults(feedback_reseed=True)
    parser.set_defaults(verify_edges=True)
    args = parser.parse_args(argv)

    root = _repo_root()
    src_dir = root / "src"
    out_dir = Path(args.out_dir).resolve()
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    python = _resolve_python(args.python)
    safe_lib = re.sub(r"[^A-Za-z0-9_]+", "_", str(args.library))
    if not safe_lib or safe_lib[0].isdigit():
        safe_lib = f"lib_{safe_lib}"
    package = args.package or f"{safe_lib}_fuzzer"

    conditions = Path(args.conditions).resolve()
    apis = Path(args.apis).resolve()
    driver = Path(args.driver).resolve() if args.driver else None
    effective_apipass_dir = Path(args.apipass_dir).resolve() if args.apipass_dir else conditions.parent
    auto_constraint_graph: Optional[Path] = None
    auto_constraint_graph_attempted = False

    if args.mutation_mode == "lpm" and args.schema_mode != "v2":
        raise SystemExit("--mutation-mode lpm currently requires --schema-mode v2")

    schema_proto = out_dir / f"{args.library}.{args.schema_mode}.proto"
    bindings_dir = out_dir / "bindings"
    harness_c = out_dir / ("harness.cc" if args.mutation_mode == "lpm" else "harness.c")
    driver_meta_path = out_dir / "driver.meta.json"

    nanopb_dir = Path(args.nanopb_dir).resolve() if args.nanopb_dir else (root / "external" / "nanopb")
    nanopb_protoc = nanopb_dir / "generator" / "protoc"
    if (args.build or args.fuzz) and args.mutation_mode == "nanopb":
        if not nanopb_protoc.exists():
            raise SystemExit(f"nanopb protoc wrapper not found: {nanopb_protoc}")

    # 0) Driver meta for wrapper generator
    if args.schema_mode == "v1" and not driver:
        raise SystemExit("--driver is required for --schema-mode v1")

    wrapper_meta = {"headers": list(args.header)}
    if driver:
        if driver.exists() and not args.dry_run:
            wrapper_meta.update(json.loads(driver.read_text()))
    if args.schema_mode == "v2":
        wrapper_meta.setdefault("api_sequence", [])
    _write_json(driver_meta_path, wrapper_meta, dry_run=args.dry_run)

    # 1) Schema
    schema_argv: List[str] = [
        python,
        str(src_dir / "proto_generator.py"),
        "--conditions",
        str(conditions),
        "--apis",
        str(apis),
        "--output",
        str(schema_proto),
        "--library",
        args.library,
        "--schema-mode",
        args.schema_mode,
        "--mutation-mode",
        args.mutation_mode,
        "--max-bytes-size",
        str(args.max_bytes_size),
        "--max-calls-per-api",
        str(args.max_calls_per_api),
        "--max-actions",
        str(args.max_actions),
    ]
    if args.minimum_apis:
        schema_argv += ["--minimum-apis", str(Path(args.minimum_apis).resolve())]
    if args.apipass_dir:
        schema_argv += ["--apipass-dir", str(Path(args.apipass_dir).resolve())]
    _run(Cmd(schema_argv), dry_run=args.dry_run)

    # 2) Bindings
    if not args.dry_run:
        bindings_dir.mkdir(parents=True, exist_ok=True)
    
    if args.mutation_mode == "lpm":
        # Use LPM's protoc
        lpm_protoc = root / "external/libprotobuf-mutator/build/external.protobuf/bin/protoc"
        if not lpm_protoc.exists():
             # Fallback or error? Let's assume it exists if we are in LPM mode
             print(f"Warning: LPM protoc not found at {lpm_protoc}, trying system protoc")
             lpm_protoc = Path("protoc")

        bindings_cmd = Cmd(
            [
                str(lpm_protoc),
                f"--cpp_out={bindings_dir}",
                f"-I{out_dir}",
                str(schema_proto),
            ]
        )
    else:
        # Nanopb
        bindings_cmd = Cmd(
            [
                str(nanopb_protoc),
                f"--nanopb_out={bindings_dir}",
                f"-I{out_dir}",
                str(schema_proto),
            ]
        )
    _run(bindings_cmd, dry_run=args.dry_run)

    # 2.5) Constraint graph (for wrapper guards and optional sequence planning)
    if args.schema_mode == "v2" and not args.constraint_graph:
        auto_constraint_graph_attempted = True
        graph_out = effective_apipass_dir / "constraint_graph.json"
        if graph_out.exists():
            auto_constraint_graph = graph_out
        elif (effective_apipass_dir / "conditions.json").exists():
            cg_argv: List[str] = [
                python,
                str(src_dir / "constraint_graph_builder.py"),
                "--apipass-dir",
                str(effective_apipass_dir),
                "--library",
                args.library,
            ]
            _run(Cmd(cg_argv), dry_run=args.dry_run)
            auto_constraint_graph = graph_out
        else:
            print(
                f"[Orch] Skipping auto constraint-graph build: "
                f"{effective_apipass_dir / 'conditions.json'} not found"
            )

    # 3) Harness
    wrapper_argv: List[str] = [
        python,
        str(src_dir / "wrapper_generator.py"),
        "--proto",
        str(schema_proto),
        "--driver",
        str(driver_meta_path),
        "--conditions",
        str(conditions),
        "--apis",
        str(apis),
        "--output",
        str(harness_c),
        "--package",
        package,
        "--schema-mode",
        args.schema_mode,
        "--mutation-mode",
        args.mutation_mode,
        "--max-actions",
        str(args.max_actions),
        "--harness-style",
        args.harness_style,
        *sum([["--header", h] for h in args.header], []),
    ]
    if args.minimum_apis:
        wrapper_argv += ["--minimum-apis", str(Path(args.minimum_apis).resolve())]
    if args.apipass_dir:
        wrapper_argv += ["--apipass-dir", str(Path(args.apipass_dir).resolve())]
    selected_graph = Path(args.constraint_graph).resolve() if args.constraint_graph else auto_constraint_graph
    if selected_graph:
        wrapper_argv += ["--constraint-graph", str(selected_graph)]
    _run(Cmd(wrapper_argv), dry_run=args.dry_run)

    # 3.5) Constraint graph (safety fallback before seed generation)
    if (
        args.generate_seeds
        and args.schema_mode == "v2"
        and not args.constraint_graph
        and not auto_constraint_graph
        and not auto_constraint_graph_attempted
    ):
        if (effective_apipass_dir / "conditions.json").exists():
            graph_out = effective_apipass_dir / "constraint_graph.json"
            cg_argv: List[str] = [
                python,
                str(src_dir / "constraint_graph_builder.py"),
                "--apipass-dir",
                str(effective_apipass_dir),
                "--library",
                args.library,
            ]
            _run(Cmd(cg_argv), dry_run=args.dry_run)
            auto_constraint_graph = graph_out
        else:
            print(
                f"[Orch] Skipping auto constraint-graph build: "
                f"{effective_apipass_dir / 'conditions.json'} not found"
            )

    # 4) Seeds (v2)
    seeds_dir = Path(args.seeds_dir).resolve() if args.seeds_dir else (out_dir / "corpus")
    if args.generate_seeds:
        if args.schema_mode != "v2":
            raise SystemExit("--generate-seeds is only supported for --schema-mode v2")
        novelty_signal_path = _auto_feedback_signal(
            novelty_signal_json=args.novelty_signal_json,
            out_dir=out_dir,
            src_dir=src_dir,
            python=python,
            dry_run=args.dry_run,
        )
        selected_graph = Path(args.constraint_graph).resolve() if args.constraint_graph else auto_constraint_graph
        seed_argv = _build_seed_generator_argv(
            python=python,
            src_dir=src_dir,
            conditions=conditions,
            seeds_dir=seeds_dir,
            num_seeds=int(args.num_seeds),
            seed_max_len=int(args.seed_max_len),
            seed_rng=int(args.seed_rng),
            driver_meta_path=driver_meta_path,
            minimum_apis=args.minimum_apis,
            apipass_dir=args.apipass_dir,
            seed_constants_json=args.seed_constants_json,
            novelty_signal_path=novelty_signal_path,
            selected_graph=selected_graph,
            schedule_mode=args.schedule_mode,
            misuse_mode=bool(args.misuse_mode),
        )
        _run(Cmd(seed_argv), dry_run=args.dry_run)

    # 5) Build
    if args.fuzz:
        args.build = True
    fuzzer_bin = out_dir / f"{args.library}_fuzzer.bin"
    profile_bin = out_dir / f"{args.library}_profile.bin"

    if args.build or args.build_profile:
        target_libs_profile = (
            list(args.target_lib) if args.profile_no_bitcode else _target_libs_for_profile(list(args.target_lib))
        )
        if args.mutation_mode == "lpm":
            # LPM Build
            pb_cc = bindings_dir / f"{args.library}.{args.schema_mode}.pb.cc"
            
            lpm_root = root / "external/libprotobuf-mutator"
            lpm_build = lpm_root / "build"
            
            # Gather all static libs from LPM build
            # We need: libprotobuf-mutator-libfuzzer.a, libprotobuf-mutator.a, libprotobuf.a, and absl libs
            # A simple approach is to find all .a files in lpm_build
            # But order matters. libprotobuf-mutator-libfuzzer -> libprotobuf-mutator -> libprotobuf -> absl
            
            libs = []
            libs.append(str(lpm_build / "src/libfuzzer/libprotobuf-mutator-libfuzzer.a"))
            libs.append(str(lpm_build / "src/libprotobuf-mutator.a"))
            libs.append(str(lpm_build / "external.protobuf/lib/libprotobuf.a"))
            
            # Add all other .a files in external.protobuf/lib (absl, etc)
            # We exclude libprotobuf.a (already added) and libprotoc.a (not needed for runtime)
            ext_lib_dir = lpm_build / "external.protobuf/lib"
            if ext_lib_dir.exists():
                for lib in ext_lib_dir.glob("*.a"):
                    if lib.name not in ["libprotobuf.a", "libprotoc.a", "libprotobuf-lite.a"]:
                        libs.append(str(lib))

            def _lpm_cc_base(*, with_asan: bool) -> List[str]:
                sanitize = "-fsanitize=fuzzer,address" if with_asan else "-fsanitize=fuzzer"
                return [
                    args.clang + "++",  # Use clang++
                    "-g",
                    "-O1",
                    sanitize,
                    "-fno-pie",
                    "-no-pie",
                    "-std=c++17",
                    f"-I{bindings_dir}",
                    f"-I{out_dir}",
                    f"-I{lpm_root}",  # For src/libfuzzer/libfuzzer_macro.h
                    f"-I{lpm_build}/external.protobuf/include",  # For google/protobuf
                ]

            def _lpm_sources() -> List[str]:
                return [
                    str(harness_c),
                    str(pb_cc),
                    *args.extra_src,
                ]

            profile_extra_objects: List[str] = []
            if args.build_profile and args.profile_extra_src:
                obj_dir = out_dir / "profile_objs"
                if not args.dry_run:
                    obj_dir.mkdir(parents=True, exist_ok=True)

                for src in args.profile_extra_src:
                    src_path = Path(src)
                    obj_path = obj_dir / (src_path.name + ".o")

                    is_cxx = src_path.suffix.lower() in {".cc", ".cpp", ".cxx"}
                    compiler = (args.clang + "++") if is_cxx else args.clang

                    cc: List[str] = [
                        compiler,
                        "-g",
                        "-O1",
                        "-c",
                        str(src_path),
                        "-o",
                        str(obj_path),
                        "-fprofile-instr-generate",
                        "-fcoverage-mapping",
                    ]
                    if is_cxx:
                        cc.append("-std=c++17")
                    for inc in args.target_include:
                        cc.append(f"-I{inc}")
                    cc.extend(args.cc_arg)
                    _run(Cmd(cc), dry_run=args.dry_run)
                    profile_extra_objects.append(str(obj_path))

            def _lpm_link(
                out_path: Path, *, extra_cflags: Optional[List[str]] = None, with_asan: bool = True
            ) -> None:
                cc: List[str] = _lpm_cc_base(with_asan=with_asan)
                for inc in args.target_include:
                    cc.append(f"-I{inc}")
                cc.extend(args.cc_arg)
                if extra_cflags:
                    cc.extend(extra_cflags)
                cc.extend(_lpm_sources())
                if out_path == profile_bin and profile_extra_objects:
                    cc.extend(profile_extra_objects)
                cc.extend(["-Wl,--start-group"])
                cc.extend(libs)
                cc.extend(["-Wl,--end-group"])
                cc.extend(["-lpthread", "-lz"])
                if out_path == profile_bin:
                    # If profile-only sources are provided, they usually replace the prebuilt target archive.
                    if args.profile_extra_src and not args.profile_keep_target_lib:
                        pass
                    else:
                        cc.extend(target_libs_profile)
                else:
                    cc.extend(args.target_lib)
                cc.extend(["-o", str(out_path)])
                _run(Cmd(cc), dry_run=args.dry_run)

            if args.build:
                _lpm_link(fuzzer_bin, with_asan=True)
            if args.build_profile:
                _lpm_link(
                    profile_bin,
                    extra_cflags=["-fprofile-instr-generate", "-fcoverage-mapping"],
                    with_asan=False,
                )

        else:
            # Nanopb Build
            pb_c = bindings_dir / f"{args.library}.{args.schema_mode}.pb.c"
            if not pb_c.exists() and not args.dry_run:
                # nanopb names output after the input proto stem
                pb_c = bindings_dir / f"{schema_proto.stem}.pb.c"

            def _nanopb_cc_base(*, with_asan: bool) -> List[str]:
                sanitize = "-fsanitize=fuzzer,address" if with_asan else "-fsanitize=fuzzer"
                return [
                    args.clang,
                    "-g",
                    "-O1",
                    sanitize,
                    "-fno-pie",
                    "-no-pie",
                    "-DPB_FIELD_32BIT",
                    f"-I{bindings_dir}",
                    f"-I{nanopb_dir}",
                    f"-I{out_dir}",
                ]

            def _nanopb_sources() -> List[str]:
                return [
                    str(harness_c),
                    str(pb_c),
                    str(nanopb_dir / "pb_common.c"),
                    str(nanopb_dir / "pb_decode.c"),
                    str(nanopb_dir / "pb_encode.c"),
                    *args.extra_src,
                ]

            profile_extra_objects: List[str] = []
            if args.build_profile and args.profile_extra_src:
                obj_dir = out_dir / "profile_objs"
                if not args.dry_run:
                    obj_dir.mkdir(parents=True, exist_ok=True)

                for src in args.profile_extra_src:
                    src_path = Path(src)
                    obj_path = obj_dir / (src_path.name + ".o")

                    compiler = args.clang
                    cc: List[str] = [
                        compiler,
                        "-g",
                        "-O1",
                        "-c",
                        str(src_path),
                        "-o",
                        str(obj_path),
                        "-fprofile-instr-generate",
                        "-fcoverage-mapping",
                    ]
                    for inc in args.target_include:
                        cc.append(f"-I{inc}")
                    cc.extend(args.cc_arg)
                    _run(Cmd(cc), dry_run=args.dry_run)
                    profile_extra_objects.append(str(obj_path))

            def _nanopb_link(
                out_path: Path, *, extra_cflags: Optional[List[str]] = None, with_asan: bool = True
            ) -> None:
                cc: List[str] = _nanopb_cc_base(with_asan=with_asan)
                for inc in args.target_include:
                    cc.append(f"-I{inc}")
                cc.extend(args.cc_arg)
                if extra_cflags:
                    cc.extend(extra_cflags)
                cc.extend(_nanopb_sources())
                if out_path == profile_bin and profile_extra_objects:
                    cc.extend(profile_extra_objects)

                if out_path == profile_bin:
                    if args.profile_extra_src and not args.profile_keep_target_lib:
                        pass
                    else:
                        cc.extend(target_libs_profile)
                else:
                    cc.extend(args.target_lib)
                cc.extend(["-o", str(out_path)])
                _run(Cmd(cc), dry_run=args.dry_run)

            if args.build:
                _nanopb_link(fuzzer_bin, with_asan=True)
            if args.build_profile:
                _nanopb_link(
                    profile_bin,
                    extra_cflags=["-fprofile-instr-generate", "-fcoverage-mapping"],
                    with_asan=False,
                )

    # 6) Fuzz
    if args.fuzz:
        artifacts_dir = out_dir / "artifacts"
        corpus_dir = seeds_dir if args.generate_seeds else (out_dir / "corpus")
        if not args.dry_run:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            corpus_dir.mkdir(parents=True, exist_ok=True)

        def _fuzz_argv_for_epoch(epoch_seconds: Optional[int]) -> List[str]:
            fuzz_argv: List[str] = [str(fuzzer_bin), str(corpus_dir)]
            if not args.detect_leaks:
                fuzz_argv.append("-detect_leaks=0")
            fuzz_argv.append(f"-artifact_prefix={artifacts_dir.as_posix()}/")
            if epoch_seconds and epoch_seconds > 0:
                fuzz_argv.append(f"-max_total_time={max(1, int(epoch_seconds))}")
            else:
                fuzz_argv.append(f"-runs={max(1, int(args.fuzz_runs))}")
            return fuzz_argv

        selected_graph = Path(args.constraint_graph).resolve() if args.constraint_graph else auto_constraint_graph
        candidate_corpus = seeds_dir if seeds_dir.exists() else (out_dir / "corpus")
        proto_include_dirs: List[Path] = [schema_proto.parent]
        nanopb_proto_inc = root / "external" / "nanopb" / "generator" / "proto"
        if nanopb_proto_inc.exists():
            proto_include_dirs.append(nanopb_proto_inc)
        reseed_base_argv: Optional[List[str]] = None
        latest_feedback_signal: Optional[Path] = None
        if args.schema_mode == "v2":
            reseed_base_argv = _build_seed_generator_argv(
                python=python,
                src_dir=src_dir,
                conditions=conditions,
                seeds_dir=corpus_dir,
                num_seeds=int(args.num_seeds),
                seed_max_len=int(args.seed_max_len),
                seed_rng=int(args.seed_rng),
                driver_meta_path=driver_meta_path,
                minimum_apis=args.minimum_apis,
                apipass_dir=args.apipass_dir,
                seed_constants_json=args.seed_constants_json,
                novelty_signal_path=None,
                selected_graph=selected_graph,
                schedule_mode=args.schedule_mode,
                misuse_mode=bool(args.misuse_mode),
            )

        env = os.environ.copy()
        if not args.detect_leaks:
            opts = env.get("ASAN_OPTIONS", "")
            if "detect_leaks=" not in opts:
                env["ASAN_OPTIONS"] = (opts + ":" if opts else "") + "detect_leaks=0"
        fuzz_duration = max(0, int(args.fuzz_duration))
        if fuzz_duration > 0:
            refresh_sec = max(1, int(args.feedback_refresh_sec))
            remaining = fuzz_duration
            epoch = 0
            while remaining > 0:
                epoch += 1
                epoch_seconds = min(remaining, refresh_sec)
                print(
                    "[Orch] fuzz epoch "
                    f"{epoch}: duration={epoch_seconds}s remaining_before={remaining}s"
                )
                _run(Cmd(_fuzz_argv_for_epoch(epoch_seconds), cwd=out_dir, env=env), dry_run=args.dry_run)
                remaining -= epoch_seconds
                if args.schema_mode == "v2":
                    epoch_causal: Optional[Path] = None
                    if args.verify_edges:
                        epoch_causal = _run_causal_edge_verifier(
                            src_dir=src_dir,
                            python=python,
                            dry_run=args.dry_run,
                            out_dir=out_dir,
                            fuzzer_bin=fuzzer_bin,
                            schema_proto=schema_proto,
                            conditions=conditions,
                            corpus_dir=candidate_corpus,
                            max_inputs=int(args.edge_verify_max_inputs),
                            max_ablations_per_input=int(args.edge_verify_max_ablations),
                            min_drop=int(args.edge_verify_min_drop),
                            timeout_sec=int(args.edge_verify_timeout_sec),
                            protoc_bin=str(args.edge_verify_protoc),
                            proto_include_dirs=proto_include_dirs,
                        )
                    latest_feedback_signal = _refresh_feedback_and_reseed(
                        out_dir=out_dir,
                        src_dir=src_dir,
                        python=python,
                        dry_run=args.dry_run,
                        causal_evidence_path=epoch_causal,
                        should_reseed=bool(args.feedback_reseed),
                        seed_argv=reseed_base_argv,
                    )
        else:
            _run(Cmd(_fuzz_argv_for_epoch(None), cwd=out_dir, env=env), dry_run=args.dry_run)
        if args.schema_mode == "v2":
            causal_evidence_path: Optional[Path] = None
            if args.verify_edges:
                causal_evidence_path = _run_causal_edge_verifier(
                    src_dir=src_dir,
                    python=python,
                    dry_run=args.dry_run,
                    out_dir=out_dir,
                    fuzzer_bin=fuzzer_bin,
                    schema_proto=schema_proto,
                    conditions=conditions,
                    corpus_dir=candidate_corpus,
                    max_inputs=int(args.edge_verify_max_inputs),
                    max_ablations_per_input=int(args.edge_verify_max_ablations),
                    min_drop=int(args.edge_verify_min_drop),
                    timeout_sec=int(args.edge_verify_timeout_sec),
                    protoc_bin=str(args.edge_verify_protoc),
                    proto_include_dirs=proto_include_dirs,
                )
                if causal_evidence_path:
                    print(f"[Orch] causal edge evidence: {causal_evidence_path}")
            final_signal = _refresh_feedback_and_reseed(
                out_dir=out_dir,
                src_dir=src_dir,
                python=python,
                dry_run=args.dry_run,
                causal_evidence_path=causal_evidence_path,
                should_reseed=bool(args.feedback_reseed),
                seed_argv=reseed_base_argv,
            )
            latest_feedback_signal = final_signal or latest_feedback_signal
            if not final_signal:
                stats_dir = out_dir / "api_stats"
                print(
                    "[Orch] feedback refresh skipped: no per-process stats found in "
                    f"{stats_dir} (expected api_stats.*.json)"
                )
        if args.classify_crashes:
            crashes_dir = out_dir / "crashes"
            classify_argv: List[str] = [
                python,
                str(src_dir / "crash_classifier.py"),
                "--workdir",
                str(out_dir),
                "--fuzzer-bin",
                str(fuzzer_bin),
                "--crash-dir",
                str(artifacts_dir),
                "--out-dir",
                str(crashes_dir),
                "--timeout-sec",
                str(max(1, int(args.crash_timeout_sec))),
            ]
            _run(Cmd(classify_argv), dry_run=args.dry_run)
            summary_path = crashes_dir / "summary.json"
            crash_metrics = _crash_classification_metrics(summary_path=summary_path)
            print(
                "[Orch] crash classification summary: "
                f"total={crash_metrics['total']} "
                f"genuine={crash_metrics['genuine']} "
                f"constraint_misuse={crash_metrics['constraint_misuse']}"
            )
            print(f"[Orch] crash classification output: {summary_path}")
            if args.learn_crash_constraints:
                learned_constraints_path = crashes_dir / "crash_learned_constraints.json"
                learner_argv: List[str] = [
                    python,
                    str(src_dir / "crash_constraint_learner.py"),
                    "--workdir",
                    str(out_dir),
                    "--fuzzer-bin",
                    str(fuzzer_bin),
                    "--proto",
                    str(schema_proto),
                    "--crash-dir",
                    str(crashes_dir / "genuine"),
                    "--out-json",
                    str(learned_constraints_path),
                    "--timeout-sec",
                    str(max(1, int(args.crash_timeout_sec))),
                    "--max-crashes",
                    str(max(0, int(args.crash_learn_max_crashes))),
                    "--max-byte-flips",
                    str(max(1, int(args.crash_learn_max_byte_flips))),
                    "--min-evidence",
                    str(max(1, int(args.crash_learn_min_evidence))),
                ]
                _run(Cmd(learner_argv), dry_run=args.dry_run)
                learning_metrics = _crash_learning_metrics(
                    learned_constraints_path=learned_constraints_path
                )
                print(
                    "[Orch] crash learning summary: "
                    f"input_crashes={learning_metrics['input_crashes']} "
                    f"reproducible={learning_metrics['reproducible']} "
                    f"events={learning_metrics['events']} "
                    f"constraints={learning_metrics['constraints']}"
                )
                print(f"[Orch] crash learning output: {learned_constraints_path}")
                crash_constants = _crash_constraints_to_seed_constants(
                    learned_constraints_path=learned_constraints_path
                )
                if crash_constants:
                    crash_constants_path = crashes_dir / "crash_seed_constants.json"
                    _write_json(crash_constants_path, crash_constants, dry_run=args.dry_run)
                    print(f"[Orch] crash-derived seed constants: {crash_constants_path}")
                    if args.schema_mode == "v2":
                        crash_seed_argv = _build_seed_generator_argv(
                            python=python,
                            src_dir=src_dir,
                            conditions=conditions,
                            seeds_dir=corpus_dir,
                            num_seeds=int(args.num_seeds),
                            seed_max_len=int(args.seed_max_len),
                            seed_rng=int(args.seed_rng),
                            driver_meta_path=driver_meta_path,
                            minimum_apis=args.minimum_apis,
                            apipass_dir=args.apipass_dir,
                            seed_constants_json=str(crash_constants_path),
                            novelty_signal_path=latest_feedback_signal,
                            selected_graph=selected_graph,
                            schedule_mode=args.schedule_mode,
                            misuse_mode=bool(args.misuse_mode),
                        )
                        _run(Cmd(crash_seed_argv), dry_run=args.dry_run)
                        print("[Orch] crash-driven reseed complete")
        elif args.learn_crash_constraints:
            print(
                "[Orch] crash learning skipped: requires crash classification "
                "(disable --no-classify-crashes or pass --classify-crashes)"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
