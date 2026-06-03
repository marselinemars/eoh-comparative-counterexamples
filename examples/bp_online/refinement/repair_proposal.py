from __future__ import annotations

import json
import re
from typing import Any


ALLOWED_REPAIR_STATUSES = (
    "proposed_patch",
    "no_patch",
    "unsupported_request",
)


def _normalize_string_sequence(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, (list, tuple)):
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError(f"{field_name} must contain only strings.")
            stripped = item.strip()
            if stripped:
                normalized.append(stripped)
        return tuple(normalized)
    raise ValueError(f"{field_name} must be a string, list of strings, or null.")


def _normalize_optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or null.")
    stripped = value.strip()
    return stripped or None


def validate_repair_proposal(payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("status")
    if status not in ALLOWED_REPAIR_STATUSES:
        raise ValueError(
            f"Invalid repair proposal status {status!r}. "
            f"Allowed values: {ALLOWED_REPAIR_STATUSES}."
        )

    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be a number in [0, 1].")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be in [0, 1].")

    patch_family = _normalize_optional_string(payload.get("patch_family"), "patch_family")
    rationale = _normalize_optional_string(payload.get("rationale"), "rationale") or ""
    proposed_change_summary = _normalize_string_sequence(
        payload.get("proposed_change_summary"),
        "proposed_change_summary",
    )
    localized_edit_instructions = _normalize_string_sequence(
        payload.get("localized_edit_instructions"),
        "localized_edit_instructions",
    )
    proposed_code = _normalize_optional_string(payload.get("proposed_code"), "proposed_code")

    if status == "proposed_patch" and not proposed_code:
        raise ValueError("proposed_code must be non-empty when status == 'proposed_patch'.")
    if status in ("no_patch", "unsupported_request"):
        proposed_code = proposed_code or None

    return {
        "status": status,
        "patch_family": patch_family,
        "confidence": confidence,
        "rationale": rationale,
        "proposed_change_summary": proposed_change_summary,
        "localized_edit_instructions": localized_edit_instructions,
        "proposed_code": proposed_code,
    }


def _strip_think_blocks(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)
    return text.strip()


def _extract_json_object_text(raw_text: str) -> str:
    if raw_text is None:
        raise ValueError("Repair proposal text is None (LLM returned no content).")
    stripped = _strip_think_blocks(raw_text)
    if not stripped:
        raise ValueError("Repair proposal text is empty (or contained only a thinking block).")

    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced_match:
        return fenced_match.group(1)

    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            _, end = decoder.raw_decode(stripped[index:])
            return stripped[index : index + end]
        except json.JSONDecodeError:
            continue

    raise ValueError("Failed to locate a JSON object in repair proposal text.")


def parse_repair_proposal(raw_json_text: str) -> dict[str, Any]:
    try:
        json_text = _extract_json_object_text(raw_json_text)
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse repair proposal JSON: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Repair proposal JSON must decode to an object.")
    return validate_repair_proposal(payload)


def build_stub_repair_proposal(repair_request: dict[str, Any]) -> dict[str, Any]:
    heuristic_code = str(repair_request.get("heuristic_code") or "").strip()
    trace_preview = repair_request.get("trace_preview") or {}
    key_steps = trace_preview.get("key_steps") or ()

    if not heuristic_code or "def score" not in heuristic_code or not key_steps:
        return {
            "status": "no_patch",
            "patch_family": None,
            "confidence": 0.2,
            "rationale": "Stub generator did not find enough heuristic code or trace context to propose a localized patch.",
            "proposed_change_summary": (
                "Leave the heuristic unchanged in stub mode.",
            ),
            "localized_edit_instructions": (
                "Provide a stronger repair request with heuristic code and at least one trace key step.",
            ),
            "proposed_code": None,
        }

    return {
        "status": "proposed_patch",
        "patch_family": "local_edit_stub",
        "confidence": 0.35,
        "rationale": "Stub proposal anchors on the selected failing case and suggests a narrow local edit without claiming real repair quality.",
        "proposed_change_summary": (
            "Adjust the scoring logic locally around the failing pattern highlighted by the trace preview.",
            "Keep the score(item, bins) interface unchanged.",
        ),
        "localized_edit_instructions": (
            "Edit only the score function body rather than rewriting the heuristic module.",
            "Use the failing case trace as local grounding for the change.",
        ),
        "proposed_code": (
            "# STUB REPAIR OUTPUT\n"
            "# Replace this placeholder with a real localized repair proposal.\n"
            f"{heuristic_code}"
        ),
    }


def format_repair_proposal_preview(repair_proposal: dict[str, Any]) -> str:
    lines = [
        f"status={repair_proposal['status']}",
        f"patch_family={repair_proposal['patch_family']}",
        f"confidence={repair_proposal['confidence']:.2f}",
        f"change_summary_count={len(repair_proposal['proposed_change_summary'])}",
        f"localized_edit_count={len(repair_proposal['localized_edit_instructions'])}",
        f"has_proposed_code={repair_proposal['proposed_code'] is not None}",
    ]
    return "\n".join(lines)
