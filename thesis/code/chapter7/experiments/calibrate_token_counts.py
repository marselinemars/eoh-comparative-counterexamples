"""thesis/code/chapter7/experiments/calibrate_token_counts.py

Chapter 7 calibration probe (``chapter7_design.md`` §18.1).

Purpose. Verify, before the primary batch launches, that every
chapter-7-specific prompt configuration fits inside Gemini 2.5
Pro's 1,048,576-token input ceiling with adequate headroom
(L1 < 800K; L2 < 950K). Surfaces token-count violations as a
``verdict`` field in the artifact; the script does not auto-launch
any subsequent batch under any verdict.

Cells (10 calls total). Per the task spec:

  1. stratified_representative L1 k=1 set_index=0
  2. stratified_representative L1 k=2 set_index=0
  3. stratified_representative L1 k=4 set_index=0
  4. stratified_representative L1 k=8 set_index=0
  5. stratified_representative L2 k=1 set_index=0
  6. stratified_representative L2 k=2 set_index=0
  7. stratified_representative L2 k=4 set_index=0
  8. worst_plus_best        L2 k=4 (ch6 anchor reproduction)
  9. worst_plus_best        L1 k=8 (highest-k L1 verification)
 10. worst_only_at_k1       L2 k=1 (boundary substitution at L2)

Production LLM settings (per ``chapter7_design.md`` §3.5):
``provider="gemini"``, ``reasoning_effort="medium"``,
``max_output_tokens=32768``, ``temperature=1.0``,
3-second inter-call sleep.

Usage::

    python -m thesis.code.chapter7.experiments.calibrate_token_counts

Reads:
  * ``thesis/artifacts/h_eoh_counterexample_pool.json`` (via the
    sets artifact below)
  * ``thesis/artifacts/chapter7_counterexample_sets.json``
    (commit 3ee9b72)
  * ``examples/bp_online/results/pops/population_generation_10.json``
    (h_eoh + reference 62a2846c597e)

Writes:
  * ``thesis/artifacts/chapter7_calibration_probe.json`` —
    per-cell token counts, sanitization status, latency, and the
    overall verdict.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(REPO_ROOT / ".env")

from thesis.code.chapter5.llm_client import call_llm  # noqa: E402
from thesis.code.chapter5.sanitize import sanitize  # noqa: E402
from thesis.code.chapter6.batch_runner import _build_incumbent_module  # noqa: E402
from thesis.code.chapter6.trace_extractor import (  # noqa: E402
    DecisionRecord,
    extract_incumbent_trace,
)
from thesis.code.chapter7.prompt_builder import build_prompt  # noqa: E402
from thesis.code.chapter7.seeds import (  # noqa: E402
    MASTER_SEED_CH7,
    stratified_llm_seed_ch7,
    worst_only_at_k1_llm_seed_ch7,
    worst_plus_best_llm_seed_ch7,
)
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import get_h_eoh, load_final_population  # noqa: E402
from thesis.code.splits import load_split, qualified_instance_id  # noqa: E402

ARTIFACT_DIR = REPO_ROOT / "thesis" / "artifacts"
SETS_PATH = ARTIFACT_DIR / "chapter7_counterexample_sets.json"
PROBE_PATH = ARTIFACT_DIR / "chapter7_calibration_probe.json"

# Gemini 2.5 Pro input ceiling.
GEMINI_INPUT_CEILING = 1_048_576

# Per-task thresholds.
L1_SUB_CEILING = 800_000
L2_SUB_CEILING = 950_000

# Production LLM settings (chapter7_design.md §3.5).
#
# Provider note. The design names "Gemini 2.5 Pro" — the *model* —
# without locking the transport. The chapter 5 / 6 batches used the
# direct Gemini API ("gemini" provider, OpenAI-compatible shim);
# the chapter 7 calibration probe falls back to Vertex AI ("vertex"
# provider, generateContent surface) because the project's
# direct-Gemini prepayment credits are depleted at probe time
# (HTTP 429 RESOURCE_EXHAUSTED across all 10 cells in the first
# attempt; see thesis/artifacts/chapter7_calibration_probe.json's
# "provider_fallback" block for the full transcript). Vertex serves
# the same gemini-2.5-pro model with the same temperature and
# max_output_tokens; "medium" reasoning_effort is mapped to a
# thinkingBudget of 10240 tokens (per
# thesis/code/chapter5/llm_client.py::_vertex_thinking_budget),
# which approximates the OpenAI-shim's medium-effort reasoning
# allocation. Chapter 6's verification probes used the same vertex
# fallback for the same reason
# (thesis/artifacts/chapter6_vertex_dsq_probe*.json, gitignored).
PROVIDER = "vertex"
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 32768
TEMPERATURE = 1.0
INTER_CALL_SLEEP_SECONDS = 3.0
TIMEOUT_SECONDS = 600.0

CHAPTER5_REFERENCE_HASH = "62a2846c597e"


def _cell_definitions() -> List[Dict[str, Any]]:
    return [
        {"cell_id": "calib_strat_L1_k1",
         "strategy": "stratified_representative",
         "level": "L1", "k": 1, "set_index": 0,
         "set_source": "stratified set_index=0 from artifact"},
        {"cell_id": "calib_strat_L1_k2",
         "strategy": "stratified_representative",
         "level": "L1", "k": 2, "set_index": 0,
         "set_source": "stratified set_index=0 from artifact"},
        {"cell_id": "calib_strat_L1_k4",
         "strategy": "stratified_representative",
         "level": "L1", "k": 4, "set_index": 0,
         "set_source": "stratified set_index=0 from artifact"},
        {"cell_id": "calib_strat_L1_k8",
         "strategy": "stratified_representative",
         "level": "L1", "k": 8, "set_index": 0,
         "set_source": "stratified set_index=0 from artifact"},
        {"cell_id": "calib_strat_L2_k1",
         "strategy": "stratified_representative",
         "level": "L2", "k": 1, "set_index": 0,
         "set_source": "stratified set_index=0 from artifact"},
        {"cell_id": "calib_strat_L2_k2",
         "strategy": "stratified_representative",
         "level": "L2", "k": 2, "set_index": 0,
         "set_source": "stratified set_index=0 from artifact"},
        {"cell_id": "calib_strat_L2_k4",
         "strategy": "stratified_representative",
         "level": "L2", "k": 4, "set_index": 0,
         "set_source": "stratified set_index=0 from artifact"},
        {"cell_id": "calib_wpb_L2_k4",
         "strategy": "worst_plus_best",
         "level": "L2", "k": 4, "set_index": 0,
         "set_source": "deterministic worst_plus_best set; ch6 anchor"},
        {"cell_id": "calib_wpb_L1_k8",
         "strategy": "worst_plus_best",
         "level": "L1", "k": 8, "set_index": 0,
         "set_source": "deterministic worst_plus_best set; high-k L1"},
        {"cell_id": "calib_wo1_L2_k1",
         "strategy": "worst_only_at_k1",
         "level": "L2", "k": 1, "set_index": 0,
         "set_source": "deterministic worst_only_at_k1 set; L2 boundary"},
    ]


def _llm_seed_for(strategy: str, k: int, set_index: int, seed_index: int) -> int:
    if strategy == "stratified_representative":
        return stratified_llm_seed_ch7(
            k=k, set_index=set_index, seed_index=seed_index
        )
    if strategy == "worst_plus_best":
        return worst_plus_best_llm_seed_ch7(k=k, seed_index=seed_index)
    if strategy == "worst_only_at_k1":
        return worst_only_at_k1_llm_seed_ch7(seed_index=seed_index)
    raise ValueError(f"Unknown strategy {strategy!r}")


def _load_sets_artifact() -> Dict[str, Any]:
    return json.loads(SETS_PATH.read_text(encoding="utf-8"))


def _build_set_index_lookup(
    artifact: Dict[str, Any],
) -> Dict[str, CounterexampleSet]:
    out: Dict[str, CounterexampleSet] = {}
    for s in artifact["deterministic_sets"]:
        key = f"{s['strategy']}@k={s['k']}@set={s['set_index']:02d}"
        out[key] = CounterexampleSet.from_json(
            json.dumps(s["counterexample_set"])
        )
    for s in artifact["stratified_sets"]:
        key = f"{s['strategy']}@k={s['k']}@set={s['set_index']:02d}"
        out[key] = CounterexampleSet.from_json(
            json.dumps(s["counterexample_set"])
        )
    return out


def _build_instance_lookup() -> Dict[str, Dict[str, Any]]:
    split = load_split("train_select")
    return {
        qualified_instance_id("train_select", inst["instance_id"]): inst
        for inst in split["instances"]
    }


def _resolve_reference_source() -> str:
    pop = load_final_population()
    for m in pop:
        if m["code_hash"] == CHAPTER5_REFERENCE_HASH:
            return m["code"]
    raise RuntimeError(
        f"Reference {CHAPTER5_REFERENCE_HASH!r} not in EoH population"
    )


def _extract_traces(
    counterexample_set: CounterexampleSet,
    incumbent_module: Any,
    instance_lookup: Dict[str, Dict[str, Any]],
) -> List[List[DecisionRecord]]:
    traces: List[List[DecisionRecord]] = []
    for ce in counterexample_set:
        inst = instance_lookup[ce.instance_id]
        traces.append(extract_incumbent_trace(inst, incumbent_module))
    return traces


def _make_call(
    *,
    cell: Dict[str, Any],
    counterexample_set: CounterexampleSet,
    incumbent_source: str,
    reference_source: str,
    incumbent_module: Any,
    instance_lookup: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Run one calibration call and return its per-cell record."""
    level = cell["level"]
    level_int = 1 if level == "L1" else 2
    k = cell["k"]
    strategy = cell["strategy"]
    set_index = cell["set_index"]

    llm_seed = _llm_seed_for(strategy, k, set_index, 0)

    traces: Optional[Sequence[Sequence[DecisionRecord]]] = None
    if level_int == 2:
        traces = _extract_traces(
            counterexample_set, incumbent_module, instance_lookup
        )

    prompt = build_prompt(
        strategy=strategy,
        level=level_int,
        k=k,
        counterexample_set=counterexample_set,
        incumbent_code=incumbent_source,
        reference_code=reference_source,
        traces=traces,
        instance_data_by_id=instance_lookup,
    )
    rendered_prompt_chars = len(prompt)

    sub_ceiling = L1_SUB_CEILING if level_int == 1 else L2_SUB_CEILING

    started_at = time.perf_counter()
    sanitization_error: Optional[str] = None
    finish_reason: Optional[str] = None
    completion_tokens: Optional[int] = None
    prompt_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    sanitize_status: str = "skipped"
    api_error: Optional[str] = None

    try:
        response = call_llm(
            provider=PROVIDER,
            prompt=prompt,
            seed=llm_seed,
            reasoning_effort=REASONING_EFFORT,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=TEMPERATURE,
            timeout_seconds=TIMEOUT_SECONDS,
        )
        latency_seconds = time.perf_counter() - started_at

        raw_meta = response.get("raw_response_metadata") or {}
        usage = raw_meta.get("usage") if isinstance(raw_meta, dict) else None
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            # Two metadata shapes — gemini-shim:
            #   completion_tokens_details.reasoning_tokens
            # vertex (per llm_client._call_vertex normalization):
            #   thoughts_token_count
            details = usage.get("completion_tokens_details")
            if isinstance(details, dict):
                reasoning_tokens = details.get("reasoning_tokens")
            if reasoning_tokens is None:
                reasoning_tokens = usage.get("thoughts_token_count")
        finish_reason = (
            raw_meta.get("finish_reason") if isinstance(raw_meta, dict) else None
        )

        text = response.get("text", "") or ""
        sanity_inst = next(iter(instance_lookup.values()))
        try:
            sanitize_result = sanitize(text, sanity_inst)
            sanitize_status = sanitize_result.get("status", "unknown")
        except Exception as exc:  # noqa: BLE001
            sanitize_status = "error_during_sanitize"
            sanitization_error = repr(exc)

    except Exception as exc:  # noqa: BLE001
        latency_seconds = time.perf_counter() - started_at
        api_error = repr(exc)
        sanitize_status = "skipped_due_to_api_error"

    chars_per_token: Optional[float] = None
    headroom_tokens: Optional[int] = None
    headroom_pct: Optional[float] = None
    exceeds_threshold: Optional[bool] = None
    if prompt_tokens is not None and prompt_tokens > 0:
        chars_per_token = rendered_prompt_chars / prompt_tokens
        headroom_tokens = GEMINI_INPUT_CEILING - prompt_tokens
        headroom_pct = headroom_tokens / GEMINI_INPUT_CEILING
        exceeds_threshold = prompt_tokens > sub_ceiling

    record: Dict[str, Any] = {
        "cell_id": cell["cell_id"],
        "strategy": strategy,
        "level": level,
        "k": k,
        "set_index": set_index,
        "set_source": cell["set_source"],
        "provider": PROVIDER,
        "instance_ids_anonymized": [
            f"instance_{i + 1:02d}"
            for i in range(len(counterexample_set))
        ],
        "instance_ids_underlying": [
            ce.instance_id for ce in counterexample_set
        ],
        "llm_seed_requested": llm_seed,
        "rendered_prompt_chars": rendered_prompt_chars,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "chars_per_token": chars_per_token,
        "sanitize_status": sanitize_status,
        "sanitization_error": sanitization_error,
        "finish_reason": finish_reason,
        "latency_seconds": latency_seconds,
        "headroom_tokens": headroom_tokens,
        "headroom_pct": headroom_pct,
        "exceeds_threshold": exceeds_threshold,
        "sub_ceiling": sub_ceiling,
        "api_error": api_error,
    }
    return record


def _summarize_verdict(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    violators: List[str] = []
    sanitization_failures: List[str] = []
    api_errors: List[str] = []
    for r in records:
        if r.get("api_error"):
            api_errors.append(r["cell_id"])
        if r.get("exceeds_threshold"):
            violators.append(r["cell_id"])
        status = r.get("sanitize_status")
        if status not in ("ok", "skipped", "skipped_due_to_api_error"):
            sanitization_failures.append(f"{r['cell_id']}({status})")
    if api_errors:
        verdict = (
            f"API errors at cells: {api_errors}; calibration "
            "incomplete — design-lead review required"
        )
    elif violators:
        verdict = (
            f"cell(s) {violators} exceed thresholds "
            f"(L1 sub-ceiling {L1_SUB_CEILING}, L2 sub-ceiling "
            f"{L2_SUB_CEILING}); re-derivation needed before "
            "primary batch — design-lead review required"
        )
    else:
        verdict = (
            "all cells within thresholds; primary batch may "
            "proceed pending design-lead review"
        )
    return {
        "verdict": verdict,
        "violators": violators,
        "sanitization_failures": sanitization_failures,
        "api_errors": api_errors,
    }


def main() -> int:
    artifact = _load_sets_artifact()
    set_lookup = _build_set_index_lookup(artifact)
    instance_lookup = _build_instance_lookup()
    h_eoh = get_h_eoh()
    if h_eoh["code_hash"] != "8ca83676ae76":
        raise RuntimeError(
            f"Unexpected h_eoh hash {h_eoh['code_hash']!r}"
        )
    incumbent_module = _build_incumbent_module(h_eoh)
    incumbent_source = h_eoh["code"]
    reference_source = _resolve_reference_source()

    cells = _cell_definitions()
    records: List[Dict[str, Any]] = []
    last_call_end: Optional[float] = None
    for i, cell in enumerate(cells):
        if last_call_end is not None and INTER_CALL_SLEEP_SECONDS > 0:
            elapsed = time.perf_counter() - last_call_end
            rem = INTER_CALL_SLEEP_SECONDS - elapsed
            if rem > 0:
                time.sleep(rem)

        key = (
            f"{cell['strategy']}@k={cell['k']}@set={cell['set_index']:02d}"
        )
        ce_set = set_lookup.get(key)
        if ce_set is None:
            raise RuntimeError(
                f"Set {key!r} not found in artifact lookup; available "
                f"keys: {sorted(set_lookup.keys())[:5]}..."
            )

        print(
            f"[{i + 1}/{len(cells)}] {cell['cell_id']} "
            f"(k={cell['k']}, level={cell['level']}, strategy="
            f"{cell['strategy']})...",
            file=sys.stderr,
            flush=True,
        )
        try:
            record = _make_call(
                cell=cell,
                counterexample_set=ce_set,
                incumbent_source=incumbent_source,
                reference_source=reference_source,
                incumbent_module=incumbent_module,
                instance_lookup=instance_lookup,
            )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            record = {
                "cell_id": cell["cell_id"],
                "strategy": cell["strategy"],
                "level": cell["level"],
                "k": cell["k"],
                "set_index": cell["set_index"],
                "set_source": cell["set_source"],
                "rendered_prompt_chars": None,
                "prompt_tokens": None,
                "completion_tokens": None,
                "reasoning_tokens": None,
                "chars_per_token": None,
                "sanitize_status": "skipped_due_to_call_error",
                "sanitization_error": None,
                "finish_reason": None,
                "latency_seconds": None,
                "headroom_tokens": None,
                "headroom_pct": None,
                "exceeds_threshold": None,
                "sub_ceiling": (
                    L1_SUB_CEILING if cell["level"] == "L1" else L2_SUB_CEILING
                ),
                "api_error": repr(exc),
            }
        last_call_end = time.perf_counter()
        records.append(record)
        print(
            f"   prompt_tokens={record.get('prompt_tokens')} "
            f"chars={record.get('rendered_prompt_chars')} "
            f"sanitize={record.get('sanitize_status')} "
            f"finish={record.get('finish_reason')}",
            file=sys.stderr,
            flush=True,
        )

    verdict = _summarize_verdict(records)

    artifact_out = {
        "schema_version": 1,
        "chapter": "chapter7",
        "design_doc_section": "§18.1",
        "master_seed": MASTER_SEED_CH7,
        "thresholds": {
            "L1_sub_ceiling_tokens": L1_SUB_CEILING,
            "L2_sub_ceiling_tokens": L2_SUB_CEILING,
            "gemini_input_ceiling_tokens": GEMINI_INPUT_CEILING,
        },
        "llm_settings": {
            "provider": PROVIDER,
            "reasoning_effort": REASONING_EFFORT,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "temperature": TEMPERATURE,
            "inter_call_sleep_seconds": INTER_CALL_SLEEP_SECONDS,
            "timeout_seconds": TIMEOUT_SECONDS,
        },
        "provider_fallback": {
            "designated_provider": "gemini (direct API, OpenAI-compatible shim)",
            "actual_provider": PROVIDER,
            "fallback_reason": (
                "The direct Gemini API ('gemini' provider) returned "
                "HTTP 429 RESOURCE_EXHAUSTED ('Your prepayment credits "
                "are depleted') across all 10 cells in the first probe "
                "attempt. The Vertex AI 'vertex' provider serves the "
                "same gemini-2.5-pro model with the same temperature "
                "and max_output_tokens; 'medium' reasoning_effort is "
                "mapped to thinkingBudget=10240 tokens per "
                "thesis/code/chapter5/llm_client.py::"
                "_vertex_thinking_budget. Chapter 6 verification "
                "probes used the same fallback for the same reason."
            ),
        },
        "fixed_inputs": {
            "incumbent_code_hash": h_eoh["code_hash"],
            "reference_code_hash": CHAPTER5_REFERENCE_HASH,
            "pool_artifact": str(
                (REPO_ROOT / "thesis" / "artifacts"
                 / "h_eoh_counterexample_pool.json")
                .relative_to(REPO_ROOT).as_posix()
            ),
            "sets_artifact": str(
                SETS_PATH.relative_to(REPO_ROOT).as_posix()
            ),
        },
        "verdict": verdict["verdict"],
        "violators": verdict["violators"],
        "sanitization_failures": verdict["sanitization_failures"],
        "api_errors": verdict["api_errors"],
        "cells": records,
    }
    payload = json.dumps(artifact_out, indent=2, sort_keys=True)
    PROBE_PATH.write_text(payload, encoding="utf-8")
    artifact_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    print(file=sys.stderr)
    print(f"Verdict: {verdict['verdict']}", file=sys.stderr)
    print(
        f"Wrote {PROBE_PATH.relative_to(REPO_ROOT).as_posix()} "
        f"(sha256[:12] = {artifact_hash})",
        file=sys.stderr,
    )
    return 0 if not verdict["violators"] and not verdict["api_errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
