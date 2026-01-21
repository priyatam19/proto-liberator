# Codebase Concerns

**Analysis Date:** 2026-01-21

## Tech Debt

**Broad Exception Handlers (Silent Failures):**
- Issue: Multiple catch-all `except Exception:` clauses silently suppress errors without logging
- Files: `src/proto_generator.py` (lines 264, 447), `src/dependency_index.py` (lines 56, 95), `src/wrapper_generator.py` (lines 99, 344), `src/seed_generator.py` (multiple locations around 405-448, 470, 475, 480)
- Impact: Hard to debug when API loading fails, parameter parsing fails, or payload encoding fails. Users get no indication of what went wrong.
- Fix approach: Replace bare `except Exception:` with specific exception types (JSONDecodeError, ValueError, etc.) and add logging or re-raise with context

**Handle Management Complexity:**
- Issue: Single global handle table for all opaque struct pointers; no type safety enforced
- Files: `src/wrapper_generator.py` (lines 580-600 for handle table building), `templates/wrapper_v2.c.j2`
- Impact: Double-frees and use-after-free bugs can occur if same handle ID is reused across different struct types (e.g., handle 5 for `cJSON*` then for another type). Dependency index tracks type keys but harness uses single table.
- Fix approach: Implement per-type handle tables or validate handle type before dereferencing in generated C code

**Type Mapping Fragility:**
- Issue: LLVM type to protobuf mapping relies on heuristic string patterns and optional `access_type_set` fields
- Files: `src/type_mapper.py` (lines 121-170 for classification), `src/proto_generator.py` (lines 459-474 for type inference)
- Impact: Malformed or non-standard LLVM types silently fall back to `bytes`; struct size lookups may fail and fall back to handle representation instead of layout-aware blob encoding
- Fix approach: Add strict validation mode with warnings for unmapped types; add unit tests covering libErator output variations

**Struct Size Fallback Behavior:**
- Issue: When `data_layout.txt` unavailable or struct not found, struct parameters become generic handles instead of binary blobs
- Files: `src/proto_generator.py` (lines 533-543), `src/type_mapper.py` (lines 121-130)
- Impact: Loss of semantic structure in fuzzing; opaque structs limit effective mutation compared to blob encoding with known size
- Fix approach: Warn when struct size not found; support manual struct size hints via configuration

## Known Bugs

**Crash Classification Overhead:**
- Symptoms: CASR integration generates 4,000+ crash classifications on moderate campaigns; takes significant time and disk
- Files: `scripts/collect_coverage.sh` (harness call integration with CASR), campaign logs
- Trigger: Running fuzzer with in-process fork-on-crash; every unhandled exit generates a crash log
- Workaround: Use CASR clustering to reduce to 20-40 unique buckets; filter NOT_EXPLOITABLE before deep analysis

**EMI Guard Reject Rate Trade-off:**
- Symptoms: Adding strict parameter validation (null checks, range checks) collapses coverage from 78% to 20%
- Files: `src/wrapper_generator.py` (lines 576-600 for guard generation), `src/proto_generator.py` (lines 576-598 for knob generation)
- Trigger: Tight guards block too many valid (but semantically odd) test cases
- Workaround: Use `skip_dependency_check` and `allow_double_delete` knobs to relax guards; tune guard thresholds per library

**Varargs Functions Not Supported:**
- Symptoms: Functions with variadic arguments skip during seed generation; not included in dynamic dispatch
- Files: `src/seed_generator.py` (line 148 filtering), `src/type_mapper.py` (lines 70-87 varargs detection)
- Trigger: Any C library with varargs (printf-like, open with flags, etc.)
- Workaround: `--minimum-apis` flag to exclude varargs; manually add stub handling in templates if needed

## Security Considerations

**Subprocess Execution Without Validation:**
- Risk: `run_all.py` executes protoc, clang, and fuzzer with user-provided paths; no validation of binary signatures
- Files: `src/run_all.py` (lines 45-54 for `_run`, 57-67 for `_run_capture`)
- Current mitigation: No injection protection; relies on caller to provide safe paths
- Recommendations: Validate protoc path exists and is readable before execution; use absolute paths from PATH or explicit config; log command line for audit

**Seed Generation File I/O:**
- Risk: Payloads loaded from JSON with `asset.source` paths; no validation that paths stay within expected directory
- Files: `src/run_all.py` (lines 82-107 for `_copy_seed_assets`), `src/seed_generator.py` (seed payload handling around line 215+)
- Current mitigation: Paths resolved but no validation against symlinks or directory traversal
- Recommendations: Use `Path.resolve()` and verify final path is within expected tree; reject `..` components

**Template-Generated C Code Quality:**
- Risk: Jinja2 templates generate C harness without bounds validation on user-controlled nanopb decode parameters
- Files: `templates/wrapper_v2.c.j2`, `templates/wrapper_lpm.cc.j2` (harness loop bounds)
- Current mitigation: Nanopb `.max_count` and `.max_size` annotations limit inputs, but generator trusts template logic
- Recommendations: Add generated code validation pass; audit template for off-by-one in handle table access

## Performance Bottlenecks

**JSON Parsing Overhead on Large API Sets:**
- Problem: JSONL parsing for `apis_clang.json` done repeatedly without caching
- Files: `src/proto_generator.py` (lines 239-268 `load_apis`), `src/wrapper_generator.py` (lines 104-120 `build_signature_index`)
- Cause: Each tool run re-parses same JSONL; no memoization of loaded state
- Improvement path: Cache parsed JSON in wrapper/orchestrator; pass as in-memory dict between stages in `run_all.py`

**Type Context Loading Redundancy:**
- Problem: Every instance of TypeContext re-reads `data_layout.txt`, `enum_types.txt`, etc.
- Files: `src/type_mapper.py` (lines 89-119 `from_apipass_dir`), `src/proto_generator.py` (line 196), `src/wrapper_generator.py`, `src/seed_generator.py`
- Cause: No module-level cache; each generator/seed object recreates
- Improvement path: Lazy singleton or module-level cache for TypeContext per apipass_dir

**Dependency Index Build Scales O(n²):**
- Problem: Building edges requires iterating all producers×consumers for each type_key
- Files: `src/dependency_index.py` (lines 187-220 edge building)
- Cause: Nested loop over type indices without optimization for sparse graphs
- Improvement path: Use adjacency list instead; only generate edges for feasible (producer, param_idx) pairs

## Fragile Areas

**Schema Contract Evolution:**
- Files: `src/proto_generator.py` (FuzzInput generation), `src/wrapper_generator.py` (harness template logic), `templates/wrapper_v2.c.j2`
- Why fragile: v1 and v2 schemas share some field numbering; adding fields breaks wire compatibility. No version detection in harness.
- Safe modification: Always append new fields at end; increment field numbers consistently; add comment markers in proto files. Validate schema version in harness init.
- Test coverage: `tests/test_proto_generator.py` covers basic message generation but not wire compatibility; `tests/test_wrapper_generator.py` minimal

**Jinja2 Template Context Dictionary:**
- Files: `src/wrapper_generator.py` (lines 715-800+ building context), `templates/wrapper_v2.c.j2`, `templates/wrapper_lpm.cc.j2`
- Why fragile: Context dict built ad-hoc with many optional keys; templates assume keys exist. Missing key silently renders empty string.
- Safe modification: Define context schema as typed dataclass; validate all required keys before rendering; add tests that verify template can access all keys
- Test coverage: Limited; tests use stubs with minimal conditions.json

**Type Mapper Classification Logic:**
- Files: `src/type_mapper.py` (lines 145-250 classify method), `src/proto_generator.py` (lines 475-570 _add_parameter_fields)
- Why fragile: Classification depends on order of LLVM type string pattern matching; overlapping patterns (struct.*, %struct.*, etc.) cause misclassification
- Safe modification: Add comprehensive unit tests for each LLVM type pattern; separate struct detection into dedicated method; document classification order
- Test coverage: `src/type_mapper.py` line 479 has TODO comment; no test_mapper.py in test suite

## Scaling Limits

**Fuzzer Crash Volume:**
- Current capacity: ~4,000 crashes per 24-hour cJSON campaign
- Limit: Manual triage infeasible; CASR clustering helps but still O(crashes)
- Scaling path: Implement per-function coverage tracking to prioritize crashes by location; use AFL's crash dedup hashes; integrate with continuous crash monitoring (S3 upload, Slack alerts)

**Handle Table Size:**
- Current capacity: Hard-coded single global array in generated C code
- Limit: If library allocates >1000 distinct objects simultaneously, handle allocation wraps or fails
- Scaling path: Make handle table size configurable via proto field or config file; support per-type tables for larger libraries

**Protobuf Message Size:**
- Current capacity: Nanopb `.max_size` for bytes fields set to 65536 bytes
- Limit: Some libraries (image codecs, parsers) need larger buffers
- Scaling path: Per-parameter configurable max_size in conditions.json or auto-infer from typical input sizes

**API Count:**
- Current capacity: Schema generation and harness generation both O(num_apis)
- Limit: >500 APIs per library creates large proto files and wrapper code
- Scaling path: Partition APIs into multiple proto files; generate multiple harnesses per campaign; use API scheduling to select subset per seed

## Dependencies at Risk

**Nanopb Version Lock:**
- Risk: Project depends on specific nanopb version in `external/nanopb/`; generator tuned to nanopb syntax
- Impact: Upgrading nanopb may break `.max_size` annotation syntax or generated field ordering
- Migration plan: Pin nanopb version in documentation; add nanopb version check in `run_all.py`; maintain compatibility layer if syntax changes

**Jinja2 Template Syntax:**
- Risk: Template changes (filter names, context assumptions) cause silent generation failures
- Impact: Template syntax errors produce no harness code; subsequent compile fails with cryptic error
- Migration plan: Validate template renders before saving; add `strict=True` to Jinja2 environment to catch undefined variables

**libprotobuf-mutator (LPM) Stability:**
- Risk: LPM integration new (January 2025); limited test coverage vs nanopb path
- Impact: LPM harness may silently fail to mutate complex messages or crash on edge cases
- Migration plan: Run `tests/test_compile_v2.sh` before deploying LPM mode; add integration test with real library

## Missing Critical Features

**No Schema Validation Before Code Generation:**
- Problem: Generated .proto file not validated with protoc before wrapper generation
- Blocks: Silent generation of invalid C code; failures discovered at compile time with poor error messages
- Recommendation: Add `--validate-schema` flag; run protoc --lint before handing to nanopb

**No Harness Compilation Validation:**
- Problem: Generated C code not compiled in test before fuzzer build
- Blocks: Large delays discovering compilation errors; no fast feedback on schema changes
- Recommendation: Add separate `--compile-harness-only` phase; parallelize harness compilation

**No Instrumentation Configuration UI:**
- Problem: Coverage flags (trace-cmp, trace-gep) hardcoded in scripts or require manual flags
- Blocks: A/B testing different instrumentation levels requires script edits
- Recommendation: Add `--instrumentation-preset [base|cmp|gep|full]` to `run_campaign.sh`

**No Per-Function Coverage Feedback:**
- Problem: Campaign reports total branch coverage; no view of which functions are under-explored
- Blocks: Difficult to identify coverage gaps or guide seed corpus generation
- Recommendation: Integrate gcov output parsing; report coverage by function; prioritize fuzzer focus

## Test Coverage Gaps

**Untested: Large LLVM Type Strings:**
- What's not tested: Types with nested generics, incomplete types, type hashes
- Files: `src/type_mapper.py` (classify method), tests missing
- Risk: Real libErator outputs with complex types silently mismapped; only discovered in fuzzer crashes
- Priority: High - Add parametrized tests for each LLVM type pattern

**Untested: Malformed conditions.json:**
- What's not tested: Missing function_name, param_N with gaps (param_0, param_2, no param_1), invalid access_type_set
- Files: `src/proto_generator.py` (parsing), `src/wrapper_generator.py` (indexing)
- Risk: Cryptic errors or wrong schema when real conditions.json has formatting issues
- Priority: High - Add validation with clear error messages

**Untested: Template Rendering Edge Cases:**
- What's not tested: Many contract knobs (skip_dependency_check, allow_double_delete), v2 Action dispatch with 100+ functions
- Files: `templates/wrapper_v2.c.j2`, `tests/test_wrapper_generator.py` minimal
- Risk: Template buffer overflows or logic errors at scale not caught until fuzzer runs
- Priority: Medium - Add integration tests with large APIs count

**Untested: Seed Generator Wire Encoding:**
- What's not tested: Correctness of varint encoding, nested message encoding, oneof field dispatch
- Files: `src/seed_generator.py` (lines 39-66 wire encoding), tests sparse
- Risk: Generated seeds don't decode correctly; fuzzer reports "invalid input" without clear reason
- Priority: Medium - Add roundtrip tests (encode→decode→encode, must match)

**Untested: Error Recovery in run_all.py:**
- What's not tested: Partial pipeline failure (e.g., protoc fails, but harness generation attempted); resumption
- Files: `src/run_all.py` (orchestrator), no test for CalledProcessError handling
- Risk: Failed campaigns leave inconsistent state; no way to resume from checkpoint
- Priority: Low - Add optional `--resume` flag; detect generated artifacts before re-running

---

*Concerns audit: 2026-01-21*
