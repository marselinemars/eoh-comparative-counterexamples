"""
thesis/code/chapter6/experiments/shown_vs_unshown_cache_fill_parallel.py

Multiprocessing variant of shown_vs_unshown_cache_fill.py. Distributes
the 198-proposal x 30-train_select-instance scoring grid across N
worker processes (default = `os.cpu_count()`). Each worker compiles
each of its assigned proposals once and scores them against all 30
train_select instances, returning a per-key {bins_used} dict. The
parent merges all worker results into the ScoreCache and saves once.

Distribution unit: whole proposals (a worker gets some number of
proposal hashes plus all 30 instances per hash). This avoids the
fixed cost of compiling each proposal more than once.

Order-of-magnitude estimate at 25 sec/pair single-thread:
  5850 pairs / 32 workers / (25 sec/pair) ≈ ~76 min wall-clock,
optimistic if pair time variance is high (catastrophic proposals
take longer).

Run:
    python -m thesis.code.chapter6.experiments.shown_vs_unshown_cache_fill_parallel

Or with explicit worker count:
    python -m thesis.code.chapter6.experiments.shown_vs_unshown_cache_fill_parallel --workers 16
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import time
import types
from pathlib import Path
from typing import Any, Dict, List, Tuple

from thesis.code.evaluation import bins_used
from thesis.code.score_cache import ScoreCache
from thesis.code.splits import load_split

REPO = Path(__file__).resolve().parents[4]
RES = REPO / "thesis" / "results" / "chapter6_primary_batch_gemini"


def _collect_unique_proposals() -> Dict[str, str]:
    """Returns {proposal_hash: cleaned_code} over all sanitize-ok
    primary-batch records."""
    out: Dict[str, str] = {}
    for p in sorted(RES.glob("stratified_representative@L*_set*_seed*.json")) + \
             sorted(RES.glob("worst_plus_best@L*_set*_seed*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if (d.get("sanitization") or {}).get("status") != "ok":
            continue
        h = d.get("proposal_hash")
        code = (d.get("sanitization") or {}).get("cleaned_code")
        if h and code and h not in out:
            out[h] = code
    return out


def _worker(args: Tuple[int, List[Tuple[str, str]], List[Tuple[str, dict]]]) -> Dict[str, Dict[str, Any]]:
    """Score one worker's slice of (hash, code) pairs against every
    train_select instance.

    Args:
        args: (worker_id, list of (hash, code), list of (qid, instance dict))
    Returns:
        dict of {f"{hash}|{qid}": {bins_used, code_hash, instance_id}}
    """
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
                bins = int(bins_used(mod, inst))
                out[f"{h}|{qid}"] = {
                    "bins_used": bins,
                    "code_hash": h,
                    "instance_id": qid,
                }
            except Exception as exc:
                print(f"[worker {worker_id}] score-fail {h}|{qid}: {exc}", flush=True)
    return out


def _shard_proposals(
    items: List[Tuple[str, str]], n_workers: int
) -> List[List[Tuple[str, str]]]:
    """Round-robin shard proposals across workers so the heavy
    catastrophic ones spread out rather than clumping in one worker."""
    shards: List[List[Tuple[str, str]]] = [[] for _ in range(n_workers)]
    for i, item in enumerate(items):
        shards[i % n_workers].append(item)
    return shards


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workers", type=int, default=os.cpu_count() or 4,
        help="number of worker processes (default = cpu_count)",
    )
    args = parser.parse_args()
    n_workers = max(1, args.workers)

    print("Loading proposals + train_select split + cache...")
    hash_to_code = _collect_unique_proposals()
    split = load_split("train_select")
    qids_with_inst = [
        (f"thesis_train_select:{inst['instance_id']}", inst)
        for inst in split["instances"]
    ]
    cache = ScoreCache()
    n_total_pairs = len(hash_to_code) * len(qids_with_inst)
    n_existing = sum(
        1
        for h in hash_to_code
        for qid, _ in qids_with_inst
        if f"{h}|{qid}" in cache._entries
    )
    print(
        f"  {len(hash_to_code)} unique proposals × "
        f"{len(qids_with_inst)} train_select instances = "
        f"{n_total_pairs:,} total pairs"
    )
    print(f"  {n_existing} already cached; {n_total_pairs - n_existing} need scoring")
    print(f"  workers: {n_workers}")

    # Filter to uncached proposals only — entire proposals where ALL
    # 30 pairs are cached can be skipped at the worker-shard level.
    uncached_proposals = []
    for h, code in hash_to_code.items():
        n_cached_for_h = sum(
            1 for qid, _ in qids_with_inst if f"{h}|{qid}" in cache._entries
        )
        if n_cached_for_h < len(qids_with_inst):
            uncached_proposals.append((h, code))
    print(f"  {len(uncached_proposals)} proposals have at least one uncached pair")

    if not uncached_proposals:
        print("Nothing to do; cache fully populated for the analysis grid.")
        return 0

    shards = _shard_proposals(uncached_proposals, n_workers)
    print(f"  shard sizes: {[len(s) for s in shards]}")

    started = time.perf_counter()
    print(f"\nLaunching {n_workers} workers at {time.strftime('%H:%M:%S')}...")
    with mp.Pool(n_workers) as pool:
        worker_args = [
            (i, shard, qids_with_inst) for i, shard in enumerate(shards)
        ]
        results = []
        n_completed_workers = 0
        for shard_result in pool.imap_unordered(_worker, worker_args):
            results.append(shard_result)
            n_completed_workers += 1
            elapsed = time.perf_counter() - started
            print(
                f"  [{time.strftime('%H:%M:%S')}] worker complete: "
                f"{n_completed_workers}/{n_workers} done, "
                f"{len(shard_result)} new pairs scored, "
                f"elapsed={elapsed/60:.1f}m"
            )

    print("\nMerging worker results into cache...")
    n_added = 0
    for shard_result in results:
        for key, entry in shard_result.items():
            if key not in cache._entries:
                cache._entries[key] = entry
                n_added += 1

    print("Saving cache to disk...")
    cache.save()
    elapsed = time.perf_counter() - started

    # Verify
    n_after = sum(
        1
        for h in hash_to_code
        for qid, _ in qids_with_inst
        if f"{h}|{qid}" in cache._entries
    )
    print()
    print("=== cache-fill summary ===")
    print(f"  pairs newly added:  {n_added}")
    print(f"  pairs in cache for analysis grid (before/after): "
          f"{n_existing} -> {n_after}")
    print(f"  expected after:     {n_total_pairs}")
    if n_after != n_total_pairs:
        print(
            f"  WARNING: expected {n_total_pairs}, got {n_after} "
            f"(missing {n_total_pairs - n_after})"
        )
    print(f"  wall-clock:         {elapsed:.1f}s = {elapsed/60:.1f} min")
    print(f"  workers:            {n_workers}")
    print(f"  effective rate:     {n_added/elapsed:.1f} pairs/sec")
    return 0 if n_after == n_total_pairs else 1


if __name__ == "__main__":
    raise SystemExit(main())
