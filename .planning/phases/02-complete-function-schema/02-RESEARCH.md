# Phase 2: Complete Function Schema Generation - Research

**Researched:** 2026-01-22
**Domain:** Protobuf schema generation, LLVM type mapping, libErator output processing
**Confidence:** HIGH

## Summary

This research investigates how to extend `proto_generator.py` to include ALL exported functions from `apis_clang.json` in the generated protobuf schema, rather than just functions with constraints in `conditions.json`. The key findings:

1. **Existing architecture already supports this** via `--include-missing-apis` flag, which merges apis_clang entries into conditions using `_stub_condition_from_api()`
2. **TypeMapper has comprehensive coverage** for standard C types via `clang_type_to_llvmish()` in utils.py
3. **Varargs detection exists** via `TypeContext.vararg_functions` loaded from `apis_llvm.json`
4. **Function pointers and callbacks** need new handling - currently mapped as `bytes` but should be `uint64` per CONTEXT.md

**Primary recommendation:** Use the existing `--include-missing-apis` flag as foundation, enhance type inference for edge cases (varargs, function pointers, void*), and add validation/logging for unmappable types.

## Standard Stack

The implementation uses existing components with modifications:

### Core Modules (No External Dependencies)

| Module | Purpose | Modification Needed |
|--------|---------|---------------------|
| `proto_generator.py` | Schema generation | Enhance `_stub_condition_from_api()`, add varargs support |
| `type_mapper.py` | LLVM->Proto mapping | Add function pointer detection, void* context handling |
| `utils.py` | Type conversion helpers | Enhance `clang_type_to_llvmish()` for edge cases |
| `wrapper_generator.py` | Harness generation | Handle new field types (uint64 for callbacks, varargs) |

### Supporting Utilities (Already Present)

| Utility | Purpose | Changes |
|---------|---------|---------|
| `contracts.py` | Shared constants | Add SUFFIX_VARARG if needed |
| `TypeContext` | Type metadata | Already loads `apis_llvm.json` for varargs |

## Architecture Patterns

### Current Function Inclusion Flow

```
apis_clang.json ─────┐
                     ├──> ProtoGenerator.generate_schema() ──> .proto
conditions.json ────┘
                            │
                            ├── For each entry in conditions:
                            │     generate_param_message()
                            │
                            └── (if include_missing_apis)
                                  _merge_conditions_with_apis()
                                  _stub_condition_from_api()
```

### Key Code Paths

**1. API Enumeration (proto_generator.py:238-268)**
```python
def load_apis(apis_path: Path) -> List[Dict]:
    # JSONL format: one JSON object per line
    for line in load_text_lines(apis_path):
        apis.append(json.loads(line))
    return apis
```

**2. Missing API Stubbing (proto_generator.py:270-311)**
```python
def _merge_conditions_with_apis(self, conditions: object) -> object:
    # Merges apis_clang entries not in conditions
    for api in self.apis:
        name = api.get("function_name")
        if not name or name in cond_by_name:
            continue
        cond_by_name[name] = self._stub_condition_from_api(api)
    return list(cond_by_name.values())

def _stub_condition_from_api(self, api: Dict) -> Dict:
    # Creates minimal condition entry from signature
    entry: Dict = {"function_name": name}
    args = api.get("arguments_info")
    if isinstance(args, list):
        for idx, arg in enumerate(args):
            c_type = str(arg.get("type_clang") or "")
            llvmish = clang_type_to_llvmish(c_type)
            param_info: Dict = {"type_string": llvmish}
            if clang_pointer_is_bytes(c_type):
                param_info["is_array"] = True
            entry[f"param_{idx}"] = param_info
    # Return type handling
    ret_info = api.get("return_info")
    if isinstance(ret_info, dict):
        ret_type = str(ret_info.get("type_clang") or "")
        if ret_type:
            entry["return"] = {"type_string": clang_type_to_llvmish(ret_type)}
    return entry
```

**3. Type Inference (utils.py:169-246)**
```python
def clang_type_to_llvmish(type_str: str) -> str:
    # Converts Clang type to LLVM-style type string
    # Handles: struct pointers, enums, primitive pointers, scalars

    if base.startswith("struct "):
        name = base[len("struct "):].strip()
        return f"%struct.{name}*" if is_ptr else "i32"

    if is_ptr and base in {"char", "unsigned char", "uint8_t", "void", ...}:
        return "i8*"

    # Function pointers
    if "(" in clean or ")" in clean:
        return "i8*"  # ISSUE: Should be uint64 per CONTEXT.md
```

### Recommended Architecture Changes

```
                                       ┌──────────────────────────┐
apis_clang.json ───────────────────────┤                          │
                                       │  ProtoGenerator          │
conditions.json ───────────────────────┤                          │
                                       │  (enhanced)              │
                   ┌───────────────────┤                          │
apis_llvm.json ────┤ TypeContext       │  - All functions mode    │
                   │ (varargs)         │  - Varargs stub fields   │
                   └───────────────────┤  - Callback uint64       │
                                       │  - void* context-aware   │
                                       └──────────────────────────┘
```

### Pattern: Stub Condition Generation

For functions WITHOUT constraints in conditions.json, generate stub entries:

```python
# Input: apis_clang.json row
{
  "function_name": "aom_codec_control_typechecked_AV1E_SET_GF_CBR_BOOST_PCT",
  "return_info": {"type_clang": "aom_codec_err_t"},
  "arguments_info": [
    {"type_clang": "aom_codec_ctx_t *"},
    {"type_clang": "unsigned int"}
  ]
}

# Output: conditions.json-style stub
{
  "function_name": "aom_codec_control_typechecked_AV1E_SET_GF_CBR_BOOST_PCT",
  "param_0": {"type_string": "%struct.aom_codec_ctx_t*"},
  "param_1": {"type_string": "i32"},
  "return": {"type_string": "i32"}
}
```

### Anti-Patterns to Avoid

- **Skipping functions entirely:** Per CONTEXT.md, attempt best-effort for all functions
- **Ignoring varargs:** Stub with fixed max args, don't skip
- **Treating callbacks as bytes:** Use uint64 with no-op stub per decisions
- **Single-source inference:** Prefer conditions.json when available, fallback to apis_clang

## Don't Hand-Roll

Problems with existing solutions in the codebase:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Type conversion | New type mapper | `clang_type_to_llvmish()` | Already handles most cases |
| Varargs detection | Parse signatures | `TypeContext.vararg_functions` | Loaded from apis_llvm.json |
| API enumeration | New loader | `ProtoGenerator.load_apis()` | Handles JSONL format |
| Missing API merge | New mechanism | `_merge_conditions_with_apis()` | Existing `--include-missing-apis` |

## Common Pitfalls

### Pitfall 1: Schema Field Numbering Mismatch

**What goes wrong:** Seed generator and wrapper generator use different field numbers than proto_generator
**Why it happens:** Each generator independently enumerates parameters
**How to avoid:**
- All three must use identical ordering: `sorted(conditions.keys())` for functions
- Parameters must be in param_0, param_1, ... order
**Warning signs:** Seed corpus doesn't decode properly; harness crashes on valid inputs

### Pitfall 2: Varargs Handling Breaking Downstream

**What goes wrong:** Adding varargs fields changes schema, breaks existing corpus
**Why it happens:** Varargs stub fields add new field numbers
**How to avoid:**
- Keep stub fields at end of message (high field numbers)
- Mark varargs functions clearly in schema comments
- Consider separate Action oneof variants for varargs vs non-varargs calls
**Warning signs:** Proto decode errors after schema update

### Pitfall 3: Function Pointer Type Confusion

**What goes wrong:** Callbacks mapped as bytes, harness tries to call garbage pointer
**Why it happens:** Current `clang_type_to_llvmish()` returns `i8*` for function pointers
**How to avoid:**
- Detect function pointer types: `(` and `)` in type string
- Map to `uint64` in schema per CONTEXT.md decision
- Wrapper ignores value, uses fixed no-op stub
**Warning signs:** SIGSEGV in callback paths

### Pitfall 4: void* Context Loss

**What goes wrong:** All void* become bytes, missing handle relationships
**Why it happens:** Stub generation has no access_type_set context
**How to avoid:**
- Use `bytes` as default per CONTEXT.md
- Document that inferred void* loses semantic information
- Consider heuristics: param named "ctx" or "handle" likely needs handle treatment
**Warning signs:** Handle-based APIs fail with NULL when they need prior allocation

### Pitfall 5: Struct Name Normalization

**What goes wrong:** `struct foo_t *` and `struct foo *` treated as different types
**Why it happens:** TypeMapper normalizes but gaps exist
**How to avoid:** Use `TypeMapper.extract_struct_name()` consistently
**Warning signs:** Multiple handle tables for what should be same type

## Code Examples

### Example 1: Enhanced _stub_condition_from_api with varargs

```python
# Source: Current implementation + enhancement
def _stub_condition_from_api(self, api: Dict) -> Dict:
    name = api.get("function_name") or ""
    entry: Dict[str, object] = {"function_name": name}

    # Check if vararg via TypeContext
    is_vararg = name in self.type_context.vararg_functions

    args = api.get("arguments_info") if isinstance(api, dict) else None
    if isinstance(args, list):
        for idx, arg in enumerate(args):
            if not isinstance(arg, dict):
                continue
            c_type = str(arg.get("type_clang") or "")

            # Detect function pointers
            if self._is_function_pointer_type(c_type):
                param_info: Dict[str, object] = {"type_string": "uint64", "_is_callback": True}
            else:
                llvmish = clang_type_to_llvmish(c_type)
                param_info = {"type_string": llvmish}
                if clang_pointer_is_bytes(c_type):
                    param_info["is_array"] = True

            entry[f"param_{idx}"] = param_info

    # Add varargs stub fields (up to 8)
    if is_vararg:
        entry["_is_vararg"] = True
        for i in range(8):
            entry[f"vararg_{i}"] = {"type_string": "i8*", "is_array": True, "_is_vararg_field": True}

    # Return type
    ret_info = api.get("return_info") if isinstance(api, dict) else None
    if isinstance(ret_info, dict):
        ret_type = str(ret_info.get("type_clang") or "")
        if ret_type:
            entry["return"] = {"type_string": clang_type_to_llvmish(ret_type)}

    return entry

def _is_function_pointer_type(self, c_type: str) -> bool:
    """Detect function pointer types from Clang type string."""
    # Pattern: "void (*)(int, int)" or "int (*callback)(void *)"
    clean = c_type.replace("const ", "").strip()
    return "(*" in clean or ("(" in clean and "*)" in clean)
```

### Example 2: Generate Params Message with Varargs

```python
# Source: Enhanced generate_param_message
def generate_param_message(self, func_name: str, func_metadata: Dict) -> ProtoMessage:
    msg = ProtoMessage(f'{func_name}_Params')
    msg.add_comment(f'Parameters for {func_name}')

    # Regular parameters (existing logic)
    param_items = [(int(k.split("_", 1)[1]), v)
                   for k, v in func_metadata.items()
                   if k.startswith("param_") and isinstance(v, dict)]

    for idx, param_info in sorted(param_items):
        self._add_parameter_fields(msg, str(idx), param_info)

    # Varargs stub fields
    if func_metadata.get("_is_vararg"):
        msg.add_comment('')
        msg.add_comment('Varargs stub fields (best-effort)')
        for i in range(8):  # Fixed max 8 varargs
            msg.add_field('optional', 'bytes', f'vararg_{i}',
                         f'[(nanopb).max_size = {self.max_bytes_size}]')

    # Contract violation knobs
    self._add_contract_violation_knobs(msg, func_metadata)

    return msg
```

### Example 3: Wrapper Generator Handling Callbacks

```python
# Source: Enhanced wrapper_generator.py argument conversion
{% if arg.param._is_callback %}
// Callback parameter: use no-op stub
arg{{ arg.i }} = ({{ arg.c_type }})NULL;  // Fuzzer cannot provide valid function pointer
{% endif %}
```

### Example 4: Validation and Logging

```python
# Source: New helper for visibility into unmapped types
def generate_schema(self, library_name: str) -> ProtoSchema:
    schema = ProtoSchema(f"{safe_lib}_fuzzer", mutation_mode=self.mutation_mode)

    unmapped_types = []
    callback_functions = []
    vararg_functions = []

    for func_entry in func_entries:
        func_name = func_entry.get("function_name")

        # Track edge cases
        if func_entry.get("_is_vararg"):
            vararg_functions.append(func_name)

        for k, v in func_entry.items():
            if k.startswith("param_") and isinstance(v, dict):
                if v.get("_is_callback"):
                    callback_functions.append(f"{func_name}:{k}")
                if v.get("_unmapped"):
                    unmapped_types.append(f"{func_name}:{k}:{v.get('_original_type')}")

        schema.add_message(self.generate_param_message(func_name, func_entry))

    # Log summary
    if unmapped_types:
        print(f"[Proto-libErator] Warning: {len(unmapped_types)} unmapped types -> bytes")
        for ut in unmapped_types[:10]:
            print(f"  - {ut}")
    if callback_functions:
        print(f"[Proto-libErator] Note: {len(callback_functions)} callback parameters -> uint64/no-op")
    if vararg_functions:
        print(f"[Proto-libErator] Note: {len(vararg_functions)} varargs functions -> stub fields")

    return schema
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| conditions.json only | --include-missing-apis flag | Existing | Allows full function coverage |
| Skip varargs | Stub with max args | Phase 2 | Better libaom coverage |
| Callbacks as bytes | Callbacks as uint64 | Phase 2 | Safer harness execution |

**Deprecated/outdated:**
- None identified - existing infrastructure is sound, needs enhancement

## Open Questions

Things that couldn't be fully resolved:

1. **Optimal varargs stub count**
   - What we know: CONTEXT.md suggests 8 as reasonable
   - What's unclear: Performance impact, corpus size implications
   - Recommendation: Start with 8, make configurable via CLI flag

2. **void* heuristics**
   - What we know: CONTEXT.md says default to bytes
   - What's unclear: When heuristics (param name "ctx", "handle") should override
   - Recommendation: Default to bytes per decision, document limitation

3. **Callback no-op implementation**
   - What we know: uint64 field, harness uses NULL
   - What's unclear: Some callbacks are mandatory (pcap_loop requires handler)
   - Recommendation: Document which APIs are non-functional due to callbacks

## Sources

### Primary (HIGH confidence)
- `/home/priyatam/pin_compete/tools/proto-liberator.ehnace-harness/src/proto_generator.py` - Full code review
- `/home/priyatam/pin_compete/tools/proto-liberator.ehnace-harness/src/type_mapper.py` - Full code review
- `/home/priyatam/pin_compete/tools/proto-liberator.ehnace-harness/src/wrapper_generator.py` - Full code review
- `/home/priyatam/pin_compete/tools/proto-liberator.ehnace-harness/src/utils.py` - Type conversion helpers
- `/home/priyatam/pin_compete/tools/proto-liberator.ehnace-harness/.planning/phases/02-complete-function-schema/02-CONTEXT.md` - User decisions

### Secondary (MEDIUM confidence)
- `/home/priyatam/pin_compete/tools/proto-liberator.ehnace-harness/.planning/phases/01-baseline-gap-analysis/DELIVERABLES.md` - Gap counts
- `/home/priyatam/pin_compete/tools/proto-liberator.ehnace-harness/analysis/libpcap/work/apipass/apis_clang.json` - Sample JSONL format
- `/home/priyatam/pin_compete/tools/proto-liberator.ehnace-harness/analysis/libpcap/work/apipass/apis_llvm.json` - Varargs detection format

### Tertiary (LOW confidence)
- None - all findings verified against codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Direct codebase analysis
- Architecture: HIGH - Full code path tracing
- Pitfalls: HIGH - Based on observed code patterns and documented contracts

**Research date:** 2026-01-22
**Valid until:** 2026-02-22 (30 days - stable codebase)

## Implementation Summary

### Changes Required by File

| File | Changes | Effort |
|------|---------|--------|
| `proto_generator.py` | Enhance `_stub_condition_from_api()`, add varargs support, logging | MEDIUM |
| `utils.py` | Add `_is_function_pointer_type()` helper | LOW |
| `type_mapper.py` | No changes needed | NONE |
| `wrapper_generator.py` | Handle callback uint64, varargs fields in template | MEDIUM |
| `templates/wrapper_v2.c.j2` | Add callback no-op, varargs handling | MEDIUM |
| `seed_generator.py` | May need varargs field encoding | LOW |

### CLI Changes

```
--include-missing-apis  # Already exists, becomes default mode
--varargs-max N         # New: max vararg stub fields (default: 8)
--log-unmapped          # New: verbose logging of unmapped types
```

### Testing Strategy

1. **cJSON (reference):** 100% constraint coverage - validate no regressions
2. **libpcap:** Verify 11 missing functions now included
3. **libaom:** Verify 196 macro functions now included (signature inference)
4. **Compile test:** All generated harnesses must compile
5. **Fuzz test:** 60s smoke test per target without harness crashes
