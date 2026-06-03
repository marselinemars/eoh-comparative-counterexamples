"""
thesis/code/chapter4_gaponly/batch_runner.py

E2 (gap-only) batch driver. Iterates (set_index 0..19, seed_index
0..2) on chapter-5's stratified_representative L1 cell to produce
60 sanitization-ok proposals matched-paired to chapter 5 by
(set_index, seed_index). The CounterexampleSet at each set_index
is bit-identical to chapter-5's (chapter-5's set_seed function is
reused unchanged). The per-call LLM seed is fresh under the
`ch4gaponly:` namespace per design doc §6.2.

Reuses chapter-5's sanitizer, scoring helpers, transient-error
retry policy, and progress-file convention. The chapter-5 prompt
builder is NOT used; this cell's prompt is built by
thesis/code/chapter4_gaponly/prompt_builder.build_prompt.

Resumable: per-call provenance JSONs at
thesis/results/chapter4_gaponly_primary_batch_gemini/set{NN}_seed{N}.json;
re-running picks up where the previous run left off.
"""
from __future__ import annotations

import hashlib
import json
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from thesis.code.chapter4_gaponly.prompt_builder import build_prompt
from thesis.code.chapter5 import STRATEGIES
from thesis.code.chapter5.batch_runner import (
    TRANSIENT_EXCEPTIONS,
    TRANSIENT_MAX_RETRIES,
    TRANSIENT_RETRY_SLEEP_SECONDS,
    is_transient_runtime_error,
)
from thesis.code.chapter5.llm_client import call_llm
from thesis.code.chapter5.runner import (
    _score_baseline_on_split,
    _score_heuristic_on_split,
    _sanitization_record,
    _compute_metrics,
)
from thesis.code.chapter5.sanitize import sanitize
from thesis.code.chapter5.seeds import MASTER_SEED_CH5, set_seed
from thesis.code.counterexample import CounterexampleSet
from thesis.code.score_cache import ScoreCache, code_hash
from thesis.code.splits import load_split


STRATEGY_NAME = "stratified_representative"
N_SETS = 20
N_SEEDS_PER_SET = 3
K = 4
LEVEL = 1
SEED_NAMESPACE = "ch4gaponly"


def ch4gaponly_llm_seed(set_index: int, seed_index: int) -> int:
    """Per-call LLM seed under the ch4gaponly namespace. Independent
    of chapter-5's llm_seed and chapter4_noref's ch4noref_llm_seed."""
    return int(
        hashlib.sha256(
            f"{SEED_NAMESPACE}:llm:{MASTER_SEED_CH5}:"
            f"{STRATEGY_NAME}:{set_index}:{seed_index}".encode("utf-8")
        ).hexdigest()[:8],
        16,
    )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _existing_record_path(
    output_dir: Path, set_index: int, seed_index: int
) -> Path:
    return output_dir / f"set{set_index:02d}_seed{seed_index}.json"


def run_single_proposal_gaponly(
    set_index: int,
    seed_index: int,
    pool: CounterexampleSet,
    incumbent_heuristic: Dict[str, Any],
    output_dir: Path,
    *,
    provider: str = "gemini",
    reasoning_effort: Optional[str] = None,
    max_output_tokens: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Run one E2 proposal end-to-end and persist the provenance
    record. Parallels chapter5.runner.run_single_proposal but uses
    the E2 prompt builder and the ch4gaponly: seed namespace.
    """
    started_at = _utcnow_iso()

    strategy = STRATEGIES[STRATEGY_NAME]
    derived_set_seed = set_seed(STRATEGY_NAME, set_index)
    rng = np.random.default_rng(derived_set_seed)
    counterexample_set = strategy(pool, K, rng=rng)

    derived_llm_seed = ch4gaponly_llm_seed(set_index, seed_index)

    prompt = build_prompt(
        counterexample_set=counterexample_set,
        incumbent_code=incumbent_heuristic["code"],
    )

    effective_reasoning_effort = (
        reasoning_effort if reasoning_effort is not None else "medium"
    )
    effective_max_output_tokens = (
        max_output_tokens if max_output_tokens is not None else 32768
    )
    effective_timeout_seconds = (
        timeout_seconds if timeout_seconds is not None else 300.0
    )
    llm_response = call_llm(
        provider=provider,
        prompt=prompt,
        seed=derived_llm_seed,
        reasoning_effort=effective_reasoning_effort,
        max_output_tokens=effective_max_output_tokens,
        timeout_seconds=effective_timeout_seconds,
    )
    raw_response = llm_response["text"]

    split_train_select = load_split("train_select")
    sanity_instance = split_train_select["instances"][0]
    sanitize_result = sanitize(raw_response, sanity_instance)

    scoring_record: Optional[Dict[str, Any]] = None
    proposal_hash: Optional[str] = None
    if sanitize_result["status"] == "ok":
        cache = ScoreCache()
        proposal_code = sanitize_result["cleaned_code"]
        proposal_hash = code_hash(proposal_code)

        incumbent_module = types.ModuleType(
            f"incumbent_{incumbent_heuristic['code_hash']}"
        )
        exec(
            compile(
                incumbent_heuristic["code"], "<h_eoh>", "exec"
            ),
            incumbent_module.__dict__,
        )

        baseline_step = _score_baseline_on_split(
            incumbent_module,
            incumbent_heuristic["code_hash"],
            "train_step",
            cache,
        )
        baseline_gate = _score_baseline_on_split(
            incumbent_module,
            incumbent_heuristic["code_hash"],
            "train_gate",
            cache,
        )
        proposal_step = _score_heuristic_on_split(
            sanitize_result["score_fn"],
            proposal_code,
            proposal_hash,
            "train_step",
            cache,
        )
        proposal_gate = _score_heuristic_on_split(
            sanitize_result["score_fn"],
            proposal_code,
            proposal_hash,
            "train_gate",
            cache,
        )
        cache.save()
        scoring_record = _compute_metrics(
            baseline_step, proposal_step, baseline_gate, proposal_gate
        )

    finished_at = _utcnow_iso()

    reference_hashes = {c.reference_hash for c in pool}
    if len(reference_hashes) != 1:
        raise RuntimeError(
            f"Pool must have a single reference hash; "
            f"found {reference_hashes}"
        )
    reference_hash = next(iter(reference_hashes))

    record: Dict[str, Any] = {
        "cell_id": "chapter4_gaponly",
        "cell_description": (
            "E2 gap-only control; design doc §4.5.2. "
            "Stratified_representative @ L1 @ k=4. "
            "Reference source code withheld; gap_bins shown. "
            "Locked E2 task-instruction wording."
        ),
        "master_seed": MASTER_SEED_CH5,
        "seed_namespace": SEED_NAMESPACE,
        "provider": provider,
        "strategy_name": STRATEGY_NAME,
        "level": LEVEL,
        "k": K,
        "set_index": set_index,
        "seed_index": seed_index,
        "set_seed": derived_set_seed,
        "llm_seed": derived_llm_seed,
        "counterexample_set": json.loads(counterexample_set.to_json()),
        "incumbent_hash": incumbent_heuristic["code_hash"],
        "reference_hash": reference_hash,
        "proposal_hash": proposal_hash,
        "prompt": prompt,
        "raw_response": raw_response,
        "llm_metadata": {
            "model": llm_response["model"],
            "temperature": llm_response["temperature"],
            "max_output_tokens": llm_response["max_output_tokens"],
            "reasoning_effort": llm_response["reasoning_effort"],
            "reasoning_effort_requested": reasoning_effort,
            "max_output_tokens_requested": max_output_tokens,
            "seed_requested": llm_response["seed_requested"],
            "seed_honored": llm_response["seed_honored"],
            "raw_response_metadata": llm_response["raw_response_metadata"],
        },
        "sanitization": _sanitization_record(sanitize_result),
        "scoring": scoring_record,
        "timestamps": {
            "started_at": started_at,
            "finished_at": finished_at,
        },
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = _existing_record_path(output_dir, set_index, seed_index)
    out_path.write_text(
        json.dumps(record, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    record["_written_to"] = str(out_path)
    return record


def run_gaponly_batch(
    pool: CounterexampleSet,
    incumbent_heuristic: Dict[str, Any],
    output_dir: Path,
    *,
    provider: str = "gemini",
    reasoning_effort: Optional[str] = "medium",
    max_output_tokens: Optional[int] = 32768,
    temperature: float = 1.0,
    inter_call_sleep_seconds: float = 3.0,
    summary_filename: str = "primary_batch_summary.json",
    progress_filename: str = "progress.json",
    resume: bool = True,
    _run_single_proposal: Callable[..., Dict[str, Any]] = (
        run_single_proposal_gaponly
    ),
) -> Dict[str, Any]:
    """Run the E2 (gap-only) primary batch: 20 sets × 3 seeds
    = 60 calls. Resume-friendly. Returns the summary dict (also
    written to disk).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    settings = {
        "cell_id": "chapter4_gaponly",
        "provider": provider,
        "reasoning_effort": reasoning_effort,
        "max_output_tokens": max_output_tokens,
        "temperature": temperature,
        "inter_call_sleep_seconds": inter_call_sleep_seconds,
        "strategy": STRATEGY_NAME,
        "level": LEVEL,
        "k": K,
        "n_sets": N_SETS,
        "n_seeds_per_set": N_SEEDS_PER_SET,
        "resume": resume,
        "seed_namespace": SEED_NAMESPACE,
    }

    started_at = _utcnow_iso()
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
                    "last_updated_at": _utcnow_iso(),
                    "n_calls_this_run": len(per_call_records),
                    "n_skipped_existing": len(skipped),
                    "last_records": per_call_records[-5:],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    _write_progress()

    try:
        for set_index in range(N_SETS):
            for seed_index in range(N_SEEDS_PER_SET):
                existing = _existing_record_path(
                    output_dir, set_index, seed_index
                )
                if resume and existing.exists():
                    skipped.append({
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
                for _ in range(TRANSIENT_MAX_RETRIES):
                    try:
                        record = _run_single_proposal(
                            set_index=set_index,
                            seed_index=seed_index,
                            pool=pool,
                            incumbent_heuristic=incumbent_heuristic,
                            output_dir=output_dir,
                            provider=provider,
                            reasoning_effort=reasoning_effort,
                            max_output_tokens=max_output_tokens,
                        )
                        break
                    except TRANSIENT_EXCEPTIONS as exc:
                        last_exc = exc
                    except RuntimeError as exc:
                        if not is_transient_runtime_error(exc):
                            raise
                        last_exc = exc
                    time.sleep(TRANSIENT_RETRY_SLEEP_SECONDS)
                if record is None:
                    assert last_exc is not None
                    raise last_exc
                last_call_end = time.perf_counter()

                per_call_records.append({
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

    finished_at = _utcnow_iso()
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
