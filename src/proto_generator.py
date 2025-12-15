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
from utils import load_json, save_file


@dataclass
class ProtoField:
    """Represents a protobuf field"""
    label: str  # required/optional/repeated
    type: str   # Protobuf type
    name: str   # Field name
    number: int # Field number
    options: str = ""  # Nanopb options


class ProtoMessage:
    """Represents a protobuf message"""

    def __init__(self, name: str):
        self.name = name
        self.fields: List[ProtoField] = []
        self.comments: List[str] = []
        self.nested_messages: List['ProtoMessage'] = []

    def add_field(self, label: str, proto_type: str, name: str, options: str = ""):
        """Add a field to this message"""
        field_num = len(self.fields) + 1
        self.fields.append(ProtoField(label, proto_type, name, field_num, options))

    def add_comment(self, comment: str):
        """Add a comment line"""
        self.comments.append(comment)

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
        for nested in self.nested_messages:
            lines.append(nested.serialize(indent + 1))
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

    def __init__(self, conditions_path: Path, apis_path: Path):
        self.conditions = load_json(conditions_path)
        self.apis = self.load_apis(apis_path)
        self.type_mapper = TypeMapper()

    @staticmethod
    def load_apis(apis_path: Path) -> Dict:
        """Load API signatures from apis_clang.json"""
        # TODO: Handle both apis_clang.json (JSON) and apis_clang.txt (text) formats
        data = load_json(apis_path)
        return data

    def generate_schema(self, library_name: str) -> ProtoSchema:
        """
        Main entry point: generate complete protobuf schema

        Args:
            library_name: Name of library (e.g., 'cjson')

        Returns:
            Complete ProtoSchema object
        """
        schema = ProtoSchema(f'{library_name}_fuzzer')

        # Generate parameter message for each API function
        for func_entry in self.conditions:
            func_name = func_entry['function_name']

            # Generate parameter message
            param_msg = self.generate_param_message(func_name, func_entry)
            schema.add_message(param_msg)

        # TODO: Generate top-level FuzzInput message that combines all API params
        # fuzzer_input_msg = self.generate_fuzzer_input_message()
        # schema.add_message(fuzzer_input_msg)

        return schema

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
        llvm_type = param_info.get('type_string', 'bytes')
        access_types = param_info.get('access_type_set', [])

        msg.add_comment(f'{param_name}: {llvm_type}')

        # RULE 1: Array parameters
        if param_info.get('is_array'):
            msg.add_field('optional', 'bytes', param_name,
                          '[(nanopb).max_size = 65536]')
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
                msg.add_field('optional', proto_type, param_name)

        # RULE 3: Primitive types
        else:
            proto_type = self.type_mapper.map_llvm_to_proto(llvm_type)
            msg.add_field('optional', proto_type, param_name)

        # RULE 4: Nullable flag
        if self._is_nullable(param_info):
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

    def _is_nullable(self, param_info: Dict) -> bool:
        """
        Determine if parameter can be null from access_type_set

        Returns:
            True if parameter should have nullable exploration
        """
        access_types = param_info.get('access_type_set', [])

        # Extract access type strings
        access_strs = [a.get('access', '') for a in access_types]

        # If 'read' access without explicit null handling → non-nullable by default
        # But we still want to explore null for fuzzing
        if 'read' in access_strs:
            return True  # Add nullable flag for exploration

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

    args = parser.parse_args()

    # Generate schema
    print(f"[Proto-libErator] Generating protobuf schema for {args.library}...")
    generator = ProtoGenerator(Path(args.conditions), Path(args.apis))
    schema = generator.generate_schema(args.library)

    # Save to file
    output_path = Path(args.output)
    save_file(output_path, schema.serialize())

    print(f"[Proto-libErator] ✓ Generated: {output_path}")
    print(f"[Proto-libErator] Messages: {len(schema.messages)}")


if __name__ == '__main__':
    main()
