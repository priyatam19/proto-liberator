---
phase: 01-baseline-gap-analysis
plan: 01
subsystem: tooling
tags: [gap-analysis, cli-tool, python, bash]

dependency_graph:
  requires: []
  provides: [gap-analyzer-script, symbol-extraction]
  affects: [01-02, 01-03, 01-04, 01-05]

tech_stack:
  added: []
  patterns: [JSONL-parsing, subprocess-shell-integration]

key_files:
  created:
    - scripts/gap_analyzer.py
    - scripts/extract_symbols.sh
  modified: []

decisions:
  - id: gap-output-format
    choice: JSON with counts, gaps lists, coverage percentages, and categorization
    rationale: Machine-readable for downstream processing and human-readable summary

metrics:
  duration: 4 minutes
  completed: 2026-01-22
---

# Phase 01 Plan 01: Build Gap Analysis Tooling Summary

**One-liner**: Three-tier gap analysis tooling comparing library exports, libErator APIs, conditions, and schema coverage with categorization of why functions are missing.

## What Was Built

### scripts/extract_symbols.sh
Bash script that extracts exported function symbols from library files:
- Auto-detects shared (.so) vs static (.a) libraries
- Uses `nm` with appropriate flags for each type
- Filters for text (T) symbols only
- Handles versioned symbols (strips `@@VERSION` suffix)
- Outputs one function name per line

### scripts/gap_analyzer.py
Python CLI implementing three-tier gap analysis:
- **Tier 1**: Library exports vs libErator APIs (functions not analyzed)
- **Tier 2**: libErator APIs vs conditions.json (analyzed but no constraints)
- **Tier 3**: Conditions vs schema (constraints but excluded from schema)

Features:
- Parses JSONL format (apis_clang.json) and JSON array (conditions.json)
- Extracts function names from .proto schema via regex
- Computes coverage percentages at each tier
- Categorizes gaps by reason (varargs, function_pointer_param, complex_type, no_constraints)
- Outputs structured JSON report

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 15e6e94 | add symbol extraction helper script |
| 2 | e6bb2a3 | create gap analyzer Python script |
| 3 | 18d6e07 | add gap categorization to analyzer |

## Key Implementation Details

### Gap Categories
The analyzer detects these patterns in missing functions:
- `varargs` - function has variable arguments (va_list, ...)
- `function_pointer_param` - parameter type contains `(*)`
- `complex_type` - union types or multi-dimensional arrays
- `no_constraints` - in APIs but libErator didn't generate constraints
- `unknown` - no obvious pattern detected

### Output JSON Structure
```json
{
  "library": "name",
  "generated_at": "ISO timestamp",
  "counts": {
    "library_exports": N,
    "liberator_apis": N,
    "with_constraints": N,
    "in_schema": N
  },
  "gaps": {
    "tier1_not_analyzed": [...],
    "tier2_no_constraints": [...],
    "tier3_excluded_schema": [...]
  },
  "coverage_pct": {
    "api_coverage": X.X,
    "constraint_coverage": X.X,
    "schema_coverage": X.X
  },
  "categorized_gaps": {
    "tier2_by_category": {...}
  }
}
```

## Verification Results

Tested on all three priority targets:

| Library | APIs | With Constraints | Tier 2 Gap | Coverage |
|---------|------|------------------|------------|----------|
| cjson | 78 | 78 | 0 | 100.0% |
| libpcap | 99 | 88 | 11 | 88.9% |
| libaom | 243 | 47 | 196 | 19.3% |

All scripts:
- Execute without errors
- Produce valid JSON output
- Handle missing/optional files gracefully
- Run in <5 seconds per target

## Deviations from Plan

None - plan executed exactly as written.

## Next Phase Readiness

This tooling enables:
- Plan 01-02: Run gap analysis on all targets
- Plan 01-03: Run baseline coverage campaigns
- Plan 01-04: Consolidate baseline report

Blockers: None identified.
