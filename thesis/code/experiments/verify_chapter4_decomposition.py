"""
thesis/code/experiments/verify_chapter4_decomposition.py

Post-batch analysis driver for the §4.5.3 three-way decomposition
(full / gap-only / no-reference). Reads chapter-5's existing
stratified_representative L1 k=4 records (the "full" cell), the
new E1 records, and the new E2 records, then computes:

  - Per-cell delta_step distribution stats
    (design doc §6.3, top of the table).
  - All three matched-pair contrasts:
      full vs gap-only       (Δ_step paired diff + 95% CI)
      gap-only vs no-reference
      full vs no-reference
    (design doc §6.3, headline analyses)
  - Cliff's δ on each pair.
  - Argmax-equivalence rate per cell.
  - Proposal-hash overlap across cells.
  - Joint regime classification (A / B / C / D / mixed) per
    design doc §7.

Outputs:
  thesis/results/chapter4_decomposition_analysis.md
  (and a corresponding .json with the raw metrics).

Usage:
    python -m thesis.code.experiments.verify_chapter4_decomposition
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from thesis.code.chapter4_decomposition_shared.analysis import (
    argmax_equivalence_rate,
    classify_regime,
    cliffs_delta,
    load_chapter5_full_cell_records,
    load_records_from_dir,
    matched_pair_delta_step,
    per_cell_delta_step_stats,
    proposal_hash_overlap,
    _ok_delta_steps,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

CH5_DIR = REPO_ROOT / "thesis" / "results" / "chapter5_primary_batch_gemini"
NOREF_DIR = (
    REPO_ROOT / "thesis" / "results"
    / "chapter4_noref_primary_batch_gemini"
)
GAPONLY_DIR = (
    REPO_ROOT / "thesis" / "results"
    / "chapter4_gaponly_primary_batch_gemini"
)
OUT_DIR = REPO_ROOT / "thesis" / "results"
OUT_MD = OUT_DIR / "chapter4_decomposition_analysis.md"
OUT_JSON = OUT_DIR / "chapter4_decomposition_analysis.json"


def _render_markdown(metrics: Dict[str, Any]) -> str:
    out = ["# Chapter 4 §4.5.3 — Three-way decomposition analysis\n"]
    out.append(
        "Design doc: "
        "`thesis/writing/chapter4_comparative_decomposition_design.md`\n"
    )
    out.append("\n## Per-cell Δ_step distribution\n")
    out.append("| Cell | n | mean | median | p25 | p75 | IQR | trim10 | "
               "positive_tail | cat_-50 | cat_-100 |\n")
    out.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for cell, s in metrics["per_cell_stats"].items():
        if s.get("n", 0) == 0:
            out.append(f"| {cell} | 0 | — | — | — | — | — | — | — | — | — |\n")
            continue
        out.append(
            f"| {cell} | {s['n']} | {s['mean']:.3f} | {s['median']:.3f} | "
            f"{s['p25']:.3f} | {s['p75']:.3f} | {s['iqr']:.3f} | "
            f"{s['trim10']:.3f} | {s['positive_tail_mass']:.3f} | "
            f"{s['catastrophic_tail_mass_at_-50']:.3f} | "
            f"{s['catastrophic_tail_mass_at_-100']:.3f} |\n"
        )

    out.append("\n## Matched-pair Δ_step (paired difference)\n")
    out.append(
        "| Contrast | n_paired | mean_diff | mean CI 95 | "
        "median_diff | median CI 95 | excludes_zero (mean) |\n"
    )
    out.append("|---|---:|---:|---|---:|---|---|\n")
    for label, mp in metrics["matched_pair_contrasts"].items():
        if mp.get("n_paired_observations", 0) == 0:
            out.append(f"| {label} | 0 | — | — | — | — | — |\n")
            continue
        mci = mp["mean_ci_95"]
        medci = mp["median_ci_95"]
        out.append(
            f"| {label} | {mp['n_paired_observations']} | "
            f"{mp['mean_paired_diff']:+.3f} | "
            f"[{mci[0]:+.3f}, {mci[1]:+.3f}] | "
            f"{mp['median_paired_diff']:+.3f} | "
            f"[{medci[0]:+.3f}, {medci[1]:+.3f}] | "
            f"{mp['ci_excludes_zero_mean']} |\n"
        )

    out.append("\n## Cliff's δ on Δ_step distributions\n")
    out.append("| Contrast | Cliff's δ |\n|---|---:|\n")
    for label, d in metrics["cliffs_delta"].items():
        out.append(f"| {label} | {d:+.3f} |\n")

    out.append("\n## Argmax-equivalence rate per cell\n")
    out.append("| Cell | n_ok | argmax_equivalent | rate |\n|---|---:|---:|---:|\n")
    for cell, ae in metrics["argmax_equivalence"].items():
        if ae.get("n_ok", 0) == 0:
            out.append(f"| {cell} | 0 | — | — |\n")
            continue
        out.append(
            f"| {cell} | {ae['n_ok']} | {ae['n_argmax_equivalent']} | "
            f"{ae['argmax_equivalent_rate']:.3f} |\n"
        )

    out.append("\n## Proposal-hash overlap across cells\n")
    out.append(
        "| Contrast | distinct A | distinct B | overlap | Jaccard |\n"
        "|---|---:|---:|---:|---:|\n"
    )
    for label, ov in metrics["proposal_hash_overlap"].items():
        j = ov["jaccard"]
        out.append(
            f"| {label} | {ov['n_distinct_cell_a']} | "
            f"{ov['n_distinct_cell_b']} | {ov['n_overlap']} | "
            f"{(f'{j:.3f}' if j is not None else '—')} |\n"
        )

    out.append("\n## Regime classification (design doc §7)\n")
    out.append(f"**{metrics['regime']}**\n")

    return "".join(out)


def main() -> int:
    if not CH5_DIR.exists():
        print(
            f"[error] chapter-5 result dir not found: {CH5_DIR}. "
            "The 'full' cell records (stratified_representative L1) "
            "must be present.",
            file=sys.stderr,
        )
        return 1

    full = load_chapter5_full_cell_records(CH5_DIR)
    noref = load_records_from_dir(NOREF_DIR) if NOREF_DIR.exists() else []
    gaponly = (
        load_records_from_dir(GAPONLY_DIR) if GAPONLY_DIR.exists() else []
    )

    print(f"Loaded: full={len(full)}, gaponly={len(gaponly)}, "
          f"noref={len(noref)}")

    # Per-cell stats.
    per_cell_stats = {
        "full (ch5 stratified_representative L1 k=4)":
            per_cell_delta_step_stats(full),
        "gap-only (E2)": per_cell_delta_step_stats(gaponly),
        "no-reference (E1)": per_cell_delta_step_stats(noref),
    }

    # Matched-pair contrasts.
    matched_pair_contrasts = {
        "full vs gap-only": matched_pair_delta_step(full, gaponly),
        "gap-only vs no-reference": matched_pair_delta_step(gaponly, noref),
        "full vs no-reference": matched_pair_delta_step(full, noref),
    }

    # Cliff's δ on distributions (independent-distribution treatment;
    # the matched-pair CIs above are the load-bearing inference).
    full_vals = _ok_delta_steps(full)
    gap_vals = _ok_delta_steps(gaponly)
    no_vals = _ok_delta_steps(noref)
    cliffs = {
        "full vs gap-only": cliffs_delta(full_vals, gap_vals),
        "gap-only vs no-reference": cliffs_delta(gap_vals, no_vals),
        "full vs no-reference": cliffs_delta(full_vals, no_vals),
    }

    argmax = {
        "full": argmax_equivalence_rate(full),
        "gap-only": argmax_equivalence_rate(gaponly),
        "no-reference": argmax_equivalence_rate(noref),
    }

    overlap = {
        "full vs gap-only": proposal_hash_overlap(full, gaponly),
        "gap-only vs no-reference": proposal_hash_overlap(gaponly, noref),
        "full vs no-reference": proposal_hash_overlap(full, noref),
    }

    regime = classify_regime(
        matched_pair_contrasts["full vs gap-only"],
        matched_pair_contrasts["gap-only vs no-reference"],
    )

    metrics = {
        "n_records_loaded": {
            "full": len(full),
            "gap-only": len(gaponly),
            "no-reference": len(noref),
        },
        "per_cell_stats": per_cell_stats,
        "matched_pair_contrasts": matched_pair_contrasts,
        "cliffs_delta": cliffs,
        "argmax_equivalence": argmax,
        "proposal_hash_overlap": overlap,
        "regime": regime,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    OUT_MD.write_text(_render_markdown(metrics), encoding="utf-8")
    print(f"Wrote {OUT_MD.relative_to(REPO_ROOT).as_posix()}")
    print(f"Wrote {OUT_JSON.relative_to(REPO_ROOT).as_posix()}")
    print(f"Regime: {regime}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
