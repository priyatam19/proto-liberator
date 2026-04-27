# Proto-libErator CCS 2026 Cycle B Draft

This folder contains an initial ACM CCS 2026 Cycle B submission package derived
from the current thesis/paper drafts, with desk-reject-sensitive requirements
pre-wired.

## Build

```bash
cd /home/fuzzserver/Research/proto-liberator/ccs_paper/ccs26_cycleB
make all
```

Output:
- `main.pdf`

## Key files

- `main.tex`: CCS-format anonymous draft (`acmart`, `sigconf`).
- `proto_liberator_refs.bib`: bibliography.
- `appendices/open_science.tex`: required Open Science appendix.
- `appendices/ethical_considerations.tex`: ethics appendix.
- `appendices/generative_ai_usage.tex`: AI-usage disclosure section.
- `docs/CCS26_CycleB_Submission_Checklist.md`: desk-reject guardrail checklist.
- `docs/hotcrp_abstract_draft.txt`: proposed final abstract text for registration.
- `docs/hotcrp_track_justification_draft.txt`: track justification draft.
- `docs/Required_Experiments_Before_Full_Submission.md`: short critical-path experiment plan.
- `scripts/scrape_ccs26_requirements.py`: reproducible CFP extractor.
- `web_sources/`: saved CFP/template snapshots with fetch timestamps.

## Current status

- Compiles successfully to PDF.
- Includes mandatory appendix names required by CCS 2026 CFP.
- Needs final factual tightening and experiment completion before full submission.
