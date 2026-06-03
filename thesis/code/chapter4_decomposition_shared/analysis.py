"""
thesis/code/chapter4_decomposition_shared/analysis.py

Shared analysis layer for the §4.5.3 three-way matched-pair
decomposition (full / gap-only / no-reference). Reusable by both
chapter4_noref and chapter4_gaponly verify scripts and by the
top-level verify_chapter4_decomposition driver.

Functions implement design doc §6.3, §6.4, §6.5:
  - per_cell_delta_step_stats: distribution stats per cell.
  - matched_pair_delta_step: matched-pair mean / median / 95% CI
    bootstrap on the paired difference, indexed by set_index +
    seed_index.
  - cliffs_delta: nonparametric stochastic-dominance index.
  - argmax_equivalence_rate: share of proposals whose argmax
    behavior matches h_eoh on the load-bearing instances.
  - proposal_hash_overlap: count of (sanitization-ok) proposals
    whose code hash appears in both cells.
  - classify_regime: A / B / C / D / mixed per design doc §7.

The per-cell record format expected by these functions is the
chapter-5 per-call JSON record extended with the cell-specific
fields. The relevant subset of fields used here:
  set_index, seed_index, sanitization.status, proposal_hash,
  scoring.delta_step, scoring.delta_gate.

Bootstrap is percentile, n=10,000 resamples, seeded by a fixed
seed for reproducibility (design doc §6.3 implies 10000 in
"bootstrap 95% CI on the mean of the paired difference" without
specifying n; chapter 6 Analysis G uses 10000 and we match).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np


N_BOOT = 10_000
BOOTSTRAP_SEED = 20_260_522
CATASTROPHE_THRESHOLDS = (-50.0, -100.0)


# ---------------------------------------------------------------------------
# Record loading
# ---------------------------------------------------------------------------


def load_records_from_dir(
    directory: Path,
    filename_pattern: str = "*.json",
    exclude: Iterable[str] = ("primary_batch_summary.json", "progress.json"),
) -> List[Dict[str, Any]]:
    """Load every per-call provenance JSON in a directory, sorted by
    (set_index, seed_index)."""
    exclude_set = set(exclude)
    records: List[Dict[str, Any]] = []
    for p in sorted(Path(directory).glob(filename_pattern)):
        if p.name in exclude_set or p.name.startswith("_"):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        records.append(d)
    records.sort(
        key=lambda r: (
            int(r.get("set_index", -1)),
            int(r.get("seed_index", -1)),
        )
    )
    return records


def load_chapter5_full_cell_records(
    directory: Path,
    strategy_name: str = "stratified_representative",
) -> List[Dict[str, Any]]:
    """Load chapter-5's stratified_representative L1 k=4 records as
    the 'full' cell for the three-way decomposition. Filters by
    strategy_name; relies on chapter-5's filename convention
    `{strategy}_{set}_{seed}.json`."""
    return load_records_from_dir(
        directory, filename_pattern=f"{strategy_name}_*_*.json"
    )


# ---------------------------------------------------------------------------
# Distribution statistics
# ---------------------------------------------------------------------------


def _ok_delta_steps(records: Sequence[Dict[str, Any]]) -> List[float]:
    """Return delta_step values from sanitization-ok records only."""
    out: List[float] = []
    for r in records:
        if (r.get("sanitization") or {}).get("status") != "ok":
            continue
        scoring = r.get("scoring") or {}
        ds = scoring.get("delta_step")
        if ds is None:
            continue
        out.append(float(ds))
    return out


def per_cell_delta_step_stats(
    records: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Per-cell distribution stats on delta_step (design doc §6.3).

    Mirrors the chapter-5 / chapter-6 summary format: mean, median,
    p25, p75, IQR, trim10, positive-tail mass, catastrophic-tail
    mass at -50 and -100.
    """
    values = _ok_delta_steps(records)
    n = len(values)
    if n == 0:
        return {"n": 0}
    arr = np.asarray(values, dtype=float)
    p25 = float(np.percentile(arr, 25))
    p75 = float(np.percentile(arr, 75))
    iqr = p75 - p25
    # 10% trimmed mean
    sorted_arr = np.sort(arr)
    trim_count = int(n * 0.1)
    if trim_count > 0 and 2 * trim_count < n:
        trimmed = sorted_arr[trim_count : n - trim_count]
        trim10 = float(trimmed.mean())
    else:
        trim10 = float(arr.mean())
    return {
        "n": n,
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "std": float(arr.std(ddof=1)) if n > 1 else 0.0,
        "min": float(arr.min()),
        "max": float(arr.max()),
        "p10": float(np.percentile(arr, 10)),
        "p25": p25,
        "p75": p75,
        "p90": float(np.percentile(arr, 90)),
        "iqr": iqr,
        "trim10": trim10,
        "positive_tail_mass": float((arr > 0).mean()),
        "catastrophic_tail_mass_at_-50": float((arr < -50.0).mean()),
        "catastrophic_tail_mass_at_-100": float((arr < -100.0).mean()),
    }


# ---------------------------------------------------------------------------
# Matched-pair statistics
# ---------------------------------------------------------------------------


def _key(record: Dict[str, Any]) -> Tuple[int, int]:
    return int(record["set_index"]), int(record["seed_index"])


def matched_pair_delta_step(
    cell_a: Sequence[Dict[str, Any]],
    cell_b: Sequence[Dict[str, Any]],
    *,
    n_boot: int = N_BOOT,
    seed: int = BOOTSTRAP_SEED,
) -> Dict[str, Any]:
    """Matched-pair mean / median / 95% CI on the paired difference
    delta_step(cell_a) - delta_step(cell_b), indexed by
    (set_index, seed_index). Only pairs where both cells have a
    sanitization-ok record contribute.

    Returns a dict with the point estimates and percentile CIs.
    """
    a_map: Dict[Tuple[int, int], float] = {}
    for r in cell_a:
        if (r.get("sanitization") or {}).get("status") != "ok":
            continue
        scoring = r.get("scoring") or {}
        ds = scoring.get("delta_step")
        if ds is not None:
            a_map[_key(r)] = float(ds)
    b_map: Dict[Tuple[int, int], float] = {}
    for r in cell_b:
        if (r.get("sanitization") or {}).get("status") != "ok":
            continue
        scoring = r.get("scoring") or {}
        ds = scoring.get("delta_step")
        if ds is not None:
            b_map[_key(r)] = float(ds)
    common_keys = sorted(a_map.keys() & b_map.keys())
    diffs = np.asarray([a_map[k] - b_map[k] for k in common_keys])
    n = len(diffs)
    if n == 0:
        return {
            "n_paired_observations": 0,
            "mean_paired_diff": None,
            "median_paired_diff": None,
            "mean_ci_95": None,
            "median_ci_95": None,
            "ci_excludes_zero_mean": None,
            "ci_excludes_zero_median": None,
        }
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    samples = diffs[idx]
    mean_samples = samples.mean(axis=1)
    median_samples = np.median(samples, axis=1)
    mean_ci = [
        float(np.percentile(mean_samples, 2.5)),
        float(np.percentile(mean_samples, 97.5)),
    ]
    median_ci = [
        float(np.percentile(median_samples, 2.5)),
        float(np.percentile(median_samples, 97.5)),
    ]
    return {
        "n_paired_observations": n,
        "mean_paired_diff": float(diffs.mean()),
        "median_paired_diff": float(np.median(diffs)),
        "mean_ci_95": mean_ci,
        "median_ci_95": median_ci,
        "ci_excludes_zero_mean": mean_ci[0] > 0 or mean_ci[1] < 0,
        "ci_excludes_zero_median": median_ci[0] > 0 or median_ci[1] < 0,
        "bootstrap_n_resamples": n_boot,
        "bootstrap_seed": seed,
    }


# ---------------------------------------------------------------------------
# Cliff's delta
# ---------------------------------------------------------------------------


def cliffs_delta(
    xs: Sequence[float], ys: Sequence[float]
) -> float:
    """Cliff's δ on two independent distributions. δ ∈ [-1, +1]:
    +1 means every xi > every yj; -1 means every xi < every yj;
    0 means stochastic equivalence. The O(n*m) implementation is
    fine at n=60 each.
    """
    xa = np.asarray(xs, dtype=float)
    ya = np.asarray(ys, dtype=float)
    if xa.size == 0 or ya.size == 0:
        return 0.0
    # broadcast comparison; sum of sign(xi - yj) over all pairs.
    diff_sign = np.sign(xa[:, None] - ya[None, :])
    return float(diff_sign.sum() / (xa.size * ya.size))


# ---------------------------------------------------------------------------
# Argmax equivalence and proposal hash overlap
# ---------------------------------------------------------------------------


def argmax_equivalence_rate(
    records: Sequence[Dict[str, Any]],
    h_eoh_hash: str = "8ca83676ae76",
) -> Dict[str, Any]:
    """Share of sanitization-ok proposals whose proposal_hash equals
    the incumbent hash (i.e., the LLM returned a hash-equivalent
    rewrite). A coarse proxy for argmax-equivalence: chapter 5 / 6
    have richer per-instance argmax checks; this fast version is
    enough for the §4.5.3 decomposition table.
    """
    ok = [
        r for r in records
        if (r.get("sanitization") or {}).get("status") == "ok"
    ]
    if not ok:
        return {"n_ok": 0, "argmax_equivalent_rate": None}
    n_equiv = sum(1 for r in ok if r.get("proposal_hash") == h_eoh_hash)
    return {
        "n_ok": len(ok),
        "argmax_equivalent_rate": n_equiv / len(ok),
        "n_argmax_equivalent": n_equiv,
    }


def proposal_hash_overlap(
    cell_a: Sequence[Dict[str, Any]],
    cell_b: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Count of proposal_hashes that appear in both cells'
    sanitization-ok records. Tests whether the same proposal text
    emerges under different framings (design doc §6.3)."""
    ha = {
        r.get("proposal_hash")
        for r in cell_a
        if (r.get("sanitization") or {}).get("status") == "ok"
        and r.get("proposal_hash") is not None
    }
    hb = {
        r.get("proposal_hash")
        for r in cell_b
        if (r.get("sanitization") or {}).get("status") == "ok"
        and r.get("proposal_hash") is not None
    }
    return {
        "n_distinct_cell_a": len(ha),
        "n_distinct_cell_b": len(hb),
        "n_overlap": len(ha & hb),
        "jaccard": (
            len(ha & hb) / len(ha | hb) if (ha | hb) else None
        ),
    }


# ---------------------------------------------------------------------------
# Three-way regime classification
# ---------------------------------------------------------------------------


def classify_regime(
    full_vs_gaponly: Dict[str, Any],
    gaponly_vs_noref: Dict[str, Any],
) -> str:
    """Per design doc §7, classify the joint matched-pair CI
    pattern into one of:
      A monotonic        — both CIs exclude zero, both positive
                           (full > gap-only > no-reference)
      B code-matters     — (full - gap-only) CI excludes zero positive;
                           (gap-only - no-reference) CI includes zero
      C gap-suffices     — (full - gap-only) CI includes zero;
                           (gap-only - no-reference) CI excludes zero
                           positive
      D irrelevant       — both CIs include zero
      mixed              — any other configuration (e.g. CIs
                           negative, non-monotonic).

    Note on sign: §7's prose convention is "full > gap-only" => the
    paired difference (full - gap-only) is positive. So
    "excludes_zero with positive sign" = CI lower bound > 0.
    """
    def _excludes_positive(d: Dict[str, Any]) -> bool:
        ci = d.get("mean_ci_95")
        return ci is not None and ci[0] > 0

    def _excludes_negative(d: Dict[str, Any]) -> bool:
        ci = d.get("mean_ci_95")
        return ci is not None and ci[1] < 0

    def _includes_zero(d: Dict[str, Any]) -> bool:
        ci = d.get("mean_ci_95")
        return ci is not None and ci[0] <= 0 <= ci[1]

    fg = full_vs_gaponly
    gn = gaponly_vs_noref

    if _excludes_positive(fg) and _excludes_positive(gn):
        return "A_monotonic"
    if _excludes_positive(fg) and _includes_zero(gn):
        return "B_code_matters"
    if _includes_zero(fg) and _excludes_positive(gn):
        return "C_gap_suffices"
    if _includes_zero(fg) and _includes_zero(gn):
        return "D_irrelevant"
    if _excludes_negative(fg) or _excludes_negative(gn):
        return "mixed_non_monotonic"
    return "mixed"
