from __future__ import annotations

import importlib.util
import math
import types
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_EVALUATION_PATH = REPO_ROOT / "examples" / "bp_online" / "evaluation" / "evaluation.py"


def _load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {module_path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_evaluation_module = _load_module(EXAMPLE_EVALUATION_PATH, "bp_online_example_evaluation")
Evaluation = _evaluation_module.Evaluation


def load_heuristic_module_from_code(
    code_string: str,
    module_name: str = "bp_online_refinement_heuristic",
):
    heuristic_module = types.ModuleType(module_name)
    exec(code_string, heuristic_module.__dict__)
    if not hasattr(heuristic_module, "score"):
        raise ValueError("Loaded heuristic code does not define a 'score' function.")
    return heuristic_module


def _instance_lower_bound(instance: dict[str, Any]) -> float:
    if instance.get("lower_bound") is not None:
        return float(instance["lower_bound"])
    items = np.array(instance["items"])
    capacity = float(instance["capacity"])
    return float(math.ceil(float(np.sum(items)) / capacity))


def evaluate_heuristic_on_instance(
    heuristic_module,
    instance: dict[str, Any],
    evaluator: Evaluation | None = None,
) -> dict[str, Any]:
    evaluator = evaluator or Evaluation()
    capacity = float(instance["capacity"])
    items = np.array(instance["items"])
    bins = np.array([capacity for _ in range(instance["num_items"])])

    _, bins_packed = evaluator.online_binpack(items, bins, heuristic_module)
    bins_used = int((bins_packed != capacity).sum())
    lower_bound = _instance_lower_bound(instance)
    objective_gap = float((bins_used - lower_bound) / lower_bound)

    return {
        "instance_id": instance["instance_id"],
        "dataset_name": instance.get("dataset_name"),
        "case_name": instance.get("case_name"),
        "capacity": float(instance["capacity"]),
        "num_items": int(instance["num_items"]),
        "bins_used": bins_used,
        "lower_bound": lower_bound,
        "objective_gap": objective_gap,
        "objective_value": float(bins_used),
    }


def evaluate_heuristic_on_instances(
    instances: list[dict[str, Any]],
    *,
    code_string: str | None = None,
    heuristic_module=None,
) -> list[dict[str, Any]]:
    if heuristic_module is None:
        if code_string is None:
            raise ValueError("Provide either code_string or heuristic_module.")
        heuristic_module = load_heuristic_module_from_code(code_string)

    evaluator = Evaluation()
    return [
        evaluate_heuristic_on_instance(heuristic_module, instance, evaluator=evaluator)
        for instance in instances
    ]


def summarize_case_results(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not case_results:
        return {
            "num_instances": 0,
            "mean_bins_used": None,
            "mean_lower_bound": None,
            "mean_objective_gap": None,
        }

    bins_used = np.array([result["bins_used"] for result in case_results], dtype=float)
    lower_bounds = np.array([result["lower_bound"] for result in case_results], dtype=float)
    gaps = np.array([result["objective_gap"] for result in case_results], dtype=float)
    return {
        "num_instances": len(case_results),
        "mean_bins_used": float(np.mean(bins_used)),
        "mean_lower_bound": float(np.mean(lower_bounds)),
        "mean_objective_gap": float(np.mean(gaps)),
    }
