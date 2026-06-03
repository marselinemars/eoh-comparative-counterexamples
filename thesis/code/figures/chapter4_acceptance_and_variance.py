"""Chapter 4 acceptance-rate + variance figure (post-session-3 figure addition).

Two-panel figure visualizing proposal acceptance rates (Panel A) and
bootstrap 95% CI half-widths on cumulative Δ_step(5) (Panel B) across the
21 validation cells (§4.2: 3 cells, §4.3: 4 cells, §4.4: 14 cells). Both
panels share the same cell ordering, sorted by acceptance rate descending
in Panel A, so left-to-right comparison between acceptance and variance
is meaningful.

Data sourcing per cell:
  - §4.2 cells (chapter 5 validation): per-step records in
    thesis/results/chapter5_validation_batch_gemini/
    <strategy>_traj<i>_step<j>.json (1-indexed steps).
    Two cells (stratified_representative, worst_plus_best) use n=6 from
    the W-D.3 extension; uniform_random stays at n=3.
  - §4.3 cells (chapter 6 validation): per-step records in
    thesis/results/chapter6_validation_batch_gemini/
    <strategy>@L<level>_traj<i>_step<j>.json (0-indexed steps).
    All 4 cells at n=3.
  - §4.4 cells (chapter 7 validation): per-step records in
    thesis/results/chapter7_validation_batch_gemini/
    chapter7_validation_<cell_id>_traj<i>_step<j>.json (0-indexed steps).
    Two cells (CH7-09, CH7-12) use n=6 via the artifact's
    n3_extension_debug block; the other 12 stay at n=3.

Outputs: thesis/figures/chapter4_acceptance_and_variance.{pdf,png}.
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


# ---------- Cell registry ----------------------------------------------------

# Each cell: dict with label (short monospace), level (1 or 2), and a loader
# that returns list[list[(accepted: bool, delta: float)]] for [traj][step].

CH5_CELLS = [
    ("strat L1 k4", "stratified_representative", 1, 4, "n6"),
    ("wpb L1 k4",   "worst_plus_best",           1, 4, "n6"),
    ("uni L1 k4",   "uniform_random",            1, 4, "n3"),
]

CH6_CELLS = [
    ("strat L1 k4 (§4.3)", "stratified_representative@L1", 1, 4),
    ("strat L2 k4 (§4.3)", "stratified_representative@L2", 2, 4),
    ("wpb L1 k4 (§4.3)",   "worst_plus_best@L1",           1, 4),
    ("wpb L2 k4 (§4.3)",   "worst_plus_best@L2",           2, 4),
]

CH7_CELLS = [
    ("CH7-01 strat L1 k1", "CH7-01", 1, 1),
    ("CH7-02 strat L1 k2", "CH7-02", 1, 2),
    ("CH7-03 strat L1 k4", "CH7-03", 1, 4),
    ("CH7-04 strat L1 k8", "CH7-04", 1, 8),
    ("CH7-05 wo1 L1 k1",   "CH7-05", 1, 1),
    ("CH7-06 wpb L1 k2",   "CH7-06", 1, 2),
    ("CH7-07 wpb L1 k4",   "CH7-07", 1, 4),
    ("CH7-08 wpb L1 k8",   "CH7-08", 1, 8),
    ("CH7-09 strat L2 k1", "CH7-09", 2, 1),
    ("CH7-10 strat L2 k2", "CH7-10", 2, 2),
    ("CH7-11 strat L2 k4", "CH7-11", 2, 4),
    ("CH7-12 wo1 L2 k1",   "CH7-12", 2, 1),
    ("CH7-13 wpb L2 k2",   "CH7-13", 2, 2),
    ("CH7-14 wpb L2 k4",   "CH7-14", 2, 4),
]

# Cells extended to n=6 via E5
CH7_N6_CELLS = {"CH7-09", "CH7-12"}


# ---------- Loaders ----------------------------------------------------------

def load_ch5_cell(strategy: str, want_n6: bool) -> list[list[tuple[bool, float]]]:
    """Return [traj][step] of (accepted, delta) for chapter 5 cells.

    Chapter 5 step indexing: 1..5 (1-indexed).
    Trajectories: 0..2 (original) and 3..5 (E5 extension if available).
    """
    val_dir = RESULTS / "chapter5_validation_batch_gemini"
    n_traj = 6 if want_n6 else 3
    out: list[list[tuple[bool, float]]] = []
    for traj_idx in range(n_traj):
        per_step: list[tuple[bool, float]] = []
        for step in range(1, 6):
            f = val_dir / f"{strategy}_traj{traj_idx}_step{step}.json"
            if not f.exists():
                # Fall back to E5 extension artifact if traj>=3 files missing
                ext_art = (
                    ARTIFACTS
                    / f"chapter5_{strategy.replace('worst_plus_best', 'worst_plus_best')}_L1_k4_trajectories_n6.json"
                )
                if traj_idx >= 3 and ext_art.exists():
                    art = json.loads(ext_art.read_text(encoding="utf-8"))
                    debug = art["n3_extension_debug"]
                    ext_entry = debug[traj_idx - 3]
                    ext_steps = sorted(ext_entry["per_step"], key=lambda s: s.get("step", 0))
                    s = ext_steps[step - 1]
                    accepted = bool(s.get("accepted"))
                    d = float(s.get("delta_step_local") or 0.0)
                    per_step.append((accepted, d))
                    continue
                raise FileNotFoundError(f)
            rec = json.loads(f.read_text(encoding="utf-8"))
            accepted = bool(rec.get("accepted"))
            d = float(rec.get("delta_step_local") or 0.0)
            per_step.append((accepted, d))
        out.append(per_step)
    return out


def load_ch6_cell(cell_id: str) -> list[list[tuple[bool, float]]]:
    """Return [traj][step] of (accepted, delta) for chapter 6 cells.

    Chapter 6 step indexing: 0..4 (0-indexed). 3 trajectories per cell.
    """
    val_dir = RESULTS / "chapter6_validation_batch_gemini"
    out: list[list[tuple[bool, float]]] = []
    for traj_idx in range(3):
        per_step: list[tuple[bool, float]] = []
        for step in range(5):
            f = val_dir / f"{cell_id}_traj{traj_idx}_step{step}.json"
            if not f.exists():
                raise FileNotFoundError(f)
            rec = json.loads(f.read_text(encoding="utf-8"))
            accepted = rec.get("acceptance_decision") == "accepted"
            d = float(rec.get("delta_step_local") or 0.0)
            per_step.append((accepted, d))
        out.append(per_step)
    return out


def load_ch7_cell(cell_id: str, want_n6: bool) -> list[list[tuple[bool, float]]]:
    """Return [traj][step] of (accepted, delta) for chapter 7 cells.

    Chapter 7 step indexing: 0..4 (0-indexed). 3 trajectories per cell;
    CH7-09 and CH7-12 extended to 6 via the n=6 artifact.
    """
    val_dir = RESULTS / "chapter7_validation_batch_gemini"
    out: list[list[tuple[bool, float]]] = []
    # Original 3 trajectories from per-step records
    for traj_idx in range(3):
        per_step: list[tuple[bool, float]] = []
        for step in range(5):
            f = val_dir / f"chapter7_validation_{cell_id}_traj{traj_idx}_step{step}.json"
            if not f.exists():
                raise FileNotFoundError(f)
            rec = json.loads(f.read_text(encoding="utf-8"))
            accepted = rec.get("acceptance_decision") == "accepted"
            d = float(rec.get("delta_step_local") or 0.0)
            per_step.append((accepted, d))
        out.append(per_step)

    # Extension 3 trajectories from the n6 artifact (only for CH7-09 / CH7-12)
    if want_n6 and cell_id in CH7_N6_CELLS:
        if cell_id == "CH7-09":
            art_path = ARTIFACTS / "chapter7_stratified_L2_k1_trajectories_n6.json"
        else:
            art_path = ARTIFACTS / "chapter7_worst_only_L2_k1_trajectories_n6.json"
        art = json.loads(art_path.read_text(encoding="utf-8"))
        debug = art["n3_extension_debug"]
        for entry in debug:
            steps_sorted = sorted(entry["per_step"], key=lambda s: s.get("step", 0))
            per_step: list[tuple[bool, float]] = []
            for s in steps_sorted[:5]:
                accepted = bool(s.get("accepted"))
                d = float(s.get("delta_step_local") or 0.0)
                per_step.append((accepted, d))
            out.append(per_step)
    return out


# ---------- Per-cell stats ---------------------------------------------------

def cell_acceptance_rate(per_traj: list[list[tuple[bool, float]]]) -> float:
    total = sum(len(t) for t in per_traj)
    accepted = sum(1 for t in per_traj for (acc, _) in t if acc)
    return accepted / total if total else 0.0


def cell_cumulative_endpoints(per_traj: list[list[tuple[bool, float]]]) -> np.ndarray:
    """Return one cumulative Δ_step(5) per trajectory."""
    out = []
    for traj in per_traj:
        cum = 0.0
        for acc, d in traj:
            if acc:
                cum += d
        out.append(cum)
    return np.array(out, dtype=float)


def bootstrap_ci_halfwidth(endpoints: np.ndarray, n_resamples: int = 10000,
                            seed: int = 2026) -> tuple[float, float, float]:
    """Return (mean, ci_low, ci_high) under 95% percentile bootstrap."""
    rng = np.random.default_rng(seed)
    n = len(endpoints)
    if n == 0:
        return (0.0, 0.0, 0.0)
    means = np.empty(n_resamples)
    for r in range(n_resamples):
        idx = rng.integers(0, n, n)
        means[r] = endpoints[idx].mean()
    lo = float(np.percentile(means, 2.5))
    hi = float(np.percentile(means, 97.5))
    return (float(endpoints.mean()), lo, hi)


# ---------- Build records ---------------------------------------------------

def collect_all_cells() -> list[dict]:
    records: list[dict] = []

    # Chapter 5
    for label, strategy, lv, k, n_tag in CH5_CELLS:
        per_traj = load_ch5_cell(strategy, want_n6=(n_tag == "n6"))
        endpoints = cell_cumulative_endpoints(per_traj)
        mean, lo, hi = bootstrap_ci_halfwidth(endpoints)
        records.append({
            "label": label,
            "level": lv,
            "k": k,
            "n_traj": len(per_traj),
            "acceptance": cell_acceptance_rate(per_traj),
            "mean": mean,
            "ci_low": lo,
            "ci_high": hi,
            "ci_half": (hi - lo) / 2.0,
            "source": "§4.2",
        })

    # Chapter 6
    for label, cell_id, lv, k in CH6_CELLS:
        per_traj = load_ch6_cell(cell_id)
        endpoints = cell_cumulative_endpoints(per_traj)
        mean, lo, hi = bootstrap_ci_halfwidth(endpoints)
        records.append({
            "label": label,
            "level": lv,
            "k": k,
            "n_traj": len(per_traj),
            "acceptance": cell_acceptance_rate(per_traj),
            "mean": mean,
            "ci_low": lo,
            "ci_high": hi,
            "ci_half": (hi - lo) / 2.0,
            "source": "§4.3",
        })

    # Chapter 7
    for label, cell_id, lv, k in CH7_CELLS:
        per_traj = load_ch7_cell(cell_id, want_n6=(cell_id in CH7_N6_CELLS))
        endpoints = cell_cumulative_endpoints(per_traj)
        mean, lo, hi = bootstrap_ci_halfwidth(endpoints)
        records.append({
            "label": label,
            "level": lv,
            "k": k,
            "n_traj": len(per_traj),
            "acceptance": cell_acceptance_rate(per_traj),
            "mean": mean,
            "ci_low": lo,
            "ci_high": hi,
            "ci_half": (hi - lo) / 2.0,
            "source": "§4.4",
        })

    return records


# ---------- Plot ------------------------------------------------------------

def main() -> None:
    FIG_OUT.mkdir(parents=True, exist_ok=True)

    records = collect_all_cells()
    # Sort by acceptance descending (Panel A's natural ordering)
    records.sort(key=lambda r: -r["acceptance"])

    labels = [r["label"] for r in records]
    acceptance = [r["acceptance"] for r in records]
    ci_half = [r["ci_half"] for r in records]
    levels = [r["level"] for r in records]

    # Two-color encoding for structural level (L1 vs L2), colorblind-safe
    color_L1 = "#999999"  # mid grey
    color_L2 = "#0072B2"  # blue (Wong)
    colors = [color_L2 if lv == 2 else color_L1 for lv in levels]

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(13.5, 6.0))

    x = np.arange(len(labels))

    # Panel A — acceptance rate
    axA.bar(x, acceptance, color=colors, edgecolor="black", linewidth=0.5)
    axA.set_xticks(x)
    axA.set_xticklabels(labels, rotation=55, ha="right", fontfamily="monospace", fontsize=8)
    axA.set_ylabel("Acceptance rate")
    axA.set_title("Proposal acceptance rate per validation cell", fontsize=11)
    axA.set_ylim(0, max(1.0, max(acceptance) * 1.08))
    axA.grid(True, axis="y", alpha=0.3, linewidth=0.6)
    axA.set_axisbelow(True)
    axA.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))

    # Panel B — CI half-width
    axB.bar(x, ci_half, color=colors, edgecolor="black", linewidth=0.5)
    axB.set_xticks(x)
    axB.set_xticklabels(labels, rotation=55, ha="right", fontfamily="monospace", fontsize=8)
    axB.set_ylabel("Bootstrap 95% CI half-width (bins)")
    axB.set_title("CI half-width on cumulative Δ_step(5)", fontsize=11)
    axB.grid(True, axis="y", alpha=0.3, linewidth=0.6)
    axB.set_axisbelow(True)

    # Shared legend for the L1 / L2 color encoding
    from matplotlib.patches import Patch
    legend_handles = [
        Patch(facecolor=color_L1, edgecolor="black", linewidth=0.5, label="Level 1 (no trace)"),
        Patch(facecolor=color_L2, edgecolor="black", linewidth=0.5, label="Level 2 (trace)"),
    ]
    fig.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.005),
        ncol=2,
        frameon=False,
        fontsize=9,
    )

    fig.tight_layout(rect=(0, 0, 1, 0.96))

    pdf_path = FIG_OUT / "chapter4_acceptance_and_variance.pdf"
    png_path = FIG_OUT / "chapter4_acceptance_and_variance.png"
    fig.savefig(pdf_path)
    fig.savefig(png_path, dpi=200)
    print(f"wrote {pdf_path}")
    print(f"wrote {png_path}")

    # Console sanity check
    print(f"\n{len(records)} cells (sorted by acceptance rate descending):")
    print(f"{'label':<25s} {'n':>3s} {'accept':>7s} {'mean':>8s} {'CI_half':>8s}")
    for r in records:
        print(f"  {r['label']:<23s} {r['n_traj']:>3d} {r['acceptance']:>7.1%} "
              f"{r['mean']:>+8.2f} {r['ci_half']:>8.2f}")


if __name__ == "__main__":
    main()
