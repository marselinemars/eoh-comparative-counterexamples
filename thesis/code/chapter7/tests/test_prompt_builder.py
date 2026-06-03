"""Tests for ``thesis/code/chapter7/prompt_builder.py``.

Verifies the chapter 7 §18.2 contract:

  * Byte-equivalence of the ch7 L1 and L2 templates against
    chapter 5's L1 and chapter 6's L2 respectively.
  * Correct rendering at every k ∈ {1, 2, 4, 8} (L1) and
    k ∈ {1, 2, 4} (L2): exactly k counterexample blocks,
    anonymized as ``instance_01`` .. ``instance_<k:02>``.
  * The framing line states the runtime k value.
  * At L2: exactly k decision-trace blocks rendered under the
    locked N=60 head+stride rule from chapter 6.

Mirrors the precedent in
``thesis/code/chapter5/tests/test_prompt_builder.py`` (synthetic
instances; small ``items`` lists for hermeticity) and
``thesis/code/chapter6/tests/test_prompt_renderer.py``
(synthetic ``DecisionRecord`` traces).
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from thesis.code.chapter5.prompt_builder import _DEFAULT_TEMPLATE_PATH as _CH5_L1_PATH
from thesis.code.chapter6.prompt_renderer import (
    LEVEL2_SNIPPET_PATH as _CH6_L2_PATH,
)
from thesis.code.chapter6.trace_extractor import DecisionRecord
from thesis.code.chapter7.prompt_builder import (
    LEVEL1_TEMPLATE_PATH,
    LEVEL2_TEMPLATE_PATH,
    build_prompt,
)
from thesis.code.counterexample import Counterexample, CounterexampleSet

_FAKE_INCUMBENT_CODE = (
    "import numpy as np\n\n"
    "def score(item, bins):\n"
    "    return bins - item\n"
)
_FAKE_REFERENCE_CODE = (
    "import numpy as np\n\n"
    "def score(item, bins):\n"
    "    return np.ones_like(bins)\n"
)


def _synthetic_instance(instance_id: str) -> dict:
    items = [
        5, 10, 15, 20, 25, 30, 35, 40, 45, 50,
        55, 60, 65, 70, 75, 80, 85, 90, 95, 100,
    ]
    return {
        "instance_id": instance_id.split(":", 1)[-1],
        "items": items,
        "capacity": 100,
        "num_items": len(items),
    }


def _build_synthetic_set(k: int) -> CounterexampleSet:
    """k Counterexamples, distinct instance_ids, varying gaps."""
    items = []
    for i in range(k):
        ce = Counterexample.from_bin_counts(
            instance_id=(
                f"thesis_train_select:thesis_train_select_5k_{i}"
            ),
            candidate_hash="c" * 12,
            reference_hash="r" * 12,
            candidate_bins_used=10 + i,
            reference_bins_used=20 + i,
        )
        items.append(ce)
    return CounterexampleSet(items=items)


def _lookup_for(ce_set: CounterexampleSet) -> dict:
    return {ce.instance_id: _synthetic_instance(ce.instance_id) for ce in ce_set}


def _synthetic_trace(n_rows: int = 5000) -> List[DecisionRecord]:
    """A synthetic 5000-row trace with each row's fields filled in.

    Mirrors the production-pool's row count so the §7.4 head+stride
    rule produces exactly 60 selected positions.
    """
    out: List[DecisionRecord] = []
    for i in range(n_rows):
        out.append(
            DecisionRecord(
                idx=i + 1,
                item=10.0 + (i % 20),
                open_bins=(50.0, 30.0, 10.0),
                chose=0,
                score_winner=0.5,
                score_runner_up=0.4,
                margin=0.1,
                cap_after=40.0,
                new_bin=False,
            )
        )
    return out


# --- byte-equivalence tests ------------------------------------------


def test_ch7_l1_template_byte_equivalent_to_ch5():
    assert LEVEL1_TEMPLATE_PATH.read_bytes() == _CH5_L1_PATH.read_bytes(), (
        "ch7 L1 template diverges from ch5 prompt_template.txt"
    )


def test_ch7_l2_template_byte_equivalent_to_ch6():
    assert LEVEL2_TEMPLATE_PATH.read_bytes() == _CH6_L2_PATH.read_bytes(), (
        "ch7 L2 trace-block snippet diverges from ch6's"
    )


# --- L1 rendering tests at every k ----------------------------------


@pytest.mark.parametrize("k", [1, 2, 4, 8])
def test_l1_renders_exactly_k_counterexample_blocks(k: int):
    ce_set = _build_synthetic_set(k)
    lookup = _lookup_for(ce_set)
    prompt = build_prompt(
        strategy="stratified_representative",
        level=1,
        k=k,
        counterexample_set=ce_set,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    # Each counterexample's anonymized header.
    for i in range(1, k + 1):
        assert f"instance_{i:02d}:" in prompt, (
            f"missing instance_{i:02d}: header at k={k}"
        )
    # No (k+1)-th block.
    assert f"instance_{k + 1:02d}:" not in prompt, (
        f"unexpected instance_{k + 1:02d}: header at k={k}"
    )
    # Per-counterexample subsections appear exactly k times.
    for marker in (
        "item_distribution:",
        "histogram (10 buckets",
        "largest 5:",
        "smallest 5:",
        "near-median 5:",
        "random 5:",
    ):
        assert prompt.count(marker) == k, (
            f"{marker!r} appeared {prompt.count(marker)} times; "
            f"expected {k} at k={k}"
        )


@pytest.mark.parametrize("k", [1, 2, 4, 8])
def test_l1_framing_line_states_runtime_k(k: int):
    ce_set = _build_synthetic_set(k)
    lookup = _lookup_for(ce_set)
    prompt = build_prompt(
        strategy="stratified_representative",
        level=1,
        k=k,
        counterexample_set=ce_set,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    assert f"Below are {k} instances" in prompt, (
        f"framing line should state k={k}; prompt slice: "
        f"{prompt[prompt.find('Below are'):prompt.find('Below are') + 80]!r}"
    )


def test_l1_anonymization_no_qualified_id_leakage():
    ce_set = _build_synthetic_set(4)
    lookup = _lookup_for(ce_set)
    prompt = build_prompt(
        strategy="stratified_representative",
        level=1,
        k=4,
        counterexample_set=ce_set,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    assert "thesis_train_select" not in prompt
    for ce in ce_set:
        tail = ce.instance_id.split(":", 1)[-1]
        assert tail not in prompt, (
            f"prompt leaks raw instance_id tail {tail!r}"
        )


def test_l1_includes_step_by_step_reasoning_scaffold():
    ce_set = _build_synthetic_set(2)
    lookup = _lookup_for(ce_set)
    prompt = build_prompt(
        strategy="stratified_representative",
        level=1,
        k=2,
        counterexample_set=ce_set,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    assert "\nSTEP_BY_STEP_REASONING\n" in prompt
    assert "\nCODE\n" in prompt


# --- L2 rendering tests at every supported k ------------------------


@pytest.mark.parametrize("k", [1, 2, 4])
def test_l2_renders_exactly_k_counterexample_blocks(k: int):
    ce_set = _build_synthetic_set(k)
    lookup = _lookup_for(ce_set)
    traces = [_synthetic_trace() for _ in range(k)]
    prompt = build_prompt(
        strategy="stratified_representative",
        level=2,
        k=k,
        counterexample_set=ce_set,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        traces=traces,
        instance_data_by_id=lookup,
    )
    # Same instance_NN: anonymization as L1.
    for i in range(1, k + 1):
        assert f"instance_{i:02d}:" in prompt
    assert f"instance_{k + 1:02d}:" not in prompt


@pytest.mark.parametrize("k", [1, 2, 4])
def test_l2_renders_exactly_k_trace_blocks(k: int):
    ce_set = _build_synthetic_set(k)
    lookup = _lookup_for(ce_set)
    traces = [_synthetic_trace() for _ in range(k)]
    prompt = build_prompt(
        strategy="stratified_representative",
        level=2,
        k=k,
        counterexample_set=ce_set,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        traces=traces,
        instance_data_by_id=lookup,
    )
    assert prompt.count("decision_trace:") == k, (
        f"expected {k} decision_trace blocks, got "
        f"{prompt.count('decision_trace:')}"
    )


@pytest.mark.parametrize("k", [1, 2, 4])
def test_l2_each_trace_block_has_60_rendered_rows(k: int):
    """The §7.4 N=60 rule selects exactly 60 positions out of 5000."""
    ce_set = _build_synthetic_set(k)
    lookup = _lookup_for(ce_set)
    traces = [_synthetic_trace(n_rows=5000) for _ in range(k)]
    prompt = build_prompt(
        strategy="stratified_representative",
        level=2,
        k=k,
        counterexample_set=ce_set,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        traces=traces,
        instance_data_by_id=lookup,
    )
    # Every rendered row starts with "idx=".
    n_rendered_rows = prompt.count("idx=")
    assert n_rendered_rows == 60 * k, (
        f"expected 60*k={60 * k} rendered trace rows; got "
        f"{n_rendered_rows} at k={k}"
    )


@pytest.mark.parametrize("k", [1, 2, 4])
def test_l2_framing_line_states_runtime_k(k: int):
    ce_set = _build_synthetic_set(k)
    lookup = _lookup_for(ce_set)
    traces = [_synthetic_trace() for _ in range(k)]
    prompt = build_prompt(
        strategy="stratified_representative",
        level=2,
        k=k,
        counterexample_set=ce_set,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        traces=traces,
        instance_data_by_id=lookup,
    )
    assert f"Below are {k} instances" in prompt


# --- Error-path tests -----------------------------------------------


def test_build_prompt_rejects_invalid_level():
    ce_set = _build_synthetic_set(2)
    with pytest.raises(ValueError, match="level must be 1 or 2"):
        build_prompt(
            strategy="stratified_representative",
            level=3,
            k=2,
            counterexample_set=ce_set,
            incumbent_code=_FAKE_INCUMBENT_CODE,
            reference_code=_FAKE_REFERENCE_CODE,
        )


def test_build_prompt_rejects_k_set_length_mismatch():
    ce_set = _build_synthetic_set(2)
    with pytest.raises(ValueError, match="does not match"):
        build_prompt(
            strategy="stratified_representative",
            level=1,
            k=4,
            counterexample_set=ce_set,
            incumbent_code=_FAKE_INCUMBENT_CODE,
            reference_code=_FAKE_REFERENCE_CODE,
        )


def test_l1_rejects_traces_passed():
    ce_set = _build_synthetic_set(2)
    lookup = _lookup_for(ce_set)
    traces = [_synthetic_trace() for _ in range(2)]
    with pytest.raises(ValueError, match="L1 build_prompt does not accept traces"):
        build_prompt(
            strategy="stratified_representative",
            level=1,
            k=2,
            counterexample_set=ce_set,
            incumbent_code=_FAKE_INCUMBENT_CODE,
            reference_code=_FAKE_REFERENCE_CODE,
            traces=traces,
            instance_data_by_id=lookup,
        )


def test_l2_requires_traces():
    ce_set = _build_synthetic_set(2)
    lookup = _lookup_for(ce_set)
    with pytest.raises(ValueError, match="L2 build_prompt requires traces"):
        build_prompt(
            strategy="stratified_representative",
            level=2,
            k=2,
            counterexample_set=ce_set,
            incumbent_code=_FAKE_INCUMBENT_CODE,
            reference_code=_FAKE_REFERENCE_CODE,
            instance_data_by_id=lookup,
        )


def test_l2_traces_length_must_match_k():
    ce_set = _build_synthetic_set(4)
    lookup = _lookup_for(ce_set)
    traces = [_synthetic_trace() for _ in range(2)]  # mismatched
    with pytest.raises(ValueError, match=r"len\(traces\)"):
        build_prompt(
            strategy="stratified_representative",
            level=2,
            k=4,
            counterexample_set=ce_set,
            incumbent_code=_FAKE_INCUMBENT_CODE,
            reference_code=_FAKE_REFERENCE_CODE,
            traces=traces,
            instance_data_by_id=lookup,
        )


# --- worst_only_at_k1 boundary substitution -------------------------


def test_worst_only_at_k1_at_k1_returns_single_largest_loss():
    from thesis.code.chapter7.strategies import worst_only_at_k1

    ce_a = Counterexample.from_bin_counts(
        instance_id="thesis_train_select:thesis_train_select_5k_0",
        candidate_hash="c" * 12, reference_hash="r" * 12,
        candidate_bins_used=20, reference_bins_used=10,  # gap=-10 (loss)
    )
    ce_b = Counterexample.from_bin_counts(
        instance_id="thesis_train_select:thesis_train_select_5k_1",
        candidate_hash="c" * 12, reference_hash="r" * 12,
        candidate_bins_used=10, reference_bins_used=20,  # gap=+10 (win)
    )
    ce_c = Counterexample.from_bin_counts(
        instance_id="thesis_train_select:thesis_train_select_5k_2",
        candidate_hash="c" * 12, reference_hash="r" * 12,
        candidate_bins_used=25, reference_bins_used=10,  # gap=-15 (worst)
    )
    pool = CounterexampleSet(items=[ce_a, ce_b, ce_c])
    selected = worst_only_at_k1(pool, k=1)
    assert len(selected) == 1
    assert selected[0].instance_id == ce_c.instance_id
    assert selected[0].gap == -15


def test_worst_only_at_k1_rejects_k_neq_1():
    from thesis.code.chapter7.strategies import worst_only_at_k1

    ce_a = Counterexample.from_bin_counts(
        instance_id="thesis_train_select:thesis_train_select_5k_0",
        candidate_hash="c" * 12, reference_hash="r" * 12,
        candidate_bins_used=20, reference_bins_used=10,
    )
    pool = CounterexampleSet(items=[ce_a])
    with pytest.raises(ValueError, match="defined only at k=1"):
        worst_only_at_k1(pool, k=2)


# --- seed-namespace smoke test --------------------------------------


def test_seed_namespace_distinct_across_k_at_same_set_index():
    """Per design §5.2 literal reading: different k values produce
    different stratified set seeds at the same set_index. Documents
    the slot-alignment-only interpretation surfaced in the §12
    coordinate-alignment ambiguity report."""
    from thesis.code.chapter7.seeds import stratified_set_seed_ch7

    seeds_k = {
        k: stratified_set_seed_ch7(k=k, set_index=5)
        for k in (1, 2, 4, 8)
    }
    # Four distinct seeds — set_index slot aligns; content differs.
    assert len(set(seeds_k.values())) == 4


def test_seed_namespace_disjoint_from_ch6():
    """ch7's seeds must not collide with ch6's at any plausible
    coordinate. Spot-check by comparing one ch7 seed against the
    ch6 same-strategy same-set-index seed."""
    from thesis.code.chapter6.batch_runner import set_seed_ch6
    from thesis.code.chapter7.seeds import stratified_set_seed_ch7

    s_ch7 = stratified_set_seed_ch7(k=4, set_index=0)
    s_ch6_l1 = set_seed_ch6("stratified_representative", 0, 1)
    s_ch6_l2 = set_seed_ch6("stratified_representative", 0, 2)
    assert s_ch7 != s_ch6_l1
    assert s_ch7 != s_ch6_l2
