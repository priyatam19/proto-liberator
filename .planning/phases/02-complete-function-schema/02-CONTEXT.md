# Phase 2: Complete Function Schema Generation - Context

**Gathered:** 2026-01-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Modify proto_generator to include ALL exported functions in the protobuf schema, not just the NDA-selected subset. Handle edge cases for unsupported parameter types. Generate complete schemas for all 3 targets (cJSON, libpcap, libaom) and validate they compile.

</domain>

<decisions>
## Implementation Decisions

### Function Inclusion Criteria
- Include ALL functions from apis_clang.json — let the fuzzer decide what's reachable
- For functions WITHOUT constraints (like libaom's 196 macro-generated ones): infer parameters from signature using TypeMapper defaults
- Trust apis_clang.json filtering — include everything, don't apply additional internal/helper filters
- Generate complete schemas for all 3 targets equally, even if libaom coverage will be limited

### Varargs Handling
- Stub varargs functions with fixed max args (e.g., up to 8 optional bytes fields)
- Include the non-vararg parameters normally, add repeated bytes for varargs portion
- Don't skip varargs functions — attempt best-effort fuzzing

### Function Pointer Parameters
- Include as opaque uint64 field in the protobuf message
- Harness ignores the fuzzer-provided value and uses a fixed no-op stub
- Don't skip functions with callbacks — they can still exercise other parameters

### void* Parameter Handling
- Context-dependent mapping based on conditions.json access_type:
  - `read` access → map to `bytes` (fuzzer provides data)
  - `create` access → map to `uint32` handle (requires prior allocation)
  - Unknown/missing → default to `bytes`

### Unmappable Types Fallback
- Use `bytes` as universal fallback for unions, multi-dimensional arrays, etc.
- Don't skip fields or functions — attempt best-effort with raw bytes
- Log warnings during generation for visibility

### Claude's Discretion
- Exact number of varargs stub fields (4, 8, or 16)
- Specific TypeMapper implementation details
- Warning/logging format and verbosity
- Order of function processing

</decisions>

<specifics>
## Specific Ideas

- Phase 1 gap analysis provides exact counts: 78 cJSON, 99 libpcap, 243 libaom functions
- libaom's 196 missing constraints are `aom_codec_control_typechecked_*` macro functions — will use signature inference
- libpcap's 11 missing are option/remote APIs — signature inference applies
- cJSON has 100% constraints — will serve as validation reference

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-complete-function-schema*
*Context gathered: 2026-01-22*
