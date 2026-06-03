"""
Eighth and final calibration call. Tests reasoning_effort="low"
with max_output_tokens=8192 on the chapter-5 smoke prompt.

Phase 1 established reasoning_effort is the only supported
thinking-budget control parameter. Call 7 was wasted on an
unsupported `thinking_config` shape (bug in the first calibration
script). This script sends one direct-HTTP request with
reasoning_effort="low" and writes provenance.
"""
from __future__ import annotations

import http.client
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from thesis.code.chapter5 import worst_only
from thesis.code.chapter5.llm_client import (
    API_ENDPOINT,
    MODEL_ID,
    REQUEST_PATH_SUFFIX,
)
from thesis.code.chapter5.prompt_builder import build_prompt
from thesis.code.chapter5.sanitize import sanitize
from thesis.code.counterexample import CounterexampleSet
from thesis.code.incumbents import get_h_eoh
from thesis.code.splits import load_split

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = REPO_ROOT / "thesis" / "results" / "chapter5_smoke"
POOL_PATH = REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"


def main() -> int:
    pool = CounterexampleSet.from_json(POOL_PATH.read_text(encoding="utf-8"))
    h_eoh = get_h_eoh()
    ce_set = worst_only(pool, k=4)
    prompt = build_prompt(
        counterexample_set=ce_set, incumbent_code=h_eoh["code"]
    )

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("No API key in env")

    parsed = urlparse(API_ENDPOINT)
    host = parsed.hostname
    path = parsed.path.rstrip("/") + REQUEST_PATH_SUFFIX

    payload = {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 1.0,
        "max_completion_tokens": 8192,
        "reasoning_effort": "low",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print("[Call 8/8] max_output_tokens=8192, reasoning_effort=low")
    t0 = time.perf_counter()
    conn = http.client.HTTPSConnection(host, timeout=250)
    try:
        conn.request("POST", path, json.dumps(payload), headers)
        res = conn.getresponse()
        body = res.read().decode("utf-8")
        status = res.status
    finally:
        conn.close()
    latency = time.perf_counter() - t0

    if status != 200:
        print(f"  status={status}, body[:400]={body[:400]}")
        out_path = OUTPUT_DIR / "calibration_07_phase2_m8192_reasoning_low_ERROR.json"
        out_path.write_text(
            json.dumps(
                {"status": status, "body": body[:2000], "latency": latency},
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"  wrote {out_path.name}")
        return 1

    parsed_body = json.loads(body)
    choice = parsed_body["choices"][0]
    raw_text = choice["message"]["content"]
    finish_reason = choice.get("finish_reason")
    usage = parsed_body.get("usage", {})
    reasoning_tokens = (
        usage.get("total_tokens", 0)
        - usage.get("prompt_tokens", 0)
        - usage.get("completion_tokens", 0)
    )

    split_ts = load_split("train_select")
    san = sanitize(raw_text, split_ts["instances"][0])

    cost = (
        usage.get("prompt_tokens", 0) * 2.0 / 1_000_000
        + (usage.get("total_tokens", 0) - usage.get("prompt_tokens", 0))
        * 12.0 / 1_000_000
    )

    row = {
        "phase": "2b",
        "max_output_tokens": 8192,
        "reasoning_effort": "low",
        "thinking_budget": None,
        "status": status,
        "latency_seconds": latency,
        "usage": usage,
        "reasoning_tokens_inferred": reasoning_tokens,
        "finish_reason": finish_reason,
        "cost_usd_estimate": cost,
        "sanitization_status": san["status"],
        "sanitization_error": san["error"],
        "raw_response_length_chars": len(raw_text),
        "raw_response_preview": raw_text[-600:],
        "cleaned_code_if_ok": san.get("cleaned_code") if san["status"] == "ok" else None,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "calibration_07_phase2_m8192_reasoning_low.json"
    out_path.write_text(
        json.dumps(row, indent=2, sort_keys=True), encoding="utf-8"
    )

    print(f"  status={status} latency={latency:.2f}s finish={finish_reason}")
    print(
        f"  usage: prompt={usage.get('prompt_tokens')} "
        f"completion={usage.get('completion_tokens')} "
        f"total={usage.get('total_tokens')} reasoning={reasoning_tokens}"
    )
    print(f"  sanitize={san['status']}  cost=${cost:.4f}")
    if san["status"] == "ok":
        print(f"  cleaned_code (first 400 chars):")
        print(san["cleaned_code"][:400])
    elif san["error"]:
        print(f"  error: {san['error']}")
    print(f"  wrote {out_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
