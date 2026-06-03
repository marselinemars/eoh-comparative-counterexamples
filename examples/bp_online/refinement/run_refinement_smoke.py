from __future__ import annotations

import os
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from build_trace_preview import build_trace_previews_for_selected_cases, format_trace_preview
from build_repair_request import (
    build_repair_prompt,
    build_repair_request,
    format_repair_prompt_preview,
    format_repair_request_preview,
)
from repair_proposal import build_stub_repair_proposal, format_repair_proposal_preview
from evaluate_heuristic_cases import (
    evaluate_heuristic_on_instances,
    load_heuristic_module_from_code,
    summarize_case_results,
)
from load_best_heuristic import format_heuristic_preview, load_newest_best_heuristic
from load_instances import load_bundled_instances
from select_failure_cases import (
    format_failure_case_preview,
    format_selection_summary_preview,
    select_failure_cases,
)


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


if __name__ == "__main__":
    instance_limit = env_int("REFINE_INSTANCE_LIMIT", 3)
    select_top_k = env_int("REFINE_SELECT_TOP_K", 3)
    trace_preview_cases = env_int("REFINE_TRACE_PREVIEW_CASES", 2)
    trace_key_steps = env_int("REFINE_TRACE_KEY_STEPS", 6)

    best = load_newest_best_heuristic()
    heuristic_module = load_heuristic_module_from_code(best["code"])
    instances = load_bundled_instances(limit=instance_limit)
    case_results = evaluate_heuristic_on_instances(instances, heuristic_module=heuristic_module)
    summary = summarize_case_results(case_results)
    selection = select_failure_cases(case_results, top_k=select_top_k)
    trace_previews = build_trace_previews_for_selected_cases(
        instances=instances,
        selected_failure_cases=selection["selected_failure_cases"][:trace_preview_cases],
        heuristic_module=heuristic_module,
        max_key_steps=trace_key_steps,
    )

    print("=== Heuristic Preview ===")
    print(format_heuristic_preview(best))
    print()
    print(f"evaluated_instances={summary['num_instances']}")
    print("=== Case Preview ===")
    for result in case_results[: min(3, len(case_results))]:
        print(
            f"{result['instance_id']} "
            f"bins_used={result['bins_used']} "
            f"lower_bound={result['lower_bound']:.2f} "
            f"objective_gap={result['objective_gap']:.6f}"
        )
    print()
    print(f"mean_objective_gap={summary['mean_objective_gap']:.6f}")
    print()
    print("=== Failure Selection Summary ===")
    print(format_selection_summary_preview(selection["selection_summary"]))
    print("=== Selected Failure Cases ===")
    for selected_case in selection["selected_failure_cases"]:
        print(format_failure_case_preview(selected_case))
    if trace_previews:
        print()
        print("=== Trace Preview ===")
        for trace_preview in trace_previews:
            print(format_trace_preview(trace_preview))
            print()

    if selection["selected_failure_cases"] and trace_previews:
        repair_request = build_repair_request(
            best,
            selection["selected_failure_cases"][0],
            trace_previews[0],
        )
        repair_prompt = build_repair_prompt(repair_request)
        print("=== Repair Request Preview ===")
        print(format_repair_request_preview(repair_request))
        print()
        print("=== Repair Prompt Preview ===")
        print(format_repair_prompt_preview(repair_prompt))
        print()
        print("=== Repair Proposal Preview ===")
        print(format_repair_proposal_preview(build_stub_repair_proposal(repair_request)))
