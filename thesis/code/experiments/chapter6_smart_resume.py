"""
thesis/code/experiments/chapter6_smart_resume.py

Smart resume for the chapter-6 primary batch. Bypasses the
production driver's iterate-first-N resume bug by:

1. **Merge phase**: Scans sidelined directories for valid L2
   stratified records produced under the locked N=60 rule
   (commit 9d5bd37), picks the most-recent-by-mtime version of
   each (set, seed) coordinate, and copies them into the
   canonical primary results directory.

2. **Run-missing phase**: For each of the four cells, identifies
   the (set, seed) coordinates that are NOT in the primary dir,
   and generates only those via the per-proposal worker
   (`_run_chapter6_single_proposal`). Bypasses
   `run_chapter6_cell` entirely — that function uses
   `_iterate_proposals` which is the broken
   iterate-first-N logic.

Validity contract for merged records (verified per record):
  - chapter == "chapter6"
  - level == expected for cell
  - sanitization.status == "ok"
  - scoring populated with delta_step
  - prompt contains the locked framing string
    "60 rows total from 5000 actual decisions" (L2 only)
  - llm_metadata.model == "gemini-2.5-pro"

Idempotent. Safe to re-run after interruption.

Usage:
    python -m thesis.code.experiments.chapter6_smart_resume --dry-run
    python -m thesis.code.experiments.chapter6_smart_resume
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_env_file(Path(__file__).resolve().parents[3] / ".env")

from thesis.code.chapter5 import (  # noqa: E402
    DETERMINISTIC_STRATEGY_NAMES,
    STOCHASTIC_STRATEGY_NAMES,
)
from thesis.code.chapter6.batch_runner import (  # noqa: E402
    DEFAULT_CELLS,
    _run_chapter6_single_proposal,
)
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import (  # noqa: E402
    get_h_eoh,
    load_final_population,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
POOL_PATH = REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
PRIMARY_DIR = REPO_ROOT / "thesis" / "results" / "chapter6_primary_batch_gemini"

# Sidelined dirs in scan order. The picker takes the most-recent-by-mtime
# valid record per coordinate regardless of which dir it came from.
SIDELINED_DIRS = [
    REPO_ROOT / "thesis" / "results" / "chapter6_primary_batch_partial_stratified_representative_at_L2",
    REPO_ROOT / "thesis" / "results" / "chapter6_primary_batch_partial_stratified_l2",
    REPO_ROOT / "thesis" / "results" / "chapter6_primary_batch_smallrun",
]

LOCKED_RULE_FRAMING_STRING = "60 rows total from 5000 actual decisions"
EXPECTED_MODEL = "gemini-2.5-pro"

PROVIDER = "gemini"
REASONING_EFFORT = "medium"
# 32768 was the original AI-Studio cap. Vertex DSQ on this project
# rejects anything >12288 even on us-central1 (probed 2026-04-29).
# 12288 with reasoning_effort="medium" maps to thinkingBudget=-1
# (dynamic) on Vertex, mirroring AI-Studio's auto-thinking behavior
# (median 7.6K thoughts, p90 10.9K thoughts on the existing 94 records).
MAX_OUTPUT_TOKENS_BY_PROVIDER = {
    "gemini": 32768,
    "vertex": 12288,
    "groq": 2048,
}
# Vertex requires a regional endpoint with DSQ headroom. global is
# saturated at >8K output even on tiny prompts; us-central1 cleared
# 12288. Override env at run start so users don't have to remember.
VERTEX_LOCATION = "us-central1"
INTER_CALL_SLEEP_SECONDS = 3.0
TIMEOUT_SECONDS = 300.0
N_PROPOSALS_PER_CELL = 60

FILENAME_RE = re.compile(
    r"^(?P<cell>.+?)_set(?P<set>\d+)_seed(?P<seed>\d+)\.json$"
)


# ---------------------------------------------------------------------------
# Allocation per strategy
# ---------------------------------------------------------------------------


def _expected_coords_for(strategy_name: str) -> Set[Tuple[int, int]]:
    """All (set, seed) coordinates that should exist for a complete cell."""
    if strategy_name in DETERMINISTIC_STRATEGY_NAMES:
        return {(0, e) for e in range(N_PROPOSALS_PER_CELL)}
    if strategy_name in STOCHASTIC_STRATEGY_NAMES:
        # 20 sets × 3 seeds = 60
        return {(s, e) for s in range(20) for e in range(3)}
    raise ValueError(f"Unknown strategy: {strategy_name}")


def _existing_coords_for_cell(cell_id: str) -> Set[Tuple[int, int]]:
    """Coordinates that already have an OK record in the primary dir.

    Records with sanitization.status != "ok" (e.g. failed_extraction
    from MAX_TOKENS truncation) are intentionally NOT counted here, so
    the resume run will retry them. The retry overwrites the file
    in-place via run_chapter6_cell's path convention.
    """
    out: Set[Tuple[int, int]] = set()
    for path in PRIMARY_DIR.glob(f"{cell_id}_set*.json"):
        m = FILENAME_RE.match(path.name)
        if not m:
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (d.get("sanitization") or {}).get("status") == "ok":
            out.add((int(m["set"]), int(m["seed"])))
    return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_record(rec: Dict[str, Any], expected_cell_id: str, expected_level: int) -> Optional[str]:
    """Return None if record is valid; else a human-readable reason it isn't."""
    if rec.get("chapter") != "chapter6":
        return f"chapter != 'chapter6' (got {rec.get('chapter')!r})"
    if rec.get("cell_id") != expected_cell_id:
        return f"cell_id mismatch (got {rec.get('cell_id')!r}, expected {expected_cell_id!r})"
    if rec.get("level") != expected_level:
        return f"level mismatch (got {rec.get('level')!r}, expected {expected_level})"
    san = (rec.get("sanitization") or {}).get("status")
    if san != "ok":
        return f"sanitization.status={san!r}"
    if rec.get("scoring") is None:
        return "scoring is None"
    if rec["scoring"].get("delta_step") is None:
        return "scoring.delta_step is None"
    meta = rec.get("llm_metadata") or {}
    if meta.get("model") != EXPECTED_MODEL:
        return f"model mismatch (got {meta.get('model')!r})"
    if expected_level == 2:
        if LOCKED_RULE_FRAMING_STRING not in (rec.get("prompt") or ""):
            return "prompt missing locked-rule framing string"
    return None


# ---------------------------------------------------------------------------
# Phase 1: merge sidelined records
# ---------------------------------------------------------------------------


def _scan_sidelined_for_l2_stratified() -> Dict[Tuple[int, int], Tuple[float, Path]]:
    """For stratified_representative@L2, find the most-recent valid record at
    each (set, seed) coordinate across all sidelined dirs.

    Returns: dict (set, seed) → (mtime, src_path).
    """
    expected_cell_id = "stratified_representative@L2"
    expected_level = 2
    candidates: Dict[Tuple[int, int], List[Tuple[float, Path, Dict[str, Any]]]] = {}

    for d in SIDELINED_DIRS:
        if not d.exists():
            continue
        for path in d.glob(f"{expected_cell_id}_set*.json"):
            m = FILENAME_RE.match(path.name)
            if not m:
                continue
            key = (int(m["set"]), int(m["seed"]))
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"  [skip] {path.name}: parse error: {exc}", file=sys.stderr)
                continue
            reason = _validate_record(rec, expected_cell_id, expected_level)
            if reason:
                print(f"  [skip] {path.name}: {reason}", file=sys.stderr)
                continue
            candidates.setdefault(key, []).append(
                (path.stat().st_mtime, path, rec)
            )

    chosen: Dict[Tuple[int, int], Tuple[float, Path]] = {}
    for key, opts in candidates.items():
        opts.sort(key=lambda t: -t[0])  # most recent first
        chosen[key] = (opts[0][0], opts[0][1])
    return chosen


def merge_phase(dry_run: bool) -> Dict[str, Any]:
    """Copy chosen sidelined records into the primary dir.

    Returns a summary dict with what was found, copied, and skipped.
    """
    print("=" * 72)
    print("PHASE 1 — merge sidelined L2 stratified records")
    print("=" * 72)
    chosen = _scan_sidelined_for_l2_stratified()
    print(
        f"  found {len(chosen)} unique (set, seed) coordinates with valid "
        f"records across {len(SIDELINED_DIRS)} sidelined dirs"
    )

    existing_in_primary = _existing_coords_for_cell("stratified_representative@L2")
    print(f"  primary dir already has {len(existing_in_primary)} L2 stratified records")

    to_copy: List[Tuple[Tuple[int, int], Path]] = []
    skipped_already_in_primary: List[Tuple[int, int]] = []
    for key, (mtime, src) in sorted(chosen.items()):
        if key in existing_in_primary:
            skipped_already_in_primary.append(key)
            continue
        to_copy.append((key, src))

    print(f"  will copy {len(to_copy)} records into primary dir")
    if skipped_already_in_primary:
        print(
            f"  (skipping {len(skipped_already_in_primary)} that are "
            "already in primary)"
        )

    copied: List[Tuple[Tuple[int, int], Path, Path]] = []
    if not dry_run:
        PRIMARY_DIR.mkdir(parents=True, exist_ok=True)
        for key, src in to_copy:
            dst = PRIMARY_DIR / src.name
            shutil.copy2(src, dst)
            copied.append((key, src, dst))
            (s, e) = key
            print(
                f"  copied set={s:03d} seed={e:03d} from "
                f"{src.parent.name}/"
            )
    else:
        print("  [dry-run] no files copied")

    return {
        "chosen_coordinates": sorted(chosen.keys()),
        "copied_count": len(copied),
        "skipped_already_in_primary_count": len(skipped_already_in_primary),
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Phase 2: run only missing coordinates per cell
# ---------------------------------------------------------------------------


def _missing_coords_for_cell(strategy_name: str, level: int) -> List[Tuple[int, int]]:
    cell_id = f"{strategy_name}@L{level}"
    expected = _expected_coords_for(strategy_name)
    existing = _existing_coords_for_cell(cell_id)
    return sorted(expected - existing)


def _reference_source_for_pool(pool: CounterexampleSet) -> str:
    target = next(iter({c.reference_hash for c in pool}))
    for member in load_final_population():
        if member["code_hash"] == target:
            return member["code"]
    raise RuntimeError(f"Reference {target!r} not found in EoH final population")


def run_missing_phase(dry_run: bool, provider: str = PROVIDER) -> Dict[str, Any]:
    """For each cell, run only the missing (set, seed) coordinates."""
    print()
    print("=" * 72)
    print("PHASE 2 — run only missing coordinates per cell")
    print("=" * 72)

    pool = CounterexampleSet.from_json(POOL_PATH.read_text(encoding="utf-8"))
    h_eoh = get_h_eoh()
    reference_source = _reference_source_for_pool(pool)

    plan: List[Dict[str, Any]] = []
    for strategy_name, level in DEFAULT_CELLS:
        cell_id = f"{strategy_name}@L{level}"
        missing = _missing_coords_for_cell(strategy_name, level)
        plan.append({
            "cell_id": cell_id,
            "strategy_name": strategy_name,
            "level": level,
            "missing_count": len(missing),
            "missing": missing,
        })
        print(f"  {cell_id}: {len(missing)} missing")

    total_missing = sum(p["missing_count"] for p in plan)
    print(f"  TOTAL missing: {total_missing} calls")

    if dry_run:
        print("  [dry-run] no calls made")
        return {"plan": plan, "n_attempted": 0, "n_succeeded": 0, "n_failed_per_label": {}, "dry_run": True}

    n_attempted = 0
    n_succeeded = 0
    failure_counts: Dict[str, int] = {}
    last_call_end: Optional[float] = None

    for cell in plan:
        if cell["missing_count"] == 0:
            continue
        strategy_name = cell["strategy_name"]
        level = cell["level"]
        cell_id = cell["cell_id"]
        print()
        print(f"--- {cell_id}: running {cell['missing_count']} calls ---")
        for set_index, seed_index in cell["missing"]:
            if last_call_end is not None and INTER_CALL_SLEEP_SECONDS > 0:
                elapsed = time.perf_counter() - last_call_end
                rem = INTER_CALL_SLEEP_SECONDS - elapsed
                if rem > 0:
                    time.sleep(rem)
            try:
                record = _run_chapter6_single_proposal(
                    strategy_name=strategy_name,
                    level=level,
                    set_index=set_index,
                    seed_index=seed_index,
                    pool=pool,
                    incumbent_heuristic=h_eoh,
                    reference_source=reference_source,
                    output_dir=PRIMARY_DIR,
                    k=4,
                    provider=provider,
                    reasoning_effort=REASONING_EFFORT,
                    max_output_tokens=MAX_OUTPUT_TOKENS_BY_PROVIDER[provider],
                    timeout_seconds=TIMEOUT_SECONDS,
                )
            except Exception as exc:
                # 429 after retry-with-backoff: log and keep going.
                # DSQ pool is bursty; the next coord may succeed, and
                # any uncovered coords get picked up by re-running the
                # resume command (idempotent: skip-existing-OK).
                # Other exception types also non-fatal here for the
                # same reason — we'd rather collect partial progress
                # than crash mid-run.
                msg = str(exc)
                tag = "429" if "429" in msg or "RESOURCE_EXHAUSTED" in msg else "EXCEPTION"
                print(
                    f"  [{cell_id} set={set_index:03d} seed={seed_index:03d}] "
                    f"{tag} {type(exc).__name__}: {msg[:200]}",
                    file=sys.stderr,
                )
                failure_counts[tag] = failure_counts.get(tag, 0) + 1
                n_attempted += 1
                last_call_end = time.perf_counter()
                continue
            last_call_end = time.perf_counter()
            n_attempted += 1
            status = record["sanitization"]["status"]
            if status == "ok":
                n_succeeded += 1
                delta = (record.get("scoring") or {}).get("delta_step")
                delta_s = f"{delta:+.2f}" if isinstance(delta, (int, float)) else "n/a"
                print(
                    f"  [{cell_id} set={set_index:03d} seed={seed_index:03d}] "
                    f"sanitize=ok delta_step={delta_s}",
                    file=sys.stderr,
                )
            else:
                failure_counts[status] = failure_counts.get(status, 0) + 1
                print(
                    f"  [{cell_id} set={set_index:03d} seed={seed_index:03d}] "
                    f"sanitize={status}",
                    file=sys.stderr,
                )

    return {
        "plan": [{k: v for k, v in p.items() if k != "missing"} for p in plan],
        "n_attempted": n_attempted,
        "n_succeeded": n_succeeded,
        "n_failed_per_label": failure_counts,
        "dry_run": False,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only; don't copy files or make API calls.",
    )
    parser.add_argument(
        "--skip-merge",
        action="store_true",
        help="Skip phase 1 (merge); only run the missing-coordinates phase.",
    )
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Skip phase 2 (run); only do the merge phase.",
    )
    parser.add_argument(
        "--provider",
        default=PROVIDER,
        choices=["gemini", "vertex", "groq"],
        help=(
            "LLM provider for phase 2. 'gemini' = AI Studio API key (default); "
            "'vertex' = Vertex AI via gcloud bearer token "
            "(requires GOOGLE_CLOUD_PROJECT and either gcloud on PATH or "
            "GOOGLE_CLOUD_ACCESS_TOKEN env)."
        ),
    )
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc).isoformat()

    merge_summary: Dict[str, Any] = {}
    if not args.skip_merge:
        merge_summary = merge_phase(dry_run=args.dry_run)

    run_summary: Dict[str, Any] = {}
    if not args.skip_run:
        if args.provider == "vertex":
            # Force regional endpoint with DSQ headroom; user does not
            # need to remember to export GOOGLE_CLOUD_LOCATION.
            current = os.environ.get("GOOGLE_CLOUD_LOCATION")
            if current != VERTEX_LOCATION:
                print(
                    f"  [vertex] setting GOOGLE_CLOUD_LOCATION={VERTEX_LOCATION} "
                    f"(was {current!r}); required by DSQ-survival probe."
                )
                os.environ["GOOGLE_CLOUD_LOCATION"] = VERTEX_LOCATION
        run_summary = run_missing_phase(
            dry_run=args.dry_run, provider=args.provider
        )

    finished_at = datetime.now(timezone.utc).isoformat()

    print()
    print("=" * 72)
    print("SMART RESUME complete")
    print("=" * 72)
    if merge_summary:
        print(
            f"  merge phase: copied {merge_summary['copied_count']} "
            f"records into primary dir"
        )
    if run_summary:
        print(
            f"  run phase: {run_summary['n_succeeded']}/"
            f"{run_summary['n_attempted']} sanitize-ok; "
            f"failures={run_summary['n_failed_per_label']}"
        )
    print(f"  started:  {started_at}")
    print(f"  finished: {finished_at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
