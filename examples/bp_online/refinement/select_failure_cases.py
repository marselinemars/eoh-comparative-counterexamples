from __future__ import annotations

from typing import Any


def _rank_key(case_result: dict[str, Any]) -> tuple[float, float, str]:
    return (
        -float(case_result["objective_gap"]),
        -float(case_result["objective_value"]),
        str(case_result["instance_id"]),
    )


def _selection_reason(fallback_all_instances_used: bool) -> str:
    if fallback_all_instances_used:
        return "fallback_all_instances ranked by objective_gap, objective_value, instance_id"
    return "failure_pool objective_gap>0 ranked by objective_gap, objective_value, instance_id"


def _selection_stage(fallback_all_instances_used: bool) -> str:
    if fallback_all_instances_used:
        return "fallback_all_instances"
    return "failure_pool"


def _to_selected_failure_case(
    case_result: dict[str, Any],
    *,
    fallback_all_instances_used: bool,
) -> dict[str, Any]:
    return {
        "instance_id": case_result["instance_id"],
        "dataset_name": case_result.get("dataset_name"),
        "case_name": case_result.get("case_name"),
        "capacity": case_result["capacity"],
        "num_items": case_result["num_items"],
        "bins_used": case_result["bins_used"],
        "lower_bound": case_result["lower_bound"],
        "objective_gap": case_result["objective_gap"],
        "objective_value": case_result["objective_value"],
        "selection_stage": _selection_stage(fallback_all_instances_used),
        "selection_reason": _selection_reason(fallback_all_instances_used),
    }


def summarize_failure_selection(
    case_results: list[dict[str, Any]],
    *,
    selected_count: int,
    fallback_all_instances_used: bool,
) -> dict[str, Any]:
    failure_pool_size = sum(float(case["objective_gap"]) > 0 for case in case_results)
    return {
        "total_cases": len(case_results),
        "failure_pool_size": int(failure_pool_size),
        "selected_count": int(selected_count),
        "fallback_all_instances_used": bool(fallback_all_instances_used),
    }


def select_failure_cases(
    case_results: list[dict[str, Any]],
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    failure_pool = [case for case in case_results if float(case["objective_gap"]) > 0]
    fallback_all_instances_used = len(failure_pool) == 0
    ranking_pool = failure_pool if failure_pool else list(case_results)
    ranked_cases = sorted(ranking_pool, key=_rank_key)
    selected_cases = [
        _to_selected_failure_case(
            case_result,
            fallback_all_instances_used=fallback_all_instances_used,
        )
        for case_result in ranked_cases[: max(top_k, 0)]
    ]
    selection_summary = summarize_failure_selection(
        case_results,
        selected_count=len(selected_cases),
        fallback_all_instances_used=fallback_all_instances_used,
    )
    return {
        "selected_failure_cases": selected_cases,
        "selection_summary": selection_summary,
    }


def format_selection_summary_preview(selection_summary: dict[str, Any]) -> str:
    return (
        f"total_cases={selection_summary['total_cases']} "
        f"failure_pool_size={selection_summary['failure_pool_size']} "
        f"selected_count={selection_summary['selected_count']} "
        f"fallback_all_instances_used={selection_summary['fallback_all_instances_used']}"
    )


def format_failure_case_preview(selected_case: dict[str, Any]) -> str:
    return (
        f"{selected_case['instance_id']} "
        f"bins_used={selected_case['bins_used']} "
        f"lower_bound={selected_case['lower_bound']:.2f} "
        f"objective_gap={selected_case['objective_gap']:.6f} "
        f"selection_stage={selected_case['selection_stage']}"
    )
