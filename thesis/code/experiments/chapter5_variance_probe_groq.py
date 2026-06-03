"""
thesis/code/experiments/chapter5_variance_probe_groq.py

2-call variance probe on Groq to distinguish today's observed
−49 Δ_step from an n=1 outlier vs. a systemic quality regression.

Calls worst_only at seed_index=1 and seed_index=2, combines with
the existing seed_index=0 record from the 2026-04-23 Task 4l
pre-batch validation, and computes Δ_step statistics.

Hard cap: 2 real LLM calls. 20s inter-call sleep. No commits.

Usage:
    python thesis/code/experiments/chapter5_variance_probe_groq.py
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from thesis.code.chapter5.runner import run_single_proposal
from thesis.code.counterexample import CounterexampleSet
from thesis.code.incumbents import get_h_eoh

REPO_ROOT = Path(__file__).resolve().parents[3]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)
OUTPUT_DIR = (
    REPO_ROOT
    / "thesis"
    / "results"
    / "chapter5_variance_probe_groq_2026_04_23"
)
EXISTING_TODAY_CALL_PATH = (
    REPO_ROOT
    / "thesis"
    / "results"
    / "chapter5_prebatch_validation_groq"
    / "worst_only_0_0.json"
)
YESTERDAY_CALIB_DIR = (
    REPO_ROOT / "thesis" / "results" / "chapter5_calibration_groq_v2"
)

PROVIDER = "groq"
LATENCY_ABORT_SECONDS = 120.0
COST_ABORT_USD = 0.01
INTER_CALL_SLEEP_SECONDS = 20.0

PRICE_INPUT_PER_M = 0.59
PRICE_OUTPUT_PER_M = 0.79


def _cost(usage: Dict[str, Any]) -> float:
    p = usage.get("prompt_tokens") or 0
    c = usage.get("completion_tokens") or 0
    return (
        p * PRICE_INPUT_PER_M / 1_000_000
        + c * PRICE_OUTPUT_PER_M / 1_000_000
    )


def _summarize_record(record: Dict[str, Any], latency: float) -> Dict[str, Any]:
    md = record["llm_metadata"]["raw_response_metadata"]
    usage = md.get("usage") or {}
    scoring = record.get("scoring") or {}
    return {
        "strategy_name": record["strategy_name"],
        "seed_index": record["seed_index"],
        "llm_seed": record["llm_seed"],
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "finish_reason": md.get("finish_reason"),
        "sanitization_status": record["sanitization"]["status"],
        "sanitization_error": record["sanitization"].get("error"),
        "delta_step": scoring.get("delta_step"),
        "delta_gate": scoring.get("delta_gate"),
        "win_rate_step": scoring.get("win_rate_step"),
        "mean_bins_proposal_train_step": scoring.get(
            "mean_bins_proposal_train_step"
        ),
        "cost_usd_estimate": _cost(usage),
        "latency_seconds": latency,
        "seed_requested": record["llm_metadata"].get("seed_requested"),
        "seed_honored": record["llm_metadata"].get("seed_honored"),
    }


def _load_today_existing() -> Dict[str, Any] | None:
    """Today's prior call from Task 4l (worst_only, seed_index=0)."""
    if not EXISTING_TODAY_CALL_PATH.exists():
        return None
    d = json.loads(EXISTING_TODAY_CALL_PATH.read_text(encoding="utf-8"))
    md = d["llm_metadata"]["raw_response_metadata"]
    usage = md.get("usage") or {}
    scoring = d.get("scoring") or {}
    return {
        "strategy_name": d["strategy_name"],
        "seed_index": d["seed_index"],
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "delta_step": scoring.get("delta_step"),
        "delta_gate": scoring.get("delta_gate"),
        "win_rate_step": scoring.get("win_rate_step"),
        "cost_usd_estimate": _cost(usage),
        # Latency wasn't recorded inside the provenance; approximate
        # from Task 4l report (68.76s) — we only use it for mean
        # latency reporting, not as a stopping criterion.
        "latency_seconds": 68.76,
        "sanitization_status": d["sanitization"]["status"],
    }


def _load_yesterday_calibration() -> List[Dict[str, Any]]:
    """Yesterday's 3 worst_only calls at varying budgets/seeds."""
    if not YESTERDAY_CALIB_DIR.exists():
        return []
    rows = []
    for p in sorted(YESTERDAY_CALIB_DIR.glob("call*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        rows.append(
            {
                "label": d.get("label"),
                "delta_step": d.get("delta_step"),
                "delta_gate": d.get("delta_gate"),
                "win_rate_step": d.get("win_rate_step"),
                "latency_seconds": d.get("latency_seconds"),
                "sanitization_status": d.get("sanitization_status"),
            }
        )
    return rows


def _stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"n": 0, "mean": None, "stddev": None, "min": None, "max": None}
    n = len(values)
    m = sum(values) / n
    var = sum((v - m) ** 2 for v in values) / n if n > 0 else 0.0
    return {
        "n": n,
        "mean": m,
        "stddev": math.sqrt(var),
        "min": min(values),
        "max": max(values),
    }


def main() -> int:
    pool = CounterexampleSet.from_json(
        POOL_PATH.read_text(encoding="utf-8")
    )
    h_eoh = get_h_eoh()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("Chapter 5 Groq variance probe — 2026-04-23")
    print("=" * 72)

    # --- 2 new calls -------------------------------------------------
    new_rows: List[Dict[str, Any]] = []
    stopped = False
    stop_reason = None
    last_call_end = None

    for seed_index in (1, 2):
        if last_call_end is not None:
            elapsed = time.perf_counter() - last_call_end
            remaining = INTER_CALL_SLEEP_SECONDS - elapsed
            if remaining > 0:
                print(f"\n[inter-call sleep] {remaining:.1f}s")
                time.sleep(remaining)

        label = f"worst_only_0_{seed_index}"
        print(f"\n[call {seed_index}] strategy=worst_only seed_index={seed_index}")
        t0 = time.perf_counter()
        try:
            record = run_single_proposal(
                strategy_name="worst_only",
                set_index=0,
                seed_index=seed_index,
                pool=pool,
                incumbent_heuristic=h_eoh,
                output_dir=OUTPUT_DIR,
                provider=PROVIDER,
            )
        except Exception as exc:
            stopped = True
            stop_reason = f"seed_index={seed_index}: {type(exc).__name__}: {exc}"
            print(f"  STOP: {stop_reason}")
            break
        latency = time.perf_counter() - t0
        last_call_end = time.perf_counter()
        row = _summarize_record(record, latency)
        new_rows.append(row)

        print(
            f"  finish={row['finish_reason']:<8} "
            f"sanitize={row['sanitization_status']:<18} "
            f"cost=${row['cost_usd_estimate']:.4f} latency={latency:.2f}s"
        )
        if row["delta_step"] is not None:
            print(
                f"  d_step={row['delta_step']:+.2f} "
                f"d_gate={row['delta_gate']:+.2f} "
                f"win_rate_step={row['win_rate_step']:.3f}"
            )

        if latency > LATENCY_ABORT_SECONDS:
            stopped = True
            stop_reason = (
                f"seed_index={seed_index} latency {latency:.1f}s "
                f"> {LATENCY_ABORT_SECONDS}s"
            )
            print(f"  STOP: {stop_reason}")
            break
        if row["cost_usd_estimate"] > COST_ABORT_USD:
            stopped = True
            stop_reason = (
                f"seed_index={seed_index} cost "
                f"${row['cost_usd_estimate']:.4f} > ${COST_ABORT_USD}"
            )
            print(f"  STOP: {stop_reason}")
            break

    # --- Combine with today's seed_index=0 and compute stats ---------
    today_existing = _load_today_existing()
    if today_existing is not None:
        today_all = [today_existing] + new_rows
    else:
        today_all = list(new_rows)

    today_deltas = [
        r["delta_step"] for r in today_all
        if r.get("delta_step") is not None
    ]
    today_latencies = [
        r.get("latency_seconds", 0.0) for r in today_all
    ]
    today_wins = [
        r["win_rate_step"] for r in today_all
        if r.get("win_rate_step") is not None
    ]

    today_stats = _stats(today_deltas)
    today_beat_h_eoh = sum(1 for d in today_deltas if d > 0)
    today_sanitize_ok = sum(
        1 for r in today_all if r.get("sanitization_status") == "ok"
    )

    yesterday_rows = _load_yesterday_calibration()
    yest_deltas = [
        r["delta_step"] for r in yesterday_rows if r["delta_step"] is not None
    ]
    yest_latencies = [
        r["latency_seconds"] for r in yesterday_rows
        if r.get("latency_seconds") is not None
    ]
    yest_stats = _stats(yest_deltas)
    yest_beat_h_eoh = sum(1 for d in yest_deltas if d > 0)
    yest_sanitize_ok = sum(
        1 for r in yesterday_rows if r.get("sanitization_status") == "ok"
    )

    # --- Print comparison --------------------------------------------
    print()
    print("=" * 72)
    print("Today's 3 calls (worst_only, seed 0/1/2, 2026-04-23):")
    print(
        f"  {'seed_idx':<10} {'sanitize':<18} {'d_step':>8} "
        f"{'d_gate':>8} {'win_rt':>7} {'lat(s)':>8}"
    )
    for r in today_all:
        print(
            f"  {r['seed_index']!s:<10} "
            f"{r.get('sanitization_status', '?'):<18} "
            f"{(r.get('delta_step') if r.get('delta_step') is not None else float('nan')):>+8.2f} "
            f"{(r.get('delta_gate') if r.get('delta_gate') is not None else float('nan')):>+8.2f} "
            f"{(r.get('win_rate_step') if r.get('win_rate_step') is not None else float('nan')):>7.3f} "
            f"{r.get('latency_seconds', 0.0):>8.2f}"
        )
    print()
    print(
        f"  Today Δ_step  n={today_stats['n']} "
        f"mean={today_stats['mean']:.2f} "
        f"stddev={today_stats['stddev']:.2f} "
        f"range=[{today_stats['min']:+.2f}, {today_stats['max']:+.2f}]"
    )
    print(f"  Today beat h_eoh (Δ_step>0): {today_beat_h_eoh}/{len(today_deltas)}")
    print(f"  Today sanitize ok: {today_sanitize_ok}/{len(today_all)}")
    if today_latencies:
        print(
            f"  Today mean latency: "
            f"{sum(today_latencies)/len(today_latencies):.2f}s"
        )

    print()
    print(
        f"Yesterday's 3 calls (Task 4k calibration, 2026-04-22):"
    )
    print(
        f"  {'label':<22} {'sanitize':<18} {'d_step':>8} "
        f"{'d_gate':>8} {'win_rt':>7} {'lat(s)':>8}"
    )
    for r in yesterday_rows:
        print(
            f"  {r.get('label', '?'):<22} "
            f"{r.get('sanitization_status', '?'):<18} "
            f"{(r.get('delta_step') if r.get('delta_step') is not None else float('nan')):>+8.2f} "
            f"{(r.get('delta_gate') if r.get('delta_gate') is not None else float('nan')):>+8.2f} "
            f"{(r.get('win_rate_step') if r.get('win_rate_step') is not None else float('nan')):>7.3f} "
            f"{r.get('latency_seconds', 0.0):>8.2f}"
        )
    print()
    if yest_deltas:
        print(
            f"  Yesterday Δ_step  n={yest_stats['n']} "
            f"mean={yest_stats['mean']:.2f} "
            f"stddev={yest_stats['stddev']:.2f} "
            f"range=[{yest_stats['min']:+.2f}, {yest_stats['max']:+.2f}]"
        )
    print(f"  Yesterday beat h_eoh: {yest_beat_h_eoh}/{len(yest_deltas)}")
    print(f"  Yesterday sanitize ok: {yest_sanitize_ok}/{len(yesterday_rows)}")
    if yest_latencies:
        print(
            f"  Yesterday mean latency: "
            f"{sum(yest_latencies)/len(yest_latencies):.2f}s"
        )

    # --- Classification ---------------------------------------------
    print()
    print("=" * 72)
    print("Classification")
    print("=" * 72)
    if today_deltas:
        rng = today_stats["max"] - today_stats["min"]
        max_d = today_stats["max"]
        all_below_neg30 = all(d < -30 for d in today_deltas)
        any_above_neg20 = any(d > -20 for d in today_deltas)
        if rng > 30 and any_above_neg20:
            classification = "(a) high-variance today"
        elif rng < 15 and all_below_neg30:
            classification = "(b) low-variance today (systemic regression)"
        else:
            classification = "(c) mixed / ambiguous"
        print(f"  range = {rng:.2f}, max_delta_step = {max_d:+.2f}")
        print(f"  all below −30? {all_below_neg30}")
        print(f"  any above −20? {any_above_neg20}")
        print(f"  classification: {classification}")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stopped_early": stopped,
        "stop_reason": stop_reason,
        "today_calls": today_all,
        "today_stats": today_stats,
        "today_beat_h_eoh": today_beat_h_eoh,
        "today_sanitize_ok": today_sanitize_ok,
        "yesterday_calls": yesterday_rows,
        "yesterday_stats": yest_stats,
        "yesterday_beat_h_eoh": yest_beat_h_eoh,
        "yesterday_sanitize_ok": yest_sanitize_ok,
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(
        f"\nSummary JSON: "
        f"{(OUTPUT_DIR / 'summary.json').relative_to(REPO_ROOT).as_posix()}"
    )
    return 0 if not stopped else 1


if __name__ == "__main__":
    raise SystemExit(main())
