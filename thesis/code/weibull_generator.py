"""
thesis/code/weibull_generator.py

Seeded, reproducible Weibull instance generator for the thesis.

Matches the parameters of the existing bp_online pickles:
    shape = 3
    scale = 45
    clip  = [1, 100]    (effectively no clipping at 5000-10000 items:
                         P(x > 100) ~ 1.7e-5)
    rounded to integer item sizes

All randomness flows through np.random.default_rng(seed). Given the
same seed and the same (num_instances, num_items), this generator
produces bit-identical output across runs and machines.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

WEIBULL_SHAPE = 3.0
WEIBULL_SCALE = 45.0
CLIP_LOW = 1
CLIP_HIGH = 100
DEFAULT_CAPACITY = 100


@dataclass(frozen=True)
class Instance:
    """One bp_online instance."""
    instance_id: str         # e.g. "thesis_train_select_5k_0"
    num_items: int
    capacity: int
    items: List[int]


def generate_instances(
    num_instances: int,
    num_items: int,
    seed: int,
    instance_id_prefix: str,
    capacity: int = DEFAULT_CAPACITY,
) -> List[Instance]:
    """Generate `num_instances` Weibull instances of `num_items` items each.

    The seed is advanced once per instance so each instance has an
    independent-but-reproducible item stream.
    """
    if num_instances <= 0 or num_items <= 0:
        raise ValueError(
            f"num_instances and num_items must be positive, "
            f"got {num_instances}, {num_items}"
        )
    rng = np.random.default_rng(seed)
    out: List[Instance] = []
    for i in range(num_instances):
        raw = rng.weibull(WEIBULL_SHAPE, num_items) * WEIBULL_SCALE
        clipped = np.clip(raw, CLIP_LOW, CLIP_HIGH)
        items = np.round(clipped).astype(int).tolist()
        out.append(
            Instance(
                instance_id=f"{instance_id_prefix}_{i}",
                num_items=num_items,
                capacity=capacity,
                items=items,
            )
        )
    return out


def instance_to_dict(inst: Instance) -> Dict:
    """Serialization shape used by the thesis split JSONs and by the
    score cache's instance-ID convention."""
    return {
        "instance_id": inst.instance_id,
        "num_items": inst.num_items,
        "capacity": inst.capacity,
        "items": list(inst.items),
    }
