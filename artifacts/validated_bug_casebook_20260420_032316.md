# Validated Crash/Vulnerability Casebook (Best Campaigns)

- Generated: 2026-04-20T03:23:16
- Source strict bug list: `/home/fuzzserver/Research/proto-liberator/artifacts/best_campaigns_real_bugs_strict_20260419_235517.tsv`
- Bug count in this casebook: **36** (high-confidence validated)

## Scope and Confidence

- This document covers the validated/high-confidence bugs from CASR triage.
- Each case includes concrete sanitizer evidence, reproducible crash input, and exploit-path reasoning suitable for developer triage.
- The argument for "real crash" is based on ASan evidence + target-function crash location + reproducible crashing test case in campaign artifacts.
- Note: some historical `cjson` entries include CASR reports copied from an earlier environment where the exact crash corpus file was not preserved locally; those cases still include strong ASan/stack evidence but may require re-generation of the exact crashing input in this workspace.

## Quick Stats by Library

| Library | Validated Bugs | CASR Clusters (campaign) | Exploitable+Probably clusters |
|---|---:|---:|---:|
| c-ares | 6 | 34 | 6 + 13 |
| cjson | 5 | 36 | 7 + 0 |
| libdwarf | 13 | 74 | 14 + 28 |
| libhtp | 1 | 66 | 1 + 21 |
| libpcap | 3 | 75 | 5 + 7 |
| libplist | 3 | 155 | 4 + 1 |
| libsndfile | 1 | 6 | 1 + 0 |
| libtiff | 4 | 152 | 4 + 13 |

## c-ares

### Case 1: `c-ares` - `heap-buffer-overflow(write)` in `ares_create_query_int`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `ares_create_query_int` at `ares_create_query.c`
- CASR crash line hint: `ares_create_query.c`
- Cluster evidence size: `1` crashing input(s) in cluster `cl13`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3346670==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x502000020a70 at pc 0x00000093be8a bp 0x7fffffffb590 sp 0x7fffffffb588`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow ares_create_query.c in ares_create_query_int`
- Top stack frame: `#0 0x93be89 in ares_create_query_int ares_create_query.c`
- Next frame(s): `#1 0x93bb92 in ares_create_query (/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x93bb92) (BuildId: e8848e795f9514b0fc80062f16d57bf2e3dc4ad8)`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/casr/clusters/cl13/_home_fuzzserver_Research_proto-liberator_artifacts_c-ares_c-ares_c-ares_20260324_165513_default_casr_triage_cl21_crash-7ad7e35d5396e05488630f5f53b30706201d5d1f.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DNS query/record parsing and helper API path handling attacker-controlled DNS-formatted data.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/artifacts/crash-7ad7e35d5396e05488630f5f53b30706201d5d1f
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/artifacts/crash-7ad7e35d5396e05488630f5f53b30706201d5d1f`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 2: `c-ares` - `heap-buffer-overflow(write)` in `ares_dns_pton`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `ares_dns_pton` at `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x8f8ab1`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x8f8ab1`
- Cluster evidence size: `1` crashing input(s) in cluster `cl20`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3341181==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x502000020a90 at pc 0x0000008f8ab2 bp 0x7fffffffb660 sp 0x7fffffffb658`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x8f8ab1) (BuildId: e8848e795f9514b0fc80062f16d57bf2e3dc4ad8) in ares_dns_pton`
- Top stack frame: `#0 0x8f8ab1 in ares_dns_pton (/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x8f8ab1) (BuildId: e8848e795f9514b0fc80062f16d57bf2e3dc4ad8)`
- Next frame(s): `#1 0x5bf13f in TestOneProtoInput(c_ares_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260325_121652_cares/c-ares/c-ares_20260324_165513/default/harness.cc:5296:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/casr/clusters/cl20/_home_fuzzserver_Research_proto-liberator_artifacts_c-ares_c-ares_c-ares_20260324_165513_default_casr_triage_cl28_crash-b48f1042072a8934f182803f68c0f1760feade7f.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DNS query/record parsing and helper API path handling attacker-controlled DNS-formatted data.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/artifacts/crash-b48f1042072a8934f182803f68c0f1760feade7f
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/artifacts/crash-b48f1042072a8934f182803f68c0f1760feade7f`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 3: `c-ares` - `heap-buffer-overflow(write)` in `ares_dns_rr_get_keys`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `ares_dns_rr_get_keys` at `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x90c087`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x90c087`
- Cluster evidence size: `1` crashing input(s) in cluster `cl16`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3342658==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x502000020a70 at pc 0x00000090c088 bp 0x7fffffffb680 sp 0x7fffffffb678`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x90c087) (BuildId: e8848e795f9514b0fc80062f16d57bf2e3dc4ad8) in ares_dns_rr_get_keys`
- Top stack frame: `#0 0x90c087 in ares_dns_rr_get_keys (/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x90c087) (BuildId: e8848e795f9514b0fc80062f16d57bf2e3dc4ad8)`
- Next frame(s): `#1 0x5a4c0a in TestOneProtoInput(c_ares_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260325_121652_cares/c-ares/c-ares_20260324_165513/default/harness.cc:8955:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/casr/clusters/cl16/_home_fuzzserver_Research_proto-liberator_artifacts_c-ares_c-ares_c-ares_20260324_165513_default_casr_triage_cl24_crash-9f819dcc9c81da90da612958417468beed9c2ef2.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DNS query/record parsing and helper API path handling attacker-controlled DNS-formatted data.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/artifacts/crash-9f819dcc9c81da90da612958417468beed9c2ef2
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/artifacts/crash-9f819dcc9c81da90da612958417468beed9c2ef2`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 4: `c-ares` - `heap-buffer-overflow(write)` in `ares_dns_rr_get_opt_byid`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `ares_dns_rr_get_opt_byid` at `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x91a745`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x91a745`
- Cluster evidence size: `1` crashing input(s) in cluster `cl23`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3347636==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x502000020a70 at pc 0x00000091a746 bp 0x7fffffffb5f0 sp 0x7fffffffb5e8`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x91a745) (BuildId: e8848e795f9514b0fc80062f16d57bf2e3dc4ad8) in ares_dns_rr_get_opt_byid`
- Top stack frame: `#0 0x91a745 in ares_dns_rr_get_opt_byid (/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x91a745) (BuildId: e8848e795f9514b0fc80062f16d57bf2e3dc4ad8)`
- Next frame(s): `#1 0x5bda1f in TestOneProtoInput(c_ares_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260325_121652_cares/c-ares/c-ares_20260324_165513/default/harness.cc:9581:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/casr/clusters/cl23/_home_fuzzserver_Research_proto-liberator_artifacts_c-ares_c-ares_c-ares_20260324_165513_default_casr_triage_cl30_crash-ef7b7b2edfd182117fc79599666147235a1ccd9d.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DNS query/record parsing and helper API path handling attacker-controlled DNS-formatted data.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/artifacts/crash-ef7b7b2edfd182117fc79599666147235a1ccd9d
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/artifacts/crash-ef7b7b2edfd182117fc79599666147235a1ccd9d`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 5: `c-ares` - `heap-buffer-overflow(write)` in `ares_expand_name`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `ares_expand_name` at `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x92899f`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x92899f`
- Cluster evidence size: `1` crashing input(s) in cluster `cl18`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3347255==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x502000020a70 at pc 0x0000009289a0 bp 0x7fffffffb650 sp 0x7fffffffb648`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x92899f) (BuildId: e8848e795f9514b0fc80062f16d57bf2e3dc4ad8) in ares_expand_name`
- Top stack frame: `#0 0x92899f in ares_expand_name (/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x92899f) (BuildId: e8848e795f9514b0fc80062f16d57bf2e3dc4ad8)`
- Next frame(s): `#1 0x5c01e6 in TestOneProtoInput(c_ares_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260325_121652_cares/c-ares/c-ares_20260324_165513/default/harness.cc:12874:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/casr/clusters/cl18/_home_fuzzserver_Research_proto-liberator_artifacts_c-ares_c-ares_c-ares_20260324_165513_default_casr_triage_cl26_crash-a387811a74f17d7e9a2c7ea02d11c6540d4a79ae.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DNS query/record parsing and helper API path handling attacker-controlled DNS-formatted data.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/artifacts/crash-a387811a74f17d7e9a2c7ea02d11c6540d4a79ae
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/artifacts/crash-a387811a74f17d7e9a2c7ea02d11c6540d4a79ae`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 6: `c-ares` - `heap-buffer-overflow(write)` in `ares_version`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `ares_version` at `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x96d312`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x96d312`
- Cluster evidence size: `1` crashing input(s) in cluster `cl4`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3342398==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x502000020a70 at pc 0x00000096d313 bp 0x7fffffffb720 sp 0x7fffffffb718`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x96d312) (BuildId: e8848e795f9514b0fc80062f16d57bf2e3dc4ad8) in ares_version`
- Top stack frame: `#0 0x96d312 in ares_version (/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin+0x96d312) (BuildId: e8848e795f9514b0fc80062f16d57bf2e3dc4ad8)`
- Next frame(s): `#1 0x5aa500 in TestOneProtoInput(c_ares_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260325_121652_cares/c-ares/c-ares_20260324_165513/default/harness.cc:24441:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/casr/clusters/cl4/_home_fuzzserver_Research_proto-liberator_artifacts_c-ares_c-ares_c-ares_20260324_165513_default_casr_triage_cl13_crash-2183c7d761b1e89bb43895baaa54c5ba33e9bfc9.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DNS query/record parsing and helper API path handling attacker-controlled DNS-formatted data.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/artifacts/crash-2183c7d761b1e89bb43895baaa54c5ba33e9bfc9
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/c-ares_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/c-ares/c-ares/c-ares_20260324_165513/default/artifacts/crash-2183c7d761b1e89bb43895baaa54c5ba33e9bfc9`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

## cjson

### Case 7: `cjson` - `heap-buffer-overflow(write)` in `__asan_memcpy`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `__asan_memcpy` at `/home/priyatam/older_campaigns_proto-lib/cjson_lpm_24hr_20251216_144614/rerun_newcfg_notimeout_20251227_162411/cjson_fuzzer.bin+0x4ea019`
- CASR crash line hint: `/home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:944:9`
- Cluster evidence size: `8` crashing input(s) in cluster `cl36`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==1895526==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000015111 at pc 0x0000004ea01a bp 0x7fffffffc5f0 sp 0x7fffffffbdc0`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/priyatam/older_campaigns_proto-lib/cjson_lpm_24hr_20251216_144614/rerun_newcfg_notimeout_20251227_162411/cjson_fuzzer.bin+0x4ea019) (BuildId: e85360909167e0e405404883bc8a22a223025a53) in __asan_memcpy`
- Top stack frame: `#0 0x4ea019 in __asan_memcpy (/home/priyatam/older_campaigns_proto-lib/cjson_lpm_24hr_20251216_144614/rerun_newcfg_notimeout_20251227_162411/cjson_fuzzer.bin+0x4ea019) (BuildId: e85360909167e0e405404883bc8a22a223025a53)`
- Next frame(s): `#1 0x645235 in print_string_ptr /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:944:9`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/cjson/rerun_newcfg_notimeout_20251227_162411/casr/clusters/cl36/_home_priyatam_older_campaigns_proto-lib_cjson_lpm_24hr_20251216_144614_rerun_newcfg_notimeout_20251227_162411_casr_triage_cl32_crash-007b4fb27cceb8ec0e771bc009825b44a0b218b6.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: JSON parse/print/manipulation path handling attacker-controlled JSON values.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
- Could not fully auto-resolve both binary and crash input from CASR metadata; use campaign root and crash basename from CASR ProcCmdline.
- Campaign root guess: `/home/fuzzserver/Research/proto-liberator/artifacts/cjson/rerun_newcfg_notimeout_20251227_162411`
- Crash basename: `crash-007b4fb27cceb8ec0e771bc009825b44a0b218b6`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 8: `cjson` - `heap-buffer-overflow(write)` in `print_array`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `print_array` at `/home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c`
- CASR crash line hint: `/home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:1629:23`
- Cluster evidence size: `4` crashing input(s) in cluster `cl22`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==4002179==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000015111 at pc 0x00000063c4fb bp 0x7fffffffc650 sp 0x7fffffffc648`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:1629:23 in print_array`
- Top stack frame: `#0 0x63c4fa in print_array /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:1629:23`
- Next frame(s): `#1 0x63c4fa in print_value /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:1466:20`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/cjson/rerun_newcfg_notimeout_20251227_162411/casr/clusters/cl22/_home_priyatam_older_campaigns_proto-lib_cjson_lpm_24hr_20251216_144614_rerun_newcfg_notimeout_20251227_162411_casr_triage_cl18_crash-00e9101fbc4fa7ee8c25f24477ab3975e0eb2f31.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: JSON parse/print/manipulation path handling attacker-controlled JSON values.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
- Could not fully auto-resolve both binary and crash input from CASR metadata; use campaign root and crash basename from CASR ProcCmdline.
- Campaign root guess: `/home/fuzzserver/Research/proto-liberator/artifacts/cjson/rerun_newcfg_notimeout_20251227_162411`
- Crash basename: `crash-00e9101fbc4fa7ee8c25f24477ab3975e0eb2f31`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 9: `cjson` - `heap-buffer-overflow(write)` in `print_number`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `print_number` at `/home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c`
- CASR crash line hint: `/home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:626:23`
- Cluster evidence size: `3` crashing input(s) in cluster `cl21`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==1721448==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000015111 at pc 0x00000063c53f bp 0x7fffffffc650 sp 0x7fffffffc648`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:626:23 in print_number`
- Top stack frame: `#0 0x63c53e in print_number /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:626:23`
- Next frame(s): `#1 0x63c53e in print_value /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:1442:20`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/cjson/rerun_newcfg_notimeout_20251227_162411/casr/clusters/cl21/_home_priyatam_older_campaigns_proto-lib_cjson_lpm_24hr_20251216_144614_rerun_newcfg_notimeout_20251227_162411_casr_triage_cl16_crash-0000d7d14eec10bdbdfbac92b2aac847c026cf2e.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: JSON parse/print/manipulation path handling attacker-controlled JSON values.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
- Could not fully auto-resolve both binary and crash input from CASR metadata; use campaign root and crash basename from CASR ProcCmdline.
- Campaign root guess: `/home/fuzzserver/Research/proto-liberator/artifacts/cjson/rerun_newcfg_notimeout_20251227_162411`
- Crash basename: `crash-0000d7d14eec10bdbdfbac92b2aac847c026cf2e`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 10: `cjson` - `heap-buffer-overflow(write)` in `print_object`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `print_object` at `/home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c`
- CASR crash line hint: `/home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:1778:27`
- Cluster evidence size: `2` crashing input(s) in cluster `cl16`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3804127==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000015171 at pc 0x00000063c4b5 bp 0x7fffffffc650 sp 0x7fffffffc648`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:1778:27 in print_object`
- Top stack frame: `#0 0x63c4b4 in print_object /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:1778:27`
- Next frame(s): `#1 0x63c4b4 in print_value /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:1469:20`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/cjson/rerun_newcfg_notimeout_20251227_162411/casr/clusters/cl16/_home_priyatam_older_campaigns_proto-lib_cjson_lpm_24hr_20251216_144614_rerun_newcfg_notimeout_20251227_162411_casr_triage_cl17_crash-26b3574e6c15df9ba6a0341c854065f607dff0c5.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: JSON parse/print/manipulation path handling attacker-controlled JSON values.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
- Could not fully auto-resolve both binary and crash input from CASR metadata; use campaign root and crash basename from CASR ProcCmdline.
- Campaign root guess: `/home/fuzzserver/Research/proto-liberator/artifacts/cjson/rerun_newcfg_notimeout_20251227_162411`
- Crash basename: `crash-26b3574e6c15df9ba6a0341c854065f607dff0c5`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 11: `cjson` - `heap-use-after-free(write)` in `cJSON_ReplaceItemViaPointer`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-use-after-free(write)` (Use of deallocated memory)
- Crashing location: `cJSON_ReplaceItemViaPointer` at `/home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c`
- CASR crash line hint: `/home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:2351:23`
- Cluster evidence size: `2` crashing input(s) in cluster `cl29`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==56191==ERROR: AddressSanitizer: heap-use-after-free on address 0x60600000d0a0 at pc 0x000000640135 bp 0x7fffffffc880 sp 0x7fffffffc878`
- ASan summary: `SUMMARY: AddressSanitizer: heap-use-after-free /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:2351:23 in cJSON_ReplaceItemViaPointer`
- Top stack frame: `#0 0x640134 in cJSON_ReplaceItemViaPointer /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:2351:23`
- Next frame(s): `#1 0x6402b5 in cJSON_ReplaceItemInArray /home/priyatam/pin_compete/tools/liberator/targets/cjson/repo/cJSON.c:2395:12`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/cjson/rerun_newcfg_notimeout_20251227_162411/casr/clusters/cl29/_home_priyatam_older_campaigns_proto-lib_cjson_lpm_24hr_20251216_144614_rerun_newcfg_notimeout_20251227_162411_casr_triage_cl24_crash-04a2995f7e05fe33b6c1f59c42ebb48c1eaa89ad.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: JSON parse/print/manipulation path handling attacker-controlled JSON values.
- Memory primitive: Write via dangling pointer (freed object reused).
- Trigger mechanics: Attacker shapes object lifetime via input sequence, then triggers write to stale pointer after free.
- Security impact: High-risk memory corruption; potentially controllable overwrite of reallocated object memory.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
- Could not fully auto-resolve both binary and crash input from CASR metadata; use campaign root and crash basename from CASR ProcCmdline.
- Campaign root guess: `/home/fuzzserver/Research/proto-liberator/artifacts/cjson/rerun_newcfg_notimeout_20251227_162411`
- Crash basename: `crash-04a2995f7e05fe33b6c1f59c42ebb48c1eaa89ad`

**Recommended fix direction**
- Rework ownership/lifetime transitions; null out or invalidate pointers after free and prevent stale alias writes/reads.
- Add lifetime-focused unit/regression tests to verify no post-free dereference on the triggering path.

---

## libdwarf

### Case 12: `libdwarf` - `heap-buffer-overflow(write)` in `_dwarf_get_fde_list_internal`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `_dwarf_get_fde_list_internal` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd520ea`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd520ea`
- Cluster evidence size: `1` crashing input(s) in cluster `cl14`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3821172==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c630 at pc 0x000000d520eb bp 0x7ffffffe3f50 sp 0x7ffffffe3f48`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd520ea) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in _dwarf_get_fde_list_internal`
- Top stack frame: `#0 0xd520ea in _dwarf_get_fde_list_internal (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd520ea) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0xd45f84 in dwarf_get_fde_list_eh (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd45f84) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl14/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl23_crash-117b8b1dfd5a1149d122ede00ca0c73a0c49acad.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-117b8b1dfd5a1149d122ede00ca0c73a0c49acad
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-117b8b1dfd5a1149d122ede00ca0c73a0c49acad`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 13: `libdwarf` - `heap-buffer-overflow(write)` in `dwarf_get_loclist_offset_index_value`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `dwarf_get_loclist_offset_index_value` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xdbcacf`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xdbcacf`
- Cluster evidence size: `1` crashing input(s) in cluster `cl53`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3854240==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c630 at pc 0x000000dbcad0 bp 0x7ffffffe42b0 sp 0x7ffffffe42a8`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xdbcacf) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in dwarf_get_loclist_offset_index_value`
- Top stack frame: `#0 0xdbcacf in dwarf_get_loclist_offset_index_value (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xdbcacf) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0x6aab0a in TestOneProtoInput(libdwarf_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick/libdwarf/libdwarf_20260324_180736/default/harness.cc:60423:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl53/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl5_crash-007b2ec44cfaaa7def44811259ade632e75169c6.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-007b2ec44cfaaa7def44811259ade632e75169c6
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-007b2ec44cfaaa7def44811259ade632e75169c6`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 14: `libdwarf` - `heap-buffer-overflow(write)` in `dwarf_get_rnglist_offset_index_value`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `dwarf_get_rnglist_offset_index_value` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xe328b8`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xe328b8`
- Cluster evidence size: `1` crashing input(s) in cluster `cl64`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3831010==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c670 at pc 0x000000e328b9 bp 0x7ffffffe4250 sp 0x7ffffffe4248`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xe328b8) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in dwarf_get_rnglist_offset_index_value`
- Top stack frame: `#0 0xe328b8 in dwarf_get_rnglist_offset_index_value (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xe328b8) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0x6aa19b in TestOneProtoInput(libdwarf_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick/libdwarf/libdwarf_20260324_180736/default/harness.cc:66552:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl64/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl6_crash-00dc5f7e82ce09db0f054f9caefbd0382fe8d54c.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-00dc5f7e82ce09db0f054f9caefbd0382fe8d54c
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-00dc5f7e82ce09db0f054f9caefbd0382fe8d54c`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 15: `libdwarf` - `heap-buffer-overflow(write)` in `dwarf_get_section_info_by_index_a`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `dwarf_get_section_info_by_index_a` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd801c1`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd801c1`
- Cluster evidence size: `2` crashing input(s) in cluster `cl73`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3849881==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c6d0 at pc 0x000000d801c2 bp 0x7ffffffe4230 sp 0x7ffffffe4228`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd801c1) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in dwarf_get_section_info_by_index_a`
- Top stack frame: `#0 0xd801c1 in dwarf_get_section_info_by_index_a (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd801c1) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0xd7fe13 in dwarf_get_section_info_by_index (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7fe13) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl73/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl73_crash-0fb39c05d55a003ef96e679f0bec545d60fefc11.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-0fb39c05d55a003ef96e679f0bec545d60fefc11
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-0fb39c05d55a003ef96e679f0bec545d60fefc11`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 16: `libdwarf` - `heap-buffer-overflow(write)` in `dwarf_get_section_info_by_index_a`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `dwarf_get_section_info_by_index_a` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd80291`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd80291`
- Cluster evidence size: `1` crashing input(s) in cluster `cl26`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3832907==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c630 at pc 0x000000d80292 bp 0x7ffffffe42b0 sp 0x7ffffffe42a8`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd80291) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in dwarf_get_section_info_by_index_a`
- Top stack frame: `#0 0xd80291 in dwarf_get_section_info_by_index_a (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd80291) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0x6e1f98 in TestOneProtoInput(libdwarf_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick/libdwarf/libdwarf_20260324_180736/default/harness.cc:68217:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl26/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl35_crash-376691b9bdf163d17bd6db55321416ce9800bb0e.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-376691b9bdf163d17bd6db55321416ce9800bb0e
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-376691b9bdf163d17bd6db55321416ce9800bb0e`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 17: `libdwarf` - `heap-buffer-overflow(write)` in `dwarf_get_section_info_by_name_a`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `dwarf_get_section_info_by_name_a` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f45c`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f45c`
- Cluster evidence size: `2` crashing input(s) in cluster `cl74`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3849906==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c630 at pc 0x000000d7f45d bp 0x7ffffffe4230 sp 0x7ffffffe4228`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f45c) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in dwarf_get_section_info_by_name_a`
- Top stack frame: `#0 0xd7f45c in dwarf_get_section_info_by_name_a (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f45c) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0xd7f111 in dwarf_get_section_info_by_name (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f111) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl74/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl74_crash-01532fb980266dd286012955af2fdcda9a714362.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-01532fb980266dd286012955af2fdcda9a714362
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-01532fb980266dd286012955af2fdcda9a714362`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 18: `libdwarf` - `heap-buffer-overflow(write)` in `dwarf_get_section_info_by_name_a`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `dwarf_get_section_info_by_name_a` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f4c4`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f4c4`
- Cluster evidence size: `2` crashing input(s) in cluster `cl71`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3863663==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c670 at pc 0x000000d7f4c5 bp 0x7ffffffe4230 sp 0x7ffffffe4228`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f4c4) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in dwarf_get_section_info_by_name_a`
- Top stack frame: `#0 0xd7f4c4 in dwarf_get_section_info_by_name_a (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f4c4) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0xd7f111 in dwarf_get_section_info_by_name (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f111) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl71/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl71_crash-056a8baabd71d1391213c27941b2e32923c029bb.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-056a8baabd71d1391213c27941b2e32923c029bb
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-056a8baabd71d1391213c27941b2e32923c029bb`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 19: `libdwarf` - `heap-buffer-overflow(write)` in `dwarf_get_section_info_by_name_a`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `dwarf_get_section_info_by_name_a` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f52c`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f52c`
- Cluster evidence size: `1` crashing input(s) in cluster `cl44`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3821422==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c650 at pc 0x000000d7f52d bp 0x7ffffffe4290 sp 0x7ffffffe4288`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f52c) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in dwarf_get_section_info_by_name_a`
- Top stack frame: `#0 0xd7f52c in dwarf_get_section_info_by_name_a (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f52c) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0x6f05f0 in TestOneProtoInput(libdwarf_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick/libdwarf/libdwarf_20260324_180736/default/harness.cc:68885:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl44/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl51_crash-842406381ee098d6d17fc7398c62df8a1967325c.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-842406381ee098d6d17fc7398c62df8a1967325c
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-842406381ee098d6d17fc7398c62df8a1967325c`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 20: `libdwarf` - `heap-buffer-overflow(write)` in `dwarf_get_section_info_by_name_a`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `dwarf_get_section_info_by_name_a` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f594`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f594`
- Cluster evidence size: `1` crashing input(s) in cluster `cl36`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3817203==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c630 at pc 0x000000d7f595 bp 0x7ffffffe4290 sp 0x7ffffffe4288`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f594) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in dwarf_get_section_info_by_name_a`
- Top stack frame: `#0 0xd7f594 in dwarf_get_section_info_by_name_a (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd7f594) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0x6f05f0 in TestOneProtoInput(libdwarf_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick/libdwarf/libdwarf_20260324_180736/default/harness.cc:68885:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl36/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl44_crash-5ab77081b0f955b33eee737bea7bb869342ba602.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-5ab77081b0f955b33eee737bea7bb869342ba602
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-5ab77081b0f955b33eee737bea7bb869342ba602`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 21: `libdwarf` - `heap-buffer-overflow(write)` in `dwarf_globals_by_type`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `dwarf_globals_by_type` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd6384c`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd6384c`
- Cluster evidence size: `2` crashing input(s) in cluster `cl69`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3860943==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c630 at pc 0x000000d6384d bp 0x7ffffffe4230 sp 0x7ffffffe4228`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd6384c) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in dwarf_globals_by_type`
- Top stack frame: `#0 0xd6384c in dwarf_globals_by_type (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd6384c) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0xd69939 in dwarf_get_pubtypes (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd69939) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl69/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl29_crash-22b4104359700f0d93b1229bd59d7f3dea6b4234.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-22b4104359700f0d93b1229bd59d7f3dea6b4234
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-22b4104359700f0d93b1229bd59d7f3dea6b4234`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 22: `libdwarf` - `heap-buffer-overflow(write)` in `dwarf_hasattr`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `dwarf_hasattr` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xe1d55f`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xe1d55f`
- Cluster evidence size: `1` crashing input(s) in cluster `cl2`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3849799==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c630 at pc 0x000000e1d560 bp 0x7ffffffe4390 sp 0x7ffffffe4388`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xe1d55f) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in dwarf_hasattr`
- Top stack frame: `#0 0xe1d55f in dwarf_hasattr (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xe1d55f) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0x6774f6 in TestOneProtoInput(libdwarf_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick/libdwarf/libdwarf_20260324_180736/default/harness.cc:75468:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl2/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl11_crash-038a504638304cdc45c1594d02095cc49ff8b9bb.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-038a504638304cdc45c1594d02095cc49ff8b9bb
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-038a504638304cdc45c1594d02095cc49ff8b9bb`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 23: `libdwarf` - `heap-buffer-overflow(write)` in `dwarf_offset_list`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `dwarf_offset_list` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xe18ce9`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xe18ce9`
- Cluster evidence size: `1` crashing input(s) in cluster `cl58`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3861490==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c6d0 at pc 0x000000e18cea bp 0x7ffffffe42b0 sp 0x7ffffffe42a8`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xe18ce9) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in dwarf_offset_list`
- Top stack frame: `#0 0xe18ce9 in dwarf_offset_list (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xe18ce9) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0x6d1c4e in TestOneProtoInput(libdwarf_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick/libdwarf/libdwarf_20260324_180736/default/harness.cc:85873:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl58/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl64_crash-f06b8f26aff37c725dcf27c3dba540653481801f.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-f06b8f26aff37c725dcf27c3dba540653481801f
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-f06b8f26aff37c725dcf27c3dba540653481801f`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 24: `libdwarf` - `heap-buffer-overflow(write)` in `dwarf_uncompress_integer_block_a`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `dwarf_uncompress_integer_block_a` at `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd24806`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd24806`
- Cluster evidence size: `1` crashing input(s) in cluster `cl41`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3841406==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200006c650 at pc 0x000000d24807 bp 0x7ffffffe42f0 sp 0x7ffffffe42e8`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd24806) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35) in dwarf_uncompress_integer_block_a`
- Top stack frame: `#0 0xd24806 in dwarf_uncompress_integer_block_a (/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin+0xd24806) (BuildId: 87dd87c2907cbc20ac8eb9741d3dc216659f6d35)`
- Next frame(s): `#1 0x64a6dd in TestOneProtoInput(libdwarf_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick/libdwarf/libdwarf_20260324_180736/default/harness.cc:94332:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/casr/clusters/cl41/_home_fuzzserver_Research_proto-liberator_artifacts_libdwarf_patch_eval_20260415_162428_after_15m_casr_triage_cl49_crash-6ed0d89c1af6f4ad0be9f712497600740cd47393.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: DWARF debug-info parsing APIs consuming attacker-controlled binary metadata.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-6ed0d89c1af6f4ad0be9f712497600740cd47393
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/libdwarf_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libdwarf/patch_eval_20260415_162428/after_15m/artifacts/crash-6ed0d89c1af6f4ad0be9f712497600740cd47393`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

## libhtp

### Case 25: `libhtp` - `heap-buffer-overflow(write)` in `bstr_alloc`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `bstr_alloc` at `/home/fuzzserver/Research/proto-liberator/ground_truths/sources/libhtp/repo/htp/bstr.c`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/ground_truths/sources/libhtp/repo/htp/bstr.c:48:13`
- Cluster evidence size: `1` crashing input(s) in cluster `cl38`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3353470==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x502000038b18 at pc 0x000000a8012d bp 0x7fffffff98d0 sp 0x7fffffff98c8`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow /home/fuzzserver/Research/proto-liberator/ground_truths/sources/libhtp/repo/htp/bstr.c:48:13 in bstr_alloc`
- Top stack frame: `#0 0xa8012c in bstr_alloc /home/fuzzserver/Research/proto-liberator/ground_truths/sources/libhtp/repo/htp/bstr.c:48:13`
- Next frame(s): `#1 0x615047 in TestOneProtoInput(libhtp_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libhtp/libhtp_20260324_165828/default/harness.cc:10503:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libhtp/default/casr/clusters/cl38/_home_fuzzserver_Research_proto-liberator_artifacts_libhtp_default_casr_triage_cl44_crash-836c5058f9cf06da376e0b94cc1fb0f1295550af.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: HTTP parser/configuration path handling attacker-controlled request bytes and parser state.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libhtp/default/libhtp_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libhtp/default/artifacts/crash-836c5058f9cf06da376e0b94cc1fb0f1295550af
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libhtp/default/libhtp_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libhtp/default/artifacts/crash-836c5058f9cf06da376e0b94cc1fb0f1295550af`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

## libpcap

### Case 26: `libpcap` - `heap-buffer-overflow(write)` in `pcap_lookupnet`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `pcap_lookupnet` at `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x8d40cd`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x8d40cd`
- Cluster evidence size: `1` crashing input(s) in cluster `cl49`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3401240==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x502000018230 at pc 0x0000008d40ce bp 0x7fffffffbe10 sp 0x7fffffffbe08`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x8d40cd) (BuildId: c9c903765ee39a93d31a038eded0c7f0e9ab3cfe) in pcap_lookupnet`
- Top stack frame: `#0 0x8d40cd in pcap_lookupnet (/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x8d40cd) (BuildId: c9c903765ee39a93d31a038eded0c7f0e9ab3cfe)`
- Next frame(s): `#1 0x5a1320 in TestOneProtoInput(libpcap_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libpcap/libpcap_20260324_170134/default/harness.cc:10303:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/casr/clusters/cl49/_home_fuzzserver_Research_proto-liberator_artifacts_libpcap_default_runs_rerun15m_hardened4_p1p3_20260330_205001_casr_triage_cl54_crash-169702e821cced3661014506876c1a54b15d05ea.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: Packet capture/source parsing path handling attacker-controlled capture descriptors/inputs.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/artifacts/crash-169702e821cced3661014506876c1a54b15d05ea
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/artifacts/crash-169702e821cced3661014506876c1a54b15d05ea`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 27: `libpcap` - `heap-buffer-overflow(write)` in `pcapint_parsesrcstr_ex`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `pcapint_parsesrcstr_ex` at `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x8d59ed`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x8d59ed`
- Cluster evidence size: `1` crashing input(s) in cluster `cl32`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3447036==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x502000018250 at pc 0x0000008d59ee bp 0x7fffffffbdd0 sp 0x7fffffffbdc8`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x8d59ed) (BuildId: c9c903765ee39a93d31a038eded0c7f0e9ab3cfe) in pcapint_parsesrcstr_ex`
- Top stack frame: `#0 0x8d59ed in pcapint_parsesrcstr_ex (/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x8d59ed) (BuildId: c9c903765ee39a93d31a038eded0c7f0e9ab3cfe)`
- Next frame(s): `#1 0x8d76e6 in pcap_parsesrcstr (/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x8d76e6) (BuildId: c9c903765ee39a93d31a038eded0c7f0e9ab3cfe)`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/casr/clusters/cl32/_home_fuzzserver_Research_proto-liberator_artifacts_libpcap_default_runs_rerun15m_hardened4_p1p3_20260330_205001_casr_triage_cl39_crash-04968fc4b5ac21ead102c7608aa5e9cc49a0d54c.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: Packet capture/source parsing path handling attacker-controlled capture descriptors/inputs.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/artifacts/crash-04968fc4b5ac21ead102c7608aa5e9cc49a0d54c
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/artifacts/crash-04968fc4b5ac21ead102c7608aa5e9cc49a0d54c`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 28: `libpcap` - `heap-buffer-overflow(write)` in `vsnprintf`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `vsnprintf` at `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x4981ae`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x4981ae`
- Cluster evidence size: `1` crashing input(s) in cluster `cl62`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3438765==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x502000018252 at pc 0x0000004981af bp 0x7fffffffbf20 sp 0x7fffffffb6c0`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x4981ae) (BuildId: c9c903765ee39a93d31a038eded0c7f0e9ab3cfe) in vsnprintf`
- Top stack frame: `#0 0x4981ae in vsnprintf (/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x4981ae) (BuildId: c9c903765ee39a93d31a038eded0c7f0e9ab3cfe)`
- Next frame(s): `#1 0x499961 in snprintf (/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin+0x499961) (BuildId: c9c903765ee39a93d31a038eded0c7f0e9ab3cfe)`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/casr/clusters/cl62/_home_fuzzserver_Research_proto-liberator_artifacts_libpcap_default_runs_rerun15m_hardened4_p1p3_20260330_205001_casr_triage_cl67_crash-e0c5f289bb662e37c20e133d9e66c375a663b3a6.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: Packet capture/source parsing path handling attacker-controlled capture descriptors/inputs.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/artifacts/crash-e0c5f289bb662e37c20e133d9e66c375a663b3a6
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/libpcap_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libpcap/default/runs/rerun15m_hardened4_p1p3_20260330_205001/artifacts/crash-e0c5f289bb662e37c20e133d9e66c375a663b3a6`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

## libplist

### Case 29: `libplist` - `heap-buffer-overflow(write)` in `plist_from_memory`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `plist_from_memory` at `/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x8f24a7`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x8f24a7`
- Cluster evidence size: `1` crashing input(s) in cluster `cl14`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3494125==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200001e4d0 at pc 0x0000008f24a8 bp 0x7fffffffb9d0 sp 0x7fffffffb9c8`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x8f24a7) (BuildId: f1c9f6b45b7255cbe5e07ab2e0a898ac8c4102cc) in plist_from_memory`
- Top stack frame: `#0 0x8f24a7 in plist_from_memory (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x8f24a7) (BuildId: f1c9f6b45b7255cbe5e07ab2e0a898ac8c4102cc)`
- Next frame(s): `#1 0x5a48b0 in TestOneProtoInput(libplist_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/harness.cc:10573:28`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/casr/clusters/cl14/_home_fuzzserver_Research_proto-liberator_artifacts_libplist_default_runs_hardening_stateful5_20260330_204619_casr_triage_cl23_crash-0616c2b317411f0bbb50eeb3cace2df9ab4560b0.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: plist parse/manipulation path handling attacker-controlled plist/XML/binary plist payloads.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/libplist_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/artifacts/crash-0616c2b317411f0bbb50eeb3cace2df9ab4560b0
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/libplist_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/artifacts/crash-0616c2b317411f0bbb50eeb3cace2df9ab4560b0`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 30: `libplist` - `heap-use-after-free(write)` in `node_attach`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-use-after-free(write)` (Use of deallocated memory)
- Crashing location: `node_attach` at `/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x90266b`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x90266b`
- Cluster evidence size: `1` crashing input(s) in cluster `cl22`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3606198==ERROR: AddressSanitizer: heap-use-after-free on address 0x5040000137b0 at pc 0x00000090266c bp 0x7fffffffbc00 sp 0x7fffffffbbf8`
- ASan summary: `SUMMARY: AddressSanitizer: heap-use-after-free (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x90266b) (BuildId: f1c9f6b45b7255cbe5e07ab2e0a898ac8c4102cc) in node_attach`
- Top stack frame: `#0 0x90266b in node_attach (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x90266b) (BuildId: f1c9f6b45b7255cbe5e07ab2e0a898ac8c4102cc)`
- Next frame(s): `#1 0x8f6459 in plist_array_append_item (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x8f6459) (BuildId: f1c9f6b45b7255cbe5e07ab2e0a898ac8c4102cc)`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/casr/clusters/cl22/_home_fuzzserver_Research_proto-liberator_artifacts_libplist_default_runs_hardening_stateful5_20260330_204619_casr_triage_cl30_crash-0b4c1046e537b22d014fcca8e5101ae639786c8b.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: plist parse/manipulation path handling attacker-controlled plist/XML/binary plist payloads.
- Memory primitive: Write via dangling pointer (freed object reused).
- Trigger mechanics: Attacker shapes object lifetime via input sequence, then triggers write to stale pointer after free.
- Security impact: High-risk memory corruption; potentially controllable overwrite of reallocated object memory.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/libplist_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/artifacts/crash-0b4c1046e537b22d014fcca8e5101ae639786c8b
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/libplist_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/artifacts/crash-0b4c1046e537b22d014fcca8e5101ae639786c8b`

**Recommended fix direction**
- Rework ownership/lifetime transitions; null out or invalidate pointers after free and prevent stale alias writes/reads.
- Add lifetime-focused unit/regression tests to verify no post-free dereference on the triggering path.

---

### Case 31: `libplist` - `heap-use-after-free(write)` in `node_insert`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-use-after-free(write)` (Use of deallocated memory)
- Crashing location: `node_insert` at `/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x902a24`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x902a24`
- Cluster evidence size: `1` crashing input(s) in cluster `cl30`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3606612==ERROR: AddressSanitizer: heap-use-after-free on address 0x504000013df0 at pc 0x000000902a25 bp 0x7fffffffbba0 sp 0x7fffffffbb98`
- ASan summary: `SUMMARY: AddressSanitizer: heap-use-after-free (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x902a24) (BuildId: f1c9f6b45b7255cbe5e07ab2e0a898ac8c4102cc) in node_insert`
- Top stack frame: `#0 0x902a24 in node_insert (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x902a24) (BuildId: f1c9f6b45b7255cbe5e07ab2e0a898ac8c4102cc)`
- Next frame(s): `#1 0x8f6228 in plist_array_set_item (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libplist/libplist_20260324_170256/default/libplist_fuzzer.bin+0x8f6228) (BuildId: f1c9f6b45b7255cbe5e07ab2e0a898ac8c4102cc)`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/casr/clusters/cl30/_home_fuzzserver_Research_proto-liberator_artifacts_libplist_default_runs_hardening_stateful5_20260330_204619_casr_triage_cl38_crash-1133cc7d4e9d2d58ea4d67ea353c169e2849428b.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: plist parse/manipulation path handling attacker-controlled plist/XML/binary plist payloads.
- Memory primitive: Write via dangling pointer (freed object reused).
- Trigger mechanics: Attacker shapes object lifetime via input sequence, then triggers write to stale pointer after free.
- Security impact: High-risk memory corruption; potentially controllable overwrite of reallocated object memory.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/libplist_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/artifacts/crash-1133cc7d4e9d2d58ea4d67ea353c169e2849428b
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/libplist_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libplist/default/runs/hardening_stateful5_20260330_204619/artifacts/crash-1133cc7d4e9d2d58ea4d67ea353c169e2849428b`

**Recommended fix direction**
- Rework ownership/lifetime transitions; null out or invalidate pointers after free and prevent stale alias writes/reads.
- Add lifetime-focused unit/regression tests to verify no post-free dereference on the triggering path.

---

## libsndfile

### Case 32: `libsndfile` - `heap-buffer-overflow(write)` in `vsnprintf`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `vsnprintf` at `/home/fuzzserver/Research/proto-liberator/artifacts/libsndfile/default/libsndfile_fuzzer.bin+0x49810e`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/artifacts/libsndfile/default/libsndfile_fuzzer.bin+0x49810e`
- Cluster evidence size: `1` crashing input(s) in cluster `cl3`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3641017==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x502000010392 at pc 0x00000049810f bp 0x7fffffffcbd0 sp 0x7fffffffc370`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/artifacts/libsndfile/default/libsndfile_fuzzer.bin+0x49810e) (BuildId: 8856c67b28a264b858d8e6b78b99f814a4da90ab) in vsnprintf`
- Top stack frame: `#0 0x49810e in vsnprintf (/home/fuzzserver/Research/proto-liberator/artifacts/libsndfile/default/libsndfile_fuzzer.bin+0x49810e) (BuildId: 8856c67b28a264b858d8e6b78b99f814a4da90ab)`
- Next frame(s): `#1 0x4998c1 in snprintf (/home/fuzzserver/Research/proto-liberator/artifacts/libsndfile/default/libsndfile_fuzzer.bin+0x4998c1) (BuildId: 8856c67b28a264b858d8e6b78b99f814a4da90ab)`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libsndfile/default/casr/clusters/cl3/_home_fuzzserver_Research_proto-liberator_artifacts_libsndfile_default_casr_triage_cl3_crash-2ddf72759738d64b1bb063dfee17a0d90aec8671.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: Input parsing / structured data handling path in a public library API surface.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libsndfile/default/libsndfile_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libsndfile/default/artifacts/crash-2ddf72759738d64b1bb063dfee17a0d90aec8671
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libsndfile/default/libsndfile_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libsndfile/default/artifacts/crash-2ddf72759738d64b1bb063dfee17a0d90aec8671`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

## libtiff

### Case 33: `libtiff` - `heap-buffer-overflow(write)` in `LogLuv24toXYZ`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `LogLuv24toXYZ` at `/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0xae9391`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0xae9391`
- Cluster evidence size: `1` crashing input(s) in cluster `cl8`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3671406==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200002dcf8 at pc 0x000000ae9392 bp 0x7ffffffe9990 sp 0x7ffffffe9988`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0xae9391) (BuildId: 61b291aa23999e63b97cb3bc2726098f0bd51d32) in LogLuv24toXYZ`
- Top stack frame: `#0 0xae9391 in LogLuv24toXYZ (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0xae9391) (BuildId: 61b291aa23999e63b97cb3bc2726098f0bd51d32)`
- Next frame(s): `#1 0x5bc1f5 in TestOneProtoInput(libtiff_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/harness.cc:6396:17`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/casr/clusters/cl8/_home_fuzzserver_Research_proto-liberator_artifacts_libtiff_rerun15m_hardened6_20260330_210854_casr_triage_cl107_crash-710fc708e53f722d6d919169f0ef220613e905e9.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: TIFF image decode/transform path processing attacker-controlled image files.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/libtiff_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/artifacts/crash-710fc708e53f722d6d919169f0ef220613e905e9
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/libtiff_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/artifacts/crash-710fc708e53f722d6d919169f0ef220613e905e9`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 34: `libtiff` - `heap-buffer-overflow(write)` in `LogLuv32toXYZ`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `LogLuv32toXYZ` at `/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0xae9c34`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0xae9c34`
- Cluster evidence size: `1` crashing input(s) in cluster `cl119`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3688094==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200002dcf8 at pc 0x000000ae9c35 bp 0x7ffffffe9a10 sp 0x7ffffffe9a08`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0xae9c34) (BuildId: 61b291aa23999e63b97cb3bc2726098f0bd51d32) in LogLuv32toXYZ`
- Top stack frame: `#0 0xae9c34 in LogLuv32toXYZ (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0xae9c34) (BuildId: 61b291aa23999e63b97cb3bc2726098f0bd51d32)`
- Next frame(s): `#1 0x5bbf74 in TestOneProtoInput(libtiff_fuzzer::FuzzInput const&) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/harness.cc:6670:17`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/casr/clusters/cl119/_home_fuzzserver_Research_proto-liberator_artifacts_libtiff_rerun15m_hardened6_20260330_210854_casr_triage_cl89_crash-4726e0f59b5e9628ccc9aacad26a1f4f16bc6d0c.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: TIFF image decode/transform path processing attacker-controlled image files.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/libtiff_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/artifacts/crash-4726e0f59b5e9628ccc9aacad26a1f4f16bc6d0c
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/libtiff_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/artifacts/crash-4726e0f59b5e9628ccc9aacad26a1f4f16bc6d0c`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 35: `libtiff` - `heap-buffer-overflow(write)` in `TIFFYCbCrToRGBInit`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `TIFFYCbCrToRGBInit` at `/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0x9e1aaf`
- CASR crash line hint: `/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0x9e1aaf`
- Cluster evidence size: `2` crashing input(s) in cluster `cl142`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3684556==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x523000001830 at pc 0x0000009e1ab0 bp 0x7ffffffe97d0 sp 0x7ffffffe97c8`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0x9e1aaf) (BuildId: 61b291aa23999e63b97cb3bc2726098f0bd51d32) in TIFFYCbCrToRGBInit`
- Top stack frame: `#0 0x9e1aaf in TIFFYCbCrToRGBInit (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0x9e1aaf) (BuildId: 61b291aa23999e63b97cb3bc2726098f0bd51d32)`
- Next frame(s): `#1 0x5a2464 in init_ycbcr_state_with_defaults(TIFFYCbCrToRGB*) /home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/harness.cc:255:12`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/casr/clusters/cl142/_home_fuzzserver_Research_proto-liberator_artifacts_libtiff_rerun15m_hardened6_20260330_210854_casr_triage_cl135_crash-0030a1facdd3bf453d3e558b8d6c81c29d8a4d6b.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: TIFF image decode/transform path processing attacker-controlled image files.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/libtiff_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/artifacts/crash-0030a1facdd3bf453d3e558b8d6c81c29d8a4d6b
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/libtiff_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/artifacts/crash-0030a1facdd3bf453d3e558b8d6c81c29d8a4d6b`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

### Case 36: `libtiff` - `heap-buffer-overflow(write)` in `_TIFFGetStrileOffsetOrByteCountValue`

**What is the bug?**
- Class: `EXPLOITABLE` / `heap-buffer-overflow(write)` (Heap buffer overflow)
- Crashing location: `_TIFFGetStrileOffsetOrByteCountValue` at `tif_dirread.c`
- CASR crash line hint: `tif_dirread.c`
- Cluster evidence size: `2` crashing input(s) in cluster `cl139`

**Why this is a real crash (developer-convincing evidence)**
- ASan fatal line: `==3661920==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200002dcf0 at pc 0x000000a3c731 bp 0x7ffffffe9960 sp 0x7ffffffe9958`
- ASan summary: `SUMMARY: AddressSanitizer: heap-buffer-overflow tif_dirread.c in _TIFFGetStrileOffsetOrByteCountValue`
- Top stack frame: `#0 0xa3c730 in _TIFFGetStrileOffsetOrByteCountValue tif_dirread.c`
- Next frame(s): `#1 0xa3c632 in TIFFGetStrileOffsetWithErr (/home/fuzzserver/Research/proto-liberator/ground_truths/simple_harness_fullapis_llvm18_quick_isolated_postedit_20260324_181724/libtiff/libtiff_20260324_170531/default/libtiff_fuzzer.bin+0xa3c632) (BuildId: 61b291aa23999e63b97cb3bc2726098f0bd51d32)`
- Representative CASR report: `/home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/casr/clusters/cl139/_home_fuzzserver_Research_proto-liberator_artifacts_libtiff_rerun15m_hardened6_20260330_210854_casr_triage_cl132_crash-071ceadddc97e1992c7665ff12a671118ffc829c.casrep`

**How it can be exploited (practical attacker path)**
- Reachability: TIFF image decode/transform path processing attacker-controlled image files.
- Memory primitive: Out-of-bounds heap write.
- Trigger mechanics: Attacker supplies a crafted input that drives size/index/state into a write past allocated heap bounds in the target function.
- Security impact: Memory corruption with potential for process crash and, in favorable heap layouts, code execution.
- Real-world effect: at minimum reliable denial-of-service; with heap shaping and suitable process context, memory-corruption classes may enable control-flow impact.

**Reproduction (campaign artifact)**
```bash
ASAN_OPTIONS=abort_on_error=1:symbolize=1 /home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/libtiff_fuzzer.bin /home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/artifacts/crash-071ceadddc97e1992c7665ff12a671118ffc829c
```
- Fuzzer binary: `/home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/libtiff_fuzzer.bin`
- Crash input: `/home/fuzzserver/Research/proto-liberator/artifacts/libtiff/rerun15m_hardened6_20260330_210854/artifacts/crash-071ceadddc97e1992c7665ff12a671118ffc829c`

**Recommended fix direction**
- Add strict bounds checks on all length/index arithmetic before writes, and validate allocation-size assumptions at call boundaries.
- Add regression test with this crashing input and neighboring boundary values.

---

## Appendix: Related Lower-Confidence/Potential Cases

- Full exploitable+potential triage JSON: `/home/fuzzserver/Research/proto-liberator/artifacts/best_campaigns_exploitable_triage_20260419_235411.json`
- Broader common list TSV: `/home/fuzzserver/Research/proto-liberator/artifacts/best_campaigns_real_bugs_common_20260419_235411.tsv`
