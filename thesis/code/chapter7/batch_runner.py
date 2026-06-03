"""thesis/code/chapter7/batch_runner.py

Chapter 7 per-call worker. Mirrors
``thesis.code.chapter6.batch_runner._run_chapter6_single_proposal``
but threads chapter-7-specific seed namespaces, the ch7 prompt
builder, and the cardinality axis through the call.

The function writes one provenance JSON per call, atomically
(via a tempfile + os.replace pattern), so a process crash after
the write but before the loop advances leaves a complete record
on disk and the resumable driver in
``experiments/primary_batch.py`` correctly counts that record as
done.

Filename pattern (the resume contract):
    {cell_id}_set{set_index:03d}_seed{seed_index:03d}.json
"""
from __future__ import annotations

import json
import os
import socket
import time
import types
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from thesis.code.chapter5 import STRATEGIES
from thesis.code.chapter5.llm_client import call_llm as _ch5_call_llm
from thesis.code.chapter5.runner import (
    _compute_metrics,
    _sanitization_record,
    _score_baseline_on_split,
    _score_heuristic_on_split,
)
from thesis.code.chapter5.sanitize import sanitize
from thesis.code.chapter6.batch_runner import _build_incumbent_module
from thesis.code.chapter6.trace_extractor import (
    DecisionRecord,
    extract_incumbent_trace,
)
from thesis.code.chapter7.prompt_builder import build_prompt
from thesis.code.chapter7.seeds import (
    MASTER_SEED_CH7,
    stratified_llm_seed_ch7,
    stratified_set_seed_ch7,
    worst_only_at_k1_llm_seed_ch7,
    worst_plus_best_llm_seed_ch7,
)
from thesis.code.chapter7.strategies import worst_only_at_k1
from thesis.code.counterexample import CounterexampleSet
from thesis.code.score_cache import ScoreCache, code_hash
from thesis.code.splits import load_split

# §3.5 production settings.
PROVIDER_DEFAULT = "vertex"
REASONING_EFFORT_DEFAULT = "medium"
MAX_OUTPUT_TOKENS_DEFAULT = 32768
TEMPERATURE_DEFAULT = 1.0
TIMEOUT_SECONDS_DEFAULT = 600.0


# --- transient retry policy --------------------------------------------

TRANSIENT_RETRY_BACKOFFS_S = (30.0, 60.0, 120.0, 240.0)
PERSISTENT_429_FRAGMENTS = (
    "prepayment credits are depleted",
    "billing account",
)


def _is_persistent_credits_429(msg: str) -> bool:
    msg_lower = msg.lower()
    return any(frag in msg_lower for frag in PERSISTENT_429_FRAGMENTS)


def _is_transient_429_or_5xx(msg: str) -> bool:
    msg_lower = msg.lower()
    if "resource_exhausted" in msg_lower or "429" in msg_lower:
        return True
    return any(s in msg for s in (" 500", " 502", " 503", " 504"))


class PersistentCreditsExhausted(RuntimeError):
    """Raised when 429 + credits-depletion message persists across all
    backoff attempts. Driver catches this and exits with non-zero."""


# --- llm seed lookup ---------------------------------------------------


def _llm_seed_for(
    strategy: str, k: int, set_index: int, seed_index: int
) -> int:
    if strategy == "stratified_representative":
        return stratified_llm_seed_ch7(
            k=k, set_index=set_index, seed_index=seed_index
        )
    if strategy == "worst_plus_best":
        return worst_plus_best_llm_seed_ch7(k=k, seed_index=seed_index)
    if strategy == "worst_only_at_k1":
        return worst_only_at_k1_llm_seed_ch7(seed_index=seed_index)
    raise ValueError(f"Unknown strategy {strategy!r}")


def _set_seed_for(strategy: str, k: int, set_index: int) -> Optional[int]:
    if strategy == "stratified_representative":
        return stratified_set_seed_ch7(k=k, set_index=set_index)
    return None  # deterministic strategies — no set seed


# --- atomic write helper -----------------------------------------------


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, indent=2, sort_keys=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


# --- record filename ---------------------------------------------------


def record_filename(cell_id: str, set_index: int, seed_index: int) -> str:
    return f"{cell_id}_set{set_index:03d}_seed{seed_index:03d}.json"


# --- LLM call with retry ----------------------------------------------


def _llm_call_with_retry(
    *,
    prompt: str,
    seed: int,
    provider: str,
    reasoning_effort: str,
    max_output_tokens: int,
    temperature: float,
    timeout_seconds: float,
    log_prefix: str,
) -> Dict[str, Any]:
    """Call call_llm; on 429/5xx retry per TRANSIENT_RETRY_BACKOFFS_S.

    Raises PersistentCreditsExhausted if every attempt returns a
    persistent-credits-depleted 429. Raises the last exception
    otherwise.
    """
    last_exc: Optional[BaseException] = None
    consecutive_persistent = 0
    for attempt_idx in range(len(TRANSIENT_RETRY_BACKOFFS_S) + 1):
        try:
            return call_llm_inner(
                prompt=prompt,
                seed=seed,
                provider=provider,
                reasoning_effort=reasoning_effort,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
            )
        except (
            socket.gaierror,
            TimeoutError,
            ConnectionError,
        ) as exc:
            last_exc = exc
            msg = f"{type(exc).__name__}: {exc}"
            if attempt_idx < len(TRANSIENT_RETRY_BACKOFFS_S):
                back = TRANSIENT_RETRY_BACKOFFS_S[attempt_idx]
                print(
                    f"  {log_prefix} network error — backoff {back}s "
                    f"(attempt {attempt_idx + 1}): {msg[:200]}",
                    flush=True,
                )
                time.sleep(back)
                continue
            raise
        except RuntimeError as exc:
            last_exc = exc
            msg = str(exc)
            persistent = _is_persistent_credits_429(msg)
            transient = _is_transient_429_or_5xx(msg)
            if persistent:
                consecutive_persistent += 1
            if not (persistent or transient):
                raise
            if attempt_idx < len(TRANSIENT_RETRY_BACKOFFS_S):
                back = TRANSIENT_RETRY_BACKOFFS_S[attempt_idx]
                tag = "PERSISTENT-429" if persistent else "TRANSIENT-429/5xx"
                print(
                    f"  {log_prefix} {tag} — backoff {back}s "
                    f"(attempt {attempt_idx + 1}): {msg[:200]}",
                    flush=True,
                )
                time.sleep(back)
                continue
            if consecutive_persistent >= len(TRANSIENT_RETRY_BACKOFFS_S) + 1:
                raise PersistentCreditsExhausted(msg) from exc
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable")


def call_llm_inner(**kwargs):
    """Thin wrapper so tests can monkey-patch _ch5_call_llm easily."""
    return _ch5_call_llm(**kwargs)


# --- per-proposal record builder --------------------------------------


def _build_record(
    *,
    cell_id: str,
    strategy: str,
    level: int,
    k: int,
    set_index: int,
    seed_index: int,
    set_seed: Optional[int],
    llm_seed: int,
    counterexample_set: CounterexampleSet,
    incumbent_hash: str,
    reference_hash: str,
    prompt: str,
    rendered_prompt_chars: int,
    llm_response: Optional[Dict[str, Any]],
    sanitization: Optional[Dict[str, Any]],
    scoring: Optional[Dict[str, Any]],
    proposal_hash: Optional[str],
    api_error: Optional[str],
    started_at: str,
    finished_at: str,
    trace_summary: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    if llm_response is not None:
        llm_meta = {
            "model": llm_response.get("model"),
            "temperature": llm_response.get("temperature"),
            "max_output_tokens": llm_response.get("max_output_tokens"),
            "reasoning_effort": llm_response.get("reasoning_effort"),
            "seed_requested": llm_response.get("seed_requested"),
            "seed_honored": llm_response.get("seed_honored"),
            "raw_response_metadata": llm_response.get("raw_response_metadata"),
            "provider": llm_response.get("provider"),
        }
        raw_response = llm_response.get("text", "") or ""
    else:
        llm_meta = None
        raw_response = ""
    return {
        "chapter": "chapter7",
        "cell_id": cell_id,
        "strategy_name": strategy,
        "level": level,
        "k": k,
        "set_index": set_index,
        "seed_index": seed_index,
        "set_seed": set_seed,
        "llm_seed": llm_seed,
        "master_seed": MASTER_SEED_CH7,
        "incumbent_hash": incumbent_hash,
        "reference_hash": reference_hash,
        "counterexample_set": json.loads(counterexample_set.to_json()),
        "rendered_prompt_chars": rendered_prompt_chars,
        "prompt": prompt,
        "raw_response": raw_response,
        "llm_metadata": llm_meta,
        "sanitization": sanitization or {"status": "skipped_due_to_api_error"},
        "scoring": scoring,
        "proposal_hash": proposal_hash,
        "api_error": api_error,
        "trace_summary": trace_summary,
        "timestamps": {"started_at": started_at, "finished_at": finished_at},
    }


# --- per-proposal worker ----------------------------------------------


def run_chapter7_single_proposal(
    *,
    cell_id: str,
    strategy: str,
    level: int,
    k: int,
    set_index: int,
    seed_index: int,
    counterexample_set: CounterexampleSet,
    incumbent_heuristic: Dict[str, Any],
    incumbent_module: types.ModuleType,
    reference_source: str,
    instance_lookup: Dict[str, Dict[str, Any]],
    output_dir: Path,
    provider: str = PROVIDER_DEFAULT,
    reasoning_effort: str = REASONING_EFFORT_DEFAULT,
    max_output_tokens: int = MAX_OUTPUT_TOKENS_DEFAULT,
    temperature: float = TEMPERATURE_DEFAULT,
    timeout_seconds: float = TIMEOUT_SECONDS_DEFAULT,
    do_scoring: bool = True,
) -> Dict[str, Any]:
    """Execute one chapter-7 proposal end-to-end and write a record."""
    started_at = datetime.now(timezone.utc).isoformat()
    incumbent_hash = incumbent_heuristic["code_hash"]
    incumbent_source = incumbent_heuristic["code"]

    # --- seeds ---
    set_seed = _set_seed_for(strategy, k, set_index)
    llm_seed = _llm_seed_for(strategy, k, set_index, seed_index)

    # --- traces (L2 only) ---
    traces_for_record: Optional[List[Dict[str, Any]]] = None
    traces: Optional[Sequence[Sequence[DecisionRecord]]] = None
    if level == 2:
        trace_lists: List[List[DecisionRecord]] = []
        for ce in counterexample_set:
            inst = instance_lookup[ce.instance_id]
            trace_lists.append(extract_incumbent_trace(inst, incumbent_module))
        traces = trace_lists
        traces_for_record = [
            {"trace_row_count": len(t)} for t in trace_lists
        ]

    # --- prompt rendering ---
    prompt = build_prompt(
        strategy=strategy,
        level=level,
        k=k,
        counterexample_set=counterexample_set,
        incumbent_code=incumbent_source,
        reference_code=reference_source,
        traces=traces,
        instance_data_by_id=instance_lookup,
    )
    rendered_prompt_chars = len(prompt)

    # --- LLM call ---
    log_prefix = (
        f"[{cell_id} set={set_index:03d} seed={seed_index:03d}]"
    )
    llm_response: Optional[Dict[str, Any]] = None
    api_error: Optional[str] = None
    try:
        llm_response = _llm_call_with_retry(
            prompt=prompt,
            seed=llm_seed,
            provider=provider,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            log_prefix=log_prefix,
        )
    except PersistentCreditsExhausted:
        # Bubble up to the driver.
        raise
    except Exception as exc:  # noqa: BLE001
        api_error = repr(exc)
        print(
            f"  {log_prefix} EXHAUSTED retries: {api_error[:300]}",
            flush=True,
        )

    # --- sanitize ---
    sanitization_record: Optional[Dict[str, Any]] = None
    sanitize_result: Optional[Dict[str, Any]] = None
    proposal_hash: Optional[str] = None
    scoring_record: Optional[Dict[str, Any]] = None

    if llm_response is not None:
        text = llm_response.get("text", "") or ""
        sanity_inst = next(iter(instance_lookup.values()))
        try:
            sanitize_result = sanitize(text, sanity_inst)
            sanitization_record = _sanitization_record(sanitize_result)
        except Exception as exc:  # noqa: BLE001
            sanitization_record = {
                "status": "error_during_sanitize",
                "error": repr(exc),
            }

    # --- scoring (only if sanitize ok) ---
    if (
        do_scoring
        and sanitize_result is not None
        and sanitize_result.get("status") == "ok"
    ):
        try:
            cache = ScoreCache()
            proposal_code = sanitize_result["cleaned_code"]
            proposal_hash = code_hash(proposal_code)
            baseline_step = _score_baseline_on_split(
                incumbent_module, incumbent_hash, "train_step", cache,
            )
            baseline_gate = _score_baseline_on_split(
                incumbent_module, incumbent_hash, "train_gate", cache,
            )
            proposal_step = _score_heuristic_on_split(
                sanitize_result["score_fn"], proposal_code, proposal_hash,
                "train_step", cache,
            )
            proposal_gate = _score_heuristic_on_split(
                sanitize_result["score_fn"], proposal_code, proposal_hash,
                "train_gate", cache,
            )
            cache.save()
            scoring_record = _compute_metrics(
                baseline_step, proposal_step, baseline_gate, proposal_gate
            )
        except Exception as exc:  # noqa: BLE001
            scoring_record = {"status": "error_during_scoring", "error": repr(exc)}

    finished_at = datetime.now(timezone.utc).isoformat()

    reference_hashes = {c.reference_hash for c in counterexample_set}
    reference_hash = next(iter(reference_hashes)) if reference_hashes else ""

    record = _build_record(
        cell_id=cell_id,
        strategy=strategy,
        level=level,
        k=k,
        set_index=set_index,
        seed_index=seed_index,
        set_seed=set_seed,
        llm_seed=llm_seed,
        counterexample_set=counterexample_set,
        incumbent_hash=incumbent_hash,
        reference_hash=reference_hash,
        prompt=prompt,
        rendered_prompt_chars=rendered_prompt_chars,
        llm_response=llm_response,
        sanitization=sanitization_record,
        scoring=scoring_record,
        proposal_hash=proposal_hash,
        api_error=api_error,
        started_at=started_at,
        finished_at=finished_at,
        trace_summary=traces_for_record,
    )
    out_path = output_dir / record_filename(cell_id, set_index, seed_index)
    _atomic_write_json(out_path, record)
    record["_written_to"] = str(out_path)
    return record
