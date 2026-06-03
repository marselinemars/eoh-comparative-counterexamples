"""
thesis/code/experiments/chapter5_primary_batch_smoke.py

3-call smoke run at Chapter-5 production settings. Exercises
run_single_proposal with the new reasoning_effort / max_output_tokens
plumbing before the full batch launches.

Covers:
  1. worst_only                 (catastrophic on probe — sanity)
  2. random_discriminative      (beat h_eoh on probe — sanity)
  3. stratified_representative  (beat h_eoh on probe — sanity)

Hard cap: 3 LLM calls. STOP on any sanitize failure — smoke is a
plumbing check, not a quality check.

Usage:
    python thesis/code/experiments/chapter5_primary_batch_smoke.py
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


_load_env_file(Path(__file__).resolve().parents[3] / ".env")

from thesis.code.chapter5.runner import run_single_proposal  # noqa: E402
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import get_h_eoh  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)
OUTPUT_DIR = (
    REPO_ROOT
    / "thesis"
    / "results"
    / "chapter5_primary_batch_smoke_2026_04_23"
)

PROVIDER = "gemini"
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 32768
LATENCY_ABORT_SECONDS = 240.0
COST_ABORT_USD = 0.15
INTER_CALL_SLEEP_SECONDS = 3.0

PRICE_INPUT_PER_M = 1.25
PRICE_OUTPUT_PER_M = 10.0

SMOKE_TARGETS = [
    "worst_only",
    "random_discriminative",
    "stratified_representative",
]


def _cost(usage: Dict[str, Any]) -> float:
    p = usage.get("prompt_tokens") or 0
    c = usage.get("completion_tokens") or 0
    total = usage.get("total_tokens") or (p + c)
    rt = max(0, total - p - c)
    return (
        p * PRICE_INPUT_PER_M / 1_000_000
        + (c + rt) * PRICE_OUTPUT_PER_M / 1_000_000
    )


def _summarize(record: Dict[str, Any], latency: float) -> Dict[str, Any]:
    md = record["llm_metadata"]["raw_response_metadata"]
    usage = md.get("usage") or {}
    scoring = record.get("scoring") or {}
    sanit = record.get("sanitization") or {}
    p = usage.get("prompt_tokens") or 0
    c = usage.get("completion_tokens") or 0
    t = usage.get("total_tokens") or (p + c)
    return {
        "strategy_name": record["strategy_name"],
        "sanitization_status": sanit.get("status"),
        "sanitization_error": sanit.get("error"),
        "format_detected": sanit.get("format_detected"),
        "prompt_tokens": p,
        "completion_tokens": c,
        "total_tokens": t,
        "reasoning_tokens": max(0, t - p - c),
        "delta_step": scoring.get("delta_step"),
        "delta_gate": scoring.get("delta_gate"),
        "win_rate_step": scoring.get("win_rate_step"),
        "finish_reason": md.get("finish_reason"),
        "latency_seconds": latency,
        "cost_usd_estimate": _cost(usage),
    }


def main() -> int:
    pool = CounterexampleSet.from_json(
        POOL_PATH.read_text(encoding="utf-8")
    )
    h_eoh = get_h_eoh()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(
        "Chapter 5 primary-batch smoke (Gemini 2.5 Pro, medium, 32k)"
    )
    print("=" * 72)

    rows: List[Dict[str, Any]] = []
    stopped = False
    stop_reason: Optional[str] = None
    last_call_end: Optional[float] = None

    for i, strategy_name in enumerate(SMOKE_TARGETS):
        if last_call_end is not None:
            elapsed = time.perf_counter() - last_call_end
            rem = INTER_CALL_SLEEP_SECONDS - elapsed
            if rem > 0:
                time.sleep(rem)

        print(f"\n[{i + 1}/3] strategy={strategy_name}")
        t0 = time.perf_counter()
        try:
            record = run_single_proposal(
                strategy_name=strategy_name,
                set_index=0,
                seed_index=0,
                pool=pool,
                incumbent_heuristic=h_eoh,
                output_dir=OUTPUT_DIR,
                provider=PROVIDER,
                reasoning_effort=REASONING_EFFORT,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
        except Exception as exc:
            stopped = True
            stop_reason = f"{strategy_name}: {type(exc).__name__}: {exc}"
            print(f"  STOP (error): {stop_reason}")
            break
        latency = time.perf_counter() - t0
        last_call_end = time.perf_counter()
        row = _summarize(record, latency)
        rows.append(row)

        print(
            f"  finish={row['finish_reason']:<8} "
            f"sanitize={row['sanitization_status']:<18} "
            f"format={row['format_detected']!s}"
        )
        print(
            f"  tokens p/c/r={row['prompt_tokens']}/"
            f"{row['completion_tokens']}/{row['reasoning_tokens']} "
            f"cost=${row['cost_usd_estimate']:.4f} "
            f"latency={latency:.2f}s"
        )
        if row["delta_step"] is not None:
            print(
                f"  d_step={row['delta_step']:+.2f} "
                f"d_gate={row['delta_gate']:+.2f} "
                f"win_rate={row['win_rate_step']:.3f}"
            )

        if latency > LATENCY_ABORT_SECONDS:
            stopped = True
            stop_reason = f"latency {latency:.1f}s > {LATENCY_ABORT_SECONDS}s"
            print(f"  STOP: {stop_reason}")
            break
        if row["cost_usd_estimate"] > COST_ABORT_USD:
            stopped = True
            stop_reason = (
                f"call cost ${row['cost_usd_estimate']:.4f} > "
                f"${COST_ABORT_USD}"
            )
            print(f"  STOP: {stop_reason}")
            break
        if row["sanitization_status"] != "ok":
            stopped = True
            stop_reason = (
                f"{strategy_name} sanitize={row['sanitization_status']} "
                f"(plumbing regression suspected)"
            )
            print(f"  STOP: {stop_reason}")
            break

    # Per-call table
    print()
    print("=" * 72)
    print("Smoke per-call table")
    print("=" * 72)
    print(
        f"{'strategy':<26} {'san':<12} "
        f"{'d_step':>8} {'d_gate':>8} "
        f"{'ptok':>5} {'ctok':>5} {'rtok':>5} "
        f"{'lat':>7} {'cost':>7}"
    )
    for r in rows:
        ds = r.get("delta_step")
        dg = r.get("delta_gate")
        print(
            f"{r['strategy_name']:<26} "
            f"{(r['sanitization_status'] or '?'):<12} "
            f"{(ds if ds is not None else float('nan')):>+8.2f} "
            f"{(dg if dg is not None else float('nan')):>+8.2f} "
            f"{r['prompt_tokens']:>5d} "
            f"{r['completion_tokens']:>5d} "
            f"{r['reasoning_tokens']:>5d} "
            f"{r['latency_seconds']:>7.2f} "
            f"${r['cost_usd_estimate']:>6.4f}"
        )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": PROVIDER,
        "reasoning_effort": REASONING_EFFORT,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "stopped_early": stopped,
        "stop_reason": stop_reason,
        "rows": rows,
    }
    (OUTPUT_DIR / "smoke_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        f"\nSmoke summary: "
        f"{(OUTPUT_DIR / 'smoke_summary.json').relative_to(REPO_ROOT).as_posix()}"
    )
    return 0 if not stopped else 1


if __name__ == "__main__":
    sys.exit(main())
