"""
thesis/code/experiments/chapter5_validation_batch.py

Chapter 5 validation batch — top-3 strategies x 3 trajectories x
5 steps = 45 LLM calls, per chapter5_design.md §6.2 with the
2026-04-23 revised acceptance criterion (argmax-distinct AND
non-regressing).

Top-3 strategies chosen from the primary-batch analysis
(chapter5_summary.json, sha256[:12] 8bdffb7172f5):
  - uniform_random            (best trimmed_mean, lowest cat%)
  - stratified_representative (highest positive_tail_mass)
  - worst_plus_best           (lowest catastrophic tail)

Trajectory step:
  1. Step 1: use committed pool. Later steps: rebuild pool
     against current incumbent via
     validation.rebuild_pool_against_incumbent.
  2. Run the strategy to draw a CounterexampleSet.
  3. Call the LLM, sanitize, score on train_step / train_gate.
  4. Compute current incumbent's per-instance bins on train_step.
  5. Apply the revised acceptance rule
     (validation.should_accept_proposal).
  6. If accepted, promote proposal to current incumbent.

Per-step JSON + per-trajectory consolidated JSON. Resume-friendly
via filename-based skip.

Usage:
    python thesis/code/experiments/chapter5_validation_batch.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

TOP_3_STRATEGIES: List[str] = [
    "uniform_random",
    "stratified_representative",
    "worst_plus_best",
]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_env_file(Path(__file__).resolve().parents[3] / ".env")

from thesis.code.chapter5.batch_runner import (  # noqa: E402
    call_with_transient_retry,
)
from thesis.code.chapter5.runner import run_single_proposal  # noqa: E402
from thesis.code.chapter5.validation import (  # noqa: E402
    compute_per_instance_bins_for_heuristic,
    rebuild_pool_against_incumbent,
    should_accept_proposal,
)
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import get_h_eoh  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)
OUTPUT_DIR = (
    REPO_ROOT / "thesis" / "results" / "chapter5_validation_batch_gemini"
)
PROGRESS_PATH = OUTPUT_DIR / "progress.json"

PROVIDER = "gemini"
MODEL = "gemini-2.5-pro"
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 32768
TEMPERATURE = 1.0
INTER_CALL_SLEEP_SECONDS = 3.0

N_TRAJECTORIES = 3
N_STEPS = 5

CHAPTER5_REFERENCE_HASH = "62a2846c597e"

# Stopping rules (per task spec)
LATENCY_ABORT_SECONDS = 240.0
COST_ABORT_USD = 0.15
MAX_CONSECUTIVE_SANITIZE_FAILURES = 3

PRICE_INPUT_PER_M = 1.25
PRICE_OUTPUT_PER_M = 10.0


def _cost(usage: Dict[str, Any]) -> float:
    p = usage.get("prompt_tokens") or 0
    c = usage.get("completion_tokens") or 0
    total = usage.get("total_tokens") or (p + c)
    rt = max(0, total - p - c)
    return (
        p * PRICE_INPUT_PER_M / 1_000_000
        + (c + rt) * PRICE_OUTPUT_PER_M / 1_000_000
    )


def _update_progress(
    started_at: str,
    steps_completed: int,
    total_steps: int,
    last_record_brief: Optional[Dict[str, Any]] = None,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(
        json.dumps(
            {
                "started_at": started_at,
                "last_updated_at": datetime.now(timezone.utc).isoformat(),
                "steps_completed": steps_completed,
                "total_steps": total_steps,
                "top_3_strategies": TOP_3_STRATEGIES,
                "last_record_brief": last_record_brief,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _step_filename(
    strategy_name: str, trajectory_index: int, step_index: int
) -> str:
    return (
        f"{strategy_name}_traj{trajectory_index}_step{step_index}.json"
    )


def _run_one_step(
    strategy_name: str,
    trajectory_index: int,
    step_index: int,
    pool: CounterexampleSet,
    current_incumbent: Dict[str, Any],
) -> Dict[str, Any]:
    """Run a single trajectory step.

    The per-call JSON emitted by run_single_proposal lands in
    OUTPUT_DIR as `{strategy}_{set}_{seed}.json` where set=100+traj
    and seed=step, matching the earlier skeleton's naming so the
    provenance file doesn't collide with the primary batch. The
    trajectory-consolidated record is written separately.
    """
    # run_single_proposal picks its own set/seed indices for seed
    # derivation; we encode trajectory coordinates into them so the
    # seed derivation is reproducible per (strategy, trajectory,
    # step).
    fake_set_index = 100 + trajectory_index
    fake_seed_index = step_index

    record = call_with_transient_retry(
        run_single_proposal,
        strategy_name=strategy_name,
        set_index=fake_set_index,
        seed_index=fake_seed_index,
        pool=pool,
        incumbent_heuristic=current_incumbent,
        output_dir=OUTPUT_DIR,
        provider=PROVIDER,
        reasoning_effort=REASONING_EFFORT,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    scoring = record.get("scoring") or {}
    sanit = record.get("sanitization") or {}

    accepted = False
    reason = "rejected_sanitize_failed"
    incumbent_bins_step: List[int] = []
    proposal_bins_step: List[int] = scoring.get(
        "per_instance_bins_proposal_train_step"
    ) or []

    if sanit.get("status") == "ok" and proposal_bins_step:
        incumbent_bins_step = (
            compute_per_instance_bins_for_heuristic(
                current_incumbent["code"],
                current_incumbent["code_hash"],
                "train_step",
            )
        )
        accepted, reason = should_accept_proposal(
            proposal_bins_step, incumbent_bins_step
        )

    step_record = {
        "strategy_name": strategy_name,
        "trajectory_index": trajectory_index,
        "step_index": step_index,
        "set_index_in_provenance": fake_set_index,
        "seed_index_in_provenance": fake_seed_index,
        "current_incumbent_hash": current_incumbent["code_hash"],
        "proposal_hash": record.get("proposal_hash"),
        "sanitization_status": sanit.get("status"),
        "delta_step_local": scoring.get("delta_step"),
        "delta_gate_local": scoring.get("delta_gate"),
        "incumbent_per_instance_bins_train_step": incumbent_bins_step,
        "proposal_per_instance_bins_train_step": proposal_bins_step,
        "accepted": accepted,
        "acceptance_reason": reason,
        "timestamps": record.get("timestamps", {}),
    }
    # Write the consolidated trajectory-step record.
    out_path = OUTPUT_DIR / _step_filename(
        strategy_name, trajectory_index, step_index
    )
    out_path.write_text(
        json.dumps(step_record, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    # Attach cost/latency for stopping-rule inspection.
    md = record["llm_metadata"]["raw_response_metadata"]
    usage = md.get("usage") or {}
    step_record["_cost_usd_estimate"] = _cost(usage)
    ts = record.get("timestamps") or {}
    if ts.get("started_at") and ts.get("finished_at"):
        step_record["_latency_seconds"] = (
            datetime.fromisoformat(ts["finished_at"])
            - datetime.fromisoformat(ts["started_at"])
        ).total_seconds()
    else:
        step_record["_latency_seconds"] = 0.0
    return step_record


def _run_one_trajectory(
    strategy_name: str,
    trajectory_index: int,
    started_at: str,
    steps_so_far: List[int],
    total_steps: int,
) -> Dict[str, Any]:
    """Run N_STEPS steps of one trajectory with the revised
    acceptance rule. Returns a trajectory summary dict.

    Raises a StopIteration-style RuntimeError if a stopping rule
    trips; caller catches and persists partial state.
    """
    current_incumbent = get_h_eoh()
    steps: List[Dict[str, Any]] = []
    consecutive_failures = 0

    for step_index in range(1, N_STEPS + 1):
        # Skip if the step's JSON is already on disk (resume).
        fn = _step_filename(strategy_name, trajectory_index, step_index)
        if (OUTPUT_DIR / fn).exists():
            prior = json.loads((OUTPUT_DIR / fn).read_text(encoding="utf-8"))
            steps.append(prior)
            # Reconstruct current_incumbent from the prior state.
            if prior.get("accepted") and prior.get("sanitization_status") == "ok":
                # Load the proposal code from the per-call JSON
                # in the primary-batch-style filename.
                call_json = OUTPUT_DIR / (
                    f"{strategy_name}_{prior['set_index_in_provenance']}"
                    f"_{prior['seed_index_in_provenance']}.json"
                )
                if call_json.exists():
                    call_record = json.loads(
                        call_json.read_text(encoding="utf-8")
                    )
                    current_incumbent = {
                        "code": call_record["sanitization"][
                            "cleaned_code"
                        ],
                        "code_hash": call_record["proposal_hash"],
                        "algorithm": (
                            f"proposal_{strategy_name}_"
                            f"traj{trajectory_index}_step{step_index}"
                        ),
                    }
            continue

        # Inter-call sleep before actual calls.
        if steps_so_far and steps:
            time.sleep(INTER_CALL_SLEEP_SECONDS)

        # Pool: step 1 uses the committed pool; later steps rebuild.
        if step_index == 1:
            pool = CounterexampleSet.from_json(
                POOL_PATH.read_text(encoding="utf-8")
            )
        else:
            pool = rebuild_pool_against_incumbent(
                incumbent=current_incumbent,
                reference_hash=CHAPTER5_REFERENCE_HASH,
                split_name="train_select",
            )

        print(
            f"\n[{strategy_name} traj={trajectory_index} "
            f"step={step_index}] incumbent={current_incumbent['code_hash']}"
        )
        step_record = _run_one_step(
            strategy_name=strategy_name,
            trajectory_index=trajectory_index,
            step_index=step_index,
            pool=pool,
            current_incumbent=current_incumbent,
        )
        steps.append(step_record)
        steps_so_far.append(1)

        brief = {
            "strategy": strategy_name,
            "trajectory": trajectory_index,
            "step": step_index,
            "sanitize": step_record["sanitization_status"],
            "delta_step_local": step_record["delta_step_local"],
            "accepted": step_record["accepted"],
            "reason": step_record["acceptance_reason"],
            "cost": step_record["_cost_usd_estimate"],
            "latency": step_record["_latency_seconds"],
        }
        print(
            f"  sanitize={step_record['sanitization_status']} "
            f"d_step_local={step_record['delta_step_local']!s} "
            f"accepted={step_record['accepted']} "
            f"reason={step_record['acceptance_reason']} "
            f"cost=${step_record['_cost_usd_estimate']:.4f} "
            f"lat={step_record['_latency_seconds']:.1f}s"
        )
        _update_progress(
            started_at, len(steps_so_far), total_steps, brief
        )

        # Stopping rules
        if step_record["_latency_seconds"] > LATENCY_ABORT_SECONDS:
            raise RuntimeError(
                f"latency {step_record['_latency_seconds']:.1f}s "
                f"> {LATENCY_ABORT_SECONDS}s"
            )
        if step_record["_cost_usd_estimate"] > COST_ABORT_USD:
            raise RuntimeError(
                f"call cost ${step_record['_cost_usd_estimate']:.4f} "
                f"> ${COST_ABORT_USD}"
            )
        if step_record["sanitization_status"] != "ok":
            consecutive_failures += 1
        else:
            consecutive_failures = 0
        if consecutive_failures >= MAX_CONSECUTIVE_SANITIZE_FAILURES:
            raise RuntimeError(
                f"{consecutive_failures} consecutive sanitize failures"
            )

        # Promote proposal if accepted.
        if step_record["accepted"]:
            sc = step_record
            call_json_path = OUTPUT_DIR / (
                f"{strategy_name}_{sc['set_index_in_provenance']}"
                f"_{sc['seed_index_in_provenance']}.json"
            )
            call_record = json.loads(
                call_json_path.read_text(encoding="utf-8")
            )
            current_incumbent = {
                "code": call_record["sanitization"]["cleaned_code"],
                "code_hash": call_record["proposal_hash"],
                "algorithm": (
                    f"proposal_{strategy_name}_traj{trajectory_index}"
                    f"_step{step_index}"
                ),
            }

    reasons: Dict[str, int] = {}
    for s in steps:
        k = s.get("acceptance_reason") or "unknown"
        reasons[k] = reasons.get(k, 0) + 1

    # Cumulative Δ_step: final incumbent vs h_eoh, on train_step.
    h_eoh = get_h_eoh()
    h_bins = compute_per_instance_bins_for_heuristic(
        h_eoh["code"], h_eoh["code_hash"], "train_step"
    )
    final_bins = compute_per_instance_bins_for_heuristic(
        current_incumbent["code"], current_incumbent["code_hash"],
        "train_step",
    )
    n = len(h_bins)
    d_cumulative = (
        sum(h_bins) / n - sum(final_bins) / n
        if n else 0.0
    )

    return {
        "strategy_name": strategy_name,
        "trajectory_index": trajectory_index,
        "steps": steps,
        "acceptance_reason_counts": reasons,
        "final_incumbent_hash": current_incumbent["code_hash"],
        "delta_step_cumulative": d_cumulative,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    total_steps = len(TOP_3_STRATEGIES) * N_TRAJECTORIES * N_STEPS
    _update_progress(started_at, 0, total_steps, None)

    print("=" * 72)
    print(
        "CHAPTER 5 VALIDATION BATCH — Gemini 2.5 Pro / medium / 32k"
    )
    print(
        f"top-3: {TOP_3_STRATEGIES}  "
        f"trajectories={N_TRAJECTORIES}  steps={N_STEPS}  "
        f"total_calls={total_steps}"
    )
    print("acceptance: argmax-distinct AND non-regressing "
          "(decisions log 2026-04-23)")
    print(f"output: {OUTPUT_DIR}")
    print("=" * 72)

    all_trajectories: List[Dict[str, Any]] = []
    stopped = False
    stop_reason: Optional[str] = None
    steps_so_far: List[int] = []

    try:
        for strategy_name in TOP_3_STRATEGIES:
            for traj_idx in range(N_TRAJECTORIES):
                print(
                    f"\n=== {strategy_name} — trajectory "
                    f"{traj_idx} ==="
                )
                traj = _run_one_trajectory(
                    strategy_name=strategy_name,
                    trajectory_index=traj_idx,
                    started_at=started_at,
                    steps_so_far=steps_so_far,
                    total_steps=total_steps,
                )
                all_trajectories.append(traj)
                (OUTPUT_DIR / (
                    f"{strategy_name}_traj{traj_idx}"
                    "_trajectory_summary.json"
                )).write_text(
                    json.dumps(traj, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
    except KeyboardInterrupt:
        stopped = True
        stop_reason = "KeyboardInterrupt"
    except RuntimeError as exc:
        stopped = True
        stop_reason = str(exc)

    finished_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "started_at": started_at,
        "finished_at": finished_at,
        "stopped_early": stopped,
        "stop_reason": stop_reason,
        "settings": {
            "provider": PROVIDER,
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "temperature": TEMPERATURE,
            "inter_call_sleep_seconds": INTER_CALL_SLEEP_SECONDS,
            "top_3_strategies": TOP_3_STRATEGIES,
            "n_trajectories": N_TRAJECTORIES,
            "n_steps": N_STEPS,
        },
        "trajectories": all_trajectories,
    }
    (OUTPUT_DIR / "validation_batch_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if stopped:
        print(f"\n[STOPPED] {stop_reason}")
        return 1
    print("\n[DONE] validation batch complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
