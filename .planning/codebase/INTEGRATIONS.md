# External Integrations

**Analysis Date:** 2026-01-21

## APIs & External Services

**None detected.** Proto-libErator is fully offline and does not integrate with external APIs or cloud services.

## Data Storage

**Databases:**
- Not applicable. No database integration.

**File Storage:**
- Local filesystem only
  - Input: libErator analysis outputs (conditions.json, apis_clang.json, driver.meta)
  - Output: Generated `.proto` files, C/C++ harness binaries, seed corpora
  - Coverage data: Stored in `workdir/*/corpus/`, `workdir/*/coverage/`
  - API statistics: Stored in `api_stats/` directory (JSON format)

**Caching:**
- No caching layer. Inputs are stateless JSON files.

## Authentication & Identity

**Auth Provider:**
- Not applicable. No authentication required.

## Monitoring & Observability

**Error Tracking:**
- Not applicable. No remote error tracking.

**Logs:**
- Standard output/stderr via Python print statements and bash logging
- Log levels: Implicit (INFO level via print, exceptions via stderr)
- No centralized log aggregation

## CI/CD & Deployment

**Hosting:**
- Local development and on-premises fuzzing only
- No cloud hosting integration

**CI Pipeline:**
- Not detected. No `.github/workflows/`, GitLab CI, Jenkins integration
- Manual script-based pipeline: `scripts/build_dependencies.sh` → `src/run_all.py` → `scripts/run_campaign.sh`

**Dependency Installation:**
- git submodules for external libraries: `libprotobuf-mutator`, `nanopb`
- Python: pip install from `requirements.txt`

```bash
# Standard installation:
git submodule update --init --recursive
./scripts/build_dependencies.sh
pip install -r requirements.txt
python3 tests/test_installation.py
```

## Environment Configuration

**Required env vars:**
- None explicitly required at runtime
- Optional env vars (set during build):
  - `ASAN_OPTIONS`: Address Sanitizer options (set in harness generation for leak detection)
  - `PROTO_LIBERATOR_RUN_CAMPAIGN_SNAPSHOTTED`: Internal flag for script snapshots in `run_campaign.sh`
  - `PROTO_LIBERATOR_RUN_CAMPAIGN_ORIG_ROOT`: Internal tracking for campaign root

**Secrets location:**
- Not applicable. No secrets used.

**Path configuration:**
- libErator input paths: Passed as `--conditions`, `--apis`, `--driver` arguments
- Output paths: `--out-dir` for all generated artifacts
- Build paths: `--target-include`, `--target-lib` for linking target library

## Webhooks & Callbacks

**Incoming:**
- None. No webhook endpoints.

**Outgoing:**
- None. No outbound callbacks or notifications.

## External Library Consumption

**libErator Analysis Outputs (Required Inputs):**
- **conditions.json** - Function metadata from libErator's static analysis
  - Format: JSON list of function entries with parameter types and access patterns
  - Loaded by: `proto_generator.py`, `wrapper_generator.py`, `seed_generator.py`
  - Example fields: `function_name`, `param_0`, `param_1`, `return`, `access_type_set`

- **apis_clang.json** - Function signatures from libErator's LLVM analysis
  - Format: JSONL (one function per line)
  - Example: `{"function_name":"cJSON_Parse","signature":"struct cJSON* cJSON_Parse(const char*)","param_types":["i8*"],"return_type":"%struct.cJSON*"}`
  - Loaded by: `wrapper_generator.py`, `seed_generator.py`

- **driver.meta** - API sequences and headers (for v1 mode; optional for v2)
  - Format: JSON with `api_sequence`, `api_multiset`, `includes`
  - Loaded by: `wrapper_generator.py` (v1 harness generation)

**Target Library Inputs:**
- **Target library headers** - User-provided via `--header` argument
- **Target library binaries** - User-provided via `--target-lib` argument (`.a` archives)
- **Bitcode variants** - Optional `.bc` files for coverage-enabled builds

## Compiler Toolchain Integration

**Clang/LLVM Integration:**
- Compiler: Configurable via `--clang` (default: `clang` in PATH)
- C++ compiler: `clang++` for LPM-based harnesses
- Coverage flags: `-fprofile-instr-generate -fcoverage-mapping`
- Sanitizers: `-fsanitize=address`, `-fsanitize-coverage=trace-cmp,trace-gep`
- Used by: `src/run_all.py` for building fuzzer binaries

**Protocol Buffer Compiler Integration:**
- LPM variant: `external/libprotobuf-mutator/build/external.protobuf/bin/protoc`
- nanopb variant: `external/nanopb/generator/protoc` (wrapper around system protoc)
- Usage: Compiles generated `.proto` files to C/C++ bindings
- Invoked by: `src/run_all.py` after schema generation

**Coverage Analysis Integration:**
- llvm-cov: For coverage reporting from instrumented binaries
- Used by: `scripts/collect_coverage.sh --final` to generate coverage reports

## Testing & Validation Harnesses

**Test Files:**
- Location: `tests/` directory
- test_installation.py - Verifies dependencies are correctly built
- Integration tests in `scripts/test_e2e_cjson.sh` - End-to-end pipeline test

## Post-Processing Tools

**Crash Analysis:**
- CASR (Crash Analysis and Security Reproduction tool)
- Used by: `scripts/cluster_crashes.sh` for crash triaging and categorization

**Coverage Collection:**
- Script: `scripts/collect_coverage.sh`
- Method: Invokes `*_profile.bin` on corpus, collects `.profraw` files, runs llvm-cov for reporting
- Filters: Ignores harness/nanopb code, focuses on target library coverage

**API Statistics:**
- Script: `scripts/merge_api_stats.py`
- Input: Per-process `api_stats/*.json` files from fuzzer runs
- Output: Aggregated coverage/mutation statistics

## Deployment & Distribution

**Artifact Type:**
- Standalone ELF binaries: `*_fuzzer.bin`, `*_profile.bin`
- Reproducible builds via fixed seed, deterministic code generation
- No runtime dependencies beyond GLIBC (statically linked libprotobuf-mutator, nanopb)

**Distribution Method:**
- File-based: Copy fuzzer binary to target system
- No package manager integration (no .deb, .rpm, or container images detected)

---

*Integration audit: 2026-01-21*
