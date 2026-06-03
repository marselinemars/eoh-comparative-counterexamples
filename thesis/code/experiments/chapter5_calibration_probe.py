"""
thesis/code/experiments/chapter5_calibration_probe.py

Calibration probe for chapter-5 LLM settings. Runs up to 8 real
Gemini 3.1 Pro Preview calls split across two phases:

  Phase 1 (up to 4 calls): tests whether the OpenAI-compatible shim
  at generativelanguage.googleapis.com/v1beta/openai accepts any
  thinking/reasoning budget control parameter (4 candidate shapes).
  Each probe uses a minimal "respond with OK" prompt.

  Phase 2 (2-4 calls): runs the real chapter-5 smoke-test prompt
  (worst_only strategy, committed pool, h_eoh incumbent) at
  varying max_output_tokens and (if Phase 1 found one) optional
  thinking-budget settings. Writes full provenance per call.

Hard cap: 8 real LLM calls. Script aborts if the budget is reached
mid-run.

Usage:
    python thesis/code/experiments/chapter5_calibration_probe.py
"""
from __future__ import annotations

import http.client
import json
import os
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import numpy as np

# --- repo-local imports -------------------------------------------------

from thesis.code.chapter5 import worst_only
from thesis.code.chapter5.llm_client import (
    API_ENDPOINT,
    MODEL_ID,
    REQUEST_PATH_SUFFIX,
    call_gemini,
)
from thesis.code.chapter5.prompt_builder import build_prompt
from thesis.code.chapter5.sanitize import sanitize
from thesis.code.chapter5.seeds import llm_seed, set_seed
from thesis.code.counterexample import CounterexampleSet
from thesis.code.incumbents import get_h_eoh
from thesis.code.splits import load_split

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = REPO_ROOT / "thesis" / "results" / "chapter5_smoke"
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)

CALL_BUDGET = 8
CALL_COUNT = 0
PRICE_INPUT_PER_M = 2.0
PRICE_OUTPUT_PER_M = 12.0


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_key() -> str:
    k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not k:
        raise RuntimeError(
            "No API key in env (set GEMINI_API_KEY or GOOGLE_API_KEY)."
        )
    return k


def _post_raw(
    payload: Dict[str, Any],
    timeout_seconds: int = 250,
) -> Tuple[int, str, float]:
    """Direct HTTP POST against the Gemini OpenAI shim. Returns
    (status, body_text, wall_clock_seconds). Increments the global
    CALL_COUNT. Raises if the budget is exhausted."""
    global CALL_COUNT
    if CALL_COUNT >= CALL_BUDGET:
        raise RuntimeError(
            f"Calibration call budget of {CALL_BUDGET} exhausted"
        )
    CALL_COUNT += 1

    api_key = _resolve_key()
    parsed = urlparse(API_ENDPOINT)
    host = parsed.hostname
    if host is None:
        raise ValueError(f"Invalid endpoint: {API_ENDPOINT}")
    base_path = parsed.path.rstrip("/")
    path = (
        base_path + REQUEST_PATH_SUFFIX
        if base_path
        else REQUEST_PATH_SUFFIX
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    t0 = time.perf_counter()
    conn = http.client.HTTPSConnection(host, timeout=timeout_seconds)
    try:
        conn.request("POST", path, json.dumps(payload), headers)
        res = conn.getresponse()
        body = res.read().decode("utf-8")
        status = res.status
    finally:
        conn.close()
    latency = time.perf_counter() - t0
    return status, body, latency


def _redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Payload as-is; no key lives in payload. Auth is header-only."""
    return payload


def _extract_usage(body_parsed: Any) -> Dict[str, Any]:
    if not isinstance(body_parsed, dict):
        return {}
    usage = body_parsed.get("usage") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def _cost_usd(usage: Dict[str, Any]) -> Optional[float]:
    """Rough cost at $2/M input, $12/M output. The output bucket
    here includes hidden-reasoning tokens: total - prompt."""
    p = usage.get("prompt_tokens")
    t = usage.get("total_tokens")
    if p is None or t is None:
        return None
    out_tokens = max(0, t - p)
    return (
        p * PRICE_INPUT_PER_M / 1_000_000
        + out_tokens * PRICE_OUTPUT_PER_M / 1_000_000
    )


# --- Phase 1: parameter-shape probes -----------------------------------

PHASE1_PROBES = [
    {
        "name": "openai_reasoning_effort_medium",
        "override": {"reasoning_effort": "medium"},
        "placement": "top_level",
    },
    {
        "name": "gemini_thinking_config_toplevel",
        "override": {"thinking_config": {"thinking_budget": 512}},
        "placement": "top_level",
    },
    {
        "name": "gemini_generation_config_thinking",
        "override": {
            "generation_config": {
                "thinking_config": {"thinking_budget": 512}
            }
        },
        "placement": "top_level",
    },
    {
        "name": "openai_extra_body_thinking",
        "override": {
            "extra_body": {
                "thinking_config": {"thinking_budget": 512}
            }
        },
        "placement": "top_level",
    },
]


def phase1(record_paths: list) -> Dict[str, Any]:
    """Run up to 4 minimal-prompt probes, one per candidate shape.
    Returns summary dict: {probe_name: {...}} and logs each."""
    results = {}
    for probe in PHASE1_PROBES:
        print(f"\n[Phase 1] {probe['name']}")
        print(f"  call {CALL_COUNT + 1}/{CALL_BUDGET}")

        payload = {
            "model": MODEL_ID,
            "messages": [
                {"role": "user", "content": "Respond with the word OK, nothing else."}
            ],
            "temperature": 0.0,
            "max_completion_tokens": 32,
        }
        payload.update(probe["override"])

        started_at = _utcnow_iso()
        try:
            status, body, latency = _post_raw(payload)
        except RuntimeError as exc:
            print(f"  BUDGET_EXHAUSTED: {exc}")
            break

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = None

        # Extract error message or usage
        err_msg = None
        usage = {}
        text_out = None
        finish_reason = None
        if status >= 400:
            # extract error
            if isinstance(parsed, dict):
                err = parsed.get("error", {})
                if isinstance(err, dict):
                    err_msg = err.get("message")
            elif isinstance(parsed, list) and parsed:
                for item in parsed:
                    if isinstance(item, dict) and "error" in item:
                        err = item["error"]
                        if isinstance(err, dict):
                            err_msg = err.get("message")
                            break
        else:
            if isinstance(parsed, dict):
                usage = _extract_usage(parsed)
                choices = parsed.get("choices") or []
                if choices:
                    choice = choices[0]
                    text_out = choice.get("message", {}).get("content", "")
                    finish_reason = choice.get("finish_reason")

        finished_at = _utcnow_iso()
        row = {
            "probe_name": probe["name"],
            "payload_sent": _redact_payload(payload),
            "status": status,
            "error_message": err_msg,
            "latency_seconds": latency,
            "usage": usage,
            "text_first_200": (text_out or "")[:200] if text_out else None,
            "finish_reason": finish_reason,
            "reasoning_tokens_inferred": (
                (usage.get("total_tokens") or 0)
                - (usage.get("prompt_tokens") or 0)
                - (usage.get("completion_tokens") or 0)
                if usage.get("total_tokens") is not None
                else None
            ),
            "cost_usd_estimate": _cost_usd(usage),
            "started_at": started_at,
            "finished_at": finished_at,
            "phase": "1",
        }
        results[probe["name"]] = row

        # Write provenance per probe
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = (
            OUTPUT_DIR
            / f"calibration_{len(record_paths):02d}_phase1_{probe['name']}.json"
        )
        out_path.write_text(
            json.dumps(row, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        record_paths.append(out_path)

        print(
            f"  status={status}  latency={latency:.2f}s  "
            f"err={err_msg[:80] if err_msg else 'none'}"
        )
        if status < 400 and usage:
            print(
                f"  usage: prompt={usage.get('prompt_tokens')} "
                f"completion={usage.get('completion_tokens')} "
                f"total={usage.get('total_tokens')} "
                f"reasoning_inferred={row['reasoning_tokens_inferred']}"
            )
            if text_out:
                print(f"  text[:40]={text_out[:40]!r}")

    return results


# --- Phase 2: max_output_tokens sweep ----------------------------------

def _build_chapter5_prompt() -> Tuple[str, CounterexampleSet, Dict[str, Any]]:
    """Reproduce the chapter-5 smoke prompt exactly: worst_only
    selection on committed pool, h_eoh incumbent."""
    pool = CounterexampleSet.from_json(
        POOL_PATH.read_text(encoding="utf-8")
    )
    h_eoh = get_h_eoh()
    ce_set = worst_only(pool, k=4)
    prompt = build_prompt(
        counterexample_set=ce_set,
        incumbent_code=h_eoh["code"],
    )
    return prompt, ce_set, h_eoh


def _score_via_call_gemini(
    prompt: str,
    max_output_tokens: int,
    seed: Optional[int],
) -> Dict[str, Any]:
    """Use the committed call_gemini with overridden max_output_tokens.
    Does not accept thinking-budget; Phase 2 thinking-budget variants
    need _post_raw directly."""
    global CALL_COUNT
    if CALL_COUNT >= CALL_BUDGET:
        raise RuntimeError(
            f"Calibration call budget of {CALL_BUDGET} exhausted"
        )
    CALL_COUNT += 1

    t0 = time.perf_counter()
    result = call_gemini(
        prompt=prompt,
        max_output_tokens=max_output_tokens,
        seed=seed,
    )
    latency = time.perf_counter() - t0
    result["_latency_seconds"] = latency
    return result


def phase2_call(
    max_output_tokens: int,
    thinking_budget: Optional[int],
    seed: int,
    record_idx: int,
    record_paths: list,
) -> Dict[str, Any]:
    """Run the chapter-5 smoke prompt at a given settings combination,
    sanitize the output, and write a provenance record. Does NOT
    score on train_step/train_gate even on sanitization success; the
    calibration is cost/truncation-focused."""
    prompt, ce_set, h_eoh = _build_chapter5_prompt()

    print(
        f"\n[Phase 2] max_output_tokens={max_output_tokens} "
        f"thinking_budget={thinking_budget} "
        f"call {CALL_COUNT + 1}/{CALL_BUDGET}"
    )

    started_at = _utcnow_iso()

    if thinking_budget is None:
        # Standard call via call_gemini
        try:
            resp = _score_via_call_gemini(
                prompt, max_output_tokens, seed=seed
            )
        except Exception as exc:
            return {"error": str(exc), "max_output_tokens": max_output_tokens}
        raw_text = resp["text"]
        usage = resp["raw_response_metadata"]["usage"]
        finish_reason = resp["raw_response_metadata"]["finish_reason"]
        latency = resp["_latency_seconds"]
        status = 200
        system_fingerprint = resp["raw_response_metadata"].get(
            "system_fingerprint"
        )
    else:
        # Direct HTTP with thinking-budget override (Phase 1 found one)
        payload = {
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 1.0,
            "max_completion_tokens": max_output_tokens,
            # shape determined by Phase 1 result; inject here if found
            "thinking_config": {"thinking_budget": thinking_budget},
        }
        status, body, latency = _post_raw(payload)
        if status != 200:
            print(f"  phase2 non-200 status: {status}; body[:200]={body[:200]}")
            return {
                "error": f"status {status}",
                "body": body[:500],
                "max_output_tokens": max_output_tokens,
                "thinking_budget": thinking_budget,
            }
        parsed = json.loads(body)
        choice = parsed["choices"][0]
        raw_text = choice["message"]["content"]
        finish_reason = choice.get("finish_reason")
        usage = _extract_usage(parsed)
        system_fingerprint = parsed.get("system_fingerprint")

    # Sanitize
    split_train_select = load_split("train_select")
    sanity_inst = split_train_select["instances"][0]
    san = sanitize(raw_text, sanity_inst)

    reasoning_tokens = None
    if usage.get("total_tokens") is not None:
        reasoning_tokens = (
            (usage.get("total_tokens") or 0)
            - (usage.get("prompt_tokens") or 0)
            - (usage.get("completion_tokens") or 0)
        )

    row = {
        "phase": "2",
        "max_output_tokens": max_output_tokens,
        "thinking_budget": thinking_budget,
        "status": status,
        "latency_seconds": latency,
        "usage": usage,
        "reasoning_tokens_inferred": reasoning_tokens,
        "finish_reason": finish_reason,
        "cost_usd_estimate": _cost_usd(usage),
        "sanitization_status": san["status"],
        "sanitization_error": san["error"],
        "raw_response_preview": raw_text[-400:] if raw_text else None,
        "raw_response_length_chars": len(raw_text) if raw_text else 0,
        "system_fingerprint": system_fingerprint,
        "started_at": started_at,
        "finished_at": _utcnow_iso(),
    }

    # Write provenance
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    budget_suffix = (
        f"_b{thinking_budget}" if thinking_budget is not None else "_nobudget"
    )
    out_path = (
        OUTPUT_DIR
        / f"calibration_{record_idx:02d}_phase2_m{max_output_tokens}{budget_suffix}.json"
    )
    out_path.write_text(
        json.dumps(row, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    record_paths.append(out_path)

    print(
        f"  status={status}  latency={latency:.2f}s  "
        f"finish={finish_reason}  sanitize={san['status']}"
    )
    if usage:
        print(
            f"  usage: prompt={usage.get('prompt_tokens')} "
            f"completion={usage.get('completion_tokens')} "
            f"total={usage.get('total_tokens')} "
            f"reasoning={reasoning_tokens}"
        )
    if san["error"]:
        print(f"  sanitize_error: {san['error']}")

    return row


# --- Main --------------------------------------------------------------

def main() -> int:
    global CALL_COUNT
    CALL_COUNT = 0
    record_paths: list = []
    print(f"Calibration probe starting. Budget: {CALL_BUDGET} calls.")

    # Phase 1
    phase1_results = phase1(record_paths)
    supported = [
        r for r in phase1_results.values() if r["status"] < 400
    ]
    print(f"\n[Phase 1] supported thinking-budget shapes: {len(supported)}")
    for r in supported:
        print(f"  - {r['probe_name']}")

    # Choose Phase 2 plan based on Phase 1 result
    plan = []
    seed = llm_seed("worst_only", 0, 0)

    if not supported:
        plan = [
            {"max_output_tokens": 8192, "thinking_budget": None},
            {"max_output_tokens": 16384, "thinking_budget": None},
        ]
    else:
        plan = [
            {"max_output_tokens": 8192, "thinking_budget": None},
            {"max_output_tokens": 16384, "thinking_budget": None},
            {"max_output_tokens": 16384, "thinking_budget": 512},
        ]

    remaining = CALL_BUDGET - CALL_COUNT
    if len(plan) > remaining:
        print(f"\n[Phase 2] trimming plan from {len(plan)} to {remaining} calls")
        plan = plan[:remaining]

    phase2_rows = []
    for i, cfg in enumerate(plan):
        try:
            row = phase2_call(
                max_output_tokens=cfg["max_output_tokens"],
                thinking_budget=cfg["thinking_budget"],
                seed=seed,
                record_idx=len(record_paths),
                record_paths=record_paths,
            )
            phase2_rows.append(row)
        except Exception as exc:
            print(f"  ABORT: {exc}")
            break

    # Summary
    print("\n" + "=" * 68)
    print("Calibration summary")
    print("=" * 68)
    print(f"Total calls used: {CALL_COUNT}/{CALL_BUDGET}")
    print()
    print("Phase 1 — parameter-shape probes:")
    for name, r in phase1_results.items():
        short_err = (r.get("error_message") or "")[:80]
        print(
            f"  {name:<40} status={r['status']:>3}  "
            f"err={short_err!r}"
        )
    print()
    print("Phase 2 — max_output_tokens sweep:")
    print(
        f"  {'max_tok':>8}  {'tb':>6}  {'prompt':>7}  "
        f"{'compl':>7}  {'total':>7}  {'reas':>7}  "
        f"{'finish':<10}  {'sanitize':<20}  {'$ est':>8}"
    )
    for r in phase2_rows:
        u = r.get("usage") or {}
        print(
            f"  {r['max_output_tokens']:>8}  "
            f"{str(r['thinking_budget']):>6}  "
            f"{u.get('prompt_tokens'):>7}  "
            f"{u.get('completion_tokens'):>7}  "
            f"{u.get('total_tokens'):>7}  "
            f"{r.get('reasoning_tokens_inferred'):>7}  "
            f"{r.get('finish_reason'):<10}  "
            f"{r.get('sanitization_status'):<20}  "
            f"${r.get('cost_usd_estimate') or 0:.4f}"
        )
    print()
    print("Records written:")
    for p in record_paths:
        print(f"  {p.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
