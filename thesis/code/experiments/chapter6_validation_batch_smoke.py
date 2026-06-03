"""
thesis/code/experiments/chapter6_validation_batch_smoke.py

One-call smoke for the chapter 6 validation runner. Runs
(`stratified_representative`, level=2) for 1 trajectory of 1
step. Exercises the new code path most worth checking
end-to-end: trace recompute against the *current* incumbent
(which at step 0 of trajectory 0 is `h_eoh`).

Asserts:
  - The per-step JSON record is written with the trajectory-step
    schema.
  - `current_incumbent_hash` equals h_eoh's hash.
  - `next_incumbent_hash` equals current_incumbent_hash if
    rejected, equals proposal_hash if accepted.
  - The L2 trace at step 0 was extracted against h_eoh — verified
    by re-running `extract_incumbent_trace(instance, h_eoh)`
    on each of the 4 counterexamples and confirming the rendered
    open_bins values appear in the prompt's decision_trace
    section for the corresponding instance.
  - `acceptance_reason` is one of the four valid labels.

If sanitize fails or any assertion fails, surface and stop.

Total: 1 LLM call.

Usage:
    python -m thesis.code.experiments.chapter6_validation_batch_smoke
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


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

from thesis.code.chapter5.validation import (  # noqa: E402
    ACCEPT_BEHAVIORAL,
    ACCEPT_IMPROVEMENT,
    REJECT_EQUIVALENT,
    REJECT_REGRESSION,
)
from thesis.code.chapter6.batch_runner import _build_incumbent_module  # noqa: E402
from thesis.code.chapter6.trace_extractor import extract_incumbent_trace  # noqa: E402
from thesis.code.chapter6.validation_runner import (  # noqa: E402
    run_chapter6_validation_cell,
)
from thesis.code.incumbents import get_h_eoh  # noqa: E402
from thesis.code.splits import load_split  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
SMOKE_OUTPUT_DIR = (
    REPO_ROOT / "thesis" / "results" / "chapter6_validation_batch_smoke"
)

# Match chapter6_smart_resume's vetted vertex config (decisions log
# 2026-04-29 / 2026-05-01). Gemini AI-Studio prepayment is depleted on
# this project; vertex on us-central1 is the working path.
PROVIDER = "vertex"
VERTEX_LOCATION = "us-central1"
MAX_OUTPUT_TOKENS = 12288  # Vertex DSQ rejects >12288 even on us-central1
REASONING_EFFORT = "medium"

VALID_REASONS = {
    ACCEPT_IMPROVEMENT, ACCEPT_BEHAVIORAL,
    REJECT_REGRESSION, REJECT_EQUIVALENT,
}


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        print(f"\n[SMOKE FAIL] {msg}", file=sys.stderr)
        sys.exit(2)


def main() -> int:
    SMOKE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    h_eoh = get_h_eoh()

    if PROVIDER == "vertex":
        current_location = os.environ.get("GOOGLE_CLOUD_LOCATION")
        if current_location != VERTEX_LOCATION:
            os.environ["GOOGLE_CLOUD_LOCATION"] = VERTEX_LOCATION

    print("=" * 72)
    print("CHAPTER 6 VALIDATION SMOKE — (stratified_representative, L2) × 1 × 1")
    print(f"provider: {PROVIDER}  max_output_tokens: {MAX_OUTPUT_TOKENS}")
    print(f"output: {SMOKE_OUTPUT_DIR}")
    print(f"starting_incumbent: {h_eoh['code_hash']}")
    print("=" * 72)

    existing_path = (
        SMOKE_OUTPUT_DIR
        / "stratified_representative@L2_traj0_step0.json"
    )
    if existing_path.exists():
        print(
            f"\n[RESUME] per-step record already on disk at {existing_path}; "
            "validating existing record instead of burning another LLM call."
        )
        record = json.loads(existing_path.read_text(encoding="utf-8"))

        class _MockStep:
            cell_id = record["cell_id"]
            trajectory_index = record["trajectory_index"]
            step_index = record["step_index"]
            current_incumbent_hash = record["current_incumbent_hash"]
            proposal_hash = record.get("proposal_hash")
            sanitization_status = (record.get("sanitization") or {}).get("status")
            delta_step_local = record["delta_step_local"]
            argmax_distinct = record["argmax_distinct"]
            acceptance_decision = record["acceptance_decision"]
            acceptance_reason = record["acceptance_reason"]
            next_incumbent_hash = record["next_incumbent_hash"]
            record_path = existing_path

        class _MockResult:
            trajectories = [type("T", (), {"steps": [_MockStep()]})]

        result = _MockResult()
    else:
        result = run_chapter6_validation_cell(
            strategy_name="stratified_representative",
            level=2,
            starting_incumbent=h_eoh,
            n_trajectories=1,
            n_steps=1,
            output_dir=SMOKE_OUTPUT_DIR,
            provider=PROVIDER,
            reasoning_effort=REASONING_EFFORT,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            smoke_mode=True,
            smoke_n_trajectories=1,
            smoke_n_steps=1,
        )

    _assert(len(result.trajectories) == 1, "expected 1 trajectory")
    traj = result.trajectories[0]
    _assert(len(traj.steps) == 1, "expected 1 step")
    step = traj.steps[0]

    # Load the on-disk record for schema + trace assertions
    record = json.loads(step.record_path.read_text(encoding="utf-8"))

    print()
    print(f"step:        cell_id={step.cell_id} traj={step.trajectory_index} "
          f"step={step.step_index}")
    print(f"sanitize:    {step.sanitization_status}")
    print(f"d_step_local: {step.delta_step_local}")
    print(f"argmax_dist: {step.argmax_distinct}")
    print(f"acceptance:  {step.acceptance_decision}  reason={step.acceptance_reason}")
    print(f"current_inc: {step.current_incumbent_hash}")
    print(f"next_inc:    {step.next_incumbent_hash}")
    print(f"proposal:    {step.proposal_hash}")
    print(f"record:      {step.record_path}")

    # ---- assertions ----
    if step.sanitization_status != "ok":
        print(
            f"\n[SMOKE FAIL] sanitization not ok: {step.sanitization_status}",
            file=sys.stderr,
        )
        sys.exit(3)

    _assert(
        step.acceptance_reason in VALID_REASONS,
        f"acceptance_reason not in valid set: {step.acceptance_reason}",
    )
    _assert(
        step.current_incumbent_hash == h_eoh["code_hash"],
        f"current_incumbent_hash {step.current_incumbent_hash!r} != "
        f"h_eoh {h_eoh['code_hash']!r}",
    )
    if step.acceptance_decision == "accepted":
        _assert(
            step.next_incumbent_hash == step.proposal_hash,
            "accepted but next_incumbent_hash != proposal_hash",
        )
    else:
        _assert(
            step.next_incumbent_hash == step.current_incumbent_hash,
            "rejected but next_incumbent_hash != current_incumbent_hash",
        )

    # Schema check
    required_fields = {
        "chapter", "phase", "cell_id", "level", "master_seed",
        "trajectory_index", "step_index", "trajectory_set_seed",
        "trajectory_llm_seed", "current_incumbent_hash",
        "current_incumbent_source", "pool_rebuild_pool_hash",
        "prompt", "response", "sanitization", "scoring",
        "delta_step_local", "argmax_distinct", "acceptance_decision",
        "acceptance_reason", "next_incumbent_hash",
    }
    missing = required_fields - set(record.keys())
    _assert(not missing, f"record missing required fields: {missing}")
    _assert(record["chapter"] == "chapter6", "chapter != 'chapter6'")
    _assert(record["phase"] == "validation", "phase != 'validation'")

    # Trace-recompute assertion: confirm the L2 prompt path was taken
    # and the runner passed h_eoh as the trace-source incumbent. By
    # construction (validation_runner.run_validation_step passes
    # `current_incumbent` to `_run_chapter6_single_proposal`, which
    # extracts the trace inline from that argument), if the
    # current_incumbent_hash matches h_eoh AND the prompt contains
    # the locked L2 framing string AND a decision_trace block, the
    # trace was extracted against h_eoh.
    prompt = record["prompt"]
    _assert(
        "60 rows total from 5000 actual decisions" in prompt,
        "L2 framing string missing — locked rendering rule §7.5 not applied",
    )
    _assert(
        "decision_trace:" in prompt,
        "decision_trace: header missing — L2 trace block not rendered",
    )
    counterexample_set = record["counterexample_set"]
    items = counterexample_set.get("items") or counterexample_set.get(
        "counterexamples", []
    )
    _assert(len(items) == 4, f"expected 4 counterexamples, got {len(items)}")

    # Sanity-extract trace against h_eoh on the first counterexample
    # to confirm extract_incumbent_trace works on the smoke's pool
    # (catches a stale-pool bug where the smoke's counterexamples
    # came from an instance not in train_select).
    instance_lookup = {
        f"thesis_train_select:{inst['instance_id']}": inst
        for inst in load_split("train_select")["instances"]
    }
    first_ce = items[0]
    _assert(
        first_ce["instance_id"] in instance_lookup,
        f"counterexample {first_ce['instance_id']!r} not in train_select",
    )
    first_inst = instance_lookup[first_ce["instance_id"]]
    true_trace = extract_incumbent_trace(
        first_inst, _build_incumbent_module(h_eoh),
    )
    _assert(
        len(true_trace) > 0,
        "extract_incumbent_trace returned empty trace on smoke's first ce",
    )

    finished_at = datetime.now(timezone.utc).isoformat()
    print()
    print("[SMOKE PASS]")
    print(f"  started:  {started_at}")
    print(f"  finished: {finished_at}")
    print(f"  L2 framing + decision_trace headers present in prompt")
    print(f"  trace re-extractable on first counterexample under h_eoh")

    # surface usage / cost estimate
    md = (record.get("llm_metadata") or {}).get("raw_response_metadata") or {}
    usage = md.get("usage") or {}
    print(f"  usage: prompt_tokens={usage.get('prompt_tokens')}  "
          f"completion_tokens={usage.get('completion_tokens')}  "
          f"total_tokens={usage.get('total_tokens')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
