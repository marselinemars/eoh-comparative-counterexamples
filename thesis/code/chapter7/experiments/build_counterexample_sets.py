"""thesis/code/chapter7/experiments/build_counterexample_sets.py

Generate the chapter 7 CounterexampleSets per ``chapter7_design.md``
§5.1 / §5.2 / §3.8 / §4.1 and the 2026-05-05 master-seed entry.

Outputs ``thesis/artifacts/chapter7_counterexample_sets.json`` —
a single JSON file containing every set the chapter-7 batches
will consume:

  * 4 deterministic sets:
      - ``worst_only_at_k1`` at k=1 (1 set)
      - ``worst_plus_best``  at k=2, 4, 8 (3 sets)

  * 80 stratified sets:
      - ``stratified_representative`` at k ∈ {1, 2, 4, 8}
        × set_index ∈ [0, 20).

The same ``(strategy, k, set_index)`` produces the same set
regardless of structural level — the §5.2 seed namespace does
not include ``L<level>``, so a stratified set at
``(k=4, set_index=5)`` is reused at both CH7-03 (L1) and CH7-11
(L2). This shrinks the §5.1 nominal "20 × 4 + 20 × 3 = 140
stratified sets" figure to 80 unique sets — flagged in the §12
coordinate-alignment ambiguity report shipped with this commit
(see the section header in this file).

Pre-flight assertions:

  * ``thesis/artifacts/h_eoh_counterexample_pool.json`` exists.
  * Its sha256 first-12-hex prefix equals ``f89434911301``
    (the committed ch5 pool hash, per
    ``thesis/docs/02_current_state.md`` and the ch5 build
    artifact). A mismatch raises RuntimeError before any sets
    are generated.

The §12 coordinate-alignment ambiguity (slot-only vs.
nested-prefix) is resolved here in favor of the literal §5.2
seed namespace — ``ch7:set:strat:{master}:k{N}:set{idx}``,
which produces independent draws across ``k`` at the same
``set_index``. The matched-pair statistics this enables are
slot-aligned ("set_index=5 at k=2" vs. "set_index=5 at k=4")
rather than nested-prefix ("k=4 set extends k=2 set").

Usage::

    python -m thesis.code.chapter7.experiments.build_counterexample_sets

"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from thesis.code.chapter5.strategies import (
    stratified_representative,
    worst_plus_best,
)
from thesis.code.chapter7.seeds import (
    MASTER_SEED_CH7,
    stratified_set_seed_ch7,
)
from thesis.code.chapter7.strategies import worst_only_at_k1
from thesis.code.counterexample import CounterexampleSet

REPO_ROOT = Path(__file__).resolve().parents[4]
POOL_PATH = REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
ARTIFACT_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "chapter7_counterexample_sets.json"
)
EXPECTED_POOL_HASH_PREFIX = "f89434911301"

# §3.8 / §4.1 cardinality axes.
L1_K_VALUES = (1, 2, 4, 8)
L2_K_VALUES = (1, 2, 4)
STRATIFIED_K_VALUES = (1, 2, 4, 8)
WORST_PLUS_BEST_K_VALUES = (2, 4, 8)
N_STRATIFIED_SETS_PER_K = 20


def _verify_pool_hash() -> bytes:
    """Read the committed pool, assert its sha256[:12] hash, return bytes."""
    if not POOL_PATH.exists():
        raise RuntimeError(
            f"Counterexample pool not found at {POOL_PATH}. "
            "Run build_counterexample_pool first."
        )
    pool_bytes = POOL_PATH.read_bytes()
    actual = hashlib.sha256(pool_bytes).hexdigest()[:12]
    if actual != EXPECTED_POOL_HASH_PREFIX:
        raise RuntimeError(
            f"Pool hash mismatch: expected {EXPECTED_POOL_HASH_PREFIX!r}, "
            f"got {actual!r}. The chapter-7 design assumes the pool is "
            f"the byte-identical ch5 pool; investigate before proceeding."
        )
    return pool_bytes


def _set_to_dict(
    *,
    cell_label: str,
    strategy: str,
    k: int,
    set_index: int,
    set_seed: int | None,
    determinism: str,
    counterexample_set: CounterexampleSet,
) -> Dict[str, Any]:
    return {
        "cell_label": cell_label,
        "strategy": strategy,
        "k": k,
        "set_index": set_index,
        "set_seed": set_seed,
        "determinism": determinism,
        "counterexample_set": json.loads(counterexample_set.to_json()),
    }


def _build_deterministic_sets(pool: CounterexampleSet) -> List[Dict[str, Any]]:
    """4 deterministic sets: ``worst_only_at_k1`` × k=1 plus
    ``worst_plus_best`` × k ∈ {2, 4, 8}.

    These four sets are reused across L1 and L2 cells with the
    matching strategy and k.
    """
    out: List[Dict[str, Any]] = []
    out.append(
        _set_to_dict(
            cell_label="worst_only_at_k1@k=1",
            strategy="worst_only_at_k1",
            k=1,
            set_index=0,
            set_seed=None,
            determinism="deterministic",
            counterexample_set=worst_only_at_k1(pool, k=1),
        )
    )
    for k in WORST_PLUS_BEST_K_VALUES:
        out.append(
            _set_to_dict(
                cell_label=f"worst_plus_best@k={k}",
                strategy="worst_plus_best",
                k=k,
                set_index=0,
                set_seed=None,
                determinism="deterministic",
                counterexample_set=worst_plus_best(pool, k=k),
            )
        )
    return out


def _build_stratified_sets(pool: CounterexampleSet) -> List[Dict[str, Any]]:
    """20 sets × 4 k-values = 80 stratified sets."""
    out: List[Dict[str, Any]] = []
    for k in STRATIFIED_K_VALUES:
        for set_index in range(N_STRATIFIED_SETS_PER_K):
            seed = stratified_set_seed_ch7(k=k, set_index=set_index)
            rng = np.random.default_rng(seed)
            ce_set = stratified_representative(pool, k=k, rng=rng)
            out.append(
                _set_to_dict(
                    cell_label=(
                        f"stratified_representative@k={k}"
                        f"@set={set_index:02d}"
                    ),
                    strategy="stratified_representative",
                    k=k,
                    set_index=set_index,
                    set_seed=seed,
                    determinism="stochastic",
                    counterexample_set=ce_set,
                )
            )
    return out


def _build_artifact(pool_bytes: bytes) -> Dict[str, Any]:
    pool = CounterexampleSet.from_json(pool_bytes.decode("utf-8"))
    deterministic = _build_deterministic_sets(pool)
    stratified = _build_stratified_sets(pool)
    return {
        "schema_version": 1,
        "chapter": "chapter7",
        "master_seed": MASTER_SEED_CH7,
        "namespace_prefix": "ch7:",
        "pool_path": str(POOL_PATH.relative_to(REPO_ROOT).as_posix()),
        "pool_hash_prefix12": EXPECTED_POOL_HASH_PREFIX,
        "expected_pool_hash_prefix12": EXPECTED_POOL_HASH_PREFIX,
        "design_doc_sections": [
            "chapter7_design.md §3.8",
            "chapter7_design.md §4.1",
            "chapter7_design.md §5.1",
            "chapter7_design.md §5.2",
        ],
        "set_index_alignment": {
            "interpretation": "slot-aligned only (literal §5.2)",
            "rationale": (
                "§5.2 namespace 'ch7:set:strat:{master}:k{N}:set{idx}' "
                "derives an independent seed for each (k, set_index) "
                "pair. Same set_index at different k values produces "
                "*different* CounterexampleSets — they share the slot "
                "index, not the underlying instance content. The "
                "alternative reading (nested-prefix) would require the "
                "k=2 set at set_index=5 to extend the k=1 set at "
                "set_index=5 with one additional draw under the same "
                "set_seed; the literal §5.2 namespace does not support "
                "this and the design doc was not amended to specify "
                "either reading. Surfaced and resolved in favor of the "
                "literal namespace; the cross-k matched-pair statistic "
                "is therefore slot-aligned, not nested-prefix-aligned."
            ),
        },
        "level_sharing": {
            "interpretation": (
                "L1 and L2 cells with the same (strategy, k, set_index) "
                "share the same CounterexampleSet — selection is "
                "level-agnostic; only prompt rendering differs"
            ),
            "rationale": (
                "§5.2 namespace has no L<level> suffix, so "
                "set_seed_ch7(k, set_index) is invariant in level. The "
                "§5.1 phrasing '20 × 4 = 80 sets at L1 + 20 × 3 = 60 "
                "sets at L2 = 140 total stratified sets' is therefore "
                "an accounting overstatement — there are 80 unique "
                "stratified sets shared between L1 and L2, not 140. "
                "Same applies to the 7 nominal vs. 4 unique "
                "deterministic sets."
            ),
        },
        "deterministic_sets": deterministic,
        "stratified_sets": stratified,
        "totals": {
            "n_unique_deterministic_sets": len(deterministic),
            "n_unique_stratified_sets": len(stratified),
            "n_unique_sets_total": len(deterministic) + len(stratified),
            "n_design_doc_5p1_nominal_total": 4 + 7 + 80 + 60,
        },
    }


def _print_summary(artifact: Dict[str, Any]) -> None:
    print(
        f"Pool hash sha256[:12] verified: "
        f"{artifact['pool_hash_prefix12']}"
    )
    print(
        f"Generated {artifact['totals']['n_unique_deterministic_sets']} "
        f"deterministic sets and "
        f"{artifact['totals']['n_unique_stratified_sets']} stratified sets "
        f"({artifact['totals']['n_unique_sets_total']} total unique)."
    )
    print("Deterministic sets:")
    for s in artifact["deterministic_sets"]:
        gaps = [c["gap"] for c in s["counterexample_set"]["items"]]
        print(
            f"  {s['cell_label']:<36} "
            f"k={s['k']} "
            f"gaps={gaps}"
        )
    # Sample one stratified set per k for inspection.
    seen_k = set()
    print("Stratified samples (set_index=0 at each k):")
    for s in artifact["stratified_sets"]:
        if s["set_index"] != 0 or s["k"] in seen_k:
            continue
        seen_k.add(s["k"])
        gaps = [c["gap"] for c in s["counterexample_set"]["items"]]
        print(
            f"  k={s['k']} set={s['set_index']:02d} "
            f"set_seed={s['set_seed']} gaps={gaps}"
        )


def main() -> int:
    pool_bytes = _verify_pool_hash()
    artifact = _build_artifact(pool_bytes)
    payload = json.dumps(artifact, indent=2, sort_keys=True)
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(payload, encoding="utf-8")
    artifact_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    _print_summary(artifact)
    print()
    print(f"Wrote {ARTIFACT_PATH.relative_to(REPO_ROOT).as_posix()}")
    print(f"Artifact sha256[:12] = {artifact_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
