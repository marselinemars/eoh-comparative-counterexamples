"""Unit tests for thesis/code/chapter4_noref/prompt_builder.py.

Asserts the E1 (no-reference) cell manipulation per design doc
§4.2 / §5.2 / §8.1: no reference / gap / comparison substrings,
locked task instruction wording, structural field set per §4.1.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from thesis.code.chapter4_noref.prompt_builder import (
    LOCKED_TASK_INSTRUCTION,
    build_prompt,
)
from thesis.code.counterexample import Counterexample, CounterexampleSet


_INCUMBENT_CODE_FIXTURE = """import numpy as np

def score(item, bins):
    # Minimal fixture; not the real h_eoh.
    return -np.abs(bins - item)
"""


def _make_fixture_set(n: int = 4) -> CounterexampleSet:
    """Build a 4-counterexample set whose instance_ids point at the
    first n entries of the chapter-5 train_select split."""
    return CounterexampleSet(items=[
        Counterexample.from_bin_counts(
            instance_id=f"thesis_train_select:thesis_train_select_5k_{i}",
            candidate_hash="aaaaaaaaaaaa",
            reference_hash="bbbbbbbbbbbb",
            candidate_bins_used=2000 + i,
            reference_bins_used=2050 + i,
        )
        for i in range(n)
    ])


def test_locked_task_instruction_appears_verbatim():
    """The §5.2 locked wording must appear character-identically in
    the rendered prompt."""
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    assert LOCKED_TASK_INSTRUCTION in prompt, (
        "Locked E1 task instruction not found verbatim in prompt"
    )


def test_no_reference_substring_anywhere():
    """No `reference` substring (case-insensitive) anywhere."""
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    assert "reference" not in prompt.lower(), (
        "E1 prompt contains 'reference' substring"
    )


def test_no_gap_substring_anywhere():
    """No `gap` substring (case-insensitive) anywhere. Watch for
    spurious matches: 'gap' as a substring of 'gappy', 'gap_bins',
    etc.; the broad check is what we want."""
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    assert "gap" not in prompt.lower(), (
        "E1 prompt contains 'gap' substring"
    )


def test_no_comparative_framing_substrings():
    """No `comparison`, `versus`, `compared to`, `alternative`
    substrings appear (case-insensitive)."""
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    low = prompt.lower()
    for needle in ("comparison", "versus", "compared to", "alternative"):
        assert needle not in low, (
            f"E1 prompt contains comparative-framing substring "
            f"{needle!r}"
        )


def test_instance_blocks_have_only_expected_fields():
    """Each instance block has exactly the §4.1 fields:
    instance_NN:, n_items+capacity line, incumbent_bins_used,
    item_distribution, item_samples. No reference_bins, no
    reference_bins_used, no gap_bins, no diff field.
    """
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)

    # Find all instance block headers.
    headers = re.findall(r"^  instance_(\d{2}):$", prompt, re.MULTILINE)
    assert len(headers) == 4, (
        f"Expected 4 instance blocks; found {len(headers)}: "
        f"{headers}"
    )

    # Forbidden fields anywhere in the prompt
    for forbidden in (
        "reference_bins",
        "reference_bins_used",
        "gap_bins",
        "diff:",
        "diff =",
    ):
        assert forbidden not in prompt, (
            f"Forbidden field {forbidden!r} found in E1 prompt"
        )

    # Required fields appear 4 times (once per instance block)
    for required in (
        "incumbent_bins_used:",
        "item_distribution:",
        "item_samples:",
        "n_items:",
    ):
        count = prompt.count(required)
        assert count == 4, (
            f"Expected {required!r} 4 times (one per instance); "
            f"got {count}"
        )


def test_incumbent_code_renders_byte_identically():
    """The incumbent code is substituted verbatim into the
    prompt. Asserts byte-identical inclusion of the source code
    string we passed in."""
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    assert _INCUMBENT_CODE_FIXTURE in prompt, (
        "Incumbent code not rendered byte-identically"
    )


def test_instance_distribution_block_matches_chapter5_byte_for_byte():
    """The item_distribution + item_samples portion of each
    instance block must be byte-identical to chapter-5's rendering
    of the same instance, to preserve matched-pair defensibility.
    """
    from thesis.code.chapter5.instance_summary import (
        build_instance_summary,
        render_instance_summary,
    )

    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)

    # Pull chapter-5's rendering of instance 1 and check that its
    # distribution+samples lines all appear in the E1 prompt.
    from thesis.code.splits import load_split, qualified_instance_id

    split = load_split("train_select")
    inst = split["instances"][0]
    summary = build_instance_summary(inst)
    ch5_block = render_instance_summary(
        summary=summary,
        instance_id_anonymized="instance_01",
        incumbent_bins=2000,
        reference_bins=2050,
    )
    # Extract just the distribution + samples lines (everything
    # from "item_distribution:" onward).
    ch5_tail = ch5_block.split("item_distribution:", 1)[1]

    # E1 prompt must contain that tail verbatim (starting from
    # "item_distribution:").
    e1_tail_marker = "item_distribution:" + ch5_tail
    assert e1_tail_marker in prompt, (
        "item_distribution+item_samples block diverges from "
        "chapter-5's rendering"
    )


def test_byte_reproducibility():
    """Two calls with the same inputs must return byte-identical
    prompts."""
    ce_set = _make_fixture_set()
    p1 = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    p2 = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    assert p1 == p2


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
