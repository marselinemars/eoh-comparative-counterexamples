"""
thesis/code/experiments/chapter5_prebatch_validation.py

Pre-batch validation of the chapter-5 pipeline at provisional
Groq settings per the 2026-04-22 decisions-log entry:

    provider          = "groq"
    model             = llama-3.3-70b-versatile (llm_client default)
    temperature       = 1.0
    max_output_tokens = 2048 (provider default for groq)
    reasoning_effort  = "low" (caller-intent; Groq silently drops it)

Runs run_single_proposal exactly once per strategy for all six
chapter-5 strategies, with set_index=0 and seed_index=0. Writes
provenance records plus a summary JSON; prints a summary table
to stdout.

Stopping rules (hard stops before running all 6):
  - HTTP 4xx/5xx on any call.
  - Latency > 30s on any call (Groq is typically <3s; 30s is
    deeply anomalous).
  - Per-call cost > $0.05.
  - Three consecutive sanitization failures.

Inter-call sleep: 20 seconds between calls (not before the first)
to respect Groq's free-tier 12,000 TPM limit, which debits
`max_output_tokens` at request time rather than actual usage.

Call budget: exactly 6 real LLM calls.

Pricing (Groq Llama 3.3 70B Versatile, 2026-Q1):
  $0.59/M input, $0.79/M output.

Usage:
    python thesis/code/experiments/chapter5_prebatch_validation.py
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from thesis.code.chapter5.llm_client import MAX_OUTPUT_TOKENS_DEFAULTS, MODEL_IDS
from thesis.code.chapter5.runner import run_single_proposal
from thesis.code.counterexample import CounterexampleSet
from thesis.code.incumbents import get_h_eoh

REPO_ROOT = Path(__file__).resolve().parents[3]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)

PROVIDER = "groq"
OUTPUT_DIR = (
    REPO_ROOT / "thesis" / "results" / f"chapter5_prebatch_validation_{PROVIDER}"
)
SUMMARY_PATH = OUTPUT_DIR / "summary.json"

STRATEGIES_IN_ORDER = [
    "worst_only",
    "worst_plus_best",
    "most_discriminative",
    "uniform_random",
    "random_discriminative",
    "stratified_representative",
]

# Pricing per provider. Verify before relying on specific numbers.
PRICING: Dict[str, Dict[str, float]] = {
    "gemini": {"input_per_m_usd": 1.25, "output_per_m_usd": 10.00},
    "groq": {"input_per_m_usd": 0.59, "output_per_m_usd": 0.79},
}

LATENCY_ABORT_SECONDS = 30.0
COST_ABORT_USD = 0.05
CONSECUTIVE_SANITIZE_FAILURE_LIMIT = 3
INTER_CALL_SLEEP_SECONDS = 20.0


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cost_usd(usage: Dict[str, Any], provider: str) -> float:
    p = usage.get("prompt_tokens") or 0
    c = usage.get("completion_tokens") or 0
    price = PRICING[provider]
    # Gemini bills hidden reasoning tokens as output (total - prompt).
    # Groq bills only visible completion tokens as output.
    if provider == "gemini":
        t = usage.get("total_tokens") or 0
        out_tokens = max(0, t - p)
    else:
        out_tokens = c
    return (
        p * price["input_per_m_usd"] / 1_000_000
        + out_tokens * price["output_per_m_usd"] / 1_000_000
    )


def _summarize_call(
    strategy: str, record: Dict[str, Any], latency: float, provider: str
) -> Dict[str, Any]:
    md = record["llm_metadata"]["raw_response_metadata"]
    usage = md.get("usage") or {}
    reasoning = None
    if usage.get("total_tokens") is not None:
        reasoning = (
            (usage.get("total_tokens") or 0)
            - (usage.get("prompt_tokens") or 0)
            - (usage.get("completion_tokens") or 0)
        )
    san = record["sanitization"]
    scoring = record.get("scoring")
    row: Dict[str, Any] = {
        "strategy_name": strategy,
        "provider": provider,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "reasoning_tokens_inferred": reasoning,
        "finish_reason": md.get("finish_reason"),
        "sanitization_status": san["status"],
        "sanitization_error": san.get("error"),
        "cost_usd_estimate": _cost_usd(usage, provider),
        "latency_seconds": latency,
        "seed_requested": record["llm_metadata"].get("seed_requested"),
        "seed_honored": record["llm_metadata"].get("seed_honored"),
        "proposal_hash": record.get("proposal_hash"),
    }
    if scoring is not None:
        row["delta_step"] = scoring["delta_step"]
        row["delta_gate"] = scoring["delta_gate"]
        row["generalization_gap"] = scoring["generalization_gap"]
        row["win_rate_step"] = scoring["win_rate_step"]
        row["mean_bins_proposal_train_step"] = scoring[
            "mean_bins_proposal_train_step"
        ]
    else:
        row["delta_step"] = None
        row["delta_gate"] = None
        row["generalization_gap"] = None
        row["win_rate_step"] = None
        row["mean_bins_proposal_train_step"] = None
    return row


def main() -> int:
    pool = CounterexampleSet.from_json(
        POOL_PATH.read_text(encoding="utf-8")
    )
    h_eoh = get_h_eoh()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("Chapter 5 pre-batch validation")
    print(
        f"Settings: provider={PROVIDER}, model={MODEL_IDS[PROVIDER]}, "
        f"temperature=1.0, max_output_tokens="
        f"{MAX_OUTPUT_TOKENS_DEFAULTS[PROVIDER]}, reasoning_effort=low"
    )
    print(
        f"Stopping: HTTP 4xx/5xx, latency>{LATENCY_ABORT_SECONDS}s, "
        f"cost>${COST_ABORT_USD}, "
        f"{CONSECUTIVE_SANITIZE_FAILURE_LIMIT} consecutive sanitize fails"
    )
    print(f"Inter-call sleep: {INTER_CALL_SLEEP_SECONDS}s")
    print("=" * 72)

    rows: List[Dict[str, Any]] = []
    stopped = False
    stop_reason = None
    consecutive_sanitize_fails = 0
    last_call_end: float | None = None

    started_at = _utcnow_iso()
    t_batch = time.perf_counter()

    for i, strategy in enumerate(STRATEGIES_IN_ORDER):
        # Respect TPM budget by spacing calls.
        if last_call_end is not None:
            elapsed = time.perf_counter() - last_call_end
            remaining = INTER_CALL_SLEEP_SECONDS - elapsed
            if remaining > 0:
                print(
                    f"\n[inter-call sleep] {remaining:.1f}s "
                    f"(budget={INTER_CALL_SLEEP_SECONDS}s)"
                )
                time.sleep(remaining)

        print(
            f"\n[{i + 1}/6] strategy={strategy}  "
            f"set_index=0 seed_index=0"
        )
        t0 = time.perf_counter()
        try:
            record = run_single_proposal(
                strategy_name=strategy,
                set_index=0,
                seed_index=0,
                pool=pool,
                incumbent_heuristic=h_eoh,
                output_dir=OUTPUT_DIR,
                provider=PROVIDER,
            )
        except Exception as exc:
            latency = time.perf_counter() - t0
            print(
                f"  ERROR: {type(exc).__name__}: {exc} "
                f"(after {latency:.1f}s)"
            )
            stopped = True
            stop_reason = f"exception on {strategy}: {exc}"
            break
        latency = time.perf_counter() - t0
        last_call_end = time.perf_counter()
        row = _summarize_call(strategy, record, latency, PROVIDER)
        rows.append(row)

        finish = row["finish_reason"]
        san_status = row["sanitization_status"]
        cost = row["cost_usd_estimate"]
        print(
            f"  finish={finish:<8}  sanitize={san_status:<18}  "
            f"cost=${cost:.4f}  latency={latency:.2f}s"
        )
        if row["delta_step"] is not None:
            print(
                f"  d_step={row['delta_step']:+.2f}  "
                f"d_gate={row['delta_gate']:+.2f}  "
                f"win_rate_step={row['win_rate_step']:.3f}"
            )

        # Consecutive sanitization failure tracking
        if san_status == "ok":
            consecutive_sanitize_fails = 0
        else:
            consecutive_sanitize_fails += 1

        # Stopping rules
        if latency > LATENCY_ABORT_SECONDS:
            stopped = True
            stop_reason = (
                f"{strategy} latency {latency:.1f}s "
                f"> {LATENCY_ABORT_SECONDS}s"
            )
            print(f"  STOP: {stop_reason}")
            break
        if cost > COST_ABORT_USD:
            stopped = True
            stop_reason = (
                f"{strategy} cost ${cost:.4f} > ${COST_ABORT_USD}"
            )
            print(f"  STOP: {stop_reason}")
            break
        if consecutive_sanitize_fails >= CONSECUTIVE_SANITIZE_FAILURE_LIMIT:
            stopped = True
            stop_reason = (
                f"{consecutive_sanitize_fails} consecutive sanitize "
                f"failures"
            )
            print(f"  STOP: {stop_reason}")
            break

    batch_wall_clock = time.perf_counter() - t_batch
    finished_at = _utcnow_iso()

    # Aggregate metrics
    n_calls = len(rows)
    n_truncated = sum(1 for r in rows if r["finish_reason"] == "length")
    n_ok = sum(1 for r in rows if r["sanitization_status"] == "ok")
    costs = [r["cost_usd_estimate"] for r in rows]
    latencies = [r["latency_seconds"] for r in rows]
    mean_cost = sum(costs) / n_calls if n_calls > 0 else 0.0
    mean_latency = sum(latencies) / n_calls if n_calls > 0 else 0.0

    # Sanitize-ok aggregates
    ok_rows = [r for r in rows if r["sanitization_status"] == "ok"]
    if ok_rows:
        mean_delta_step = sum(r["delta_step"] for r in ok_rows) / len(ok_rows)
        mean_delta_gate = sum(r["delta_gate"] for r in ok_rows) / len(ok_rows)
        gen_gaps = [r["generalization_gap"] for r in ok_rows]
        mean_win_rate = sum(r["win_rate_step"] for r in ok_rows) / len(ok_rows)
        n_beat_h_eoh_step = sum(1 for r in ok_rows if r["delta_step"] > 0)
        n_beat_h_eoh_gate = sum(1 for r in ok_rows if r["delta_gate"] > 0)
    else:
        mean_delta_step = None
        mean_delta_gate = None
        gen_gaps = []
        mean_win_rate = None
        n_beat_h_eoh_step = 0
        n_beat_h_eoh_gate = 0

    extrapolated_batch_cost = mean_cost * 405
    # Sequential wall-clock = 405 × (latency + inter-call sleep),
    # minus one sleep interval (no sleep after the last call).
    extrapolated_sequential_wall_clock_seconds = (
        (mean_latency + INTER_CALL_SLEEP_SECONDS) * 405
        - INTER_CALL_SLEEP_SECONDS
    )

    # Summary print
    print()
    print("=" * 72)
    print("Summary")
    print("=" * 72)
    print(f"  calls ran:                       {n_calls}/6")
    print(f"  truncated (finish_reason=length): {n_truncated}/{n_calls}")
    print(f"  sanitize ok:                     {n_ok}/{n_calls}")
    print(f"  mean cost per call:              ${mean_cost:.4f}")
    print(
        f"  extrapolated 405-call batch cost: ${extrapolated_batch_cost:.2f}"
    )
    print(f"  mean latency per call:           {mean_latency:.2f}s")
    sequential_min = extrapolated_sequential_wall_clock_seconds / 60
    print(
        f"  extrapolated sequential wall-clock for 405 calls "
        f"(incl. {INTER_CALL_SLEEP_SECONDS}s/call sleep): "
        f"{sequential_min:.1f} min"
    )
    print(f"  batch wall-clock for these 6 calls: {batch_wall_clock:.1f}s")
    if ok_rows:
        print()
        print(f"  sanitize-ok aggregates (n={len(ok_rows)}):")
        print(f"    mean d_step = {mean_delta_step:+.3f}")
        print(f"    mean d_gate = {mean_delta_gate:+.3f}")
        print(
            f"    gen_gap range = [{min(gen_gaps):+.3f}, "
            f"{max(gen_gaps):+.3f}]"
        )
        print(f"    mean win_rate_step = {mean_win_rate:.3f}")
        print(
            f"    beat h_eoh on train_step: {n_beat_h_eoh_step}/{len(ok_rows)}"
        )
        print(
            f"    beat h_eoh on train_gate: {n_beat_h_eoh_gate}/{len(ok_rows)}"
        )
    if stopped:
        print(f"\n  STOPPED EARLY: {stop_reason}")

    summary = {
        "started_at": started_at,
        "finished_at": finished_at,
        "stopped_early": stopped,
        "stop_reason": stop_reason,
        "n_calls": n_calls,
        "n_truncated": n_truncated,
        "n_sanitize_ok": n_ok,
        "mean_cost_usd": mean_cost,
        "mean_latency_seconds": mean_latency,
        "extrapolated_405_call_batch_cost_usd": extrapolated_batch_cost,
        "extrapolated_sequential_wall_clock_seconds_for_405_calls":
            extrapolated_sequential_wall_clock_seconds,
        "batch_wall_clock_seconds": batch_wall_clock,
        "ok_aggregates": {
            "n_ok": len(ok_rows),
            "mean_delta_step": mean_delta_step,
            "mean_delta_gate": mean_delta_gate,
            "gen_gap_min": min(gen_gaps) if gen_gaps else None,
            "gen_gap_max": max(gen_gaps) if gen_gaps else None,
            "mean_win_rate_step": mean_win_rate,
            "n_beat_h_eoh_train_step": n_beat_h_eoh_step,
            "n_beat_h_eoh_train_gate": n_beat_h_eoh_gate,
        },
        "rows": rows,
        "settings": {
            "provider": PROVIDER,
            "model": MODEL_IDS[PROVIDER],
            "temperature": 1.0,
            "max_output_tokens": MAX_OUTPUT_TOKENS_DEFAULTS[PROVIDER],
            "reasoning_effort": "low",
            "set_index": 0,
            "seed_index": 0,
            "inter_call_sleep_seconds": INTER_CALL_SLEEP_SECONDS,
        },
        "pricing": PRICING[PROVIDER],
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        f"\nSummary JSON written to: "
        f"{SUMMARY_PATH.relative_to(REPO_ROOT).as_posix()}"
    )

    return 0 if not stopped else 1


if __name__ == "__main__":
    raise SystemExit(main())
