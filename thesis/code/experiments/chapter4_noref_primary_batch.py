"""
thesis/code/experiments/chapter4_noref_primary_batch.py

E1 (no-reference) primary batch driver — chapter 4 §4.5.1 control
cell. Launches the 20-set × 3-seed batch on Gemini 2.5 Pro at
medium reasoning, 32k max output tokens.

DO NOT run without an explicit operator go — this is a real
batch, ~60 LLM calls, billable.

Resume-friendly: each per-call provenance JSON lands in OUTPUT_DIR;
re-running picks up where the previous run left off
(chapter4_noref.batch_runner skips any (set, seed) pair whose JSON
already exists).

Matched-paired to chapter-5's stratified_representative L1 cell:
CounterexampleSet draws are bit-identical (chapter-5's set_seed
reused); per-call LLM seeds are fresh under the ch4noref:
namespace.

Usage:
    python -m thesis.code.experiments.chapter4_noref_primary_batch
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


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

from thesis.code.chapter4_noref.batch_runner import run_noref_batch  # noqa: E402
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import get_h_eoh  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)
OUTPUT_DIR = (
    REPO_ROOT / "thesis" / "results"
    / "chapter4_noref_primary_batch_gemini"
)

PROVIDER = "vertex"  # Per decisions-log 2026-05-05: Gemini 2.5 Pro via Vertex AI
MODEL = "gemini-2.5-pro"
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 32768
TEMPERATURE = 1.0
INTER_CALL_SLEEP_SECONDS = 3.0


def main() -> int:
    pool = CounterexampleSet.from_json(
        POOL_PATH.read_text(encoding="utf-8")
    )
    h_eoh = get_h_eoh()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(
        "CHAPTER 4 §4.5.1 — E1 NO-REFERENCE primary batch "
        "— Gemini 2.5 Pro / medium reasoning"
    )
    print(
        "Cell: stratified_representative @ L1 @ k=4; "
        "20 sets × 3 seeds = 60 calls; ~$0.07/call observed; "
        "expected ~$4–5"
    )
    print(f"Output: {OUTPUT_DIR}")
    print(
        "Matched-paired to chapter-5's stratified_representative "
        "L1 cell at the same (set_index, seed_index) coordinates."
    )
    print("=" * 72)

    try:
        summary = run_noref_batch(
            pool=pool,
            incumbent_heuristic=h_eoh,
            output_dir=OUTPUT_DIR,
            provider=PROVIDER,
            reasoning_effort=REASONING_EFFORT,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=TEMPERATURE,
            inter_call_sleep_seconds=INTER_CALL_SLEEP_SECONDS,
            summary_filename="primary_batch_summary.json",
            resume=True,
        )
    except KeyboardInterrupt:
        print(
            "\n[interrupted] partial batch persisted; re-run this "
            "script to resume."
        )
        return 130

    print()
    print("=" * 72)
    print(
        f"E1 batch done: {summary['n_calls_this_run']} calls this "
        f"run, {summary['n_skipped_existing']} skipped (pre-existing)."
    )
    print("=" * 72)
    return 0 if not summary.get("stopped_early") else 1


if __name__ == "__main__":
    sys.exit(main())
