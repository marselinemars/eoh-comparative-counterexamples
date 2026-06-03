"""
thesis/code/experiments/chapter4_extra_trajectories.py

W-E5 driver. Extends four key validation cells from n=3 to n=6
trajectories by running three additional trajectories on each at
fresh trajectory_indices {3, 4, 5}. 4 cells × 3 trajectories × 5
steps = 60 LLM calls. Governed by
thesis/writing/chapter4_extra_trajectories_design.md.

Cells:
  - stratified_representative @ L1 @ k=4  (chapter 5; +14.20 cell)
  - worst_plus_best @ L1 @ k=4           (chapter 5)
  - stratified_representative @ L2 @ k=1  (chapter 7; CH7-09)
  - worst_only_at_k1 @ L2 @ k=1           (chapter 7; CH7-12)

The two chapter-5 cells use chapter-5's trajectory protocol
(chapter5.validation.should_accept_proposal acceptance rule, ch5
prompt builder, ch5 reference). The two chapter-7 cells use
chapter-7's run_chapter7_validation_step (ch7 prompt builder,
trace extraction at L2). Both protocols are reused unchanged from
their respective modules — this is a configuration shim, not a
reimplementation.

Output dirs (gitignored):
  thesis/results/chapter5_validation_batch_gemini/   (L1 cells)
  thesis/results/chapter7_validation_batch_gemini/   (L2 cells)
Filenames for the new trajectories don't collide with the
existing n=3 (trajectory_index ∈ {3, 4, 5} vs {0, 1, 2}).

Seed-namespace note. Design doc §4.2 names `ch4extra:` as the
namespace for these trajectories. The actual seeds are derived
under chapter-5's `ch5:traj:` and chapter-7's `ch7:traj:`
namespaces with fresh trajectory_index coordinates {3, 4, 5}. The
extension is statistically homogeneous with the original n=3
(same code path, same protocol, fresh-but-deterministic seeds).
The `ch4extra:` name is recorded in the launch artifact's
metadata as the conceptual label for this extension family.

Resumable: each step's per-call JSON is checked before launching;
existing records are skipped and their incumbent state is
recovered to seed the next step.

Transport: PROVIDER = "vertex" per the 2026-05-05 decisions-log
entry, matching commits 02c3149's smoke success.

Usage:
    python -m thesis.code.experiments.chapter4_extra_trajectories
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


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


REPO_ROOT = Path(__file__).resolve().parents[3]
_load_env_file(REPO_ROOT / ".env")

from thesis.code.chapter5.batch_runner import (  # noqa: E402
    call_with_transient_retry,
)
from thesis.code.chapter5.runner import run_single_proposal  # noqa: E402
from thesis.code.chapter5.validation import (  # noqa: E402
    compute_per_instance_bins_for_heuristic,
    rebuild_pool_against_incumbent,
    should_accept_proposal,
)
from thesis.code.chapter7.validation_runner import (  # noqa: E402
    _load_reference_source,
    _train_select_lookup,
    incumbent_for_next_step,
    is_step_complete,
    load_step_record,
    run_chapter7_validation_step,
)
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import get_h_eoh  # noqa: E402
from thesis.code.score_cache import ScoreCache  # noqa: E402

POOL_PATH = REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
CH5_VAL_DIR = REPO_ROOT / "thesis" / "results" / "chapter5_validation_batch_gemini"
CH7_VAL_DIR = REPO_ROOT / "thesis" / "results" / "chapter7_validation_batch_gemini"

PROVIDER = "vertex"
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 32768
TEMPERATURE = 1.0
INTER_CALL_SLEEP_SECONDS = 3.0

CHAPTER5_REFERENCE_HASH = "62a2846c597e"
NEW_TRAJECTORY_INDICES = [3, 4, 5]
N_STEPS = 5
SEED_NAMESPACE_LABEL = "ch4extra"  # conceptual; see module docstring

CELLS: List[Dict[str, Any]] = [
    {
        "label": "stratified_representative_L1_k4",
        "origin": "ch5",
        "strategy": "stratified_representative",
        "level": 1,
        "k": 4,
        "output_dir": CH5_VAL_DIR,
    },
    {
        "label": "worst_plus_best_L1_k4",
        "origin": "ch5",
        "strategy": "worst_plus_best",
        "level": 1,
        "k": 4,
        "output_dir": CH5_VAL_DIR,
    },
    {
        "label": "stratified_representative_L2_k1",
        "origin": "ch7",
        "cell_id": "CH7-09",
        "strategy": "stratified_representative",
        "level": 2,
        "k": 1,
        "output_dir": CH7_VAL_DIR,
    },
    {
        "label": "worst_only_at_k1_L2_k1",
        "origin": "ch7",
        "cell_id": "CH7-12",
        "strategy": "worst_only_at_k1",
        "level": 2,
        "k": 1,
        "output_dir": CH7_VAL_DIR,
    },
]


# ---------------------------------------------------------------------------
# Chapter-5-style trajectory step (L1 cells)
# ---------------------------------------------------------------------------


def _ch5_step_filename(strategy: str, traj_idx: int, step_idx: int) -> str:
    # Chapter-5 validation convention.
    return f"{strategy}_traj{traj_idx}_step{step_idx}.json"


def _ch5_run_one_step(
    *,
    strategy: str,
    trajectory_index: int,
    step_index: int,
    pool: CounterexampleSet,
    current_incumbent: Dict[str, Any],
    output_dir: Path,
) -> Dict[str, Any]:
    """Run one chapter-5-style trajectory step. Mirrors the inline
    body of chapter5_validation_batch._run_one_step but with
    PROVIDER='vertex' and stripped of the cost/latency stop-rule
    enforcement (this driver's outer loop runs to completion)."""
    fake_set_index = 100 + trajectory_index
    fake_seed_index = step_index

    record = call_with_transient_retry(
        run_single_proposal,
        strategy_name=strategy,
        set_index=fake_set_index,
        seed_index=fake_seed_index,
        pool=pool,
        incumbent_heuristic=current_incumbent,
        output_dir=output_dir,
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
        incumbent_bins_step = compute_per_instance_bins_for_heuristic(
            current_incumbent["code"],
            current_incumbent["code_hash"],
            "train_step",
        )
        accepted, reason = should_accept_proposal(
            proposal_bins_step, incumbent_bins_step
        )

    step_record = {
        "phase": "validation_extension",
        "ch4extra_namespace_label": SEED_NAMESPACE_LABEL,
        "strategy_name": strategy,
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
    out_path = output_dir / _ch5_step_filename(
        strategy, trajectory_index, step_index
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(step_record, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return step_record


def _run_l1_trajectory(cell: Dict[str, Any], traj_idx: int) -> None:
    """Run all N_STEPS of one chapter-5-style trajectory at the
    given cell + trajectory_index. Resumable per-step."""
    strategy = cell["strategy"]
    output_dir = cell["output_dir"]
    current_incumbent = get_h_eoh()

    for step_idx in range(1, N_STEPS + 1):
        fn = _ch5_step_filename(strategy, traj_idx, step_idx)
        step_path = output_dir / fn
        if step_path.exists():
            prior = json.loads(step_path.read_text(encoding="utf-8"))
            if prior.get("accepted") and prior.get("sanitization_status") == "ok":
                # Reload the call record to recover the proposal source.
                call_json = output_dir / (
                    f"{strategy}_{prior['set_index_in_provenance']}"
                    f"_{prior['seed_index_in_provenance']}.json"
                )
                if call_json.exists():
                    call_record = json.loads(
                        call_json.read_text(encoding="utf-8")
                    )
                    current_incumbent = {
                        "code": call_record["sanitization"]["cleaned_code"],
                        "code_hash": call_record["proposal_hash"],
                        "algorithm": (
                            f"proposal_{strategy}_traj{traj_idx}_step{step_idx}"
                        ),
                    }
            print(
                f"  [{cell['label']} traj={traj_idx} step={step_idx}] "
                f"resumed (existing record)"
            )
            continue

        if step_idx == 1:
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
            f"  [{cell['label']} traj={traj_idx} step={step_idx}] "
            f"incumbent={current_incumbent['code_hash']}"
        )
        step_record = _ch5_run_one_step(
            strategy=strategy,
            trajectory_index=traj_idx,
            step_index=step_idx,
            pool=pool,
            current_incumbent=current_incumbent,
            output_dir=output_dir,
        )
        print(
            f"    sanitize={step_record['sanitization_status']} "
            f"d_step={step_record['delta_step_local']} "
            f"accepted={step_record['accepted']} "
            f"reason={step_record['acceptance_reason']}"
        )

        if step_record["accepted"]:
            call_json = output_dir / (
                f"{strategy}_{step_record['set_index_in_provenance']}"
                f"_{step_record['seed_index_in_provenance']}.json"
            )
            call_record = json.loads(
                call_json.read_text(encoding="utf-8")
            )
            current_incumbent = {
                "code": call_record["sanitization"]["cleaned_code"],
                "code_hash": call_record["proposal_hash"],
                "algorithm": (
                    f"proposal_{strategy}_traj{traj_idx}_step{step_idx}"
                ),
            }
        time.sleep(INTER_CALL_SLEEP_SECONDS)


# ---------------------------------------------------------------------------
# Chapter-7-style trajectory step (L2 cells)
# ---------------------------------------------------------------------------


def _run_l2_trajectory(cell: Dict[str, Any], traj_idx: int) -> None:
    """Run all N_STEPS of one chapter-7-style trajectory at the
    given cell + trajectory_index. Resumable per-step using
    chapter-7's helpers."""
    h_eoh = get_h_eoh()
    instance_lookup = _train_select_lookup()
    reference_source = _load_reference_source()
    score_cache = ScoreCache()

    output_dir = cell["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    current_incumbent = h_eoh
    for step_idx in range(N_STEPS):
        prior = load_step_record(
            output_dir, cell["cell_id"], traj_idx, step_idx
        )
        if is_step_complete(prior):
            current_incumbent = incumbent_for_next_step(prior, h_eoh)
            print(
                f"  [{cell['label']} traj={traj_idx} step={step_idx}] "
                f"resumed (existing record)"
            )
            continue

        print(
            f"  [{cell['label']} traj={traj_idx} step={step_idx}] "
            f"incumbent={current_incumbent['code_hash']}"
        )
        record = call_with_transient_retry(
            run_chapter7_validation_step,
            cell_id=cell["cell_id"],
            strategy=cell["strategy"],
            level=cell["level"],
            k=cell["k"],
            trajectory_index=traj_idx,
            step_index=step_idx,
            current_incumbent=current_incumbent,
            instance_lookup=instance_lookup,
            reference_source=reference_source,
            output_dir=output_dir,
            score_cache=score_cache,
            provider=PROVIDER,
            reasoning_effort=REASONING_EFFORT,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        print(
            f"    sanitize={(record.get('sanitization') or {}).get('status')} "
            f"d_step={record.get('delta_step_local')} "
            f"accepted={record.get('accepted')} "
            f"reason={record.get('acceptance_reason')}"
        )
        current_incumbent = incumbent_for_next_step(record, h_eoh)
        time.sleep(INTER_CALL_SLEEP_SECONDS)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _print_plan() -> None:
    print("=" * 72)
    print("CHAPTER 4 W-E5 — EXTRA VALIDATION TRAJECTORIES")
    print("=" * 72)
    print(f"Trajectory indices: {NEW_TRAJECTORY_INDICES}")
    print(f"Steps per trajectory: {N_STEPS}")
    print(f"Total LLM calls: 4 cells × 3 trajectories × 5 steps = 60")
    print(f"Provider: {PROVIDER}; reasoning_effort: {REASONING_EFFORT}; "
          f"max_output_tokens: {MAX_OUTPUT_TOKENS}")
    print(f"Conceptual namespace label: {SEED_NAMESPACE_LABEL}")
    print()
    print("Cells:")
    for c in CELLS:
        print(
            f"  {c['label']:<40} origin={c['origin']:<3} "
            f"strategy={c['strategy']:<28} L{c['level']} k={c['k']} "
            f"-> {c['output_dir'].name}/"
        )
    print("=" * 72)


def main() -> int:
    _print_plan()
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        for cell in CELLS:
            for traj_idx in NEW_TRAJECTORY_INDICES:
                print()
                print(
                    f">>> Cell {cell['label']}, trajectory_index={traj_idx} "
                    f"({cell['origin']}-protocol)"
                )
                if cell["origin"] == "ch5":
                    _run_l1_trajectory(cell, traj_idx)
                elif cell["origin"] == "ch7":
                    _run_l2_trajectory(cell, traj_idx)
                else:
                    raise ValueError(
                        f"Unknown cell origin: {cell['origin']!r}"
                    )
    except KeyboardInterrupt:
        finished_at = datetime.now(timezone.utc).isoformat()
        print(
            f"\n[interrupted] started_at={started_at} "
            f"finished_at={finished_at}; re-run to resume."
        )
        return 130

    finished_at = datetime.now(timezone.utc).isoformat()
    print()
    print("=" * 72)
    print(f"W-E5 finished. started_at={started_at}  finished_at={finished_at}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
