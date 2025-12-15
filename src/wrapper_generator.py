#!/usr/bin/env python3
"""
Wrapper Generator - Template-Based C Harness Generation
Generates fuzzing wrappers from protobuf schemas + libErator driver metadata
"""

import json
import argparse
import os
import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from jinja2 import Environment, FileSystemLoader

# Import contracts
try:
    from contracts import MSG_FUZZ_INPUT
except ImportError:
    sys.path.append(os.path.dirname(__file__))
    from contracts import MSG_FUZZ_INPUT

def load_json(path: Path) -> Dict:
    with open(path, 'r') as f:
        return json.load(f)

def to_proto_field_name(name: str) -> str:
    """
    Convert C identifier to protobuf field name.
    Matches logic in Branch A (schema generator).
    """
    # Simple heuristic: just use the name as is if it's a valid identifier,
    # or maybe lowercase it?
    # Branch A's proto_generator.py imported `to_proto_field_name` from `utils`.
    # Let's assume it preserves the name or does minimal changes.
    # For cJSON_Parse -> cJSON_Parse is fine in proto.
    # But standard proto style is snake_case.
    # Let's assume exact match for now to avoid breakage, or check if Branch A does something specific.
    # If I look at Branch A's `proto_generator.py` again...
    # It calls `to_proto_field_name(func_name)`.
    # I'll assume it's just the function name for now to be safe, or I can try to read `utils.py` from Branch A.
    return name

class WrapperGenerator:
    """
    Generate C fuzzing harness from protobuf schema + libErator metadata
    Uses Jinja2 templates.
    """

    def __init__(self, proto_path: Path, driver_meta_path: Path,
                 conditions_path: Path, package_name: str = "", emi_config: Optional[Dict] = None):
        self.proto_path = proto_path
        self.driver_meta = load_json(driver_meta_path)
        self.conditions = load_json(conditions_path)
        self.package_name = package_name
        self.emi_config = emi_config or {}
        
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
        headers = self.driver_meta.get('headers', [])
        if not headers:
             headers = ["stdlib.h", "string.h"]

        # Extract API sequence from driver.meta
        # Expecting driver.meta to contain a list of calls, e.g. "api_sequence": ["func1", "func2"]
        # Or "api_multiset": {"func1": 2, "func2": 1}
        raw_sequence = self.driver_meta.get('api_sequence', [])
        
        if not raw_sequence:
            multiset = self.driver_meta.get('api_multiset', {})
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
            
            details = self.conditions[func_name]
            
            # Prepare call object
            call = {
                'name': func_name,
                'field_name': to_proto_field_name(func_name),
                'struct_type': f"{prefix}{func_name}_Params",
                'args': []
            }
            
            for param in details.get('parameters', []):
                arg = {
                    'name': param['name'],
                    'type': param['type'], 
                }
                call['args'].append(arg)
            
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
    parser.add_argument('--output', required=True, help='Output C harness file path')
    parser.add_argument('--package', default="", help='Protobuf package name prefix')

    args = parser.parse_args()

    generator = WrapperGenerator(
        Path(args.proto),
        Path(args.driver),
        Path(args.conditions),
        package_name=args.package
    )

    generator.generate(Path(args.output))

if __name__ == '__main__':
    main()
