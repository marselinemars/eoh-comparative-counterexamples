"""W-D.3 (session 3) — §4.5.4.1 trajectory plot.

Reads the four n=6 trajectory artifacts and the underlying per-call
validation records, reconstructs cumulative Δ_step per trajectory across
five refinement steps, and renders a 2×2 panel figure (one cell per
panel; six trajectory lines per panel).

Cells:
  Top-left:    stratified_representative @ L1 @ k=4
  Top-right:   worst_plus_best          @ L1 @ k=4
  Bottom-left: stratified_representative @ L2 @ k=1   (CH7-09)
  Bottom-right: worst_only_at_k1        @ L2 @ k=1   (CH7-12)

Data sourcing per cell:
  - The 3 ORIGINAL trajectories (traj 0,1,2) are reconstructed from the
    per-step records in thesis/results/chapter{5,7}_validation_batch_gemini/.
  - The 3 EXTENSION trajectories (traj 3,4,5) come from the artifact's
    n3_extension_debug[*].per_step block.

Outputs: thesis/figures/chapter4_trajectory_plot.{pdf,png}.

Hard-coded paths are intentional — this is for in-repo reproducibility,
not general reuse.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


REPO = Path(__file__).resolve().parents[3]
ARTIFACTS = REPO / "thesis" / "artifacts"
RESULTS = REPO / "thesis" / "results"
FIG_OUT = REPO / "thesis" / "figures"

CELLS = [
    {
        "title": "stratified_representative, L1, k=4",
        "artifact": ARTIFACTS / "chapter5_stratified_L1_k4_trajectories_n6.json",
        "ch": 5,
        "strategy": "stratified_representative",
        "n6_mean_n3": 7.12,
    },
    {
        "title": "worst_plus_best, L1, k=4",
        "artifact": ARTIFACTS / "chapter5_worst_plus_best_L1_k4_trajectories_n6.json",
        "ch": 5,
        "strategy": "worst_plus_best",
        "n6_mean_n3": 4.31,
    },
    {
        "title": "stratified_representative, L2, k=1",
        "artifact": ARTIFACTS / "chapter7_stratified_L2_k1_trajectories_n6.json",
        "ch": 7,
        "cell_id": "CH7-09",
        "n6_mean_n3": None,
    },
    {
        "title": "worst_only_at_k1, L2, k=1",
        "artifact": ARTIFACTS / "chapter7_worst_only_L2_k1_trajectories_n6.json",
        "ch": 7,
        "cell_id": "CH7-12",
        "n6_mean_n3": None,
    },
]


def load_chapter5_original(strategy: str) -> list[list[float]]:
    """Return [traj][step_index 0..4] of per-step delta-or-zero values for
    the 3 original trajectories (set_index 100,101,102)."""
    out: list[list[float]] = []
    val_dir = RESULTS / "chapter5_validation_batch_gemini"
    for traj_idx in (0, 1, 2):
        per_step: list[float] = []
        for step in range(1, 6):  # chapter5 uses step1..step5 (1-indexed)
            f = val_dir / f"{strategy}_traj{traj_idx}_step{step}.json"
            if not f.exists():
                raise FileNotFoundError(f)
            rec = json.loads(f.read_text(encoding="utf-8"))
            accepted = bool(rec.get("accepted"))
            d = float(rec.get("delta_step_local") or 0.0)
            per_step.append(d if accepted else 0.0)
        out.append(per_step)
    return out


def load_chapter7_original(cell_id: str) -> list[list[float]]:
    out: list[list[float]] = []
    val_dir = RESULTS / "chapter7_validation_batch_gemini"
    for traj_idx in (0, 1, 2):
        per_step: list[float] = []
        for step in range(5):  # chapter7 uses step0..step4 (0-indexed)
            f = val_dir / f"chapter7_validation_{cell_id}_traj{traj_idx}_step{step}.json"
            if not f.exists():
                raise FileNotFoundError(f)
            rec = json.loads(f.read_text(encoding="utf-8"))
            ad = rec.get("acceptance_decision")
            accepted = ad == "accepted"
            d = float(rec.get("delta_step_local") or 0.0)
            per_step.append(d if accepted else 0.0)
        out.append(per_step)
    return out


def load_extension(artifact_path: Path) -> list[list[float]]:
    """Return [traj 3,4,5][step 1..5] of accepted-only per-step deltas."""
    art = json.loads(artifact_path.read_text(encoding="utf-8"))
    debug = art["n3_extension_debug"]
    out: list[list[float]] = []
    for entry in debug:
        steps = entry["per_step"]
        steps_sorted = sorted(steps, key=lambda s: s.get("step", 0))
        per_step: list[float] = []
        for s in steps_sorted:
            accepted = bool(s.get("accepted"))
            d = float(s.get("delta_step_local") or 0.0)
            per_step.append(d if accepted else 0.0)
        out.append(per_step[:5])
    return out


def cumulative(per_step_deltas: list[float]) -> np.ndarray:
    """Convert a length-5 list of accepted-only deltas to a length-6
    cumulative trajectory starting at 0."""
    arr = np.zeros(6, dtype=float)
    arr[1:] = np.cumsum(per_step_deltas)
    return arr


def collect_cell(cell: dict) -> list[np.ndarray]:
    """Return 6 cumulative trajectories for the cell."""
    if cell["ch"] == 5:
        original = load_chapter5_original(cell["strategy"])
    else:
        original = load_chapter7_original(cell["cell_id"])
    extension = load_extension(cell["artifact"])
    all_six = original + extension
    return [cumulative(steps) for steps in all_six]


def main() -> None:
    FIG_OUT.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(9.0, 6.5), sharex=True)

    panel_data: list[list[np.ndarray]] = []
    for cell in CELLS:
        panel_data.append(collect_cell(cell))

    # Share y-axis within each row
    row_ranges: list[tuple[float, float]] = []
    for r in range(2):
        vals = np.concatenate(panel_data[2 * r] + panel_data[2 * r + 1])
        lo = float(min(vals.min(), -1.0))
        hi = float(vals.max())
        pad = max(1.0, 0.05 * (hi - lo))
        row_ranges.append((lo - pad, hi + pad))

    # Colorblind-safe palette (Wong 2011 / matplotlib 'tab10' subset);
    # 6 distinct hues, one per trajectory. Original 3 (traj 0,1,2) use
    # darker hues; the E5-extension 3 (traj 3,4,5) use lighter hues so
    # the "original-vs-extension" distinction stays visually readable.
    traj_colors = [
        "#0072B2",  # traj 0 (original) — blue
        "#D55E00",  # traj 1 (original) — vermillion
        "#009E73",  # traj 2 (original) — bluish green
        "#56B4E9",  # traj 3 (extension) — sky blue
        "#E69F00",  # traj 4 (extension) — orange
        "#CC79A7",  # traj 5 (extension) — reddish purple
    ]
    line_alpha = 0.85

    for i, (ax, cell, trajs) in enumerate(zip(axes.flat, CELLS, panel_data)):
        for traj_idx, traj in enumerate(trajs):
            ax.plot(
                range(6),
                traj,
                color=traj_colors[traj_idx],
                alpha=line_alpha,
                linewidth=1.6,
                marker="o",
                markersize=3.5,
                label=f"traj {traj_idx}" if i == 0 else None,
            )
        ax.axhline(0.0, color="#999999", linewidth=0.7, linestyle="--", zorder=0)
        ax.set_title(cell["title"], fontfamily="monospace", fontsize=10.5, pad=6)
        ax.grid(True, alpha=0.25, linewidth=0.6)
        ax.set_xticks(range(6))

        # Apply per-row shared y-range
        r = i // 2
        ax.set_ylim(*row_ranges[r])

        # Axis labels only on bottom row / left column
        if i // 2 == 1:
            ax.set_xlabel("Refinement step")
        if i % 2 == 0:
            ax.set_ylabel("Cumulative Δ_step (bins)")

    fig.suptitle(
        "Per-trajectory cumulative Δ_step across the four E5-extended validation cells (n=6)",
        fontsize=11.5,
        y=0.995,
    )
    # Legend (one shared legend at top, labelling traj 0-5)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.955),
        ncol=6,
        frameon=False,
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))

    pdf_path = FIG_OUT / "chapter4_trajectory_plot.pdf"
    png_path = FIG_OUT / "chapter4_trajectory_plot.png"
    fig.savefig(pdf_path)
    fig.savefig(png_path, dpi=200)
    print(f"wrote {pdf_path}")
    print(f"wrote {png_path}")

    # Print endpoint sanity check
    for cell, trajs in zip(CELLS, panel_data):
        endpoints = [float(t[-1]) for t in trajs]
        mean = sum(endpoints) / len(endpoints)
        print(
            f"  cell={cell['title']:<48s}  endpoints={[round(e, 2) for e in endpoints]}  n6_mean={mean:.3f}"
        )


if __name__ == "__main__":
    main()
