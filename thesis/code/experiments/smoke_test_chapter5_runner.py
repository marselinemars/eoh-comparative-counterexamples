"""
thesis/code/experiments/smoke_test_chapter5_runner.py

Single-proposal end-to-end smoke test for the chapter-5 proposal
runner. Uses the deterministic `worst_only` strategy at
`set_index=0`, `seed_index=0` — the simplest possible invocation.

Writes one provenance JSON to
`thesis/results/chapter5_smoke/worst_only_0_0.json` and prints a
human-readable summary to stdout. One real LLM call.

Usage:
    python -m thesis.code.experiments.smoke_test_chapter5_runner
"""
from __future__ import annotations

from pathlib import Path

from thesis.code.chapter5.runner import run_single_proposal
from thesis.code.chapter5.seeds import llm_seed, set_seed
from thesis.code.counterexample import CounterexampleSet
from thesis.code.incumbents import get_h_eoh

REPO_ROOT = Path(__file__).resolve().parents[3]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)
OUTPUT_DIR = REPO_ROOT / "thesis" / "results" / "chapter5_smoke"


def main() -> int:
    pool = CounterexampleSet.from_json(POOL_PATH.read_text(encoding="utf-8"))
    h_eoh = get_h_eoh()

    strategy_name = "worst_only"
    set_index = 0
    seed_index = 0
    print(f"=== Chapter 5 smoke test ===")
    print(f"strategy:   {strategy_name}")
    print(f"set_index:  {set_index}")
    print(f"seed_index: {seed_index}")
    print(f"set_seed:   {set_seed(strategy_name, set_index)}")
    print(f"llm_seed:   {llm_seed(strategy_name, set_index, seed_index)}")
    print()

    record = run_single_proposal(
        strategy_name=strategy_name,
        set_index=set_index,
        seed_index=seed_index,
        pool=pool,
        incumbent_heuristic=h_eoh,
        output_dir=OUTPUT_DIR,
    )

    ce_ids = [ce["instance_id"] for ce in record["counterexample_set"]["items"]]
    print(f"selected counterexample instance_ids ({len(ce_ids)}):")
    for i, iid in enumerate(ce_ids, start=1):
        gap = record["counterexample_set"]["items"][i - 1]["gap"]
        print(f"  {i}. {iid}  (gap={gap})")
    print()

    prompt_preview = record["prompt"][:500]
    print("=== prompt (first 500 chars) ===")
    print(prompt_preview)
    if len(record["prompt"]) > 500:
        print(f"... [truncated; full length {len(record['prompt'])} chars]")
    print()

    print(f"=== sanitization ===")
    print(f"  status: {record['sanitization']['status']}")
    if record["sanitization"]["error"]:
        print(f"  error:  {record['sanitization']['error']}")
    print()

    scoring = record["scoring"]
    if scoring is not None:
        print("=== scoring ===")
        print(
            f"  mean_bins_h_eoh_train_step     = "
            f"{scoring['mean_bins_h_eoh_train_step']:.3f}"
        )
        print(
            f"  mean_bins_proposal_train_step  = "
            f"{scoring['mean_bins_proposal_train_step']:.3f}"
        )
        print(f"  delta_step         = {scoring['delta_step']:.3f}")
        print(
            f"  mean_bins_h_eoh_train_gate     = "
            f"{scoring['mean_bins_h_eoh_train_gate']:.3f}"
        )
        print(
            f"  mean_bins_proposal_train_gate  = "
            f"{scoring['mean_bins_proposal_train_gate']:.3f}"
        )
        print(f"  delta_gate         = {scoring['delta_gate']:.3f}")
        print(
            f"  generalization_gap = {scoring['generalization_gap']:.3f}"
        )
        print(f"  win_rate_step      = {scoring['win_rate_step']:.3f}")
    else:
        print("=== scoring ===")
        print("  skipped (sanitization did not return ok)")
    print()

    print(f"=== LLM usage ===")
    usage = record["llm_metadata"]["raw_response_metadata"].get("usage")
    print(f"  usage: {usage}")
    print(
        f"  finish_reason: "
        f"{record['llm_metadata']['raw_response_metadata'].get('finish_reason')}"
    )
    print(
        f"  system_fingerprint: "
        f"{record['llm_metadata']['raw_response_metadata'].get('system_fingerprint')}"
    )
    print(f"  seed_honored: {record['llm_metadata']['seed_honored']}")
    print()

    print(f"record written to: {record['_written_to']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
