"""Tests for thesis/code/chapter5/prompt_builder.py and
instance_summary.py at the Level-3 information floor."""
from __future__ import annotations

from pathlib import Path

import pytest

from thesis.code.chapter5 import worst_only
from thesis.code.chapter5.instance_summary import build_instance_summary
from thesis.code.chapter5.prompt_builder import build_prompt
from thesis.code.counterexample import Counterexample, CounterexampleSet

REPO_ROOT = Path(__file__).resolve().parents[4]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)


def _load_committed_pool() -> CounterexampleSet:
    return CounterexampleSet.from_json(POOL_PATH.read_text(encoding="utf-8"))


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


def _synthetic_instance(
    instance_id: str = "thesis_train_select:thesis_train_select_5k_0",
    items=None,
    capacity: int = 100,
) -> dict:
    """Small synthetic instance for fast hermetic tests."""
    if items is None:
        items = [
            5, 10, 15, 20, 25, 30, 35, 40, 45, 50,
            55, 60, 65, 70, 75, 80, 85, 90, 95, 100,
        ]
    return {
        "instance_id": instance_id.split(":", 1)[-1],
        "items": items,
        "capacity": capacity,
        "num_items": len(items),
    }


def _lookup_for(ce_set: CounterexampleSet, items_per_instance=None) -> dict:
    """Build a minimal instance_data_by_id lookup covering every
    counterexample in the set, using small synthetic item lists."""
    lookup = {}
    for ce in ce_set.items:
        lookup[ce.instance_id] = _synthetic_instance(
            instance_id=ce.instance_id,
            items=items_per_instance,
        )
    return lookup


# --- build_prompt tests ------------------------------------------------


def test_build_prompt_still_anonymizes_instance_ids():
    pool = _load_committed_pool()
    selected = worst_only(pool, k=4)
    lookup = _lookup_for(selected)
    prompt = build_prompt(
        counterexample_set=selected,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    # Anonymized labels present
    for i in range(1, 5):
        assert f"instance_{i:02d}:" in prompt

    # No qualified-id leakage
    assert "thesis_train_select" not in prompt
    for ce in selected:
        inner = ce.instance_id.split(":", 1)[-1]
        assert inner not in prompt, (
            f"prompt leaks raw instance_id tail {inner!r}"
        )


def test_build_prompt_includes_incumbent_code_verbatim():
    pool = _load_committed_pool()
    selected = worst_only(pool, k=4)
    lookup = _lookup_for(selected)
    prompt = build_prompt(
        counterexample_set=selected,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    assert _FAKE_INCUMBENT_CODE.rstrip() in prompt


def test_build_prompt_preserves_diff_sign_convention():
    """A gap=+14 counterexample must render diff=+14 in the prompt
    (per the 2026-04-21 diff-sign fix)."""
    ce = Counterexample.from_bin_counts(
        instance_id="thesis_train_select:thesis_train_select_5k_99",
        candidate_hash="c" * 12,
        reference_hash="r" * 12,
        candidate_bins_used=10,
        reference_bins_used=24,
    )
    assert ce.gap == 14
    set_of_one = CounterexampleSet(items=[ce])
    lookup = _lookup_for(set_of_one)

    prompt = build_prompt(
        counterexample_set=set_of_one,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    assert "diff: +14" in prompt, (
        f"prompt diff column has the wrong sign/value"
    )
    assert "incumbent_bins: 10" in prompt
    assert "reference_bins: 24" in prompt


def test_build_prompt_k_placeholder_matches_set_length():
    pool = _load_committed_pool()
    selected = worst_only(pool, k=4)
    lookup = _lookup_for(selected)
    prompt = build_prompt(
        counterexample_set=selected,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    assert "Below are 4 instances" in prompt


def test_build_prompt_includes_item_distribution_per_counterexample():
    pool = _load_committed_pool()
    selected = worst_only(pool, k=4)
    lookup = _lookup_for(selected)
    prompt = build_prompt(
        counterexample_set=selected,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    # Every counterexample block must include the distribution
    # header and the 10-bucket histogram header.
    assert prompt.count("item_distribution:") == 4, (
        f"expected 4 item_distribution blocks, got "
        f"{prompt.count('item_distribution:')}"
    )
    assert prompt.count("histogram (10 buckets") == 4


def test_build_prompt_includes_item_samples_per_counterexample():
    pool = _load_committed_pool()
    selected = worst_only(pool, k=4)
    lookup = _lookup_for(selected)
    prompt = build_prompt(
        counterexample_set=selected,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    for label in ("largest 5:", "smallest 5:", "near-median 5:", "random 5:"):
        assert prompt.count(label) == 4, (
            f"{label} appeared {prompt.count(label)} times; expected 4"
        )


def test_build_prompt_includes_reference_code_verbatim():
    pool = _load_committed_pool()
    selected = worst_only(pool, k=4)
    lookup = _lookup_for(selected)
    prompt = build_prompt(
        counterexample_set=selected,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    assert _FAKE_REFERENCE_CODE.rstrip() in prompt
    assert "=== REFERENCE HEURISTIC ===" in prompt


def test_build_prompt_contains_step_by_step_reasoning_scaffold():
    pool = _load_committed_pool()
    selected = worst_only(pool, k=4)
    lookup = _lookup_for(selected)
    prompt = build_prompt(
        counterexample_set=selected,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    # Exact locked headings must appear on their own lines.
    assert "\nSTEP_BY_STEP_REASONING\n" in prompt
    assert "\nCODE\n" in prompt
    # Key phrases from the four-point reasoning rubric.
    assert "specific pattern do you observe" in prompt
    assert "specific modification" in prompt


def test_build_prompt_preamble_mentions_reference_heuristic():
    pool = _load_committed_pool()
    selected = worst_only(pool, k=4)
    lookup = _lookup_for(selected)
    prompt = build_prompt(
        counterexample_set=selected,
        incumbent_code=_FAKE_INCUMBENT_CODE,
        reference_code=_FAKE_REFERENCE_CODE,
        instance_data_by_id=lookup,
    )
    assert "reference heuristic" in prompt.lower()


# --- InstanceSummary tests --------------------------------------------


def test_instance_summary_random_5_is_deterministic():
    """Same instance_id → same random_5 sample, byte-for-byte,
    across independent invocations."""
    items = list(range(1, 101))  # 1..100
    inst = {
        "instance_id": "thesis_train_select_5k_7",
        "items": items,
        "capacity": 100,
        "num_items": 100,
    }
    a = build_instance_summary(inst)
    b = build_instance_summary(inst)
    assert a.random_5 == b.random_5
    assert len(a.random_5) == 5
    # Different instance_id → different random_5 (almost surely).
    inst2 = dict(inst)
    inst2["instance_id"] = "thesis_train_select_5k_8"
    c = build_instance_summary(inst2)
    assert c.random_5 != a.random_5


def test_instance_summary_stats_on_known_items():
    """Spot-check stats on a small deterministic item list."""
    items = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    inst = {
        "instance_id": "thesis_train_select_5k_0",
        "items": items,
        "capacity": 100,
        "num_items": 10,
    }
    s = build_instance_summary(inst)
    assert s.n_items == 10
    assert s.capacity == 100
    assert s.min_ == 10
    assert s.max_ == 100
    assert s.q50 == 55  # median of 10..100 step 10 = 55
    # largest 5 descending
    assert s.largest_5 == [100, 90, 80, 70, 60]
    # smallest 5 ascending
    assert s.smallest_5 == [10, 20, 30, 40, 50]
    # histogram: 10 buckets of width 10; each item falls in exactly
    # one bucket. 10 items distributed one per bucket (edges 0..100).
    assert sum(s.histogram) == 10
