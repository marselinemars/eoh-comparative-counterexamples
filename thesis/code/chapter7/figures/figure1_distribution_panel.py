"""thesis/code/chapter7/figures/figure1_distribution_panel.py

Figure 1: 14-cell Δ_step distribution panel. Box-plots of Δ_step
per cell arranged in a 4×4 grid (rows = (strategy × level) pairs,
columns = k values). Catastrophe threshold (−50) marked as a
horizontal reference line. §7.3.1 anchor.

Source: per-proposal records in
``thesis/results/chapter7_primary_batch_gemini/``.

Usage::

    python -m thesis.code.chapter7.figures.figure1_distribution_panel
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
RESULTS_DIR = REPO_ROOT / "thesis" / "results" / "chapter7_primary_batch_gemini"
OUT_DIR = REPO_ROOT / "thesis" / "writing" / "figures"
OUT_BASENAME = "chapter7_14cell_distribution_panel"

CATASTROPHE = -50.0

# Row order: (strategy_label, level) → row index.
ROWS = [
    ("stratified_representative", 1),
    ("stratified_representative", 2),
    ("worst_plus_best", 1),
    ("worst_plus_best", 2),
]
K_COLS = [1, 2, 4, 8]


def _load_per_cell_deltas() -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = defaultdict(list)
    for path in sorted(RESULTS_DIR.glob("CH7-*.json")):
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        san = r.get("sanitization") or {}
        if san.get("status") != "ok":
            continue
        d = (r.get("scoring") or {}).get("delta_step")
        if not isinstance(d, (int, float)):
            continue
        out[r["cell_id"]].append(float(d))
    return out


def _cell_lookup() -> Dict[tuple, str]:
    return {
        ("stratified_representative", 1, 1): "CH7-01",
        ("stratified_representative", 1, 2): "CH7-02",
        ("stratified_representative", 1, 4): "CH7-03",
        ("stratified_representative", 1, 8): "CH7-04",
        # k=1 boundary substitution for worst_plus_best curve.
        ("worst_plus_best", 1, 1): "CH7-05",  # worst_only_at_k1
        ("worst_plus_best", 1, 2): "CH7-06",
        ("worst_plus_best", 1, 4): "CH7-07",
        ("worst_plus_best", 1, 8): "CH7-08",
        ("stratified_representative", 2, 1): "CH7-09",
        ("stratified_representative", 2, 2): "CH7-10",
        ("stratified_representative", 2, 4): "CH7-11",
        ("worst_plus_best", 2, 1): "CH7-12",  # worst_only_at_k1
        ("worst_plus_best", 2, 2): "CH7-13",
        ("worst_plus_best", 2, 4): "CH7-14",
    }


def main() -> int:
    by_cell = _load_per_cell_deltas()
    cell_lookup = _cell_lookup()
    fig, axes = plt.subplots(4, 4, figsize=(13, 11), sharey=True)
    for r_idx, (strategy, level) in enumerate(ROWS):
        for c_idx, k in enumerate(K_COLS):
            ax = axes[r_idx, c_idx]
            cid = cell_lookup.get((strategy, level, k))
            data = by_cell.get(cid or "", [])
            if not data:
                ax.set_title(
                    f"{cid or '—'}\n(no data)",
                    fontsize=9,
                )
                ax.axhline(0, color="grey", linewidth=0.5)
                ax.axhline(CATASTROPHE, color="red", linewidth=0.5, linestyle=":")
                ax.set_xticks([])
                continue
            bp = ax.boxplot(
                [data], showfliers=True, widths=0.5,
                medianprops={"color": "black", "linewidth": 1.5},
                boxprops={"facecolor": "#cce5ff", "edgecolor": "black"},
                whiskerprops={"color": "black"},
                capprops={"color": "black"},
                flierprops={"marker": "o", "markersize": 3,
                            "markerfacecolor": "red",
                            "markeredgecolor": "none", "alpha": 0.5},
                patch_artist=True,
            )
            ax.axhline(0, color="grey", linewidth=0.6, linestyle="-")
            ax.axhline(CATASTROPHE, color="red", linewidth=0.6, linestyle=":",
                       label="catastrophe @ −50")
            mean = float(np.mean(data))
            ax.scatter([1], [mean], color="black", marker="D", s=18, zorder=5)
            n = len(data)
            label = (
                "worst_only_at_k1" if (strategy == "worst_plus_best" and k == 1)
                else strategy
            )
            ax.set_title(
                f"{cid} ({label[:18]}, L{level}, k={k})\n"
                f"n={n}  mean={mean:+.1f}",
                fontsize=8,
            )
            ax.set_xticks([])
            ax.tick_params(axis="y", labelsize=8)
    for r_idx, (strategy, level) in enumerate(ROWS):
        label = (
            f"{strategy.replace('_',' ')}\nL{level}"
            if strategy != "worst_plus_best"
            else f"worst_plus_best\n(wo1 at k=1)\nL{level}"
        )
        axes[r_idx, 0].set_ylabel(label, fontsize=9)
    for c_idx, k in enumerate(K_COLS):
        axes[-1, c_idx].set_xlabel(f"k={k}", fontsize=10)
    fig.suptitle(
        "Figure 1. Δ_step distribution across the 14 chapter-7 primary cells.\n"
        "Box = IQR; whiskers = 1.5×IQR; black diamond = cell mean; red dots = outliers; "
        "red dotted line = catastrophe threshold (−50).",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png_path = OUT_DIR / f"{OUT_BASENAME}.png"
    pdf_path = OUT_DIR / f"{OUT_BASENAME}.pdf"
    fig.savefig(png_path, dpi=150)
    fig.savefig(pdf_path)
    plt.close(fig)
    print(f"Wrote {png_path} ({png_path.stat().st_size // 1024} KB)", file=sys.stderr)
    print(f"Wrote {pdf_path} ({pdf_path.stat().st_size // 1024} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
