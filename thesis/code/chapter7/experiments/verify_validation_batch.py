"""thesis/code/chapter7/experiments/verify_validation_batch.py

Chapter 7 §18.7 validation analysis. Mirrors the chapter-6
validation analysis structure, adapted to ch7's 14-cell ×
3-trajectory × 5-step matrix.

Outputs:
- ``thesis/artifacts/chapter7_validation_summary.json`` — top-level
- ``thesis/artifacts/chapter7_validation_l2_interaction_stratified_by_k.json``
- ``thesis/artifacts/chapter7_validation_anchor_reproduction.json``
- ``thesis/artifacts/chapter7_validation_failure_taxonomy.json``

Usage::

    python -m thesis.code.chapter7.experiments.verify_validation_batch
"""
from __future__ import annotations

import json
import os
import sys
import types
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(REPO_ROOT / ".env")

from thesis.code.chapter5.validation import (  # noqa: E402
    compute_per_instance_bins_for_heuristic,
)
from thesis.code.incumbents import get_h_eoh  # noqa: E402
from thesis.code.score_cache import ScoreCache  # noqa: E402
from thesis.code.splits import load_split, qualified_instance_id  # noqa: E402

RESULTS_DIR = REPO_ROOT / "thesis" / "results" / "chapter7_validation_batch_gemini"
ARTIFACTS_DIR = REPO_ROOT / "thesis" / "artifacts"
SUMMARY_PATH = ARTIFACTS_DIR / "chapter7_validation_summary.json"
L2_STRAT_PATH = ARTIFACTS_DIR / "chapter7_validation_l2_interaction_stratified_by_k.json"
ANCHOR_PATH = ARTIFACTS_DIR / "chapter7_validation_anchor_reproduction.json"
FAILURE_PATH = ARTIFACTS_DIR / "chapter7_validation_failure_taxonomy.json"
PRIMARY_SUMMARY_PATH = ARTIFACTS_DIR / "chapter7_summary.json"

N_TRAJECTORIES = 3
N_STEPS = 5
BOOTSTRAP_N = 5000
BOOTSTRAP_SEED = 20_260_511
CATASTROPHE_THRESHOLD = -50.0

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


def _step_filename(cell_id: str, traj_idx: int, step_idx: int) -> str:
    return f"chapter7_validation_{cell_id}_traj{traj_idx}_step{step_idx}.json"


def _load_step(cell_id: str, traj_idx: int, step_idx: int) -> Optional[Dict[str, Any]]:
    path = RESULTS_DIR / _step_filename(cell_id, traj_idx, step_idx)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_trajectory(cell_id: str, traj_idx: int) -> List[Optional[Dict[str, Any]]]:
    return [_load_step(cell_id, traj_idx, s) for s in range(N_STEPS)]


def _h_eoh_mean_train_step(cache: ScoreCache, h_eoh: Dict[str, Any]) -> float:
    bins = compute_per_instance_bins_for_heuristic(
        h_eoh["code"], h_eoh["code_hash"], "train_step", cache=cache,
    )
    return float(np.mean(bins))


def _final_incumbent_mean_train_step(
    rec_at_step: Dict[str, Any], cache: ScoreCache,
) -> Optional[float]:
    """Mean train_step bins of this step's *next* incumbent (i.e., the
    incumbent the trajectory carries after this step). Uses the
    next_incumbent_source field from the record."""
    code = rec_at_step.get("next_incumbent_source")
    code_hash = rec_at_step.get("next_incumbent_hash")
    if not code or not code_hash:
        return None
    bins = compute_per_instance_bins_for_heuristic(
        code, code_hash, "train_step", cache=cache,
    )
    return float(np.mean(bins))


def _bootstrap_ci_mean(
    values: List[float],
    *, seed: int = BOOTSTRAP_SEED, n: int = BOOTSTRAP_N, alpha: float = 0.05,
) -> Optional[Tuple[float, float]]:
    if not values:
        return None
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    means = np.empty(n, dtype=float)
    for i in range(n):
        idx = rng.integers(0, arr.size, size=arr.size)
        means[i] = float(np.mean(arr[idx]))
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


# ---------------------------------------------------------------------
# Per-trajectory + per-cell aggregation
# ---------------------------------------------------------------------


def _per_trajectory_outcome(
    cell_id: str, traj_idx: int, h_eoh_mean: float, cache: ScoreCache,
) -> Dict[str, Any]:
    steps_recs = _load_trajectory(cell_id, traj_idx)
    out_steps: List[Dict[str, Any]] = []
    cumulative_per_step: List[Optional[float]] = []
    accepted_count = 0
    moved = False
    for i, rec in enumerate(steps_recs):
        if rec is None:
            out_steps.append({"step_index": i, "status": "missing"})
            cumulative_per_step.append(None)
            continue
        decision = rec.get("acceptance_decision")
        reason = rec.get("acceptance_reason")
        delta_local = rec.get("delta_step_local")
        next_hash = rec.get("next_incumbent_hash")
        cur_hash = rec.get("current_incumbent_hash")
        if decision == "accepted":
            accepted_count += 1
            if next_hash != cur_hash:
                moved = True
        # Cumulative Δ at this step: h_eoh mean − next_incumbent mean.
        next_mean = _final_incumbent_mean_train_step(rec, cache)
        cum = (h_eoh_mean - next_mean) if next_mean is not None else None
        cumulative_per_step.append(cum)
        out_steps.append({
            "step_index": i,
            "acceptance_decision": decision,
            "acceptance_reason": reason,
            "delta_step_local": delta_local,
            "argmax_distinct": rec.get("argmax_distinct"),
            "current_incumbent_hash": cur_hash,
            "next_incumbent_hash": next_hash,
            "proposal_hash": rec.get("proposal_hash"),
            "sanitize_status": (rec.get("sanitization") or {}).get("status"),
            "delta_step_cumulative_through_this_step": cum,
        })
    final_cum = next(
        (v for v in reversed(cumulative_per_step) if v is not None), None
    )
    return {
        "trajectory_index": traj_idx,
        "n_steps_complete": sum(1 for r in steps_recs if r is not None),
        "n_accepted": accepted_count,
        "trajectory_moved": moved,
        "delta_step_cumulative_through_step": cumulative_per_step,
        "delta_step_cumulative_5_terminal": final_cum,
        "final_incumbent_hash": (
            steps_recs[-1].get("next_incumbent_hash") if steps_recs[-1] else None
        ),
        "steps": out_steps,
    }


def _per_cell(cell: Dict[str, Any], h_eoh_mean: float, cache: ScoreCache) -> Dict[str, Any]:
    cell_id = cell["cell_id"]
    trajs = [_per_trajectory_outcome(cell_id, t, h_eoh_mean, cache)
             for t in range(N_TRAJECTORIES)]
    terminal_cums = [t["delta_step_cumulative_5_terminal"] for t in trajs
                     if t["delta_step_cumulative_5_terminal"] is not None]
    accepted_total = sum(t["n_accepted"] for t in trajs)
    moved_count = sum(1 for t in trajs if t["trajectory_moved"])
    n_steps_total = sum(t["n_steps_complete"] for t in trajs)
    # acceptance reason distribution
    reason_counts: Dict[str, int] = defaultdict(int)
    sanitize_status_counts: Dict[str, int] = defaultdict(int)
    for t in trajs:
        for s in t["steps"]:
            r = s.get("acceptance_reason")
            if r:
                reason_counts[r] += 1
            ss = s.get("sanitize_status")
            if ss:
                sanitize_status_counts[ss] += 1
    return {
        "cell": cell,
        "n_steps_complete_total": n_steps_total,
        "n_steps_planned": N_TRAJECTORIES * N_STEPS,
        "n_accepted_total": accepted_total,
        "n_trajectories_moved": moved_count,
        "acceptance_reason_counts": dict(reason_counts),
        "sanitize_status_counts": dict(sanitize_status_counts),
        "sanitize_rate": (
            sanitize_status_counts.get("ok", 0) / n_steps_total
            if n_steps_total > 0 else None
        ),
        "trajectories": trajs,
        "delta_step_cumulative_5_per_trajectory": [
            t["delta_step_cumulative_5_terminal"] for t in trajs
        ],
        "delta_step_cumulative_5_mean": (
            float(np.mean(terminal_cums)) if terminal_cums else None
        ),
        "delta_step_cumulative_5_ci_95": _bootstrap_ci_mean(terminal_cums) if terminal_cums else None,
    }


# ---------------------------------------------------------------------
# Cross-cell rankings + single-shot vs compound inversions
# ---------------------------------------------------------------------


def _rank_by(cells: List[Dict[str, Any]], key_fn) -> List[Tuple[str, Optional[float]]]:
    pairs = [(c["cell"]["cell_id"], key_fn(c)) for c in cells]
    # Most-positive first; None at the bottom.
    pairs.sort(key=lambda p: (-(p[1] if p[1] is not None else -1e18)))
    return pairs


def _single_shot_vs_compound(per_cell_validation: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare primary-batch single-shot Δ_step ranks (from
    chapter7_summary.json) to validation cumulative ranks."""
    out: Dict[str, Any] = {}
    primary_summary = None
    if PRIMARY_SUMMARY_PATH.exists():
        try:
            primary_summary = json.loads(
                PRIMARY_SUMMARY_PATH.read_text(encoding="utf-8")
            )
        except Exception:
            primary_summary = None
    if primary_summary is None:
        out["status"] = "primary_summary_missing"
        return out
    primary_per_cell = primary_summary.get("per_cell_summary", {})
    primary_means = {
        cid: ((c.get("delta_step_stats") or {}).get("mean"))
        for cid, c in primary_per_cell.items()
    }
    valid_means = {
        c["cell"]["cell_id"]: c["delta_step_cumulative_5_mean"]
        for c in per_cell_validation
    }
    rank_primary = sorted(
        [c for c in primary_means if primary_means[c] is not None],
        key=lambda c: -primary_means[c],
    )
    rank_valid = sorted(
        [c for c in valid_means if valid_means[c] is not None],
        key=lambda c: -valid_means[c],
    )
    inversions: List[Dict[str, Any]] = []
    common = [c for c in rank_primary if c in rank_valid]
    for i, ca in enumerate(common):
        for cb in common[i + 1:]:
            order_primary = ca if rank_primary.index(ca) < rank_primary.index(cb) else cb
            order_valid = ca if rank_valid.index(ca) < rank_valid.index(cb) else cb
            if order_primary != order_valid:
                inversions.append({
                    "cell_a": ca, "cell_b": cb,
                    "primary_winner": order_primary,
                    "validation_winner": order_valid,
                    "primary_means": [primary_means[ca], primary_means[cb]],
                    "validation_means": [valid_means[ca], valid_means[cb]],
                })
    out.update({
        "primary_means": primary_means,
        "validation_terminal_cumulative_means": valid_means,
        "rank_primary_top_to_bottom": rank_primary,
        "rank_validation_top_to_bottom": rank_valid,
        "inversion_count_pairwise": len(inversions),
        "inversions": inversions,
    })
    return out


# ---------------------------------------------------------------------
# §7.4 stratified-by-k under compound improvement
# ---------------------------------------------------------------------

PER_K_L2_CELLS_VALIDATION: Dict[int, Dict[str, str]] = {
    1: {"cell_a_id": "CH7-09", "cell_b_id": "CH7-12",
        "strategy_a": "stratified_representative",
        "strategy_b": "worst_only_at_k1",
        "boundary_substitution_active": True},
    2: {"cell_a_id": "CH7-10", "cell_b_id": "CH7-13",
        "strategy_a": "stratified_representative",
        "strategy_b": "worst_plus_best",
        "boundary_substitution_active": False},
    4: {"cell_a_id": "CH7-11", "cell_b_id": "CH7-14",
        "strategy_a": "stratified_representative",
        "strategy_b": "worst_plus_best",
        "boundary_substitution_active": False},
}


def _l2_interaction_stratified_validation(
    per_cell_validation: List[Dict[str, Any]],
) -> Dict[str, Any]:
    by_id = {c["cell"]["cell_id"]: c for c in per_cell_validation}
    out_per_k: List[Dict[str, Any]] = []
    for k, cfg in PER_K_L2_CELLS_VALIDATION.items():
        a = by_id.get(cfg["cell_a_id"])
        b = by_id.get(cfg["cell_b_id"])
        if a is None or b is None:
            out_per_k.append({"k": k, "status": "missing_cell"})
            continue
        a_terms = a["delta_step_cumulative_5_per_trajectory"]
        b_terms = b["delta_step_cumulative_5_per_trajectory"]
        # Slot-aligned matched pair on trajectory_index.
        diffs: List[float] = []
        for ti in range(N_TRAJECTORIES):
            if (ti < len(a_terms) and ti < len(b_terms)
                    and a_terms[ti] is not None
                    and b_terms[ti] is not None):
                diffs.append(a_terms[ti] - b_terms[ti])
        ci = _bootstrap_ci_mean(diffs, seed=BOOTSTRAP_SEED + k)
        out_per_k.append({
            "k": k,
            "cell_a_id": cfg["cell_a_id"],
            "cell_b_id": cfg["cell_b_id"],
            "strategy_a": cfg["strategy_a"],
            "strategy_b": cfg["strategy_b"],
            "boundary_substitution_active": cfg["boundary_substitution_active"],
            "n_matched_trajectories": len(diffs),
            "matched_pair_diffs": diffs,
            "mean_diff": float(np.mean(diffs)) if diffs else None,
            "ci_95": list(ci) if ci is not None else None,
            "ci_excludes_zero": (ci is not None and (ci[0] > 0 or ci[1] < 0)),
            "direction": (
                "positive" if ci is not None and ci[0] > 0
                else "negative" if ci is not None and ci[1] < 0
                else "null"
            ),
        })
    # Reproduction-vs-primary verdict.
    primary = None
    primary_path = ARTIFACTS_DIR / "chapter7_l2_interaction_stratified_by_k.json"
    if primary_path.exists():
        try:
            primary = json.loads(primary_path.read_text(encoding="utf-8"))
        except Exception:
            primary = None
    reproduction = {}
    if primary is not None:
        primary_dirs = {
            r["k"]: r["delta_step"]["direction"]
            for r in primary["per_k_results"]
        }
        valid_dirs = {r["k"]: r["direction"] for r in out_per_k if "direction" in r}
        agreements = []
        for k in (1, 2, 4):
            pd = primary_dirs.get(k)
            vd = valid_dirs.get(k)
            agreements.append({
                "k": k,
                "primary_direction": pd,
                "validation_direction": vd,
                "agree": pd == vd,
            })
        reproduction = {
            "primary_artifact": str(primary_path.relative_to(REPO_ROOT).as_posix()),
            "n_trajectories_per_cell": N_TRAJECTORIES,
            "agreement_per_k": agreements,
            "fully_agrees_across_k": all(a["agree"] for a in agreements),
            "note": (
                "Validation is underpowered at n=3 trajectories per cell "
                "vs. primary's n=60 records per cell. A 'null' direction "
                "in validation that was 'positive' in primary may reflect "
                "low statistical power rather than disagreement; the "
                "matched-pair point estimates and signs are the more "
                "informative comparison."
            ),
        }
    return {
        "per_k_results": out_per_k,
        "reproduction_vs_primary": reproduction,
    }


# ---------------------------------------------------------------------
# Anchor-cells reproduction vs ch6 validation
# ---------------------------------------------------------------------

# ch6 validation reference numbers per the user task-spec note.
# These are placeholders pending exact ch6 reference numbers; the
# task spec says "Pull the exact ch6 reference numbers from
# chapter6_validation_batch_gemini/ analysis or the ch6 prose itself"
# — we read from chapter6_validation_batch_overview.json if it exists,
# falling back to the task-spec figures.
CH6_ANCHOR_FALLBACK_VALIDATION_CUMS = {
    "stratified_representative@L1": None,  # ch5 reference: +7.12 (commit 9f...; ch5 §5.4)
    "stratified_representative@L2": None,  # ch6 +7.32 per user task spec note (verify in artifact)
    "worst_plus_best@L1": None,            # ch5 reference: +4.31; ch6 §6.7.1 noted +3.01-bin gap
    "worst_plus_best@L2": None,
}


def _ch6_anchor_validation_cums() -> Dict[str, Optional[float]]:
    """Read ch6 validation cumulative numbers from the ch6 overview
    artifact if available; otherwise return None placeholders."""
    p = ARTIFACTS_DIR / "chapter6_validation_batch_overview.json"
    if not p.exists():
        return dict(CH6_ANCHOR_FALLBACK_VALIDATION_CUMS)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return dict(CH6_ANCHOR_FALLBACK_VALIDATION_CUMS)
    out: Dict[str, Optional[float]] = {}
    cells = data.get("cells", [])
    for c in cells:
        cid = c.get("cell_id")
        traj_terminals = []
        for t in c.get("trajectories", []):
            cs = t.get("delta_step_cumulative_per_step")
            if isinstance(cs, list) and cs:
                traj_terminals.append(cs[-1])
        if traj_terminals:
            out[cid] = float(np.mean(traj_terminals))
        else:
            out[cid] = None
    return out


def _anchor_validation_reproduction(
    per_cell_validation: List[Dict[str, Any]],
) -> Dict[str, Any]:
    by_id = {c["cell"]["cell_id"]: c for c in per_cell_validation}
    ch7_anchor_map = {
        "stratified_representative@L1": "CH7-03",
        "stratified_representative@L2": "CH7-11",
        "worst_plus_best@L1": "CH7-07",
        "worst_plus_best@L2": "CH7-14",
    }
    ch6_cums = _ch6_anchor_validation_cums()
    rows = []
    for label, cid in ch7_anchor_map.items():
        c = by_id.get(cid)
        ch7_mean = c["delta_step_cumulative_5_mean"] if c else None
        ch6_mean = ch6_cums.get(label)
        rows.append({
            "cell_label": label,
            "ch7_cell_id": cid,
            "ch7_validation_terminal_cum_mean": ch7_mean,
            "ch7_per_trajectory": (
                c["delta_step_cumulative_5_per_trajectory"] if c else None
            ),
            "ch6_validation_terminal_cum_mean": ch6_mean,
            "delta_ch7_minus_ch6": (
                (ch7_mean - ch6_mean) if (ch7_mean is not None and ch6_mean is not None)
                else None
            ),
        })
    return {
        "anchors": rows,
        "note": (
            "ch6 reference numbers read from "
            "thesis/artifacts/chapter6_validation_batch_overview.json when "
            "present (per-cell mean over 3 trajectories of step-5 "
            "cumulative). Absent values indicate the ch6 overview was not "
            "found at that path — chapter prose should cite the ch6 "
            "validation source explicitly."
        ),
    }


# ---------------------------------------------------------------------
# Sanitization failure taxonomy
# ---------------------------------------------------------------------


def _failure_taxonomy(per_cell_validation: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    grand: Dict[str, int] = defaultdict(int)
    for c in per_cell_validation:
        cid = c["cell"]["cell_id"]
        out[cid] = {
            "cell": c["cell"],
            "sanitize_status_counts": c["sanitize_status_counts"],
            "acceptance_reason_counts": c["acceptance_reason_counts"],
            "n_steps_complete": c["n_steps_complete_total"],
        }
        for k, v in c["sanitize_status_counts"].items():
            grand[k] += v
        for k, v in c["acceptance_reason_counts"].items():
            grand[f"acceptance:{k}"] += v
    out["_grand_totals"] = dict(grand)
    return out


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------


def main() -> int:
    if not RESULTS_DIR.exists():
        print(f"results dir not found: {RESULTS_DIR}", file=sys.stderr)
        return 1
    cache = ScoreCache()
    h_eoh = get_h_eoh()
    h_eoh_mean = _h_eoh_mean_train_step(cache, h_eoh)
    print(f"h_eoh train_step mean = {h_eoh_mean:.4f}", file=sys.stderr)

    per_cell = [_per_cell(cell, h_eoh_mean, cache) for cell in CELLS]
    cache.save()

    inversions = _single_shot_vs_compound(per_cell)
    l2_strat = _l2_interaction_stratified_validation(per_cell)
    anchor = _anchor_validation_reproduction(per_cell)
    failures = _failure_taxonomy(per_cell)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    L2_STRAT_PATH.write_text(
        json.dumps({
            "schema_version": 1,
            "design_doc_section": "§18.7 E (validation portion of §7.4)",
            "method": (
                "Cross-strategy matched-pair on terminal cumulative "
                "Δ_step at L2, stratified by k, on validation trajectories. "
                "n_pairs = n_trajectories = 3 per cell — underpowered "
                "relative to primary's n=60 per cell."
            ),
            **l2_strat,
        }, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    ANCHOR_PATH.write_text(
        json.dumps({
            "schema_version": 1,
            "design_doc_section": "§18.7 F",
            **anchor,
        }, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    FAILURE_PATH.write_text(
        json.dumps({
            "schema_version": 1,
            "design_doc_section": "§18.7 G",
            "per_cell": failures,
        }, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = {
        "schema_version": 1,
        "chapter": "chapter7",
        "phase": "validation",
        "design_doc_section": "§18.7",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "h_eoh_mean_train_step": h_eoh_mean,
        "per_cell": per_cell,
        "single_shot_vs_compound": inversions,
        "l2_interaction_stratified_by_k_summary": {
            "_artifact_path": str(L2_STRAT_PATH.relative_to(REPO_ROOT).as_posix()),
            "per_k": [
                {k_name: r.get(k_name) for k_name in
                 ("k", "n_matched_trajectories", "mean_diff", "ci_95",
                  "direction")}
                for r in l2_strat.get("per_k_results", [])
            ],
            "reproduction_vs_primary": l2_strat.get("reproduction_vs_primary"),
        },
        "anchor_reproduction_summary": {
            "_artifact_path": str(ANCHOR_PATH.relative_to(REPO_ROOT).as_posix()),
            "anchors": anchor.get("anchors"),
        },
        "failure_taxonomy_summary": {
            "_artifact_path": str(FAILURE_PATH.relative_to(REPO_ROOT).as_posix()),
            "grand_totals": failures.get("_grand_totals"),
        },
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"Wrote {SUMMARY_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
