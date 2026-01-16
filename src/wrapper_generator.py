#!/usr/bin/env python3
"""
Wrapper Generator - Template-Based C Harness Generation

Consumes:
- Generated `.proto` (only for header naming / package prefix)
- libErator `driver.meta` (headers and, for v1, fixed API sequence)
- libErator `conditions.json` (function+param metadata; list of entries)
- libErator `apis_clang.json` (JSONL; function signatures; optional)

Generates:
- `harness.c` implementing nanopb decode and:
  - v1: fixed API sequence (driver.meta api_sequence/api_multiset)
  - v2: dynamic dispatch over repeated Action.oneof

This module must stay aligned with:
- v1: `docs/SCHEMA_CONTRACT.md`
- v2: `docs/SCHEMA_CONTRACT_V2.md`
"""

import argparse
import json
import os
import sys
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader

try:
    from contracts import MSG_FUZZ_INPUT, MSG_ACTION, FIELD_ACTIONS, FIELD_ACTION_ONEOF, DEFAULT_MAX_ACTIONS
    from utils import load_json, load_text_lines, to_proto_field_name
    from type_mapper import TypeMapper, TypeContext
except ImportError:
    sys.path.append(os.path.dirname(__file__))
    from contracts import MSG_FUZZ_INPUT, MSG_ACTION, FIELD_ACTIONS, FIELD_ACTION_ONEOF, DEFAULT_MAX_ACTIONS
    from utils import load_json, load_text_lines, to_proto_field_name
    from type_mapper import TypeMapper, TypeContext


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in load_text_lines(path):
        rows.append(json.loads(line))
    return rows


def index_conditions(conditions: Any) -> Dict[str, Dict[str, Any]]:
    """
    Normalize libErator conditions.json into {function_name -> entry}.

    libErator format (cJSON): a list of dicts with keys like:
      - function_name
      - param_0, param_1, ...
      - return
    Test stubs may use a simpler dict format; we support both.
    """
    if isinstance(conditions, dict):
        # Stub format: {func: {...}}
        return conditions

    if not isinstance(conditions, list):
        raise TypeError(f"Unsupported conditions format: {type(conditions)}")

    out: Dict[str, Dict[str, Any]] = {}
    for entry in conditions:
        if not isinstance(entry, dict):
            continue
        name = entry.get("function_name") or entry.get("functionName")
        if name:
            out[name] = entry
    return out


def infer_argc_from_conditions(entry: Dict[str, Any]) -> int:
    # Stub format: {"parameters": [{"name":..., "type":...}, ...]}
    params = entry.get("parameters")
    if isinstance(params, list):
        return len(params)

    idxs = []
    for key in entry.keys():
        if key.startswith("param_"):
            try:
                idxs.append(int(key.split("_", 1)[1]))
            except Exception:
                pass
    return (max(idxs) + 1) if idxs else 0


def build_signature_index(apis_path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """
    Build {function_name -> apis_clang row}.

    apis_clang.json is JSONL (one object per line).
    """
    if not apis_path:
        return {}
    if not apis_path.exists():
        return {}
    rows = load_jsonl(apis_path)
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        name = row.get("function_name")
        if name:
            out[name] = row
    return out


def normalize_c_type(type_str: str) -> str:
    if not type_str:
        return "int"
    sanitized = type_str.replace("__va_list_tag", "va_list").replace("__gnuc_va_list", "va_list")
    sanitized = sanitized.replace("va_list *", "va_list")
    return " ".join(sanitized.strip().split())


def is_char_ptr(c_type: str) -> bool:
    t = c_type.replace("const", "").strip()
    return ("char" in t) and ("*" in t) and ("**" not in t.replace(" ", ""))

def is_char_ptr_ptr(c_type: str) -> bool:
    # Matches: char **, const char **, char* const*, etc (best-effort).
    t = c_type.replace("const", "")
    t = "".join(t.split())
    return "char**" in t


def is_void_ptr(c_type: str) -> bool:
    t = c_type.replace("const", "").strip()
    return ("void" in t) and ("*" in t)


def is_pointer_type(c_type: str) -> bool:
    return "*" in c_type


def is_void_return(ret: str) -> bool:
    r = normalize_c_type(ret)
    return r == "void"


def is_integral_c_type(c_type: str) -> bool:
    t = normalize_c_type(c_type)
    t = t.replace("const", "").replace("volatile", "").strip()
    if "*" in t:
        return False
    if re.search(r"\b(bool|_Bool)\b", t):
        return False
    if re.search(r"\b(float|double)\b", t):
        return False
    if re.search(r"\b(size_t|ssize_t|ptrdiff_t|uintptr_t|intptr_t)\b", t):
        return True
    if re.search(r"\b(u?int(8|16|32|64)_t)\b", t):
        return True
    if re.search(r"\b(short|int|long|signed|unsigned)\b", t):
        return True
    return False


def is_size_like_c_type(c_type: str) -> bool:
    t = normalize_c_type(c_type)
    t = t.replace("const", "").replace("volatile", "").strip()
    if "*" in t:
        return False
    return bool(re.search(r"\b(size_t|ssize_t|ptrdiff_t|uintptr_t|intptr_t|u?int(8|16|32|64)_t)\b", t))


def infer_len_depends_on_index(args: List[Dict[str, Any]], index: int) -> Optional[int]:
    candidates: List[Dict[str, Any]] = []
    for arg in args:
        if arg.get("i") == index:
            continue
        param = arg.get("param") if isinstance(arg.get("param"), dict) else {}
        if param.get("kind") != "scalar":
            continue
        if arg.get("is_pointer"):
            continue
        c_type = str(arg.get("c_type") or "")
        if not is_integral_c_type(c_type):
            continue
        candidates.append(
            {
                "index": int(arg.get("i")),
                "is_const": "const" in c_type,
                "is_size": is_size_like_c_type(c_type),
            }
        )

    if not candidates:
        return None

    def adjacent(cands: List[Dict[str, Any]]) -> Optional[int]:
        for idx in (index + 1, index - 1):
            for cand in cands:
                if cand["index"] == idx:
                    return idx
        return None

    size_candidates = [c for c in candidates if c["is_size"]]
    adj = adjacent(size_candidates)
    if adj is not None:
        return adj
    if len(size_candidates) == 1:
        return size_candidates[0]["index"]

    const_candidates = [c for c in candidates if c["is_const"]]
    adj = adjacent(const_candidates)
    if adj is not None:
        return adj
    if len(const_candidates) == 1:
        return const_candidates[0]["index"]

    adj = adjacent(candidates)
    if adj is not None:
        return adj

    best = None
    best_dist = None
    for ci in candidates:
        idx = ci["index"]
        dist = abs(idx - index)
        if dist > 2:
            continue
        if best is None or dist < best_dist or (dist == best_dist and idx > index):
            best = idx
            best_dist = dist
    return best


def apply_len_depends_on_heuristics(args: List[Dict[str, Any]]) -> None:
    for arg in args:
        param = arg.get("param")
        if not isinstance(param, dict):
            continue
        if param.get("kind") not in ("bytes", "bytes_array"):
            continue
        if not arg.get("is_pointer"):
            continue
        if param.get("len_depends_on_index") is not None:
            continue
        idx = int(arg.get("i"))
        inferred = infer_len_depends_on_index(args, idx)
        if inferred is None or inferred == idx:
            continue
        if inferred < 0 or inferred >= len(args):
            continue
        param["len_depends_on_index"] = inferred


def conditions_return_is_handle(entry: Dict[str, Any], mapper: TypeMapper, *, ret_c_type: Optional[str] = None) -> bool:
    ret = entry.get("return")
    if not isinstance(ret, dict):
        return False
    access_set = ret.get("access_type_set", [])
    if isinstance(access_set, list):
        for a in access_set:
            if not isinstance(a, dict):
                continue
            access = a.get("access")
            llvm_t = a.get("type_string") or ret.get("type_string") or ""
            # Only treat struct-pointer returns as handles by default.
            if mapper.map_llvm_to_proto(str(llvm_t)) == "uint32":
                return True
            # Avoid treating owned i8*/void* as handles (e.g., error strings / print buffers).
            if access in ("create", "delete") and "%struct." in str(llvm_t):
                return True
    llvm_t = ret.get("type_string") or ""
    if mapper.map_llvm_to_proto(str(llvm_t)) == "uint32":
        return True

    # Heuristic: allocator-like APIs returning pointers should be tracked as handles even if conditions.json
    # doesn't include access_type_set for the return (some libraries omit it for malloc-like wrappers).
    fn = str(entry.get("function_name") or entry.get("functionName") or "")
    if ret_c_type and "*" in ret_c_type and "%struct." in llvm_t and fn:
        lowered = fn.lower()
        if any(x in lowered for x in ("malloc", "realloc", "calloc", "alloc", "new", "create")):
            return True
    return False


def function_has_deps(entry: Dict[str, Any]) -> bool:
    for k, v in entry.items():
        if not k.startswith("param_") or not isinstance(v, dict):
            continue
        set_by = v.get("set_by", [])
        if set_by:
            return True
    return False


def is_destructor_name(func_name: str) -> bool:
    lowered = func_name.lower()
    return any(x in lowered for x in ("delete", "destroy", "free"))


def classify_param(
    entry: Dict[str, Any],
    param_index: int,
    mapper: TypeMapper,
    *,
    context: Optional[TypeContext] = None,
    managed_struct_names: Optional[set] = None,
) -> Dict[str, Any]:
    key = f"param_{param_index}"
    info = entry.get(key)
    if not isinstance(info, dict):
        return {"kind": "scalar", "field": key, "index": param_index, "has_is_null": False}

    llvm_type = str(info.get("type_string") or info.get("type") or "")
    if not llvm_type:
        access = info.get("access_type_set", [])
        if isinstance(access, list) and access and isinstance(access[0], dict):
            llvm_type = str(access[0].get("type_string") or access[0].get("type") or "")
    if "__va_list_tag" in llvm_type or "__gnuc_va_list" in llvm_type or "va_list" in llvm_type:
        return {
            "kind": "va_list",
            "field": key,
            "index": param_index,
            "has_is_null": False,
        }
    is_array = bool(info.get("is_array"))
    access_set = info.get("access_type_set", [])
    has_set_by = bool(info.get("set_by", []))
    has_delete_access = any(isinstance(a, dict) and a.get("access") == "delete" for a in (access_set or []))
    len_depends_on = str(info.get("len_depends_on") or "")
    len_depends_on_index: Optional[int] = None
    if len_depends_on.startswith("param_"):
        try:
            len_depends_on_index = int(len_depends_on.split("_", 1)[1])
        except Exception:
            len_depends_on_index = None
    proto_type = mapper.map_llvm_to_proto(llvm_type) if llvm_type else "bytes"
    is_ptr_like = bool(
        is_array
        or llvm_type.endswith("*")
        or llvm_type.startswith("%struct.")
        or proto_type in ("bytes", "uint32")
    )
    classification = mapper.classify_llvm_type(
        llvm_type,
        context=context,
        is_array=is_array and not (llvm_type.startswith("%struct.") or llvm_type.endswith("*") and llvm_type.replace("const ", "").strip().startswith("%struct.")),
    )

    is_struct_ptr = llvm_type.startswith("%struct.") or (
        llvm_type.endswith("*") and llvm_type.replace("const ", "").strip().startswith("%struct.")
    )

    # Struct pointers: struct blob when layout is known and not dependency-handle; else handle.
    if is_struct_ptr:
        struct_size = classification.struct_size
        struct_name = classification.struct_name
        if managed_struct_names and struct_name and struct_name in managed_struct_names:
            struct_size = None
        if has_set_by or has_delete_access or proto_type == "uint32" and struct_size is None:
            return {
                "kind": "handle",
                "field": f"{key}_handle",
                "index": param_index,
                "has_is_null": True,
                "type_key": mapper.type_key(llvm_type),
                "len_depends_on": len_depends_on,
                "len_depends_on_index": len_depends_on_index,
            }
        if struct_size:
            return {
                "kind": "struct_blob",
                "field": f"{key}_blob",
                "index": param_index,
                "has_is_null": True,
                "type_key": mapper.type_key(llvm_type),
                "struct_name": struct_name,
                "struct_size": int(struct_size),
                "len_depends_on": len_depends_on,
                "len_depends_on_index": len_depends_on_index,
            }
        return {
            "kind": "handle",
            "field": f"{key}_handle",
            "index": param_index,
            "has_is_null": True,
            "type_key": mapper.type_key(llvm_type),
            "len_depends_on": len_depends_on,
            "len_depends_on_index": len_depends_on_index,
        }

    if classification.kind == "bytes_array":
        return {
            "kind": "bytes_array",
            "field": key,
            "index": param_index,
            "has_is_null": True,
            "has_length": True,
            "type_key": mapper.type_key(llvm_type),
            "len_depends_on": len_depends_on,
            "len_depends_on_index": len_depends_on_index,
        }

    if has_set_by or has_delete_access:
        if is_ptr_like:
            return {
                "kind": "handle",
                "field": f"{key}_handle",
                "index": param_index,
                "has_is_null": True,
                "type_key": mapper.type_key(llvm_type),
                "len_depends_on": len_depends_on,
                "len_depends_on_index": len_depends_on_index,
            }
        return {
            "kind": "scalar",
            "field": key,
            "index": param_index,
            "has_is_null": False,
            "type_key": mapper.type_key(llvm_type),
            "len_depends_on": len_depends_on,
            "len_depends_on_index": len_depends_on_index,
        }

    if proto_type == "uint32":
        return {
            "kind": "handle",
            "field": f"{key}_handle",
            "index": param_index,
            "has_is_null": True,
            "type_key": mapper.type_key(llvm_type),
            "len_depends_on": len_depends_on,
            "len_depends_on_index": len_depends_on_index,
        }

    if proto_type == "bytes":
        return {
            "kind": "bytes",
            "field": key,
            "index": param_index,
            "has_is_null": True,
            "type_key": mapper.type_key(llvm_type),
            "len_depends_on": len_depends_on,
            "len_depends_on_index": len_depends_on_index,
        }

    return {
        "kind": "scalar",
        "field": key,
        "index": param_index,
        "has_is_null": False,
        "type_key": mapper.type_key(llvm_type),
        "len_depends_on": len_depends_on,
        "len_depends_on_index": len_depends_on_index,
    }


def get_type_with_const(info: Dict[str, Any], default: str = "int") -> str:
    raw_type = str(info.get("type_clang") or default)
    t = normalize_c_type(raw_type)
    consts = info.get("const")
    if isinstance(consts, list) and len(consts) > 0 and consts[0]:
        return f"const {t}"
    return t


class WrapperGenerator:
    """
    Generate C fuzzing harness from protobuf schema + libErator metadata.
    Uses Jinja2 templates.
    """

    def __init__(
        self,
        proto_path: Path,
        driver_meta_path: Path,
        conditions_path: Path,
        *,
        apis_path: Optional[Path] = None,
        minimum_apis: Optional[List[str]] = None,
        package_name: str = "",
        schema_mode: str = "v1",
        mutation_mode: str = "nanopb",
        max_actions: int = DEFAULT_MAX_ACTIONS,
        emi_config: Optional[Dict] = None,
        extra_headers: Optional[List[str]] = None,
        apipass_dir: Optional[Path] = None,
        harness_style: str = "strict",
    ):
        self.proto_path = proto_path
        self.driver_meta = load_json(driver_meta_path)
        self.conditions_raw = load_json(conditions_path)
        self.conditions = index_conditions(self.conditions_raw)
        self.api_sigs = build_signature_index(apis_path)
        self.mapper = TypeMapper()
        self.type_context = TypeContext.from_apipass_dir(apipass_dir or conditions_path.parent)
        self.minimum_apis = set(str(x) for x in (minimum_apis or []) if str(x).strip())
        self.managed_struct_names = self._infer_managed_struct_names()
        self.package_name = package_name
        self.schema_mode = schema_mode
        self.mutation_mode = mutation_mode
        self.max_actions = int(max_actions)
        self.emi_config = emi_config or {}
        self.extra_headers = extra_headers or []
        self.harness_style = harness_style

        if self.mutation_mode == "lpm" and self.schema_mode != "v2":
            raise ValueError("mutation_mode=lpm currently requires schema_mode=v2")
        if self.harness_style not in ("strict", "simple"):
            raise ValueError(f"Unsupported harness style: {self.harness_style}")

        template_dir = Path(__file__).parent.parent / "templates"
        self.env = Environment(loader=FileSystemLoader(str(template_dir)))
        
        if self.mutation_mode == "lpm":
            template_name = "wrapper_lpm.cc.j2"
        else:
            template_name = "wrapper_v2.c.j2" if self.schema_mode == "v2" else "wrapper.c.j2"
            
        self.template = self.env.get_template(template_name)

    def generate(self, output_path: Path):
        print(f"[Wrapper-Gen] Generating fuzzing harness...")
        context = self._prepare_context()
        wrapper_code = self.template.render(context)
        with open(output_path, "w") as f:
            f.write(wrapper_code)
        print(f"[Wrapper-Gen] ✓ Generated: {output_path}")

    def _infer_managed_struct_names(self) -> set:
        """
        Heuristic: treat struct pointer types returned by any API as "managed objects"
        and represent them as handles (not struct blobs).
        """
        out: set = set()
        for _, entry in self.conditions.items():
            if not isinstance(entry, dict):
                continue
            if not conditions_return_is_handle(entry, self.mapper):
                continue
            ret = entry.get("return")
            if not isinstance(ret, dict):
                continue
            llvm_t = str(ret.get("type_string") or ret.get("type") or "")
            if not llvm_t:
                access = ret.get("access_type_set", [])
                if isinstance(access, list) and access and isinstance(access[0], dict):
                    llvm_t = str(access[0].get("type_string") or access[0].get("type") or "")
            name = self.mapper.extract_struct_name(llvm_t)
            if name:
                out.add(name)
        return out

    def _prepare_context(self) -> Dict:
        if self.schema_mode == "v2":
            return self._prepare_context_v2()
        return self._prepare_context_v1()

    def _prepare_context_v1(self) -> Dict:
        """
        v1: fixed-sequence driver. Contract: docs/SCHEMA_CONTRACT.md
        """
        headers = self.driver_meta.get("headers", []) or []
        if not isinstance(headers, list):
            headers = []
        headers.extend(self.extra_headers)
        # Stable de-dupe, preserve order.
        seen = set()
        headers = [h for h in headers if isinstance(h, str) and not (h in seen or seen.add(h))]

        raw_sequence = self.driver_meta.get("api_sequence", [])
        if not raw_sequence:
            multiset = self.driver_meta.get("api_multiset", {})
            if multiset:
                for func_name in sorted(multiset.keys()):
                    count = multiset[func_name]
                    raw_sequence.extend([func_name] * count)
            else:
                print(
                    "[Wrapper-Gen] Warning: No 'api_sequence' or 'api_multiset' in driver.meta. Using all functions."
                )
                raw_sequence = sorted(self.conditions.keys())

        prefix = f"{self.package_name}_" if self.package_name else ""
        fuzz_input_type = f"{prefix}{MSG_FUZZ_INPUT}"

        api_sequence = []
        unique_apis_set = set()
        unique_apis = []

        for func_name in raw_sequence:
            if func_name not in self.conditions:
                print(f"[Wrapper-Gen] Warning: Function {func_name} in sequence but not in conditions.json")
                continue
            if self.minimum_apis and func_name not in self.minimum_apis:
                continue

            entry = self.conditions[func_name]
            sig = self.api_sigs.get(func_name)

            arg_types: List[str] = []
            ret_type = "void"
            if sig:
                ret_info = sig.get("return_info") or {}
                ret_type = normalize_c_type(str(ret_info.get("type_clang") or "void"))
                args_info = sig.get("arguments_info")
                if isinstance(args_info, list):
                    arg_types = [normalize_c_type(str(a.get("type_clang") or "int")) for a in args_info]

            argc = len(arg_types) if arg_types else infer_argc_from_conditions(entry)
            if not arg_types:
                params = entry.get("parameters")
                if isinstance(params, list):
                    arg_types = [normalize_c_type(str(p.get("type") or "int")) for p in params][:argc]
                if len(arg_types) < argc:
                    arg_types.extend(["int"] * (argc - len(arg_types)))

            args: List[Dict[str, Any]] = []
            for i in range(argc):
                param_desc = classify_param(
                    entry,
                    i,
                    self.mapper,
                    context=self.type_context,
                    managed_struct_names=self.managed_struct_names,
                )
                dep = param_desc.get("len_depends_on_index") if isinstance(param_desc, dict) else None
                if isinstance(dep, int) and dep >= argc:
                    param_desc["len_depends_on_index"] = None
                c_type = arg_types[i] if i < len(arg_types) else "int"
                args.append(
                    {
                        "i": i,
                        "c_type": c_type,
                        "param": param_desc,
                        "is_char_ptr": is_char_ptr(c_type),
                        "is_char_ptr_ptr": is_char_ptr_ptr(c_type),
                        "is_void_ptr": is_void_ptr(c_type),
                        "is_pointer": is_pointer_type(c_type),
                    }
                )

            apply_len_depends_on_heuristics(args)

            returns_handle = conditions_return_is_handle(entry, self.mapper, ret_c_type=ret_type)

            call = {
                "name": func_name,
                "field_name": to_proto_field_name(func_name),
                "struct_type": f"{prefix}{func_name}_Params",
                "argc": argc,
                "args": args,
                "return_type": ret_type,
                "return_is_void": is_void_return(ret_type),
                "returns_handle": returns_handle,
                "has_skip_dependency_check": function_has_deps(entry),
                "has_allow_double_delete": "return" in entry,
                "is_destructor": is_destructor_name(func_name),
            }

            api_sequence.append(call)

            if func_name not in unique_apis_set:
                unique_apis_set.add(func_name)
                unique_apis.append(call)

        return {
            "headers": headers,
            "proto_header": self.proto_path.stem + ".pb.h",
            "fuzz_input_type": fuzz_input_type,
            "unique_apis": unique_apis,
            "api_sequence": api_sequence,
            "harness_style": self.harness_style,
        }

    def _prepare_context_v2(self) -> Dict:
        """
        v2: dynamic dispatch “super harness”. Contract: docs/SCHEMA_CONTRACT_V2.md
        """
        headers = self.driver_meta.get("headers", []) or []
        if not isinstance(headers, list):
            headers = []
        headers.extend(self.extra_headers)
        # Stable de-dupe, preserve order.
        seen = set()
        headers = [h for h in headers if isinstance(h, str) and not (h in seen or seen.add(h))]

        if self.mutation_mode == "lpm":
            # C++ Namespace logic
            # We don't bake the package name into the type name here, 
            # because the template handles the namespace.
            prefix = "" 
            fuzz_input_type = MSG_FUZZ_INPUT
            action_type = MSG_ACTION
        else:
            # Nanopb C struct logic
            prefix = f"{self.package_name}_" if self.package_name else ""
            fuzz_input_type = f"{prefix}{MSG_FUZZ_INPUT}"
            action_type = f"{prefix}{MSG_ACTION}"

        sorted_funcs = sorted(self.conditions.keys())
        if self.minimum_apis:
            sorted_funcs = [fn for fn in sorted_funcs if fn in self.minimum_apis]

        apis = []
        handle_type_keys: List[str] = []
        for func_name in sorted_funcs:
            entry = self.conditions[func_name]
            sig = self.api_sigs.get(func_name)

            arg_types: List[str] = []
            ret_type = "void"
            if sig:
                ret_info = sig.get("return_info") or {}
                ret_type = get_type_with_const(ret_info, default="void")
                args_info = sig.get("arguments_info")
                if isinstance(args_info, list):
                    arg_types = [get_type_with_const(a, default="int") for a in args_info]

            argc = len(arg_types) if arg_types else infer_argc_from_conditions(entry)
            if not arg_types:
                params = entry.get("parameters")
                if isinstance(params, list):
                    arg_types = [normalize_c_type(str(p.get("type") or "int")) for p in params][:argc]
                if len(arg_types) < argc:
                    arg_types.extend(["int"] * (argc - len(arg_types)))

            args: List[Dict[str, Any]] = []
            for i in range(argc):
                param_desc = classify_param(
                    entry,
                    i,
                    self.mapper,
                    context=self.type_context,
                    managed_struct_names=self.managed_struct_names,
                )
                dep = param_desc.get("len_depends_on_index") if isinstance(param_desc, dict) else None
                if isinstance(dep, int) and dep >= argc:
                    param_desc["len_depends_on_index"] = None
                c_type = arg_types[i] if i < len(arg_types) else "int"
                if param_desc.get("kind") == "handle":
                    handle_type_keys.append(str(param_desc.get("type_key") or ""))
                args.append(
                    {
                        "i": i,
                        "c_type": c_type,
                        "param": param_desc,
                        "is_char_ptr": is_char_ptr(c_type),
                        "is_char_ptr_ptr": is_char_ptr_ptr(c_type),
                        "is_void_ptr": is_void_ptr(c_type),
                        "is_pointer": is_pointer_type(c_type),
                    }
                )

            apply_len_depends_on_heuristics(args)

            returns_handle = conditions_return_is_handle(entry, self.mapper, ret_c_type=ret_type)
            return_type_key = self.mapper.type_key(str(entry.get("return", {}).get("type_string") or "")) if returns_handle else ""
            if returns_handle and return_type_key:
                handle_type_keys.append(return_type_key)
            field_name = to_proto_field_name(func_name)
            unsupported_vararg = self.mapper.is_unsupported_vararg(func_name, context=self.type_context)

            apis.append(
                {
                    "name": func_name,
                    "field_name": field_name,
                    "struct_type": f"{prefix}{func_name}_Params",
                    "oneof_tag": f"{action_type}_{field_name}_tag",
                    "args": args,
                    "return_type": ret_type,
                    "return_is_void": is_void_return(ret_type),
                    "returns_handle": returns_handle,
                    "return_type_key": return_type_key,
                    "has_skip_dependency_check": function_has_deps(entry),
                    "has_allow_double_delete": "return" in entry,
                    "is_destructor": is_destructor_name(func_name),
                    "unsupported_vararg": unsupported_vararg,
                }
            )

        # Stable handle-type list for typed-handle tables.
        uniq: List[str] = []
        seen = set()
        for k in handle_type_keys:
            if not k or k in seen:
                continue
            seen.add(k)
            uniq.append(k)
        if not uniq:
            uniq = ["default"]

        def _ident(s: str) -> str:
            out = re.sub(r"[^A-Za-z0-9_]+", "_", s)
            if not out or out[0].isdigit():
                out = "_" + out
            return out

        handle_types = [{"id": i, "key": k, "ident": _ident(k)} for i, k in enumerate(uniq)]
        key_to_id = {h["key"]: h["id"] for h in handle_types}

        for api in apis:
            for a in api.get("args", []):
                p = a.get("param") or {}
                if isinstance(p, dict) and p.get("kind") == "handle":
                    p["type_id"] = key_to_id.get(p.get("type_key", ""), 0)
            if api.get("returns_handle"):
                api["return_type_id"] = key_to_id.get(api.get("return_type_key", ""), 0)

        return {
            "headers": headers,
            "proto_header": self.proto_path.stem + ".pb.h",
            "package_name": self.package_name,
            "fuzz_input_type": fuzz_input_type,
            "actions_field": FIELD_ACTIONS,
            "action_type": action_type,
            "action_oneof_field": FIELD_ACTION_ONEOF,
            "max_actions": self.max_actions,
            "apis": apis,
            "handle_types": handle_types,
            "harness_style": self.harness_style,
        }


def main():
    parser = argparse.ArgumentParser(description="Template-Based Wrapper Generator for Proto-libErator")

    parser.add_argument("--proto", required=True, help="Path to generated .proto file")
    parser.add_argument("--driver", required=True, help="Path to libErator driver.meta file")
    parser.add_argument("--conditions", required=True, help="Path to conditions.json")
    parser.add_argument("--apis", help="Path to apis_clang.json (JSONL) for accurate arg counts")
    parser.add_argument("--minimum-apis", help="Optional apis_minimized.txt (one function per line) to restrict harness APIs")
    parser.add_argument("--output", required=True, help="Output C harness file path")
    parser.add_argument("--package", default="", help="Protobuf package name prefix")
    parser.add_argument("--schema-mode", choices=["v1", "v2"], default="v1", help="Schema contract version")
    parser.add_argument("--mutation-mode", choices=["nanopb", "lpm"], default="nanopb", help="Mutation engine")
    parser.add_argument("--max-actions", type=int, default=DEFAULT_MAX_ACTIONS, help="(v2) Max actions to execute")
    parser.add_argument(
        "--apipass-dir",
        help="Optional apipass directory (defaults to parent of conditions.json)",
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        help="Extra header to include (repeatable), e.g. cjson/cJSON.h",
    )
    parser.add_argument(
        "--harness-style",
        choices=["strict", "simple"],
        default="strict",
        help="Validation strictness for generated harness",
    )

    args = parser.parse_args()

    generator = WrapperGenerator(
        Path(args.proto),
        Path(args.driver),
        Path(args.conditions),
        apis_path=Path(args.apis) if args.apis else None,
        minimum_apis=load_text_lines(Path(args.minimum_apis)) if args.minimum_apis else None,
        package_name=args.package,
        schema_mode=args.schema_mode,
        mutation_mode=args.mutation_mode,
        max_actions=args.max_actions,
        extra_headers=args.header,
        apipass_dir=Path(args.apipass_dir) if args.apipass_dir else None,
        harness_style=args.harness_style,
    )

    generator.generate(Path(args.output))


if __name__ == "__main__":
    main()
