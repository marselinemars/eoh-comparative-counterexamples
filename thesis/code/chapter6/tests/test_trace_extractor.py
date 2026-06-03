"""Tests for thesis/code/chapter6/trace_extractor.py.

Run:
    python -m pytest thesis/code/chapter6/tests/test_trace_extractor.py -v
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from thesis.code.chapter6.trace_extractor import (
    NEW_BIN_TOKEN,
    DecisionRecord,
    _final_bins_used,
    extract_incumbent_trace,
)
from thesis.code.evaluation import bins_used, load_heuristic_from_code

# --- Hand-written heuristics for semantics tests -----------------------

# best_fit: prefers the tightest-fitting bin (lowest remaining capacity
# among valid bins).  Returns -capacity so np.argmax picks the smallest.
BEST_FIT_CODE = """
import numpy as np
def score(item, bins):
    return -np.asarray(bins, dtype=float)
"""

# worst_fit: prefers the loosest bin (highest remaining capacity).
# Always opens a new bin when one is available, because unused bins
# are at full capacity and ties break to the lowest index (the first
# unused bin in the preallocated array, which is also the first
# unused bin in creation order).
WORST_FIT_CODE = """
import numpy as np
def score(item, bins):
    return np.asarray(bins, dtype=float)
"""


@pytest.fixture(scope="module")
def best_fit():
    return load_heuristic_from_code(BEST_FIT_CODE, "best_fit_heuristic")


@pytest.fixture(scope="module")
def worst_fit():
    return load_heuristic_from_code(WORST_FIT_CODE, "worst_fit_heuristic")


def _inst(items: List[float], num_items: int, capacity: float = 100.0) -> Dict[str, Any]:
    """Shorthand constructor for a synthetic bp_online instance."""
    return {"capacity": capacity, "num_items": num_items, "items": list(items)}


# --- Test 1: schema and basic run -------------------------------------


def test_schema_and_basic_run(best_fit) -> None:
    """Run on a tiny instance, verify one record per decision and that
    every field has the type and inter-field relationship the
    DecisionRecord docstring promises (margin >= 0, new_bin ==
    (chose == "new"), open_bins is a tuple, etc.).
    """
    instance = _inst(items=[50.0, 30.0, 20.0, 10.0, 5.0], num_items=5)
    records = extract_incumbent_trace(instance, best_fit)

    assert len(records) == len(instance["items"])

    for r in records:
        assert isinstance(r, DecisionRecord)
        assert isinstance(r.idx, int) and r.idx >= 1
        assert isinstance(r.item, float)
        assert isinstance(r.open_bins, tuple)
        assert all(isinstance(c, float) for c in r.open_bins)
        assert isinstance(r.chose, (int, str))
        if isinstance(r.chose, str):
            assert r.chose == NEW_BIN_TOKEN
        else:
            assert 0 <= r.chose < len(r.open_bins)
        assert isinstance(r.score_winner, float)
        assert isinstance(r.score_runner_up, float)
        assert isinstance(r.margin, float)
        assert r.margin >= 0.0
        assert r.margin == r.score_winner - r.score_runner_up
        assert isinstance(r.cap_after, float)
        assert isinstance(r.new_bin, bool)
        assert r.new_bin == (r.chose == NEW_BIN_TOKEN)


# --- Test 2: first-decision semantics ---------------------------------


def test_first_decision_has_only_new_bin_candidate(best_fit) -> None:
    """At arrival index 1 no bin has been opened yet, so the abstract
    candidate set is exactly {new-bin slot}: open_bins is empty,
    chose == "new", new_bin == True, score_runner_up == score_winner,
    and margin == 0.0.
    """
    instance = _inst(items=[50.0], num_items=3)
    records = extract_incumbent_trace(instance, best_fit)

    assert len(records) == 1
    r = records[0]
    assert r.idx == 1
    assert r.item == 50.0
    assert r.open_bins == ()
    assert r.chose == NEW_BIN_TOKEN
    assert r.new_bin is True
    assert r.score_runner_up == r.score_winner
    assert r.margin == 0.0
    assert r.cap_after == 50.0  # capacity (100) − item (50)


# --- Test 3: existing-bin choice on a later decision ------------------


def test_existing_bin_choice(best_fit) -> None:
    """At a later decision where best_fit's tight-fit preference picks
    an already-open bin, chose is an integer position into open_bins,
    new_bin is False, and cap_after = open_bins[chose] - item.
    """
    instance = _inst(items=[50.0, 30.0], num_items=2)
    records = extract_incumbent_trace(instance, best_fit)

    assert len(records) == 2
    r = records[1]
    assert r.idx == 2
    assert r.item == 30.0
    assert r.open_bins == (50.0,)  # bin 0 was opened to cap 50 at step 1
    assert r.chose == 0
    assert isinstance(r.chose, int)
    assert r.new_bin is False
    assert r.cap_after == r.open_bins[r.chose] - r.item
    assert r.cap_after == 20.0


# --- Test 4: new-bin choice on a later decision -----------------------


def test_new_bin_choice_mid_instance(worst_fit) -> None:
    """At a later decision where worst_fit's loose-fit preference opens
    a fresh bin even though an existing open bin is valid for the
    item, chose == "new", new_bin == True, and cap_after =
    capacity - item.
    """
    instance = _inst(items=[50.0, 30.0], num_items=2)
    records = extract_incumbent_trace(instance, worst_fit)

    assert len(records) == 2
    r = records[1]
    assert r.idx == 2
    assert r.item == 30.0
    assert r.open_bins == (50.0,)
    assert r.chose == NEW_BIN_TOKEN
    assert r.new_bin is True
    assert r.cap_after == 70.0  # capacity (100) − item (30)


# --- Test 5: abstract-set dedup of redundant unused bins --------------


def test_abstract_set_deduplicates_unused_bins(worst_fit) -> None:
    """At a decision where the harness's preallocated bin vector
    contains many unused bins all tied at full capacity, the
    abstract candidate set must collapse them to a single new-bin
    slot. Without dedup, score_runner_up would be the (tied)
    maximum and margin would collapse to 0.

    Setup: items=[50, 30] with num_items=5 and worst_fit. At step 2,
    the harness scores [bin0=50, bin1=100, bin2=100, bin3=100,
    bin4=100] → priorities=[50,100,100,100,100]. Without dedup,
    sorted-desc top two are [100, 100] → margin 0. With the §7.2.1
    dedup, the abstract set is {0: 50, "new": 100} → margin 50.
    """
    instance = _inst(items=[50.0, 30.0], num_items=5)
    records = extract_incumbent_trace(instance, worst_fit)

    assert len(records) == 2
    r = records[1]
    assert r.chose == NEW_BIN_TOKEN
    assert r.score_winner == 100.0
    assert r.score_runner_up == 50.0
    assert r.margin == 50.0


# --- Test 6: single-element abstract set at a later decision ----------


def test_single_candidate_abstract_set_margin_zero(best_fit) -> None:
    """When every open bin is too full to fit the item and the
    abstract candidate set therefore contains only the new-bin slot,
    score_runner_up == score_winner and margin == 0.0.

    Setup: items=[80, 80] with num_items=3 and best_fit. At step 2
    the only existing open bin (cap 20) cannot fit the 80-sized
    item, so the abstract set has one element (the new-bin slot).
    """
    instance = _inst(items=[80.0, 80.0], num_items=3)
    records = extract_incumbent_trace(instance, best_fit)

    assert len(records) == 2
    r = records[1]
    assert r.chose == NEW_BIN_TOKEN
    assert r.new_bin is True
    assert r.score_runner_up == r.score_winner
    assert r.margin == 0.0


# --- Test 7: chronological ordering -----------------------------------


def test_records_are_chronological_starting_at_one(best_fit) -> None:
    """The returned list's idx values are strictly increasing by 1
    starting from 1; one record per arrival index, no gaps, no
    reordering.
    """
    instance = _inst(items=[30.0, 30.0, 30.0, 30.0, 30.0], num_items=5)
    records = extract_incumbent_trace(instance, best_fit)

    assert [r.idx for r in records] == list(range(1, len(instance["items"]) + 1))


# --- Test 8: determinism ----------------------------------------------


def test_extractor_is_deterministic(best_fit) -> None:
    """Two extractor calls on the same inputs must return byte-equal
    record sequences. No hidden RNG, no nondeterministic ordering.
    """
    instance = _inst(items=[30.0, 30.0, 30.0, 30.0], num_items=4)
    first = extract_incumbent_trace(instance, best_fit)
    second = extract_incumbent_trace(instance, best_fit)

    assert first == second
    for r1, r2 in zip(first, second):
        assert r1 == r2


# --- Test 9: to_dict round-trip ---------------------------------------


def test_to_dict_schema(best_fit) -> None:
    """to_dict() returns a JSON-safe flat mapping matching
    chapter6_design.md §7.2: tuple → list, the union-typed 'chose'
    field retains its native int-or-str type, no nesting (the trace
    is single-side).
    """
    instance = _inst(items=[50.0, 30.0], num_items=2)
    records = extract_incumbent_trace(instance, best_fit)
    assert len(records) == 2

    # First record: a new-bin decision; chose should serialize as the
    # str "new". Second record: an existing-bin decision; chose
    # should serialize as int 0.
    d0 = records[0].to_dict()
    d1 = records[1].to_dict()

    expected_keys = {
        "idx",
        "item",
        "open_bins",
        "chose",
        "score_winner",
        "score_runner_up",
        "margin",
        "cap_after",
        "new_bin",
    }
    assert set(d0.keys()) == expected_keys
    assert set(d1.keys()) == expected_keys

    assert isinstance(d0["open_bins"], list)
    assert isinstance(d1["open_bins"], list)
    assert d0["open_bins"] == []
    assert d1["open_bins"] == [50.0]

    assert d0["chose"] == NEW_BIN_TOKEN
    assert isinstance(d0["chose"], str)
    assert d0["new_bin"] is True

    assert d1["chose"] == 0
    assert isinstance(d1["chose"], int)
    assert d1["new_bin"] is False


# --- Test 10: harness-alignment with thesis.code.evaluation -----------


@pytest.mark.parametrize(
    "items, num_items",
    [
        ([30.0, 30.0, 30.0, 30.0], 4),
        ([50.0, 40.0, 30.0, 20.0, 10.0], 5),
        ([100.0], 3),
        ([30.0, 30.0, 50.0], 2),
    ],
    ids=["all-30s", "descending-items", "single-large-item", "tight-pool"],
)
def test_final_bins_used_matches_harness(
    best_fit, worst_fit, items: List[float], num_items: int
) -> None:
    """For every synthetic instance in the parametrize set, the
    extractor's internal final-bin-count helper agrees with
    ``thesis.code.evaluation.bins_used`` for both heuristics.

    This is the gating check: the extractor replays the harness
    decision-for-decision, so the integer bin count it derives at
    the end of replay must equal what the harness's
    ``online_binpack`` would have returned on the same
    (instance, heuristic) pair. A divergence here would mean the
    chapter 6 trace data is silently inconsistent with the rest of
    the thesis's scoring.
    """
    instance = _inst(items=items, num_items=num_items)

    for name, h in [("best_fit", best_fit), ("worst_fit", worst_fit)]:
        expected = bins_used(h, instance)
        actual = _final_bins_used(instance, h)
        assert expected == actual, (
            f"{name}: extractor final bin count {actual} != harness "
            f"bin count {expected} for items={items} num_items={num_items}"
        )
