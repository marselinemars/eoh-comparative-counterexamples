"""thesis/code/chapter7 — chapter 7 cardinality-axis package.

See ``thesis/writing/chapter7_design.md`` for the implementation
spec. The package wraps chapter 5's prompt builder and chapter 6's
Level-2 trace renderer; it adds the cardinality axis (§3.8), the
``worst_only_at_k1`` boundary substitution (§3.8 / §4.1), and the
chapter-7 seed namespace (§5.2).
"""
from __future__ import annotations

from thesis.code.chapter7.seeds import (  # noqa: F401
    MASTER_SEED_CH7,
    stratified_set_seed_ch7,
    stratified_llm_seed_ch7,
    worst_plus_best_llm_seed_ch7,
    worst_only_at_k1_llm_seed_ch7,
    trajectory_set_seed_ch7,
    trajectory_llm_seed_ch7,
)
from thesis.code.chapter7.strategies import worst_only_at_k1  # noqa: F401
