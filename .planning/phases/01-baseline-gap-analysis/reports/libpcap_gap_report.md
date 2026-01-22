# libpcap Function Coverage Gap Report

Generated: 2026-01-22T18:03:16Z

## Summary

| Metric | Count |
|--------|-------|
| Library Exports | N/A (symbol extraction not run) |
| libErator APIs | 99 |
| Functions with Constraints | 88 |
| Functions in Schema | N/A (schema not yet generated) |

## Coverage Percentages

- **API Coverage**: N/A (no library symbol baseline)
- **Constraint Coverage**: **88.89%** (88/99 APIs have constraints)
- **Schema Coverage**: N/A (schema not yet generated)

## Key Finding: Strong Constraint Coverage

Unlike the initial research note that suggested libpcap might have issues with conditions.json, the actual data shows:

- **conditions.json size**: 253,099 bytes (not empty)
- **Function entries**: 88 out of 99 APIs have constraint data
- **Gap**: Only 11 functions missing constraints (11.11%)

This is actually **excellent constraint coverage** - better than libaom (19.3%) and close to cJSON (100%).

## Gap Analysis

### Tier 1: Functions Not Analyzed by libErator

No exported symbols baseline available. Tier 1 analysis skipped.

### Tier 2: Functions Without Constraints (11 functions)

| Function | Category | Notes |
|----------|----------|-------|
| pcap_alloc_option | option API | New options API (pcap 1.10+) |
| pcap_free_option | option API | New options API (pcap 1.10+) |
| pcap_get_option_int | option API | New options API (pcap 1.10+) |
| pcap_get_option_string | option API | New options API (pcap 1.10+) |
| pcap_set_option_int | option API | New options API (pcap 1.10+) |
| pcap_set_option_string | option API | New options API (pcap 1.10+) |
| pcap_remoteact_accept | remote API | Remote capture functionality |
| pcap_remoteact_accept_ex | remote API | Remote capture functionality |
| pcap_remoteact_cleanup | remote API | Remote capture functionality |
| pcap_remoteact_close | remote API | Remote capture functionality |
| pcap_remoteact_list | remote API | Remote capture functionality |

**Pattern**: The 11 missing functions fall into two categories:
1. **pcap_option_* (6 functions)**: Newer options API added in libpcap 1.10+
2. **pcap_remoteact_* (5 functions)**: Remote capture APIs (WinPcap/Npcap extension)

These are likely excluded from libErator analysis because:
- They may not be present in the analyzed libpcap version
- Remote APIs are platform-specific (Windows-focused)

### Tier 3: Schema Exclusions

Not applicable - schema not yet generated.

## Known Blocking Factors for Fuzzing

### 1. Callback-Heavy API Functions

Two critical packet-processing functions require callback parameters:

| Function | Callback Signature |
|----------|-------------------|
| `pcap_loop` | `void (*)(u_char *, const struct pcap_pkthdr *, const u_char *)` |
| `pcap_dispatch` | `void (*)(u_char *, const struct pcap_pkthdr *, const u_char *)` |

**Impact**: These functions ARE in constraints but require special handling:
- Current proto-liberator cannot generate callback stub functions
- These are core packet iteration APIs - missing them limits coverage significantly
- Alternative: Use `pcap_next` or `pcap_next_ex` for packet retrieval (no callbacks)

### 2. Resource Dependencies (pcap_t* Handles)

Most libpcap functions require a valid `pcap_t*` handle. Analysis shows:

**Handle Creators (12 functions)**:
- `pcap_create`, `pcap_open_live`, `pcap_open_offline`, etc.
- All have constraints - good for harness generation

**Handle Consumers (~60+ functions)**:
- Require valid pcap_t* from creator
- Handle management in harness is critical

**Challenge**: Creating valid handles requires:
- Network interface access (for live capture) - **not fuzzable**
- Valid pcap file (for offline) - can be synthesized

### 3. Platform-Specific Functions

Some functions have platform dependencies:
- `pcap_set_protocol_linux` - Linux-only
- `pcap_remoteact_*` - WinPcap/Npcap extension
- `pcap_get_selectable_fd` - Unix FD API

### 4. External Resource Requirements

| Function Group | Resource Needed |
|---------------|-----------------|
| `pcap_open_live`, `pcap_create` | Network interface |
| `pcap_open_offline`, `pcap_fopen_offline` | Valid pcap file |
| `pcap_dump_*` | Writable file path |
| `pcap_findalldevs` | System network config |

## Baseline Performance Analysis

Current proto-liberator performance (Jan 19, 2026):
- **Function Coverage**: 13.12% (CMP mode)
- **Branch Coverage**: 3.27%

**Gap to close**: 86.88% function coverage

### Why is coverage so low despite good constraint data?

1. **Callback functions not fuzzable**: `pcap_loop`, `pcap_dispatch` blocked
2. **Resource initialization**: Most APIs need valid pcap_t* handles
3. **External dependencies**: Live capture needs interfaces, offline needs files
4. **Sequence complexity**: APIs have strict ordering requirements

### Estimated Reachable Coverage

With current capabilities, potentially reachable functions:

| Category | Count | Fuzzable? |
|----------|-------|-----------|
| Stateless/utility functions | 39 | Yes |
| Handle creators (offline) | 6 | Partial (need pcap files) |
| Handle creators (dead) | 3 | Yes (pcap_open_dead) |
| Handle consumers | ~50 | Yes (if handle valid) |
| Callback-based | 2 | No (need callback stubs) |

**Conservative estimate**: 30-40% function coverage achievable without major changes.
**With file corpus**: 50-60% potentially reachable.
**With callback stubs**: 70%+ possible.

## Recommendations

### Immediate (Phase 2)

1. **Focus on pcap_open_dead path**: Creates dummy pcap_t* without network/file
   - `pcap_open_dead(linktype, snaplen)` - fully fuzzable
   - Enables testing many consumer functions

2. **Generate pcap file corpus**: For offline capture path
   - Create minimal valid pcap files with varying structures
   - Enables `pcap_open_offline` and related functions

3. **Prioritize stateless functions**:
   - `bpf_*` functions (filter validation/dumping)
   - `pcap_*_name_to_val`, `pcap_*_val_to_name` (lookup functions)
   - `pcap_statustostr`, `pcap_strerror` (error handling)

### Medium-term (Phase 3)

4. **Implement callback stubs**: For pcap_loop/pcap_dispatch
   - Generate empty callback that just returns
   - Or implement packet-counting callback
   - Significant coverage improvement potential

5. **Add option API support**: If using libpcap 1.10+
   - 6 functions currently without constraints
   - May need updated libErator analysis

### Long-term

6. **Network interface mocking**: For live capture APIs
   - Complex, may not be worth the effort
   - Low ROI vs offline/dead paths

## Function Coverage Breakdown

### Functions WITH Constraints (88) - By Category

**BPF Functions (4)**: `bpf_dump`, `bpf_filter`, `bpf_image`, `bpf_validate`

**Handle Creation (12)**: `pcap_create`, `pcap_open_live`, `pcap_open_dead`, `pcap_open_offline`, etc.

**Handle Configuration (15)**: `pcap_set_snaplen`, `pcap_set_promisc`, `pcap_set_timeout`, etc.

**Packet Capture (7)**: `pcap_loop`, `pcap_dispatch`, `pcap_next`, `pcap_next_ex`, `pcap_breakloop`, etc.

**Filter Compilation (4)**: `pcap_compile`, `pcap_compile_nopcap`, `pcap_setfilter`, `pcap_freecode`

**Datalink Functions (9)**: `pcap_datalink`, `pcap_list_datalinks`, `pcap_datalink_name_to_val`, etc.

**Dumper Functions (8)**: `pcap_dump_open`, `pcap_dump`, `pcap_dump_close`, etc.

**Utility/Info (29)**: `pcap_geterr`, `pcap_stats`, `pcap_snapshot`, `pcap_lib_version`, etc.

### Functions WITHOUT Constraints (11)

**Option API (6)**: `pcap_alloc_option`, `pcap_free_option`, `pcap_get_option_*`, `pcap_set_option_*`

**Remote API (5)**: `pcap_remoteact_accept`, `pcap_remoteact_accept_ex`, `pcap_remoteact_cleanup`, `pcap_remoteact_close`, `pcap_remoteact_list`

## Next Steps for Phase 2

1. Generate schema for libpcap with constraints (88 functions)
2. Create harness focusing on:
   - `pcap_open_dead` path (no external resources)
   - Stateless BPF functions
   - Offline capture with synthesized pcap files
3. Measure coverage improvement
4. Plan callback stub implementation for pcap_loop/pcap_dispatch

---

*Report generated by gap_analyzer.py as part of Phase 1: Baseline Gap Analysis*
