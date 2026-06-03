"""
thesis/code/counterexample.py

The canonical counterexample data object for the thesis.

Definition (from thesis/docs/05_glossary.md):
    A counterexample is a tuple
        (instance, candidate, reference, gap, trace_slice?, diagnosis?)
    where `instance` is a problem instance, `candidate` and `reference`
    are heuristics identified by their code_hash, `gap = score(candidate, I)
    - score(reference, I) = bins_used(reference, I) - bins_used(candidate, I)`,
    and the optional fields attach structural enrichment introduced in
    chapter 6.

Counterexamples are:
    * Comparative, not absolute. A `Counterexample` is defined relative
      to a reference heuristic. The same instance can yield many
      counterexamples, one per choice of reference.
    * Immutable. Once constructed, a Counterexample is frozen.
    * Serializable. Round-trips to/from JSON without loss, so
      experiment outputs can persist counterexample lists for later
      analysis without re-running any scoring.
    * Identity-free on heuristics. Only code_hashes are stored, not
      heuristic source code. Resolving a code_hash back to source is
      the caller's responsibility.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Counterexample:
    """See the module docstring.

    Fields
    ------
    instance_id:
        Fully-qualified instance ID, e.g. `thesis_train_select:thesis_train_select_5k_0`.
        Must match the score cache's instance-ID convention.
    candidate_hash, reference_hash:
        12-hex-char sha256 prefixes of the heuristics' source code.
    gap:
        `bins_used(reference, I) - bins_used(candidate, I)`. Positive
        means the candidate is better than the reference on this
        instance. Zero means a tie; negative means the reference
        beats the candidate.
    candidate_bins_used, reference_bins_used:
        Absolute bin counts. Redundant with `gap` (which could be
        derived) but stored to make the JSON self-contained and to
        let analysis code compute per-instance absolute quality
        without an additional lookup.
    trace_slice, diagnosis:
        Optional enrichment introduced in chapter 6. Both default
        to None. When present, `trace_slice` is a free-form dict
        whose schema is defined by the chapter-6 extractor;
        `diagnosis` is a free-form dict whose schema is defined by
        the chapter-6 diagnoser.
    """

    instance_id: str
    candidate_hash: str
    reference_hash: str
    candidate_bins_used: int
    reference_bins_used: int
    gap: int
    trace_slice: Optional[Dict[str, Any]] = None
    diagnosis: Optional[Dict[str, Any]] = None

    # -- construction helpers -------------------------------------------

    @classmethod
    def from_bin_counts(
        cls,
        *,
        instance_id: str,
        candidate_hash: str,
        reference_hash: str,
        candidate_bins_used: int,
        reference_bins_used: int,
        trace_slice: Optional[Dict[str, Any]] = None,
        diagnosis: Optional[Dict[str, Any]] = None,
    ) -> "Counterexample":
        """Derive gap from the two bin counts.

        This is the preferred constructor in experimental code —
        callers pass bin counts (which they just computed or looked
        up in the score cache) and the sign convention is enforced
        here in one place.
        """
        if not isinstance(candidate_bins_used, int) or not isinstance(
            reference_bins_used, int
        ):
            raise TypeError(
                "bins_used values must be int "
                f"(got {type(candidate_bins_used).__name__}, "
                f"{type(reference_bins_used).__name__})"
            )
        if candidate_hash == reference_hash:
            raise ValueError(
                "candidate and reference must be different heuristics; "
                f"both are {candidate_hash!r}"
            )
        gap = reference_bins_used - candidate_bins_used
        return cls(
            instance_id=instance_id,
            candidate_hash=candidate_hash,
            reference_hash=reference_hash,
            candidate_bins_used=candidate_bins_used,
            reference_bins_used=reference_bins_used,
            gap=gap,
            trace_slice=trace_slice,
            diagnosis=diagnosis,
        )

    # -- derived quantities ---------------------------------------------

    @property
    def abs_gap(self) -> int:
        """Discriminative strength: magnitude of gap."""
        return abs(self.gap)

    @property
    def candidate_wins(self) -> bool:
        """True if candidate beats reference on this instance."""
        return self.gap > 0

    @property
    def reference_wins(self) -> bool:
        return self.gap < 0

    @property
    def tie(self) -> bool:
        return self.gap == 0

    # -- serialization --------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Round-trippable plain-dict form."""
        d = asdict(self)
        # Strip fields that are None to keep output compact — round-trip
        # still preserves them because from_dict defaults them to None.
        if d["trace_slice"] is None:
            d.pop("trace_slice")
        if d["diagnosis"] is None:
            d.pop("diagnosis")
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Counterexample":
        expected_keys = {
            "instance_id",
            "candidate_hash",
            "reference_hash",
            "candidate_bins_used",
            "reference_bins_used",
            "gap",
        }
        missing = expected_keys - set(d.keys())
        if missing:
            raise ValueError(
                f"Counterexample dict missing required keys: "
                f"{sorted(missing)}"
            )
        ce = cls(
            instance_id=d["instance_id"],
            candidate_hash=d["candidate_hash"],
            reference_hash=d["reference_hash"],
            candidate_bins_used=int(d["candidate_bins_used"]),
            reference_bins_used=int(d["reference_bins_used"]),
            gap=int(d["gap"]),
            trace_slice=d.get("trace_slice"),
            diagnosis=d.get("diagnosis"),
        )
        # Consistency check: gap must equal the difference.
        expected_gap = ce.reference_bins_used - ce.candidate_bins_used
        if ce.gap != expected_gap:
            raise ValueError(
                f"Counterexample has inconsistent gap: gap={ce.gap} "
                f"but reference_bins_used - candidate_bins_used = "
                f"{expected_gap} (instance={ce.instance_id!r})"
            )
        return ce


@dataclass(frozen=True)
class CounterexampleSet:
    """An ordered, possibly-empty collection of counterexamples.

    A CounterexampleSet is what a selection strategy returns (chapter
    5) and what a refinement-proposal prompt consumes (chapter 5+).
    It is ordered because some selection strategies care about the
    order in which counterexamples are shown to the LLM, and because
    deterministic serialization benefits downstream analysis.
    """

    items: List[Counterexample] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def __getitem__(self, i):
        return self.items[i]

    # -- convenience accessors ------------------------------------------

    @property
    def candidate_hashes(self) -> List[str]:
        """All candidate hashes in order (usually the same hash
        repeated, since a selection run typically fixes the candidate
        and varies the reference and instance)."""
        return [c.candidate_hash for c in self.items]

    @property
    def reference_hashes(self) -> List[str]:
        return [c.reference_hash for c in self.items]

    @property
    def instance_ids(self) -> List[str]:
        return [c.instance_id for c in self.items]

    @property
    def mean_gap(self) -> float:
        if not self.items:
            return 0.0
        return sum(c.gap for c in self.items) / len(self.items)

    @property
    def mean_abs_gap(self) -> float:
        if not self.items:
            return 0.0
        return sum(c.abs_gap for c in self.items) / len(self.items)

    # -- serialization --------------------------------------------------

    def to_json(self) -> str:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "items": [c.to_dict() for c in self.items],
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "CounterexampleSet":
        payload = json.loads(s)
        version = payload.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"CounterexampleSet has schema_version {version!r}, "
                f"expected {SCHEMA_VERSION}"
            )
        return cls(items=[Counterexample.from_dict(d)
                          for d in payload["items"]])
