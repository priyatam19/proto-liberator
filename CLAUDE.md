# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Proto-libErator** is an LLM-free protobuf-based fuzzing framework that extends [libErator](https://github.com/HexHive/liberator) with structure-aware fuzzing using libprotobuf-mutator. It generates protobuf schemas and fuzzing harnesses from libErator's static analysis outputs using purely rule-based transformations.

**Core Principle**: Protobuf for function parameters, NOT full API sequences. libErator's NDA-generated API sequences are preserved.

## Build Commands

### Initial Setup

```bash
# Initialize submodules and build dependencies
git submodule update --init --recursive
./scripts/build_dependencies.sh

# Verify installation
python3 tests/test_installation.py
```

### Full End-to-End Pipeline

The main orchestrator script `src/run_all.py` handles the complete pipeline from libErator outputs to built fuzzers:

```bash
# Generate schema + bindings + harness + build fuzzer (v2 super-harness)
python3 src/run_all.py \
  --library cjson \
  --conditions /path/to/conditions.json \
  --apis /path/to/apis_clang.json \
  --out-dir workdir/cjson_test \
  --header cjson/cJSON.h \
  --target-include /path/to/include \
  --target-lib /path/to/libcjson.a \
  --schema-mode v2 \
  --build

# Add seed generation
python3 src/run_all.py [above args] --generate-seeds --num-seeds 64

# Run fuzzer immediately after build
python3 src/run_all.py [above args] --build --fuzz --fuzz-duration 3600
```

### Individual Components

```bash
# 1. Generate protobuf schema (v1: fixed sequence)
python3 src/proto_generator.py \
  --conditions /path/to/conditions.json \
  --apis /path/to/apis_clang.json \
  --output generated/params.proto \
  --library cjson

# 2. Generate schema (v2: dynamic dispatch super-harness)
python3 src/proto_generator.py \
  --conditions /path/to/conditions.json \
  --apis /path/to/apis_clang.json \
  --output generated/params_v2.proto \
  --library cjson \
  --schema-mode v2 \
  --max-actions 64

# 3. Generate fuzzing wrapper/harness
python3 src/wrapper_generator.py \
  --proto generated/params.proto \
  --driver /path/to/driver0.meta \
  --conditions /path/to/conditions.json \
  --output generated/harness.c

# 4. Generate seed corpus (v2 only, wire-only mode)
python3 src/seed_generator.py \
  --conditions /path/to/conditions.json \
  --output-dir corpus/ \
  --num-seeds 64 \
  --max-len 16
```

### Running Fuzzing Campaigns

```bash
# Full campaign with variants (base, trace-cmp, trace-gep)
scripts/run_campaign.sh \
  --library cjson \
  --conditions /path/to/conditions.json \
  --apis /path/to/apis_clang.json \
  --out-root workdir/campaigns \
  --header cjson/cJSON.h \
  --target-include /path/to/include \
  --target-lib /path/to/libcjson.a \
  --duration-sec 86400 \
  --jobs 2 \
  --workers 2 \
  --variant base \
  --variant cmp --variant-cc-arg -fsanitize-coverage=trace-cmp

# Simpler single-variant campaign
scripts/run_campaign.sh --library cjson [paths] --variant base --duration-sec 3600
```

### Coverage Collection

```bash
# Final coverage report (matches libErator paper methodology: Branch Coverage)
scripts/collect_coverage.sh workdir/campaign_dir --final

# Live coverage monitoring
scripts/collect_coverage.sh workdir/campaign_dir --live

# Library-only coverage (exclude harness/nanopb)
scripts/collect_coverage.sh workdir/campaign_dir --final --ignore-regex 'nanopb|harness'

# Function-level coverage
scripts/collect_coverage.sh workdir/campaign_dir --final --sources-file /path/to/sources.txt
```

### Testing

```bash
# Run specific wrapper generator tests
python3 -m pytest tests/test_wrapper_generator.py -v

# Run all unit tests
python3 -m pytest tests/ -v

# Test installation
python3 tests/test_installation.py
```

## Architecture Overview

### Pipeline Flow

```
libErator Analysis → Proto Generation → Wrapper Generation → Fuzzing
    (SVF/LLVM)         (Rule-Based)       (Template-Based)    (LPM + LibFuzzer)
```

**Key Constraint**: Proto-libErator NEVER runs libErator analysis itself. It consumes existing libErator outputs.

### Two Schema Modes

1. **v1 (fixed sequence)**:
   - Uses libErator's `driver.meta` API sequence
   - Each API gets `repeated <Func>_Params` in `FuzzInput`
   - Template: `templates/wrapper.c.j2` or `wrapper_lpm.cc.j2`

2. **v2 (super-harness)**:
   - Dynamic dispatch via `Action.oneof` with `repeated Action`
   - Fuzzer decides API call order at runtime
   - Template: `templates/wrapper_v2.c.j2`
   - Requires seed generation (`seed_generator.py`)

### Core Modules

#### `src/proto_generator.py`
- Reads libErator's `conditions.json` (function metadata + parameter constraints)
- Reads libErator's `apis_clang.json` (function signatures)
- Generates `.proto` files using rule-based LLVM type → protobuf type mapping
- Two modes: v1 (fixed sequence) and v2 (dynamic dispatch)
- **NO LLMs**: purely deterministic transformations

Key responsibilities:
- Extract parameter types and constraints from `conditions.json`
- Map LLVM IR types to protobuf types via `TypeMapper`
- Generate parameter messages (`<FuncName>_Params`)
- Generate top-level `FuzzInput` message with `repeated` fields or `Action.oneof`
- Add nanopb `max_size`/`max_count` annotations

#### `src/wrapper_generator.py`
- Reads generated `.proto` file
- Reads libErator's `driver.meta` (for v1 API sequence + header includes)
- Reads `conditions.json` (for parameter metadata and EMI guards)
- Uses Jinja2 templates to generate C/C++ fuzzing harness
- **NO LLMs**: template-based code generation

Key responsibilities:
- Generate nanopb decode logic
- Generate handle management (for opaque pointers like `struct cJSON*`)
- Generate EMI guards from constraint metadata
- For v1: execute fixed API sequence from `driver.meta`
- For v2: dispatch loop over `Action.oneof` array

#### `src/seed_generator.py`
- Generates initial seed corpus for v2 super-harness
- Wire-only encoding (no protoc/python-protobuf dependency)
- Reads `conditions.json` to identify creators vs destructors
- Creates semantically valid action sequences (e.g., create before use, free after use)

#### `src/type_mapper.py`
- Maps LLVM IR types to protobuf types
- Handles pointers, structs, primitives, arrays
- Struct pointers → `uint32` handles
- Generic pointers → `bytes`
- Primitives → protobuf scalars (`int32`, `uint32`, `bool`, etc.)

#### `src/run_all.py` (Orchestrator)
- Coordinates the full pipeline: schema → nanopb bindings → harness → build → seeds → fuzz
- Supports both schema modes (v1/v2)
- Handles protoc/nanopb invocation
- Manages compiler flags (ASAN, coverage instrumentation)
- Optionally launches fuzzer with timeout

### Important Files

#### libErator Input Files (External)
- `conditions.json`: Parameter constraints and type metadata from libErator's static analysis
- `apis_clang.json`: Function signatures (JSONL format)
- `driver.meta`: NDA-generated API sequences and header includes (v1 only)

#### Schema Contract Documents
- `docs/SCHEMA_CONTRACT.md`: v1 schema specification
- `docs/SCHEMA_CONTRACT_V2.md`: v2 dynamic dispatch schema specification (if exists)

#### Templates
- `templates/wrapper.c.j2`: v1 C harness template (nanopb)
- `templates/wrapper_lpm.cc.j2`: v1 C++ harness template (libprotobuf-mutator)
- `templates/wrapper_v2.c.j2`: v2 super-harness template

### External Dependencies

- **libprotobuf-mutator**: Structure-aware fuzzing engine (external/libprotobuf-mutator)
- **nanopb**: Embedded protobuf C library (external/nanopb)
- **protoc**: Protocol buffer compiler (system dependency)
- **clang/llvm**: Compiler and instrumentation (system dependency)

## Development Workflow

### When Adding a New Target Library

1. Run libErator analysis externally (NOT in proto-liberator)
2. Locate libErator outputs: `conditions.json`, `apis_clang.json`, `driver*.meta`
3. Use `run_all.py` to generate schema + harness + build fuzzer
4. Generate seeds if using v2 mode
5. Run campaign with `run_campaign.sh`
6. Collect coverage with `collect_coverage.sh`

### When Modifying Schema Generation

1. Edit `src/proto_generator.py` logic
2. Update schema contract docs if changing message structure
3. Test with `python3 src/proto_generator.py [args]`
4. Verify generated `.proto` compiles with `protoc --proto_path=. --nanopb_out=. schema.proto`
5. Update wrapper templates if schema changes break harness generation

### When Modifying Wrapper Generation

1. Edit Jinja2 templates in `templates/`
2. Edit `src/wrapper_generator.py` if context building logic changes
3. Test with `python3 src/wrapper_generator.py [args]`
4. Verify generated harness compiles with clang
5. Run fuzzer briefly to ensure no runtime errors

### When Debugging Fuzzing Issues

1. Check `ASAN_OPTIONS` in logs (leak detection disabled by default in `run_all.py`)
2. Examine crash reproducer: `./fuzzer crash-file`
3. Use coverage binary for debugging: `workdir/*/build/*_profile.bin`
4. Check EMI guard reject rate: high reject rate → guards too strict
5. Verify handle management: UAF/double-free often means handle reuse bugs

## Key Design Decisions

### Why LLM-Free?

- libErator's static analysis already provides all constraint metadata
- Type mapping is deterministic (LLVM IR → protobuf)
- Wrapper generation is template-based (follows fixed patterns)
- **Result**: Zero API cost, fully offline, reproducible

### Why Protobuf?

- Structure-aware mutations via libprotobuf-mutator
- Automatic validity (95-99% valid input rate vs 60-80% for libErator)
- Preserves semantic structure during mutation
- Integrates with LibFuzzer ecosystem

### Why Two Schema Modes?

- **v1**: Preserves libErator's NDA-generated sequences (minimal change)
- **v2**: Enables fuzzer to explore call order space (more general)
- Trade-off: v1 is simpler, v2 has higher coverage potential

### Handle Management

Opaque struct pointers (e.g., `struct cJSON*`) are represented as `uint32` handles:
- Creator APIs allocate handle IDs
- Destructor APIs invalidate handles
- Consumer APIs validate handle exists before use
- Prevents UAF and double-free by default (unless violation knobs enabled)

### EMI Guards (Equivalence Modulo Inputs)

Guards are generated from `conditions.json` constraints to filter semantically invalid inputs:
- Parameter range checks (e.g., size must be > 0)
- Null pointer guards (based on `access_type_set`)
- Dependency checks (e.g., pointer must be allocated before use)
- Contract violation knobs allow controlled relaxation for bug finding

## Common Issues and Solutions

### "nanopb.proto: File not found"

Add `--proto-path` pointing to nanopb directory:
```bash
protoc --proto_path=external/nanopb/generator/proto --proto_path=. --nanopb_out=. schema.proto
```

### High Reject Rate (>50%)

EMI guards too strict. Options:
1. Relax guards in `wrapper_generator.py`
2. Enable contract violation knobs in schema
3. Use v2 mode for more flexibility

### Low Coverage

1. Increase fuzzing duration
2. Use v2 mode for call order exploration
3. Add more seed corpus entries
4. Enable coverage instrumentations: `-fsanitize-coverage=trace-cmp,trace-gep`

### Harness Won't Compile

1. Check nanopb bindings generated correctly
2. Verify target library headers are accessible
3. Ensure `driver.meta` includes all necessary headers
4. Check for type mismatches in template rendering

### Crashes During Fuzzing

1. Review ASAN output
2. Check handle management logic (especially for `free`/`delete` APIs)
3. Verify EMI guards aren't allowing invalid states
4. Use `--fuzz-workers 1` to reproduce deterministically

## File Formats

### conditions.json (libErator Output)

List of function metadata objects:
```json
[
  {
    "function_name": "cJSON_Parse",
    "param_0": {
      "param_type": "i8*",
      "is_array": false,
      "access_type_set": [{"access": "read"}]
    },
    "return": {
      "return_type": "%struct.cJSON*",
      "access_type_set": [{"access": "create"}]
    }
  }
]
```

### driver.meta (libErator Output, v1 only)

JSON with API sequence and headers:
```json
{
  "api_sequence": ["cJSON_Parse", "cJSON_GetObjectItem", "cJSON_Delete"],
  "api_multiset": {"cJSON_Parse": 1, "cJSON_GetObjectItem": 2, "cJSON_Delete": 1},
  "includes": ["<stdio.h>", "\"cJSON.h\""]
}
```

### apis_clang.json (libErator Output)

JSONL format (one function per line):
```json
{"function_name":"cJSON_Parse","signature":"struct cJSON* cJSON_Parse(const char*)","param_types":["i8*"],"return_type":"%struct.cJSON*"}
```

## Testing Philosophy

Tests should verify:
1. Schema generation produces valid protobuf syntax
2. Type mapping is deterministic and correct
3. Wrapper generation produces compilable C code
4. Generated harnesses can be fuzzed without immediate crashes
5. Coverage improves over time

Use real libErator outputs (cJSON, libTIFF) for integration tests, not synthetic examples.
