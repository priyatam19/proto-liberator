# Proto-libErator

LLM-free, structure-aware C library fuzzing on top of [libErator](https://github.com/HexHive/liberator). Consumes libErator's static analysis outputs and generates protobuf schemas, LPM harnesses, and seed corpora — no manual harness writing, no LLMs.

---

## Prerequisites

- **Python 3.10+** and `pip install -r requirements.txt`
- **clang-14** (or newer) + **llvm-14**
- `cmake`, `ninja-build`, `protobuf-compiler` (`protoc`)
- External C++ deps built once via `./scripts/build_dependencies.sh` (libprotobuf-mutator + nanopb)

```bash
sudo apt-get install -y clang llvm protobuf-compiler libprotobuf-dev cmake ninja-build python3 python3-pip
pip3 install -r requirements.txt
./scripts/build_dependencies.sh
```

---

## Quick Start

Proto-libErator takes `conditions.json` and `apis_clang.json` from libErator's `apipass` stage. If you already have analysis outputs for a library, point directly to them:

```bash
python3 src/run_all.py \
  --library pthreadpool \
  --conditions /path/to/apipass/conditions.json \
  --apis /path/to/apipass/apis_clang.json \
  --out-dir workdir/pthreadpool_demo \
  --schema-mode v2
```

Expected output in `workdir/pthreadpool_demo/`:
- `pthreadpool.v2.proto` — protobuf schema with `Action.oneof` for all 30 APIs
- `harness.cc` — LPM C++ harness (~11k lines): typed handle pools, callback trampolines, ensure_live factories, size clamping, per-iteration cleanup
- `bindings/*.pb.{h,cc}` — generated protobuf bindings

To also build the fuzzer binary and run it:
```bash
python3 src/run_all.py \
  ... \
  --header /path/to/pthreadpool.h \
  --target-lib /path/to/libpthreadpool.a \
  --build \
  --fuzz --fuzz-duration 3600
```

---

## How It Works

Proto-libErator wraps libErator's static constraint metadata (what parameters each API reads/writes, which APIs produce or consume which handle types) into a structure-aware fuzzing pipeline:

```
libErator apipass outputs (conditions.json, apis_clang.json)
  -> proto_generator.py       — emit .proto schema (v1 fixed or v2 dynamic dispatch)
  -> wrapper_generator.py     — render Jinja2 harness template with EMI guards + handle pools
  -> seed_generator.py        — build planned seed corpus from API lifecycle graph
  -> build (clang + LPM)
  -> fuzz (LibFuzzer + libprotobuf-mutator custom mutator)
  -> feedback_aggregator.py   — merge runtime API stats into novelty/edge/prefix weights
  -> crash_classifier.py      — separate genuine crashes from constraint-misuse replays
  -> crash_constraint_learner.py — learn parameter bounds from genuine crashes
```

**Two schema modes:**
- `--schema-mode v1` — fixed API sequence from `driver.meta` (one repeated-params struct per API)
- `--schema-mode v2` — dynamic dispatch super-harness (`repeated Action` + `oneof`; fuzzer decides call order)

**LPM harness features** (v2, `--mutation-mode lpm`):
- Typed handle tables prevent cross-type handle reuse
- Callback trampolines replace raw fn-ptr bytes with safe static stubs
- `ensure_live_<type>()` factories seed the handle pool before the action loop
- Size-like parameters clamped to avoid OOM before reaching interesting code
- `cleanup_all_handles()` after each iteration prevents handle leaks
- Multi-pass semantic repair mutator: `SEQ_REPAIR`, `NORM_HANDLES`, `SYNC_LENGTHS`, opt-in `UAF_PROBE`

---

## Repository Layout

| Path | Contents |
|---|---|
| `src/` | 14 Python pipeline modules (see below) |
| `templates/` | Jinja2 harness templates (`wrapper_lpm.cc.j2`, `wrapper_v2.c.j2`, `wrapper.c.j2`) |
| `scripts/` | Build, campaign, coverage, and analysis shell/Python scripts |
| `tests/` | 46-test pytest suite + shell compile tests + fixtures |
| `docs/` | Schema contracts, architecture docs, toolchain explanation, workflow guides |
| `external/` | libprotobuf-mutator and nanopb (built by `build_dependencies.sh`; only `.gitkeep` in repo) |
| `examples/` | Minimal worked example inputs |

### Source modules (`src/`)

| Module | Role |
|---|---|
| `run_all.py` | End-to-end orchestrator: generate → build → fuzz → feedback → triage |
| `proto_generator.py` | Emit `.proto` schema from `conditions.json` + `apis_clang.json` |
| `wrapper_generator.py` | Render Jinja2 harness with EMI guards, handle pools, trampolines, clamping |
| `seed_generator.py` | Wire-encoded seed corpus from API lifecycle graph (no protoc needed) |
| `sequence_planner.py` | Stateful sequence planning: `strict`, `balanced`, `explore` modes |
| `constraint_graph_builder.py` | Build inter/intra API dependency graph (producers, consumers, invalidators) |
| `emi_guard_rules.py` | Generate set_by repair guards and len_depends_on clamping snippets |
| `feedback_aggregator.py` | Merge runtime API stats into novelty scores, learned edges, prefix weights |
| `causal_edge_verifier.py` | Ablation-based edge validation (promote/demote confidence) |
| `crash_classifier.py` | Classify replayed crashes as `genuine` vs. `constraint_misuse` |
| `crash_constraint_learner.py` | Learn parameter bounds from genuine crashes via shadow-byte replay |
| `type_mapper.py` | Map LLVM IR types to protobuf field types (struct ptrs → handles, etc.) |
| `contracts.py` | Protobuf schema contract definitions and field name constants |
| `utils.py` | Shared utilities: JSON loading, path helpers, field name normalization |

---

## Running Tests

```bash
python3 -m pytest tests/ -v    # 46 tests, all should pass
```

The test suite is self-contained — no library builds required, uses in-tree fixtures.

---

## Further Reading

| Document | What it covers |
|---|---|
| [`docs/SCHEMA_CONTRACT_V2.md`](docs/SCHEMA_CONTRACT_V2.md) | Protobuf schema spec for v2 dynamic dispatch mode |
| [`docs/SCHEMA_CONTRACT.md`](docs/SCHEMA_CONTRACT.md) | Protobuf schema spec for v1 fixed-sequence mode |
| [`docs/LLM_FREE_ARCHITECTURE.md`](docs/LLM_FREE_ARCHITECTURE.md) | Why no LLMs are needed; design rationale |
| [`docs/TOOLCHAIN_EXPLANATION.md`](docs/TOOLCHAIN_EXPLANATION.md) | End-to-end data-flow walkthrough with worked examples |
| [`docs/GROUND_TRUTH_WORKFLOW.md`](docs/GROUND_TRUTH_WORKFLOW.md) | Ground-truth-first evaluation methodology |
| [`CLAUDE.md`](CLAUDE.md) | Full command reference, architecture deep-dive, all CLI flags |

---

## Notes

- Proto-libErator does **not** run libErator static analysis. It consumes the `apipass` outputs.
- Entry-point discovery comes from libErator's SVF/NDA analysis. Proto-libErator's gains are in mutation quality, sequence exploration, online feedback, and crash-learning loops.
- Research artifacts (paper drafts, thesis files, campaign data) are kept local and are not published to this repository.
