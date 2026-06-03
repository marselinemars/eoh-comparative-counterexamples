"""
thesis/code/chapter5/strategies.py

The six chapter 5 counterexample-selection strategies per
`thesis/writing/chapter5_design.md` §5.

Each strategy is a pure function of signature

    strategy(pool, k, rng=None) -> CounterexampleSet

where `pool` is a `CounterexampleSet`, `k` is a positive integer, and
`rng` is an `np.random.Generator` (required for stochastic strategies,
ignored for deterministic ones). Returned set always has length
exactly `k`, contains no duplicates by instance_id, and preserves
object identity of Counterexample items drawn from `pool`.

Deterministic strategies break ties by ascending `instance_id` as a
stable secondary key, so outputs are reproducible byte-for-byte
regardless of pool input order. Stochastic strategies draw exclusively
from `rng`; module-level randomness is never touched.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List

import numpy as np

from thesis.code.counterexample import Counterexample, CounterexampleSet


def _validate_k(pool: CounterexampleSet, k: int) -> None:
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")
    if k > len(pool):
        raise ValueError(
            f"k={k} exceeds pool size {len(pool)}; cannot draw "
            "without replacement"
        )


# --- 5.1 uniform_random ------------------------------------------------

def uniform_random(
    pool: CounterexampleSet,
    k: int,
    rng: np.random.Generator | None = None,
) -> CounterexampleSet:
    """Draw `k` counterexamples uniformly at random without replacement.

    Stochastic. Returns counterexamples in the order `rng` produced
    their indices.
    """
    if rng is None:
        raise ValueError("uniform_random requires an rng (np.random.Generator)")
    _validate_k(pool, k)
    indices = rng.choice(len(pool), size=k, replace=False)
    return CounterexampleSet(items=[pool[int(i)] for i in indices])


# --- 5.2 worst_only ----------------------------------------------------

def worst_only(
    pool: CounterexampleSet,
    k: int,
    rng: np.random.Generator | None = None,
) -> CounterexampleSet:
    """Return the `k` counterexamples where the candidate loses hardest.

    Sort pool ascending by (gap, instance_id); take first `k`. If the
    pool has fewer than `k` losses (gap < 0), pad with ties (gap == 0)
    then with smallest-gap wins (gap > 0), each class sorted ascending
    by (gap, instance_id). Deterministic; `rng` is ignored.
    """
    _validate_k(pool, k)
    items = list(pool)
    losses = sorted(
        (c for c in items if c.gap < 0),
        key=lambda c: (c.gap, c.instance_id),
    )
    ties = sorted(
        (c for c in items if c.gap == 0),
        key=lambda c: (c.gap, c.instance_id),
    )
    wins = sorted(
        (c for c in items if c.gap > 0),
        key=lambda c: (c.gap, c.instance_id),
    )
    combined = losses + ties + wins
    return CounterexampleSet(items=combined[:k])


# --- 5.3 worst_plus_best -----------------------------------------------

def worst_plus_best(
    pool: CounterexampleSet,
    k: int,
    rng: np.random.Generator | None = None,
) -> CounterexampleSet:
    """Return the `k/2` smallest-gap counterexamples and the `k/2`
    largest-gap counterexamples.

    Requires `k` even. Deterministic; ties broken by instance_id
    ascending. Return order: all `k/2` worst first (gap ascending),
    then all `k/2` best (gap descending). Raises ValueError if the
    two halves would overlap.
    """
    if k % 2 != 0:
        raise ValueError(f"worst_plus_best requires k even, got {k}")
    _validate_k(pool, k)
    items = list(pool)
    by_gap_asc = sorted(items, key=lambda c: (c.gap, c.instance_id))
    by_gap_desc = sorted(items, key=lambda c: (-c.gap, c.instance_id))
    half = k // 2
    worst: List[Counterexample] = by_gap_asc[:half]
    best: List[Counterexample] = by_gap_desc[:half]
    worst_ids = {c.instance_id for c in worst}
    best_ids = {c.instance_id for c in best}
    overlap = worst_ids & best_ids
    if overlap:
        raise ValueError(
            f"worst_plus_best: worst and best halves overlap on "
            f"{sorted(overlap)}. Pool may be too small for this k or "
            "have collapsed gap structure."
        )
    return CounterexampleSet(items=worst + best)


# --- 5.4 most_discriminative -------------------------------------------

def most_discriminative(
    pool: CounterexampleSet,
    k: int,
    rng: np.random.Generator | None = None,
) -> CounterexampleSet:
    """Return the `k` counterexamples with largest |gap|.

    Sort by (|gap| descending, instance_id ascending); take first `k`.
    Deterministic; `rng` is ignored.
    """
    _validate_k(pool, k)
    items = list(pool)
    ranked = sorted(items, key=lambda c: (-abs(c.gap), c.instance_id))
    return CounterexampleSet(items=ranked[:k])


# --- 5.5 random_discriminative -----------------------------------------

def random_discriminative(
    pool: CounterexampleSet,
    k: int,
    rng: np.random.Generator | None = None,
) -> CounterexampleSet:
    """Draw `k` uniformly from {c ∈ pool : |c.gap| ≥ median(|gap|)}.

    Threshold is the median of `abs(gap)` across the full pool,
    computed once. Stochastic.

    Filter size is guaranteed to be >= ceil(len(pool) / 2) by the
    median-of-|gap| construction; this is >= k whenever
    k <= ceil(len(pool) / 2). For the Chapter 5 regime (k=4, n=30)
    the invariant holds trivially. The assertion below guards
    against accidental misuse outside this regime.
    """
    if rng is None:
        raise ValueError(
            "random_discriminative requires an rng (np.random.Generator)"
        )
    _validate_k(pool, k)
    items = list(pool)
    abs_gaps = np.array([abs(c.gap) for c in items])
    threshold = float(np.median(abs_gaps))
    filtered_indices = [
        i for i, c in enumerate(items) if abs(c.gap) >= threshold
    ]
    assert len(filtered_indices) >= k, (
        f"random_discriminative invariant violated: filter size "
        f"{len(filtered_indices)} < k={k}. The median-|gap| filter "
        f"guarantees filter size >= ceil(len(pool)/2) = "
        f"{math.ceil(len(pool)/2)}; k must satisfy "
        f"k <= ceil(len(pool)/2)."
    )
    chosen = rng.choice(filtered_indices, size=k, replace=False)
    return CounterexampleSet(items=[items[int(i)] for i in chosen])


# --- 5.6 stratified_representative -------------------------------------

_STRATUM_ORDER = ("strong_wins", "strong_losses", "ties_and_small")


def _allocate_strata(
    strata_sizes: Dict[str, int], k: int
) -> Dict[str, int]:
    """Proportional allocation with priority-ranked remainder
    distribution, restricted to non-empty strata.

    Empty strata receive allocation 0 (from the floor step, since
    `k * 0 / N = 0`) and are excluded from the remainder-ranking, so
    they cannot receive +1 increments. With this restriction the
    allocation provably respects stratum-size caps: for each non-empty
    stratum `s` with size `n_s` and target `k·n_s/N`, `floor < n_s`
    whenever `k < N` (strict); and when `k = N` every target is
    integer, so `r = 0` and no +1 is ever assigned. The two
    assertions below pin the invariant. See design §5.6 and the
    decisions-log entry 2026-04-20 ("strata anchored at zero").
    """
    total = sum(strata_sizes.values())
    if total < k:
        raise ValueError(
            f"stratified_representative: pool size {total} < k={k}"
        )

    targets = {n: k * strata_sizes[n] / total for n in _STRATUM_ORDER}
    allocations = {n: int(targets[n]) for n in _STRATUM_ORDER}  # floor
    fracs = {n: targets[n] - allocations[n] for n in _STRATUM_ORDER}
    r = k - sum(allocations.values())

    priority_idx = {n: i for i, n in enumerate(_STRATUM_ORDER)}
    # Primary: priority class ascending (strong_wins first).
    # Secondary: fractional part descending.
    # Tertiary: priority class ascending (tie-break within fraction).
    # Only non-empty strata are eligible for +1 increments — empty
    # strata cannot receive draws, so they must not consume remainder.
    non_empty = [n for n in _STRATUM_ORDER if strata_sizes[n] > 0]
    ranked = sorted(
        non_empty,
        key=lambda n: (priority_idx[n], -fracs[n], priority_idx[n]),
    )
    for name in ranked[:r]:
        allocations[name] += 1

    assert sum(allocations.values()) == k, (
        f"stratified allocation sum {sum(allocations.values())} != k={k}"
    )
    assert all(
        allocations[s] <= strata_sizes[s]
        for s in strata_sizes
    ), (
        f"stratified allocation exceeds stratum size: "
        f"alloc={allocations}, sizes={strata_sizes}"
    )
    return allocations


def stratified_representative(
    pool: CounterexampleSet,
    k: int,
    rng: np.random.Generator | None = None,
) -> CounterexampleSet:
    """Stratified proportional allocation across three gap-based strata.

    Strata, anchored at zero (see decisions-log 2026-04-20):
        strong_wins    := gap ≥  σ
        strong_losses  := gap ≤ -σ
        ties_and_small := |gap| < σ
    where σ is the population standard deviation of gaps in the pool,
    computed once. `k` is split by proportional allocation with
    floor-then-priority-ranked remainder distribution (priority:
    strong_wins > strong_losses > ties_and_small); overflow against
    stratum size is capped and redistributed. Within each stratum,
    draw the quota uniformly without replacement via `rng`.
    Return order: all strong_wins draws, then strong_losses draws,
    then ties_and_small draws.
    """
    if rng is None:
        raise ValueError(
            "stratified_representative requires an rng (np.random.Generator)"
        )
    _validate_k(pool, k)
    items = list(pool)
    gaps = np.array([c.gap for c in items], dtype=float)
    sigma = float(np.std(gaps, ddof=0))

    strata: Dict[str, List[Counterexample]] = {
        "strong_wins":    [c for c in items if c.gap >= sigma],
        "strong_losses":  [c for c in items if c.gap <= -sigma],
        "ties_and_small": [c for c in items if abs(c.gap) < sigma],
    }
    # Sanity: strata must partition the pool.
    assert sum(len(strata[n]) for n in _STRATUM_ORDER) == len(items)

    allocations = _allocate_strata(
        {n: len(strata[n]) for n in _STRATUM_ORDER}, k
    )

    result: List[Counterexample] = []
    for name in _STRATUM_ORDER:
        n_alloc = allocations[name]
        if n_alloc == 0:
            continue
        stratum = strata[name]
        chosen = rng.choice(len(stratum), size=n_alloc, replace=False)
        for i in chosen:
            result.append(stratum[int(i)])

    return CounterexampleSet(items=result)


# --- Registry ----------------------------------------------------------

STRATEGIES: Dict[str, Callable[..., CounterexampleSet]] = {
    "uniform_random": uniform_random,
    "worst_only": worst_only,
    "worst_plus_best": worst_plus_best,
    "most_discriminative": most_discriminative,
    "random_discriminative": random_discriminative,
    "stratified_representative": stratified_representative,
}

DETERMINISTIC_STRATEGY_NAMES = frozenset({
    "worst_only",
    "worst_plus_best",
    "most_discriminative",
})

STOCHASTIC_STRATEGY_NAMES = frozenset({
    "uniform_random",
    "random_discriminative",
    "stratified_representative",
})
