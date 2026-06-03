"""
generate_eval_splits.py

Generates fixed dev and test_ood instance splits for bp_online refinement
evaluation. Run once to produce the split files; never regenerate after that.

The 5 existing bundled Weibull 5k instances become search_train.
This script generates:
  - dev split     (5 instances, seed 20260001) — for acceptance decisions
  - test_ood split (5 instances, seed 20260002) — held out, final reporting only

Output: two pickle files saved alongside this script.

Usage:
    python generate_eval_splits.py
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np

REFINEMENT_DIR = Path(__file__).resolve().parent
DEV_PATH = REFINEMENT_DIR / "eval_split_dev.pkl"
TEST_OOD_PATH = REFINEMENT_DIR / "eval_split_test_ood.pkl"

NUM_ITEMS = 5000
CAPACITY = 100
WEIBULL_SHAPE = 3
WEIBULL_SCALE = 45
CLIP_MAX = 100


def generate_weibull_instances(
    n: int,
    num_items: int,
    seed: int,
) -> list[dict]:
    rng = np.random.default_rng(seed)
    instances = []
    for i in range(n):
        samples = rng.weibull(WEIBULL_SHAPE, num_items) * WEIBULL_SCALE
        samples = np.clip(samples, 1, CLIP_MAX)
        sizes = np.round(samples).astype(int).tolist()
        instances.append({
            "capacity": CAPACITY,
            "num_items": num_items,
            "items": sizes,
        })
    return instances


def build_split_records(
    instances: list[dict],
    split_name: str,
    dataset_name: str = "Weibull 5k",
) -> list[dict]:
    import math
    records = []
    for i, inst in enumerate(instances):
        items = np.array(inst["items"])
        capacity = float(inst["capacity"])
        lower_bound = float(math.ceil(float(np.sum(items)) / capacity))
        records.append({
            "instance_id": f"{dataset_name}/{split_name}_{i}",
            "dataset_name": dataset_name,
            "case_name": f"{split_name}_{i}",
            "split": split_name,
            "capacity": capacity,
            "num_items": int(inst["num_items"]),
            "items": inst["items"],
            "lower_bound": lower_bound,
        })
    return records


def main() -> None:
    if DEV_PATH.exists() or TEST_OOD_PATH.exists():
        print("WARNING: split files already exist.")
        answer = input("Overwrite? (yes/no): ").strip().lower()
        if answer != "yes":
            print("Aborted. Existing files preserved.")
            return

    print("Generating dev split (seed=20260001, 5 instances)...")
    dev_instances = generate_weibull_instances(5, NUM_ITEMS, seed=20260001)
    dev_records = build_split_records(dev_instances, "dev")

    print("Generating test_ood split (seed=20260002, 5 instances)...")
    test_instances = generate_weibull_instances(5, NUM_ITEMS, seed=20260002)
    test_records = build_split_records(test_instances, "test_ood")

    with DEV_PATH.open("wb") as fh:
        pickle.dump(dev_records, fh)
    print(f"  saved: {DEV_PATH}")

    with TEST_OOD_PATH.open("wb") as fh:
        pickle.dump(test_records, fh)
    print(f"  saved: {TEST_OOD_PATH}")

    # Sanity check: evaluate the current best incumbent on all splits
    print("\nSanity-checking current best incumbent across splits...")
    import sys
    sys.path.insert(0, str(REFINEMENT_DIR))
    from evaluate_heuristic_cases import (
        evaluate_heuristic_on_instances,
        load_heuristic_module_from_code,
        summarize_case_results,
    )
    from load_instances import load_split_instances

    INCUMBENT_CODE = """\
import numpy as np

def score(item, bins):
    remainder = bins - item
    utilization_score = item / bins
    small_remainder_incentive = 1.0 / (1.0 + remainder / item)
    steepness_multiple = 20.0
    multiplicity_bonus = np.exp(
        -steepness_multiple * (np.round(remainder / item) - remainder / item) ** 2
    )
    fragment_penalty_term = np.where(
        (remainder > 0) & (remainder < item),
        (1.0 - (remainder / item)) ** 4, 0.0,
    )
    fragment_penalty_magnitude = 3.1
    combined_score_for_non_perfect_fits = (
        utilization_score
        + 0.5 * small_remainder_incentive
        + 1.15 * multiplicity_bonus
        - fragment_penalty_magnitude * fragment_penalty_term
    )
    scores = np.where(remainder == 0, np.inf, combined_score_for_non_perfect_fits)
    return scores
"""
    mod = load_heuristic_module_from_code(INCUMBENT_CODE)

    for split in ("search_train", "dev", "test_ood"):
        insts = load_split_instances(split)
        results = evaluate_heuristic_on_instances(insts, heuristic_module=mod)
        summary = summarize_case_results(results)
        print(f"  {split:12s}  mean_gap={summary['mean_objective_gap']:.8f}  "
              f"n={summary['num_instances']}")

    print("\nDone. Splits are fixed — do not regenerate.")
    print("  search_train = 5 bundled instances (existing)")
    print("  dev          = eval_split_dev.pkl")
    print("  test_ood     = eval_split_test_ood.pkl")
    print("\nIMPORTANT: test_ood must not be used during any refinement experiment.")
    print("Only open test_ood for final reporting to the supervisor.")


if __name__ == "__main__":
    main()
