"""
thesis/code/splits.py

The thesis's canonical five-subset split of Weibull instances.

Subsets:
    train_select   — pool from which counterexamples are selected
    train_step     — instances on which the LLM-proposed move is
                     evaluated during a single refinement step
    train_gate     — instances on which a proposed improvement is
                     accepted or rejected
    dev            — held-out validation, reported but not used to
                     make experimental decisions
    test_ood       — out-of-distribution test (larger problem scale)

train_select, train_step, and train_gate are strictly disjoint and
each have their own seed. dev shares the 5000-item scale with the
three train subsets but draws from a separate seed; test_ood uses
10000-item instances with yet another seed to give chapter 7 a real
distribution-shift test.

All seeds are the master seed plus a small per-subset offset. The
master seed is prominently displayed so it is impossible to accidentally
reshuffle the split by changing an unrelated constant.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from thesis.code.weibull_generator import (
    Instance,
    generate_instances,
    instance_to_dict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SPLITS_DIR = REPO_ROOT / "thesis" / "artifacts" / "splits"

# -- Seed configuration ---------------------------------------------------
# Master seed for the entire thesis. Changing this reshuffles every split.
# Do not change without an explicit decisions-log entry.
MASTER_SEED = 2026_04_20

# Per-subset offsets. Arbitrary small constants chosen once.
_OFFSETS = {
    "train_select": 101,
    "train_step":   102,
    "train_gate":   103,
    "dev":          201,
    "test_ood":     301,
}

# -- Split sizes ----------------------------------------------------------
N_PER_TRAIN = 30
N_DEV = 30
N_TEST_OOD = 30

IN_DIST_NUM_ITEMS = 5000
OOD_NUM_ITEMS = 10000


@dataclass(frozen=True)
class Split:
    name: str
    instances: List[Instance]

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "num_instances": len(self.instances),
            "instances": [instance_to_dict(i) for i in self.instances],
        }


def _seed_for(subset: str) -> int:
    return MASTER_SEED + _OFFSETS[subset]


def build_all_splits() -> Dict[str, Split]:
    """Generate all five subsets from the locked seeds."""
    splits: Dict[str, Split] = {}

    for name in ("train_select", "train_step", "train_gate"):
        instances = generate_instances(
            num_instances=N_PER_TRAIN,
            num_items=IN_DIST_NUM_ITEMS,
            seed=_seed_for(name),
            instance_id_prefix=f"thesis_{name}_5k",
        )
        splits[name] = Split(name=name, instances=instances)

    splits["dev"] = Split(
        name="dev",
        instances=generate_instances(
            num_instances=N_DEV,
            num_items=IN_DIST_NUM_ITEMS,
            seed=_seed_for("dev"),
            instance_id_prefix="thesis_dev_5k",
        ),
    )

    splits["test_ood"] = Split(
        name="test_ood",
        instances=generate_instances(
            num_instances=N_TEST_OOD,
            num_items=OOD_NUM_ITEMS,
            seed=_seed_for("test_ood"),
            instance_id_prefix="thesis_test_ood_10k",
        ),
    )

    _validate_disjoint(splits)
    return splits


def _validate_disjoint(splits: Dict[str, Split]) -> None:
    """The three train_* subsets must share no instance IDs. This is
    the load-bearing discipline of the thesis's split design."""
    train_names = ("train_select", "train_step", "train_gate")
    id_sets = {
        name: {i.instance_id for i in splits[name].instances}
        for name in train_names
    }
    for a in train_names:
        for b in train_names:
            if a >= b:
                continue
            overlap = id_sets[a] & id_sets[b]
            if overlap:
                raise RuntimeError(
                    f"Split discipline violated: {a} and {b} share "
                    f"{len(overlap)} instance IDs: {sorted(overlap)[:3]}..."
                )


def write_splits_to_disk(
    splits: Dict[str, Split], out_dir: Path = SPLITS_DIR
) -> Dict[str, Path]:
    """Write each split as JSON at out_dir/<name>.json, return the paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: Dict[str, Path] = {}
    for name, split in splits.items():
        p = out_dir / f"{name}.json"
        p.write_text(
            json.dumps(split.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        paths[name] = p
    return paths


def load_split(name: str, splits_dir: Path = SPLITS_DIR) -> Dict:
    """Load a persisted split by name. Returns the raw JSON dict."""
    path = splits_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Split {name!r} not found at {path}. "
            "Run `python -m thesis.code.splits` to generate all splits."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def qualified_instance_id(split_name: str, inner_id: str) -> str:
    """Produce the score-cache-compatible qualified ID for an instance."""
    return f"thesis_{split_name}:{inner_id}"


def main() -> int:
    splits = build_all_splits()
    paths = write_splits_to_disk(splits)
    print("Wrote splits:")
    for name, path in paths.items():
        n = len(splits[name].instances)
        items = splits[name].instances[0].num_items if n else 0
        print(f"  {name:<13} {n:>3} × {items:>5} items  -> "
              f"{path.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
