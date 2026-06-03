"""
thesis/code/chapter4_gaponly/prompt_builder.py

E2 (gap-only) prompt builder for the §4.5.2 control cell of the
examiner-response revision sprint
(thesis/writing/chapter4_comparative_decomposition_design.md §4.1 / §5.3).

Renders a prompt that contains:
  - The locked E2 task instruction (verbatim from design doc §5.3).
  - Incumbent source code (h_eoh).
  - Four instance blocks. Per design doc §4.1 + §4.3 (option (a)
    default), each block has fields: instance_id, n_items+capacity,
    incumbent_bins_used, reference_bins_used, gap_bins,
    item_distribution, item_samples. No reference_heuristic: block.
    No reference source code anywhere.

`gap_bins` sign convention is the one fixed in the locked E2 task
instruction (§5.3): positive `gap_bins` means the incumbent uses
MORE bins than the reference, negative means fewer. This is the
OPPOSITE sign convention of chapter-5's `diff` field (which used
diff = reference_bins - incumbent_bins, positive = incumbent
better). E2 must therefore compute gap_bins = incumbent_bins -
reference_bins.

The instance_distribution + item_samples rendering uses
chapter-5's build_instance_summary to ensure the distribution
data is byte-identical to chapter-5's rendering of the same
instance.

Pure function given a fixed instance-lookup: same counterexample
set + same incumbent code + same instance data → byte-identical
prompt.

Option-(a) default for the reference_bins_used field (per design
doc §4.3) is rendered: the LLM sees both incumbent_bins_used and
reference_bins_used (plus their signed difference as gap_bins) but
no reference source code.
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


# Locked task-instruction wording (design doc §5.3). Kept as a
# module-level constant so unit tests can assert character-
# identicality against this string.
LOCKED_TASK_INSTRUCTION = (
    "You are given a heuristic scoring function `incumbent` and "
    "four instances of online bin packing on which the incumbent's "
    "behavior is shown by `incumbent_bins_used`. For each instance, "
    "a `gap_bins` field reports the signed difference between the "
    "incumbent's bin count and the bin count achieved by a fixed "
    "reference scoring function not shown here (positive `gap_bins` "
    "means the incumbent uses more bins than the reference; "
    "negative means fewer). Propose a revised scoring function "
    "whose behavior improves performance — that is, reduces the "
    "bin count — on these instances and on the broader instance "
    "distribution they represent. Return only the revised function."
)


def _load_train_select_lookup() -> Dict[str, Dict[str, Any]]:
    split = load_split("train_select")
    out: Dict[str, Dict[str, Any]] = {}
    for inst in split["instances"]:
        qid = qualified_instance_id("train_select", inst["instance_id"])
        out[qid] = inst
    return out


def _render_instance_distribution_and_samples(summary) -> str:
    """Identical layout to chapter-5's render (and to
    chapter4_noref). The distribution+samples portion of the block
    matches chapter-5 byte-for-byte."""
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
    reference_bins_used: int,
) -> str:
    """Render one E2 instance block per design doc §4.1 + §4.3
    option (a):

        instance_<idx>:
          n_items: ..., capacity: ...
          incumbent_bins_used: <int>
          reference_bins_used: <int>
          gap_bins: <signed int>   # = incumbent - reference
          item_distribution: ...
          item_samples: ...

    gap_bins sign convention (§5.3 locked):
      positive  => incumbent uses MORE bins than reference (worse)
      negative  => incumbent uses fewer bins than reference (better)
    """
    gap_bins = incumbent_bins_used - reference_bins_used
    gap_str = f"{gap_bins:+d}"
    body = _render_instance_distribution_and_samples(summary)
    return (
        f"  {instance_id_anonymized}:\n"
        f"    n_items: {summary.n_items}, "
        f"capacity: {summary.capacity}\n"
        f"    incumbent_bins_used: {incumbent_bins_used}\n"
        f"    reference_bins_used: {reference_bins_used}\n"
        f"    gap_bins: {gap_str}\n"
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
                reference_bins_used=ce.reference_bins_used,
            )
        )
    return "\n\n".join(blocks)


def build_prompt(
    counterexample_set: CounterexampleSet,
    incumbent_code: str,
    template_path: str | Path | None = None,
    instance_data_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Render the E2 (gap-only) prompt.

    Parameters
    ----------
    counterexample_set:
        CounterexampleSet of length 4. Both candidate_bins_used and
        reference_bins_used are read; reference source code is NOT
        rendered.
    incumbent_code:
        Source code of h_eoh.
    template_path:
        Optional override for the template path.
    instance_data_by_id:
        Optional instance lookup; defaults to chapter-5's train_select.

    Returns
    -------
    str: the fully rendered E2 prompt.
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
