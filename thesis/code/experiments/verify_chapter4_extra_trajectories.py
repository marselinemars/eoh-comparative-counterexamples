"""
thesis/code/experiments/verify_chapter4_extra_trajectories.py

W-E5 post-batch analysis. Consolidates the original n=3 validation
trajectories with the new n=3 extension trajectories (trajectory
indices 3, 4, 5) into n=6 per-cell statistics, and classifies the
n=3 → n=6 direction agreement per design doc
`chapter4_extra_trajectories_design.md` §6:

  α agree         — both load-bearing pairs preserve their n=3 ordering
  β one inverts   — one of two pairs inverts at n=6
  γ both invert   — both pairs invert
  δ ambiguous     — CIs overlap; ordering cannot be defended

Cumulative Δ_step at step 5 per trajectory:
  = sum of `delta_step_local` over accepted steps
  (rejected steps leave the incumbent unchanged → 0 contribution).

For the two ch5 cells (L1 k=4) the new trajectories were run by
`chapter4_extra_trajectories.py` with set_index 100 + traj_idx, so
new trajectories live at fake_set_index ∈ {103, 104, 105}. The
existing n=3 finals are read from
`thesis/artifacts/chapter5_summary.json::validation_batch.per_strategy.{name}.trajectory_final_deltas`.

For the two ch7 cells (L2 k=1) the new trajectories live in
`chapter7_validation_batch_gemini/chapter7_validation_{cell_id}_traj{3,4,5}_step{0..4}.json`.
The existing n=3 finals are read from
`thesis/artifacts/chapter7_validation_summary.json::per_cell[idx].delta_step_cumulative_5_per_trajectory`.

Outputs:
  thesis/artifacts/chapter5_stratified_L1_k4_trajectories_n6.json
  thesis/artifacts/chapter5_worst_plus_best_L1_k4_trajectories_n6.json
  thesis/artifacts/chapter7_stratified_L2_k1_trajectories_n6.json
  thesis/artifacts/chapter7_worst_only_L2_k1_trajectories_n6.json
  thesis/artifacts/chapter4_extra_trajectories_n6_regime.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

REPO = Path(__file__).resolve().parents[3]
CH5_VAL = REPO / "thesis" / "results" / "chapter5_validation_batch_gemini"
CH7_VAL = REPO / "thesis" / "results" / "chapter7_validation_batch_gemini"
ARTIFACTS = REPO / "thesis" / "artifacts"

N_STEPS = 5
N_BOOT = 10_000
BOOTSTRAP_SEED = 20_260_523


# -----------------------------------------------------------------------
# Cumulative-final computation per trajectory
# -----------------------------------------------------------------------


def cumulative_for_ch5_trajectory(
    strategy: str, traj_idx: int
) -> Dict[str, Any]:
    """Sum delta_step_local across accepted steps of one chapter-5
    trajectory. Returns the cumulative, plus per-step debug data."""
    cum = 0.0
    per_step: List[Dict[str, Any]] = []
    for step_idx in range(1, N_STEPS + 1):
        p = CH5_VAL / f"{strategy}_traj{traj_idx}_step{step_idx}.json"
        if not p.exists():
            return {"cumulative": None, "missing_step": step_idx, "per_step": per_step}
        d = json.loads(p.read_text(encoding="utf-8"))
        accepted = bool(d.get("accepted"))
        dsl = d.get("delta_step_local")
        if accepted and dsl is not None:
            cum += float(dsl)
        per_step.append({
            "step": step_idx,
            "accepted": accepted,
            "reason": d.get("acceptance_reason"),
            "delta_step_local": dsl,
        })
    return {"cumulative": cum, "per_step": per_step}


def cumulative_for_ch7_trajectory(
    cell_id: str, traj_idx: int
) -> Dict[str, Any]:
    cum = 0.0
    per_step: List[Dict[str, Any]] = []
    for step_idx in range(N_STEPS):
        p = CH7_VAL / f"chapter7_validation_{cell_id}_traj{traj_idx}_step{step_idx}.json"
        if not p.exists():
            return {"cumulative": None, "missing_step": step_idx, "per_step": per_step}
        d = json.loads(p.read_text(encoding="utf-8"))
        reason = d.get("acceptance_reason") or ""
        accepted = reason.startswith("accepted")
        dsl = d.get("delta_step_local")
        if accepted and dsl is not None:
            cum += float(dsl)
        per_step.append({
            "step": step_idx,
            "accepted": accepted,
            "reason": reason,
            "delta_step_local": dsl,
        })
    return {"cumulative": cum, "per_step": per_step}


# -----------------------------------------------------------------------
# Per-cell n=6 statistics
# -----------------------------------------------------------------------


def cell_stats(values_n6: List[float]) -> Dict[str, Any]:
    arr = np.asarray(values_n6, dtype=float)
    n = arr.size
    loo = [
        float(np.mean(np.delete(arr, i))) for i in range(n)
    ]
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    idx = rng.integers(0, n, size=(N_BOOT, n))
    samples = arr[idx].mean(axis=1)
    ci = [
        float(np.percentile(samples, 2.5)),
        float(np.percentile(samples, 97.5)),
    ]
    return {
        "n": int(n),
        "values": [float(v) for v in arr],
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "std": float(arr.std(ddof=1)) if n > 1 else 0.0,
        "loo_means": loo,
        "loo_range": [min(loo), max(loo)],
        "mean_ci_95": ci,
    }


# -----------------------------------------------------------------------
# Per-cell artifact
# -----------------------------------------------------------------------


def build_ch5_cell_artifact(
    label: str, strategy: str, n3_finals: List[float],
) -> Dict[str, Any]:
    new = []
    new_debug = []
    for traj_idx in [3, 4, 5]:
        info = cumulative_for_ch5_trajectory(strategy, traj_idx)
        if info["cumulative"] is None:
            raise RuntimeError(
                f"{label} traj{traj_idx} missing step {info.get('missing_step')}"
            )
        new.append(info["cumulative"])
        new_debug.append({"trajectory_index": traj_idx, **info})

    n3_stats = cell_stats(n3_finals)
    n6_stats = cell_stats(n3_finals + new)
    return {
        "cell_label": label,
        "strategy": strategy,
        "level": 1,
        "k": 4,
        "n3_finals_original": n3_finals,
        "n3_stats_original": n3_stats,
        "n3_finals_extension": new,
        "n3_extension_debug": new_debug,
        "n6_finals": n3_finals + new,
        "n6_stats": n6_stats,
    }


def build_ch7_cell_artifact(
    label: str, cell_id: str, strategy: str, k: int,
    n3_finals: List[float],
) -> Dict[str, Any]:
    new = []
    new_debug = []
    for traj_idx in [3, 4, 5]:
        info = cumulative_for_ch7_trajectory(cell_id, traj_idx)
        if info["cumulative"] is None:
            raise RuntimeError(
                f"{label} traj{traj_idx} missing step {info.get('missing_step')}"
            )
        new.append(info["cumulative"])
        new_debug.append({"trajectory_index": traj_idx, **info})

    n3_stats = cell_stats(n3_finals)
    n6_stats = cell_stats(n3_finals + new)
    return {
        "cell_label": label,
        "cell_id": cell_id,
        "strategy": strategy,
        "level": 2,
        "k": k,
        "n3_finals_original": n3_finals,
        "n3_stats_original": n3_stats,
        "n3_finals_extension": new,
        "n3_extension_debug": new_debug,
        "n6_finals": n3_finals + new,
        "n6_stats": n6_stats,
    }


# -----------------------------------------------------------------------
# Regime classification (design doc §6)
# -----------------------------------------------------------------------


def classify_pair(
    cell_a_stats: Dict[str, Any], cell_b_stats: Dict[str, Any],
) -> Dict[str, Any]:
    """Direction at n=3 and n=6 for cell_a vs cell_b.
    Direction = sign(mean_A - mean_B). Returns ambiguity flag based
    on n=6 bootstrap CIs."""
    a3 = np.mean(cell_a_stats["n3_finals_original"])
    b3 = np.mean(cell_b_stats["n3_finals_original"])
    a6 = cell_a_stats["n6_stats"]["mean"]
    b6 = cell_b_stats["n6_stats"]["mean"]
    a6_ci = cell_a_stats["n6_stats"]["mean_ci_95"]
    b6_ci = cell_b_stats["n6_stats"]["mean_ci_95"]
    dir_n3 = "a>b" if a3 > b3 else ("a<b" if a3 < b3 else "tie")
    dir_n6 = "a>b" if a6 > b6 else ("a<b" if a6 < b6 else "tie")
    # Ambiguity: if the two n=6 CIs overlap, the ordering is not
    # well-defended even at n=6.
    cis_overlap = (a6_ci[0] <= b6_ci[1]) and (b6_ci[0] <= a6_ci[1])
    return {
        "a_mean_n3": float(a3),
        "b_mean_n3": float(b3),
        "a_mean_n6": float(a6),
        "b_mean_n6": float(b6),
        "a_ci_95_n6": a6_ci,
        "b_ci_95_n6": b6_ci,
        "direction_n3": dir_n3,
        "direction_n6": dir_n6,
        "ordering_inverted": dir_n3 != dir_n6 and "tie" not in (dir_n3, dir_n6),
        "n6_cis_overlap": bool(cis_overlap),
    }


def classify_regime(
    pair_ch5: Dict[str, Any], pair_ch7: Dict[str, Any],
) -> str:
    """Per design doc §6.1-§6.4."""
    inv5 = pair_ch5["ordering_inverted"]
    inv7 = pair_ch7["ordering_inverted"]
    amb5 = pair_ch5["n6_cis_overlap"]
    amb7 = pair_ch7["n6_cis_overlap"]
    # δ if either pair's CIs span the comparison (i.e., overlap).
    if amb5 or amb7:
        if inv5 or inv7:
            return "delta_ambiguous_with_inversion"
        return "delta_ambiguous"
    if not inv5 and not inv7:
        return "alpha_agree"
    if inv5 and inv7:
        return "gamma_both_invert"
    return "beta_one_inverts"


# -----------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------


def main() -> None:
    ch5_summary = json.loads(
        (ARTIFACTS / "chapter5_summary.json").read_text(encoding="utf-8")
    )
    ch7_val_summary = json.loads(
        (ARTIFACTS / "chapter7_validation_summary.json").read_text(
            encoding="utf-8"
        )
    )

    # Pull existing n=3 finals.
    strat_l1_k4_n3 = ch5_summary["validation_batch"]["per_strategy"][
        "stratified_representative"
    ]["trajectory_final_deltas"]
    wpb_l1_k4_n3 = ch5_summary["validation_batch"]["per_strategy"][
        "worst_plus_best"
    ]["trajectory_final_deltas"]

    # Find ch7 cells by cell_id.
    def _ch7_finals(cell_id: str) -> List[float]:
        for entry in ch7_val_summary["per_cell"]:
            if entry["cell"]["cell_id"] == cell_id:
                return entry["delta_step_cumulative_5_per_trajectory"]
        raise KeyError(cell_id)

    strat_l2_k1_n3 = _ch7_finals("CH7-09")
    wo1_l2_k1_n3 = _ch7_finals("CH7-12")

    # Build per-cell artifacts.
    a_strat_l1 = build_ch5_cell_artifact(
        "stratified_representative_L1_k4",
        "stratified_representative",
        strat_l1_k4_n3,
    )
    a_wpb_l1 = build_ch5_cell_artifact(
        "worst_plus_best_L1_k4",
        "worst_plus_best",
        wpb_l1_k4_n3,
    )
    a_strat_l2 = build_ch7_cell_artifact(
        "stratified_representative_L2_k1",
        "CH7-09",
        "stratified_representative",
        1,
        strat_l2_k1_n3,
    )
    a_wo1_l2 = build_ch7_cell_artifact(
        "worst_only_at_k1_L2_k1",
        "CH7-12",
        "worst_only_at_k1",
        1,
        wo1_l2_k1_n3,
    )

    # Write per-cell artifacts.
    out_files = {
        ARTIFACTS / "chapter5_stratified_L1_k4_trajectories_n6.json": a_strat_l1,
        ARTIFACTS / "chapter5_worst_plus_best_L1_k4_trajectories_n6.json": a_wpb_l1,
        ARTIFACTS / "chapter7_stratified_L2_k1_trajectories_n6.json": a_strat_l2,
        ARTIFACTS / "chapter7_worst_only_L2_k1_trajectories_n6.json": a_wo1_l2,
    }
    for path, art in out_files.items():
        path.write_text(json.dumps(art, indent=2), encoding="utf-8")
        print(f"wrote {path.relative_to(REPO).as_posix()}")

    # Pairwise direction analysis + regime classification.
    pair_ch5 = classify_pair(a_strat_l1, a_wpb_l1)
    pair_ch7 = classify_pair(a_strat_l2, a_wo1_l2)
    regime = classify_regime(pair_ch5, pair_ch7)

    regime_artifact = {
        "design_doc": "thesis/writing/chapter4_extra_trajectories_design.md (§6 regime classification)",
        "pairs": {
            "ch5_L1_k4_stratified_vs_wpb": pair_ch5,
            "ch7_L2_k1_stratified_vs_wo1": pair_ch7,
        },
        "regime": regime,
        "regime_interpretation": {
            "alpha_agree": "Both pairs preserve their n=3 ordering at n=6 — the original finding is strengthened.",
            "beta_one_inverts": "One ordering pair inverts at n=6 — the corresponding chapter claim softens.",
            "gamma_both_invert": "Both pairs invert at n=6 — major finding shift; the n=3 rankings were unstable.",
            "delta_ambiguous": "At least one n=6 pair has overlapping CIs — ordering cannot be defended even at n=6.",
            "delta_ambiguous_with_inversion": "Same as delta plus at least one inversion.",
        }[regime],
        "bootstrap_n_resamples": N_BOOT,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }
    regime_path = ARTIFACTS / "chapter4_extra_trajectories_n6_regime.json"
    regime_path.write_text(
        json.dumps(regime_artifact, indent=2), encoding="utf-8"
    )
    print(f"wrote {regime_path.relative_to(REPO).as_posix()}")

    print()
    print("=" * 72)
    print(f"Regime: {regime}")
    print("=" * 72)
    print(
        f"  ch5 L1 k=4 pair (strat vs wpb):  "
        f"n3 dir={pair_ch5['direction_n3']} -> n6 dir={pair_ch5['direction_n6']}  "
        f"inverted={pair_ch5['ordering_inverted']}  "
        f"n6_cis_overlap={pair_ch5['n6_cis_overlap']}"
    )
    print(
        f"  ch7 L2 k=1 pair (strat vs wo1):  "
        f"n3 dir={pair_ch7['direction_n3']} -> n6 dir={pair_ch7['direction_n6']}  "
        f"inverted={pair_ch7['ordering_inverted']}  "
        f"n6_cis_overlap={pair_ch7['n6_cis_overlap']}"
    )
    print()
    print("Per-cell n=6 finals:")
    for art in [a_strat_l1, a_wpb_l1, a_strat_l2, a_wo1_l2]:
        s = art["n6_stats"]
        print(
            f"  {art['cell_label']:<40} n=6 mean={s['mean']:+.3f}  "
            f"median={s['median']:+.3f}  CI=[{s['mean_ci_95'][0]:+.3f}, "
            f"{s['mean_ci_95'][1]:+.3f}]  LOO=[{s['loo_range'][0]:+.3f}, "
            f"{s['loo_range'][1]:+.3f}]"
        )


if __name__ == "__main__":
    main()
