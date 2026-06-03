"""
thesis/code/chapter6/experiments/shown_vs_unshown_cache_fill.py

Cache-fill pre-step for the train_select shown-vs-unshown
decomposition analysis (Option A from the Prompt 39 reframing).

For each unique sanitize-ok proposal hash from the chapter-6
primary batch, scores the proposal against every train_select
instance via the canonical ScoreCache.get_or_compute path so
that subsequent (and any future) per-instance analyses benefit
from a fully-populated cache.

Logs progress every 500 scorings. No LLM calls.

Run:
    python -m thesis.code.chapter6.experiments.shown_vs_unshown_cache_fill
"""
from __future__ import annotations

import json
import time
import types
from pathlib import Path

from thesis.code.evaluation import bins_used
from thesis.code.score_cache import ScoreCache
from thesis.code.splits import load_split

REPO = Path(__file__).resolve().parents[4]
RES = REPO / "thesis" / "results" / "chapter6_primary_batch_gemini"
LOG_EVERY = 500


def _collect_unique_proposals() -> dict[str, str]:
    """Returns {proposal_hash: cleaned_code} over the 240
    sanitize-ok primary-batch records."""
    out: dict[str, str] = {}
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


def main() -> int:
    print("Loading proposals + train_select split + cache...")
    hash_to_code = _collect_unique_proposals()
    split = load_split("train_select")
    qids_with_inst = [
        (f"thesis_train_select:{inst['instance_id']}", inst)
        for inst in split["instances"]
    ]
    cache = ScoreCache()
    print(f"  {len(hash_to_code)} unique proposals × {len(qids_with_inst)} train_select instances")
    print(f"  total pairs to ensure: {len(hash_to_code) * len(qids_with_inst):,}")

    started = time.perf_counter()
    n_done = 0
    n_hits = 0
    n_misses = 0
    n_failures = 0
    failures: list[tuple[str, str, str]] = []

    for h, code in hash_to_code.items():
        mod = types.ModuleType(f"h_{h}")
        try:
            exec(compile(code, f"<{h}>", "exec"), mod.__dict__)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  [compile-fail] {h}: {exc}")
            for qid, _ in qids_with_inst:
                failures.append((h, qid, f"compile: {exc}"))
                n_failures += 1
            continue

        for qid, inst in qids_with_inst:
            existing = cache._entries.get(f"{h}|{qid}")
            try:
                cache.get_or_compute(h, qid, lambda i=inst: bins_used(mod, i))
                if existing is not None:
                    n_hits += 1
                else:
                    n_misses += 1
            except Exception as exc:
                failures.append((h, qid, f"score: {exc}"))
                n_failures += 1
            n_done += 1
            if n_done % LOG_EVERY == 0:
                elapsed = time.perf_counter() - started
                rate = n_done / elapsed
                remaining = (len(hash_to_code) * len(qids_with_inst)) - n_done
                eta_s = remaining / rate if rate > 0 else 0
                print(
                    f"  [{n_done:>5}/{len(hash_to_code)*len(qids_with_inst)}] "
                    f"hits={n_hits} misses={n_misses} fails={n_failures} "
                    f"elapsed={elapsed/60:.1f}m rate={rate:.1f}/s eta={eta_s/60:.1f}m"
                )

    print()
    print("Saving cache to disk...")
    cache.save()
    elapsed = time.perf_counter() - started
    print()
    print("=== cache-fill summary ===")
    print(f"  total pairs:    {n_done}")
    print(f"  cache hits:     {n_hits}")
    print(f"  cache misses (newly scored): {n_misses}")
    print(f"  failures:       {n_failures}")
    print(f"  wall-clock:     {elapsed:.1f}s = {elapsed/60:.1f} min")

    if failures:
        print()
        print("Failures (first 20):")
        for h, qid, why in failures[:20]:
            print(f"  {h} | {qid}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
