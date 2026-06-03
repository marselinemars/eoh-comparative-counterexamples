"""
thesis/code/evaluation.py

Per-instance and dataset-level evaluation primitives for the thesis.
Thin wrapper around the read-only harness at
`examples/bp_online/evaluation/evaluation.py`.

Conventions (authoritative: thesis/docs/05_glossary.md):
    bins_used(h, I) is the integer count of bins used by heuristic h
                     on instance I.
    score(h, I)     := -bins_used(h, I)               (higher is better)
    gap(c, r, I)    := score(c, I) - score(r, I)
                     = bins_used(r, I) - bins_used(c, I)
                     (positive means candidate c is better than
                      reference r on I)
"""
from __future__ import annotations

import pickle
import sys
import types
from pathlib import Path
from typing import Dict

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "examples" / "bp_online" / "evaluation"
TESTING_DATA_DIR = EVAL_DIR / "testingdata"

# Expose the read-only harness for import without turning it into a
# package. See AGENTS.md — this file is treated as read-only.
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import evaluation as _harness  # noqa: E402

Evaluation = _harness.Evaluation


def load_heuristic_from_code(
    code_string: str,
    module_name: str = "thesis_heuristic",
) -> types.ModuleType:
    """Exec a heuristic source string into a fresh module and return it.

    The module must define `score(item, bins) -> np.ndarray`. This is
    the canonical pattern used throughout EoH and the harness.
    """
    module = types.ModuleType(module_name)
    exec(code_string, module.__dict__)  # noqa: S102 — heuristic code is the payload
    if not hasattr(module, "score"):
        raise ValueError(
            f"Heuristic module {module_name!r} does not define a "
            "'score' function."
        )
    return module


def load_instances(size: str = "1k", capacity: int = 100) -> Dict[str, Dict]:
    """Load a bp_online instance set from the harness's testingdata pickles.

    Parameters
    ----------
    size : str
        Pickle suffix; "1k" loads `test_dataset_1k.pkl`.
    capacity : int
        Bin capacity to set on every loaded instance. Default 100
        matches the harness's documented default.

    Returns
    -------
    dict[str, dict]
        Mapping from instance_id ("test_0", "test_1", ...) to an
        instance dict with keys {"capacity", "num_items", "items"}.
    """
    path = TESTING_DATA_DIR / f"test_dataset_{size}.pkl"
    if not path.exists():
        raise FileNotFoundError(f"No test pickle at {path}")
    with path.open("rb") as f:
        raw = pickle.load(f)
    if not isinstance(raw, dict):
        raise ValueError(
            f"Expected a dict in {path}, got {type(raw).__name__}"
        )
    instances: Dict[str, Dict] = {}
    for num_items, instance_list in raw.items():
        for i, items in enumerate(instance_list):
            iid = f"test_{i}"
            if iid in instances:
                raise ValueError(
                    f"Duplicate instance_id {iid} in {path} "
                    "(multiple num_items keys in pickle?)"
                )
            instances[iid] = {
                "capacity": capacity,
                "num_items": int(num_items),
                "items": items,
            }
    return instances


def bins_used(heuristic_module: types.ModuleType, instance: Dict) -> int:
    """Run the heuristic on an instance and return integer bins used."""
    capacity = instance["capacity"]
    items = np.array(instance["items"])
    bins = np.array([capacity for _ in range(instance["num_items"])])
    _, bins_packed = Evaluation().online_binpack(items, bins, heuristic_module)
    return int((bins_packed != capacity).sum())


def score(heuristic_module: types.ModuleType, instance: Dict) -> int:
    """Higher-is-better per-instance score: -bins_used(h, I)."""
    return -bins_used(heuristic_module, instance)


def gap(
    candidate_module: types.ModuleType,
    reference_module: types.ModuleType,
    instance: Dict,
) -> int:
    """Discriminative gap. Positive means candidate c beats reference r on I."""
    return bins_used(reference_module, instance) - bins_used(candidate_module, instance)
