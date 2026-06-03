"""thesis/code/chapter7/prompt_builder.py — chapter 7 prompt builder.

Wraps chapter 5's :func:`thesis.code.chapter5.prompt_builder.build_prompt`
(L1) and chapter 6's
:func:`thesis.code.chapter6.prompt_renderer.render_level2_prompt`
(L2). The chapter-7 contribution is parameterizing the renderer
over a runtime ``k`` value at non-``k=4`` configurations
(``chapter7_design.md`` §9 / §16.3 / §18.2).

The chapter-5 prompt builder already threads ``k = len(counterexample_set)``
into the template's ``{k}`` placeholder, so no new substitution
machinery is needed here. This wrapper:

  * Asserts that ``len(counterexample_set) == k`` (caller-side
    safety).
  * Routes L1 calls through ch5's ``build_prompt`` against the
    chapter-7 L1 template.
  * Routes L2 calls through ch6's ``render_level2_prompt``. Because
    ch7's L2 template is byte-equivalent to ch6's (asserted by
    :func:`_assert_template_byte_equivalence` at module load time),
    using ch6's renderer produces byte-identical output to a
    hypothetical ch7-paths renderer.

The byte-equivalence assertion fires once at module import. It
catches accidental divergence between the chapter-7 templates
(committed under ``thesis/code/chapter7/``) and the chapter-5 / 6
templates the wrapper trusts. A divergence is a chapter-7
contract violation and must be either reverted or accompanied by
a decisions-log event.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from thesis.code.chapter5 import prompt_builder as _ch5_pb
from thesis.code.chapter5.prompt_builder import build_prompt as _ch5_build_prompt
from thesis.code.chapter6.prompt_renderer import (
    LEVEL1_TEMPLATE_PATH as _CH6_LEVEL1_PATH,
    LEVEL2_SNIPPET_PATH as _CH6_LEVEL2_PATH,
    render_level2_prompt as _ch6_render_l2,
)
from thesis.code.chapter6.trace_extractor import DecisionRecord
from thesis.code.counterexample import CounterexampleSet

_PACKAGE_DIR = Path(__file__).resolve().parent
LEVEL1_TEMPLATE_PATH: Path = _PACKAGE_DIR / "prompt_template_level1.txt"
LEVEL2_TEMPLATE_PATH: Path = _PACKAGE_DIR / "prompt_template_level2.txt"

_CH5_LEVEL1_PATH: Path = _ch5_pb._DEFAULT_TEMPLATE_PATH


def _assert_template_byte_equivalence() -> None:
    """Assert ch7's templates are byte-equivalent to ch5's L1 and ch6's
    L2. Runs once at module import; raises RuntimeError on divergence.
    """
    ch7_l1 = LEVEL1_TEMPLATE_PATH.read_bytes()
    ch5_l1 = _CH5_LEVEL1_PATH.read_bytes()
    if ch7_l1 != ch5_l1:
        raise RuntimeError(
            "chapter 7 Level-1 template diverges from chapter 5's "
            "(byte-equivalence contract violated). Either revert "
            f"{LEVEL1_TEMPLATE_PATH} or file a decisions-log event."
        )
    ch6_l1 = _CH6_LEVEL1_PATH.read_bytes()
    if ch7_l1 != ch6_l1:
        raise RuntimeError(
            "chapter 7 Level-1 template diverges from chapter 6's "
            "(byte-equivalence contract violated)."
        )

    ch7_l2 = LEVEL2_TEMPLATE_PATH.read_bytes()
    ch6_l2 = _CH6_LEVEL2_PATH.read_bytes()
    if ch7_l2 != ch6_l2:
        raise RuntimeError(
            "chapter 7 Level-2 trace-block snippet diverges from "
            "chapter 6's (byte-equivalence contract violated)."
        )


_assert_template_byte_equivalence()


def build_prompt(
    *,
    strategy: str,
    level: int,
    k: int,
    counterexample_set: CounterexampleSet,
    incumbent_code: str,
    reference_code: str,
    traces: Optional[Sequence[Sequence[DecisionRecord]]] = None,
    instance_data_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Build a chapter 7 prompt at any (strategy, level, k).

    Parameters
    ----------
    strategy:
        Strategy name (e.g., ``"stratified_representative"``,
        ``"worst_plus_best"``, ``"worst_only_at_k1"``). Currently
        used only for runtime validation; the renderer is
        strategy-agnostic.
    level:
        ``1`` (L1, raw counterexamples) or ``2`` (L2, raw + trace).
    k:
        Number of counterexamples shown to the LLM. Must equal
        ``len(counterexample_set)``.
    counterexample_set:
        The selected counterexamples, ordered as the rendered prompt
        will show them.
    incumbent_code, reference_code:
        Source strings inlined into the template's ``{incumbent_code}``
        and ``{reference_code}`` slots.
    traces:
        Required at L2: a sequence of length ``k``, where ``traces[i]``
        is the incumbent's full per-decision trace on
        ``counterexample_set[i]``. Pass ``None`` at L1.
    instance_data_by_id:
        Optional override for the ``train_select`` lookup. When
        ``None`` the renderers auto-load.
    """
    if level not in (1, 2):
        raise ValueError(f"level must be 1 or 2; got {level!r}")
    if len(counterexample_set) != k:
        raise ValueError(
            f"counterexample_set length {len(counterexample_set)} "
            f"does not match k={k}"
        )
    if level == 1:
        if traces is not None:
            raise ValueError("L1 build_prompt does not accept traces")
        return _ch5_build_prompt(
            counterexample_set=counterexample_set,
            incumbent_code=incumbent_code,
            reference_code=reference_code,
            template_path=LEVEL1_TEMPLATE_PATH,
            instance_data_by_id=instance_data_by_id,
        )
    # level == 2
    if traces is None:
        raise ValueError(
            "L2 build_prompt requires traces (one per counterexample)"
        )
    if len(traces) != k:
        raise ValueError(
            f"len(traces)={len(traces)} != k={k}"
        )
    # ch7 templates are byte-equivalent to ch6's (asserted at module
    # load); routing through ch6's renderer produces byte-identical
    # bytes to a hypothetical ch7-paths renderer.
    return _ch6_render_l2(
        counterexample_set=counterexample_set,
        traces=traces,
        incumbent_source=incumbent_code,
        reference_source=reference_code,
        instance_data_by_id=instance_data_by_id,
    )
