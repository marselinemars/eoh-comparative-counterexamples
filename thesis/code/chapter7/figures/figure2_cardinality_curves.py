"""thesis/code/chapter7/figures/figure2_cardinality_curves.py

Figure 2: Cardinality curves. 2×2 grid (rows = level, columns =
strategy). Each panel plots cell-mean Δ_step on y-axis vs k on
x-axis with bootstrap 95% CIs as error bars. §7.3.2 anchor.

The L2 "k=2 is worst" U-shape is visually obvious at both
selection strategies; the L2 worst_plus_best amplitude is much
larger than the stratified amplitude.

Source: ``thesis/artifacts/chapter7_summary.json``.

Usage::

    python -m thesis.code.chapter7.figures.figure2_cardinality_curves
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[4]
SUMMARY_PATH = REPO_ROOT / "thesis" / "artifacts" / "chapter7_summary.json"
OUT_DIR = REPO_ROOT / "thesis" / "writing" / "figures"
OUT_BASENAME = "chapter7_cardinality_curves"


def main() -> int:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    curves = summary["cardinality_curves"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharey=False)
    strategies = ["stratified_representative", "worst_plus_best"]
    levels = [1, 2]
    for r_idx, level in enumerate(levels):
        for c_idx, strategy in enumerate(strategies):
            ax = axes[r_idx, c_idx]
            key = f"{strategy}@L{level}"
            curve = curves.get(key)
            if curve is None:
                ax.set_title(f"{strategy} L{level}\n(no data)")
                continue
            rows = curve["rows"]
            ks = [r["k"] for r in rows]
            means = [r["delta_step_mean"] for r in rows]
            cis = [r["delta_step_ci_mean"] for r in rows]
            lo = [m - ci[0] for m, ci in zip(means, cis)]
            hi = [ci[1] - m for m, ci in zip(means, cis)]
            ax.errorbar(
                ks, means, yerr=[lo, hi],
                marker="o", linestyle="-", color="#1f77b4",
                capsize=4, linewidth=1.5,
            )
            ax.axhline(0, color="grey", linewidth=0.6, linestyle="-")
            ax.set_xscale("log", base=2)
            ax.set_xticks(ks)
            ax.set_xticklabels([str(k) for k in ks])
            ax.set_xlabel("k (cardinality)")
            ax.set_ylabel("cell-mean Δ_step (bins)")
            label = "worst_plus_best (wo1 at k=1)" if strategy == "worst_plus_best" else strategy
            ax.set_title(f"{label} at L{level}", fontsize=10)
            # Annotate each cell with cell_id.
            for x, y, cid in zip(ks, means, [r["cell_id"] for r in rows]):
                ax.annotate(
                    cid, xy=(x, y), xytext=(4, 4),
                    textcoords="offset points", fontsize=7, color="grey",
                )
    fig.suptitle(
        "Figure 2. Cell-mean Δ_step on train_step as a function of k, "
        "per (strategy × level). Error bars are 5,000-resample bootstrap 95% CIs.\n"
        "Both L2 panels show a clear k=2-is-worst U-shape; the worst_plus_best "
        "L2 amplitude dwarfs the stratified L2 amplitude.",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
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
