"""
thesis/code/chapter5/analysis.py

Post-batch analysis for the Chapter 5 primary experiment.

Reads the per-call provenance JSONs produced by `runner.run_single_
proposal` (via `batch_runner.run_primary_batch`), computes the
distribution-level statistics and effect sizes specified in
`chapter5_design.md` §9 and §10, and returns a single `summary`
dict that serializes to the committed `chapter5_summary.json`
artifact.

No LLM calls; pure numeric reduction over on-disk records.

Key pieces:
  - load_primary_batch_proposals  — read per-call JSONs by strategy
  - compute_distribution_stats    — central tendency, spread, tail
                                    masses, robust means
  - compute_cliffs_delta          — pairwise stochastic dominance
  - compute_iqr_overlap           — Jaccard overlap of IQR bands
  - build_summary                 — assemble the summary dict
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Strategies not in this set are treated as pure-loss in the
# mixed-composition aggregate observation (the one chapter 5 open
# item from the 2026-04-23 decisions log). Currently:
#   - worst_only and most_discriminative are pure-loss
#   - every other chapter-5 strategy is mixed-composition
PURE_LOSS_STRATEGIES = frozenset({"worst_only", "most_discriminative"})

_NEAR_PARITY_THRESHOLD = 5.0
_CATASTROPHIC_THRESHOLD = -50.0
_TRIM_FRACTION = 0.10


H_EOH_CODE_HASH = "8ca83676ae76"


def load_primary_batch_proposals(
    results_dir: Path,
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Load per-call provenance JSONs from `results_dir`, grouped
    by strategy name.

    Any file that fails to parse or whose ``sanitization.status``
    is not ``"ok"`` is excluded from the per-strategy lists and
    its filename is appended to the returned ``skipped`` list. The
    primary-batch-summary and progress JSONs are skipped silently.

    Returns
    -------
    proposals_by_strategy : dict
        ``{strategy_name: [record, ...]}`` for all ok records.
    skipped : list
        Filenames of records that were excluded.
    """
    results_dir = Path(results_dir)
    proposals: Dict[str, List[Dict[str, Any]]] = {}
    skipped: List[str] = []
    NON_PROPOSAL = {"progress.json", "primary_batch_summary.json"}

    for path in sorted(results_dir.glob("*.json")):
        if path.name in NON_PROPOSAL:
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skipped.append(path.name)
            continue
        strategy = record.get("strategy_name")
        sanit = record.get("sanitization") or {}
        if strategy is None or sanit.get("status") != "ok":
            skipped.append(path.name)
            continue
        proposals.setdefault(strategy, []).append(record)

    return proposals, skipped


def _percentile(arr: np.ndarray, q: float) -> float:
    return float(np.percentile(arr, q))


def compute_distribution_stats(values: List[float]) -> Dict[str, Any]:
    """Distribution-level summary used per-metric per-strategy.

    All fields are JSON-serializable floats (or 0 for empty
    inputs) except ``n`` which is an int.
    """
    n = len(values)
    if n == 0:
        return {
            "n": 0,
            "mean": 0.0,
            "median": 0.0,
            "std": 0.0,
            "min": 0.0,
            "p10": 0.0,
            "p25": 0.0,
            "p75": 0.0,
            "p90": 0.0,
            "max": 0.0,
            "iqr": 0.0,
            "trimmed_mean_10pct": 0.0,
            "winsorized_mean_10pct": 0.0,
            "positive_tail_mass": 0.0,
            "near_parity_mass": 0.0,
            "catastrophic_tail_mass": 0.0,
        }

    arr = np.asarray(values, dtype=float)
    sorted_arr = np.sort(arr)
    p10 = _percentile(arr, 10)
    p25 = _percentile(arr, 25)
    p50 = _percentile(arr, 50)
    p75 = _percentile(arr, 75)
    p90 = _percentile(arr, 90)

    # Trimmed mean: drop top/bottom 10% (symmetric), average the rest.
    k = int(np.floor(n * _TRIM_FRACTION))
    if n - 2 * k > 0:
        trimmed_mean = float(np.mean(sorted_arr[k: n - k]))
    else:
        trimmed_mean = float(np.mean(arr))

    # Winsorized mean: clip below p10 and above p90, then average.
    winsorized = np.clip(arr, p10, p90)
    winsorized_mean = float(np.mean(winsorized))

    positive_tail_mass = float(np.mean(arr > 0.0))
    near_parity_mass = float(np.mean(np.abs(arr) <= _NEAR_PARITY_THRESHOLD))
    catastrophic_tail_mass = float(
        np.mean(arr < _CATASTROPHIC_THRESHOLD)
    )

    return {
        "n": n,
        "mean": float(np.mean(arr)),
        "median": float(p50),
        "std": float(np.std(arr, ddof=0)),
        "min": float(np.min(arr)),
        "p10": float(p10),
        "p25": float(p25),
        "p75": float(p75),
        "p90": float(p90),
        "max": float(np.max(arr)),
        "iqr": float(p75 - p25),
        "trimmed_mean_10pct": trimmed_mean,
        "winsorized_mean_10pct": winsorized_mean,
        "positive_tail_mass": positive_tail_mass,
        "near_parity_mass": near_parity_mass,
        "catastrophic_tail_mass": catastrophic_tail_mass,
    }


def compute_cliffs_delta(xs: List[float], ys: List[float]) -> float:
    """Cliff's delta between two samples.

    delta = (#{xi > yj} - #{xi < yj}) / (n * m)

    +1 means xs strictly dominate ys, -1 means ys dominate, 0
    means no stochastic dominance. Ties contribute 0.
    """
    if not xs or not ys:
        return 0.0
    x = np.asarray(xs, dtype=float)[:, None]
    y = np.asarray(ys, dtype=float)[None, :]
    greater = int((x > y).sum())
    less = int((x < y).sum())
    denom = x.shape[0] * y.shape[1]
    return float((greater - less) / denom)


def compute_iqr_overlap(xs: List[float], ys: List[float]) -> float:
    """Jaccard-style overlap of the two samples' IQR intervals.

    1.0 means identical IQR bands; 0.0 means disjoint.
    """
    if not xs or not ys:
        return 0.0
    xs_p25 = _percentile(np.asarray(xs, dtype=float), 25)
    xs_p75 = _percentile(np.asarray(xs, dtype=float), 75)
    ys_p25 = _percentile(np.asarray(ys, dtype=float), 25)
    ys_p75 = _percentile(np.asarray(ys, dtype=float), 75)
    overlap_range = max(0.0, min(xs_p75, ys_p75) - max(xs_p25, ys_p25))
    total_range = max(xs_p75, ys_p75) - min(xs_p25, ys_p25)
    if total_range <= 0.0:
        # Both IQRs collapsed to a point AND they coincide.
        return 1.0 if xs_p25 == ys_p25 and xs_p75 == ys_p75 else 0.0
    return float(overlap_range / total_range)


def _metric_array(
    records: List[Dict[str, Any]], metric_key: str
) -> List[float]:
    """Extract one metric across records, skipping None values."""
    out: List[float] = []
    for r in records:
        sc = r.get("scoring") or {}
        v = sc.get(metric_key)
        if v is not None:
            out.append(float(v))
    return out


def is_argmax_equivalent_to_h_eoh(
    proposal_per_instance_bins: List[int],
    h_eoh_per_instance_bins: List[int],
) -> bool:
    """Return True iff the two per-instance bin-count lists are
    element-wise equal.

    For the bp_online harness each decision is an argmax over the
    proposal's score(item, bins) vector. Identical bin counts on
    every instance ⇒ the proposal's score function produced the
    same argmax as h_eoh on every decision across those instances.
    The two scoring functions may differ syntactically / numerically
    yet lie in the same argmax-equivalence class on this sample.
    """
    if len(proposal_per_instance_bins) != len(h_eoh_per_instance_bins):
        return False
    return all(
        int(a) == int(b)
        for a, b in zip(
            proposal_per_instance_bins, h_eoh_per_instance_bins
        )
    )


def compute_h_eoh_per_instance_bins(
    split_name: str = "train_step",
) -> List[int]:
    """Return h_eoh's per-instance bin counts on `split_name`,
    using the persistent score cache. Cheap on a cached score
    cache (no re-evaluation), which the primary batch has already
    populated."""
    import types

    from thesis.code.evaluation import bins_used
    from thesis.code.incumbents import get_h_eoh
    from thesis.code.score_cache import ScoreCache
    from thesis.code.splits import load_split, qualified_instance_id

    h_eoh = get_h_eoh()
    mod = types.ModuleType(f"incumbent_{h_eoh['code_hash']}")
    exec(compile(h_eoh["code"], "<h_eoh>", "exec"), mod.__dict__)
    cache = ScoreCache()
    split = load_split(split_name)
    per: List[int] = []
    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        b = cache.get_or_compute(
            h_eoh["code_hash"],
            qid,
            lambda i=inst: bins_used(mod, i),
        )
        per.append(int(b))
    return per


def _count_failure_labels(
    records: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Count `sanitization.status` values other than `ok` across a
    strategy's records. Primary batch expected to be all-ok; this
    is defensive."""
    counts: Dict[str, int] = {}
    for r in records:
        status = (r.get("sanitization") or {}).get("status")
        if status and status != "ok":
            counts[status] = counts.get(status, 0) + 1
    return counts


def _pairwise(
    strategies: List[str],
    metric_by_strategy: Dict[str, List[float]],
    fn,
) -> Dict[str, float]:
    """Compute `fn(xs, ys)` over unordered strategy pairs. Key
    format: ``"s1__vs__s2"`` with s1 < s2 lexicographically."""
    out: Dict[str, float] = {}
    for i, a in enumerate(strategies):
        for b in strategies[i + 1:]:
            key = f"{a}__vs__{b}"
            out[key] = fn(
                metric_by_strategy.get(a, []),
                metric_by_strategy.get(b, []),
            )
    return out


def build_summary(
    proposals_by_strategy: Dict[str, List[Dict[str, Any]]],
    *,
    batch_id: str = "chapter5_primary_batch_gemini",
    h_eoh_per_instance_by_split: Optional[Dict[str, List[int]]] = None,
) -> Dict[str, Any]:
    """Assemble the post-batch summary dict (§9/§10 of chapter5_
    design.md, §12 artifact spec).

    If `h_eoh_per_instance_by_split` is provided with keys
    ``"train_step"`` and ``"train_gate"``, the summary includes
    argmax-equivalence metrics per strategy plus a reduced-
    distribution re-analysis over the argmax-distinct subset
    (§10 addendum per the 2026-04-23 findings-log entry). When
    absent those blocks are omitted.
    """
    strategies = sorted(proposals_by_strategy.keys())
    total_records = sum(
        len(v) for v in proposals_by_strategy.values()
    )

    per_strategy: Dict[str, Any] = {}
    delta_step_by_strat: Dict[str, List[float]] = {}
    delta_gate_by_strat: Dict[str, List[float]] = {}
    # Subsets restricted to argmax-distinct proposals (populated
    # only if h_eoh_per_instance_by_split is provided).
    delta_step_by_strat_distinct: Dict[str, List[float]] = {}

    for s in strategies:
        records = proposals_by_strategy[s]
        d_step = _metric_array(records, "delta_step")
        d_gate = _metric_array(records, "delta_gate")
        gen_gap = _metric_array(records, "generalization_gap")
        win_rates = _metric_array(records, "win_rate_step")
        delta_step_by_strat[s] = d_step
        delta_gate_by_strat[s] = d_gate

        strat_block: Dict[str, Any] = {
            "n_ok": len(records),
            "n_failed_by_label": _count_failure_labels(records),
            "delta_step": compute_distribution_stats(d_step),
            "delta_gate": compute_distribution_stats(d_gate),
            "generalization_gap": compute_distribution_stats(gen_gap),
            "win_rate_step_mean": (
                float(np.mean(win_rates)) if win_rates else 0.0
            ),
            "win_rate_step_median": (
                float(np.median(win_rates)) if win_rates else 0.0
            ),
        }

        if h_eoh_per_instance_by_split is not None:
            h_step = h_eoh_per_instance_by_split.get("train_step", [])
            h_gate = h_eoh_per_instance_by_split.get("train_gate", [])
            distinct_ds: List[float] = []
            eq_step = 0
            eq_gate = 0
            eq_both = 0
            for r in records:
                sc = r.get("scoring") or {}
                p_step = sc.get("per_instance_bins_proposal_train_step") or []
                p_gate = sc.get("per_instance_bins_proposal_train_gate") or []
                step_eq = is_argmax_equivalent_to_h_eoh(p_step, h_step)
                gate_eq = is_argmax_equivalent_to_h_eoh(p_gate, h_gate)
                if step_eq:
                    eq_step += 1
                if gate_eq:
                    eq_gate += 1
                if step_eq and gate_eq:
                    eq_both += 1
                if not step_eq:
                    ds_val = sc.get("delta_step")
                    if ds_val is not None:
                        distinct_ds.append(float(ds_val))
            delta_step_by_strat_distinct[s] = distinct_ds
            n = len(records)
            strat_block["argmax_equivalent_count"] = eq_step
            strat_block["argmax_equivalent_rate"] = (
                eq_step / n if n else 0.0
            )
            strat_block["argmax_distinct_count"] = n - eq_step
            strat_block["argmax_equivalent_on_train_gate_count"] = eq_gate
            strat_block["argmax_equivalent_on_both_count"] = eq_both
            strat_block["argmax_distinct_distribution_delta_step"] = (
                compute_distribution_stats(distinct_ds)
            )

        per_strategy[s] = strat_block

    pairwise_cliffs_delta: Dict[str, Any] = {
        "delta_step": _pairwise(
            strategies, delta_step_by_strat, compute_cliffs_delta
        ),
        "delta_gate": _pairwise(
            strategies, delta_gate_by_strat, compute_cliffs_delta
        ),
    }
    pairwise_iqr_overlap: Dict[str, Any] = {
        "delta_step": _pairwise(
            strategies, delta_step_by_strat, compute_iqr_overlap
        ),
        "delta_gate": _pairwise(
            strategies, delta_gate_by_strat, compute_iqr_overlap
        ),
    }
    if h_eoh_per_instance_by_split is not None:
        pairwise_cliffs_delta["delta_step_argmax_distinct"] = _pairwise(
            strategies,
            delta_step_by_strat_distinct,
            compute_cliffs_delta,
        )

    # Aggregate: pure-loss (worst_only) vs mixed-composition (the
    # other four). Defined in the 2026-04-23 findings-log entry.
    pure_loss = [
        s for s in strategies if s in PURE_LOSS_STRATEGIES
    ]
    mixed = [s for s in strategies if s not in PURE_LOSS_STRATEGIES]
    pure_loss_d_step: List[float] = []
    for s in pure_loss:
        pure_loss_d_step.extend(delta_step_by_strat.get(s, []))
    mixed_d_step: List[float] = []
    for s in mixed:
        mixed_d_step.extend(delta_step_by_strat.get(s, []))

    aggregate: Dict[str, Any] = {
        "mixed_composition_vs_pure_loss": {
            "pure_loss_strategies": pure_loss,
            "mixed_composition_strategies": mixed,
            "pure_loss_delta_step": compute_distribution_stats(
                pure_loss_d_step
            ),
            "mixed_composition_delta_step": compute_distribution_stats(
                mixed_d_step
            ),
            "cliffs_delta_mixed_vs_pure": compute_cliffs_delta(
                mixed_d_step, pure_loss_d_step
            ),
        }
    }

    if h_eoh_per_instance_by_split is not None:
        total_eq_step = sum(
            per_strategy[s]["argmax_equivalent_count"]
            for s in strategies
        )
        total_eq_both = sum(
            per_strategy[s]["argmax_equivalent_on_both_count"]
            for s in strategies
        )
        # Distinct code hashes among the argmax-equivalent records.
        eq_hashes: set[str] = set()
        h_step = h_eoh_per_instance_by_split.get("train_step", [])
        for s in strategies:
            for r in proposals_by_strategy[s]:
                sc = r.get("scoring") or {}
                p_step = sc.get("per_instance_bins_proposal_train_step") or []
                if is_argmax_equivalent_to_h_eoh(p_step, h_step):
                    ph = r.get("proposal_hash")
                    if ph:
                        eq_hashes.add(ph)
        mean_rate = (
            float(np.mean([
                per_strategy[s]["argmax_equivalent_rate"]
                for s in strategies
            ]))
            if strategies else 0.0
        )
        aggregate["argmax_equivalence"] = {
            "total_argmax_equivalent_on_train_step": total_eq_step,
            "total_argmax_equivalent_on_both_splits": total_eq_both,
            "distinct_code_hashes_among_argmax_equivalent": (
                len(eq_hashes)
            ),
            "mean_argmax_equivalent_rate_across_strategies": mean_rate,
        }

    return {
        "batch_id": batch_id,
        "n_proposals": total_records,
        "n_strategies": len(strategies),
        "strategies": strategies,
        "per_strategy": per_strategy,
        "pairwise_cliffs_delta": pairwise_cliffs_delta,
        "pairwise_iqr_overlap": pairwise_iqr_overlap,
        "aggregate_observations": aggregate,
    }


# === Validation-batch loaders and summaries =======================


def load_validation_trajectories(
    results_dir: Path,
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Load trajectory-summary JSONs from a validation results dir.

    Expects files matching ``<strategy>_traj<N>_trajectory_summary.json``.
    Per-step JSONs (``<strategy>_traj<N>_step<M>.json``) are NOT
    consumed here — they are the substrate from which the driver
    already built each trajectory summary.

    Returns
    -------
    trajectories_by_strategy : dict
        ``{strategy: [trajectory_dict, ...]}`` sorted by
        ``trajectory_index`` within each strategy.
    skipped : list
        Filenames that failed to parse.
    """
    results_dir = Path(results_dir)
    trajectories: Dict[str, List[Dict[str, Any]]] = {}
    skipped: List[str] = []
    for path in sorted(results_dir.glob("*_trajectory_summary.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skipped.append(path.name)
            continue
        strategy = rec.get("strategy_name")
        if strategy is None:
            skipped.append(path.name)
            continue
        trajectories.setdefault(strategy, []).append(rec)
    for s in trajectories:
        trajectories[s].sort(key=lambda r: r.get("trajectory_index", 0))
    return trajectories, skipped


def build_validation_summary(
    trajectories_by_strategy: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Post-batch summary of the chapter-5 validation run."""
    strategies = sorted(trajectories_by_strategy.keys())
    n_per_strat = 0
    n_steps = 0
    if strategies:
        first = trajectories_by_strategy[strategies[0]]
        if first:
            n_per_strat = len(first)
            n_steps = len(first[0].get("steps", []))
    total_calls = sum(
        len(t.get("steps", []))
        for trajs in trajectories_by_strategy.values()
        for t in trajs
    )

    per_strategy: Dict[str, Any] = {}
    all_reason_counts: Dict[str, int] = {
        "accepted_improvement": 0,
        "accepted_behavioral_change": 0,
        "rejected_regression": 0,
        "rejected_argmax_equivalent": 0,
    }
    total_accept = 0
    total_reject = 0

    for s in strategies:
        trajs = trajectories_by_strategy[s]
        finals = [
            float(t.get("delta_step_cumulative") or 0.0)
            for t in trajs
        ]
        reason_counts: Dict[str, int] = {
            "accepted_improvement": 0,
            "accepted_behavioral_change": 0,
            "rejected_regression": 0,
            "rejected_argmax_equivalent": 0,
        }
        n_acc = 0
        n_rej = 0
        for t in trajs:
            rc = t.get("acceptance_reason_counts") or {}
            for k, v in rc.items():
                reason_counts[k] = reason_counts.get(k, 0) + int(v)
                if k.startswith("accepted_"):
                    n_acc += int(v)
                elif k.startswith("rejected_"):
                    n_rej += int(v)
        n_moved = sum(
            1 for t in trajs
            if t.get("final_incumbent_hash") != H_EOH_CODE_HASH
        )
        per_strategy[s] = {
            "n_trajectories": len(trajs),
            "mean_delta_step_cumulative": (
                float(np.mean(finals)) if finals else 0.0
            ),
            "median_delta_step_cumulative": (
                float(np.median(finals)) if finals else 0.0
            ),
            "trajectory_final_deltas": finals,
            "n_accepted_steps": n_acc,
            "n_rejected_steps": n_rej,
            "acceptance_rate": (
                n_acc / (n_acc + n_rej)
                if (n_acc + n_rej) > 0 else 0.0
            ),
            "acceptance_reason_counts": reason_counts,
            "n_trajectories_that_moved_off_h_eoh": n_moved,
        }
        for k, v in reason_counts.items():
            all_reason_counts[k] += v
        total_accept += n_acc
        total_reject += n_rej

    ranking = sorted(
        strategies,
        key=lambda s: per_strategy[s]["mean_delta_step_cumulative"],
        reverse=True,
    )

    return {
        "n_strategies": len(strategies),
        "n_trajectories_per_strategy": n_per_strat,
        "n_steps_per_trajectory": n_steps,
        "total_calls": total_calls,
        "strategies": strategies,
        "per_strategy": per_strategy,
        "aggregate": {
            "total_acceptances": total_accept,
            "total_rejections": total_reject,
            "total_accepted_behavioral_change": all_reason_counts[
                "accepted_behavioral_change"
            ],
            "acceptance_reason_distribution": all_reason_counts,
            "cross_strategy_ranking_by_mean_cumulative": ranking,
        },
    }


def build_combined_summary(
    primary_proposals_by_strategy: Dict[str, List[Dict[str, Any]]],
    validation_trajectories_by_strategy: Dict[
        str, List[Dict[str, Any]]
    ],
    *,
    batch_id: str = "chapter5",
    h_eoh_per_instance_by_split: Optional[Dict[str, List[int]]] = None,
) -> Dict[str, Any]:
    """Combined chapter-5 summary covering primary + validation.

    Top-level keys:
        primary_batch          — the build_summary() output.
        validation_batch       — build_validation_summary() output.
        cross_batch_observations — primary-vs-validation ranking
                                   diff and commentary.
    """
    primary = build_summary(
        primary_proposals_by_strategy,
        batch_id=f"{batch_id}_primary_batch_gemini",
        h_eoh_per_instance_by_split=h_eoh_per_instance_by_split,
    )
    validation = build_validation_summary(
        validation_trajectories_by_strategy
    )

    # Primary ranking by trimmed_mean_10pct on delta_step.
    primary_rank = sorted(
        primary["strategies"],
        key=lambda s: primary["per_strategy"][s]["delta_step"][
            "trimmed_mean_10pct"
        ],
        reverse=True,
    )
    # Only keep the strategies present in validation for the
    # comparison.
    validated = set(validation["strategies"])
    primary_rank_restricted = [s for s in primary_rank if s in validated]
    val_rank = validation["aggregate"][
        "cross_strategy_ranking_by_mean_cumulative"
    ]

    # Inversion detection: any pair (a, b) where primary ranks
    # a above b but validation ranks b above a.
    inversions: List[Tuple[str, str]] = []
    for i, a in enumerate(primary_rank_restricted):
        for b in primary_rank_restricted[i + 1:]:
            if val_rank.index(b) < val_rank.index(a):
                inversions.append((a, b))

    cross = {
        "primary_rank_by_trimmed_mean": primary_rank_restricted,
        "validation_rank_by_mean_cumulative": val_rank,
        "rank_inversions": [
            {"primary_higher": a, "validation_higher": b}
            for (a, b) in inversions
        ],
        "note_primary_rank_inversion": bool(inversions),
    }

    return {
        "primary_batch": primary,
        "validation_batch": validation,
        "cross_batch_observations": cross,
    }
