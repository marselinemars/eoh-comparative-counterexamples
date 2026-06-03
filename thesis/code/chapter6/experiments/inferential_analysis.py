"""
thesis/code/chapter6/experiments/inferential_analysis.py

Four post-hoc inferential analyses on the chapter-6 primary batch.
Closes the uncertainty-quantification gap on the realigned
selection x structure interaction claim before validation launches.

Analyses:
  G. Bootstrap CIs on matched-pair statistics + Cliff's d, plus
     cross-strategy interaction CIs.
  H. Catastrophe rate (delta_step < -50, sensitivity at -100):
     per-cell rate; matched-pair 2x2 tabulation; rescue / induce
     rates with cross-strategy bootstrap CIs.
  I. Per-instance matched-pair Delta breakdown across the 30
     train_step instances; concentration ratio (top-5 share).
  J. Matched-pair Delta_gate replication of G + per-pair
     Pearson correlation between Delta_step and Delta_gate.

Bootstrap method: percentile (10,000 resamples). Seed locked to
MASTER_SEED_VERIFICATION = 20_260_501 so the analysis is
reproducible.

Updates in-place:
  thesis/results/chapter6_primary_batch_gemini/_verification_analysis.json
    -> adds keys analysis_G_bootstrap_cis, analysis_H_catastrophe_rate,
       analysis_I_per_instance, analysis_J_gate_generalization
  thesis/results/chapter6_primary_batch_gemini/_verification_analysis.md
    -> appends Analyses G, H, I, J (in that order) after Analysis F

Run:
  python -m thesis.code.chapter6.experiments.inferential_analysis
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[4]
RES = REPO / "thesis" / "results" / "chapter6_primary_batch_gemini"
PLOTS = RES / "_plots"
JSON_OUT = RES / "_verification_analysis.json"
MD_OUT = RES / "_verification_analysis.md"

STRATEGIES = ("stratified_representative", "worst_plus_best")
N_BOOT = 10_000
MASTER_SEED_VERIFICATION = 20_260_501
CATASTROPHE_THRESHOLD = -50.0
CATASTROPHE_THRESHOLD_SENSITIVITY = -100.0

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_records_by_strategy() -> Dict[str, Dict[Tuple[int, int], dict]]:
    """strategy -> {(set, seed) -> {l1_record, l2_record}}.
    Loads per-instance bin vectors from the on-disk records."""
    out: Dict[str, Dict[Tuple[int, int], dict]] = {s: {} for s in STRATEGIES}
    for strat in STRATEGIES:
        per_coord: Dict[Tuple[int, int], Dict[str, dict]] = {}
        for level_label in ("L1", "L2"):
            for p in sorted(RES.glob(f"{strat}@{level_label}_set*_seed*.json")):
                d = json.loads(p.read_text(encoding="utf-8"))
                if (d.get("sanitization") or {}).get("status") != "ok":
                    continue
                key = (d["set_index"], d["seed_index"])
                per_coord.setdefault(key, {})[level_label] = d
        for k, pair in per_coord.items():
            if "L1" in pair and "L2" in pair:
                out[strat][k] = pair
    return out


def _load_paired_records() -> Dict[str, list]:
    """Reads the two _paired_records.json files (built earlier)."""
    return {
        s: json.loads((PLOTS / s / "_paired_records.json").read_text(encoding="utf-8"))
        for s in STRATEGIES
    }


# ---------------------------------------------------------------------------
# Bootstrap helpers
# ---------------------------------------------------------------------------


def _percentile_ci(samples: np.ndarray, alpha: float = 0.05) -> Tuple[float, float]:
    lo = float(np.percentile(samples, 100 * alpha / 2))
    hi = float(np.percentile(samples, 100 * (1 - alpha / 2)))
    return lo, hi


def _ci_excludes_zero(lo: float, hi: float) -> bool:
    return (lo > 0 and hi > 0) or (lo < 0 and hi < 0)


def _paired_bootstrap_diffs(diffs: np.ndarray, rng: np.random.Generator,
                            n_boot: int = N_BOOT) -> np.ndarray:
    """Resample the diffs vector with replacement n_boot times.
    Returns (n_boot, n) matrix; per-row statistics are taken outside."""
    n = len(diffs)
    idx = rng.integers(0, n, size=(n_boot, n))
    return diffs[idx]


def _bootstrap_stat(diffs: np.ndarray, stat_fn, rng: np.random.Generator,
                    n_boot: int = N_BOOT) -> Tuple[float, Tuple[float, float]]:
    """Returns (point estimate, percentile 95% CI)."""
    point = float(stat_fn(diffs))
    samples = stat_fn(_paired_bootstrap_diffs(diffs, rng, n_boot), axis=1)
    return point, _percentile_ci(samples)


def _cliffs_delta(xs: np.ndarray, ys: np.ndarray) -> float:
    if len(xs) == 0 or len(ys) == 0:
        return 0.0
    diff = xs[:, None] - ys[None, :]
    g = int((diff > 0).sum())
    l = int((diff < 0).sum())
    return (g - l) / (len(xs) * len(ys))


def _bootstrap_cliffs(xs: np.ndarray, ys: np.ndarray,
                      rng: np.random.Generator) -> Tuple[float, Tuple[float, float]]:
    point = _cliffs_delta(xs, ys)
    samples = np.empty(N_BOOT)
    nx, ny = len(xs), len(ys)
    for b in range(N_BOOT):
        bx = xs[rng.integers(0, nx, size=nx)]
        by = ys[rng.integers(0, ny, size=ny)]
        samples[b] = _cliffs_delta(bx, by)
    return point, _percentile_ci(samples)


# ---------------------------------------------------------------------------
# Analysis G — bootstrap CIs and interaction test
# ---------------------------------------------------------------------------


def analysis_g(paired: Dict[str, list], records_by_strat: Dict, rng: np.random.Generator) -> Dict:
    out: Dict = {
        "method": "percentile bootstrap, 10,000 resamples; paired bootstrap "
                  "for matched-pair stats; unpaired bootstrap (per-cell "
                  "resampling) for Cliff's delta",
        "n_boot": N_BOOT,
        "seed": MASTER_SEED_VERIFICATION,
        "per_strategy": {},
        "interaction": {},
    }

    medians_full: Dict[str, np.ndarray] = {}
    means_full: Dict[str, np.ndarray] = {}

    for strat in STRATEGIES:
        pairs = paired[strat]
        diffs_all = np.array([p["diff"] for p in pairs], dtype=float)
        diffs_diff = np.array(
            [p["diff"] for p in pairs if p["l1_hash"] != p["l2_hash"]],
            dtype=float,
        )
        l1_scores = np.array([p["l1_delta_step"] for p in pairs], dtype=float)
        l2_scores = np.array([p["l2_delta_step"] for p in pairs], dtype=float)

        med_full_pt, med_full_ci = _bootstrap_stat(
            diffs_all, lambda x, axis=None: np.median(x, axis=axis), rng,
        )
        mean_full_pt, mean_full_ci = _bootstrap_stat(
            diffs_all, lambda x, axis=None: np.mean(x, axis=axis), rng,
        )
        med_diff_pt, med_diff_ci = _bootstrap_stat(
            diffs_diff, lambda x, axis=None: np.median(x, axis=axis), rng,
        )
        mean_diff_pt, mean_diff_ci = _bootstrap_stat(
            diffs_diff, lambda x, axis=None: np.mean(x, axis=axis), rng,
        )
        cliffs_pt, cliffs_ci = _bootstrap_cliffs(l2_scores, l1_scores, rng)

        # Save sample arrays for the interaction step
        medians_full[strat] = np.median(
            _paired_bootstrap_diffs(diffs_all, rng), axis=1
        )
        means_full[strat] = np.mean(
            _paired_bootstrap_diffs(diffs_all, rng), axis=1
        )

        out["per_strategy"][strat] = {
            "n_full": len(diffs_all),
            "n_diff_hash": len(diffs_diff),
            "matched_pair_median_full": {"point": med_full_pt, "ci": med_full_ci,
                                         "ci_excludes_zero": _ci_excludes_zero(*med_full_ci)},
            "matched_pair_mean_full":   {"point": mean_full_pt, "ci": mean_full_ci,
                                         "ci_excludes_zero": _ci_excludes_zero(*mean_full_ci)},
            "matched_pair_median_diffhash": {"point": med_diff_pt, "ci": med_diff_ci,
                                             "ci_excludes_zero": _ci_excludes_zero(*med_diff_ci)},
            "matched_pair_mean_diffhash":   {"point": mean_diff_pt, "ci": mean_diff_ci,
                                             "ci_excludes_zero": _ci_excludes_zero(*mean_diff_ci)},
            "cliffs_delta_l2_vs_l1": {"point": cliffs_pt, "ci": cliffs_ci,
                                      "ci_excludes_zero": _ci_excludes_zero(*cliffs_ci)},
        }

    # Interaction CIs
    diff_med_samples = medians_full["stratified_representative"] - medians_full["worst_plus_best"]
    diff_mean_samples = means_full["stratified_representative"] - means_full["worst_plus_best"]
    diff_med_ci = _percentile_ci(diff_med_samples)
    diff_mean_ci = _percentile_ci(diff_mean_samples)

    # Cliff's-delta interaction: bootstrap each strategy independently
    strat_pairs_l1 = np.array([p["l1_delta_step"] for p in paired["stratified_representative"]], dtype=float)
    strat_pairs_l2 = np.array([p["l2_delta_step"] for p in paired["stratified_representative"]], dtype=float)
    wpb_pairs_l1 = np.array([p["l1_delta_step"] for p in paired["worst_plus_best"]], dtype=float)
    wpb_pairs_l2 = np.array([p["l2_delta_step"] for p in paired["worst_plus_best"]], dtype=float)

    cliffs_diff_samples = np.empty(N_BOOT)
    for b in range(N_BOOT):
        s_l2 = strat_pairs_l2[rng.integers(0, len(strat_pairs_l2), size=len(strat_pairs_l2))]
        s_l1 = strat_pairs_l1[rng.integers(0, len(strat_pairs_l1), size=len(strat_pairs_l1))]
        w_l2 = wpb_pairs_l2[rng.integers(0, len(wpb_pairs_l2), size=len(wpb_pairs_l2))]
        w_l1 = wpb_pairs_l1[rng.integers(0, len(wpb_pairs_l1), size=len(wpb_pairs_l1))]
        cliffs_diff_samples[b] = _cliffs_delta(s_l2, s_l1) - _cliffs_delta(w_l2, w_l1)
    cliffs_diff_pt = (
        _cliffs_delta(strat_pairs_l2, strat_pairs_l1)
        - _cliffs_delta(wpb_pairs_l2, wpb_pairs_l1)
    )
    cliffs_diff_ci = _percentile_ci(cliffs_diff_samples)

    out["interaction"] = {
        "median_diff_strat_minus_wpb": {
            "point": float(np.median(np.array([p["diff"] for p in paired["stratified_representative"]]))) -
                     float(np.median(np.array([p["diff"] for p in paired["worst_plus_best"]]))),
            "ci": diff_med_ci,
            "ci_excludes_zero": _ci_excludes_zero(*diff_med_ci),
        },
        "mean_diff_strat_minus_wpb": {
            "point": float(np.mean(np.array([p["diff"] for p in paired["stratified_representative"]]))) -
                     float(np.mean(np.array([p["diff"] for p in paired["worst_plus_best"]]))),
            "ci": diff_mean_ci,
            "ci_excludes_zero": _ci_excludes_zero(*diff_mean_ci),
        },
        "cliffs_delta_diff_strat_minus_wpb": {
            "point": cliffs_diff_pt,
            "ci": cliffs_diff_ci,
            "ci_excludes_zero": _ci_excludes_zero(*cliffs_diff_ci),
        },
    }
    return out


# ---------------------------------------------------------------------------
# Analysis H — catastrophe rate
# ---------------------------------------------------------------------------


def _catastrophe_tabulation(paired_strat: list, threshold: float) -> Dict:
    classes = {"L1_cat_L2_cat": 0, "L1_cat_L2_safe": 0,
               "L1_safe_L2_cat": 0, "L1_safe_L2_safe": 0}
    flags = []  # (l1_cat_bool, l2_cat_bool) per pair
    for p in paired_strat:
        l1c = p["l1_delta_step"] < threshold
        l2c = p["l2_delta_step"] < threshold
        flags.append((l1c, l2c))
        if l1c and l2c:
            classes["L1_cat_L2_cat"] += 1
        elif l1c and not l2c:
            classes["L1_cat_L2_safe"] += 1
        elif not l1c and l2c:
            classes["L1_safe_L2_cat"] += 1
        else:
            classes["L1_safe_L2_safe"] += 1
    total_l1_cat = classes["L1_cat_L2_cat"] + classes["L1_cat_L2_safe"]
    total_l1_safe = classes["L1_safe_L2_cat"] + classes["L1_safe_L2_safe"]
    rescue = (classes["L1_cat_L2_safe"] / total_l1_cat) if total_l1_cat else None
    induce = (classes["L1_safe_L2_cat"] / total_l1_safe) if total_l1_safe else None
    return {"classes": classes, "rescue_rate": rescue,
            "induce_rate": induce, "flags": flags}


def analysis_h(paired: Dict[str, list], records_by_strat: Dict,
               rng: np.random.Generator) -> Dict:
    out: Dict = {
        "threshold_primary": CATASTROPHE_THRESHOLD,
        "threshold_sensitivity": CATASTROPHE_THRESHOLD_SENSITIVITY,
        "per_cell_rate": {},
        "per_strategy_matched_pairs": {},
        "interaction_bootstrap": {},
        "sensitivity": {},
    }

    # Per-cell rates
    for strat in STRATEGIES:
        for level_label in ("L1", "L2"):
            scores = []
            for p in RES.glob(f"{strat}@{level_label}_set*_seed*.json"):
                d = json.loads(p.read_text(encoding="utf-8"))
                if (d.get("sanitization") or {}).get("status") != "ok":
                    continue
                scores.append(d["scoring"]["delta_step"])
            cell = f"{strat}@{level_label}"
            n_cat = sum(1 for s in scores if s < CATASTROPHE_THRESHOLD)
            n_cat_100 = sum(1 for s in scores if s < CATASTROPHE_THRESHOLD_SENSITIVITY)
            out["per_cell_rate"][cell] = {
                "n": len(scores),
                "n_catastrophes_t50": n_cat,
                "rate_t50": n_cat / len(scores) if scores else None,
                "n_catastrophes_t100": n_cat_100,
                "rate_t100": n_cat_100 / len(scores) if scores else None,
            }

    # Matched-pair tabulation per strategy
    for strat in STRATEGIES:
        out["per_strategy_matched_pairs"][strat] = _catastrophe_tabulation(
            paired[strat], CATASTROPHE_THRESHOLD,
        )
    for strat in STRATEGIES:
        out["sensitivity"][strat] = _catastrophe_tabulation(
            paired[strat], CATASTROPHE_THRESHOLD_SENSITIVITY,
        )

    # Cross-strategy bootstrap on rescue / induce rate differences
    def _resample_rate(flags: list, kind: str, rng) -> float:
        # flags: list of (l1c, l2c)
        idx = rng.integers(0, len(flags), size=len(flags))
        sub = [flags[i] for i in idx]
        l1cat = sum(1 for (a, _) in sub if a)
        l1safe = sum(1 for (a, _) in sub if not a)
        l1cat_l2safe = sum(1 for (a, b) in sub if a and not b)
        l1safe_l2cat = sum(1 for (a, b) in sub if not a and b)
        if kind == "rescue":
            return l1cat_l2safe / l1cat if l1cat else float("nan")
        else:
            return l1safe_l2cat / l1safe if l1safe else float("nan")

    for kind in ("rescue", "induce"):
        diffs = np.empty(N_BOOT)
        nan_count = 0
        for b in range(N_BOOT):
            r_strat = _resample_rate(out["per_strategy_matched_pairs"]
                                     ["stratified_representative"]["flags"], kind, rng)
            r_wpb = _resample_rate(out["per_strategy_matched_pairs"]
                                   ["worst_plus_best"]["flags"], kind, rng)
            if math.isnan(r_strat) or math.isnan(r_wpb):
                nan_count += 1
                diffs[b] = np.nan
            else:
                diffs[b] = r_strat - r_wpb
        valid = diffs[~np.isnan(diffs)]
        if len(valid) > 0:
            ci = _percentile_ci(valid)
            point_strat = out["per_strategy_matched_pairs"]["stratified_representative"][f"{kind}_rate"]
            point_wpb = out["per_strategy_matched_pairs"]["worst_plus_best"][f"{kind}_rate"]
            point_diff = (
                point_strat - point_wpb
                if (point_strat is not None and point_wpb is not None)
                else None
            )
            out["interaction_bootstrap"][f"{kind}_rate_diff_strat_minus_wpb"] = {
                "point": point_diff,
                "ci": ci,
                "ci_excludes_zero": _ci_excludes_zero(*ci),
                "n_resamples_with_undefined_rate": nan_count,
            }
        else:
            out["interaction_bootstrap"][f"{kind}_rate_diff_strat_minus_wpb"] = {
                "point": None, "ci": None, "ci_excludes_zero": False,
                "n_resamples_with_undefined_rate": nan_count,
            }

    # Strip the heavy "flags" before serializing
    for strat in STRATEGIES:
        out["per_strategy_matched_pairs"][strat].pop("flags", None)
        out["sensitivity"][strat].pop("flags", None)

    # Sensitivity verdict
    pat_primary_strat_minus_wpb_rescue = (
        (out["per_strategy_matched_pairs"]["stratified_representative"]["rescue_rate"] or 0)
        - (out["per_strategy_matched_pairs"]["worst_plus_best"]["rescue_rate"] or 0)
    )
    pat_primary_strat_minus_wpb_induce = (
        (out["per_strategy_matched_pairs"]["stratified_representative"]["induce_rate"] or 0)
        - (out["per_strategy_matched_pairs"]["worst_plus_best"]["induce_rate"] or 0)
    )
    pat_sens_strat_minus_wpb_rescue = (
        (out["sensitivity"]["stratified_representative"]["rescue_rate"] or 0)
        - (out["sensitivity"]["worst_plus_best"]["rescue_rate"] or 0)
    )
    pat_sens_strat_minus_wpb_induce = (
        (out["sensitivity"]["stratified_representative"]["induce_rate"] or 0)
        - (out["sensitivity"]["worst_plus_best"]["induce_rate"] or 0)
    )
    out["sensitivity_verdict"] = {
        "rescue_sign_matches": (
            (pat_primary_strat_minus_wpb_rescue >= 0) ==
            (pat_sens_strat_minus_wpb_rescue >= 0)
        ),
        "induce_sign_matches": (
            (pat_primary_strat_minus_wpb_induce >= 0) ==
            (pat_sens_strat_minus_wpb_induce >= 0)
        ),
        "primary_rescue_diff": pat_primary_strat_minus_wpb_rescue,
        "sensitivity_rescue_diff": pat_sens_strat_minus_wpb_rescue,
        "primary_induce_diff": pat_primary_strat_minus_wpb_induce,
        "sensitivity_induce_diff": pat_sens_strat_minus_wpb_induce,
    }
    return out


# ---------------------------------------------------------------------------
# Analysis I — per-instance Delta within matched pairs
# ---------------------------------------------------------------------------


def analysis_i(records_by_strat: Dict, paired: Dict[str, list]) -> Dict:
    out: Dict = {"per_strategy": {}}
    for strat in STRATEGIES:
        # Build 60x30 matrices: per_pair_per_instance_delta = bins_l1[i] - bins_l2[i]
        coords = sorted(records_by_strat[strat].keys())
        rows: List[np.ndarray] = []
        for c in coords:
            l1 = records_by_strat[strat][c]["L1"]["scoring"]["per_instance_bins_proposal_train_step"]
            l2 = records_by_strat[strat][c]["L2"]["scoring"]["per_instance_bins_proposal_train_step"]
            rows.append(np.array(l1, dtype=float) - np.array(l2, dtype=float))
        mat = np.array(rows)  # shape (n_pairs, 30)

        per_inst_mean = mat.mean(axis=0)  # length 30
        per_inst_frac_pos = (mat > 0).mean(axis=0)

        # Concentration: positive instance contributions only
        pos_only = np.where(per_inst_mean > 0, per_inst_mean, 0.0)
        total_pos = pos_only.sum()
        sorted_idx_desc = np.argsort(-per_inst_mean)
        top5_idx = sorted_idx_desc[:5].tolist()
        top5_share = (
            float(per_inst_mean[sorted_idx_desc[:5]].clip(min=0).sum() / total_pos)
            if total_pos > 0 else None
        )

        # Different-hash subset
        diff_hash_pairs = [
            (c, p) for c, p in zip(coords, paired[strat]) if p["l1_hash"] != p["l2_hash"]
        ]
        if diff_hash_pairs:
            rows_dh: List[np.ndarray] = []
            for c, _ in diff_hash_pairs:
                l1 = records_by_strat[strat][c]["L1"]["scoring"]["per_instance_bins_proposal_train_step"]
                l2 = records_by_strat[strat][c]["L2"]["scoring"]["per_instance_bins_proposal_train_step"]
                rows_dh.append(np.array(l1, dtype=float) - np.array(l2, dtype=float))
            mat_dh = np.array(rows_dh)
            per_inst_mean_dh = mat_dh.mean(axis=0)
        else:
            per_inst_mean_dh = np.full(30, np.nan)

        out["per_strategy"][strat] = {
            "n_pairs_full": len(rows),
            "n_pairs_diff_hash": len(diff_hash_pairs),
            "per_instance_mean_full": per_inst_mean.tolist(),
            "per_instance_frac_positive_full": per_inst_frac_pos.tolist(),
            "per_instance_mean_diff_hash": per_inst_mean_dh.tolist(),
            "concentration": {
                "top5_instance_indices_desc": top5_idx,
                "top5_share_of_total_positive": top5_share,
                "proportional_top5_share": 5 / 30,
                "concentration_driven": (
                    top5_share is not None and top5_share > 0.5
                ),
            },
        }
    return out


# ---------------------------------------------------------------------------
# Analysis J — gate-set replication of G + gap correlation
# ---------------------------------------------------------------------------


def _pair_gate_diffs(records_by_strat: Dict, strat: str) -> np.ndarray:
    coords = sorted(records_by_strat[strat].keys())
    out = []
    for c in coords:
        l1g = records_by_strat[strat][c]["L1"]["scoring"]["delta_gate"]
        l2g = records_by_strat[strat][c]["L2"]["scoring"]["delta_gate"]
        out.append(l2g - l1g)
    return np.array(out, dtype=float)


def analysis_j(paired: Dict[str, list], records_by_strat: Dict,
               rng: np.random.Generator) -> Dict:
    out: Dict = {
        "method": "percentile bootstrap, 10,000 resamples; paired bootstrap",
        "n_boot": N_BOOT,
        "per_strategy": {},
        "interaction": {},
    }

    medians_gate: Dict[str, np.ndarray] = {}
    means_gate: Dict[str, np.ndarray] = {}

    for strat in STRATEGIES:
        coords = sorted(records_by_strat[strat].keys())
        gate_diffs_full = _pair_gate_diffs(records_by_strat, strat)
        # Same coord list as paired[strat]; build diff-hash subset
        diff_hash_mask = np.array(
            [p["l1_hash"] != p["l2_hash"] for p in paired[strat]], dtype=bool
        )
        gate_diffs_diff = gate_diffs_full[diff_hash_mask]

        med_full_pt, med_full_ci = _bootstrap_stat(
            gate_diffs_full, lambda x, axis=None: np.median(x, axis=axis), rng,
        )
        mean_full_pt, mean_full_ci = _bootstrap_stat(
            gate_diffs_full, lambda x, axis=None: np.mean(x, axis=axis), rng,
        )
        med_diff_pt, med_diff_ci = _bootstrap_stat(
            gate_diffs_diff, lambda x, axis=None: np.median(x, axis=axis), rng,
        )
        mean_diff_pt, mean_diff_ci = _bootstrap_stat(
            gate_diffs_diff, lambda x, axis=None: np.mean(x, axis=axis), rng,
        )

        # Save sample arrays for the interaction step
        medians_gate[strat] = np.median(
            _paired_bootstrap_diffs(gate_diffs_full, rng), axis=1
        )
        means_gate[strat] = np.mean(
            _paired_bootstrap_diffs(gate_diffs_full, rng), axis=1
        )

        # Pearson correlation: per-pair Δ_step vs Δ_gate diff
        step_diffs = np.array([p["diff"] for p in paired[strat]], dtype=float)
        if len(step_diffs) >= 2:
            cm = np.corrcoef(step_diffs, gate_diffs_full)
            corr = float(cm[0, 1]) if cm.shape == (2, 2) else float("nan")
        else:
            corr = float("nan")

        out["per_strategy"][strat] = {
            "n_full": int(len(gate_diffs_full)),
            "n_diff_hash": int(len(gate_diffs_diff)),
            "matched_pair_median_gate_full":
                {"point": med_full_pt, "ci": med_full_ci,
                 "ci_excludes_zero": _ci_excludes_zero(*med_full_ci)},
            "matched_pair_mean_gate_full":
                {"point": mean_full_pt, "ci": mean_full_ci,
                 "ci_excludes_zero": _ci_excludes_zero(*mean_full_ci)},
            "matched_pair_median_gate_diffhash":
                {"point": med_diff_pt, "ci": med_diff_ci,
                 "ci_excludes_zero": _ci_excludes_zero(*med_diff_ci)},
            "matched_pair_mean_gate_diffhash":
                {"point": mean_diff_pt, "ci": mean_diff_ci,
                 "ci_excludes_zero": _ci_excludes_zero(*mean_diff_ci)},
            "pearson_corr_step_vs_gate_perpair": corr,
        }

    diff_med_samples = (
        medians_gate["stratified_representative"]
        - medians_gate["worst_plus_best"]
    )
    diff_mean_samples = (
        means_gate["stratified_representative"]
        - means_gate["worst_plus_best"]
    )
    diff_med_ci = _percentile_ci(diff_med_samples)
    diff_mean_ci = _percentile_ci(diff_mean_samples)
    out["interaction"] = {
        "median_gate_diff_strat_minus_wpb": {
            "point": float(np.median(_pair_gate_diffs(records_by_strat,
                                                      "stratified_representative")))
                     - float(np.median(_pair_gate_diffs(records_by_strat,
                                                        "worst_plus_best"))),
            "ci": diff_med_ci,
            "ci_excludes_zero": _ci_excludes_zero(*diff_med_ci),
        },
        "mean_gate_diff_strat_minus_wpb": {
            "point": float(np.mean(_pair_gate_diffs(records_by_strat,
                                                    "stratified_representative")))
                     - float(np.mean(_pair_gate_diffs(records_by_strat,
                                                      "worst_plus_best"))),
            "ci": diff_mean_ci,
            "ci_excludes_zero": _ci_excludes_zero(*diff_mean_ci),
        },
    }
    return out


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _ci_str(d: Dict) -> str:
    pt = d["point"]
    lo, hi = d["ci"]
    excl = "excludes 0" if d["ci_excludes_zero"] else "includes 0"
    return f"{pt:+.3f}  [{lo:+.3f}, {hi:+.3f}]  ({excl})"


def md_g(g: Dict) -> List[str]:
    out = ["", "## Analysis G — Bootstrap CIs and the interaction test", ""]
    out.append(f"Method: {g['method']}.  n_boot = {g['n_boot']}.  seed = {g['seed']}.")
    out.append("")
    out.append("### Per-strategy matched-pair statistics with 95% CIs\n")
    out.append("| strategy | metric | point [95% CI] | excludes 0? |")
    out.append("|---|---|---|---|")
    for strat in STRATEGIES:
        s = g["per_strategy"][strat]
        for label, key in [
            ("median Δ (full)",            "matched_pair_median_full"),
            ("mean Δ (full)",              "matched_pair_mean_full"),
            ("median Δ (diff-hash)",       "matched_pair_median_diffhash"),
            ("mean Δ (diff-hash)",         "matched_pair_mean_diffhash"),
            ("Cliff's δ (cell-level)",     "cliffs_delta_l2_vs_l1"),
        ]:
            d = s[key]
            lo, hi = d["ci"]
            excl = "yes" if d["ci_excludes_zero"] else "no"
            out.append(f"| `{strat}` | {label} | "
                       f"{d['point']:+.4f} [{lo:+.4f}, {hi:+.4f}] | {excl} |")
    out.append("")
    out.append("### Cross-strategy interaction CIs\n")
    out.append("| statistic (stratified − wpb) | point [95% CI] | excludes 0? |")
    out.append("|---|---|---|")
    for label, key in [
        ("matched-pair median Δ", "median_diff_strat_minus_wpb"),
        ("matched-pair mean Δ",   "mean_diff_strat_minus_wpb"),
        ("Cliff's δ",             "cliffs_delta_diff_strat_minus_wpb"),
    ]:
        d = g["interaction"][key]
        lo, hi = d["ci"]
        excl = "yes" if d["ci_excludes_zero"] else "no"
        out.append(f"| {label} | {d['point']:+.4f} [{lo:+.4f}, {hi:+.4f}] | {excl} |")
    out.append("")
    out.append("### One-line readouts\n")
    for strat in STRATEGIES:
        s = g["per_strategy"][strat]
        d = s["matched_pair_median_full"]
        excl = "excludes zero" if d["ci_excludes_zero"] else "includes zero"
        out.append(
            f"- `{strat}`: matched-pair median Δ = {d['point']:+.3f} "
            f"[{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}]; CI {excl}."
        )
    inter_med = g["interaction"]["median_diff_strat_minus_wpb"]
    excl_inter = "excludes zero" if inter_med["ci_excludes_zero"] else "includes zero"
    out.append(
        f"- Interaction (stratified − wpb) on matched-pair median Δ: "
        f"{inter_med['point']:+.3f} "
        f"[{inter_med['ci'][0]:+.3f}, {inter_med['ci'][1]:+.3f}]; CI {excl_inter}."
    )
    out.append("")
    return out


def md_h(h: Dict) -> List[str]:
    out = ["", "## Analysis H — Catastrophe rate", ""]
    out.append(f"Catastrophe = `delta_step < {h['threshold_primary']}`. "
               f"Sensitivity threshold: `{h['threshold_sensitivity']}`.\n")
    out.append("### Per-cell catastrophe rate\n")
    out.append("| cell | n | n_cat (t=−50) | rate (t=−50) | n_cat (t=−100) | rate (t=−100) |")
    out.append("|---|---:|---:|---:|---:|---:|")
    for cell, c in h["per_cell_rate"].items():
        out.append(
            f"| `{cell}` | {c['n']} | {c['n_catastrophes_t50']} | "
            f"{(c['rate_t50'] or 0)*100:.1f}% | {c['n_catastrophes_t100']} | "
            f"{(c['rate_t100'] or 0)*100:.1f}% |"
        )
    out.append("")
    out.append("### Matched-pair 2×2 (threshold = −50)\n")
    out.append("| strategy | L1_cat∧L2_cat | L1_cat∧L2_safe (rescue) | "
               "L1_safe∧L2_cat (induce) | L1_safe∧L2_safe | rescue_rate | induce_rate |")
    out.append("|---|---:|---:|---:|---:|---:|---:|")
    for strat in STRATEGIES:
        m = h["per_strategy_matched_pairs"][strat]
        c = m["classes"]
        out.append(
            f"| `{strat}` | {c['L1_cat_L2_cat']} | {c['L1_cat_L2_safe']} | "
            f"{c['L1_safe_L2_cat']} | {c['L1_safe_L2_safe']} | "
            f"{(m['rescue_rate'] or 0)*100:.1f}% | "
            f"{(m['induce_rate'] or 0)*100:.1f}% |"
        )
    out.append("")
    out.append("### Cross-strategy bootstrap on rate differences\n")
    out.append("| statistic (stratified − wpb) | point | 95% CI | excludes 0? |")
    out.append("|---|---:|---|---|")
    for label, key in [("rescue_rate diff", "rescue_rate_diff_strat_minus_wpb"),
                       ("induce_rate diff", "induce_rate_diff_strat_minus_wpb")]:
        d = h["interaction_bootstrap"].get(key) or {}
        if d.get("ci") is None:
            out.append(f"| {label} | n/a | n/a | n/a |")
            continue
        lo, hi = d["ci"]
        excl = "yes" if d["ci_excludes_zero"] else "no"
        pt = d["point"]
        pt_str = f"{pt:+.4f}" if pt is not None else "n/a"
        out.append(f"| {label} | {pt_str} | [{lo:+.4f}, {hi:+.4f}] | {excl} |")
    out.append("")
    out.append("### Sensitivity check at threshold = −100\n")
    out.append("| strategy | L1_cat∧L2_cat | L1_cat∧L2_safe | L1_safe∧L2_cat | "
               "L1_safe∧L2_safe | rescue | induce |")
    out.append("|---|---:|---:|---:|---:|---:|---:|")
    for strat in STRATEGIES:
        m = h["sensitivity"][strat]
        c = m["classes"]
        rr = "n/a" if m["rescue_rate"] is None else f"{m['rescue_rate']*100:.1f}%"
        ir = "n/a" if m["induce_rate"] is None else f"{m['induce_rate']*100:.1f}%"
        out.append(
            f"| `{strat}` | {c['L1_cat_L2_cat']} | {c['L1_cat_L2_safe']} | "
            f"{c['L1_safe_L2_cat']} | {c['L1_safe_L2_safe']} | {rr} | {ir} |"
        )
    out.append("")
    sv = h["sensitivity_verdict"]
    out.append(
        f"Sensitivity verdict: rescue-direction sign matches "
        f"({sv['primary_rescue_diff']:+.4f} → {sv['sensitivity_rescue_diff']:+.4f}): "
        f"**{sv['rescue_sign_matches']}**.  "
        f"Induce-direction sign matches "
        f"({sv['primary_induce_diff']:+.4f} → {sv['sensitivity_induce_diff']:+.4f}): "
        f"**{sv['induce_sign_matches']}**."
    )
    out.append("")
    return out


def md_i(i: Dict) -> List[str]:
    out = ["", "## Analysis I — Per-instance Δ within matched pairs", ""]
    out.append("Per-instance Δ_i = `bins_l1[i] − bins_l2[i]` (positive = L2 used "
               "fewer bins on instance i).")
    out.append("")
    for strat in STRATEGIES:
        s = i["per_strategy"][strat]
        out.append(f"### `{strat}` — n_pairs = {s['n_pairs_full']} "
                   f"(diff-hash subset n = {s['n_pairs_diff_hash']})\n")
        # Build sortable rows
        per_mean = s["per_instance_mean_full"]
        per_frac = s["per_instance_frac_positive_full"]
        per_mean_dh = s["per_instance_mean_diff_hash"]
        rows = sorted(range(30), key=lambda k: -per_mean[k])
        out.append("| inst_idx | mean Δ (full) | frac L2 better (full) | mean Δ (diff-hash) |")
        out.append("|---:|---:|---:|---:|")
        for k in rows:
            mdh = per_mean_dh[k]
            mdh_s = f"{mdh:+.2f}" if not (isinstance(mdh, float) and math.isnan(mdh)) else "n/a"
            out.append(
                f"| {k} | {per_mean[k]:+.2f} | {per_frac[k]*100:.1f}% | {mdh_s} |"
            )
        c = s["concentration"]
        share = c["top5_share_of_total_positive"]
        share_s = f"{share*100:.1f}%" if share is not None else "n/a"
        out.append("")
        out.append(
            f"Concentration: top-5 instance share of total positive Δ = "
            f"**{share_s}** "
            f"(proportional baseline = {c['proportional_top5_share']*100:.1f}%; "
            f"concentration-driven? **{c['concentration_driven']}**).  "
            f"Top-5 instance indices: {c['top5_instance_indices_desc']}."
        )
        out.append("")
    return out


def md_j(j: Dict) -> List[str]:
    out = ["", "## Analysis J — Gate-set generalization of the matched-pair Δ", ""]
    out.append(f"Method: {j['method']}.  n_boot = {j['n_boot']}.")
    out.append("")
    out.append("### Per-strategy Δ_gate matched-pair statistics with 95% CIs\n")
    out.append("| strategy | metric | point [95% CI] | excludes 0? |")
    out.append("|---|---|---|---|")
    for strat in STRATEGIES:
        s = j["per_strategy"][strat]
        for label, key in [
            ("median Δ_gate (full)",      "matched_pair_median_gate_full"),
            ("mean Δ_gate (full)",        "matched_pair_mean_gate_full"),
            ("median Δ_gate (diff-hash)", "matched_pair_median_gate_diffhash"),
            ("mean Δ_gate (diff-hash)",   "matched_pair_mean_gate_diffhash"),
        ]:
            d = s[key]
            lo, hi = d["ci"]
            excl = "yes" if d["ci_excludes_zero"] else "no"
            out.append(f"| `{strat}` | {label} | "
                       f"{d['point']:+.4f} [{lo:+.4f}, {hi:+.4f}] | {excl} |")
    out.append("")
    out.append("### Cross-strategy interaction CIs (Δ_gate)\n")
    out.append("| statistic (stratified − wpb) | point [95% CI] | excludes 0? |")
    out.append("|---|---|---|")
    for label, key in [
        ("matched-pair median Δ_gate", "median_gate_diff_strat_minus_wpb"),
        ("matched-pair mean Δ_gate",   "mean_gate_diff_strat_minus_wpb"),
    ]:
        d = j["interaction"][key]
        lo, hi = d["ci"]
        excl = "yes" if d["ci_excludes_zero"] else "no"
        out.append(f"| {label} | {d['point']:+.4f} [{lo:+.4f}, {hi:+.4f}] | {excl} |")
    out.append("")
    out.append("### Per-pair Pearson correlation between Δ_step and Δ_gate\n")
    out.append("| strategy | Pearson r |")
    out.append("|---|---:|")
    for strat in STRATEGIES:
        c = j["per_strategy"][strat]["pearson_corr_step_vs_gate_perpair"]
        out.append(f"| `{strat}` | {c:+.3f} |")
    out.append("")
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    rng = np.random.default_rng(MASTER_SEED_VERIFICATION)
    print(f"Loading records (seed={MASTER_SEED_VERIFICATION}, n_boot={N_BOOT})...")
    records_by_strat = _load_records_by_strategy()
    paired = _load_paired_records()
    for s in STRATEGIES:
        print(f"  {s}: {len(records_by_strat[s])} matched pairs, "
              f"{len(paired[s])} in _paired_records.json")

    print("Analysis G (bootstrap CIs)...")
    g = analysis_g(paired, records_by_strat, rng)
    print("Analysis H (catastrophe rate)...")
    h = analysis_h(paired, records_by_strat, rng)
    print("Analysis I (per-instance)...")
    i = analysis_i(records_by_strat, paired)
    print("Analysis J (gate generalization)...")
    j = analysis_j(paired, records_by_strat, rng)

    verif = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    verif["analysis_G_bootstrap_cis"] = g
    verif["analysis_H_catastrophe_rate"] = h
    verif["analysis_I_per_instance"] = i
    verif["analysis_J_gate_generalization"] = j
    JSON_OUT.write_text(json.dumps(verif, indent=2), encoding="utf-8")

    md_existing = MD_OUT.read_text(encoding="utf-8").rstrip()
    new_sections = md_g(g) + md_h(h) + md_i(i) + md_j(j)
    MD_OUT.write_text(md_existing + "\n" + "\n".join(new_sections) + "\n",
                      encoding="utf-8")

    print()
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {JSON_OUT}")
    print()
    print("Headlines:")
    for strat in STRATEGIES:
        d = g["per_strategy"][strat]["matched_pair_median_full"]
        print(f"  G [{strat}] median dpoint={d['point']:+.3f} "
              f"CI=[{d['ci'][0]:+.3f},{d['ci'][1]:+.3f}] "
              f"excl0={d['ci_excludes_zero']}")
    inter = g["interaction"]["median_diff_strat_minus_wpb"]
    print(f"  G interaction (median d, strat-wpb): {inter['point']:+.3f} "
          f"CI=[{inter['ci'][0]:+.3f},{inter['ci'][1]:+.3f}] "
          f"excl0={inter['ci_excludes_zero']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
