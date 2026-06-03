"""
thesis/code/experiments/chapter6_validation_batch.py

Chapter 6 validation batch driver. Runs the four (strategy, level)
cells in canonical order at 3 trajectories × 5 steps per cell — 60
total LLM calls — on Gemini 2.5 Pro at medium reasoning, 32k max
output tokens (chapter6_design.md §8.2, §13).

DO NOT run without an explicit operator go — this is the real
batch. Per-step JSON records land in
``thesis/results/chapter6_validation_batch_gemini/`` (gitignored);
on completion the consolidated overview is written to
``thesis/artifacts/chapter6_validation_batch_overview.json``.

Usage:
    python -m thesis.code.experiments.chapter6_validation_batch
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


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

from thesis.code.chapter6.batch_runner import DEFAULT_CELLS  # noqa: E402
from thesis.code.chapter6.validation_runner import (  # noqa: E402
    CellValidationResult,
    run_chapter6_validation_cell,
)
from thesis.code.incumbents import get_h_eoh  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS_DIR = REPO_ROOT / "thesis" / "artifacts"
OUTPUT_DIR = (
    REPO_ROOT / "thesis" / "results" / "chapter6_validation_batch_gemini"
)
OVERVIEW_PATH = ARTIFACTS_DIR / "chapter6_validation_batch_overview.json"

PROVIDER = "vertex"
MODEL = "gemini-2.5-pro"
REASONING_EFFORT = "medium"
# Per-provider max_output_tokens cap (mirrors chapter6_smart_resume).
# Vertex DSQ on this project rejects >12288 even on us-central1
# (probed 2026-04-29; see decisions log).
MAX_OUTPUT_TOKENS_BY_PROVIDER = {
    "gemini": 32768,
    "vertex": 12288,
    "groq": 2048,
}
VERTEX_LOCATION = "us-central1"
INTER_CALL_SLEEP_SECONDS = 3.0
TIMEOUT_SECONDS = 300.0
N_TRAJECTORIES = 3
N_STEPS = 5

LOCKED_RENDER_RULE = (
    "compact4 numeric format, N=60 rows (head=12 + stride=48); "
    "decisions log 2026-04-25"
)


def _serialize_cell(result: CellValidationResult) -> Dict[str, Any]:
    n_completed = sum(len(t.steps) for t in result.trajectories)
    n_succeeded = sum(
        1
        for t in result.trajectories
        for s in t.steps
        if s.sanitization_status == "ok"
    )
    return {
        "cell_id": result.cell_id,
        "n_trajectories": result.n_trajectories,
        "n_steps_per_trajectory": result.n_steps_per_trajectory,
        "n_completed_steps": n_completed,
        "n_succeeded_steps": n_succeeded,
        "trajectories": [
            {
                "trajectory_index": t.trajectory_index,
                "delta_step_cumulative_per_step": t.delta_step_cumulative_per_step,
                "final_incumbent_hash": t.final_incumbent_hash,
                "step_outcomes": [
                    {
                        "step_index": s.step_index,
                        "sanitization_status": s.sanitization_status,
                        "delta_step_local": s.delta_step_local,
                        "argmax_distinct": s.argmax_distinct,
                        "acceptance_decision": s.acceptance_decision,
                        "acceptance_reason": s.acceptance_reason,
                        "current_incumbent_hash": s.current_incumbent_hash,
                        "next_incumbent_hash": s.next_incumbent_hash,
                        "proposal_hash": s.proposal_hash,
                        "record_path": str(s.record_path),
                    }
                    for s in t.steps
                ],
            }
            for t in result.trajectories
        ],
        "acceptance_reason_counts": result.acceptance_reason_counts,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    h_eoh = get_h_eoh()

    if PROVIDER == "vertex":
        current_location = os.environ.get("GOOGLE_CLOUD_LOCATION")
        if current_location != VERTEX_LOCATION:
            print(
                f"  [vertex] setting GOOGLE_CLOUD_LOCATION={VERTEX_LOCATION} "
                f"(was {current_location!r}); required by DSQ-survival probe."
            )
            os.environ["GOOGLE_CLOUD_LOCATION"] = VERTEX_LOCATION

    print("=" * 72)
    print("CHAPTER 6 VALIDATION BATCH — Gemini 2.5 Pro / medium / 32k")
    print(
        f"cells={len(DEFAULT_CELLS)}  trajectories={N_TRAJECTORIES}  "
        f"steps={N_STEPS}  total_calls={len(DEFAULT_CELLS) * N_TRAJECTORIES * N_STEPS}"
    )
    print(f"output: {OUTPUT_DIR}")
    print(f"overview: {OVERVIEW_PATH}")
    print("=" * 72)

    cell_results: List[CellValidationResult] = []
    stopped = False
    stop_reason: str = ""

    try:
        for strategy_name, level in DEFAULT_CELLS:
            cell_id = f"{strategy_name}@L{level}"
            print(f"\n=== {cell_id} ===")
            result = run_chapter6_validation_cell(
                strategy_name=strategy_name,
                level=level,
                starting_incumbent=h_eoh,
                n_trajectories=N_TRAJECTORIES,
                n_steps=N_STEPS,
                output_dir=OUTPUT_DIR,
                provider=PROVIDER,
                reasoning_effort=REASONING_EFFORT,
                max_output_tokens=MAX_OUTPUT_TOKENS_BY_PROVIDER[PROVIDER],
                timeout_seconds=TIMEOUT_SECONDS,
                inter_call_sleep_seconds=INTER_CALL_SLEEP_SECONDS,
            )
            cell_results.append(result)
            for t in result.trajectories:
                print(
                    f"  traj={t.trajectory_index}  "
                    f"final={t.final_incumbent_hash[:12]}  "
                    f"cum_d_step={t.delta_step_cumulative_per_step}"
                )
    except KeyboardInterrupt:
        stopped = True
        stop_reason = "KeyboardInterrupt"
    except Exception as exc:  # noqa: BLE001
        stopped = True
        stop_reason = f"{type(exc).__name__}: {exc}"
        print(f"\n[FAILED] {stop_reason}", file=sys.stderr)

    finished_at = datetime.now(timezone.utc).isoformat()
    overview: Dict[str, Any] = {
        "header": {
            "started_at": started_at,
            "finished_at": finished_at,
            "stopped_early": stopped,
            "stop_reason": stop_reason,
            "model": MODEL,
            "provider": PROVIDER,
            "reasoning_effort": REASONING_EFFORT,
            "max_output_tokens": MAX_OUTPUT_TOKENS_BY_PROVIDER[PROVIDER],
            "temperature": 1.0,
            "inter_call_sleep_seconds": INTER_CALL_SLEEP_SECONDS,
            "timeout_seconds": TIMEOUT_SECONDS,
            "n_trajectories": N_TRAJECTORIES,
            "n_steps_per_trajectory": N_STEPS,
            "locked_render_rule": LOCKED_RENDER_RULE,
            "cells": [list(c) for c in DEFAULT_CELLS],
        },
        "cells": [_serialize_cell(r) for r in cell_results],
        "n_attempted": sum(
            len(t.steps) for r in cell_results for t in r.trajectories
        ),
    }
    OVERVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    OVERVIEW_PATH.write_text(
        json.dumps(overview, indent=2, sort_keys=True), encoding="utf-8",
    )
    print(f"\nOverview written to {OVERVIEW_PATH}")
    return 1 if stopped else 0


if __name__ == "__main__":
    sys.exit(main())
