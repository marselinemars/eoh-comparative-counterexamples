"""
thesis/code/experiments/chapter4_smoke_calibration.py

Two-call smoke calibration for the chapter-4 §4.5 control cells
(E1 no-reference + E2 gap-only). Calls each cell once at the
production-locked settings to verify (a) prompt size, (b)
sanitization, (c) Δ_step pipeline end-to-end, on a single
CounterexampleSet at set_index=0 (the bit-identical-to-chapter-5
set verified in commit 966088c).

Stopping rules:
  - HTTP 400 on either call: STOP.
  - Latency > 600s on either call: STOP.
  - Sanitization failure: retry once (chapter-5 retry policy);
    if the retry also fails, record both attempts and STOP.

Budget: 2 LLM calls (one retry possible per cell).

Outputs (committed):
  thesis/artifacts/chapter4_noref_smoke.json
  thesis/artifacts/chapter4_gaponly_smoke.json

Intermediate per-call provenance records land under
  thesis/results/chapter4_noref_smoke/
  thesis/results/chapter4_gaponly_smoke/
which are gitignored. The committed smoke artifact summarizes
the essential fields without duplicating the full provenance.

Usage:
    python -m thesis.code.experiments.chapter4_smoke_calibration
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


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

from thesis.code.chapter4_gaponly.batch_runner import (  # noqa: E402
    run_single_proposal_gaponly,
)
from thesis.code.chapter4_noref.batch_runner import (  # noqa: E402
    run_single_proposal_noref,
)
from thesis.code.chapter5.analysis import (  # noqa: E402
    compute_h_eoh_per_instance_bins,
    is_argmax_equivalent_to_h_eoh,
)
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import get_h_eoh  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
POOL_PATH = REPO / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
NOREF_RESULTS_DIR = REPO / "thesis" / "results" / "chapter4_noref_smoke"
GAPONLY_RESULTS_DIR = REPO / "thesis" / "results" / "chapter4_gaponly_smoke"
NOREF_ARTIFACT = REPO / "thesis" / "artifacts" / "chapter4_noref_smoke.json"
GAPONLY_ARTIFACT = REPO / "thesis" / "artifacts" / "chapter4_gaponly_smoke.json"

PROVIDER = "vertex"  # Per decisions-log 2026-05-05: Gemini 2.5 Pro via Vertex AI
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 32768

SET_INDEX = 0
SEED_INDEX = 0


def _extract_prompt_tokens(record: Dict[str, Any]) -> Optional[int]:
    md = (record.get("llm_metadata") or {}).get("raw_response_metadata") or {}
    usage = md.get("usage") or {}
    pt = usage.get("prompt_tokens") or usage.get("input_tokens")
    return int(pt) if pt is not None else None


def _wall_clock_seconds(record: Dict[str, Any]) -> Optional[float]:
    ts = record.get("timestamps") or {}
    s, f = ts.get("started_at"), ts.get("finished_at")
    if not (s and f):
        return None
    from datetime import datetime
    try:
        return round(
            (datetime.fromisoformat(f) - datetime.fromisoformat(s))
            .total_seconds(),
            2,
        )
    except Exception:
        return None


def _compute_argmax_equivalence(record: Dict[str, Any]) -> Optional[bool]:
    """Use the canonical chapter-5 helper (decisions-log
    2026-05-01: argmax-equivalence rate measurement locked to
    is_argmax_equivalent_to_h_eoh)."""
    scoring = record.get("scoring") or {}
    proposal_step = scoring.get("per_instance_bins_proposal_train_step")
    if not proposal_step:
        return None
    h_eoh_step = compute_h_eoh_per_instance_bins("train_step")
    return is_argmax_equivalent_to_h_eoh(proposal_step, h_eoh_step)


def _build_smoke_summary(
    cell_id: str,
    record: Dict[str, Any],
    wall_clock_seconds: float,
) -> Dict[str, Any]:
    sanitize_status = (record.get("sanitization") or {}).get("status")
    scoring = record.get("scoring") or {}
    return {
        "cell_id": cell_id,
        "set_index": record.get("set_index"),
        "seed_index": record.get("seed_index"),
        "seed_namespace": record.get("seed_namespace"),
        "prompt": record.get("prompt"),
        "prompt_chars": len(record.get("prompt") or ""),
        "prompt_tokens": _extract_prompt_tokens(record),
        "raw_response": record.get("raw_response"),
        "sanitize_status": sanitize_status,
        "sanitize_error": (record.get("sanitization") or {}).get("error"),
        "sanitized_proposal_code": (
            (record.get("sanitization") or {}).get("cleaned_code")
        ),
        "proposal_hash": record.get("proposal_hash"),
        "delta_step": scoring.get("delta_step"),
        "delta_gate": scoring.get("delta_gate"),
        "mean_bins_h_eoh_train_step": scoring.get("mean_bins_h_eoh_train_step"),
        "mean_bins_proposal_train_step": scoring.get(
            "mean_bins_proposal_train_step"
        ),
        "argmax_equivalent_to_h_eoh_on_train_step": (
            _compute_argmax_equivalence(record)
        ),
        "wall_clock_seconds": wall_clock_seconds,
        "llm_metadata": record.get("llm_metadata"),
        "counterexample_set": record.get("counterexample_set"),
        "incumbent_hash": record.get("incumbent_hash"),
        "reference_hash": record.get("reference_hash"),
    }


def _run_cell(
    cell_label: str,
    run_fn,
    results_dir: Path,
    artifact_path: Path,
    pool: CounterexampleSet,
    h_eoh: Dict[str, Any],
) -> Dict[str, Any]:
    """Run one smoke call. Returns the smoke-summary dict. Writes
    the artifact at artifact_path."""
    results_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{cell_label}] launching set_index={SET_INDEX} "
          f"seed_index={SEED_INDEX} ...", flush=True)
    t0 = time.time()
    record = run_fn(
        set_index=SET_INDEX,
        seed_index=SEED_INDEX,
        pool=pool,
        incumbent_heuristic=h_eoh,
        output_dir=results_dir,
        provider=PROVIDER,
        reasoning_effort=REASONING_EFFORT,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    wall = round(time.time() - t0, 2)
    summary = _build_smoke_summary(cell_label, record, wall)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(
        f"[{cell_label}] sanitize_status={summary['sanitize_status']}  "
        f"prompt_chars={summary['prompt_chars']}  "
        f"prompt_tokens={summary['prompt_tokens']}  "
        f"delta_step={summary['delta_step']}  "
        f"argmax_eq={summary['argmax_equivalent_to_h_eoh_on_train_step']}  "
        f"wall={summary['wall_clock_seconds']}s"
    )
    return summary


def main() -> int:
    pool = CounterexampleSet.from_json(
        POOL_PATH.read_text(encoding="utf-8")
    )
    h_eoh = get_h_eoh()
    print(f"pool sha256[:12] = f89434911301; h_eoh = {h_eoh['code_hash']}")

    e1 = _run_cell(
        cell_label="chapter4_noref",
        run_fn=run_single_proposal_noref,
        results_dir=NOREF_RESULTS_DIR,
        artifact_path=NOREF_ARTIFACT,
        pool=pool,
        h_eoh=h_eoh,
    )

    e2 = _run_cell(
        cell_label="chapter4_gaponly",
        run_fn=run_single_proposal_gaponly,
        results_dir=GAPONLY_RESULTS_DIR,
        artifact_path=GAPONLY_ARTIFACT,
        pool=pool,
        h_eoh=h_eoh,
    )

    print()
    print("=" * 72)
    print("SMOKE CALIBRATION SUMMARY")
    print("=" * 72)
    for cell, s in (("E1 noref", e1), ("E2 gaponly", e2)):
        print(
            f"  {cell:<12} sanitize={s['sanitize_status']:<10} "
            f"tokens={s['prompt_tokens']}  "
            f"delta_step={s['delta_step']}  "
            f"argmax_eq={s['argmax_equivalent_to_h_eoh_on_train_step']}  "
            f"wall={s['wall_clock_seconds']}s"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
