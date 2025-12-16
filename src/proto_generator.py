#!/usr/bin/env python3
"""
Proto Generator - LLM-Free Protobuf Schema Generation
Transforms libErator's conditions.json to .proto files using rule-based logic
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass

# Import local modules
from type_mapper import TypeMapper
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

    def __init__(self, package_name: str):
        self.package = package_name
        self.messages: List[ProtoMessage] = []
        self.imports: Set[str] = {'import "nanopb.proto";'}

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
        max_calls_per_api: int = 4,
        max_actions: int = DEFAULT_MAX_ACTIONS,
        max_bytes_size: int = 65536,
    ):
        self.conditions = load_json(conditions_path)
        self.apis = self.load_apis(apis_path)
        self.type_mapper = TypeMapper()
        self.schema_mode = schema_mode
        self.max_calls_per_api = max_calls_per_api
        self.max_actions = max_actions
        self.max_bytes_size = max_bytes_size

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
        schema = ProtoSchema(f'{library_name}_fuzzer')

        # Generate parameter message for each API function (stable ordering)
        func_entries = sorted(
            self.conditions,
            key=lambda e: str(e.get("function_name") or e.get("functionName") or ""),
        )

        function_names: List[str] = []
        for func_entry in func_entries:
            func_name = func_entry.get("function_name") or func_entry.get("functionName")
            if not func_name:
                continue
            function_names.append(func_name)
            schema.add_message(self.generate_param_message(func_name, func_entry))

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

        for func_name in sorted(set(function_names)):
            field_name = to_proto_field_name(func_name)
            params_type = f"{func_name}_Params"
            msg.add_field(
                "repeated",
                params_type,
                field_name,
                f"[(nanopb).max_count = {self.max_calls_per_api}]",
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
        msg.add_field(
            "repeated",
            "Action",
            "actions",
            f"[(nanopb).max_count = {self.max_actions}]",
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

        # Process each parameter
        for param_key, param_info in func_metadata.items():
            if not param_key.startswith('param_'):
                continue

            param_idx = param_key.replace('param_', '')
            self._add_parameter_fields(msg, param_idx, param_info)

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

        msg.add_comment(f'{param_name}: {llvm_type}')

        # RULE 1: Array parameters
        if param_info.get('is_array'):
            msg.add_field('optional', 'bytes', param_name,
                          f'[(nanopb).max_size = {self.max_bytes_size}]')
            msg.add_field('optional', 'uint32', f'{param_name}_length')
            msg.add_field('optional', 'uint32', f'{param_name}_length_override')
            msg.add_comment(f'  ↳ Array with explicit length control')

        # RULE 2: Struct pointer → Handle ID
        elif llvm_type.startswith('%struct.') or llvm_type.endswith('*'):
            proto_type = self.type_mapper.map_llvm_to_proto(llvm_type)

            if proto_type == 'uint32':  # Handle to object
                msg.add_field('optional', 'uint32', f'{param_name}_handle')
                msg.add_comment(f'  ↳ Handle to {llvm_type} object')
            else:
                if proto_type == 'bytes':
                    msg.add_field(
                        'optional',
                        'bytes',
                        param_name,
                        f'[(nanopb).max_size = {self.max_bytes_size}]',
                    )
                else:
                    msg.add_field('optional', proto_type, param_name)

        # RULE 3: Primitive types
        else:
            proto_type = self.type_mapper.map_llvm_to_proto(llvm_type)
            if proto_type == 'bytes':
                msg.add_field(
                    'optional',
                    'bytes',
                    param_name,
                    f'[(nanopb).max_size = {self.max_bytes_size}]',
                )
            else:
                msg.add_field('optional', proto_type, param_name)

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
    parser.add_argument('--max-calls-per-api', type=int, default=4,
                        help='Max repeated Params entries per API in FuzzInput (default: 4)')
    parser.add_argument('--max-actions', type=int, default=DEFAULT_MAX_ACTIONS,
                        help=f'Max Action entries in v2 FuzzInput (default: {DEFAULT_MAX_ACTIONS})')
    parser.add_argument('--max-bytes-size', type=int, default=65536,
                        help='Nanopb max_size for bytes fields (default: 65536)')

    args = parser.parse_args()

    # Generate schema
    print(f"[Proto-libErator] Generating protobuf schema for {args.library}...")
    generator = ProtoGenerator(
        Path(args.conditions),
        Path(args.apis),
        schema_mode=args.schema_mode,
        max_calls_per_api=args.max_calls_per_api,
        max_actions=args.max_actions,
        max_bytes_size=args.max_bytes_size,
    )
    schema = generator.generate_schema(args.library)

    # Save to file
    output_path = Path(args.output)
    save_file(output_path, schema.serialize())

    print(f"[Proto-libErator] ✓ Generated: {output_path}")
    print(f"[Proto-libErator] Messages: {len(schema.messages)}")


if __name__ == '__main__':
    main()
