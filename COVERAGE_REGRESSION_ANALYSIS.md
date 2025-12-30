# Coverage Regression Analysis: Dec 16 vs Dec 27 Campaigns (Revalidated)

**Date:** 2025-12-27

**Older campaign:** `/home/priyatam/pin_compete/tools/proto-liberator/workdir/cjson_lpm_24hr_20251216_144614`

**Newer campaign:** `/home/priyatam/pin_compete/tools/proto-liberator/workdir/campaigns/cjson_20251227_005025`

This document revisits and validates the claims in the original analysis using on-disk artifacts (proto diffs, harness code, fuzz logs, and llvm-cov reports).

---

## TL;DR (Validated)

- There is a real *library-only coverage gap* between the Dec 16 final report and the Dec 27 live snapshot.
- The earlier report over-attributed the gap to “typed handle tables”; several mechanisms described there are incorrect.
- `cov:` in `fuzz-0.log` is SanitizerCoverage edge coverage for the whole binary (harness + protobuf + library) and is strongly affected by how many seed inputs are loaded.
- The proto schema is not “identical” between the two runs; it has at least a couple semantic parameter-modeling differences (not just comments).

---

## 1) What Exactly Is Being Compared

### Coverage reports used

- **Dec 16 (final, library-only):** `/home/priyatam/pin_compete/tools/proto-liberator/workdir/cjson_lpm_24hr_20251216_144614/coverage_report.library_only.txt`
- **Dec 27 (live snapshot, library-only):** `/home/priyatam/pin_compete/tools/proto-liberator/workdir/campaigns/cjson_20251227_005025/default/coverage/live/report_full.txt`

Important: “live” vs “final” can differ materially because “final” typically replays a minimized corpus under a dedicated replay budget. This comparison is still useful for diagnosing regressions, but it is not perfectly apples-to-apples unless we run a Dec 27 final replay as well.

---

## 2) Library-Only Coverage Numbers (Validated)

The earlier report mixed “`cJSON.c` only” numbers with “total library” numbers. Below are both:

| File / Total | Dec 16 (final) | Dec 27 (live snapshot) |
|---|---:|---:|
| `cJSON.c` branch cover | **73.95%** | **26.25%** |
| `TOTAL` branch cover | **51.13%** | **18.15%** |

Also validated in both reports: `cJSON_Utils.c` is at **0% coverage**, so the delta is dominated by `cJSON.c`.

---

## 3) Why New Campaign `cov:` Starts at ~2783 (Validated)

The earlier report suggested the high starting `cov:` might be “accumulated coverage” from prior campaigns. The fuzz logs indicate a simpler explanation: **the newer run loads many more seed inputs up front**, so it starts with much higher edge coverage.

- Dec 16: `INFO: -fork=1: 2 seed inputs ...` and first printed stat `cov: 106`
- Dec 27: `INFO: -fork=1: 133 seed inputs ...` and first printed stat `cov: 2783`

Interpretation:

- `cov:` in `fuzz-0.log` = **SanitizerCoverage edge coverage** for the entire binary.
- Higher initial `cov:` commonly means **“more/larger seed corpus”**, not “coverage state leakage”.

Artifacts:

- Dec 16 fuzz log: `/home/priyatam/pin_compete/tools/proto-liberator/workdir/cjson_lpm_24hr_20251216_144614/fuzz-0.log`
- Dec 27 fuzz log: `/home/priyatam/pin_compete/tools/proto-liberator/workdir/campaigns/cjson_20251227_005025/default/fuzz-0.log`

---

## 4) Proto Schema Differences (Revalidated: Prior claim was wrong)

The earlier report said the protos were “nearly identical” and the diff was “trivial”.

Validated reality:

- Line-count is close (`1401` vs `1404`), but `diff -u` shows **semantic changes**, not just comment edits.
- Example: `cJSON_InitHooks_Params` changed from a **handle-based** parameter to a **bytes blob** parameter.
- Example: at least one `i8**` parameter changed from `bytes` to a `*_handle` field (dependency-aware handle mutation instead of raw bytes).

Why it matters:

- Pointer-to-pointer and struct-pointer modeling changes can affect:
  - call validity rates,
  - crash behavior,
  - and which library paths become reachable.

Artifacts:

- Dec 16 proto: `/home/priyatam/pin_compete/tools/proto-liberator/workdir/cjson_lpm_24hr_20251216_144614/cjson.v2.proto`
- Dec 27 proto: `/home/priyatam/pin_compete/tools/proto-liberator/workdir/campaigns/cjson_20251227_005025/default/cjson.v2.proto`

---

## 5) Harness Differences (Validated) and What They Actually Imply

### A) Typed handle tables

Validated:

- Dec 16 harness uses a unified handle namespace.
- Dec 27 harness uses typed handle tables and requires a `type_id` for `handle_get()`.

**Critical correction to the earlier report:**

The Dec 27 harness does *not* “fail because the handle belongs to another type”. Handle IDs are no longer global; each `handle_get(type_id, requested, ...)` selects an index via modulo *inside that type’s table*:

```cpp
uint32_t idx = requested % tab.count;
if (idx == 0) idx = tab.count;
```

So once a table has entries, most mutated integers map to an in-range handle for that type (unless `tab.count == 0` or the selected entry is invalidated).

What typed tables really do:

- They **prevent cross-type pointer confusion** (e.g., a `char*` buffer being used as if it were a `cJSON*`) by removing the shared pointer pool.
- This can be good for “valid-ish usage” exploration, but it can also remove some “UB-driven” crashes/edges.

What is *not validated*:

- The claim that typed tables explain “90% of the regression”.
- The claim that low coverage is primarily caused by “type mismatch => NULL => skip” (that specific mechanism is inconsistent with the modulo selection above).

Artifacts:

- Dec 16 harness: `/home/priyatam/pin_compete/tools/proto-liberator/workdir/cjson_lpm_24hr_20251216_144614/harness.cc`
- Dec 27 harness: `/home/priyatam/pin_compete/tools/proto-liberator/workdir/campaigns/cjson_20251227_005025/default/harness.cc`

### B) Runtime action limit

Validated:

- Dec 27 harness caps actions at 64.
- Dec 16 harness iterates all `input.actions()`.

However, both orchestration logs pass `--max-actions 64` to the generators, so the runtime cap may be redundant in practice unless inputs exceed that constraint.

### C) Fuzzer entry macro changed

Validated:

- Dec 16 uses `DEFINE_PROTO_FUZZER(...)`.
- Dec 27 uses `DEFINE_BINARY_PROTO_FUZZER(...)`.

This can change overhead and throughput characteristics, which can indirectly affect “how much library code gets exercised per unit time”.

### D) API execution stats are missing in Dec 27 harness

Validated:

- Dec 16 harness records per-API `seen/executed/skipped` and writes `api_stats.*.json` at process exit.
- Dec 27 harness does not have this instrumentation.

This blocks an important validation step: proving whether low coverage comes from skipping too much, executing but not going deep, or spending too much time in overhead.

---

## 6) Compilation Flags: “Identical” Is Not Proven (Revalidated)

Both campaigns appear to use LLVM profiling coverage (`-fprofile-instr-generate -fcoverage-mapping`) for `llvm-cov` reports, but the build pipelines are not literally identical (e.g., separate “profile objects” compilation in the Dec 27 launch log).

Given the evidence so far, compilation differences are **not the leading suspect**, but the earlier report’s “IDENTICAL” statement should be downgraded to “similar enough that it’s unlikely to explain a 30–50 point swing without other changes”.

Artifacts:

- Dec 16 build log: `/home/priyatam/pin_compete/tools/proto-liberator/workdir/cjson_lpm_24hr_20251216_144614/orch.log`
- Dec 27 launch log: `/home/priyatam/pin_compete/tools/proto-liberator/workdir/campaigns/launch_cjson_live300_final30m_20251227_005025.log`

---

## 7) Updated Hypothesis (Consistent With Evidence)

The Dec 27 “low library-only coverage” is most consistent with a **multi-factor change**, not a single smoking gun:

1. Harness semantics changed (typed handles + different fuzzer macro + runtime action cap).
2. Proto semantics changed for some APIs (struct-pointer and pointer-to-pointer modeling).
3. Seed corpus differs (133 initial seeds vs 2), which explains the “cov starts at 2783” symptom and can also bias exploration.
4. Live snapshot vs final replay may differ; compare final-vs-final for a clean conclusion.

The earlier report’s key overreach was asserting:

- proto is identical,
- compilation is identical,
- typed handles cause widespread “type mismatch => NULL => skip” behavior,
- typed handles explain ~90% of the regression.

Those are not supported by the artifacts.

---

## 8) Concrete Next Experiments (To Isolate Root Cause)

If the goal is to prove whether harness/proto changes caused the library-only coverage drop, the cleanest experiments are:

1. Hold binary fixed, vary only corpus size/config (2 seeds vs 133 seeds, same replay budgets), compare final library-only.
2. Build two Dec 27 variants: typed handles ON vs OFF (everything else identical), compare final library-only.
3. Add back per-API `seen/executed/skipped` stats to Dec 27 harness to validate “skipping vs executing” as the driver.
4. Re-run Dec 27 with a final replay budget comparable to Dec 16, then compare final-vs-final.

---

**End of Revalidated Analysis**
