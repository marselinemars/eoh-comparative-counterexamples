"""thesis/code/chapter7/figures/figure4_dev_vs_gate_scatter.py

Figure 4: Δ_dev vs Δ_gate scatter across the 53 accepted
validation-step proposals. §7.5 supporting figure. Visualizes
the +0.944 Pearson correlation that defends the
clean_generalization verdict, and surfaces the two negative-Δ_dev
records (CH7-02 and CH7-14) called out in §7.5 prose.

x-axis: Δ_gate (bins). y-axis: Δ_dev (bins). y=x reference line.
Two outlier records (Δ_dev < 0) annotated.

Source: ``thesis/artifacts/chapter7_full_dev_pass.json``.

Usage::

    python -m thesis.code.chapter7.figures.figure4_dev_vs_gate_scatter
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
ART = REPO_ROOT / "thesis" / "artifacts"
SOURCE_PATH = ART / "chapter7_full_dev_pass.json"
OUT_DIR = REPO_ROOT / "thesis" / "writing" / "figures"
OUT_BASENAME = "chapter7_dev_vs_gate_scatter"


def main() -> int:
    d = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    proposals = d["proposals"]
    gates = [p["delta_gate"] for p in proposals]
    devs = [p["delta_dev"] for p in proposals]

    fig, ax = plt.subplots(figsize=(8, 7))
    # Main scatter.
    above_x = [(g, dv) for g, dv in zip(gates, devs) if dv >= 0]
    below_x = [(g, dv) for g, dv in zip(gates, devs) if dv < 0]
    if above_x:
        gx, gy = zip(*above_x)
        ax.scatter(
            gx, gy, s=42, color="#1f77b4", edgecolor="white",
            linewidth=0.7, alpha=0.85, label=f"Δ_dev ≥ 0  (n={len(above_x)})",
        )
    if below_x:
        gx, gy = zip(*below_x)
        ax.scatter(
            gx, gy, s=70, color="#d62728", edgecolor="black",
            linewidth=0.9, label=f"Δ_dev < 0  (n={len(below_x)})",
            zorder=5,
        )

    # y = x reference line spanning both ranges.
    lo = min(min(gates) - 1.0, min(devs) - 1.0)
    hi = max(max(gates) + 1.0, max(devs) + 1.0)
    ax.plot([lo, hi], [lo, hi], color="grey",
            linewidth=0.9, linestyle="--", label="y = x")
    ax.axhline(0, color="black", linewidth=0.5, alpha=0.4)
    ax.axvline(0, color="black", linewidth=0.5, alpha=0.4)

    # Annotate the two negative-Δ_dev outliers.
    for p in proposals:
        if p["delta_dev"] < 0:
            cell = p["cell_id"]
            ti = p["trajectory_index"]
            si = p["step_index"]
            ax.annotate(
                f"{cell} t={ti} s={si}\nΔ_dev={p['delta_dev']:+.2f}",
                xy=(p["delta_gate"], p["delta_dev"]),
                xytext=(12, -22), textcoords="offset points",
                fontsize=8,
                arrowprops={"arrowstyle": "->", "color": "#d62728",
                            "lw": 0.8, "shrinkA": 4, "shrinkB": 4},
                bbox={"boxstyle": "round,pad=0.25",
                      "facecolor": "white",
                      "edgecolor": "#d62728", "alpha": 0.92},
            )

    ax.set_xlabel("Δ_gate (bins; train_gate vs h_eoh)")
    ax.set_ylabel("Δ_dev (bins; dev vs h_eoh)")
    ax.grid(linestyle=":", alpha=0.4)
    ax.legend(loc="lower right", fontsize=9)

    # Pearson + verdict footer.
    pa = d.get("pattern_analysis", {})
    pearson_pt = pa.get("pearson_delta_dev_vs_delta_gate", {}).get("point")
    pearson_ci = pa.get("pearson_delta_dev_vs_delta_gate", {}).get("ci_95")
    verdict = pa.get("verdict", "n/a")
    ax.text(
        0.02, 0.98,
        (
            f"Pearson(Δ_dev, Δ_gate) = {pearson_pt:+.3f}\n"
            f"  95% CI [{pearson_ci[0]:+.3f}, {pearson_ci[1]:+.3f}]\n"
            f"Verdict: {verdict}"
        ),
        transform=ax.transAxes,
        ha="left", va="top", fontsize=9,
        bbox={"facecolor": "#f0f0f0", "edgecolor": "#888888",
              "boxstyle": "round,pad=0.4", "alpha": 0.9},
    )

    fig.suptitle(
        "Figure 4. Δ_dev versus Δ_gate across the 53 accepted "
        "validation-step proposals.\n"
        "Bulk sits tightly along y=x in the positive quadrant; "
        "two records have Δ_dev < 0 (red).",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.92])
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
