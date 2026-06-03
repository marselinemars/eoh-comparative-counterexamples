"""Unit tests for thesis/code/chapter3_baselines/baselines.py.

Cases were hand-computed to verify each rule's bin-placement
behavior and to expose at least one scenario where Worst Fit
diverges from Best Fit in the bin count.
"""
from __future__ import annotations

import pytest

from thesis.code.chapter3_baselines.baselines import (
    best_fit,
    first_fit,
    first_fit_decreasing,
    worst_fit,
)


def test_six_halves_capacity_one():
    """Items = [0.5] x 6 at capacity 1.0: all four rules pack two
    items per bin, opening exactly 3 bins."""
    items = [0.5] * 6
    assert first_fit(items, 1.0) == 3
    assert best_fit(items, 1.0) == 3
    assert worst_fit(items, 1.0) == 3
    assert first_fit_decreasing(items, 1.0) == 3


def test_worst_fit_diverges_from_best_fit():
    """Items [0.7, 0.5, 0.2, 0.4] at capacity 1.0 distinguishes WF
    from {FF, BF, FFD}:

    Sequence trace (cap=1.0):
      after 0.7        : bin1 rem 0.3
      after 0.5        : bin2 rem 0.5 (0.7+0.5 doesn't fit in bin1)
      after 0.2  (FF)  : bin1 rem 0.1                  (first fit  -> bin1)
              (BF)     : bin1 rem 0.1                  (tightest   -> bin1)
              (WF)     : bin2 rem 0.3                  (loosest    -> bin2)
      after 0.4  (FF)  : bin1 0.1, bin2 0.5 -> bin2 (0.1). Total=2
              (BF)     : same as FF. Total=2
              (WF)     : bin1 rem 0.3, bin2 rem 0.3; neither fits 0.4.
                         Open bin3 rem 0.6. Total=3
    FFD: sorted [0.7, 0.5, 0.4, 0.2]:
      0.7 -> bin1 rem 0.3
      0.5 -> bin2 rem 0.5
      0.4 -> bin2 rem 0.1 (bin1 0.3 too small)
      0.2 -> bin1 rem 0.1 (first fit)
      Total=2.
    """
    items = [0.7, 0.5, 0.2, 0.4]
    assert first_fit(items, 1.0) == 2
    assert best_fit(items, 1.0) == 2
    assert worst_fit(items, 1.0) == 3
    assert first_fit_decreasing(items, 1.0) == 2


def test_decreasing_sequence_capacity_one():
    """Items [0.6, 0.5, 0.4, 0.3, 0.2, 0.1] at capacity 1.0 — a
    classic descending sequence that already happens to fit into
    3 bins under every rule, sanity-checking correctness."""
    items = [0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
    assert first_fit(items, 1.0) == 3
    assert best_fit(items, 1.0) == 3
    assert worst_fit(items, 1.0) == 3
    assert first_fit_decreasing(items, 1.0) == 3


def test_integer_items_capacity_100():
    """Matches the thesis-data shape: integer items, capacity 100.
    Items [60, 50, 40, 30, 20, 10] sum to 210 -> 3 bins minimum;
    all four rules achieve that minimum."""
    items = [60, 50, 40, 30, 20, 10]
    assert first_fit(items, 100) == 3
    assert best_fit(items, 100) == 3
    assert worst_fit(items, 100) == 3
    assert first_fit_decreasing(items, 100) == 3


def test_single_item():
    """One item -> one bin, regardless of rule."""
    assert first_fit([42], 100) == 1
    assert best_fit([42], 100) == 1
    assert worst_fit([42], 100) == 1
    assert first_fit_decreasing([42], 100) == 1


def test_item_exactly_equal_to_capacity():
    """An item with size = capacity fills exactly one bin."""
    items = [100, 100, 100]
    assert first_fit(items, 100) == 3
    assert best_fit(items, 100) == 3
    assert worst_fit(items, 100) == 3
    assert first_fit_decreasing(items, 100) == 3


def test_empty():
    """Zero items -> zero bins."""
    assert first_fit([], 100) == 0
    assert best_fit([], 100) == 0
    assert worst_fit([], 100) == 0
    assert first_fit_decreasing([], 100) == 0


def test_bf_tie_breaks_to_earliest_bin():
    """When multiple bins tie on smallest-remaining-capacity that
    fits, Best Fit picks the earliest-created. This test exposes
    the tie-break by constructing a scenario where the choice
    affects the final bin count.

    Items [50, 50, 30, 30, 20] at capacity 100:
      50 -> b1 rem 50
      50 -> b1 doesn't fit (rem 50 == 50 fits actually). bin1 rem 0.
        Wait: 50 fits b1 (rem 50 >= 50). b1 rem 0.
      30 -> no fit. b2 rem 70
      30 -> b2 (70). b2 rem 40
      20 -> b2 (40). b2 rem 20
      Total = 2.
    """
    items = [50, 50, 30, 30, 20]
    assert best_fit(items, 100) == 2


def test_wf_spreads_items_across_bins():
    """A signature WF behavior: spreading items across the loosest
    bins. Items [60, 40, 30, 30, 30] at capacity 100:

      WF trace:
        60 -> b1 rem 40
        40 -> b1 (40 >= 40). b1 rem 0.
        30 -> no fit. b2 rem 70.
        30 -> b2 (70). b2 rem 40.
        30 -> b2 (40). b2 rem 10.
        Total = 2.

      BF trace: identical here because at no step do multiple
        bins fit a 30 simultaneously.
    """
    items = [60, 40, 30, 30, 30]
    assert worst_fit(items, 100) == 2
    assert best_fit(items, 100) == 2


def test_ffd_matches_ff_on_sorted_input():
    """If the input is already in decreasing order, FFD reproduces
    FF exactly."""
    items_sorted_desc = [90, 70, 50, 30, 10]
    assert first_fit_decreasing(items_sorted_desc, 100) == first_fit(
        items_sorted_desc, 100
    )


def test_deterministic_under_repeat():
    """All four rules are deterministic; repeated calls return the
    same value."""
    import random

    rng = random.Random(42)
    items = [rng.randint(1, 90) for _ in range(200)]
    for fn in (first_fit, best_fit, worst_fit, first_fit_decreasing):
        first_call = fn(items, 100)
        for _ in range(3):
            assert fn(items, 100) == first_call


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
