"""Unit tests for thesis/code/chapter4_gaponly/prompt_builder.py.

Asserts the E2 (gap-only) cell manipulation per design doc
§4.2 / §5.3 / §8.1: no reference source code, gap_bins field
present, locked task instruction wording (the "not shown here"
phrasing is the load-bearing test of the wording lock), structural
field set per §4.1 + §4.3 option (a).

Option (a) default: each instance block contains six fields after
the header (n_items+capacity counts as one rendered line, then
incumbent_bins_used, reference_bins_used, gap_bins,
item_distribution, item_samples) — option (a) per design doc §4.3.
The reference bin count is shown (incumbent and reference's bin
counts are visible) but the reference source code is NOT.
"""
from __future__ import annotations

import re

from thesis.code.chapter4_gaponly.prompt_builder import (
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
    """The §5.3 locked wording must appear character-identically in
    the rendered prompt."""
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    assert LOCKED_TASK_INSTRUCTION in prompt, (
        "Locked E2 task instruction not found verbatim in prompt"
    )


def test_not_shown_here_phrasing_present():
    """The 'not shown here' phrasing is the load-bearing wording
    that tells the LLM the reference is real but withheld; assert
    it appears explicitly so a wording regression is loud."""
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    assert "not shown here" in prompt, (
        "E2 prompt is missing the locked 'not shown here' phrasing"
    )


def test_no_reference_heuristic_block():
    """No `=== REFERENCE HEURISTIC ===` block (chapter-5's header
    for the reference source code section)."""
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    assert "REFERENCE HEURISTIC" not in prompt, (
        "E2 prompt contains a REFERENCE HEURISTIC header"
    )


def test_no_reference_function_definition():
    """No `def reference(` or equivalent appears anywhere. The
    reference's source code is the load-bearing thing E2 must
    withhold."""
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    # In practice the chapter-5 reference (62a2846c597e) defines
    # a function called `score`, not `reference`. The robust check
    # is to make sure no top-level `=== REFERENCE` marker appears
    # AND no second `def score(` (which would be the reference
    # source code inlined alongside the incumbent).
    n_score_defs = prompt.count("def score(")
    assert n_score_defs == 1, (
        f"Expected exactly 1 `def score(` (the incumbent); "
        f"found {n_score_defs}"
    )


def test_gap_bins_field_present_in_every_instance_block():
    """`gap_bins:` appears as a field exactly four times (one per
    counterexample)."""
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    assert prompt.count("gap_bins:") == 4, (
        f"Expected gap_bins: 4 times; got {prompt.count('gap_bins:')}"
    )


def test_gap_bins_sign_convention():
    """gap_bins = incumbent_bins - reference_bins (§5.3 locked):
    positive ⇒ incumbent uses MORE bins. The fixture has
    candidate=2000+i, reference=2050+i, so gap_bins must be -50
    on every instance.
    """
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    # Four instances; each renders 'gap_bins: -50'.
    occurrences = re.findall(r"gap_bins: ([+-]?\d+)", prompt)
    assert len(occurrences) == 4, occurrences
    assert all(v == "-50" for v in occurrences), (
        f"gap_bins values diverge from the locked convention: "
        f"{occurrences}. Expected -50 for fixture "
        f"(incumbent 2000+i, reference 2050+i)."
    )


def test_instance_blocks_have_exactly_expected_fields():
    """Per design doc §4.1 + §4.3 option (a), each block has these
    field-lines (after the header line):
      n_items+capacity, incumbent_bins_used, reference_bins_used,
      gap_bins, item_distribution, item_samples.
    Confirm via per-field count = 4 and confirm no `diff` field
    leaks in.
    """
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)

    headers = re.findall(r"^  instance_(\d{2}):$", prompt, re.MULTILINE)
    assert len(headers) == 4

    for required in (
        "incumbent_bins_used:",
        "reference_bins_used:",
        "gap_bins:",
        "item_distribution:",
        "item_samples:",
        "n_items:",
    ):
        count = prompt.count(required)
        assert count == 4, (
            f"Expected {required!r} 4 times; got {count}"
        )

    # `diff:` was chapter-5's field name; it must NOT appear in E2
    # (E2 uses gap_bins with the opposite sign convention).
    assert "diff:" not in prompt, "E2 must not use chapter-5's `diff:` field"


def test_incumbent_code_renders_byte_identically():
    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    assert _INCUMBENT_CODE_FIXTURE in prompt


def test_instance_distribution_block_matches_chapter5_byte_for_byte():
    """The item_distribution + item_samples portion must be
    byte-identical to chapter-5's rendering of the same instance."""
    from thesis.code.chapter5.instance_summary import (
        build_instance_summary,
        render_instance_summary,
    )
    from thesis.code.splits import load_split

    ce_set = _make_fixture_set()
    prompt = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)

    split = load_split("train_select")
    inst = split["instances"][0]
    summary = build_instance_summary(inst)
    ch5_block = render_instance_summary(
        summary=summary,
        instance_id_anonymized="instance_01",
        incumbent_bins=2000,
        reference_bins=2050,
    )
    ch5_tail = ch5_block.split("item_distribution:", 1)[1]
    e2_tail_marker = "item_distribution:" + ch5_tail
    assert e2_tail_marker in prompt, (
        "item_distribution+item_samples block diverges from "
        "chapter-5's rendering"
    )


def test_byte_reproducibility():
    ce_set = _make_fixture_set()
    p1 = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    p2 = build_prompt(ce_set, _INCUMBENT_CODE_FIXTURE)
    assert p1 == p2


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
