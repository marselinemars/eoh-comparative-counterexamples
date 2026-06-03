"""thesis/code/chapter7/validation_runner.py

Chapter 7 validation-batch trajectory orchestration.

Per ``chapter7_design.md`` §4.2, §5, §8.2, §11, §18.6: each
of the 14 cells runs ``n_trajectories`` trajectories of
``n_steps`` steps each. Each step:

  1. Pool rebuilt against the trajectory's current incumbent.
  2. Strategy applied to the rebuilt pool with the trajectory
     seed (``ch7:traj:set:{strategy}@L{level}@k{k}:traj{t}:step{i}``).
  3. Prompt rendered (L1 via ch5; L2 via ch6 with trace against
     the *current* incumbent).
  4. Vertex AI call (gemini-2.5-pro, medium reasoning,
     32k max output, temp 1.0; thinkingBudget=10240 maps from
     reasoning_effort="medium" per the §3.5 patched lock).
  5. Sanitization (ch5 §8 pipeline).
  6. If sanitization OK: score on train_step, apply
     ``should_accept_proposal``; promote proposal to current
     incumbent iff accepted.
  7. Atomic per-step record write.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import types
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from thesis.code.chapter5 import STRATEGIES as _CH5_STRATEGIES
from thesis.code.chapter5.llm_client import call_llm as _ch5_call_llm
from thesis.code.chapter5.sanitize import sanitize
from thesis.code.chapter5.validation import (
    compute_per_instance_bins_for_heuristic,
    rebuild_pool_against_incumbent,
    should_accept_proposal,
    REJECT_REGRESSION,
    REJECT_EQUIVALENT,
)
from thesis.code.chapter5.analysis import is_argmax_equivalent_to_h_eoh
from thesis.code.chapter6.batch_runner import _build_incumbent_module
from thesis.code.chapter6.trace_extractor import (
    DecisionRecord,
    extract_incumbent_trace,
)
from thesis.code.chapter7.batch_runner import (
    MAX_OUTPUT_TOKENS_DEFAULT,
    PROVIDER_DEFAULT,
    REASONING_EFFORT_DEFAULT,
    TEMPERATURE_DEFAULT,
    TIMEOUT_SECONDS_DEFAULT,
    PersistentCreditsExhausted,
    _atomic_write_json,
    _llm_call_with_retry,
)
from thesis.code.chapter7.prompt_builder import build_prompt
from thesis.code.chapter7.seeds import (
    MASTER_SEED_CH7,
    trajectory_llm_seed_ch7,
    trajectory_set_seed_ch7,
)
from thesis.code.chapter7.strategies import worst_only_at_k1
from thesis.code.counterexample import CounterexampleSet
from thesis.code.score_cache import ScoreCache, code_hash
from thesis.code.splits import load_split, qualified_instance_id

CHAPTER5_REFERENCE_HASH = "62a2846c597e"
REJECT_SANITIZE_FAILED = "rejected_sanitize_failed"
REJECT_API_ERROR = "rejected_api_error"

# Strategy registry: ch5 strategies + ch7's worst_only_at_k1.
_CH7_STRATEGIES = dict(_CH5_STRATEGIES)
_CH7_STRATEGIES["worst_only_at_k1"] = worst_only_at_k1
_DETERMINISTIC_NAMES = frozenset({"worst_only", "worst_plus_best",
                                  "most_discriminative",
                                  "worst_only_at_k1"})


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _step_filename(cell_id: str, traj_idx: int, step_idx: int) -> str:
    return f"chapter7_validation_{cell_id}_traj{traj_idx}_step{step_idx}.json"


def _load_reference_source() -> str:
    from thesis.code.incumbents import load_final_population
    for m in load_final_population():
        if m["code_hash"] == CHAPTER5_REFERENCE_HASH:
            return m["code"]
    raise RuntimeError(
        f"reference {CHAPTER5_REFERENCE_HASH!r} not found in EoH population"
    )


def _train_select_lookup() -> Dict[str, Dict[str, Any]]:
    split = load_split("train_select")
    return {
        qualified_instance_id("train_select", inst["instance_id"]): inst
        for inst in split["instances"]
    }


def _select_set(
    strategy: str, pool: CounterexampleSet, k: int, set_seed: int,
) -> CounterexampleSet:
    fn = _CH7_STRATEGIES[strategy]
    if strategy in _DETERMINISTIC_NAMES:
        return fn(pool, k=k)
    rng = np.random.default_rng(set_seed)
    return fn(pool, k=k, rng=rng)


def _make_proposal_incumbent(
    proposal_hash: str, proposal_source: str,
) -> Dict[str, Any]:
    return {
        "code": proposal_source,
        "code_hash": proposal_hash,
        "algorithm": f"ch7_validation_proposal_{proposal_hash}",
    }


# ---------------------------------------------------------------------
# Per-step orchestration
# ---------------------------------------------------------------------


def run_chapter7_validation_step(
    *,
    cell_id: str,
    strategy: str,
    level: int,
    k: int,
    trajectory_index: int,
    step_index: int,
    current_incumbent: Dict[str, Any],
    instance_lookup: Dict[str, Dict[str, Any]],
    reference_source: str,
    output_dir: Path,
    score_cache: ScoreCache,
    provider: str = PROVIDER_DEFAULT,
    reasoning_effort: str = REASONING_EFFORT_DEFAULT,
    max_output_tokens: int = MAX_OUTPUT_TOKENS_DEFAULT,
    temperature: float = TEMPERATURE_DEFAULT,
    timeout_seconds: float = TIMEOUT_SECONDS_DEFAULT,
) -> Dict[str, Any]:
    """Run one trajectory step end-to-end and write its per-step record.

    Returns the parsed record dict (which also got written to disk).
    The caller uses the returned ``next_incumbent_*`` fields to
    seed the next step.
    """
    started_at = _utcnow_iso()
    cell_traj_step_label = f"{cell_id}@k{k} traj={trajectory_index} step={step_index}"

    # --- pool rebuild ---
    pool = rebuild_pool_against_incumbent(
        incumbent=current_incumbent,
        reference_hash=CHAPTER5_REFERENCE_HASH,
        split_name="train_select",
        cache=score_cache,
    )
    pool_hash = hashlib.sha256(pool.to_json().encode("utf-8")).hexdigest()[:12]

    # --- seeds ---
    cell_label = f"{strategy}@L{level}@k{k}"
    set_seed = trajectory_set_seed_ch7(cell_label, trajectory_index, step_index)
    llm_seed = trajectory_llm_seed_ch7(cell_label, trajectory_index, step_index)

    # --- selection ---
    counterexample_set = _select_set(strategy, pool, k, set_seed)

    # --- L2 traces (against the *current* incumbent) ---
    traces: Optional[Sequence[Sequence[DecisionRecord]]] = None
    trace_summary: Optional[List[Dict[str, Any]]] = None
    if level == 2:
        incumbent_module_for_trace = _build_incumbent_module(current_incumbent)
        trace_lists: List[List[DecisionRecord]] = []
        for ce in counterexample_set:
            inst = instance_lookup[ce.instance_id]
            trace_lists.append(extract_incumbent_trace(inst, incumbent_module_for_trace))
        traces = trace_lists
        trace_summary = [{"trace_row_count": len(t)} for t in trace_lists]

    # --- prompt ---
    prompt = build_prompt(
        strategy=strategy,
        level=level,
        k=k,
        counterexample_set=counterexample_set,
        incumbent_code=current_incumbent["code"],
        reference_code=reference_source,
        traces=traces,
        instance_data_by_id=instance_lookup,
    )
    rendered_prompt_chars = len(prompt)

    # --- LLM call (with retry; persistent 429 raises to caller) ---
    llm_response: Optional[Dict[str, Any]] = None
    api_error: Optional[str] = None
    try:
        llm_response = _llm_call_with_retry(
            prompt=prompt,
            seed=llm_seed,
            provider=provider,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            log_prefix=f"[{cell_traj_step_label}]",
        )
    except PersistentCreditsExhausted:
        raise
    except Exception as exc:  # noqa: BLE001
        api_error = repr(exc)
        print(
            f"  [{cell_traj_step_label}] EXHAUSTED retries: {api_error[:300]}",
            flush=True,
        )

    # --- sanitize ---
    sanitization: Optional[Dict[str, Any]] = None
    sanitize_result: Optional[Dict[str, Any]] = None
    proposal_hash: Optional[str] = None
    if llm_response is not None:
        text = llm_response.get("text", "") or ""
        sanity_inst = next(iter(instance_lookup.values()))
        try:
            sanitize_result = sanitize(text, sanity_inst)
            sanitization = {
                "status": sanitize_result["status"],
                "error": sanitize_result.get("error"),
                "cleaned_code": sanitize_result.get("cleaned_code"),
                "reasoning": sanitize_result.get("reasoning"),
                "format_detected": sanitize_result.get("format_detected"),
            }
        except Exception as exc:
            sanitization = {
                "status": "error_during_sanitize",
                "error": repr(exc),
            }

    # --- score on train_step + acceptance rule ---
    delta_step_local: Optional[float] = None
    argmax_distinct: Optional[bool] = None
    acceptance_decision = "rejected"
    acceptance_reason: str
    if api_error is not None:
        acceptance_reason = REJECT_API_ERROR
    else:
        acceptance_reason = REJECT_SANITIZE_FAILED

    next_incumbent_hash = current_incumbent["code_hash"]
    next_incumbent_source = current_incumbent["code"]
    proposal_per_instance_step: Optional[List[int]] = None
    incumbent_per_instance_step: Optional[List[int]] = None

    if sanitize_result is not None and sanitize_result.get("status") == "ok":
        proposal_code = sanitize_result["cleaned_code"]
        proposal_hash = code_hash(proposal_code)
        # Score proposal on train_step.
        proposal_per_instance_step = compute_per_instance_bins_for_heuristic(
            proposal_code, proposal_hash, "train_step", cache=score_cache,
        )
        incumbent_per_instance_step = compute_per_instance_bins_for_heuristic(
            current_incumbent["code"], current_incumbent["code_hash"],
            "train_step", cache=score_cache,
        )
        n = len(incumbent_per_instance_step)
        if n > 0:
            inc_mean = sum(incumbent_per_instance_step) / n
            prop_mean = sum(proposal_per_instance_step) / n
            delta_step_local = inc_mean - prop_mean
            argmax_distinct = not is_argmax_equivalent_to_h_eoh(
                proposal_per_instance_step, incumbent_per_instance_step,
            )
            accepted, reason = should_accept_proposal(
                proposal_per_instance_step, incumbent_per_instance_step,
            )
            acceptance_decision = "accepted" if accepted else "rejected"
            acceptance_reason = reason
            if accepted:
                next_incumbent_hash = proposal_hash
                next_incumbent_source = proposal_code

    finished_at = _utcnow_iso()

    raw_meta = (llm_response or {}).get("raw_response_metadata") or {}
    llm_metadata: Optional[Dict[str, Any]] = None
    if llm_response is not None:
        llm_metadata = {
            "model": llm_response.get("model"),
            "temperature": llm_response.get("temperature"),
            "max_output_tokens": llm_response.get("max_output_tokens"),
            "reasoning_effort": llm_response.get("reasoning_effort"),
            "seed_requested": llm_response.get("seed_requested"),
            "seed_honored": llm_response.get("seed_honored"),
            "raw_response_metadata": raw_meta,
            "provider": llm_response.get("provider"),
        }

    record: Dict[str, Any] = {
        "chapter": "chapter7",
        "phase": "validation",
        "cell_id": cell_id,
        "strategy_name": strategy,
        "level": level,
        "k": k,
        "master_seed": MASTER_SEED_CH7,
        "trajectory_index": trajectory_index,
        "step_index": step_index,
        "trajectory_set_seed": set_seed,
        "trajectory_llm_seed": llm_seed,
        "current_incumbent_hash": current_incumbent["code_hash"],
        "current_incumbent_source": current_incumbent["code"],
        "pool_rebuild_pool_hash": pool_hash,
        "counterexample_set": json.loads(counterexample_set.to_json()),
        "rendered_prompt_chars": rendered_prompt_chars,
        "prompt": prompt,
        "raw_response": (llm_response or {}).get("text", "") or "",
        "proposal_hash": proposal_hash,
        "sanitization": sanitization,
        "scoring": {
            "delta_step_local": delta_step_local,
            "argmax_distinct": argmax_distinct,
            "per_instance_bins_proposal_train_step": proposal_per_instance_step,
            "per_instance_bins_incumbent_train_step": incumbent_per_instance_step,
        },
        "delta_step_local": delta_step_local,
        "argmax_distinct": argmax_distinct,
        "acceptance_decision": acceptance_decision,
        "acceptance_reason": acceptance_reason,
        "next_incumbent_hash": next_incumbent_hash,
        "next_incumbent_source": next_incumbent_source,
        "trace_summary": trace_summary,
        "llm_metadata": llm_metadata,
        "api_error": api_error,
        "timestamps": {"started_at": started_at, "finished_at": finished_at},
    }

    out_path = output_dir / _step_filename(cell_id, trajectory_index, step_index)
    _atomic_write_json(out_path, record)
    record["_written_to"] = str(out_path)
    return record


def load_step_record(
    output_dir: Path, cell_id: str, traj_idx: int, step_idx: int,
) -> Optional[Dict[str, Any]]:
    path = output_dir / _step_filename(cell_id, traj_idx, step_idx)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_step_complete(
    rec: Optional[Dict[str, Any]], retry_api_errors: bool = False,
) -> bool:
    if rec is None:
        return False
    if rec.get("chapter") != "chapter7" or rec.get("phase") != "validation":
        return False
    if retry_api_errors and (
        rec.get("api_error")
        or rec.get("acceptance_reason") == "rejected_api_error"
    ):
        return False
    san = rec.get("sanitization") or {}
    if isinstance(san, dict) and san.get("status"):
        return True
    if rec.get("api_error"):
        return True
    if rec.get("acceptance_reason"):
        return True
    return False


def incumbent_for_next_step(
    rec: Dict[str, Any], h_eoh: Dict[str, Any],
) -> Dict[str, Any]:
    """Given a completed step record, return the incumbent that the
    *next* step should use as `current_incumbent`.

    If the recorded acceptance_decision is "accepted", the new
    incumbent is the proposal (proposal_hash + sanitization.cleaned_code).
    Otherwise, the new incumbent is the same as this step's
    current_incumbent (next_incumbent_hash == current_incumbent_hash).
    """
    next_hash = rec.get("next_incumbent_hash")
    next_source = rec.get("next_incumbent_source")
    if next_hash and next_source:
        return {
            "code": next_source,
            "code_hash": next_hash,
            "algorithm": f"ch7_validation_resume_{next_hash}",
        }
    # Defensive fallback: use the current incumbent from the record.
    cur_hash = rec.get("current_incumbent_hash")
    cur_source = rec.get("current_incumbent_source")
    if cur_hash and cur_source:
        return {
            "code": cur_source,
            "code_hash": cur_hash,
            "algorithm": f"ch7_validation_resume_{cur_hash}",
        }
    # Last-ditch: h_eoh.
    return h_eoh
