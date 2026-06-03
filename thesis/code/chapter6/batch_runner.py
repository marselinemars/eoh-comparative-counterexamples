"""
thesis/code/chapter6/batch_runner.py

Chapter 6 cell-level batch runner. One cell = one (strategy, level)
combination; one call to :func:`run_chapter6_cell` produces
``n_proposals`` proposals for that cell.

Per chapter6_design.md §8.1, the four primary cells are:

  - (stratified_representative, L1)  20 sets x 3 seeds = 60
  - (stratified_representative, L2)  20 sets x 3 seeds = 60
  - (worst_plus_best,           L1)   1 set  x 60 seeds = 60
  - (worst_plus_best,           L2)   1 set  x 60 seeds = 60

Seed namespacing follows §13: a master seed of 20_260_424 plus
sha256-hashed strategy / set / seed / level coordinates, with a
``ch6:`` prefix that makes the resulting integer disjoint from
chapter 5's seed space (which uses ``ch5:``).

Architectural note. The per-proposal worker
:func:`_run_chapter6_single_proposal` is a chapter-6 parallel of
chapter 5's ``run_single_proposal`` — it does *not* wrap that
function. The reason is that chapter 5's runner builds the
prompt internally via ``chapter5.prompt_builder.build_prompt``,
which is the wrong renderer for chapter 6 (chapter 6 needs
:func:`thesis.code.chapter6.prompt_renderer.render_level1_prompt`
or :func:`render_level2_prompt`). The chapter-6 worker
therefore re-implements the orchestration loop and reuses
chapter 5's sanitization, scoring, and LLM-client helpers as a
frozen library, on the same discipline as the prompt renderer's
ch6 → ch5 import dependency (chapter6_design.md §9.2
implementation note).

The per-proposal record schema is the chapter 5 schema with four
chapter-6-specific fields added: ``chapter`` (= ``"chapter6"``),
``cell_id`` (= ``"<strategy>@L<level>"``), ``level`` (1 or 2),
and ``master_seed`` (= ``MASTER_SEED_CH6``).
"""
from __future__ import annotations

import hashlib
import json
import socket
import time
import types
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np

from thesis.code.chapter5 import (
    DETERMINISTIC_STRATEGY_NAMES,
    STOCHASTIC_STRATEGY_NAMES,
    STRATEGIES,
)
from thesis.code.chapter5.llm_client import call_llm as _ch5_call_llm
from thesis.code.chapter5.runner import (
    _compute_metrics,
    _sanitization_record,
    _score_baseline_on_split,
    _score_heuristic_on_split,
)
from thesis.code.chapter5.sanitize import sanitize
from thesis.code.chapter6.prompt_renderer import (
    render_level1_prompt,
    render_level2_prompt,
)
from thesis.code.chapter6.trace_extractor import (
    DecisionRecord,
    extract_incumbent_trace,
)
from thesis.code.counterexample import CounterexampleSet
from thesis.code.score_cache import ScoreCache, code_hash
from thesis.code.splits import load_split

# ---------------------------------------------------------------------------
# Seed derivation (§13).
# ---------------------------------------------------------------------------

MASTER_SEED_CH6: int = 20_260_424


def set_seed_ch6(strategy_name: str, set_index: int, level: int) -> int:
    """Deterministic 32-bit set seed for chapter 6.

    Namespacing: ``ch6:set:<master>:<strategy>:<set_index>:L<level>``.
    The ``ch6:`` prefix and the ``:L<level>`` suffix together make the
    output disjoint from chapter 5's seed space and from the other
    structural level inside chapter 6.
    """
    payload = (
        f"ch6:set:{MASTER_SEED_CH6}:{strategy_name}:"
        f"{set_index}:L{level}"
    )
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16)


def llm_seed_ch6(
    strategy_name: str, set_index: int, seed_index: int, level: int
) -> int:
    """Deterministic 32-bit per-call LLM seed for chapter 6.

    Namespacing: ``ch6:llm:<master>:<strategy>:<set>:<seed>:L<level>``.
    """
    payload = (
        f"ch6:llm:{MASTER_SEED_CH6}:{strategy_name}:"
        f"{set_index}:{seed_index}:L{level}"
    )
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16)


def trajectory_set_seed_ch6(
    strategy_name: str, trajectory_index: int, step_index: int, level: int
) -> int:
    """Deterministic 32-bit set seed for chapter 6 validation steps.

    Namespacing: ``ch6:traj:set:<master>:<strategy>:<traj>:<step>:L<level>``.
    The ``ch6:traj:`` prefix makes the result disjoint from the
    primary-batch ``ch6:set:`` namespace and from chapter 5's
    ``ch5:traj:`` namespace.
    """
    payload = (
        f"ch6:traj:set:{MASTER_SEED_CH6}:{strategy_name}:"
        f"{trajectory_index}:{step_index}:L{level}"
    )
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16)


def trajectory_llm_seed_ch6(
    strategy_name: str, trajectory_index: int, step_index: int, level: int
) -> int:
    """Deterministic 32-bit per-call LLM seed for chapter 6 validation steps.

    Namespacing: ``ch6:traj:llm:<master>:<strategy>:<traj>:<step>:L<level>``.
    """
    payload = (
        f"ch6:traj:llm:{MASTER_SEED_CH6}:{strategy_name}:"
        f"{trajectory_index}:{step_index}:L{level}"
    )
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16)


# ---------------------------------------------------------------------------
# Per-cell allocation table (§5 / §8.1, inherited from ch5 §5.7).
# ---------------------------------------------------------------------------

_DET_ALLOCATION: Tuple[int, int] = (1, 60)
_STOCH_ALLOCATION: Tuple[int, int] = (20, 3)


def _allocation_for(strategy_name: str) -> Tuple[int, int]:
    if strategy_name in DETERMINISTIC_STRATEGY_NAMES:
        return _DET_ALLOCATION
    if strategy_name in STOCHASTIC_STRATEGY_NAMES:
        return _STOCH_ALLOCATION
    raise ValueError(
        f"Strategy {strategy_name!r} is neither deterministic nor "
        "stochastic; cannot allocate (set, seed) matrix."
    )


def _iterate_proposals(
    strategy_name: str, n_proposals: int
) -> Iterator[Tuple[int, int]]:
    """Yield (set_index, seed_index) pairs for the first ``n_proposals``
    of this cell.

    Pairs are yielded in (set_index ascending, seed_index ascending)
    order. Capped at ``n_proposals`` total.
    """
    n_sets, n_seeds = _allocation_for(strategy_name)
    count = 0
    for set_idx in range(n_sets):
        for seed_idx in range(n_seeds):
            if count >= n_proposals:
                return
            yield set_idx, seed_idx
            count += 1


# ---------------------------------------------------------------------------
# Transient-error retry policy (mirrors ch5).
# ---------------------------------------------------------------------------

TRANSIENT_EXCEPTIONS: tuple = (
    socket.gaierror,
    TimeoutError,
    ConnectionError,
)
TRANSIENT_MAX_RETRIES = 5
TRANSIENT_RETRY_SLEEP_SECONDS = 30.0


def _is_transient_runtime_error(exc: BaseException) -> bool:
    if not isinstance(exc, RuntimeError):
        return False
    msg = str(exc).lower()
    return "returned 5" in msg or "rate limit" in msg or "429" in msg


# ---------------------------------------------------------------------------
# Per-proposal worker.
# ---------------------------------------------------------------------------


def _build_incumbent_module(incumbent_heuristic: Dict[str, Any]) -> types.ModuleType:
    """Exec the incumbent's source into a fresh module, the same way
    ch5's runner does for scoring."""
    mod = types.ModuleType(f"incumbent_{incumbent_heuristic['code_hash']}")
    exec(
        compile(incumbent_heuristic["code"], "<incumbent>", "exec"),
        mod.__dict__,
    )
    return mod


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_filename(cell_id: str, set_index: int, seed_index: int) -> str:
    return f"{cell_id}_set{set_index:03d}_seed{seed_index:03d}.json"


def _run_chapter6_single_proposal(
    *,
    strategy_name: str,
    level: int,
    set_index: int,
    seed_index: int,
    pool: CounterexampleSet,
    incumbent_heuristic: Dict[str, Any],
    reference_source: str,
    output_dir: Path,
    k: int,
    provider: str,
    reasoning_effort: Optional[str],
    max_output_tokens: Optional[int],
    timeout_seconds: float,
    call_llm_fn: Callable[..., Dict[str, Any]] = _ch5_call_llm,
    set_seed_override: Optional[int] = None,
    llm_seed_override: Optional[int] = None,
    write_record: bool = True,
) -> Dict[str, Any]:
    """Run one chapter-6 proposal and persist its provenance record.

    Mirrors ``thesis.code.chapter5.runner.run_single_proposal``
    decision-for-decision but renders the prompt via the chapter 6
    renderer (Level 1 or Level 2) and writes the chapter-6
    provenance schema. The LLM client, sanitizer, and scoring
    helpers are reused unchanged from chapter 5.

    Optional ``set_seed_override`` and ``llm_seed_override`` let the
    validation runner inject seeds derived under the ``ch6:traj:``
    namespace (per §13) instead of the primary-batch ``ch6:set:`` /
    ``ch6:llm:`` derivations. When omitted, the function behaves
    exactly as the primary-batch driver expects.

    ``write_record=False`` suppresses the per-call JSON write; the
    record dict is still returned. The validation runner uses this
    to write a single combined trajectory-step record instead.
    """
    started_at = _utcnow_iso()

    if level not in (1, 2):
        raise ValueError(f"level must be 1 or 2; got {level!r}")
    if strategy_name not in STRATEGIES:
        raise ValueError(
            f"Unknown strategy: {strategy_name}. "
            f"Valid: {sorted(STRATEGIES.keys())}"
        )
    cell_id = f"{strategy_name}@L{level}"
    incumbent_source = incumbent_heuristic["code"]
    incumbent_hash = incumbent_heuristic["code_hash"]

    # --- seeds (ch6 namespace; trajectory variants when injected) ---
    derived_set_seed = (
        set_seed_override
        if set_seed_override is not None
        else set_seed_ch6(strategy_name, set_index, level)
    )
    derived_llm_seed = (
        llm_seed_override
        if llm_seed_override is not None
        else llm_seed_ch6(strategy_name, set_index, seed_index, level)
    )

    # --- selection ---
    strategy = STRATEGIES[strategy_name]
    if strategy_name in STOCHASTIC_STRATEGY_NAMES:
        rng = np.random.default_rng(derived_set_seed)
        counterexample_set = strategy(pool, k, rng=rng)
    else:
        counterexample_set = strategy(pool, k)

    # --- prompt rendering ---
    if level == 1:
        prompt = render_level1_prompt(
            counterexample_set=counterexample_set,
            incumbent_source=incumbent_source,
            reference_source=reference_source,
        )
        traces_for_record: Optional[List[List[Dict[str, Any]]]] = None
    else:
        # Level 2: extract one full trace per counterexample, render
        # via the level-2 renderer (which applies the §7.4 subsample
        # internally).
        incumbent_module = _build_incumbent_module(incumbent_heuristic)
        train_select = load_split("train_select")
        instance_lookup = {
            f"thesis_train_select:{inst['instance_id']}": inst
            for inst in train_select["instances"]
        }
        traces: List[List[DecisionRecord]] = []
        for ce in counterexample_set.items:
            inst = instance_lookup[ce.instance_id]
            traces.append(extract_incumbent_trace(inst, incumbent_module))
        prompt = render_level2_prompt(
            counterexample_set=counterexample_set,
            traces=traces,
            incumbent_source=incumbent_source,
            reference_source=reference_source,
            instance_data_by_id=instance_lookup,
        )
        # Trace-row-count summary in the record (the rendered prompt
        # includes the §7.4-subsampled rows; the per-counterexample
        # row counts are useful provenance without dumping the full
        # extracted trace into the JSON).
        traces_for_record = [
            [{"trace_row_count": len(t)} for t in [trace]] for trace in traces
        ]

    # --- LLM call ---
    effective_reasoning_effort = (
        reasoning_effort if reasoning_effort is not None else "medium"
    )
    effective_max_output_tokens = (
        max_output_tokens if max_output_tokens is not None else 32768
    )
    llm_response = call_llm_fn(
        provider=provider,
        prompt=prompt,
        seed=derived_llm_seed,
        reasoning_effort=effective_reasoning_effort,
        max_output_tokens=effective_max_output_tokens,
        timeout_seconds=timeout_seconds,
    )
    raw_response = llm_response["text"]

    # --- sanitize ---
    train_select_for_sanity = load_split("train_select")
    sanity_instance = train_select_for_sanity["instances"][0]
    sanitize_result = sanitize(raw_response, sanity_instance)

    # --- score (only if sanitize ok) ---
    scoring_record: Optional[Dict[str, Any]] = None
    proposal_hash: Optional[str] = None
    if sanitize_result["status"] == "ok":
        cache = ScoreCache()
        proposal_code = sanitize_result["cleaned_code"]
        proposal_hash = code_hash(proposal_code)

        incumbent_module = _build_incumbent_module(incumbent_heuristic)

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

    finished_at = _utcnow_iso()

    # --- reference hash from the pool ---
    reference_hashes = {c.reference_hash for c in pool}
    if len(reference_hashes) != 1:
        raise RuntimeError(
            f"Chapter 6 pool must have a single reference hash; "
            f"found {reference_hashes}"
        )
    reference_hash = next(iter(reference_hashes))

    record: Dict[str, Any] = {
        "chapter": "chapter6",
        "cell_id": cell_id,
        "level": level,
        "master_seed": MASTER_SEED_CH6,
        "provider": provider,
        "strategy_name": strategy_name,
        "set_index": set_index,
        "seed_index": seed_index,
        "set_seed": derived_set_seed,
        "llm_seed": derived_llm_seed,
        "k": k,
        "counterexample_set": json.loads(counterexample_set.to_json()),
        "incumbent_hash": incumbent_hash,
        "reference_hash": reference_hash,
        "proposal_hash": proposal_hash,
        "prompt": prompt,
        "raw_response": raw_response,
        "llm_metadata": {
            "model": llm_response.get("model"),
            "temperature": llm_response.get("temperature"),
            "max_output_tokens": llm_response.get("max_output_tokens"),
            "reasoning_effort": llm_response.get("reasoning_effort"),
            "reasoning_effort_requested": reasoning_effort,
            "max_output_tokens_requested": max_output_tokens,
            "seed_requested": llm_response.get("seed_requested"),
            "seed_honored": llm_response.get("seed_honored"),
            "raw_response_metadata": llm_response.get("raw_response_metadata"),
        },
        "sanitization": _sanitization_record(sanitize_result),
        "scoring": scoring_record,
        "trace_summary": (
            None
            if level == 1
            else [
                {"trace_row_count": len(t)}
                for t in (traces if level == 2 else [])
            ]
        ),
        "timestamps": {"started_at": started_at, "finished_at": finished_at},
    }

    if write_record:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / _record_filename(cell_id, set_index, seed_index)
        out_path.write_text(
            json.dumps(record, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        record["_written_to"] = str(out_path)
    return record


# ---------------------------------------------------------------------------
# Cell driver and CellResult.
# ---------------------------------------------------------------------------


@dataclass
class CellResult:
    """Aggregate stats for one cell run."""

    cell_id: str
    n_attempted: int
    n_succeeded: int
    n_failed_per_label: Dict[str, int] = field(default_factory=dict)
    proposal_record_paths: List[str] = field(default_factory=list)


def run_chapter6_cell(
    strategy_name: str,
    level: int,
    pool: CounterexampleSet,
    incumbent_heuristic: Dict[str, Any],
    reference_source: str,
    n_proposals: int,
    output_dir: Path,
    *,
    smoke_mode: bool = False,
    smoke_n: int = 3,
    k: int = 4,
    provider: str = "gemini",
    reasoning_effort: Optional[str] = "medium",
    max_output_tokens: Optional[int] = 32768,
    timeout_seconds: float = 300.0,
    inter_call_sleep_seconds: float = 3.0,
    call_llm_fn: Callable[..., Dict[str, Any]] = _ch5_call_llm,
    _run_proposal_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> CellResult:
    """Run one chapter 6 cell: ``n_proposals`` proposals for the given
    (strategy, level) combination.

    Iterates ``(set_index, seed_index)`` per :func:`_iterate_proposals`,
    delegates each proposal to :func:`_run_chapter6_single_proposal`
    (or to ``_run_proposal_fn`` if injected for tests), counts
    sanitize-ok / sanitize-failed, and returns a :class:`CellResult`.

    Note: this function is not resume-aware. The next-task primary-
    batch driver layers resume on top via existence-check on each
    record path before calling here.
    """
    if smoke_mode:
        n_proposals = smoke_n

    cell_id = f"{strategy_name}@L{level}"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    proposal_runner = _run_proposal_fn or _run_chapter6_single_proposal

    n_attempted = 0
    n_succeeded = 0
    failure_counts: Dict[str, int] = {}
    paths: List[str] = []
    last_call_end: Optional[float] = None

    for set_index, seed_index in _iterate_proposals(strategy_name, n_proposals):
        if last_call_end is not None and inter_call_sleep_seconds > 0:
            elapsed = time.perf_counter() - last_call_end
            rem = inter_call_sleep_seconds - elapsed
            if rem > 0:
                time.sleep(rem)

        record = proposal_runner(
            strategy_name=strategy_name,
            level=level,
            set_index=set_index,
            seed_index=seed_index,
            pool=pool,
            incumbent_heuristic=incumbent_heuristic,
            reference_source=reference_source,
            output_dir=output_dir,
            k=k,
            provider=provider,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
            call_llm_fn=call_llm_fn,
        )
        last_call_end = time.perf_counter()

        n_attempted += 1
        status = record["sanitization"]["status"]
        if status == "ok":
            n_succeeded += 1
        else:
            failure_counts[status] = failure_counts.get(status, 0) + 1
        if "_written_to" in record:
            paths.append(record["_written_to"])

    return CellResult(
        cell_id=cell_id,
        n_attempted=n_attempted,
        n_succeeded=n_succeeded,
        n_failed_per_label=failure_counts,
        proposal_record_paths=paths,
    )


# ---------------------------------------------------------------------------
# Cell list constant.
# ---------------------------------------------------------------------------

DEFAULT_CELLS: Sequence[Tuple[str, int]] = (
    ("stratified_representative", 1),
    ("stratified_representative", 2),
    ("worst_plus_best", 1),
    ("worst_plus_best", 2),
)
"""The four chapter 6 primary cells, in the canonical run order
defined by chapter6_design.md §8.1."""
