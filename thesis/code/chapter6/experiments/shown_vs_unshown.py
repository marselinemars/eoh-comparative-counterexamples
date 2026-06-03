"""
thesis/code/chapter6/experiments/shown_vs_unshown.py

Train_select shown-vs-unshown decomposition analysis on the
chapter-6 primary batch (Option A from the Prompt 39 reframing).

Mirrors §6.3 / verification-Analysis-G structure on a per-instance
decomposition where Δ is decomposed into the 4 train_select
counterexample instances actually shown to the LLM and the 26
train_select instances not shown. Tests whether the chapter's
selection × structure interaction is uniform across the
train_select pool or concentrated on shown vs unshown subsets.

Outputs:
  thesis/results/chapter6_primary_batch_gemini/_shown_vs_unshown_analysis.md
  thesis/results/chapter6_primary_batch_gemini/_shown_vs_unshown_analysis.json

Inputs:
  - 240 primary-batch per-record JSONs in
    thesis/results/chapter6_primary_batch_gemini/
  - score_cache.json (must be filled with 198 unique proposal hashes
    × 30 train_select instances; run shown_vs_unshown_cache_fill
    first to populate)

Bootstrap method: percentile, 10,000 paired resamples, matching
verification Analysis G's protocol. Seed locked.

Run:
  python -m thesis.code.chapter6.experiments.shown_vs_unshown
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from thesis.code.chapter5.analysis import compute_h_eoh_per_instance_bins
from thesis.code.score_cache import ScoreCache
from thesis.code.splits import load_split

REPO = Path(__file__).resolve().parents[4]
RES = REPO / "thesis" / "results" / "chapter6_primary_batch_gemini"
MD_OUT = RES / "_shown_vs_unshown_analysis.md"
JSON_OUT = RES / "_shown_vs_unshown_analysis.json"

CELL_IDS = (
    "stratified_representative@L1",
    "stratified_representative@L2",
    "worst_plus_best@L1",
    "worst_plus_best@L2",
)

CATASTROPHE_T_PRIMARY = -50.0
CATASTROPHE_T_SENSITIVITY = -100.0
N_BOOT = 10_000
SEED = 20_260_502


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _load_records() -> Dict[Tuple[str, int, int], Dict[str, Any]]:
    out: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
    for cell_id in CELL_IDS:
        for p in sorted(RES.glob(f"{cell_id}_set*_seed*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            if (d.get("sanitization") or {}).get("status") != "ok":
                continue
            out[(cell_id, d["set_index"], d["seed_index"])] = d
    return out


def _train_select_qids() -> List[str]:
    split = load_split("train_select")
    return [
        f"thesis_train_select:{inst['instance_id']}"
        for inst in split["instances"]
    ]


def _h_eoh_train_select_bins() -> List[int]:
    """Per-instance bin counts for h_eoh on train_select (cached)."""
    return compute_h_eoh_per_instance_bins("train_select")


def _ce_qids_for_record(rec: Dict[str, Any]) -> List[str]:
    items = rec["counterexample_set"].get("items") or rec[
        "counterexample_set"
    ].get("counterexamples", [])
    return [it["instance_id"] for it in items]


# ---------------------------------------------------------------------------
# Decomposition
# ---------------------------------------------------------------------------


def _decompose(
    rec: Dict[str, Any],
    cache: ScoreCache,
    qids: List[str],
    h_eoh_bins: List[int],
) -> Dict[str, Any]:
    proposal_hash = rec["proposal_hash"]
    qid_to_idx = {q: i for i, q in enumerate(qids)}

    proposal_bins: List[Optional[int]] = [None] * 30
    for i, qid in enumerate(qids):
        entry = cache._entries.get(f"{proposal_hash}|{qid}")
        if entry is None:
            raise RuntimeError(
                f"missing cache entry for proposal {proposal_hash} on {qid}; "
                "run shown_vs_unshown_cache_fill first"
            )
        proposal_bins[i] = int(entry["bins_used"])

    delta_per = [h_eoh_bins[i] - proposal_bins[i] for i in range(30)]

    shown_qids = _ce_qids_for_record(rec)
    shown_indices = sorted({qid_to_idx[q] for q in shown_qids})
    unshown_indices = sorted(set(range(30)) - set(shown_indices))

    delta_shown = float(np.mean([delta_per[i] for i in shown_indices]))
    delta_unshown = float(np.mean([delta_per[i] for i in unshown_indices]))
    delta_full = float(np.mean(delta_per))

    return {
        "proposal_hash": proposal_hash,
        "proposal_bins": proposal_bins,
        "delta_per_instance": delta_per,
        "shown_indices": shown_indices,
        "unshown_indices": unshown_indices,
        "delta_select_shown": delta_shown,
        "delta_select_unshown": delta_unshown,
        "delta_select_full": delta_full,
    }


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------


def _dist_stats(xs: List[float]) -> Dict[str, float]:
    if not xs:
        return {}
    arr = np.array(xs, dtype=float)
    p25, p75 = np.percentile(arr, [25, 75])
    return {
        "n": int(len(arr)),
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "p25": float(p25),
        "p75": float(p75),
        "iqr": float(p75 - p25),
        "min": float(arr.min()),
        "max": float(arr.max()),
    }


def analysis_p(
    decomps: Dict[Tuple[str, int, int], Dict[str, Any]],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"per_cell": {}}
    for cell in CELL_IDS:
        cell_decomps = [
            v for (cid, _, _), v in decomps.items() if cid == cell
        ]
        out["per_cell"][cell] = {
            "delta_select_shown": _dist_stats(
                [d["delta_select_shown"] for d in cell_decomps]
            ),
            "delta_select_unshown": _dist_stats(
                [d["delta_select_unshown"] for d in cell_decomps]
            ),
            "delta_select_full": _dist_stats(
                [d["delta_select_full"] for d in cell_decomps]
            ),
        }
    return out


def _matched_pair_diffs(
    decomps: Dict[Tuple[str, int, int], Dict[str, Any]],
    strategy: str,
    field: str,
) -> List[Dict[str, Any]]:
    coords: Dict[Tuple[int, int], Dict[str, Dict[str, Any]]] = {}
    for (cid, s, seed), d in decomps.items():
        if not cid.startswith(strategy + "@"):
            continue
        level = "L1" if cid.endswith("@L1") else "L2"
        coords.setdefault((s, seed), {})[level] = d
    pairs = []
    for (s, seed), pair in coords.items():
        if "L1" in pair and "L2" in pair:
            pairs.append({
                "set_index": s,
                "seed_index": seed,
                "l1_value": pair["L1"][field],
                "l2_value": pair["L2"][field],
                "diff": pair["L2"][field] - pair["L1"][field],
                "l1_hash": pair["L1"]["proposal_hash"],
                "l2_hash": pair["L2"]["proposal_hash"],
            })
    pairs.sort(key=lambda p: (p["set_index"], p["seed_index"]))
    return pairs


def _summarize_pairs(pairs: List[Dict[str, Any]], eps: float = 1e-9) -> Dict:
    if not pairs:
        return {"n": 0}
    diffs = [p["diff"] for p in pairs]
    arr = np.array(diffs)
    return {
        "n": len(diffs),
        "median": float(np.median(arr)),
        "mean": float(arr.mean()),
        "n_l2_better": sum(1 for d in diffs if d > eps),
        "n_l2_worse": sum(1 for d in diffs if d < -eps),
        "n_ties": sum(1 for d in diffs if -eps <= d <= eps),
    }


def analysis_q(
    decomps: Dict[Tuple[str, int, int], Dict[str, Any]],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"per_strategy": {}}
    for strat in ("stratified_representative", "worst_plus_best"):
        per_field: Dict[str, Any] = {}
        for field in (
            "delta_select_shown",
            "delta_select_unshown",
            "delta_select_full",
        ):
            full = _matched_pair_diffs(decomps, strat, field)
            diff_hash = [p for p in full if p["l1_hash"] != p["l2_hash"]]
            per_field[field] = {
                "full": _summarize_pairs(full),
                "different_hash": _summarize_pairs(diff_hash),
                "n_same_hash": sum(
                    1 for p in full if p["l1_hash"] == p["l2_hash"]
                ),
            }
        out["per_strategy"][strat] = per_field
    return out


def analysis_r(
    decomps: Dict[Tuple[str, int, int], Dict[str, Any]],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"per_cell": {}, "thresholds": {
        "primary": CATASTROPHE_T_PRIMARY,
        "sensitivity": CATASTROPHE_T_SENSITIVITY,
    }}
    for cell in CELL_IDS:
        cell_decomps = [
            v for (cid, _, _), v in decomps.items() if cid == cell
        ]
        n = len(cell_decomps)
        per_field = {}
        for field in (
            "delta_select_shown",
            "delta_select_unshown",
            "delta_select_full",
        ):
            vals = [d[field] for d in cell_decomps]
            n_t50 = sum(1 for v in vals if v < CATASTROPHE_T_PRIMARY)
            n_t100 = sum(1 for v in vals if v < CATASTROPHE_T_SENSITIVITY)
            per_field[field] = {
                "n": n,
                "n_cat_t50": n_t50,
                "rate_t50": n_t50 / n if n else None,
                "n_cat_t100": n_t100,
                "rate_t100": n_t100 / n if n else None,
            }
        out["per_cell"][cell] = per_field
    return out


def _percentile_ci(samples: np.ndarray, alpha: float = 0.05) -> Tuple[float, float]:
    return (
        float(np.percentile(samples, 100 * alpha / 2)),
        float(np.percentile(samples, 100 * (1 - alpha / 2))),
    )


def _excludes_zero(lo: float, hi: float) -> bool:
    return (lo > 0 and hi > 0) or (lo < 0 and hi < 0)


def analysis_s(
    decomps: Dict[Tuple[str, int, int], Dict[str, Any]],
    rng: np.random.Generator,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "method": "percentile bootstrap, 10,000 paired resamples; "
                  "matched-pair within strategy + cross-strategy "
                  "difference of resampled means",
        "n_boot": N_BOOT,
        "seed": SEED,
        "per_strategy_means": {},
        "interaction": {},
    }
    bootstrap_means: Dict[str, Dict[str, np.ndarray]] = {}

    for strat in ("stratified_representative", "worst_plus_best"):
        per_field_means: Dict[str, np.ndarray] = {}
        per_field_meta: Dict[str, Dict[str, Any]] = {}
        for field in (
            "delta_select_shown",
            "delta_select_unshown",
            "delta_select_full",
        ):
            full_pairs = _matched_pair_diffs(decomps, strat, field)
            diff_pairs = [p for p in full_pairs if p["l1_hash"] != p["l2_hash"]]

            full_diffs = np.array([p["diff"] for p in full_pairs], dtype=float)
            diff_diffs = np.array([p["diff"] for p in diff_pairs], dtype=float)

            n_full = len(full_diffs)
            full_idx = rng.integers(0, n_full, size=(N_BOOT, n_full))
            full_boot_means = full_diffs[full_idx].mean(axis=1)
            per_field_means[f"{field}_full"] = full_boot_means

            n_diff = len(diff_diffs)
            if n_diff > 0:
                diff_idx = rng.integers(0, n_diff, size=(N_BOOT, n_diff))
                diff_boot_means = diff_diffs[diff_idx].mean(axis=1)
                per_field_means[f"{field}_diffhash"] = diff_boot_means
            else:
                per_field_means[f"{field}_diffhash"] = np.zeros(N_BOOT)

            per_field_meta[field] = {
                "n_full": n_full,
                "n_diff_hash": n_diff,
                "full_mean_point": float(full_diffs.mean()) if n_full else None,
                "diff_mean_point": float(diff_diffs.mean()) if n_diff else None,
            }

        bootstrap_means[strat] = per_field_means
        out["per_strategy_means"][strat] = per_field_meta

    # Cross-strategy interaction CIs (strat - wpb)
    for field in (
        "delta_select_shown",
        "delta_select_unshown",
        "delta_select_full",
    ):
        for subset in ("full", "diffhash"):
            key = f"{field}_{subset}"
            samples = (
                bootstrap_means["stratified_representative"][key]
                - bootstrap_means["worst_plus_best"][key]
            )
            ci = _percentile_ci(samples)
            point = float(
                bootstrap_means["stratified_representative"][key].mean()
                - bootstrap_means["worst_plus_best"][key].mean()
            )
            # More stable point estimate: difference of full-data means
            strat_pairs = _matched_pair_diffs(
                decomps, "stratified_representative", field
            )
            wpb_pairs = _matched_pair_diffs(decomps, "worst_plus_best", field)
            if subset == "diffhash":
                strat_pairs = [
                    p for p in strat_pairs if p["l1_hash"] != p["l2_hash"]
                ]
                wpb_pairs = [
                    p for p in wpb_pairs if p["l1_hash"] != p["l2_hash"]
                ]
            point_data = (
                float(np.mean([p["diff"] for p in strat_pairs]))
                - float(np.mean([p["diff"] for p in wpb_pairs]))
            )
            out["interaction"][f"{field}_{subset}"] = {
                "point": point_data,
                "ci": ci,
                "ci_excludes_zero": _excludes_zero(*ci),
            }
    return out


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _md_dist_table(p: Dict[str, Any], field_label: str) -> List[str]:
    rows = [f"| cell | n | mean | median | p25 | p75 | IQR | min | max |",
            f"|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for cell in CELL_IDS:
        s = p["per_cell"][cell][field_label]
        rows.append(
            f"| `{cell}` | {s['n']} | "
            f"{s['mean']:+.2f} | {s['median']:+.2f} | "
            f"{s['p25']:+.2f} | {s['p75']:+.2f} | {s['iqr']:.2f} | "
            f"{s['min']:+.2f} | {s['max']:+.2f} |"
        )
    return rows


def render_md(p: Dict, q: Dict, r: Dict, s: Dict) -> str:
    lines: List[str] = []
    lines.append("# Chapter 6 — train_select shown-vs-unshown decomposition\n")
    lines.append(
        "Diagnostic re-analysis testing whether the chapter's "
        "selection × structure interaction is concentrated on the "
        "4 train_select instances shown to the LLM as counterexamples, "
        "concentrated on the 26 unshown train_select instances, or "
        "uniform across the pool. Pure post-hoc analysis on existing "
        "primary-batch records plus a cache-filled 198-proposal × "
        "30-train_select-instance scoring grid. No new LLM calls.\n"
    )
    lines.append("Sources:\n")
    lines.append("- 240 primary-batch per-record JSONs (commit `0b05f72`-aligned).")
    lines.append("- `score_cache.json` after the cache-fill commit (5,940 (proposal_hash, train_select_qid) pairs covered).")
    lines.append("- `train_select` split (30 instances).")
    lines.append("- `h_eoh` per-instance bins on `train_select` via `compute_h_eoh_per_instance_bins`.")
    lines.append("")

    # Methodological note
    lines.append("## Methodological note\n")
    lines.append(
        "Δ_select_shown is a 4-instance mean; Δ_select_unshown is a "
        "26-instance mean; Δ_select_full is a 30-instance mean. "
        "Catastrophe threshold (Δ < −50) is applied without retuning "
        "to all three decompositions, but its qualitative meaning shifts "
        "with the underlying instance count. A 4-instance Δ < −50 means "
        "a per-instance bin gap averaging > 50 on each of 4 instances; "
        "a 26-instance Δ < −50 averages over 26 instances. Read "
        "Δ_shown's catastrophe rate accordingly: a single catastrophic "
        "instance can drive Δ_shown below the threshold."
    )
    lines.append("")
    lines.append(
        "Sanity check: per-record `(4 * Δ_shown + 26 * Δ_unshown) / 30` "
        "= `Δ_select_full` to within float precision (verified at script "
        "build time)."
    )
    lines.append("")

    # P
    lines.append("## Analysis P — Cell-level distributions on the train_select decomposition\n")
    lines.append("### Δ_select_shown (mean over 4 shown counterexample instances per record)\n")
    lines.extend(_md_dist_table(p, "delta_select_shown"))
    lines.append("")
    lines.append("### Δ_select_unshown (mean over 26 train_select instances NOT shown)\n")
    lines.extend(_md_dist_table(p, "delta_select_unshown"))
    lines.append("")
    lines.append("### Δ_select_full (mean over all 30 train_select instances)\n")
    lines.extend(_md_dist_table(p, "delta_select_full"))
    lines.append("")

    # Q
    lines.append("## Analysis Q — Matched-pair Δ on the train_select decomposition\n")
    lines.append("Per-strategy median, mean, win/loss/tie for matched pairs at "
                 "the 60 (set_index, seed_index) coordinates. Different-hash "
                 "subset excludes coordinates where the trace did not change "
                 "the proposal (per §6.3.3 / Analysis F convention).\n")
    for strat in ("stratified_representative", "worst_plus_best"):
        lines.append(f"### `{strat}`\n")
        for field in ("delta_select_shown",
                      "delta_select_unshown",
                      "delta_select_full"):
            full = q["per_strategy"][strat][field]["full"]
            dh = q["per_strategy"][strat][field]["different_hash"]
            n_same = q["per_strategy"][strat][field]["n_same_hash"]
            lines.append(
                f"**{field}** (n_same_hash = {n_same})\n"
            )
            lines.append("| subset | n | median | mean | L2 better / worse / ties |")
            lines.append("|---|---:|---:|---:|---|")
            for label, summ in (("full", full), ("different_hash", dh)):
                if summ.get("n", 0) == 0:
                    lines.append(f"| {label} | 0 | — | — | — |")
                    continue
                lines.append(
                    f"| {label} | {summ['n']} | "
                    f"{summ['median']:+.3f} | {summ['mean']:+.3f} | "
                    f"{summ['n_l2_better']} / {summ['n_l2_worse']} / "
                    f"{summ['n_ties']} |"
                )
            lines.append("")

    # R
    lines.append("## Analysis R — Catastrophe-rate on the train_select decomposition\n")
    lines.append(
        f"Catastrophe = Δ < {CATASTROPHE_T_PRIMARY}. Sensitivity = "
        f"{CATASTROPHE_T_SENSITIVITY}. Threshold not retuned across "
        "the three decompositions; see methodological note above."
    )
    lines.append("")
    for field in ("delta_select_shown",
                  "delta_select_unshown",
                  "delta_select_full"):
        lines.append(f"### {field}\n")
        lines.append("| cell | n | n_cat (t=−50) | rate (t=−50) | n_cat (t=−100) | rate (t=−100) |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for cell in CELL_IDS:
            x = r["per_cell"][cell][field]
            lines.append(
                f"| `{cell}` | {x['n']} | {x['n_cat_t50']} | "
                f"{(x['rate_t50'] or 0)*100:.1f}% | {x['n_cat_t100']} | "
                f"{(x['rate_t100'] or 0)*100:.1f}% |"
            )
        lines.append("")

    # S
    lines.append("## Analysis S — Cross-strategy bootstrap CIs on the decomposition\n")
    lines.append("Method: percentile bootstrap, 10,000 paired resamples within "
                 "each strategy, then differenced. Matches verification Analysis "
                 "G's protocol.\n")
    lines.append("| statistic (stratified − wpb) | point | 95% CI | excludes 0? |")
    lines.append("|---|---:|---|---|")
    for field in ("delta_select_shown",
                  "delta_select_unshown",
                  "delta_select_full"):
        for subset in ("full", "diffhash"):
            key = f"{field}_{subset}"
            d = s["interaction"][key]
            lo, hi = d["ci"]
            excl = "yes" if d["ci_excludes_zero"] else "no"
            lines.append(
                f"| {field} ({subset}) | {d['point']:+.3f} | "
                f"[{lo:+.3f}, {hi:+.3f}] | {excl} |"
            )
    lines.append("")
    lines.append("Sanity-check comparison: the chapter's existing Δ_step "
                 "interaction CI is +76.97 [+8.94, +155.04] (excludes zero; "
                 "verification Analysis G). The Δ_select_full row above is "
                 "the train_select analog and should sit in the same ballpark.")
    lines.append("")

    # Interpretation
    lines.append("## Interpretation\n")
    f_full = s["interaction"]["delta_select_full_full"]
    f_shown = s["interaction"]["delta_select_shown_full"]
    f_unshown = s["interaction"]["delta_select_unshown_full"]
    lines.append(
        f"Cross-strategy interaction CIs at this decomposition:\n"
        f"- **Δ_select_shown (full set):** {f_shown['point']:+.3f} "
        f"[{f_shown['ci'][0]:+.3f}, {f_shown['ci'][1]:+.3f}], "
        f"excludes 0 = {f_shown['ci_excludes_zero']}.\n"
        f"- **Δ_select_unshown (full set):** {f_unshown['point']:+.3f} "
        f"[{f_unshown['ci'][0]:+.3f}, {f_unshown['ci'][1]:+.3f}], "
        f"excludes 0 = {f_unshown['ci_excludes_zero']}.\n"
        f"- **Δ_select_full (sanity check):** {f_full['point']:+.3f} "
        f"[{f_full['ci'][0]:+.3f}, {f_full['ci'][1]:+.3f}], "
        f"excludes 0 = {f_full['ci_excludes_zero']}.\n"
    )
    lines.append("")
    # Determine finding type
    shown_excl = f_shown["ci_excludes_zero"]
    unshown_excl = f_unshown["ci_excludes_zero"]
    if shown_excl and unshown_excl:
        finding = "uniform"
        verdict = (
            "**Finding type 1 (uniform).** The cross-strategy interaction CI "
            "excludes zero on BOTH the 4-shown and 26-unshown decompositions. "
            "The selection × structure catastrophe-asymmetry is not concentrated "
            "on the LLM's prompt-shown counterexamples; it is a property of "
            "the proposed scoring functions' general behavior across the "
            "train_select pool. §6.6.1's reading that under worst+best evidence "
            "the trace 'frames per-decision detail as a record of failure modes "
            "the LLM is being asked to repair' — interpreted as the LLM "
            "hyper-fitting the 4 shown instances — gets weakened by this finding. "
            "The interaction claim itself is unaffected: it shows up at the same "
            "magnitude on both decompositions."
        )
    elif unshown_excl and not shown_excl:
        finding = "concentrated_on_unshown"
        verdict = (
            "**Finding type 2 (concentrated on unshown).** The cross-strategy "
            "interaction CI excludes zero on the 26-unshown decomposition but "
            "includes zero on the 4-shown decomposition. Proposals look "
            "comparable on the counterexamples actually shown to the LLM but "
            "differ on the broader train_select pool. §6.6.1's overfitting "
            "reading is directly supported."
        )
    elif shown_excl and not unshown_excl:
        finding = "concentrated_on_shown"
        verdict = (
            "**Finding type 3 (concentrated on shown).** The cross-strategy "
            "interaction CI excludes zero on the 4-shown decomposition but "
            "not on the 26-unshown decomposition. This is unexpected — proposals "
            "differ on the counterexamples actually shown but not on the broader "
            "pool. §6.6.1's framing would need revisiting; one possibility is "
            "that the trace's effect is transient at the decision level even "
            "on the instances it operates over directly."
        )
    else:
        finding = "ambiguous"
        verdict = (
            "**Ambiguous.** Neither cross-strategy interaction CI excludes "
            "zero on either decomposition at this n. The decomposition cannot "
            "directly test §6.6.1's hyper-fitting interpretation from this "
            "analysis alone. The Δ_select_full sanity-check interaction value "
            f"({f_full['point']:+.3f}, [{f_full['ci'][0]:+.3f}, {f_full['ci'][1]:+.3f}]) "
            "should be compared to the existing Δ_step interaction CI to "
            "confirm that train_select and train_step show similar interaction "
            "shapes; if so, the chapter's primary claim survives unaffected, "
            "and the per-instance overfitting question remains open at this n."
        )
    lines.append(verdict)
    lines.append("")
    lines.append(
        "Hedging note: n = 60 matched pairs per strategy is the same "
        "sample size that produces wide CIs in §6.3.2 / §6.3.3. The "
        "decomposition cuts each per-proposal Δ into a 4-instance mean "
        "(noisier) and a 26-instance mean (comparable to Δ_step). "
        "Bootstrap CIs on the shown decomposition will be wider than on "
        "the unshown decomposition or on Δ_step itself."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print("Loading records, splits, h_eoh bins, and cache...")
    records = _load_records()
    qids = _train_select_qids()
    h_eoh_bins = _h_eoh_train_select_bins()
    cache = ScoreCache()
    print(f"  {len(records)} sanitize-ok records; {len(qids)} train_select instances")
    print(f"  cache entries: {len(cache._entries)}")

    print("Decomposing per record...")
    decomps: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
    sanity_failures = []
    for coord, rec in records.items():
        d = _decompose(rec, cache, qids, h_eoh_bins)
        # Sanity: (4 * shown + 26 * unshown) / 30 == full
        n_s = len(d["shown_indices"])
        n_u = len(d["unshown_indices"])
        recomputed = (
            n_s * d["delta_select_shown"]
            + n_u * d["delta_select_unshown"]
        ) / 30
        if abs(recomputed - d["delta_select_full"]) > 1e-6:
            sanity_failures.append((coord, recomputed, d["delta_select_full"]))
        decomps[coord] = d
    if sanity_failures:
        print(f"  SANITY-CHECK FAILURES: {len(sanity_failures)}")
        for coord, recomputed, full in sanity_failures[:5]:
            print(f"    {coord}: recomputed {recomputed} vs full {full}")
        return 2
    print("  sanity check passed on all records")

    print("Analysis P (cell-level distributions)...")
    p = analysis_p(decomps)
    print("Analysis Q (matched-pair Δ)...")
    q = analysis_q(decomps)
    print("Analysis R (catastrophe rates)...")
    r = analysis_r(decomps)
    print("Analysis S (cross-strategy bootstrap CIs)...")
    rng = np.random.default_rng(SEED)
    s = analysis_s(decomps, rng)

    print("Rendering markdown + JSON...")
    md = render_md(p, q, r, s)
    MD_OUT.write_text(md, encoding="utf-8")
    JSON_OUT.write_text(json.dumps({
        "metadata": {
            "primary_batch_records": len(records),
            "train_select_instances": len(qids),
            "n_boot": N_BOOT,
            "seed": SEED,
        },
        "analysis_P_distributions": p,
        "analysis_Q_matched_pair": q,
        "analysis_R_catastrophe_rates": r,
        "analysis_S_bootstrap_cis": s,
    }, indent=2), encoding="utf-8")
    print(f"\nWrote {MD_OUT}")
    print(f"Wrote {JSON_OUT}")

    # Headline echo
    print()
    print("=== Cross-strategy interaction CIs ===")
    for field in ("delta_select_shown",
                  "delta_select_unshown",
                  "delta_select_full"):
        for subset in ("full", "diffhash"):
            d = s["interaction"][f"{field}_{subset}"]
            lo, hi = d["ci"]
            excl = "EXCL" if d["ci_excludes_zero"] else "incl"
            print(f"  {field:<22} ({subset:<8}): "
                  f"{d['point']:+.3f} [{lo:+.3f}, {hi:+.3f}] {excl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
