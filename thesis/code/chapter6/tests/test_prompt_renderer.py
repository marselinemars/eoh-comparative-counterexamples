"""Tests for thesis/code/chapter6/prompt_renderer.py.

Run:
    python -m pytest thesis/code/chapter6/tests/test_prompt_renderer.py -v
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from thesis.code.chapter6.prompt_renderer import (
    LEVEL1_TEMPLATE_PATH,
    LEVEL2_SNIPPET_PATH,
    format_decision_row,
    render_level1_prompt,
    render_level2_prompt,
    select_trace_row_positions,
)
from thesis.code.chapter6.trace_extractor import NEW_BIN_TOKEN, DecisionRecord
from thesis.code.counterexample import Counterexample, CounterexampleSet

REPO_ROOT = Path(__file__).resolve().parents[4]
CH5_TEMPLATE_PATH = (
    REPO_ROOT / "thesis" / "code" / "chapter5" / "prompt_template.txt"
)


# --- Test 1: Level-1 template byte-equivalence ------------------------


def test_level1_template_byte_equivalent_to_ch5() -> None:
    """The chapter 6 Level-1 template must be byte-identical to
    chapter 5's prompt template (chapter6_design.md §9.1). This
    is the load-time guard against silent ch5 drift altering ch6
    Level-1 stimulus.
    """
    ch5_bytes = CH5_TEMPLATE_PATH.read_bytes()
    ch6_bytes = LEVEL1_TEMPLATE_PATH.read_bytes()
    assert ch5_bytes == ch6_bytes, (
        "ch6 Level-1 template has drifted from ch5's. Do NOT 'fix' "
        "by editing ch5; investigate and surface the divergence."
    )


# --- Tests 2–5: select_trace_row_positions ----------------------------


def test_select_positions_n5000() -> None:
    """For the canonical pool's 5000-row traces, the §7.4 rule
    returns 60 strictly-increasing positions in [0, 4999], with
    head [0..11] verbatim and the final position = 4999.
    """
    positions = select_trace_row_positions(5000)
    assert len(positions) == 60
    assert positions[:12] == list(range(12))
    assert positions[-1] == 4999
    assert all(positions[i] < positions[i + 1] for i in range(len(positions) - 1))
    assert all(0 <= p <= 4999 for p in positions)


def test_select_positions_n60_defensive_branch() -> None:
    """When n_trace_rows == 60, the rule's defensive branch returns
    every position (no subsampling).
    """
    positions = select_trace_row_positions(60)
    assert positions == list(range(60))


def test_select_positions_n40_defensive_branch() -> None:
    """When n_trace_rows < 60, the rule's defensive branch returns
    every position (no subsampling).
    """
    positions = select_trace_row_positions(40)
    assert positions == list(range(40))


def test_select_positions_n100_dedup_below_60() -> None:
    """For n=100, the integer-cast linspace tail produces duplicates
    that the set-union dedups, so the returned count is ≤ 60 even
    though head (12) + tail nominal (48) = 60. Verifies rule
    totality on a small range.
    """
    positions = select_trace_row_positions(100)
    assert len(positions) <= 60
    assert len(positions) > 12  # tail must contribute something
    assert all(0 <= p <= 99 for p in positions)
    assert positions[0] == 0
    assert positions[-1] == 99
    assert all(positions[i] < positions[i + 1] for i in range(len(positions) - 1))


# --- Tests 6–8: format_decision_row -----------------------------------


def test_format_row_new_bin_at_idx1() -> None:
    """First-decision render: chose='new', open_bins=[],
    new_bin=true, all numeric fields under compact4 (".4g").
    """
    record = DecisionRecord(
        idx=1,
        item=50.0,
        open_bins=(),
        chose=NEW_BIN_TOKEN,
        score_winner=-100.0,
        score_runner_up=-100.0,
        margin=0.0,
        cap_after=50.0,
        new_bin=True,
    )
    expected = (
        "idx=1 item=50 open_bins=[] chose=new winner=-100 "
        "runner_up=-100 margin=0 cap_after=50 new_bin=true"
    )
    assert format_decision_row(record) == expected


def test_format_row_existing_bin_choice() -> None:
    """Existing-bin render: chose=int (0-based position),
    new_bin=false, non-empty open_bins rendered as
    [<v>, <v>, ...] with comma-space separators. Verifies
    the score_winner→winner / score_runner_up→runner_up
    field-name renaming, and the lowercase 'false' boolean
    formatting.
    """
    record = DecisionRecord(
        idx=17,
        item=22.0,
        open_bins=(51.2, 34.1, 8.7, 22.5),
        chose=2,
        score_winner=-8.7,
        score_runner_up=-22.5,
        margin=13.8,
        cap_after=-13.3,  # nonsensical but tests the format
        new_bin=False,
    )
    out = format_decision_row(record)
    # Spot-check the renaming and booleans first, then full match:
    assert "winner=-8.7" in out
    assert "score_winner=" not in out
    assert "runner_up=-22.5" in out
    assert "score_runner_up=" not in out
    assert "new_bin=false" in out
    assert "new_bin=False" not in out
    assert "open_bins=[51.2, 34.1, 8.7, 22.5]" in out
    expected = (
        "idx=17 item=22 open_bins=[51.2, 34.1, 8.7, 22.5] chose=2 "
        "winner=-8.7 runner_up=-22.5 margin=13.8 cap_after=-13.3 "
        "new_bin=false"
    )
    assert out == expected


def test_format_row_compact4_edge_cases() -> None:
    """Compact4 formatting on edge values: 17-sig-fig float gets
    truncated to 4 sig figs; 0.0 renders as '0' (Python's '%g'
    drops trailing '.0').
    """
    record = DecisionRecord(
        idx=42,
        item=0.9979135035659347,
        open_bins=(0.0,),
        chose=0,
        score_winner=0.9979135035659347,
        score_runner_up=0.9979135035659347,
        margin=0.0,
        cap_after=0.0,
        new_bin=False,
    )
    out = format_decision_row(record)
    # Locking the exact compact4 output so a future format change
    # surfaces in this test.
    assert "item=0.9979" in out
    assert "margin=0" in out
    assert "margin=0.0" not in out
    assert "open_bins=[0]" in out
    assert "cap_after=0" in out
    expected = (
        "idx=42 item=0.9979 open_bins=[0] chose=0 "
        "winner=0.9979 runner_up=0.9979 margin=0 "
        "cap_after=0 new_bin=false"
    )
    assert out == expected


# --- Test 9: full Level-2 renderer, small synthetic case --------------


def _build_synthetic_instance() -> Dict[str, Any]:
    """A 5-item bp_online instance with capacity 100, hand-crafted
    so the ch5 instance summary builds without surprises."""
    return {
        "capacity": 100,
        "instance_id": "synthetic_test_5",
        "items": [50, 30, 20, 10, 5],
        "num_items": 5,
    }


def _build_synthetic_counterexample() -> Counterexample:
    return Counterexample.from_bin_counts(
        instance_id="synthetic:synthetic_test_5",
        candidate_hash="aaaaaaaaaaaa",
        reference_hash="bbbbbbbbbbbb",
        candidate_bins_used=2,
        reference_bins_used=3,
    )


def _build_synthetic_trace() -> list:
    """A 5-row hand-built trace matching what the extractor would
    plausibly produce for the synthetic instance under a tight-fit
    heuristic."""
    return [
        DecisionRecord(
            idx=1, item=50.0, open_bins=(), chose=NEW_BIN_TOKEN,
            score_winner=-100.0, score_runner_up=-100.0, margin=0.0,
            cap_after=50.0, new_bin=True,
        ),
        DecisionRecord(
            idx=2, item=30.0, open_bins=(50.0,), chose=0,
            score_winner=-50.0, score_runner_up=-100.0, margin=50.0,
            cap_after=20.0, new_bin=False,
        ),
        DecisionRecord(
            idx=3, item=20.0, open_bins=(20.0,), chose=0,
            score_winner=-20.0, score_runner_up=-100.0, margin=80.0,
            cap_after=0.0, new_bin=False,
        ),
        DecisionRecord(
            idx=4, item=10.0, open_bins=(0.0,), chose=NEW_BIN_TOKEN,
            score_winner=-100.0, score_runner_up=-100.0, margin=0.0,
            cap_after=90.0, new_bin=True,
        ),
        DecisionRecord(
            idx=5, item=5.0, open_bins=(0.0, 90.0), chose=1,
            score_winner=-90.0, score_runner_up=-100.0, margin=10.0,
            cap_after=85.0, new_bin=False,
        ),
    ]


def test_render_level2_prompt_structural_properties() -> None:
    """Render a 1-counterexample Level-2 prompt from a synthetic
    instance + 5-row trace. The trace is short enough that the
    §7.4 defensive branch returns all 5 positions — every row
    appears in the rendered prompt verbatim.
    """
    ce = _build_synthetic_counterexample()
    cs = CounterexampleSet(items=[ce])
    instance_data = {ce.instance_id: _build_synthetic_instance()}
    trace = _build_synthetic_trace()

    prompt = render_level2_prompt(
        counterexample_set=cs,
        traces=[trace],
        incumbent_source="def score(item, bins):\n    return -bins\n",
        reference_source="def score(item, bins):\n    return bins\n",
        instance_data_by_id=instance_data,
    )

    # Outer template structure inherited from ch5.
    assert "=== INCUMBENT HEURISTIC ===" in prompt
    assert "=== REFERENCE HEURISTIC ===" in prompt
    assert "=== COUNTEREXAMPLES ===" in prompt
    assert "STEP_BY_STEP_REASONING" in prompt
    assert "CODE" in prompt

    # decision_trace block: header appears exactly once (one
    # counterexample → one block).
    assert prompt.count("decision_trace:") == 1

    # The §7.5 framing paragraph appears verbatim.
    framing_anchor = (
        "The rows below are a representative sample of the decisions"
    )
    assert framing_anchor in prompt
    assert (
        "60 rows total from 5000 actual decisions" in prompt
    )

    # All 5 rendered rows appear verbatim (no trace truncation at
    # n=5 since 5 ≤ 200 → defensive branch).
    for r in trace:
        assert format_decision_row(r) in prompt

    # The trace block must be inside the counterexample sub-block,
    # i.e. between item_samples: and the task closing. A coarse
    # check by index ordering is sufficient — exact substring
    # matching of the block boundaries is fragile across template
    # tweaks.
    pos_item_samples = prompt.index("item_samples:")
    pos_decision_trace = prompt.index("decision_trace:")
    pos_task = prompt.index("=== YOUR TASK ===")
    assert pos_item_samples < pos_decision_trace < pos_task


# --- Test 10: length-mismatch validation -----------------------------


def test_render_level2_raises_on_trace_length_mismatch() -> None:
    """ValueError when the caller passes a different number of
    traces than the counterexample set's length. Catches the
    common bug of calling extract_incumbent_trace per
    counterexample but losing one in the loop.
    """
    ce = _build_synthetic_counterexample()
    cs = CounterexampleSet(items=[ce])
    instance_data = {ce.instance_id: _build_synthetic_instance()}
    trace = _build_synthetic_trace()

    with pytest.raises(ValueError, match="len\\(traces\\)"):
        render_level2_prompt(
            counterexample_set=cs,
            traces=[trace, trace],  # 2 traces vs 1 counterexample
            incumbent_source="def score(item, bins):\n    return -bins\n",
            reference_source="def score(item, bins):\n    return bins\n",
            instance_data_by_id=instance_data,
        )

    with pytest.raises(ValueError, match="len\\(traces\\)"):
        render_level2_prompt(
            counterexample_set=cs,
            traces=[],  # 0 traces vs 1 counterexample
            incumbent_source="def score(item, bins):\n    return -bins\n",
            reference_source="def score(item, bins):\n    return bins\n",
            instance_data_by_id=instance_data,
        )


# --- Test 11: determinism ---------------------------------------------


def test_render_level2_is_deterministic() -> None:
    """Two calls with the same inputs must return byte-identical
    strings. No hidden state, no nondeterministic ordering
    inside the renderer.
    """
    ce = _build_synthetic_counterexample()
    cs = CounterexampleSet(items=[ce])
    instance_data = {ce.instance_id: _build_synthetic_instance()}
    trace = _build_synthetic_trace()

    first = render_level2_prompt(
        counterexample_set=cs,
        traces=[trace],
        incumbent_source="def score(item, bins):\n    return -bins\n",
        reference_source="def score(item, bins):\n    return bins\n",
        instance_data_by_id=instance_data,
    )
    second = render_level2_prompt(
        counterexample_set=cs,
        traces=[trace],
        incumbent_source="def score(item, bins):\n    return -bins\n",
        reference_source="def score(item, bins):\n    return bins\n",
        instance_data_by_id=instance_data,
    )
    assert first == second


# --- Bonus: Level-1 renderer also functions ---------------------------


def test_render_level1_prompt_works_through_ch5() -> None:
    """The Level-1 wrapper produces a prompt with the ch5 outer
    structure and no decision_trace block (Level-1 has no trace).
    """
    ce = _build_synthetic_counterexample()
    cs = CounterexampleSet(items=[ce])
    instance_data = {ce.instance_id: _build_synthetic_instance()}

    prompt = render_level1_prompt(
        counterexample_set=cs,
        incumbent_source="def score(item, bins):\n    return -bins\n",
        reference_source="def score(item, bins):\n    return bins\n",
        instance_data_by_id=instance_data,
    )
    assert "=== INCUMBENT HEURISTIC ===" in prompt
    assert "STEP_BY_STEP_REASONING" in prompt
    assert "decision_trace:" not in prompt
