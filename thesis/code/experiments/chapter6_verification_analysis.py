"""
thesis/code/experiments/chapter6_verification_analysis.py

Five verification analyses on the full 240/240 chapter-6 batch.
Pure post-hoc — no new LLM calls, no production-code modifications.

Outputs:
  thesis/results/chapter6_primary_batch_gemini/_verification_analysis.md
  thesis/results/chapter6_primary_batch_gemini/_verification_analysis.json

Sections:
  A. The −1255 outliers (worst_plus_best@L2)
  B. L1 catastrophe concentration (stratified + wpb)
  C. Argmax-equivalence rate verification (strict + near)
  D. Modal-proposal analysis (hash repetition across 240)
  E. Refined trace-engagement classification (Cited/Mentioned/Absent)

Run:
  python -m thesis.code.experiments.chapter6_verification_analysis
"""
from __future__ import annotations

import collections
import difflib
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[3]
RESULTS_DIR = REPO / "thesis" / "results" / "chapter6_primary_batch_gemini"
MD_OUT = RESULTS_DIR / "_verification_analysis.md"
JSON_OUT = RESULTS_DIR / "_verification_analysis.json"

CELL_IDS = (
    "stratified_representative@L1",
    "stratified_representative@L2",
    "worst_plus_best@L1",
    "worst_plus_best@L2",
)


def _load_all_records() -> Dict[Tuple[str, int, int], dict]:
    """coord -> record dict, where coord = (cell_id, set_index, seed_index)."""
    out: Dict[Tuple[str, int, int], dict] = {}
    for cell_id in CELL_IDS:
        for p in sorted(RESULTS_DIR.glob(f"{cell_id}_set*_seed*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            if (d.get("sanitization") or {}).get("status") != "ok":
                # Verification analyses operate on OK records only;
                # non-OK records are surfaced separately at the top.
                continue
            out[(cell_id, d["set_index"], d["seed_index"])] = d
    return out


def _records_in_cell(records: Dict, cell_id: str) -> List[dict]:
    return [r for (cid, _, _), r in records.items() if cid == cell_id]


# ---------------------------------------------------------------------------
# Analysis A — the −1255 outliers
# ---------------------------------------------------------------------------


def analysis_a(records: Dict) -> Dict[str, Any]:
    targets = [
        ("worst_plus_best@L2", 0, 24),
        ("worst_plus_best@L2", 0, 31),
    ]
    pair = []
    for coord in targets:
        r = records.get(coord)
        if r is None:
            raise RuntimeError(f"Record missing for {coord}")
        pair.append(r)

    a, b = pair[0], pair[1]
    src_a = a["sanitization"]["cleaned_code"]
    src_b = b["sanitization"]["cleaned_code"]
    bins_a = a["scoring"]["per_instance_bins_proposal_train_step"]
    bins_b = b["scoring"]["per_instance_bins_proposal_train_step"]
    h_eoh_step_mean = a["scoring"]["mean_bins_h_eoh_train_step"]

    # 1) Hash-level
    norm_a = "".join(src_a.split())
    norm_b = "".join(src_b.split())
    if src_a == src_b:
        diff_kind = "byte_identical"
    elif norm_a == norm_b:
        diff_kind = "whitespace_only"
    else:
        diff_kind = "syntactically_different"

    diff_text = "\n".join(
        difflib.unified_diff(
            src_a.splitlines(), src_b.splitlines(),
            fromfile=f"set000_seed024 ({a['proposal_hash']})",
            tofile=f"set000_seed031 ({b['proposal_hash']})",
            lineterm="",
        )
    )

    # 2) Behavior-level
    bins_match = bins_a == bins_b
    elementwise_max_diff = max(
        abs(int(x) - int(y)) for x, y in zip(bins_a, bins_b)
    ) if len(bins_a) == len(bins_b) else None

    # 3) Failure mechanism
    # Identify catastrophic instances on proposal-A (drive of mean).
    # h_eoh per-instance not stored on records; compute once.
    from thesis.code.chapter5.analysis import compute_h_eoh_per_instance_bins
    h_eoh_step = compute_h_eoh_per_instance_bins("train_step")
    per_instance_diff_a = [
        int(p) - int(h) for p, h in zip(bins_a, h_eoh_step)
    ]
    sorted_indices = sorted(
        range(len(per_instance_diff_a)),
        key=lambda i: per_instance_diff_a[i],
        reverse=True,
    )
    top_drivers = [
        {
            "instance_idx": i,
            "proposal_bins": int(bins_a[i]),
            "h_eoh_bins": int(h_eoh_step[i]),
            "delta": per_instance_diff_a[i],
        }
        for i in sorted_indices[:8]
    ]

    # 4) Reasoning
    reason_a = (a["sanitization"].get("reasoning") or "").strip()
    reason_b = (b["sanitization"].get("reasoning") or "").strip()

    return {
        "diff_kind": diff_kind,
        "hash_a": a["proposal_hash"],
        "hash_b": b["proposal_hash"],
        "delta_step_a": a["scoring"]["delta_step"],
        "delta_step_b": b["scoring"]["delta_step"],
        "per_instance_bins_a": [int(x) for x in bins_a],
        "per_instance_bins_b": [int(x) for x in bins_b],
        "per_instance_bins_match": bins_match,
        "elementwise_max_diff": elementwise_max_diff,
        "h_eoh_step_mean": h_eoh_step_mean,
        "top_failure_drivers_for_a": top_drivers,
        "unified_diff": diff_text,
        "src_a": src_a,
        "src_b": src_b,
        "reasoning_a": reason_a,
        "reasoning_b": reason_b,
    }


# ---------------------------------------------------------------------------
# Analysis B — L1 catastrophe concentration
# ---------------------------------------------------------------------------


def analysis_b(records: Dict) -> Dict[str, Any]:
    out: Dict[str, Any] = {"stratified_representative": {}, "worst_plus_best": {}}

    # Stratified L1
    strat = [r for r in _records_in_cell(records, "stratified_representative@L1")
             if r["scoring"]["delta_step"] < -100]
    by_set: Dict[int, List[dict]] = collections.defaultdict(list)
    for r in strat:
        by_set[r["set_index"]].append(r)

    set_table = []
    for s, recs in sorted(by_set.items()):
        items = recs[0]["counterexample_set"]["items"]
        # All 3 seeds in a set share counterexamples (same set_seed); list once
        instance_ids = [it["instance_id"] for it in items]
        gaps = [it.get("gap") for it in items]
        hashes = [r["proposal_hash"] for r in recs]
        deltas = [r["scoring"]["delta_step"] for r in recs]
        set_table.append({
            "set_index": s,
            "n_catastrophes": len(recs),
            "proposal_hashes": hashes,
            "delta_steps": deltas,
            "instance_ids": instance_ids,
            "gaps": gaps,
        })
    out["stratified_representative"] = {
        "n_catastrophes_total": len(strat),
        "n_sets_with_catastrophes": len(by_set),
        "n_sets_with_2plus": sum(1 for v in by_set.values() if len(v) >= 2),
        "per_set": set_table,
    }

    # All sets vs catastrophe-prone sets — gap-distribution comparison
    all_strat = _records_in_cell(records, "stratified_representative@L1")
    set_to_gaps = {}
    for r in all_strat:
        s = r["set_index"]
        if s not in set_to_gaps:
            set_to_gaps[s] = [it.get("gap") for it in r["counterexample_set"]["items"]]
    catastrophe_sets = set(by_set.keys())
    cat_gaps = [g for s, gs in set_to_gaps.items() if s in catastrophe_sets for g in gs if g is not None]
    safe_gaps = [g for s, gs in set_to_gaps.items() if s not in catastrophe_sets for g in gs if g is not None]
    out["stratified_representative"]["gap_distribution"] = {
        "catastrophe_sets_n_gaps": len(cat_gaps),
        "catastrophe_sets_mean_gap": statistics.mean(cat_gaps) if cat_gaps else None,
        "catastrophe_sets_median_gap": statistics.median(cat_gaps) if cat_gaps else None,
        "safe_sets_n_gaps": len(safe_gaps),
        "safe_sets_mean_gap": statistics.mean(safe_gaps) if safe_gaps else None,
        "safe_sets_median_gap": statistics.median(safe_gaps) if safe_gaps else None,
    }

    # WPB L1
    wpb = [r for r in _records_in_cell(records, "worst_plus_best@L1")
           if r["scoring"]["delta_step"] < -100]
    hash_counts = collections.Counter(r["proposal_hash"] for r in wpb)
    out["worst_plus_best"] = {
        "n_catastrophes": len(wpb),
        "n_distinct_hashes": len(hash_counts),
        "hash_count_top": hash_counts.most_common(10),
        "delta_steps_summary": {
            "min": min((r["scoring"]["delta_step"] for r in wpb), default=None),
            "max": max((r["scoring"]["delta_step"] for r in wpb), default=None),
            "mean": (statistics.mean([r["scoring"]["delta_step"] for r in wpb])
                     if wpb else None),
        },
    }
    return out


# ---------------------------------------------------------------------------
# Analysis C — argmax-equivalence
# ---------------------------------------------------------------------------


def analysis_c(records: Dict) -> Dict[str, Any]:
    from thesis.code.chapter5.analysis import (
        compute_h_eoh_per_instance_bins,
        is_argmax_equivalent_to_h_eoh,
    )
    h_eoh_step = compute_h_eoh_per_instance_bins("train_step")

    summary: Dict[str, Dict[str, Any]] = {}
    strict_examples: List[dict] = []
    near_examples: List[dict] = []
    for cell_id in CELL_IDS:
        recs = _records_in_cell(records, cell_id)
        n = len(recs)
        n_strict = 0
        n_near = 0
        for r in recs:
            bins = r["scoring"]["per_instance_bins_proposal_train_step"]
            if is_argmax_equivalent_to_h_eoh(bins, h_eoh_step):
                n_strict += 1
                strict_examples.append({
                    "cell_id": cell_id,
                    "set_index": r["set_index"],
                    "seed_index": r["seed_index"],
                    "proposal_hash": r["proposal_hash"],
                })
            else:
                max_diff = max(abs(int(a) - int(b)) for a, b in zip(bins, h_eoh_step))
                if max_diff <= 1:
                    n_near += 1
                    near_examples.append({
                        "cell_id": cell_id,
                        "set_index": r["set_index"],
                        "seed_index": r["seed_index"],
                        "proposal_hash": r["proposal_hash"],
                        "max_elementwise_diff": int(max_diff),
                    })
        summary[cell_id] = {
            "n_records": n,
            "n_strict_argmax_equivalent": n_strict,
            "rate_strict": (n_strict / n) if n else None,
            "n_near_argmax_equivalent": n_near,
            "rate_near_or_strict": ((n_strict + n_near) / n) if n else None,
        }

    return {
        "per_cell": summary,
        "strict_equivalent_examples": strict_examples,
        "near_equivalent_examples": near_examples,
        "h_eoh_step_mean": statistics.mean(h_eoh_step),
        "definition_strict": "per_instance_bins_proposal_train_step element-wise == per_instance_bins_h_eoh_train_step",
        "definition_near": "max_i |proposal[i] - h_eoh[i]| <= 1 over the 30 train_step instances",
    }


# ---------------------------------------------------------------------------
# Analysis D — modal proposals
# ---------------------------------------------------------------------------


def analysis_d(records: Dict) -> Dict[str, Any]:
    hash_to_records: Dict[str, List[dict]] = collections.defaultdict(list)
    for (cid, s, seed), r in records.items():
        hash_to_records[r["proposal_hash"]].append({
            "cell_id": cid,
            "set_index": s,
            "seed_index": seed,
            "delta_step": r["scoring"]["delta_step"],
            "src": r["sanitization"]["cleaned_code"],
        })
    counts = sorted(hash_to_records.items(), key=lambda kv: -len(kv[1]))
    top10 = []
    cross_l1_l2: List[dict] = []
    for h, recs in counts[:10]:
        if len(recs) < 3:
            break
        cells = sorted({r["cell_id"] for r in recs})
        deltas = [r["delta_step"] for r in recs]
        delta_min, delta_max = min(deltas), max(deltas)
        # Cross L1/L2 within same strategy
        strategies_with_l1 = {c.split("@")[0] for c in cells if c.endswith("@L1")}
        strategies_with_l2 = {c.split("@")[0] for c in cells if c.endswith("@L2")}
        cross_levels = sorted(strategies_with_l1 & strategies_with_l2)
        entry = {
            "hash": h,
            "n_occurrences": len(recs),
            "cells": cells,
            "delta_step": deltas[0] if delta_min == delta_max else None,
            "delta_step_min": delta_min,
            "delta_step_max": delta_max,
            "cross_level_strategies": cross_levels,
            "src_preview": "\n".join(recs[0]["src"].splitlines()[:30]),
            "all_occurrences": [
                {"cell_id": r["cell_id"], "set": r["set_index"], "seed": r["seed_index"]}
                for r in recs
            ],
        }
        top10.append(entry)
        if cross_levels:
            cross_l1_l2.append(entry)

    # Per-cell unique-vs-modal breakdown
    per_cell_uniqueness: Dict[str, Dict[str, Any]] = {}
    for cell_id in CELL_IDS:
        recs = _records_in_cell(records, cell_id)
        hashes = [r["proposal_hash"] for r in recs]
        c = collections.Counter(hashes)
        n = len(recs)
        n_unique = sum(1 for v in c.values() if v == 1)
        n_distinct = len(c)
        biggest_modal = max(c.values()) if c else 0
        per_cell_uniqueness[cell_id] = {
            "n_records": n,
            "n_distinct_hashes": n_distinct,
            "n_unique_singletons": n_unique,
            "max_modal_size": biggest_modal,
            "fraction_records_in_modal_clusters": (
                (n - n_unique) / n if n else None
            ),
        }

    return {
        "top10_modal": top10,
        "cross_level_within_strategy": cross_l1_l2,
        "per_cell_uniqueness": per_cell_uniqueness,
    }


# ---------------------------------------------------------------------------
# Analysis E — refined trace-engagement classification
# ---------------------------------------------------------------------------


_RE_IDX_CITATION = re.compile(r"\bidx\s*=\s*\d+", re.I)
_RE_INST_IDX = re.compile(r"instance_\d+\s*,?\s*idx\s*=\s*\d+", re.I)
_TRACE_VOCAB = (
    "open_bins", "open bins", "runner_up", "runner-up", "runner up",
    "margin", "decision trace", "decision_trace",
)


def _classify_l2(text: str) -> str:
    t = text or ""
    if _RE_IDX_CITATION.search(t) or _RE_INST_IDX.search(t):
        return "C"
    low = t.lower()
    if any(v in low for v in _TRACE_VOCAB):
        return "M"
    return "A"


def analysis_e(records: Dict, modal_hashes: List[str]) -> Dict[str, Any]:
    classification: Dict[str, str] = {}
    per_record: List[dict] = []
    cells: Dict[str, Dict[str, Any]] = {}
    for cell_id in ("stratified_representative@L2", "worst_plus_best@L2"):
        recs = _records_in_cell(records, cell_id)
        cls_counts: collections.Counter = collections.Counter()
        cls_deltas: Dict[str, List[float]] = {"C": [], "M": [], "A": []}
        for r in recs:
            text = (r["sanitization"].get("reasoning") or "")
            cls = _classify_l2(text)
            key = f"{cell_id}_set{r['set_index']:03d}_seed{r['seed_index']:03d}"
            classification[key] = cls
            cls_counts[cls] += 1
            cls_deltas[cls].append(r["scoring"]["delta_step"])
            per_record.append({
                "cell_id": cell_id,
                "set_index": r["set_index"],
                "seed_index": r["seed_index"],
                "class": cls,
                "delta_step": r["scoring"]["delta_step"],
                "in_modal_cluster": r["proposal_hash"] in set(modal_hashes),
            })

        per_class_means = {
            k: (statistics.mean(v) if v else None) for k, v in cls_deltas.items()
        }

        # Matched-pair Δ(L2 - L1) by L2 class
        l1_cell = cell_id.replace("@L2", "@L1")
        l1_lookup = {(r["set_index"], r["seed_index"]):
                     r["scoring"]["delta_step"]
                     for r in _records_in_cell(records, l1_cell)}
        per_class_pair_diffs: Dict[str, List[float]] = {"C": [], "M": [], "A": []}
        for r in recs:
            l1d = l1_lookup.get((r["set_index"], r["seed_index"]))
            if l1d is None:
                continue
            text = (r["sanitization"].get("reasoning") or "")
            cls = _classify_l2(text)
            per_class_pair_diffs[cls].append(r["scoring"]["delta_step"] - l1d)

        per_class_pair_summary = {}
        for k, vs in per_class_pair_diffs.items():
            if vs:
                per_class_pair_summary[k] = {
                    "n_pairs": len(vs),
                    "mean_diff": statistics.mean(vs),
                    "median_diff": statistics.median(vs),
                }
            else:
                per_class_pair_summary[k] = {
                    "n_pairs": 0, "mean_diff": None, "median_diff": None,
                }

        # In-modal-cluster overlap by class
        modal_set = set(modal_hashes)
        in_modal_by_class: Dict[str, int] = {"C": 0, "M": 0, "A": 0}
        for r in recs:
            cls = _classify_l2(r["sanitization"].get("reasoning") or "")
            if r["proposal_hash"] in modal_set:
                in_modal_by_class[cls] += 1

        cells[cell_id] = {
            "n_records": len(recs),
            "class_counts": dict(cls_counts),
            "class_share": {k: cls_counts[k] / len(recs)
                            for k in ("C", "M", "A")} if recs else {},
            "mean_delta_step_by_class": per_class_means,
            "matched_pair_diff_by_class": per_class_pair_summary,
            "in_modal_cluster_by_class": in_modal_by_class,
        }

    return {
        "definitions": {
            "C": "reasoning text contains explicit decision-index citation (idx=N or instance_X, idx=N)",
            "M": "trace-vocabulary present (open_bins, runner_up, margin, decision trace) but no idx=N citation",
            "A": "no trace-vocabulary at all",
        },
        "per_record_classification": classification,
        "per_record_table": per_record,
        "per_cell": cells,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _md_for_analysis_a(a: Dict[str, Any]) -> List[str]:
    out = ["## Analysis A — The −1255 outliers (worst_plus_best@L2)\n"]
    out.append(f"- Records compared: `set000_seed024` (hash `{a['hash_a']}`) "
               f"and `set000_seed031` (hash `{a['hash_b']}`).")
    out.append(f"- delta_step_a = {a['delta_step_a']:.3f}, "
               f"delta_step_b = {a['delta_step_b']:.3f}")
    out.append(f"- Source-diff kind: **{a['diff_kind']}**.")
    out.append(f"- Per-instance bin counts identical? **{a['per_instance_bins_match']}** "
               f"(max element-wise diff = {a['elementwise_max_diff']}).\n")
    out.append("### Top failure drivers for proposal A (set000_seed024)\n")
    out.append(f"h_eoh train_step mean = {a['h_eoh_step_mean']:.2f}.")
    out.append("")
    out.append("| inst_idx | proposal_bins | h_eoh_bins | delta |")
    out.append("|---:|---:|---:|---:|")
    for d in a["top_failure_drivers_for_a"]:
        out.append(f"| {d['instance_idx']} | {d['proposal_bins']} | {d['h_eoh_bins']} | "
                   f"{d['delta']:+d} |")
    out.append("")
    out.append("### Unified source diff\n")
    out.append("```diff")
    out.append(a["unified_diff"][:6000])
    out.append("```\n")
    out.append("### Reasoning text — proposal A (set000_seed024)\n")
    out.append("> " + a["reasoning_a"].replace("\n", "\n> "))
    out.append("\n### Reasoning text — proposal B (set000_seed031)\n")
    out.append("> " + a["reasoning_b"].replace("\n", "\n> "))
    out.append("")
    return out


def _md_for_analysis_b(b: Dict[str, Any]) -> List[str]:
    out = ["## Analysis B — L1 catastrophe concentration\n"]
    sr = b["stratified_representative"]
    out.append(f"### `stratified_representative@L1`\n")
    out.append(f"- Total catastrophes (delta_step < −100): **{sr['n_catastrophes_total']}**")
    out.append(f"- Sets containing ≥1 catastrophe: {sr['n_sets_with_catastrophes']} of 20")
    out.append(f"- Sets with 2+ catastrophes: {sr['n_sets_with_2plus']}")
    out.append("")
    out.append("| set | n_catastrophes | proposal_hashes (distinct?) | delta_steps |")
    out.append("|---:|---:|---|---|")
    for s in sr["per_set"]:
        hashes = s["proposal_hashes"]
        distinct = len(set(hashes))
        marker = f"{distinct} distinct" if distinct == len(hashes) else f"{distinct} distinct of {len(hashes)}"
        out.append(f"| {s['set_index']} | {s['n_catastrophes']} | {marker} "
                   f"({', '.join(hashes)}) | "
                   f"{', '.join(f'{d:+.1f}' for d in s['delta_steps'])} |")
    out.append("")
    g = sr["gap_distribution"]
    out.append("Gap distribution comparison (counterexample-set gaps):\n")
    out.append(f"- Catastrophe-prone sets: n={g['catastrophe_sets_n_gaps']} gaps, "
               f"mean = {g['catastrophe_sets_mean_gap']}, median = {g['catastrophe_sets_median_gap']}")
    out.append(f"- Safe sets:               n={g['safe_sets_n_gaps']} gaps, "
               f"mean = {g['safe_sets_mean_gap']}, median = {g['safe_sets_median_gap']}")
    out.append("")
    out.append("### `worst_plus_best@L1`\n")
    wpb = b["worst_plus_best"]
    out.append(f"- Catastrophes: **{wpb['n_catastrophes']}** of 60")
    out.append(f"- Distinct catastrophe hashes: {wpb['n_distinct_hashes']}")
    out.append(f"- Top-10 most-repeated catastrophe hashes (hash, count): "
               f"{wpb['hash_count_top']}")
    s = wpb["delta_steps_summary"]
    if s["mean"] is not None:
        out.append(f"- delta_step among catastrophes: min {s['min']:.1f}, "
                   f"mean {s['mean']:.1f}, max {s['max']:.1f}")
    out.append("")
    return out


def _md_for_analysis_c(c: Dict[str, Any]) -> List[str]:
    out = ["## Analysis C — Argmax-equivalence rate verification\n"]
    out.append(f"- Strict definition: `{c['definition_strict']}`")
    out.append(f"- Near definition:   `{c['definition_near']}`")
    out.append(f"- h_eoh train_step mean: {c['h_eoh_step_mean']:.2f}")
    out.append("")
    out.append("| cell | n | strict-equiv | rate | near-or-strict | combined rate |")
    out.append("|---|---:|---:|---:|---:|---:|")
    for cell_id in CELL_IDS:
        s = c["per_cell"][cell_id]
        out.append(
            f"| `{cell_id}` | {s['n_records']} | "
            f"{s['n_strict_argmax_equivalent']} | "
            f"{(s['rate_strict'] or 0)*100:.1f}% | "
            f"{s['n_strict_argmax_equivalent'] + s['n_near_argmax_equivalent']} | "
            f"{(s['rate_near_or_strict'] or 0)*100:.1f}% |"
        )
    out.append("")
    if c["strict_equivalent_examples"]:
        out.append(f"### Strict-equivalent records ({len(c['strict_equivalent_examples'])})\n")
        for e in c["strict_equivalent_examples"]:
            out.append(f"- `{e['cell_id']}` set={e['set_index']:03d} seed={e['seed_index']:03d}  "
                       f"hash=`{e['proposal_hash']}`")
        out.append("")
    if c["near_equivalent_examples"]:
        out.append(f"### Near-equivalent records ({len(c['near_equivalent_examples'])})\n")
        for e in c["near_equivalent_examples"][:30]:
            out.append(f"- `{e['cell_id']}` set={e['set_index']:03d} seed={e['seed_index']:03d}  "
                       f"hash=`{e['proposal_hash']}`  max_diff={e['max_elementwise_diff']}")
        if len(c["near_equivalent_examples"]) > 30:
            out.append(f"- ... ({len(c['near_equivalent_examples']) - 30} more)")
        out.append("")
    return out


def _md_for_analysis_d(d: Dict[str, Any]) -> List[str]:
    out = ["## Analysis D — Modal-proposal analysis\n"]
    out.append("### Per-cell uniqueness\n")
    out.append("| cell | n | distinct_hashes | unique_singletons | max_modal_size | "
               "fraction_in_modal_clusters |")
    out.append("|---|---:|---:|---:|---:|---:|")
    for cell_id in CELL_IDS:
        u = d["per_cell_uniqueness"][cell_id]
        out.append(
            f"| `{cell_id}` | {u['n_records']} | {u['n_distinct_hashes']} | "
            f"{u['n_unique_singletons']} | {u['max_modal_size']} | "
            f"{(u['fraction_records_in_modal_clusters'] or 0)*100:.1f}% |"
        )
    out.append("")
    out.append("### Top-10 modal proposals (≥3 occurrences)\n")
    if not d["top10_modal"]:
        out.append("(No proposal hash appeared 3+ times.)")
    for e in d["top10_modal"]:
        out.append(f"\n#### Hash `{e['hash']}` — {e['n_occurrences']} occurrences\n")
        out.append(f"- Cells: {', '.join(f'`{c}`' for c in e['cells'])}")
        if e["delta_step"] is not None:
            out.append(f"- delta_step (constant): {e['delta_step']:+.3f}")
        else:
            out.append(f"- delta_step range: {e['delta_step_min']:+.3f} … {e['delta_step_max']:+.3f}")
        if e["cross_level_strategies"]:
            out.append(f"- **Cross-level (L1 ∩ L2) strategies**: "
                       f"{', '.join(f'`{s}`' for s in e['cross_level_strategies'])}")
        out.append("- Coordinates: " + ", ".join(
            f"{o['cell_id']} ({o['set']},{o['seed']})" for o in e["all_occurrences"]
        ))
        out.append("\n```python")
        out.append(e["src_preview"])
        out.append("```")
    out.append("")
    if d["cross_level_within_strategy"]:
        out.append("### Cross-level overlap (L1 ∩ L2 within same strategy)\n")
        for e in d["cross_level_within_strategy"]:
            out.append(f"- `{e['hash']}` ({e['n_occurrences']} total) crosses "
                       f"L1 and L2 in: {', '.join(e['cross_level_strategies'])}")
        out.append("")
    return out


def _md_for_analysis_e(e: Dict[str, Any]) -> List[str]:
    out = ["## Analysis E — Refined trace-engagement classification\n"]
    out.append("Definitions:\n")
    for k, v in e["definitions"].items():
        out.append(f"- **{k}**: {v}")
    out.append("")
    out.append("### Per-cell breakdown\n")
    out.append("| cell | n | C (cited) | M (mentioned) | A (absent) | "
               "mean Δ_step C / M / A |")
    out.append("|---|---:|---:|---:|---:|---|")
    for cell_id in ("stratified_representative@L2", "worst_plus_best@L2"):
        c = e["per_cell"][cell_id]
        n = c["n_records"]
        cc = c["class_counts"]
        ms = c["mean_delta_step_by_class"]

        def fmt(k):
            return (f"{ms[k]:+.2f}" if ms[k] is not None else "n/a") + f" (n={cc.get(k,0)})"

        out.append(
            f"| `{cell_id}` | {n} | {cc.get('C',0)} | {cc.get('M',0)} | {cc.get('A',0)} | "
            f"{fmt('C')} / {fmt('M')} / {fmt('A')} |"
        )
    out.append("")
    out.append("### Matched-pair Δ(L2 − L1) by L2 class\n")
    out.append("| cell | C mean (n) | M mean (n) | A mean (n) |")
    out.append("|---|---|---|---|")
    for cell_id in ("stratified_representative@L2", "worst_plus_best@L2"):
        p = e["per_cell"][cell_id]["matched_pair_diff_by_class"]
        def fmt(k):
            v = p[k]
            if v["n_pairs"] == 0:
                return "n=0"
            return f"{v['mean_diff']:+.2f} (n={v['n_pairs']})"
        out.append(f"| `{cell_id}` | {fmt('C')} | {fmt('M')} | {fmt('A')} |")
    out.append("")
    out.append("### Modal-cluster membership by class\n")
    out.append("| cell | C in modal | M in modal | A in modal |")
    out.append("|---|---:|---:|---:|")
    for cell_id in ("stratified_representative@L2", "worst_plus_best@L2"):
        m = e["per_cell"][cell_id]["in_modal_cluster_by_class"]
        out.append(f"| `{cell_id}` | {m.get('C',0)} | {m.get('M',0)} | {m.get('A',0)} |")
    out.append("")
    return out


def _summary_bullets(a, b, c, d, e) -> List[str]:
    bullets = []
    bullets.append(
        f"- **A**: the two −1255 outliers in `worst_plus_best@L2` are "
        f"{a['diff_kind']} at the source level "
        f"(per_instance_bins identical = {a['per_instance_bins_match']})."
    )
    sr = b["stratified_representative"]
    wpb = b["worst_plus_best"]
    bullets.append(
        f"- **B**: stratified L1 has {sr['n_catastrophes_total']} catastrophes "
        f"across {sr['n_sets_with_catastrophes']} sets ({sr['n_sets_with_2plus']} "
        f"with 2+); wpb L1 has {wpb['n_catastrophes']} catastrophes "
        f"({wpb['n_distinct_hashes']} distinct hashes)."
    )
    strict_total = sum(c["per_cell"][k]["n_strict_argmax_equivalent"] for k in CELL_IDS)
    near_total = sum(c["per_cell"][k]["n_near_argmax_equivalent"] for k in CELL_IDS)
    bullets.append(
        f"- **C**: strict argmax-equivalence rate across all 240 records is "
        f"{strict_total}/240 ({strict_total/240*100:.1f}%); near-equivalence "
        f"(max element-wise diff ≤ 1) adds {near_total} more "
        f"({(strict_total + near_total)/240*100:.1f}% combined)."
    )
    n_modal = len(d["top10_modal"])
    n_cross = len(d["cross_level_within_strategy"])
    bullets.append(
        f"- **D**: {n_modal} hashes appear ≥3 times among 240 records; "
        f"{n_cross} of those cross L1↔L2 within the same strategy."
    )
    s_l2 = e["per_cell"]["stratified_representative@L2"]["class_counts"]
    w_l2 = e["per_cell"]["worst_plus_best@L2"]["class_counts"]
    bullets.append(
        f"- **E**: trace-engagement classes — stratified L2 C/M/A = "
        f"{s_l2.get('C',0)}/{s_l2.get('M',0)}/{s_l2.get('A',0)}; wpb L2 C/M/A = "
        f"{w_l2.get('C',0)}/{w_l2.get('M',0)}/{w_l2.get('A',0)} (out of 60 each)."
    )
    return bullets


def main() -> int:
    print("Loading records...")
    records = _load_all_records()
    print(f"  loaded {len(records)} OK records")

    # Anomaly: any non-OK records on disk?
    all_files = list(RESULTS_DIR.glob("stratified_representative@L*_set*.json")) + \
                list(RESULTS_DIR.glob("worst_plus_best@L*_set*.json"))
    non_ok = []
    for p in all_files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            non_ok.append({"file": p.name, "issue": "parse_error"})
            continue
        if (d.get("sanitization") or {}).get("status") != "ok":
            non_ok.append({"file": p.name, "issue": d.get("sanitization", {}).get("status")})

    print("Analysis A...")
    a = analysis_a(records)
    print("Analysis B...")
    b = analysis_b(records)
    print("Analysis C...")
    c = analysis_c(records)
    print("Analysis D...")
    d = analysis_d(records)
    print("Analysis E...")
    modal_hashes = [m["hash"] for m in d["top10_modal"]]
    e = analysis_e(records, modal_hashes)

    bullets = _summary_bullets(a, b, c, d, e)

    md: List[str] = []
    md.append("# Chapter 6 verification analysis\n")
    md.append("Pure post-hoc analysis on the full 240/240 batch (no new LLM calls). "
              "Five analyses; outputs into `_verification_analysis.json` for "
              "structured re-use.\n")
    md.append("## Summary of findings\n")
    md.extend(bullets)
    md.append("")
    if non_ok:
        md.append("### Anomalies\n")
        for item in non_ok:
            md.append(f"- `{item['file']}`: {item['issue']}")
        md.append("")
    else:
        md.append("### Anomalies\n\n- None detected: all 240 expected records present, "
                  "all `sanitization.status == 'ok'`.\n")
    md.extend(_md_for_analysis_a(a))
    md.extend(_md_for_analysis_b(b))
    md.extend(_md_for_analysis_c(c))
    md.extend(_md_for_analysis_d(d))
    md.extend(_md_for_analysis_e(e))

    MD_OUT.write_text("\n".join(md), encoding="utf-8")
    JSON_OUT.write_text(json.dumps({
        "analysis_A_minus1255": a,
        "analysis_B_l1_catastrophes": b,
        "analysis_C_argmax_equivalence": c,
        "analysis_D_modal_proposals": d,
        "analysis_E_engagement_classification": e,
        "anomalies": non_ok,
        "summary_bullets": bullets,
    }, indent=2), encoding="utf-8")
    print(f"\nWrote {MD_OUT}")
    print(f"Wrote {JSON_OUT}")
    print()
    print("Summary bullets:")
    for line in bullets:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
