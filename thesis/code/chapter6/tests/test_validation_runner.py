"""Tests for thesis/code/chapter6/validation_runner.py.

All hermetic — no live LLM calls. Tests inject a fake step
runner into the cell driver, or call helpers directly with
fixture inputs, and assert on trajectory state, schema, and
the seed namespace.

Run:
    python -m pytest thesis/code/chapter6/tests/test_validation_runner.py -v
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from thesis.code.chapter5.seeds import (
    trajectory_set_seed as ch5_trajectory_set_seed,
)
from thesis.code.chapter5.validation import (
    ACCEPT_BEHAVIORAL,
    ACCEPT_IMPROVEMENT,
    REJECT_EQUIVALENT,
    REJECT_REGRESSION,
    should_accept_proposal,
)
from thesis.code.chapter6.batch_runner import (
    _build_incumbent_module,
    set_seed_ch6,
    trajectory_llm_seed_ch6,
    trajectory_set_seed_ch6,
)
from thesis.code.chapter6.trace_extractor import extract_incumbent_trace
from thesis.code.chapter6.validation_runner import (
    REJECT_SANITIZE_FAILED,
    StepRecord,
    run_chapter6_validation_cell,
    run_validation_step,
)
from thesis.code.incumbents import get_h_eoh
from thesis.code.splits import load_split

REPO_ROOT = Path(__file__).resolve().parents[4]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_BEST_FIT_SOURCE = (
    "import numpy as np\n"
    "def score(item, bins):\n"
    "    return -np.asarray(bins, dtype=float)\n"
)
_BEST_FIT_HASH = "fake_best_fit_hash_aaaa"
_BEST_FIT = {
    "code": _BEST_FIT_SOURCE,
    "code_hash": _BEST_FIT_HASH,
    "algorithm": "fake_best_fit",
}

_WORST_FIT_SOURCE = (
    "import numpy as np\n"
    "def score(item, bins):\n"
    "    return np.asarray(bins, dtype=float)\n"
)
_WORST_FIT_HASH = "fake_worst_fit_hash_bbbb"


# ---------------------------------------------------------------------------
# Fake step runner: writes a per-step JSON in the trajectory-step schema
# and returns a StepRecord. Driven by a `scorebook` mapping
# (cell_id, traj, step) -> (delta_step_local, accept_decision, reason,
# proposal_hash, proposal_source, sanitize_status).
# ---------------------------------------------------------------------------


class _FakeStepRunner:
    def __init__(self, scorebook: Dict[Tuple[str, int, int], Dict[str, Any]]) -> None:
        self.scorebook = scorebook
        self.received_incumbent_hashes: List[str] = []
        self.received_calls: List[Dict[str, Any]] = []

    def __call__(
        self,
        *,
        strategy_name: str,
        level: int,
        trajectory_index: int,
        step_index: int,
        current_incumbent: Dict[str, Any],
        output_dir: Path,
        provider: str = "gemini",
        reasoning_effort: Any = "medium",
        max_output_tokens: Any = 32768,
        timeout_seconds: float = 300.0,
        pool_cache: Any = None,
        call_llm_fn: Any = None,
    ) -> StepRecord:
        cell_id = f"{strategy_name}@L{level}"
        key = (cell_id, trajectory_index, step_index)
        cfg = self.scorebook[key]
        proposal_hash = cfg["proposal_hash"]
        proposal_source = cfg["proposal_source"]
        san_status = cfg.get("sanitize_status", "ok")
        delta_local = cfg.get("delta_step_local", 0.0)
        argmax_distinct = cfg.get("argmax_distinct", True)
        decision = cfg.get("decision", "accepted")
        reason = cfg.get("reason", ACCEPT_IMPROVEMENT)

        self.received_incumbent_hashes.append(current_incumbent["code_hash"])
        self.received_calls.append({
            "cell_id": cell_id,
            "trajectory_index": trajectory_index,
            "step_index": step_index,
            "current_incumbent_hash": current_incumbent["code_hash"],
        })

        next_hash = (
            proposal_hash if decision == "accepted"
            else current_incumbent["code_hash"]
        )
        record = {
            "chapter": "chapter6",
            "phase": "validation",
            "cell_id": cell_id,
            "level": level,
            "master_seed": 20_260_424,
            "trajectory_index": trajectory_index,
            "step_index": step_index,
            "trajectory_set_seed": trajectory_set_seed_ch6(
                strategy_name, trajectory_index, step_index, level,
            ),
            "trajectory_llm_seed": trajectory_llm_seed_ch6(
                strategy_name, trajectory_index, step_index, level,
            ),
            "current_incumbent_hash": current_incumbent["code_hash"],
            "current_incumbent_source": current_incumbent["code"],
            "pool_rebuild_pool_hash": "fake_pool_hash",
            "prompt": "fake_prompt",
            "response": "fake_response",
            "proposal_hash": proposal_hash,
            "sanitization": {
                "status": san_status,
                "cleaned_code": proposal_source if san_status == "ok" else None,
            },
            "scoring": cfg.get("scoring") or {
                "delta_step": delta_local,
            },
            "delta_step_local": delta_local,
            "argmax_distinct": argmax_distinct,
            "acceptance_decision": decision,
            "acceptance_reason": reason,
            "next_incumbent_hash": next_hash,
        }
        out_path = (
            Path(output_dir)
            / f"{cell_id}_traj{trajectory_index}_step{step_index}.json"
        )
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(record), encoding="utf-8")

        return StepRecord(
            cell_id=cell_id,
            trajectory_index=trajectory_index,
            step_index=step_index,
            current_incumbent_hash=current_incumbent["code_hash"],
            proposal_hash=proposal_hash,
            sanitization_status=san_status,
            delta_step_local=delta_local,
            argmax_distinct=argmax_distinct,
            acceptance_decision=decision,
            acceptance_reason=reason,
            next_incumbent_hash=next_hash,
            record_path=out_path,
        )


# ---------------------------------------------------------------------------
# Test 1 — Trajectory state propagation under acceptance
# ---------------------------------------------------------------------------


def test_state_propagation_accept(tmp_path: Path) -> None:
    """When step 0 is accepted, step 1's current_incumbent_hash equals
    step 0's proposal_hash. When step 1 is also accepted, step 2's
    current_incumbent_hash equals step 1's proposal_hash."""
    h_eoh = get_h_eoh()
    cell_id = "stratified_representative@L2"
    scorebook = {
        (cell_id, 0, 0): {
            "proposal_hash": "p0",
            "proposal_source": _BEST_FIT_SOURCE,  # accept-source
            "decision": "accepted", "reason": ACCEPT_IMPROVEMENT,
            "delta_step_local": 1.0,
        },
        (cell_id, 0, 1): {
            "proposal_hash": "p1",
            "proposal_source": _WORST_FIT_SOURCE,
            "decision": "accepted", "reason": ACCEPT_IMPROVEMENT,
            "delta_step_local": 1.0,
        },
        (cell_id, 0, 2): {
            "proposal_hash": "p2",
            "proposal_source": _BEST_FIT_SOURCE,
            "decision": "accepted", "reason": ACCEPT_IMPROVEMENT,
            "delta_step_local": 1.0,
        },
    }
    fake = _FakeStepRunner(scorebook)
    result = run_chapter6_validation_cell(
        strategy_name="stratified_representative",
        level=2,
        starting_incumbent=h_eoh,
        n_trajectories=1,
        n_steps=3,
        output_dir=tmp_path,
        inter_call_sleep_seconds=0.0,
        _run_step_fn=fake,
    )
    seen = fake.received_incumbent_hashes
    assert seen[0] == h_eoh["code_hash"]
    assert seen[1] == "p0"
    assert seen[2] == "p1"
    assert result.trajectories[0].final_incumbent_hash == "p2"


# ---------------------------------------------------------------------------
# Test 2 — Trajectory state propagation under rejection
# ---------------------------------------------------------------------------


def test_state_propagation_reject(tmp_path: Path) -> None:
    """When step 0 is rejected, step 1's current_incumbent_hash is
    still h_eoh. The trajectory continues from h_eoh."""
    h_eoh = get_h_eoh()
    cell_id = "worst_plus_best@L1"
    scorebook = {
        (cell_id, 0, 0): {
            "proposal_hash": "p_bad",
            "proposal_source": _BEST_FIT_SOURCE,
            "decision": "rejected", "reason": REJECT_REGRESSION,
            "delta_step_local": -10.0,
        },
        (cell_id, 0, 1): {
            "proposal_hash": "p_also_bad",
            "proposal_source": _BEST_FIT_SOURCE,
            "decision": "rejected", "reason": REJECT_REGRESSION,
            "delta_step_local": -5.0,
        },
    }
    fake = _FakeStepRunner(scorebook)
    result = run_chapter6_validation_cell(
        strategy_name="worst_plus_best",
        level=1,
        starting_incumbent=h_eoh,
        n_trajectories=1,
        n_steps=2,
        output_dir=tmp_path,
        inter_call_sleep_seconds=0.0,
        _run_step_fn=fake,
    )
    seen = fake.received_incumbent_hashes
    assert seen[0] == h_eoh["code_hash"]
    assert seen[1] == h_eoh["code_hash"], "rejection must keep incumbent unchanged"
    assert result.trajectories[0].final_incumbent_hash == h_eoh["code_hash"]


# ---------------------------------------------------------------------------
# Test 3 — Acceptance-reason labeling
# ---------------------------------------------------------------------------


def test_acceptance_reason_labels() -> None:
    """should_accept_proposal returns the four labels per their
    Δ_step_local × argmax-distinctness conditions. We exercise all
    four cells of the truth table directly."""
    # (a) Δ_local > 0 AND argmax-distinct -> accepted_improvement
    accepted, reason = should_accept_proposal([10, 10, 10], [11, 11, 11])
    assert accepted and reason == ACCEPT_IMPROVEMENT

    # (b) Δ_local == 0 AND argmax-distinct -> accepted_behavioral_change
    accepted, reason = should_accept_proposal([10, 11, 9], [9, 11, 10])
    # Sums equal (30 == 30); per-instance differs.
    assert accepted and reason == ACCEPT_BEHAVIORAL

    # (c) Δ_local < 0 -> rejected_regression
    accepted, reason = should_accept_proposal([12, 12, 12], [11, 11, 11])
    assert not accepted and reason == REJECT_REGRESSION

    # (d) Δ_local == 0 AND NOT argmax-distinct -> rejected_argmax_equivalent
    accepted, reason = should_accept_proposal([11, 11, 11], [11, 11, 11])
    assert not accepted and reason == REJECT_EQUIVALENT


# ---------------------------------------------------------------------------
# Test 4 — L2 trace re-extracted per step (against the current incumbent)
# ---------------------------------------------------------------------------


def test_l2_trace_differs_across_incumbents() -> None:
    """The §8.2 trace-recompute extension is implemented by passing
    `current_incumbent` as `incumbent_heuristic` to
    `_run_chapter6_single_proposal`, which extracts the trace from
    that argument. Underlying primitive: extract_incumbent_trace
    must produce different traces for different incumbents on the
    same instance (otherwise the trace-recompute is a no-op)."""
    split = load_split("train_select")
    inst = split["instances"][0]

    h_eoh = get_h_eoh()
    h_eoh_module = _build_incumbent_module(h_eoh)
    bf_module = _build_incumbent_module(_BEST_FIT)

    trace_h_eoh = extract_incumbent_trace(inst, h_eoh_module)
    trace_bf = extract_incumbent_trace(inst, bf_module)

    assert len(trace_h_eoh) == len(trace_bf), \
        "traces must align in arrival count"
    diffs = sum(
        1 for a, b in zip(trace_h_eoh, trace_bf)
        if (getattr(a, "open_bins", None) != getattr(b, "open_bins", None)
            or getattr(a, "chosen_bin", None) != getattr(b, "chosen_bin", None))
    )
    assert diffs > 0, (
        "extract_incumbent_trace produced byte-identical traces for two "
        "different incumbents on the same instance — trace recompute "
        "would be a no-op"
    )


# ---------------------------------------------------------------------------
# Test 5 — Pool rebuild per step
# ---------------------------------------------------------------------------


def test_pool_rebuild_differs_across_incumbents() -> None:
    """rebuild_pool_against_incumbent must produce different gap values
    when given a different incumbent (since gap = candidate_bins -
    reference_bins, and candidate_bins depends on the incumbent).
    Catches a bug where a step reuses the prior step's pool."""
    from thesis.code.chapter5.validation import rebuild_pool_against_incumbent
    h_eoh = get_h_eoh()
    pool_eoh = rebuild_pool_against_incumbent(
        incumbent=h_eoh,
        reference_hash="62a2846c597e",
        split_name="train_select",
    )
    pool_bf = rebuild_pool_against_incumbent(
        incumbent=_BEST_FIT,
        reference_hash="62a2846c597e",
        split_name="train_select",
    )
    gaps_eoh = [c.gap for c in pool_eoh.items]
    gaps_bf = [c.gap for c in pool_bf.items]
    assert gaps_eoh != gaps_bf, (
        "pool gap vector identical across two distinct incumbents — "
        "pool rebuild may be reusing cached results across incumbents"
    )


# ---------------------------------------------------------------------------
# Test 6 — Seed namespace ch6:traj is disjoint from ch6:set and ch5:traj
# ---------------------------------------------------------------------------


def test_trajectory_seed_namespace_disjointness() -> None:
    """trajectory_set_seed_ch6 and trajectory_llm_seed_ch6 use the
    `ch6:traj:` prefix; their values differ from both the primary
    `ch6:set:` namespace and the ch5 `ch5:traj:` namespace."""
    s_traj_ch6 = trajectory_set_seed_ch6(
        "stratified_representative", 0, 0, level=1,
    )
    s_set_ch6 = set_seed_ch6("stratified_representative", 0, level=1)
    s_traj_ch5 = ch5_trajectory_set_seed(
        "stratified_representative", 0, 0,
    )

    assert s_traj_ch6 != s_set_ch6, (
        "ch6:traj:set and ch6:set namespaces collide for "
        "(strategy=0, traj=0=set=0, step=0=seed=0, level=1)"
    )
    assert s_traj_ch6 != s_traj_ch5, (
        "ch6:traj:set and ch5:traj:set namespaces collide"
    )

    l_traj_ch6 = trajectory_llm_seed_ch6(
        "stratified_representative", 0, 0, level=1,
    )
    # llm seed must also be different from a deterministic set seed.
    assert l_traj_ch6 != s_traj_ch6


# ---------------------------------------------------------------------------
# Test 7 — Per-step record schema (real run_validation_step path)
# ---------------------------------------------------------------------------


def _fake_proposal_runner_factory(
    proposal_source: str,
    proposal_hash: str,
    sanitize_ok: bool = True,
):
    """Returns a callable mimicking _run_chapter6_single_proposal."""
    def _runner(
        *,
        strategy_name: str,
        level: int,
        set_index: int,
        seed_index: int,
        pool: Any,
        incumbent_heuristic: Dict[str, Any],
        reference_source: str,
        output_dir: Path,
        k: int,
        provider: str,
        reasoning_effort: Any,
        max_output_tokens: Any,
        timeout_seconds: float,
        call_llm_fn: Any = None,
        set_seed_override: Optional[int] = None,
        llm_seed_override: Optional[int] = None,
        write_record: bool = True,
    ) -> Dict[str, Any]:
        cell_id = f"{strategy_name}@L{level}"
        sanitization = {
            "status": "ok" if sanitize_ok else "failed_extraction",
            "cleaned_code": proposal_source if sanitize_ok else None,
        }
        scoring = (
            {
                "delta_step": 1.0, "delta_gate": 0.5,
                "per_instance_bins_proposal_train_step": [
                    int(b - 1) for b in [
                        2046, 2046, 2046, 2046, 2046, 2046, 2046, 2046, 2046,
                        2046, 2046, 2046, 2046, 2046, 2046, 2046, 2046, 2046,
                        2046, 2046, 2046, 2046, 2046, 2046, 2046, 2046, 2046,
                        2046, 2046, 2046,
                    ]
                ],
                "per_instance_bins_proposal_train_gate": [],
                "mean_bins_h_eoh_train_step": 2046.0,
                "mean_bins_proposal_train_step": 2045.0,
                "mean_bins_h_eoh_train_gate": 2046.0,
                "mean_bins_proposal_train_gate": 2046.0,
            }
            if sanitize_ok else None
        )
        return {
            "chapter": "chapter6",
            "cell_id": cell_id,
            "level": level,
            "master_seed": 20_260_424,
            "provider": provider,
            "strategy_name": strategy_name,
            "set_index": set_index,
            "seed_index": seed_index,
            "set_seed": set_seed_override or 0,
            "llm_seed": llm_seed_override or 0,
            "k": k,
            "counterexample_set": {"items": [], "schema_version": 1},
            "incumbent_hash": incumbent_heuristic["code_hash"],
            "reference_hash": "62a2846c597e",
            "proposal_hash": proposal_hash if sanitize_ok else None,
            "prompt": "fake_prompt",
            "raw_response": "fake_response",
            "llm_metadata": {},
            "sanitization": sanitization,
            "scoring": scoring,
            "trace_summary": None,
        }
    return _runner


def test_per_step_record_schema(tmp_path: Path, monkeypatch) -> None:
    """run_validation_step writes a per-step JSON with all spec'd
    fields populated and typed correctly."""
    h_eoh = get_h_eoh()
    fake_runner = _fake_proposal_runner_factory(
        proposal_source=_BEST_FIT_SOURCE,
        proposal_hash="proposal_xyz",
        sanitize_ok=True,
    )
    step = run_validation_step(
        strategy_name="stratified_representative",
        level=2,
        trajectory_index=0,
        step_index=0,
        current_incumbent=h_eoh,
        output_dir=tmp_path,
        inter_call_sleep_seconds=0.0
        if False else 0.0,  # keep signature compat; ignored at step level
        _run_proposal_fn=fake_runner,
    ) if False else run_validation_step(
        strategy_name="stratified_representative",
        level=2,
        trajectory_index=0,
        step_index=0,
        current_incumbent=h_eoh,
        output_dir=tmp_path,
        _run_proposal_fn=fake_runner,
    )

    assert step.record_path.exists()
    record = json.loads(step.record_path.read_text(encoding="utf-8"))

    required = {
        "chapter", "phase", "cell_id", "level", "master_seed",
        "trajectory_index", "step_index", "trajectory_set_seed",
        "trajectory_llm_seed", "current_incumbent_hash",
        "current_incumbent_source", "pool_rebuild_pool_hash",
        "prompt", "response", "sanitization", "scoring",
        "delta_step_local", "argmax_distinct", "acceptance_decision",
        "acceptance_reason", "next_incumbent_hash",
    }
    missing = required - set(record.keys())
    assert not missing, f"record missing fields: {missing}"

    assert record["chapter"] == "chapter6"
    assert record["phase"] == "validation"
    assert record["cell_id"] == "stratified_representative@L2"
    assert record["level"] == 2
    assert isinstance(record["delta_step_local"], (int, float))
    assert isinstance(record["argmax_distinct"], bool)
    assert record["acceptance_decision"] in ("accepted", "rejected")
    assert record["acceptance_reason"] in (
        ACCEPT_IMPROVEMENT, ACCEPT_BEHAVIORAL,
        REJECT_REGRESSION, REJECT_EQUIVALENT,
        REJECT_SANITIZE_FAILED,
    )
    if record["acceptance_decision"] == "accepted":
        assert record["next_incumbent_hash"] == record["proposal_hash"]
    else:
        assert (
            record["next_incumbent_hash"] == record["current_incumbent_hash"]
        )
