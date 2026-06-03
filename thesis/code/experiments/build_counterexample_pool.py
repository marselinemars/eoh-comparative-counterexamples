"""
thesis/code/experiments/build_counterexample_pool.py

Build the canonical chapter-5 counterexample pool for h_eoh against
the fixed chapter-5 reference (code hash 62a2846c597e), over the 30
instances of train_select.

Idempotent and deterministic: running twice produces byte-identical
output. Uses the score cache so re-runs are instant.

Artifacts produced:
    thesis/artifacts/h_eoh_counterexample_pool.json
    thesis/artifacts/h_eoh_counterexample_pool_stats.json

Usage:
    python -m thesis.code.experiments.build_counterexample_pool
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

from thesis.code.counterexample import Counterexample, CounterexampleSet
from thesis.code.evaluation import bins_used, load_heuristic_from_code
from thesis.code.incumbents import get_h_eoh, load_final_population
from thesis.code.score_cache import ScoreCache
from thesis.code.splits import load_split, qualified_instance_id

REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS_DIR = REPO_ROOT / "thesis" / "artifacts"
POOL_PATH = ARTIFACTS_DIR / "h_eoh_counterexample_pool.json"
STATS_PATH = ARTIFACTS_DIR / "h_eoh_counterexample_pool_stats.json"

EXPECTED_H_EOH_HASH = "8ca83676ae76"
CHAPTER5_REFERENCE_HASH = "62a2846c597e"
SPLIT_NAME = "train_select"


def _load_reference():
    pop = load_final_population()
    for m in pop:
        if m["code_hash"] == CHAPTER5_REFERENCE_HASH:
            return m
    raise RuntimeError(
        f"Chapter-5 reference heuristic (hash {CHAPTER5_REFERENCE_HASH!r}) "
        f"not found in EoH final population. Population hashes: "
        f"{[m['code_hash'] for m in pop]}"
    )


def _compute_pool(split: dict, cache: ScoreCache) -> CounterexampleSet:
    h_eoh = get_h_eoh()
    if h_eoh["code_hash"] != EXPECTED_H_EOH_HASH:
        raise RuntimeError(
            f"h_eoh hash mismatch: got {h_eoh['code_hash']!r}, "
            f"expected {EXPECTED_H_EOH_HASH!r}"
        )
    reference = _load_reference()

    cand_module = load_heuristic_from_code(
        h_eoh["code"], module_name=f"h_cand_{h_eoh['code_hash']}"
    )
    ref_module = load_heuristic_from_code(
        reference["code"], module_name=f"h_ref_{reference['code_hash']}"
    )

    items = []
    for inst in split["instances"]:
        qid = qualified_instance_id(SPLIT_NAME, inst["instance_id"])
        cand_bins = cache.get_or_compute(
            h_eoh["code_hash"],
            qid,
            lambda i=inst: bins_used(cand_module, i),
        )
        ref_bins = cache.get_or_compute(
            reference["code_hash"],
            qid,
            lambda i=inst: bins_used(ref_module, i),
        )
        items.append(
            Counterexample.from_bin_counts(
                instance_id=qid,
                candidate_hash=h_eoh["code_hash"],
                reference_hash=reference["code_hash"],
                candidate_bins_used=cand_bins,
                reference_bins_used=ref_bins,
            )
        )
    return CounterexampleSet(items=items)


def _summarize_pool(pool: CounterexampleSet) -> dict:
    gaps = [c.gap for c in pool]
    wins = sum(1 for g in gaps if g > 0)
    losses = sum(1 for g in gaps if g < 0)
    ties = sum(1 for g in gaps if g == 0)
    hist = dict(sorted(Counter(gaps).items()))
    return {
        "n": len(gaps),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "min_gap": min(gaps),
        "max_gap": max(gaps),
        "mean_gap": statistics.fmean(gaps),
        "median_gap": statistics.median(gaps),
        "std_gap": statistics.pstdev(gaps),
        "histogram": {str(k): v for k, v in hist.items()},
    }


def _print_stats(stats: dict) -> None:
    print(f"Pool size: {stats['n']}")
    print(
        f"wins={stats['wins']}  losses={stats['losses']}  "
        f"ties={stats['ties']}"
    )
    print(
        f"gap min={stats['min_gap']}  max={stats['max_gap']}  "
        f"mean={stats['mean_gap']:.3f}  "
        f"median={stats['median_gap']}  std={stats['std_gap']:.3f}"
    )
    print("Histogram (gap -> count):")
    for k, v in stats["histogram"].items():
        print(f"  {k:>4}: {v}")


def _assert_pool_healthy(stats: dict) -> None:
    if stats["ties"] == stats["n"]:
        raise RuntimeError(
            "Pool is degenerate: all 30 gaps are zero. "
            "Candidate and reference are indistinguishable on train_select."
        )
    if stats["wins"] < 10:
        raise RuntimeError(
            f"Pool is unexpectedly reference-dominated: only "
            f"{stats['wins']} wins out of {stats['n']}. "
            "This contradicts the stored objectives (h_eoh=0.01207 < "
            "reference=0.01308). Investigate before proceeding."
        )


def main() -> int:
    split = load_split(SPLIT_NAME)
    if len(split["instances"]) != 30:
        raise RuntimeError(
            f"Expected 30 instances in {SPLIT_NAME}, got "
            f"{len(split['instances'])}"
        )

    cache = ScoreCache()
    pool = _compute_pool(split, cache)
    cache.save()

    stats = _summarize_pool(pool)
    _print_stats(stats)
    _assert_pool_healthy(stats)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    POOL_PATH.write_text(pool.to_json(), encoding="utf-8")
    STATS_PATH.write_text(
        json.dumps(stats, indent=2, sort_keys=True), encoding="utf-8"
    )
    print()
    print(f"Wrote {POOL_PATH.relative_to(REPO_ROOT).as_posix()}")
    print(f"Wrote {STATS_PATH.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
