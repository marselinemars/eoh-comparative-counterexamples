from __future__ import annotations

from typing import Any

import numpy as np

from evaluate_heuristic_cases import Evaluation, load_heuristic_module_from_code


def trace_instance_execution(
    heuristic_module,
    instance: dict[str, Any],
) -> list[dict[str, Any]]:
    evaluator = Evaluation()
    capacity = float(instance["capacity"])
    items = np.array(instance["items"], dtype=float)
    bins = np.array([capacity for _ in range(int(instance["num_items"]))], dtype=float)

    trace_steps: list[dict[str, Any]] = []
    for step_index, item in enumerate(items):
        valid_bin_indices = evaluator.get_valid_bin_indices(float(item), bins)
        priorities = heuristic_module.score(float(item), bins[valid_bin_indices])
        best_bin = int(valid_bin_indices[int(np.argmax(priorities))])

        num_open_bins_before = int(np.sum(bins != capacity))
        remaining_capacity_before = float(bins[best_bin])
        opened_new_bin = remaining_capacity_before == capacity

        bins[best_bin] -= float(item)
        remaining_capacity_after = float(bins[best_bin])

        trace_steps.append(
            {
                "step_index": int(step_index),
                "item_size": float(item),
                "action_taken": "open_new_bin" if opened_new_bin else "place_existing_bin",
                "chosen_bin_index": "new_bin" if opened_new_bin else best_bin,
                "remaining_capacity_before": remaining_capacity_before,
                "remaining_capacity_after": remaining_capacity_after,
                "num_open_bins_before": num_open_bins_before,
            }
        )

    return trace_steps


def _select_key_steps(
    trace_steps: list[dict[str, Any]],
    *,
    max_key_steps: int = 8,
) -> list[dict[str, Any]]:
    if max_key_steps <= 0:
        return []

    key_indices: list[int] = []
    for step in trace_steps:
        if step["action_taken"] != "open_new_bin":
            continue
        step_index = int(step["step_index"])
        if step_index > 0:
            key_indices.append(step_index - 1)
        key_indices.append(step_index)

    if not key_indices:
        key_indices = list(range(min(len(trace_steps), max_key_steps)))

    seen: set[int] = set()
    ordered_indices: list[int] = []
    for index in key_indices:
        if index in seen:
            continue
        seen.add(index)
        ordered_indices.append(index)

    return [trace_steps[index] for index in ordered_indices[:max_key_steps]]


def build_trace_preview_for_instance(
    heuristic_module,
    instance: dict[str, Any],
    *,
    max_key_steps: int = 8,
) -> dict[str, Any]:
    trace_steps = trace_instance_execution(heuristic_module, instance)
    number_of_new_bin_openings = sum(
        step["action_taken"] == "open_new_bin" for step in trace_steps
    )
    return {
        "instance_id": instance["instance_id"],
        "number_of_steps": len(trace_steps),
        "number_of_new_bin_openings": int(number_of_new_bin_openings),
        "key_steps": _select_key_steps(trace_steps, max_key_steps=max_key_steps),
    }


def build_trace_previews_for_selected_cases(
    *,
    instances: list[dict[str, Any]],
    selected_failure_cases: list[dict[str, Any]],
    heuristic_module=None,
    code_string: str | None = None,
    max_key_steps: int = 8,
) -> list[dict[str, Any]]:
    if heuristic_module is None:
        if code_string is None:
            raise ValueError("Provide either heuristic_module or code_string.")
        heuristic_module = load_heuristic_module_from_code(code_string)

    instances_by_id = {instance["instance_id"]: instance for instance in instances}
    trace_previews: list[dict[str, Any]] = []
    for selected_case in selected_failure_cases:
        instance_id = selected_case["instance_id"]
        if instance_id not in instances_by_id:
            raise KeyError(f"Selected failure case {instance_id} was not found in explicit instances.")
        trace_previews.append(
            build_trace_preview_for_instance(
                heuristic_module,
                instances_by_id[instance_id],
                max_key_steps=max_key_steps,
            )
        )

    return trace_previews


def format_trace_preview(trace_preview: dict[str, Any]) -> str:
    lines = [
        f"instance_id={trace_preview['instance_id']}",
        f"number_of_steps={trace_preview['number_of_steps']}",
        f"number_of_new_bin_openings={trace_preview['number_of_new_bin_openings']}",
        "key_steps:",
    ]
    for step in trace_preview["key_steps"]:
        lines.append(
            f"step={step['step_index']} "
            f"item_size={step['item_size']:.2f} "
            f"action_taken={step['action_taken']} "
            f"chosen_bin_index={step['chosen_bin_index']} "
            f"remaining_capacity_before={step['remaining_capacity_before']:.2f} "
            f"remaining_capacity_after={step['remaining_capacity_after']:.2f} "
            f"num_open_bins_before={step['num_open_bins_before']}"
        )
    return "\n".join(lines)
