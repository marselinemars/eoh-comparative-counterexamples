from __future__ import annotations

import json
from typing import Any


def build_repair_request(
    heuristic: dict[str, Any],
    selected_failure_case: dict[str, Any],
    trace_preview: dict[str, Any],
) -> dict[str, Any]:
    if selected_failure_case["instance_id"] != trace_preview["instance_id"]:
        raise ValueError(
            "Selected failure case and trace preview must match on instance_id: "
            f"{selected_failure_case['instance_id']} != {trace_preview['instance_id']}"
        )

    return {
        "heuristic_artifact_id": heuristic.get("artifact_path")
        or heuristic.get("generation_id")
        or "<unknown>",
        "heuristic_algorithm": heuristic.get("algorithm"),
        "heuristic_code": heuristic.get("code"),
        "instance_id": selected_failure_case["instance_id"],
        "dataset_name": selected_failure_case.get("dataset_name"),
        "case_name": selected_failure_case.get("case_name"),
        "capacity": selected_failure_case["capacity"],
        "num_items": selected_failure_case["num_items"],
        "bins_used": selected_failure_case["bins_used"],
        "lower_bound": selected_failure_case["lower_bound"],
        "objective_gap": selected_failure_case["objective_gap"],
        "objective_value": selected_failure_case["objective_value"],
        "selection_stage": selected_failure_case["selection_stage"],
        "selection_reason": selected_failure_case["selection_reason"],
        "trace_preview": trace_preview,
        "allowed_patch_families": (),
        "banned_patch_families": (),
    }


def build_repair_prompt(repair_request: dict[str, Any]) -> str:
    request_json = json.dumps(repair_request, indent=2, ensure_ascii=True)
    output_contract = {
        "status": "proposed_patch | no_patch | unsupported_request",
        "patch_family": "short string or null",
        "confidence": "number in [0, 1]",
        "rationale": "brief explanation grounded in the failure case and trace preview",
        "proposed_change_summary": [
            "brief localized change summary item"
        ],
        "localized_edit_instructions": [
            "short step-by-step instructions for a local edit only"
        ],
        "proposed_code": "full revised heuristic code with the same interface, or null when no patch is proposed",
    }
    output_contract_json = json.dumps(output_contract, indent=2, ensure_ascii=True)

    return (
        "You are repairing one bin-packing heuristic for one specific failing case.\n"
        "Analyze only this failure case and its trace preview.\n"
        "Propose a localized code edit, not a rewrite.\n"
        "Keep the heuristic interface unchanged: the code must still define score(item, bins).\n"
        "Ground your proposal in the provided failure case and trace preview.\n"
        "Return structured JSON only with this exact top-level schema:\n"
        f"{output_contract_json}\n\n"
        "Repair request:\n"
        f"{request_json}"
    )


def _single_line(text: str | None) -> str:
    if not text:
        return "<missing>"
    return " ".join(str(text).split())


def format_repair_request_preview(repair_request: dict[str, Any]) -> str:
    algorithm = _single_line(repair_request.get("heuristic_algorithm"))
    if len(algorithm) > 120:
        algorithm = algorithm[:117] + "..."

    trace_preview = repair_request["trace_preview"]
    lines = [
        f"heuristic_artifact_id={repair_request['heuristic_artifact_id']}",
        f"instance_id={repair_request['instance_id']}",
        f"objective_gap={repair_request['objective_gap']:.6f}",
        f"selection_stage={repair_request['selection_stage']}",
        f"algorithm={algorithm}",
        f"trace_steps={trace_preview['number_of_steps']}",
        f"trace_new_bin_openings={trace_preview['number_of_new_bin_openings']}",
        f"allowed_patch_families={repair_request['allowed_patch_families']}",
        f"banned_patch_families={repair_request['banned_patch_families']}",
    ]
    return "\n".join(lines)


def format_repair_prompt_preview(repair_prompt: str, max_chars: int = 500) -> str:
    preview = repair_prompt if len(repair_prompt) <= max_chars else repair_prompt[: max_chars - 3] + "..."
    return preview
