"""thesis/code/chapter7/experiments/shown_vs_unshown.py

Chapter 7 train_select shown-vs-unshown decomposition (§6.8;
§18.5 analysis F). Mirrors the chapter-6 analysis at commit
17e2665 and decisions-log entry 2026-05-01.

Two phases in one run:

1. **Cache-fill** (parallel). For every unique sanitize-ok
   proposal hash, scores the proposal against every train_select
   instance via the canonical ScoreCache. Skips pairs that are
   already cached. Uses a multiprocessing pool to amortize the
   per-proposal compile cost.
2. **Decomposition**. For each per-proposal record, computes
   Δ_select_full (mean over all 30 train_select instances vs.
   h_eoh), Δ_select_shown (mean over the k counterexample
   instances the LLM saw), and Δ_select_unshown (mean over the
   30-k instances the LLM did not see). Aggregates per cell
   with 5,000-resample bootstrap 95% CIs.

Output: ``thesis/artifacts/chapter7_shown_vs_unshown.json`` —
overwrites the stub from the 2026-05-09 verification commit.

Usage::

    python -m thesis.code.chapter7.experiments.shown_vs_unshown
    python -m thesis.code.chapter7.experiments.shown_vs_unshown --workers 16
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
from typing import Any, Dict, List, Optional, Tuple

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

RESULTS_DIR = REPO_ROOT / "thesis" / "results" / "chapter7_primary_batch_gemini"
ARTIFACT_PATH = REPO_ROOT / "thesis" / "artifacts" / "chapter7_shown_vs_unshown.json"

CELL_IDS = [f"CH7-{i:02d}" for i in range(1, 15)]

BOOTSTRAP_N = 5000
BOOTSTRAP_SEED = 20_260_510


# --- record loading --------------------------------------------------


def _load_ok_records() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for cid in CELL_IDS:
        for path in sorted(RESULTS_DIR.glob(f"{cid}_set*.json")):
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if (d.get("sanitization") or {}).get("status") != "ok":
                continue
            out.append(d)
    return out


def _unique_proposals(records: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for r in records:
        h = r.get("proposal_hash")
        code = (r.get("sanitization") or {}).get("cleaned_code")
        if h and code and h not in out:
            out[h] = code
    return out


# --- cache-fill (parallel) -------------------------------------------


def _worker(
    args: Tuple[int, List[Tuple[str, str]], List[Tuple[str, dict]]]
) -> Dict[str, Dict[str, Any]]:
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
                print(
                    f"[worker {worker_id}] score-fail {h}|{qid}: {exc}",
                    flush=True,
                )
    return out


def _cache_fill(
    hash_to_code: Dict[str, str],
    qids_with_inst: List[Tuple[str, dict]],
    n_workers: int,
) -> None:
    cache = ScoreCache()
    n_total = len(hash_to_code) * len(qids_with_inst)
    uncached = []
    for h, code in hash_to_code.items():
        n_cached = sum(
            1 for qid, _ in qids_with_inst
            if f"{h}|{qid}" in cache._entries
        )
        if n_cached < len(qids_with_inst):
            uncached.append((h, code))
    print(
        f"  cache-fill: {n_total} total pairs; "
        f"{len(uncached)} proposals have at least one uncached pair",
        file=sys.stderr,
    )
    if not uncached:
        print("  cache already complete; nothing to fill", file=sys.stderr)
        return
    shards: List[List[Tuple[str, str]]] = [[] for _ in range(n_workers)]
    for i, item in enumerate(uncached):
        shards[i % n_workers].append(item)
    started = time.perf_counter()
    print(f"  launching {n_workers} workers...", file=sys.stderr)
    with mp.Pool(n_workers) as pool:
        worker_args = [(i, shard, qids_with_inst) for i, shard in enumerate(shards)]
        n_done = 0
        for shard_result in pool.imap_unordered(_worker, worker_args):
            for key, entry in shard_result.items():
                if key not in cache._entries:
                    cache._entries[key] = entry
            n_done += 1
            elapsed = time.perf_counter() - started
            print(
                f"  worker {n_done}/{n_workers} done; elapsed={elapsed/60:.1f}m",
                file=sys.stderr,
            )
    cache.save()
    print(f"  cache-fill complete in {(time.perf_counter() - started)/60:.1f} min",
          file=sys.stderr)


# --- per-record decomposition ---------------------------------------


def _shown_qids(rec: Dict[str, Any]) -> List[str]:
    items = (rec.get("counterexample_set") or {}).get("items", [])
    return [it["instance_id"] for it in items]


def _decompose_record(
    rec: Dict[str, Any],
    cache: ScoreCache,
    train_select_qids: List[str],
    h_eoh_bins_by_qid: Dict[str, int],
) -> Optional[Dict[str, Any]]:
    proposal_hash = rec.get("proposal_hash")
    if not proposal_hash:
        return None
    shown = set(_shown_qids(rec))
    proposal_bins: List[int] = []
    h_eoh_bins: List[int] = []
    is_shown: List[bool] = []
    for qid in train_select_qids:
        key = f"{proposal_hash}|{qid}"
        entry = cache._entries.get(key)
        if entry is None:
            return None
        proposal_bins.append(int(entry["bins_used"]))
        h_eoh_bins.append(int(h_eoh_bins_by_qid[qid]))
        is_shown.append(qid in shown)
    arr_p = np.asarray(proposal_bins, dtype=float)
    arr_h = np.asarray(h_eoh_bins, dtype=float)
    deltas = arr_h - arr_p  # higher = proposal beats h_eoh on the instance
    shown_mask = np.asarray(is_shown, dtype=bool)
    out = {
        "delta_select_full_mean": float(deltas.mean()),
        "n_shown": int(shown_mask.sum()),
        "n_unshown": int((~shown_mask).sum()),
    }
    if shown_mask.any():
        out["delta_select_shown_mean"] = float(deltas[shown_mask].mean())
    if (~shown_mask).any():
        out["delta_select_unshown_mean"] = float(deltas[~shown_mask].mean())
    return out


# --- bootstrap CI helpers -------------------------------------------


def _bootstrap_ci_mean(
    values: List[float], *, n: int = BOOTSTRAP_N, seed: int = BOOTSTRAP_SEED
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


# --- main -----------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workers", type=int, default=os.cpu_count() or 4,
    )
    parser.add_argument(
        "--skip-cache-fill", action="store_true",
        help="Skip phase 1 (cache fill); run decomposition only.",
    )
    args = parser.parse_args()

    print(f"Loading records from {RESULTS_DIR}", file=sys.stderr)
    records = _load_ok_records()
    hash_to_code = _unique_proposals(records)
    print(
        f"  {len(records)} sanitize-ok records; "
        f"{len(hash_to_code)} unique proposal hashes",
        file=sys.stderr,
    )

    train_select = load_split("train_select")
    train_select_qids = [
        qualified_instance_id("train_select", inst["instance_id"])
        for inst in train_select["instances"]
    ]
    qids_with_inst = list(zip(train_select_qids, train_select["instances"]))

    if not args.skip_cache_fill:
        _cache_fill(hash_to_code, qids_with_inst, args.workers)

    print("Computing h_eoh bins on train_select via cache...", file=sys.stderr)
    cache = ScoreCache()
    h_eoh = get_h_eoh()
    incumbent_module = _build_incumbent_module(h_eoh)
    h_eoh_bins_by_qid: Dict[str, int] = {}
    for qid, inst in qids_with_inst:
        b = cache.get_or_compute(
            h_eoh["code_hash"], qid, lambda i=inst: bins_used(incumbent_module, i)
        )
        h_eoh_bins_by_qid[qid] = int(b)
    cache.save()

    print("Decomposing per record...", file=sys.stderr)
    by_cell: Dict[str, Dict[str, List[float]]] = defaultdict(
        lambda: {"full": [], "shown": [], "unshown": []}
    )
    n_records_decomposed = 0
    n_records_skipped_missing = 0
    for r in records:
        cell_id = r.get("cell_id")
        d = _decompose_record(r, cache, train_select_qids, h_eoh_bins_by_qid)
        if d is None:
            n_records_skipped_missing += 1
            continue
        by_cell[cell_id]["full"].append(d["delta_select_full_mean"])
        if "delta_select_shown_mean" in d:
            by_cell[cell_id]["shown"].append(d["delta_select_shown_mean"])
        if "delta_select_unshown_mean" in d:
            by_cell[cell_id]["unshown"].append(d["delta_select_unshown_mean"])
        n_records_decomposed += 1

    print(
        f"  decomposed {n_records_decomposed} records; "
        f"{n_records_skipped_missing} skipped due to missing cache entries",
        file=sys.stderr,
    )

    per_cell_out: Dict[str, Any] = {}
    for cell_id in CELL_IDS:
        bucket = by_cell.get(cell_id, {"full": [], "shown": [], "unshown": []})
        per_cell_out[cell_id] = {
            "n_records": len(bucket["full"]),
            "delta_select_full": {
                "mean": float(np.mean(bucket["full"])) if bucket["full"] else None,
                "median": float(np.median(bucket["full"])) if bucket["full"] else None,
                "ci_95": _bootstrap_ci_mean(bucket["full"]),
            },
            "delta_select_shown": {
                "n": len(bucket["shown"]),
                "mean": float(np.mean(bucket["shown"])) if bucket["shown"] else None,
                "median": float(np.median(bucket["shown"])) if bucket["shown"] else None,
                "ci_95": _bootstrap_ci_mean(bucket["shown"]),
            },
            "delta_select_unshown": {
                "n": len(bucket["unshown"]),
                "mean": float(np.mean(bucket["unshown"])) if bucket["unshown"] else None,
                "median": float(np.median(bucket["unshown"])) if bucket["unshown"] else None,
                "ci_95": _bootstrap_ci_mean(bucket["unshown"]),
            },
        }

    # Cross-strategy interaction CIs at the L2 anchor (CH7-11 strat L2 k=4
    # and CH7-14 wpb L2 k=4) — same statistic ch6 reported for shown/unshown.
    def _interaction_ci(metric_key: str) -> Optional[Tuple[float, float]]:
        cells = {
            ("strat", 1): "CH7-03",
            ("strat", 2): "CH7-11",
            ("wpb",   1): "CH7-07",
            ("wpb",   2): "CH7-14",
        }
        arrays = {}
        for k, cid in cells.items():
            vals = by_cell.get(cid, {}).get(metric_key, [])
            if not vals:
                return None
            arrays[k] = np.asarray(vals, dtype=float)
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        stats = np.empty(BOOTSTRAP_N, dtype=float)
        for i in range(BOOTSTRAP_N):
            means = {}
            for k, arr in arrays.items():
                idx = rng.integers(0, arr.size, size=arr.size)
                means[k] = float(np.mean(arr[idx]))
            stats[i] = (
                (means[("strat", 2)] - means[("strat", 1)])
                - (means[("wpb", 2)] - means[("wpb", 1)])
            )
        return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))

    interaction = {
        "ci_delta_select_full": _interaction_ci("full"),
        "ci_delta_select_shown": _interaction_ci("shown"),
        "ci_delta_select_unshown": _interaction_ci("unshown"),
        "note": (
            "Same cross-strategy L2-vs-L1 interaction statistic ch6 reports "
            "for the shown-vs-unshown decomposition. Excluding-zero CI in "
            "the same direction for shown and unshown indicates the "
            "interaction is uniform across the train_select pool, not "
            "concentrated on the prompt-shown subset."
        ),
    }

    artifact = {
        "schema_version": 2,
        "_status": "complete",
        "chapter": "chapter7",
        "design_doc_section": "§6.8 / §18.5 analysis F",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_records_decomposed": n_records_decomposed,
        "n_records_skipped_missing_cache": n_records_skipped_missing,
        "n_unique_proposal_hashes": len(hash_to_code),
        "train_select_size": len(train_select_qids),
        "bootstrap_n_resamples": BOOTSTRAP_N,
        "per_cell": per_cell_out,
        "anchor_interaction": interaction,
    }
    ARTIFACT_PATH.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"Wrote {ARTIFACT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
