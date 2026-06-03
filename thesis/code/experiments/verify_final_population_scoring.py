"""
thesis/code/experiments/verify_final_population_scoring.py

Observation script. Scores every member of EoH's final population on
a chosen evaluation set, reports per-instance bin counts and the mean
ranking, and compares this ranking to the stored EoH `objective`
ordering (which is the ranking on EoH's own training distribution,
Weibull 5k).

Ranking disagreement is an observation, not a failure. Wrapper
correctness is established separately by
`verify_eoh_objective_5k.py`, which reproduces EoH's stored objective
to 5 decimals on EoH's own training distribution.

Usage:
    python -m thesis.code.experiments.verify_final_population_scoring
    python -m thesis.code.experiments.verify_final_population_scoring --size 1k
    python -m thesis.code.experiments.verify_final_population_scoring --size 2k
"""
from __future__ import annotations

import argparse

from thesis.code.evaluation import (
    bins_used,
    load_heuristic_from_code,
    load_instances,
)
from thesis.code.incumbents import load_final_population


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score the EoH final population on a chosen dataset.",
    )
    parser.add_argument(
        "--size",
        default="1k",
        help="Test pickle suffix (e.g. 1k, 2k, 5k). Default: 1k.",
    )
    parser.add_argument(
        "--capacity",
        type=int,
        default=100,
        help="Bin capacity. Default: 100 (matches the harness default).",
    )
    args = parser.parse_args()

    pop = load_final_population()
    pop_sorted = sorted(pop, key=lambda m: m["objective"])

    instances = load_instances(size=args.size, capacity=args.capacity)
    instance_ids = sorted(instances.keys())

    print(
        f"Scoring {len(pop_sorted)} heuristics on {len(instances)} "
        f"instances from Weibull {args.size} (capacity={args.capacity})\n"
    )

    header = (
        f"{'hash':<14} | {'stored_obj':>10} | "
        + " | ".join(f"{iid:>7}" for iid in instance_ids)
        + f" | {'mean_bins':>10}"
    )
    print(header)
    print("-" * len(header))

    results = {}
    for m in pop_sorted:
        module = load_heuristic_from_code(
            m["code"], module_name=f"h_{m['code_hash']}"
        )
        row = {iid: bins_used(module, instances[iid]) for iid in instance_ids}
        mean_bins = sum(row.values()) / len(row)
        results[m["code_hash"]] = {
            "stored_obj": m["objective"],
            "mean_bins": mean_bins,
        }
        print(
            f"{m['code_hash']:<14} | {m['objective']:>10.5f} | "
            + " | ".join(f"{row[iid]:>7d}" for iid in instance_ids)
            + f" | {mean_bins:>10.3f}"
        )

    by_stored = sorted(results.keys(), key=lambda h: results[h]["stored_obj"])
    by_mean = sorted(results.keys(), key=lambda h: results[h]["mean_bins"])

    print()
    print("Ordering by stored EoH objective (asc): " + " -> ".join(by_stored))
    print(f"Ordering by mean bins_used on Weibull {args.size} (asc): "
          + " -> ".join(by_mean))
    if by_stored == by_mean:
        print(f"\nRankings agree on Weibull {args.size}.")
    else:
        print(
            f"\nRankings disagree on Weibull {args.size}. "
            "This is an observation about ranking stability across "
            "evaluation distributions, not a wrapper error. See "
            "thesis/docs/06_findings_log.md for context; see "
            "verify_eoh_objective_5k.py for the wrapper correctness "
            "check."
        )
    return 0  # observation only, never a failure


if __name__ == "__main__":
    raise SystemExit(main())
