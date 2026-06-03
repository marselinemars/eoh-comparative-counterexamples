"""Tests for thesis/code/chapter5/validation.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from thesis.code.chapter5.validation import (
    ACCEPT_BEHAVIORAL,
    ACCEPT_IMPROVEMENT,
    REJECT_EQUIVALENT,
    REJECT_REGRESSION,
    rebuild_pool_against_incumbent,
    should_accept_proposal,
)
from thesis.code.counterexample import CounterexampleSet

REPO_ROOT = Path(__file__).resolve().parents[4]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)
CHAPTER5_REFERENCE_HASH = "62a2846c597e"


# --- should_accept_proposal ---------------------------------------


def test_should_accept_proposal_improvement():
    incumbent = [2034, 2050, 2012]
    proposal = [2033, 2049, 2011]
    accepted, reason = should_accept_proposal(proposal, incumbent)
    assert accepted is True
    assert reason == ACCEPT_IMPROVEMENT


def test_should_accept_proposal_behavioral_change_no_regression():
    incumbent = [2034, 2050, 2012]
    proposal = [2033, 2050, 2013]  # 1 better on i0, 1 worse on i2
    accepted, reason = should_accept_proposal(proposal, incumbent)
    assert accepted is True
    assert reason == ACCEPT_BEHAVIORAL


def test_should_reject_proposal_argmax_equivalent():
    incumbent = [2034, 2050, 2012]
    proposal = [2034, 2050, 2012]  # identical
    accepted, reason = should_accept_proposal(proposal, incumbent)
    assert accepted is False
    assert reason == REJECT_EQUIVALENT


def test_should_reject_proposal_regression():
    incumbent = [2034, 2050, 2012]
    proposal = [2035, 2051, 2013]  # all 1 worse
    accepted, reason = should_accept_proposal(proposal, incumbent)
    assert accepted is False
    assert reason == REJECT_REGRESSION


def test_should_reject_proposal_regression_even_if_argmax_distinct():
    incumbent = [2034, 2050, 2012]
    proposal = [2033, 2050, 2014]  # 1 better, 2 worse ⇒ mean worse
    accepted, reason = should_accept_proposal(proposal, incumbent)
    assert accepted is False
    assert reason == REJECT_REGRESSION


# --- pool-rebuild byte-equivalence --------------------------------


@pytest.mark.skipif(
    not POOL_PATH.exists(),
    reason="committed chapter-5 pool artifact missing on this checkout",
)
def test_rebuild_pool_against_h_eoh_matches_committed_pool():
    """rebuild_pool_against_incumbent(h_eoh, chapter-5 reference)
    must reproduce the committed pool byte-for-byte (modulo JSON
    whitespace) — it's the same computation that
    build_counterexample_pool runs."""
    from thesis.code.incumbents import get_h_eoh

    committed = CounterexampleSet.from_json(
        POOL_PATH.read_text(encoding="utf-8")
    )
    rebuilt = rebuild_pool_against_incumbent(
        incumbent=get_h_eoh(),
        reference_hash=CHAPTER5_REFERENCE_HASH,
        split_name="train_select",
    )
    assert len(rebuilt.items) == len(committed.items)
    for a, b in zip(rebuilt.items, committed.items):
        assert a.instance_id == b.instance_id
        assert a.candidate_hash == b.candidate_hash
        assert a.reference_hash == b.reference_hash
        assert a.candidate_bins_used == b.candidate_bins_used
        assert a.reference_bins_used == b.reference_bins_used
        assert a.gap == b.gap
