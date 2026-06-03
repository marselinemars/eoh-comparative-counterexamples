"""
thesis/code/chapter6/experiments/different_hash_pairs.py

Analysis F. Restricts the matched-pair L1-vs-L2 analysis to
coordinates where the trace genuinely changed what the model
produced (l1_hash != l2_hash) and reports the same statistics
on that subset, plus an engagement-class cross-tab.

Inputs (already on disk):
  thesis/results/chapter6_primary_batch_gemini/_plots/<strategy>/_paired_records.json
  thesis/results/chapter6_primary_batch_gemini/_verification_analysis.json

Updates in-place:
  thesis/results/chapter6_primary_batch_gemini/_verification_analysis.json
    -> adds key `analysis_F_different_hash`
  thesis/results/chapter6_primary_batch_gemini/_verification_analysis.md
    -> appends "## Analysis F" section

Run:
  python -m thesis.code.chapter6.experiments.different_hash_pairs
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[4]
RES = REPO / "thesis" / "results" / "chapter6_primary_batch_gemini"
PLOTS = RES / "_plots"
JSON_OUT = RES / "_verification_analysis.json"
MD_OUT = RES / "_verification_analysis.md"
STRATEGIES = ("stratified_representative", "worst_plus_best")


def _cliffs_delta(xs: List[float], ys: List[float]) -> float:
    if not xs or not ys:
        return 0.0
    g = l = 0
    for x in xs:
        for y in ys:
            if x > y: g += 1
            elif x < y: l += 1
    return (g - l) / (len(xs) * len(ys))


def _summarize(diffs: List[float]) -> Dict:
    if not diffs:
        return {"n": 0}
    return {
        "n": len(diffs),
        "mean_diff": statistics.mean(diffs),
        "median_diff": statistics.median(diffs),
        "n_l2_better": sum(1 for d in diffs if d > 0),
        "n_l2_worse":  sum(1 for d in diffs if d < 0),
        "n_ties":      sum(1 for d in diffs if d == 0),
    }


def main() -> int:
    verif = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    classification = verif["analysis_E_engagement_classification"][
        "per_record_classification"
    ]

    out: Dict[str, Dict] = {}
    for strat in STRATEGIES:
        pairs = json.loads(
            (PLOTS / strat / "_paired_records.json").read_text(encoding="utf-8")
        )
        same  = [p for p in pairs if p["l1_hash"] == p["l2_hash"]]
        diff  = [p for p in pairs if p["l1_hash"] != p["l2_hash"]]
        same_diffs = [p["diff"] for p in same]
        diff_diffs = [p["diff"] for p in diff]

        # Anomaly check: same_hash diffs should all be 0
        non_zero_same = [p for p in same if abs(p["diff"]) > 1e-9]

        # Engagement-class cross-tab on the different-hash subset
        l1_scores = [p["l1_delta_step"] for p in diff]
        l2_scores = [p["l2_delta_step"] for p in diff]
        cliffs = _cliffs_delta(l2_scores, l1_scores)

        cls_diffs: Dict[str, List[float]] = {"C": [], "M": [], "A": []}
        cls_counts: Dict[str, int] = {"C": 0, "M": 0, "A": 0}
        for p in diff:
            key = f"{strat}@L2_set{p['set_index']:03d}_seed{p['seed_index']:03d}"
            cls = classification.get(key, "A")
            cls_counts[cls] += 1
            cls_diffs[cls].append(p["diff"])

        out[strat] = {
            "n_same_hash": len(same),
            "n_different_hash": len(diff),
            "same_hash_anomalies": [
                {"set": p["set_index"], "seed": p["seed_index"], "diff": p["diff"]}
                for p in non_zero_same
            ],
            "different_hash_summary": {
                **_summarize(diff_diffs),
                "cliffs_delta_l2_vs_l1": cliffs,
            },
            "engagement_class_counts_in_different_hash": cls_counts,
            "engagement_class_pair_summary_in_different_hash": {
                k: _summarize(v) for k, v in cls_diffs.items()
            },
        }

    verif["analysis_F_different_hash"] = out
    JSON_OUT.write_text(json.dumps(verif, indent=2), encoding="utf-8")

    # Append markdown section
    md = ["", "## Analysis F — Different-hash matched-pair subset", ""]
    md.append(
        "Restricts the matched-pair view to coordinates where the trace "
        "actually changed the proposal (`l1_hash != l2_hash`). The "
        "same-hash pairs (where the LLM produced byte-identical code "
        "with and without the trace) contribute Δ = 0 by construction "
        "and dilute the cell-mean view."
    )
    md.append("")
    md.append(
        "| strategy | n_same_hash | n_diff_hash | Cliff's δ (L2 vs L1, diff subset) | "
        "matched-pair median Δ | matched-pair mean Δ | L2 win/loss/tie |"
    )
    md.append("|---|---:|---:|---:|---:|---:|---|")
    for strat in STRATEGIES:
        s = out[strat]
        d = s["different_hash_summary"]
        md.append(
            f"| `{strat}` | {s['n_same_hash']} | {s['n_different_hash']} | "
            f"{d['cliffs_delta_l2_vs_l1']:+.4f} | "
            f"{d['median_diff']:+.3f} | {d['mean_diff']:+.3f} | "
            f"{d['n_l2_better']} / {d['n_l2_worse']} / {d['n_ties']} |"
        )
    md.append("")
    md.append("### Per-class Δ(L2 − L1) on the different-hash subset")
    md.append("")
    md.append("| strategy | C mean (n) | M mean (n) | A mean (n) |")
    md.append("|---|---|---|---|")

    def _fmt(s):
        if s["n"] == 0:
            return "n=0"
        return f"{s['mean_diff']:+.2f} (n={s['n']})"

    for strat in STRATEGIES:
        ps = out[strat]["engagement_class_pair_summary_in_different_hash"]
        md.append(f"| `{strat}` | {_fmt(ps['C'])} | {_fmt(ps['M'])} | {_fmt(ps['A'])} |")
    md.append("")

    anomalies = []
    for strat in STRATEGIES:
        s = out[strat]
        if s["same_hash_anomalies"]:
            anomalies.append(
                f"- `{strat}`: {len(s['same_hash_anomalies'])} same-hash pairs "
                f"have non-zero Δ (should be 0): {s['same_hash_anomalies']}"
            )
        if s["n_same_hash"] > 0.5 * (s["n_same_hash"] + s["n_different_hash"]):
            anomalies.append(
                f"- `{strat}`: same_hash pairs ({s['n_same_hash']}) > "
                f"different_hash ({s['n_different_hash']}), unusual."
            )
    if anomalies:
        md.append("**Anomalies:**")
        md.extend(anomalies)
        md.append("")

    existing = MD_OUT.read_text(encoding="utf-8").rstrip()
    MD_OUT.write_text(existing + "\n" + "\n".join(md) + "\n", encoding="utf-8")

    print("Analysis F written.")
    for strat in STRATEGIES:
        s = out[strat]
        d = s["different_hash_summary"]
        print(
            f"  {strat}: same={s['n_same_hash']}  diff={s['n_different_hash']}  "
            f"cliffs={d['cliffs_delta_l2_vs_l1']:+.4f}  "
            f"median={d['median_diff']:+.3f}  mean={d['mean_diff']:+.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
