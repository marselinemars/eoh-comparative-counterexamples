"""
thesis/code/chapter3_baselines/baselines.py

Four classical bin-packing heuristics for the §3.3 incumbent
characterization (W-E4 of the examiner-response revision sprint;
governed by thesis/writing/chapter3_incumbent_baselines_design.md).

Each function returns the integer count of bins used to pack a
sequence of items into bins of fixed capacity. Items are placed in
the order they arrive (online) for FF / BF / WF. FFD sorts items in
decreasing size first (offline) and then applies FF.

Tie-breaking (per design doc §3): when multiple open bins fit and
have equal "best" remaining capacity (for BF / WF), choose the one
with the smallest bin-creation index (earliest first). numpy's
argmin/argmax break ties by returning the first occurrence, so this
behavior comes for free.

The implementations use a numpy array of remaining-capacity slots
grown lazily via a preallocated buffer (no Python-level append; no
hidden allocation costs). Pure-Python iteration over items keeps
the code readable; the per-item bin-search is vectorized.
"""
from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np


def _pack(
    items: Sequence[float],
    capacity: float,
    rule: str,
) -> int:
    """Generic online packer. `rule` selects which bin to place into.

    Returns the integer count of bins opened. Behavior:
      - rule == "ff"   : first bin whose remaining capacity >= item
      - rule == "bf"   : among bins that fit, the one with smallest
                          remaining capacity (tightest fit)
      - rule == "wf"   : among bins that fit, the one with largest
                          remaining capacity (loosest fit)
    Ties broken by bin-creation order (earliest first).
    """
    n = len(items)
    # Preallocate enough slots for the worst case (one bin per item).
    rem = np.zeros(n, dtype=np.float64)
    n_open = 0
    for item in items:
        if n_open == 0:
            rem[0] = capacity - item
            n_open = 1
            continue
        view = rem[:n_open]
        mask = view >= item
        if mask.any():
            if rule == "ff":
                idx = int(np.argmax(mask))  # first True
            elif rule == "bf":
                # Smallest remaining capacity among fitting bins.
                # Set non-fitting bins to +inf so argmin ignores them.
                masked = np.where(mask, view, np.inf)
                idx = int(np.argmin(masked))
            elif rule == "wf":
                # Largest remaining capacity among fitting bins.
                # Set non-fitting bins to -inf so argmax ignores them.
                masked = np.where(mask, view, -np.inf)
                idx = int(np.argmax(masked))
            else:
                raise ValueError(f"Unknown rule {rule!r}")
            rem[idx] -= item
        else:
            rem[n_open] = capacity - item
            n_open += 1
    return n_open


def first_fit(items: Sequence[float], capacity: float = 100.0) -> int:
    """First Fit: place each item in the first open bin with enough
    remaining capacity; else open a new bin."""
    return _pack(items, capacity, "ff")


def best_fit(items: Sequence[float], capacity: float = 100.0) -> int:
    """Best Fit: place each item in the open bin with the smallest
    remaining capacity that still fits; else open a new bin.
    Ties broken by bin creation order (earliest first)."""
    return _pack(items, capacity, "bf")


def worst_fit(items: Sequence[float], capacity: float = 100.0) -> int:
    """Worst Fit: place each item in the open bin with the largest
    remaining capacity that still fits; else open a new bin.
    Ties broken by bin creation order (earliest first)."""
    return _pack(items, capacity, "wf")


def first_fit_decreasing(items: Sequence[float], capacity: float = 100.0) -> int:
    """First Fit Decreasing: sort items by size in decreasing order,
    then apply First Fit. This is an OFFLINE algorithm (requires
    advance knowledge of all items); §3.3 prose must label it so."""
    sorted_items = sorted(items, reverse=True)
    return first_fit(sorted_items, capacity)
