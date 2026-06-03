"""
thesis/code/chapter6/experiments/trace_stats_probe.py

One-shot pool-level probe for the chapter-6 trace extractor.

Runs ``extract_incumbent_trace(instance, h_eoh)`` across the 30
counterexample-pool instances and writes per-instance plus
pool-aggregate statistics to
``thesis/artifacts/chapter6_trace_stats.json``. The output is
the empirical input to the §7.4 rendering-rule lock decision
that follows in a separate task; this script measures, it does
not decide.

Usage:
    python -m thesis.code.chapter6.experiments.trace_stats_probe

The script overwrites the artifact each run. Per-instance
extraction failures are recorded in the artifact (status,
error_message) rather than raising; the script's exit code is
0 even if some instances fail, so that the artifact-as-data is
always produced. The one-line stderr summary at the end reports
the success / failure count.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

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
OUTPUT_PATH = ARTIFACTS_DIR / "chapter6_trace_stats.json"

PROBE_VERSION = "1.0"


def _percentile_stats(values: Sequence[float]) -> Dict[str, Optional[float]]:
    """min/max/mean/median/p25/p75/p90/p99 over a numeric sample.

    Returns a mapping with all eight keys present; values are
    ``None`` when ``values`` is empty.
    """
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


def _open_bins_length_stats(
    lengths: Sequence[int],
) -> Dict[str, Optional[float]]:
    """min/max/mean/median over ``len(open_bins)`` across a trace."""
    if not lengths:
        return {"min": None, "max": None, "mean": None, "median": None}
    arr = np.asarray(lengths, dtype=float)
    return {
        "min": float(arr.min()),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
    }


def _render_trace_naively(records: Sequence[DecisionRecord]) -> str:
    """Render a trace under the naive measurement format.

    One logical line per row, terminator ``\\n``. Numeric fields
    use ``repr`` for floats and ``str`` for ints; the boolean
    ``new_bin`` renders as the lowercase tokens ``true`` / ``false``.
    The format is for the char-count measurement only — it is not
    the production Level-2 prompt format, which is locked in a
    later task after the rendering-rule decision.
    """
    lines: List[str] = []
    for r in records:
        open_bins_str = "[" + ", ".join(repr(c) for c in r.open_bins) + "]"
        chose_str = r.chose if isinstance(r.chose, str) else str(r.chose)
        new_bin_str = "true" if r.new_bin else "false"
        lines.append(
            f"idx={r.idx} item={repr(r.item)} open_bins={open_bins_str} "
            f"chose={chose_str} winner={repr(r.score_winner)} "
            f"runner_up={repr(r.score_runner_up)} margin={repr(r.margin)} "
            f"cap_after={repr(r.cap_after)} new_bin={new_bin_str}"
        )
    return "".join(line + "\n" for line in lines)


def _instance_lookup() -> Dict[str, Mapping[str, Any]]:
    """Map qualified pool instance_ids → instance dicts.

    Pool entries reference instances by qualified IDs of the form
    ``thesis_train_select:thesis_train_select_5k_<n>``; the
    train_select split provides the instance contents.
    """
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
    """Run the extractor on one instance and produce its stats entry.

    On success, the returned mapping contains every per-instance
    key listed in the task spec with ``status == "ok"``. On
    failure, it returns a degenerate entry with ``status ==
    "error:<ExceptionClass>"`` and a populated ``error_message``;
    numeric fields are filled with ``None`` so the artifact's
    schema is uniform across rows.
    """
    try:
        records = extract_incumbent_trace(instance, incumbent_module)
    except Exception as exc:  # noqa: BLE001 — failure is data, not a bug
        return {
            "instance_id": instance_id,
            "n_items": int(instance["num_items"]),
            "trace_row_count": None,
            "trace_row_count_equals_n_items": False,
            "new_bin_decision_count": None,
            "existing_bin_decision_count": None,
            "final_bins_used": None,
            "margin_stats": _percentile_stats([]),
            "margin_zero_count": None,
            "margin_zero_rate": None,
            "open_bins_length_stats": _open_bins_length_stats([]),
            "naive_render_char_count": None,
            "status": f"error:{type(exc).__name__}",
            "error_message": str(exc),
        }

    n_items = int(instance["num_items"])
    row_count = len(records)
    new_bin_count = sum(1 for r in records if r.new_bin)
    margins = [r.margin for r in records]
    margin_zero_count = sum(1 for m in margins if m == 0.0)
    open_bins_lengths = [len(r.open_bins) for r in records]

    naive_text = _render_trace_naively(records)

    return {
        "instance_id": instance_id,
        "n_items": n_items,
        "trace_row_count": row_count,
        "trace_row_count_equals_n_items": row_count == n_items,
        "new_bin_decision_count": new_bin_count,
        "existing_bin_decision_count": row_count - new_bin_count,
        "final_bins_used": new_bin_count,
        "margin_stats": _percentile_stats(margins),
        "margin_zero_count": margin_zero_count,
        "margin_zero_rate": (
            margin_zero_count / row_count if row_count else 0.0
        ),
        "open_bins_length_stats": _open_bins_length_stats(open_bins_lengths),
        "naive_render_char_count": len(naive_text),
        "status": "ok",
    }


def _aggregate(per_instance: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Pool-level aggregate stats over the per-instance entries."""
    ok = [e for e in per_instance if e["status"] == "ok"]
    n_instances = len(per_instance)
    n_successful = len(ok)
    n_failed = n_instances - n_successful

    row_counts: List[int] = [e["trace_row_count"] for e in ok]
    char_counts: List[int] = [e["naive_render_char_count"] for e in ok]
    margin_zero_rates: List[float] = [e["margin_zero_rate"] for e in ok]

    sorted_chars_desc = sorted(char_counts, reverse=True)
    if len(sorted_chars_desc) >= 4:
        max_4_char = int(sum(sorted_chars_desc[:4]))
    else:
        max_4_char = None

    if char_counts:
        mean_4_char = 4.0 * float(np.mean(char_counts))
    else:
        mean_4_char = None

    return {
        "n_instances": n_instances,
        "n_successful": n_successful,
        "n_failed": n_failed,
        "total_trace_rows": int(sum(row_counts)),
        "trace_row_count_stats": _percentile_stats(row_counts),
        "naive_render_char_count_stats": _percentile_stats(char_counts),
        "margin_zero_rate_stats": _percentile_stats(margin_zero_rates),
        "k4_prompt_render_projection": {
            "mean_4_instance_char_sum": mean_4_char,
            "max_4_instance_char_sum": max_4_char,
        },
    }


def main() -> int:
    h_eoh_meta = get_h_eoh()
    h_eoh_module = load_heuristic_from_code(
        h_eoh_meta["code"], "h_eoh_for_trace_probe"
    )
    h_eoh_hash = h_eoh_meta["code_hash"]

    pool_bytes = POOL_PATH.read_bytes()
    pool_sha_prefix = hashlib.sha256(pool_bytes).hexdigest()[:12]

    pool = CounterexampleSet.from_json(pool_bytes.decode("utf-8"))
    instance_map = _instance_lookup()

    per_instance: List[Dict[str, Any]] = []
    succeeded = 0
    failed = 0

    for ce in pool:
        inst_id = ce.instance_id
        if inst_id not in instance_map:
            entry: Dict[str, Any] = {
                "instance_id": inst_id,
                "n_items": None,
                "trace_row_count": None,
                "trace_row_count_equals_n_items": False,
                "new_bin_decision_count": None,
                "existing_bin_decision_count": None,
                "final_bins_used": None,
                "margin_stats": _percentile_stats([]),
                "margin_zero_count": None,
                "margin_zero_rate": None,
                "open_bins_length_stats": _open_bins_length_stats([]),
                "naive_render_char_count": None,
                "status": "error:KeyError",
                "error_message": (
                    f"instance_id {inst_id!r} not present in "
                    "train_select split"
                ),
            }
            failed += 1
        else:
            entry = _measure_instance(inst_id, instance_map[inst_id], h_eoh_module)
            if entry["status"] == "ok":
                succeeded += 1
            else:
                failed += 1
        per_instance.append(entry)

    per_instance.sort(key=lambda e: e["instance_id"])

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
        },
        "pool_aggregates": _aggregate(per_instance),
        "per_instance": per_instance,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    print(
        f"trace_stats_probe: {succeeded}/{len(per_instance)} succeeded, "
        f"{failed} failed; wrote "
        f"{OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
