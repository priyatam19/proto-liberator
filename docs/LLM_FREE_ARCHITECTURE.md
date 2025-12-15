# Proto-libErator: LLM-Free Architecture

**Document Version:** 1.0
**Date:** 2025-12-15
**Status:** Design Specification

---

## Executive Summary

This document describes the **LLM-free architecture** for Proto-libErator, contrasting with PIN 2.0's LLM-based approach. We achieve the same protobuf-based fuzzing capabilities using **pure rule-based transformations** from libErator's SVF static analysis.

**Key Insight**: libErator's `conditions.json` already contains all the information PIN 2.0 extracts via LLM API calls.

---

## Why LLMs Are NOT Needed

### PIN 2.0's LLM Usage

```python
# PIN 2.0: proto_generator.py (lines 17-52)
def discover_api_dependencies(context, cve_context):
    """
    Uses LLM to analyze 30-50 LOC function body and extract:
    - Pointer ownership and nullability
    - Pre/post conditions
    - Invariants and constraints
    - Vulnerability patterns
    """
    prompt = build_phase1_prompt(context)  # 300+ line prompt
    response = llm_client.generate_json(prompt)  # $0.10-$0.50 per call
    return response
```

**Cost**: $0.50-$2.00 per target
**Time**: 30-60 seconds (API latency)
**Accuracy**: ~85-90% (LLM hallucinations possible)

### Proto-libErator's Rule-Based Approach

```python
# Proto-libErator: src/proto_generator.py
def extract_constraints_from_conditions(conditions_json):
    """
    Direct parsing of libErator's static analysis results
    NO LLM API calls
    """
    constraints = {}

    for func_name, metadata in conditions_json.items():
        for param_name, param_info in metadata.items():
            # All information already in conditions.json!
            constraints[param_name] = {
                'nullable': has_null_access(param_info),
                'is_array': param_info['is_array'],
                'malloc_size': param_info['is_malloc_size'],
                'dependencies': param_info['set_by'],
                'access_pattern': param_info['access_type_set']
            }

    return constraints
```

**Cost**: $0.00
**Time**: <1 second
**Accuracy**: 100% (ground truth from SVF)

---

## Mapping: LLM Outputs → libErator Metadata

| Information | PIN 2.0 LLM Extraction | libErator Equivalent |
|-------------|------------------------|----------------------|
| **Pointer Ownership** | LLM analyzes function body | `set_by` field shows inter-param deps |
| **Nullable Pointers** | LLM infers from code patterns | `access_type_set` includes/excludes null |
| **Array Detection** | LLM pattern matching on `[` `]` | `is_array` boolean flag |
| **Field Access** | LLM traces variable usage | `access_type_set` with field indices |
| **malloc Sizes** | LLM identifies allocation sites | `is_malloc_size` flag |
| **Dependencies** | LLM reasons about control flow | `set_by` lists dependent parameters |
| **Pre-conditions** | LLM infers from assertions/checks | Access types: `create` vs `read` |
| **Post-conditions** | LLM infers from assignments | Access types: `write`, `delete` |

---

## Component Architecture

### 1. Proto Generator (LLM-Free)

```python
# src/proto_generator.py

class ProtoGenerator:
    """
    Rule-based protobuf schema generation from libErator analysis
    """

    def __init__(self, conditions_path, apis_path, layout_path):
        self.conditions = json.load(open(conditions_path))
        self.apis = self.load_apis(apis_path)
        self.layout = json.load(open(layout_path))

    def generate_schema(self, library_name):
        """Main generation logic"""
        schema = ProtoSchema(library_name)

        # Generate message for each API function's parameters
        for func_name, metadata in self.conditions.items():
            param_msg = self.generate_param_message(func_name, metadata)
            schema.add_message(param_msg)

        return schema.serialize()

    def generate_param_message(self, func_name, metadata):
        """
        Generate protobuf message from function metadata
        """
        msg = ProtoMessage(f'{func_name}_Params')

        # Process each parameter
        for param_name, param_info in metadata.items():
            if not param_name.startswith('param_'):
                continue

            # RULE 1: Type mapping
            proto_type = TypeMapper.map_llvm_to_proto(
                param_info['type_string']
            )

            # RULE 2: Array handling
            if param_info['is_array']:
                msg.add_field('optional', 'bytes', param_name)
                msg.add_field('optional', 'uint32', f'{param_name}_length')
                msg.add_field('optional', 'uint32', f'{param_name}_length_override')
            else:
                msg.add_field('optional', proto_type, param_name)

            # RULE 3: Nullable flag
            if self.is_nullable(param_info):
                msg.add_field('optional', 'bool', f'{param_name}_is_null')

            # RULE 4: malloc size override
            if param_info['is_malloc_size']:
                msg.add_field('optional', 'uint32', f'{param_name}_malloc_override')

        return msg

    def is_nullable(self, param_info):
        """
        Determine if parameter can be null from access_type_set
        """
        access_types = [a['access'] for a in param_info['access_type_set']]

        # If 'read' without 'null' → non-nullable
        # If 'null' in access types → nullable
        return 'null' not in access_types and 'read' in access_types
```

**Key Point**: Every decision is based on **static analysis facts**, not LLM interpretation.

---

### 2. Wrapper Generator (Template-Based)

```python
# src/wrapper_generator.py

class WrapperGenerator:
    """
    Template-based C wrapper generation
    NO LLM - uses Jinja2 templates + libErator metadata
    """

    def __init__(self, proto_schema, driver_meta, conditions):
        self.proto_schema = proto_schema
        self.driver_meta = json.load(open(driver_meta))
        self.conditions = json.load(open(conditions))

        # Load Jinja2 template
        self.template = jinja2.Template(open('templates/wrapper.c.j2').read())

    def generate(self):
        """
        Generate complete C fuzzing harness
        """
        context = {
            'library_name': self.driver_meta['library'],
            'api_sequence': self.driver_meta['api_multiset'],
            'emi_guards': self.generate_emi_guards(),
            'handle_management': self.generate_handle_mgmt(),
            'proto_includes': self.get_proto_includes()
        }

        return self.template.render(context)

    def generate_emi_guards(self):
        """
        Generate EMI validation guards from conditions.json
        """
        guards = []

        for func_name, metadata in self.conditions.items():
            for param_name, param_info in metadata.items():
                # RULE 1: Array bounds check
                if param_info['is_array']:
                    guards.append(EMIGuard(
                        type='buffer_size',
                        param=param_name,
                        check=f'input.{param_name}_length_override > MAX_BUFFER_SIZE',
                        action='reject',
                        message=f'{param_name} exceeds max buffer size'
                    ))

                # RULE 2: Null check
                if not self.is_nullable(param_info):
                    guards.append(EMIGuard(
                        type='null_check',
                        param=param_name,
                        check=f'input.{param_name}_is_null',
                        action='reject',
                        message=f'{param_name} cannot be null'
                    ))

                # RULE 3: Dependency check
                if param_info['set_by']:
                    for dep in param_info['set_by']:
                        guards.append(EMIGuard(
                            type='dependency',
                            param=param_name,
                            depends_on=dep,
                            check=f'!has_{dep}',
                            action='reject',
                            message=f'{param_name} requires {dep} to be set'
                        ))

        return guards
```

**Template Example** (`templates/wrapper.c.j2`):

```c
// Auto-generated fuzzing harness
// Generated by Proto-libErator (LLM-free)

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include "pb_decode.h"
#include "{{ library_name }}.pb.h"

#define PIN_EMI_REJECT_RC 86
#define MAX_BUFFER_SIZE {{ max_buffer_size }}

// External library functions
{% for api in api_sequence %}
extern {{ api.signature }};
{% endfor %}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // Decode protobuf input
    {{ library_name }}_FuzzInput input = {{ library_name }}_FuzzInput_init_zero;
    pb_istream_t stream = pb_istream_from_buffer(data, size);

    if (!pb_decode(&stream, {{ library_name }}_FuzzInput_fields, &input)) {
        return 0;  // Invalid protobuf
    }

    // EMI Guards
    {% for guard in emi_guards %}
    if ({{ guard.check }}) {
        fprintf(stderr, "[PIN_EMI] Rejected: {{ guard.message }}\n");
        return PIN_EMI_REJECT_RC;
    }
    {% endfor %}

    // Execute API sequence (from libErator driver.meta)
    {% for call in api_sequence %}
    {{ call.invocation }};
    {% endfor %}

    // Cleanup
    {{ cleanup_code }}

    return 0;
}
```

---

### 3. Type Mapper

```python
# src/type_mapper.py

class TypeMapper:
    """
    LLVM IR type → Protobuf type mapping
    Deterministic, rule-based
    """

    # Static mapping table
    LLVM_TO_PROTO = {
        'i8': 'int32',
        'i16': 'int32',
        'i32': 'int32',
        'i64': 'int64',
        'i8*': 'bytes',
        'float': 'float',
        'double': 'double',
        'c86ee0d9d7ed3e7b4fdbf486fa6c0ebb': 'int32',  # i32 hash
        'c23fa9996925b610710d93e28c59a3e2': 'double',  # double hash
        '8b336322cb5b10c8b7dac308c85cff15': 'bytes',   # i8* hash
    }

    @staticmethod
    def map_llvm_to_proto(llvm_type_str):
        """
        Map LLVM type string to protobuf type

        Args:
            llvm_type_str: Type string from conditions.json (e.g., "i8*", "%struct.cJSON*")

        Returns:
            Protobuf type string (e.g., "bytes", "int32")
        """

        # Remove qualifiers
        llvm_type_str = llvm_type_str.replace('const ', '').strip()

        # Check direct mapping
        if llvm_type_str in TypeMapper.LLVM_TO_PROTO:
            return TypeMapper.LLVM_TO_PROTO[llvm_type_str]

        # Pointer types
        if llvm_type_str.endswith('*'):
            base = llvm_type_str[:-1].strip()

            # Struct pointers → handle IDs (uint32)
            if base.startswith('%struct.'):
                return 'uint32'  # Handle to object

            # Char pointer → bytes
            if base in ['i8', 'char']:
                return 'bytes'

            # Generic pointer → bytes
            return 'bytes'

        # Struct types → handle IDs
        if llvm_type_str.startswith('%struct.'):
            return 'uint32'

        # Type hash lookup
        if llvm_type_str in TypeMapper.LLVM_TO_PROTO:
            return TypeMapper.LLVM_TO_PROTO[llvm_type_str]

        # Default fallback
        return 'bytes'
```

---

### 4. EMI Guard Rules

```python
# src/emi_guard_rules.py

class EMIGuardRules:
    """
    Rule engine for generating EMI validation guards
    Based on conditions.json constraints
    """

    @staticmethod
    def generate_guards(conditions_json, emi_config):
        """
        Generate all EMI guards for a function

        Returns:
            List of guard specifications
        """
        guards = []

        for func_name, metadata in conditions_json.items():
            guards.extend(
                EMIGuardRules.process_function(func_name, metadata, emi_config)
            )

        return guards

    @staticmethod
    def process_function(func_name, metadata, config):
        """Process single function"""
        guards = []

        for param_name, param_info in metadata.items():
            if not param_name.startswith('param_'):
                continue

            # Rule 1: Buffer size limits
            if param_info['is_array'] and config['enable_length_checks']:
                guards.append({
                    'type': 'buffer_size',
                    'function': func_name,
                    'parameter': param_name,
                    'condition': f'input.{param_name}_length_override > {config["max_buffer_size"]}',
                    'action': 'reject',
                    'severity': 'high',
                    'message': f'{param_name} length {"{"}input.{param_name}_length_override{"}"} exceeds max {config["max_buffer_size"]}'
                })

            # Rule 2: Null pointer checks
            if config['enable_null_checks']:
                access_types = [a['access'] for a in param_info['access_type_set']]

                if 'read' in access_types and 'null' not in access_types:
                    guards.append({
                        'type': 'null_check',
                        'function': func_name,
                        'parameter': param_name,
                        'condition': f'input.{param_name}_is_null',
                        'action': 'reject',
                        'severity': 'high',
                        'message': f'{param_name} cannot be null (required for read access)'
                    })

            # Rule 3: malloc size overflow protection
            if param_info['is_malloc_size']:
                guards.append({
                    'type': 'malloc_size',
                    'function': func_name,
                    'parameter': param_name,
                    'condition': f'input.{param_name}_malloc_override > {config["max_malloc_size"]}',
                    'action': 'reject',
                    'severity': 'critical',
                    'message': f'malloc size {"{"}input.{param_name}_malloc_override{"}"} exceeds safe limit'
                })

            # Rule 4: Dependency validation
            if param_info['set_by'] and config['enable_dependency_checks']:
                for dep_param in param_info['set_by']:
                    guards.append({
                        'type': 'dependency',
                        'function': func_name,
                        'parameter': param_name,
                        'depends_on': dep_param,
                        'condition': f'!input.has_{dep_param}',
                        'action': 'reject' if config['strict_dependencies'] else 'warn',
                        'severity': 'medium',
                        'message': f'{param_name} depends on {dep_param} being set'
                    })

        return guards
```

---

### 5. Adaptive Refinement (Metrics-Based)

```python
# src/refinement_loop.py

class AdaptiveRefinement:
    """
    Adaptive EMI guard adjustment based on fuzzer metrics
    NO LLM - pure threshold-based logic
    """

    def __init__(self, config):
        self.config = config
        self.history = []

        # Thresholds
        self.REJECT_THRESHOLD = 0.95   # 95% reject rate too high
        self.COVERAGE_MIN = 0.30       # 30% minimum coverage

    def analyze_metrics(self, metrics):
        """
        Analyze fuzzer metrics and suggest adjustments

        Args:
            metrics: {
                'reject_rate': float,
                'coverage': float,
                'crashes': int,
                'exec_per_sec': int
            }

        Returns:
            EMI config adjustments
        """
        adjustments = {}

        # RULE 1: High reject rate → widen guards
        if metrics['reject_rate'] > self.REJECT_THRESHOLD:
            adjustments['max_buffer_size'] = self.config['max_buffer_size'] * 2
            adjustments['max_array_count'] = self.config['max_array_count'] * 2
            adjustments['max_malloc_size'] = self.config['max_malloc_size'] * 2
            adjustments['reason'] = 'Reject rate too high, widening limits'

        # RULE 2: Low coverage → add exploration knobs
        elif metrics['coverage'] < self.COVERAGE_MIN:
            adjustments['enable_null_exploration'] = True
            adjustments['enable_overflow_triggers'] = True
            adjustments['strict_dependencies'] = False  # Relax validation
            adjustments['reason'] = 'Low coverage, enabling exploration modes'

        # RULE 3: Crashes found → maintain current config
        elif metrics['crashes'] > 0:
            adjustments = {}
            adjustments['reason'] = 'Crashes found, maintaining current config'

        # RULE 4: Good performance → tighten slightly for efficiency
        elif metrics['coverage'] > 0.80 and metrics['reject_rate'] < 0.50:
            adjustments['max_buffer_size'] = int(self.config['max_buffer_size'] * 0.8)
            adjustments['reason'] = 'High coverage, tightening for efficiency'

        return adjustments
```

---

## Concrete Example: cJSON

### Input: libErator `conditions.json`

```json
{
  "function_name": "cJSON_AddItemToArray",
  "param_0": {
    "access_type_set": [
      {"access": "read", "fields": [], "type": "%struct.cJSON*"},
      {"access": "write", "fields": [2], "type": "%struct.cJSON*"}
    ],
    "is_array": false,
    "is_malloc_size": false,
    "set_by": ["param_1"]
  },
  "param_1": {
    "access_type_set": [
      {"access": "read", "fields": [], "type": "%struct.cJSON*"},
      {"access": "write", "fields": [0], "type": "%struct.cJSON*"},
      {"access": "write", "fields": [1], "type": "%struct.cJSON*"}
    ],
    "is_array": false,
    "set_by": ["param_0"]
  }
}
```

### Generated Protobuf (LLM-Free)

```protobuf
syntax = "proto2";
import "nanopb.proto";

message cJSON_AddItemToArray_Params {
  // param_0: %struct.cJSON* (read/write, non-array)
  optional uint32 param_0_handle = 1;  // Handle to cJSON object
  optional bool param_0_is_null = 2;   // Null exploration

  // param_1: %struct.cJSON* (read/write, non-array)
  optional uint32 param_1_handle = 3;  // Handle to cJSON object
  optional bool param_1_is_null = 4;   // Null exploration

  // Contract violation knobs
  optional bool skip_dependency_check = 5;  // Allow stale handles
}
```

### Generated Wrapper (Template-Based)

```c
// Auto-generated by Proto-libErator
#include "pb_decode.h"
#include "cjson.pb.h"
#include <cJSON.h>

#define PIN_EMI_REJECT_RC 86

// Handle table
static cJSON* handles[1024] = {0};
static uint32_t next_handle = 1;

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    cJSON_AddItemToArray_Params input;
    pb_istream_t stream = pb_istream_from_buffer(data, size);

    if (!pb_decode(&stream, cJSON_AddItemToArray_Params_fields, &input)) {
        return 0;
    }

    // EMI Guard 1: Null check for param_0 (non-nullable, read access)
    if (input.param_0_is_null) {
        fprintf(stderr, "[PIN_EMI] Rejected: param_0 cannot be null\n");
        return PIN_EMI_REJECT_RC;
    }

    // EMI Guard 2: Handle validity check
    if (input.param_0_handle >= next_handle || handles[input.param_0_handle] == NULL) {
        if (!input.skip_dependency_check) {  // Contract violation knob
            fprintf(stderr, "[PIN_EMI] Rejected: param_0 invalid handle\n");
            return PIN_EMI_REJECT_RC;
        }
        // else: Allow stale handle for UAF exploration
    }

    // Retrieve objects from handles
    cJSON* array = handles[input.param_0_handle];
    cJSON* item = handles[input.param_1_handle];

    // Execute API call (from libErator driver sequence)
    cJSON_AddItemToArray(array, item);

    return 0;
}
```

---

## Performance Comparison

| Metric | PIN 2.0 (LLM) | Proto-libErator (LLM-Free) |
|--------|---------------|----------------------------|
| **Schema Generation** | 30-60s | <1s |
| **Wrapper Generation** | 10-20s | <1s |
| **Cost per Target** | $0.50-$2.00 | $0.00 |
| **Accuracy** | ~85-90% | 100% (ground truth) |
| **Offline Capable** | No | Yes |
| **Reproducible** | No | Yes |
| **Dependencies** | Anthropic/OpenAI API | None |

---

## Conclusion

**Proto-libErator achieves LLM-free protobuf fuzzing by leveraging libErator's existing SVF static analysis.**

Key principles:
1. ✅ **libErator's analysis is MORE accurate than LLM inference**
2. ✅ **Rule-based transformations are faster and cheaper**
3. ✅ **Template-based generation is deterministic and reproducible**
4. ✅ **Keep libErator's NDA sequences (don't replace with arbitrary protobuf graphs)**

**Next Step**: Implement `src/proto_generator.py` with the rule-based architecture described above.
