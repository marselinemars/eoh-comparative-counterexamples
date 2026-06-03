"""thesis/code/chapter7/experiments/validation_batch.py

Resumable chapter-7 validation-batch driver. Runs all 14 cells ×
3 trajectories × 5 steps = 210 LLM calls per
``chapter7_design.md`` §4.2 / §8.2 / §18.6.

Resumability:
  * Per-step records written atomically to
    ``thesis/results/chapter7_validation_batch_gemini/``.
  * Filename:
    ``chapter7_validation_<cell_id>_traj<t>_step<s>.json``.
  * On startup, the driver scans the directory and computes
    completed-(cell, traj, step) tuples. Trajectory restart
    semantics: if step i is on disk, the next step's incumbent
    is read from step i's ``next_incumbent_*`` fields (not
    re-derived from h_eoh). The driver continues each
    trajectory at the lowest missing step in order.
  * Persistent 429 (credits depleted) raises
    ``PersistentCreditsExhausted``; driver exits with status 2.

Usage::

    python -m thesis.code.chapter7.experiments.validation_batch
    python -m thesis.code.chapter7.experiments.validation_batch --dry-run
    python -m thesis.code.chapter7.experiments.validation_batch --max-steps 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(REPO_ROOT / ".env")

from thesis.code.chapter7.batch_runner import (  # noqa: E402
    MAX_OUTPUT_TOKENS_DEFAULT,
    PROVIDER_DEFAULT,
    REASONING_EFFORT_DEFAULT,
    TEMPERATURE_DEFAULT,
    TIMEOUT_SECONDS_DEFAULT,
    PersistentCreditsExhausted,
)
from thesis.code.chapter7.validation_runner import (  # noqa: E402
    incumbent_for_next_step,
    is_step_complete,
    load_step_record,
    run_chapter7_validation_step,
    _load_reference_source,
    _train_select_lookup,
)
from thesis.code.incumbents import get_h_eoh  # noqa: E402
from thesis.code.score_cache import ScoreCache  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "thesis" / "results" / "chapter7_validation_batch_gemini"
LOG_PATH = OUTPUT_DIR / "chapter7_validation_batch_log.txt"
OVERVIEW_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "chapter7_validation_batch_overview.json"
)
N_TRAJECTORIES = 3
N_STEPS = 5
INTER_CALL_SLEEP_S = 3.0

CELLS: List[Dict[str, Any]] = [
    {"cell_id": "CH7-01", "strategy": "stratified_representative", "level": 1, "k": 1},
    {"cell_id": "CH7-02", "strategy": "stratified_representative", "level": 1, "k": 2},
    {"cell_id": "CH7-03", "strategy": "stratified_representative", "level": 1, "k": 4},
    {"cell_id": "CH7-04", "strategy": "stratified_representative", "level": 1, "k": 8},
    {"cell_id": "CH7-05", "strategy": "worst_only_at_k1", "level": 1, "k": 1},
    {"cell_id": "CH7-06", "strategy": "worst_plus_best", "level": 1, "k": 2},
    {"cell_id": "CH7-07", "strategy": "worst_plus_best", "level": 1, "k": 4},
    {"cell_id": "CH7-08", "strategy": "worst_plus_best", "level": 1, "k": 8},
    {"cell_id": "CH7-09", "strategy": "stratified_representative", "level": 2, "k": 1},
    {"cell_id": "CH7-10", "strategy": "stratified_representative", "level": 2, "k": 2},
    {"cell_id": "CH7-11", "strategy": "stratified_representative", "level": 2, "k": 4},
    {"cell_id": "CH7-12", "strategy": "worst_only_at_k1", "level": 2, "k": 1},
    {"cell_id": "CH7-13", "strategy": "worst_plus_best", "level": 2, "k": 2},
    {"cell_id": "CH7-14", "strategy": "worst_plus_best", "level": 2, "k": 4},
]


def _log(line: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(f"[{ts}] {line}\n")
    print(line, flush=True)


def _compute_remaining(
    h_eoh: Dict[str, Any], retry_api_errors: bool = False,
) -> List[Dict[str, Any]]:
    """Walk every cell × trajectory and identify the missing steps.
    For trajectories with partial progress, derive the resume-step
    incumbent from the latest completed step's record.

    With ``retry_api_errors=True``, records whose acceptance_reason
    is ``rejected_api_error`` (or have api_error set) are treated as
    incomplete and re-run. Because api_error records leave the
    incumbent unchanged (next_incumbent_hash == current_incumbent_hash),
    re-running them does not invalidate any later step that was
    based on the same incumbent.
    """
    remaining: List[Dict[str, Any]] = []
    for cell in CELLS:
        cell_id = cell["cell_id"]
        for traj_idx in range(N_TRAJECTORIES):
            current_incumbent = h_eoh
            for step_idx in range(N_STEPS):
                rec = load_step_record(OUTPUT_DIR, cell_id, traj_idx, step_idx)
                if is_step_complete(rec, retry_api_errors=retry_api_errors):
                    current_incumbent = incumbent_for_next_step(rec, h_eoh)
                    continue
                # First missing step in this trajectory.
                remaining.append({
                    "cell": cell,
                    "trajectory_index": traj_idx,
                    "step_index": step_idx,
                    "current_incumbent": current_incumbent,
                })
                # Mark the rest of this trajectory as remaining too —
                # but they'll be discovered at the next driver pass
                # after this step writes its record. Continue to the
                # next trajectory.
                break
    return remaining


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-steps", type=int, default=None,
                        help="Run at most N steps then exit (smoke).")
    parser.add_argument("--provider", default=PROVIDER_DEFAULT)
    parser.add_argument("--reasoning-effort", default=REASONING_EFFORT_DEFAULT)
    parser.add_argument("--max-output-tokens", type=int,
                        default=MAX_OUTPUT_TOKENS_DEFAULT)
    parser.add_argument("--temperature", type=float, default=TEMPERATURE_DEFAULT)
    parser.add_argument("--timeout-seconds", type=float,
                        default=TIMEOUT_SECONDS_DEFAULT)
    parser.add_argument(
        "--retry-api-errors", action="store_true",
        help=(
            "Treat trajectory steps with api_error or "
            "acceptance_reason='rejected_api_error' as incomplete so "
            "they get re-run. Safe because api_error records leave the "
            "incumbent unchanged, so re-running them does not "
            "invalidate any later step in the same trajectory."
        ),
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    h_eoh = get_h_eoh()
    if h_eoh["code_hash"] != "8ca83676ae76":
        raise RuntimeError(f"Unexpected h_eoh hash {h_eoh['code_hash']!r}")

    plan_size = len(CELLS) * N_TRAJECTORIES * N_STEPS
    # Count completed records on disk (across all trajectories).
    completed_count = 0
    for cell in CELLS:
        for traj_idx in range(N_TRAJECTORIES):
            for step_idx in range(N_STEPS):
                rec = load_step_record(
                    OUTPUT_DIR, cell["cell_id"], traj_idx, step_idx
                )
                if is_step_complete(rec, retry_api_errors=args.retry_api_errors):
                    completed_count += 1

    _log("=" * 72)
    _log(
        f"CH7 VALIDATION BATCH — provider={args.provider} "
        f"reasoning={args.reasoning_effort} max_tok={args.max_output_tokens}"
    )
    _log(
        f"plan: {plan_size} step-records  completed: {completed_count}  "
        f"remaining: {plan_size - completed_count}"
    )
    _log("=" * 72)

    if args.dry_run:
        # Show per-cell breakdown.
        print(f"{'cell':<8} {'strategy':<28} {'L':<3} {'k':<3} done/total per traj")
        for cell in CELLS:
            cid = cell["cell_id"]
            per_traj = []
            for traj_idx in range(N_TRAJECTORIES):
                done = sum(
                    1
                    for s in range(N_STEPS)
                    if is_step_complete(
                        load_step_record(OUTPUT_DIR, cid, traj_idx, s)
                    )
                )
                per_traj.append(f"{done}/{N_STEPS}")
            print(
                f"  {cid:<6} {cell['strategy']:<28} L{cell['level']:<2} "
                f"k={cell['k']:<2} {' '.join(per_traj)}"
            )
        return 0

    if completed_count >= plan_size:
        _log("all validation records complete — nothing to do.")
        return 0

    # Heavy setup.
    instance_lookup = _train_select_lookup()
    reference_source = _load_reference_source()
    score_cache = ScoreCache()

    started_at = datetime.now(timezone.utc).isoformat()
    n_run = 0
    n_accepted = 0
    n_fail_per_label: Dict[str, int] = {}
    last_call_end: Optional[float] = None
    exit_code = 0

    try:
        # Outer loop: keep recomputing remaining until plan complete or
        # we exhaust max-steps. Each pass does one trajectory step per
        # (cell × trajectory) at the leading missing step; subsequent
        # passes pick up the next step.
        while True:
            if args.max_steps is not None and n_run >= args.max_steps:
                _log(f"--max-steps={args.max_steps} reached; stopping.")
                break

            remaining = _compute_remaining(h_eoh, retry_api_errors=args.retry_api_errors)
            if not remaining:
                _log("no remaining steps; batch complete.")
                break

            for item in remaining:
                if args.max_steps is not None and n_run >= args.max_steps:
                    break
                if last_call_end is not None:
                    elapsed = time.perf_counter() - last_call_end
                    rem = INTER_CALL_SLEEP_S - elapsed
                    if rem > 0:
                        time.sleep(rem)

                cell = item["cell"]
                cell_id = cell["cell_id"]
                strategy = cell["strategy"]
                level = cell["level"]
                k = cell["k"]
                traj_idx = item["trajectory_index"]
                step_idx = item["step_index"]
                current_incumbent = item["current_incumbent"]

                try:
                    record = run_chapter7_validation_step(
                        cell_id=cell_id,
                        strategy=strategy,
                        level=level,
                        k=k,
                        trajectory_index=traj_idx,
                        step_index=step_idx,
                        current_incumbent=current_incumbent,
                        instance_lookup=instance_lookup,
                        reference_source=reference_source,
                        output_dir=OUTPUT_DIR,
                        score_cache=score_cache,
                        provider=args.provider,
                        reasoning_effort=args.reasoning_effort,
                        max_output_tokens=args.max_output_tokens,
                        temperature=args.temperature,
                        timeout_seconds=args.timeout_seconds,
                    )
                except PersistentCreditsExhausted as exc:
                    _log(
                        f"  {cell_id} traj={traj_idx} step={step_idx} "
                        f"PERSISTENT_CREDITS_EXHAUSTED — exiting status 2. "
                        f"Error: {exc}"
                    )
                    exit_code = 2
                    raise
                except KeyboardInterrupt:
                    _log("KeyboardInterrupt — partial batch persisted; re-run to resume.")
                    exit_code = 130
                    raise

                last_call_end = time.perf_counter()
                n_run += 1
                decision = record.get("acceptance_decision")
                reason = record.get("acceptance_reason")
                if decision == "accepted":
                    n_accepted += 1
                else:
                    n_fail_per_label[reason] = n_fail_per_label.get(reason, 0) + 1
                ds = record.get("delta_step_local")
                ds_str = f"{ds:+.2f}" if isinstance(ds, (int, float)) else "n/a"
                _log(
                    f"  {cell_id} traj={traj_idx} step={step_idx} "
                    f"{decision}/{reason} delta_step_local={ds_str}"
                )

            # After processing one step per trajectory, the loop will
            # recompute `remaining` and continue. This advances each
            # trajectory by one step per outer iteration, ensuring that
            # the trajectory's incumbent is updated correctly between
            # steps.

    except (PersistentCreditsExhausted, KeyboardInterrupt):
        pass
    finally:
        finished_at = datetime.now(timezone.utc).isoformat()
        completed_after = 0
        for cell in CELLS:
            for traj_idx in range(N_TRAJECTORIES):
                for step_idx in range(N_STEPS):
                    rec = load_step_record(
                        OUTPUT_DIR, cell["cell_id"], traj_idx, step_idx
                    )
                    if is_step_complete(rec, retry_api_errors=args.retry_api_errors):
                        completed_after += 1
        overview = {
            "started_at": started_at,
            "finished_at": finished_at,
            "settings": {
                "provider": args.provider,
                "reasoning_effort": args.reasoning_effort,
                "max_output_tokens": args.max_output_tokens,
                "temperature": args.temperature,
                "inter_call_sleep_s": INTER_CALL_SLEEP_S,
                "timeout_seconds": args.timeout_seconds,
            },
            "totals": {
                "plan_size": plan_size,
                "completed_at_start": completed_count,
                "completed_at_end": completed_after,
                "n_run_this_session": n_run,
                "n_accepted_this_session": n_accepted,
                "n_fail_per_label_this_session": n_fail_per_label,
                "exit_code": exit_code,
            },
            "output_dir": str(OUTPUT_DIR),
        }
        OVERVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
        OVERVIEW_PATH.write_text(
            json.dumps(overview, indent=2, sort_keys=True), encoding="utf-8"
        )
        _log(
            f"session done: ran {n_run} steps, {n_accepted} accepted, "
            f"fails={n_fail_per_label}; "
            f"completed-on-disk {completed_after}/{plan_size}; "
            f"exit_code={exit_code}"
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
