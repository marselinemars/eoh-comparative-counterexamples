"""thesis/code/chapter7/experiments/primary_batch.py

Resumable chapter-7 primary-batch driver. Runs all 14 cells × 60
proposals = 840 LLM calls per ``chapter7_design.md`` §4.1, §5,
§3.5, §10, §13, §18.4.

Resumability contract:
  * Per-call records are written atomically to
    ``thesis/results/chapter7_primary_batch_gemini/``.
  * Filename is ``{cell_id}_set{NNN}_seed{NNN}.json`` — derivable
    from (cell_id, set_index, seed_index).
  * On startup, the driver scans the results directory and treats
    every record with a populated ``sanitization.status`` field
    (or an ``api_error`` field set) as "complete." Remaining work
    = full plan − completed.
  * Persistent 429 (credits depleted) raises
    ``PersistentCreditsExhausted`` from the worker; the driver
    catches it, logs to ``chapter7_primary_batch_log.txt``, and
    exits with status 2.
  * The same driver re-running picks up from the remaining set,
    no manual intervention.

Usage::

    python -m thesis.code.chapter7.experiments.primary_batch
    python -m thesis.code.chapter7.experiments.primary_batch --dry-run
    python -m thesis.code.chapter7.experiments.primary_batch --max-calls 10
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

from thesis.code.chapter6.batch_runner import _build_incumbent_module  # noqa: E402
from thesis.code.chapter7.batch_runner import (  # noqa: E402
    MAX_OUTPUT_TOKENS_DEFAULT,
    PROVIDER_DEFAULT,
    REASONING_EFFORT_DEFAULT,
    TEMPERATURE_DEFAULT,
    TIMEOUT_SECONDS_DEFAULT,
    PersistentCreditsExhausted,
    record_filename,
    run_chapter7_single_proposal,
)
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import get_h_eoh, load_final_population  # noqa: E402
from thesis.code.splits import load_split, qualified_instance_id  # noqa: E402

# Paths and constants.
SETS_PATH = REPO_ROOT / "thesis" / "artifacts" / "chapter7_counterexample_sets.json"
OUTPUT_DIR = REPO_ROOT / "thesis" / "results" / "chapter7_primary_batch_gemini"
LOG_PATH = OUTPUT_DIR / "chapter7_primary_batch_log.txt"
OVERVIEW_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "chapter7_primary_batch_overview.json"
)

CHAPTER5_REFERENCE_HASH = "62a2846c597e"
INTER_CALL_SLEEP_S = 3.0

# §4.1 14-cell matrix in canonical order.
CELLS: List[Dict[str, Any]] = [
    {"cell_id": "CH7-01", "strategy": "stratified_representative", "level": 1, "k": 1, "determinism": "stochastic"},
    {"cell_id": "CH7-02", "strategy": "stratified_representative", "level": 1, "k": 2, "determinism": "stochastic"},
    {"cell_id": "CH7-03", "strategy": "stratified_representative", "level": 1, "k": 4, "determinism": "stochastic"},
    {"cell_id": "CH7-04", "strategy": "stratified_representative", "level": 1, "k": 8, "determinism": "stochastic"},
    {"cell_id": "CH7-05", "strategy": "worst_only_at_k1", "level": 1, "k": 1, "determinism": "deterministic"},
    {"cell_id": "CH7-06", "strategy": "worst_plus_best", "level": 1, "k": 2, "determinism": "deterministic"},
    {"cell_id": "CH7-07", "strategy": "worst_plus_best", "level": 1, "k": 4, "determinism": "deterministic"},
    {"cell_id": "CH7-08", "strategy": "worst_plus_best", "level": 1, "k": 8, "determinism": "deterministic"},
    {"cell_id": "CH7-09", "strategy": "stratified_representative", "level": 2, "k": 1, "determinism": "stochastic"},
    {"cell_id": "CH7-10", "strategy": "stratified_representative", "level": 2, "k": 2, "determinism": "stochastic"},
    {"cell_id": "CH7-11", "strategy": "stratified_representative", "level": 2, "k": 4, "determinism": "stochastic"},
    {"cell_id": "CH7-12", "strategy": "worst_only_at_k1", "level": 2, "k": 1, "determinism": "deterministic"},
    {"cell_id": "CH7-13", "strategy": "worst_plus_best", "level": 2, "k": 2, "determinism": "deterministic"},
    {"cell_id": "CH7-14", "strategy": "worst_plus_best", "level": 2, "k": 4, "determinism": "deterministic"},
]


def _enumerate_plan() -> List[Tuple[Dict[str, Any], int, int]]:
    """Compute the full 840-record plan deterministically.

    Returns a list of (cell_dict, set_index, seed_index) tuples in
    canonical order: cell ascending, then set_index ascending, then
    seed_index ascending.
    """
    plan: List[Tuple[Dict[str, Any], int, int]] = []
    for cell in CELLS:
        if cell["determinism"] == "stochastic":
            n_sets, n_seeds = 20, 3
        else:
            n_sets, n_seeds = 1, 60
        for set_idx in range(n_sets):
            for seed_idx in range(n_seeds):
                plan.append((cell, set_idx, seed_idx))
    return plan


def _is_record_complete(path: Path, retry_api_errors: bool = False) -> bool:
    """A record is "complete" if it parses, has chapter=='chapter7', and
    has a populated sanitize_status. With ``retry_api_errors=True``,
    records that have ``api_error`` set or ``sanitize_status`` ==
    ``skipped_due_to_api_error`` are treated as INcomplete so they
    get re-run.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if data.get("chapter") != "chapter7":
        return False
    san = data.get("sanitization") or {}
    san_status = san.get("status") if isinstance(san, dict) else None
    has_api_error = bool(data.get("api_error"))
    if retry_api_errors and (
        has_api_error or san_status == "skipped_due_to_api_error"
    ):
        return False
    if san_status:
        return True
    if has_api_error:
        return True
    return False


def _completed_set(output_dir: Path, retry_api_errors: bool = False) -> set:
    """Set of (cell_id, set_index, seed_index) tuples already on disk."""
    completed = set()
    if not output_dir.exists():
        return completed
    for cell in CELLS:
        prefix = f"{cell['cell_id']}_set"
        for path in output_dir.glob(f"{prefix}*.json"):
            name = path.name
            try:
                tail = name[len(f"{cell['cell_id']}_"):]
                # set{NNN}_seed{NNN}.json
                set_part, seed_part = tail.split("_", 1)
                set_index = int(set_part[3:])  # strip 'set'
                seed_index = int(seed_part[4:].split(".", 1)[0])  # strip 'seed'
            except Exception:
                continue
            if _is_record_complete(path, retry_api_errors=retry_api_errors):
                completed.add((cell["cell_id"], set_index, seed_index))
    return completed


def _build_set_lookup() -> Dict[str, CounterexampleSet]:
    """Map (strategy, k, set_index) → CounterexampleSet from the
    chapter7_counterexample_sets artifact."""
    artifact = json.loads(SETS_PATH.read_text(encoding="utf-8"))
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
    raise RuntimeError(f"Reference {CHAPTER5_REFERENCE_HASH} not found")


def _log(line: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(f"[{ts}] {line}\n")
    print(line, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute and print the plan; do not call LLM.")
    parser.add_argument("--max-calls", type=int, default=None,
                        help="Run at most N calls then exit (smoke).")
    parser.add_argument("--provider", default=PROVIDER_DEFAULT)
    parser.add_argument("--reasoning-effort", default=REASONING_EFFORT_DEFAULT)
    parser.add_argument("--max-output-tokens", type=int,
                        default=MAX_OUTPUT_TOKENS_DEFAULT)
    parser.add_argument("--temperature", type=float, default=TEMPERATURE_DEFAULT)
    parser.add_argument("--timeout-seconds", type=float,
                        default=TIMEOUT_SECONDS_DEFAULT)
    parser.add_argument(
        "--retry-api-errors", action="store_true",
        help=(
            "Treat records with api_error or "
            "sanitize_status='skipped_due_to_api_error' as incomplete "
            "so they get re-run. Default: api_error counts as complete."
        ),
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    plan = _enumerate_plan()
    completed = _completed_set(OUTPUT_DIR, retry_api_errors=args.retry_api_errors)
    remaining = [
        (cell, s, e) for (cell, s, e) in plan
        if (cell["cell_id"], s, e) not in completed
    ]

    _log("=" * 72)
    _log(
        f"CH7 PRIMARY BATCH — provider={args.provider} "
        f"reasoning={args.reasoning_effort} max_tok={args.max_output_tokens}"
    )
    _log(
        f"plan: {len(plan)} records  completed: {len(completed)}  "
        f"remaining: {len(remaining)}"
    )
    _log("=" * 72)

    if args.dry_run:
        per_cell_remaining: Dict[str, int] = {}
        for cell, s, e in remaining:
            per_cell_remaining[cell["cell_id"]] = (
                per_cell_remaining.get(cell["cell_id"], 0) + 1
            )
        for cell in CELLS:
            cid = cell["cell_id"]
            n_total = 60
            n_remain = per_cell_remaining.get(cid, 0)
            print(
                f"  {cid} ({cell['strategy']:<26} L{cell['level']} k={cell['k']}): "
                f"{n_total - n_remain}/{n_total} done, "
                f"{n_remain} remaining"
            )
        return 0

    if not remaining:
        _log("all primary-batch records complete — nothing to do.")
        return 0

    # Heavy setup happens once.
    set_lookup = _build_set_lookup()
    instance_lookup = _build_instance_lookup()
    h_eoh = get_h_eoh()
    incumbent_module = _build_incumbent_module(h_eoh)
    reference_source = _resolve_reference_source()

    started_at = datetime.now(timezone.utc).isoformat()
    n_run = 0
    n_ok = 0
    n_fail_per_label: Dict[str, int] = {}
    last_call_end: Optional[float] = None
    exit_code = 0

    try:
        for cell, set_index, seed_index in remaining:
            if args.max_calls is not None and n_run >= args.max_calls:
                _log(f"--max-calls={args.max_calls} reached; stopping.")
                break

            if last_call_end is not None:
                elapsed = time.perf_counter() - last_call_end
                rem = INTER_CALL_SLEEP_S - elapsed
                if rem > 0:
                    time.sleep(rem)

            cell_id = cell["cell_id"]
            strategy = cell["strategy"]
            level = cell["level"]
            k = cell["k"]
            set_key = f"{strategy}@k={k}@set={set_index:02d}"
            ce_set = set_lookup.get(set_key)
            if ce_set is None:
                _log(
                    f"  {cell_id} set={set_index:03d} seed={seed_index:03d} "
                    f"FATAL: set key {set_key!r} not in artifact"
                )
                n_fail_per_label["missing_set"] = (
                    n_fail_per_label.get("missing_set", 0) + 1
                )
                last_call_end = time.perf_counter()
                continue

            try:
                record = run_chapter7_single_proposal(
                    cell_id=cell_id,
                    strategy=strategy,
                    level=level,
                    k=k,
                    set_index=set_index,
                    seed_index=seed_index,
                    counterexample_set=ce_set,
                    incumbent_heuristic=h_eoh,
                    incumbent_module=incumbent_module,
                    reference_source=reference_source,
                    instance_lookup=instance_lookup,
                    output_dir=OUTPUT_DIR,
                    provider=args.provider,
                    reasoning_effort=args.reasoning_effort,
                    max_output_tokens=args.max_output_tokens,
                    temperature=args.temperature,
                    timeout_seconds=args.timeout_seconds,
                )
            except PersistentCreditsExhausted as exc:
                _log(
                    f"  {cell_id} set={set_index:03d} seed={seed_index:03d} "
                    f"PERSISTENT_CREDITS_EXHAUSTED — exiting with status 2 "
                    f"so the design lead can resolve. Error: {exc}"
                )
                exit_code = 2
                break
            except KeyboardInterrupt:
                _log("KeyboardInterrupt — partial batch persisted; re-run to resume.")
                exit_code = 130
                break

            last_call_end = time.perf_counter()
            n_run += 1
            san = (record.get("sanitization") or {})
            status = san.get("status", "unknown")
            if status == "ok":
                n_ok += 1
                delta_step = (record.get("scoring") or {}).get("delta_step")
                ds_str = (
                    f"{delta_step:+.2f}"
                    if isinstance(delta_step, (int, float))
                    else "n/a"
                )
                _log(
                    f"  {cell_id} set={set_index:03d} seed={seed_index:03d} "
                    f"sanitize=ok delta_step={ds_str}"
                )
            else:
                n_fail_per_label[status] = n_fail_per_label.get(status, 0) + 1
                _log(
                    f"  {cell_id} set={set_index:03d} seed={seed_index:03d} "
                    f"sanitize={status}"
                )
    finally:
        finished_at = datetime.now(timezone.utc).isoformat()
        completed_after = _completed_set(
            OUTPUT_DIR, retry_api_errors=args.retry_api_errors
        )
        overview = {
            "started_at": started_at,
            "finished_at": finished_at,
            "settings": {
                "provider": args.provider,
                "reasoning_effort": args.reasoning_effort,
                "max_output_tokens": args.max_output_tokens,
                "temperature": args.temperature,
                "inter_call_sleep_s": INTER_CALL_SLEEP_S,
                "timeout_seconds": args.timeout_seconds,
            },
            "totals": {
                "plan_size": len(plan),
                "completed_at_start": len(completed),
                "completed_at_end": len(completed_after),
                "n_run_this_session": n_run,
                "n_ok_this_session": n_ok,
                "n_fail_per_label_this_session": n_fail_per_label,
                "exit_code": exit_code,
            },
            "output_dir": str(OUTPUT_DIR),
        }
        OVERVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
        OVERVIEW_PATH.write_text(
            json.dumps(overview, indent=2, sort_keys=True), encoding="utf-8"
        )
        _log(
            f"session done: ran {n_run} calls, "
            f"{n_ok} sanitize-ok, fails={n_fail_per_label}; "
            f"completed-on-disk {len(completed_after)}/{len(plan)}; "
            f"exit_code={exit_code}"
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
