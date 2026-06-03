"""Tests for thesis/code/chapter5/seeds.py."""
from __future__ import annotations

from thesis.code.chapter5.seeds import (
    MASTER_SEED_CH5,
    llm_seed,
    set_seed,
    trajectory_llm_seed,
    trajectory_set_seed,
)


def test_master_seed_constant():
    assert MASTER_SEED_CH5 == 20_260_420


def test_set_seed_deterministic():
    a = set_seed("worst_only", 0)
    b = set_seed("worst_only", 0)
    assert a == b


def test_set_seed_distinct_across_set_index():
    assert set_seed("worst_only", 0) != set_seed("worst_only", 1)


def test_set_seed_distinct_across_strategy():
    assert set_seed("worst_only", 0) != set_seed("worst_plus_best", 0)


def test_llm_seed_deterministic():
    a = llm_seed("worst_only", 0, 0)
    b = llm_seed("worst_only", 0, 0)
    assert a == b


def test_llm_seed_distinct_across_seed_index():
    assert llm_seed("worst_only", 0, 0) != llm_seed("worst_only", 0, 1)


def test_llm_seed_distinct_across_set_index():
    assert llm_seed("worst_only", 0, 0) != llm_seed("worst_only", 1, 0)


def test_llm_seed_distinct_across_strategy():
    assert llm_seed("worst_only", 0, 0) != llm_seed(
        "most_discriminative", 0, 0
    )


def test_set_seed_returns_non_negative_int():
    s = set_seed("worst_only", 0)
    assert isinstance(s, int)
    assert s >= 0


def test_trajectory_seeds_deterministic_and_distinct():
    a = trajectory_set_seed("worst_only", 0, 0)
    b = trajectory_set_seed("worst_only", 0, 0)
    assert a == b
    assert trajectory_set_seed("worst_only", 0, 0) != trajectory_set_seed(
        "worst_only", 0, 1
    )
    assert trajectory_set_seed("worst_only", 0, 0) != trajectory_set_seed(
        "worst_only", 1, 0
    )

    c = trajectory_llm_seed("worst_only", 0, 0)
    d = trajectory_llm_seed("worst_only", 0, 0)
    assert c == d
    assert trajectory_llm_seed("worst_only", 0, 0) != trajectory_llm_seed(
        "worst_only", 0, 1
    )


def test_set_and_llm_seeds_are_different_namespaces():
    """Same (strategy, set_index) should give different set_seed vs
    llm_seed(0) — the namespace prefix in the sha256 input differs."""
    assert set_seed("worst_only", 0) != llm_seed("worst_only", 0, 0)
