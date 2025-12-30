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
    from type_mapper import TypeMapper, TypeContext
    from utils import load_json, to_proto_field_name
except ImportError:
    sys.path.append(str(Path(__file__).parent))
    from contracts import FIELD_ACTIONS, FIELD_ACTION_ONEOF, FIELD_GLOBAL_SEED
    from type_mapper import TypeMapper, TypeContext
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

def _encode_bool(field_number: int, value: bool) -> bytes:
    return _encode_key(field_number, WIRE_VARINT) + _encode_varint(1 if value else 0)


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

    def __init__(
        self,
        *,
        conditions_path: Path,
        rng_seed: int = 0,
        apipass_dir: Optional[Path] = None,
        minimum_apis: Optional[List[str]] = None,
        constants: Optional[Dict[str, Dict[str, int]]] = None,
    ):
        self.conditions_raw = load_json(conditions_path)
        self.entries = _conditions_entries(self.conditions_raw)
        self.mapper = TypeMapper()
        self.type_context = TypeContext.from_apipass_dir(apipass_dir or conditions_path.parent)
        self.managed_struct_names = self._infer_managed_struct_names()
        self.rng = random.Random(rng_seed)
        self.minimum_apis = set(str(x) for x in (minimum_apis or []) if str(x))
        self.constants = constants or {}

        self.func_entries: Dict[str, Dict[str, Any]] = {}
        for e in self.entries:
            n = _get_func_name(e)
            if n:
                self.func_entries[n] = e

        filtered = sorted(self.func_entries.keys())
        if self.minimum_apis:
            filtered = [fn for fn in filtered if fn in self.minimum_apis]
        # Skip unsupported vararg APIs by default.
        filtered = [fn for fn in filtered if fn not in self.type_context.vararg_functions]
        self.functions_sorted = filtered
        self.oneof_tag_by_function = {
            fn: idx + 1 for idx, fn in enumerate(self.functions_sorted)
        }

        self.creators = [fn for fn in self.functions_sorted if _is_creator(self.func_entries[fn])]
        self.destructors = [fn for fn in self.functions_sorted if _is_destructor_name(fn)]
        self.others = [fn for fn in self.functions_sorted if fn not in set(self.creators + self.destructors)]
        self.handle_consumers = [
            fn for fn in self.functions_sorted
            if self._function_has_handle_param(self.func_entries[fn])
        ]

    def _infer_managed_struct_names(self) -> set:
        """
        Keep seed field numbering aligned with proto_generator/wrapper_generator:
        treat returned struct-pointer types as managed handles (not struct blobs).
        """
        out: set = set()
        for entry in self.entries:
            fn = _get_func_name(entry) or ""
            if not fn:
                continue
            ret = entry.get("return")
            if not isinstance(ret, dict):
                continue
            llvm_t = str(ret.get("type_string") or ret.get("type") or "")
            if not llvm_t:
                access = ret.get("access_type_set", [])
                if isinstance(access, list) and access and isinstance(access[0], dict):
                    llvm_t = str(access[0].get("type_string") or access[0].get("type") or "")
            if not llvm_t:
                continue
            if self.mapper.map_llvm_to_proto(llvm_t) != "uint32":
                continue
            name = self.mapper.extract_struct_name(llvm_t)
            if name:
                out.add(name)
        return out

    def _infer_llvm_type(self, param_info: Dict[str, Any]) -> str:
        t = param_info.get("type_string") or param_info.get("type")
        if t:
            return str(t)
        access = param_info.get("access_type_set", [])
        if isinstance(access, list) and access:
            first = access[0]
            if isinstance(first, dict):
                return str(first.get("type_string") or first.get("type") or "")
        return ""

    def _function_has_handle_param(self, entry: Dict[str, Any]) -> bool:
        for k, v in entry.items():
            if not (isinstance(k, str) and k.startswith("param_") and isinstance(v, dict)):
                continue
            llvm_type = self._infer_llvm_type(v)
            if not llvm_type:
                continue
            proto_type = self.mapper.map_llvm_to_proto(llvm_type)
            is_array = bool(v.get("is_array"))
            access_set = v.get("access_type_set", [])
            has_set_by = bool(v.get("set_by", []))
            has_delete_access = any(isinstance(a, dict) and a.get("access") == "delete" for a in (access_set or []))
            is_struct_ptr = llvm_type.startswith("%struct.") or (
                llvm_type.endswith("*") and llvm_type.replace("const ", "").strip().startswith("%struct.")
            )

            if has_set_by or has_delete_access:
                if is_array or llvm_type.endswith("*") or llvm_type.startswith("%struct.") or proto_type in ("bytes", "uint32"):
                    return True
                continue
            if is_struct_ptr:
                struct_name = self.mapper.extract_struct_name(llvm_type)
                if struct_name and struct_name in self.managed_struct_names:
                    return True
                struct_size = self.type_context.struct_size_for(struct_name) if struct_name else None
                if not struct_size:
                    return True
                continue
            if is_array:
                continue
            if proto_type == "uint32":
                return True
        return False

    def _field_numbers_for_entry(self, entry: Dict[str, Any]) -> Dict[str, int]:
        """
        Mirror `proto_generator.py` field numbering so wire seeds hit the intended fields.
        """
        fields: Dict[str, int] = {}
        field_no = 1

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

        for param_idx, info in param_infos:
            param_name = f"param_{param_idx}"
            llvm_type = self._infer_llvm_type(info)
            proto_type = self.mapper.map_llvm_to_proto(llvm_type) if llvm_type else "bytes"
            is_array = bool(info.get("is_array"))
            access_set = info.get("access_type_set", [])
            has_set_by = bool(info.get("set_by", []))
            has_delete_access = any(isinstance(a, dict) and a.get("access") == "delete" for a in (access_set or []))
            is_struct_ptr = llvm_type.startswith("%struct.") or (
                llvm_type.endswith("*") and llvm_type.replace("const ", "").strip().startswith("%struct.")
            )

            # Mirror proto_generator.py ordering rules.
            if is_struct_ptr:
                struct_name = self.mapper.extract_struct_name(llvm_type)
                struct_size = self.type_context.struct_size_for(struct_name) if struct_name else None
                if struct_name and struct_name in self.managed_struct_names:
                    struct_size = None
                if has_set_by or has_delete_access:
                    fields[param_name + "_handle"] = field_no
                    field_no += 1
                elif struct_size:
                    fields[param_name + "_blob"] = field_no
                    field_no += 1
                else:
                    fields[param_name + "_handle"] = field_no
                    field_no += 1
            elif is_array:
                fields[param_name] = field_no
                field_no += 1
                fields[param_name + "_length"] = field_no
                field_no += 1
                fields[param_name + "_length_override"] = field_no
                field_no += 1
            elif has_set_by or has_delete_access:
                if llvm_type.endswith("*") or llvm_type.startswith("%struct.") or proto_type in ("bytes", "uint32"):
                    fields[param_name + "_handle"] = field_no
                    field_no += 1
                else:
                    fields[param_name] = field_no
                    field_no += 1
            elif proto_type == "uint32":
                fields[param_name + "_handle"] = field_no
                field_no += 1
            else:
                fields[param_name] = field_no
                field_no += 1

            # Nullable knob (mirrors proto_generator._is_nullable)
            if is_array or llvm_type.endswith("*") or llvm_type.startswith("%struct.") or proto_type == "uint32":
                fields[param_name + "_is_null"] = field_no
                field_no += 1

            if info.get("is_malloc_size"):
                fields[param_name + "_malloc_override"] = field_no
                field_no += 1

        # Contract violation knobs
        has_deps = any(
            isinstance(v, dict) and v.get("set_by")
            for k, v in entry.items()
            if isinstance(k, str) and k.startswith("param_")
        )
        if has_deps:
            fields["skip_dependency_check"] = field_no
            field_no += 1
        if "return" in entry:
            fields["allow_double_delete"] = field_no
            field_no += 1

        return fields

    def _default_payloads_for_function(self, func_name: str) -> List[bytes]:
        lowered = func_name.lower()
        if "json" in lowered or "parse" in lowered:
            return [b"{}", b"[]", b"null", b"true", b"0", b"\"a\"", b"{\"a\":1}"]
        return [b"", b"A", b"0", b"\x00"]

    def _encode_params_for_function(
        self,
        func_name: str,
        *,
        set_skip_dependency_check: bool = False,
        set_allow_double_delete: bool = False,
        set_first_is_null: bool = False,
    ) -> bytes:
        """
        Best-effort small params message.

        This tries to seed obvious string/bytes inputs for `param_0` when it's an array-like bytes field
        to improve early handle creation (e.g., cJSON_Parse).
        """
        entry = self.func_entries.get(func_name)
        if not entry:
            return b""

        field_nums = self._field_numbers_for_entry(entry)
        chunks: List[bytes] = []

        # Prefer populating:
        #  - first array/bytes payload
        #  - else first struct blob (to enable init-style APIs)
        #  - else first bytes pointer
        payloads = self._default_payloads_for_function(func_name)
        payload = payloads[self.rng.randrange(0, len(payloads))] if payloads else b"{}"

        chosen_param_field: Optional[str] = None
        chosen_len_override_field: Optional[str] = None
        chosen_len_dep_field: Optional[str] = None
        chosen_is_struct_blob = False

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

        for param_idx, info in param_infos:
            llvm_type = self._infer_llvm_type(info)
            proto_type = self.mapper.map_llvm_to_proto(llvm_type) if llvm_type else "bytes"
            is_array = bool(info.get("is_array"))
            access_set = info.get("access_type_set", [])
            has_set_by = bool(info.get("set_by", []))
            has_delete_access = any(isinstance(a, dict) and a.get("access") == "delete" for a in (access_set or []))
            is_struct_ptr = llvm_type.startswith("%struct.") or (
                llvm_type.endswith("*") and llvm_type.replace("const ", "").strip().startswith("%struct.")
            )
            struct_name = self.mapper.extract_struct_name(llvm_type) if is_struct_ptr else ""
            struct_size = self.type_context.struct_size_for(struct_name) if struct_name else None

            # Array params are best bytes targets (often "input" strings).
            if is_array:
                candidate = f"param_{param_idx}"
                if candidate in field_nums:
                    chosen_param_field = candidate
                    override = candidate + "_length_override"
                    if override in field_nums:
                        chosen_len_override_field = override
                    dep = str(info.get("len_depends_on") or "")
                    if dep and dep in field_nums:
                        chosen_len_dep_field = dep
                    break

            # Struct blob params are good for init/ctx-style APIs (if modeled as blob).
            if is_struct_ptr and struct_size and not (has_set_by or has_delete_access) and f"param_{param_idx}_blob" in field_nums:
                if struct_name and struct_name in self.managed_struct_names:
                    continue
                chosen_param_field = f"param_{param_idx}_blob"
                chosen_is_struct_blob = True
                break

            # Non-handle bytes fields (including i8*/void* etc).
            candidate = f"param_{param_idx}"
            if proto_type == "bytes" and candidate in field_nums:
                chosen_param_field = candidate
                break

        if chosen_param_field:
            if chosen_is_struct_blob:
                # For blobs, cap payload to a small prefix; harness will zero-fill the remainder.
                n = min(len(payload), 32)
                chunks.append(_encode_len_delim(field_nums[chosen_param_field], payload[:n]))
            else:
                chunks.append(_encode_len_delim(field_nums[chosen_param_field], payload))
                if chosen_len_override_field:
                    n = min(len(payload), 32)
                    chunks.append(_encode_uint32(field_nums[chosen_len_override_field], n))
                    if chosen_len_dep_field:
                        chunks.append(_encode_uint32(field_nums[chosen_len_dep_field], n))

        # Apply any per-function scalar constants overrides (best-effort).
        overrides = self.constants.get(func_name, {})
        if isinstance(overrides, dict):
            for k, v in overrides.items():
                if not isinstance(k, str):
                    continue
                if k in field_nums:
                    chunks.append(_encode_uint32(field_nums[k], int(v)))

        # Optional: flip a nullable knob for "NULL path" exploration.
        if set_first_is_null:
            for key in ("param_0_is_null", "param_1_is_null", "param_2_is_null"):
                if key in field_nums:
                    chunks.append(_encode_bool(field_nums[key], True))
                    break

        if set_skip_dependency_check and "skip_dependency_check" in field_nums:
            chunks.append(_encode_bool(field_nums["skip_dependency_check"], True))
        if set_allow_double_delete and "allow_double_delete" in field_nums:
            chunks.append(_encode_bool(field_nums["allow_double_delete"], True))

        return b"".join(chunks)

    def action_for_function(
        self,
        func_name: str,
        *,
        set_skip_dependency_check: bool = False,
        set_allow_double_delete: bool = False,
        set_first_is_null: bool = False,
    ) -> ActionVariant:
        tag = self.oneof_tag_by_function[func_name]
        params_bytes = self._encode_params_for_function(
            func_name,
            set_skip_dependency_check=set_skip_dependency_check,
            set_allow_double_delete=set_allow_double_delete,
            set_first_is_null=set_first_is_null,
        )
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

        default_creator = self.creators[0] if self.creators else None

        # Deterministic “smoke” seeds: one action per creator (up to num_seeds).
        for fn in self.creators:
            if len(sequences) >= num_seeds:
                break
            sequences.append([fn])

        # Minimal creator -> destructor seeds (exercise handle lifecycle).
        if default_creator:
            for fn in self.destructors:
                if len(sequences) >= num_seeds:
                    break
                sequences.append([default_creator, fn])

            # Minimal creator -> consumer seeds (exercise handle selection + deps).
            for fn in self.handle_consumers:
                if len(sequences) >= num_seeds:
                    break
                if fn == default_creator:
                    continue
                sequences.append([default_creator, fn])

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
    parser.add_argument("--minimum-apis", help="Optional apis_minimized.txt to filter functions")
    parser.add_argument("--apipass-dir", help="Optional apipass dir (defaults to parent of conditions.json)")
    parser.add_argument("--constants-json", help="Optional JSON mapping function -> {field_name: value}")
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

    constants = load_json(Path(args.constants_json)) if args.constants_json else None
    gen = SeedGenerator(
        conditions_path=Path(args.conditions),
        rng_seed=args.rng_seed,
        apipass_dir=Path(args.apipass_dir) if args.apipass_dir else None,
        minimum_apis=list(Path(args.minimum_apis).read_text().splitlines()) if args.minimum_apis else None,
        constants=constants if isinstance(constants, dict) else None,
    )
    sequences: List[List[str]] = []

    for d in args.driver:
        meta = load_json(Path(d))
        sequences.extend(gen.seed_sequences_from_driver(meta))

    if not sequences:
        sequences = gen.seed_sequences_default(args.num_seeds, args.max_len)

    for i, seq in enumerate(sequences[: args.num_seeds]):
        actions: List[ActionVariant] = []
        creators_set = set(gen.creators)
        destructors_set = set(gen.destructors)
        for j, fn in enumerate(seq):
            if fn not in gen.oneof_tag_by_function:
                continue
            is_first = j == 0
            is_creator = fn in creators_set
            actions.append(
                gen.action_for_function(
                    fn,
                    set_skip_dependency_check=(not is_first and not is_creator),
                    set_allow_double_delete=(fn in destructors_set and not is_first),
                    set_first_is_null=(fn in destructors_set and not is_first),
                )
            )
        data = gen.encode_fuzz_input(actions, global_seed=i)
        (out_dir / f"seed_{i:04d}.bin").write_bytes(data)

    print(f"[Seed-Gen] ✓ Wrote {min(len(sequences), args.num_seeds)} seeds to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
