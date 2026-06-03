"""
thesis/code/experiments/scale_sweep_final_population.py

Observation. Scores every member of EoH's final population across
four evaluation sets and writes the consolidated result to
thesis/results/observations/final_pop_rankings_scale_sweep.json.

Per-instance bins_used values are routed through the persistent
score cache at thesis/artifacts/score_cache.json. On a clean cache
the full sweep takes ~40s; subsequent runs are effectively instant.

The four evaluation sets:
    pickle_1k         Weibull 1k from testingdata/test_dataset_1k.pkl
    pickle_2k         Weibull 2k from testingdata/test_dataset_2k.pkl
    pickle_5k         Weibull 5k from testingdata/test_dataset_5k.pkl
    eoh_inline_5k     the 5k dataset EoH actually trained on,
                      hardcoded in eoh/src/.../bp_online/get_instance.py

Usage:
    python -m thesis.code.experiments.scale_sweep_final_population
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from thesis.code.evaluation import (
    bins_used,
    load_heuristic_from_code,
    load_instances,
)
from thesis.code.incumbents import load_final_population
from thesis.code.score_cache import ScoreCache

REPO_ROOT = Path(__file__).resolve().parents[3]
EOH_BP = REPO_ROOT / "eoh" / "src" / "eoh" / "problems" / "optimization" / "bp_online"
OUT_PATH = (
    REPO_ROOT
    / "thesis"
    / "results"
    / "observations"
    / "final_pop_rankings_scale_sweep.json"
)
CAPACITY = 100


def load_eoh_inline_5k():
    """Return the single dataset EoH trained on, as a dict of instances."""
    if str(EOH_BP) not in sys.path:
        sys.path.insert(0, str(EOH_BP))
    from get_instance import GetData  # noqa: E402
    gd = GetData()
    datasets, _ = gd.get_instances()
    if len(datasets) != 1:
        raise RuntimeError(
            f"Expected 1 EoH inline dataset, got {len(datasets)}"
        )
    (_, instances), = datasets.items()
    return instances


def score_heuristics(pop_sorted, instances, source_label, cache):
    print(f"=== {source_label} ===")
    instance_ids = sorted(instances.keys())
    rows = {}
    for m in pop_sorted:
        module = load_heuristic_from_code(
            m["code"], module_name=f"h_{m['code_hash']}_{source_label}"
        )
        per_inst = {}
        for iid in instance_ids:
            qualified_iid = f"{source_label}:{iid}"
            per_inst[iid] = cache.get_or_compute(
                m["code_hash"],
                qualified_iid,
                lambda iid_=iid: bins_used(module, instances[iid_]),
            )
        mean_bins = sum(per_inst.values()) / len(per_inst)
        rows[m["code_hash"]] = {
            "per_instance_bins_used": per_inst,
            "mean_bins_used": mean_bins,
        }
        print(
            f"  {m['code_hash']} stored_obj={m['objective']:.5f} "
            f"mean_bins={mean_bins:.3f}"
        )
    ranking = sorted(rows.keys(), key=lambda h: rows[h]["mean_bins_used"])
    print(f"  ranking (best -> worst): " + " -> ".join(ranking))
    print()
    return {
        "instance_ids": instance_ids,
        "per_heuristic": rows,
        "ranking_by_mean_bins_asc": ranking,
    }


def main() -> int:
    t0 = time.perf_counter()
    cache = ScoreCache()
    stats_before = cache.stats()
    print(f"Cache before: {stats_before}\n")

    pop = load_final_population()
    pop_sorted = sorted(pop, key=lambda m: m["objective"])

    out = {
        "capacity": CAPACITY,
        "sources": ["pickle_1k", "pickle_2k", "pickle_5k", "eoh_inline_5k"],
        "heuristics": [
            {"code_hash": m["code_hash"], "stored_objective": m["objective"]}
            for m in pop_sorted
        ],
        "by_source": {},
    }

    for size in ("1k", "2k", "5k"):
        label = f"pickle_{size}"
        out["by_source"][label] = score_heuristics(
            pop_sorted,
            load_instances(size=size, capacity=CAPACITY),
            label,
            cache,
        )

    out["by_source"]["eoh_inline_5k"] = score_heuristics(
        pop_sorted, load_eoh_inline_5k(), "eoh_inline_5k", cache
    )

    cache.save()
    stats_after = cache.stats()
    print(f"Cache after:  {stats_after}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(out, indent=2, sort_keys=True), encoding="utf-8"
    )
    elapsed = time.perf_counter() - t0
    print(f"\nWrote {OUT_PATH.relative_to(REPO_ROOT).as_posix()}")
    print(f"Elapsed: {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
