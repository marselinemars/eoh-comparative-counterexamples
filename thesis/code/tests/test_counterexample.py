"""Tests for thesis/code/counterexample.py.

Run:
    python -m pytest thesis/code/tests/test_counterexample.py -q
"""
from __future__ import annotations

import pytest

from thesis.code.counterexample import (
    SCHEMA_VERSION,
    Counterexample,
    CounterexampleSet,
)


# --- Counterexample construction & invariants --------------------------

def _make(**overrides) -> Counterexample:
    """Build a default counterexample, overridable per test."""
    base = dict(
        instance_id="thesis_train_select:thesis_train_select_5k_0",
        candidate_hash="aaaaaaaaaaaa",
        reference_hash="bbbbbbbbbbbb",
        candidate_bins_used=2010,
        reference_bins_used=2020,
    )
    base.update(overrides)
    return Counterexample.from_bin_counts(**base)


def test_gap_sign_candidate_wins():
    ce = _make(candidate_bins_used=2000, reference_bins_used=2020)
    assert ce.gap == 20
    assert ce.candidate_wins
    assert not ce.reference_wins
    assert not ce.tie


def test_gap_sign_reference_wins():
    ce = _make(candidate_bins_used=2030, reference_bins_used=2020)
    assert ce.gap == -10
    assert ce.reference_wins
    assert not ce.candidate_wins


def test_gap_sign_tie():
    ce = _make(candidate_bins_used=2020, reference_bins_used=2020)
    assert ce.gap == 0
    assert ce.tie
    assert not ce.candidate_wins
    assert not ce.reference_wins


def test_abs_gap():
    ce = _make(candidate_bins_used=2030, reference_bins_used=2020)
    assert ce.gap == -10
    assert ce.abs_gap == 10


def test_rejects_same_candidate_and_reference():
    with pytest.raises(ValueError, match="different heuristics"):
        _make(candidate_hash="xxxxxxxxxxxx", reference_hash="xxxxxxxxxxxx")


def test_rejects_non_int_bins():
    with pytest.raises(TypeError):
        _make(candidate_bins_used=2010.0)
    with pytest.raises(TypeError):
        _make(reference_bins_used=2020.0)


def test_immutable():
    ce = _make()
    with pytest.raises(Exception):
        ce.gap = 999  # frozen dataclass must reject attribute assignment


# --- Counterexample serialization --------------------------------------

def test_to_dict_omits_none_optionals():
    d = _make().to_dict()
    assert "trace_slice" not in d
    assert "diagnosis" not in d


def test_roundtrip_without_optionals():
    ce = _make(candidate_bins_used=2005, reference_bins_used=2030)
    restored = Counterexample.from_dict(ce.to_dict())
    assert restored == ce


def test_roundtrip_with_optionals():
    ce = _make(
        trace_slice={"motif": "late_zero_margin", "start": 1200, "end": 1260},
        diagnosis={"label": "tail_thrash", "patch_family": "threshold_shift"},
    )
    restored = Counterexample.from_dict(ce.to_dict())
    assert restored == ce
    assert restored.trace_slice == {"motif": "late_zero_margin",
                                    "start": 1200, "end": 1260}


def test_from_dict_missing_key_raises():
    bad = _make().to_dict()
    del bad["gap"]
    with pytest.raises(ValueError, match="missing required keys"):
        Counterexample.from_dict(bad)


def test_from_dict_inconsistent_gap_raises():
    d = _make().to_dict()
    d["gap"] = d["gap"] + 7
    with pytest.raises(ValueError, match="inconsistent gap"):
        Counterexample.from_dict(d)


# --- CounterexampleSet -------------------------------------------------

def test_empty_set_behavior():
    s = CounterexampleSet()
    assert len(s) == 0
    assert list(s) == []
    assert s.mean_gap == 0.0
    assert s.mean_abs_gap == 0.0


def test_set_len_iter_index():
    a = _make(candidate_bins_used=2000, reference_bins_used=2020)
    b = _make(
        instance_id="thesis_train_select:thesis_train_select_5k_1",
        candidate_bins_used=2005,
        reference_bins_used=2015,
    )
    s = CounterexampleSet(items=[a, b])
    assert len(s) == 2
    assert list(s) == [a, b]
    assert s[0] is a
    assert s[1] is b


def test_set_mean_gap_and_abs_gap():
    a = _make(candidate_bins_used=2000, reference_bins_used=2020)  # gap +20
    b = _make(
        instance_id="thesis_train_select:thesis_train_select_5k_1",
        candidate_bins_used=2030,
        reference_bins_used=2020,
    )                                                               # gap -10
    s = CounterexampleSet(items=[a, b])
    assert s.mean_gap == 5.0
    assert s.mean_abs_gap == 15.0


def test_set_hash_accessors():
    a = _make()
    b = _make(instance_id="thesis_train_select:thesis_train_select_5k_1")
    s = CounterexampleSet(items=[a, b])
    assert s.candidate_hashes == ["aaaaaaaaaaaa", "aaaaaaaaaaaa"]
    assert s.reference_hashes == ["bbbbbbbbbbbb", "bbbbbbbbbbbb"]
    assert s.instance_ids == [
        "thesis_train_select:thesis_train_select_5k_0",
        "thesis_train_select:thesis_train_select_5k_1",
    ]


def test_set_json_roundtrip():
    a = _make()
    b = _make(
        instance_id="thesis_train_select:thesis_train_select_5k_1",
        trace_slice={"motif": "x"},
    )
    original = CounterexampleSet(items=[a, b])
    restored = CounterexampleSet.from_json(original.to_json())
    assert restored.items == original.items


def test_set_from_json_schema_version_mismatch():
    import json

    bad = json.dumps({"schema_version": 999, "items": []})
    with pytest.raises(ValueError, match="schema_version"):
        CounterexampleSet.from_json(bad)


def test_schema_version_constant():
    """Lock the schema version; bumping it is a deliberate event."""
    assert SCHEMA_VERSION == 1
