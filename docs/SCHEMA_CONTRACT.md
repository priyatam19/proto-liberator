# Proto-libErator Schema Contract (Branch A)

This document defines the **stable protobuf schema contract** produced by `src/proto_generator.py` and consumed by wrapper/harness generation.

## Goals

- Deterministic, LLM-free schema generation from libErator analysis outputs.
- A stable `FuzzInput` top-level message that wrapper code can depend on.
- Support **NDA-generated fixed sequences** while still allowing multiple calls to the same API.

## File Format

- `syntax = "proto2";`
- Always imports `nanopb.proto` for `max_size` / `max_count` options.

## Messages

### `<FunctionName>_Params`

For every function entry in `conditions.json`, a params message is generated:

- Message name: `<FunctionName>_Params` (exact function name plus `_Params`)
- Parameter fields are named `param_<index>` based on `param_0`, `param_1`, ...
- Additional “contract violation knobs” may be appended:
  - `skip_dependency_check` (when any param has `set_by`)
  - `allow_double_delete` (when the function entry has a `return` block)

#### Parameter Field Rules (current)

- If `param_info.is_array`:
  - `optional bytes param_N [(nanopb).max_size = MAX_BYTES_SIZE];`
  - `optional uint32 param_N_length;`
  - `optional uint32 param_N_length_override;`
  - `optional bool param_N_is_null;`
- Else if pointer/struct pointer:
  - Struct pointers are represented as handles:
    - `optional uint32 param_N_handle;`
  - Other pointers are represented as bytes:
    - `optional bytes param_N;`
  - Pointers get:
    - `optional bool param_N_is_null;`
- Else (primitive):
  - `optional <scalar_type> param_N;`

### `FuzzInput` (top-level)

`FuzzInput` is always emitted and provides per-API parameter lists:

```
message FuzzInput {
  optional uint32 global_seed = 1;

  repeated <FuncA>_Params func_a = 2 [(nanopb).max_count = MAX_CALLS_PER_API];
  repeated <FuncB>_Params func_b = 3 [(nanopb).max_count = MAX_CALLS_PER_API];
  ...
}
```

#### Field Naming

- Each repeated field name is derived from the original function name using `utils.to_proto_field_name()`:
  - snake_case
  - lower-case
  - sanitized to `[a-z0-9_]+`

#### Wrapper Consumption Model (required for Branch B)

- The wrapper executes a fixed NDA-generated sequence of calls.
- For each API call, it consumes the “next” params entry from the corresponding repeated field:
  - Maintain `call_index[function_name]` counters.
  - If the list is empty or the index is out of range, the wrapper should use defaults.

## Versioning

This contract is intentionally conservative. Any incompatible changes should:

1. Update this document.
2. Update tests under `tests/`.
3. Bump a schema version field (future work).

