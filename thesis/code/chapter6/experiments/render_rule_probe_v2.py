"""
thesis/code/chapter6/experiments/render_rule_probe_v2.py

Tertiary chapter-6 trace probe. Triggered by the smoke-batch
finding (commit 505c70e): the locked compact4_200_full_open_bins
rule produces ~2.07 MB k=4 prompts that exceed Gemini 2.5 Pro's
1,048,576-token input limit at the dense-numeric ~2.06
chars/token ratio observed in the smoke.

For each of the 30 pool instances, extracts the incumbent trace
once and renders it under each of 4 candidate rules:

  - compact4_200_full_open_bins  — the current locked rule,
                                   re-measured for tokens.
  - compact4_200_open_bins_20    — N=200 rows, per-row
                                   open_bins capped at 20 via
                                   the §spec sampling rule.
  - compact4_200_open_bins_50    — N=200 rows, capped at 50.
  - compact4_150_full_open_bins  — N=150 rows, every open bin
                                   rendered. The "just shrink
                                   N" comparison.

Two new per-row fields are introduced (and rendered in all four
cells, so the format is consistent across the matrix):

  - open_bins_total_n=<int>  — the true number of incumbent
    open bins at decision time. Disambiguates whether the
    rendered list is exhaustive or a sample.
  - runner_up_pos=<int|new>  — the abstract-set position of
    the runner-up bin, re-derived at probe time by re-scoring
    the abstract candidate set with h_eoh's score function.
    With bin sampling, this disambiguates which of the
    rendered bins has the runner-up score; without sampling
    it remains useful context for the LLM. Defaults to
    `chose` in the degenerate score_runner_up == score_winner
    case (margin == 0); the LLM sees "winner and runner-up
    at the same slot" rather than a contradictory third
    sentinel.

Bin-sampling rule (truncation cells only, applied per row when
total_n > cap):
  1. Always-include = {chose if int} ∪ {runner_up_pos if int}.
  2. Stride-fill the remainder by capacity ascending via
     numpy.linspace.
  3. Sort the union by capacity ascending.
  4. Re-map chose and runner_up_pos to indices in the rendered
     (sorted) list.

The probe measures — it does not pick a rule. The artifact is
the empirical input to the §7.4 rule revision that follows in a
separate task.

Usage:
    python -m thesis.code.chapter6.experiments.render_rule_probe_v2
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

from thesis.code.chapter6 import trace_extractor as _trace_extractor_module
from thesis.code.chapter6.trace_extractor import (
    DecisionRecord,
    extract_incumbent_trace,
)
from thesis.code.counterexample import CounterexampleSet
from thesis.code.evaluation import load_heuristic_from_code
from thesis.code.incumbents import get_h_eoh
from thesis.code.splits import load_split

REPO_ROOT = Path(__file__).resolve().parents[4]
ARTIFACTS_DIR = REPO_ROOT / "thesis" / "artifacts"
POOL_PATH = ARTIFACTS_DIR / "h_eoh_counterexample_pool.json"
OUTPUT_PATH = ARTIFACTS_DIR / "chapter6_render_rule_probe_v2.json"

PROBE_VERSION = "2.0"

# Empirical chars-per-token ratio observed on the L2 smoke prompt
# (commit 505c70e): 2,166,388 chars ⇒ ~1,051,400 tokens reported by
# Gemini's 400-error message ⇒ 2.06 chars/token. Used as the
# token-count estimator for all cells in this probe.
CHAR_TO_TOKEN_RATIO = 2.06
GEMINI_INPUT_TOKEN_LIMIT = 1_048_576


# --- Per-cell candidate rules ---------------------------------------------


CellSpec = Tuple[str, Optional[int], Optional[int]]
"""(rule_name, row_count_cap, open_bins_cap)."""

CANDIDATE_CELLS: List[CellSpec] = [
    ("compact4_200_full_open_bins", 200, None),
    ("compact4_200_open_bins_20", 200, 20),
    ("compact4_200_open_bins_50", 200, 50),
    ("compact4_150_full_open_bins", 150, None),
]


# --- §7.4 part (b) row selection (parameterized by row_count_cap) ---------


def _select_row_positions(n_trace_rows: int, row_count_cap: int) -> List[int]:
    """Same head+stride rule as the locked §7.4, parameterized by N.

    head = floor(0.2 * row_count_cap) rows verbatim;
    tail = numpy.linspace(head_count, n-1, row_count_cap - head_count, dtype=int);
    union-deduped, sorted ascending. Defensive branch returns all
    positions when n_trace_rows <= row_count_cap.
    """
    if n_trace_rows <= row_count_cap:
        return list(range(n_trace_rows))
    head_count = int(0.2 * row_count_cap)
    tail_count = row_count_cap - head_count
    head = list(range(head_count))
    tail = np.linspace(head_count, n_trace_rows - 1, tail_count, dtype=int).tolist()
    return sorted(set(head) | {int(t) for t in tail})


# --- runner_up_pos derivation ---------------------------------------------


def _derive_runner_up_pos(
    record: DecisionRecord,
    capacity: float,
    heuristic: types.ModuleType,
) -> Union[int, str]:
    """Re-derive which abstract slot is the runner-up.

    Returns either an integer position into ``record.open_bins`` or
    the string ``"new"`` if the new-bin slot is the runner-up.

    In the degenerate ``score_runner_up == score_winner`` case
    (margin == 0; abstract set has fewer than two elements, or
    all candidates tie at the top), returns ``record.chose`` so
    the LLM sees ``runner_up_pos == chose``.
    """
    if record.score_runner_up == record.score_winner:
        return record.chose

    item = record.item

    # Score the valid open bins
    valid_positions: List[int] = [
        i for i, c in enumerate(record.open_bins) if c >= item
    ]
    pos_to_score: Dict[int, float] = {}
    if valid_positions:
        caps = np.array(
            [record.open_bins[i] for i in valid_positions], dtype=float
        )
        scores = np.asarray(heuristic.score(item, caps), dtype=float)
        for k, pos in enumerate(valid_positions):
            pos_to_score[pos] = float(scores[k])

    # Score the new-bin slot
    new_slot_score: Optional[float] = None
    if capacity >= item:
        new_score_arr = np.asarray(
            heuristic.score(item, np.array([capacity], dtype=float)),
            dtype=float,
        )
        new_slot_score = float(new_score_arr[0])

    # Find non-winner candidates whose score matches score_runner_up
    matches: List[Union[int, str]] = []
    for pos, scr in pos_to_score.items():
        if pos == record.chose:
            continue
        if abs(scr - record.score_runner_up) < 1e-9:
            matches.append(pos)
    if (
        new_slot_score is not None
        and record.chose != "new"
        and abs(new_slot_score - record.score_runner_up) < 1e-9
    ):
        matches.append("new")

    if not matches:
        return record.chose  # fallback: should not happen for canonical pool

    int_matches = [m for m in matches if isinstance(m, int)]
    if int_matches:
        return min(int_matches)
    return "new"


# --- Bin sampling for truncation cells ------------------------------------


def _sample_open_bins(
    open_bins: Sequence[float],
    chose: Union[int, str],
    runner_up_pos: Union[int, str],
    cap: int,
) -> Tuple[Tuple[float, ...], Union[int, str], Union[int, str], bool]:
    """Sample open_bins to ≤ cap entries per the task's spec.

    Returns ``(rendered_caps, rendered_chose, rendered_runner_up_pos,
    sampling_fired)``. When sampling does not fire (``total_n <=
    cap``), open_bins is returned unchanged in creation order and
    chose / runner_up_pos pass through untouched.
    """
    total_n = len(open_bins)

    if total_n <= cap:
        return tuple(open_bins), chose, runner_up_pos, False

    always_positions: List[int] = []
    if isinstance(chose, int):
        always_positions.append(chose)
    if isinstance(runner_up_pos, int) and runner_up_pos not in always_positions:
        always_positions.append(runner_up_pos)

    remaining_positions = [
        i for i in range(total_n) if i not in always_positions
    ]
    n_fill = cap - len(always_positions)

    if n_fill <= 0:
        fill_positions: List[int] = []
    elif n_fill >= len(remaining_positions):
        fill_positions = list(remaining_positions)
    else:
        remaining_sorted = sorted(
            remaining_positions, key=lambda i: open_bins[i]
        )
        stride_idx = np.linspace(
            0, len(remaining_sorted) - 1, n_fill, dtype=int
        ).tolist()
        fill_positions = [
            remaining_sorted[i] for i in sorted(set(int(s) for s in stride_idx))
        ]

    union_positions = sorted(
        set(always_positions) | set(fill_positions),
        key=lambda i: (open_bins[i], i),
    )
    rendered_caps = tuple(open_bins[i] for i in union_positions)

    rendered_chose: Union[int, str]
    if isinstance(chose, int):
        rendered_chose = union_positions.index(chose)
    else:
        rendered_chose = "new"

    rendered_runner_up_pos: Union[int, str]
    if isinstance(runner_up_pos, int) and runner_up_pos in union_positions:
        rendered_runner_up_pos = union_positions.index(runner_up_pos)
    else:
        rendered_runner_up_pos = "new" if runner_up_pos == "new" else rendered_chose

    return rendered_caps, rendered_chose, rendered_runner_up_pos, True


# --- Row formatting (consistent across all four cells) --------------------


def _format_row(
    record: DecisionRecord,
    rendered_open_bins: Sequence[float],
    rendered_chose: Union[int, str],
    rendered_runner_up_pos: Union[int, str],
    total_n: int,
) -> str:
    """Format one row under the v2 schema (existing fields plus
    open_bins_total_n and runner_up_pos)."""
    item_str = f"{record.item:.4g}"
    if rendered_open_bins:
        open_bins_str = (
            "[" + ", ".join(f"{c:.4g}" for c in rendered_open_bins) + "]"
        )
    else:
        open_bins_str = "[]"
    chose_str = "new" if rendered_chose == "new" else str(rendered_chose)
    runner_up_pos_str = (
        "new"
        if rendered_runner_up_pos == "new"
        else str(rendered_runner_up_pos)
    )
    winner_str = f"{record.score_winner:.4g}"
    runner_up_str = f"{record.score_runner_up:.4g}"
    margin_str = f"{record.margin:.4g}"
    cap_after_str = f"{record.cap_after:.4g}"
    new_bin_str = "true" if record.new_bin else "false"
    return (
        f"idx={record.idx} item={item_str} open_bins={open_bins_str} "
        f"open_bins_total_n={total_n} chose={chose_str} "
        f"runner_up_pos={runner_up_pos_str} winner={winner_str} "
        f"runner_up={runner_up_str} margin={margin_str} "
        f"cap_after={cap_after_str} new_bin={new_bin_str}"
    )


# --- Bin-capacity preservation -------------------------------------------


def _within_5pct(rendered: float, true: float) -> bool:
    if true == 0.0:
        return rendered == 0.0
    return abs(rendered - true) / abs(true) <= 0.05


def _capacity_preservation(
    rendered_caps: Sequence[float], true_open_bins: Sequence[float]
) -> Tuple[bool, bool, bool]:
    """Returns (min_preserved, max_preserved, iqr_preserved) for one row.

    "Preserved" = within 5% of the true value. The IQR check
    requires both p25 and p75 within 5%. Empty inputs are treated
    as trivially preserved (no comparison meaningful).
    """
    if not true_open_bins:
        return True, True, True
    if not rendered_caps:
        return False, False, False
    true_arr = np.asarray(true_open_bins, dtype=float)
    rend_arr = np.asarray(rendered_caps, dtype=float)
    min_pres = _within_5pct(float(rend_arr.min()), float(true_arr.min()))
    max_pres = _within_5pct(float(rend_arr.max()), float(true_arr.max()))
    true_p25 = float(np.percentile(true_arr, 25))
    true_p75 = float(np.percentile(true_arr, 75))
    rend_p25 = float(np.percentile(rend_arr, 25))
    rend_p75 = float(np.percentile(rend_arr, 75))
    iqr_pres = (
        _within_5pct(rend_p25, true_p25)
        and _within_5pct(rend_p75, true_p75)
    )
    return min_pres, max_pres, iqr_pres


# --- Stats helpers --------------------------------------------------------


def _percentile_stats(values: Sequence[float]) -> Dict[str, Optional[float]]:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return {k: None for k in ("min", "max", "mean", "median", "p25", "p75", "p90", "p99")}
    return {
        "min": float(arr.min()),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "p90": float(np.percentile(arr, 90)),
        "p99": float(np.percentile(arr, 99)),
    }


# --- Per-cell measurement -------------------------------------------------


def _measure_cell(
    records: Sequence[DecisionRecord],
    runner_up_positions: Sequence[Union[int, str]],
    rule_name: str,
    row_count_cap: int,
    open_bins_cap: Optional[int],
) -> Dict[str, Any]:
    """Render the trace under the cell's rule and produce its stats entry."""
    try:
        positions = _select_row_positions(len(records), row_count_cap)
        sampled_records = [records[p] for p in positions]
        sampled_runner_up = [runner_up_positions[p] for p in positions]

        row_lines: List[str] = []
        bin_sampling_fired = 0
        rendered_open_bins_sizes: List[int] = []

        min_preserved = 0
        max_preserved = 0
        iqr_preserved = 0
        n_sampled_rows = 0  # rows where bin sampling actually fired

        for rec, ru_pos in zip(sampled_records, sampled_runner_up):
            true_total_n = len(rec.open_bins)
            if open_bins_cap is None:
                rendered_open_bins = tuple(rec.open_bins)
                rendered_chose: Union[int, str] = rec.chose
                rendered_runner_up_pos: Union[int, str] = ru_pos
                sampling_fired = False
            else:
                (
                    rendered_open_bins,
                    rendered_chose,
                    rendered_runner_up_pos,
                    sampling_fired,
                ) = _sample_open_bins(
                    rec.open_bins, rec.chose, ru_pos, open_bins_cap
                )

            if sampling_fired:
                bin_sampling_fired += 1
                n_sampled_rows += 1
                mn, mx, iqr = _capacity_preservation(
                    rendered_open_bins, rec.open_bins
                )
                min_preserved += int(mn)
                max_preserved += int(mx)
                iqr_preserved += int(iqr)

            rendered_open_bins_sizes.append(len(rendered_open_bins))

            row_lines.append(
                _format_row(
                    rec,
                    rendered_open_bins,
                    rendered_chose,
                    rendered_runner_up_pos,
                    true_total_n,
                )
            )

        rendered_text = "".join(line + "\n" for line in row_lines)
        char_count = len(rendered_text)
        token_estimate = int(round(char_count / CHAR_TO_TOKEN_RATIO))

        if open_bins_cap is None:
            # Full-bins cells: no sampling rows, distortion is 1.0 by
            # construction.
            min_rate = 1.0
            max_rate = 1.0
            iqr_rate = 1.0
        elif n_sampled_rows == 0:
            # Truncated cell, but no row had total_n > cap on this
            # instance. All renders were exhaustive.
            min_rate = 1.0
            max_rate = 1.0
            iqr_rate = 1.0
        else:
            min_rate = min_preserved / n_sampled_rows
            max_rate = max_preserved / n_sampled_rows
            iqr_rate = iqr_preserved / n_sampled_rows

        return {
            "rule": rule_name,
            "rendered_char_count": char_count,
            "rendered_token_count_estimate": token_estimate,
            "rendered_row_count": len(sampled_records),
            "bin_sampling_fired_count": bin_sampling_fired,
            "mean_rendered_open_bins_size": (
                float(np.mean(rendered_open_bins_sizes))
                if rendered_open_bins_sizes
                else None
            ),
            "bin_capacity_distortion": {
                "min_capacity_preservation_rate": min_rate,
                "max_capacity_preservation_rate": max_rate,
                "interquartile_capacity_preservation_rate": iqr_rate,
            },
            "status": "ok",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "rule": rule_name,
            "rendered_char_count": None,
            "rendered_token_count_estimate": None,
            "rendered_row_count": None,
            "bin_sampling_fired_count": None,
            "mean_rendered_open_bins_size": None,
            "bin_capacity_distortion": {
                "min_capacity_preservation_rate": None,
                "max_capacity_preservation_rate": None,
                "interquartile_capacity_preservation_rate": None,
            },
            "status": f"error:{type(exc).__name__}",
            "error_message": str(exc),
        }


# --- Aggregation ---------------------------------------------------------


def _aggregate_cell(
    rule: str,
    row_count_cap: int,
    open_bins_cap: Optional[int],
    per_instance: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    char_counts: List[int] = []
    token_estimates: List[int] = []
    n_failed = 0
    bin_sampling_fired_rates: List[float] = []
    mean_open_bins_sizes: List[float] = []
    min_pres_rates: List[float] = []
    max_pres_rates: List[float] = []
    iqr_pres_rates: List[float] = []

    for entry in per_instance:
        cell = next(c for c in entry["cells"] if c["rule"] == rule)
        if cell["status"] != "ok":
            n_failed += 1
            continue
        char_counts.append(cell["rendered_char_count"])
        token_estimates.append(cell["rendered_token_count_estimate"])
        rrc = cell["rendered_row_count"]
        bin_sampling_fired_rates.append(
            cell["bin_sampling_fired_count"] / rrc if rrc else 0.0
        )
        mean_open_bins_sizes.append(cell["mean_rendered_open_bins_size"])
        bcd = cell["bin_capacity_distortion"]
        min_pres_rates.append(bcd["min_capacity_preservation_rate"])
        max_pres_rates.append(bcd["max_capacity_preservation_rate"])
        iqr_pres_rates.append(bcd["interquartile_capacity_preservation_rate"])

    if char_counts:
        sorted_chars_desc = sorted(char_counts, reverse=True)
        max_4_char = (
            int(sum(sorted_chars_desc[:4])) if len(sorted_chars_desc) >= 4 else None
        )
        mean_4_char = 4.0 * float(np.mean(char_counts))
    else:
        max_4_char = None
        mean_4_char = None

    if token_estimates:
        sorted_tokens_desc = sorted(token_estimates, reverse=True)
        max_4_token = (
            int(sum(sorted_tokens_desc[:4])) if len(sorted_tokens_desc) >= 4 else None
        )
        mean_4_token = 4.0 * float(np.mean(token_estimates))
        headroom = (
            GEMINI_INPUT_TOKEN_LIMIT - max_4_token if max_4_token is not None else None
        )
    else:
        max_4_token = None
        mean_4_token = None
        headroom = None

    return {
        "rule": rule,
        "numeric_format": "compact4",
        "row_count_cap": row_count_cap,
        "open_bins_cap": open_bins_cap,
        "n_successful": len(char_counts),
        "n_failed": n_failed,
        "rendered_char_count_stats": _percentile_stats(char_counts),
        "rendered_token_count_estimate_stats": _percentile_stats(token_estimates),
        "bin_sampling_fired_rate_stats": _percentile_stats(bin_sampling_fired_rates),
        "mean_rendered_open_bins_size_stats": _percentile_stats(mean_open_bins_sizes),
        "k4_prompt_render_projection": {
            "mean_4_instance_char_sum": mean_4_char,
            "max_4_instance_char_sum": max_4_char,
            "mean_4_instance_token_estimate_sum": mean_4_token,
            "max_4_instance_token_estimate_sum": max_4_token,
            "headroom_below_1M_tokens": headroom,
        },
        "bin_capacity_distortion": {
            "min_capacity_preservation_rate": _percentile_stats(min_pres_rates),
            "max_capacity_preservation_rate": _percentile_stats(max_pres_rates),
            "interquartile_capacity_preservation_rate": _percentile_stats(
                iqr_pres_rates
            ),
        },
    }


# --- Per-instance loop ---------------------------------------------------


def _instance_lookup() -> Dict[str, Mapping[str, Any]]:
    split = load_split("train_select")
    return {
        f"thesis_train_select:{inst['instance_id']}": inst
        for inst in split["instances"]
    }


def _measure_instance(
    instance_id: str,
    instance: Mapping[str, Any],
    incumbent_module: types.ModuleType,
) -> Dict[str, Any]:
    """Extract one trace, derive runner_up positions, render under all
    4 cells. Per-row format is consistent across cells; only the row
    selection and bin-sampling differ."""
    try:
        records = extract_incumbent_trace(instance, incumbent_module)
    except Exception as exc:  # noqa: BLE001
        cells = []
        for rule_name, rcc, obc in CANDIDATE_CELLS:
            cells.append({
                "rule": rule_name,
                "rendered_char_count": None,
                "rendered_token_count_estimate": None,
                "rendered_row_count": None,
                "bin_sampling_fired_count": None,
                "mean_rendered_open_bins_size": None,
                "bin_capacity_distortion": {
                    "min_capacity_preservation_rate": None,
                    "max_capacity_preservation_rate": None,
                    "interquartile_capacity_preservation_rate": None,
                },
                "status": f"error:{type(exc).__name__}",
                "error_message": str(exc),
            })
        cells.sort(key=lambda c: c["rule"])
        return {
            "instance_id": instance_id,
            "n_items": int(instance["num_items"]),
            "trace_extracted": False,
            "extraction_error": f"{type(exc).__name__}: {exc!s}",
            "cells": cells,
        }

    capacity = float(instance["capacity"])
    runner_up_positions: List[Union[int, str]] = [
        _derive_runner_up_pos(rec, capacity, incumbent_module)
        for rec in records
    ]

    cells: List[Dict[str, Any]] = []
    for rule_name, rcc, obc in CANDIDATE_CELLS:
        cells.append(
            _measure_cell(records, runner_up_positions, rule_name, rcc, obc)
        )
    cells.sort(key=lambda c: c["rule"])

    return {
        "instance_id": instance_id,
        "n_items": int(instance["num_items"]),
        "trace_extracted": True,
        "trace_row_count": len(records),
        "cells": cells,
    }


def main() -> int:
    h_eoh_meta = get_h_eoh()
    h_eoh_module = load_heuristic_from_code(
        h_eoh_meta["code"], "h_eoh_for_render_rule_probe_v2"
    )
    h_eoh_hash = h_eoh_meta["code_hash"]

    pool_bytes = POOL_PATH.read_bytes()
    pool_sha_prefix = hashlib.sha256(pool_bytes).hexdigest()[:12]
    pool = CounterexampleSet.from_json(pool_bytes.decode("utf-8"))
    instance_map = _instance_lookup()

    per_instance: List[Dict[str, Any]] = []
    n_extract_ok = 0
    n_extract_failed = 0
    n_cell_failed = 0

    for ce in pool:
        inst_id = ce.instance_id
        if inst_id not in instance_map:
            cells = []
            for rule_name, _rcc, _obc in CANDIDATE_CELLS:
                cells.append({
                    "rule": rule_name,
                    "rendered_char_count": None,
                    "rendered_token_count_estimate": None,
                    "rendered_row_count": None,
                    "bin_sampling_fired_count": None,
                    "mean_rendered_open_bins_size": None,
                    "bin_capacity_distortion": {
                        "min_capacity_preservation_rate": None,
                        "max_capacity_preservation_rate": None,
                        "interquartile_capacity_preservation_rate": None,
                    },
                    "status": "error:KeyError",
                    "error_message": (
                        f"instance_id {inst_id!r} not in train_select split"
                    ),
                })
            cells.sort(key=lambda c: c["rule"])
            per_instance.append({
                "instance_id": inst_id,
                "n_items": None,
                "trace_extracted": False,
                "extraction_error": (
                    f"KeyError: instance_id {inst_id!r} not in "
                    "train_select split"
                ),
                "cells": cells,
            })
            n_extract_failed += 1
            n_cell_failed += len(cells)
            continue

        entry = _measure_instance(
            inst_id, instance_map[inst_id], h_eoh_module
        )
        per_instance.append(entry)
        if entry["trace_extracted"]:
            n_extract_ok += 1
            n_cell_failed += sum(
                1 for c in entry["cells"] if c["status"] != "ok"
            )
        else:
            n_extract_failed += 1
            n_cell_failed += len(entry["cells"])

    per_instance.sort(key=lambda e: e["instance_id"])

    cell_aggregates = sorted(
        [
            _aggregate_cell(rule, rcc, obc, per_instance)
            for rule, rcc, obc in CANDIDATE_CELLS
        ],
        key=lambda c: c["rule"],
    )

    artifact: Dict[str, Any] = {
        "probe_metadata": {
            "probe_version": PROBE_VERSION,
            "run_date": dt.datetime.now(dt.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "pool_sha256_prefix_12": pool_sha_prefix,
            "h_eoh_hash_prefix_12": h_eoh_hash,
            "extractor_module_path": _trace_extractor_module.__name__,
            "char_to_token_ratio_used": CHAR_TO_TOKEN_RATIO,
            "char_to_token_ratio_source": "smoke batch 505c70e",
            "gemini_input_token_limit": GEMINI_INPUT_TOKEN_LIMIT,
            "bin_sampling_rule_description": (
                "When total_n > cap: always-include {chose, "
                "runner_up_pos} (only if int positions); stride-fill "
                "the remainder by capacity ascending via "
                "numpy.linspace; sort the union by capacity ascending; "
                "re-map chose and runner_up_pos to indices in the "
                "rendered list. When total_n <= cap: render in "
                "creation order, no transformation. See "
                "render_rule_probe_v2.py."
            ),
            "row_format_description": (
                "Per-row schema extends the §7.5 v1 format with "
                "open_bins_total_n=<int> and runner_up_pos=<int|new>; "
                "consistent across all four cells in this probe."
            ),
        },
        "cell_aggregates": cell_aggregates,
        "per_instance": per_instance,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    print(
        f"render_rule_probe_v2: {n_extract_ok}/{len(per_instance)} "
        f"instances extracted ok, {n_extract_failed} failed; "
        f"{n_cell_failed} of {len(per_instance) * len(CANDIDATE_CELLS)} "
        f"per-cell renders failed; wrote "
        f"{OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
