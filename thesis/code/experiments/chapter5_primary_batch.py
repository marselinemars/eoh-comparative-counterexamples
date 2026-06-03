"""
thesis/code/experiments/chapter5_primary_batch.py

Chapter 5 primary batch driver. Launches the 5-strategy x 60-proposal
batch on Gemini 2.5 Pro at medium reasoning, 32k max output tokens.

DO NOT run without an explicit operator go — this is the real
batch, ~10 hours and ~$21.

Resume-friendly: each per-call provenance JSON lands in OUTPUT_DIR;
re-running picks up where the previous run left off (batch_runner
skips any triple whose JSON already exists).

Most_discriminative is omitted: on the committed pool it collides
with worst_only (see decisions log 2026-04-23 and findings log
2026-04-20).

Usage:
    python thesis/code/experiments/chapter5_primary_batch.py
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

from thesis.code.chapter5.batch_runner import run_primary_batch  # noqa: E402
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import get_h_eoh  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)
OUTPUT_DIR = (
    REPO_ROOT / "thesis" / "results" / "chapter5_primary_batch_gemini"
)

PROVIDER = "gemini"
MODEL = "gemini-2.5-pro"
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 32768
TEMPERATURE = 1.0
INTER_CALL_SLEEP_SECONDS = 3.0

STRATEGIES = [
    "worst_only",
    "worst_plus_best",
    # "most_discriminative" DROPPED — collides with worst_only on
    # the committed pool. See decisions log 2026-04-23 and
    # findings log 2026-04-20.
    "uniform_random",
    "random_discriminative",
    "stratified_representative",
]


def main() -> int:
    pool = CounterexampleSet.from_json(
        POOL_PATH.read_text(encoding="utf-8")
    )
    h_eoh = get_h_eoh()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("CHAPTER 5 PRIMARY BATCH — Gemini 2.5 Pro / medium reasoning")
    print(
        "Expected wall-clock: ~10 hours "
        "(300 calls x ~116s + 3s sleep)"
    )
    print("Expected cost: ~$21 at observed mean $0.0713/call")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 72)

    try:
        summary = run_primary_batch(
            pool=pool,
            incumbent_heuristic=h_eoh,
            output_dir=OUTPUT_DIR,
            provider=PROVIDER,
            reasoning_effort=REASONING_EFFORT,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=TEMPERATURE,
            inter_call_sleep_seconds=INTER_CALL_SLEEP_SECONDS,
            strategies=STRATEGIES,
            summary_filename="primary_batch_summary.json",
            resume=True,
        )
    except KeyboardInterrupt:
        print(
            "\n[interrupted] partial batch persisted; re-run this "
            "script to resume (existing per-call JSONs will be "
            "skipped)."
        )
        return 130

    print()
    print("=" * 72)
    print(
        f"Primary batch done: {summary['n_calls_this_run']} calls "
        f"this run, {summary['n_skipped_existing']} skipped "
        "(pre-existing)."
    )
    print("=" * 72)
    return 0 if not summary.get("stopped_early") else 1


if __name__ == "__main__":
    sys.exit(main())
