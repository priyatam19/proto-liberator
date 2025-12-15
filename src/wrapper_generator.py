#!/usr/bin/env python3
"""
Wrapper Generator - Template-Based C Harness Generation
Generates fuzzing wrappers from protobuf schemas + libErator driver metadata
NO LLM - uses Jinja2 templates
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

# TODO: Add jinja2 import once template system is implemented
# import jinja2

from utils import load_json, save_file, format_c_comment


@dataclass
class EMIGuard:
    """Represents an EMI validation guard"""
    guard_type: str      # 'buffer_size', 'null_check', 'dependency', 'malloc_size'
    parameter: str       # Parameter name
    condition: str       # C boolean expression
    action: str          # 'reject' or 'warn'
    severity: str        # 'low', 'medium', 'high', 'critical'
    message: str         # Error message
    depends_on: Optional[str] = None  # For dependency guards


@dataclass
class APICallInfo:
    """Information about an API call in the sequence"""
    function_name: str
    parameters: List[str]
    return_type: str
    is_creator: bool     # Creates an object (handle)
    is_destructor: bool  # Deletes an object


class WrapperGenerator:
    """
    Generate C fuzzing harness from protobuf schema + libErator metadata
    Uses template-based generation (NO LLM)
    """

    def __init__(self, proto_path: Path, driver_meta_path: Path,
                 conditions_path: Path, emi_config: Optional[Dict] = None):
        self.proto_path = proto_path
        self.driver_meta = load_json(driver_meta_path)
        self.conditions = load_json(conditions_path)
        self.emi_config = emi_config or self.get_default_emi_config()

    @staticmethod
    def get_default_emi_config() -> Dict:
        """Default EMI guard configuration"""
        return {
            'max_buffer_size': 65536,
            'max_array_count': 10000,
            'max_malloc_size': 1048576,  # 1 MB
            'max_recursion_depth': 100,
            'enable_null_checks': True,
            'enable_length_checks': True,
            'enable_dependency_checks': True,
            'enable_canaries': True,
            'strict_dependencies': False,  # Allow violations for exploration
        }

    def generate(self, output_path: Path):
        """
        Main generation entry point

        Args:
            output_path: Path for generated C harness
        """
        print(f"[Wrapper-Gen] Generating fuzzing harness...")

        # TODO: Extract API sequence from driver.meta
        # api_sequence = self.extract_api_sequence()

        # TODO: Generate EMI guards from conditions.json
        # emi_guards = self.generate_emi_guards()

        # TODO: Generate handle management code
        # handle_mgmt = self.generate_handle_management()

        # TODO: Render template with context
        # wrapper_code = self.render_template(api_sequence, emi_guards, handle_mgmt)

        # For now, generate a placeholder
        wrapper_code = self.generate_placeholder_wrapper()

        save_file(output_path, wrapper_code)
        print(f"[Wrapper-Gen] ✓ Generated: {output_path}")

    def generate_placeholder_wrapper(self) -> str:
        """
        Generate placeholder wrapper (TODO: Replace with template system)
        """
        # TODO: This is a temporary placeholder. Implement full template rendering.

        code = f'''// Auto-generated fuzzing harness by Proto-libErator
// WARNING: This is a placeholder. Full implementation in progress.

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

// TODO: Add protobuf includes
// #include "pb_decode.h"
// #include "generated_proto.pb.h"

// TODO: Add library includes

#define PIN_EMI_REJECT_RC 86
#define MAX_BUFFER_SIZE {self.emi_config['max_buffer_size']}
#define MAX_ARRAY_COUNT {self.emi_config['max_array_count']}
#define MAX_MALLOC_SIZE {self.emi_config['max_malloc_size']}

// TODO: Implement handle management
typedef struct {{
    void* ptr;
    const char* type_name;
    bool is_valid;
}} HandleEntry;

static HandleEntry g_handles[1024];
static uint32_t g_next_handle = 1;

// TODO: Implement handle registration
uint32_t register_handle(void* ptr, const char* type_name) {{
    if (g_next_handle >= 1024) return 0;
    uint32_t handle = g_next_handle++;
    g_handles[handle].ptr = ptr;
    g_handles[handle].type_name = type_name;
    g_handles[handle].is_valid = true;
    return handle;
}}

// TODO: Implement handle retrieval
void* get_handle(uint32_t handle_id) {{
    if (handle_id >= g_next_handle) return NULL;
    if (!g_handles[handle_id].is_valid) return NULL;
    return g_handles[handle_id].ptr;
}}

// TODO: Implement LibFuzzer entry point
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {{
    // TODO: Decode protobuf input
    fprintf(stderr, "[TODO] Protobuf decoding not yet implemented\\n");

    // TODO: Apply EMI guards
    fprintf(stderr, "[TODO] EMI guards not yet implemented\\n");

    // TODO: Execute API sequence from libErator driver.meta
    fprintf(stderr, "[TODO] API sequence execution not yet implemented\\n");

    // TODO: Cleanup handles
    fprintf(stderr, "[TODO] Handle cleanup not yet implemented\\n");

    return 0;
}}
'''
        return code

    def generate_emi_guards(self) -> List[EMIGuard]:
        """
        Generate EMI validation guards from conditions.json

        Returns:
            List of EMIGuard objects
        """
        guards = []

        for func_entry in self.conditions:
            func_name = func_entry['function_name']

            for param_key, param_info in func_entry.items():
                if not param_key.startswith('param_'):
                    continue

                param_name = param_key

                # RULE 1: Buffer size checks
                if param_info.get('is_array') and self.emi_config['enable_length_checks']:
                    guards.append(EMIGuard(
                        guard_type='buffer_size',
                        parameter=param_name,
                        condition=f'input.{param_name}_length_override > MAX_BUFFER_SIZE',
                        action='reject',
                        severity='high',
                        message=f'{param_name} length exceeds maximum'
                    ))

                # RULE 2: Null pointer checks
                if self.emi_config['enable_null_checks']:
                    access_types = [a.get('access') for a in param_info.get('access_type_set', [])]
                    if 'read' in access_types:
                        guards.append(EMIGuard(
                            guard_type='null_check',
                            parameter=param_name,
                            condition=f'input.{param_name}_is_null',
                            action='reject' if self.emi_config['strict_dependencies'] else 'warn',
                            severity='high',
                            message=f'{param_name} cannot be null (required for read)'
                        ))

                # RULE 3: malloc size limits
                if param_info.get('is_malloc_size'):
                    guards.append(EMIGuard(
                        guard_type='malloc_size',
                        parameter=param_name,
                        condition=f'input.{param_name}_malloc_override > MAX_MALLOC_SIZE',
                        action='reject',
                        severity='critical',
                        message=f'malloc size exceeds safe limit'
                    ))

                # RULE 4: Dependency checks
                if self.emi_config['enable_dependency_checks']:
                    for dep_param in param_info.get('set_by', []):
                        guards.append(EMIGuard(
                            guard_type='dependency',
                            parameter=param_name,
                            condition=f'!input.has_{dep_param}',
                            action='reject' if self.emi_config['strict_dependencies'] else 'warn',
                            severity='medium',
                            message=f'{param_name} depends on {dep_param}',
                            depends_on=dep_param
                        ))

        return guards

    def extract_api_sequence(self) -> List[APICallInfo]:
        """
        Extract API call sequence from libErator driver.meta

        Returns:
            List of APICallInfo objects
        """
        # TODO: Parse driver.meta['api_multiset'] and create APICallInfo objects
        # The api_multiset contains the sequence of API calls generated by NDA

        api_sequence = []

        # Placeholder
        # for api_name in self.driver_meta.get('api_multiset', []):
        #     api_info = APICallInfo(
        #         function_name=api_name,
        #         parameters=[],  # TODO: Extract from conditions.json
        #         return_type='',  # TODO: Extract from conditions.json
        #         is_creator=False,  # TODO: Check access_type_set for 'create'
        #         is_destructor=False  # TODO: Check access_type_set for 'delete'
        #     )
        #     api_sequence.append(api_info)

        return api_sequence

    def generate_handle_management(self) -> str:
        """
        Generate handle management code

        Returns:
            C code for handle table
        """
        # TODO: Generate sophisticated handle management
        # - Type tracking
        # - Validity flags
        # - Reference counting (optional)
        # - Automatic cleanup

        code = '''
// TODO: Implement handle management
typedef struct {
    void* ptr;
    const char* type_name;
    uint32_t api_call_index;  // Where it was created
    bool is_valid;
} HandleInfo;

static HandleInfo g_handle_table[1024];
static uint32_t g_next_handle = 1;

uint32_t register_handle(void* ptr, const char* type, uint32_t call_idx) {
    // TODO: Implement
    return 0;
}

void* get_handle(uint32_t handle_id, const char* expected_type) {
    // TODO: Implement with type checking
    return NULL;
}

void invalidate_handle(uint32_t handle_id) {
    // TODO: Implement
}

void cleanup_all_handles(void) {
    // TODO: Implement cleanup in reverse creation order
}
'''
        return code

    def render_template(self, api_sequence: List[APICallInfo],
                       emi_guards: List[EMIGuard],
                       handle_mgmt: str) -> str:
        """
        Render wrapper template with context

        Args:
            api_sequence: API calls to execute
            emi_guards: EMI validation guards
            handle_mgmt: Handle management code

        Returns:
            Complete C source code
        """
        # TODO: Implement Jinja2 template rendering
        # template_path = Path(__file__).parent.parent / 'templates' / 'wrapper.c.j2'
        # template = jinja2.Template(template_path.read_text())
        # return template.render(...)

        return "// TODO: Template rendering not implemented"


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Template-Based Wrapper Generator for Proto-libErator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python3 wrapper_generator.py \\
    --proto examples/cjson/generated/cjson_params.proto \\
    --driver ../liberator/workdir/cjson/metadata/driver0.meta \\
    --conditions ../liberator/analysis/cjson/work/apipass/conditions.json \\
    --output examples/cjson/generated/driver0_proto.c
        """
    )

    parser.add_argument('--proto', required=True,
                        help='Path to generated .proto file')
    parser.add_argument('--driver', required=True,
                        help='Path to libErator driver.meta file')
    parser.add_argument('--conditions', required=True,
                        help='Path to conditions.json')
    parser.add_argument('--output', required=True,
                        help='Output C harness file path')
    parser.add_argument('--max-buffer-size', type=int, default=65536,
                        help='Maximum buffer size for EMI guards')
    parser.add_argument('--strict', action='store_true',
                        help='Enable strict dependency checking')

    args = parser.parse_args()

    # Create EMI config from CLI args
    emi_config = WrapperGenerator.get_default_emi_config()
    emi_config['max_buffer_size'] = args.max_buffer_size
    emi_config['strict_dependencies'] = args.strict

    # Generate wrapper
    generator = WrapperGenerator(
        Path(args.proto),
        Path(args.driver),
        Path(args.conditions),
        emi_config
    )

    generator.generate(Path(args.output))


if __name__ == '__main__':
    main()
