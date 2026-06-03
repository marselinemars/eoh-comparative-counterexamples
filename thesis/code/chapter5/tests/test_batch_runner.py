"""Tests for thesis/code/chapter5/batch_runner.py."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from thesis.code.chapter5.batch_runner import (
    DEFAULT_STRATEGIES,
    run_primary_batch,
)
from thesis.code.counterexample import CounterexampleSet

REPO_ROOT = Path(__file__).resolve().parents[4]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)


def _load_pool() -> CounterexampleSet:
    return CounterexampleSet.from_json(
        POOL_PATH.read_text(encoding="utf-8")
    )


class _FakeRunSingleProposal:
    """Records each call and writes a trivial provenance JSON per
    (strategy, set, seed) triple. Never touches the network."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def __call__(
        self,
        strategy_name: str,
        set_index: int,
        seed_index: int,
        pool: CounterexampleSet,
        incumbent_heuristic: Dict[str, Any],
        output_dir: Path,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        self.calls.append({
            "strategy_name": strategy_name,
            "set_index": set_index,
            "seed_index": seed_index,
            "kwargs": dict(kwargs),
        })
        out = (
            output_dir
            / f"{strategy_name}_{set_index}_{seed_index}.json"
        )
        record = {
            "strategy_name": strategy_name,
            "set_index": set_index,
            "seed_index": seed_index,
            "sanitization": {"status": "ok"},
            "proposal_hash": f"hash_{strategy_name}_{set_index}_{seed_index}",
        }
        out.write_text(json.dumps(record), encoding="utf-8")
        return record


_FAKE_INCUMBENT = {
    "code": "import numpy as np\ndef score(i, b): return b\n",
    "code_hash": "abcdef123456",
    "algorithm": "fake",
}


def test_batch_runner_respects_strategies_kwarg(tmp_path: Path):
    """strategies=['worst_only','worst_plus_best'] runs exactly those
    two strategies (both deterministic → 60 calls each = 120 total)."""
    fake = _FakeRunSingleProposal()
    summary = run_primary_batch(
        pool=_load_pool(),
        incumbent_heuristic=_FAKE_INCUMBENT,
        output_dir=tmp_path,
        strategies=["worst_only", "worst_plus_best"],
        inter_call_sleep_seconds=0.0,
        reasoning_effort="medium",
        max_output_tokens=32768,
        _run_single_proposal=fake,
    )
    assert len(fake.calls) == 120, fake.calls[:3]
    seen = {c["strategy_name"] for c in fake.calls}
    assert seen == {"worst_only", "worst_plus_best"}
    # Deterministic allocation: set_index==0 for all.
    assert all(c["set_index"] == 0 for c in fake.calls)
    assert summary["settings"]["strategies"] == [
        "worst_only", "worst_plus_best"
    ]
    assert summary["settings"]["reasoning_effort"] == "medium"
    assert summary["settings"]["max_output_tokens"] == 32768
    assert summary["n_calls_this_run"] == 120
    assert summary["n_skipped_existing"] == 0


def test_batch_runner_default_strategies_produce_360_calls(tmp_path: Path):
    """With strategies=None the default six strategies produce 60
    calls each = 360 total (3 det × 60 + 3 stoch × 20 × 3)."""
    fake = _FakeRunSingleProposal()
    run_primary_batch(
        pool=_load_pool(),
        incumbent_heuristic=_FAKE_INCUMBENT,
        output_dir=tmp_path,
        inter_call_sleep_seconds=0.0,
        _run_single_proposal=fake,
    )
    assert len(fake.calls) == 360
    # By strategy
    per_strat: Dict[str, int] = {}
    for c in fake.calls:
        per_strat[c["strategy_name"]] = (
            per_strat.get(c["strategy_name"], 0) + 1
        )
    for s in DEFAULT_STRATEGIES:
        assert per_strat[s] == 60, (s, per_strat)


def test_batch_runner_writes_progress_json(tmp_path: Path):
    """progress.json appears in output_dir, updates per call, and
    contains settings + n_calls_this_run."""
    fake = _FakeRunSingleProposal()
    run_primary_batch(
        pool=_load_pool(),
        incumbent_heuristic=_FAKE_INCUMBENT,
        output_dir=tmp_path,
        strategies=["worst_only"],
        inter_call_sleep_seconds=0.0,
        _run_single_proposal=fake,
    )
    progress_path = tmp_path / "progress.json"
    assert progress_path.exists()
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    assert progress["settings"]["strategies"] == ["worst_only"]
    assert progress["settings"]["resume"] is True
    assert progress["n_calls_this_run"] == 60


def test_batch_runner_resume_false_overwrites_existing(tmp_path: Path):
    """resume=False re-runs even when per-strategy JSONs exist."""
    (tmp_path / "worst_only_0_0.json").write_text(
        json.dumps({"strategy_name": "worst_only"}), encoding="utf-8"
    )
    fake = _FakeRunSingleProposal()
    run_primary_batch(
        pool=_load_pool(),
        incumbent_heuristic=_FAKE_INCUMBENT,
        output_dir=tmp_path,
        strategies=["worst_only"],
        inter_call_sleep_seconds=0.0,
        resume=False,
        _run_single_proposal=fake,
    )
    # With resume=False, all 60 deterministic calls run — the
    # pre-existing JSON is overwritten.
    assert len(fake.calls) == 60


def test_batch_runner_skips_existing_records(tmp_path: Path):
    """If a per-call JSON already exists on disk, the runner skips it
    instead of re-calling the LLM. Resumes mid-batch."""
    # Pre-populate two records for worst_only.
    for seed_index in (0, 1):
        (tmp_path / f"worst_only_0_{seed_index}.json").write_text(
            json.dumps({"strategy_name": "worst_only"}), encoding="utf-8"
        )
    fake = _FakeRunSingleProposal()
    summary = run_primary_batch(
        pool=_load_pool(),
        incumbent_heuristic=_FAKE_INCUMBENT,
        output_dir=tmp_path,
        strategies=["worst_only"],
        inter_call_sleep_seconds=0.0,
        _run_single_proposal=fake,
    )
    assert len(fake.calls) == 58
    assert summary["n_skipped_existing"] == 2
