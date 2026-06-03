"""Tests for thesis/code/splits.py and weibull_generator.py.

Run:
    python -m pytest thesis/code/tests/test_splits.py -q
"""
from __future__ import annotations

import numpy as np

from thesis.code.splits import (
    IN_DIST_NUM_ITEMS,
    MASTER_SEED,
    N_DEV,
    N_PER_TRAIN,
    N_TEST_OOD,
    OOD_NUM_ITEMS,
    build_all_splits,
    qualified_instance_id,
)
from thesis.code.weibull_generator import (
    CLIP_HIGH,
    CLIP_LOW,
    WEIBULL_SCALE,
    WEIBULL_SHAPE,
    generate_instances,
)


def test_generator_is_deterministic():
    a = generate_instances(3, 500, seed=42, instance_id_prefix="t")
    b = generate_instances(3, 500, seed=42, instance_id_prefix="t")
    assert len(a) == len(b) == 3
    for ai, bi in zip(a, b):
        assert ai.items == bi.items
        assert ai.instance_id == bi.instance_id


def test_generator_different_seeds_produce_different_items():
    a = generate_instances(1, 500, seed=1, instance_id_prefix="t")
    b = generate_instances(1, 500, seed=2, instance_id_prefix="t")
    assert a[0].items != b[0].items


def test_generator_items_are_in_clip_range():
    insts = generate_instances(2, 1000, seed=7, instance_id_prefix="t")
    for inst in insts:
        arr = np.array(inst.items)
        assert arr.min() >= CLIP_LOW
        assert arr.max() <= CLIP_HIGH


def test_generator_distribution_parameters_roughly_match():
    """5000-item sample should have mean ~= theoretical Weibull mean."""
    from math import gamma
    theoretical_mean = WEIBULL_SCALE * gamma(1 + 1.0 / WEIBULL_SHAPE)
    insts = generate_instances(1, 5000, seed=13, instance_id_prefix="t")
    observed = float(np.mean(insts[0].items))
    assert abs(observed - theoretical_mean) < 1.0, (
        f"observed mean {observed:.3f} too far from theoretical "
        f"{theoretical_mean:.3f}"
    )


def test_generator_instance_id_format():
    insts = generate_instances(3, 100, seed=11, instance_id_prefix="myprefix")
    assert [i.instance_id for i in insts] == [
        "myprefix_0", "myprefix_1", "myprefix_2"
    ]


def test_build_all_splits_has_expected_names_and_sizes():
    splits = build_all_splits()
    assert set(splits.keys()) == {
        "train_select", "train_step", "train_gate", "dev", "test_ood"
    }
    for n in ("train_select", "train_step", "train_gate"):
        assert len(splits[n].instances) == N_PER_TRAIN
        assert splits[n].instances[0].num_items == IN_DIST_NUM_ITEMS
    assert len(splits["dev"].instances) == N_DEV
    assert splits["dev"].instances[0].num_items == IN_DIST_NUM_ITEMS
    assert len(splits["test_ood"].instances) == N_TEST_OOD
    assert splits["test_ood"].instances[0].num_items == OOD_NUM_ITEMS


def test_train_subsets_are_disjoint_by_items():
    """The three train subsets share no instance IDs and no item sequences.

    Disjoint IDs are enforced by build_all_splits. This test also
    checks that the underlying item sequences differ — a tighter
    guarantee that the seeds actually produce independent samples.
    """
    splits = build_all_splits()
    train = {n: splits[n].instances for n in
             ("train_select", "train_step", "train_gate")}
    for a in train:
        for b in train:
            if a >= b:
                continue
            ids_a = {i.instance_id for i in train[a]}
            ids_b = {i.instance_id for i in train[b]}
            assert not (ids_a & ids_b), f"{a} and {b} share instance IDs"
            items_a = {tuple(i.items) for i in train[a]}
            items_b = {tuple(i.items) for i in train[b]}
            assert not (items_a & items_b), (
                f"{a} and {b} share item sequences despite different seeds"
            )


def test_splits_are_deterministic_end_to_end():
    s1 = build_all_splits()
    s2 = build_all_splits()
    for name in s1:
        for i1, i2 in zip(s1[name].instances, s2[name].instances):
            assert i1.items == i2.items
            assert i1.instance_id == i2.instance_id


def test_master_seed_documented_value():
    """Lock the master seed. Changing it is a deliberate event that
    reshuffles every split in the thesis."""
    assert MASTER_SEED == 2026_04_20


def test_qualified_instance_id_matches_score_cache_convention():
    qid = qualified_instance_id("train_select", "thesis_train_select_5k_0")
    assert qid == "thesis_train_select:thesis_train_select_5k_0"
    assert "|" not in qid  # score cache forbids pipe in keys
