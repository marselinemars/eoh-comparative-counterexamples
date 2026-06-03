"""
thesis/code/chapter5/prompt_builder.py

Renders the chapter-5 mutation prompt from the committed template.

Each counterexample is rendered as a Level-3 instance summary
(item-distribution stats + purposeful item samples) per the
2026-04-23 prompt-floor-raise decision. Real qualified instance
IDs are replaced with anonymized labels (instance_01, instance_02,
...). The `diff` column follows the 2026-04-21 convention:
diff = reference_bins_used − candidate_bins_used (= +gap); positive
means the incumbent (candidate) was better.

Pure function given a fixed instance-lookup: same counterexample
set + same incumbent code + same instance data → byte-identical
prompt. By default, instance data is auto-loaded from the
`train_select` split (chapter 5's pool source). Tests can override
the lookup via the `instance_data_by_id` parameter.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from thesis.code.chapter5.instance_summary import (
    build_instance_summary,
    render_instance_summary,
)
from thesis.code.counterexample import CounterexampleSet
from thesis.code.splits import load_split, qualified_instance_id

_DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "prompt_template.txt"
)


def _load_train_select_lookup() -> Dict[str, Dict[str, Any]]:
    """Build a lookup from qualified instance_id to instance dict
    over the committed chapter-5 pool's source split."""
    split = load_split("train_select")
    out: Dict[str, Dict[str, Any]] = {}
    for inst in split["instances"]:
        qid = qualified_instance_id("train_select", inst["instance_id"])
        out[qid] = inst
    return out


def _render_counterexamples_block(
    counterexample_set: CounterexampleSet,
    instance_data_by_id: Dict[str, Dict[str, Any]],
) -> str:
    """Render each counterexample's full Level-3 block, joined by
    blank lines. Anonymized labels start at instance_01."""
    blocks = []
    for i, ce in enumerate(counterexample_set.items, start=1):
        inst = instance_data_by_id.get(ce.instance_id)
        if inst is None:
            raise KeyError(
                f"No instance data found for counterexample "
                f"instance_id={ce.instance_id!r}. Provide it via "
                "the instance_data_by_id parameter or ensure it is "
                "present in the train_select split."
            )
        summary = build_instance_summary(inst)
        label = f"instance_{i:02d}"
        blocks.append(
            render_instance_summary(
                summary=summary,
                instance_id_anonymized=label,
                incumbent_bins=ce.candidate_bins_used,
                reference_bins=ce.reference_bins_used,
            )
        )
    return "\n\n".join(blocks)


def build_prompt(
    counterexample_set: CounterexampleSet,
    incumbent_code: str,
    reference_code: str,
    template_path: str | Path | None = None,
    instance_data_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Render the chapter-5 mutation prompt.

    Parameters
    ----------
    counterexample_set:
        CounterexampleSet of length k (typically 4 in chapter 5).
    incumbent_code:
        Source code of the incumbent heuristic, inlined verbatim.
    reference_code:
        Source code of the reference heuristic (the alternative that
        produced the `reference_bins_used` column in each
        counterexample). Inlined verbatim. See decisions-log entry
        2026-04-23 "Chapter 5 prompt: render full counterexample
        tuple" for rationale.
    template_path:
        Optional path to the template file. Defaults to
        `thesis/code/chapter5/prompt_template.txt`.
    instance_data_by_id:
        Optional mapping from qualified instance_id to the instance
        dict (as returned by `splits.load_split`). If None, the
        function auto-loads the `train_select` split. Tests can
        pass a hand-built lookup to avoid loading real data.

    Returns
    -------
    str: the fully rendered prompt, ready to send to an LLM.
    """
    path = (
        Path(template_path)
        if template_path is not None
        else _DEFAULT_TEMPLATE_PATH
    )
    template = path.read_text(encoding="utf-8")
    k = len(counterexample_set)
    if instance_data_by_id is None:
        instance_data_by_id = _load_train_select_lookup()
    counterexamples_block = _render_counterexamples_block(
        counterexample_set, instance_data_by_id
    )
    return template.format(
        k=k,
        incumbent_code=incumbent_code,
        reference_code=reference_code,
        counterexamples_block=counterexamples_block,
    )
