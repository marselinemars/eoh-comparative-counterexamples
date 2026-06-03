"""thesis/code/chapter7/figures/figure5_l2_k1_forest.py

Figure 5: L2 k=1 cross-strategy gap — three-measurements forest
plot. The chapter's most important figure (§7.6.1 anchor).

Three horizontal 95% CIs stacked vertically with sources labeled:

  1. Primary single-shot matched-pair (n=59):
     +82.16 [+15.75, +167.99]   →  chapter7_l2_interaction_stratified_by_k.json
  2. Validation trajectory matched-pair (n=3):
     +5.13  [+4.17, +6.93]      →  chapter7_validation_l2_interaction_stratified_by_k.json
  3. Full-dev pass unpaired bootstrap (n_a=5, n_b=3):
     +3.99  [+0.61, +7.93]      →  chapter7_full_dev_pass.json

All three exclude zero (vertical reference at x=0). Three
independent measurements of the same selection-axis advantage of
stratified_representative over worst_only_at_k1 (the boundary
substitute for worst_plus_best at k=1) at L2 k=1.

Usage::

    python -m thesis.code.chapter7.figures.figure5_l2_k1_forest
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[4]
ART = REPO_ROOT / "thesis" / "artifacts"
PRIMARY_PATH = ART / "chapter7_l2_interaction_stratified_by_k.json"
VALIDATION_PATH = ART / "chapter7_validation_l2_interaction_stratified_by_k.json"
FULL_DEV_PATH = ART / "chapter7_full_dev_pass.json"
OUT_DIR = REPO_ROOT / "thesis" / "writing" / "figures"
OUT_BASENAME = "chapter7_l2_k1_three_measurements"


def _primary_k1() -> tuple:
    d = json.loads(PRIMARY_PATH.read_text(encoding="utf-8"))
    for r in d["per_k_results"]:
        if r["k"] == 1:
            return (r["delta_step"]["interaction_mean_diff"],
                    r["delta_step"]["interaction_ci_95"],
                    r["n_matched_pairs"])
    raise RuntimeError("k=1 not found in primary stratified-by-k artifact")


def _validation_k1() -> tuple:
    d = json.loads(VALIDATION_PATH.read_text(encoding="utf-8"))
    for r in d["per_k_results"]:
        if r["k"] == 1:
            return (r["mean_diff"], r["ci_95"], r["n_matched_trajectories"])
    raise RuntimeError("k=1 not found in validation stratified-by-k artifact")


def _full_dev_k1() -> tuple:
    d = json.loads(FULL_DEV_PATH.read_text(encoding="utf-8"))
    for r in d["l2_stratified_by_k_delta_dev"]["per_k_results"]:
        if r["k"] == 1:
            return (r.get("mean_diff_delta_dev"), r.get("ci_95"),
                    (r.get("n_accepted_a"), r.get("n_accepted_b")))
    raise RuntimeError("k=1 not found in full_dev artifact")


def main() -> int:
    p_mean, p_ci, p_n = _primary_k1()
    v_mean, v_ci, v_n = _validation_k1()
    fd_mean, fd_ci, fd_n = _full_dev_k1()

    rows = [
        {
            "label": (
                f"Primary single-shot\nmatched-pair (n={p_n})\n"
                f"on Δ_step (train_step)"
            ),
            "mean": p_mean, "ci": p_ci, "color": "#1f77b4",
        },
        {
            "label": (
                f"Validation trajectory\nmatched-pair (n={v_n})\n"
                f"on terminal Δ_step_cumulative"
            ),
            "mean": v_mean, "ci": v_ci, "color": "#2ca02c",
        },
        {
            "label": (
                f"Full-dev pass\nunpaired bootstrap "
                f"(n_a={fd_n[0]}, n_b={fd_n[1]})\non Δ_dev"
            ),
            "mean": fd_mean, "ci": fd_ci, "color": "#d62728",
        },
    ]

    fig, ax = plt.subplots(figsize=(11, 4.5))
    y_positions = [3, 2, 1]
    for row, y in zip(rows, y_positions):
        lo, hi = row["ci"]
        ax.errorbar(
            [row["mean"]], [y],
            xerr=[[row["mean"] - lo], [hi - row["mean"]]],
            fmt="o", color=row["color"], capsize=6, markersize=10,
            linewidth=2.5,
        )
        ax.text(
            row["mean"], y + 0.13,
            f"{row['mean']:+.2f}  [{lo:+.2f}, {hi:+.2f}]",
            ha="center", va="bottom", fontsize=9, fontweight="bold",
            color=row["color"],
        )

    ax.axvline(0, color="grey", linewidth=1.0, linestyle="--",
               label="cross-strategy gap = 0")
    ax.set_yticks(y_positions)
    ax.set_yticklabels([r["label"] for r in rows], fontsize=9)
    ax.set_xlabel("Cross-strategy gap (bins): "
                  "stratified_representative − worst_plus_best (wo1 at k=1) at L2")
    ax.set_ylim(0.4, 3.6)
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    ax.legend(loc="lower right", fontsize=9)
    fig.suptitle(
        "Figure 5. The L2 k=1 cross-strategy gap, measured three independent ways.\n"
        "All three CIs exclude zero. The selection-axis advantage of "
        "stratified_representative over worst_plus_best (worst_only_at_k1\n"
        "substituting at k=1) at L2 k=1 is the chapter's most reproducible "
        "finding.",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png = OUT_DIR / f"{OUT_BASENAME}.png"
    pdf = OUT_DIR / f"{OUT_BASENAME}.pdf"
    fig.savefig(png, dpi=150)
    fig.savefig(pdf)
    plt.close(fig)
    print(f"Wrote {png} ({png.stat().st_size // 1024} KB)", file=sys.stderr)
    print(f"Wrote {pdf} ({pdf.stat().st_size // 1024} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
