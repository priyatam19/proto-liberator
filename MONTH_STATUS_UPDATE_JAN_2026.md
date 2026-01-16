# Proto-Liberator Simple Harness: 1-Month Status Update
**Date:** January 13, 2026
**Period:** December 17, 2025 - January 13, 2026
**Presenter:** Priyatam

---

## Slide 1: Agenda
- Dec 17 baseline status
- Crash scale problem and triage
- cJSON results and coverage comparison
- Scaling gap on larger libraries
- Experiments (typed handles, hybrid, seeds)
- Current understanding and next steps

---

## Slide 2: Tool Overview and Pipeline
```
┌─────────────────────┐
│ Static Analysis     │
│ (Liberator/SVF)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Proto Generation    │
│ (Type-aware schemas)│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Harness Generation  │
│ (Dynamic Dispatch)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Fuzzer Integration  │
│ (LibFuzzer in-proc) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Campaign Launch     │
│ (1hr / 24hr runs)   │
└─────────────────────┘
```

**Key Features:**
- Protobuf-based parameter fuzzing
- Dynamic function dispatch
- In-process fuzzing (fork on crash)
- Pointer handle management (single table; typed attempt evaluated)

---

## Slide 3: Status on Dec 17, 2025 (Baseline)
- Integrated Liberator output: `/home/priyatam/pin_compete/tools/analysis/cjson/work/apipass`
- End-to-end pipeline validated: proto gen -> harness -> fuzzer -> campaign
- cJSON campaigns:
  - 1 hr: ~60% branch coverage
  - 24 hr: ~78% branch coverage
- Problem: ~4,000 crashes, manual triage infeasible

---

## Slide 4: Crash Scale Problem (Dynamic Dispatch)
- Random function selection using protobuf-decoded bytes
- Subsequent calls chosen from input bytes
- In-process fuzzing enables fork-on-crash and continued execution
- Side effect: many crashes of unclear exploitability

---

## Slide 5: Hardening Attempt (Rejected)
- Added input validity checks (null pointers, basic guards)
- Outcome (cJSON):

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Crashes | ~4,000 | ~1,000 | -75% |
| Coverage | ~78% | ~20% | -75% |
| Throughput | Baseline | ~25% | -75% |

**Conclusion:** strict checks block too many paths; coverage collapses.

---

## Slide 6: CASR Integration and cJSON Results
- Reverted strict checks and added CASR (LLVM) for triage and clustering
- CASR reduces ~4,000 crashes to 20-40 clusters
- Classification: EXPLOITABLE / POTENTIALLY_EXPLOITABLE / NOT_EXPLOITABLE
- Verified 4-5 exploitable crashes on cJSON
- Found both EBOSS challenge bugs in whole-library fuzzing

---

## Slide 7: Coverage Comparison (cJSON)
| Tool | Branch Coverage |
|------|------------------|
| Proto-Liberator Simple Harness | ~80% |
| Liberator | ~75% |
| Hooper | ~87% |
| OSS-Fuzz | ~46% |

**Takeaway:** approach is competitive on cJSON.

---

## Slide 8: Scaling Gap on Larger Libraries
- Tested: c-ares, libpcap, libtiff, libaom
- Coverage is ~1.5-2x lower than competitors
- Coverage saturates after ~15-20 minutes on most libraries
- cJSON continues improving beyond 1-2 hours

---

## Slide 9: Experiments Summary (What Did Not Help)
- Typed handle tables: coverage dropped ~15-20%, fewer crashes
- Hybrid strict + lenient campaigns sharing corpus: no improvement
- Seed vs zero-seed campaigns: no consistent long-term benefit

---

## Slide 10: Coverage Saturation Observation
- cJSON: continues to gain coverage after 1-2 hours
- Larger libs: plateau at 15-20 minutes
- Hypothesis: complex type/state requirements block deeper exploration

---

## Slide 11: Current Understanding
- Lenient pointer reuse enables cross-mutations and higher coverage
- Strict checks reduce false positives but limit exploration
- cJSON is structurally simple; complex libraries need better type/state flow

---

## Slide 12: Next Steps and Decision Ask
**Proposed direction (short list):**
1. Selective typing: enforce only on critical structs
2. Feedback-guided dispatch: bias toward new coverage paths
3. Initialization phases for complex libraries

**Decision needed:**
- Focus on scaling to complex libraries vs. productizing cJSON-level success

---

# Backup Slides (Optional)

## Backup 1: Dynamic Dispatch Pseudocode
```c
// Current approach
while (1) {
    FuzzInput input = decode_protobuf(data);
    int func_id = input.function_id % NUM_FUNCTIONS;
    void* handle = handle_table[input.handle_id % num_handles];
    call_function(func_id, handle, input.params);
    if (is_pointer_return(func_id)) {
        handle_table[num_handles++] = return_value;
    }
}
```

---

## Backup 2: Typed Handle Tables (Summary)
- Separate handle table per struct type
- On cJSON: coverage -15 to -20%, crashes reduced 60-70%
- Tradeoff: fewer cross-mutations, high input rejection

---

## Backup 3: Seed Generation Snapshot (1hr Runs)
| Library | No Seeds | With Seeds | Difference |
|---------|----------|------------|------------|
| cJSON | 78.2% | 79.1% | +0.9% |
| c-ares | 45.3% | 43.8% | -1.5% |
| libpcap | 52.1% | 53.4% | +1.3% |
| libtiff | 38.7% | 38.2% | -0.5% |
| libaom | 31.2% | 32.1% | +0.9% |

---

## Backup 4: CASR Clustering Example
```
Group 1 (15 crashes): Stack overflow in cJSON_Minify
  -> Exploitability: EXPLOITABLE
  -> Stacktrace: parse_value -> parse_object -> cJSON_Minify

Group 2 (450 crashes): Null dereference in print_string_ptr
  -> Exploitability: NOT_EXPLOITABLE
  -> Stacktrace: print_value -> print_string_ptr -> strlen(NULL)

Group 3 (8 crashes): Heap overflow in ensure
  -> Exploitability: EXPLOITABLE
  -> Stacktrace: print_value -> ensure -> realloc
```
