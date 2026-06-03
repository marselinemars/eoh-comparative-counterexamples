"""
thesis/code/experiments/verify_eoh_objective_5k.py

Wrapper-correctness check. Reproduces EoH's stored `objective` field
for every member of EoH's final population, on EoH's own training
distribution (the one hardcoded in
eoh/src/eoh/problems/optimization/bp_online/get_instance.py), and
compares to the stored values to five-decimal precision.

If all four heuristics match their stored objective to 5 decimals,
the thesis wrapper is correct and any ranking disagreement on other
datasets is a real scale-dependent phenomenon, not a wrapper bug.

Usage:
    python -m thesis.code.experiments.verify_eoh_objective_5k
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
EOH_BP = REPO_ROOT / "eoh" / "src" / "eoh" / "problems" / "optimization" / "bp_online"
if str(EOH_BP) not in sys.path:
    sys.path.insert(0, str(EOH_BP))

from get_instance import GetData  # noqa: E402  (EoH's vendored dataset loader)

from thesis.code.evaluation import bins_used, load_heuristic_from_code
from thesis.code.incumbents import load_final_population

TOLERANCE = 5e-6  # rounded to 5 decimals, so 0.5 ULP at that precision


def main() -> int:
    gd = GetData()
    datasets, opt_num_bins = gd.get_instances()
    if len(datasets) != 1:
        print(f"ERROR: expected 1 dataset, got {len(datasets)}: "
              f"{list(datasets.keys())}")
        return 2
    (dataset_name, instances), = datasets.items()
    lb = opt_num_bins[dataset_name]
    print(f"Dataset: {dataset_name}")
    print(f"Instances: {len(instances)}")
    print(f"L1 lower bound (dataset-level mean): {lb}")
    print()

    pop = load_final_population()
    pop_sorted = sorted(pop, key=lambda m: m["objective"])

    header = (
        f"{'hash':<14} | {'stored_obj':>10} | "
        + " | ".join(f"{iid:>8}" for iid in instances.keys())
        + f" | {'mean_bins':>10} | {'computed':>10} | {'delta':>12}"
    )
    print(header)
    print("-" * len(header))

    all_match = True
    for m in pop_sorted:
        module = load_heuristic_from_code(
            m["code"], module_name=f"h_{m['code_hash']}"
        )
        per_instance = {
            iid: bins_used(module, inst)
            for iid, inst in instances.items()
        }
        mean_bins = float(np.mean(list(per_instance.values())))
        computed = (mean_bins - lb) / lb
        computed_rounded = float(np.round(computed, 5))
        delta = abs(computed_rounded - m["objective"])
        status = "ok" if delta <= TOLERANCE else "MISMATCH"
        if delta > TOLERANCE:
            all_match = False
        print(
            f"{m['code_hash']:<14} | {m['objective']:>10.5f} | "
            + " | ".join(f"{per_instance[iid]:>8d}" for iid in instances.keys())
            + f" | {mean_bins:>10.3f} | {computed_rounded:>10.5f} | "
            + f"{delta:>12.2e} {status}"
        )

    print()
    if all_match:
        print("WRAPPER VERIFIED: all four heuristics reproduce EoH's "
              "stored objective to 5 decimals.")
        return 0
    print("WRAPPER MISMATCH: at least one heuristic disagrees. "
          "Investigate before committing thesis/code/evaluation.py.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
