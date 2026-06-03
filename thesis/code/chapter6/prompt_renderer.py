"""
thesis/code/chapter6/prompt_renderer.py

Chapter 6 prompt rendering — Level 1 (raw, identical to ch5)
and Level 2 (raw + incumbent decision trace).

The Level-1 path is a thin wrapper around chapter 5's
``prompt_builder.build_prompt`` pointed at the byte-identical
ch6 Level-1 template (``prompt_template_level1.txt``). The
Level-2 path extends ch5's per-counterexample rendering by
appending the §7.5 ``decision_trace:`` block — header, framing
paragraph, and the §7.4-subsampled rows under the §7.4 compact4
numeric format — inside each per-counterexample sub-block,
immediately after ``item_samples:``.

The two pure functions that operationalize the §7.4 / §7.5
specs are exposed at module level so they can be tested
independently of the full-prompt rendering:

  - :func:`select_trace_row_positions` — §7.4 part (b),
    head-+-stride row selection.
  - :func:`format_decision_row` — §7.5 per-row format under §7.4
    part (a) ``compact4`` numeric formatting.

The §7.5 framing paragraph is **not** rendered by Python; it is
loaded verbatim from ``prompt_template_level2.txt``. Any change
to the framing text is a decisions-log event and is made by
editing that file (with the §7.4 / §7.5 / §9.2 design-doc
edits that locked the wording in the first place).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from thesis.code.chapter5.instance_summary import (
    build_instance_summary,
    render_instance_summary,
)
from thesis.code.chapter5.prompt_builder import build_prompt as _ch5_build_prompt
from thesis.code.chapter6.trace_extractor import DecisionRecord
from thesis.code.counterexample import CounterexampleSet
from thesis.code.splits import load_split, qualified_instance_id

_PACKAGE_DIR = Path(__file__).resolve().parent

LEVEL1_TEMPLATE_PATH = _PACKAGE_DIR / "prompt_template_level1.txt"
"""Byte-identical copy of ``thesis/code/chapter5/prompt_template.txt``
(``chapter6_design.md`` §9.1). Asserted by unit test."""

LEVEL2_SNIPPET_PATH = _PACKAGE_DIR / "prompt_template_level2.txt"
"""The chapter 6 ``decision_trace:`` block — header, framing
paragraph, and the ``<rendered_decision_trace_rows>`` placeholder
— that is appended inside each per-counterexample sub-block
(``chapter6_design.md`` §7.5)."""

_TRACE_ROWS_PLACEHOLDER = "<rendered_decision_trace_rows>"

# §7.4 part (b) constants. Defined as module-level constants so
# the test suite can reference them without re-deriving.
_HEAD_LEN = 12
_TAIL_LEN = 48
_TOTAL_TARGET = _HEAD_LEN + _TAIL_LEN  # 60 rows per counterexample

# Indentation prefix for trace rows inside the rendered prompt.
# Six spaces = the same level as the framing paragraph in
# prompt_template_level2.txt; matches the ch5 instance-summary
# convention for sub-fields (the "      mean: ..." level inside
# "    item_distribution:").
_ROW_INDENT = "      "


# --- §7.4 part (b): row selection ------------------------------------


def select_trace_row_positions(n_trace_rows: int) -> List[int]:
    """Return the 0-based list-positions selected by the §7.4 rule.

    Implements ``chapter6_design.md`` §7.4 part (b) verbatim:

    - If ``n_trace_rows <= 60``, every position is kept (the
      defensive branch; not expected to fire on the committed
      pool whose traces are all 5000 rows).
    - Otherwise:
        head = [0, 1, ..., 11]
        tail = numpy.linspace(12, n_trace_rows - 1, 48, dtype=int)
        return sorted(set(head) | set(tail))

    For ``(n_trace_rows=5000, cap=60)`` the ``set`` union has
    exactly 60 distinct positions and no dedup fires; for
    smaller ``n`` (synthetic test cases) the dedup may reduce the
    returned count below the head + tail nominal of 60.
    """
    if n_trace_rows <= _TOTAL_TARGET:
        return list(range(n_trace_rows))
    head = list(range(_HEAD_LEN))
    tail = np.linspace(
        _HEAD_LEN, n_trace_rows - 1, _TAIL_LEN, dtype=int
    ).tolist()
    return sorted(set(head) | {int(t) for t in tail})


# --- §7.5: per-row format ---------------------------------------------


def format_decision_row(record: DecisionRecord) -> str:
    """Format one DecisionRecord per the §7.5 per-row spec.

    Compact4 (§7.4 part a) for every numeric field; ``str`` for
    integers; ``true`` / ``false`` for ``new_bin``; the literal
    string ``new`` for ``chose == "new"``.

    The ``DecisionRecord`` field names ``score_winner`` and
    ``score_runner_up`` are renamed to the prompt labels
    ``winner`` and ``runner_up`` respectively; this is the one
    place the dataclass field names diverge from the prompt
    schema (``chapter6_design.md`` §7.5).
    """
    item_str = f"{record.item:.4g}"
    if record.open_bins:
        open_bins_str = (
            "[" + ", ".join(f"{c:.4g}" for c in record.open_bins) + "]"
        )
    else:
        open_bins_str = "[]"
    if isinstance(record.chose, str):
        chose_str = record.chose  # the literal "new" token
    else:
        chose_str = str(record.chose)
    winner_str = f"{record.score_winner:.4g}"
    runner_up_str = f"{record.score_runner_up:.4g}"
    margin_str = f"{record.margin:.4g}"
    cap_after_str = f"{record.cap_after:.4g}"
    new_bin_str = "true" if record.new_bin else "false"
    return (
        f"idx={record.idx} item={item_str} open_bins={open_bins_str} "
        f"chose={chose_str} winner={winner_str} "
        f"runner_up={runner_up_str} margin={margin_str} "
        f"cap_after={cap_after_str} new_bin={new_bin_str}"
    )


# --- internals --------------------------------------------------------


def _load_train_select_lookup() -> Dict[str, Dict[str, Any]]:
    """Build the qualified-instance-id → instance-dict lookup that
    the chapter 5 prompt builder uses by default. Replicated here
    so the Level-2 path can produce the same lookup without
    invoking ch5's private helper."""
    split = load_split("train_select")
    return {
        qualified_instance_id("train_select", inst["instance_id"]): inst
        for inst in split["instances"]
    }


def _load_level2_snippet() -> str:
    """Read the §7.5 trace-block snippet from disk.

    A trailing newline (if present) is stripped so the snippet
    composes cleanly when joined to the per-counterexample
    Level-1 block by ``"\\n"``.
    """
    text = LEVEL2_SNIPPET_PATH.read_text(encoding="utf-8")
    if text.endswith("\n"):
        text = text[:-1]
    return text


def _build_trace_block(
    trace: Sequence[DecisionRecord], snippet_template: str
) -> str:
    """Render the §7.5 decision_trace block for one counterexample.

    Subsamples the trace per :func:`select_trace_row_positions`,
    formats each selected record per :func:`format_decision_row`,
    and substitutes the joined rows into the snippet's
    ``<rendered_decision_trace_rows>`` placeholder. Subsequent
    rows after the first are prefixed by ``_ROW_INDENT`` so the
    rendered block preserves the placeholder's indentation
    level.
    """
    positions = select_trace_row_positions(len(trace))
    selected = [trace[i] for i in positions]
    row_lines = [format_decision_row(r) for r in selected]
    rendered_rows = ("\n" + _ROW_INDENT).join(row_lines)
    return snippet_template.replace(_TRACE_ROWS_PLACEHOLDER, rendered_rows)


# --- public render entry points --------------------------------------


def render_level1_prompt(
    counterexample_set: CounterexampleSet,
    incumbent_source: str,
    reference_source: str,
    instance_data_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Render a chapter 6 Level-1 prompt.

    Thin wrapper around chapter 5's ``build_prompt`` pointed at
    the ch6 Level-1 template (which is byte-identical to ch5's
    per ``chapter6_design.md`` §9.1, asserted by a unit test).
    Returned bytes are identical to what chapter 5 would produce
    for the same inputs.
    """
    return _ch5_build_prompt(
        counterexample_set=counterexample_set,
        incumbent_code=incumbent_source,
        reference_code=reference_source,
        template_path=LEVEL1_TEMPLATE_PATH,
        instance_data_by_id=instance_data_by_id,
    )


def render_level2_prompt(
    counterexample_set: CounterexampleSet,
    traces: Sequence[Sequence[DecisionRecord]],
    incumbent_source: str,
    reference_source: str,
    instance_data_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Render a chapter 6 Level-2 prompt.

    The Level-1 template is the outer skeleton (header,
    incumbent block, reference block, k counterexample blocks,
    task closing). For each counterexample, the per-instance
    Level-1 summary is rendered as in chapter 5, then the §7.5
    decision_trace block (loaded from
    ``prompt_template_level2.txt``) is appended inside the same
    per-counterexample sub-block, with the
    ``<rendered_decision_trace_rows>`` placeholder substituted
    by the §7.4-subsampled rows formatted under
    :func:`format_decision_row`.

    Parameters
    ----------
    counterexample_set:
        Chapter 5 ``CounterexampleSet`` of length ``k``
        (typically 4 in chapter 6).
    traces:
        Sequence of length ``k``. ``traces[i]`` is the
        incumbent's full per-decision trace
        (``list[DecisionRecord]``) for ``counterexample_set[i]``,
        as produced by
        :func:`thesis.code.chapter6.trace_extractor.extract_incumbent_trace`.
        The caller is responsible for extracting and ordering
        the traces; this renderer does not re-extract.
    incumbent_source, reference_source:
        Heuristic source strings, inlined verbatim into the
        Level-1 template's ``=== INCUMBENT HEURISTIC ===`` and
        ``=== REFERENCE HEURISTIC ===`` sections.
    instance_data_by_id:
        Optional override for the ``train_select`` lookup
        (matches ch5 ``build_prompt``'s parameter). When
        ``None`` the lookup is auto-loaded.

    Raises
    ------
    ValueError
        When ``len(traces) != len(counterexample_set)``.
    KeyError
        When a counterexample's ``instance_id`` is not present
        in the resolved ``instance_data_by_id``.
    """
    if len(traces) != len(counterexample_set):
        raise ValueError(
            f"len(traces)={len(traces)} does not match "
            f"len(counterexample_set)={len(counterexample_set)}"
        )

    if instance_data_by_id is None:
        instance_data_by_id = _load_train_select_lookup()

    snippet = _load_level2_snippet()
    template = LEVEL1_TEMPLATE_PATH.read_text(encoding="utf-8")
    k = len(counterexample_set)

    blocks: List[str] = []
    for i, ce in enumerate(counterexample_set.items, start=1):
        inst = instance_data_by_id.get(ce.instance_id)
        if inst is None:
            raise KeyError(
                f"No instance data found for counterexample "
                f"instance_id={ce.instance_id!r}. Provide it via "
                "instance_data_by_id or ensure it is present in "
                "the train_select split."
            )
        summary = build_instance_summary(inst)
        label = f"instance_{i:02d}"
        l1_block = render_instance_summary(
            summary=summary,
            instance_id_anonymized=label,
            incumbent_bins=ce.candidate_bins_used,
            reference_bins=ce.reference_bins_used,
        )
        trace_block = _build_trace_block(traces[i - 1], snippet)
        blocks.append(l1_block + "\n" + trace_block)

    counterexamples_block = "\n\n".join(blocks)
    return template.format(
        k=k,
        incumbent_code=incumbent_source,
        reference_code=reference_source,
        counterexamples_block=counterexamples_block,
    )
