"""Tests for thesis/code/chapter5/strategies.py.

Run:
    python -m pytest thesis/code/chapter5/tests/test_strategies.py -v
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pytest

from thesis.code.chapter5 import (
    DETERMINISTIC_STRATEGY_NAMES,
    STOCHASTIC_STRATEGY_NAMES,
    STRATEGIES,
    most_discriminative,
    random_discriminative,
    stratified_representative,
    uniform_random,
    worst_only,
    worst_plus_best,
)
from thesis.code.counterexample import CounterexampleSet

REPO_ROOT = Path(__file__).resolve().parents[4]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)
STATS_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool_stats.json"
)

K = 4
ALL_STRATEGY_NAMES = sorted(STRATEGIES.keys())
DET_NAMES = sorted(DETERMINISTIC_STRATEGY_NAMES)
STO_NAMES = sorted(STOCHASTIC_STRATEGY_NAMES)


@pytest.fixture(scope="module")
def pool() -> CounterexampleSet:
    return CounterexampleSet.from_json(POOL_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def stats() -> dict:
    return json.loads(STATS_PATH.read_text(encoding="utf-8"))


def _call(name: str, pool: CounterexampleSet, k: int, seed: int = 0):
    strategy = STRATEGIES[name]
    if name in STOCHASTIC_STRATEGY_NAMES:
        return strategy(pool, k, rng=np.random.default_rng(seed))
    return strategy(pool, k)


# --- Baseline guardrail -----------------------------------------------

def test_pool_stats_match_committed_file(pool, stats):
    """If the pool is ever regenerated with different contents, every
    strategy test below needs re-review. This test is the canary."""
    wins = sum(1 for c in pool if c.gap > 0)
    losses = sum(1 for c in pool if c.gap < 0)
    ties = sum(1 for c in pool if c.gap == 0)
    assert wins == stats["wins"] == 12
    assert losses == stats["losses"] == 16
    assert ties == stats["ties"] == 2
    assert min(c.gap for c in pool) == stats["min_gap"] == -25
    assert max(c.gap for c in pool) == stats["max_gap"] == 14
    assert len(pool) == 30


def test_strategies_registry_and_frozensets():
    assert set(STRATEGIES.keys()) == {
        "uniform_random",
        "worst_only",
        "worst_plus_best",
        "most_discriminative",
        "random_discriminative",
        "stratified_representative",
    }
    assert (
        DETERMINISTIC_STRATEGY_NAMES | STOCHASTIC_STRATEGY_NAMES
        == set(STRATEGIES.keys())
    )
    assert DETERMINISTIC_STRATEGY_NAMES & STOCHASTIC_STRATEGY_NAMES == set()


# --- Universal properties (parametrized over all 6 strategies) --------

@pytest.mark.parametrize("name", ALL_STRATEGY_NAMES)
def test_returns_counterexample_set_of_exactly_k(pool, name):
    result = _call(name, pool, K)
    assert isinstance(result, CounterexampleSet)
    assert len(result) == K


@pytest.mark.parametrize("name", ALL_STRATEGY_NAMES)
def test_no_duplicate_instance_ids_within_result(pool, name):
    result = _call(name, pool, K)
    ids = [c.instance_id for c in result]
    assert len(set(ids)) == K


@pytest.mark.parametrize("name", ALL_STRATEGY_NAMES)
def test_result_items_are_pool_objects_by_identity(pool, name):
    result = _call(name, pool, K)
    pool_items = list(pool)
    pool_ids = {c.instance_id for c in pool_items}
    for c in result:
        assert c.instance_id in pool_ids
        assert any(c is p for p in pool_items), (
            f"Returned counterexample {c.instance_id!r} is not the "
            "same object as any pool counterexample — strategies must "
            "preserve object identity"
        )


# --- Determinism properties --------------------------------------------

@pytest.mark.parametrize("name", DET_NAMES)
def test_deterministic_strategy_is_byte_identical(pool, name):
    strategy = STRATEGIES[name]
    a = strategy(pool, K).to_json()
    b = strategy(pool, K).to_json()
    assert a == b


@pytest.mark.parametrize("name", STO_NAMES)
def test_stochastic_strategy_differs_across_seeds(pool, name):
    strategy = STRATEGIES[name]
    a = strategy(pool, K, rng=np.random.default_rng(0))
    b = strategy(pool, K, rng=np.random.default_rng(1))
    ids_a = [c.instance_id for c in a]
    ids_b = [c.instance_id for c in b]
    assert ids_a != ids_b, (
        f"{name} produced the same instance_ids for seeds 0 and 1 — "
        "either a genuine collision or the rng is not actually being used"
    )


@pytest.mark.parametrize("name", STO_NAMES)
def test_stochastic_strategy_is_reproducible_with_same_seed(pool, name):
    strategy = STRATEGIES[name]
    a = strategy(pool, K, rng=np.random.default_rng(7))
    b = strategy(pool, K, rng=np.random.default_rng(7))
    assert a.to_json() == b.to_json()


@pytest.mark.parametrize("name", STO_NAMES)
def test_stochastic_strategy_rejects_missing_rng(pool, name):
    strategy = STRATEGIES[name]
    with pytest.raises(ValueError):
        strategy(pool, K)


# --- Strategy-specific properties -------------------------------------

def test_worst_only_returns_four_most_negative_gaps(pool):
    result = worst_only(pool, K)
    gaps = sorted(c.gap for c in result)
    assert gaps == [-25, -21, -20, -15]


def test_worst_plus_best_two_worst_two_best(pool):
    result = worst_plus_best(pool, K)
    gaps = [c.gap for c in result]
    # Return order: 2 worst (gap ascending), then 2 best (gap descending)
    assert gaps == [-25, -21, 14, 13]


def test_worst_plus_best_requires_even_k(pool):
    with pytest.raises(ValueError, match="even"):
        worst_plus_best(pool, 3)


def test_most_discriminative_top_four_abs_gaps(pool):
    result = most_discriminative(pool, K)
    abs_gaps = sorted((abs(c.gap) for c in result), reverse=True)
    assert abs_gaps == [25, 21, 20, 15]


def test_most_discriminative_collides_with_worst_only_on_this_pool(pool):
    """The four largest-magnitude gaps on this pool are all negative
    (|-25|, |-21|, |-20|, |-15| all exceed the max positive gap +14),
    so worst_only and most_discriminative return the same set."""
    a = worst_only(pool, K)
    b = most_discriminative(pool, K)
    assert a.to_json() == b.to_json()


def test_random_discriminative_threshold_is_six_on_this_pool(pool):
    abs_gaps = np.array([abs(c.gap) for c in pool])
    threshold = float(np.median(abs_gaps))
    assert threshold == 6.0


def test_random_discriminative_respects_filter(pool):
    """On this pool, median(|gap|)=6 and 17 items have |gap|≥6, so
    every returned item must be at or above the threshold. The
    warnings.simplefilter below guards against any spurious warnings
    from the strategy; there is no fallback path."""
    threshold = 6.0
    filter_size = sum(1 for c in pool if abs(c.gap) >= threshold)
    assert filter_size >= K  # sanity

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = random_discriminative(pool, K, rng=np.random.default_rng(42))

    for c in result:
        assert abs(c.gap) >= threshold, (
            f"instance_id={c.instance_id} has |gap|={abs(c.gap)} "
            f"< threshold {threshold}"
        )


# --- stratified_representative on the committed pool ------------------

def test_stratified_representative_allocation_on_committed_pool(pool):
    """With σ ≈ 9.703 on the committed pool: strata sizes
    (strong_wins=3, strong_losses=6, ties_and_small=21). Proportional
    allocation for k=4 gives floors (0, 0, 2), remainder 2 distributed
    by priority (strong_wins > strong_losses > ties_and_small), final
    allocation (strong_wins=1, strong_losses=1, ties_and_small=2)."""
    gaps = np.array([c.gap for c in pool], dtype=float)
    sigma = float(np.std(gaps, ddof=0))

    # Verify strata sizes on this pool (sanity check pinning σ∈(8,11])
    strong_wins_pool = [c for c in pool if c.gap >= sigma]
    strong_losses_pool = [c for c in pool if c.gap <= -sigma]
    ties_and_small_pool = [c for c in pool if abs(c.gap) < sigma]
    assert len(strong_wins_pool) == 3
    assert len(strong_losses_pool) == 6
    assert len(ties_and_small_pool) == 21

    result = stratified_representative(
        pool, K, rng=np.random.default_rng(42)
    )

    strong_wins_count = sum(1 for c in result if c.gap >= sigma)
    strong_losses_count = sum(1 for c in result if c.gap <= -sigma)
    ties_and_small_count = sum(1 for c in result if abs(c.gap) < sigma)

    assert strong_wins_count == 1
    assert strong_losses_count == 1
    assert ties_and_small_count == 2


def test_stratified_representative_result_order_is_by_stratum(pool):
    """Return order convention: strong_wins draws, then strong_losses,
    then ties_and_small. Verify allocation (1,1,2) produces the
    expected ordered class signature."""
    gaps = np.array([c.gap for c in pool], dtype=float)
    sigma = float(np.std(gaps, ddof=0))

    result = stratified_representative(
        pool, K, rng=np.random.default_rng(42)
    )
    items = list(result)
    # position 0: strong_wins (gap >= sigma)
    assert items[0].gap >= sigma
    # position 1: strong_losses (gap <= -sigma)
    assert items[1].gap <= -sigma
    # positions 2,3: ties_and_small
    assert abs(items[2].gap) < sigma
    assert abs(items[3].gap) < sigma


def test_stratified_representative_empty_strong_wins_stratum():
    """Covers the empty-stratum path in _allocate_strata.

    Synthetic pool where σ induces strata (strong_wins=0,
    strong_losses=3, ties_and_small=4). Under the refactored logic,
    strong_wins is excluded from the remainder ranking, so the +1
    remainder goes to the next-priority non-empty stratum
    (strong_losses). Expected final allocation: (0, 2, 2).
    """
    from thesis.code.counterexample import Counterexample

    synth_gaps = [-15, -12, -10, 0, 1, -2, 2]
    items = [
        Counterexample.from_bin_counts(
            instance_id=f"synthetic_empty_sw:i_{i}",
            candidate_hash="c" * 12,
            reference_hash="r" * 12,
            candidate_bins_used=100,
            reference_bins_used=100 + g,
        )
        for i, g in enumerate(synth_gaps)
    ]
    synth_pool = CounterexampleSet(items=items)

    # Compute sigma inline and verify the expected partition.
    sigma = float(np.std(np.array(synth_gaps, dtype=float), ddof=0))
    strong_wins_pool = [c for c in synth_pool if c.gap >= sigma]
    strong_losses_pool = [c for c in synth_pool if c.gap <= -sigma]
    ties_and_small_pool = [c for c in synth_pool if abs(c.gap) < sigma]
    assert len(strong_wins_pool) == 0
    assert len(strong_losses_pool) == 3
    assert len(ties_and_small_pool) == 4

    result = stratified_representative(
        synth_pool, 4, rng=np.random.default_rng(0)
    )

    # Allocation per stratum
    strong_wins_count = sum(1 for c in result if c.gap >= sigma)
    strong_losses_count = sum(1 for c in result if c.gap <= -sigma)
    ties_and_small_count = sum(1 for c in result if abs(c.gap) < sigma)
    assert strong_wins_count == 0
    assert strong_losses_count == 2
    assert ties_and_small_count == 2

    # No duplicates, correct length, all from non-empty strata.
    assert len(result) == 4
    assert len({c.instance_id for c in result}) == 4
    for c in result:
        assert c.gap < sigma or c.gap > -sigma  # not from empty strong_wins
        # Stronger form: every returned item is in strong_losses or ties_and_small.
        in_strong_losses = c.gap <= -sigma
        in_ties_and_small = abs(c.gap) < sigma
        assert in_strong_losses or in_ties_and_small


def test_stratified_representative_allocation_invariants_on_random_pools():
    """Randomized smoke test: for 100 synthetic pools varying in size
    and k, the allocation must sum to k and never exceed any stratum
    size, and the returned set must contain no duplicates.
    """
    from thesis.code.counterexample import Counterexample

    master = np.random.default_rng(20_260_420)
    sizes = [5, 10, 20, 30]
    ks = [2, 3, 4, 6]
    executed = 0
    for i in range(100):
        pool_size = int(master.choice(sizes))
        valid_ks = [ki for ki in ks if ki <= pool_size]
        k = int(master.choice(valid_ks))

        # Generate random integer gaps wide enough to guarantee σ > 0
        # with high probability on pool_size >= 5.
        gaps = master.integers(low=-10, high=11, size=pool_size)
        if len(set(gaps.tolist())) < 2:
            # Degenerate σ=0 (identical gaps) would make strong_wins
            # and strong_losses overlap on gap=0 items. Skip these
            # exceedingly rare draws.
            continue

        items = [
            Counterexample.from_bin_counts(
                instance_id=f"synthetic_random:pool{i}_item{j}",
                candidate_hash="c" * 12,
                reference_hash="r" * 12,
                candidate_bins_used=100,
                reference_bins_used=100 + int(g),
            )
            for j, g in enumerate(gaps)
        ]
        test_pool = CounterexampleSet(items=items)

        result = stratified_representative(
            test_pool, k, rng=np.random.default_rng(i)
        )

        # Correct length and no duplicates.
        assert len(result) == k, (
            f"pool {i} (size={pool_size}, k={k}): got {len(result)}"
        )
        ids = [c.instance_id for c in result]
        assert len(set(ids)) == k, f"pool {i}: duplicate ids in result"

        # Stratum-size invariant.
        sigma = float(np.std(np.array([c.gap for c in test_pool],
                                      dtype=float), ddof=0))
        strata_sizes = {
            "strong_wins":    sum(1 for c in test_pool if c.gap >= sigma),
            "strong_losses":  sum(1 for c in test_pool if c.gap <= -sigma),
            "ties_and_small": sum(1 for c in test_pool if abs(c.gap) < sigma),
        }
        result_counts = {
            "strong_wins":    sum(1 for c in result if c.gap >= sigma),
            "strong_losses":  sum(1 for c in result if c.gap <= -sigma),
            "ties_and_small": sum(1 for c in result if abs(c.gap) < sigma),
        }
        for name in strata_sizes:
            assert result_counts[name] <= strata_sizes[name], (
                f"pool {i} (size={pool_size}, k={k}): "
                f"{name} alloc {result_counts[name]} > size "
                f"{strata_sizes[name]}"
            )
        executed += 1

    assert executed > 80, (
        f"Expected most of 100 iterations to execute; only {executed} did "
        "(degenerate-σ skips should be rare)."
    )


def test_stratified_representative_committed_pool_unchanged_after_refactor(pool):
    """Refactor-safety guardrail: on the chapter-5 committed pool,
    stratified_representative with seed=42 must produce exactly the
    instance_ids recorded in Task 3 ("implement selection strategies"),
    byte-identical. If this test fails the _allocate_strata refactor
    changed behavior on non-empty strata."""
    result = stratified_representative(
        pool, K, rng=np.random.default_rng(42)
    )
    recorded = [
        ("thesis_train_select:thesis_train_select_5k_11",  12),
        ("thesis_train_select:thesis_train_select_5k_25", -15),
        ("thesis_train_select:thesis_train_select_5k_12",  -3),
        ("thesis_train_select:thesis_train_select_5k_18",   0),
    ]
    got = [(c.instance_id, c.gap) for c in result]
    assert got == recorded, (
        f"Committed-pool output changed after refactor.\n"
        f"  expected: {recorded}\n"
        f"  got:      {got}"
    )
