"""
thesis/code/chapter3_baselines/run_baselines.py

Driver for W-E4: run First Fit, Best Fit, Worst Fit, and First Fit
Decreasing on every instance in every split, and report each per
(baseline, split) cell alongside h_eoh.

h_eoh's per-instance bins_used are computed by loading
thesis/artifacts/h_eoh.py and running it through the same harness
that chapter-5 / 6 / 7 used (thesis.code.evaluation.bins_used),
with results memoized via the persistent score cache
(thesis/artifacts/score_cache.json) so re-runs are instant.

Output: thesis/artifacts/chapter3_incumbent_baselines.json.

Run:
    python -m thesis.code.chapter3_baselines.run_baselines
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

import numpy as np

from thesis.code.chapter3_baselines.baselines import (
    best_fit,
    first_fit,
    first_fit_decreasing,
    worst_fit,
)
from thesis.code.evaluation import bins_used, load_heuristic_from_code
from thesis.code.incumbents import get_h_eoh
from thesis.code.score_cache import ScoreCache
from thesis.code.splits import load_split, qualified_instance_id

REPO = Path(__file__).resolve().parents[3]
OUT_PATH = REPO / "thesis" / "artifacts" / "chapter3_incumbent_baselines.json"

SPLITS = ("train_select", "train_step", "train_gate", "dev", "test_ood")

BASELINES: Dict[str, Callable[[List[float], float], int]] = {
    "first_fit": first_fit,
    "best_fit": best_fit,
    "worst_fit": worst_fit,
    "first_fit_decreasing": first_fit_decreasing,
}


def _git_head() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True
        ).strip()
        return out
    except Exception:
        return "unknown"


def _stats(values: List[int]) -> Dict[str, Any]:
    arr = np.asarray(values)
    return {
        "n": int(arr.size),
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
        "median": float(np.median(arr)),
        "min": int(arr.min()),
        "max": int(arr.max()),
    }


def _run_h_eoh_on_split(
    split_name: str,
    h_eoh_module,
    h_eoh_hash: str,
    cache: ScoreCache,
) -> List[int]:
    split = load_split(split_name)
    out: List[int] = []
    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        b = cache.get_or_compute(
            h_eoh_hash,
            qid,
            lambda i=inst: bins_used(h_eoh_module, i),
        )
        out.append(b)
    return out


def _run_baseline_on_split(
    split_name: str, fn: Callable[[List[float], float], int]
) -> List[int]:
    split = load_split(split_name)
    out: List[int] = []
    for inst in split["instances"]:
        out.append(int(fn(inst["items"], inst["capacity"])))
    return out


def _win_loss_tie(
    baseline_per_inst: List[int], h_eoh_per_inst: List[int]
) -> Dict[str, int]:
    wins = sum(1 for b, h in zip(baseline_per_inst, h_eoh_per_inst) if b < h)
    losses = sum(1 for b, h in zip(baseline_per_inst, h_eoh_per_inst) if b > h)
    ties = sum(1 for b, h in zip(baseline_per_inst, h_eoh_per_inst) if b == h)
    return {"wins": wins, "losses": losses, "ties": ties}


def main() -> None:
    started = time.time()
    h_eoh = get_h_eoh()
    h_eoh_code = h_eoh["code"]
    h_eoh_hash = h_eoh["code_hash"]
    h_eoh_module = load_heuristic_from_code(h_eoh_code, "h_eoh")
    cache = ScoreCache()

    print(f"h_eoh code_hash = {h_eoh_hash}")
    print(f"score_cache has {len(cache)} entries before run")

    splits_block: Dict[str, Any] = {}
    all_h_eoh: List[int] = []
    all_baseline: Dict[str, List[int]] = {name: [] for name in BASELINES}

    for split_name in SPLITS:
        print(f"[{split_name}] computing h_eoh ...", flush=True)
        t0 = time.time()
        h_per_inst = _run_h_eoh_on_split(
            split_name, h_eoh_module, h_eoh_hash, cache
        )
        print(f"  h_eoh: n={len(h_per_inst)} ({time.time()-t0:.1f}s)")
        cache.save()

        per_baseline: Dict[str, Any] = {}
        per_baseline["h_eoh"] = {**_stats(h_per_inst), "per_instance": h_per_inst}
        all_h_eoh.extend(h_per_inst)

        for name, fn in BASELINES.items():
            t0 = time.time()
            b_per_inst = _run_baseline_on_split(split_name, fn)
            stats = _stats(b_per_inst)
            wlt = _win_loss_tie(b_per_inst, h_per_inst)
            delta = stats["mean"] - _stats(h_per_inst)["mean"]
            per_baseline[name] = {
                **stats,
                "delta_vs_h_eoh_mean": delta,
                "wins": wlt["wins"],
                "losses": wlt["losses"],
                "ties": wlt["ties"],
                "per_instance": b_per_inst,
            }
            all_baseline[name].extend(b_per_inst)
            print(
                f"  {name:<25} mean={stats['mean']:.2f}  "
                f"delta_vs_h_eoh={delta:+.2f}  "
                f"W/L/T={wlt['wins']}/{wlt['losses']}/{wlt['ties']}  "
                f"({time.time()-t0:.1f}s)"
            )

        splits_block[split_name] = {
            "n_instances": len(h_per_inst),
            **per_baseline,
        }

    h_eoh_mean_all = float(np.mean(all_h_eoh))
    summary = {
        f"h_eoh_vs_{name}_mean_delta_across_all_150_instances": float(
            np.mean(all_baseline[name]) - h_eoh_mean_all
        )
        for name in BASELINES
    }
    summary["h_eoh_mean_across_all_150_instances"] = h_eoh_mean_all
    for name in BASELINES:
        summary[f"{name}_mean_across_all_150_instances"] = float(
            np.mean(all_baseline[name])
        )
    summary["total_wins_losses_ties_per_baseline"] = {
        name: {
            "wins": sum(
                splits_block[s][name]["wins"] for s in SPLITS
            ),
            "losses": sum(
                splits_block[s][name]["losses"] for s in SPLITS
            ),
            "ties": sum(
                splits_block[s][name]["ties"] for s in SPLITS
            ),
        }
        for name in BASELINES
    }

    artifact = {
        "metadata": {
            "design_doc": (
                "thesis/writing/chapter3_incumbent_baselines_design.md"
            ),
            "h_eoh_code_hash": h_eoh_hash,
            "h_eoh_bins_source": (
                "computed from the canonical EoH-final-population "
                "code string (via thesis.code.incumbents.get_h_eoh) "
                "through thesis.code.evaluation.bins_used; memoized "
                "in thesis/artifacts/score_cache.json. The hash is "
                "sha256 of the bare function source, matching the "
                "value used in chapter 5 / 6 / 7."
            ),
            "ffd_is_offline": True,
            "tie_breaking": "bin_creation_order_earliest_first",
            "bin_capacity": "per-instance (100 for in-distribution, 100 for OOD)",
            "splits_evaluated": list(SPLITS),
            "n_instances_total": sum(
                splits_block[s]["n_instances"] for s in SPLITS
            ),
            "commit_hash": _git_head(),
            "runtime_seconds": round(time.time() - started, 1),
        },
        "splits": splits_block,
        "summary": summary,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH.relative_to(REPO).as_posix()}")
    print(f"Total runtime: {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
