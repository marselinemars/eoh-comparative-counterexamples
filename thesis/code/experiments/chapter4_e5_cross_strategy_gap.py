"""
thesis/code/experiments/chapter4_e5_cross_strategy_gap.py

Compute the n=6 cross-strategy gap CI for chapter-7 L2 k=1
(stratified_representative minus worst_only_at_k1) on
Δ_step_cumulative(5), paired by trajectory index. Bootstrap
95% CI on the mean of paired differences. 10,000 resamples,
seed 20260523.

Required input artifacts (commit d2f3ea9):
    thesis/artifacts/chapter7_stratified_L2_k1_trajectories_n6.json
    thesis/artifacts/chapter7_worst_only_L2_k1_trajectories_n6.json

Output:
    thesis/artifacts/chapter4_e5_cross_strategy_gap_n6.json

The n=3 baseline figures (+5.13 bins, CI [+4.17, +6.93]) are
taken from Table 4.13 in thesis/writing/thesis_main.md
(line 1090).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
STRAT_PATH = REPO / "thesis" / "artifacts" / "chapter7_stratified_L2_k1_trajectories_n6.json"
WO1_PATH = REPO / "thesis" / "artifacts" / "chapter7_worst_only_L2_k1_trajectories_n6.json"
OUT_PATH = REPO / "thesis" / "artifacts" / "chapter4_e5_cross_strategy_gap_n6.json"

N_BOOT = 10_000
BOOTSTRAP_SEED = 20_260_523

N3_BASELINE_MEAN = 5.13
N3_BASELINE_CI = [4.17, 6.93]


def main() -> None:
    strat = json.loads(STRAT_PATH.read_text(encoding="utf-8"))
    wo1 = json.loads(WO1_PATH.read_text(encoding="utf-8"))

    strat_finals = strat["n6_finals"]
    wo1_finals = wo1["n6_finals"]

    if len(strat_finals) != 6 or len(wo1_finals) != 6:
        raise RuntimeError(
            f"Expected 6 trajectory finals per cell; got "
            f"strat={len(strat_finals)}, wo1={len(wo1_finals)}"
        )

    # Paired differences by trajectory_index.
    diffs = np.asarray(
        [float(strat_finals[i]) - float(wo1_finals[i]) for i in range(6)]
    )
    point = float(diffs.mean())

    # Bootstrap on paired diffs.
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    idx = rng.integers(0, len(diffs), size=(N_BOOT, len(diffs)))
    samples = diffs[idx].mean(axis=1)
    ci_lo = float(np.percentile(samples, 2.5))
    ci_hi = float(np.percentile(samples, 97.5))

    ci_excludes_zero = (ci_lo > 0) or (ci_hi < 0)
    direction_preserved = (point > 0) == (N3_BASELINE_MEAN > 0)

    out = {
        "n3_baseline": {
            "mean_paired_diff": N3_BASELINE_MEAN,
            "ci_lower": N3_BASELINE_CI[0],
            "ci_upper": N3_BASELINE_CI[1],
            "source": "thesis_main.md Table 4.13 row at line 1090",
        },
        "n6_extension": {
            "mean_paired_diff": round(point, 4),
            "ci_lower": round(ci_lo, 4),
            "ci_upper": round(ci_hi, 4),
            "n_pairs": 6,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_resamples": N_BOOT,
            "strat_L2_k1_trajectory_values_n6": [
                round(v, 4) for v in strat_finals
            ],
            "wo1_L2_k1_trajectory_values_n6": [
                round(v, 4) for v in wo1_finals
            ],
            "paired_differences": [round(v, 4) for v in diffs.tolist()],
        },
        "ci_excludes_zero_at_n6": ci_excludes_zero,
        "direction_preserved_n3_to_n6": direction_preserved,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"n=3 baseline: +{N3_BASELINE_MEAN} bins "
          f"CI [+{N3_BASELINE_CI[0]}, +{N3_BASELINE_CI[1]}]")
    print(f"n=6 extension: {point:+.3f} bins "
          f"CI [{ci_lo:+.3f}, {ci_hi:+.3f}]")
    print(f"CI excludes zero at n=6: {ci_excludes_zero}")
    print(f"Direction preserved n=3 to n=6: {direction_preserved}")
    print(f"Wrote {OUT_PATH.relative_to(REPO).as_posix()}")


if __name__ == "__main__":
    main()
