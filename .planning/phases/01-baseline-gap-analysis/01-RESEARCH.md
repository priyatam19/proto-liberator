# Phase 1: Baseline & Function Coverage Gap Analysis - Research

**Researched:** 2026-01-21
**Domain:** Coverage analysis, function enumeration, fuzzing baselines
**Confidence:** HIGH

## Summary

This research investigates methods for analyzing function coverage gaps in library fuzzing campaigns. The goal is to identify which functions are NOT being fuzzed and understand why, enabling systematic improvement toward 100% function coverage.

**Key findings:**
- libErator provides pre-analyzed function metadata in `apis_clang.json` and `conditions.json`
- Function gaps can be measured at three levels: libErator's analysis output vs library exports vs current schema
- Coverage measurement uses llvm-cov with function-level reporting (`-show-functions`)
- Gap categorization requires understanding type mapping, parameter complexity, and dependency analysis

**Primary recommendation:** Build a three-tier comparison pipeline: (1) Extract library symbols with nm/objdump, (2) Enumerate functions from apis_clang.json, (3) Check which functions appear in generated v2 schema, then analyze the gaps at each boundary.

## Standard Stack

### Core Tools
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| llvm-cov | 14+ | Coverage reporting | Official LLVM coverage tool, matches libErator paper methodology |
| llvm-profdata | 14+ | Profile merging | Required companion to llvm-cov for indexed profiles |
| nm | GNU binutils | Symbol extraction | Standard for listing dynamic symbols from shared libraries |
| objdump | GNU binutils | Symbol analysis | Alternative to nm with more detailed output |
| readelf | GNU binutils | ELF symbol table | Low-level alternative for ELF binaries |

### Supporting Tools
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| jq | 1.6+ | JSON processing | Parsing apis_clang.json and conditions.json |
| python3 | 3.8+ | Data analysis | Comparing function sets, generating reports |
| grep/awk | System | Text filtering | Quick filtering of symbol lists |

**Installation:**
```bash
# Already available in proto-liberator environment
apt-get install binutils llvm-14 jq python3
```

## Data Sources

### 1. libErator Analysis Outputs

libErator provides three key files per target (in `analysis/<library>/work/apipass/`):

**apis_clang.json** (JSONL format - one function per line)
- Complete list of functions analyzed by libErator
- Contains function signatures with parameter and return types
- Example count: cJSON has 78 functions, libpcap has 99 functions, libaom has 243 functions
- Format: `{"function_name": "...", "return_info": {...}, "arguments_info": [...]}`
- **This is the authoritative list of what libErator found**

**conditions.json** (JSON array)
- Parameter constraints and type metadata
- Only includes functions where libErator extracted usable constraints
- May be subset of apis_clang.json (e.g., libpcap has 99 APIs but 0-byte conditions.json in current analysis)
- Contains `param_0`, `param_1`, etc. with `type_string`, `is_array`, `access_type_set`
- **This determines what can be included in protobuf schema**

**driver.meta** (v1 only, JSON)
- NDA-generated API sequences
- Lists includes and API call order
- Only relevant for v1 schema mode
- v2 mode doesn't use this (dynamic dispatch instead)

### 2. Library Symbol Tables

Use `nm -D` or `objdump -T` to extract actual exported symbols from compiled libraries:

```bash
# Extract dynamic symbols from shared library
nm -D --defined-only --extern-only /path/to/libfoo.so | awk '{print $3}'

# Alternative with objdump
objdump -T /path/to/libfoo.so | grep "DF .text" | awk '{print $NF}'

# For static libraries
nm --defined-only --extern-only /path/to/libfoo.a | grep " T " | awk '{print $3}'
```

**Notes:**
- Shared libraries (.so) show dynamic symbols with `-D` flag
- Static libraries (.a) require different approach (archive members)
- Symbol types: T = text (function), D = data, etc.
- Filter for text symbols to get functions only

### 3. Generated Protobuf Schema

Check current schema coverage by inspecting generated `.proto` files:

```bash
# For v2 schema, check Action.oneof
grep -A 1000 "message Action" generated_schema.proto | grep "Params"

# Count functions in schema
grep "_Params {" generated_schema.proto | wc -l
```

Schema includes functions from `conditions.json` that pass type mapping rules in `proto_generator.py`.

### 4. Coverage Reports

Use `llvm-cov` with function-level reporting to see which functions were actually executed:

```bash
# Generate function-level coverage report
llvm-cov report fuzzer_profile.bin \
  -instr-profile=merged.profdata \
  -show-functions \
  > functions_coverage.txt

# Extract executed functions
awk '$7 != "0.00%" {print $1}' functions_coverage.txt
```

**Metrics from llvm-cov report:**
- Column 7: Function Coverage % (libErator paper uses this)
- Column 13: Branch Coverage % (primary metric in libErator Tables 4-6)

### 5. libErator Baseline Numbers

From the [libErator FSE'25 paper](https://nebelwelt.net/files/25FSE2.pdf) (HexHive):

**Target Coverage Baselines (Table 4 - Branch Coverage):**
- libTIFF: 24.4% branch coverage (libErator baseline)
- cJSON: Not in original paper evaluation (proto-liberator addition)
- libpcap: Not in original paper evaluation
- libaom: Not in original paper evaluation

**Proto-liberator Current Baselines (Jan 19, 2026):**
- cJSON: 76.99% function coverage (CMP mode), 30.09% (base mode)
- libpcap: 13.12% function coverage (CMP mode), 12.57% (base mode)
- libaom: 0.69% function coverage (CMP/base mode - effectively unchanged)

**Note:** libErator paper focuses on branch coverage as primary metric, but function coverage is tracked separately for gap analysis purposes.

## Analysis Methods

### Method 1: Three-Tier Gap Analysis

**Recommended approach** - Compare at three boundaries:

```python
# Tier 1: Library exports vs libErator analysis
library_symbols = extract_symbols("libfoo.so")  # nm -D
liberator_apis = load_jsonl("apis_clang.json")
gap_1 = library_symbols - set(api["function_name"] for api in liberator_apis)
# Gap 1 = functions libErator didn't analyze

# Tier 2: libErator analysis vs conditions
api_names = set(api["function_name"] for api in liberator_apis)
condition_names = set(c["function_name"] for c in conditions)
gap_2 = api_names - condition_names
# Gap 2 = functions analyzed but no constraints extracted

# Tier 3: Conditions vs schema
condition_names = set(c["function_name"] for c in conditions)
schema_functions = extract_from_proto("schema.proto")
gap_3 = condition_names - schema_functions
# Gap 3 = functions with constraints but excluded from schema

# Tier 4: Schema vs executed
schema_functions = extract_from_proto("schema.proto")
executed_functions = parse_llvm_cov_report("functions_coverage.txt")
gap_4 = schema_functions - executed_functions
# Gap 4 = functions in schema but never called during fuzzing
```

### Method 2: Category-Based Gap Analysis

Categorize why functions are missing:

**Category A: Not Exported**
- Internal/static functions
- Hidden symbols (symbol visibility)
- Not in analysis scope

**Category B: libErator Limitations**
- Varargs functions (e.g., `printf`-style)
- Function pointer callbacks
- Complex template instantiations (C++)
- Inline functions (no symbol)

**Category C: Type Mapping Failures**
- Complex structs without known layout
- Nested function pointers in parameters
- Platform-specific types (e.g., `__int128`)
- Unions with ambiguous layouts

**Category D: Dependency Issues**
- Requires specific initialization sequence
- Needs external resources (files, network)
- Platform-specific APIs (e.g., Windows-only)

**Category E: Intentionally Excluded**
- Deprecated functions
- Internal test functions
- Debug-only functions

**Category F: Harness Execution Issues**
- Function in schema but handle never created
- Dependency chain broken (missing prerequisite)
- EMI guards too strict (all inputs rejected)

### Method 3: Incremental Coverage Attribution

Track which phase adds coverage:

```bash
# 1. Baseline: functions in apis_clang.json
baseline_count=$(wc -l < apis_clang.json)

# 2. After schema generation
schema_count=$(grep "_Params {" schema.proto | wc -l)
schema_delta=$((schema_count - baseline_count))

# 3. After fuzzing campaign
executed_count=$(awk '$7 != "0.00%"' functions_coverage.txt | wc -l)
execution_delta=$((executed_count - schema_count))
```

### Method 4: Automated Gap Reporting

Create a Python script to automate the comparison:

```python
#!/usr/bin/env python3
"""
Function coverage gap analyzer for proto-liberator
"""

import json
import subprocess
from pathlib import Path

def extract_library_symbols(lib_path):
    """Extract exported function symbols from library"""
    cmd = ["nm", "-D", "--defined-only", "--extern-only", str(lib_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    symbols = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == 'T':  # Text (function) symbols
            symbols.append(parts[2])
    return set(symbols)

def load_apis_clang(path):
    """Load function names from apis_clang.json (JSONL)"""
    functions = []
    with open(path) as f:
        for line in f:
            data = json.loads(line)
            functions.append(data["function_name"])
    return set(functions)

def load_conditions(path):
    """Load function names from conditions.json"""
    with open(path) as f:
        data = json.load(f)
    return set(entry["function_name"] for entry in data)

def extract_schema_functions(proto_path):
    """Extract function names from generated .proto file"""
    functions = []
    with open(proto_path) as f:
        for line in f:
            if line.strip().endswith("_Params {"):
                func_name = line.strip().replace("message ", "").replace("_Params {", "")
                functions.append(func_name)
    return set(functions)

def generate_gap_report(library_name, lib_path, apis_path, conditions_path, proto_path=None):
    """Generate comprehensive gap report"""

    lib_symbols = extract_library_symbols(lib_path)
    api_functions = load_apis_clang(apis_path)
    condition_functions = load_conditions(conditions_path)

    report = {
        "library": library_name,
        "total_exported": len(lib_symbols),
        "liberator_analyzed": len(api_functions),
        "with_constraints": len(condition_functions),
        "gap_analysis": {
            "not_analyzed": list(lib_symbols - api_functions),
            "no_constraints": list(api_functions - condition_functions),
        }
    }

    if proto_path:
        schema_functions = extract_schema_functions(proto_path)
        report["in_schema"] = len(schema_functions)
        report["gap_analysis"]["excluded_from_schema"] = list(condition_functions - schema_functions)

    return report
```

## Gap Categories

Based on proto-liberator's type mapping rules and libErator's analysis approach:

### 1. Function Signature Complexity

**Varargs Functions**
- **Problem:** `printf(const char *fmt, ...)`-style signatures
- **Detection:** `arguments_info` contains variable-length array
- **Workaround:** None in current framework (requires manual wrapper)
- **Example:** `pcap_fprintf`, logging functions

**Function Pointer Parameters**
- **Problem:** Callbacks like `pcap_loop(pcap_t *, int, void (*)(u_char *, const struct pcap_pkthdr *, const u_char *), u_char *)`
- **Detection:** `type_clang` contains function pointer syntax `(*)()`
- **Current Handling:** Excluded from schema (can't generate valid function pointers)
- **Impact:** High for event-driven APIs (pcap_loop, pcap_dispatch)

### 2. Type Mapping Limitations

**Unmapped LLVM Types**
- **Problem:** Type not in `TypeMapper.map_llvm_to_proto()`
- **Detection:** Falls back to `bytes` type
- **Common Cases:** Platform-specific types, complex bitfields, unions
- **Example:** `__uint128_t`, compiler intrinsics

**Struct Layout Unknown**
- **Problem:** Struct size not in `TypeContext.struct_size_for()`
- **Current Handling:** Treated as handle (uint32) instead of blob
- **Impact:** Can't initialize struct parameters directly
- **Workaround:** Requires creator functions instead

### 3. Dependency Chain Gaps

**Missing Creators**
- **Problem:** Function needs handle type X but no function creates X
- **Detection:** Parameter has `set_by` dependency with no satisfying function
- **Example:** `pcap_stats(pcap_t *)` without `pcap_create()` in schema

**Circular Dependencies**
- **Problem:** Function A needs handle from B, B needs handle from A
- **Detection:** Dependency graph has cycles
- **Resolution:** Manual ordering or seed corpus with pre-created handles

**Initialization Sequences**
- **Problem:** Function requires specific call order (init → config → use → destroy)
- **Current Handling:** v2 scheduler can help but not guaranteed
- **Example:** libaom codec init → decode → get_frame → destroy

### 4. Runtime Execution Barriers

**EMI Guard Rejection**
- **Problem:** All fuzz inputs rejected by EMI guards
- **Detection:** High skip count for function in api_stats
- **Cause:** Overly strict constraint from `conditions.json`
- **Example:** Size parameter must be exact value, null pointer not allowed

**Handle Pool Exhaustion**
- **Problem:** Function needs handle but all handles deleted/invalid
- **Detection:** `missing_handle` skip reason in logs
- **Cause:** Scheduler deletes handles before they're used
- **Impact:** High for stateful APIs

**Resource Unavailable**
- **Problem:** Function needs external resource (file, network, device)
- **Example:** `pcap_open_live()` needs network interface
- **Workaround:** Mock or use offline variants (`pcap_open_offline()`)

### 5. Analysis Artifacts

**Incomplete conditions.json**
- **Problem:** libErator analysis didn't extract constraints
- **Evidence:** Function in apis_clang.json but not conditions.json
- **Cause:** Static analysis limitations, complex control flow
- **Example:** libpcap has 99 APIs but 0-byte conditions.json (analysis issue)

**False Positives in apis_clang.json**
- **Problem:** Function listed but not actually exported
- **Cause:** Header parsing vs actual symbols mismatch
- **Detection:** Compare with `nm -D` output

## Code Examples

### Extract Function Lists

```bash
# 1. Get library exports
nm -D --defined-only --extern-only /path/to/libfoo.so | \
  awk '$2 == "T" {print $3}' | \
  sort > library_exports.txt

# 2. Get libErator analysis
jq -r '.function_name' apis_clang.json | sort > liberator_apis.txt

# 3. Get functions with constraints
jq -r '.[].function_name' conditions.json | sort > with_constraints.txt

# 4. Get schema functions
grep "message.*_Params {" schema.proto | \
  sed 's/message //; s/_Params {//' | \
  sort > schema_functions.txt

# 5. Find gaps
comm -23 library_exports.txt liberator_apis.txt > gap_not_analyzed.txt
comm -23 liberator_apis.txt with_constraints.txt > gap_no_constraints.txt
comm -23 with_constraints.txt schema_functions.txt > gap_excluded.txt
```

### Generate Function Coverage Report

```bash
# Run corpus through coverage-instrumented binary
LLVM_PROFILE_FILE="coverage_%m.profraw" ./fuzzer_profile.bin corpus/ -runs=0

# Merge profiles
llvm-profdata merge -sparse coverage_*.profraw -o merged.profdata

# Generate function-level report
llvm-cov report ./fuzzer_profile.bin \
  -instr-profile=merged.profdata \
  -show-functions \
  -ignore-filename-regex='(nanopb|harness)' \
  > functions_report.txt

# Extract executed functions (>0% coverage)
awk 'NR > 2 && $7 != "0.00%" {print $1}' functions_report.txt | \
  sort > executed_functions.txt

# Find functions in schema but never executed
comm -23 schema_functions.txt executed_functions.txt > gap_never_executed.txt
```

### Categorize Gap Reasons

```python
#!/usr/bin/env python3
"""Categorize why functions are missing from coverage"""

import json
import re

def categorize_gap(func_name, api_info, condition_info):
    """Determine why function is not covered"""

    reasons = []

    # Check if function has varargs
    if api_info and any("..." in str(arg) for arg in api_info.get("arguments_info", [])):
        reasons.append("varargs")

    # Check for function pointer parameters
    if api_info:
        for arg in api_info.get("arguments_info", []):
            if "(*)" in str(arg.get("type_clang", "")):
                reasons.append("function_pointer_param")

    # Check if conditions exist
    if not condition_info:
        reasons.append("no_constraints")

    # Check for complex types
    if condition_info:
        for key, param in condition_info.items():
            if key.startswith("param_"):
                type_str = param.get("type_string", "")
                if "union" in type_str.lower():
                    reasons.append("union_type")
                if re.search(r'\[\d+\s+x\s+', type_str):  # LLVM array syntax
                    reasons.append("fixed_array")

    # Check for dependency issues
    if condition_info:
        has_deps = any(
            param.get("set_by")
            for key, param in condition_info.items()
            if key.startswith("param_")
        )
        if has_deps:
            reasons.append("has_dependencies")

    return reasons if reasons else ["unknown"]

# Usage example
with open("apis_clang.json") as f:
    apis = {json.loads(line)["function_name"]: json.loads(line) for line in f}

with open("conditions.json") as f:
    conditions = {entry["function_name"]: entry for entry in json.load(f)}

for func_name in gap_functions:
    categories = categorize_gap(
        func_name,
        apis.get(func_name),
        conditions.get(func_name)
    )
    print(f"{func_name}: {', '.join(categories)}")
```

## State of the Art

### Coverage Measurement Evolution

| Old Approach | Current Approach (2026) | When Changed | Impact |
|--------------|-------------------------|--------------|--------|
| Basic block coverage | Branch coverage + edge coverage | LLVM 8+ | More precise path exploration |
| Manual corpus creation | Automatic corpus minimization | libFuzzer 2018+ | Smaller, faster corpus |
| Single coverage metric | Multi-metric (region/function/line/branch) | llvm-cov 10+ | Better gap visibility |
| Post-fuzzing analysis | Live coverage monitoring | Proto-liberator addition | Real-time feedback |

### Function Coverage Best Practices

| Practice | Rationale | Source |
|----------|-----------|--------|
| Use `-show-functions` with llvm-cov | Function-level granularity matches API fuzzing goals | [LLVM docs](https://llvm.org/docs/CommandGuide/llvm-cov.html) |
| Filter harness/infrastructure code | Match libErator methodology (library-only coverage) | libErator FSE'25 paper |
| Track both branch and function coverage | Branch coverage is primary, function coverage shows API reach | Coverage analysis best practices |
| Use `nm -D` for ground truth | Symbol table is authoritative for actual exports | [Baeldung Linux guide](https://www.baeldung.com/linux/shared-library-exported-functions) |

### Deprecated/Outdated Approaches

- **gcov/lcov for fuzzing:** LLVM-based coverage is now standard (faster, more integrated)
- **Manual driver writing:** Automated harness generation (libErator, FuzzGen) is state of art
- **Ignoring function coverage:** Modern practice tracks multiple coverage dimensions
- **Single baseline comparison:** Multi-tier gap analysis provides more insight

## Open Questions

### 1. libpcap Empty conditions.json

**What we know:**
- `apis_clang.json` has 99 functions
- `conditions.json` is 0 bytes (empty file)
- libErator analysis may have failed or produced no output

**What's unclear:**
- Did libErator's static analysis fail on libpcap?
- Is this expected (no extractable constraints)?
- Can we re-run libErator analysis?

**Recommendation:**
- Check libErator logs for libpcap analysis errors
- Try re-running libErator's apipass on libpcap
- Fallback: Use `--include-missing-apis` flag in proto_generator to create stub entries

### 2. Baseline Comparison Target

**What we know:**
- libErator paper doesn't include cJSON, libpcap, libaom benchmarks
- Proto-liberator has current numbers (Jan 2026) but no "before proto-liberator" baseline

**What's unclear:**
- Should we compare against vanilla libFuzzer (no structure)?
- Should we compare against libErator's approach (NDA sequences)?
- Do we need to run libErator's original harnesses for comparison?

**Recommendation:**
- Primary baseline: proto-liberator current numbers (we're improving from here)
- Secondary baseline: If possible, run libErator's generated drivers for same targets
- Document that we're extending libErator, not replacing it

### 3. Internal Function Coverage

**What we know:**
- Phase 1 focuses on exported functions
- Internal/static functions are out of scope

**What's unclear:**
- How much additional coverage would internal functions provide?
- Is 100% exported function coverage sufficient for bug finding?

**Recommendation:**
- Document as future work (Phase 6 in roadmap)
- Focus on exported API completeness first
- Re-evaluate after achieving 80%+ exported function coverage

### 4. Function vs Branch Coverage Priority

**What we know:**
- libErator paper reports branch coverage as primary metric
- Function coverage is easier to understand and measure
- High function coverage doesn't guarantee high branch coverage

**What's unclear:**
- Should Phase 1 optimize for function coverage or branch coverage?
- What's the correlation between the two metrics for these targets?

**Recommendation:**
- Track BOTH metrics in all reports
- Primary goal: 100% function coverage (easier to define "complete")
- Secondary goal: Maximize branch coverage per function
- Report both in format matching libErator Tables 4-6

### 5. Gap Categorization Automation

**What we know:**
- Manual categorization is time-consuming
- Many gaps have detectable signatures (varargs, function pointers, etc.)

**What's unclear:**
- How accurate would automated categorization be?
- Which categories need manual review?

**Recommendation:**
- Build automated categorizer for obvious cases (varargs, function pointers)
- Flag "unknown" category for manual review
- Validate automated results on small sample first

## Recommendations

### Immediate Actions (Week 1)

1. **Build gap analysis script**
   - Input: library path, apis_clang.json, conditions.json, schema.proto
   - Output: JSON report with function counts at each tier
   - Include categorization for missing functions

2. **Generate baseline reports for 3 targets**
   - cJSON: Should be mostly complete (78 functions is small)
   - libpcap: Investigate empty conditions.json issue first
   - libaom: Large API surface (243 functions), expect many gaps

3. **Validate llvm-cov function reporting**
   - Ensure coverage scripts use `-show-functions`
   - Verify library-only filtering works correctly
   - Document how to extract executed function list

### Planning Phase Requirements

Before creating PLAN.md, have these artifacts ready:

1. **Gap analysis JSON report per target** showing:
   - Total exported functions (from nm)
   - Functions in apis_clang.json
   - Functions in conditions.json
   - Functions in schema
   - Functions executed in last campaign
   - Gap counts at each tier

2. **Category distribution** for missing functions:
   - How many are varargs?
   - How many have function pointers?
   - How many have no constraints?
   - How many have dependencies?

3. **Baseline coverage metrics** (already have from Jan 19):
   - cJSON: 76.99% function, 22.19% branch (CMP)
   - libpcap: 13.12% function, 3.27% branch (CMP)
   - libaom: 0.69% function, 0.35% branch (CMP)

4. **Coverage report extraction commands** that work:
   - Verified llvm-cov commands for function lists
   - Verified corpus replay for coverage collection
   - Verified filtering for library-only coverage

### Success Criteria Validation

The phase deliverables are well-defined and achievable:

- ✅ "Know exact count of exported functions per target" - `nm -D` provides this
- ✅ "Know which functions are in current schema vs missing" - grep schema.proto
- ✅ "Have baseline numbers to beat" - Already have from Jan 19 campaigns
- ✅ "Categorized list of unreachable functions and why" - Automated categorizer can provide this

### Risk Mitigation

**Risk: libpcap empty conditions.json**
- **Mitigation:** Use `--include-missing-apis` flag to generate stub schema from apis_clang.json
- **Fallback:** Re-run libErator analysis or use type inference from signatures

**Risk: Too many gap categories to track**
- **Mitigation:** Start with top 3-5 categories (varargs, function pointers, no constraints, dependencies, unknown)
- **Fallback:** Lump rare cases into "other" category

**Risk: Baseline comparison not apples-to-apples**
- **Mitigation:** Clearly document what we're comparing against
- **Fallback:** Focus on absolute coverage numbers rather than relative improvement

## Sources

### Primary (HIGH confidence)
- [libErator GitHub Repository](https://github.com/HexHive/liberator) - Tool implementation and examples
- [libErator FSE'25 Paper](https://nebelwelt.net/files/25FSE2.pdf) - Methodology and evaluation
- [LLVM llvm-cov Documentation](https://llvm.org/docs/CommandGuide/llvm-cov.html) - Official coverage tool reference
- [LLVM Source-based Code Coverage](https://clang.llvm.org/docs/SourceBasedCodeCoverage.html) - Instrumentation guide
- Proto-liberator codebase: `src/proto_generator.py`, `scripts/collect_coverage.sh` - Actual implementation

### Secondary (MEDIUM confidence)
- [Baeldung: View Exported Functions](https://www.baeldung.com/linux/shared-library-exported-functions) - Symbol extraction methods
- [Sumit's Space: External Functions](https://sumit-ghosh.com/posts/list-external-functions-used-exported-executables-shared-libraries/) - nm/objdump usage
- Current campaign data: `workdir/campaigns/*/coverage_summary.txt` - Baseline metrics
- Weekly status update (Jan 19, 2026) - Current coverage numbers

### Tertiary (LOW confidence)
- [Mind the Gap: Fuzz Tests and Coverage](https://dl.acm.org/doi/10.1145/3639477.3639721) - Developer perspective on gaps
- [ICSE 2024: Coverage Analysis](https://appsec.guide/docs/fuzzing/c-cpp/techniques/coverage-analysis/) - General fuzzing coverage practices

## Metadata

**Confidence breakdown:**
- Data sources: HIGH - All files exist in codebase, tools are standard
- Analysis methods: HIGH - Proven techniques (symbol extraction, coverage reporting)
- Gap categories: MEDIUM - Based on code inspection but needs validation
- Baseline numbers: HIGH - Directly from campaign runs and paper

**Research date:** 2026-01-21
**Valid until:** 60 days (stable domain - coverage tools change slowly)

**Key assumptions:**
1. libErator analysis outputs (apis_clang.json, conditions.json) are available for all targets
2. llvm-cov 14+ is available in build environment
3. Target libraries are compiled and available for symbol extraction
4. Current campaign infrastructure (scripts/collect_coverage.sh) is working
