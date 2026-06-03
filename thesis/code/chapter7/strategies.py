"""thesis/code/chapter7/strategies.py — chapter 7 boundary substitution.

Per ``chapter7_design.md`` §3.8 and decisions log 2026-05-05
"Chapter 7 lower-boundary convention". The chapter 7 cardinality
axis hits a strategy-collapse at its lower boundary:
``worst_plus_best`` requires ``k ≥ 2`` because it partitions
selection into ``k/2`` worst plus ``k/2`` best instances. At
``k=1`` the partition is undefined.

Chapter 7 uses :func:`worst_only_at_k1` — the single-instance
limit of ``worst_plus_best``'s deterministic worst-half
component — as the boundary substitution. Operationally this is
identical to chapter 5's ``worst_only`` strategy at ``k=1``, but
named distinctly so the chapter-7-specific cardinality curve at
the ``worst_plus_best`` strategy preserves its convention as a
single labeled trajectory.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from thesis.code.chapter5.strategies import worst_only as _ch5_worst_only
from thesis.code.counterexample import CounterexampleSet


def worst_only_at_k1(
    pool: CounterexampleSet,
    k: int,
    rng: Optional[np.random.Generator] = None,
) -> CounterexampleSet:
    """Return the single largest-loss counterexample.

    Defined only at ``k=1``. Operationally identical to
    chapter 5's ``worst_only`` at ``k=1``. The ``worst_only_at_k1``
    name reserves a chapter-7 boundary identity for this point on
    the ``worst_plus_best`` cardinality curve.

    ``rng`` is ignored (deterministic strategy).
    """
    if k != 1:
        raise ValueError(
            f"worst_only_at_k1 is defined only at k=1; got k={k}"
        )
    return _ch5_worst_only(pool, k=1, rng=rng)


# Registry add-on. The ch7 driver code combines this with ch5's
# STRATEGIES dict.
CH7_STRATEGIES = {
    "worst_only_at_k1": worst_only_at_k1,
}

DETERMINISTIC_CH7_STRATEGY_NAMES = frozenset({"worst_only_at_k1"})
