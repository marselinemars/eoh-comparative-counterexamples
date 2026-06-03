"""
thesis/code/chapter6/experiments/render_rule_probe.py

Secondary chapter-6 trace probe. For each pool instance,
extracts the incumbent trace once and renders it under each of
8 candidate rules — a 2 × 4 matrix of (numeric_format ×
row_count) — then writes per-instance, per-cell, and
pool-aggregate statistics to
``thesis/artifacts/chapter6_render_rule_probe.json``.

This probe complements
``thesis/artifacts/chapter6_trace_stats.json`` (commit ec23424):
the first probe measured the lossless / full cost; this one
measures the cost (and the margin-zero / new-bin distortion)
under realistic candidate rendering rules. The probe measures —
the §7.4 rendering-rule lock decision is a separate task that
reads these numbers.

Usage:
    python -m thesis.code.chapter6.experiments.render_rule_probe

No arguments. Overwrites the artifact each run. Per-instance
extraction or per-cell rendering failures are recorded in the
artifact (status, error_message) rather than raising; exit
code is 0 even when failures occur, with a summary line on
stderr.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

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
OUTPUT_PATH = ARTIFACTS_DIR / "chapter6_render_rule_probe.json"

PROBE_VERSION = "1.0"

# --- Numeric formatters -----------------------------------------------------

FloatFmt = Callable[[float], str]


def _fmt_lossless(x: float) -> str:
    """Python repr — same format used by the first probe."""
    return repr(x)


def _fmt_compact4(x: float) -> str:
    """4-significant-figure compact format ('%.4g')."""
    return f"{x:.4g}"


NUMERIC_FORMATS: Dict[str, FloatFmt] = {
    "lossless": _fmt_lossless,
    "compact4": _fmt_compact4,
}

ROW_COUNTS: List[Tuple[str, Optional[int]]] = [
    ("full", None),
    ("400", 400),
    ("200", 200),
    ("150", 150),
    ("100", 100),
    ("60", 60),
]


# --- Subsampling ------------------------------------------------------------


def subsample_indices(total_rows: int, cap: Optional[int]) -> List[int]:
    """Return the 1-based idx values selected by the head+linspace rule.

    For ``cap is None`` or ``cap >= total_rows``, returns
    ``[1, 2, ..., total_rows]`` (no subsampling).

    Otherwise:
      - head: the first ``floor(0.2 * cap)`` rows verbatim,
        i.e. ``[1, 2, ..., head_count]``.
      - tail: ``cap - head_count`` rows from a uniform stride
        across ``[head_count + 1, total_rows]`` produced by
        ``np.linspace(start, total_rows, tail_count, dtype=int)``,
        which always includes both endpoints.
      - The two are union'd, sorted, and deduplicated. The
        returned count may therefore be < ``cap`` if collisions
        occurred (in practice they do not for the
        ``(total_rows=5000, cap in {100, 200, 400})`` cells of
        this probe).
    """
    if cap is None or cap >= total_rows:
        return list(range(1, total_rows + 1))

    head_count = int(0.2 * cap)  # floor for positive cap
    tail_count = cap - head_count
    head = list(range(1, head_count + 1))
    start = head_count + 1
    tail = np.linspace(start, total_rows, tail_count, dtype=int).tolist()
    return sorted(set(head) | {int(t) for t in tail})


# --- Rendering --------------------------------------------------------------


def _render_row(record: DecisionRecord, fmt: FloatFmt) -> str:
    """Render a single row in the per-row format the first probe used.

    Numeric fields go through ``fmt`` (which is one of the
    NUMERIC_FORMATS variants); integer fields (``idx``, ``chose``
    when int) use ``str``; the bool ``new_bin`` renders as
    ``true`` / ``false``. ``open_bins`` is a comma-separated
    list of per-bin capacities formatted by ``fmt``.
    """
    open_bins_str = "[" + ", ".join(fmt(c) for c in record.open_bins) + "]"
    chose_str = record.chose if isinstance(record.chose, str) else str(record.chose)
    new_bin_str = "true" if record.new_bin else "false"
    return (
        f"idx={record.idx} item={fmt(record.item)} open_bins={open_bins_str} "
        f"chose={chose_str} winner={fmt(record.score_winner)} "
        f"runner_up={fmt(record.score_runner_up)} margin={fmt(record.margin)} "
        f"cap_after={fmt(record.cap_after)} new_bin={new_bin_str}"
    )


def _render_trace(records: Sequence[DecisionRecord], fmt: FloatFmt) -> str:
    """Render a trace (or a subsample of one) under the per-row format."""
    lines = [_render_row(r, fmt) for r in records]
    return "".join(line + "\n" for line in lines)


# --- Stats helpers ----------------------------------------------------------


def _percentile_stats(values: Sequence[float]) -> Dict[str, Optional[float]]:
    """min/max/mean/median/p25/p75/p90/p99 over a numeric sample."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "p25": None,
            "p75": None,
            "p90": None,
            "p99": None,
        }
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


# --- Per-instance / per-cell ------------------------------------------------


def _measure_cell(
    records: Sequence[DecisionRecord],
    rule: str,
    numeric_format: str,
    row_count_label: str,
    row_count_cap: Optional[int],
) -> Dict[str, Any]:
    """Render one (instance, rule) cell and measure its statistics.

    Catches and records render-time exceptions per cell, so a
    single bad cell does not poison the per-instance entry.
    """
    try:
        total_rows = len(records)
        idxs = subsample_indices(total_rows, row_count_cap)
        # records are 1-indexed by idx; subscript is idx - 1.
        sampled = [records[i - 1] for i in idxs]

        rendered = _render_trace(sampled, NUMERIC_FORMATS[numeric_format])
        rendered_row_count = len(sampled)
        rendered_margin_zero = sum(1 for r in sampled if r.margin == 0.0)
        rendered_new_bin = sum(1 for r in sampled if r.new_bin)

        cell: Dict[str, Any] = {
            "rule": rule,
            "rendered_char_count": len(rendered),
            "rendered_row_count": rendered_row_count,
            "rendered_margin_zero_count": rendered_margin_zero,
            "rendered_margin_zero_rate": (
                rendered_margin_zero / rendered_row_count
                if rendered_row_count
                else 0.0
            ),
            "rendered_new_bin_count": rendered_new_bin,
            "rendered_new_bin_rate": (
                rendered_new_bin / rendered_row_count
                if rendered_row_count
                else 0.0
            ),
            "status": "ok",
        }
        if row_count_cap is not None:
            cell["sampled_indices"] = idxs
        return cell
    except Exception as exc:  # noqa: BLE001 — failure is data, not a bug
        return {
            "rule": rule,
            "rendered_char_count": None,
            "rendered_row_count": None,
            "rendered_margin_zero_count": None,
            "rendered_margin_zero_rate": None,
            "rendered_new_bin_count": None,
            "rendered_new_bin_rate": None,
            "status": f"error:{type(exc).__name__}",
            "error_message": str(exc),
        }


def _instance_lookup() -> Dict[str, Mapping[str, Any]]:
    """Map qualified pool instance_ids → instance dicts (train_select)."""
    split = load_split("train_select")
    return {
        f"thesis_train_select:{inst['instance_id']}": inst
        for inst in split["instances"]
    }


def _measure_instance(
    instance_id: str,
    instance: Mapping[str, Any],
    incumbent_module: Any,
) -> Dict[str, Any]:
    """Extract the trace once and measure all 8 cells for this instance."""
    try:
        records = extract_incumbent_trace(instance, incumbent_module)
    except Exception as exc:  # noqa: BLE001
        # Whole instance failed to extract — emit one degenerate cell
        # entry per rule so the per-cell aggregator still sees a row.
        cells = []
        for nfmt_name in NUMERIC_FORMATS:
            for row_label, _row_cap in ROW_COUNTS:
                cells.append(
                    {
                        "rule": f"{nfmt_name}_{row_label}",
                        "rendered_char_count": None,
                        "rendered_row_count": None,
                        "rendered_margin_zero_count": None,
                        "rendered_margin_zero_rate": None,
                        "rendered_new_bin_count": None,
                        "rendered_new_bin_rate": None,
                        "status": f"error:{type(exc).__name__}",
                        "error_message": str(exc),
                    }
                )
        cells.sort(key=lambda c: c["rule"])
        return {
            "instance_id": instance_id,
            "n_items": int(instance["num_items"]),
            "trace_extracted": False,
            "extraction_error": f"{type(exc).__name__}: {exc!s}",
            "cells": cells,
        }

    cells: List[Dict[str, Any]] = []
    for nfmt_name in NUMERIC_FORMATS:
        for row_label, row_cap in ROW_COUNTS:
            rule = f"{nfmt_name}_{row_label}"
            cells.append(
                _measure_cell(records, rule, nfmt_name, row_label, row_cap)
            )
    cells.sort(key=lambda c: c["rule"])

    return {
        "instance_id": instance_id,
        "n_items": int(instance["num_items"]),
        "trace_extracted": True,
        "trace_row_count": len(records),
        "cells": cells,
    }


# --- Aggregation ------------------------------------------------------------


def _aggregate_cell(
    rule: str,
    numeric_format: str,
    row_count_label: str,
    row_count_cap_value: int,
    per_instance: Sequence[Mapping[str, Any]],
    full_lossless_aggregate: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Pool-level aggregate stats for one cell (numeric_format × row_count)."""
    char_counts: List[int] = []
    margin_zero_rates: List[float] = []
    new_bin_rates: List[float] = []
    n_failed = 0

    for entry in per_instance:
        cell = next(c for c in entry["cells"] if c["rule"] == rule)
        if cell["status"] != "ok":
            n_failed += 1
            continue
        char_counts.append(cell["rendered_char_count"])
        margin_zero_rates.append(cell["rendered_margin_zero_rate"])
        new_bin_rates.append(cell["rendered_new_bin_rate"])

    if char_counts:
        sorted_chars_desc = sorted(char_counts, reverse=True)
        max_4_char = (
            int(sum(sorted_chars_desc[:4]))
            if len(sorted_chars_desc) >= 4
            else None
        )
        mean_4_char = 4.0 * float(np.mean(char_counts))
    else:
        max_4_char = None
        mean_4_char = None

    margin_zero_stats = _percentile_stats(margin_zero_rates)
    new_bin_stats = _percentile_stats(new_bin_rates)

    if full_lossless_aggregate is None:
        # We are aggregating full_lossless itself; deltas are 0.
        margin_zero_delta: Optional[float] = 0.0
        new_bin_delta: Optional[float] = 0.0
    else:
        baseline_mz = full_lossless_aggregate["rendered_margin_zero_rate_stats"][
            "mean"
        ]
        baseline_nb = full_lossless_aggregate["rendered_new_bin_rate_stats"]["mean"]
        if margin_zero_stats["mean"] is None or baseline_mz is None:
            margin_zero_delta = None
        else:
            margin_zero_delta = margin_zero_stats["mean"] - baseline_mz
        if new_bin_stats["mean"] is None or baseline_nb is None:
            new_bin_delta = None
        else:
            new_bin_delta = new_bin_stats["mean"] - baseline_nb

    return {
        "rule": rule,
        "numeric_format": numeric_format,
        "row_count_cap": row_count_cap_value,
        "n_successful": len(char_counts),
        "n_failed": n_failed,
        "rendered_char_count_stats": _percentile_stats(char_counts),
        "rendered_margin_zero_rate_stats": margin_zero_stats,
        "rendered_new_bin_rate_stats": new_bin_stats,
        "k4_prompt_render_projection": {
            "mean_4_instance_char_sum": mean_4_char,
            "max_4_instance_char_sum": max_4_char,
        },
        "distortion_vs_full": {
            "margin_zero_rate_mean_delta": margin_zero_delta,
            "new_bin_rate_mean_delta": new_bin_delta,
        },
    }


def main() -> int:
    h_eoh_meta = get_h_eoh()
    h_eoh_module = load_heuristic_from_code(
        h_eoh_meta["code"], "h_eoh_for_render_rule_probe"
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
            for nfmt_name in NUMERIC_FORMATS:
                for row_label, _row_cap in ROW_COUNTS:
                    cells.append(
                        {
                            "rule": f"{nfmt_name}_{row_label}",
                            "rendered_char_count": None,
                            "rendered_row_count": None,
                            "rendered_margin_zero_count": None,
                            "rendered_margin_zero_rate": None,
                            "rendered_new_bin_count": None,
                            "rendered_new_bin_rate": None,
                            "status": "error:KeyError",
                            "error_message": (
                                f"instance_id {inst_id!r} not in train_select split"
                            ),
                        }
                    )
            cells.sort(key=lambda c: c["rule"])
            per_instance.append(
                {
                    "instance_id": inst_id,
                    "n_items": None,
                    "trace_extracted": False,
                    "extraction_error": (
                        f"KeyError: instance_id {inst_id!r} not in train_select split"
                    ),
                    "cells": cells,
                }
            )
            n_extract_failed += 1
            n_cell_failed += len(cells)
            continue

        entry = _measure_instance(inst_id, instance_map[inst_id], h_eoh_module)
        per_instance.append(entry)
        if entry["trace_extracted"]:
            n_extract_ok += 1
            n_cell_failed += sum(1 for c in entry["cells"] if c["status"] != "ok")
        else:
            n_extract_failed += 1
            n_cell_failed += len(entry["cells"])

    per_instance.sort(key=lambda e: e["instance_id"])

    # Aggregates: produce full_lossless first so the delta baseline
    # exists for the other 7 cells.
    cell_keys: List[Tuple[str, str, str, int]] = []
    for nfmt_name in NUMERIC_FORMATS:
        for row_label, row_cap in ROW_COUNTS:
            row_cap_value = 5000 if row_cap is None else row_cap
            cell_keys.append((f"{nfmt_name}_{row_label}", nfmt_name, row_label, row_cap_value))

    full_lossless_agg = _aggregate_cell(
        rule="lossless_full",
        numeric_format="lossless",
        row_count_label="full",
        row_count_cap_value=5000,
        per_instance=per_instance,
        full_lossless_aggregate=None,
    )

    cell_aggregates: List[Dict[str, Any]] = []
    for rule, nfmt, row_label, row_cap_value in cell_keys:
        if rule == "lossless_full":
            cell_aggregates.append(full_lossless_agg)
        else:
            cell_aggregates.append(
                _aggregate_cell(
                    rule=rule,
                    numeric_format=nfmt,
                    row_count_label=row_label,
                    row_count_cap_value=row_cap_value,
                    per_instance=per_instance,
                    full_lossless_aggregate=full_lossless_agg,
                )
            )

    cell_aggregates.sort(key=lambda c: c["rule"])

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
            "sampling_rule_description": (
                "First-20%-head plus uniform-stride tail; head = "
                "floor(0.2*cap) rows starting at idx=1, tail = "
                "remaining cap selected by "
                "np.linspace(head_count+1, 5000, tail_count, dtype=int) "
                "(includes idx=5000); union deduped; see render_rule_probe.py"
            ),
        },
        "cell_aggregates": cell_aggregates,
        "per_instance": per_instance,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    print(
        f"render_rule_probe: {n_extract_ok}/{len(per_instance)} instances "
        f"extracted ok, {n_extract_failed} failed; "
        f"{n_cell_failed} of {len(per_instance) * len(cell_keys)} per-cell "
        f"renders failed; wrote "
        f"{OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
