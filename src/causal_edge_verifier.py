#!/usr/bin/env python3
"""
Approximate causal edge verification via action ablation.

For each corpus input:
  1) Run the original input and capture libFuzzer feature count (ft).
  2) Remove one action at a time (bounded), rerun, and compare ft.
  3) If ft drops, treat adjacent API edges around that removed action as supported.
     Otherwise, treat them as refuted evidence.

Output is a compact JSON file that feedback_aggregator.py can consume.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from utils import load_json, to_proto_field_name
except ImportError:
    sys.path.append(str(Path(__file__).resolve().parent))
    from utils import load_json, to_proto_field_name


PairKey = Tuple[str, str]


def _extract_ft(output: str) -> int:
    # libFuzzer progress lines: "... ft: 123 corp: ..."
    m = re.findall(r"\bft:\s*(\d+)\b", output)
    if m:
        try:
            return int(m[-1])
        except Exception:
            return 0
    # Fallback in case of alternate formatting.
    m2 = re.findall(r"\bcov:\s*(\d+)\b", output)
    if m2:
        try:
            return int(m2[-1])
        except Exception:
            return 0
    return 0


def _run_input_ft(
    *,
    fuzzer_bin: Path,
    payload: bytes,
    timeout_sec: int,
) -> int:
    with tempfile.TemporaryDirectory(prefix="plb_edge_verify_") as td:
        corpus = Path(td) / "corpus"
        corpus.mkdir(parents=True, exist_ok=True)
        inp = corpus / "seed"
        inp.write_bytes(payload)
        cmd = [
            str(fuzzer_bin),
            "-runs=1",
            "-print_final_stats=1",
            f"-artifact_prefix={td}/",
            str(corpus),
        ]
        env = os.environ.copy()
        opts = env.get("ASAN_OPTIONS", "")
        if "detect_leaks=" not in opts:
            env["ASAN_OPTIONS"] = (opts + ":" if opts else "") + "detect_leaks=0"
        env["PROTO_LIBERATOR_API_STATS"] = str(Path(td) / "api_stats.json")
        proc = subprocess.run(
            cmd,
            cwd=td,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=max(1, int(timeout_sec)),
            env=env,
            check=False,
        )
        return _extract_ft(proc.stdout or "")


def _compile_proto_py(
    proto: Path,
    *,
    protoc_bin: str,
    include_dirs: List[Path],
) -> Tuple[tempfile.TemporaryDirectory[str], Path, str]:
    td = tempfile.TemporaryDirectory(prefix="plb_proto_py_")
    out_dir = Path(td.name)
    stem_parts = [p for p in proto.stem.split(".") if p]
    if not stem_parts:
        stem_parts = [proto.stem]
    module_name = ".".join(stem_parts[:-1] + [f"{stem_parts[-1]}_pb2"])

    extra_proto_args: List[str] = []
    for inc in include_dirs:
        cand = inc / "nanopb.proto"
        if cand.exists():
            extra_proto_args.append(str(cand))
            break

    cmd = [
        protoc_bin,
        *[f"-I{inc}" for inc in include_dirs],
        f"--python_out={out_dir}",
        str(proto),
        *extra_proto_args,
    ]
    subprocess.check_call(cmd)
    return td, out_dir, module_name


def _import_module_from_dir(module_name: str, directory: Path):
    mod_rel = Path(*module_name.split(".")).with_suffix(".py")
    mod_path = directory / mod_rel
    spec = importlib.util.spec_from_file_location(module_name, mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import generated module: {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(directory))
    try:
        spec.loader.exec_module(mod)
        return mod
    finally:
        if sys.path and sys.path[0] == str(directory):
            sys.path.pop(0)


def _conditions_entries(conditions_path: Path) -> Iterable[dict]:
    raw = load_json(conditions_path)
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        return [x for x in raw.values() if isinstance(x, dict)]
    return []


def _build_field_to_api_map(conditions_path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for entry in _conditions_entries(conditions_path):
        fn = str(entry.get("function_name") or entry.get("functionName") or "").strip()
        if not fn:
            continue
        out[to_proto_field_name(fn)] = fn
    return out


def _find_action_field(msg_cls):
    desc = msg_cls.DESCRIPTOR
    for f in desc.fields:
        # repeated message field
        if bool(getattr(f, "is_repeated", False)) and f.type == f.TYPE_MESSAGE:
            action_desc = f.message_type
            if action_desc and action_desc.oneofs:
                return f.name, action_desc.oneofs[0].name
    return None, None


def _api_sequence_from_input(msg, *, action_field: str, action_oneof: str, field_to_api: Dict[str, str]) -> List[str]:
    seq: List[str] = []
    for action in getattr(msg, action_field):
        field = action.WhichOneof(action_oneof)
        if not field:
            continue
        seq.append(field_to_api.get(field, field))
    return seq


def _candidate_pairs_from_removed(seq: List[str], idx: int) -> List[PairKey]:
    out: List[PairKey] = []
    if idx > 0:
        out.append((seq[idx - 1], seq[idx]))
    if idx + 1 < len(seq):
        out.append((seq[idx], seq[idx + 1]))
    return out


def _edge_stats_row(src: str, dst: str, stat: dict) -> dict:
    supports = int(stat.get("supports", 0))
    refutes = int(stat.get("refutes", 0))
    total = supports + refutes
    drops = stat.get("drops", [])
    avg_drop = (sum(drops) / len(drops)) if drops else 0.0
    support_ratio = (float(supports) / float(total)) if total > 0 else 0.0
    return {
        "src": src,
        "dst": dst,
        "supports": supports,
        "refutes": refutes,
        "support_ratio": round(support_ratio, 6),
        "avg_drop": round(float(avg_drop), 6),
        "max_drop": int(max(drops) if drops else 0),
    }


def verify_edges(
    *,
    fuzzer_bin: Path,
    proto_path: Path,
    message_name: str,
    conditions_path: Path,
    corpus_paths: Iterable[Path],
    protoc_bin: str,
    timeout_sec: int,
    max_inputs: int,
    max_ablations_per_input: int,
    min_drop: int,
    proto_include_dirs: Optional[List[Path]] = None,
) -> dict:
    field_to_api = _build_field_to_api_map(conditions_path)
    if not field_to_api:
        raise RuntimeError(f"No APIs found in conditions file: {conditions_path}")

    include_dirs: List[Path] = [proto_path.parent]
    for inc in proto_include_dirs or []:
        if inc not in include_dirs:
            include_dirs.append(inc)
    tmp_dir_obj, tmp_dir_path, module_name = _compile_proto_py(
        proto_path,
        protoc_bin=protoc_bin,
        include_dirs=include_dirs,
    )
    try:
        pb2 = _import_module_from_dir(module_name, tmp_dir_path)
        msg_cls = getattr(pb2, message_name, None)
        if msg_cls is None:
            raise RuntimeError(f"Message '{message_name}' not found in generated module {module_name}")
        action_field, action_oneof = _find_action_field(msg_cls)
        if not action_field or not action_oneof:
            raise RuntimeError(f"Could not infer action field/oneof from message '{message_name}'")

        evidence: Dict[PairKey, dict] = {}
        files = [p for p in corpus_paths if p.is_file()]
        files = files[: max(1, int(max_inputs))]

        processed_inputs = 0
        processed_ablations = 0

        for path in files:
            data = path.read_bytes()
            msg = msg_cls()
            try:
                msg.ParseFromString(data)
            except Exception:
                continue
            seq = _api_sequence_from_input(
                msg,
                action_field=action_field,
                action_oneof=action_oneof,
                field_to_api=field_to_api,
            )
            if len(seq) < 2:
                continue

            baseline_ft = _run_input_ft(
                fuzzer_bin=fuzzer_bin,
                payload=data,
                timeout_sec=timeout_sec,
            )
            processed_inputs += 1

            ablation_budget = min(len(seq), max(1, int(max_ablations_per_input)))
            for idx in range(ablation_budget):
                candidate_pairs = _candidate_pairs_from_removed(seq, idx)
                if not candidate_pairs:
                    continue
                modified = msg_cls()
                modified.CopyFrom(msg)
                del getattr(modified, action_field)[idx]
                ablated_payload = modified.SerializeToString()
                ablated_ft = _run_input_ft(
                    fuzzer_bin=fuzzer_bin,
                    payload=ablated_payload,
                    timeout_sec=timeout_sec,
                )
                drop = int(max(0, baseline_ft - ablated_ft))
                supports = drop >= max(1, int(min_drop))
                processed_ablations += 1
                for pair in candidate_pairs:
                    stat = evidence.setdefault(pair, {"supports": 0, "refutes": 0, "drops": []})
                    if supports:
                        stat["supports"] += 1
                        stat["drops"].append(drop)
                    else:
                        stat["refutes"] += 1

        rows = [
            _edge_stats_row(src, dst, stat)
            for (src, dst), stat in sorted(evidence.items())
            if src and dst
        ]
        rows.sort(
            key=lambda r: (
                -float(r.get("support_ratio", 0.0)),
                -int(r.get("supports", 0)),
                -float(r.get("avg_drop", 0.0)),
                str(r.get("src")),
                str(r.get("dst")),
            )
        )
        return {
            "edges": rows,
            "meta": {
                "processed_inputs": int(processed_inputs),
                "processed_ablations": int(processed_ablations),
                "edge_count": len(rows),
                "max_inputs": int(max_inputs),
                "max_ablations_per_input": int(max_ablations_per_input),
                "min_drop": int(min_drop),
                "generated_at_unix": int(time.time()),
            },
        }
    finally:
        tmp_dir_obj.cleanup()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Causal edge verifier (ablation-based)")
    parser.add_argument("--fuzzer-bin", required=True, help="Path to libFuzzer binary")
    parser.add_argument("--proto", required=True, help="Path to generated .proto schema")
    parser.add_argument("--conditions", required=True, help="Path to conditions.json (API name mapping)")
    parser.add_argument("--corpus-dir", required=True, help="Corpus directory to sample inputs from")
    parser.add_argument("--output", required=True, help="Output JSON path for causal evidence")
    parser.add_argument("--message", default="FuzzInput", help="Top-level protobuf message name (default: FuzzInput)")
    parser.add_argument("--protoc-bin", default="protoc", help="protoc binary to compile python bindings")
    parser.add_argument(
        "--proto-include",
        action="append",
        default=[],
        help="Additional --proto_path include directory for protoc (repeatable)",
    )
    parser.add_argument("--timeout-sec", type=int, default=15, help="Timeout per verifier run (default: 15)")
    parser.add_argument("--max-inputs", type=int, default=32, help="Max corpus inputs to evaluate (default: 32)")
    parser.add_argument(
        "--max-ablations-per-input",
        type=int,
        default=4,
        help="Max removed-action trials per input (default: 4)",
    )
    parser.add_argument("--min-drop", type=int, default=1, help="Minimum ft drop to count as support (default: 1)")
    args = parser.parse_args(argv)

    fuzzer_bin = Path(args.fuzzer_bin).resolve()
    proto_path = Path(args.proto).resolve()
    conditions_path = Path(args.conditions).resolve()
    corpus_dir = Path(args.corpus_dir).resolve()
    output = Path(args.output).resolve()

    files = sorted(corpus_dir.glob("*"))
    result = verify_edges(
        fuzzer_bin=fuzzer_bin,
        proto_path=proto_path,
        message_name=str(args.message),
        conditions_path=conditions_path,
        corpus_paths=files,
        protoc_bin=str(args.protoc_bin),
        timeout_sec=max(1, int(args.timeout_sec)),
        max_inputs=max(1, int(args.max_inputs)),
        max_ablations_per_input=max(1, int(args.max_ablations_per_input)),
        min_drop=max(1, int(args.min_drop)),
        proto_include_dirs=[Path(x).resolve() for x in args.proto_include],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    meta = result.get("meta", {})
    print(
        f"[CausalVerifier] wrote {output} "
        f"(inputs={meta.get('processed_inputs', 0)} "
        f"ablations={meta.get('processed_ablations', 0)} "
        f"edges={meta.get('edge_count', 0)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
