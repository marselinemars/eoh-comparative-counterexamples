"""thesis/code/chapter7/experiments/l2_interaction_stratified_by_k.py

Chapter 7 §7.4 cross-strategy interaction CI at L2, stratified by
``k``. Mirrors the §7.3 anchor reproduction analysis but reports
the cross-strategy difference at L2 *separately at each
``k ∈ {1, 2, 4}``* rather than pooled at the k=4 anchor.

The pair-level statistic is the within-coordinate matched-pair
difference between stratified_representative @ L2 @ k and
worst_plus_best @ L2 @ k (at k=1 worst_plus_best is replaced by
worst_only_at_k1 per the §3.8 boundary-substitution lock; this
substitution is flagged in the artifact's per-k verdict block).

Coordinate alignment (slot-aligned per the §12 patched lock,
commit f5f623):
- stratified_representative: 20 sets × 3 LLM seeds = 60 records.
  Flatten to index ``i = set_index * 3 + seed_index``.
- worst_plus_best / worst_only_at_k1: 1 set × 60 LLM seeds = 60
  records. Flatten to index ``i = seed_index``.

Cross-strategy matched pair at L2 at index ``i`` is
``Δ(strat_L2_k_i) − Δ(wpb_or_sub_L2_k_i)``. Mean across
matched pairs is the per-k cross-strategy difference; 5,000-
resample bootstrap CI of the mean gives the per-k interaction
CI.

Output:
- ``thesis/artifacts/chapter7_l2_interaction_stratified_by_k.json``
- updates ``thesis/artifacts/chapter7_summary.json`` with a
  compact ``l2_interaction_stratified_by_k`` summary block

Usage::

    python -m thesis.code.chapter7.experiments.l2_interaction_stratified_by_k
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
RESULTS_DIR = REPO_ROOT / "thesis" / "results" / "chapter7_primary_batch_gemini"
ARTIFACTS_DIR = REPO_ROOT / "thesis" / "artifacts"
OUT_PATH = ARTIFACTS_DIR / "chapter7_l2_interaction_stratified_by_k.json"
SUMMARY_PATH = ARTIFACTS_DIR / "chapter7_summary.json"
ANCHOR_PATH = ARTIFACTS_DIR / "chapter7_anchor_reproduction.json"

BOOTSTRAP_N = 5000
BOOTSTRAP_SEED = 20_260_510
CATASTROPHE_THRESHOLD = -50.0

# Per-k L2 cell mapping. At k=1, worst_only_at_k1 substitutes for
# worst_plus_best per the §3.8 boundary lock.
PER_K_L2_CELLS: Dict[int, Dict[str, str]] = {
    1: {
        "strategy_a": "stratified_representative",
        "cell_a_id": "CH7-09",
        "strategy_b": "worst_only_at_k1",
        "cell_b_id": "CH7-12",
        "boundary_substitution_active": True,
    },
    2: {
        "strategy_a": "stratified_representative",
        "cell_a_id": "CH7-10",
        "strategy_b": "worst_plus_best",
        "cell_b_id": "CH7-13",
        "boundary_substitution_active": False,
    },
    4: {
        "strategy_a": "stratified_representative",
        "cell_a_id": "CH7-11",
        "strategy_b": "worst_plus_best",
        "cell_b_id": "CH7-14",
        "boundary_substitution_active": False,
    },
}


# --- record loading ---------------------------------------------------


def _load_ok_records_for_cell(cell_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in sorted(RESULTS_DIR.glob(f"{cell_id}_set*.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        san = d.get("sanitization") or {}
        if san.get("status") != "ok":
            continue
        out.append(d)
    return out


def _flat_index_for(rec: Dict[str, Any], strategy: str) -> int:
    """Per the §12 coordinate convention. Stochastic strategies
    flatten (set_index, seed_index) → set_index*3 + seed_index;
    deterministic strategies use seed_index directly."""
    set_idx = int(rec.get("set_index", 0))
    seed_idx = int(rec.get("seed_index", 0))
    if strategy == "stratified_representative":
        return set_idx * 3 + seed_idx
    # worst_plus_best / worst_only_at_k1
    return seed_idx


def _delta_step(rec: Dict[str, Any]) -> Optional[float]:
    s = rec.get("scoring") or {}
    v = s.get("delta_step") if isinstance(s, dict) else None
    return float(v) if isinstance(v, (int, float)) else None


def _delta_gate(rec: Dict[str, Any]) -> Optional[float]:
    s = rec.get("scoring") or {}
    v = s.get("delta_gate") if isinstance(s, dict) else None
    return float(v) if isinstance(v, (int, float)) else None


# --- bootstrap helpers ------------------------------------------------


def _bootstrap_ci_mean(
    values: List[float],
    *,
    seed: int = BOOTSTRAP_SEED,
    n: int = BOOTSTRAP_N,
    alpha: float = 0.05,
) -> Optional[Tuple[float, float]]:
    if not values:
        return None
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    means = np.empty(n, dtype=float)
    size = arr.size
    for i in range(n):
        idx = rng.integers(0, size, size=size)
        means[i] = float(np.mean(arr[idx]))
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return (lo, hi)


def _bootstrap_ci_rate_diff(
    bool_a: List[bool],
    bool_b: List[bool],
    *,
    seed: int = BOOTSTRAP_SEED + 1,
    n: int = BOOTSTRAP_N,
    alpha: float = 0.05,
) -> Optional[Tuple[float, float]]:
    """Per-cell bootstrap on the rate difference (rate_a - rate_b).
    Resamples each strategy's records independently with replacement."""
    if not bool_a or not bool_b:
        return None
    rng = np.random.default_rng(seed)
    arr_a = np.asarray(bool_a, dtype=float)
    arr_b = np.asarray(bool_b, dtype=float)
    diffs = np.empty(n, dtype=float)
    for i in range(n):
        ia = rng.integers(0, arr_a.size, size=arr_a.size)
        ib = rng.integers(0, arr_b.size, size=arr_b.size)
        diffs[i] = float(np.mean(arr_a[ia]) - np.mean(arr_b[ib]))
    lo = float(np.percentile(diffs, 100 * alpha / 2))
    hi = float(np.percentile(diffs, 100 * (1 - alpha / 2)))
    return (lo, hi)


def _direction(ci: Optional[Tuple[float, float]]) -> str:
    if ci is None:
        return "n/a"
    lo, hi = ci
    if lo > 0:
        return "positive"
    if hi < 0:
        return "negative"
    return "null"


# --- per-k matched-pair compute ---------------------------------------


def _matched_pair_diffs(
    recs_a: List[Dict[str, Any]],
    strategy_a: str,
    recs_b: List[Dict[str, Any]],
    strategy_b: str,
    metric_fn,
) -> Tuple[List[float], int, int, int]:
    """Pair records by slot-aligned flat index. Return (paired_diffs,
    n_pairs, n_records_a, n_records_b)."""
    by_idx_a: Dict[int, Dict[str, Any]] = {}
    for r in recs_a:
        by_idx_a[_flat_index_for(r, strategy_a)] = r
    by_idx_b: Dict[int, Dict[str, Any]] = {}
    for r in recs_b:
        by_idx_b[_flat_index_for(r, strategy_b)] = r
    common = sorted(set(by_idx_a) & set(by_idx_b))
    diffs: List[float] = []
    for i in common:
        va = metric_fn(by_idx_a[i])
        vb = metric_fn(by_idx_b[i])
        if va is not None and vb is not None:
            diffs.append(va - vb)
    return diffs, len(diffs), len(recs_a), len(recs_b)


def _per_k_block(k: int) -> Dict[str, Any]:
    cfg = PER_K_L2_CELLS[k]
    recs_a = _load_ok_records_for_cell(cfg["cell_a_id"])
    recs_b = _load_ok_records_for_cell(cfg["cell_b_id"])

    out: Dict[str, Any] = {
        "k": k,
        "strategy_a": cfg["strategy_a"],
        "cell_a_id": cfg["cell_a_id"],
        "strategy_b": cfg["strategy_b"],
        "cell_b_id": cfg["cell_b_id"],
        "boundary_substitution_active": cfg["boundary_substitution_active"],
        "n_records_strategy_a": len(recs_a),
        "n_records_strategy_b": len(recs_b),
    }

    # Δ_step and Δ_gate matched-pair CIs.
    for metric_name, metric_fn, seed_offset in (
        ("delta_step", _delta_step, 0),
        ("delta_gate", _delta_gate, 13),
    ):
        diffs, n_pairs, _, _ = _matched_pair_diffs(
            recs_a, cfg["strategy_a"], recs_b, cfg["strategy_b"], metric_fn,
        )
        ci = _bootstrap_ci_mean(diffs, seed=BOOTSTRAP_SEED + 100 * k + seed_offset)
        out["n_matched_pairs"] = n_pairs  # last assigned wins; both metrics use same pairing
        out[metric_name] = {
            "interaction_mean_diff": (
                float(np.mean(diffs)) if diffs else None
            ),
            "interaction_ci_95": list(ci) if ci is not None else None,
            "ci_excludes_zero": (
                ci is not None and (ci[0] > 0 or ci[1] < 0)
            ),
            "direction": _direction(ci),
        }

    # Catastrophe-rate diff at threshold = -50.
    cat_a = [
        ((_delta_step(r) is not None) and _delta_step(r) < CATASTROPHE_THRESHOLD)
        for r in recs_a
        if _delta_step(r) is not None
    ]
    cat_b = [
        ((_delta_step(r) is not None) and _delta_step(r) < CATASTROPHE_THRESHOLD)
        for r in recs_b
        if _delta_step(r) is not None
    ]
    rate_a = float(np.mean(cat_a)) if cat_a else None
    rate_b = float(np.mean(cat_b)) if cat_b else None
    diff_pp = (
        (rate_a - rate_b) * 100 if (rate_a is not None and rate_b is not None)
        else None
    )
    rate_diff_ci_unit = _bootstrap_ci_rate_diff(
        cat_a, cat_b, seed=BOOTSTRAP_SEED + 100 * k + 23
    )
    rate_diff_ci_pp = (
        [rate_diff_ci_unit[0] * 100, rate_diff_ci_unit[1] * 100]
        if rate_diff_ci_unit is not None else None
    )
    out["catastrophe_rate_diff_at_-50"] = {
        "stratified_rate": rate_a,
        "wpb_or_substitute_rate": rate_b,
        "diff_pp": diff_pp,
        "bootstrap_ci_95_pp": rate_diff_ci_pp,
    }
    return out


# --- main -------------------------------------------------------------


def main() -> int:
    print("Computing per-k L2 cross-strategy interactions...", file=sys.stderr)
    per_k = [_per_k_block(k) for k in (1, 2, 4)]

    # Headline summary.
    headline = {
        f"k{r['k']}_delta_step_direction": r["delta_step"]["direction"]
        for r in per_k
    }
    headline.update({
        f"k{r['k']}_delta_gate_direction": r["delta_gate"]["direction"]
        for r in per_k
    })

    dirs_step = {r["k"]: r["delta_step"]["direction"] for r in per_k}
    dirs_gate = {r["k"]: r["delta_gate"]["direction"] for r in per_k}
    sign_stable_step = (
        len({d for d in dirs_step.values() if d != "null"}) <= 1
    )
    sign_stable_gate = (
        len({d for d in dirs_gate.values() if d != "null"}) <= 1
    )
    headline["u_shape_test"] = (
        "Whether the per-k interaction CI is sign-stable across k. "
        "If signs differ between k=2 and {k=1, k=4}, the U-shape "
        "observed in the cell-mean is itself a cross-strategy "
        "structural feature; if signs agree across k, the U-shape "
        "is a parallel main effect at both strategies."
    )
    headline["delta_step_sign_stable_across_k"] = sign_stable_step
    headline["delta_gate_sign_stable_across_k"] = sign_stable_gate

    # Comparison-to-pooled block (read from existing anchor artifact).
    comp = {}
    if ANCHOR_PATH.exists():
        try:
            anchor = json.loads(ANCHOR_PATH.read_text(encoding="utf-8"))
            comp = {
                "ch7_pooled_at_k4_delta_step_ci_4cell_2x2": anchor.get(
                    "ch7_interaction_ci_delta_step"
                ),
                "ch7_pooled_at_k4_delta_gate_ci_4cell_2x2": anchor.get(
                    "ch7_interaction_ci_delta_gate"
                ),
                "note": (
                    "The pooled-at-k=4 statistic from "
                    "chapter7_anchor_reproduction.json is the 2x2 "
                    "L1-vs-L2 difference-of-differences ((strat_L2 - "
                    "strat_L1) - (wpb_L2 - wpb_L1)). The per-k results "
                    "above are 2-cell L2-only matched-pair differences "
                    "(strat_L2_at_k - wpb_L2_at_k), not 2x2 "
                    "interactions. The two statistics are different by "
                    "design: §7.3 measures whether the structure axis "
                    "interacts with selection at k=4; §7.4 measures "
                    "whether the cross-strategy gap at L2 is itself "
                    "stable across k."
                ),
            }
        except Exception:
            pass

    artifact = {
        "schema_version": 1,
        "design_doc_section": "§7.4",
        "method": (
            "Cross-strategy matched-pair mean Δ at L2, stratified by k. "
            "For each k ∈ {1, 2, 4}, the per-pair statistic is "
            "Δ(strat_L2_k_i) − Δ(wpb_or_sub_L2_k_i) at slot-aligned "
            "coordinate i; the reported CI is the 5,000-resample "
            "bootstrap CI on the mean of paired differences."
        ),
        "coordinate_alignment": (
            "slot-aligned per §12 patched lock (commit f5f623). "
            "stratified flat index = set_index*3 + seed_index; "
            "wpb / wo1 flat index = seed_index."
        ),
        "k1_special_case": (
            "worst_only_at_k1 substitutes for worst_plus_best per "
            "§3.8 boundary lock (worst_plus_best is undefined at k=1)"
        ),
        "bootstrap_n_resamples": BOOTSTRAP_N,
        "catastrophe_threshold": CATASTROPHE_THRESHOLD,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "per_k_results": per_k,
        "headline_summary": headline,
        "comparison_to_pooled": comp,
    }
    OUT_PATH.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"Wrote {OUT_PATH}", file=sys.stderr)

    # Update chapter7_summary.json with a compact summary block.
    if SUMMARY_PATH.exists():
        try:
            summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
            summary["l2_interaction_stratified_by_k"] = {
                "_artifact_path": str(
                    OUT_PATH.relative_to(REPO_ROOT).as_posix()
                ),
                "method_short": (
                    "Per-k cross-strategy matched-pair mean Δ at L2 "
                    "(strat_L2 − wpb/wo1_L2), 5000-resample bootstrap "
                    "CI; §7.4. Different statistic from §7.3's 2x2."
                ),
                "per_k": [
                    {
                        "k": r["k"],
                        "n_matched_pairs": r["n_matched_pairs"],
                        "boundary_substitution_active": r[
                            "boundary_substitution_active"
                        ],
                        "delta_step_mean_diff": r["delta_step"][
                            "interaction_mean_diff"
                        ],
                        "delta_step_ci_95": r["delta_step"][
                            "interaction_ci_95"
                        ],
                        "delta_step_direction": r["delta_step"]["direction"],
                        "delta_gate_mean_diff": r["delta_gate"][
                            "interaction_mean_diff"
                        ],
                        "delta_gate_ci_95": r["delta_gate"][
                            "interaction_ci_95"
                        ],
                        "delta_gate_direction": r["delta_gate"]["direction"],
                    }
                    for r in per_k
                ],
                "delta_step_sign_stable_across_k": sign_stable_step,
                "delta_gate_sign_stable_across_k": sign_stable_gate,
            }
            SUMMARY_PATH.write_text(
                json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
            )
            print(f"Updated {SUMMARY_PATH}", file=sys.stderr)
        except Exception as exc:
            print(f"  warn: failed to update summary: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
