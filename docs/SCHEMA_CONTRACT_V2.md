# Proto-libErator Schema Contract v2 (Dynamic Dispatch “Super Harness”)

This document defines **Schema v2**, which enables a single harness to fuzz **arbitrary API sequences** via dynamic dispatch.

It is intended to replace v1’s “repeated params per function + fixed compile-time sequence” model.

## Goals

- One harness binary can execute **many sequences** without regenerate/recompile.
- Keep libErator’s static analysis as ground truth for parameter shapes and handle semantics.
- Preserve “semantic bug exploration knobs” (allow stale handles, double-delete attempts, etc.).
- Stay nanopb-friendly (bounded repeated fields, explicit `bytes` sizing, proto2 has_*).

## File Format

- `syntax = "proto2";`
- Always import `nanopb.proto`.
- Package: `<library>_fuzzer` (same as v1).

## Message Overview

### Per-function params (same as v1)

For every function in `conditions.json`, the generator emits:

```
message <Func>_Params {
  // param_0, param_1, ... derived from libErator
  // plus optional contract-violation knobs:
  //   optional bool skip_dependency_check;
  //   optional bool allow_double_delete;
}
```

### `Action` (dynamic dispatch oneof)

`Action` chooses exactly one API call variant per element:

```
message Action {
  oneof action {
    <FuncA>_Params func_a = 1;
    <FuncB>_Params func_b = 2;
    ...
  }
}
```

**Field naming**
- Field name inside `Action.oneof action` is derived from the function name using the same normalization as v1:
  - `utils.to_proto_field_name(<FuncName>)`

**Tag assignment (critical for stable builds)**
- Tags must be deterministic:
  - Sort functions by exact function name (bytewise / Python default string sort).
  - Assign tags starting from `1` in that sorted order.

### `FuzzInput` (sequence container)

```
message FuzzInput {
  optional uint32 global_seed = 1;
  repeated Action actions = 2 [(nanopb).max_count = MAX_ACTIONS];
}
```

**`MAX_ACTIONS`**
- Configurable generator flag (default recommendation: `64` or `128`).

## Dynamic Execution Model (Wrapper Requirements)

The wrapper/harness MUST:

1. Decode `FuzzInput` using nanopb.
2. Maintain a **handle table**:
   - `uint32 handle_id -> void* ptr`
   - validity bit for “stale handle” exploration
3. For each `Action` in `actions` (in order):
   - `switch(action.which_action)` (nanopb oneof discriminator)
   - Select the correct `<Func>_Params` struct
   - Convert proto fields -> C arguments
   - Call the function
   - If the function “creates” an object (return access includes `create`), register handle
   - If the function is a destructor, invalidate handle unless `allow_double_delete`

## Conversion Rules (Minimum Viable)

- Scalar: use `has_param_N` then `param_N`
- Handle param: `param_N_handle` selects an entry (mod handle_count); if `param_N_is_null` then pass NULL
- `bytes` / `is_array`:
  - For `char*` parameters: allocate N+1, copy bytes, null-terminate, free after call
  - For other pointer parameters: pass `bytes->bytes` pointer (do not free)
  - Length coupling (future): use `_length` / `_length_override`

## Compatibility / Migration

- v2 is intended to be selectable via `--schema-mode=v2`.
- v1 remains for regression and for libErator-driver-aligned fixed sequences.
- Wrapper generator should support both modes during transition.

## Non-goals (for v2 MVP)

- Perfect dependency satisfaction / cycle handling (handled later via EMI + seed corpus).
- Precise ownership modeling for all libraries (start with handle creation + invalidation).
- Exhaustive type conversions (start with scalars, bytes/strings, handles).

