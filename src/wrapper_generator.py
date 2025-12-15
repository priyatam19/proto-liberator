#!/usr/bin/env python3
"""
Wrapper Generator - Template-Based C Harness Generation
Generates fuzzing wrappers from protobuf schemas + libErator driver metadata
"""

import json
import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from jinja2 import Environment, FileSystemLoader

# Import contracts
# Assuming contracts.py is in the same directory
try:
    from contracts import MSG_FUZZ_INPUT, FIELD_API_CALLS
except ImportError:
    # Fallback if running as script
    sys.path.append(os.path.dirname(__file__))
    from contracts import MSG_FUZZ_INPUT, FIELD_API_CALLS

def load_json(path: Path) -> Dict:
    with open(path, 'r') as f:
        return json.load(f)

class WrapperGenerator:
    """
    Generate C fuzzing harness from protobuf schema + libErator metadata
    Uses Jinja2 templates.
    """

    def __init__(self, proto_path: Path, driver_meta_path: Path,
                 conditions_path: Path, emi_config: Optional[Dict] = None):
        self.proto_path = proto_path
        self.driver_meta = load_json(driver_meta_path)
        self.conditions = load_json(conditions_path)
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
        # Extract headers from driver.meta or conditions
        headers = self.driver_meta.get('headers', [])
        if not headers:
             # Fallback or default headers
             headers = ["stdlib.h", "string.h"]

        apis = []
        # Sort keys to ensure deterministic order
        sorted_funcs = sorted(self.conditions.keys())
        
        for idx, func_name in enumerate(sorted_funcs):
            details = self.conditions[func_name]
            
            # Construct API context
            # Note: Tag assignment must match Schema Generator's logic.
            # We assume sequential tags starting at 1 for the 'oneof' in ApiCall.
            
            api = {
                'name': func_name,
                'tag': idx + 1, 
                'oneof_tag': f"ApiCall_call_{func_name}_tag", # Nanopb tag convention
                'field_name': func_name,
                'struct_type': f"{func_name}_Params", # Schema convention
                'args': []
            }
            
            for param in details.get('parameters', []):
                arg = {
                    'name': param['name'],
                    'type': param['type'], 
                    # Add more details as needed for conversion
                }
                api['args'].append(arg)
            
            apis.append(api)

        return {
            'headers': headers,
            'fuzz_input_type': MSG_FUZZ_INPUT,
            'api_calls_field': FIELD_API_CALLS,
            'api_call_type': 'ApiCall',
            'apis': apis
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

    args = parser.parse_args()

    generator = WrapperGenerator(
        Path(args.proto),
        Path(args.driver),
        Path(args.conditions)
    )

    generator.generate(Path(args.output))

if __name__ == '__main__':
    main()
