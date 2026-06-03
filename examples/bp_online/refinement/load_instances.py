from __future__ import annotations

import importlib.util
import math
import pickle
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_GET_INSTANCE_PATH = (
    REPO_ROOT / "eoh" / "src" / "eoh" / "problems" / "optimization" / "bp_online" / "get_instance.py"
)

REFINEMENT_DIR = Path(__file__).resolve().parent
_SPLIT_FILES = {
    "dev": REFINEMENT_DIR / "eval_split_dev.pkl",
    "test_ood": REFINEMENT_DIR / "eval_split_test_ood.pkl",
}

VALID_SPLITS = ("search_train", "dev", "test_ood")


def _load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {module_path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_bundled_instances(limit: int | None = None) -> list[dict[str, Any]]:
    """Return the 5 bundled search_train instances. Legacy name kept for compatibility."""
    return load_split_instances("search_train", limit=limit)


def load_split_instances(
    split: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Load instances for the requested split.

    split must be one of: 'search_train', 'dev', 'test_ood'

    search_train  — the 5 bundled instances used for mutation context and
                    initial fitness estimation. These are the instances the
                    LLM sees during refinement.
    dev           — 5 fresh instances never shown to the LLM. Used for
                    acceptance decisions (did the mutation generalize?).
    test_ood      — 5 held-out instances. Touch only for final reporting.
                    Never use during any refinement episode.
    """
    if split not in VALID_SPLITS:
        raise ValueError(f"split must be one of {VALID_SPLITS}, got {split!r}")

    if split == "search_train":
        return _load_search_train(limit)

    split_path = _SPLIT_FILES[split]
    if not split_path.exists():
        raise FileNotFoundError(
            f"Split file not found: {split_path}\n"
            f"Run generate_eval_splits.py first to create the dev and test_ood splits."
        )
    with split_path.open("rb") as fh:
        records = pickle.load(fh)
    if limit is not None:
        records = records[:limit]
    return records


def _load_search_train(limit: int | None = None) -> list[dict[str, Any]]:
    module = _load_module(CORE_GET_INSTANCE_PATH, "bp_online_core_get_instance")
    loader = module.GetData()
    datasets, _ = loader.get_instances()

    instances: list[dict[str, Any]] = []
    for dataset_name, dataset in datasets.items():
        for case_name, instance in dataset.items():
            lower_bound = float(loader.l1_bound(instance["items"], instance["capacity"]))
            instances.append(
                {
                    "instance_id": f"{dataset_name}/{case_name}",
                    "dataset_name": dataset_name,
                    "case_name": case_name,
                    "split": "search_train",
                    "capacity": int(instance["capacity"]),
                    "num_items": int(instance["num_items"]),
                    "items": list(instance["items"]),
                    "lower_bound": lower_bound,
                }
            )

    if limit is not None:
        return instances[:limit]
    return instances
