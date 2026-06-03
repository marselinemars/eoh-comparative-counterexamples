"""thesis/code/chapter7/figures/figure3_rank_inversion.py

Figure 3: Single-shot vs compound ranking inversion (slope-graph).
14 cells on the left axis ranked by primary mean Δ_step; the same
14 cells on the right axis ranked by validation mean
Δ_step_cumulative(5); lines connecting each cell's two ranked
positions. Lines crossing visualize inversions. §7.4.2 anchor.

Source: ``thesis/artifacts/chapter7_summary.json`` (primary)
and ``thesis/artifacts/chapter7_validation_summary.json``
(validation).

Usage::

    python -m thesis.code.chapter7.figures.figure3_rank_inversion
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[4]
PRIMARY_PATH = REPO_ROOT / "thesis" / "artifacts" / "chapter7_summary.json"
VALIDATION_PATH = REPO_ROOT / "thesis" / "artifacts" / "chapter7_validation_summary.json"
OUT_DIR = REPO_ROOT / "thesis" / "writing" / "figures"
OUT_BASENAME = "chapter7_rank_inversion"


def main() -> int:
    primary = json.loads(PRIMARY_PATH.read_text(encoding="utf-8"))
    validation = json.loads(VALIDATION_PATH.read_text(encoding="utf-8"))
    primary_means: Dict[str, float] = {
        cid: ((c.get("delta_step_stats") or {}).get("mean"))
        for cid, c in primary["per_cell_summary"].items()
    }
    valid_means: Dict[str, float] = {
        c["cell"]["cell_id"]: c["delta_step_cumulative_5_mean"]
        for c in validation["per_cell"]
    }
    cell_ids = sorted(primary_means.keys())
    # Rank: most-positive at top (rank 1).
    rank_primary = sorted(cell_ids, key=lambda c: -primary_means[c])
    rank_valid = sorted(
        cell_ids, key=lambda c: -(valid_means.get(c) or -1e18)
    )

    fig, ax = plt.subplots(figsize=(10, 9))
    n = len(cell_ids)
    # Y positions: top = rank 1 = y = n, bottom = rank n = y = 1.
    y_primary = {cid: (n - rank_primary.index(cid)) for cid in cell_ids}
    y_valid = {cid: (n - rank_valid.index(cid)) for cid in cell_ids}

    for cid in cell_ids:
        y1, y2 = y_primary[cid], y_valid[cid]
        crossed = (y1 != y2)
        color = "#1f77b4" if crossed else "#cccccc"
        lw = 1.4 if crossed else 0.8
        ax.plot([0, 1], [y1, y2], color=color, linewidth=lw, alpha=0.85)

    for cid in cell_ids:
        ax.text(-0.04, y_primary[cid],
                f"{cid}  {primary_means[cid]:+.1f}",
                ha="right", va="center", fontsize=9)
        ax.text(1.04, y_valid[cid],
                f"{cid}  {valid_means.get(cid, float('nan')):+.2f}",
                ha="left", va="center", fontsize=9)

    ax.text(0, n + 0.7, "Primary single-shot\nmean Δ_step",
            ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.text(1, n + 0.7, "Validation compound\nmean Δ_step_cumulative(5)",
            ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.set_xlim(-0.5, 1.5)
    ax.set_ylim(0.4, n + 2.1)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    # 42-of-91 inversion count from chapter7_validation_summary.json.
    inv = validation.get("single_shot_vs_compound", {}).get(
        "inversion_count_pairwise"
    )
    fig.suptitle(
        f"Figure 3. Single-shot vs compound ranking of the 14 ch7 cells.\n"
        f"Left axis: rank by primary single-shot mean Δ_step. "
        f"Right axis: rank by validation mean Δ_step_cumulative(5).\n"
        f"Crossing lines visualize the {inv} of 91 pairwise inversions.",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.93])
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
