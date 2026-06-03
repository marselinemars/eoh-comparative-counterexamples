"""
thesis/code/chapter5/validation.py

Chapter 5 validation helpers: the canonical acceptance rule and
the pool-rebuild-against-incumbent function used by
§6.2 trajectory steps.

Acceptance rule (decisions log 2026-04-23, revised from the
original §6.2 `Δ_step_local > 0` test):

    accept iff Δ_step_local >= 0
        AND the proposal is argmax-distinct from the current
            incumbent on the evaluation split.

The rule lives here in one place; the trajectory driver calls
`should_accept_proposal`; tests assert against the same function;
any future protocol change updates this module plus a
decisions-log entry.
"""
from __future__ import annotations

import types
from typing import Any, Dict, List, Tuple

import numpy as np

from thesis.code.chapter5.analysis import (
    is_argmax_equivalent_to_h_eoh,
)
from thesis.code.counterexample import Counterexample, CounterexampleSet
from thesis.code.evaluation import bins_used
from thesis.code.score_cache import ScoreCache
from thesis.code.splits import load_split, qualified_instance_id

ACCEPT_IMPROVEMENT = "accepted_improvement"
ACCEPT_BEHAVIORAL = "accepted_behavioral_change"
REJECT_REGRESSION = "rejected_regression"
REJECT_EQUIVALENT = "rejected_argmax_equivalent"


def should_accept_proposal(
    proposal_per_instance_bins: List[int],
    incumbent_per_instance_bins: List[int],
) -> Tuple[bool, str]:
    """Chapter 5 validation acceptance criterion (Option B).

    Returns ``(accepted, reason)`` where reason is one of:
      - ``accepted_improvement``: Δ_step_local > 0 (implies
        argmax-distinct).
      - ``accepted_behavioral_change``: Δ_step_local = 0 and the
        proposal's per-instance bin counts differ from the
        incumbent's on at least one instance.
      - ``rejected_regression``: Δ_step_local < 0.
      - ``rejected_argmax_equivalent``: Δ_step_local = 0 and
        the per-instance bin counts are element-wise identical.
    """
    if len(proposal_per_instance_bins) != len(
        incumbent_per_instance_bins
    ):
        raise ValueError(
            f"per-instance lengths differ: "
            f"{len(proposal_per_instance_bins)} vs "
            f"{len(incumbent_per_instance_bins)}"
        )
    n = len(incumbent_per_instance_bins)
    if n == 0:
        raise ValueError("per-instance lists are empty")

    incumbent_mean = sum(incumbent_per_instance_bins) / n
    proposal_mean = sum(proposal_per_instance_bins) / n
    delta_step_local = incumbent_mean - proposal_mean

    argmax_distinct = not is_argmax_equivalent_to_h_eoh(
        proposal_per_instance_bins, incumbent_per_instance_bins
    )

    if delta_step_local < 0.0:
        return (False, REJECT_REGRESSION)
    if not argmax_distinct:
        return (False, REJECT_EQUIVALENT)
    if delta_step_local == 0.0:
        return (True, ACCEPT_BEHAVIORAL)
    return (True, ACCEPT_IMPROVEMENT)


def rebuild_pool_against_incumbent(
    incumbent: Dict[str, Any],
    reference_hash: str,
    split_name: str = "train_select",
    cache: ScoreCache | None = None,
) -> CounterexampleSet:
    """Rebuild the chapter-5 pool with `incumbent` as candidate and
    the reference identified by `reference_hash` as the alternative.

    Mirrors `thesis.code.experiments.build_counterexample_pool`'s
    logic: iterate the named split, score both heuristics per
    instance via the persistent cache, emit one Counterexample per
    instance. Calling with `incumbent == get_h_eoh()` and
    `reference_hash` = the chapter-5 fixed reference reproduces
    the committed `h_eoh_counterexample_pool.json` byte-for-byte
    (the integration test in test_validation.py verifies this).

    Parameters
    ----------
    incumbent:
        Dict with keys ``code``, ``code_hash``. Typically
        `get_h_eoh()` at step 1 of a trajectory, or a prior
        step's accepted proposal at later steps.
    reference_hash:
        Code hash of the fixed reference. For chapter 5 this is
        always EoH's second-best member (``62a2846c597e``).
    split_name:
        Which split to derive gaps against. Chapter 5 uses
        ``train_select``.
    cache:
        Optional shared ScoreCache. When None a fresh instance is
        constructed (its saves persist immediately).
    """
    from thesis.code.incumbents import load_final_population

    if cache is None:
        cache = ScoreCache()

    reference = None
    for m in load_final_population():
        if m["code_hash"] == reference_hash:
            reference = m
            break
    if reference is None:
        raise RuntimeError(
            f"reference heuristic {reference_hash!r} not found "
            "in EoH final population"
        )

    cand_module = types.ModuleType(f"h_cand_{incumbent['code_hash']}")
    exec(
        compile(incumbent["code"], "<candidate>", "exec"),
        cand_module.__dict__,
    )
    ref_module = types.ModuleType(f"h_ref_{reference['code_hash']}")
    exec(
        compile(reference["code"], "<reference>", "exec"),
        ref_module.__dict__,
    )

    split = load_split(split_name)
    items: List[Counterexample] = []
    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        cand_bins = cache.get_or_compute(
            incumbent["code_hash"],
            qid,
            lambda i=inst: bins_used(cand_module, i),
        )
        ref_bins = cache.get_or_compute(
            reference["code_hash"],
            qid,
            lambda i=inst: bins_used(ref_module, i),
        )
        items.append(
            Counterexample.from_bin_counts(
                instance_id=qid,
                candidate_hash=incumbent["code_hash"],
                reference_hash=reference["code_hash"],
                candidate_bins_used=cand_bins,
                reference_bins_used=ref_bins,
            )
        )
    cache.save()
    return CounterexampleSet(items=items)


def compute_per_instance_bins_for_heuristic(
    heuristic_code: str,
    heuristic_hash: str,
    split_name: str,
    cache: ScoreCache | None = None,
) -> List[int]:
    """Return per-instance bin counts for a heuristic on `split_name`,
    routing through the persistent score cache. Used by the
    trajectory loop to score current-incumbent and proposal on
    `train_step` before applying the acceptance rule."""
    if cache is None:
        cache = ScoreCache()
    mod = types.ModuleType(f"h_{heuristic_hash}")
    exec(
        compile(heuristic_code, f"<{heuristic_hash}>", "exec"),
        mod.__dict__,
    )
    split = load_split(split_name)
    per: List[int] = []
    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        b = cache.get_or_compute(
            heuristic_hash,
            qid,
            lambda i=inst: bins_used(mod, i),
        )
        per.append(int(b))
    cache.save()
    return per
