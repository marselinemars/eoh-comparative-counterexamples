"""
thesis/code/experiments/chapter6_primary_batch_smoke.py

3-call smoke test for the chapter 6 primary-batch plumbing.

Runs one LLM call for each of three cells:
  - (stratified_representative, L1)  set 0, seed 0
  - (stratified_representative, L2)  set 0, seed 0
  - (worst_plus_best,           L2)  set 0, seed 0

The fourth cell (worst_plus_best, L1) is skipped because its
plumbing is identical to the L2 cell except for the prompt
renderer's level branch — already exercised by the L1 smoke
above.

Verifies the live LLM path end-to-end (renderer →
call_llm → sanitize → score → record write). 3/3 sanitize-ok
is the green-light signal for the full batch; anything less is
a stop-and-investigate.

Usage:
    python thesis/code/experiments/chapter6_primary_batch_smoke.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Tuple


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

from thesis.code.chapter6.batch_runner import run_chapter6_cell  # noqa: E402
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import (  # noqa: E402
    get_h_eoh,
    load_final_population,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)
OUTPUT_DIR = (
    REPO_ROOT / "thesis" / "results" / "chapter6_primary_batch_smoke"
)

PROVIDER = "gemini"
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 32768
TIMEOUT_SECONDS = 300.0

SMOKE_CELLS: List[Tuple[str, int]] = [
    ("stratified_representative", 1),
    ("stratified_representative", 2),
    ("worst_plus_best", 2),
]


def _reference_source_for_pool(pool: CounterexampleSet) -> str:
    reference_hashes = {c.reference_hash for c in pool}
    target = next(iter(reference_hashes))
    for member in load_final_population():
        if member["code_hash"] == target:
            return member["code"]
    raise RuntimeError(
        f"Reference heuristic {target!r} not found in EoH final population"
    )


def main() -> int:
    pool = CounterexampleSet.from_json(POOL_PATH.read_text(encoding="utf-8"))
    h_eoh = get_h_eoh()
    reference_source = _reference_source_for_pool(pool)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("CHAPTER 6 SMOKE — 3 cells x 1 proposal")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 72)

    summaries = []
    for strategy_name, level in SMOKE_CELLS:
        cell_id = f"{strategy_name}@L{level}"
        print()
        print(f"--- {cell_id} ---")
        result = run_chapter6_cell(
            strategy_name=strategy_name,
            level=level,
            pool=pool,
            incumbent_heuristic=h_eoh,
            reference_source=reference_source,
            n_proposals=1,
            output_dir=OUTPUT_DIR,
            provider=PROVIDER,
            reasoning_effort=REASONING_EFFORT,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            timeout_seconds=TIMEOUT_SECONDS,
            inter_call_sleep_seconds=3.0,
        )
        summaries.append(result)
        # The per-call record contains prompt char count and Δ_step;
        # surface a one-line line per call.
        if result.proposal_record_paths:
            import json as _json
            rec_path = Path(result.proposal_record_paths[0])
            rec = _json.loads(rec_path.read_text(encoding="utf-8"))
            prompt_chars = len(rec.get("prompt", ""))
            response_chars = len(rec.get("raw_response", ""))
            scoring = rec.get("scoring") or {}
            delta_step = scoring.get("delta_step")
            llm_meta = rec.get("llm_metadata", {})
            raw_meta = llm_meta.get("raw_response_metadata") or {}
            # Best-effort token counts from provider metadata.
            usage = raw_meta.get("usage") if isinstance(raw_meta, dict) else None
            print(
                f"  cell={cell_id} "
                f"sanitize={result.n_succeeded}/{result.n_attempted} "
                f"prompt_chars={prompt_chars} "
                f"response_chars={response_chars} "
                f"delta_step={delta_step} "
                f"usage={usage}"
            )

    n_ok = sum(s.n_succeeded for s in summaries)
    n_attempted = sum(s.n_attempted for s in summaries)
    print()
    print("=" * 72)
    print(f"smoke aggregate: {n_ok}/{n_attempted} sanitize-ok")
    if n_ok == n_attempted:
        print("GREEN — primary batch is cleared to launch.")
    else:
        for s in summaries:
            if s.n_succeeded < s.n_attempted:
                print(
                    f"FAILED cell {s.cell_id}: "
                    f"{s.n_failed_per_label}"
                )
        print("RED — investigate before launching the primary batch.")
    print("=" * 72)
    return 0 if n_ok == n_attempted else 1


if __name__ == "__main__":
    sys.exit(main())
