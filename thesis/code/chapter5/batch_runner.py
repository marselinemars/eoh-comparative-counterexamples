"""
thesis/code/chapter5/batch_runner.py

Primary batch driver for chapter 5. Iterates strategies in order
and, for each, produces 60 proposals per the per-strategy
determinism table (§5.7 of chapter5_design.md):

    deterministic strategies: set_index=0, seed_index in 0..59
    stochastic strategies:    set_index in 0..19, seed_index in 0..2

Resume-friendly: if a per-strategy provenance JSON already exists
under ``output_dir``, the call is skipped. Runs sequentially with
an inter-call sleep; KeyboardInterrupt exits cleanly (re-run to
resume).

No LLM calls happen in this module's tests — they parametrize on
a fake ``run_single_proposal`` to verify dispatch semantics.
"""
from __future__ import annotations

import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from thesis.code.chapter5 import (
    DETERMINISTIC_STRATEGY_NAMES,
    STOCHASTIC_STRATEGY_NAMES,
)
from thesis.code.chapter5.runner import run_single_proposal
from thesis.code.counterexample import CounterexampleSet

# Full default order across the six strategies, mirroring §5.7.
# Drivers may pass `strategies=` to run a subset or reorder.
DEFAULT_STRATEGIES: List[str] = [
    "worst_only",
    "worst_plus_best",
    "most_discriminative",
    "uniform_random",
    "random_discriminative",
    "stratified_representative",
]

# Per-strategy (set_count, seeds_per_set) derived from §5.7.
_DET_ALLOCATION = (1, 60)
_STOCH_ALLOCATION = (20, 3)

# Transient-error retry policy. Any call that raises one of these
# is retried up to TRANSIENT_MAX_RETRIES times with
# TRANSIENT_RETRY_SLEEP_SECONDS between attempts. A 10-hour batch
# on a home-network machine sees DNS flakes and socket read
# timeouts with some regularity; a hard crash on each one is worse
# than a 30-second retry. Exposed so validation_batch can use the
# same policy without duplicating the constants.
TRANSIENT_EXCEPTIONS: tuple = (
    socket.gaierror,
    TimeoutError,
    ConnectionError,
)
TRANSIENT_MAX_RETRIES = 5
TRANSIENT_RETRY_SLEEP_SECONDS = 30.0


def is_transient_runtime_error(exc: BaseException) -> bool:
    """RuntimeError from call_llm wraps HTTP 5xx and some 429s;
    treat those as transient too. Message-based sniff — fragile
    but narrow."""
    if not isinstance(exc, RuntimeError):
        return False
    msg = str(exc).lower()
    return (
        "returned 5" in msg
        or "rate limit" in msg
        or "429" in msg
    )


def call_with_transient_retry(fn: Callable, /, **kwargs) -> Any:
    """Call `fn(**kwargs)` with the transient-error retry policy.
    Raises the final exception if retries are exhausted."""
    last_exc: Optional[BaseException] = None
    for _ in range(TRANSIENT_MAX_RETRIES):
        try:
            return fn(**kwargs)
        except TRANSIENT_EXCEPTIONS as exc:
            last_exc = exc
        except RuntimeError as exc:
            if not is_transient_runtime_error(exc):
                raise
            last_exc = exc
        time.sleep(TRANSIENT_RETRY_SLEEP_SECONDS)
    assert last_exc is not None
    raise last_exc


# Back-compat aliases used internally below. Keep the _-prefixed
# names for the existing body.
_TRANSIENT_EXCEPTIONS = TRANSIENT_EXCEPTIONS
_MAX_RETRIES = TRANSIENT_MAX_RETRIES
_RETRY_SLEEP_SECONDS = TRANSIENT_RETRY_SLEEP_SECONDS
_is_transient_runtime_error = is_transient_runtime_error


def _allocation_for(strategy_name: str) -> tuple[int, int]:
    if strategy_name in DETERMINISTIC_STRATEGY_NAMES:
        return _DET_ALLOCATION
    if strategy_name in STOCHASTIC_STRATEGY_NAMES:
        return _STOCH_ALLOCATION
    raise ValueError(
        f"Strategy {strategy_name!r} is neither deterministic nor "
        "stochastic; cannot allocate (set, seed) matrix."
    )


def _existing_record_path(
    output_dir: Path, strategy_name: str, set_index: int, seed_index: int
) -> Path:
    return (
        output_dir
        / f"{strategy_name}_{set_index}_{seed_index}.json"
    )


def run_primary_batch(
    pool: CounterexampleSet,
    incumbent_heuristic: Dict[str, Any],
    output_dir: Path,
    *,
    provider: str = "gemini",
    reasoning_effort: Optional[str] = None,
    max_output_tokens: Optional[int] = None,
    temperature: float = 1.0,
    inter_call_sleep_seconds: float = 3.0,
    strategies: Optional[Sequence[str]] = None,
    summary_filename: str = "primary_batch_summary.json",
    progress_filename: str = "progress.json",
    resume: bool = True,
    k: int = 4,
    _run_single_proposal: Callable[..., Dict[str, Any]] = (
        run_single_proposal
    ),
) -> Dict[str, Any]:
    """Run the chapter-5 primary batch.

    Per-strategy iteration follows §5.7 of the design doc. Calls
    `_run_single_proposal` once per (strategy, set_index, seed_index)
    triple; the injected default is the production run_single_proposal
    but tests can pass a fake.

    Returns the summary dict (also written to disk).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    targets: Sequence[str] = (
        list(strategies) if strategies is not None
        else list(DEFAULT_STRATEGIES)
    )

    settings = {
        "provider": provider,
        "reasoning_effort": reasoning_effort,
        "max_output_tokens": max_output_tokens,
        "temperature": temperature,
        "inter_call_sleep_seconds": inter_call_sleep_seconds,
        "strategies": list(targets),
        "k": k,
        "resume": resume,
    }

    started_at = datetime.now(timezone.utc).isoformat()
    per_call_records: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    stopped = False
    stop_reason: Optional[str] = None
    last_call_end: Optional[float] = None
    progress_path = output_dir / progress_filename

    def _write_progress() -> None:
        progress_path.write_text(
            json.dumps(
                {
                    "settings": settings,
                    "started_at": started_at,
                    "last_updated_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "n_calls_this_run": len(per_call_records),
                    "n_skipped_existing": len(skipped),
                    "last_records": per_call_records[-5:],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    # Initial progress stamp so the file always exists once the
    # batch has begun — prevents false-positive "progress missing"
    # during the first inter-call window.
    _write_progress()

    try:
        for strategy_name in targets:
            n_sets, n_seeds = _allocation_for(strategy_name)
            for set_index in range(n_sets):
                for seed_index in range(n_seeds):
                    existing = _existing_record_path(
                        output_dir, strategy_name, set_index, seed_index
                    )
                    if resume and existing.exists():
                        skipped.append({
                            "strategy_name": strategy_name,
                            "set_index": set_index,
                            "seed_index": seed_index,
                            "reason": "existing_record",
                            "path": existing.name,
                        })
                        continue

                    if last_call_end is not None:
                        elapsed = time.perf_counter() - last_call_end
                        rem = inter_call_sleep_seconds - elapsed
                        if rem > 0:
                            time.sleep(rem)

                    record = None
                    last_exc: Optional[BaseException] = None
                    for attempt in range(_MAX_RETRIES):
                        try:
                            record = _run_single_proposal(
                                strategy_name=strategy_name,
                                set_index=set_index,
                                seed_index=seed_index,
                                pool=pool,
                                incumbent_heuristic=incumbent_heuristic,
                                output_dir=output_dir,
                                k=k,
                                provider=provider,
                                reasoning_effort=reasoning_effort,
                                max_output_tokens=max_output_tokens,
                            )
                            break
                        except _TRANSIENT_EXCEPTIONS as exc:
                            last_exc = exc
                        except RuntimeError as exc:
                            if not _is_transient_runtime_error(exc):
                                raise
                            last_exc = exc
                        time.sleep(_RETRY_SLEEP_SECONDS)
                    if record is None:
                        # Exhausted retries — propagate the last
                        # exception. Batch stops; operator
                        # relaunches after investigating.
                        assert last_exc is not None
                        raise last_exc
                    last_call_end = time.perf_counter()

                    per_call_records.append({
                        "strategy_name": record["strategy_name"],
                        "set_index": record["set_index"],
                        "seed_index": record["seed_index"],
                        "sanitization_status": record["sanitization"]["status"],
                        "proposal_hash": record.get("proposal_hash"),
                    })
                    _write_progress()
    except KeyboardInterrupt:
        stopped = True
        stop_reason = (
            "KeyboardInterrupt — partial batch persisted; re-run to "
            "resume (existing per-call JSONs will be skipped)."
        )

    finished_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "settings": settings,
        "started_at": started_at,
        "finished_at": finished_at,
        "stopped_early": stopped,
        "stop_reason": stop_reason,
        "n_calls_this_run": len(per_call_records),
        "n_skipped_existing": len(skipped),
        "per_call_records": per_call_records,
        "skipped_records": skipped,
    }
    (output_dir / summary_filename).write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary
