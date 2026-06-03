"""
thesis/code/chapter5/instance_summary.py

Per-instance statistical summary rendered into the chapter-5
prompt. Raises the information floor from "bare instance ID" to
"Level 3 instance summary" per the 2026-04-23 decisions-log entry
("Chapter 5 prompt raised from bare instance ID to instance-summary
(Level 3)") and the corresponding glossary entry ("Instance
summary" in thesis/docs/05_glossary.md).

Two public entry points:
  build_instance_summary(instance, capacity=100) -> InstanceSummary
  render_instance_summary(summary, instance_id_anonymized,
                          incumbent_bins, reference_bins) -> str

Separation of concerns: Counterexample carries only bin counts and
hashes, not item data. Item sequences are loaded from the split
(see thesis/code/splits.py::load_split) by the caller (the prompt
builder). InstanceSummary reduces one instance's items to the
fields that the chapter-5 prompt shows the LLM.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np


@dataclass(frozen=True)
class InstanceSummary:
    """Level-3 summary of one bp_online instance.

    Integers are integers (items are integer-valued in bp_online).
    `mean` and `std` are stored as floats and rendered to 1 decimal.
    `histogram` is always 10 buckets wide, bucket width
    capacity / 10, left-closed / right-open except the last bucket
    which is inclusive on the upper bound.
    """

    n_items: int
    capacity: int
    mean: float
    std: float
    min_: int
    max_: int
    q25: int
    q50: int
    q75: int
    p10: int
    p90: int
    histogram: List[int]
    largest_5: List[int]
    smallest_5: List[int]
    near_median_5: List[int]
    random_5: List[int]


def _seed_from_instance_id(instance_id: str) -> int:
    """Deterministic 64-bit seed derived from instance_id. Used for
    the `random_5` sample so the prompt is byte-reproducible."""
    return int(
        hashlib.sha256(instance_id.encode("utf-8")).hexdigest()[:16], 16
    )


def build_instance_summary(
    instance: Dict[str, Any], capacity: int = 100
) -> InstanceSummary:
    """Reduce one instance's items to a Level-3 summary.

    Parameters
    ----------
    instance:
        Dict in the shape returned by
        `thesis.code.splits.load_split` per-instance entry. Must
        contain keys ``instance_id``, ``items``. If ``capacity`` is
        present on the instance, it wins over the ``capacity``
        parameter; otherwise the parameter default applies.
    capacity:
        Bin capacity (default 100 matches bp_online standard).

    Returns
    -------
    InstanceSummary with all fields populated.
    """
    items: List[int] = [int(x) for x in instance["items"]]
    n = len(items)
    cap = int(instance.get("capacity", capacity))
    arr = np.asarray(items, dtype=float)

    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=0))
    mn = int(np.min(arr))
    mx = int(np.max(arr))
    q25 = int(round(float(np.percentile(arr, 25))))
    q50 = int(round(float(np.percentile(arr, 50))))
    q75 = int(round(float(np.percentile(arr, 75))))
    p10 = int(round(float(np.percentile(arr, 10))))
    p90 = int(round(float(np.percentile(arr, 90))))

    # Histogram: 10 buckets, width cap/10, last bucket inclusive on
    # upper bound. np.histogram's default is left-closed / right-open
    # except the last bucket, which matches the requirement.
    edges = np.linspace(0, cap, 11)
    hist_counts, _ = np.histogram(arr, bins=edges)
    histogram = [int(x) for x in hist_counts]

    # largest 5 descending, smallest 5 ascending
    sorted_asc = sorted(items)
    smallest_5 = sorted_asc[: min(5, n)]
    largest_5 = list(reversed(sorted_asc[-min(5, n) :]))

    # Near-median 5: smallest |item - median|, tiebreak by item asc
    near_median_5 = sorted(
        items, key=lambda x: (abs(x - q50), x)
    )[: min(5, n)]

    # Random 5: deterministic, seeded by sha256(instance_id).
    rng = np.random.default_rng(
        _seed_from_instance_id(str(instance["instance_id"]))
    )
    sample_size = min(5, n)
    idx = rng.choice(n, size=sample_size, replace=False)
    random_5 = [items[int(i)] for i in idx]

    return InstanceSummary(
        n_items=n,
        capacity=cap,
        mean=mean,
        std=std,
        min_=mn,
        max_=mx,
        q25=q25,
        q50=q50,
        q75=q75,
        p10=p10,
        p90=p90,
        histogram=histogram,
        largest_5=largest_5,
        smallest_5=smallest_5,
        near_median_5=near_median_5,
        random_5=random_5,
    )


def render_instance_summary(
    summary: InstanceSummary,
    instance_id_anonymized: str,
    incumbent_bins: int,
    reference_bins: int,
) -> str:
    """Render one instance-summary block as it appears in the
    chapter-5 prompt. See chapter5_design.md §7.

    `diff` convention: ref_bins − cand_bins (= +gap), per the
    2026-04-21 decisions-log fix. Positive diff means the incumbent
    used fewer bins.
    """
    diff = reference_bins - incumbent_bins
    bucket_width = summary.capacity // 10

    # Three-column histogram grid for the first 9 buckets, then the
    # 10th on its own row.
    rows: List[str] = []
    for row_start in range(0, 9, 3):
        cells = []
        for offset in range(3):
            idx = row_start + offset
            lo = idx * bucket_width
            hi = lo + bucket_width
            cells.append(
                f"[{lo:>2}-{hi:>3}]: {summary.histogram[idx]:>4}"
            )
        rows.append("  ".join(cells))
    last_lo = 9 * bucket_width
    last_hi = summary.capacity
    rows.append(
        f"[{last_lo:>2}-{last_hi:>3}]: {summary.histogram[9]:>4}"
    )
    histogram_block = "\n        ".join(rows)

    diff_str = f"{diff:+d}"

    return (
        f"  {instance_id_anonymized}:\n"
        f"    n_items: {summary.n_items}, capacity: {summary.capacity}\n"
        f"    incumbent_bins: {incumbent_bins}, "
        f"reference_bins: {reference_bins}, diff: {diff_str}\n"
        f"    item_distribution:\n"
        f"      mean: {summary.mean:.1f}, std: {summary.std:.1f}, "
        f"min: {summary.min_}, max: {summary.max_}\n"
        f"      quartiles (25/50/75): "
        f"{summary.q25} / {summary.q50} / {summary.q75}\n"
        f"      percentiles (p10/p90): {summary.p10} / {summary.p90}\n"
        f"      histogram (10 buckets of width {bucket_width}):\n"
        f"        {histogram_block}\n"
        f"    item_samples:\n"
        f"      largest 5:       {summary.largest_5}\n"
        f"      smallest 5:      {summary.smallest_5}\n"
        f"      near-median 5:   {summary.near_median_5}\n"
        f"      random 5:        {summary.random_5}"
    )
