# Architecture

**Analysis Date:** 2026-01-21

## Pattern Overview

**Overall:** Rule-based LLM-free pipeline orchestration with schema versioning and template-based code generation.

**Key Characteristics:**
- Purely deterministic transformations (no LLM involvement)
- Two schema contract versions: v1 (fixed sequence) and v2 (dynamic dispatch)
- Template-based harness generation using Jinja2
- Externally-driven (consumes libErator outputs, does not run analysis)
- Modular layering: type mapping → schema generation → harness generation → orchestration

## Layers

**Input/Analysis Layer:**
- Purpose: Receive libErator static analysis outputs
- Location: External (not in this repo)
- Contains: `conditions.json`, `apis_clang.json`, `driver.meta` files
- Depends on: libErator tool (external)
- Used by: Type mapper, proto generator, wrapper generator

**Type Mapping Layer:**
- Purpose: Convert LLVM IR types to protobuf types deterministically
- Location: `src/type_mapper.py`
- Contains: `TypeMapper` class, `TypeContext` for per-target type data
- Depends on: `conditions.json` for access metadata; optional apipass artifacts
- Used by: Proto generator, wrapper generator, seed generator

**Schema Generation Layer:**
- Purpose: Create `.proto` files from function metadata
- Location: `src/proto_generator.py`
- Contains: `ProtoGenerator` class, message builders (`ProtoMessage`, `ProtoOneof`, `ProtoField`)
- Depends on: Type mapper for type conversion; `utils` for naming
- Used by: Orchestrator; produces `.proto` files consumed by nanopb/protoc
- Modes: v1 (fixed sequence per `driver.meta`), v2 (dynamic dispatch with Action.oneof)

**Wrapper/Harness Generation Layer:**
- Purpose: Generate C/C++ fuzzing harness from schema and libErator metadata
- Location: `src/wrapper_generator.py`
- Contains: `WrapperGenerator` class, EMI guard logic, handle management
- Depends on: Generated `.proto`, `driver.meta` (v1), `conditions.json`, type mapper
- Used by: Orchestrator; produces harness C/C++ source files
- Templates: `templates/wrapper.c.j2`, `templates/wrapper_lpm.cc.j2`, `templates/wrapper_v2.c.j2`

**Seed Generation Layer:**
- Purpose: Create valid input corpus for v2 super-harness
- Location: `src/seed_generator.py`
- Contains: Wire-only protobuf encoding, dependency-aware scheduling, action sequencing
- Depends on: `conditions.json`, dependency index, type mapper
- Used by: Orchestrator; produces binary seed files
- Modes: wire-only (no python-protobuf), optional protobuf-python, optional dependency scheduling

**Dependency Analysis Layer:**
- Purpose: Build lightweight dependency index for handle/type tracking
- Location: `src/dependency_index.py`, `src/scheduler.py`
- Contains: `DependencyIndex` class, `schedule_sequence()` for insertion of missing setup calls
- Depends on: `conditions.json` (function metadata), type mapper
- Used by: Seed generator (optional), orchestrator (for Phase 1 analysis)
- Optional: Used only when `--dependency-index` or `--schedule-seeds` flags enabled

**Utility/Constants Layer:**
- Purpose: Shared utilities and cross-module constants
- Location: `src/utils.py`, `src/contracts.py`, `src/emi_guard_rules.py`
- Contains: Naming functions, file I/O, schema field name contracts
- Used by: All other layers

**Orchestration Layer:**
- Purpose: Coordinate full pipeline with option handling and build integration
- Location: `src/run_all.py`
- Contains: Command dispatch, file management, compiler invocation (protoc/clang/clang++)
- Depends on: All generation layers
- Used by: User scripts (`scripts/run_campaign.sh`), manual CLI invocation

**Build Integration Layer:**
- Purpose: Compile fuzzer executable with coverage instrumentation
- Location: `scripts/build_proto_fuzzer.sh`
- Contains: nanopb C bindings generation, clang/clang++ invocation, ASAN/coverage flags
- Depends on: Generated harness C/C++, target library, external dependencies
- Used by: Orchestrator, campaign scripts

**Fuzzing/Coverage Layer:**
- Purpose: Run fuzzer campaigns and collect coverage metrics
- Location: `scripts/run_campaign.sh`, `scripts/collect_coverage.sh`
- Contains: Fuzzer invocation, crash clustering, coverage instrumentation
- Depends on: Compiled fuzzer binary, seed corpus
- Used by: User for empirical testing

## Data Flow

**Primary Pipeline (v1 fixed-sequence):**

1. libErator produces `conditions.json`, `apis_clang.json`, `driver.meta`
2. Orchestrator (`run_all.py`) validates inputs, resolves paths
3. Proto Generator reads `conditions.json` + `apis_clang.json`, generates `params.proto` (v1 schema)
4. Protoc compiles `params.proto` → nanopb C bindings (`params.pb.c`, `params.pb.h`)
5. Wrapper Generator reads:
   - Generated `.proto` (for field names)
   - `driver.meta` (API sequence, headers)
   - `conditions.json` (parameter constraints, EMI guards)
   - Templates
6. Wrapper Generator outputs `harness.c` with fixed nanopb decode loop
7. Clang compiles harness + nanopb bindings + target library → `fuzzer` binary
8. Fuzzer runs, mutates protobuf inputs via libprotobuf-mutator, feeds to library

**Primary Pipeline (v2 dynamic-dispatch super-harness):**

1. Same inputs as v1
2. Proto Generator generates `params_v2.proto` with `Action.oneof` and `repeated actions` field
3. Protoc generates nanopb bindings
4. Wrapper Generator uses `templates/wrapper_v2.c.j2` for dynamic dispatch loop
5. Seed Generator (optional) creates `corpus/*.seed` files using wire-only encoding
6. Compiler and fuzzer as in v1
7. Fuzzer decides API call order at runtime (explores call-order space)

**Optional Phase 1 (Dependency Index):**

1. Orchestrator runs `dependency_index.py` to analyze handle/type dependencies
2. Outputs `dependency_index.json` with producers, consumers, type keys
3. Used by seed generator for `--schedule-seeds` mode
4. Scheduler inserts missing setup calls (e.g., create before use)

**State Management:**

- Handle state: opaque struct pointers represented as `uint32` handles
  - Creator APIs allocate new handle IDs
  - Destructor APIs invalidate handles
  - Consumer APIs validate handle before use
  - Prevents UAF/double-free by default
- EMI guard state: constraints applied at fuzz input decode time
- Seed corpus state: v2 only, initialized by seed generator

## Key Abstractions

**TypeMapper (type mapping):**
- Purpose: Map LLVM IR types to protobuf types
- Examples: `src/type_mapper.py` class `TypeMapper`
- Pattern: Rule-based deterministic lookup (pointer → handle or bytes, struct → message, primitive → scalar)
- LLVM type examples:
  - `i8*` (char pointer) → `bytes` (fuzz payload)
  - `%struct.cJSON*` (opaque struct) → `uint32` (handle ID)
  - `i32` → `int32` (protobuf)

**ProtoMessage/ProtoField/ProtoOneof (schema representation):**
- Purpose: In-memory AST for protobuf messages
- Examples: `src/proto_generator.py` classes `ProtoMessage`, `ProtoField`, `ProtoOneof`
- Pattern: Builder pattern with `.serialize()` → proto text format
- Used for v1 and v2 schema generation

**ProtoGenerator (schema generation):**
- Purpose: Transform libErator metadata to `.proto` schema
- Examples: `src/proto_generator.py` class `ProtoGenerator`
- Pattern: Stateful builder; reads conditions/apis, builds message tree, serializes
- Two modes:
  - v1: `repeated <FuncName>_Params` for each API in sequence
  - v2: `Action.oneof` for dynamic dispatch

**WrapperGenerator (harness generation):**
- Purpose: Render Jinja2 templates with context from libErator metadata
- Examples: `src/wrapper_generator.py` class `WrapperGenerator`
- Pattern: Load metadata, build template context dict, render Jinja2 template
- Handles:
  - Nanopb decode logic
  - Handle allocation/validation
  - EMI guard generation from constraints
  - Header inclusion from `driver.meta`

**DependencyIndex (dependency tracking):**
- Purpose: Track which functions produce which handle types, and what they require
- Examples: `src/dependency_index.py` class `DependencyIndex`
- Pattern: Precomputed lookup tables (requires_by_api, producers_by_type, returns_by_api)
- Used by scheduler for insertion-based sequence augmentation

**SeedGenerator (corpus generation):**
- Purpose: Create semantically valid initial seeds for v2 harness
- Examples: `src/seed_generator.py` class `SeedGenerator`
- Pattern: Wire-only protobuf encoding (varint/length-delimited), dependency-aware action sequencing
- Two encodings:
  - Wire-only: bytes generated directly (no python-protobuf dependency)
  - Protobuf-python: import generated `*_pb2.py` and serialize

## Entry Points

**`src/run_all.py` (Orchestrator CLI):**
- Location: `src/run_all.py`
- Triggers: Direct invocation: `python3 run_all.py --library cjson --conditions ... --apis ... --out-dir ...`
- Responsibilities:
  - Parse all options (schema mode, mutation mode, build flags, fuzzing options)
  - Invoke proto generator, protoc, wrapper generator
  - Manage nanopb binding generation
  - Compile harness + target library
  - Optionally run seed generation
  - Optionally launch fuzzer with timeout

**`src/proto_generator.py` (Schema Generation CLI):**
- Location: `src/proto_generator.py`, main function
- Triggers: `python3 proto_generator.py --conditions ... --apis ... --output schema.proto`
- Responsibilities: Parse metadata, generate `.proto`, write to file

**`src/wrapper_generator.py` (Harness Generation CLI):**
- Location: `src/wrapper_generator.py`, main function
- Triggers: `python3 wrapper_generator.py --proto schema.proto --driver driver.meta --conditions ... --output harness.c`
- Responsibilities: Load schema/metadata, render template, write harness

**`src/seed_generator.py` (Corpus Generation CLI):**
- Location: `src/seed_generator.py`, main function
- Triggers: `python3 seed_generator.py --conditions ... --output-dir corpus/ --num-seeds 64`
- Responsibilities: Load conditions, generate seed sequences, encode to wire format, write files

**`src/dependency_index.py` (Dependency Analysis CLI):**
- Location: `src/dependency_index.py`, main function
- Triggers: `python3 dependency_index.py --conditions ... --apis ... --output dep_index.json`
- Responsibilities: Analyze function dependencies, build producer/consumer maps, write JSON

**`scripts/run_campaign.sh` (Fuzzing Campaign CLI):**
- Location: `scripts/run_campaign.sh`
- Triggers: Bash script invocation with target library config
- Responsibilities: Build fuzzer variants, launch parallel jobs, collect coverage

## Error Handling

**Strategy:** Defensive: explicit type checks, graceful fallbacks for missing metadata

**Patterns:**

- **Conditions format normalization** (`wrapper_generator.py`):
  - Accepts both list-of-dicts and dict-of-dicts formats
  - Falls back to empty dict on parse errors
  - Provides best-effort stub parameters for missing metadata

- **Type mapping fallbacks** (`type_mapper.py`):
  - Missing type → default to `i32` or `i8*` heuristic
  - Unknown struct → generic `%struct.name*` or handle
  - Varargs detection optional; missing → normal params

- **Handle management** (`wrapper_generator.py`):
  - Unallocated handle use → caught at decode time or guarded by EMI checks
  - Double-free → tracked state invalidation (if enabled)
  - UAF → prevented by handle lifecycle validation

- **Seed generation** (`seed_generator.py`):
  - Missing producer for type → skip insertion (graceful degrade)
  - Malformed dependency index → proceed with default sequences

- **Compilation errors** (`run_all.py`):
  - Protoc failures → early exit with error message
  - Clang failures → exit with compiler output for debugging
  - Missing dependencies (nanopb, protoc) → checked at startup

## Cross-Cutting Concerns

**Logging:**
- Approach: Print statements with `[Orch]`, `[DRY]` prefixes in orchestrator
- For individual generators: silent unless errors
- Campaign scripts: progress output to stdout, errors to stderr

**Validation:**
- Approach: Inline schema validation (protobuf field number uniqueness, type correctness)
- EMI guards: applied at harness decode time (runtime validation)
- Dependency checks: static (dependency_index.py) or dynamic (scheduler.py)

**Authentication:**
- Approach: Not applicable (no external APIs or services)

**Naming:**
- Proto field names: snake_case, sanitized via `to_proto_field_name()`
- Function names: preserved from libErator (no mangling)
- Type names: preserved from LLVM IR (struct/enum names)

---

*Architecture analysis: 2026-01-21*
