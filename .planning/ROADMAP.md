# Roadmap: Complete Library Fuzzing

**Milestone 1: Achieve 100% Function Coverage with Crash Traceability**

## Phase 1: Baseline & Function Coverage Gap Analysis

**Goal**: Understand exactly which functions are NOT being fuzzed and why.

**Plans:** 5 plans

Plans:
- [ ] 01-01-PLAN.md - Build gap analysis tooling (scripts/gap_analyzer.py)
- [ ] 01-02-PLAN.md - Analyze cJSON function coverage gaps
- [ ] 01-03-PLAN.md - Analyze libpcap function coverage gaps
- [ ] 01-04-PLAN.md - Analyze libaom function coverage gaps
- [ ] 01-05-PLAN.md - Generate consolidated deliverables

**Deliverables**:
- Function gap report per target (cJSON, libpcap, libaom)
- Baseline coverage numbers from libErator paper/runs
- Categorized list of "unreachable" functions and why

**Success Criteria**:
- [ ] Know exact count of exported functions per target
- [ ] Know which functions are in current schema vs missing
- [ ] Have baseline numbers to beat

---

## Phase 2: Complete Function Schema Generation

**Goal**: Generate protobuf schema that includes ALL exported functions, not just NDA-selected subset.

**Plans:** (created by /gsd:plan-phase)

**Tasks**:
1. Modify proto_generator to enumerate all functions from apis_clang.json
2. Generate parameter messages for previously-missing functions
3. Add to v2 Action.oneof so any function can be called
4. Handle edge cases: varargs, function pointers, complex structs
5. Validate schema compiles and harness builds for all 3 targets

**Deliverables**:
- Updated proto_generator with "all functions" mode
- Complete schemas for cJSON, libpcap, libaom
- Build verification for all targets

**Success Criteria**:
- [ ] Schema includes 100% of exported functions
- [ ] Harness compiles for all targets
- [ ] Basic fuzzing runs without crashes in harness itself

---

## Phase 3: Dependency-Aware Sequence Generation

**Goal**: Generate valid API sequences that can reach any function with proper setup.

**Plans:** (created by /gsd:plan-phase)

**Tasks**:
1. Enhance dependency_index.py to cover all functions (not just driver.meta set)
2. Identify required setup sequences for each function (creators, init, config)
3. Implement sequence scheduler that ensures prerequisites are met
4. Add handle/resource tracking for stateful APIs
5. Reduce skip rate to <10% (currently high due to missing dependencies)

**Deliverables**:
- Complete dependency index per target
- Scheduler module that inserts setup calls
- Skip-rate metrics (before/after)

**Success Criteria**:
- [ ] Skip rate <10% for core APIs
- [ ] Every function reachable via some valid sequence
- [ ] No infinite loops in scheduler

---

## Phase 4: Crash Traceability & Reproducers

**Goal**: When crashes occur, produce actionable artifacts that developers can use.

**Plans:** (created by /gsd:plan-phase)

**Tasks**:
1. Implement protobuf decoder for crash inputs (show exact API sequence)
2. Generate standalone C reproducer from crash sequence
3. Add sequence -> real-world pattern mapping (optional)
4. Integrate with CASR for crash deduplication
5. Create crash report format with sequence, input, and stack trace

**Deliverables**:
- `crash_decoder.py` - decode protobuf crash inputs
- `reproducer_generator.py` - emit standalone C files
- Updated campaign scripts with crash processing

**Success Criteria**:
- [ ] Any crash input can be decoded to readable sequence
- [ ] C reproducer compiles and triggers same crash
- [ ] Crash reports include actionable information

---

## Phase 5: Coverage Optimization & Bug Hunting

**Goal**: Push toward 100% function coverage and find real bugs.

**Plans:** (created by /gsd:plan-phase)

**Tasks**:
1. Analyze uncovered functions, add target-specific policies
2. Implement coverage-guided seed selection
3. Add mutation strategies that explore deeper state
4. Run extended campaigns (72h+) with all optimizations
5. Triage crashes, report valid bugs

**Deliverables**:
- Target-specific tuning configs
- Extended campaign results
- Bug reports for any novel findings

**Success Criteria**:
- [ ] cJSON: 100% function coverage
- [ ] libpcap: 80%+ function coverage
- [ ] libaom: 50%+ function coverage
- [ ] At least 1 valid bug per target (stretch)

---

## Phase 6 (Future): Internal Function Coverage

**Goal**: Extend to internal/static functions for truly complete coverage.

**Tasks**:
- Instrument internal functions for visibility
- Generate test points for static functions
- Handle cross-TU dependencies

**Status**: Out of scope for Milestone 1

---

## Dependencies

```
Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 5
                  │           │
                  └───→ Phase 4 ──┘
```

- Phase 2 needs gap analysis from Phase 1
- Phase 3 needs complete schema from Phase 2
- Phase 4 can start once basic fuzzing works (parallel with Phase 3)
- Phase 5 needs both sequencing (3) and traceability (4)

## Timeline Targets

| Phase | Focus |
|-------|-------|
| 1 | Gap analysis - understand current state |
| 2 | Schema completeness - include all functions |
| 3 | Valid sequences - reduce skips |
| 4 | Crash artifacts - reproducibility |
| 5 | Coverage push - hit targets |
