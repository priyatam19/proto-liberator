# CCS'26 Reviewer-Style Review: Proto-libErator

**Submission target:** ACM CCS 2026, Cycle 2 (deadline April 29, 2026)
**Format expected:** ACM sigconf, ≤12 pages main + bib + appendices, double-blind
**Reviewer model:** I'm reviewing as a CCS PC member would — focused on novelty, rigor, and the bar set by recent fuzzing/harness-generation work at the Big Four (S&P, USENIX Security, CCS, NDSS).

---

## Bottom-line read

You have an interesting story — *protobuf-as-API-interposition + super-harness over libErator's static analysis* — and a couple of headline numbers that look real (cjson 85.4% / 100% function, pthreadpool 80%). But as a CCS submission *as it stands today,* my honest prediction is **reject** in the 25–30% strong / 25% weak / 50% reject range, leaning weak-reject to reject, for the following reasons:

1. **Evaluation does not meet the Klees-et-al. bar that CCS reviewers now treat as table stakes.** No multiple trials, no variance/CIs, no Mann-Whitney U or equivalent statistical test, baselines not rerun under matched conditions, and Table 8.4 explicitly carries a † footnote saying campaigns are *not* under equal time budget. This alone is enough to sink the paper for several reviewers, especially after the 2024 SoK on fuzzing evaluations (Schloegel et al.).
2. **Baselines are not actually rerun.** Hopper / libErator / NEXZZER numbers appear to be lifted from prior papers, on different hardware. Section 8.11 candidly says matched-budget reruns are "in progress." A reviewer will not give credit for SOTA comparisons that were not actually executed.
3. **The competitive frontier has shifted to LLM-based harness generation** (PromptFuzz CCS'24, PromeFuzz CCS'25, CKGFuzzer ICSE'25, OSS-Fuzz-Gen, OGHARN ICSE'25). Your work is positioned against Hopper/libErator/NEXZZER but does not engage with the LLM-driven baselines that CCS'25 already accepted as state-of-the-art. The thesis itself acknowledges this in §9.4 ("The Role of LLM-Assisted Harness Engineering"), but a reviewer will read that as: "the authors know the SOTA is somewhere else, and they don't compare."
4. **Delta over libErator may be perceived as incremental.** §3.2.4 says Proto-libErator is "explicitly designed as a downstream consumer of libErator's static analysis"; you take their `conditions.json` and `apis_clang.json`. The technical delta is (a) protobuf interposition / super-harness and (b) RNR guards. A skeptical reviewer will ask: "is this a CCS paper or a SAC/RAID paper?" The empirical evidence has to do work to defend the venue.
5. **Several internal-validity concerns** about the headline numbers — the cjson 85.4% comes from a 24-hour single run, the pthreadpool 80% comparison vs Hopper 31% is suspicious (Hopper is *very* strong on dense-state libraries — the gap is so large I'd want to see the run repeated five times each before believing it).

These are all *fixable* between now and 4/29 in the sense that you can run experiments and reorganize the paper. They are not fixable in the sense of "wave a wand and you're at the bar." The recommendations at the end are prioritized by ROI given the 72-hour clock.

A secondary concern, separate from accept/reject: **a 12-page paper based on a 120-page thesis is a serious compression problem.** Most of the thesis (Chapters 2, 3, 6, 7) cannot survive in the paper; you need to hard-pick a thesis (in the rhetorical sense — *one* claim) and ruthlessly delete everything that doesn't serve it.

---

## Detailed comments by axis

### 1. Framing and scope

**Strength.** The framing in §1.2 ("two contributions: static head-start + randomized typed dispatch") is clean, and the class-conditional positioning ("we don't claim universal dominance") is honest and a refreshing change from the usual "we beat everything" framing. CCS reviewers respond well to honest scope, *if* the empirical evidence is rigorous.

**Concerns.**

- **The "two contributions" claim, on close reading, splits into one mechanism.** The static head-start (C1) and the randomized typed dispatch (C2) are not separable in the evaluation. There is no ablation that turns *off* the super-harness while keeping the SCG seeds, nor one that turns *off* the SCG seeds while keeping the super-harness. The +RNR/+SCG/+LPM ablation in Table 8.7 bundles three changes together. A reviewer will ask: which contribution is doing the work?
- **The relationship to libErator is too dependent.** §3.2.4: "Proto-libErator is explicitly designed as a downstream consumer of libErator's static analysis: it takes libErator's `conditions.json` and `apis_clang.json` artifacts." Read in the worst-case framing, this says: the static analysis came from prior work, and the new contribution is a runtime architecture (protobuf + super-harness + RNR). That is a real contribution, but it's a *systems* contribution, not a static-analysis contribution. The paper should own that — pitch it as "we keep libErator's SCG and replace the harness model" — and then justify why the harness model alone is worth a CCS paper.
- **The "consumer-code-independent" framing is strong but the LLM elephant is unaddressed.** PromptFuzz (CCS'24) and PromeFuzz (CCS'25) are also CCI in any meaningful sense — the LLM's training corpus is not the *target* library's consumer code. A reviewer will not let "we're CCI and they're not" stand as the differentiator. The actual differentiator you want is "we're *deterministic and reproducible* and they're not" — but you have to argue it.

### 2. Technical novelty

**What is genuinely novel.**

- Using protobuf as the API interposition surface for a *super-harness* (one binary covering all APIs) is, as far as I know, not done in the prior CCI literature. libprotobuf-mutator is well-known for parser fuzzing but the application here — protobuf as the schema for an API-call sequence — is a fresh framing.
- The Repair-Not-Reject (RNR) guard pattern, where a missing handle causes inline creator injection rather than loop termination, is a clean and defensible engineering idea.
- The two-mode seed planner (strict / explore) is a sensible operationalization of soft vs hard SCG edges.

**What is not novel enough on its own.**

- The SCG itself is essentially libErator's AFG with confidence weights. §5.1 defines the SCG as a directed graph from SVF, and the SVF NDA pass is libErator's. The "evidence-aware" confidence scores are an addition, but a small one.
- Type-driven schema generation from C signatures (§4.2, R1–R4) is a deterministic, rule-based mapping. It's a clean engineering artifact, but a reviewer will not see this as research novelty — every prior C harness generator does some version of it.
- Five-pass semantic mutator (§6.3) — the passes are sensible but the design space is well-explored; cf. structure-aware mutators in libFuzzer/AFL++ literature.

**The "three properties simultaneously" claim (§4.1.3) is the right rhetorical move but currently unsupported.** You say P1+P2+P3 are not provided simultaneously by any prior tool. A reviewer will scan Table 3 / a feature matrix and try to find a counterexample. You don't have that table — you should. If a reviewer has to construct it themselves, half of them won't, and the other half will find one. Build the table for them.

### 3. Evaluation rigor

This is the biggest single category of risk. I'll be specific.

**Klees et al. compliance.** The Schloegel et al. SoK at S&P 2024 has made non-compliance with Klees et al. a *flag* that PC members are now trained to look for. The minimum bar at CCS today:

- **≥5 independent trials per (tool, target) cell**, ideally 10. The OGHARN paper at ICSE'25 ran 5 trials. PromptFuzz at CCS'24 ran 5. PromeFuzz at CCS'25 ran 10. Single-run results in Tables 8.3, 8.4, 8.7 are below this bar.
- **Variance reporting** — at minimum, mean ± std or 95% CIs. Box plots or violin plots for trajectories. Figure 8.1 shows single-run trajectories with no shaded bands; reviewers will discount this figure heavily.
- **Statistical significance testing** — Mann-Whitney U at p<0.05 (Klees et al. recommends Vargha-Delaney Â₁₂ for effect size). None of the tables in the thesis carry significance markers.
- **Matched time budget** — Table 8.4 carries a † saying baselines are *not* under equal time budget. This is a reviewer-fatal footnote. Either match the budgets or remove the comparison.

**Baseline reproduction.** I see no evidence anywhere in the thesis that you reran Hopper, libErator, or NEXZZER on your hardware. The numbers in Table 8.4 are quoted from prior papers (Hopper [4] CCS'23 evaluation; libErator [15] which appears to be the predecessor work). This is a problem because:

- Prior papers run on different hardware (different CPU, RAM, storage). Coverage numbers are *not* portable across hardware for libFuzzer, especially with `-fork`.
- Prior papers may use different library versions, different fuzzer flags (including `-fork=N`, timeout, RSS limits), different coverage instrumentation modes (LLVM source-based vs SanitizerCoverage edge counters), and different coverage measurement (line vs region vs branch).
- Most damaging: the thesis runs `libFuzzer -fork=2`. Recent fuzzing literature (OGHARN ICSE'25 explicitly notes this) is moving to AFL++ because libFuzzer is no longer maintained since 2022. A CCS reviewer may ask why libFuzzer was chosen over AFL++.

**Benchmark choice.** 11 libraries is fine for breadth but the choice is non-standard:

- The community-standard benchmarks are **FuzzBench**, **Magma**, and (for harness work) the **Hopper benchmark suite**. None of the eleven libraries here match those benchmarks 1:1.
- The libErator benchmark overlaps but is not identical.
- libdwarf, minijail, and cpu_features are reported as "Proto-libErator firsts" — this looks bad if a reviewer reads it as "we picked targets nobody else evaluated, then declared best-in-class."

Fix: align (at least partially) with one of FuzzBench-fuzzgen, Magma, or the Hopper benchmark to allow apples-to-apples comparison.

**The pthreadpool 80% vs Hopper 31% gap is too good to be true and needs defending.** Hopper's Table 1 in the CCS'23 paper (which I believe is what you're citing) reports Hopper at very high coverage on most stateful libraries — it does well on cjson (87.44%) and on c-ares (60.43%). A 49-pp gap on pthreadpool is enormous. Possible explanations a reviewer will entertain:

- pthreadpool's API surface is small (30 APIs), so "100% function coverage" can be reached by a few good sequences and lost by a few bad ones — high variance.
- libFuzzer + your super-harness happens to invoke `pthreadpool_create` early in most seeds (because of SCG); Hopper without that prior may take many hours to learn the create-before-use ordering on synchronization primitives that have *no return value* you can use as feedback.
- The Hopper number you cite is from libErator's reported reproduction, not Hopper's own paper.

The 49-pp claim *might* be real, but it requires defense. Run pthreadpool with both tools 10× each on the same hardware and report the distribution.

**Validity ablation (Table 8.7) bundles too many changes.** "+RNR+SCG+LPM" is three independent changes. Without separate ablations, a reviewer cannot tell whether RNR alone, SCG alone, or LPM alone, or any pair, is doing the work. This is a real (and tractable) experiment — unbundle it. The result might also be more interesting than the bundled version.

**Constraint graph quality (§8.6) is preliminary.** Table 8.6 reports precision/recall on *15 hand-audited edges of cjson alone*. The thesis admits "Full benchmark table pending automated causal edge verification." For a CCS submission this needs to be at least 5 libraries with the automated procedure, or the section should be cut and replaced with a discussion subsection.

**Crash triage is incomplete.** Table 8.8 reports CASR clusters but the thesis says manual triage is "in progress." 426 of 520 clusters are null-dereferences, which the author themselves attributes to harness-induced misuse from RNR guards (§8.10). This means the headline crash count is very likely inflated. The bug count that survives manual triage and is reported to upstream is what reviewers care about; you need that number.

### 4. Specific bugs and CVEs claim

The thesis lists four "high-confidence" bugs (c-ares, cjson, libplist, libtiff). For a CCS paper, *bug claims need to be hardened*:

- **CVE numbers, or upstream issue links, or fix commits.** None are mentioned in the thesis. A reviewer will check OSS-Fuzz to see if these crashes are already known. Several of these libraries (c-ares, libtiff, cjson) have been on OSS-Fuzz for years; rediscovery of known bugs counts much less than novel discoveries.
- **For each bug**: stack trace, ASAN report fingerprint, root-cause analysis, did the maintainer accept the fix, was a CVE assigned. Even one well-documented N-day with these details is worth more than four undocumented "high-confidence" findings.
- The cjson `cJSON_ReplaceItemViaPointer` UAF in particular: cJSON has been on OSS-Fuzz since 2018 and has had several public UAFs. You need to show this is novel, or drop it.

### 5. Limitations chapter (§9) — a double-edged sword

The §9 limitations chapter is admirably honest, and the §9.5 Table 9.1 is a great taxonomy. **In a thesis, this is praiseworthy. In a CCS paper, it's a reviewer's free ammunition.**

Specific issues that will be quoted back at you in reviews:

- §9.2.1: "Function pointer parameters become empty stubs." → "So callbacks are never tested. PromptFuzz/PromeFuzz handle this with LLM-generated callback bodies. Why is this acceptable?"
- §9.2.2: "No loop generation in action sequences." → "So iterative API patterns (read-until-EOF, push-then-query) are unreachable. This is a major coverage limit on stateful libraries — exactly the class you claim to dominate."
- §9.3.1: "Static constraints cannot capture all semantic requirements" with the SSL example. → "Right, this is *the* hard problem in API fuzzing, and you punt on it."
- §9.3.4: "The one-size-fits-all super harness has coverage trade-offs." → "Wait, didn't you just spend 8 chapters arguing the super-harness is the right model? Now you're saying it isn't?"
- §9.4: explicit acknowledgment that LLM-based work would help. → "Then why didn't you compare to it?"

Recommendation for the CCS version: keep the limitations *short and structural*. Don't enumerate engineering bugs (duplicate oneof names, nullable field sync, C++ namespace handling) — those make it look like the artifact isn't ready. Move them to an appendix titled "Implementation engineering" or to the artifact README.

### 6. Reproducibility

The reproducibility position is the strongest part of the paper and you should lean into it:

- Deterministic, rule-based schema synthesis (§4.2)
- Bit-for-bit identical artifacts given the same inputs (§7.5)
- Fixed-seed campaigns
- LLM-free pipeline → no API costs, no model drift

This is the single best response to PromptFuzz/PromeFuzz reviewers. *Frame the paper around this.* The pitch becomes: "LLM-based harness generation has variance, cost, and reproducibility problems. We give up some coverage in exchange for full determinism, no API cost, and class-predictable performance." That is a CCS-shaped story.

### 7. Writing and presentation

- The thesis is written in a thesis register: long quotations of mentor wisdom at chapter starts, second-person commentary, lots of "as we will see" forward references. Strip all of this for the paper. Move from thesis voice to S&P-paper voice.
- Two-column ACM sigconf at 12 pages is brutal. The whole of Chapter 2 (background on SVF, AFL, libFuzzer, protobuf) cannot survive — assume the reader knows libFuzzer and protobuf, give SVF half a paragraph. Chapter 3 becomes one tight Related Work section. Chapter 7 (toolchain integration) is appendix material.
- Algorithms 1, 2, 3, 4, 5: at most one should be in the main paper. The rest go to the appendix.
- The cjson SCG visualization (Fig 8.3) is more useful than the architecture figure — keep it.

---

## What to do between now and April 29

You have about 72 hours. Here is a triage list, ordered by ROI per hour.

### Tier 0 — Do these first (24–36 hours)

These are the experiments that, if you skip them, the paper *will* be rejected, regardless of what else you do.

**T0-1. Multiple-trial campaigns on the headline targets.** Pick the four libraries that carry the story: **cjson, pthreadpool, libplist, libdwarf**. Run **5 independent trials** of Proto-libErator on each, each trial 24 hours. Collect:
- Final line/branch/function/region coverage per trial
- Coverage trajectory (every 5 min) per trial
- Mean ± std and 95% CI

If you only have time for one set of overnight runs (∼60 hours wall clock for 4 libs × 5 trials at 24h each on a parallel machine — you may need to rent), prioritize cjson and pthreadpool (the headline numbers) and libplist (where you currently look weakest). Drop the 24h budget to 12 hours per trial if you must — Klees et al. accepts 12h with disclosure. Do not go below 12h.

**Hardware option:** if you don't have parallel machines, rent 4× c5.4xlarge or c6i.4xlarge AWS instances for ∼$60 total over the 72 hours. That cost is trivial against the value of having the data.

**T0-2. Rerun the strongest baseline on the same hardware on the same library set.** You don't need to rerun everyone. Pick ONE: rerun **Hopper** on cjson + pthreadpool + libplist, 5 trials × 24h each, on your hardware, with your library version. If you can't get Hopper running (it's a known-fragile artifact), run **libErator** instead — it's your direct predecessor and you should be able to.

If even that is not feasible: explicitly state in the paper that "baselines are quoted from cited papers under the original authors' configurations" and remove all bold-face / "best-in-class" claims from Table 8.4. Do *not* leave the table in its current form. Honest framing of weak comparisons is dramatically better than dishonest framing of strong ones.

**T0-3. Disaggregate the +RNR+SCG+LPM ablation.** Running 4 conditions × 4 libraries × 5 trials × 30min = 40 wall-clock hours, parallelizable. Conditions: (i) baseline harness (none), (ii) +SCG seeds only, (iii) +RNR only, (iv) +SCG+RNR (current "with"). Optionally (v) +LPM-only. This is the experiment that tells reviewers which contribution is doing the work, and right now you can't say.

If time-constrained: do this on cjson + pthreadpool only, 3 trials each. That's 1 lib × 5 conditions × 3 trials × 30min = 7.5 hours per library, sequential.

**T0-4. Manual triage of crashes for at least 2 libraries.** Pick libtiff (153 clusters) and cjson (29 clusters). For each, sample at least 10 clusters, classify true bug vs harness-induced, file an issue or check OSS-Fuzz. Get at least **2 documented bugs with upstream confirmation or CVE.** Even one CVE from a confirmed-novel finding moves the needle hard.

If even that is unrealistic: cut Table 8.8 down to crash-cluster *count* only, drop all "high-confidence" claims, and frame the whole crash story as "supporting evidence" not "headline finding."

### Tier 1 — Do these if you have time (12–24 additional hours)

**T1-1. Add at least one LLM-based baseline.** The cheapest comparison is **PromptFuzz** (open source, deterministic with fixed seed, GPT-3.5 cost ∼$5 per library). Even a one-library comparison on cjson + pthreadpool gives you the ability to say "we compared to a SOTA LLM-based tool." Without it the paper has a CCS'24-shaped hole in the related work.

If you can't run PromptFuzz: at minimum, **discuss** PromptFuzz/PromeFuzz/CKGFuzzer in Related Work, explicitly explain why direct comparison was infeasible (artifact issues, cost, model drift), and pitch reproducibility as your differentiator. Do NOT leave them out.

**T1-2. Constraint graph quality on at least 5 libraries, automated.** §6.4.3 already describes the causal edge verification procedure. Run it on 5 libraries (cjson, pthreadpool, libplist, c-ares, libdwarf), report precision/recall per library. Replaces the "Full benchmark table pending" line with a real table.

**T1-3. Statistical tests.** For every cross-tool comparison: Mann-Whitney U at p<0.05, Vargha-Delaney Â₁₂ for effect size. This is mechanical once you have the trial data from T0-1 and T0-2. Add a column to Table 8.4 ("p-value vs. Hopper") or a footnote per row.

**T1-4. Validity rate measured directly.** §1.1 motivates the work by "valid action rate," but I don't see a direct measurement of it anywhere — only line coverage as a proxy. Instrument the harness to log per-action executed-vs-skipped, and report **fraction of actions that reach the library call** as a primary metric. This is one of your two main claims and it should have its own number.

### Tier 2 — Polish (any remaining time)

**T2-1. Build the feature matrix table for §3.3.** Tools as rows (Fudge, FuzzGen, Utopia, WildSync, APICraft, Hopper, NEXZZER, libErator, PromptFuzz, PromeFuzz, CKGFuzzer, Proto-libErator); features as columns (CCI, static analysis, super-harness, repair-not-reject, deterministic, LLM-free). Make it visually obvious that no other tool has all the columns checked.

**T2-2. Aggressive pruning to fit 12 pages.** Likely structure:
- §1 Introduction (1.5 pp)
- §2 Background — SVF, libFuzzer, libprotobuf-mutator, libErator (1 pp)
- §3 Related Work (1 pp)
- §4 Design — PAI + TMS + Super-harness + RNR (3 pp; 1 figure of architecture, 1 of cjson SCG)
- §5 Implementation (0.5 pp)
- §6 Evaluation (4.5 pp; this is where the new experiments live)
- §7 Limitations & Discussion (0.5 pp; trim §9 from 12 pages to half a page)
- §8 Related Work integration / conclusion (0.5 pp)

**T2-3. Anonymize.** Thesis is single-author, Virginia Tech, advisor-named on cover. CCS is double-blind. Strip all of this, anonymize the GitHub link if you have one, third-person all references to libErator [15] (since libErator may be the author's advisor's group's prior work — make sure self-cites are blinded properly).

**T2-4. Title and framing pass.** "Proto-libErator" as a name preserves the connection to libErator, which makes the contribution look smaller than it is. Consider a name that foregrounds the new idea: something like "ProtoFuzz", "TypedDispatch", "API-PAI", or "SuperHarness." The title should probably foreground the *protobuf interposition* idea rather than the libErator parentage.

### Things to NOT do

- Do not run more libraries — you have 11, that's enough for breadth. Depth matters more now.
- Do not run longer campaigns — 24h is fine; reviewers care about coverage curves, not asymptotes.
- Do not try to add LLM features. Stay LLM-free; that's now your differentiator.
- Do not ask the advisor to add new authors / new sections at the last minute.

---

## What I would frame the paper around (if I were writing it)

A paper like this lives or dies on the *claim it picks*. The thesis is hedging across three claims (head-start, sequence exploration, bug finding). For 12 pages I'd pick exactly one and let the others be supporting evidence.

**The pitch I'd lead with:** "Determinism is a feature." Library API fuzzing has split into two camps: precise-but-narrow static analysis (libErator) and broad-but-stochastic LLM-driven generation (PromeFuzz). The first under-explores; the second is non-reproducible, expensive, and class-unpredictable. We show a third path: protobuf-as-API-schema gives you a single deterministic harness covering the entire API surface, with class-predictable performance. On the class where static analysis can capture the constraints (stateful, constraint-dense), we match or exceed LLM-driven SOTA *while being free, deterministic, and offline.*

That's a CCS-shaped story. The current thesis hints at it (§9.4, §10.3) but doesn't lead with it. If you reframe the abstract and intro around this, the same evidence you have looks much stronger, because every "we don't compete on this class" becomes principled scoping rather than a limitation.

---

## Summary of recommended actions, time-prioritized

| Priority | Action | Hours | Required for? |
|---|---|---|---|
| **MUST** | 5-trial reruns on cjson, pthreadpool, libplist, libdwarf (T0-1) | 24-30 | Klees compliance — without this, reject |
| **MUST** | Rerun ≥1 baseline (Hopper or libErator) on same hardware (T0-2) | 12-24 | Honest comparison — without this, reject |
| **MUST** | Disaggregate +RNR / +SCG / +LPM ablation (T0-3) | 8-15 | Attribution — without this, weak |
| **MUST** | Manual crash triage, 2 confirmed bugs with upstream link (T0-4) | 6-12 | Bug claim integrity |
| Should | One LLM-baseline run on cjson + pthreadpool (T1-1) | 8-12 | Engages with current SOTA |
| Should | Automated constraint-graph precision/recall on 5 libs (T1-2) | 4-8 | Replaces "preliminary" with real data |
| Should | Mann-Whitney U + Vargha-Delaney for all cross-tool comparisons (T1-3) | 2 | Statistical bar |
| Should | Direct validity-rate metric (T1-4) | 4 | Measures the thing you claim |
| Polish | Feature-matrix table in Related Work (T2-1) | 1 | Helps reviewers see novelty |
| Polish | Page-budget surgery (T2-2) | 6 | Required to fit 12pp |
| Polish | Anonymize for double-blind (T2-3) | 1 | Required by CFP |

Total MUST budget: ∼55 hours of compute (mostly parallel) + ∼15 hours of writing. Total full plan: ∼80 hours wall-clock.

If you cannot do all of MUST, my honest advice is **withdraw and aim for the next CCS cycle, USENIX Security, or NDSS** rather than submit weak. CCS rejections at a particular cycle do not block resubmission to other venues, but a withdrawn submission is cheaper reputationally than a public CCS reject. If you have the MUST experiments running and most of the writing ready, the submission is worth making.

Good luck. The core idea — protobuf schemas as a typed interposition layer for super-harness fuzzing — is interesting. The work to surface it as a CCS paper is real but tractable, and the runway is tight but not zero.
