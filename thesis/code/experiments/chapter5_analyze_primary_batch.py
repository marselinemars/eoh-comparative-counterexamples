"""
thesis/code/experiments/chapter5_analyze_primary_batch.py

Run the Chapter-5 post-batch analysis against the completed primary
batch and write the committed `chapter5_summary.json` artifact.

Usage:
    python thesis/code/experiments/chapter5_analyze_primary_batch.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from thesis.code.chapter5.analysis import (
    build_combined_summary,
    build_summary,
    compute_h_eoh_per_instance_bins,
    load_primary_batch_proposals,
    load_validation_trajectories,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = (
    REPO_ROOT / "thesis" / "results" / "chapter5_primary_batch_gemini"
)
VALIDATION_DIR = (
    REPO_ROOT / "thesis" / "results" / "chapter5_validation_batch_gemini"
)
SUMMARY_OUT = (
    REPO_ROOT / "thesis" / "artifacts" / "chapter5_summary.json"
)


def _fmt_stats_row(name: str, s: Dict[str, Any]) -> str:
    return (
        f"{name:<28} {s['n']:>4} "
        f"{s['mean']:>+8.2f} {s['median']:>+8.2f} "
        f"{s['p25']:>+8.2f} {s['p75']:>+8.2f} "
        f"{s['iqr']:>7.2f} {s['trimmed_mean_10pct']:>+8.2f} "
        f"{s['positive_tail_mass']:>6.2f} "
        f"{s['catastrophic_tail_mass']:>6.2f}"
    )


def _print_summary(summary: Dict[str, Any]) -> None:
    print("=" * 110)
    print(
        f"Chapter 5 primary batch summary — "
        f"{summary['n_proposals']} proposals across "
        f"{summary['n_strategies']} strategies"
    )
    print("=" * 110)

    print()
    print("-- Per-strategy Δ_step --")
    print(
        f"{'strategy':<28} {'n':>4} "
        f"{'mean':>8} {'median':>8} "
        f"{'p25':>8} {'p75':>8} "
        f"{'IQR':>7} {'trim_mean':>8} "
        f"{'pos%':>6} {'cat%':>6}"
    )
    for s in summary["strategies"]:
        ps = summary["per_strategy"][s]
        print(_fmt_stats_row(s, ps["delta_step"]))

    print()
    print("-- Per-strategy Δ_gate --")
    for s in summary["strategies"]:
        ps = summary["per_strategy"][s]
        print(_fmt_stats_row(s, ps["delta_gate"]))

    print()
    print("-- Per-strategy win_rate_step --")
    print(f"{'strategy':<28} {'mean':>8} {'median':>8}")
    for s in summary["strategies"]:
        ps = summary["per_strategy"][s]
        print(
            f"{s:<28} {ps['win_rate_step_mean']:>8.3f} "
            f"{ps['win_rate_step_median']:>8.3f}"
        )

    print()
    print("-- Failure rate --")
    any_failures = False
    for s in summary["strategies"]:
        ps = summary["per_strategy"][s]
        fails = ps["n_failed_by_label"]
        if fails:
            any_failures = True
            print(f"{s}: {fails}")
    if not any_failures:
        print("0 failures across all strategies "
              "(60/60 sanitize-ok per strategy).")

    print()
    print("-- Pairwise Cliff's delta on Δ_step --")
    print("(positive = row dominates column; |δ|>=0.3 is a notable effect)")
    for key, val in sorted(
        summary["pairwise_cliffs_delta"]["delta_step"].items()
    ):
        a, b = key.split("__vs__")
        tag = " (notable)" if abs(val) >= 0.3 else ""
        print(f"  {a:<28} vs {b:<28} {val:>+6.3f}{tag}")

    print()
    print("-- Pairwise IQR overlap on Δ_step --")
    print("(1.0 = identical IQR band; 0.0 = disjoint)")
    for key, val in sorted(
        summary["pairwise_iqr_overlap"]["delta_step"].items()
    ):
        a, b = key.split("__vs__")
        print(f"  {a:<28} vs {b:<28} {val:>6.3f}")

    # Argmax-equivalence block (only present if CLI passed
    # h_eoh_per_instance_by_split).
    if any(
        "argmax_equivalent_count" in summary["per_strategy"][s]
        for s in summary["strategies"]
    ):
        print()
        print("-- Per-strategy argmax-equivalence on train_step --")
        print(
            f"{'strategy':<28} {'eq_count':>8} {'eq_rate':>8} "
            f"{'distinct':>8} {'eq_on_gate':>10} {'eq_on_both':>10}"
        )
        for s in summary["strategies"]:
            ps = summary["per_strategy"][s]
            print(
                f"{s:<28} {ps['argmax_equivalent_count']:>8d} "
                f"{ps['argmax_equivalent_rate']:>8.3f} "
                f"{ps['argmax_distinct_count']:>8d} "
                f"{ps['argmax_equivalent_on_train_gate_count']:>10d} "
                f"{ps['argmax_equivalent_on_both_count']:>10d}"
            )
        print()
        print("-- Per-strategy Δ_step (argmax-distinct subset only) --")
        print(
            f"{'strategy':<28} {'n':>4} "
            f"{'mean':>8} {'median':>8} "
            f"{'p25':>8} {'p75':>8} "
            f"{'IQR':>7} {'trim_mean':>8} "
            f"{'pos%':>6} {'cat%':>6}"
        )
        for s in summary["strategies"]:
            ps = summary["per_strategy"][s]
            print(_fmt_stats_row(
                s, ps["argmax_distinct_distribution_delta_step"]
            ))

        dist_cd = summary["pairwise_cliffs_delta"].get(
            "delta_step_argmax_distinct", {}
        )
        if dist_cd:
            print()
            print(
                "-- Pairwise Cliff's delta on Δ_step, "
                "argmax-distinct subset --"
            )
            for key, val in sorted(dist_cd.items()):
                a, b = key.split("__vs__")
                tag = " (notable)" if abs(val) >= 0.3 else ""
                print(f"  {a:<28} vs {b:<28} {val:>+6.3f}{tag}")

    print()
    print("-- Aggregate: mixed-composition vs pure-loss --")
    agg = summary["aggregate_observations"]["mixed_composition_vs_pure_loss"]
    print(f"  pure_loss_strategies     : {agg['pure_loss_strategies']}")
    print(f"  mixed_composition_strategies : "
          f"{agg['mixed_composition_strategies']}")
    print(
        f"  pure_loss     Δ_step mean={agg['pure_loss_delta_step']['mean']:+.2f}"
        f" median={agg['pure_loss_delta_step']['median']:+.2f}"
        f" cat%={agg['pure_loss_delta_step']['catastrophic_tail_mass']:.2f}"
        f" pos%={agg['pure_loss_delta_step']['positive_tail_mass']:.2f}"
    )
    print(
        f"  mixed-comp    Δ_step mean={agg['mixed_composition_delta_step']['mean']:+.2f}"
        f" median={agg['mixed_composition_delta_step']['median']:+.2f}"
        f" cat%={agg['mixed_composition_delta_step']['catastrophic_tail_mass']:.2f}"
        f" pos%={agg['mixed_composition_delta_step']['positive_tail_mass']:.2f}"
    )
    print(
        f"  Cliff's delta mixed vs pure (Δ_step): "
        f"{agg['cliffs_delta_mixed_vs_pure']:+.3f}"
    )

    argmax_agg = summary["aggregate_observations"].get("argmax_equivalence")
    if argmax_agg is not None:
        print()
        print("-- Aggregate: argmax-equivalence --")
        print(
            f"  total argmax-equivalent on train_step: "
            f"{argmax_agg['total_argmax_equivalent_on_train_step']}/300"
        )
        print(
            f"  total argmax-equivalent on both splits: "
            f"{argmax_agg['total_argmax_equivalent_on_both_splits']}"
        )
        print(
            f"  distinct code hashes among argmax-equivalent: "
            f"{argmax_agg['distinct_code_hashes_among_argmax_equivalent']}"
        )
        print(
            f"  mean argmax-equivalent rate across strategies: "
            f"{argmax_agg['mean_argmax_equivalent_rate_across_strategies']:.3f}"
        )


def main() -> int:
    if not RESULTS_DIR.exists():
        print(f"Missing primary batch results at {RESULTS_DIR}", file=sys.stderr)
        return 2

    proposals, skipped = load_primary_batch_proposals(RESULTS_DIR)
    if skipped:
        print(f"Skipped {len(skipped)} records: {skipped[:5]} ...")
    else:
        print("0 records skipped (all provenance files loaded cleanly).")

    print("Computing h_eoh per-instance bins on train_step/train_gate...")
    h_eoh_per_instance_by_split = {
        "train_step": compute_h_eoh_per_instance_bins("train_step"),
        "train_gate": compute_h_eoh_per_instance_bins("train_gate"),
    }
    primary_summary = build_summary(
        proposals,
        h_eoh_per_instance_by_split=h_eoh_per_instance_by_split,
    )
    _print_summary(primary_summary)

    # Validation (optional — run only if the dir exists)
    validation_trajectories: Dict[str, Any] = {}
    if VALIDATION_DIR.exists():
        validation_trajectories, val_skipped = (
            load_validation_trajectories(VALIDATION_DIR)
        )
        if val_skipped:
            print(
                f"Validation skipped {len(val_skipped)} files: "
                f"{val_skipped[:5]}"
            )
    else:
        print(
            f"(validation batch dir {VALIDATION_DIR} missing — "
            "primary-only summary)"
        )

    if validation_trajectories:
        combined = build_combined_summary(
            proposals,
            validation_trajectories,
            h_eoh_per_instance_by_split=h_eoh_per_instance_by_split,
        )
        _print_validation_block(combined)
        to_write = combined
    else:
        to_write = primary_summary

    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.write_text(
        json.dumps(to_write, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print()
    print(f"Wrote {SUMMARY_OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


def _print_validation_block(combined: Dict[str, Any]) -> None:
    v = combined["validation_batch"]
    print()
    print("=" * 110)
    print(
        f"Validation batch — {v['total_calls']} calls "
        f"across {v['n_strategies']} strategies x "
        f"{v['n_trajectories_per_strategy']} trajectories x "
        f"{v['n_steps_per_trajectory']} steps"
    )
    print("=" * 110)
    print(
        f"{'strategy':<28} {'mean_cumul':>11} {'median':>9} "
        f"{'acc':>4} {'rej':>4} {'moved':>5}"
    )
    for s in v["strategies"]:
        ps = v["per_strategy"][s]
        print(
            f"{s:<28} {ps['mean_delta_step_cumulative']:>+11.3f} "
            f"{ps['median_delta_step_cumulative']:>+9.3f} "
            f"{ps['n_accepted_steps']:>4d} "
            f"{ps['n_rejected_steps']:>4d} "
            f"{ps['n_trajectories_that_moved_off_h_eoh']:>5d}"
        )
    print()
    print(
        f"  total acceptances  : {v['aggregate']['total_acceptances']}"
    )
    print(
        f"  total rejections   : {v['aggregate']['total_rejections']}"
    )
    print(
        f"  accepted_behavioral_change (novel): "
        f"{v['aggregate']['total_accepted_behavioral_change']}"
    )
    print(
        f"  reason distribution: "
        f"{v['aggregate']['acceptance_reason_distribution']}"
    )
    print(
        f"  validation rank    : "
        f"{v['aggregate']['cross_strategy_ranking_by_mean_cumulative']}"
    )

    cross = combined["cross_batch_observations"]
    print()
    print("-- Cross-batch ranking comparison --")
    print(
        f"  primary rank (trimmed mean): "
        f"{cross['primary_rank_by_trimmed_mean']}"
    )
    print(
        f"  validation rank (mean cumul): "
        f"{cross['validation_rank_by_mean_cumulative']}"
    )
    if cross["rank_inversions"]:
        print("  rank inversions (primary > validation):")
        for inv in cross["rank_inversions"]:
            print(
                f"    {inv['primary_higher']} ranked above "
                f"{inv['validation_higher']} in primary, below in "
                "validation"
            )
    else:
        print("  (no rank inversions)")


if __name__ == "__main__":
    sys.exit(main())
