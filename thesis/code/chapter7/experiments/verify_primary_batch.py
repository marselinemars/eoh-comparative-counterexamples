"""thesis/code/chapter7/experiments/verify_primary_batch.py

Chapter 7 primary-batch verification analysis (§18.5). Mirrors
the chapter-6 verification structure: produces a top-level
``chapter7_summary.json`` and subsidiary artifacts for the
distributional summary (A), cardinality curves (B),
cross-`k` matched-pair statistics (C), monotonicity tests (D),
ch6 anchor cross-time-window reproduction (E), train_select
shown-vs-unshown decomposition (F), and sanitization failure
taxonomy (G).

Reads from
``thesis/results/chapter7_primary_batch_gemini/``
(per-proposal JSONs) and writes to ``thesis/artifacts/``.

Usage::

    python -m thesis.code.chapter7.experiments.verify_primary_batch
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
RESULTS_DIR = REPO_ROOT / "thesis" / "results" / "chapter7_primary_batch_gemini"
ARTIFACTS_DIR = REPO_ROOT / "thesis" / "artifacts"
SUMMARY_PATH = ARTIFACTS_DIR / "chapter7_summary.json"
ANCHOR_PATH = ARTIFACTS_DIR / "chapter7_anchor_reproduction.json"
SHOWN_VS_UNSHOWN_PATH = ARTIFACTS_DIR / "chapter7_shown_vs_unshown.json"
FAILURE_TAXONOMY_PATH = ARTIFACTS_DIR / "chapter7_failure_taxonomy.json"

# §6.4 catastrophe thresholds — match ch6 §6.3.2 Table 2.
CATASTROPHE_THRESHOLD_STRICT = -50.0
CATASTROPHE_THRESHOLD_LENIENT = -10.0

# §7.1 bootstrap parameters.
BOOTSTRAP_N_RESAMPLES = 5000
BOOTSTRAP_SEED = 20_260_505

# ch6 published anchor CIs (for §7.3 / §18.9 reproduction comparison).
CH6_INTERACTION_CI_DELTA_STEP = (8.94, 155.04)
CH6_INTERACTION_CI_DELTA_GATE = (8.53, 158.66)
CH6_CATASTROPHE_RATES_AT_50 = {
    ("stratified_representative", 1): 0.183,
    ("stratified_representative", 2): 0.083,
    ("worst_plus_best", 1): 0.100,
    ("worst_plus_best", 2): 0.200,
}

# §4.1 14-cell matrix.
CELLS = [
    {"cell_id": "CH7-01", "strategy": "stratified_representative", "level": 1, "k": 1},
    {"cell_id": "CH7-02", "strategy": "stratified_representative", "level": 1, "k": 2},
    {"cell_id": "CH7-03", "strategy": "stratified_representative", "level": 1, "k": 4},
    {"cell_id": "CH7-04", "strategy": "stratified_representative", "level": 1, "k": 8},
    {"cell_id": "CH7-05", "strategy": "worst_only_at_k1", "level": 1, "k": 1},
    {"cell_id": "CH7-06", "strategy": "worst_plus_best", "level": 1, "k": 2},
    {"cell_id": "CH7-07", "strategy": "worst_plus_best", "level": 1, "k": 4},
    {"cell_id": "CH7-08", "strategy": "worst_plus_best", "level": 1, "k": 8},
    {"cell_id": "CH7-09", "strategy": "stratified_representative", "level": 2, "k": 1},
    {"cell_id": "CH7-10", "strategy": "stratified_representative", "level": 2, "k": 2},
    {"cell_id": "CH7-11", "strategy": "stratified_representative", "level": 2, "k": 4},
    {"cell_id": "CH7-12", "strategy": "worst_only_at_k1", "level": 2, "k": 1},
    {"cell_id": "CH7-13", "strategy": "worst_plus_best", "level": 2, "k": 2},
    {"cell_id": "CH7-14", "strategy": "worst_plus_best", "level": 2, "k": 4},
]

ANCHOR_CELL_IDS = {"CH7-03", "CH7-07", "CH7-11", "CH7-14"}


# --- record loading ----------------------------------------------------


def _load_all_records(results_dir: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in sorted(results_dir.glob("CH7-*.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"  [skip] {path.name}: {exc}", file=sys.stderr)
            continue
        if d.get("chapter") != "chapter7":
            continue
        d["_path"] = str(path)
        out.append(d)
    return out


def _records_by_cell(records: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        cid = r.get("cell_id")
        if cid:
            out[cid].append(r)
    return out


# --- distributional helpers -------------------------------------------


def _delta_step(rec: Dict[str, Any]) -> Optional[float]:
    s = rec.get("scoring") or {}
    if not isinstance(s, dict):
        return None
    val = s.get("delta_step")
    return float(val) if isinstance(val, (int, float)) else None


def _delta_gate(rec: Dict[str, Any]) -> Optional[float]:
    s = rec.get("scoring") or {}
    if not isinstance(s, dict):
        return None
    val = s.get("delta_gate")
    return float(val) if isinstance(val, (int, float)) else None


def _is_argmax_distinct(rec: Dict[str, Any]) -> Optional[bool]:
    """argmax-equivalent = NOT argmax-distinct. ch5 records this in
    scoring as 'argmax_distinct' or similar; we look for both names."""
    s = rec.get("scoring") or {}
    if not isinstance(s, dict):
        return None
    if "argmax_distinct" in s:
        return bool(s["argmax_distinct"])
    if "argmax_equivalent" in s:
        return not bool(s["argmax_equivalent"])
    return None


def _is_ok(rec: Dict[str, Any]) -> bool:
    san = rec.get("sanitization") or {}
    return isinstance(san, dict) and san.get("status") == "ok"


def _coordinate(rec: Dict[str, Any]) -> Tuple[int, int]:
    return (int(rec.get("set_index", -1)), int(rec.get("seed_index", -1)))


def _summary_stats(values: Sequence[float]) -> Dict[str, Any]:
    if not values:
        return {
            "n": 0, "mean": None, "median": None, "p10": None,
            "p25": None, "p50": None, "p75": None, "p90": None,
            "std": None, "min": None, "max": None, "iqr": None,
        }
    arr = np.asarray(values, dtype=float)
    return {
        "n": int(arr.size),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p25": float(np.percentile(arr, 25)),
        "p50": float(np.median(arr)),
        "p75": float(np.percentile(arr, 75)),
        "p90": float(np.percentile(arr, 90)),
        "std": float(np.std(arr, ddof=0)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "iqr": float(np.percentile(arr, 75) - np.percentile(arr, 25)),
    }


def _bootstrap_ci_mean(
    values: Sequence[float],
    *,
    n_resamples: int = BOOTSTRAP_N_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    alpha: float = 0.05,
) -> Optional[Tuple[float, float]]:
    if not values:
        return None
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    n = arr.size
    means = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        means[i] = float(np.mean(arr[idx]))
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return (lo, hi)


def _spearman_rank_corr(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Spearman rank correlation. Returns 0.0 on degenerate input."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    rx = _ranks(x)
    ry = _ranks(y)
    return float(np.corrcoef(rx, ry)[0, 1]) if np.std(rx) > 0 and np.std(ry) > 0 else 0.0


def _ranks(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    order = arr.argsort()
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(arr.size)
    # Average ranks for ties.
    unique_vals, inverse = np.unique(arr, return_inverse=True)
    if unique_vals.size != arr.size:
        for u in range(unique_vals.size):
            mask = inverse == u
            ranks[mask] = ranks[mask].mean()
    return ranks


# --- A: per-cell distributional summaries -----------------------------


def _per_cell_summary(records_by_cell: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for cell in CELLS:
        cid = cell["cell_id"]
        recs = records_by_cell.get(cid, [])
        ok_recs = [r for r in recs if _is_ok(r)]
        delta_steps = [v for v in (_delta_step(r) for r in ok_recs) if v is not None]
        delta_gates = [v for v in (_delta_gate(r) for r in ok_recs) if v is not None]
        argmax_distincts = [
            v for v in (_is_argmax_distinct(r) for r in ok_recs) if v is not None
        ]
        sanitize_ok = sum(1 for r in recs if _is_ok(r))
        cat_strict = sum(1 for v in delta_steps if v < CATASTROPHE_THRESHOLD_STRICT)
        cat_lenient = sum(1 for v in delta_steps if v < CATASTROPHE_THRESHOLD_LENIENT)
        out[cid] = {
            "cell": cell,
            "n_records": len(recs),
            "n_sanitize_ok": sanitize_ok,
            "sanitize_rate": sanitize_ok / len(recs) if recs else None,
            "delta_step_stats": _summary_stats(delta_steps),
            "delta_gate_stats": _summary_stats(delta_gates),
            "delta_step_bootstrap_ci_mean": _bootstrap_ci_mean(delta_steps),
            "delta_gate_bootstrap_ci_mean": _bootstrap_ci_mean(delta_gates),
            "n_argmax_distinct_recorded": len(argmax_distincts),
            "argmax_equivalent_rate": (
                (len(argmax_distincts) - sum(argmax_distincts)) / len(argmax_distincts)
                if argmax_distincts else None
            ),
            "catastrophe_count_at_-50": cat_strict,
            "catastrophe_rate_at_-50": cat_strict / len(delta_steps) if delta_steps else None,
            "catastrophe_count_at_-10": cat_lenient,
            "catastrophe_rate_at_-10": cat_lenient / len(delta_steps) if delta_steps else None,
        }
    return out


# --- B: cardinality-curve tables --------------------------------------


def _cardinality_curves(per_cell: Dict[str, Any]) -> Dict[str, Any]:
    grouped: Dict[Tuple[str, int], List[Dict[str, Any]]] = defaultdict(list)
    for cid, summary in per_cell.items():
        cell = summary["cell"]
        # worst_only_at_k1 is the k=1 boundary for worst_plus_best
        # per design §3.8; we group it into the worst_plus_best curve.
        strategy_label = (
            "worst_plus_best"
            if cell["strategy"] == "worst_only_at_k1"
            else cell["strategy"]
        )
        key = (strategy_label, cell["level"])
        grouped[key].append(summary)
    out: Dict[str, Any] = {}
    for (strategy_label, level), summaries in sorted(grouped.items()):
        summaries_sorted = sorted(summaries, key=lambda s: s["cell"]["k"])
        rows = []
        for s in summaries_sorted:
            rows.append({
                "cell_id": s["cell"]["cell_id"],
                "strategy": s["cell"]["strategy"],
                "k": s["cell"]["k"],
                "delta_step_mean": s["delta_step_stats"]["mean"],
                "delta_step_median": s["delta_step_stats"]["median"],
                "delta_step_ci_mean": s["delta_step_bootstrap_ci_mean"],
                "delta_gate_mean": s["delta_gate_stats"]["mean"],
                "delta_gate_ci_mean": s["delta_gate_bootstrap_ci_mean"],
                "catastrophe_rate_at_-50": s["catastrophe_rate_at_-50"],
                "n_records": s["n_records"],
                "sanitize_rate": s["sanitize_rate"],
            })
        out[f"{strategy_label}@L{level}"] = {
            "strategy": strategy_label,
            "level": level,
            "rows": rows,
        }
    return out


# --- C: cross-k matched-pair statistics --------------------------------


def _matched_pair_diffs(
    recs_a: List[Dict[str, Any]],
    recs_b: List[Dict[str, Any]],
    metric: Callable[[Dict[str, Any]], Optional[float]],
) -> List[float]:
    by_coord_a = {_coordinate(r): r for r in recs_a if _is_ok(r)}
    by_coord_b = {_coordinate(r): r for r in recs_b if _is_ok(r)}
    common = sorted(set(by_coord_a) & set(by_coord_b))
    diffs: List[float] = []
    for coord in common:
        va = metric(by_coord_a[coord])
        vb = metric(by_coord_b[coord])
        if va is not None and vb is not None:
            diffs.append(va - vb)
    return diffs


def _cross_k_matched_pairs(
    records_by_cell: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    contrasts = {
        ("stratified_representative", 1): [(2, 1), (4, 2), (8, 4)],
        ("worst_plus_best",           1): [(2, 1), (4, 2), (8, 4)],
        ("stratified_representative", 2): [(2, 1), (4, 2)],
        ("worst_plus_best",           2): [(2, 1), (4, 2)],
    }

    cells_by_skl: Dict[Tuple[str, int, int], str] = {}
    for cell in CELLS:
        if cell["strategy"] == "worst_only_at_k1":
            cells_by_skl[("worst_plus_best", cell["level"], 1)] = cell["cell_id"]
        cells_by_skl[(cell["strategy"], cell["level"], cell["k"])] = cell["cell_id"]

    for (strategy, level), pairs in contrasts.items():
        for k_a, k_b in pairs:
            cid_a = cells_by_skl.get((strategy, level, k_a))
            cid_b = cells_by_skl.get((strategy, level, k_b))
            if not cid_a or not cid_b:
                continue
            recs_a = records_by_cell.get(cid_a, [])
            recs_b = records_by_cell.get(cid_b, [])
            for metric_name, metric_fn in (
                ("delta_step", _delta_step),
                ("delta_gate", _delta_gate),
            ):
                diffs = _matched_pair_diffs(recs_a, recs_b, metric_fn)
                ci = _bootstrap_ci_mean(diffs)
                key = f"{strategy}@L{level}__k{k_a}_minus_k{k_b}__{metric_name}"
                out[key] = {
                    "strategy": strategy,
                    "level": level,
                    "k_a": k_a,
                    "k_b": k_b,
                    "metric": metric_name,
                    "cell_a": cid_a,
                    "cell_b": cid_b,
                    "n_pairs": len(diffs),
                    "mean_diff": float(np.mean(diffs)) if diffs else None,
                    "ci_95": ci,
                    "ci_excludes_zero": (
                        ci is not None and (ci[0] > 0 or ci[1] < 0)
                    ),
                }
    return out


# --- D: monotonicity tests --------------------------------------------


def _monotonicity_tests(per_cell: Dict[str, Any]) -> Dict[str, Any]:
    """Bootstrap CI on Spearman correlation between k (ordinal) and
    cell-mean delta_step / delta_gate, per (strategy, level)."""
    out: Dict[str, Any] = {}
    grouped: Dict[Tuple[str, int], List[Dict[str, Any]]] = defaultdict(list)
    for cid, summary in per_cell.items():
        cell = summary["cell"]
        strategy_label = (
            "worst_plus_best"
            if cell["strategy"] == "worst_only_at_k1"
            else cell["strategy"]
        )
        key = (strategy_label, cell["level"])
        grouped[key].append(summary)

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    for (strategy_label, level), summaries in sorted(grouped.items()):
        if len(summaries) < 2:
            continue
        for metric_name, stat_field in (
            ("delta_step", "delta_step_stats"),
            ("delta_gate", "delta_gate_stats"),
        ):
            ks = []
            means = []
            for s in summaries:
                m = s[stat_field]["mean"]
                if m is not None:
                    ks.append(s["cell"]["k"])
                    means.append(m)
            if len(ks) < 2:
                continue
            point_rho = _spearman_rank_corr(ks, means)
            # Bootstrap by resampling the (k, mean) pairs with replacement.
            rhos = np.empty(BOOTSTRAP_N_RESAMPLES, dtype=float)
            n = len(ks)
            for i in range(BOOTSTRAP_N_RESAMPLES):
                idx = rng.integers(0, n, size=n)
                rhos[i] = _spearman_rank_corr(
                    [ks[j] for j in idx], [means[j] for j in idx]
                )
            lo = float(np.percentile(rhos, 2.5))
            hi = float(np.percentile(rhos, 97.5))
            out[f"{strategy_label}@L{level}__{metric_name}"] = {
                "strategy": strategy_label,
                "level": level,
                "metric": metric_name,
                "k_values": ks,
                "cell_means": means,
                "spearman_rho": point_rho,
                "spearman_ci_95": [lo, hi],
                "ci_excludes_zero": lo > 0 or hi < 0,
                "direction": (
                    "monotone-positive" if lo > 0
                    else "monotone-negative" if hi < 0
                    else "not-distinguishable-from-zero"
                ),
            }
    return out


# --- E: ch6 anchor cross-time-window reproduction ---------------------


def _interaction_ci(
    records_by_cell: Dict[str, List[Dict[str, Any]]],
    metric_fn: Callable[[Dict[str, Any]], Optional[float]],
) -> Optional[Tuple[float, float]]:
    """ch6 cross-strategy interaction at k=4, the anchor 2x2.

    Statistic: (mean(strat L2) − mean(strat L1)) −
              (mean(wpb   L2) − mean(wpb   L1))
    Bootstrap CI by per-cell resampling.
    """
    cells = {
        ("strat", 1): records_by_cell.get("CH7-03", []),
        ("strat", 2): records_by_cell.get("CH7-11", []),
        ("wpb",   1): records_by_cell.get("CH7-07", []),
        ("wpb",   2): records_by_cell.get("CH7-14", []),
    }
    arrays = {}
    for key, recs in cells.items():
        ok_recs = [r for r in recs if _is_ok(r)]
        vals = [v for v in (metric_fn(r) for r in ok_recs) if v is not None]
        if not vals:
            return None
        arrays[key] = np.asarray(vals, dtype=float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    stats = np.empty(BOOTSTRAP_N_RESAMPLES, dtype=float)
    for i in range(BOOTSTRAP_N_RESAMPLES):
        means = {}
        for key, arr in arrays.items():
            idx = rng.integers(0, arr.size, size=arr.size)
            means[key] = float(np.mean(arr[idx]))
        stats[i] = (
            (means[("strat", 2)] - means[("strat", 1)])
            - (means[("wpb", 2)] - means[("wpb", 1)])
        )
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def _verdict_for_ci(ch7_ci: Optional[Tuple[float, float]],
                    ch6_ci: Tuple[float, float]) -> str:
    if ch7_ci is None:
        return "not_computable"
    a_lo, a_hi = ch7_ci
    b_lo, b_hi = ch6_ci
    if a_lo > 0 and b_lo > 0:
        same_dir = True
    elif a_hi < 0 and b_hi < 0:
        same_dir = True
    else:
        same_dir = False
    overlap = (a_lo <= b_hi) and (b_lo <= a_hi)
    if same_dir and overlap:
        return "reproduces"
    if same_dir and not overlap:
        return "partial_reproduction"
    return "does_not_reproduce"


def _anchor_reproduction(
    records_by_cell: Dict[str, List[Dict[str, Any]]],
    per_cell: Dict[str, Any],
) -> Dict[str, Any]:
    ch7_step = _interaction_ci(records_by_cell, _delta_step)
    ch7_gate = _interaction_ci(records_by_cell, _delta_gate)

    cat_rates: Dict[str, Dict[str, Any]] = {}
    cat_anchor_map = {
        ("stratified_representative", 1): "CH7-03",
        ("stratified_representative", 2): "CH7-11",
        ("worst_plus_best",           1): "CH7-07",
        ("worst_plus_best",           2): "CH7-14",
    }
    for (strategy, level), cid in cat_anchor_map.items():
        ch7_rate = per_cell.get(cid, {}).get("catastrophe_rate_at_-50")
        ch6_rate = CH6_CATASTROPHE_RATES_AT_50.get((strategy, level))
        cat_rates[f"{strategy}@L{level}"] = {
            "ch7_anchor_cell": cid,
            "ch7_catastrophe_rate_at_-50": ch7_rate,
            "ch6_catastrophe_rate_at_-50": ch6_rate,
            "delta_pp": (
                None if (ch7_rate is None or ch6_rate is None)
                else (ch7_rate - ch6_rate) * 100
            ),
        }

    return {
        "ch7_interaction_ci_delta_step": ch7_step,
        "ch6_interaction_ci_delta_step": list(CH6_INTERACTION_CI_DELTA_STEP),
        "verdict_delta_step": (
            _verdict_for_ci(ch7_step, CH6_INTERACTION_CI_DELTA_STEP)
            if ch7_step else "not_computable"
        ),
        "ch7_interaction_ci_delta_gate": ch7_gate,
        "ch6_interaction_ci_delta_gate": list(CH6_INTERACTION_CI_DELTA_GATE),
        "verdict_delta_gate": (
            _verdict_for_ci(ch7_gate, CH6_INTERACTION_CI_DELTA_GATE)
            if ch7_gate else "not_computable"
        ),
        "catastrophe_rate_comparison": cat_rates,
        "criterion": "§7.3: reproduces iff same-direction AND CI-overlap",
    }


# --- F: train_select shown-vs-unshown decomposition --------------------
#
# Per design-doc §6.8 and ch6 decisions-log 2026-05-01. This requires
# scoring proposals against ALL train_select instances (decomposed by
# whether each instance was in the prompt). Producing this here would
# require additional score-cache fills; we stub the structure now and
# fill the actual numbers in a follow-on pass once the score cache is
# warmed (the chapter6_smart_resume cache-fill script is the precedent).


def _shown_vs_unshown_stub(records_by_cell: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "_status": "stub",
        "_note": (
            "Per design-doc §6.8 and ch6 decisions-log 2026-05-01 entry, "
            "this analysis decomposes per-cell scoring into 'instances "
            "shown in prompt' vs 'instances in train_select but not "
            "shown'. It requires score-cache fills for every "
            "(proposal, train_select_instance) pair across all 14 "
            "cells, a non-trivial workload. The structure below is "
            "populated with cell-level n_shown/n_unshown counts; the "
            "Δ_select_shown / Δ_select_unshown means and bootstrap CIs "
            "are deferred to a follow-on cache-fill pass that mirrors "
            "ch6's chapter6_smart_resume.py shown-vs-unshown_cache_fill "
            "stage."
        ),
    }
    cells = []
    for cell in CELLS:
        cid = cell["cell_id"]
        recs = records_by_cell.get(cid, [])
        n_shown = cell["k"]  # k counterexamples shown
        n_unshown = 30 - cell["k"]  # train_select pool size = 30
        cells.append({
            "cell_id": cid,
            "strategy": cell["strategy"],
            "level": cell["level"],
            "k": cell["k"],
            "n_shown_per_proposal": n_shown,
            "n_unshown_per_proposal": n_unshown,
            "n_proposals": len(recs),
        })
    out["cells"] = cells
    return out


# --- G: sanitization failure taxonomy ---------------------------------


def _failure_taxonomy(records_by_cell: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    grand_total = defaultdict(int)
    for cell in CELLS:
        cid = cell["cell_id"]
        counts: Dict[str, int] = defaultdict(int)
        api_errors = 0
        for r in records_by_cell.get(cid, []):
            san = (r.get("sanitization") or {})
            status = san.get("status") if isinstance(san, dict) else None
            if status:
                counts[status] += 1
                grand_total[status] += 1
            if r.get("api_error"):
                api_errors += 1
                grand_total["api_error"] += 1
        out[cid] = {
            "cell": cell,
            "status_counts": dict(counts),
            "n_api_errors": api_errors,
            "n_total": len(records_by_cell.get(cid, [])),
        }
    out["_grand_totals"] = dict(grand_total)
    return out


# --- main --------------------------------------------------------------


def main() -> int:
    if not RESULTS_DIR.exists():
        print(f"results dir not found: {RESULTS_DIR}", file=sys.stderr)
        return 1
    records = _load_all_records(RESULTS_DIR)
    print(f"Loaded {len(records)} records from {RESULTS_DIR}", file=sys.stderr)
    by_cell = _records_by_cell(records)

    per_cell = _per_cell_summary(by_cell)
    curves = _cardinality_curves(per_cell)
    cross_k = _cross_k_matched_pairs(by_cell)
    monotonicity = _monotonicity_tests(per_cell)
    anchor = _anchor_reproduction(by_cell, per_cell)
    shown_vs_unshown = _shown_vs_unshown_stub(by_cell)
    failures = _failure_taxonomy(by_cell)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    ANCHOR_PATH.write_text(
        json.dumps(anchor, indent=2, sort_keys=True), encoding="utf-8"
    )
    # Don't overwrite a complete shown-vs-unshown artifact with the stub.
    # The full analysis is produced by experiments/shown_vs_unshown.py
    # and writes ``"_status": "complete"``.
    if SHOWN_VS_UNSHOWN_PATH.exists():
        try:
            existing = json.loads(SHOWN_VS_UNSHOWN_PATH.read_text(encoding="utf-8"))
            if existing.get("_status") == "complete":
                shown_vs_unshown = existing  # preserve real analysis
            else:
                SHOWN_VS_UNSHOWN_PATH.write_text(
                    json.dumps(shown_vs_unshown, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
        except Exception:
            SHOWN_VS_UNSHOWN_PATH.write_text(
                json.dumps(shown_vs_unshown, indent=2, sort_keys=True),
                encoding="utf-8",
            )
    else:
        SHOWN_VS_UNSHOWN_PATH.write_text(
            json.dumps(shown_vs_unshown, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    FAILURE_TAXONOMY_PATH.write_text(
        json.dumps(failures, indent=2, sort_keys=True), encoding="utf-8"
    )

    summary = {
        "schema_version": 1,
        "chapter": "chapter7",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_records_loaded": len(records),
        "subsidiary_artifacts": {
            "anchor_reproduction": str(
                ANCHOR_PATH.relative_to(REPO_ROOT).as_posix()
            ),
            "shown_vs_unshown": str(
                SHOWN_VS_UNSHOWN_PATH.relative_to(REPO_ROOT).as_posix()
            ),
            "failure_taxonomy": str(
                FAILURE_TAXONOMY_PATH.relative_to(REPO_ROOT).as_posix()
            ),
        },
        "per_cell_summary": per_cell,
        "cardinality_curves": curves,
        "cross_k_matched_pairs": cross_k,
        "monotonicity_tests": monotonicity,
        "anchor_reproduction_verdicts": {
            "delta_step": anchor.get("verdict_delta_step"),
            "delta_gate": anchor.get("verdict_delta_gate"),
        },
        "headline_directions": {
            key: m.get("direction")
            for key, m in monotonicity.items()
        },
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    summary_hash = hashlib.sha256(
        SUMMARY_PATH.read_bytes()
    ).hexdigest()[:12]
    print(f"Wrote {SUMMARY_PATH} (sha256[:12] = {summary_hash})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
