# Proto-libErator Source Code: Complete Line-by-Line Explanation

This document provides an exhaustive explanation of the proto-liberator source code, focusing on how protobuf schemas are generated from libErator outputs and how a single harness covers an entire library.

---

## Table of Contents

1. [Overview: Data Flow](#overview-data-flow)
2. [Module 1: Proto Generation (`proto_generator.py`)](#module-1-proto-generation)
3. [Module 2: Wrapper/Harness Generation (`wrapper_generator.py`)](#module-2-wrapper-generation)
4. [Module 3: Type Mapping (`type_mapper.py`)](#module-3-type-mapping)
5. [Module 4: Utilities (`utils.py`)](#module-4-utilities)
6. [Module 5: Orchestration (`run_all.py`)](#module-5-orchestration)
7. [Module 6: Templates (Jinja2)](#module-6-templates)

---

## Overview: Data Flow

```
libErator Outputs              Proto-libErator Pipeline              Final Output
┌──────────────────┐          ┌──────────────────────┐            ┌──────────────┐
│ conditions.json  │─────────>│ proto_generator.py   │───────────>│ schema.proto │
│ (API metadata)   │          │ + type_mapper.py     │            │              │
└──────────────────┘          └──────────────────────┘            └──────────────┘
                                         │                                │
┌──────────────────┐                    │                                │
│ apis_clang.json  │────────────────────┘                                │
│ (signatures)     │                                                     │
└──────────────────┘                                                     │
                                                                         │
┌──────────────────┐          ┌──────────────────────┐                  │
│ driver.meta      │─────────>│ wrapper_generator.py │<─────────────────┘
│ (headers, seq)   │          │ + templates/*.j2     │
└──────────────────┘          └──────────────────────┘
                                         │
                                         v
                              ┌──────────────────────┐
                              │ harness.c            │
                              │ (single fuzzer for   │
                              │  entire library)     │
                              └──────────────────────┘
```

**Key Insight**: Proto-liberator transforms **static analysis metadata** into a **structure-aware fuzzing harness** without any LLM involvement. Everything is rule-based and deterministic.

---

## Module 1: Proto Generation

**File**: `src/proto_generator.py`

This module reads libErator's analysis outputs and generates a `.proto` schema file using deterministic transformation rules.

### Lines 1-16: Imports and Module Documentation

```python
#!/usr/bin/env python3
"""
Proto Generator - LLM-Free Protobuf Schema Generation
Transforms libErator's conditions.json to .proto files using rule-based logic
"""
```

**Purpose**: Declares that this is a Python 3 script. The docstring emphasizes **LLM-FREE** - everything is rule-based.

```python
import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
```

- `json`: Parse libErator's JSON outputs
- `argparse`: CLI interface
- `pathlib.Path`: Modern path handling
- `typing`: Type hints for better code quality
- `dataclasses`: Clean data structures

```python
from type_mapper import TypeMapper
from contracts import DEFAULT_MAX_ACTIONS
from utils import load_json, load_text_lines, save_file, to_proto_field_name
```

**Imports from our modules**:
- `TypeMapper`: Converts LLVM types → Protobuf types
- `DEFAULT_MAX_ACTIONS`: Contract constant (64 max actions for v2 schema)
- `utils`: File I/O helpers and name sanitization

---

### Lines 19-66: Data Structures for Protobuf Schema

#### ProtoField (Lines 19-27)

```python
@dataclass
class ProtoField:
    """Represents a protobuf field"""
    label: str  # required/optional/repeated
    type: str   # Protobuf type
    name: str   # Field name
    number: int # Field number
    options: str = ""  # Nanopb options
```

**Purpose**: Represents a single field in a protobuf message.

**Example**:
```protobuf
optional bytes param_0 = 1 [(nanopb).max_size = 65536];
^^^^^^^  ^^^^^  ^^^^^^^  ^  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
label    type    name   num  options
```

**Why we need this**: Protobuf fields have 5 components. This dataclass bundles them together.

#### ProtoOneofField (Lines 29-36)

```python
@dataclass
class ProtoOneofField:
    """Represents a protobuf field within a oneof"""
    type: str
    name: str
    number: int
    options: str = ""
```

**Purpose**: Represents a field inside a `oneof` block (used for v2 dynamic dispatch).

**Why separate from ProtoField**: Oneof fields don't have labels (`optional`/`required`/`repeated`).

#### ProtoOneof (Lines 38-66)

```python
class ProtoOneof:
    """Represents a protobuf oneof block"""

    def __init__(self, name: str):
        self.name = name
        self.fields: List[ProtoOneofField] = []
        self.comments: List[str] = []
```

**Purpose**: Represents a protobuf `oneof` (discriminated union for dynamic dispatch).

**Example**:
```protobuf
oneof action {
  cJSON_Parse_Params cjson_parse = 1;
  cJSON_Delete_Params cjson_delete = 2;
  cJSON_Print_Params cjson_print = 3;
}
```

```python
def add_field(self, proto_type: str, name: str, number: int, options: str = ""):
    self.fields.append(ProtoOneofField(proto_type, name, number, options))
```

**add_field**: Adds a new variant to the oneof.

```python
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
```

**serialize**: Converts the oneof to protobuf syntax with proper indentation.

**Indentation logic**:
- `indent=0`: No indentation (root level)
- `indent=1`: Two spaces (inside a message)
- Fields inside oneof get `indent+1` (four spaces)

---

### Lines 68-126: ProtoMessage Class

```python
class ProtoMessage:
    """Represents a protobuf message"""

    def __init__(self, name: str):
        self.name = name
        self.fields: List[ProtoField] = []
        self.comments: List[str] = []
        self.nested_messages: List['ProtoMessage'] = []
        self.oneofs: List[ProtoOneof] = []
```

**Purpose**: Represents a complete protobuf message definition.

**Data members**:
- `name`: Message name (e.g., `"cJSON_Parse_Params"`)
- `fields`: List of regular fields
- `comments`: Documentation comments
- `nested_messages`: Messages defined inside this message
- `oneofs`: Oneof blocks (for v2 dynamic dispatch)

```python
def add_field(self, label: str, proto_type: str, name: str, options: str = ""):
    """Add a field to this message"""
    field_num = len(self.fields) + 1
    self.fields.append(ProtoField(label, proto_type, name, field_num, options))
```

**add_field**: Adds a field and **auto-increments field number**.

**Why auto-increment**: Protobuf requires unique sequential field numbers. Starting at 1, we increment for each field.

**Example**:
```python
msg.add_field("optional", "bytes", "param_0", "[(nanopb).max_size = 65536]")
# Creates: optional bytes param_0 = 1 [(nanopb).max_size = 65536];

msg.add_field("optional", "uint32", "param_0_length")
# Creates: optional uint32 param_0_length = 2;
```

```python
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
            lines.append("")  # Blank line separator

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
```

**serialize**: Converts message to protobuf syntax with proper structure.

**Structure order**:
1. Comments
2. `message Name {`
3. Nested messages (with blank line separators)
4. Oneofs (with blank line separators)
5. Regular fields
6. `}`

**Why this order**: Protobuf convention is to declare nested types before using them.

---

### Lines 128-160: ProtoSchema Class

```python
class ProtoSchema:
    """Represents a complete protobuf schema file"""

    def __init__(self, package_name: str):
        self.package = package_name
        self.messages: List[ProtoMessage] = []
        self.imports: Set[str] = {'import "nanopb.proto";'}
```

**Purpose**: Represents the entire `.proto` file.

**Why import nanopb.proto**: We use nanopb-specific options like `[(nanopb).max_size = 65536]`.

```python
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
```

**serialize**: Generates the complete `.proto` file content.

**Output structure**:
```protobuf
syntax = "proto2";

package cjson_fuzzer;

import "nanopb.proto";

message cJSON_Parse_Params {
  optional bytes param_0 = 1 [(nanopb).max_size = 65536];
  optional bool param_0_is_null = 2;
}

message cJSON_Delete_Params {
  optional uint32 param_0_handle = 1;
  optional bool param_0_is_null = 2;
  optional bool allow_double_delete = 3;
}

... (78 messages for cJSON)

message FuzzInput {
  optional uint32 global_seed = 1;
  repeated cJSON_Parse_Params cjson_parse = 2 [(nanopb).max_count = 4];
  repeated cJSON_Delete_Params cjson_delete = 3 [(nanopb).max_count = 4];
  ...
}
```

---

### Lines 162-217: ProtoGenerator Class - Initialization

```python
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
```

**Constructor parameters**:
- `conditions_path`: Path to libErator's `conditions.json` (API metadata)
- `apis_path`: Path to libErator's `apis_clang.json` (type signatures)
- `schema_mode`: `"v1"` (fixed sequence) or `"v2"` (dynamic dispatch)
- `max_calls_per_api`: For v1, max repeated calls per API (default: 4)
- `max_actions`: For v2, max actions in sequence (default: 64)
- `max_bytes_size`: Nanopb buffer size limit (default: 64KB)

**What it loads**:
1. `self.conditions`: List of API metadata dicts from libErator
2. `self.apis`: List of function signatures
3. `self.type_mapper`: Type conversion engine

```python
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
```

**load_apis**: Handles 3 different file formats for maximum compatibility.

**Format 1 - JSONL** (libErator default):
```jsonl
{"function_name": "cJSON_Parse", "return_info": {...}, "arguments_info": [...]}
{"function_name": "cJSON_Delete", "return_info": {...}, "arguments_info": [...]}
```

**Format 2 - JSON array**:
```json
[
  {"function_name": "cJSON_Parse", ...},
  {"function_name": "cJSON_Delete", ...}
]
```

**Format 3 - Plain text**:
```
cJSON_Parse
cJSON_Delete
cJSON_Print
```

**Why support multiple formats**: Different libErator versions may output different formats. We want broad compatibility.

---

### Lines 218-251: generate_schema - Main Entry Point

```python
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
```

**Step 1**: Create schema with package name `cjson_fuzzer`.

**Step 2**: Sort functions alphabetically for **deterministic output**.

**Why sort**: Ensures the same input always produces the same `.proto` file (important for reproducibility and diffs).

```python
    function_names: List[str] = []
    for func_entry in func_entries:
        func_name = func_entry.get("function_name") or func_entry.get("functionName")
        if not func_name:
            continue
        function_names.append(func_name)
        schema.add_message(self.generate_param_message(func_name, func_entry))
```

**Step 3**: For each function, generate a `<FuncName>_Params` message.

**Example**: For `cJSON_Parse`, generates:
```protobuf
message cJSON_Parse_Params {
  optional bytes param_0 = 1 [(nanopb).max_size = 65536];
  optional bool param_0_is_null = 2;
}
```

```python
    if self.schema_mode == "v2":
        schema.add_message(self.generate_action_message(function_names))
        schema.add_message(self.generate_fuzz_input_message_v2())
    else:
        schema.add_message(self.generate_fuzz_input_message(function_names))

    return schema
```

**Step 4**: Generate top-level `FuzzInput` message.

**v1 (fixed sequence)**: One repeated field per API.
**v2 (dynamic dispatch)**: `Action` oneof + repeated actions.

---

### Lines 253-277: generate_fuzz_input_message (v1)

```python
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
```

**global_seed**: Optional RNG seed for deterministic fuzzing.

```python
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
```

**For each API**: Add a repeated field with nanopb count limit.

**Example output**:
```protobuf
message FuzzInput {
  optional uint32 global_seed = 1;
  repeated cJSON_Parse_Params cjson_parse = 2 [(nanopb).max_count = 4];
  repeated cJSON_Delete_Params cjson_delete = 3 [(nanopb).max_count = 4];
  repeated cJSON_Print_Params cjson_print = 4 [(nanopb).max_count = 4];
  ...
}
```

**How the harness uses this**:
- The harness has a **fixed call sequence** from `driver.meta`
- Each time it calls `cJSON_Parse`, it consumes the next entry from `message->cjson_parse[]`
- If the array is empty, it uses default values
- This allows calling `cJSON_Parse` up to 4 times in a single fuzz input

---

### Lines 279-316: generate_action_message + generate_fuzz_input_message_v2 (v2)

```python
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
```

**Generates**:
```protobuf
message Action {
  // Dynamic dispatch: exactly one API call variant per Action.
  oneof action {
    cJSON_Parse_Params cjson_parse = 1;
    cJSON_Delete_Params cjson_delete = 2;
    cJSON_Print_Params cjson_print = 3;
    cJSON_AddItemToArray_Params cjson_add_item_to_array = 4;
    ... (78 total for cJSON)
  }
}
```

**What this means**: Each `Action` can be **exactly one** of the 78 API calls.

```python
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
```

**Generates**:
```protobuf
message FuzzInput {
  // Top-level fuzz input (v2). Dynamic sequence of Actions.
  optional uint32 global_seed = 1;
  repeated Action actions = 2 [(nanopb).max_count = 64];
}
```

**What this means**:
- Fuzzer can provide up to 64 actions
- Each action is one of 78 possible API calls
- The sequence is **arbitrary** (not fixed like v1)

**v1 vs v2 comparison**:

**v1 Fixed Sequence**:
```
cJSON_Parse(...)      // Always calls in this order
cJSON_Parse(...)      // Can call same function multiple times
cJSON_Delete(...)
cJSON_Print(...)
cJSON_AddItemToArray(...)
```

**v2 Dynamic Dispatch**:
```
Action 1: cJSON_Parse(...)          // Fuzzer chooses order
Action 2: cJSON_AddItemToArray(...) // Can be any of 78 APIs
Action 3: cJSON_Delete(...)         // Arbitrary sequence
Action 4: cJSON_Parse(...)          // Can repeat
... up to 64 actions
```

**Why v2 is better for coverage**: It can explore arbitrary API sequences, not just the fixed sequence from libErator's NDA algorithm.

---

### Lines 318-426: generate_param_message - Core Transformation Logic

```python
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
```

**Purpose**: For each function, create a `Params` message from libErator metadata.

**Input** (`func_metadata` from conditions.json):
```json
{
  "function_name": "cJSON_AddItemToArray",
  "param_0": {
    "type_string": "%struct.cJSON*",
    "access_type_set": [{"access": "use", "type_string": "%struct.cJSON*"}],
    "set_by": ["cJSON_CreateArray"]
  },
  "param_1": {
    "type_string": "%struct.cJSON*",
    "access_type_set": [{"access": "use", "type_string": "%struct.cJSON*"}],
    "set_by": ["cJSON_Parse", "cJSON_CreateObject"]
  },
  "return": {
    "type_string": "i32",
    "access_type_set": []
  }
}
```

**Step 1**: Find all keys starting with `param_` (param_0, param_1, ...)

**Step 2**: For each parameter, call `_add_parameter_fields`

**Step 3**: Add contract violation knobs (`skip_dependency_check`, `allow_double_delete`)

```python
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
```

**Purpose**: Extract LLVM type string from libErator metadata.

**Fallback logic**:
1. Check `param_info["type_string"]`
2. Check `param_info["type"]`
3. Check `param_info["access_type_set"][0]["type_string"]`
4. Default to `"bytes"`

**Why**: libErator's format varies depending on version and library. We need to handle all cases.

---

### Lines 361-426: _add_parameter_fields - The 5 Transformation Rules

This is the **heart of proto-liberator**: converting libErator's metadata into protobuf fields.

```python
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
```

**Setup**: Get LLVM type and add comment for debugging.

#### **RULE 1: Array Parameters**

```python
    # RULE 1: Array parameters
    if param_info.get('is_array'):
        msg.add_field('optional', 'bytes', param_name,
                      f'[(nanopb).max_size = {self.max_bytes_size}]')
        msg.add_field('optional', 'uint32', f'{param_name}_length')
        msg.add_field('optional', 'uint32', f'{param_name}_length_override')
        msg.add_comment(f'  ↳ Array with explicit length control')
```

**When applied**: `param_info["is_array"] == True`

**Example**: `void process_buffer(const char* data, size_t len)`

**libErator metadata**:
```json
{
  "param_0": {
    "type_string": "i8*",
    "is_array": true
  }
}
```

**Generated proto**:
```protobuf
// param_0: i8*
optional bytes param_0 = 1 [(nanopb).max_size = 65536];
optional uint32 param_0_length = 2;
optional uint32 param_0_length_override = 3;
//   ↳ Array with explicit length control
```

**Why 3 fields**:
1. `param_0`: The actual buffer data
2. `param_0_length`: Natural length of buffer
3. `param_0_length_override`: Override for testing buffer overflows

**Harness usage**:
```c
size_t len = params->has_param_0_length ? params->param_0_length : params->param_0.size;
if (params->has_param_0_length_override) {
    len = params->param_0_length_override;  // Intentional mismatch for bug finding
}
```

#### **RULE 2: Struct Pointer → Handle ID**

```python
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
```

**When applied**: Type is a struct pointer like `%struct.cJSON*`

**Example**: `void cJSON_Delete(cJSON* item)`

**libErator metadata**:
```json
{
  "param_0": {
    "type_string": "%struct.cJSON*",
    "set_by": ["cJSON_Parse", "cJSON_CreateObject"]
  }
}
```

**Type mapper decision**:
```python
TypeMapper.map_llvm_to_proto("%struct.cJSON*") → "uint32"
```

**Generated proto**:
```protobuf
// param_0: %struct.cJSON*
optional uint32 param_0_handle = 1;
//   ↳ Handle to %struct.cJSON* object
```

**Why uint32 handle**:
- Protobuf cannot represent C pointers
- We use a **handle table** (array of pointers) in the harness
- The fuzzer provides a uint32 ID
- Harness looks up `g_handles[id]` to get the actual pointer

**Handle table in harness** (from template):
```c
#define MAX_HANDLES 1024
static void *g_handles[MAX_HANDLES];
static uint32_t g_handle_count = 0;

static uint32_t handle_register(void *ptr) {
    uint32_t id = ++g_handle_count;
    g_handles[id] = ptr;
    return id;
}

static void *handle_get(uint32_t requested) {
    uint32_t idx = handle_select(requested);
    return g_handles[idx];
}
```

**Complete example**:
```c
// Call 1: cJSON_Parse returns a cJSON* object
cJSON* obj = cJSON_Parse("{\"key\":\"value\"}");
uint32_t handle_1 = handle_register(obj);  // Store at ID 1

// Call 2: Fuzzer wants to call cJSON_Delete
// Proto field: param_0_handle = 1
uint32_t hid = params->param_0_handle;  // = 1
cJSON* ptr = handle_get(hid);            // Looks up g_handles[1]
cJSON_Delete(ptr);                       // Calls with correct pointer!
```

**This is how we connect API calls**: The return value of one call becomes the input to another via handles.

#### **RULE 3: Primitive Types**

```python
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
```

**When applied**: Scalar types (int, float, etc.)

**Example**: `int cJSON_GetArraySize(cJSON* array)`

**libErator metadata**:
```json
{
  "param_0": {
    "type_string": "%struct.cJSON*"
  }
}
```

**Generated proto**:
```protobuf
optional uint32 param_0_handle = 1;
```

**Another example**: `void cJSON_SetIntValue(cJSON* object, int val)`

**libErator metadata**:
```json
{
  "param_0": {"type_string": "%struct.cJSON*"},
  "param_1": {"type_string": "i32"}
}
```

**Generated proto**:
```protobuf
optional uint32 param_0_handle = 1;  // Handle
optional int32 param_1 = 2;           // Direct value
```

#### **RULE 4: Nullable Flag**

```python
    # RULE 4: Nullable flag
    if self._is_nullable(param_info, llvm_type):
        msg.add_field('optional', 'bool', f'{param_name}_is_null')
        msg.add_comment(f'  ↳ Nullable exploration knob')
```

**When applied**: Pointers, arrays, or handles

```python
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
```

**Example**: `void cJSON_Delete(cJSON* item)`

**Generated proto**:
```protobuf
optional uint32 param_0_handle = 1;
optional bool param_0_is_null = 2;
//   ↳ Nullable exploration knob
```

**Harness usage**:
```c
bool is_null = params->has_param_0_is_null && params->param_0_is_null;
void *ptr = NULL;
if (!is_null) {
    ptr = handle_get(params->param_0_handle);
}
cJSON_Delete((cJSON*)ptr);  // May intentionally pass NULL for bug finding
```

**Why this matters**: Many bugs happen when NULL is passed to functions expecting valid pointers. This knob lets the fuzzer explore that.

#### **RULE 5: malloc Size Override**

```python
    # RULE 5: malloc size override
    if param_info.get('is_malloc_size'):
        msg.add_field('optional', 'uint32', f'{param_name}_malloc_override')
        msg.add_comment(f'  ↳ malloc size override for overflow testing')
```

**When applied**: libErator marks parameter as a malloc size

**Example**: `void* malloc(size_t size)`

**Generated proto**:
```protobuf
optional uint32 param_0 = 1;
optional uint32 param_0_malloc_override = 2;
//   ↳ malloc size override for overflow testing
```

**Harness usage**:
```c
size_t size = params->param_0;
if (params->has_param_0_malloc_override) {
    size = params->param_0_malloc_override;  // Intentionally wrong size
}
void* ptr = malloc(size);
```

**Use case**: Test for buffer overflow bugs by allocating less memory than code expects.

---

### Lines 427-449: Contract Violation Knobs

```python
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
```

**skip_dependency_check**: Allows using handles that were invalidated (freed).

**Example bug it finds**: Use-after-free

**Normal behavior**:
```c
cJSON* obj = cJSON_Parse("{}");  // Create object, handle=1, valid=true
cJSON_Delete(obj);               // Delete object, valid=false
// If fuzzer tries to use handle=1 again, harness rejects it
```

**With skip_dependency_check=true**:
```c
cJSON* obj = cJSON_Parse("{}");     // handle=1, valid=true
cJSON_Delete(obj);                  // valid=false
// Fuzzer says: skip_dependency_check=true
void* ptr = handle_get(1, true);    // Returns freed pointer!
cJSON_Print((cJSON*)ptr);           // USE-AFTER-FREE! 🐛
```

```python
    # Check if function has returns (for double-free testing)
    if 'return' in func_metadata:
        msg.add_field('optional', 'bool', 'allow_double_delete')
        msg.add_comment('  ↳ Skip double-delete protection')
```

**allow_double_delete**: Allows calling delete/free twice on same handle.

**Example bug it finds**: Double-free

**Normal behavior**:
```c
cJSON* obj = cJSON_Parse("{}");  // handle=1, valid=true
cJSON_Delete(obj);               // valid=false (invalidated)
cJSON_Delete(obj);               // Harness blocks: handle already invalid
```

**With allow_double_delete=true**:
```c
cJSON* obj = cJSON_Parse("{}");      // handle=1, valid=true
cJSON_Delete(obj);                   // Frees memory
// Fuzzer says: allow_double_delete=true, skip_dependency_check=true
void* ptr = handle_get(1, true);     // Returns freed pointer
cJSON_Delete((cJSON*)ptr);           // DOUBLE-FREE! 🐛
```

**Why these are powerful**: These knobs turn the fuzzer from "test valid inputs" to "actively hunt for semantic bugs".

---

## Summary of Proto Generation

**What proto_generator.py does**:

1. **Reads** libErator's `conditions.json` (API metadata) and `apis_clang.json` (signatures)
2. **For each API function**, creates a `<FuncName>_Params` message with fields for:
   - Each parameter (following 5 transformation rules)
   - Contract violation knobs
3. **Creates top-level `FuzzInput` message**:
   - v1: One repeated field per API (fixed sequence)
   - v2: Action oneof + repeated actions (dynamic dispatch)
4. **Outputs** a complete `.proto` file

**No LLM, no heuristics, just deterministic rules based on types and metadata.**

---

