#!/usr/bin/env python3
"""
Build static constraint graphs from libErator apipass outputs.

Inputs (per library apipass dir):
  - conditions.json
  - apis_clang.json (optional but recommended)
  - apis_llvm.json (optional)

Outputs:
  - constraint_graph.json
  - constraint_graph.validation.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


_PARAM_RE = re.compile(r"^param_(\d+)$")
_STRUCT_RE = re.compile(r"%struct\.([^*\s=,]+)")
_TRAILING_DOT_NUM_RE = re.compile(r"\.\d+$")


@dataclass
class BuildResult:
    library: str
    apipass_dir: Path
    output_graph: Path
    output_validation: Path
    stats: Dict[str, Any]
    validation: Dict[str, Any]


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _is_param_key(key: str) -> bool:
    return bool(_PARAM_RE.match(key))


def _param_index(key: str) -> Optional[int]:
    m = _PARAM_RE.match(key)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _normalize_object_type(type_string: str) -> Optional[str]:
    if not type_string:
        return None
    m = _STRUCT_RE.search(type_string)
    if not m:
        return None
    name = m.group(1).strip()
    # Collapse debug-suffixed variants (e.g., aom_codec_iface.1320 -> aom_codec_iface)
    name = _TRAILING_DOT_NUM_RE.sub("", name)
    return name or None


def _extract_type_string(info: Dict[str, Any]) -> str:
    t = info.get("type_string") or info.get("type") or ""
    if t:
        return str(t)
    access = info.get("access_type_set", [])
    if isinstance(access, list):
        for a in access:
            if not isinstance(a, dict):
                continue
            tt = a.get("type_string") or a.get("type") or ""
            if tt:
                return str(tt)
    return ""


def _access_entries(info: Dict[str, Any]) -> List[Dict[str, Any]]:
    acc = info.get("access_type_set", [])
    return [a for a in acc if isinstance(a, dict)] if isinstance(acc, list) else []


def _signature_index(apis_clang_path: Path) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for row in _load_jsonl(apis_clang_path):
        fn = row.get("function_name")
        if isinstance(fn, str) and fn:
            idx[fn] = row
    return idx


def _conditions_entries(conditions: Any) -> List[Dict[str, Any]]:
    if isinstance(conditions, list):
        return [e for e in conditions if isinstance(e, dict)]
    if isinstance(conditions, dict):
        out: List[Dict[str, Any]] = []
        for fn, meta in conditions.items():
            if not isinstance(meta, dict):
                continue
            out.append({"function_name": fn, **meta})
        return out
    return []


def _infer_library_name(apipass_dir: Path) -> str:
    # expected: <repo>/analysis/<library>/work/apipass
    try:
        return apipass_dir.parents[1].name
    except Exception:
        return apipass_dir.name


def _build_graph_for_apipass(apipass_dir: Path, library: Optional[str] = None) -> BuildResult:
    conditions_path = apipass_dir / "conditions.json"
    apis_clang_path = apipass_dir / "apis_clang.json"
    apis_llvm_path = apipass_dir / "apis_llvm.json"

    if not conditions_path.exists():
        raise FileNotFoundError(f"missing conditions.json: {conditions_path}")

    lib = library or _infer_library_name(apipass_dir)

    conditions = _load_json(conditions_path)
    entries = _conditions_entries(conditions)
    sig_idx = _signature_index(apis_clang_path)

    nodes: List[Dict[str, Any]] = []
    intra: Dict[str, Any] = {}

    producers_by_type: Dict[str, Set[str]] = defaultdict(set)
    weak_producers_by_type: Dict[str, Set[str]] = defaultdict(set)
    consumers_by_type: Dict[str, Set[str]] = defaultdict(set)
    deleters_by_type: Dict[str, Set[str]] = defaultdict(set)

    errors: List[str] = []
    warnings: List[str] = []

    set_by_constraints = 0
    len_constraints = 0

    for entry in sorted(entries, key=lambda e: str(e.get("function_name") or e.get("functionName") or "")):
        fn = str(entry.get("function_name") or entry.get("functionName") or "").strip()
        if not fn:
            continue

        sig = sig_idx.get(fn, {})
        node = {
            "id": fn,
            "name": fn,
            "signature": {
                "return_type": (sig.get("return_info", {}) or {}).get("type_clang"),
                "arg_types": [a.get("type_clang") for a in (sig.get("arguments_info", []) or []) if isinstance(a, dict)],
            },
        }
        nodes.append(node)

        # Per-function constraints and role extraction.
        fn_intra = {
            "params": {},
            "return": {},
        }

        param_keys = [k for k in entry.keys() if isinstance(k, str) and _is_param_key(k)]
        param_keys.sort(key=lambda k: _param_index(k) if _param_index(k) is not None else 10**9)
        valid_param_set = set(param_keys)

        for pk in param_keys:
            p = entry.get(pk)
            if not isinstance(p, dict):
                continue
            pi = _param_index(pk)
            if pi is None:
                continue

            llvm_t = _extract_type_string(p)
            obj_t = _normalize_object_type(llvm_t)
            accesses = sorted({str(a.get("access") or "") for a in _access_entries(p) if a.get("access")})
            is_array = bool(p.get("is_array"))
            is_malloc_size = bool(p.get("is_malloc_size"))
            len_dep = str(p.get("len_depends_on") or "").strip()
            set_by = [str(x) for x in (p.get("set_by") or []) if str(x)]

            if set_by:
                set_by_constraints += len(set_by)
            if len_dep:
                len_constraints += 1

            # Validate param references.
            bad_set_by: List[str] = []
            for ref in set_by:
                if ref not in valid_param_set:
                    bad_set_by.append(ref)
            if bad_set_by:
                errors.append(f"{fn}:{pk} has invalid set_by refs: {bad_set_by}")

            bad_len_dep = None
            if len_dep and len_dep not in valid_param_set:
                bad_len_dep = len_dep
                errors.append(f"{fn}:{pk} has invalid len_depends_on ref: {len_dep}")

            fn_intra["params"][pk] = {
                "index": pi,
                "llvm_type": llvm_t,
                "object_type": obj_t,
                "is_array": is_array,
                "is_malloc_size": is_malloc_size,
                "set_by": set_by,
                "len_depends_on": len_dep,
                "accesses": accesses,
                "validation": {
                    "bad_set_by": bad_set_by,
                    "bad_len_depends_on": bad_len_dep,
                },
            }

            # Inter-role inference from params.
            if obj_t:
                if any(a in ("read", "write", "create", "delete") for a in accesses):
                    consumers_by_type[obj_t].add(fn)
                if "delete" in accesses:
                    deleters_by_type[obj_t].add(fn)

        ret = entry.get("return")
        if isinstance(ret, dict):
            ret_t = _extract_type_string(ret)
            ret_obj = _normalize_object_type(ret_t)
            ret_accesses = sorted({str(a.get("access") or "") for a in _access_entries(ret) if a.get("access")})
            fn_intra["return"] = {
                "llvm_type": ret_t,
                "object_type": ret_obj,
                "accesses": ret_accesses,
            }
            if ret_obj:
                if "create" in ret_accesses:
                    producers_by_type[ret_obj].add(fn)
                elif any(a in ("write", "read") for a in ret_accesses):
                    # weaker producer-like signal (e.g., pointer return with write/read only)
                    weak_producers_by_type[ret_obj].add(fn)
        else:
            fn_intra["return"] = {}

        intra[fn] = fn_intra

    # Build inter edges.
    edges: List[Dict[str, Any]] = []
    edge_keys: Set[Tuple[str, str, str, str]] = set()

    def add_edge(src: str, dst: str, rel: str, obj_t: str, hardness: str, confidence: float, reason: str) -> None:
        key = (src, dst, rel, obj_t)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append(
            {
                "src": src,
                "dst": dst,
                "relation": rel,
                "object_type": obj_t,
                "hardness": hardness,
                "confidence": round(confidence, 2),
                "source": "static",
                "reason": reason,
            }
        )

    all_types = sorted(set(list(producers_by_type.keys()) + list(weak_producers_by_type.keys()) + list(consumers_by_type.keys()) + list(deleters_by_type.keys())))

    for obj_t in all_types:
        producers = sorted(producers_by_type.get(obj_t, set()))
        weak_producers = sorted(weak_producers_by_type.get(obj_t, set()))
        consumers = sorted(consumers_by_type.get(obj_t, set()))
        deleters = sorted(deleters_by_type.get(obj_t, set()))

        if not producers and weak_producers and consumers:
            warnings.append(
                f"object_type={obj_t} has consumers but no explicit create producer; using weak producers"
            )

        # High-confidence producer -> consumer edges.
        for p in producers:
            for c in consumers:
                if p == c:
                    continue
                add_edge(
                    p,
                    c,
                    "producer_consumer",
                    obj_t,
                    "hard",
                    0.95,
                    "return(create) type matches consumer param type",
                )

        # Medium-confidence weak producer -> consumer edges.
        for p in weak_producers:
            for c in consumers:
                if p == c:
                    continue
                add_edge(
                    p,
                    c,
                    "producer_consumer",
                    obj_t,
                    "soft",
                    0.6,
                    "return(read/write) type matches consumer param type",
                )

        # Deleter -> consumer invalidation edges.
        for d in deleters:
            for c in consumers:
                if d == c:
                    continue
                add_edge(
                    d,
                    c,
                    "invalidates_before_use",
                    obj_t,
                    "hard",
                    0.9,
                    "param(delete) for object type",
                )

    # Build object catalog.
    object_catalog = []
    for obj_t in all_types:
        object_catalog.append(
            {
                "object_type": obj_t,
                "producers": sorted(producers_by_type.get(obj_t, set())),
                "weak_producers": sorted(weak_producers_by_type.get(obj_t, set())),
                "consumers": sorted(consumers_by_type.get(obj_t, set())),
                "deleters": sorted(deleters_by_type.get(obj_t, set())),
            }
        )

    node_ids = {n["id"] for n in nodes}
    bad_edge_refs = [e for e in edges if e["src"] not in node_ids or e["dst"] not in node_ids]
    if bad_edge_refs:
        errors.append(f"found {len(bad_edge_refs)} edges with unknown node refs")

    # Additional quality checks.
    missing_sig_count = sum(1 for n in nodes if not n["signature"].get("return_type") and not n["signature"].get("arg_types"))
    if missing_sig_count:
        warnings.append(f"{missing_sig_count} functions missing apis_clang signature rows")

    # Validate that every hard producer-consumer edge has a known object type and confidence >= 0.8.
    for e in edges:
        if e["hardness"] == "hard" and (not e["object_type"] or e["confidence"] < 0.8):
            errors.append(f"invalid hard edge quality: {e['src']}->{e['dst']} ({e['relation']})")

    stats = {
        "functions": len(nodes),
        "intra_set_by_constraints": set_by_constraints,
        "intra_len_constraints": len_constraints,
        "object_types": len(object_catalog),
        "explicit_producer_object_types": len([o for o in object_catalog if o["producers"]]),
        "inter_edges": len(edges),
        "hard_edges": len([e for e in edges if e["hardness"] == "hard"]),
        "soft_edges": len([e for e in edges if e["hardness"] == "soft"]),
    }

    validation = {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "bad_edge_refs": len(bad_edge_refs),
            "missing_signature_rows": missing_sig_count,
            "functions": len(nodes),
            "inter_edges": len(edges),
        },
    }

    graph = {
        "version": "0.1",
        "library": lib,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_files": {
            "conditions_json": str(conditions_path),
            "apis_clang_json": str(apis_clang_path),
            "apis_llvm_json": str(apis_llvm_path),
        },
        "nodes": nodes,
        "intra_constraints": intra,
        "inter_edges": sorted(edges, key=lambda e: (e["object_type"], e["src"], e["dst"], e["relation"])),
        "object_catalog": object_catalog,
        "stats": stats,
        "validation": validation,
    }

    out_graph = apipass_dir / "constraint_graph.json"
    out_validation = apipass_dir / "constraint_graph.validation.json"

    out_graph.write_text(json.dumps(graph, indent=2, sort_keys=False), encoding="utf-8")
    out_validation.write_text(json.dumps(validation, indent=2, sort_keys=False), encoding="utf-8")

    return BuildResult(
        library=lib,
        apipass_dir=apipass_dir,
        output_graph=out_graph,
        output_validation=out_validation,
        stats=stats,
        validation=validation,
    )


def _iter_apipass_dirs(analysis_root: Path) -> Iterable[Tuple[str, Path]]:
    if not analysis_root.exists():
        return
    for lib_dir in sorted(p for p in analysis_root.iterdir() if p.is_dir()):
        ap = lib_dir / "work" / "apipass"
        if ap.exists() and (ap / "conditions.json").exists():
            yield lib_dir.name, ap


def main() -> int:
    parser = argparse.ArgumentParser(description="Build static constraint graph(s) from apipass outputs")
    parser.add_argument("--apipass-dir", default=None, help="Path to one work/apipass directory")
    parser.add_argument("--library", default=None, help="Optional library name override (single mode)")
    parser.add_argument("--analysis-root", default=None, help="Path to analysis root (batch mode)")
    parser.add_argument("--all", action="store_true", help="Process all libraries under --analysis-root")
    parser.add_argument(
        "--summary-out",
        default=None,
        help="Optional JSON path for batch summary (default: <analysis-root>/constraint_graph_summary.json)",
    )
    args = parser.parse_args()

    if args.all:
        if not args.analysis_root:
            raise SystemExit("--all requires --analysis-root")
        analysis_root = Path(args.analysis_root).resolve()
        results: List[BuildResult] = []
        failures: List[Dict[str, str]] = []

        for lib, ap in _iter_apipass_dirs(analysis_root):
            try:
                res = _build_graph_for_apipass(ap, library=lib)
            except Exception as exc:  # noqa: BLE001
                failures.append({"library": lib, "apipass_dir": str(ap), "error": str(exc)})
                continue
            results.append(res)
            print(
                f"[constraint-graph] {lib}: functions={res.stats['functions']} edges={res.stats['inter_edges']} ok={res.validation['ok']}"
            )

        summary = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "analysis_root": str(analysis_root),
            "libraries_processed": len(results),
            "libraries_failed": len(failures),
            "results": [
                {
                    "library": r.library,
                    "apipass_dir": str(r.apipass_dir),
                    "graph": str(r.output_graph),
                    "validation": str(r.output_validation),
                    "ok": r.validation.get("ok", False),
                    "errors": len(r.validation.get("errors", [])),
                    "warnings": len(r.validation.get("warnings", [])),
                    "stats": r.stats,
                }
                for r in results
            ],
            "failures": failures,
        }

        summary_path = Path(args.summary_out).resolve() if args.summary_out else (analysis_root / "constraint_graph_summary.json")
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=False), encoding="utf-8")
        print(f"[constraint-graph] summary: {summary_path}")

        return 0 if not failures else 1

    if not args.apipass_dir:
        raise SystemExit("single mode requires --apipass-dir")

    apipass = Path(args.apipass_dir).resolve()
    res = _build_graph_for_apipass(apipass, library=args.library)
    print(
        f"[constraint-graph] {res.library}: functions={res.stats['functions']} edges={res.stats['inter_edges']} ok={res.validation['ok']}"
    )
    print(f"[constraint-graph] graph: {res.output_graph}")
    print(f"[constraint-graph] validation: {res.output_validation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
