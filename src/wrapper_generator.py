#!/usr/bin/env python3
"""
Wrapper Generator - Template-Based C Harness Generation

Consumes:
- Generated `.proto` (only for header naming / package prefix)
- libErator `driver.meta` (sequence driver)
- libErator `conditions.json` (function+param metadata; list of entries)
- libErator `apis_clang.json` (JSONL; function signatures; optional)

Generates:
- `harness.c` implementing nanopb decode and a fixed API sequence.

This module must stay aligned with the schema contract in `docs/SCHEMA_CONTRACT.md`.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader

try:
    from contracts import MSG_FUZZ_INPUT
    from utils import load_json, load_text_lines, to_proto_field_name
    from type_mapper import TypeMapper
except ImportError:
    sys.path.append(os.path.dirname(__file__))
    from contracts import MSG_FUZZ_INPUT
    from utils import load_json, load_text_lines, to_proto_field_name
    from type_mapper import TypeMapper


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
    return " ".join(type_str.strip().split())


def is_char_ptr(c_type: str) -> bool:
    t = c_type.replace("const", "").strip()
    return ("char" in t) and ("*" in t) and ("**" not in t.replace(" ", ""))


def is_void_ptr(c_type: str) -> bool:
    t = c_type.replace("const", "").strip()
    return ("void" in t) and ("*" in t)


def is_pointer_type(c_type: str) -> bool:
    return "*" in c_type


def is_void_return(ret: str) -> bool:
    r = normalize_c_type(ret)
    return r == "void"


def conditions_return_is_handle(entry: Dict[str, Any], mapper: TypeMapper) -> bool:
    ret = entry.get("return")
    if not isinstance(ret, dict):
        return False
    access_set = ret.get("access_type_set", [])
    if isinstance(access_set, list):
        for a in access_set:
            if isinstance(a, dict) and a.get("access") == "create":
                llvm_t = a.get("type_string") or ret.get("type_string") or ""
                return mapper.map_llvm_to_proto(str(llvm_t)) == "uint32"
    llvm_t = ret.get("type_string") or ""
    return mapper.map_llvm_to_proto(str(llvm_t)) == "uint32"


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
    is_array = bool(info.get("is_array"))
    proto_type = mapper.map_llvm_to_proto(llvm_type) if llvm_type else "bytes"

    if is_array:
        return {
            "kind": "bytes_array",
            "field": key,
            "index": param_index,
            "has_is_null": True,
            "has_length": True,
        }

    if proto_type == "uint32":
        return {
            "kind": "handle",
            "field": f"{key}_handle",
            "index": param_index,
            "has_is_null": True,
        }

    if proto_type == "bytes":
        return {
            "kind": "bytes",
            "field": key,
            "index": param_index,
            "has_is_null": True,
        }

    return {"kind": "scalar", "field": key, "index": param_index, "has_is_null": False}


class WrapperGenerator:
    """
    Generate C fuzzing harness from protobuf schema + libErator metadata
    Uses Jinja2 templates.
    """

    def __init__(
        self,
        proto_path: Path,
        driver_meta_path: Path,
        conditions_path: Path,
        *,
        apis_path: Optional[Path] = None,
        package_name: str = "",
        emi_config: Optional[Dict] = None,
        extra_headers: Optional[List[str]] = None,
    ):
        self.proto_path = proto_path
        self.driver_meta = load_json(driver_meta_path)
        self.conditions_raw = load_json(conditions_path)
        self.conditions = index_conditions(self.conditions_raw)
        self.api_sigs = build_signature_index(apis_path)
        self.package_name = package_name
        self.emi_config = emi_config or {}
        self.extra_headers = extra_headers or []
        self.mapper = TypeMapper()
        
        # Setup Jinja2 environment
        template_dir = Path(__file__).parent.parent / 'templates'
        self.env = Environment(loader=FileSystemLoader(str(template_dir)))
        self.template = self.env.get_template('wrapper.c.j2')

    def generate(self, output_path: Path):
        """
        Main generation entry point
        """
        print(f"[Wrapper-Gen] Generating fuzzing harness...")

        # Prepare context for template
        context = self._prepare_context()
        
        # Render template
        wrapper_code = self.template.render(context)

        with open(output_path, 'w') as f:
            f.write(wrapper_code)
            
        print(f"[Wrapper-Gen] ✓ Generated: {output_path}")

    def _prepare_context(self) -> Dict:
        """
        Transform input data into template context
        """
        headers = self.driver_meta.get("headers", []) or []
        if not isinstance(headers, list):
            headers = []
        headers.extend(self.extra_headers)
        if not headers:
            headers = []

        # Extract API sequence from driver.meta
        # Expecting driver.meta to contain a list of calls, e.g. "api_sequence": ["func1", "func2"]
        # Or "api_multiset": {"func1": 2, "func2": 1}
        raw_sequence = self.driver_meta.get("api_sequence", [])
        
        if not raw_sequence:
            multiset = self.driver_meta.get("api_multiset", {})
            if multiset:
                # Expand multiset into a list
                # Note: Order is arbitrary here, which is risky for dependencies.
                # Ideally we'd use the dependency graph to sort.
                # For now, we sort by name to be deterministic.
                for func_name in sorted(multiset.keys()):
                    count = multiset[func_name]
                    raw_sequence.extend([func_name] * count)
            else:
                # Fallback: use all keys from conditions.json sorted
                print("[Wrapper-Gen] Warning: No 'api_sequence' or 'api_multiset' in driver.meta. Using all functions.")
                raw_sequence = sorted(self.conditions.keys())

        # Determine type names with package prefix
        prefix = f"{self.package_name}_" if self.package_name else ""
        fuzz_input_type = f"{prefix}{MSG_FUZZ_INPUT}"

        api_sequence = []
        unique_apis_set = set()
        unique_apis = []

        for func_name in raw_sequence:
            if func_name not in self.conditions:
                print(f"[Wrapper-Gen] Warning: Function {func_name} in sequence but not in conditions.json")
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
                # Stub mode: attempt to use `parameters` list for types.
                params = entry.get("parameters")
                if isinstance(params, list):
                    arg_types = [normalize_c_type(str(p.get("type") or "int")) for p in params][:argc]
                if len(arg_types) < argc:
                    arg_types.extend(["int"] * (argc - len(arg_types)))
            
            args: List[Dict[str, Any]] = []
            for i in range(argc):
                param_desc = classify_param(entry, i, self.mapper)
                c_type = arg_types[i] if i < len(arg_types) else "int"
                args.append(
                    {
                        "i": i,
                        "c_type": c_type,
                        "param": param_desc,
                        "is_char_ptr": is_char_ptr(c_type),
                        "is_void_ptr": is_void_ptr(c_type),
                        "is_pointer": is_pointer_type(c_type),
                    }
                )

            returns_handle = conditions_return_is_handle(entry, self.mapper)

            # Prepare call object (template-facing)
            call = {
                'name': func_name,
                'field_name': to_proto_field_name(func_name),
                'struct_type': f"{prefix}{func_name}_Params",
                'argc': argc,
                'args': args,
                'return_type': ret_type,
                'return_is_void': is_void_return(ret_type),
                'returns_handle': returns_handle,
                'has_skip_dependency_check': function_has_deps(entry),
                'has_allow_double_delete': "return" in entry,
                'is_destructor': is_destructor_name(func_name),
            }
            
            api_sequence.append(call)
            
            if func_name not in unique_apis_set:
                unique_apis_set.add(func_name)
                unique_apis.append(call)

        return {
            'headers': headers,
            'proto_header': self.proto_path.stem + ".pb.h",
            'fuzz_input_type': fuzz_input_type,
            'unique_apis': unique_apis,
            'api_sequence': api_sequence
        }

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Template-Based Wrapper Generator for Proto-libErator'
    )

    parser.add_argument('--proto', required=True, help='Path to generated .proto file')
    parser.add_argument('--driver', required=True, help='Path to libErator driver.meta file')
    parser.add_argument('--conditions', required=True, help='Path to conditions.json')
    parser.add_argument('--apis', help='Path to apis_clang.json (JSONL) for accurate arg counts')
    parser.add_argument('--output', required=True, help='Output C harness file path')
    parser.add_argument('--package', default="", help='Protobuf package name prefix')
    parser.add_argument('--header', action='append', default=[],
                        help='Extra header to include (repeatable), e.g. cjson/cJSON.h')

    args = parser.parse_args()

    generator = WrapperGenerator(
        Path(args.proto),
        Path(args.driver),
        Path(args.conditions),
        apis_path=Path(args.apis) if args.apis else None,
        package_name=args.package,
        extra_headers=args.header,
    )

    generator.generate(Path(args.output))

if __name__ == '__main__':
    main()
