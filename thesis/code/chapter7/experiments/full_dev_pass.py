"""thesis/code/chapter7/experiments/full_dev_pass.py

Chapter 7 §18.8 full-dev pass. For every accepted validation-step
proposal (acceptance_reason ∈ {accepted_improvement,
accepted_behavioral_change}):

  1. Score against ``dev`` (30 × 5k) via the persistent score
     cache. Same machinery as the per-cell-best partial pass
     (``score_per_cell_dev.py``); reuses ``dev``-split cache
     entries already populated.
  2. Score against ``train_gate`` (also 30 × 5k) since the
     validation batch only scored ``train_step`` for the §11
     acceptance rule.
  3. Compute Δ_dev, Δ_gate, Δ_step (vs h_eoh, not vs the
     trajectory's current incumbent). Δ_step_local is already in
     the validation record.
  4. Update the per-step record on disk in place (atomic) with
     scoring.delta_dev / scoring.delta_gate / scoring.delta_step
     / scoring.dev_per_instance / scoring.dev_mean_bins /
     scoring.dev_baseline_mean_bins.

Cache-fill is parallelized over workers (per the ch6 precedent
``shown_vs_unshown_cache_fill_parallel.py``). The artifact
``thesis/artifacts/chapter7_full_dev_pass.json`` summarizes the
41 accepted proposals with per-proposal table, per-cell
aggregates, correlations, and the L2 stratified-by-k Δ_dev
analysis.

Usage::

    python -m thesis.code.chapter7.experiments.full_dev_pass
    python -m thesis.code.chapter7.experiments.full_dev_pass --workers 16
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
import types
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(REPO_ROOT / ".env")

from thesis.code.chapter6.batch_runner import _build_incumbent_module  # noqa: E402
from thesis.code.evaluation import bins_used  # noqa: E402
from thesis.code.incumbents import get_h_eoh  # noqa: E402
from thesis.code.score_cache import ScoreCache  # noqa: E402
from thesis.code.splits import load_split, qualified_instance_id  # noqa: E402

RESULTS_DIR = REPO_ROOT / "thesis" / "results" / "chapter7_validation_batch_gemini"
ARTIFACT_PATH = REPO_ROOT / "thesis" / "artifacts" / "chapter7_full_dev_pass.json"

ACCEPTED_REASONS = {"accepted_improvement", "accepted_behavioral_change"}
BOOTSTRAP_N = 5000
BOOTSTRAP_SEED = 20_260_512

CELLS = [
    {"cell_id": "CH7-01", "strategy": "stratified_representative", "level": 1, "k": 1},
    {"cell_id": "CH7-02", "strategy": "stratified_representative", "level": 1, "k": 2},
    {"cell_id": "CH7-03", "strategy": "stratified_representative", "level": 1, "k": 4},
    {"cell_id": "CH7-04", "strategy": "stratified_representative", "level": 1, "k": 8},
    {"cell_id": "CH7-05", "strategy": "worst_only_at_k1", "level": 1, "k": 1},
    {"cell_id": "CH7-06", "strategy": "worst_plus_best", "level": 1, "k": 2},
    {"cell_id": "CH7-07", "strategy": "worst_plus_best", "level": 1, "k": 4},
    {"cell_id": "CH7-08", "strategy": "worst_plus_best", "level": 1, "k": 8},
    {"cell_id": "CH7-09", "strategy": "stratified_representative", "level": 2, "k": 1},
    {"cell_id": "CH7-10", "strategy": "stratified_representative", "level": 2, "k": 2},
    {"cell_id": "CH7-11", "strategy": "stratified_representative", "level": 2, "k": 4},
    {"cell_id": "CH7-12", "strategy": "worst_only_at_k1", "level": 2, "k": 1},
    {"cell_id": "CH7-13", "strategy": "worst_plus_best", "level": 2, "k": 2},
    {"cell_id": "CH7-14", "strategy": "worst_plus_best", "level": 2, "k": 4},
]
CELL_BY_ID = {c["cell_id"]: c for c in CELLS}


def _load_accepted_records() -> List[Dict[str, Any]]:
    """Load every validation per-step record whose acceptance_reason
    is in ``ACCEPTED_REASONS``."""
    out: List[Dict[str, Any]] = []
    for path in sorted(RESULTS_DIR.glob("chapter7_validation_*.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("chapter") != "chapter7" or d.get("phase") != "validation":
            continue
        if d.get("acceptance_reason") not in ACCEPTED_REASONS:
            continue
        d["_path"] = str(path)
        out.append(d)
    return out


def _atomic_update_record(path: Path, mutate_fn: Callable[[Dict[str, Any]], None]) -> None:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    mutate_fn(data)
    tmp = Path(path).with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
    )
    os.replace(tmp, path)


def _has_field(rec: Dict[str, Any], field: str) -> bool:
    s = rec.get("scoring") or {}
    if not isinstance(s, dict):
        return False
    return field in s and s[field] is not None


# --- parallel cache fill --------------------------------------------


def _worker_fill(
    args: Tuple[int, List[Tuple[str, str]], List[Tuple[str, dict]]]
) -> Dict[str, Dict[str, Any]]:
    """Score the worker's slice of (hash, code) pairs against the
    given (qid, instance) pairs. Returns a per-key entry dict."""
    worker_id, proposal_slice, qids_with_inst = args
    out: Dict[str, Dict[str, Any]] = {}
    for h, code in proposal_slice:
        try:
            mod = types.ModuleType(f"h_{h}")
            exec(compile(code, f"<{h}>", "exec"), mod.__dict__)
        except Exception as exc:
            print(f"[worker {worker_id}] compile-fail {h}: {exc}", flush=True)
            continue
        for qid, inst in qids_with_inst:
            try:
                b = int(bins_used(mod, inst))
                out[f"{h}|{qid}"] = {
                    "bins_used": b,
                    "code_hash": h,
                    "instance_id": qid,
                }
            except Exception as exc:
                print(f"[worker {worker_id}] score-fail {h}|{qid}: {exc}", flush=True)
    return out


def _parallel_cache_fill_for_split(
    *,
    split_name: str,
    hash_to_code: Dict[str, str],
    n_workers: int,
    cache: ScoreCache,
) -> Tuple[int, int]:
    """Fill cache entries for (proposal × instance) across one split.
    Returns (n_already_cached, n_newly_filled)."""
    split = load_split(split_name)
    qids_with_inst: List[Tuple[str, dict]] = [
        (qualified_instance_id(split_name, inst["instance_id"]), inst)
        for inst in split["instances"]
    ]
    uncached_proposals: List[Tuple[str, str]] = []
    n_already = 0
    for h, code in hash_to_code.items():
        n_cached_h = sum(
            1 for qid, _ in qids_with_inst if f"{h}|{qid}" in cache._entries
        )
        n_already += n_cached_h
        if n_cached_h < len(qids_with_inst):
            uncached_proposals.append((h, code))
    n_total = len(hash_to_code) * len(qids_with_inst)
    n_uncached = n_total - n_already
    print(
        f"  [{split_name}] {n_total} pairs total; {n_already} cached; "
        f"{n_uncached} to fill across {len(uncached_proposals)} proposals",
        file=sys.stderr,
    )
    if not uncached_proposals:
        return n_already, 0
    shards: List[List[Tuple[str, str]]] = [[] for _ in range(n_workers)]
    for i, item in enumerate(uncached_proposals):
        shards[i % n_workers].append(item)
    started = time.perf_counter()
    n_newly = 0
    with mp.Pool(n_workers) as pool:
        worker_args = [(i, s, qids_with_inst) for i, s in enumerate(shards)]
        for shard_result in pool.imap_unordered(_worker_fill, worker_args):
            for key, entry in shard_result.items():
                if key not in cache._entries:
                    cache._entries[key] = entry
                    n_newly += 1
    cache.save()
    elapsed = time.perf_counter() - started
    print(
        f"  [{split_name}] filled {n_newly} new entries in "
        f"{elapsed/60:.1f} min",
        file=sys.stderr,
    )
    return n_already, n_newly


def _mean_bins_for(
    code_hash_: str, code: str, split_name: str, cache: ScoreCache,
) -> Tuple[float, List[int]]:
    """Read mean bins_used for one proposal on one split via cache.
    Assumes cache is fully filled for this (proposal, split). Falls
    back to live compute if cache is missing entries (rare; logged)."""
    split = load_split(split_name)
    mod = None
    per_instance: List[int] = []
    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        key = f"{code_hash_}|{qid}"
        entry = cache._entries.get(key)
        if entry is None:
            if mod is None:
                mod = types.ModuleType(f"h_{code_hash_}")
                exec(compile(code, f"<{code_hash_}>", "exec"), mod.__dict__)
            b = int(bins_used(mod, inst))
            cache._entries[key] = {
                "bins_used": b, "code_hash": code_hash_, "instance_id": qid,
            }
        else:
            b = int(entry["bins_used"])
        per_instance.append(b)
    return float(np.mean(per_instance)), per_instance


# --- bootstrap helpers ------------------------------------------------


def _bootstrap_ci_mean(
    values: List[float],
    *, seed: int = BOOTSTRAP_SEED, n: int = BOOTSTRAP_N, alpha: float = 0.05,
) -> Optional[Tuple[float, float]]:
    if not values:
        return None
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    means = np.empty(n, dtype=float)
    for i in range(n):
        idx = rng.integers(0, arr.size, size=arr.size)
        means[i] = float(np.mean(arr[idx]))
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _bootstrap_ci_paired_diff(
    a: List[float], b: List[float],
    *, seed: int = BOOTSTRAP_SEED, n: int = BOOTSTRAP_N, alpha: float = 0.05,
) -> Optional[Tuple[float, float]]:
    if not a or not b or len(a) != len(b):
        return None
    rng = np.random.default_rng(seed)
    diffs = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    means = np.empty(n, dtype=float)
    for i in range(n):
        idx = rng.integers(0, diffs.size, size=diffs.size)
        means[i] = float(np.mean(diffs[idx]))
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _bootstrap_ci_pearson(
    a: List[float], b: List[float],
    *, seed: int = BOOTSTRAP_SEED, n: int = BOOTSTRAP_N, alpha: float = 0.05,
) -> Optional[Tuple[float, Tuple[float, float]]]:
    if len(a) < 3 or len(b) < 3 or len(a) != len(b):
        return None
    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    point = float(np.corrcoef(a_arr, b_arr)[0, 1])
    rng = np.random.default_rng(seed)
    rhos = np.empty(n, dtype=float)
    size = a_arr.size
    for i in range(n):
        idx = rng.integers(0, size, size=size)
        aa = a_arr[idx]; bb = b_arr[idx]
        if np.std(aa) > 0 and np.std(bb) > 0:
            rhos[i] = float(np.corrcoef(aa, bb)[0, 1])
        else:
            rhos[i] = 0.0
    lo = float(np.percentile(rhos, 2.5))
    hi = float(np.percentile(rhos, 97.5))
    return point, (lo, hi)


# --- per-cell-best lookup -------------------------------------------


def _per_cell_best_proposal_hashes() -> Dict[str, str]:
    """From chapter7_per_cell_dev_scoring.json, the proposal hash that
    was scored as per-cell-best for each primary cell."""
    p = REPO_ROOT / "thesis" / "artifacts" / "chapter7_per_cell_dev_scoring.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {
        cell_id: ent.get("proposal_hash")
        for cell_id, ent in d.get("per_cell", {}).items()
        if ent.get("proposal_hash")
    }


# --- main -----------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    args = parser.parse_args()

    accepted = _load_accepted_records()
    print(
        f"Loaded {len(accepted)} accepted validation-step records",
        file=sys.stderr,
    )
    if not accepted:
        print("no accepted records — exiting", file=sys.stderr)
        return 1

    # Build proposal hash -> code mapping (unique hashes).
    hash_to_code: Dict[str, str] = {}
    for r in accepted:
        h = r.get("proposal_hash")
        code = (r.get("sanitization") or {}).get("cleaned_code")
        if h and code and h not in hash_to_code:
            hash_to_code[h] = code
    print(
        f"  unique proposal hashes: {len(hash_to_code)}",
        file=sys.stderr,
    )

    cache = ScoreCache()
    n_entries_before = len(cache._entries)
    print(
        f"  score-cache entries at start: {n_entries_before}",
        file=sys.stderr,
    )

    # Fill caches for the three relevant splits across all unique hashes.
    print("Cache-filling train_step / train_gate / dev ...", file=sys.stderr)
    n_already_ts, n_new_ts = _parallel_cache_fill_for_split(
        split_name="train_step",
        hash_to_code=hash_to_code,
        n_workers=args.workers,
        cache=cache,
    )
    n_already_tg, n_new_tg = _parallel_cache_fill_for_split(
        split_name="train_gate",
        hash_to_code=hash_to_code,
        n_workers=args.workers,
        cache=cache,
    )
    n_already_dv, n_new_dv = _parallel_cache_fill_for_split(
        split_name="dev",
        hash_to_code=hash_to_code,
        n_workers=args.workers,
        cache=cache,
    )

    # Baseline (h_eoh) per-split means.
    h_eoh = get_h_eoh()
    h_eoh_means: Dict[str, float] = {}
    for split_name in ("train_step", "train_gate", "dev"):
        mean_, _ = _mean_bins_for(
            h_eoh["code_hash"], h_eoh["code"], split_name, cache,
        )
        h_eoh_means[split_name] = mean_
    cache.save()
    print(
        f"  h_eoh means: train_step={h_eoh_means['train_step']:.4f}, "
        f"train_gate={h_eoh_means['train_gate']:.4f}, "
        f"dev={h_eoh_means['dev']:.4f}",
        file=sys.stderr,
    )

    # Per-proposal mean bins on each split (computed once per unique hash).
    per_hash_means: Dict[str, Dict[str, float]] = {}
    per_hash_per_instance: Dict[str, Dict[str, List[int]]] = {}
    for h, code in hash_to_code.items():
        per_hash_means[h] = {}
        per_hash_per_instance[h] = {}
        for split_name in ("train_step", "train_gate", "dev"):
            m, pi = _mean_bins_for(h, code, split_name, cache)
            per_hash_means[h][split_name] = m
            per_hash_per_instance[h][split_name] = pi

    cache.save()
    n_entries_after = len(cache._entries)
    print(
        f"  score-cache entries at end: {n_entries_after} "
        f"(+{n_entries_after - n_entries_before})",
        file=sys.stderr,
    )

    per_cell_best_hashes = _per_cell_best_proposal_hashes()

    # Per-accepted-proposal table + record updates.
    proposals_table: List[Dict[str, Any]] = []
    n_already_had_dev = 0
    for rec in accepted:
        h = rec.get("proposal_hash")
        means = per_hash_means.get(h, {})
        per_inst = per_hash_per_instance.get(h, {})
        delta_step = h_eoh_means["train_step"] - means.get("train_step", h_eoh_means["train_step"])
        delta_gate = h_eoh_means["train_gate"] - means.get("train_gate", h_eoh_means["train_gate"])
        delta_dev = h_eoh_means["dev"] - means.get("dev", h_eoh_means["dev"])
        # Update record in place.
        existing_scoring = rec.get("scoring") or {}
        already_had = existing_scoring.get("delta_dev") is not None
        if already_had:
            n_already_had_dev += 1

        def _mutate(d: Dict[str, Any], _h=h, _ds=delta_step, _dg=delta_gate,
                    _dd=delta_dev, _pi=per_inst, _hm=h_eoh_means) -> None:
            s = d.get("scoring") or {}
            s["delta_step"] = float(_ds)
            s["delta_gate"] = float(_dg)
            s["delta_dev"] = float(_dd)
            s["dev_per_instance"] = _pi.get("dev")
            s["dev_mean_bins"] = float(
                np.mean(_pi.get("dev", [])) if _pi.get("dev") else 0.0
            )
            s["dev_baseline_mean_bins"] = float(_hm["dev"])
            d["scoring"] = s

        _atomic_update_record(Path(rec["_path"]), _mutate)

        proposals_table.append({
            "cell_id": rec.get("cell_id"),
            "strategy": rec.get("strategy_name"),
            "level": rec.get("level"),
            "k": rec.get("k"),
            "trajectory_index": rec.get("trajectory_index"),
            "step_index": rec.get("step_index"),
            "trajectory_set_seed": rec.get("trajectory_set_seed"),
            "trajectory_llm_seed": rec.get("trajectory_llm_seed"),
            "proposal_hash": h,
            "current_incumbent_hash": rec.get("current_incumbent_hash"),
            "next_incumbent_hash": rec.get("next_incumbent_hash"),
            "delta_step": float(delta_step),
            "delta_step_local": rec.get("delta_step_local"),
            "delta_gate": float(delta_gate),
            "delta_dev": float(delta_dev),
            "acceptance_reason": rec.get("acceptance_reason"),
            "is_per_cell_best_primary": (
                h in set(per_cell_best_hashes.values())
            ),
        })
        print(
            f"  {rec['cell_id']} traj={rec['trajectory_index']} "
            f"step={rec['step_index']} "
            f"hash={h[:8]} "
            f"Δstep={delta_step:+.2f} Δgate={delta_gate:+.2f} "
            f"Δdev={delta_dev:+.2f}",
            file=sys.stderr,
        )

    # Per-cell aggregates over accepted proposals.
    by_cell: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in proposals_table:
        by_cell[p["cell_id"]].append(p)
    per_cell_aggregates: Dict[str, Any] = {}
    for cell in CELLS:
        cid = cell["cell_id"]
        recs = by_cell.get(cid, [])
        per_cell_aggregates[cid] = {
            "cell": cell,
            "n_accepted": len(recs),
            "flagged_zero_acceptances": (len(recs) == 0),
            "mean_delta_step": (
                float(np.mean([r["delta_step"] for r in recs])) if recs else None
            ),
            "mean_delta_gate": (
                float(np.mean([r["delta_gate"] for r in recs])) if recs else None
            ),
            "mean_delta_dev": (
                float(np.mean([r["delta_dev"] for r in recs])) if recs else None
            ),
        }

    # Δ_dev vs Δ_gate pattern analysis.
    delta_steps = [p["delta_step"] for p in proposals_table]
    delta_gates = [p["delta_gate"] for p in proposals_table]
    delta_devs = [p["delta_dev"] for p in proposals_table]

    pearson_gate_dev = _bootstrap_ci_pearson(delta_devs, delta_gates,
                                             seed=BOOTSTRAP_SEED)
    pearson_step_dev = _bootstrap_ci_pearson(delta_devs, delta_steps,
                                             seed=BOOTSTRAP_SEED + 1)
    paired_diff_dev_minus_gate_ci = _bootstrap_ci_paired_diff(
        delta_devs, delta_gates, seed=BOOTSTRAP_SEED + 2,
    )
    mean_dev_minus_gate = (
        float(np.mean(np.asarray(delta_devs) - np.asarray(delta_gates)))
        if delta_devs and delta_gates else None
    )
    verdict_clean = (
        pearson_gate_dev is not None
        and pearson_gate_dev[0] > 0.9
        and paired_diff_dev_minus_gate_ci is not None
        and paired_diff_dev_minus_gate_ci[0] <= 0 <= paired_diff_dev_minus_gate_ci[1]
    )

    pattern_analysis = {
        "n_accepted_proposals": len(proposals_table),
        "pearson_delta_dev_vs_delta_gate": {
            "point": pearson_gate_dev[0] if pearson_gate_dev else None,
            "ci_95": list(pearson_gate_dev[1]) if pearson_gate_dev else None,
        },
        "pearson_delta_dev_vs_delta_step": {
            "point": pearson_step_dev[0] if pearson_step_dev else None,
            "ci_95": list(pearson_step_dev[1]) if pearson_step_dev else None,
        },
        "mean_delta_dev_minus_mean_delta_gate": mean_dev_minus_gate,
        "mean_delta_dev_minus_mean_delta_gate_ci_95": (
            list(paired_diff_dev_minus_gate_ci)
            if paired_diff_dev_minus_gate_ci else None
        ),
        "verdict": "clean_generalization" if verdict_clean else "divergent",
        "verdict_criterion": (
            "clean_generalization iff Pearson(Δ_dev, Δ_gate) > 0.9 AND "
            "CI on Mean(Δ_dev) − Mean(Δ_gate) overlaps zero"
        ),
    }

    # Cardinality curves on Δ_dev per (strategy, level) over accepted only.
    grouped: Dict[Tuple[str, int], List[Dict[str, Any]]] = defaultdict(list)
    for cid, agg in per_cell_aggregates.items():
        cell = agg["cell"]
        strat_label = (
            "worst_plus_best" if cell["strategy"] == "worst_only_at_k1"
            else cell["strategy"]
        )
        grouped[(strat_label, cell["level"])].append(agg)
    cardinality_curves: Dict[str, Any] = {}
    for (strat_label, level), aggs in sorted(grouped.items()):
        aggs_sorted = sorted(aggs, key=lambda a: a["cell"]["k"])
        cardinality_curves[f"{strat_label}@L{level}"] = {
            "strategy": strat_label,
            "level": level,
            "rows": [
                {
                    "cell_id": a["cell"]["cell_id"],
                    "k": a["cell"]["k"],
                    "n_accepted": a["n_accepted"],
                    "mean_delta_dev": a["mean_delta_dev"],
                    "mean_delta_gate": a["mean_delta_gate"],
                    "mean_delta_step": a["mean_delta_step"],
                }
                for a in aggs_sorted
            ],
        }

    # L2 stratified-by-k Δ_dev cross-strategy matched-pair.
    L2_BY_K = {
        1: {"a": "CH7-09", "b": "CH7-12",
            "strategy_a": "stratified_representative",
            "strategy_b": "worst_only_at_k1",
            "boundary_substitution_active": True},
        2: {"a": "CH7-10", "b": "CH7-13",
            "strategy_a": "stratified_representative",
            "strategy_b": "worst_plus_best",
            "boundary_substitution_active": False},
        4: {"a": "CH7-11", "b": "CH7-14",
            "strategy_a": "stratified_representative",
            "strategy_b": "worst_plus_best",
            "boundary_substitution_active": False},
    }
    l2_per_k: List[Dict[str, Any]] = []
    for k_val, cfg in L2_BY_K.items():
        recs_a = by_cell.get(cfg["a"], [])
        recs_b = by_cell.get(cfg["b"], [])
        if not recs_a or not recs_b:
            l2_per_k.append({
                "k": k_val,
                "cell_a_id": cfg["a"], "cell_b_id": cfg["b"],
                "strategy_a": cfg["strategy_a"],
                "strategy_b": cfg["strategy_b"],
                "boundary_substitution_active": cfg["boundary_substitution_active"],
                "n_accepted_a": len(recs_a), "n_accepted_b": len(recs_b),
                "status": "undefined_due_to_zero_acceptances",
            })
            continue
        # Bootstrap-resampled per-cell mean difference (unpaired, since
        # acceptance counts differ).
        rng = np.random.default_rng(BOOTSTRAP_SEED + 100 + k_val)
        a_devs = np.asarray([r["delta_dev"] for r in recs_a], dtype=float)
        b_devs = np.asarray([r["delta_dev"] for r in recs_b], dtype=float)
        diffs = np.empty(BOOTSTRAP_N, dtype=float)
        for i in range(BOOTSTRAP_N):
            ia = rng.integers(0, a_devs.size, size=a_devs.size)
            ib = rng.integers(0, b_devs.size, size=b_devs.size)
            diffs[i] = float(np.mean(a_devs[ia]) - np.mean(b_devs[ib]))
        ci_lo = float(np.percentile(diffs, 2.5))
        ci_hi = float(np.percentile(diffs, 97.5))
        mean_diff = float(np.mean(a_devs) - np.mean(b_devs))
        l2_per_k.append({
            "k": k_val,
            "cell_a_id": cfg["a"], "cell_b_id": cfg["b"],
            "strategy_a": cfg["strategy_a"],
            "strategy_b": cfg["strategy_b"],
            "boundary_substitution_active": cfg["boundary_substitution_active"],
            "n_accepted_a": len(recs_a), "n_accepted_b": len(recs_b),
            "mean_diff_delta_dev": mean_diff,
            "ci_95": [ci_lo, ci_hi],
            "ci_excludes_zero": (ci_lo > 0 or ci_hi < 0),
            "direction": (
                "positive" if ci_lo > 0 else "negative" if ci_hi < 0 else "null"
            ),
            "note": (
                "Per-cell unpaired bootstrap (acceptance counts differ "
                "between strategies). Underpowered at validation-acceptance "
                "n; report as descriptive."
            ),
        })

    artifact = {
        "schema_version": 1,
        "chapter": "chapter7",
        "design_doc_section": "§18.8 / §6.3 full-dev pass",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache_state": {
            "n_entries_before": n_entries_before,
            "n_entries_after": n_entries_after,
            "delta": n_entries_after - n_entries_before,
            "per_split_cache_fill_summary": {
                "train_step": {
                    "already_cached": n_already_ts,
                    "newly_filled": n_new_ts,
                },
                "train_gate": {
                    "already_cached": n_already_tg,
                    "newly_filled": n_new_tg,
                },
                "dev": {
                    "already_cached": n_already_dv,
                    "newly_filled": n_new_dv,
                },
            },
        },
        "h_eoh_means": h_eoh_means,
        "n_accepted_proposals": len(proposals_table),
        "n_already_had_delta_dev_before_this_pass": n_already_had_dev,
        "n_unique_proposal_hashes": len(hash_to_code),
        "proposals": proposals_table,
        "per_cell_aggregates": per_cell_aggregates,
        "pattern_analysis": pattern_analysis,
        "cardinality_curves_delta_dev_accepted_only": cardinality_curves,
        "l2_stratified_by_k_delta_dev": {
            "method": (
                "Cross-strategy mean-Δ_dev difference at L2, stratified by k. "
                "Per-cell unpaired bootstrap (acceptance counts differ "
                "between strategies). 5,000 resamples. Boundary substitution "
                "(worst_only_at_k1 for worst_plus_best at k=1) per §3.8."
            ),
            "per_k_results": l2_per_k,
        },
    }
    ARTIFACT_PATH.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"Wrote {ARTIFACT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
