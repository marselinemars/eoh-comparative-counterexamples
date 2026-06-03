"""thesis/code/chapter7/seeds.py — chapter 7 seed derivation.

Per ``chapter7_design.md`` §5.2 (and decisions log 2026-05-05
"Chapter 7 master seed and namespace"). Every seed is a 32-bit
integer derived from sha256 of the namespace payload; the
``ch7:`` prefix and the embedded master seed make the result
disjoint from chapter 5's and chapter 6's seed spaces.

§5.2 namespace structure (verbatim):
- ``ch7:set:strat:k{N}:set{idx}`` — stratified_representative set
  generation, ``idx ∈ [0, 20)``
- ``ch7:llm:strat:k{N}:set{idx}:seed{s}`` — stratified-cell LLM
  seeds, ``s ∈ [0, 3)``
- ``ch7:llm:wpb:k{N}:seed{s}`` — ``worst_plus_best`` LLM seeds,
  ``s ∈ [0, 60)``
- ``ch7:llm:wo1:seed{s}`` — ``worst_only_at_k1`` LLM seeds,
  ``s ∈ [0, 60)``
- ``ch7:traj:set:{cell}:traj{t}:step{i}`` — trajectory pool-rebuild
  set seeds
- ``ch7:traj:llm:{cell}:traj{t}:step{i}`` — trajectory LLM seeds

The master seed is interpolated into the payload between the
namespace prefix and the variable parts, matching ch6's pattern
(``thesis/code/chapter6/batch_runner.py`` ``set_seed_ch6``).
"""
from __future__ import annotations

import hashlib

MASTER_SEED_CH7: int = 20_260_505


def _sha256_int32(payload: str) -> int:
    return int(
        hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8],
        16,
    )


def stratified_set_seed_ch7(k: int, set_index: int) -> int:
    """Derive the set_seed for a ``stratified_representative`` cell.

    Each ``(k, set_index)`` pair gets an independent 32-bit seed.
    The seed payload includes ``k``, so set_index alignment across
    different ``k`` values is positional — i.e., set_index=5 at
    k=2 is *not* derived from set_index=5 at k=1's content; it is
    an independent draw under a different seed. See the §12
    coordinate-alignment note in this file's module docstring.
    """
    payload = (
        f"ch7:set:strat:{MASTER_SEED_CH7}:k{k}:set{set_index}"
    )
    return _sha256_int32(payload)


def stratified_llm_seed_ch7(
    k: int, set_index: int, seed_index: int
) -> int:
    """Derive the per-call LLM seed for a stratified cell."""
    payload = (
        f"ch7:llm:strat:{MASTER_SEED_CH7}:k{k}:set{set_index}:"
        f"seed{seed_index}"
    )
    return _sha256_int32(payload)


def worst_plus_best_llm_seed_ch7(k: int, seed_index: int) -> int:
    """Derive the per-call LLM seed for a ``worst_plus_best`` cell."""
    payload = f"ch7:llm:wpb:{MASTER_SEED_CH7}:k{k}:seed{seed_index}"
    return _sha256_int32(payload)


def worst_only_at_k1_llm_seed_ch7(seed_index: int) -> int:
    """Derive the per-call LLM seed for the ``worst_only_at_k1`` cell.

    ``k`` is implicit (=1) for this strategy and is therefore not
    part of the namespace.
    """
    payload = f"ch7:llm:wo1:{MASTER_SEED_CH7}:seed{seed_index}"
    return _sha256_int32(payload)


def trajectory_set_seed_ch7(
    cell: str, trajectory_index: int, step_index: int
) -> int:
    """Derive the trajectory pool-rebuild set seed.

    ``cell`` is the cell_id string (e.g.,
    ``"stratified_representative@L2@k4"``). The trajectory namespace
    is keyed on ``cell`` rather than ``(strategy, k, level)``
    separately so the namespace string is short and unambiguous.
    """
    payload = (
        f"ch7:traj:set:{MASTER_SEED_CH7}:{cell}:"
        f"traj{trajectory_index}:step{step_index}"
    )
    return _sha256_int32(payload)


def trajectory_llm_seed_ch7(
    cell: str, trajectory_index: int, step_index: int
) -> int:
    """Derive the trajectory per-call LLM seed."""
    payload = (
        f"ch7:traj:llm:{MASTER_SEED_CH7}:{cell}:"
        f"traj{trajectory_index}:step{step_index}"
    )
    return _sha256_int32(payload)
