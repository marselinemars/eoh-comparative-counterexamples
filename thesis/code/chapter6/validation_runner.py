"""
thesis/code/chapter6/validation_runner.py

Chapter 6 validation-batch trajectory orchestration.

Per chapter6_design.md §8.2: each cell runs ``n_trajectories``
trajectories of ``n_steps`` steps each. At every step:

  1. Identify the current trajectory incumbent (h_eoh at step 0;
     the prior step's accepted proposal otherwise).
  2. Rebuild the counterexample pool against the current incumbent
     via the ch5 helper ``rebuild_pool_against_incumbent``.
  3. Apply the cell's selection strategy with the trajectory-
     namespace seed (``trajectory_set_seed_ch6``) to draw a
     CounterexampleSet of size 4.
  4. Render the L1 / L2 prompt. At L2 the trace is recomputed
     against the *current* incumbent — this is the §8.2 trace-
     recompute extension. The recompute happens automatically
     because :func:`_run_chapter6_single_proposal` extracts the
     trace inline from its ``incumbent_heuristic`` argument; we
     pass the per-step current incumbent.
  5. Call the LLM, sanitize, score on train_step / train_gate.
  6. Compute the current incumbent's per-instance bins on
     train_step (cached) and apply the ch5 acceptance rule
     (``should_accept_proposal``) — four-label classification
     identical to chapter 5 §6.2.
  7. Promote the proposal to current incumbent iff accepted.
  8. Write a per-step JSON record with the trajectory-step
     schema (chapter, phase, cell_id, level, master_seed,
     trajectory_index, step_index, trajectory_set_seed,
     trajectory_llm_seed, current_incumbent_hash,
     current_incumbent_source, pool_rebuild_pool_hash, prompt,
     response, sanitization, scoring, delta_step_local,
     argmax_distinct, acceptance_decision, acceptance_reason,
     next_incumbent_hash).

Architectural note. This module wraps existing ch5 + ch6
infrastructure rather than reimplementing it:

  - Acceptance rule: ``chapter5.validation.should_accept_proposal``.
  - Pool rebuild:    ``chapter5.validation.rebuild_pool_against_incumbent``.
  - Incumbent scoring: ``chapter5.validation.compute_per_instance_bins_for_heuristic``.
  - LLM call / sanitize / score / L2 trace recompute:
    ``chapter6.batch_runner._run_chapter6_single_proposal``
    (with seed-override and write-record params introduced for
    this task; defaults preserve the primary-batch behavior).
"""
from __future__ import annotations

import hashlib
import json
import time
import types
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from thesis.code.chapter5.llm_client import call_llm as _ch5_call_llm
from thesis.code.chapter5.validation import (
    compute_per_instance_bins_for_heuristic,
    rebuild_pool_against_incumbent,
    should_accept_proposal,
)
from thesis.code.chapter6.batch_runner import (
    MASTER_SEED_CH6,
    _run_chapter6_single_proposal,
    trajectory_llm_seed_ch6,
    trajectory_set_seed_ch6,
)
from thesis.code.counterexample import CounterexampleSet
from thesis.code.score_cache import ScoreCache

CHAPTER6_REFERENCE_HASH = "62a2846c597e"


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StepRecord:
    """In-memory mirror of the per-step JSON written to disk."""

    cell_id: str
    trajectory_index: int
    step_index: int
    current_incumbent_hash: str
    proposal_hash: Optional[str]
    sanitization_status: Optional[str]
    delta_step_local: Optional[float]
    argmax_distinct: Optional[bool]
    acceptance_decision: str  # "accepted" | "rejected" | "skipped_sanitize_failed"
    acceptance_reason: str
    next_incumbent_hash: str
    record_path: Path


@dataclass
class TrajectoryRecord:
    cell_id: str
    trajectory_index: int
    steps: List[StepRecord]
    delta_step_cumulative_per_step: List[Optional[float]]
    final_incumbent_hash: str


@dataclass
class CellValidationResult:
    cell_id: str
    n_trajectories: int
    n_steps_per_trajectory: int
    trajectories: List[TrajectoryRecord]
    acceptance_reason_counts: Dict[str, int] = field(default_factory=dict)
    step_record_paths: List[Path] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REJECT_SANITIZE_FAILED = "rejected_sanitize_failed"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pool_hash(pool: CounterexampleSet) -> str:
    """sha256[:12] over the pool's canonical JSON."""
    return hashlib.sha256(pool.to_json().encode("utf-8")).hexdigest()[:12]


def _step_filename(cell_id: str, trajectory_index: int, step_index: int) -> str:
    return f"{cell_id}_traj{trajectory_index}_step{step_index}.json"


def _initial_pool(starting_incumbent: Dict[str, Any],
                  cache: Optional[ScoreCache] = None) -> CounterexampleSet:
    """Pool at trajectory step 0, against the starting incumbent
    (h_eoh on the first step of every trajectory)."""
    return rebuild_pool_against_incumbent(
        incumbent=starting_incumbent,
        reference_hash=CHAPTER6_REFERENCE_HASH,
        split_name="train_select",
        cache=cache,
    )


def _make_proposal_incumbent(
    proposal_hash: str,
    proposal_source: str,
) -> Dict[str, Any]:
    return {
        "code": proposal_source,
        "code_hash": proposal_hash,
        "algorithm": f"ch6_validation_proposal_{proposal_hash}",
    }


# ---------------------------------------------------------------------------
# Per-step orchestration
# ---------------------------------------------------------------------------


def run_validation_step(
    *,
    strategy_name: str,
    level: int,
    trajectory_index: int,
    step_index: int,
    current_incumbent: Dict[str, Any],
    output_dir: Path,
    provider: str = "gemini",
    reasoning_effort: Optional[str] = "medium",
    max_output_tokens: Optional[int] = 32768,
    timeout_seconds: float = 300.0,
    pool_cache: Optional[ScoreCache] = None,
    call_llm_fn: Callable[..., Dict[str, Any]] = _ch5_call_llm,
    _run_proposal_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> StepRecord:
    """Run one trajectory step and write its per-step record to disk.

    The step is structured exactly as §8.2 specifies. Returns a
    :class:`StepRecord` whose ``next_incumbent_hash`` reflects the
    acceptance decision; the caller (typically
    :func:`run_chapter6_validation_cell`) is responsible for
    propagating the proposal as the next step's incumbent when
    accepted.
    """
    if level not in (1, 2):
        raise ValueError(f"level must be 1 or 2; got {level!r}")

    cell_id = f"{strategy_name}@L{level}"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = _utcnow_iso()

    # ----- pool rebuild -----
    pool = rebuild_pool_against_incumbent(
        incumbent=current_incumbent,
        reference_hash=CHAPTER6_REFERENCE_HASH,
        split_name="train_select",
        cache=pool_cache,
    )
    pool_rebuild_pool_hash = _pool_hash(pool)

    # ----- seeds (ch6:traj namespace) -----
    set_seed = trajectory_set_seed_ch6(
        strategy_name, trajectory_index, step_index, level,
    )
    llm_seed = trajectory_llm_seed_ch6(
        strategy_name, trajectory_index, step_index, level,
    )

    # ----- LLM call + sanitize + score (delegates to primary-batch worker) -----
    proposal_runner = _run_proposal_fn or _run_chapter6_single_proposal
    record = proposal_runner(
        strategy_name=strategy_name,
        level=level,
        # set_index / seed_index are bookkeeping only; the actual
        # seeds are overridden below.
        set_index=trajectory_index,
        seed_index=step_index,
        pool=pool,
        incumbent_heuristic=current_incumbent,
        # reference source: need to read from the pool's reference_hash.
        reference_source=_load_reference_source(),
        output_dir=output_dir,
        k=4,
        provider=provider,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
        timeout_seconds=timeout_seconds,
        call_llm_fn=call_llm_fn,
        set_seed_override=set_seed,
        llm_seed_override=llm_seed,
        write_record=False,  # we write our own trajectory-step record below
    )

    # ----- acceptance rule -----
    sanitization = record.get("sanitization") or {}
    scoring = record.get("scoring") or {}
    proposal_per_instance_step = scoring.get(
        "per_instance_bins_proposal_train_step"
    )

    delta_step_local: Optional[float] = None
    argmax_distinct: Optional[bool] = None
    acceptance_decision = "rejected"
    acceptance_reason: str = REJECT_SANITIZE_FAILED
    next_incumbent_hash = current_incumbent["code_hash"]

    if (
        sanitization.get("status") == "ok"
        and proposal_per_instance_step is not None
    ):
        incumbent_per_instance_step = compute_per_instance_bins_for_heuristic(
            current_incumbent["code"],
            current_incumbent["code_hash"],
            "train_step",
            cache=pool_cache,
        )
        accepted, reason = should_accept_proposal(
            proposal_per_instance_step,
            incumbent_per_instance_step,
        )
        n = len(incumbent_per_instance_step)
        delta_step_local = (
            sum(incumbent_per_instance_step) / n
            - sum(proposal_per_instance_step) / n
        )
        from thesis.code.chapter5.analysis import is_argmax_equivalent_to_h_eoh
        argmax_distinct = not is_argmax_equivalent_to_h_eoh(
            proposal_per_instance_step, incumbent_per_instance_step,
        )
        acceptance_decision = "accepted" if accepted else "rejected"
        acceptance_reason = reason
        if accepted:
            next_incumbent_hash = record["proposal_hash"]

    finished_at = _utcnow_iso()

    # ----- write trajectory-step record -----
    trajectory_step_record: Dict[str, Any] = {
        "chapter": "chapter6",
        "phase": "validation",
        "cell_id": cell_id,
        "level": level,
        "master_seed": MASTER_SEED_CH6,
        "trajectory_index": trajectory_index,
        "step_index": step_index,
        "trajectory_set_seed": set_seed,
        "trajectory_llm_seed": llm_seed,
        "current_incumbent_hash": current_incumbent["code_hash"],
        "current_incumbent_source": current_incumbent["code"],
        "pool_rebuild_pool_hash": pool_rebuild_pool_hash,
        "counterexample_set": record.get("counterexample_set"),
        "k": record.get("k"),
        "prompt": record.get("prompt"),
        "response": record.get("raw_response"),
        "proposal_hash": record.get("proposal_hash"),
        "sanitization": record.get("sanitization"),
        "scoring": record.get("scoring"),
        "llm_metadata": record.get("llm_metadata"),
        "trace_summary": record.get("trace_summary"),
        "delta_step_local": delta_step_local,
        "argmax_distinct": argmax_distinct,
        "acceptance_decision": acceptance_decision,
        "acceptance_reason": acceptance_reason,
        "next_incumbent_hash": next_incumbent_hash,
        "timestamps": {"started_at": started_at, "finished_at": finished_at},
    }
    out_path = output_dir / _step_filename(cell_id, trajectory_index, step_index)
    out_path.write_text(
        json.dumps(trajectory_step_record, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return StepRecord(
        cell_id=cell_id,
        trajectory_index=trajectory_index,
        step_index=step_index,
        current_incumbent_hash=current_incumbent["code_hash"],
        proposal_hash=record.get("proposal_hash"),
        sanitization_status=sanitization.get("status"),
        delta_step_local=delta_step_local,
        argmax_distinct=argmax_distinct,
        acceptance_decision=acceptance_decision,
        acceptance_reason=acceptance_reason,
        next_incumbent_hash=next_incumbent_hash,
        record_path=out_path,
    )


def _load_reference_source() -> str:
    """Load the chapter-6 reference heuristic's source from the
    EoH final population (cached after first call)."""
    global _CACHED_REFERENCE_SOURCE
    try:
        return _CACHED_REFERENCE_SOURCE
    except NameError:
        pass
    from thesis.code.incumbents import load_final_population
    for member in load_final_population():
        if member["code_hash"] == CHAPTER6_REFERENCE_HASH:
            _CACHED_REFERENCE_SOURCE = member["code"]  # type: ignore[name-defined]
            return _CACHED_REFERENCE_SOURCE
    raise RuntimeError(
        f"reference {CHAPTER6_REFERENCE_HASH!r} not found in EoH "
        "final population"
    )


# ---------------------------------------------------------------------------
# Per-cell orchestration
# ---------------------------------------------------------------------------


def run_chapter6_validation_cell(
    *,
    strategy_name: str,
    level: int,
    starting_incumbent: Dict[str, Any],
    n_trajectories: int,
    n_steps: int,
    output_dir: Path,
    provider: str = "gemini",
    reasoning_effort: Optional[str] = "medium",
    max_output_tokens: Optional[int] = 32768,
    timeout_seconds: float = 300.0,
    inter_call_sleep_seconds: float = 3.0,
    smoke_mode: bool = False,
    smoke_n_trajectories: int = 1,
    smoke_n_steps: int = 1,
    call_llm_fn: Callable[..., Dict[str, Any]] = _ch5_call_llm,
    _run_step_fn: Optional[Callable[..., StepRecord]] = None,
) -> CellValidationResult:
    """Run all trajectories for one (strategy, level) cell.

    ``smoke_mode=True`` truncates the cell to
    ``smoke_n_trajectories`` × ``smoke_n_steps`` (1×1 by default)
    so the validation plumbing can be exercised end-to-end with a
    single LLM call before scaling.
    """
    if smoke_mode:
        n_trajectories = smoke_n_trajectories
        n_steps = smoke_n_steps

    cell_id = f"{strategy_name}@L{level}"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    step_runner = _run_step_fn or run_validation_step
    pool_cache = ScoreCache()

    trajectories: List[TrajectoryRecord] = []
    acceptance_reason_counts: Dict[str, int] = {}
    step_record_paths: List[Path] = []
    last_call_end: Optional[float] = None
    h_eoh_per_instance_train_step: Optional[List[int]] = None

    for traj_idx in range(n_trajectories):
        steps: List[StepRecord] = []
        delta_step_cumulative_per_step: List[Optional[float]] = []
        current_incumbent = starting_incumbent

        for step_idx in range(n_steps):
            if last_call_end is not None and inter_call_sleep_seconds > 0:
                elapsed = time.perf_counter() - last_call_end
                rem = inter_call_sleep_seconds - elapsed
                if rem > 0:
                    time.sleep(rem)

            step = step_runner(
                strategy_name=strategy_name,
                level=level,
                trajectory_index=traj_idx,
                step_index=step_idx,
                current_incumbent=current_incumbent,
                output_dir=output_dir,
                provider=provider,
                reasoning_effort=reasoning_effort,
                max_output_tokens=max_output_tokens,
                timeout_seconds=timeout_seconds,
                pool_cache=pool_cache,
                call_llm_fn=call_llm_fn,
            )
            last_call_end = time.perf_counter()
            steps.append(step)
            step_record_paths.append(step.record_path)
            acceptance_reason_counts[step.acceptance_reason] = (
                acceptance_reason_counts.get(step.acceptance_reason, 0) + 1
            )

            # Cumulative Δ_step at this step: h_eoh mean − current
            # incumbent (post-acceptance) mean on train_step.
            if h_eoh_per_instance_train_step is None:
                h_eoh_per_instance_train_step = (
                    compute_per_instance_bins_for_heuristic(
                        starting_incumbent["code"],
                        starting_incumbent["code_hash"],
                        "train_step",
                        cache=pool_cache,
                    )
                )
            n = len(h_eoh_per_instance_train_step)
            h_mean = sum(h_eoh_per_instance_train_step) / n

            if step.acceptance_decision == "accepted":
                # Promote proposal to current incumbent.
                # Need to load the proposal source from the per-step record
                # since StepRecord doesn't carry source.
                step_record = json.loads(step.record_path.read_text(encoding="utf-8"))
                proposal_source = (step_record.get("sanitization") or {}).get(
                    "cleaned_code"
                )
                if proposal_source is None:
                    raise RuntimeError(
                        f"step {cell_id}/{traj_idx}/{step_idx}: accepted "
                        "but sanitization.cleaned_code missing"
                    )
                current_incumbent = _make_proposal_incumbent(
                    step.next_incumbent_hash, proposal_source,
                )

            current_per_instance = compute_per_instance_bins_for_heuristic(
                current_incumbent["code"],
                current_incumbent["code_hash"],
                "train_step",
                cache=pool_cache,
            )
            current_mean = sum(current_per_instance) / n
            delta_step_cumulative_per_step.append(h_mean - current_mean)

        trajectories.append(
            TrajectoryRecord(
                cell_id=cell_id,
                trajectory_index=traj_idx,
                steps=steps,
                delta_step_cumulative_per_step=delta_step_cumulative_per_step,
                final_incumbent_hash=current_incumbent["code_hash"],
            )
        )

    return CellValidationResult(
        cell_id=cell_id,
        n_trajectories=n_trajectories,
        n_steps_per_trajectory=n_steps,
        trajectories=trajectories,
        acceptance_reason_counts=acceptance_reason_counts,
        step_record_paths=step_record_paths,
    )
