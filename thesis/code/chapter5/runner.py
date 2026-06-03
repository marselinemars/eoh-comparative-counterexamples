"""
thesis/code/chapter5/runner.py

Full pipeline for one chapter-5 proposal: seed derivation, strategy
invocation, prompt rendering, LLM call, sanitization, scoring on
train_step and train_gate, provenance record writing.

One record per LLM call. No batching in this module. The
`run_single_proposal` function is pure-ish with the side effects
of (1) one LLM HTTP request and (2) one provenance JSON file write.
"""
from __future__ import annotations

import json
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from thesis.code.chapter5 import (
    DETERMINISTIC_STRATEGY_NAMES,
    STOCHASTIC_STRATEGY_NAMES,
    STRATEGIES,
)
from thesis.code.chapter5.llm_client import call_llm
from thesis.code.chapter5.prompt_builder import build_prompt
from thesis.code.chapter5.sanitize import sanitize
from thesis.code.chapter5.seeds import (
    MASTER_SEED_CH5,
    llm_seed,
    set_seed,
)
from thesis.code.counterexample import CounterexampleSet
from thesis.code.evaluation import bins_used
from thesis.code.incumbents import load_final_population
from thesis.code.score_cache import ScoreCache, code_hash
from thesis.code.splits import load_split, qualified_instance_id


def _reference_code_for_pool(pool: CounterexampleSet) -> str:
    """Look up the source of the pool's single reference heuristic."""
    reference_hashes = {c.reference_hash for c in pool}
    if len(reference_hashes) != 1:
        raise RuntimeError(
            f"Chapter-5 pool must have a single reference hash; "
            f"found {reference_hashes}"
        )
    target_hash = next(iter(reference_hashes))
    for member in load_final_population():
        if member["code_hash"] == target_hash:
            return member["code"]
    raise RuntimeError(
        f"Reference heuristic {target_hash!r} not found in EoH final "
        "population."
    )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _score_heuristic_on_split(
    score_fn,
    proposal_code: str,
    proposal_hash: str,
    split_name: str,
    cache: ScoreCache,
) -> Dict[str, Any]:
    """Score a heuristic on every instance of a named split, routing
    through the persistent cache. Returns per-instance bin counts and
    the mean.

    The proposal's code string is hashed once to derive its cache
    key. A fresh cache-backed call_or_compute runs the proposal on
    any instance not yet cached; same-hash proposals reuse cached
    values across seeds.
    """
    split = load_split(split_name)
    per_instance = []

    # Build a throwaway "module" object with a .score attribute so
    # we can reuse evaluation.bins_used without re-exec'ing the
    # proposal per instance.
    module_shim = types.ModuleType(f"proposal_{proposal_hash}")
    module_shim.score = score_fn
    # numpy has already been imported into the namespace that
    # produced `score_fn`; nothing more to do.

    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        b = cache.get_or_compute(
            proposal_hash,
            qid,
            lambda i=inst: bins_used(module_shim, i),
        )
        per_instance.append(b)
    arr = np.array(per_instance)
    return {
        "per_instance": per_instance,
        "mean": float(arr.mean()) if arr.size > 0 else None,
    }


def _score_baseline_on_split(
    incumbent_module,
    incumbent_hash: str,
    split_name: str,
    cache: ScoreCache,
) -> Dict[str, Any]:
    """Score h_eoh on a named split. Goes through the same cache."""
    split = load_split(split_name)
    per_instance = []
    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        b = cache.get_or_compute(
            incumbent_hash,
            qid,
            lambda i=inst: bins_used(incumbent_module, i),
        )
        per_instance.append(b)
    arr = np.array(per_instance)
    return {
        "per_instance": per_instance,
        "mean": float(arr.mean()) if arr.size > 0 else None,
    }


def _compute_metrics(
    baseline_step: Dict[str, Any],
    proposal_step: Dict[str, Any],
    baseline_gate: Dict[str, Any],
    proposal_gate: Dict[str, Any],
) -> Dict[str, Any]:
    delta_step = baseline_step["mean"] - proposal_step["mean"]
    delta_gate = baseline_gate["mean"] - proposal_gate["mean"]
    generalization_gap = delta_step - delta_gate
    wins = sum(
        1
        for b, p in zip(baseline_step["per_instance"], proposal_step["per_instance"])
        if p < b
    )
    n = len(baseline_step["per_instance"])
    win_rate_step = wins / n if n > 0 else None
    return {
        "mean_bins_h_eoh_train_step": baseline_step["mean"],
        "mean_bins_proposal_train_step": proposal_step["mean"],
        "mean_bins_h_eoh_train_gate": baseline_gate["mean"],
        "mean_bins_proposal_train_gate": proposal_gate["mean"],
        "delta_step": delta_step,
        "delta_gate": delta_gate,
        "generalization_gap": generalization_gap,
        "win_rate_step": win_rate_step,
        "per_instance_bins_proposal_train_step": proposal_step["per_instance"],
        "per_instance_bins_proposal_train_gate": proposal_gate["per_instance"],
    }


def _sanitization_record(sanitize_result: Dict[str, Any]) -> Dict[str, Any]:
    """Strip the non-serializable callable from the sanitize result
    before putting it in the provenance record."""
    return {
        "status": sanitize_result["status"],
        "error": sanitize_result["error"],
        "cleaned_code": sanitize_result["cleaned_code"],
        "reasoning": sanitize_result.get("reasoning"),
        "format_detected": sanitize_result.get("format_detected"),
    }


def run_single_proposal(
    strategy_name: str,
    set_index: int,
    seed_index: int,
    pool: CounterexampleSet,
    incumbent_heuristic: Dict[str, Any],
    output_dir: Path,
    *,
    k: int = 4,
    provider: str = "gemini",
    reasoning_effort: Optional[str] = None,
    max_output_tokens: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Run one full chapter-5 proposal and persist the provenance
    record.

    Parameters
    ----------
    strategy_name:
        One of the names registered in
        `thesis.code.chapter5.STRATEGIES`.
    set_index, seed_index:
        Identify this call's set and seed within the strategy's
        sampling matrix (§6.1 of chapter5_design.md).
    pool:
        The committed chapter-5 counterexample pool.
    incumbent_heuristic:
        The heuristic dict (as returned by
        `thesis.code.incumbents.get_h_eoh`). Must include keys
        ``code``, ``code_hash``, ``algorithm``.
    output_dir:
        Directory to write the provenance JSON into. Created if
        missing.
    k:
        Cardinality (default 4 for chapter 5).

    Returns
    -------
    dict: the provenance record (also written to disk).
    """
    started_at = _utcnow_iso()

    if strategy_name not in STRATEGIES:
        raise ValueError(
            f"Unknown strategy: {strategy_name}. "
            f"Valid: {sorted(STRATEGIES.keys())}"
        )
    strategy = STRATEGIES[strategy_name]

    derived_set_seed = set_seed(strategy_name, set_index)
    derived_llm_seed = llm_seed(strategy_name, set_index, seed_index)

    # Strategy invocation
    if strategy_name in STOCHASTIC_STRATEGY_NAMES:
        rng = np.random.default_rng(derived_set_seed)
        counterexample_set = strategy(pool, k, rng=rng)
    elif strategy_name in DETERMINISTIC_STRATEGY_NAMES:
        counterexample_set = strategy(pool, k)
    else:
        raise RuntimeError(
            f"Strategy {strategy_name!r} is not classified as "
            "deterministic or stochastic."
        )

    # Prompt assembly. Reference source is pulled from EoH's final
    # population by the pool's reference_hash (chapter 5 uses one
    # shared reference across the pool).
    reference_code = _reference_code_for_pool(pool)
    prompt = build_prompt(
        counterexample_set=counterexample_set,
        incumbent_code=incumbent_heuristic["code"],
        reference_code=reference_code,
    )

    # LLM call.
    # Provider defaults to "gemini" (primary model per 2026-04-21
    # decisions-log entries); caller can override to "groq" for the
    # provisional batch per the 2026-04-22 entry. reasoning_effort
    # and max_output_tokens are pinned production settings.
    effective_reasoning_effort = (
        reasoning_effort if reasoning_effort is not None else "low"
    )
    effective_max_output_tokens = (
        max_output_tokens if max_output_tokens is not None else 8192
    )
    # Socket read timeout. Default 300s matches the probe; medium
    # reasoning can take >120s per call which exceeds call_llm's
    # 90s library default.
    effective_timeout_seconds = (
        timeout_seconds if timeout_seconds is not None else 300.0
    )
    llm_response = call_llm(
        provider=provider,
        prompt=prompt,
        seed=derived_llm_seed,
        reasoning_effort=effective_reasoning_effort,
        max_output_tokens=effective_max_output_tokens,
        timeout_seconds=effective_timeout_seconds,
    )
    raw_response = llm_response["text"]

    # Sanitization (runtime check uses the first instance of the pool)
    split_train_select = load_split("train_select")
    sanity_instance = split_train_select["instances"][0]
    sanitize_result = sanitize(raw_response, sanity_instance)

    # Scoring (only if sanitization succeeded)
    scoring_record: Optional[Dict[str, Any]] = None
    proposal_hash: Optional[str] = None
    if sanitize_result["status"] == "ok":
        cache = ScoreCache()
        proposal_code = sanitize_result["cleaned_code"]
        proposal_hash = code_hash(proposal_code)

        # Score baseline (h_eoh) on both splits via cache.
        # incumbent_heuristic['module'] isn't present; construct a
        # shim with numpy loaded and the real incumbent source.
        incumbent_module = types.ModuleType(
            f"incumbent_{incumbent_heuristic['code_hash']}"
        )
        # Exec h_eoh's source into the shim so its `score` is real.
        exec(
            compile(
                incumbent_heuristic["code"],
                "<h_eoh>",
                "exec",
            ),
            incumbent_module.__dict__,
        )

        baseline_step = _score_baseline_on_split(
            incumbent_module,
            incumbent_heuristic["code_hash"],
            "train_step",
            cache,
        )
        baseline_gate = _score_baseline_on_split(
            incumbent_module,
            incumbent_heuristic["code_hash"],
            "train_gate",
            cache,
        )
        proposal_step = _score_heuristic_on_split(
            sanitize_result["score_fn"],
            proposal_code,
            proposal_hash,
            "train_step",
            cache,
        )
        proposal_gate = _score_heuristic_on_split(
            sanitize_result["score_fn"],
            proposal_code,
            proposal_hash,
            "train_gate",
            cache,
        )
        cache.save()

        scoring_record = _compute_metrics(
            baseline_step, proposal_step, baseline_gate, proposal_gate
        )

    finished_at = _utcnow_iso()

    # Derive the reference hash from the pool (all counterexamples
    # share one reference in chapter 5).
    reference_hashes = {c.reference_hash for c in pool}
    if len(reference_hashes) != 1:
        raise RuntimeError(
            f"Chapter-5 pool must have a single reference hash; "
            f"found {reference_hashes}"
        )
    reference_hash = next(iter(reference_hashes))

    record: Dict[str, Any] = {
        "master_seed": MASTER_SEED_CH5,
        "provider": provider,
        "strategy_name": strategy_name,
        "set_index": set_index,
        "seed_index": seed_index,
        "set_seed": derived_set_seed,
        "llm_seed": derived_llm_seed,
        "k": k,
        "counterexample_set": json.loads(counterexample_set.to_json()),
        "incumbent_hash": incumbent_heuristic["code_hash"],
        "reference_hash": reference_hash,
        "proposal_hash": proposal_hash,
        "prompt": prompt,
        "raw_response": raw_response,
        "llm_metadata": {
            "model": llm_response["model"],
            "temperature": llm_response["temperature"],
            "max_output_tokens": llm_response["max_output_tokens"],
            "reasoning_effort": llm_response["reasoning_effort"],
            "reasoning_effort_requested": reasoning_effort,
            "max_output_tokens_requested": max_output_tokens,
            "seed_requested": llm_response["seed_requested"],
            "seed_honored": llm_response["seed_honored"],
            "raw_response_metadata": llm_response["raw_response_metadata"],
        },
        "sanitization": _sanitization_record(sanitize_result),
        "scoring": scoring_record,
        "timestamps": {
            "started_at": started_at,
            "finished_at": finished_at,
        },
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = (
        output_dir
        / f"{strategy_name}_{set_index}_{seed_index}.json"
    )
    out_path.write_text(
        json.dumps(record, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    record["_written_to"] = str(out_path)
    return record
