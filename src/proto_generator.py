#!/usr/bin/env python3
"""
Proto Generator - LLM-Free Protobuf Schema Generation
Transforms libErator's conditions.json to .proto files using rule-based logic
"""

import json
import argparse
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass

# Import local modules
from type_mapper import TypeMapper, TypeContext
from contracts import DEFAULT_MAX_ACTIONS
from utils import load_json, load_text_lines, save_file, to_proto_field_name


@dataclass
class ProtoField:
    """Represents a protobuf field"""
    label: str  # required/optional/repeated
    type: str   # Protobuf type
    name: str   # Field name
    number: int # Field number
    options: str = ""  # Nanopb options


@dataclass
class ProtoOneofField:
    """Represents a protobuf field within a oneof"""
    type: str
    name: str
    number: int
    options: str = ""


class ProtoOneof:
    """Represents a protobuf oneof block"""

    def __init__(self, name: str):
        self.name = name
        self.fields: List[ProtoOneofField] = []
        self.comments: List[str] = []

    def add_comment(self, comment: str):
        self.comments.append(comment)

    def add_field(self, proto_type: str, name: str, number: int, options: str = ""):
        self.fields.append(ProtoOneofField(proto_type, name, number, options))

    def serialize(self, indent: int = 0) -> str:
        ind = "  " * indent
        lines: List[str] = []
        for comment in self.comments:
            lines.append(f"{ind}// {comment}")
        lines.append(f"{ind}oneof {self.name} {{")
        for field in self.fields:
            field_line = f"{ind}  {field.type} {field.name} = {field.number}"
            if field.options:
                field_line += f" {field.options}"
            field_line += ";"
            lines.append(field_line)
        lines.append(f"{ind}}}")
        return "\n".join(lines)


class ProtoMessage:
    """Represents a protobuf message"""

    def __init__(self, name: str):
        self.name = name
        self.fields: List[ProtoField] = []
        self.comments: List[str] = []
        self.nested_messages: List['ProtoMessage'] = []
        self.oneofs: List[ProtoOneof] = []

    def add_field(self, label: str, proto_type: str, name: str, options: str = ""):
        """Add a field to this message"""
        field_num = len(self.fields) + 1
        self.fields.append(ProtoField(label, proto_type, name, field_num, options))

    def add_comment(self, comment: str):
        """Add a comment line"""
        self.comments.append(comment)

    def add_oneof(self, name: str) -> ProtoOneof:
        oneof = ProtoOneof(name)
        self.oneofs.append(oneof)
        return oneof

    def serialize(self, indent: int = 0) -> str:
        """Serialize to protobuf syntax"""
        ind = "  " * indent
        lines = []

        # Comments
        for comment in self.comments:
            lines.append(f"{ind}// {comment}")

        # Message definition
        lines.append(f"{ind}message {self.name} {{")

        # Nested messages
        for idx, nested in enumerate(self.nested_messages):
            lines.append(nested.serialize(indent + 1))
            if idx != len(self.nested_messages) - 1 or self.oneofs or self.fields:
                lines.append("")

        # Oneofs
        for idx, oneof in enumerate(self.oneofs):
            lines.append(oneof.serialize(indent + 1))
            if idx != len(self.oneofs) - 1 or self.fields:
                lines.append("")

        # Fields
        for field in self.fields:
            field_line = f"{ind}  {field.label} {field.type} {field.name} = {field.number}"
            if field.options:
                field_line += f" {field.options}"
            field_line += ";"
            lines.append(field_line)

        lines.append(f"{ind}}}")
        return "\n".join(lines)


class ProtoSchema:
    """Represents a complete protobuf schema file"""

    def __init__(self, package_name: str, mutation_mode: str = "nanopb"):
        self.package = package_name
        self.messages: List[ProtoMessage] = []
        self.imports: Set[str] = set()
        if mutation_mode == "nanopb":
            self.imports.add('import "nanopb.proto";')

    def add_message(self, msg: ProtoMessage):
        """Add a message to schema"""
        self.messages.append(msg)

    def serialize(self) -> str:
        """Serialize to complete .proto file"""
        lines = [
            'syntax = "proto2";',
            '',
            f'package {self.package};',
            ''
        ]

        # Imports
        for imp in sorted(self.imports):
            lines.append(imp)
        lines.append('')

        # Messages
        for msg in self.messages:
            lines.append(msg.serialize())
            lines.append('')

        return "\n".join(lines)


class ProtoGenerator:
    """
    Main protobuf schema generator (LLM-FREE)
    Transforms libErator's conditions.json to .proto using rules
    """

    def __init__(
        self,
        conditions_path: Path,
        apis_path: Path,
        *,
        schema_mode: str = "v1",
        mutation_mode: str = "nanopb",
        max_calls_per_api: int = 4,
        max_actions: int = DEFAULT_MAX_ACTIONS,
        max_bytes_size: int = 65536,
        minimum_apis: Optional[Set[str]] = None,
        apipass_dir: Optional[Path] = None,
    ):
        self.conditions = load_json(conditions_path)
        self.apis = self.load_apis(apis_path)
        self.type_mapper = TypeMapper()
        # Default apipass dir is the parent directory of conditions.json (libErator convention).
        self.type_context = TypeContext.from_apipass_dir(apipass_dir or conditions_path.parent)
        self.managed_struct_names = self._infer_managed_struct_names()
        self.schema_mode = schema_mode
        self.mutation_mode = mutation_mode
        self.max_calls_per_api = max_calls_per_api
        self.max_actions = max_actions
        self.max_bytes_size = max_bytes_size
        self.minimum_apis = set(minimum_apis or [])

    def _phase3_stub_metadata(self, api_row: Dict) -> Optional[Dict]:
        """
        Build synthetic metadata for APIs present in apis_clang.json but absent
        from conditions.json.

        Stub policy:
        - one generic `bytes` field per clang argument
        - no inferred inter/intra constraints
        """
        fn = str(api_row.get("function_name") or "").strip()
        if not fn:
            return None
        args = api_row.get("arguments_info") or []
        if not isinstance(args, list):
            args = []
        meta: Dict = {"function_name": fn, "_phase3_stub": True}
        for i, _ in enumerate(args):
            meta[f"param_{i}"] = {
                "type_string": "i8*",
                "_phase3_stub_param": True,
            }
        return meta

    def _infer_managed_struct_names(self) -> Set[str]:
        """
        Heuristic: treat struct pointer types returned by any API as "managed objects"
        and represent them as handles (not struct blobs).

        This avoids blob-initializing opaque library objects such as `cJSON*`.
        """
        out: Set[str] = set()
        if not isinstance(self.conditions, list):
            return out
        for entry in self.conditions:
            if not isinstance(entry, dict):
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
            if self.type_mapper.map_llvm_to_proto(llvm_t) != "uint32":
                continue
            name = self.type_mapper.extract_struct_name(llvm_t)
            if name:
                out.add(name)
        return out

    @staticmethod
    def load_apis(apis_path: Path) -> List[Dict]:
        """
        Load API signatures from libErator outputs.

        Supported formats:
        - apis_clang.json: JSONL (one JSON object per line) as produced by libErator.
        - apis_clang.txt: one function name per line.
        - (fallback) JSON array/object.
        """
        try:
            data = load_json(apis_path)
            if isinstance(data, dict):
                return [data]
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

        # JSONL (most common in libErator)
        apis: List[Dict] = []
        try:
            for line in load_text_lines(apis_path):
                apis.append(json.loads(line))
            if apis:
                return apis
        except Exception:
            apis = []

        # Plain-text list of API names
        return [{"function_name": name} for name in load_text_lines(apis_path)]

    def generate_schema(self, library_name: str) -> ProtoSchema:
        """
        Main entry point: generate complete protobuf schema

        Args:
            library_name: Name of library (e.g., 'cjson')

        Returns:
            Complete ProtoSchema object
        """
        # Proto packages must be valid identifiers; library names can include '-', '.' etc.
        safe_lib = re.sub(r"[^A-Za-z0-9_]+", "_", str(library_name))
        if not safe_lib or safe_lib[0].isdigit():
            safe_lib = f"lib_{safe_lib}"
        schema = ProtoSchema(f"{safe_lib}_fuzzer", mutation_mode=self.mutation_mode)

        # Generate parameter message for each API function (stable ordering)
        func_entries = sorted(
            self.conditions,
            key=lambda e: str(e.get("function_name") or e.get("functionName") or ""),
        )

        function_names: List[str] = []
        seen_functions: Set[str] = set()
        for func_entry in func_entries:
            func_name = func_entry.get("function_name") or func_entry.get("functionName")
            if not func_name:
                continue
            if self.minimum_apis and func_name not in self.minimum_apis:
                continue
            function_names.append(func_name)
            seen_functions.add(str(func_name))
            schema.add_message(self.generate_param_message(func_name, func_entry))

        # Phase 3: synthesize param messages for clang-only APIs.
        stub_entries: List[Tuple[str, Dict]] = []
        for api_row in sorted(self.apis, key=lambda r: str(r.get("function_name") or "")):
            stub_meta = self._phase3_stub_metadata(api_row)
            if not stub_meta:
                continue
            fn = str(stub_meta.get("function_name") or "")
            if not fn or fn in seen_functions:
                continue
            if self.minimum_apis and fn not in self.minimum_apis:
                continue
            stub_entries.append((fn, stub_meta))
            seen_functions.add(fn)

        for fn, stub_meta in stub_entries:
            function_names.append(fn)
            schema.add_message(self.generate_param_message(fn, stub_meta))

        if self.schema_mode == "v2":
            schema.add_message(self.generate_action_message(function_names))
            schema.add_message(self.generate_fuzz_input_message_v2())
        else:
            # Top-level input message: stable contract for wrappers and fuzzers
            schema.add_message(self.generate_fuzz_input_message(function_names))

        return schema

    def generate_fuzz_input_message(self, function_names: List[str]) -> ProtoMessage:
        """
        Generate the top-level `FuzzInput` message.

        Contract:
        - One repeated field per API function, containing that function's Params message.
        - Wrappers consume entries in call order (per-function index) to support multiple calls.
        - All fields are optional/repeated to maximize exploration.
        """
        msg = ProtoMessage("FuzzInput")
        msg.add_comment("Top-level fuzz input. One params list per API function.")
        msg.add_comment("Wrappers consume per-function params in call order.")
        msg.add_field("optional", "uint32", "global_seed")

        options = f"[(nanopb).max_count = {self.max_calls_per_api}]" if self.mutation_mode == "nanopb" else ""
        for func_name in sorted(set(function_names)):
            field_name = to_proto_field_name(func_name)
            params_type = f"{func_name}_Params"
            msg.add_field(
                "repeated",
                params_type,
                field_name,
                options,
            )

        return msg

    def generate_action_message(self, function_names: List[str]) -> ProtoMessage:
        """
        Generate v2 dynamic-dispatch Action message:

          message Action {
            oneof action {
              <FuncA>_Params func_a = 1;
              <FuncB>_Params func_b = 2;
              ...
            }
          }
        """
        msg = ProtoMessage("Action")
        msg.add_comment("Dynamic dispatch: exactly one API call variant per Action.")
        oneof = msg.add_oneof("action")

        unique_sorted_funcs = sorted(set(function_names))
        for tag, func_name in enumerate(unique_sorted_funcs, start=1):
            field_name = to_proto_field_name(func_name)
            params_type = f"{func_name}_Params"
            oneof.add_field(params_type, field_name, tag)

        return msg

    def generate_fuzz_input_message_v2(self) -> ProtoMessage:
        """
        Generate v2 top-level FuzzInput for dynamic dispatch.
        """
        msg = ProtoMessage("FuzzInput")
        msg.add_comment("Top-level fuzz input (v2). Dynamic sequence of Actions.")
        msg.add_field("optional", "uint32", "global_seed")
        options = f"[(nanopb).max_count = {self.max_actions}]" if self.mutation_mode == "nanopb" else ""
        msg.add_field(
            "repeated",
            "Action",
            "actions",
            options,
        )
        return msg

    def generate_param_message(self, func_name: str, func_metadata: Dict) -> ProtoMessage:
        """
        Generate protobuf message for a function's parameters

        Args:
            func_name: Function name (e.g., 'cJSON_AddItemToArray')
            func_metadata: Metadata from conditions.json

        Returns:
            ProtoMessage with fields for each parameter
        """
        msg = ProtoMessage(f'{func_name}_Params')
        msg.add_comment(f'Parameters for {func_name}')
        is_phase3_stub = bool(func_metadata.get("_phase3_stub"))

        if is_phase3_stub:
            msg.add_comment("Phase 3 stub (clang-only API): generic bytes params.")
            nanopb_bytes_opt = f'[(nanopb).max_size = {self.max_bytes_size}]' if self.mutation_mode == "nanopb" else ""
            param_idxs: List[int] = []
            for key in func_metadata.keys():
                if not (isinstance(key, str) and key.startswith("param_")):
                    continue
                try:
                    param_idxs.append(int(key.split("_", 1)[1]))
                except Exception:
                    continue
            for idx in sorted(set(param_idxs)):
                msg.add_field("optional", "bytes", f"param_{idx}", nanopb_bytes_opt)
            return msg

        # Process each parameter in numeric order for stable field numbering.
        # This is critical for:
        # - stable schema diffs across runs
        # - seed generator correctness (wire encoding depends on tag numbers)
        param_items: List[Tuple[int, Dict]] = []
        for param_key, param_info in func_metadata.items():
            if not (isinstance(param_key, str) and param_key.startswith("param_")):
                continue
            if not isinstance(param_info, dict):
                continue
            try:
                idx = int(param_key.split("_", 1)[1])
            except Exception:
                continue
            param_items.append((idx, param_info))

        for idx, param_info in sorted(param_items, key=lambda t: t[0]):
            self._add_parameter_fields(msg, str(idx), param_info)

        # Add contract violation knobs
        self._add_contract_violation_knobs(msg, func_metadata)

        return msg

    def _infer_llvm_type(self, param_info: Dict) -> str:
        """
        Infer an LLVM/libErator type string for a parameter.

        libErator sometimes stores `type_string` only inside `access_type_set`.
        """
        t = param_info.get("type_string") or param_info.get("type")
        if t:
            return str(t)
        access = param_info.get("access_type_set", [])
        if isinstance(access, list) and access:
            first = access[0]
            if isinstance(first, dict):
                return str(first.get("type_string") or first.get("type") or "bytes")
        return "bytes"

    def _add_parameter_fields(self, msg: ProtoMessage, param_idx: str, param_info: Dict):
        """
        Add fields for a single parameter

        Applies rules based on param_info flags:
        - is_array → add buffer + length + length_override
        - is_malloc_size → add malloc_override
        - Nullable → add is_null flag
        """
        param_name = f'param_{param_idx}'

        # Get type information
        llvm_type = self._infer_llvm_type(param_info)
        access_types = param_info.get('access_type_set', [])
        has_set_by = bool(param_info.get("set_by", []))
        has_delete_access = any(
            isinstance(a, dict) and a.get("access") == "delete" for a in (access_types or [])
        )

        msg.add_comment(f'{param_name}: {llvm_type}')

        nanopb_bytes_opt = f'[(nanopb).max_size = {self.max_bytes_size}]' if self.mutation_mode == "nanopb" else ""

        add_scalar_slot = False

        # RULE 1: Array parameters
        # NOTE: Some targets mark struct pointers as `is_array`. Prefer struct-pointer handling in that case.
        is_struct_ptr = llvm_type.startswith("%struct.") or (
            llvm_type.endswith("*") and llvm_type.replace("const ", "").strip().startswith("%struct.")
        )
        if param_info.get('is_array') and not is_struct_ptr:
            msg.add_field('optional', 'bytes', param_name, nanopb_bytes_opt)
            msg.add_field('optional', 'uint32', f'{param_name}_length')
            msg.add_field('optional', 'uint32', f'{param_name}_length_override')
            msg.add_comment(f'  ↳ Array with explicit length control')

        # RULE 2: Dependency / delete semantics → Handle ID (even for i8*/void* buffers),
        # but only when the underlying value is pointer-like.
        elif has_set_by or has_delete_access:
            proto_type = self.type_mapper.map_llvm_to_proto(llvm_type)
            is_ptr_like = bool(
                llvm_type.endswith("*")
                or llvm_type.startswith("%struct.")
                or proto_type in ("bytes", "uint32")
            )
            if is_ptr_like:
                msg.add_field('optional', 'uint32', f'{param_name}_handle')
                msg.add_comment('  ↳ Handle (set_by/delete) for dependency-aware mutation')
            else:
                # Keep scalars as scalars even if libErator reported set_by/write artifacts.
                msg.add_field('optional', proto_type, param_name)
                msg.add_comment('  ↳ Scalar (deps ignored for schema shape)')
                if self.schema_mode == "v2" and self.type_mapper.is_integral_proto_type(proto_type):
                    add_scalar_slot = True

        # RULE 3: Struct pointer → Struct blob (if layout known) else Handle.
        elif is_struct_ptr:
            struct_name = self.type_mapper.extract_struct_name(llvm_type)
            struct_size = self.type_context.struct_size_for(struct_name) if struct_name else None
            if struct_name and struct_name in self.managed_struct_names:
                msg.add_field('optional', 'uint32', f'{param_name}_handle')
                msg.add_comment(f'  ↳ Handle to {llvm_type} object')
            elif struct_size:
                opt = (
                    f'[(nanopb).max_size = {struct_size}]'
                    if self.mutation_mode == "nanopb"
                    else ""
                )
                msg.add_field('optional', 'bytes', f'{param_name}_blob', opt)
                msg.add_comment(f'  ↳ Struct blob init (size={struct_size})')
            else:
                msg.add_field('optional', 'uint32', f'{param_name}_handle')
                msg.add_comment(f'  ↳ Handle to {llvm_type} object')

        # RULE 4: Non-struct pointer → bytes/scalar depending on mapper.
        elif llvm_type.endswith('*'):
            proto_type = self.type_mapper.map_llvm_to_proto(llvm_type)
            if proto_type == 'bytes':
                msg.add_field('optional', 'bytes', param_name, nanopb_bytes_opt)
            else:
                msg.add_field('optional', proto_type, param_name)

        # RULE 5: Primitive types
        else:
            proto_type = self.type_mapper.map_llvm_to_proto(llvm_type)
            if proto_type == 'bytes':
                msg.add_field(
                    'optional',
                    'bytes',
                    param_name,
                    nanopb_bytes_opt,
                )
            else:
                msg.add_field('optional', proto_type, param_name)
                if self.schema_mode == "v2" and self.type_mapper.is_integral_proto_type(proto_type):
                    add_scalar_slot = True

        if add_scalar_slot:
            msg.add_field('optional', 'uint32', f'{param_name}_slot')
            msg.add_comment('  ↳ Scalar slot selector (0=latest, >0=requested slot)')

        # RULE 4: Nullable flag
        if self._is_nullable(param_info, llvm_type):
            msg.add_field('optional', 'bool', f'{param_name}_is_null')
            msg.add_comment(f'  ↳ Nullable exploration knob')

        # RULE 5: malloc size override
        if param_info.get('is_malloc_size'):
            msg.add_field('optional', 'uint32', f'{param_name}_malloc_override')
            msg.add_comment(f'  ↳ malloc size override for overflow testing')

    def _add_contract_violation_knobs(self, msg: ProtoMessage, func_metadata: Dict):
        """
        Add fields for intentional contract violations (UAF, double-free, etc.)
        """
        msg.add_comment('')
        msg.add_comment('Contract violation knobs for semantic bug exploration')

        # Check if function has dependencies
        has_deps = any(
            param_info.get('set_by', [])
            for key, param_info in func_metadata.items()
            if key.startswith('param_')
        )

        if has_deps:
            msg.add_field('optional', 'bool', 'skip_dependency_check')
            msg.add_comment('  ↳ Allow stale handles for UAF exploration')

        # Check if function has returns (for double-free testing)
        if 'return' in func_metadata:
            msg.add_field('optional', 'bool', 'allow_double_delete')
            msg.add_comment('  ↳ Skip double-delete protection')

    def _is_nullable(self, param_info: Dict, llvm_type: str) -> bool:
        """
        Determine if parameter can be null from access_type_set

        Returns:
            True if parameter should have nullable exploration
        """
        # Only pointers/handles/arrays are meaningful nullable knobs.
        if param_info.get("is_array"):
            return True
        if llvm_type.endswith("*") or llvm_type.startswith("%struct."):
            return True
        # Some libErator outputs omit a usable type string; we treat that sentinel as pointer-like.
        if llvm_type == "bytes":
            return True
        if self.type_mapper.is_handle_type(llvm_type):
            return True
        return False


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='LLM-Free Protobuf Schema Generator for libErator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python3 proto_generator.py \\
    --conditions ../liberator/analysis/cjson/work/apipass/conditions.json \\
    --apis ../liberator/analysis/cjson/work/apipass/apis_clang.json \\
    --output cjson_params.proto \\
    --library cjson
        """
    )

    parser.add_argument('--conditions', required=True,
                        help='Path to conditions.json from libErator')
    parser.add_argument('--apis', required=True,
                        help='Path to apis_clang.json from libErator')
    parser.add_argument('--output', required=True,
                        help='Output .proto file path')
    parser.add_argument('--library', required=True,
                        help='Library name (e.g., cjson)')
    parser.add_argument('--schema-mode', choices=['v1', 'v2'], default='v1',
                        help='Schema contract version (default: v1)')
    parser.add_argument('--mutation-mode', choices=['nanopb', 'lpm'], default='nanopb',
                        help='Mutation engine (default: nanopb)')
    parser.add_argument('--max-calls-per-api', type=int, default=4,
                        help='Max repeated Params entries per API in FuzzInput (default: 4)')
    parser.add_argument('--max-actions', type=int, default=DEFAULT_MAX_ACTIONS,
                        help=f'Max Action entries in v2 FuzzInput (default: {DEFAULT_MAX_ACTIONS})')
    parser.add_argument('--max-bytes-size', type=int, default=65536,
                        help='Nanopb max_size for bytes fields (default: 65536)')
    parser.add_argument(
        '--minimum-apis',
        default=None,
        help='Optional apis_minimized.txt (one function per line) to filter schema generation',
    )
    parser.add_argument(
        '--apipass-dir',
        default=None,
        help='Optional apipass directory (defaults to parent of conditions.json)',
    )

    args = parser.parse_args()

    # Generate schema
    print(f"[Proto-libErator] Generating protobuf schema for {args.library}...")
    generator = ProtoGenerator(
        Path(args.conditions),
        Path(args.apis),
        schema_mode=args.schema_mode,
        mutation_mode=args.mutation_mode,
        max_calls_per_api=args.max_calls_per_api,
        max_actions=args.max_actions,
        max_bytes_size=args.max_bytes_size,
        minimum_apis=set(load_text_lines(Path(args.minimum_apis))) if args.minimum_apis else None,
        apipass_dir=Path(args.apipass_dir) if args.apipass_dir else None,
    )
    schema = generator.generate_schema(args.library)

    # Save to file
    output_path = Path(args.output)
    save_file(output_path, schema.serialize())

    print(f"[Proto-libErator] ✓ Generated: {output_path}")
    print(f"[Proto-libErator] Messages: {len(schema.messages)}")


if __name__ == '__main__':
    main()
