"""
thesis/code/experiments/chapter6_primary_batch.py

Chapter 6 primary batch driver. Runs the four (strategy, level)
cells in canonical order at 60 proposals per cell — 240 total
LLM calls — on Gemini 2.5 Pro at medium reasoning, 32k max
output tokens (chapter6_design.md §8.1, §13).

DO NOT run without an explicit operator go — this is the real
batch, ~12 hours and ~$17 at the chapter 5 observed mean
$0.0713 / call. (The chapter 6 prompts are larger than chapter 5's
because of the Level-2 trace block; the actual cost is bounded
above by the chapter 5 figure for L1 cells and somewhat higher
for L2 cells. The smoke driver provides a tighter estimate.)

Resume-friendly: a per-cell record file is named
``<cell_id>_set<NNN>_seed<NNN>.json``; if a record already
exists in the output directory the call is skipped, mirroring
chapter 5's discipline.

Usage:
    python thesis/code/experiments/chapter6_primary_batch.py
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
    _record_filename,
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
OVERVIEW_PATH = ARTIFACTS_DIR / "chapter6_primary_batch_overview.json"

PROVIDER = "gemini"
MODEL = "gemini-2.5-pro"
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 32768
INTER_CALL_SLEEP_SECONDS = 3.0
TIMEOUT_SECONDS = 300.0
N_PROPOSALS_PER_CELL = 60


def _reference_source_for_pool(pool: CounterexampleSet) -> str:
    """Resolve the chapter 5 / chapter 6 reference heuristic source from
    the pool's reference_hash, looked up in EoH's final population."""
    reference_hashes = {c.reference_hash for c in pool}
    if len(reference_hashes) != 1:
        raise RuntimeError(
            f"Pool must have a single reference hash; got {reference_hashes}"
        )
    target = next(iter(reference_hashes))
    for member in load_final_population():
        if member["code_hash"] == target:
            return member["code"]
    raise RuntimeError(
        f"Reference heuristic {target!r} not found in EoH final population"
    )


def _existing_record_count(cell_id: str) -> int:
    """How many proposals for this cell already have a record on disk."""
    pattern = f"{cell_id}_set*.json"
    return sum(1 for _ in OUTPUT_DIR.glob(pattern))


def _resumable_n_proposals(cell_id: str) -> int:
    """Return the number of proposals still to run for this cell."""
    have = _existing_record_count(cell_id)
    return max(0, N_PROPOSALS_PER_CELL - have)


def main() -> int:
    pool = CounterexampleSet.from_json(POOL_PATH.read_text(encoding="utf-8"))
    h_eoh = get_h_eoh()
    reference_source = _reference_source_for_pool(pool)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("CHAPTER 6 PRIMARY BATCH — Gemini 2.5 Pro / medium reasoning")
    print(
        "Expected: 240 LLM calls (4 cells x 60 proposals); "
        "~12 h, ~$17–$25"
    )
    print(f"Output:   {OUTPUT_DIR}")
    print(f"Overview: {OVERVIEW_PATH}")
    print("=" * 72)

    started_at = datetime.now(timezone.utc).isoformat()
    cell_results: List[Dict[str, Any]] = []
    stopped_early = False

    try:
        for strategy_name, level in DEFAULT_CELLS:
            cell_id = f"{strategy_name}@L{level}"
            already = _existing_record_count(cell_id)
            remaining = _resumable_n_proposals(cell_id)
            print()
            print(f"--- {cell_id} ---")
            print(
                f"  existing: {already}/{N_PROPOSALS_PER_CELL}; "
                f"running:  {remaining}"
            )
            if remaining == 0:
                cell_results.append({
                    "cell_id": cell_id,
                    "strategy_name": strategy_name,
                    "level": level,
                    "n_attempted": 0,
                    "n_succeeded": already,  # assume from existing
                    "n_skipped_existing": already,
                    "output_dir": str(OUTPUT_DIR),
                    "n_failed_per_label": {},
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
                f"{result.n_attempted} sanitize-ok"
                + (
                    f"; failures={result.n_failed_per_label}"
                    if result.n_failed_per_label
                    else ""
                ),
                file=sys.stderr,
            )
    except KeyboardInterrupt:
        stopped_early = True
        print(
            "\n[interrupted] partial batch persisted; re-run to resume "
            "(per-cell record files will be skipped)."
        )

    finished_at = datetime.now(timezone.utc).isoformat()
    overview = {
        "started_at": started_at,
        "finished_at": finished_at,
        "stopped_early": stopped_early,
        "settings": {
            "provider": PROVIDER,
            "model": MODEL,
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
    print("=" * 72)
    print(f"Primary batch overview written to {OVERVIEW_PATH}")
    print("=" * 72)
    return 1 if stopped_early else 0


if __name__ == "__main__":
    sys.exit(main())
