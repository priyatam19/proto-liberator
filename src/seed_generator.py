#!/usr/bin/env python3
"""
Seed Generator - Generate v2 seed corpus for the dynamic-dispatch “super harness”.

Default mode is **wire-only** encoding (no protoc/python-protobuf required).
Optionally, a protobuf-python mode can be used if you already have `input_pb2.py`.
"""

from __future__ import annotations

import argparse
import importlib.util
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from contracts import FIELD_ACTIONS, FIELD_ACTION_ONEOF, FIELD_GLOBAL_SEED
    from type_mapper import TypeMapper
    from utils import load_json, to_proto_field_name
except ImportError:
    sys.path.append(str(Path(__file__).parent))
    from contracts import FIELD_ACTIONS, FIELD_ACTION_ONEOF, FIELD_GLOBAL_SEED
    from type_mapper import TypeMapper
    from utils import load_json, to_proto_field_name


WIRE_VARINT = 0
WIRE_LEN = 2


def _encode_varint(value: int) -> bytes:
    v = int(value) & 0xFFFFFFFFFFFFFFFF
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _encode_key(field_number: int, wire_type: int) -> bytes:
    return _encode_varint((field_number << 3) | wire_type)


def _encode_len_delim(field_number: int, payload: bytes) -> bytes:
    return _encode_key(field_number, WIRE_LEN) + _encode_varint(len(payload)) + payload


def _encode_uint32(field_number: int, value: int) -> bytes:
    return _encode_key(field_number, WIRE_VARINT) + _encode_varint(value & 0xFFFFFFFF)


def _conditions_entries(conditions: Any) -> List[Dict[str, Any]]:
    if isinstance(conditions, list):
        return [e for e in conditions if isinstance(e, dict)]
    if isinstance(conditions, dict):
        # Stub format {func_name: {...}} -> list of entries
        out: List[Dict[str, Any]] = []
        for name, meta in conditions.items():
            if isinstance(meta, dict):
                out.append({"function_name": name, **meta})
        return out
    raise TypeError(f"Unsupported conditions format: {type(conditions)}")


def _get_func_name(entry: Dict[str, Any]) -> Optional[str]:
    return entry.get("function_name") or entry.get("functionName")


def _is_destructor_name(name: str) -> bool:
    lowered = name.lower()
    return any(x in lowered for x in ("free", "delete", "destroy"))


def _is_creator(entry: Dict[str, Any]) -> bool:
    ret = entry.get("return")
    if not isinstance(ret, dict):
        return False
    access_set = ret.get("access_type_set", [])
    if isinstance(access_set, list):
        for a in access_set:
            if isinstance(a, dict) and a.get("access") == "create":
                return True
    return False


@dataclass(frozen=True)
class ActionVariant:
    function_name: str
    oneof_tag: int
    params_bytes: bytes


class SeedGenerator:
    """
    Generates `FuzzInput` binary seeds for schema v2:
      FuzzInput { optional uint32 global_seed = 1; repeated Action actions = 2; }
      Action { oneof action { <Func>_Params <field_name> = <tag>; ... } }
    """

    def __init__(self, *, conditions_path: Path, rng_seed: int = 0):
        self.conditions_raw = load_json(conditions_path)
        self.entries = _conditions_entries(self.conditions_raw)
        self.mapper = TypeMapper()
        self.rng = random.Random(rng_seed)

        self.func_entries: Dict[str, Dict[str, Any]] = {}
        for e in self.entries:
            n = _get_func_name(e)
            if n:
                self.func_entries[n] = e

        self.functions_sorted = sorted(self.func_entries.keys())
        self.oneof_tag_by_function = {
            fn: idx + 1 for idx, fn in enumerate(self.functions_sorted)
        }

        self.creators = [fn for fn in self.functions_sorted if _is_creator(self.func_entries[fn])]
        self.destructors = [fn for fn in self.functions_sorted if _is_destructor_name(fn)]
        self.others = [fn for fn in self.functions_sorted if fn not in set(self.creators + self.destructors)]

    def _encode_params_for_function(self, func_name: str) -> bytes:
        """
        Best-effort small params message.

        This tries to seed obvious string/bytes inputs for `param_0` when it's an array-like bytes field
        to improve early handle creation (e.g., cJSON_Parse).
        """
        entry = self.func_entries.get(func_name)
        if not entry:
            return b""

        # Deterministic param order: param_0, param_1, ...
        param_infos: List[Tuple[int, Dict[str, Any]]] = []
        for k, v in entry.items():
            if not (isinstance(k, str) and k.startswith("param_") and isinstance(v, dict)):
                continue
            try:
                idx = int(k.split("_", 1)[1])
            except Exception:
                continue
            param_infos.append((idx, v))
        param_infos.sort(key=lambda t: t[0])

        # Recompute field numbers exactly as the schema generator does (for param fields only).
        # We only seed a very small subset (bytes/array param_0), and omit knobs/length fields.
        field_no = 0
        chunks: List[bytes] = []
        for param_idx, info in param_infos:
            llvm_type = str(info.get("type_string") or info.get("type") or "")
            if not llvm_type:
                access = info.get("access_type_set", [])
                if isinstance(access, list) and access and isinstance(access[0], dict):
                    llvm_type = str(access[0].get("type_string") or access[0].get("type") or "")

            is_array = bool(info.get("is_array"))
            proto_type = self.mapper.map_llvm_to_proto(llvm_type) if llvm_type else "bytes"

            if is_array:
                field_no += 1  # bytes param_N
                if param_idx == 0:
                    # Seed a tiny JSON-ish string; safe default for many parsers.
                    payload = b"{}"
                    chunks.append(_encode_len_delim(field_no, payload))
                field_no += 1  # uint32 length
                field_no += 1  # uint32 length_override
            elif proto_type == "uint32":
                field_no += 1  # uint32 param_N_handle
            else:
                field_no += 1  # scalar or bytes
                if proto_type == "bytes" and param_idx == 0:
                    chunks.append(_encode_len_delim(field_no, b"{}"))

            # nullable knob added for arrays/pointers/handles in schema generator; we do not emit it.
            if is_array or llvm_type.endswith("*") or llvm_type.startswith("%struct.") or proto_type == "uint32":
                field_no += 1  # bool param_N_is_null

            if info.get("is_malloc_size"):
                field_no += 1  # uint32 malloc_override

        return b"".join(chunks)

    def action_for_function(self, func_name: str) -> ActionVariant:
        tag = self.oneof_tag_by_function[func_name]
        params_bytes = self._encode_params_for_function(func_name)
        return ActionVariant(function_name=func_name, oneof_tag=tag, params_bytes=params_bytes)

    def encode_action(self, variant: ActionVariant) -> bytes:
        # Action message contains one field (the chosen oneof variant) with an embedded Params message.
        return _encode_len_delim(variant.oneof_tag, variant.params_bytes)

    def encode_fuzz_input(self, actions: List[ActionVariant], *, global_seed: int = 0) -> bytes:
        out = bytearray()
        out += _encode_uint32(1, global_seed)
        for a in actions:
            out += _encode_len_delim(2, self.encode_action(a))
        return bytes(out)

    def seed_sequences_from_driver(self, driver_meta: Dict[str, Any]) -> List[List[str]]:
        raw_sequence = driver_meta.get("api_sequence", [])
        if isinstance(raw_sequence, list) and raw_sequence:
            return [[str(x) for x in raw_sequence if str(x) in self.func_entries]]
        multiset = driver_meta.get("api_multiset", {})
        if isinstance(multiset, dict) and multiset:
            seq: List[str] = []
            for fn in sorted(multiset.keys()):
                try:
                    count = int(multiset[fn])
                except Exception:
                    count = 0
                if fn in self.func_entries and count > 0:
                    seq.extend([fn] * count)
            return [seq] if seq else []
        return []

    def seed_sequences_default(self, num_seeds: int, max_len: int) -> List[List[str]]:
        sequences: List[List[str]] = []

        # Deterministic “smoke” seeds: one action per creator (up to num_seeds).
        for fn in self.creators:
            if len(sequences) >= num_seeds:
                break
            sequences.append([fn])

        # Random mixes (still deterministic under rng_seed).
        all_funcs = self.functions_sorted
        while len(sequences) < num_seeds and all_funcs:
            k = self.rng.randint(1, max_len)
            seq = [self.rng.choice(all_funcs) for _ in range(k)]
            sequences.append(seq)
        return sequences


def _load_proto_module(path: Path):
    # Optional mode: python-protobuf serialization using generated *_pb2.py.
    sys.path.append(str(path.parent))
    spec = importlib.util.spec_from_file_location("input_pb2", path)
    if not spec or not spec.loader:
        raise ImportError(f"Could not load protobuf module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate seed corpus for v2 harness")
    parser.add_argument("--conditions", required=True, help="Path to conditions.json")
    parser.add_argument("--output-dir", required=True, help="Directory to save seeds")
    parser.add_argument("--num-seeds", type=int, default=32, help="Number of seeds to generate")
    parser.add_argument("--max-len", type=int, default=16, help="Max actions per seed")
    parser.add_argument("--rng-seed", type=int, default=0, help="Deterministic RNG seed")
    parser.add_argument("--driver", action="append", default=[], help="Optional driver.meta (repeatable)")
    parser.add_argument(
        "--mode",
        choices=["wire", "protobuf"],
        default="wire",
        help="Seed encoding mode (default: wire-only, no protoc required)",
    )
    parser.add_argument(
        "--proto-module",
        help="(protobuf mode) Path to compiled python module (e.g., input_pb2.py)",
    )

    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "protobuf":
        if not args.proto_module:
            parser.error("--proto-module is required for --mode protobuf")
        proto_module = _load_proto_module(Path(args.proto_module))
        fuzz_input_cls = getattr(proto_module, "FuzzInput")
        print(f"[Seed-Gen] protobuf-mode writing to {out_dir}")
        for i in range(args.num_seeds):
            msg = fuzz_input_cls()
            msg.global_seed = i
            (out_dir / f"seed_{i}.bin").write_bytes(msg.SerializeToString())
        return 0

    gen = SeedGenerator(conditions_path=Path(args.conditions), rng_seed=args.rng_seed)
    sequences: List[List[str]] = []

    for d in args.driver:
        meta = load_json(Path(d))
        sequences.extend(gen.seed_sequences_from_driver(meta))

    if not sequences:
        sequences = gen.seed_sequences_default(args.num_seeds, args.max_len)

    for i, seq in enumerate(sequences[: args.num_seeds]):
        actions = [gen.action_for_function(fn) for fn in seq if fn in gen.oneof_tag_by_function]
        data = gen.encode_fuzz_input(actions, global_seed=i)
        (out_dir / f"seed_{i:04d}.bin").write_bytes(data)

    print(f"[Seed-Gen] ✓ Wrote {min(len(sequences), args.num_seeds)} seeds to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
