"""
build_mutation_request.py

Builds evidence-guided mutation prompts and triage critic prompts
for pairwise heuristic mutation. Companion to build_repair_request.py.
"""

from __future__ import annotations

import json
import re
from typing import Any


def build_mutation_request(
    incumbent: dict[str, Any],
    donor: dict[str, Any],
    anchor_cases: dict[str, Any],
    *,
    novelty_constraint: bool = True,
    banned_patch_families: tuple[str, ...] = (),
    incumbent_description: str = "Current best incumbent",
    donor_description: str = "Donor heuristic",
) -> dict[str, Any]:
    return {
        "task": "evidence_guided_mutation",
        "incumbent": {
            "description": incumbent_description,
            "core_fitness": incumbent.get("core_fitness"),
            "summary": incumbent.get("summary"),
            "code": incumbent.get("code"),
        },
        "donor": {
            "description": donor_description,
            "core_fitness": donor.get("core_fitness"),
            "summary": donor.get("summary"),
            "algorithm": donor.get("algorithm"),
            "code": donor.get("code"),
        },
        "anchor_cases": anchor_cases,
        "novelty_constraint": novelty_constraint,
        "banned_patch_families": list(banned_patch_families),
    }


def build_mutation_prompt(mutation_request: dict[str, Any]) -> str:
    labels = list(mutation_request["anchor_cases"].keys())
    context_labels_str = ", ".join(labels)

    output_contract = {
        "status": "proposed_patch | no_patch | unsupported_request",
        "patch_family": "short string or null",
        "confidence": "number in [0, 1]",
        "rationale": "brief explanation grounded in the comparative case evidence",
        "proposed_change_summary": ["brief localized change summary item"],
        "localized_edit_instructions": ["short step-by-step instructions for a local edit only"],
        "proposed_code": "full revised heuristic code with the same interface, or null when no patch is proposed",
    }
    output_contract_json = json.dumps(output_contract, indent=2, ensure_ascii=True)
    request_json = json.dumps(mutation_request, indent=2, ensure_ascii=True)

    novelty_line = (
        "- The proposed code MUST differ numerically from both parent A (incumbent) "
        "and parent B (donor). Do not reproduce either parent exactly.\n"
        if mutation_request.get("novelty_constraint")
        else ""
    )

    banned = mutation_request.get("banned_patch_families") or []
    banned_line = (
        f"- Do NOT propose any of these previously-tried patch families: {banned}\n"
        if banned
        else ""
    )

    return (
        "You are performing evidence-guided mutation between two bin-packing heuristics.\n"
        "Your goal: propose a small local interpolation or numeric adjustment that produces a new heuristic.\n"
        "Rules:\n"
        "- You may only adjust parameters, coefficients, exponents, or thresholds already present "
        "in one or both parents.\n"
        "- Do NOT transfer an entire scoring mechanism from one parent to the other.\n"
        "- Do NOT replace one scoring component with a different formula family.\n"
        "- Do NOT rewrite the scoring logic from scratch.\n"
        "- Keep the interface unchanged: the code must still define score(item, bins).\n"
        f"- Use the anchor cases ({context_labels_str}) to compare strengths and weaknesses "
        "of both parents.\n"
        "- Prefer small, calibration-style changes grounded in the observed per-case tradeoffs.\n"
        f"{novelty_line}"
        f"{banned_line}"
        "- If no safe interpolation-style mutation is justified by the evidence, return no_patch.\n"
        "Return structured JSON only with this exact top-level schema:\n"
        f"{output_contract_json}\n\n"
        "Mutation request:\n"
        f"{request_json}"
    )


def build_mutation_prompt_minimal(mutation_request: dict[str, Any]) -> str:
    """Evidence-only prompt: no interpolation rules, no size preference, no mechanism constraints.
    The LLM reasons freely from the anchor-case evidence; only structural correctness is required.
    """
    output_contract = {
        "status": "proposed_patch | no_patch | unsupported_request",
        "patch_family": "short string or null",
        "confidence": "number in [0, 1]",
        "rationale": "what the evidence shows and why you changed what you changed",
        "proposed_change_summary": ["what changed and why"],
        "proposed_code": "full modified heuristic code, or null if no change is proposed",
    }
    output_contract_json = json.dumps(output_contract, indent=2, ensure_ascii=True)
    request_json = json.dumps(mutation_request, indent=2, ensure_ascii=True)

    novelty_line = (
        "- The proposed code must differ numerically from both heuristics.\n"
        if mutation_request.get("novelty_constraint")
        else ""
    )

    return (
        "You are given two bin-packing heuristics and comparative per-case performance data.\n"
        "Analyze the evidence and propose a modification to the incumbent heuristic "
        "(parent A) that the evidence suggests would improve it.\n\n"
        "Hard requirements for the output code:\n"
        "- Must define score(item, bins) returning a numpy array of scores.\n"
        "- Must return np.inf for bins where remainder == 0 (exact fits always win).\n"
        f"{novelty_line}"
        "Everything else — what to change, how much, whether structural or numeric — "
        "should follow from what the evidence shows, not from a prior rule.\n"
        "If the evidence does not clearly support any change, return no_patch.\n\n"
        "Return structured JSON only:\n"
        f"{output_contract_json}\n\n"
        "Mutation request:\n"
        f"{request_json}"
    )


def build_critic_prompt(
    mutation_request: dict[str, Any],
    proposal: dict[str, Any],
    revision_guidance: str | None = None,
) -> str:
    output_contract = {
        "decision": "approve | revise | reject",
        "confidence": "number in [0, 1]",
        "summary": "brief explanation of the decision",
        "revision_guidance": "specific actionable guidance if decision is revise, null otherwise",
    }
    output_contract_json = json.dumps(output_contract, indent=2, ensure_ascii=True)

    incumbent_code = mutation_request.get("incumbent", {}).get("code", "")
    donor_code = mutation_request.get("donor", {}).get("code", "")
    proposed_code = proposal.get("proposed_code", "")
    rationale = proposal.get("rationale", "")
    patch_family = proposal.get("patch_family", "")
    change_summary = proposal.get("proposed_change_summary", [])

    revision_context = (
        f"\nNote: this is a revised proposal. Prior revision guidance was:\n{revision_guidance}\n"
        if revision_guidance
        else ""
    )

    return (
        "You are a triage critic for a bin-packing heuristic mutation proposal.\n"
        "Classify the proposal as: approve, revise, or reject.\n\n"
        "Evaluate ONLY these three criteria:\n"
        "1. Evidence grounding: is the rationale directly grounded in the per-case performance "
        "differences shown in the anchor cases?\n"
        "2. Locality: does the proposal stay within the same scoring formula family? "
        "(No new scoring components, no mechanism transfer, no structural rewrites.)\n"
        "3. Structural integrity: does the proposed code correctly define score(item, bins) "
        "with the same interface as the parents?\n\n"
        "Do NOT assess whether the proposal will improve objective quality — evaluation decides that.\n"
        "Do NOT reject simply because the change is small — small calibration changes are correct.\n"
        f"{revision_context}\n"
        f"Parent A (incumbent) code:\n{incumbent_code}\n\n"
        f"Parent B (donor) code:\n{donor_code}\n\n"
        f"Proposed patch family: {patch_family}\n"
        f"Proposed change summary: {json.dumps(change_summary)}\n"
        f"Rationale: {rationale}\n"
        f"Proposed code:\n{proposed_code}\n\n"
        "Return structured JSON only with this exact schema:\n"
        f"{output_contract_json}"
    )


def build_revision_prompt(
    mutation_request: dict[str, Any],
    original_proposal: dict[str, Any],
    revision_guidance: str,
) -> str:
    output_contract = {
        "status": "proposed_patch | no_patch | unsupported_request",
        "patch_family": "short string or null",
        "confidence": "number in [0, 1]",
        "rationale": "brief explanation grounded in the comparative case evidence",
        "proposed_change_summary": ["brief localized change summary item"],
        "localized_edit_instructions": ["short step-by-step instructions for a local edit only"],
        "proposed_code": "full revised heuristic code with the same interface, or null",
    }
    output_contract_json = json.dumps(output_contract, indent=2, ensure_ascii=True)
    request_json = json.dumps(mutation_request, indent=2, ensure_ascii=True)

    original_summary = json.dumps(original_proposal.get("proposed_change_summary", []))
    original_rationale = original_proposal.get("rationale", "")

    return (
        "You are revising a bin-packing heuristic mutation proposal based on critic feedback.\n"
        "Apply the revision guidance below while keeping all original mutation constraints.\n"
        "Keep the interface unchanged: the code must still define score(item, bins).\n"
        "Return structured JSON only with this exact top-level schema:\n"
        f"{output_contract_json}\n\n"
        f"Critic revision guidance:\n{revision_guidance}\n\n"
        f"Your original change summary: {original_summary}\n"
        f"Your original rationale: {original_rationale}\n\n"
        "Original mutation request (for reference):\n"
        f"{request_json}"
    )


def _strip_think_blocks(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)
    return text.strip()


def parse_critic_response(raw_text: str) -> dict[str, Any]:
    if raw_text is None:
        raise ValueError("Critic response is None (LLM returned no content).")
    stripped = _strip_think_blocks(raw_text)

    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced_match:
        json_text = fenced_match.group(1)
    else:
        decoder = json.JSONDecoder()
        json_text = None
        for i, c in enumerate(stripped):
            if c == "{":
                try:
                    _, end = decoder.raw_decode(stripped[i:])
                    json_text = stripped[i : i + end]
                    break
                except json.JSONDecodeError:
                    continue
        if json_text is None:
            raise ValueError("Failed to locate JSON object in critic response.")

    payload = json.loads(json_text)
    decision = payload.get("decision", "")
    if decision not in ("approve", "revise", "reject"):
        raise ValueError(f"Invalid critic decision: {decision!r}")

    return {
        "decision": decision,
        "confidence": float(payload.get("confidence", 0.5)),
        "summary": str(payload.get("summary", "")),
        "revision_guidance": payload.get("revision_guidance"),
    }
