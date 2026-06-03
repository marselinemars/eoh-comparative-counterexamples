"""
thesis/code/experiments/chapter5_calibration_2p5pro.py

3-call calibration probe on `gemini-2.5-pro` for chapter 5's
locked-settings swap from 3.1 Pro Preview. Uses the same full
chapter-5 smoke prompt as the 2026-04-20 Gemini 3.1 Pro Preview
calibration (worst_only, set_index=0, seed_index=0, committed pool,
h_eoh incumbent) so cross-model comparison is valid.

Calls:
  1. reasoning_effort=low,    max_output_tokens=8192  (hypothesized production)
  2. reasoning_effort=low,    max_output_tokens=4096  (tighter budget test)
  3. reasoning_effort=medium, max_output_tokens=8192  (heavier reasoning test)

Stopping rules:
  - HTTP 400 on any call: STOP.
  - Latency > 60s on any call: STOP.
  - Per-call cost > $0.05: STOP.
  - Call 1 sanitize failure is recorded but we continue to 2+3.

Budget: exactly 3 real LLM calls.

Pricing baseline (Gemini 2.5 Pro, as publicly advertised 2026-Q1):
  $1.25/M input, $10.00/M output. Output covers reasoning + visible.

Usage:
    python thesis/code/experiments/chapter5_calibration_2p5pro.py
"""
from __future__ import annotations

import json
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from thesis.code.chapter5 import worst_only
from thesis.code.chapter5.llm_client import call_gemini
from thesis.code.chapter5.prompt_builder import build_prompt
from thesis.code.chapter5.sanitize import sanitize
from thesis.code.counterexample import CounterexampleSet
from thesis.code.evaluation import bins_used
from thesis.code.incumbents import get_h_eoh
from thesis.code.score_cache import ScoreCache, code_hash
from thesis.code.splits import load_split, qualified_instance_id

REPO_ROOT = Path(__file__).resolve().parents[3]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)
OUTPUT_DIR = (
    REPO_ROOT / "thesis" / "results" / "chapter5_calibration_2p5pro"
)
SUMMARY_PATH = OUTPUT_DIR / "summary.json"

PRICE_INPUT_PER_M = 1.25
PRICE_OUTPUT_PER_M = 10.00

LATENCY_ABORT_SECONDS = 60.0
COST_ABORT_USD = 0.05

PROBE_CONFIGS = [
    {"label": "call1_low_8192", "reasoning_effort": "low", "max_output_tokens": 8192},
    {"label": "call2_low_4096", "reasoning_effort": "low", "max_output_tokens": 4096},
    {"label": "call3_medium_8192", "reasoning_effort": "medium", "max_output_tokens": 8192},
]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cost_usd(usage: Dict[str, Any]) -> float:
    p = usage.get("prompt_tokens") or 0
    t = usage.get("total_tokens") or 0
    out_tokens = max(0, t - p)
    return (
        p * PRICE_INPUT_PER_M / 1_000_000
        + out_tokens * PRICE_OUTPUT_PER_M / 1_000_000
    )


def _score_proposal(
    score_fn,
    proposal_code: str,
    proposal_hash: str,
    split_name: str,
    cache: ScoreCache,
) -> Dict[str, Any]:
    split = load_split(split_name)
    mod = types.ModuleType(f"p_{proposal_hash}")
    mod.score = score_fn
    per_inst = []
    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        b = cache.get_or_compute(
            proposal_hash, qid, lambda i=inst: bins_used(mod, i)
        )
        per_inst.append(b)
    return {
        "per_instance": per_inst,
        "mean": float(np.mean(per_inst)) if per_inst else None,
    }


def _score_baseline(
    h_eoh: Dict[str, Any], split_name: str, cache: ScoreCache
) -> Dict[str, Any]:
    incumbent_mod = types.ModuleType(f"h_eoh_{h_eoh['code_hash']}")
    exec(
        compile(h_eoh["code"], "<h_eoh>", "exec"),
        incumbent_mod.__dict__,
    )
    split = load_split(split_name)
    per_inst = []
    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        b = cache.get_or_compute(
            h_eoh["code_hash"], qid, lambda i=inst: bins_used(incumbent_mod, i)
        )
        per_inst.append(b)
    return {
        "per_instance": per_inst,
        "mean": float(np.mean(per_inst)),
    }


def _run_one(
    label: str,
    prompt: str,
    reasoning_effort: str,
    max_output_tokens: int,
    h_eoh: Dict[str, Any],
    cache: ScoreCache,
) -> Dict[str, Any]:
    print(
        f"\n[{label}] reasoning_effort={reasoning_effort} "
        f"max_output_tokens={max_output_tokens}"
    )
    started_at = _utcnow_iso()
    t0 = time.perf_counter()
    result = call_gemini(
        prompt=prompt,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
    )
    latency = time.perf_counter() - t0

    raw_text = result["text"]
    md = result["raw_response_metadata"]
    usage = md.get("usage") or {}
    finish_reason = md.get("finish_reason")
    reasoning_tokens = None
    if usage.get("total_tokens") is not None:
        reasoning_tokens = (
            (usage.get("total_tokens") or 0)
            - (usage.get("prompt_tokens") or 0)
            - (usage.get("completion_tokens") or 0)
        )
    cost = _cost_usd(usage)

    # Sanitize
    split_ts = load_split("train_select")
    san = sanitize(raw_text, split_ts["instances"][0])

    row: Dict[str, Any] = {
        "label": label,
        "model_returned": md.get("model_returned"),
        "status": 200,  # call_gemini raises on non-200
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "reasoning_tokens_inferred": reasoning_tokens,
        "finish_reason": finish_reason,
        "sanitization_status": san["status"],
        "sanitization_error": san["error"],
        "cost_usd_estimate": cost,
        "latency_seconds": latency,
        "reasoning_effort": reasoning_effort,
        "max_output_tokens": max_output_tokens,
        "raw_response_length_chars": len(raw_text),
        "raw_response_preview": raw_text[-400:] if raw_text else None,
        "cleaned_code_if_ok": san.get("cleaned_code") if san["status"] == "ok" else None,
        "started_at": started_at,
        "finished_at": _utcnow_iso(),
    }

    # Score if sanitize ok
    if san["status"] == "ok":
        proposal_code = san["cleaned_code"]
        proposal_hash = code_hash(proposal_code)
        baseline_step = _score_baseline(h_eoh, "train_step", cache)
        baseline_gate = _score_baseline(h_eoh, "train_gate", cache)
        proposal_step = _score_proposal(
            san["score_fn"], proposal_code, proposal_hash, "train_step", cache
        )
        proposal_gate = _score_proposal(
            san["score_fn"], proposal_code, proposal_hash, "train_gate", cache
        )
        delta_step = baseline_step["mean"] - proposal_step["mean"]
        delta_gate = baseline_gate["mean"] - proposal_gate["mean"]
        wins = sum(
            1
            for b, p in zip(
                baseline_step["per_instance"], proposal_step["per_instance"]
            )
            if p < b
        )
        n = len(baseline_step["per_instance"])
        row.update(
            {
                "proposal_hash": proposal_hash,
                "mean_bins_h_eoh_train_step": baseline_step["mean"],
                "mean_bins_proposal_train_step": proposal_step["mean"],
                "mean_bins_h_eoh_train_gate": baseline_gate["mean"],
                "mean_bins_proposal_train_gate": proposal_gate["mean"],
                "delta_step": delta_step,
                "delta_gate": delta_gate,
                "generalization_gap": delta_step - delta_gate,
                "win_rate_step": wins / n if n > 0 else None,
            }
        )

    # Per-call provenance
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{label}.json").write_text(
        json.dumps(row, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Print line
    print(
        f"  finish={finish_reason:<8} sanitize={san['status']:<18} "
        f"cost=${cost:.4f} latency={latency:.1f}s"
    )
    print(
        f"  usage: prompt={usage.get('prompt_tokens')} "
        f"completion={usage.get('completion_tokens')} "
        f"total={usage.get('total_tokens')} reasoning={reasoning_tokens}"
    )
    if row.get("delta_step") is not None:
        print(
            f"  d_step={row['delta_step']:+.2f} "
            f"d_gate={row['delta_gate']:+.2f} "
            f"win_rate_step={row['win_rate_step']:.3f}"
        )
    return row


def main() -> int:
    pool = CounterexampleSet.from_json(
        POOL_PATH.read_text(encoding="utf-8")
    )
    h_eoh = get_h_eoh()
    ce_set = worst_only(pool, k=4)
    prompt = build_prompt(
        counterexample_set=ce_set, incumbent_code=h_eoh["code"]
    )
    cache = ScoreCache()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 68)
    print("Chapter 5 calibration probe — gemini-2.5-pro")
    print("=" * 68)
    print(f"prompt length: {len(prompt)} chars")
    print(f"pricing: ${PRICE_INPUT_PER_M}/M input, ${PRICE_OUTPUT_PER_M}/M output")
    print(f"stopping: HTTP 400, latency>60s, cost>$0.05")

    started_at = _utcnow_iso()
    rows: List[Dict[str, Any]] = []
    stopped = False
    stop_reason = None

    for cfg in PROBE_CONFIGS:
        existing_path = OUTPUT_DIR / f"{cfg['label']}.json"
        if existing_path.exists():
            # Resume: reuse prior successful call's provenance so we
            # don't re-burn LLM budget.
            print(
                f"\n[{cfg['label']}] resuming from existing provenance "
                f"(no new LLM call)"
            )
            row = json.loads(existing_path.read_text(encoding="utf-8"))
            if row.get("delta_step") is not None:
                print(
                    f"  d_step={row['delta_step']:+.2f} "
                    f"d_gate={row['delta_gate']:+.2f} "
                    f"win_rate_step={row['win_rate_step']:.3f}"
                )
            rows.append(row)
            continue
        try:
            row = _run_one(
                label=cfg["label"],
                prompt=prompt,
                reasoning_effort=cfg["reasoning_effort"],
                max_output_tokens=cfg["max_output_tokens"],
                h_eoh=h_eoh,
                cache=cache,
            )
        except Exception as exc:
            stopped = True
            stop_reason = f"{cfg['label']}: {type(exc).__name__}: {exc}"
            print(f"  STOP: {stop_reason}")
            break

        rows.append(row)
        if row["latency_seconds"] > LATENCY_ABORT_SECONDS:
            stopped = True
            stop_reason = (
                f"{cfg['label']} latency {row['latency_seconds']:.1f}s "
                f"> {LATENCY_ABORT_SECONDS}s"
            )
            print(f"  STOP: {stop_reason}")
            break
        if row["cost_usd_estimate"] > COST_ABORT_USD:
            stopped = True
            stop_reason = (
                f"{cfg['label']} cost ${row['cost_usd_estimate']:.4f} "
                f"> ${COST_ABORT_USD}"
            )
            print(f"  STOP: {stop_reason}")
            break

    cache.save()
    finished_at = _utcnow_iso()

    # Summary
    n_calls = len(rows)
    n_trunc = sum(1 for r in rows if r["finish_reason"] == "length")
    n_ok = sum(1 for r in rows if r["sanitization_status"] == "ok")

    # Production settings are Call 1 (low, 8192)
    call1 = next(
        (r for r in rows if r["label"] == "call1_low_8192"), None
    )
    if call1 is not None:
        mean_cost_prod = call1["cost_usd_estimate"]
        mean_latency_prod = call1["latency_seconds"]
        batch_cost_405 = mean_cost_prod * 405
        # Sequential wall-clock at max 150 RPM = min 0.4s per call gap;
        # actual per-call latency dominates if > 0.4s.
        batch_wallclock_seconds_seq = max(
            mean_latency_prod * 405, 405 * 0.4
        )
    else:
        mean_cost_prod = None
        mean_latency_prod = None
        batch_cost_405 = None
        batch_wallclock_seconds_seq = None

    print()
    print("=" * 68)
    print("Summary")
    print("=" * 68)
    header = (
        f"  {'label':<20} {'prompt':>7} {'compl':>6} {'total':>7} "
        f"{'reas':>7} {'finish':<8} {'sanitize':<18} "
        f"{'$ est':>7} {'lat(s)':>7}"
    )
    print(header)
    for r in rows:
        print(
            f"  {r['label']:<20} "
            f"{r['prompt_tokens']:>7} "
            f"{r['completion_tokens']:>6} "
            f"{r['total_tokens']:>7} "
            f"{str(r['reasoning_tokens_inferred']):>7} "
            f"{r['finish_reason']:<8} "
            f"{r['sanitization_status']:<18} "
            f"${r['cost_usd_estimate']:.4f} "
            f"{r['latency_seconds']:>6.1f}"
        )
    print()
    print(f"  truncated (finish=length): {n_trunc}/{n_calls}")
    print(f"  sanitize ok:               {n_ok}/{n_calls}")
    if call1 is not None:
        print(f"\n  At production setting (call1, low/8192):")
        print(f"    mean cost:              ${mean_cost_prod:.4f}/call")
        print(f"    mean latency:           {mean_latency_prod:.1f}s")
        print(f"    extrapolated 405-call batch cost:       ${batch_cost_405:.2f}")
        print(
            f"    extrapolated sequential wall-clock:     "
            f"{batch_wallclock_seconds_seq / 60:.1f} min"
        )
        print(
            f"    rate-limited floor (150 RPM, 405 calls): "
            f"{405 / 150:.1f} min"
        )
    if stopped:
        print(f"\n  STOPPED EARLY: {stop_reason}")

    for r in rows:
        if r.get("delta_step") is not None:
            print(
                f"\n  {r['label']} proposal performance:"
                f"\n    d_step={r['delta_step']:+.3f}  "
                f"d_gate={r['delta_gate']:+.3f}  "
                f"win_rate_step={r['win_rate_step']:.3f}  "
                f"gen_gap={r['generalization_gap']:+.3f}"
            )

    summary = {
        "started_at": started_at,
        "finished_at": finished_at,
        "stopped_early": stopped,
        "stop_reason": stop_reason,
        "n_calls": n_calls,
        "n_truncated": n_trunc,
        "n_sanitize_ok": n_ok,
        "rows": rows,
        "production_settings_recommended": {
            "model": "gemini-2.5-pro",
            "temperature": 1.0,
            "max_output_tokens": 8192,
            "reasoning_effort": "low",
        },
        "mean_cost_usd_at_production_settings": mean_cost_prod,
        "mean_latency_at_production_settings": mean_latency_prod,
        "extrapolated_405_call_batch_cost_usd": batch_cost_405,
        "extrapolated_sequential_wall_clock_seconds_for_405_calls":
            batch_wallclock_seconds_seq,
        "pricing": {
            "input_per_m_usd": PRICE_INPUT_PER_M,
            "output_per_m_usd": PRICE_OUTPUT_PER_M,
        },
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(
        f"\nSummary JSON written to: "
        f"{SUMMARY_PATH.relative_to(REPO_ROOT).as_posix()}"
    )

    return 0 if not stopped else 1


if __name__ == "__main__":
    raise SystemExit(main())
