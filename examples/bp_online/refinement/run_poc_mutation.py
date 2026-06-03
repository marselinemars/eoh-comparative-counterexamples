"""
run_poc_mutation.py  —  PoC mutation episode runner.

Runs one evidence-guided pairwise mutation episode end-to-end:
  load incumbent + donor  →  evaluate both  →  build anchor cases
  →  LLM mutation call  →  triage critic  →  optional revision
  →  evaluate proposal  →  classify  →  save episode JSON.

Usage (env var):
    GROQ_API_KEY=gsk_xxx python run_poc_mutation.py

Usage (CLI):
    python run_poc_mutation.py --api-key gsk_xxx --donor-id gen3_idx3

Dry-run (no LLM calls, just prints the prompt):
    python run_poc_mutation.py --dry-run
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── path setup ────────────────────────────────────────────────────────────────
REFINEMENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = REFINEMENT_DIR.parents[2]
sys.path.insert(0, str(REFINEMENT_DIR))

# ── local module imports ──────────────────────────────────────────────────────
from load_instances import load_split_instances  # noqa: E402
from evaluate_heuristic_cases import (  # noqa: E402
    evaluate_heuristic_on_instances,
    load_heuristic_module_from_code,
    summarize_case_results,
)
from build_trace_preview import build_trace_preview_for_instance  # noqa: E402
from repair_proposal import parse_repair_proposal  # noqa: E402
from build_mutation_request import (  # noqa: E402
    build_mutation_request,
    build_mutation_prompt,
    build_mutation_prompt_minimal,
    build_critic_prompt,
    build_revision_prompt,
    parse_critic_response,
)

# ── current best incumbent (fragment=3.1, mult=1.25) ─────────────────────────
# Found via parameter grid search guided by LLM mutation experiments.
# Beats original incumbent (fragment=3.1, mult=1.15) on all 3 splits:
#   train: 0.00674 vs 0.00683 (-1.4%)  dev: 0.00707 vs 0.00767 (-7.8%)  test_ood: 0.00796 vs 0.00855 (-7.0%)
INCUMBENT_CODE = """\
import numpy as np

def score(item, bins):
    remainder = bins - item

    utilization_score = item / bins

    small_remainder_incentive = 1.0 / (1.0 + remainder / item)

    steepness_multiple = 20.0
    multiplicity_bonus = np.exp(
        -steepness_multiple * (np.round(remainder / item) - remainder / item) ** 2
    )

    fragment_penalty_term = np.where(
        (remainder > 0) & (remainder < item),
        (1.0 - (remainder / item)) ** 4,
        0.0,
    )
    fragment_penalty_magnitude = 3.1

    combined_score_for_non_perfect_fits = (
        utilization_score
        + 0.5 * small_remainder_incentive
        + 1.25 * multiplicity_bonus
        - fragment_penalty_magnitude * fragment_penalty_term
    )

    scores = np.where(remainder == 0, np.inf, combined_score_for_non_perfect_fits)
    return scores
"""

INCUMBENT_CORE_FITNESS = 0.0067406269

# ── near-lineage donor (fragment 3.25, mult 1.0) — produced current best ─────
# This donor is not in the EoH archive; it came from an earlier mutation step.
NEAR_LINEAGE_DONOR_CODE = """\
import numpy as np

def score(item, bins):
    remainder = bins - item

    utilization_score = item / bins

    small_remainder_incentive = 1.0 / (1.0 + remainder / item)

    steepness_multiple = 20.0
    multiplicity_bonus = np.exp(
        -steepness_multiple * (np.round(remainder / item) - remainder / item) ** 2
    )

    fragment_penalty_term = np.where(
        (remainder > 0) & (remainder < item),
        (1.0 - (remainder / item)) ** 4,
        0.0,
    )
    fragment_penalty_magnitude = 3.25

    combined_score_for_non_perfect_fits = (
        utilization_score
        + 0.5 * small_remainder_incentive
        + 1.0 * multiplicity_bonus
        - fragment_penalty_magnitude * fragment_penalty_term
    )

    scores = np.where(remainder == 0, np.inf, combined_score_for_non_perfect_fits)
    return scores
"""
NEAR_LINEAGE_DONOR_FITNESS = 0.0074454170439681834

ARCHIVE_DIR = (
    REFINEMENT_DIR
    / "external_runs"
    / "results_old_run"
    / "pops"
    / "pops"
)

ONE_OFF_RESULTS_DIR = REFINEMENT_DIR / "one_off_results"


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_interface_api():
    api_path = REPO_ROOT / "eoh" / "src" / "eoh" / "llm" / "api_general.py"
    spec = importlib.util.spec_from_file_location("api_general", api_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.InterfaceAPI


def load_donor(donor_id: str, donor_code_file: str | None = None) -> dict[str, Any]:
    """Load a donor heuristic.

    Special donor_id values:
      'near_lineage'  — the near-lineage donor that produced the current best
    Archive format:
      'genG_idxI'     — e.g. 'gen3_idx3', loaded from the EoH archive
    Custom file:
      pass donor_code_file to load code from a .py file (donor_id used as label)
    """
    if donor_code_file:
        code = Path(donor_code_file).read_text(encoding="utf-8")
        return {"donor_id": donor_id or "custom_file", "algorithm": None,
                "code": code, "eoh_objective": None}

    if donor_id == "near_lineage":
        return {
            "donor_id": "near_lineage",
            "algorithm": None,
            "code": NEAR_LINEAGE_DONOR_CODE,
            "eoh_objective": None,
            "known_fitness": NEAR_LINEAGE_DONOR_FITNESS,
        }

    parts = donor_id.split("_")
    if len(parts) != 2 or not parts[0].startswith("gen") or not parts[1].startswith("idx"):
        raise ValueError(f"Invalid donor_id {donor_id!r}. Expected: genG_idxI or 'near_lineage'")
    gen = int(parts[0][3:])
    idx = int(parts[1][3:])

    pop_file = ARCHIVE_DIR / f"population_generation_{gen}.json"
    if not pop_file.exists():
        raise FileNotFoundError(f"Archive file not found: {pop_file}")

    with pop_file.open("r", encoding="utf-8") as fh:
        population = json.load(fh)

    if idx >= len(population):
        raise IndexError(
            f"Index {idx} out of range for generation {gen} (size {len(population)})"
        )

    entry = population[idx]
    return {
        "donor_id": donor_id,
        "algorithm": entry.get("algorithm"),
        "code": entry.get("code"),
        "eoh_objective": entry.get("objective"),
    }


def _rank_cases(case_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return worst / median / best case results by objective_gap."""
    ranked = sorted(case_results, key=lambda r: -r["objective_gap"])
    n = len(ranked)
    mid = n // 2
    return {
        "worst": ranked[0],
        "median": ranked[mid],
        "best": ranked[-1],
    }


def build_anchor_cases(
    instances: list[dict[str, Any]],
    incumbent_cases: list[dict[str, Any]],
    donor_cases: list[dict[str, Any]],
    incumbent_module,
    donor_module,
    context_labels: tuple[str, ...],
) -> dict[str, Any]:
    """Build the anchor_cases dict used in the mutation request."""
    inc_ranked = _rank_cases(incumbent_cases)
    don_ranked = _rank_cases(donor_cases)
    instances_by_id = {inst["instance_id"]: inst for inst in instances}

    anchor_cases: dict[str, Any] = {}
    for label in context_labels:
        # Use the incumbent's ranking to pick the instance
        ref_case = inc_ranked[label]
        instance_id = ref_case["instance_id"]
        instance = instances_by_id[instance_id]

        # Donor result on the same instance
        don_case = next(
            (r for r in donor_cases if r["instance_id"] == instance_id), None
        )
        if don_case is None:
            continue

        inc_trace = build_trace_preview_for_instance(incumbent_module, instance)
        don_trace = build_trace_preview_for_instance(donor_module, instance)

        anchor_cases[label] = {
            "instance_id": instance_id,
            "incumbent": {"case_result": ref_case, "trace_preview": inc_trace},
            "donor": {"case_result": don_case, "trace_preview": don_trace},
        }

    return anchor_cases


def interpolate_codes(code_a: str, code_b: str, fraction: float) -> str:
    """Return code_a with all float literals interpolated fraction-of-the-way toward code_b.

    fraction=0.0 → code_a unchanged, fraction=1.0 → code_b's values.
    Requires both codes to have the same number of float literals in the same positions
    (i.e. identical structure, only parameter values differ).
    Raises ValueError if the literal counts differ.
    """
    import re as _re
    pattern = _re.compile(r'\b\d+\.\d+\b')
    floats_a = list(pattern.finditer(code_a))
    floats_b = list(pattern.finditer(code_b))
    if len(floats_a) != len(floats_b):
        raise ValueError(
            f"interpolate_codes: literal count mismatch "
            f"({len(floats_a)} in incumbent vs {len(floats_b)} in proposal)"
        )
    result = list(code_a)
    for ma, mb in zip(reversed(floats_a), reversed(floats_b)):
        va, vb = float(ma.group()), float(mb.group())
        vi = va + fraction * (vb - va)
        vi_str = f"{vi:.6g}"
        result[ma.start():ma.end()] = list(vi_str)
    return "".join(result)


def classify_result(
    proposal_fitness: float,
    incumbent_fitness: float,
    donor_fitness: float,
    lane: str,
    *,
    use_dev: bool = False,
) -> str:
    """Classify on search_train fitness; dev fitness is separately reported."""
    delta = proposal_fitness - incumbent_fitness
    if delta < 0:
        return "new_best"
    if lane == "donor_rehabilitation":
        if proposal_fitness < donor_fitness:
            return "donor_progress"
        return "reject"
    promising_band = incumbent_fitness * 0.003  # within 0.3% of incumbent
    if delta <= promising_band:
        return "branch_progress"
    return "reject"


def save_episode(episode: dict[str, Any], output_dir: Path, tag: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"{ts}_poc_mutation_{tag}.json"
    path = output_dir / filename
    with path.open("w", encoding="utf-8") as fh:
        json.dump(episode, fh, indent=2, ensure_ascii=False)
    return path


def run_multi_seed(
    n_seeds: int,
    *,
    output_dir: Path,
    tag: str,
    **episode_kwargs,
) -> dict[str, Any]:
    """Run the same episode n_seeds times and return an aggregate record."""
    results = []
    for seed_idx in range(n_seeds):
        seed_tag = f"{tag}_seed{seed_idx}"
        print(f"\n{'='*60}")
        print(f"SEED {seed_idx + 1} / {n_seeds}  (tag={seed_tag})")
        print(f"{'='*60}")
        ep = run_episode(tag=seed_tag, output_dir=output_dir, **episode_kwargs)
        save_episode(ep, output_dir, seed_tag)
        results.append(ep)

    # Aggregate
    fitnesses = [
        r["final_core_fitness"]
        for r in results
        if r.get("final_core_fitness") is not None
    ]
    classifications = [r.get("classification", "unknown") for r in results]

    import numpy as np_inner
    aggregate = {
        "multi_seed_tag": tag,
        "n_seeds": n_seeds,
        "seed_classifications": classifications,
        "n_new_best": classifications.count("new_best"),
        "n_donor_progress": classifications.count("donor_progress"),
        "n_branch_progress": classifications.count("branch_progress"),
        "n_reject": classifications.count("reject"),
        "fitness_mean": float(np_inner.mean(fitnesses)) if fitnesses else None,
        "fitness_std": float(np_inner.std(fitnesses)) if fitnesses else None,
        "fitness_min": float(np_inner.min(fitnesses)) if fitnesses else None,
        "fitness_max": float(np_inner.max(fitnesses)) if fitnesses else None,
        "incumbent_core_fitness": results[0].get("incumbent_core_fitness"),
    }
    agg_path = save_episode(aggregate, output_dir, f"{tag}_aggregate")
    print(f"\nAggregate saved: {agg_path}")
    return aggregate


def _print_summary(episode: dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print("EPISODE SUMMARY")
    print("=" * 60)
    print(f"  incumbent fitness : {episode['incumbent_core_fitness']:.10f}")
    print(f"  donor id          : {episode['donor_id']}")
    print(f"  donor fitness     : {episode.get('donor_core_fitness', 'n/a')}")
    print(f"  context policy    : {episode['context_policy']}")
    print(f"  novelty constraint: {episode['novelty_constraint']}")
    print(f"  lane              : {episode['lane']}")
    print(f"  proposal status   : {episode.get('proposal_status', 'n/a')}")
    print(f"  proposal family   : {episode.get('proposal_patch_family', 'n/a')}")
    print(f"  critic decision   : {episode.get('critic_decision', 'n/a')}")
    print(f"  revision used     : {episode.get('revision_used', False)}")
    print(f"  final fitness     : {episode.get('final_core_fitness', 'n/a')}")
    print(f"  delta vs incumbent: {episode.get('delta_vs_incumbent', 'n/a')}")
    print(f"  classification    : {episode.get('classification', 'n/a')}")
    print("=" * 60)


# ── main ──────────────────────────────────────────────────────────────────────

def run_episode(
    *,
    api_key: str,
    api_endpoint: str,
    model: str,
    donor_id: str,
    donor_code_file: str | None = None,
    context_policy: str,
    novelty_constraint: bool,
    lane: str,
    banned_patch_families: tuple[str, ...],
    dry_run: bool,
    tag: str,
    output_dir: Path,
    incumbent_code: str = INCUMBENT_CODE,
    incumbent_fitness: float = INCUMBENT_CORE_FITNESS,
    prompt_variant: str = "constrained",
) -> dict[str, Any]:

    print(f"\n[1/8] Loading instances...")
    instances = load_split_instances("search_train")
    try:
        dev_instances = load_split_instances("dev")
        has_dev = True
    except FileNotFoundError:
        dev_instances = []
        has_dev = False
    print(f"      search_train={len(instances)}  dev={'not generated yet' if not has_dev else len(dev_instances)}")

    print(f"[2/8] Loading donor: {donor_id}")
    donor = load_donor(donor_id, donor_code_file)
    print(f"      donor loaded (eoh_objective={donor.get('eoh_objective')})")

    print(f"[3/8] Evaluating incumbent...")
    inc_module = load_heuristic_module_from_code(incumbent_code)
    inc_cases = evaluate_heuristic_on_instances(instances, heuristic_module=inc_module)
    inc_summary = summarize_case_results(inc_cases)
    print(f"      incumbent mean_gap={inc_summary['mean_objective_gap']:.8f}")

    print(f"[4/8] Evaluating donor...")
    don_module = load_heuristic_module_from_code(donor["code"])
    don_cases = evaluate_heuristic_on_instances(instances, heuristic_module=don_module)
    don_summary = summarize_case_results(don_cases)
    donor_core_fitness = don_summary["mean_objective_gap"]
    print(f"      donor mean_gap={donor_core_fitness:.8f}")

    labels = tuple(context_policy.split("+"))  # e.g. "worst+best" → ("worst","best")

    print(f"[5/8] Building anchor cases ({context_policy})...")
    anchor_cases = build_anchor_cases(
        instances, inc_cases, don_cases, inc_module, don_module, labels
    )

    incumbent_dict = {
        "core_fitness": incumbent_fitness,
        "summary": inc_summary,
        "code": incumbent_code,
    }
    donor_dict = {
        "core_fitness": donor_core_fitness,
        "summary": don_summary,
        "algorithm": donor.get("algorithm"),
        "code": donor["code"],
    }

    mutation_req = build_mutation_request(
        incumbent_dict,
        donor_dict,
        anchor_cases,
        novelty_constraint=novelty_constraint,
        banned_patch_families=banned_patch_families,
        incumbent_description=f"Current best incumbent (fitness {incumbent_fitness:.10f})",
        donor_description=f"Archived donor {donor_id} (fitness {donor_core_fitness:.8f})",
    )
    if prompt_variant in ("minimal", "two_phase"):
        mutation_prompt = build_mutation_prompt_minimal(mutation_req)
    else:
        mutation_prompt = build_mutation_prompt(mutation_req)

    episode: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "api_endpoint": api_endpoint,
        "lane": lane,
        "prompt_variant": prompt_variant,
        "incumbent_core_fitness": incumbent_fitness,
        "donor_id": donor_id,
        "donor_core_fitness": donor_core_fitness,
        "context_policy": context_policy,
        "novelty_constraint": novelty_constraint,
        "banned_patch_families": list(banned_patch_families),
        "per_instance_results_incumbent": inc_cases,
        "per_instance_results_donor": don_cases,
        "mutation_request": mutation_req,
        "raw_mutation_prompt": mutation_prompt,
    }

    if dry_run:
        print("\n[DRY RUN] Mutation prompt:\n")
        print(mutation_prompt[:3000])
        if len(mutation_prompt) > 3000:
            print(f"\n... [truncated, total {len(mutation_prompt)} chars]")
        episode["dry_run"] = True
        return episode

    # ── LLM calls ────────────────────────────────────────────────────────────
    InterfaceAPI = _load_interface_api()
    llm = InterfaceAPI(
        api_endpoint=api_endpoint,
        api_key=api_key,
        model_LLM=model,
        debug_mode=False,
    )

    print(f"[6/8] Calling LLM for mutation proposal ({model})...")
    raw_mutation_response = llm.get_response(mutation_prompt)
    episode["raw_mutation_response"] = raw_mutation_response

    try:
        proposal = parse_repair_proposal(raw_mutation_response)
    except Exception as exc:
        print(f"      WARN: failed to parse proposal — {exc}")
        episode["proposal_status"] = "parse_error"
        episode["parse_error"] = str(exc)
        episode["classification"] = "reject"
        return episode

    episode["proposal_status"] = proposal["status"]
    episode["proposal_patch_family"] = proposal.get("patch_family")
    episode["proposal_confidence"] = proposal.get("confidence")
    episode["proposal_rationale"] = proposal.get("rationale")
    episode["proposal_change_summary"] = proposal.get("proposed_change_summary")
    episode["proposal_code"] = proposal.get("proposed_code")
    print(f"      status={proposal['status']}  family={proposal.get('patch_family')}  "
          f"confidence={proposal.get('confidence')}")

    if proposal["status"] != "proposed_patch" or not proposal.get("proposed_code"):
        episode["classification"] = "no_patch"
        return episode

    # ── triage critic ─────────────────────────────────────────────────────────
    print(f"[7/8] Running triage critic...")
    critic_prompt = build_critic_prompt(mutation_req, proposal)
    raw_critic_response = llm.get_response(critic_prompt)
    episode["raw_critic_prompt"] = critic_prompt
    episode["raw_critic_response"] = raw_critic_response

    try:
        critic = parse_critic_response(raw_critic_response)
    except Exception as exc:
        print(f"      WARN: failed to parse critic response — {exc}")
        critic = {"decision": "approve", "confidence": 0.5,
                  "summary": "parse_error — defaulting to approve", "revision_guidance": None}

    episode["critic_decision"] = critic["decision"]
    episode["critic_confidence"] = critic["confidence"]
    episode["critic_summary"] = critic["summary"]
    episode["revision_used"] = False
    print(f"      critic={critic['decision']}  confidence={critic['confidence']:.2f}")

    final_proposal = proposal

    if critic["decision"] == "reject":
        episode["classification"] = "reject"
        print(f"      critic rejected the proposal.")
        return episode

    if critic["decision"] == "revise" and critic.get("revision_guidance"):
        print(f"      critic requested revision — running one revision round...")
        revision_prompt = build_revision_prompt(
            mutation_req, proposal, critic["revision_guidance"]
        )
        raw_revision_response = llm.get_response(revision_prompt)
        episode["raw_revision_prompt"] = revision_prompt
        episode["raw_revision_response"] = raw_revision_response
        episode["revision_used"] = True

        try:
            revised = parse_repair_proposal(raw_revision_response)
            if revised["status"] == "proposed_patch" and revised.get("proposed_code"):
                final_proposal = revised
                episode["revised_proposal_status"] = revised["status"]
                episode["revised_proposal_patch_family"] = revised.get("patch_family")
                episode["revised_proposal_code"] = revised.get("proposed_code")
                episode["revised_proposal_rationale"] = revised.get("rationale")
                print(f"      revision accepted: family={revised.get('patch_family')}")
            else:
                print(f"      revision returned no_patch — using original proposal")
        except Exception as exc:
            print(f"      WARN: revision parse failed — {exc}. Using original proposal.")

    # ── two-phase: step-size search along the LLM's direction ────────────────
    if prompt_variant == "two_phase" and final_proposal.get("proposed_code"):
        fractions = [0.1, 0.2, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.75, 1.0]
        print(f"[7b/8] Two-phase step search ({fractions})...")
        step_results = []
        best_step_code = None
        best_step_fitness = float("inf")

        for frac in fractions:
            try:
                interp_code = interpolate_codes(
                    incumbent_code, final_proposal["proposed_code"], frac
                )
                interp_mod = load_heuristic_module_from_code(interp_code)
                interp_cases = evaluate_heuristic_on_instances(instances, heuristic_module=interp_mod)
                interp_fitness = summarize_case_results(interp_cases)["mean_objective_gap"]
                step_results.append({"fraction": frac, "fitness": interp_fitness})
                print(f"       frac={frac:.2f}  train={interp_fitness:.8f}")
                if interp_fitness < best_step_fitness:
                    best_step_fitness = interp_fitness
                    best_step_code = interp_code
                    best_step_fraction = frac
            except Exception as exc:
                step_results.append({"fraction": frac, "error": str(exc)})
                print(f"       frac={frac:.2f}  ERROR: {exc}")

        episode["two_phase_step_results"] = step_results
        if best_step_code and best_step_fitness < incumbent_fitness:
            print(f"       best fraction: {best_step_fraction} (train={best_step_fitness:.8f})")
            episode["two_phase_best_fraction"] = best_step_fraction
            final_proposal = dict(final_proposal)
            final_proposal["proposed_code"] = best_step_code
        else:
            print(f"       no step improved over incumbent — using fraction=1.0")
            episode["two_phase_best_fraction"] = 1.0

    # ── evaluate final proposal on search_train ───────────────────────────────
    print(f"[8/8] Evaluating proposal...")
    try:
        prop_module = load_heuristic_module_from_code(final_proposal["proposed_code"])
        prop_cases = evaluate_heuristic_on_instances(instances, heuristic_module=prop_module)
        prop_summary = summarize_case_results(prop_cases)
        final_fitness = prop_summary["mean_objective_gap"]
        delta = final_fitness - incumbent_fitness

        episode["per_instance_results_proposal"] = prop_cases
        episode["final_core_fitness_search_train"] = final_fitness
        episode["delta_vs_incumbent_search_train"] = delta
        episode["delta_vs_donor"] = final_fitness - donor_core_fitness

        classification = classify_result(final_fitness, incumbent_fitness, donor_core_fitness, lane)
        episode["classification_search_train"] = classification

        print(f"      search_train fitness : {final_fitness:.10f}")
        print(f"      delta vs incumbent   : {delta:+.10f}")
        print(f"      classification       : {classification}")

        # ── evaluate on dev split (acceptance gate) ───────────────────────────
        if has_dev:
            # incumbent dev fitness for reference
            inc_dev_cases = evaluate_heuristic_on_instances(dev_instances, heuristic_module=inc_module)
            inc_dev_summary = summarize_case_results(inc_dev_cases)
            inc_dev_fitness = inc_dev_summary["mean_objective_gap"]

            prop_dev_cases = evaluate_heuristic_on_instances(dev_instances, heuristic_module=prop_module)
            prop_dev_summary = summarize_case_results(prop_dev_cases)
            prop_dev_fitness = prop_dev_summary["mean_objective_gap"]
            dev_delta = prop_dev_fitness - inc_dev_fitness

            episode["incumbent_core_fitness_dev"] = inc_dev_fitness
            episode["final_core_fitness_dev"] = prop_dev_fitness
            episode["delta_vs_incumbent_dev"] = dev_delta
            episode["per_instance_results_proposal_dev"] = prop_dev_cases

            # Classification requires improvement on BOTH splits to be accepted
            if delta < 0 and dev_delta < 0:
                classification_dev = "new_best"
            elif delta < 0 and dev_delta >= 0:
                classification_dev = "new_best_train_only"  # overfits to search_train
            elif lane == "donor_rehabilitation" and final_fitness < donor_core_fitness:
                classification_dev = "donor_progress"
            elif delta <= incumbent_fitness * 0.003:
                classification_dev = "branch_progress"
            else:
                classification_dev = "reject"

            episode["classification"] = classification_dev
            print(f"      dev fitness          : {prop_dev_fitness:.10f}")
            print(f"      dev delta            : {dev_delta:+.10f}")
            print(f"      classification (dev) : {classification_dev}")
        else:
            episode["classification"] = classification
            episode["dev_note"] = "dev split not available — run generate_eval_splits.py"
            print(f"      WARNING: dev split not available. Classification is train-only.")

        # canonical field for backward compat
        episode["final_core_fitness"] = final_fitness
        episode["delta_vs_incumbent"] = delta

    except Exception as exc:
        print(f"      ERROR evaluating proposal — {exc}")
        episode["evaluation_error"] = str(exc)
        episode["evaluation_traceback"] = traceback.format_exc()
        episode["classification"] = "reject"

    return episode


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PoC mutation episode runner")
    p.add_argument("--api-key", default=None,
                   help="API key (or set GROQ_API_KEY / EOH_API_KEY env var)")
    p.add_argument("--api-endpoint", default="https://api.groq.com/openai/v1")
    p.add_argument("--model", default="qwen/qwen3-32b")
    p.add_argument("--donor-id", default="gen3_idx3",
                   help="Donor heuristic id: genG_idxI, or 'near_lineage' (default: gen3_idx3)")
    p.add_argument("--donor-code-file", default=None,
                   help="Path to a .py file containing the donor's score() function")
    p.add_argument("--context-policy", default="worst+best",
                   help="Anchor case labels, e.g. worst+best or worst+median+best")
    p.add_argument("--no-novelty", action="store_true",
                   help="Disable novelty constraint (not recommended for near donors)")
    p.add_argument("--lane", default="incumbent_challenge",
                   choices=["incumbent_challenge", "donor_rehabilitation", "branch_continuation"])
    p.add_argument("--banned-families", nargs="*", default=[],
                   help="Patch families to ban, e.g. parameter_extrapolation")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the mutation prompt without calling the LLM")
    p.add_argument("--tag", default="",
                   help="Short label appended to output filename")
    p.add_argument("--n-seeds", type=int, default=1,
                   help="Run this many independent seeds and aggregate (default: 1)")
    p.add_argument("--output-dir", default=str(ONE_OFF_RESULTS_DIR))
    p.add_argument("--prompt-variant", default="constrained",
                   choices=["constrained", "minimal", "two_phase"],
                   help="'constrained': interpolation rules. 'minimal': evidence-only. 'two_phase': minimal direction + automatic step-size search.")
    p.add_argument("--incumbent-code-file", default=None,
                   help="Path to a .py file to use as the incumbent (overrides default)")
    p.add_argument("--incumbent-fitness", type=float, default=None,
                   help="Known search_train fitness of the custom incumbent (optional)")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    api_key = (
        args.api_key
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("EOH_API_KEY")
    )
    if not api_key and not args.dry_run:
        print("ERROR: provide --api-key or set GROQ_API_KEY env var.")
        sys.exit(1)

    donor_label = args.donor_id.replace("/", "-")
    tag = args.tag or f"{donor_label}_{args.context_policy.replace('+', '_')}"

    print(f"PoC Mutation Runner")
    print(f"  model      : {args.model}")
    print(f"  endpoint   : {args.api_endpoint}")
    print(f"  donor      : {args.donor_id}")
    print(f"  context    : {args.context_policy}")
    print(f"  novelty    : {not args.no_novelty}")
    print(f"  lane       : {args.lane}")
    print(f"  dry_run    : {args.dry_run}")

    incumbent_code = INCUMBENT_CODE
    incumbent_fitness = INCUMBENT_CORE_FITNESS
    if args.incumbent_code_file:
        incumbent_code = Path(args.incumbent_code_file).read_text(encoding="utf-8")
        # If fitness not provided, evaluate it at runtime (run_episode will measure it)
        if args.incumbent_fitness is not None:
            incumbent_fitness = args.incumbent_fitness

    episode_kwargs = dict(
        api_key=api_key or "dry-run",
        api_endpoint=args.api_endpoint,
        model=args.model,
        donor_id=args.donor_id,
        donor_code_file=args.donor_code_file,
        context_policy=args.context_policy,
        novelty_constraint=not args.no_novelty,
        lane=args.lane,
        banned_patch_families=tuple(args.banned_families),
        dry_run=args.dry_run,
        incumbent_code=incumbent_code,
        incumbent_fitness=incumbent_fitness,
        prompt_variant=args.prompt_variant,
    )

    if args.n_seeds > 1 and not args.dry_run:
        aggregate = run_multi_seed(
            args.n_seeds,
            output_dir=Path(args.output_dir),
            tag=tag,
            **episode_kwargs,
        )
        print(f"\n{'='*60}")
        print(f"MULTI-SEED AGGREGATE  (n={args.n_seeds})")
        print(f"  fitness mean ± std : {aggregate['fitness_mean']:.8f} ± {aggregate['fitness_std']:.8f}")
        print(f"  fitness range      : [{aggregate['fitness_min']:.8f}, {aggregate['fitness_max']:.8f}]")
        print(f"  classifications    : {aggregate['seed_classifications']}")
        print(f"{'='*60}")
    else:
        episode = run_episode(tag=tag, output_dir=Path(args.output_dir), **episode_kwargs)
        if not args.dry_run:
            _print_summary(episode)
            out_path = save_episode(episode, Path(args.output_dir), tag)
            print(f"\nEpisode saved: {out_path}")


if __name__ == "__main__":
    main()
