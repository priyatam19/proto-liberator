# Codebase Structure

**Analysis Date:** 2026-01-21

## Directory Layout

```
proto-liberator.ehnace-harness/
├── src/                         # Core Python generators and orchestrators
│   ├── run_all.py              # Main orchestrator (schema → harness → build → fuzz)
│   ├── proto_generator.py       # v1/v2 protobuf schema generation
│   ├── wrapper_generator.py     # C/C++ harness generation from templates
│   ├── seed_generator.py        # v2 seed corpus generation (wire-only encoding)
│   ├── dependency_index.py      # Dependency analysis for handle/type tracking
│   ├── type_mapper.py           # LLVM IR → protobuf type mapping
│   ├── scheduler.py             # Dependency-aware API sequence insertion (prototype)
│   ├── contracts.py             # Shared schema field name constants
│   ├── emi_guard_rules.py       # EMI constraint enforcement rules
│   └── utils.py                 # Utility functions (I/O, naming, type normalization)
├── templates/                   # Jinja2 templates for harness generation
│   ├── wrapper.c.j2            # v1 C harness template (nanopb)
│   ├── wrapper_lpm.cc.j2       # v1 C++ harness template (libprotobuf-mutator)
│   └── wrapper_v2.c.j2         # v2 C harness template (dynamic dispatch)
├── scripts/                     # Shell scripts for build, fuzzing, coverage
│   ├── run_campaign.sh         # Main fuzzing campaign orchestrator
│   ├── collect_coverage.sh     # Coverage collection and reporting
│   ├── build_proto_fuzzer.sh   # Compile harness binary
│   ├── fuzz_library.sh         # Run individual fuzzer instance
│   ├── build_dependencies.sh   # Build nanopb, libprotobuf-mutator, etc.
│   ├── generate_seeds.sh       # Invoke seed generator
│   ├── cluster_crashes.sh      # Triage and cluster crash files
│   └── merge_api_stats.py      # Merge per-target API statistics
├── tests/                       # Unit and integration tests
│   ├── test_proto_generator.py      # Golden tests for schema generation
│   ├── test_wrapper_generator.py    # (mentioned in CLAUDE.md)
│   ├── test_seed_generator.py       # Seed generation tests
│   ├── test_scheduler.py            # Scheduler tests
│   ├── test_dependency_index.py     # Dependency index tests
│   ├── test_run_all.py              # Orchestrator tests
│   ├── test_installation.py         # Verify deps are installed
│   ├── fixtures/                    # Test input data
│   │   ├── minimal_conditions.json
│   │   ├── minimal_apis_clang.jsonl
│   │   ├── cjsonish_conditions.json
│   │   ├── expected_minimal.proto
│   │   ├── expected_minimal_v2.proto
│   │   └── expected_cjsonish_v2.proto
│   ├── stubs/                       # Stub implementations for testing
│   └── test_compile.sh              # Compile sanity checks
├── docs/                        # Documentation and analysis reports
│   ├── SCHEMA_CONTRACT.md           # v1 schema specification
│   ├── SCHEMA_CONTRACT_V2.md        # v2 schema specification
│   ├── LLM_FREE_ARCHITECTURE.md     # Design rationale
│   ├── LIBERATOR_COMPLETE_MANUAL.md # Integration guide
│   └── *.md                         # Success reports, design docs
├── external/                    # Vendored dependencies
│   ├── nanopb/                  # Embedded protobuf for C
│   ├── libprotobuf-mutator/     # Structure-aware fuzzing engine
│   └── ...
├── targets/                     # Target library directories (reference)
│   ├── cjson/
│   ├── libtiff/
│   ├── libxml2/
│   └── ... (25+ targets)
├── analysis/                    # libErator outputs for targets (conditions/apis/driver)
│   ├── cjson/
│   ├── libtiff/
│   └── ...
├── workdir/                     # Build artifacts from run_all.py
│   ├── <libname>_test/          # Per-target output (generated schema, harness, binary)
│   └── campaigns/               # Fuzzing campaign results
├── seed_payloads/              # Custom seed payload specs (libaom, libpcap, etc.)
│   ├── libaom/
│   └── libpcap/
├── api_stats/                  # Per-target API statistics (analysis output)
│   └── api_stats.<id>.json
├── .planning/codebase/         # (This analysis location)
│   ├── ARCHITECTURE.md
│   └── STRUCTURE.md
├── .claude/                    # Claude.ai/code workspace state
├── CLAUDE.md                   # Developer instructions (how to use this repo)
└── README.md                   # (if present) Project overview
```

## Directory Purposes

**`src/`:**
- Purpose: Core pipeline logic (schema generation, harness generation, seed generation)
- Contains: Python modules implementing the four main generators + orchestrator
- Key files: `run_all.py` (entry point), `proto_generator.py`, `wrapper_generator.py`, `seed_generator.py`
- Imports: Standard library + jinja2, no external binary dependencies

**`templates/`:**
- Purpose: Jinja2 harness templates rendered by wrapper generator
- Contains: v1 (nanopb/LPM) and v2 (dynamic dispatch) harness templates
- Key files: `wrapper.c.j2`, `wrapper_lpm.cc.j2`, `wrapper_v2.c.j2`
- Rendering context: Includes function metadata, headers, dispatch logic, handle management

**`scripts/`:**
- Purpose: Shell orchestration for build, fuzzing, coverage collection
- Contains: Bash scripts for campaign-level automation
- Key files: `run_campaign.sh` (main), `collect_coverage.sh`, `build_proto_fuzzer.sh`
- Inputs: Config files (target paths, compiler flags, duration), generated artifacts

**`tests/`:**
- Purpose: Unit tests and integration tests for generators
- Contains: Python unit tests using unittest framework; shell script sanity checks
- Key files: `test_proto_generator.py` (golden tests), `test_installation.py` (dependency check)
- Fixtures: Minimal and cJSON-like test inputs with expected schema outputs

**`docs/`:**
- Purpose: Architecture and integration documentation
- Contains: Schema contracts (v1/v2), design rationale, libErator integration guide
- Key files: `SCHEMA_CONTRACT.md` (v1 message structure), `SCHEMA_CONTRACT_V2.md` (dynamic dispatch)

**`external/`:**
- Purpose: Vendored dependencies (nanopb, libprotobuf-mutator)
- Contains: Git submodules or vendored source
- Key files: Not modified by proto-liberator (external dependency)

**`targets/`:**
- Purpose: Reference target library directories (not modified by pipeline)
- Contains: Symlinks or clones of real libraries (cjson, libtiff, libxml2, etc.)
- Used by: libErator (external tool) for analysis; fuzzing campaigns for compilation

**`analysis/`:**
- Purpose: libErator output storage (conditions.json, apis_clang.json, driver.meta)
- Contains: Per-target analysis artifacts from libErator static analysis
- Key files: `cjson/work/apipass/conditions.json`, `cjson/driver.meta`

**`workdir/`:**
- Purpose: Build outputs from orchestrator
- Contains: Generated schemas (.proto), harness (.c), nanopb bindings (.pb.c/.pb.h), compiled binary
- Structure: `workdir/<libname>_<variant>/build/` for each fuzzer variant
- Generated: Re-created on each run (safe to delete)

**`seed_payloads/`:**
- Purpose: Payload templates for custom seed generation (optional)
- Contains: JSON specs for embedding custom test data in seeds
- Example: `libaom/payloads.json` for encoder configuration

**`api_stats/`:**
- Purpose: API metadata collection (informational, not used by pipeline)
- Contains: Per-target JSON files with API usage statistics
- Generated by: libErator; used for coverage analysis post-campaign

**`.planning/codebase/`:**
- Purpose: GSD codebase analysis documents (this location)
- Contains: ARCHITECTURE.md, STRUCTURE.md, and other analysis docs
- Created by: `/gsd:map-codebase` agent

## Key File Locations

**Entry Points:**

- `src/run_all.py`: Main orchestrator CLI; use for full pipeline
- `scripts/run_campaign.sh`: Campaign-level fuzzing (multiple variants, parallel jobs)
- `src/proto_generator.py`: Standalone schema generation
- `src/wrapper_generator.py`: Standalone harness generation
- `src/seed_generator.py`: Standalone seed corpus generation

**Configuration:**

- `CLAUDE.md`: Developer instructions (build commands, architecture overview)
- `docs/SCHEMA_CONTRACT.md`: v1 schema specification (FuzzInput message structure)
- `docs/SCHEMA_CONTRACT_V2.md`: v2 schema specification (Action.oneof + repeated actions)

**Core Logic:**

- `src/proto_generator.py`: v1/v2 schema generation logic
- `src/wrapper_generator.py`: Harness generation logic; EMI guard rules; handle management
- `src/type_mapper.py`: Type conversion rules (LLVM IR → protobuf)
- `src/seed_generator.py`: Wire-only protobuf encoding, dependency-aware sequencing
- `src/dependency_index.py`: Build dependency graph from conditions

**Testing:**

- `tests/fixtures/`: Golden test inputs and expected outputs
- `tests/test_proto_generator.py`: Unit tests for schema generation
- `tests/test_installation.py`: Dependency verification

## Naming Conventions

**Files:**

- Python modules: `lowercase_with_underscores.py` (e.g., `proto_generator.py`)
- Shell scripts: `lowercase_with_underscores.sh` (e.g., `run_campaign.sh`)
- Templates: `lowercase_with_underscores.j2` (Jinja2 suffix)
- Config/data: `snake_case.json` (e.g., `conditions.json`)

**Directories:**

- Core code: `src/`
- Executable scripts: `scripts/`
- Test code: `tests/`
- Documentation: `docs/`
- External dependencies: `external/`
- Runtime outputs: `workdir/`

**Python Naming:**

- Classes: `PascalCase` (e.g., `ProtoGenerator`, `WrapperGenerator`, `TypeMapper`)
- Functions: `snake_case` (e.g., `load_json()`, `to_proto_field_name()`)
- Constants: `UPPERCASE` (e.g., `MSG_FUZZ_INPUT`, `DEFAULT_MAX_ACTIONS`, `WIRE_VARINT`)
- Module-level vars: `snake_case` or `UPPERCASE` (conventions vary by module)

**Protobuf Naming:**

- Messages: `PascalCase` (e.g., `FuzzInput`, `Action`, `CJsonParse_Params`)
- Fields: `snake_case` (e.g., `actions`, `action_type`, `param_0_length`)
- Enums: `PascalCase` (e.g., `CreateAction`, `DestroyAction`)

**Command-line Arguments:**

- Long options: `--kebab-case` (e.g., `--schema-mode`, `--out-dir`)
- Shorthand flags: `-x` where applicable
- Paths: Absolute or relative (orchestrator normalizes to absolute)

## Where to Add New Code

**New Feature (e.g., new schema constraint type):**

- Primary code: `src/proto_generator.py` (schema generation logic)
- Supporting: `src/type_mapper.py` if type handling changes needed
- Tests: `tests/test_proto_generator.py` (add golden test case)
- Docs: `docs/SCHEMA_CONTRACT*.md` if message structure changes

**New Generator Module (e.g., new harness style):**

- Implementation: Create `src/new_generator.py`
- Template: Add `templates/wrapper_new_style.j2` if using template pattern
- Integration: Add to `src/run_all.py` orchestration logic
- Tests: Create `tests/test_new_generator.py` with fixtures
- CLI: Add argument parsing in generator's `main()` function

**New Utility Function:**

- Shared helpers: `src/utils.py`
- Type mapping helpers: `src/type_mapper.py`
- Schema constants: `src/contracts.py`
- EMI rules: `src/emi_guard_rules.py`

**Campaign Variants:**

- Build script: Copy `scripts/build_proto_fuzzer.sh`, add new compiler flags
- Campaign runner: Add variant config to `scripts/run_campaign.sh`
- Coverage: Extend `scripts/collect_coverage.sh` for new instrumentation

**Tests:**

- Unit tests: `tests/test_*.py` following unittest framework
- Fixtures: Add to `tests/fixtures/` with descriptive names
- Integration tests: Use `tests/test_e2e_cjson.sh` as template
- Shell tests: Use `tests/test_compile.sh` as template

## Special Directories

**`workdir/`:**
- Purpose: Staging area for build artifacts
- Generated: Yes (created by `run_all.py`)
- Committed: No (gitignored)
- Cleanup: Safe to delete; will be regenerated on next run
- Structure: `workdir/<libname>_<variant>/build/` contains:
  - `generated/` (schema, nanopb bindings)
  - `harness.c` (generated harness)
  - `fuzzer` (compiled binary)
  - `corpus/` (seed files, if generated)
  - `artifacts/` (crashes, coverage data)

**`analysis/`:**
- Purpose: Cache libErator outputs for reference
- Generated: No (populated manually or by libErator external tool)
- Committed: Yes (provides reference data for reproducibility)
- Content: `<libname>/work/apipass/` contains:
  - `conditions.json` (function metadata)
  - `apis_clang.json` (function signatures)
  - Other artifacts: `enum_types.txt`, `data_layout.txt`, etc.

**`external/`:**
- Purpose: Vendored dependencies
- Generated: No (managed by git submodules)
- Committed: Yes (via git submodule)
- Note: Proto-liberator does not modify; built by `scripts/build_dependencies.sh`

**`api_stats/`:**
- Purpose: Informational (API statistics)
- Generated: Yes (by libErator or merge script)
- Committed: Partially (some files checked in for analysis)
- Used by: Coverage analysis, not by fuzzing pipeline

---

*Structure analysis: 2026-01-21*
