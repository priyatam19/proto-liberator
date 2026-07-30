# Ground-Truth-First Workflow

This workflow flips the current order:
- Before: add pipeline features first, then check if fuzzing output improved.
- Now: define per-library ground-truth artifacts first, then change pipeline until it matches.

## 1) Build Ground-Truth Bundles

Run once to create a bundle for every analyzed library:

```bash
python3 scripts/build_ground_truths.py \
  --analysis-root /home/fuzzserver/Research/proto-liberator/analysis \
  --targets-root /home/fuzzserver/Research/proto-liberator/targets \
  --output-root /home/fuzzserver/Research/proto-liberator/ground_truths
```

What this creates:
- `ground_truths/libraries/<lib>/analysis/apipass/`: analysis artifacts used by generation.
- `ground_truths/libraries/<lib>/target_scripts/`: fetch/build/generator scripts.
- `ground_truths/libraries/<lib>/references/hopper/`: Hopper configs/log references (when available).
- `ground_truths/libraries/<lib>/references/nexzzer/`: NEXZZER references (currently cJSON).
- `ground_truths/libraries/<lib>/candidate/`: place your target proto/harness/coverage results here.
- `ground_truths/sources/<lib>/repo`: original upstream source cloned at pinned commit from `fetch.sh`.
- `ground_truths/index.csv`: quick comparison table across all libraries.

For cJSON specifically, baseline rerun artifacts are also copied into:
- `ground_truths/libraries/cjson/baseline/`

## 2) Define Ground Truth Per Library

For each library:
1. Start from `libraries/<lib>/candidate/generate_candidate.sh`.
2. Generate proto/harness variants and run fuzzing/coverage loops.
3. Keep only the best artifacts in `libraries/<lib>/candidate/`:
   - `<lib>.v2.proto`
   - `harness.cc`
   - `<lib>_fuzzer.bin`
   - `coverage/coverage_timeline.csv`
   - `coverage/live/report_full.txt`
   - `logs/fuzz-0.log`

This candidate becomes the **ground truth target** for that library.

## 3) Use Ground Truth to Drive Pipeline Changes

Only after a library ground truth exists:
1. Run current pipeline.
2. Diff pipeline output vs `ground_truths/libraries/<lib>/candidate/`.
3. Implement minimal pipeline changes to close that gap.
4. Re-run and repeat.

## 4) Why this helps

- Prevents adding complexity without a clear target outcome.
- Makes Hopper/NEXZZER ideas actionable by treating their harness style as references, not direct integration.
- Gives a measurable contract per library: proto shape, harness behavior, and coverage trajectory.

