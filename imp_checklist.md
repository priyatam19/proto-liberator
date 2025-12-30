Implementation Checklist (proto-liberator)

type_mapper.py

Add parsing helpers for enum_types.txt, incomplete_types.txt, and data_layout.txt (new TypeContext loaded per-target).
Replace the single map_llvm_to_proto() decision with a richer classification: {kind: scalar|bytes|bytes_array|struct_blob|handle, type_key, elem_type, is_nullable}.
Introduce typed handle keys (stable ID per “object type”), derived from type_string/type-hash/struct-name, so char*/void* can’t be mixed with aom_codec_ctx_t*.
Detect varargs APIs from apis_clang.json (needs plumbed through) and mark as unsupported_vararg unless explicitly modeled.
proto_generator.py

Add an optional --minimum-apis <apis_minimized.txt> filter (or accept a list) so v2 schema only includes the minimized set for early experiments.
For each pointer param, use type classification to generate one of:
bytes + optional *_length/_length_override (true input buffers)
uint32 *_handle (opaque/owned objects)
bytes *_blob (struct buffers; sized using data_layout.txt)
Encode len_depends_on explicitly in the schema (at least as comments + consistent field naming) so seed generation/harness can enforce it.
Mark “dangerous returns” (e.g., char* “view” strings) as not handles unless conditions explicitly say create/delete; remove the current broad heuristic that tends to register non-object pointers.
wrapper_generator.py (plus wrapper_lpm.cc.j2)

Replace the single global handle table with typed handle tables keyed by type_key.
For struct_blob params, allocate stack/std::vector<uint8_t> with the exact data_layout size, optionally initialize from proto bytes, and pass a correctly-cast pointer.
Enforce len_depends_on at runtime: if param_buf.size() < param_len, clamp or skip; if param_len missing, derive it from buffer length.
For varargs APIs: either skip entirely (safe baseline) or implement a limited “control-id → arg union” model for a small curated subset.
Tighten return handling:
Only handle_register() for return types classified as handle (no more registering char* from print/error-string APIs).
On destructor calls, invalidate the typed handle; only allow stale/double-delete when the explicit proto knobs request it.
seed_generator.py

Accept --apis (apis_clang.json), --minimum-apis, and --data-layout/--incomplete-types/--enum-types so seeds reflect the same classification as the schema.
Generate valid-state seed skeletons using a small rule system:
creators (return/create) first, then consumers, then destructors
always set coupled lengths (len_depends_on) consistently
for struct blobs, emit correctly-sized initialization bytes (even if mostly zeros + a few mutated fields)
Add a “known constants” hook (per-target JSON overrides) for ABI/version params (common in codec libs), otherwise init/decode will often early-fail.
Pilot Plan (libaom end-to-end validation)

Inputs: {conditions.json, apis_clang.json, apis_minimized.txt, data_layout.txt, enum_types.txt, incomplete_types.txt}.
Step 1: Minimized schema + harness
Generate a v2 schema filtered to apis_minimized.txt.
Generate an LPM harness with typed handles + struct-blob support + vararg skipping.
Step 2: Seed corpus (valid-state)
Provide a small driver.meta.json / seed skeleton focusing on decode path (example structure): aom_codec_av1_dx → aom_codec_dec_init_ver → aom_codec_decode → aom_codec_get_frame → aom_codec_destroy.
Add a tiny constants override for the ABI/version arg(s) needed by *_init_ver.
Step 3: Build + replay sanity
Build libaom_fuzzer.bin and libaom_profile.bin.
Hard gate: libaom_profile.bin corpus -runs=0 must (a) not crash and (b) emit non-empty *.profraw (otherwise coverage will stall like your recent cjson case).
Step 4: Short fuzz + coverage check
Run 10–30 minutes; collect coverage and compare against (a) current proto-liberator baseline and (b) libErator’s first iteration.
Track metrics: executed/skipped call ratio, crash rate, and whether coverage grows over time.
Go/No-Go criteria
Go if: profile replay is stable + skipped-call rate drops significantly + line coverage increases vs current proto-liberator.
No-go if: init paths still fail due to missing constants/struct init; then next step is expanding constant inference and struct initialization (not more mutation tuning).
If you want, I can draft the exact libaom