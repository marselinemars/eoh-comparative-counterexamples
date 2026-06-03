# EoH run provenance

This directory contains the output of an EoH run that serves as the
**frozen upstream artifact** for all thesis experiments in branch
`thesis-counterexample`, per the post-hoc-on-EoH commitment recorded
in `thesis/docs/01_decisions_log.md` (2026-04-20).

## Run parameters

- **Platform:** Local workstation (MacBook Air, Model Mac14,2)
- **Node / host:** MacBook-Air-3.local
- **OS:** macOS 15.6 (build 24G84), Darwin 24.6.0
- **Architecture:** ARM64
- **CPU:** Apple M2, 8 cores (4 performance + 4 efficiency)
- **Memory:** 16 GB RAM
- **Date of run:** 2026-04-18 (started 22:06:31 local, ended
  2026-04-19 00:09:01 local)
- **Runtime:** approximately 2h 02m 30s
- **Model used by EoH:** Gemini 2.5 Pro
- **Number of generations persisted:** 11 (generations 0 through 10)
- **Population size:** 4 for generations 1–10; 2 for generation 0
  (initial seed pool before the first evolution step)
- **Random seed:** 2024 (set via `random.seed(2024)` in EoH)
- **EoH code version at time of run:** commit
  `801c4765abb54ca0c40f16fc1fbe1fc02f860189`, branch `main`

## Contents

- `pops/population_generation_{0..10}.json` — full populations per
  generation. Generation 0 has 2 members; generations 1–10 have 4
  members each.
- `pops_best/population_generation_{1..10}.json` — best-of-generation
  singletons. Generation 0 has no corresponding best-of-gen file (EoH
  convention: best-of-gen is written only for post-evolution
  generations). For every generation in which both files exist, the
  `pops_best/` entry equals the minimum-objective member of the
  matching `pops/` file (verified 2026-04-20).

## Plateau and halting behavior

Evolution effectively halted after the generation-7 → generation-8
transition. Generations 8, 9, and 10 are **bit-identical populations**
(all four members unchanged across the three generations). The
fitness-best objective value of 0.01207 first appeared in generation
7; the population composition stabilized fully in generation 8.

For thesis purposes, the canonical "EoH final population" is
`pops/population_generation_10.json`, by decision logged in
`thesis/docs/01_decisions_log.md` (2026-04-20). This is equivalent
by content to generations 8 and 9.

## Model note

EoH was executed with Gemini 2.5 Pro. The thesis-primary model for
chapters 5–7 experiments is Gemini 3.1 Pro Preview (see decisions
log, 2026-04-20). EoH's internal model choice is treated as a
black-box property of the artifact, not a thesis variable: the
artifact is consumed as frozen input, and chapters 5–7 operate on
it without further EoH invocation.

## Minor modification to the vendored EoH source

A single pre-thesis edit was committed to
`eoh/src/eoh/problems/optimization/bp_online/get_instance.py`: a
`print(opt_num_bins)` debug line was removed. No behavioral change
beyond stdout suppression. See the decisions log entry
"Two pre-thesis print-suppression edits grandfathered" (2026-04-20)
for full context. A diff against upstream EoH commit `801c4765...`
can be produced on demand.

## Final population, h_eoh, and the reference pool

- **Final population:** the 4 members of
  `pops/population_generation_10.json`.
- **`h_eoh`:** the fitness-best member of the final population
  (minimum `objective` field). Code hash `8ca83676ae76` (sha256,
  first 12 hex); objective 0.01207.
- **Reference pool for `h_eoh`:** the 3 non-`h_eoh` members of the
  final population. Code hashes `47d987c33837` (obj 0.01912),
  `62a2846c597e` (obj 0.01308), `bea3036f5424` (obj 0.01449).

See `thesis/code/incumbents.py` for the canonical extraction
pipeline and `thesis/artifacts/h_eoh.py` for the extracted heuristic.

## Regeneration policy

This artifact is immutable. If a fresh EoH run is ever required, it
is committed to a new subdirectory (for example, `results_run2/`)
with its own `RUN_PROVENANCE.md`, and the decision to adopt the new
run is logged in `thesis/docs/01_decisions_log.md`.
