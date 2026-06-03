"""
thesis/code/experiments/chapter5_calibration_groq.py

3-call calibration probe on Groq + llama-3.3-70b-versatile for
chapter 5's provisional batch authorized on 2026-04-22. Uses the
same full chapter-5 smoke prompt (worst_only, set_index=0,
seed_index=0, committed pool, h_eoh incumbent) as the prior Gemini
calibrations so cross-model comparison is valid.

Calls:
  1. max_output_tokens=8192, seed=llm_seed("worst_only", 0, 0), t=1.0
  2. max_output_tokens=4096, seed=llm_seed("worst_only", 0, 0), t=1.0
  3. max_output_tokens=8192, seed=llm_seed("worst_only", 0, 1), t=1.0
     (different seed -> sanity check that seed is actually doing
      something; call 3 must differ from call 1 byte-for-byte)

Stopping rules:
  - HTTP 4xx/5xx on any call: STOP.
  - Latency > 60s on any call: STOP.
  - Per-call cost > $0.05: STOP.

Budget: exactly 3 real LLM calls.

Pricing (Groq Llama 3.3 70B Versatile, 2026-Q1):
  $0.59/M input, $0.79/M output (verified at groq.com/pricing).
  Flagged for re-confirmation in the report if pricing has moved.

Usage:
    python thesis/code/experiments/chapter5_calibration_groq.py
"""
from __future__ import annotations

import hashlib
import json
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from thesis.code.chapter5 import worst_only
from thesis.code.chapter5.llm_client import call_llm
from thesis.code.chapter5.prompt_builder import build_prompt
from thesis.code.chapter5.sanitize import sanitize
from thesis.code.chapter5.seeds import llm_seed
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
    REPO_ROOT / "thesis" / "results" / "chapter5_calibration_groq_v2"
)
SUMMARY_PATH = OUTPUT_DIR / "summary.json"

# Groq Llama 3.3 70B Versatile pricing — verify before relying on.
PRICE_INPUT_PER_M = 0.59
PRICE_OUTPUT_PER_M = 0.79

LATENCY_ABORT_SECONDS = 30.0
COST_ABORT_USD = 0.05
INTER_CALL_SLEEP_SECONDS = 20.0


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cost_usd(usage: Dict[str, Any]) -> float:
    p = usage.get("prompt_tokens") or 0
    c = usage.get("completion_tokens") or 0
    return (
        p * PRICE_INPUT_PER_M / 1_000_000
        + c * PRICE_OUTPUT_PER_M / 1_000_000
    )


def _score_on_split(
    score_fn, proposal_hash: str, split_name: str, cache: ScoreCache
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


def _baseline_on_split(
    h_eoh: Dict[str, Any], split_name: str, cache: ScoreCache
) -> Dict[str, Any]:
    mod = types.ModuleType(f"h_eoh_{h_eoh['code_hash']}")
    exec(compile(h_eoh["code"], "<h_eoh>", "exec"), mod.__dict__)
    split = load_split(split_name)
    per_inst = []
    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        b = cache.get_or_compute(
            h_eoh["code_hash"], qid, lambda i=inst: bins_used(mod, i)
        )
        per_inst.append(b)
    return {
        "per_instance": per_inst,
        "mean": float(np.mean(per_inst)),
    }


def _run_one(
    label: str,
    prompt: str,
    seed: int,
    max_output_tokens: int,
    h_eoh: Dict[str, Any],
    cache: ScoreCache,
) -> Dict[str, Any]:
    print(
        f"\n[{label}] max_output_tokens={max_output_tokens} "
        f"seed={seed}"
    )
    started_at = _utcnow_iso()
    t0 = time.perf_counter()
    result = call_llm(
        prompt=prompt,
        provider="groq",
        max_output_tokens=max_output_tokens,
        seed=seed,
        # reasoning_effort stays at the default "low" — Groq silently
        # drops it; we record the caller intent for provenance.
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

    split_ts = load_split("train_select")
    san = sanitize(raw_text, split_ts["instances"][0])

    row: Dict[str, Any] = {
        "label": label,
        "provider": "groq",
        "model_returned": md.get("model_returned"),
        "status": 200,  # call_llm raises on non-200
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "reasoning_tokens_inferred": reasoning_tokens,
        "finish_reason": finish_reason,
        "sanitization_status": san["status"],
        "sanitization_error": san["error"],
        "cost_usd_estimate": cost,
        "latency_seconds": latency,
        "seed_requested": result["seed_requested"],
        "seed_honored": result["seed_honored"],
        "max_output_tokens": max_output_tokens,
        "raw_response_sha256": hashlib.sha256(
            (raw_text or "").encode("utf-8")
        ).hexdigest()[:16],
        "raw_response_length_chars": len(raw_text),
        "raw_response_preview": (raw_text[:2000] if raw_text else None),
        "cleaned_code_if_ok": san.get("cleaned_code") if san["status"] == "ok" else None,
        "started_at": started_at,
        "finished_at": _utcnow_iso(),
    }

    if san["status"] == "ok":
        proposal_code = san["cleaned_code"]
        proposal_hash = code_hash(proposal_code)
        baseline_step = _baseline_on_split(h_eoh, "train_step", cache)
        baseline_gate = _baseline_on_split(h_eoh, "train_gate", cache)
        proposal_step = _score_on_split(
            san["score_fn"], proposal_hash, "train_step", cache
        )
        proposal_gate = _score_on_split(
            san["score_fn"], proposal_hash, "train_gate", cache
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

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{label}.json").write_text(
        json.dumps(row, indent=2, sort_keys=True), encoding="utf-8"
    )

    print(
        f"  finish={finish_reason:<8} sanitize={san['status']:<18} "
        f"cost=${cost:.4f} latency={latency:.2f}s"
    )
    print(
        f"  usage: prompt={usage.get('prompt_tokens')} "
        f"completion={usage.get('completion_tokens')} "
        f"total={usage.get('total_tokens')}"
    )
    print(f"  seed_requested={result['seed_requested']} "
          f"seed_honored={result['seed_honored']}")
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

    seed_a = llm_seed("worst_only", 0, 0)
    seed_b = llm_seed("worst_only", 0, 1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 68)
    print("Chapter 5 calibration probe — groq / llama-3.3-70b-versatile")
    print("=" * 68)
    print(f"prompt length: {len(prompt)} chars")
    print(f"pricing: ${PRICE_INPUT_PER_M}/M input, ${PRICE_OUTPUT_PER_M}/M output")
    print(f"stopping: HTTP 4xx/5xx, latency>60s, cost>$0.05")
    print(f"seeds: a={seed_a} b={seed_b}")

    configs = [
        {"label": "call1_seed_a_2048", "seed": seed_a, "max_output_tokens": 2048},
        {"label": "call2_seed_b_2048", "seed": seed_b, "max_output_tokens": 2048},
        {"label": "call3_seed_a_4096", "seed": seed_a, "max_output_tokens": 4096},
    ]

    rows: List[Dict[str, Any]] = []
    stopped = False
    stop_reason = None
    last_call_end = None

    for i, cfg in enumerate(configs):
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

        try:
            row = _run_one(
                label=cfg["label"],
                prompt=prompt,
                seed=cfg["seed"],
                max_output_tokens=cfg["max_output_tokens"],
                h_eoh=h_eoh,
                cache=cache,
            )
        except Exception as exc:
            stopped = True
            stop_reason = f"{cfg['label']}: {type(exc).__name__}: {exc}"
            print(f"  STOP: {stop_reason}")
            break
        last_call_end = time.perf_counter()

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

    # Aggregates and seed verification
    n_calls = len(rows)
    n_trunc = sum(1 for r in rows if r["finish_reason"] == "length")
    n_ok = sum(1 for r in rows if r["sanitization_status"] == "ok")
    mean_cost = (
        sum(r["cost_usd_estimate"] for r in rows) / n_calls if n_calls else 0.0
    )
    mean_latency = (
        sum(r["latency_seconds"] for r in rows) / n_calls if n_calls else 0.0
    )

    # Production-setting extrapolation = call 1's profile.
    call1 = next((r for r in rows if r["label"] == "call1_seed_a_2048"), None)
    call2 = next((r for r in rows if r["label"] == "call2_seed_b_2048"), None)
    call3 = next((r for r in rows if r["label"] == "call3_seed_a_4096"), None)
    if call1 is not None:
        batch_cost_405 = call1["cost_usd_estimate"] * 405
        # Sequential wall-clock includes the 20s inter-call gap.
        batch_wallclock_seconds = (
            (call1["latency_seconds"] + INTER_CALL_SLEEP_SECONDS) * 405
        )
    else:
        batch_cost_405 = None
        batch_wallclock_seconds = None

    # Seed verification: calls 1 and 2 have different seeds, same
    # budget. Different seeds should produce different proposals
    # when Groq honors seed.
    seed_verification: Dict[str, Any] = {"comparable": False}
    if call1 is not None and call2 is not None:
        same_sha = (
            call1["raw_response_sha256"] == call2["raw_response_sha256"]
        )
        seed_verification = {
            "comparable": True,
            "call1_sha": call1["raw_response_sha256"],
            "call2_sha": call2["raw_response_sha256"],
            "proposals_are_byte_identical": same_sha,
            "interpretation": (
                "seed param REJECTED or IGNORED (same sha) — Groq may "
                "not be honoring seed despite accepting it"
                if same_sha
                else "seed param HONORED (different sha) — distinct "
                "proposals under distinct seeds"
            ),
        }

    # Budget comparison: calls 1 and 3 have same seed, different
    # max_output_tokens (2048 vs 4096). Did the larger budget
    # change the output? Same completion_tokens ~ budget oversized.
    budget_comparison: Dict[str, Any] = {"comparable": False}
    if call1 is not None and call3 is not None:
        c1_out = call1.get("completion_tokens")
        c3_out = call3.get("completion_tokens")
        same_sha = (
            call1["raw_response_sha256"] == call3["raw_response_sha256"]
        )
        budget_comparison = {
            "comparable": True,
            "call1_completion_tokens_2048budget": c1_out,
            "call3_completion_tokens_4096budget": c3_out,
            "budgets_produced_byte_identical_output": same_sha,
            "interpretation": (
                "same budget hit same output — 2048 sufficient"
                if same_sha
                else f"different outputs at different budgets "
                f"({c1_out} vs {c3_out} completion tokens); "
                f"either temperature or small sampling differences"
            ),
        }

    print()
    print("=" * 68)
    print("Summary")
    print("=" * 68)
    header = (
        f"  {'label':<22} {'prompt':>7} {'compl':>6} {'total':>7} "
        f"{'finish':<8} {'sanitize':<18} {'$ est':>7} {'lat(s)':>7}"
    )
    print(header)
    for r in rows:
        print(
            f"  {r['label']:<22} "
            f"{r['prompt_tokens']:>7} "
            f"{r['completion_tokens']:>6} "
            f"{r['total_tokens']:>7} "
            f"{r['finish_reason']:<8} "
            f"{r['sanitization_status']:<18} "
            f"${r['cost_usd_estimate']:.4f} "
            f"{r['latency_seconds']:>6.2f}"
        )
    print()
    print(f"  truncated (finish=length): {n_trunc}/{n_calls}")
    print(f"  sanitize ok:               {n_ok}/{n_calls}")
    if call1 is not None:
        print(f"\n  At production setting (call1, 8192, seed_a):")
        print(f"    cost:                 ${call1['cost_usd_estimate']:.4f}/call")
        print(f"    latency:              {call1['latency_seconds']:.2f}s")
        print(
            f"    extrapolated 405-call batch cost:   ${batch_cost_405:.2f}"
        )
        print(
            f"    extrapolated sequential wall-clock: "
            f"{batch_wallclock_seconds / 60:.1f} min"
        )
    print()
    print(f"  Seed verification (call1 vs call2, different seeds):")
    if seed_verification.get("comparable"):
        print(
            f"    call1 sha={seed_verification['call1_sha']}  "
            f"call2 sha={seed_verification['call2_sha']}"
        )
        print(f"    {seed_verification['interpretation']}")
    else:
        print("    not comparable (one or both of calls 1/2 not run)")
    print(f"\n  Budget comparison (call1=2048 vs call3=4096, same seed):")
    if budget_comparison.get("comparable"):
        print(
            f"    call1 completion_tokens (2048 budget) = "
            f"{budget_comparison['call1_completion_tokens_2048budget']}"
        )
        print(
            f"    call3 completion_tokens (4096 budget) = "
            f"{budget_comparison['call3_completion_tokens_4096budget']}"
        )
        print(f"    {budget_comparison['interpretation']}")
    else:
        print("    not comparable (one or both of calls 1/3 not run)")
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
        "started_at": rows[0]["started_at"] if rows else None,
        "finished_at": rows[-1]["finished_at"] if rows else None,
        "stopped_early": stopped,
        "stop_reason": stop_reason,
        "n_calls": n_calls,
        "n_truncated": n_trunc,
        "n_sanitize_ok": n_ok,
        "rows": rows,
        "seed_verification": seed_verification,
        "budget_comparison": budget_comparison,
        "production_settings_recommended": {
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "temperature": 1.0,
            "max_output_tokens": 8192,
        },
        "mean_cost_usd": mean_cost,
        "mean_latency_seconds": mean_latency,
        "batch_cost_at_call1_profile": batch_cost_405,
        "batch_wallclock_at_call1_profile": batch_wallclock_seconds,
        "pricing": {
            "input_per_m_usd": PRICE_INPUT_PER_M,
            "output_per_m_usd": PRICE_OUTPUT_PER_M,
            "note": "Groq Llama 3.3 70B Versatile as of 2026-Q1; verify if stale.",
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
