"""
evaluate_all_splits.py

Re-evaluates every meaningfully accepted heuristic from prior experiments
across all three splits: search_train, dev, test_ood.

Produces a table showing whether search_train improvements held on dev.
Saves results to one_off_results/split_evaluation_table.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REFINEMENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REFINEMENT_DIR))

from load_instances import load_split_instances
from evaluate_heuristic_cases import (
    evaluate_heuristic_on_instances,
    load_heuristic_module_from_code,
    summarize_case_results,
)

RESULTS_DIR = REFINEMENT_DIR / "one_off_results"

# ── hardcoded: current best incumbent ─────────────────────────────────────────
INCUMBENT_CODE = """\
import numpy as np

def score(item, bins):
    remainder = bins - item
    utilization_score = item / bins
    small_remainder_incentive = 1.0 / (1.0 + remainder / item)
    steepness_multiple = 20.0
    multiplicity_bonus = np.exp(
        -steepness_multiple * (np.round(remainder / item) - remainder / item) ** 2
    )
    fragment_penalty_term = np.where(
        (remainder > 0) & (remainder < item),
        (1.0 - (remainder / item)) ** 4, 0.0,
    )
    fragment_penalty_magnitude = 3.1
    combined_score_for_non_perfect_fits = (
        utilization_score
        + 0.5 * small_remainder_incentive
        + 1.15 * multiplicity_bonus
        - fragment_penalty_magnitude * fragment_penalty_term
    )
    scores = np.where(remainder == 0, np.inf, combined_score_for_non_perfect_fits)
    return scores
"""


def _load(path: str) -> dict:
    with (RESULTS_DIR / path).open(encoding="utf-8") as fh:
        return json.load(fh)


def _collect_heuristics() -> list[dict]:
    """Return list of {label, reported_train_fitness, code} for every accepted result."""
    entries = []

    # 1. Current best incumbent (fragment 3.1, mult 1.15)
    entries.append({
        "label": "current_best",
        "description": "Current best: fragment=3.10, mult_weight=1.15",
        "reported_train_fitness": 0.0068417346,
        "code": INCUMBENT_CODE,
    })

    # 2. Forced-novelty mutation result (fragment 3.15, mult 1.1)
    d = _load("2026-04-18_trace_guided_mutation_true_best_vs_donor_hybrid_forced_novelty_raw.json")
    entries.append({
        "label": "forced_novelty_new_best",
        "description": "Forced novelty: fragment=3.15, mult_weight=1.1",
        "reported_train_fitness": 0.0069423483,
        "code": d["parsed"]["proposed_code"],
    })

    # 3. Manual loop ep3: multiplicity 0.8→1.0
    d = _load("2026-04-18_manual_light_loop_prev_incumbent_episode3_raw.json")
    entries.append({
        "label": "manual_loop_ep3_mult_1.0",
        "description": "Manual loop ep3: mult_weight 0.8→1.0",
        "reported_train_fitness": 0.0072430626,
        "code": d["final_candidate"]["proposed_code"],  # final_candidate is a dict with proposed_code
    })

    # 4. Incumbent vs moderate branch (fragment 3.25)
    d = _load("2026-04-18_trace_guided_mutation_incumbent_vs_moderate_branch_raw.json")
    entries.append({
        "label": "incumbent_vs_moderate_branch",
        "description": "Incumbent vs moderate branch: fragment=3.25",
        "reported_train_fitness": 0.0074454170,
        "code": d["parsed"]["proposed_code"],
    })

    # 5. Near-pair interpolation only (worst+best) — same code as current best
    d = _load("2026-04-18_mutation_interpolation_only_ablation_raw.json")
    for result in d["results"]:
        if result.get("pair_name") == "near_pair_interpolation_only":
            entries.append({
                "label": "interpolation_only_near_pair",
                "description": "Interpolation-only near pair (confirms current best)",
                "reported_train_fitness": 0.0068417346,
                "code": result["parsed"]["proposed_code"],
            })
            break

    # 6. Gen3_idx2 child (rank2 donor validation)
    d = _load("2026-04-19_donor_pool_rank2_vs_rank3_live_validation_raw.json")
    entries.append({
        "label": "gen3_idx2_child",
        "description": "gen3_idx2 donor child (rank2)",
        "reported_train_fitness": 0.0077389812,
        "code": d["results"][0]["parsed"]["proposed_code"],
    })

    # 7. Gen3_idx3 child (rank3 donor validation — stronger child despite lower rank)
    entries.append({
        "label": "gen3_idx3_child",
        "description": "gen3_idx3 donor child (rank3, stronger child)",
        "reported_train_fitness": 0.0070454515,
        "code": d["results"][1]["parsed"]["proposed_code"],
    })

    # 8. Far donor worst+best ablation (strongest far-donor child)
    d = _load("2026-04-19_mutation_case_context_ablation_far_donor_raw.json")
    # results: [worst_only, worst_best, worst_median_best] — pick worst_best (index 1)
    for r in d["results"]:
        if r["variant_name"] == "worst_best":
            entries.append({
                "label": "far_donor_worst_best",
                "description": "Far donor worst+best ablation",
                "reported_train_fitness": 0.0078478720,
                "code": r["parsed"]["proposed_code"],
            })
            break

    # 9. Two-step donor rehabilitation round 2
    d = _load("2026-04-19_two_step_donor_rehabilitation_round2_raw.json")
    entries.append({
        "label": "donor_rehab_round2",
        "description": "Two-step donor rehabilitation round 2",
        "reported_train_fitness": 0.0080490995,
        "code": d["parsed"]["proposed_code"],
    })

    # 10. Adaptive vs fixed policy — near pair fixed (worst+median+best)
    d = _load("2026-04-19_adaptive_vs_fixed_mutation_policy_live_validation_raw.json")
    for result in d["results"]:
        if result.get("pair_name") == "near_pair_live_policy" and result.get("policy_variant") == "fixed_worst_median_best":
            entries.append({
                "label": "near_pair_fixed_policy",
                "description": "Near pair fixed policy (worst+median+best)",
                "reported_train_fitness": 0.0068417346,
                "code": result["parsed"]["proposed_code"],
            })
            break

    return entries


def evaluate_heuristic(code: str, instances_by_split: dict) -> dict:
    try:
        mod = load_heuristic_module_from_code(code)
    except Exception as exc:
        return {split: {"error": str(exc)} for split in instances_by_split}

    out = {}
    for split, instances in instances_by_split.items():
        try:
            cases = evaluate_heuristic_on_instances(instances, heuristic_module=mod)
            summary = summarize_case_results(cases)
            out[split] = summary["mean_objective_gap"]
        except Exception as exc:
            out[split] = {"error": str(exc)}
    return out


def main() -> None:
    print("Loading splits...")
    splits = {
        "search_train": load_split_instances("search_train"),
        "dev":          load_split_instances("dev"),
        "test_ood":     load_split_instances("test_ood"),
    }
    n = {s: len(v) for s, v in splits.items()}
    print(f"  search_train={n['search_train']}  dev={n['dev']}  test_ood={n['test_ood']}")

    print("\nCollecting heuristics from raw JSON results...")
    heuristics = _collect_heuristics()
    print(f"  {len(heuristics)} heuristics collected")

    print("\nEvaluating across splits...")
    rows = []
    for h in heuristics:
        print(f"  evaluating: {h['label']}...")
        fitnesses = evaluate_heuristic(h["code"], splits)
        rows.append({
            "label": h["label"],
            "description": h["description"],
            "reported_train_fitness": h["reported_train_fitness"],
            **{f"fitness_{s}": fitnesses.get(s) for s in splits},
        })

    # Sort by search_train fitness
    rows.sort(key=lambda r: r.get("fitness_search_train") or 999)

    # ── print table ──────────────────────────────────────────────────────────
    print("\n")
    print("=" * 100)
    print("CROSS-SPLIT EVALUATION TABLE")
    print(f"{'label':<35} {'train':>10} {'dev':>10} {'test_ood':>10} {'dev-train':>12} {'verdict':>20}")
    print("-" * 100)

    incumbent_train = None
    incumbent_dev = None

    for r in rows:
        tr  = r.get("fitness_search_train")
        dev = r.get("fitness_dev")
        ood = r.get("fitness_test_ood")

        if r["label"] == "current_best":
            incumbent_train = tr
            incumbent_dev   = dev

        delta_dev = (dev - tr) if isinstance(dev, float) and isinstance(tr, float) else None

        # verdict: did the train improvement hold on dev?
        if r["label"] == "current_best":
            verdict = "INCUMBENT (reference)"
        elif isinstance(tr, float) and isinstance(dev, float) and incumbent_train and incumbent_dev:
            beats_train    = tr < incumbent_train
            beats_dev      = dev < incumbent_dev
            if beats_train and beats_dev:
                verdict = "HOLDS (train+dev)"
            elif beats_train and not beats_dev:
                verdict = "train-only overfit"
            elif not beats_train:
                verdict = "below incumbent"
            else:
                verdict = "?"
        else:
            verdict = "error"

        tr_s  = f"{tr:.8f}"  if isinstance(tr,  float) else "ERROR"
        dev_s = f"{dev:.8f}" if isinstance(dev, float) else "ERROR"
        ood_s = f"{ood:.8f}" if isinstance(ood, float) else "ERROR"
        delta_s = f"{delta_dev:+.6f}" if delta_dev is not None else "n/a"

        print(f"{r['label']:<35} {tr_s:>10} {dev_s:>10} {ood_s:>10} {delta_s:>12}   {verdict}")

    print("=" * 100)
    print(f"\nNote: incumbent search_train={incumbent_train:.8f}  dev={incumbent_dev:.8f}")
    print(f"The dev-train column shows how much worse performance gets on unseen instances.")
    print(f"Any heuristic with dev > incumbent_dev is train-only overfit.")

    # Save
    output = {
        "split_sizes": n,
        "splits_description": {
            "search_train": "5 bundled instances — used for mutation context during all experiments",
            "dev": "5 fresh instances (seed=20260001) — never shown to LLM",
            "test_ood": "5 held-out instances (seed=20260002) — locked until final reporting",
        },
        "rows": rows,
        "incumbent_train": incumbent_train,
        "incumbent_dev": incumbent_dev,
    }
    out_path = RESULTS_DIR / "2026-04-19_cross_split_evaluation_table.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
