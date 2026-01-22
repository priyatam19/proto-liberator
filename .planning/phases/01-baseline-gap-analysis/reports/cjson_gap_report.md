# cJSON Function Coverage Gap Analysis

**Generated**: 2026-01-22
**Library**: cjson
**Analysis Tool**: `scripts/gap_analyzer.py`

## Executive Summary

cJSON has **100% constraint coverage** - all 78 exported functions are analyzed by libErator and have parameter constraints in `conditions.json`. This makes cJSON an ideal reference target for Proto-libErator development.

## Coverage Summary

| Tier | Metric | Count | Coverage |
|------|--------|-------|----------|
| Library Exports | Functions exported by libcjson.a | 78 | - |
| Tier 1 | Functions analyzed by libErator (apis_clang.json) | 78 | 100.0% |
| Tier 2 | Functions with constraints (conditions.json) | 78 | 100.0% |
| Tier 3 | Functions in generated schema (.proto) | N/A | - |

## Gap Analysis by Tier

### Tier 1: Library Exports vs libErator APIs

**Gap Size**: 0 functions

All library exports are analyzed by libErator. No functions are missing from `apis_clang.json`.

### Tier 2: libErator APIs vs Constraints

**Gap Size**: 0 functions

All 78 APIs have full parameter constraints in `conditions.json`. This is the ideal state - every function that libErator can analyze has been fully processed.

### Tier 3: Constraints vs Schema

**Gap Size**: N/A (schema not analyzed)

No `.proto` schema was provided for this analysis. Tier 3 gap analysis requires running `proto_generator.py` first.

## Function Categories

### Parsing Functions (4)
- `cJSON_Parse`
- `cJSON_ParseWithLength`
- `cJSON_ParseWithOpts`
- `cJSON_ParseWithLengthOpts`

### Printing Functions (4)
- `cJSON_Print`
- `cJSON_PrintUnformatted`
- `cJSON_PrintBuffered`
- `cJSON_PrintPreallocated`

### Creation Functions (17)
- `cJSON_CreateNull`, `cJSON_CreateTrue`, `cJSON_CreateFalse`, `cJSON_CreateBool`
- `cJSON_CreateNumber`, `cJSON_CreateString`, `cJSON_CreateRaw`
- `cJSON_CreateArray`, `cJSON_CreateObject`
- `cJSON_CreateStringReference`, `cJSON_CreateObjectReference`, `cJSON_CreateArrayReference`
- `cJSON_CreateIntArray`, `cJSON_CreateFloatArray`, `cJSON_CreateDoubleArray`, `cJSON_CreateStringArray`
- `cJSON_Duplicate`

### Access Functions (11)
- `cJSON_GetArraySize`, `cJSON_GetArrayItem`
- `cJSON_GetObjectItem`, `cJSON_GetObjectItemCaseSensitive`, `cJSON_HasObjectItem`
- `cJSON_GetStringValue`, `cJSON_GetNumberValue`
- `cJSON_GetErrorPtr`
- `cJSON_Version`

### Type Check Functions (10)
- `cJSON_IsInvalid`, `cJSON_IsFalse`, `cJSON_IsTrue`, `cJSON_IsBool`
- `cJSON_IsNull`, `cJSON_IsNumber`, `cJSON_IsString`
- `cJSON_IsArray`, `cJSON_IsObject`, `cJSON_IsRaw`

### Modification Functions (22)
- Add to Array: `cJSON_AddItemToArray`, `cJSON_AddItemReferenceToArray`, `cJSON_InsertItemInArray`
- Add to Object: `cJSON_AddItemToObject`, `cJSON_AddItemToObjectCS`, `cJSON_AddItemReferenceToObject`
- Add helpers: `cJSON_AddNullToObject`, `cJSON_AddTrueToObject`, `cJSON_AddFalseToObject`, `cJSON_AddBoolToObject`, `cJSON_AddNumberToObject`, `cJSON_AddStringToObject`, `cJSON_AddRawToObject`, `cJSON_AddObjectToObject`, `cJSON_AddArrayToObject`
- Detach: `cJSON_DetachItemFromArray`, `cJSON_DetachItemFromObject`, `cJSON_DetachItemFromObjectCaseSensitive`, `cJSON_DetachItemViaPointer`
- Replace: `cJSON_ReplaceItemInArray`, `cJSON_ReplaceItemInObject`, `cJSON_ReplaceItemInObjectCaseSensitive`, `cJSON_ReplaceItemViaPointer`

### Deletion Functions (4)
- `cJSON_Delete`
- `cJSON_DeleteItemFromArray`
- `cJSON_DeleteItemFromObject`, `cJSON_DeleteItemFromObjectCaseSensitive`

### Utility Functions (6)
- `cJSON_Compare`
- `cJSON_Minify`
- `cJSON_SetNumberHelper`, `cJSON_SetValuestring`
- `cJSON_malloc`, `cJSON_free`
- `cJSON_InitHooks`

## Baseline Performance Context

From January 19, 2026 fuzzing campaign:

| Metric | Value | Notes |
|--------|-------|-------|
| Function Coverage | 76.99% | CMP tracing variant |
| Branch Coverage | 22.19% | CMP tracing variant |
| Duration | 24 hours | Full campaign |

**Gap from 100%**: ~18 functions not reached during fuzzing (23% of 78).

The constraint coverage is complete (100%), so the function coverage gap is not due to missing API analysis. The gap likely comes from:
1. Insufficient API sequence diversity (v2 super-harness needed)
2. Missing edge-case input values
3. Complex control flow paths not exercised

## Recommendations

1. **Schema Generation**: Run `proto_generator.py` to complete Tier 3 analysis
2. **Sequence Analysis**: Investigate which functions are not being called by examining fuzzer traces
3. **Input Value Analysis**: Check if specific parameter values unlock unreached code paths
4. **Use as Reference**: cJSON's 100% constraint coverage makes it ideal for validating tooling

## Data Sources

- **Library Path**: `analysis/cjson/work/lib/libcjson.a`
- **APIs**: `analysis/cjson/work/apipass/apis_clang.json` (78 entries)
- **Constraints**: `analysis/cjson/work/apipass/conditions.json` (78 entries)
- **Header**: `analysis/cjson/work/include/cjson/cJSON.h`

## JSON Report

Machine-readable data available at:
`.planning/phases/01-baseline-gap-analysis/reports/cjson_gap_report.json`
