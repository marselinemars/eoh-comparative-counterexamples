"""Tests for thesis/code/chapter6/batch_runner.py.

All hermetic — no live LLM calls. Tests inject a fake LLM client
(or a fake proposal runner) and verify dispatch / seed / record
shape.

Run:
    python -m pytest thesis/code/chapter6/tests/test_batch_runner.py -v
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from thesis.code.chapter5.seeds import set_seed as ch5_set_seed
from thesis.code.chapter6.batch_runner import (
    DEFAULT_CELLS,
    MASTER_SEED_CH6,
    CellResult,
    _record_filename,
    _run_chapter6_single_proposal,
    llm_seed_ch6,
    run_chapter6_cell,
    set_seed_ch6,
)
from thesis.code.counterexample import CounterexampleSet

REPO_ROOT = Path(__file__).resolve().parents[4]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)

_FAKE_INCUMBENT: Dict[str, Any] = {
    "code": (
        "import numpy as np\n"
        "def score(item, bins):\n"
        "    return -np.asarray(bins, dtype=float)\n"
    ),
    "code_hash": "abcdef123456",
    "algorithm": "fake_best_fit",
}

_FAKE_REFERENCE_SOURCE = (
    "import numpy as np\n"
    "def score(item, bins):\n"
    "    return np.asarray(bins, dtype=float)\n"
)


def _load_pool() -> CounterexampleSet:
    return CounterexampleSet.from_json(
        POOL_PATH.read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Test 1–3: seeds
# ---------------------------------------------------------------------------


def test_seed_derivation_byte_equivalent_within_level() -> None:
    """Two calls with the same arguments produce the same integer.
    Pure deterministic sha256-based derivation — no hidden state.
    """
    s1 = set_seed_ch6("worst_plus_best", 0, level=2)
    s2 = set_seed_ch6("worst_plus_best", 0, level=2)
    assert s1 == s2

    l1 = llm_seed_ch6("stratified_representative", 5, 2, level=1)
    l2 = llm_seed_ch6("stratified_representative", 5, 2, level=1)
    assert l1 == l2


def test_seed_disjointness_across_levels() -> None:
    """For the same (strategy, set, seed), L1 and L2 produce
    different integers — the level is in the namespace string and
    contributes to the hash.
    """
    set_l1 = set_seed_ch6("worst_plus_best", 0, level=1)
    set_l2 = set_seed_ch6("worst_plus_best", 0, level=2)
    assert set_l1 != set_l2

    llm_l1 = llm_seed_ch6("stratified_representative", 0, 0, level=1)
    llm_l2 = llm_seed_ch6("stratified_representative", 0, 0, level=2)
    assert llm_l1 != llm_l2


def test_seed_disjointness_from_chapter5() -> None:
    """The ch6 set seed is different from ch5's set seed for the same
    (strategy, set) — the namespace prefix (ch5: vs ch6:) and master
    seed (different by 4 days) both contribute. Catches accidental
    seed-space collision between the two chapters' LLM batches.
    """
    ch6 = set_seed_ch6("worst_plus_best", 0, level=1)
    ch5 = ch5_set_seed("worst_plus_best", 0)
    assert ch6 != ch5


# ---------------------------------------------------------------------------
# Fake proposal runner: counts calls, records the rendered prompt the
# cell runner would have passed, and writes a minimal JSON record.
# ---------------------------------------------------------------------------


class _FakeProposalRunner:
    """A drop-in for ``_run_chapter6_single_proposal`` for tests.

    Records each call's args, renders the actual ch6 prompt the
    real worker would have rendered (so prompt-difference tests
    can assert against real renderer output), and writes a
    minimal sanitize-ok JSON record at the same path the real
    worker would.
    """

    def __init__(self, force_status: str = "ok") -> None:
        self.calls: List[Dict[str, Any]] = []
        self.force_status = force_status

    def __call__(
        self,
        *,
        strategy_name: str,
        level: int,
        set_index: int,
        seed_index: int,
        pool: CounterexampleSet,
        incumbent_heuristic: Dict[str, Any],
        reference_source: str,
        output_dir: Path,
        k: int,
        provider: str,
        reasoning_effort: Any,
        max_output_tokens: Any,
        timeout_seconds: float,
        call_llm_fn: Any,
    ) -> Dict[str, Any]:
        # Render the prompt the real worker would have rendered.
        # Imported here to avoid a circular import at module load.
        from thesis.code.chapter6.batch_runner import (
            _build_incumbent_module,
            extract_incumbent_trace,
        )
        from thesis.code.chapter6.prompt_renderer import (
            render_level1_prompt,
            render_level2_prompt,
        )
        from thesis.code.chapter5 import STOCHASTIC_STRATEGY_NAMES, STRATEGIES
        import numpy as np
        from thesis.code.splits import load_split

        derived_set_seed = set_seed_ch6(strategy_name, set_index, level)
        derived_llm_seed = llm_seed_ch6(
            strategy_name, set_index, seed_index, level
        )

        strategy = STRATEGIES[strategy_name]
        if strategy_name in STOCHASTIC_STRATEGY_NAMES:
            ce_set = strategy(pool, k, rng=np.random.default_rng(derived_set_seed))
        else:
            ce_set = strategy(pool, k)

        if level == 1:
            prompt = render_level1_prompt(
                counterexample_set=ce_set,
                incumbent_source=incumbent_heuristic["code"],
                reference_source=reference_source,
            )
        else:
            inc_mod = _build_incumbent_module(incumbent_heuristic)
            split = load_split("train_select")
            lookup = {
                f"thesis_train_select:{i['instance_id']}": i
                for i in split["instances"]
            }
            traces = [
                extract_incumbent_trace(lookup[ce.instance_id], inc_mod)
                for ce in ce_set.items
            ]
            prompt = render_level2_prompt(
                counterexample_set=ce_set,
                traces=traces,
                incumbent_source=incumbent_heuristic["code"],
                reference_source=reference_source,
                instance_data_by_id=lookup,
            )

        cell_id = f"{strategy_name}@L{level}"
        out_path = (
            Path(output_dir)
            / _record_filename(cell_id, set_index, seed_index)
        )
        record: Dict[str, Any] = {
            "chapter": "chapter6",
            "cell_id": cell_id,
            "level": level,
            "master_seed": MASTER_SEED_CH6,
            "strategy_name": strategy_name,
            "set_index": set_index,
            "seed_index": seed_index,
            "set_seed": derived_set_seed,
            "llm_seed": derived_llm_seed,
            "prompt": prompt,
            "sanitization": {"status": self.force_status},
            "_written_to": str(out_path),
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(record), encoding="utf-8")
        self.calls.append({
            "strategy_name": strategy_name,
            "level": level,
            "set_index": set_index,
            "seed_index": seed_index,
            "prompt": prompt,
        })
        return record


# ---------------------------------------------------------------------------
# Test 4: call count
# ---------------------------------------------------------------------------


def test_run_cell_calls_correct_number_of_proposals(tmp_path: Path) -> None:
    fake = _FakeProposalRunner()
    result = run_chapter6_cell(
        strategy_name="worst_plus_best",
        level=1,
        pool=_load_pool(),
        incumbent_heuristic=_FAKE_INCUMBENT,
        reference_source=_FAKE_REFERENCE_SOURCE,
        n_proposals=5,
        output_dir=tmp_path,
        inter_call_sleep_seconds=0.0,
        _run_proposal_fn=fake,
    )
    assert result.n_attempted == 5
    assert len(fake.calls) == 5
    assert result.cell_id == "worst_plus_best@L1"


# ---------------------------------------------------------------------------
# Test 5: L1 vs L2 prompt difference
# ---------------------------------------------------------------------------


def test_l1_vs_l2_prompts_differ(tmp_path: Path) -> None:
    """For the same (strategy, set), the Level-1 and Level-2 prompts
    differ: L2 contains the decision_trace block.
    """
    fake = _FakeProposalRunner()
    run_chapter6_cell(
        strategy_name="worst_plus_best",
        level=1,
        pool=_load_pool(),
        incumbent_heuristic=_FAKE_INCUMBENT,
        reference_source=_FAKE_REFERENCE_SOURCE,
        n_proposals=1,
        output_dir=tmp_path / "l1",
        inter_call_sleep_seconds=0.0,
        _run_proposal_fn=fake,
    )
    run_chapter6_cell(
        strategy_name="worst_plus_best",
        level=2,
        pool=_load_pool(),
        incumbent_heuristic=_FAKE_INCUMBENT,
        reference_source=_FAKE_REFERENCE_SOURCE,
        n_proposals=1,
        output_dir=tmp_path / "l2",
        inter_call_sleep_seconds=0.0,
        _run_proposal_fn=fake,
    )

    assert len(fake.calls) == 2
    l1_prompt = fake.calls[0]["prompt"]
    l2_prompt = fake.calls[1]["prompt"]
    assert l1_prompt != l2_prompt
    assert "decision_trace:" not in l1_prompt
    assert "decision_trace:" in l2_prompt
    assert len(l2_prompt) > len(l1_prompt)


# ---------------------------------------------------------------------------
# Test 6: deterministic-strategy prompt invariance across seeds
# ---------------------------------------------------------------------------


def test_deterministic_strategy_prompts_are_byte_identical(
    tmp_path: Path,
) -> None:
    """For worst_plus_best (deterministic, set_index=0), three
    different seed_index values produce byte-identical prompts —
    the LLM seed is in the metadata, not in the prompt.
    """
    fake = _FakeProposalRunner()
    run_chapter6_cell(
        strategy_name="worst_plus_best",
        level=2,
        pool=_load_pool(),
        incumbent_heuristic=_FAKE_INCUMBENT,
        reference_source=_FAKE_REFERENCE_SOURCE,
        n_proposals=3,
        output_dir=tmp_path,
        inter_call_sleep_seconds=0.0,
        _run_proposal_fn=fake,
    )
    prompts = [c["prompt"] for c in fake.calls]
    assert len(prompts) == 3
    assert prompts[0] == prompts[1] == prompts[2]


# ---------------------------------------------------------------------------
# Test 7: stochastic-strategy prompt difference across sets
# ---------------------------------------------------------------------------


def test_stochastic_strategy_prompts_differ_across_sets(
    tmp_path: Path,
) -> None:
    """For stratified_representative (stochastic), set_index=[0..2]
    with seed_index=0 produces three different prompts because the
    counterexample set itself is resampled per set.
    """
    fake = _FakeProposalRunner()
    # n_proposals=7 walks through (set 0, seed 0..2), (set 1, seed 0..2),
    # (set 2, seed 0). Then we pick out the seed_index==0 prompts.
    run_chapter6_cell(
        strategy_name="stratified_representative",
        level=1,
        pool=_load_pool(),
        incumbent_heuristic=_FAKE_INCUMBENT,
        reference_source=_FAKE_REFERENCE_SOURCE,
        n_proposals=7,
        output_dir=tmp_path,
        inter_call_sleep_seconds=0.0,
        _run_proposal_fn=fake,
    )
    set0_prompt = next(
        c["prompt"] for c in fake.calls
        if c["set_index"] == 0 and c["seed_index"] == 0
    )
    set1_prompt = next(
        c["prompt"] for c in fake.calls
        if c["set_index"] == 1 and c["seed_index"] == 0
    )
    set2_prompt = next(
        c["prompt"] for c in fake.calls
        if c["set_index"] == 2 and c["seed_index"] == 0
    )
    assert set0_prompt != set1_prompt
    assert set1_prompt != set2_prompt
    assert set0_prompt != set2_prompt


# ---------------------------------------------------------------------------
# Test 8: CellResult shape
# ---------------------------------------------------------------------------


class _MixedStatusFakeRunner:
    """Returns alternating sanitize statuses to exercise the
    failure-counting path."""

    def __init__(self, statuses: List[str]) -> None:
        self.statuses = statuses
        self.idx = 0

    def __call__(self, **kwargs: Any) -> Dict[str, Any]:
        s = self.statuses[self.idx % len(self.statuses)]
        self.idx += 1
        cell_id = f"{kwargs['strategy_name']}@L{kwargs['level']}"
        out_path = (
            Path(kwargs["output_dir"])
            / _record_filename(
                cell_id, kwargs["set_index"], kwargs["seed_index"]
            )
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "chapter": "chapter6",
            "cell_id": cell_id,
            "level": kwargs["level"],
            "strategy_name": kwargs["strategy_name"],
            "set_index": kwargs["set_index"],
            "seed_index": kwargs["seed_index"],
            "sanitization": {"status": s},
            "_written_to": str(out_path),
        }
        out_path.write_text(json.dumps(record), encoding="utf-8")
        return record


def test_cell_result_field_shape_and_counts(tmp_path: Path) -> None:
    """Successes + sum(failures) == n_attempted; failure dict keys
    are the per-failure status labels.
    """
    fake = _MixedStatusFakeRunner(
        statuses=["ok", "failed_runtime", "ok", "failed_parse", "ok"]
    )
    result = run_chapter6_cell(
        strategy_name="worst_plus_best",
        level=2,
        pool=_load_pool(),
        incumbent_heuristic=_FAKE_INCUMBENT,
        reference_source=_FAKE_REFERENCE_SOURCE,
        n_proposals=5,
        output_dir=tmp_path,
        inter_call_sleep_seconds=0.0,
        _run_proposal_fn=fake,
    )
    assert isinstance(result, CellResult)
    assert result.cell_id == "worst_plus_best@L2"
    assert result.n_attempted == 5
    assert result.n_succeeded == 3
    assert result.n_failed_per_label == {
        "failed_runtime": 1,
        "failed_parse": 1,
    }
    assert (
        result.n_succeeded
        + sum(result.n_failed_per_label.values())
        == result.n_attempted
    )
    assert len(result.proposal_record_paths) == 5


# ---------------------------------------------------------------------------
# Test 9: per-proposal record schema (single-proposal worker exercised)
# ---------------------------------------------------------------------------


def _fake_call_llm_returning_garbage(**kwargs: Any) -> Dict[str, Any]:
    """A fake LLM client that returns a malformed response so the
    sanitizer fails. Avoids a real LLM call while still exercising
    the worker's prompt → sanitize → record-write path end-to-end.
    """
    return {
        "text": "this is not a valid python score function response",
        "model": "fake-model",
        "temperature": 1.0,
        "max_output_tokens": kwargs.get("max_output_tokens"),
        "reasoning_effort": kwargs.get("reasoning_effort"),
        "seed_requested": kwargs.get("seed"),
        "seed_honored": False,
        "raw_response_metadata": {"usage": {"total_tokens": 12}},
    }


def test_per_proposal_record_schema(tmp_path: Path) -> None:
    """Run the real _run_chapter6_single_proposal worker against a
    fake LLM client. Sanitize will fail (response is garbage), so
    scoring is None — but every other ch6-specific field must be
    present and well-typed in the written record.
    """
    record = _run_chapter6_single_proposal(
        strategy_name="worst_plus_best",
        level=1,
        set_index=0,
        seed_index=0,
        pool=_load_pool(),
        incumbent_heuristic=_FAKE_INCUMBENT,
        reference_source=_FAKE_REFERENCE_SOURCE,
        output_dir=tmp_path,
        k=4,
        provider="gemini",
        reasoning_effort="medium",
        max_output_tokens=32768,
        timeout_seconds=300.0,
        call_llm_fn=_fake_call_llm_returning_garbage,
    )

    out_path = (
        tmp_path / _record_filename("worst_plus_best@L1", 0, 0)
    )
    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))

    # Chapter-6-specific fields.
    assert written["chapter"] == "chapter6"
    assert written["cell_id"] == "worst_plus_best@L1"
    assert written["level"] == 1
    assert written["master_seed"] == MASTER_SEED_CH6

    # Inherited from ch5 schema.
    for key in (
        "provider",
        "strategy_name",
        "set_index",
        "seed_index",
        "set_seed",
        "llm_seed",
        "k",
        "counterexample_set",
        "incumbent_hash",
        "reference_hash",
        "prompt",
        "raw_response",
        "llm_metadata",
        "sanitization",
        "scoring",
        "timestamps",
    ):
        assert key in written, f"missing field: {key}"

    # Sanitize failed → scoring is None and the failure label is
    # surfaced in the sanitization sub-record.
    assert written["scoring"] is None
    assert written["sanitization"]["status"] != "ok"

    # Seeds are the ch6-derived integers (not the ch5 ones).
    assert written["set_seed"] == set_seed_ch6("worst_plus_best", 0, 1)
    assert written["llm_seed"] == llm_seed_ch6("worst_plus_best", 0, 0, 1)


# ---------------------------------------------------------------------------
# Misc: DEFAULT_CELLS ordering matches §8.1.
# ---------------------------------------------------------------------------


def test_default_cells_match_design_doc_order() -> None:
    """The four cells iterate strategies first, then levels, in the
    canonical order spelled out in chapter6_design.md §8.1."""
    assert list(DEFAULT_CELLS) == [
        ("stratified_representative", 1),
        ("stratified_representative", 2),
        ("worst_plus_best", 1),
        ("worst_plus_best", 2),
    ]
