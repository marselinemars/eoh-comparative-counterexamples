"""Chapter 5 — counterexample selection strategies."""
from .strategies import (
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

__all__ = [
    "DETERMINISTIC_STRATEGY_NAMES",
    "STOCHASTIC_STRATEGY_NAMES",
    "STRATEGIES",
    "most_discriminative",
    "random_discriminative",
    "stratified_representative",
    "uniform_random",
    "worst_only",
    "worst_plus_best",
]
