# Thesis split provenance

This directory contains the canonical five-subset split of Weibull
instances used by all thesis experiments from chapter 5 onward. See
`thesis/docs/01_decisions_log.md` (2026-04-20) for the split-design
decision.

## Subsets

| name          | num instances | num items / instance | seed offset | purpose |
|---------------|--------------:|---------------------:|------------:|---------|
| train_select  |            30 |                 5000 |         101 | counterexample selection pool |
| train_step    |            30 |                 5000 |         102 | per-step LLM-proposal evaluation |
| train_gate    |            30 |                 5000 |         103 | proposed-improvement gating |
| dev           |            30 |                 5000 |         201 | held-out validation |
| test_ood      |            30 |                10000 |         301 | out-of-distribution (larger scale) |

## Reproducibility

All instances are regenerable from `thesis/code/splits.py` given:

- **Master seed:** `20260420` (encoded as `2026_04_20`)
- **Per-subset seeds:** master + offset from the table above
- **Distribution:** Weibull shape=3, scale=45, clipped to [1, 100],
  rounded to integer item sizes
- **Capacity:** 100 (all instances)

Running `python -m thesis.code.splits` recreates every split file
bit-identically.

## Disjointness guarantees

- `train_select`, `train_step`, and `train_gate` share no instance
  IDs and no item sequences. Enforced by `splits.build_all_splits`
  and verified by `thesis/code/tests/test_splits.py`.
- `dev` uses a separate seed from the train_* subsets; statistical
  overlap in item sequences is astronomically unlikely but not
  formally forbidden (not needed — dev is for reporting, not training).
- `test_ood` uses a different problem scale (10000 items vs 5000),
  so items and IDs cannot collide with any in-distribution subset.

## Relationship to prior artifacts

The existing pickles at `examples/bp_online/evaluation/testingdata/`
(1k, 2k, 5k, 10k, 100k) were generated without a pinned seed and
cannot be reproduced from this repo. They remain committed as the
evaluation substrate for the scale-sweep findings in
`thesis/docs/06_findings_log.md` but are not used as thesis training
or evaluation splits. The 5k-instance EoH inline dataset
(hardcoded in `eoh/src/eoh/problems/optimization/bp_online/get_instance.py`)
is EoH's training distribution and is not used as any thesis split.
