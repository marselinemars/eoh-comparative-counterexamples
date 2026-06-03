"""
thesis/code/chapter5/seeds.py

Seed-derivation functions for chapter 5 experiments, per
`thesis/writing/chapter5_design.md` §11.

Each function returns a deterministic 32-bit integer derived from
the master seed plus the call-site's structural coordinates
(strategy, set index, seed index; or strategy, trajectory index,
step index). sha256 ensures that seeds at different coordinates
are effectively independent.
"""
from __future__ import annotations

import hashlib

MASTER_SEED_CH5 = 20_260_420


def set_seed(strategy_name: str, set_index: int) -> int:
    return int(
        hashlib.sha256(
            f"ch5:set:{MASTER_SEED_CH5}:{strategy_name}:{set_index}".encode(
                "utf-8"
            )
        ).hexdigest()[:8],
        16,
    )


def llm_seed(strategy_name: str, set_index: int, seed_index: int) -> int:
    return int(
        hashlib.sha256(
            f"ch5:llm:{MASTER_SEED_CH5}:{strategy_name}:{set_index}:{seed_index}".encode(
                "utf-8"
            )
        ).hexdigest()[:8],
        16,
    )


def trajectory_set_seed(
    strategy_name: str, trajectory_index: int, step_index: int
) -> int:
    return int(
        hashlib.sha256(
            (
                f"ch5:traj:set:{MASTER_SEED_CH5}:{strategy_name}:"
                f"{trajectory_index}:{step_index}"
            ).encode("utf-8")
        ).hexdigest()[:8],
        16,
    )


def trajectory_llm_seed(
    strategy_name: str, trajectory_index: int, step_index: int
) -> int:
    return int(
        hashlib.sha256(
            (
                f"ch5:traj:llm:{MASTER_SEED_CH5}:{strategy_name}:"
                f"{trajectory_index}:{step_index}"
            ).encode("utf-8")
        ).hexdigest()[:8],
        16,
    )
