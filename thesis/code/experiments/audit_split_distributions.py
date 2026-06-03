"""
thesis/code/experiments/audit_split_distributions.py

Audit that the five thesis splits are statistically consistent with
their declared distributions, and in particular that the three
train_* subsets are indistinguishable from each other beyond sampling
noise.

Checks:
  (1) item-level summary statistics (mean, std, percentiles) per split,
  (2) L1 lower-bound summary stats per split,
  (3) pairwise Kolmogorov-Smirnov p-values on the pooled item
      distributions of train_select / train_step / train_gate —
      high p-values mean "cannot reject same distribution," which is
      what we want,
  (4) bins-used for h_eoh on each split (a packing-difficulty proxy)
      — the three train_* subsets should give similar mean bins.

The KS p-values are informational. With 30 instances × 5000 items =
150000 samples per train_* subset, pathologically tiny differences
can still be flagged as significant, so the interpretation is by
magnitude, not by the 0.05 threshold.

Usage:
    python -m thesis.code.experiments.audit_split_distributions
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import numpy as np
from scipy.stats import ks_2samp

from thesis.code.evaluation import bins_used, load_heuristic_from_code
from thesis.code.incumbents import get_h_eoh
from thesis.code.score_cache import ScoreCache
from thesis.code.splits import (
    SPLITS_DIR,
    load_split,
    qualified_instance_id,
)

SPLIT_NAMES = ("train_select", "train_step", "train_gate", "dev", "test_ood")
TRAIN_NAMES = ("train_select", "train_step", "train_gate")


def summarize_items(split: Dict) -> Dict:
    all_items = np.concatenate(
        [np.array(inst["items"]) for inst in split["instances"]]
    )
    return {
        "n_total_items": int(all_items.size),
        "mean": float(all_items.mean()),
        "std": float(all_items.std()),
        "p10": float(np.percentile(all_items, 10)),
        "p50": float(np.percentile(all_items, 50)),
        "p90": float(np.percentile(all_items, 90)),
    }


def summarize_l1_bounds(split: Dict) -> Dict:
    """Per-instance L1 lower bound = ceil(sum(items)/capacity).
    Returns (mean, std, min, max) across the split's instances."""
    bounds = []
    for inst in split["instances"]:
        bound = int(np.ceil(sum(inst["items"]) / inst["capacity"]))
        bounds.append(bound)
    arr = np.array(bounds)
    return {
        "n_instances": int(arr.size),
        "mean": float(arr.mean()),
        "std": float(arr.std()),
        "min": int(arr.min()),
        "max": int(arr.max()),
    }


def score_h_eoh_on_split(
    split: Dict, split_name: str, cache: ScoreCache, module
) -> Dict:
    """Use the score cache so this audit is cheap on re-runs."""
    h_eoh_meta = get_h_eoh()
    code_h = h_eoh_meta["code_hash"]
    per_inst: List[int] = []
    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        b = cache.get_or_compute(
            code_h, qid, lambda i=inst: bins_used(module, i)
        )
        per_inst.append(b)
    arr = np.array(per_inst)
    return {
        "n_instances": int(arr.size),
        "mean_bins": float(arr.mean()),
        "std_bins": float(arr.std()),
        "min_bins": int(arr.min()),
        "max_bins": int(arr.max()),
    }


def main() -> int:
    splits = {name: load_split(name) for name in SPLIT_NAMES}

    print("=== Item-level summary ===")
    print(f"{'split':<14} {'mean':>7} {'std':>7} {'p10':>5} {'p50':>5} {'p90':>5}")
    item_summaries = {}
    for name in SPLIT_NAMES:
        s = summarize_items(splits[name])
        item_summaries[name] = s
        print(
            f"{name:<14} {s['mean']:>7.3f} {s['std']:>7.3f} "
            f"{s['p10']:>5.1f} {s['p50']:>5.1f} {s['p90']:>5.1f}"
        )

    print("\n=== L1 lower-bound summary (per instance) ===")
    print(f"{'split':<14} {'mean':>9} {'std':>7} {'min':>6} {'max':>6}")
    for name in SPLIT_NAMES:
        s = summarize_l1_bounds(splits[name])
        print(
            f"{name:<14} {s['mean']:>9.2f} {s['std']:>7.2f} "
            f"{s['min']:>6d} {s['max']:>6d}"
        )

    print("\n=== Pairwise KS tests on pooled items (train_* subsets) ===")
    print(f"{'pair':<35} {'KS stat':>10} {'p-value':>10}")
    pooled = {}
    for name in TRAIN_NAMES:
        pooled[name] = np.concatenate(
            [np.array(inst["items"]) for inst in splits[name]["instances"]]
        )
    for i, a in enumerate(TRAIN_NAMES):
        for b in TRAIN_NAMES[i + 1:]:
            stat, p = ks_2samp(pooled[a], pooled[b])
            print(
                f"{a + ' vs ' + b:<35} "
                f"{float(stat):>10.5f} {float(p):>10.5f}"
            )

    print("\n=== h_eoh bins_used per split ===")
    cache = ScoreCache()
    h_eoh_meta = get_h_eoh()
    module = load_heuristic_from_code(
        h_eoh_meta["code"], module_name="h_eoh_audit"
    )
    print(f"{'split':<14} {'mean_bins':>10} {'std':>7} {'min':>6} {'max':>6}")
    for name in SPLIT_NAMES:
        r = score_h_eoh_on_split(splits[name], name, cache, module)
        print(
            f"{name:<14} {r['mean_bins']:>10.3f} {r['std_bins']:>7.3f} "
            f"{r['min_bins']:>6d} {r['max_bins']:>6d}"
        )
    cache.save()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
