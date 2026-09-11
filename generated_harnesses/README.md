# Reproducible saved campaigns

Each library directory is a self-contained saved campaign input:

- `harness.cc` and `<library>.v2.proto` are the sources from the archived
  high-coverage run.
- `initial_corpus.tar.gz` is that run's mature corpus, not a newly randomized
  seed corpus.
- `campaign.json` records the corpus checksum and file count, plus the runtime
  settings used by the 11-library launcher.

`scripts/run_highcoverage_campaigns.sh` uses these files by default. The normal
generator still runs, after which `scripts/run_campaign.sh` compiles the saved
proto/harness and starts from the saved corpus. The final coverage result is
collected with a comprehensive per-input replay. Use `--regenerate-harnesses`
to keep newly generated sources and start from newly generated seeds instead.
Use `--fresh-seeds` to keep the saved proto/harness and deterministic campaign
profile while generating a new simple seed corpus instead of extracting the
archived mature corpus. Separate output roots give independent fresh-start
experiments with no corpus carry-over.

The default reproducibility profile is common across the suite: 24 hours,
coverage snapshots every 15 minutes, `jobs=1`, `workers=1`, `max_len=4096`,
per-input timeout 25 seconds, `max_actions=64`, and seed 1337. Ten libraries use
`fork=2`; cJSON uses `fork=1`, matching its archived best configuration.
