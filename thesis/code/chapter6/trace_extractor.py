"""
thesis/code/chapter6/trace_extractor.py

Chapter 6 trace-slice extractor. Produces the per-counterexample
**incumbent decision trace** that augments a counterexample at
structural Level 2 (``thesis/writing/chapter6_design.md`` §7).

A trace is the incumbent's complete per-decision packing trace on
the counterexample instance: one :class:`DecisionRecord` per arrival
index, ordered chronologically, with no filter — every item the
incumbent processes produces a row, regardless of whether it placed
the item in an existing open bin or opened a new one. The reference
heuristic does not appear in the trace; the comparative frame of
the counterexample is carried by the Level-1 prompt block (the
reference's source code, the bin-count comparison) elsewhere in
the prompt.

Harness semantics inherited from
``examples/bp_online/evaluation/evaluation.py::Evaluation.online_binpack``:

- bins are preallocated as an array of length ``num_items`` with all
  entries initialized to ``capacity``;
- at each arrival index the valid bins are those with
  ``capacity_remaining >= item_size``;
- the heuristic's ``score(item, bins[valid])`` vector is max'd by
  ``numpy.argmax``, which breaks ties by returning the lowest valid
  index (so ties among currently-unused bins always resolve to the
  first unused bin globally, which — since the heuristic's scoring
  has no knowledge of bin position — is also the first unused bin in
  creation order);
- item size strictly greater than capacity would make ``valid``
  empty and ``np.argmax`` raise; this extractor inherits that
  behavior exactly (no softening or workaround).

A design-time assumption the extractor makes about heuristics: their
``score`` function depends on each bin's remaining capacity only,
not on the length or index layout of the ``bins`` array passed to
it. All committed thesis incumbents and references satisfy this.
Violations would cause the extractor's re-scoring on the abstract
candidate set (existing valid open bins ∪ one deduplicated "new"
slot) to disagree with the harness's scoring on the full
preallocated valid-bin subset; the byte-equivalence test between
:func:`_final_bins_used` and ``thesis.code.evaluation.bins_used``
is the shared guarantee, and the test in
``tests/test_trace_extractor.py`` is the gate.

The extractor returns every decision the incumbent makes,
chronologically. No trace-size cap is applied — the design doc's
§7.4 rendering rule is deliberately undetermined pending the
pool statistics probe, and trimming/sampling is the caller's
concern (the prompt renderer's, not this extractor's).
"""
from __future__ import annotations

import types
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Tuple, Union

import numpy as np

BinChoice = Union[int, str]
"""The chosen candidate slot at a decision.

Either an ``int`` (0-based position into the incumbent's own
open-bins creation-order list) or the literal string ``"new"``
when the incumbent chose to open a previously-unused bin at this
decision.
"""

NEW_BIN_TOKEN: str = "new"


@dataclass(frozen=True)
class DecisionRecord:
    """One row of a chapter-6 incumbent decision trace.

    Schema matches ``chapter6_design.md`` §7.2 field-for-field.
    Frozen so a record is hashable and the trace as a whole is
    treated as immutable downstream.

    Fields
    ------
    idx:
        1-based arrival index of the item within the instance's
        item sequence.
    item:
        Size of the arriving item, as a plain ``float``.
    open_bins:
        Remaining-capacity vector of the incumbent's open bins at
        decision time, in creation order (index 0 = first-opened,
        etc.). Reported as a tuple so the record is hashable; may
        be empty at arrival index 1 when no bin has yet been
        opened.
    chose:
        The chosen candidate slot. An integer is a 0-based
        position into ``open_bins``; the literal string ``"new"``
        means the incumbent opened a previously-unused bin at
        this decision.
    score_winner:
        The score value the heuristic's scoring function produced
        at the chosen slot (the chosen open bin, or the new-bin
        slot if ``chose == "new"``).
    score_runner_up:
        The second-highest score across the incumbent's
        **abstract candidate set** at this decision — the union
        of its currently-open valid bins with a single
        deduplicated new-bin slot (included iff at least one
        preallocated unused bin is valid for this item). When
        the abstract set has fewer than two elements (e.g., at
        arrival index 1 with no open bins yet, or at any later
        decision where every open bin is too full to fit the
        item and the new-bin slot is the only candidate),
        ``score_runner_up == score_winner`` by convention. See
        ``chapter6_design.md`` §7.2.1.
    margin:
        ``score_winner - score_runner_up``; non-negative by
        construction.
    cap_after:
        Remaining capacity of the chosen bin after the item is
        packed. For a new-bin decision, this is
        ``capacity - item``.
    new_bin:
        Boolean; ``True`` iff this decision opened a previously-
        unused bin (equivalently, ``chose == "new"``).
    """

    idx: int
    item: float
    open_bins: Tuple[float, ...]
    chose: BinChoice
    score_winner: float
    score_runner_up: float
    margin: float
    cap_after: float
    new_bin: bool

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict, JSON-safe rendering of the record.

        The ``open_bins`` tuple is emitted as a list; the
        union-typed ``chose`` field is emitted as its native
        Python type (``int`` or ``str``) with no coercion. All
        other fields are already JSON-safe scalars. Field names
        and ordering match the ``chapter6_design.md`` §7.2 schema
        directly (no nested sub-dictionaries — the trace is
        single-side).
        """
        return {
            "idx": self.idx,
            "item": self.item,
            "open_bins": list(self.open_bins),
            "chose": self.chose,
            "score_winner": self.score_winner,
            "score_runner_up": self.score_runner_up,
            "margin": self.margin,
            "cap_after": self.cap_after,
            "new_bin": self.new_bin,
        }


def _replay(
    instance: Mapping[str, Any],
    incumbent: types.ModuleType,
) -> List[DecisionRecord]:
    """Run the incumbent on the instance, yielding one record per decision.

    Mirrors ``Evaluation.online_binpack`` decision-for-decision: same
    preallocated bin array, same valid-bins filter, same
    ``numpy.argmax`` tie-break. The only additional work is
    bookkeeping for the abstract (existing valid open bins ∪ one
    "new" slot) candidate set that the §7.2.1 scoring rule operates
    over.
    """
    capacity = float(instance["capacity"])
    num_items = int(instance["num_items"])
    items = np.asarray(instance["items"])
    bins = np.array([capacity for _ in range(num_items)], dtype=float)

    creation_order: List[int] = []
    creation_pos: Dict[int, int] = {}

    records: List[DecisionRecord] = []

    for one_based_idx, raw_item in enumerate(items, start=1):
        item_val = float(raw_item)

        # Harness-equivalent candidate selection.
        valid = np.nonzero((bins - item_val) >= 0)[0]
        priorities = incumbent.score(item_val, bins[valid])
        priorities = np.asarray(priorities, dtype=float)
        best_in_valid = int(np.argmax(priorities))
        best_global = int(valid[best_in_valid])

        is_new_bin = best_global not in creation_pos

        open_bins_before: Tuple[float, ...] = tuple(
            float(bins[g]) for g in creation_order
        )

        # Build the abstract candidate set {valid existing open
        # bins} ∪ {new-bin slot} with the score each would have
        # received in this decision, deduplicating the redundant
        # unused bins (§7.2.1).
        abstract_scores: Dict[BinChoice, float] = {}
        new_bin_slot_candidates: List[float] = []
        for k, g in enumerate(valid):
            g_int = int(g)
            score_val = float(priorities[k])
            if g_int in creation_pos:
                abstract_scores[creation_pos[g_int]] = score_val
            else:
                new_bin_slot_candidates.append(score_val)
        if new_bin_slot_candidates:
            # Max across unused-bin scores is what would drive any
            # argmax-picking-a-new-bin outcome; under the
            # elementwise-independence assumption (§7.2.2) the
            # list is all one value anyway.
            abstract_scores[NEW_BIN_TOKEN] = max(new_bin_slot_candidates)

        sorted_scores = sorted(abstract_scores.values(), reverse=True)
        score_winner = sorted_scores[0]
        if len(sorted_scores) >= 2:
            score_runner_up = sorted_scores[1]
        else:
            score_runner_up = score_winner
        margin = score_winner - score_runner_up

        if is_new_bin:
            chose: BinChoice = NEW_BIN_TOKEN
        else:
            chose = creation_pos[best_global]

        # Mutate bins and update creation bookkeeping.
        bins[best_global] -= item_val
        cap_after = float(bins[best_global])
        if is_new_bin:
            creation_pos[best_global] = len(creation_order)
            creation_order.append(best_global)

        records.append(
            DecisionRecord(
                idx=one_based_idx,
                item=item_val,
                open_bins=open_bins_before,
                chose=chose,
                score_winner=score_winner,
                score_runner_up=score_runner_up,
                margin=margin,
                cap_after=cap_after,
                new_bin=is_new_bin,
            )
        )

    return records


def _final_bins_used(
    instance: Mapping[str, Any],
    incumbent: types.ModuleType,
) -> int:
    """Final integer bin count produced by the extractor's replay.

    Private helper used by the harness-alignment unit test. Equals
    the number of new-bin decisions the incumbent makes over the
    course of the instance — equivalently, the count of bins whose
    remaining capacity falls below the initial capacity by the end
    of the run.
    """
    records = _replay(instance, incumbent)
    return sum(1 for r in records if r.new_bin)


def extract_incumbent_trace(
    instance: Mapping[str, Any],
    incumbent: types.ModuleType,
) -> List[DecisionRecord]:
    """Extract the incumbent's complete per-decision trace on ``instance``.

    The incumbent is run alone on the instance from the shared
    empty starting state. At every arrival index the extractor
    records one :class:`DecisionRecord` capturing the incumbent's
    open-bin state at decision time, the chosen abstract slot, and
    the winner / runner-up / margin under the §7.2.1
    abstract-candidate-set scoring rule. Records are returned
    chronologically by ``idx``.

    No filter is applied. Every decision the incumbent makes on
    the instance produces a record, regardless of whether the
    decision opened a new bin or placed the item in an existing
    one. The list length therefore equals ``len(instance['items'])``.

    No trace-size cap is applied. The design doc's §7.4 rendering
    rule is deliberately undetermined pending the pool statistics
    probe; trimming, stride sampling, or character-budget capping
    is the caller's concern.

    Parameters
    ----------
    instance:
        Mapping with the keys ``capacity`` (int or float),
        ``num_items`` (int), and ``items`` (sequence of item
        sizes). Matches the shape used by
        ``thesis.code.evaluation.bins_used``.
    incumbent:
        Module exposing ``score(item, bins) -> np.ndarray``, as
        produced by ``thesis.code.evaluation.load_heuristic_from_code``
        (or any other mechanism yielding the canonical bp_online
        heuristic interface). The extractor calls the heuristic
        exactly once per arrival index.

    Returns
    -------
    list[DecisionRecord]
        One record per arrival index, in chronological order.

    Edge cases
    ----------
    - **No runner-up at a decision.** When the abstract candidate
      set has fewer than two elements (e.g., at arrival index 1
      with no open bins yet, or at any later decision where every
      existing open bin is too full to fit the item and the
      new-bin slot is the only valid candidate),
      ``score_runner_up == score_winner`` and ``margin == 0.0``
      by convention. See ``chapter6_design.md`` §7.2.1.
    - **Item strictly larger than capacity.** Inherited from the
      harness: ``np.argmax`` on an empty ``priorities`` vector
      raises ``ValueError``. The extractor does not soften or
      catch this; the caller is responsible for ensuring
      ``max(items) <= capacity`` if it cares about clean
      failures, which all canonical bp_online instances satisfy.
    """
    return _replay(instance, incumbent)
