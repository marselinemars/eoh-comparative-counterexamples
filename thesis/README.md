# Thesis — Supplementary Materials

This directory is the supplementary materials repository for the thesis
**"LLM-Assisted Automated Heuristic Design: Comparative Counterexamples as a Feedback Object"**
(see [`writing/`](writing/) for the manuscript itself).

The structure here mirrors Appendix B of the thesis. If you are looking for a
specific table, figure, or per-call record cited in the thesis, the inventory
below should point you to the right place.

## Layout

```
thesis/
├── writing/        Manuscript (.docx) and supporting source files
├── code/           Source code: heuristics, evaluation harness, experiment drivers
├── artifacts/      Aggregated analyses, score caches, h_eoh source, splits
├── results/        Per-call LLM provenance (one JSON per call, 645 total)
├── figures/        Generated figures used in the manuscript
├── docs/           Internal project notes (planning, decisions log) — not part of the thesis
└── notes/          Drafting audits and prose-register experiments — not part of the thesis
```

## What's in each directory

### `code/` — source code

Per-experiment packages:

- `code/chapter5/` — **§4.2 selection experiments.** Batch runner, strategy definitions, sanitizer, seed policy, validation runner, Level-1 prompt template.
- `code/chapter6/` — **§4.3 structure experiments.** Batch runner, prompt renderer, Level-1 and Level-2 prompt templates, trace extractor, validation runner.
- `code/chapter7/` — **§4.4 cardinality experiments.** Batch runner, prompt builder, Level-1 and Level-2 prompt templates, strategies, seed policy, validation runner.

Shared modules:

- `code/weibull_generator.py` — Instance generator for all five splits (§3.4).
- `code/evaluation.py` — Score-function harness: per-decision argmax placement and bin counting.
- `code/counterexample.py` — Comparative counterexample construction from per-instance gaps (§3.5).
- `code/incumbents.py` — Loaders for `h_eoh` and the reference heuristic `62a2846c597e`.
- `code/score_cache.py` — Cached per-(heuristic, instance) bin counts.
- `code/splits.py` — Five-split generator and loader.
- `code/experiments/` — One-off scripts (analysis, figure generation, probes).

### `results/` — per-call provenance

Each LLM call produced during a batch is stored as an individual JSON file
containing the request payload, the full response text, the extracted code,
the sanitization outcome, and all downstream evaluation results.

| Directory                                  | Section | Calls |
|--------------------------------------------|---------|------:|
| `results/chapter5_primary_batch_gemini/`   | §4.2 primary batch    | 300 |
| `results/chapter5_validation_batch_gemini/`| §4.2 validation       |  45 |
| `results/chapter6_primary_batch_gemini/`   | §4.3 primary batch    | 240 |
| `results/chapter6_validation_batch_gemini/`| §4.3 validation       |  60 |
| `results/chapter7_primary_batch_gemini/`   | §4.4 primary batch    | 840 |
| `results/chapter7_validation_batch_gemini/`| §4.4 validation       | 210 |

Storing responses verbatim is what makes the proposal distributions in
Chapter 4 inspectable without re-issuing model calls — important because
Gemini 2.5 Pro is not bit-deterministic across calls even with fixed
prompts and parameters.

### `artifacts/` — aggregated analyses and supporting files

- `h_eoh.py` — Full source of the incumbent heuristic (§3.3).
- `h_eoh_counterexample_pool.json` — Per-instance score gaps between `h_eoh` and the reference on `train_select` (§3.5).
- `score_cache.json` — Materialized per-(heuristic, instance) bin counts.
- `splits/` — Five-split definitions: `train_select`, `train_step`, `train_gate`, `dev`, `test_ood`.
- `chapter5_summary.json` — §4.2 selection summary statistics.
- `chapter6_*.json` (12 files) — §4.3 structural-enrichment analyses: primary-batch overview, validation overview, jackknife sensitivity, matched-pair statistics, trace-render probes.
- `chapter7_*.json` (15 files) — §4.4 cardinality analyses: primary-batch overview, validation overview, failure taxonomy, dev-split scoring, L2-interaction stratified by k, anchor reproduction, per-cell counterexample sets.
- `argmax_equivalent_reasoning_bundle.md` — Per-call records supporting the argmax-equivalence analysis (§§4.2 and 4.3).

## Note on directory naming

The `chapter5`, `chapter6`, and `chapter7` prefixes used throughout `code/`,
`results/`, and the aggregated-artifact filenames correspond to thesis
sections **§4.2 (selection)**, **§4.3 (structure)**, and **§4.4 (cardinality)**
respectively. The numeric prefix was kept stable across drafts because
scripts (in particular the batch runners and score-cache routines) key on
these path components; renaming them would invalidate cached evaluation
results without changing the underlying evidence.

Cell identifiers used in §4.4 (`CH7-01` through `CH7-14`) share this
historical prefix and correspond to the `cell_id` field in the
`chapter7_*.json` records.

## Reproducing thesis tables and figures

The aggregated-analysis JSON files in `artifacts/` contain the source data
for the Chapter 4 tables. The figure scripts live under
`code/experiments/` (search for `make_figures`, `matched_pairs_plots`,
`figure_*` prefixes).

The per-call provenance in `results/` is the source of truth for any
statistic that depends on individual LLM responses (proposal distributions,
argmax-equivalence rates, acceptance decisions). Aggregated analyses can
be regenerated from the per-call records.

## Internal documentation (not part of the thesis)

`docs/` and `notes/` contain working notes, decisions log, drafting audits,
and outline files used during the writing process. They are kept under
version control for transparency but are not intended for the jury — the
canonical results, claims, and methodology are in the thesis manuscript
itself.

## Branch

Thesis work lives on branch `thesis-counterexample`.
