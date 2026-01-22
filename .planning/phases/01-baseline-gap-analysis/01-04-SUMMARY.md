---
phase: 01-baseline-gap-analysis
plan: 04
subsystem: gap-analysis
tags: [libaom, av1, codec, gap-analysis, constraints]
dependency-graph:
  requires: [01-01]
  provides: [libaom-gap-report, libaom-architectural-analysis]
  affects: [01-05, 02-xx]
tech-stack:
  added: []
  patterns: [macro-expansion-gap, stateful-codec-analysis]
key-files:
  created:
    - .planning/phases/01-baseline-gap-analysis/reports/libaom_gap_report.json
    - .planning/phases/01-baseline-gap-analysis/reports/libaom_gap_report.md
  modified: []
decisions:
  - id: libaom-constraint-gap
    choice: "80.7% of APIs missing constraints due to macro-generated functions"
    rationale: "196 aom_codec_control_typechecked_* functions cannot be statically analyzed"
  - id: libaom-realistic-target
    choice: "19% function coverage is realistic upper bound for Phase 1"
    rationale: "Only 47 functions have constraints; rest need manual addition"
metrics:
  duration: "~5 minutes"
  completed: "2026-01-22"
---

# Phase 01 Plan 04: Analyze libaom Function Coverage Gaps Summary

**One-liner**: libaom has 80.7% constraint gap from 196 macro-generated control functions; only 47/243 APIs are fuzzable without manual work.

## What Was Done

1. **Ran gap analysis on libaom** (Task 1)
   - Analyzed 243 functions from apis_clang.json
   - Found 47 functions with constraints (19.3%)
   - Identified 196 functions missing constraints (80.7%)

2. **Documented architectural blockers** (Task 2)
   - Explained why 0.69% baseline coverage occurs
   - Categorized 196 missing functions as `aom_codec_control_typechecked_*` macro expansions
   - Created reachability analysis for 47 constrained functions
   - Provided short/medium/long term recommendations

## Key Findings

### Constraint Gap Analysis

| Metric | Value |
|--------|-------|
| Total APIs | 243 |
| With Constraints | 47 (19.3%) |
| Missing Constraints | 196 (80.7%) |

### Why 0.69% Coverage?

1. **Codec init sequence complexity** - Encoder/decoder require strict initialization
2. **State machine dependencies** - Functions need active codec context
3. **Macro-generated function gap** - 196 `aom_codec_control_typechecked_*` functions from C macros

### Constrained Functions (Fuzzable Now)

The 47 functions with constraints fall into categories:
- Codec lifecycle: `aom_codec_*_init_ver`, `aom_codec_encode/decode`, `aom_codec_destroy`
- Image utilities: `aom_img_alloc*`, `aom_img_free`, `aom_img_set_rect`
- Stateless utilities: `aom_codec_version*`, `aom_uleb_*`, `aom_obu_type_to_string`

### Missing Functions (Need Manual Work)

All 196 missing functions are `aom_codec_control_typechecked_<CONTROL_ID>`:
- Encoder settings (~100): `AV1E_SET_*`
- Decoder settings (~30): `AV1D_SET_*`
- Getters (~40): `AOMD_GET_*`, `AV1E_GET_*`
- Shared controls (~26): `AV1_*`

## Commits

| Hash | Type | Description |
|------|------|-------------|
| eb9038b | feat | run libaom gap analysis |
| 0c0bd73 | docs | document libaom architectural blockers |

## Artifacts Produced

1. **libaom_gap_report.json** (419 lines)
   - Machine-readable gap data
   - Full list of 196 missing functions
   - Coverage percentages

2. **libaom_gap_report.md** (254 lines)
   - Executive summary
   - Architectural analysis (init, state, macros)
   - Reachability assessment
   - Risk table and recommendations

## Deviations from Plan

None - plan executed exactly as written.

## Next Phase Readiness

### For Phase 2 (Schema Generation)
- Only 47 functions should be included in libaom schema
- 196 macro functions require manual constraint generation (medium-term)

### Blockers Identified
- libaom cannot exceed 19.3% function coverage without manual constraint work
- Codec initialization sequence must be understood for encode/decode coverage

### Recommended Priority
- libaom is LOWEST priority for Phase 2 due to massive constraint gap
- Focus on cJSON (100% constraints) and libpcap (88.9% constraints) first

## Success Criteria Checklist

- [x] libaom_gap_report.json exists with 243 functions analyzed
- [x] Markdown explains why 0.69% coverage occurs
- [x] Report identifies "low hanging fruit" functions (stateless utilities)
- [x] Realistic coverage targets documented (19% upper bound)
