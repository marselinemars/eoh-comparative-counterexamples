"""
thesis/code/chapter4_noref/prompt_builder.py

E1 (no-reference) prompt builder for the §4.5.1 control cell of
the examiner-response revision sprint
(thesis/writing/chapter4_comparative_decomposition_design.md §4.1 / §5.2).

Renders a prompt that contains:
  - The locked E1 task instruction (verbatim from design doc §5.2).
  - Incumbent source code (h_eoh).
  - Four instance blocks. Per design doc §4.1 schema, each block
    has fields: instance_id, item_distribution, item_samples,
    incumbent_bins_used — and nothing else. No reference_bins_used,
    no gap_bins, no reference source code.

The instance_distribution + item_samples rendering uses
chapter-5's build_instance_summary to ensure the distribution
data is byte-identical to chapter-5's rendering of the same
instance (a load-bearing matched-pair property).

The task instruction does NOT mention "reference", "alternative",
"comparison", "gap", "versus", or "compared to".

Pure function given a fixed instance-lookup: same counterexample
set + same incumbent code + same instance data → byte-identical
prompt.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from thesis.code.chapter5.instance_summary import build_instance_summary
from thesis.code.counterexample import CounterexampleSet
from thesis.code.splits import load_split, qualified_instance_id

_DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "prompt_template.txt"
)


# Locked task-instruction wording (design doc §5.2). Kept as a
# module-level constant so unit tests can assert character-
# identicality against this string.
LOCKED_TASK_INSTRUCTION = (
    "You are given a heuristic scoring function `incumbent` and "
    "four instances of online bin packing on which the incumbent's "
    "behavior is shown by `incumbent_bins_used`. Propose a revised "
    "scoring function whose behavior improves performance — that "
    "is, uses fewer bins — on these instances and on the broader "
    "instance distribution they represent. Return only the revised "
    "function."
)


def _load_train_select_lookup() -> Dict[str, Dict[str, Any]]:
    """Build a lookup from qualified instance_id to instance dict
    over chapter-5's pool source split. Identical to
    chapter5/prompt_builder._load_train_select_lookup."""
    split = load_split("train_select")
    out: Dict[str, Dict[str, Any]] = {}
    for inst in split["instances"]:
        qid = qualified_instance_id("train_select", inst["instance_id"])
        out[qid] = inst
    return out


def _render_instance_distribution_and_samples(summary) -> str:
    """Render only the item_distribution and item_samples parts of
    one InstanceSummary. The histogram block is rendered with the
    same three-column layout chapter-5 uses, so the bytes match
    chapter-5's rendering of the same instance.
    """
    bucket_width = summary.capacity // 10
    rows: List[str] = []
    for row_start in range(0, 9, 3):
        cells = []
        for offset in range(3):
            idx = row_start + offset
            lo = idx * bucket_width
            hi = lo + bucket_width
            cells.append(
                f"[{lo:>2}-{hi:>3}]: {summary.histogram[idx]:>4}"
            )
        rows.append("  ".join(cells))
    last_lo = 9 * bucket_width
    last_hi = summary.capacity
    rows.append(
        f"[{last_lo:>2}-{last_hi:>3}]: {summary.histogram[9]:>4}"
    )
    histogram_block = "\n        ".join(rows)
    return (
        f"    item_distribution:\n"
        f"      mean: {summary.mean:.1f}, std: {summary.std:.1f}, "
        f"min: {summary.min_}, max: {summary.max_}\n"
        f"      quartiles (25/50/75): "
        f"{summary.q25} / {summary.q50} / {summary.q75}\n"
        f"      percentiles (p10/p90): {summary.p10} / {summary.p90}\n"
        f"      histogram (10 buckets of width {bucket_width}):\n"
        f"        {histogram_block}\n"
        f"    item_samples:\n"
        f"      largest 5:       {summary.largest_5}\n"
        f"      smallest 5:      {summary.smallest_5}\n"
        f"      near-median 5:   {summary.near_median_5}\n"
        f"      random 5:        {summary.random_5}"
    )


def _render_one_instance_block(
    instance_id_anonymized: str,
    summary,
    incumbent_bins_used: int,
) -> str:
    """Render one E1 instance block per design doc §4.1 schema:

        instance_<idx>:
          n_items: ..., capacity: ...
          incumbent_bins_used: <int>
          item_distribution: ...
          item_samples: ...
    """
    body = _render_instance_distribution_and_samples(summary)
    return (
        f"  {instance_id_anonymized}:\n"
        f"    n_items: {summary.n_items}, "
        f"capacity: {summary.capacity}\n"
        f"    incumbent_bins_used: {incumbent_bins_used}\n"
        f"{body}"
    )


def _render_counterexamples_block(
    counterexample_set: CounterexampleSet,
    instance_data_by_id: Dict[str, Dict[str, Any]],
) -> str:
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
            _render_one_instance_block(
                instance_id_anonymized=label,
                summary=summary,
                incumbent_bins_used=ce.candidate_bins_used,
            )
        )
    return "\n\n".join(blocks)


def build_prompt(
    counterexample_set: CounterexampleSet,
    incumbent_code: str,
    template_path: str | Path | None = None,
    instance_data_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Render the E1 (no-reference) prompt.

    Parameters
    ----------
    counterexample_set:
        CounterexampleSet of length 4. Only the candidate_bins_used
        field on each Counterexample is consulted; reference_bins_used
        and gap are NOT rendered.
    incumbent_code:
        Source code of h_eoh.
    template_path:
        Optional override for the template path.
    instance_data_by_id:
        Optional instance lookup; defaults to chapter-5's train_select.

    Returns
    -------
    str: the fully rendered E1 prompt.
    """
    path = (
        Path(template_path)
        if template_path is not None
        else _DEFAULT_TEMPLATE_PATH
    )
    template = path.read_text(encoding="utf-8")
    if instance_data_by_id is None:
        instance_data_by_id = _load_train_select_lookup()
    counterexamples_block = _render_counterexamples_block(
        counterexample_set, instance_data_by_id
    )
    return template.format(
        incumbent_code=incumbent_code,
        counterexamples_block=counterexamples_block,
    )
