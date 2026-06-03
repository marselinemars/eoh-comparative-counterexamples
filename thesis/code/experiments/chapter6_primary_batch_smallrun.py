"""
thesis/code/experiments/chapter6_primary_batch_smallrun.py

Small-N variant of chapter6_primary_batch.py. Same four cells,
same locked settings, but only N_PROPOSALS_PER_CELL=5 per cell
(20 LLM calls total). Diagnostic: confirms the prompt + pipeline
+ scoring path produces useful proposals at small scale before
committing to the full 240-call batch.

Same OUTPUT_DIR as the primary driver, so records produced here
count toward the eventual full batch — the production driver's
resume logic will skip them on a later relaunch.

Usage:
    python -m thesis.code.experiments.chapter6_primary_batch_smallrun
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

from thesis.code.chapter6.batch_runner import (  # noqa: E402
    DEFAULT_CELLS,
    CellResult,
    run_chapter6_cell,
)
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import (  # noqa: E402
    get_h_eoh,
    load_final_population,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)
ARTIFACTS_DIR = REPO_ROOT / "thesis" / "artifacts"
OUTPUT_DIR = (
    REPO_ROOT / "thesis" / "results" / "chapter6_primary_batch_gemini"
)
OVERVIEW_PATH = ARTIFACTS_DIR / "chapter6_primary_batch_smallrun_overview.json"

PROVIDER = "gemini"
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 32768
INTER_CALL_SLEEP_SECONDS = 3.0
TIMEOUT_SECONDS = 300.0
N_PROPOSALS_PER_CELL = 5


def _reference_source_for_pool(pool: CounterexampleSet) -> str:
    target = next(iter({c.reference_hash for c in pool}))
    for member in load_final_population():
        if member["code_hash"] == target:
            return member["code"]
    raise RuntimeError(f"Reference {target!r} not found in EoH final population")


def _existing_record_count(cell_id: str) -> int:
    return sum(1 for _ in OUTPUT_DIR.glob(f"{cell_id}_set*.json"))


def main() -> int:
    pool = CounterexampleSet.from_json(POOL_PATH.read_text(encoding="utf-8"))
    h_eoh = get_h_eoh()
    reference_source = _reference_source_for_pool(pool)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("CHAPTER 6 SMALL-RUN — 5 proposals × 4 cells = 20 LLM calls")
    print(f"Output:   {OUTPUT_DIR}")
    print(f"Overview: {OVERVIEW_PATH}")
    print("=" * 72)

    started_at = datetime.now(timezone.utc).isoformat()
    cell_results: List[Dict[str, Any]] = []

    try:
        for strategy_name, level in DEFAULT_CELLS:
            cell_id = f"{strategy_name}@L{level}"
            already = _existing_record_count(cell_id)
            remaining = max(0, N_PROPOSALS_PER_CELL - already)
            print()
            print(f"--- {cell_id} ---  existing: {already}, running: {remaining}")
            if remaining == 0:
                cell_results.append({
                    "cell_id": cell_id,
                    "strategy_name": strategy_name,
                    "level": level,
                    "n_attempted": 0,
                    "n_succeeded": already,
                    "n_skipped_existing": already,
                    "n_failed_per_label": {},
                    "output_dir": str(OUTPUT_DIR),
                })
                continue

            result: CellResult = run_chapter6_cell(
                strategy_name=strategy_name,
                level=level,
                pool=pool,
                incumbent_heuristic=h_eoh,
                reference_source=reference_source,
                n_proposals=remaining,
                output_dir=OUTPUT_DIR,
                provider=PROVIDER,
                reasoning_effort=REASONING_EFFORT,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                timeout_seconds=TIMEOUT_SECONDS,
                inter_call_sleep_seconds=INTER_CALL_SLEEP_SECONDS,
            )
            cell_results.append({
                "cell_id": result.cell_id,
                "strategy_name": strategy_name,
                "level": level,
                "n_attempted": result.n_attempted,
                "n_succeeded": result.n_succeeded,
                "n_skipped_existing": already,
                "n_failed_per_label": result.n_failed_per_label,
                "output_dir": str(OUTPUT_DIR),
            })
            print(
                f"  {result.cell_id}: {result.n_succeeded}/"
                f"{result.n_attempted} sanitize-ok",
                file=sys.stderr,
            )
    except KeyboardInterrupt:
        print(
            "\n[interrupted] partial small-run persisted; re-run to resume.",
            file=sys.stderr,
        )

    finished_at = datetime.now(timezone.utc).isoformat()
    overview = {
        "started_at": started_at,
        "finished_at": finished_at,
        "settings": {
            "provider": PROVIDER,
            "reasoning_effort": REASONING_EFFORT,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "inter_call_sleep_seconds": INTER_CALL_SLEEP_SECONDS,
            "timeout_seconds": TIMEOUT_SECONDS,
            "n_proposals_per_cell": N_PROPOSALS_PER_CELL,
        },
        "cells": cell_results,
        "output_dir": str(OUTPUT_DIR),
    }
    OVERVIEW_PATH.write_text(
        json.dumps(overview, indent=2, sort_keys=True), encoding="utf-8"
    )
    print()
    print(f"Small-run overview written to {OVERVIEW_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
