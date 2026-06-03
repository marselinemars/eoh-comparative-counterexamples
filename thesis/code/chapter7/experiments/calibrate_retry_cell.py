"""thesis/code/chapter7/experiments/calibrate_retry_cell.py

Retry a single calibration-probe cell after a transient Vertex
429. Loads the existing
``thesis/artifacts/chapter7_calibration_probe.json``, reruns
the named cell, replaces its record, recomputes the verdict, and
writes the artifact back.

Usage::

    python -m thesis.code.chapter7.experiments.calibrate_retry_cell calib_strat_L2_k4

This is the precedent ch5/ch6 used for retrying transiently-
failed cells without rerunning the whole batch (analogous to ch6's
``chapter6_smart_resume.py``). It does not change the
calibration-probe semantics; the per-cell record schema is
identical to a first-attempt record except for an added
``retried_due_to`` field documenting the prior failure.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(REPO_ROOT / ".env")

from thesis.code.chapter6.batch_runner import _build_incumbent_module  # noqa: E402
from thesis.code.chapter7.experiments.calibrate_token_counts import (  # noqa: E402
    PROBE_PATH,
    _build_instance_lookup,
    _build_set_index_lookup,
    _cell_definitions,
    _load_sets_artifact,
    _make_call,
    _resolve_reference_source,
    _summarize_verdict,
)
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import get_h_eoh  # noqa: E402


def main(target_cell_id: str) -> int:
    if not PROBE_PATH.exists():
        raise RuntimeError(
            f"No probe artifact at {PROBE_PATH}; run "
            "calibrate_token_counts first."
        )
    probe = json.loads(PROBE_PATH.read_text(encoding="utf-8"))

    target_idx = None
    for i, c in enumerate(probe["cells"]):
        if c["cell_id"] == target_cell_id:
            target_idx = i
            break
    if target_idx is None:
        raise RuntimeError(
            f"Cell {target_cell_id!r} not found in probe artifact"
        )
    prior_record = probe["cells"][target_idx]
    prior_error = prior_record.get("api_error")

    cell_def = next(
        c for c in _cell_definitions() if c["cell_id"] == target_cell_id
    )
    artifact = _load_sets_artifact()
    set_lookup = _build_set_index_lookup(artifact)
    instance_lookup = _build_instance_lookup()
    h_eoh = get_h_eoh()
    incumbent_module = _build_incumbent_module(h_eoh)
    incumbent_source = h_eoh["code"]
    reference_source = _resolve_reference_source()

    key = (
        f"{cell_def['strategy']}@k={cell_def['k']}"
        f"@set={cell_def['set_index']:02d}"
    )
    ce_set = set_lookup[key]
    print(
        f"Retrying {target_cell_id} (set key {key})...",
        file=sys.stderr,
    )
    new_record = _make_call(
        cell=cell_def,
        counterexample_set=ce_set,
        incumbent_source=incumbent_source,
        reference_source=reference_source,
        incumbent_module=incumbent_module,
        instance_lookup=instance_lookup,
    )
    new_record["retried_due_to"] = prior_error
    print(
        f"  prompt_tokens={new_record.get('prompt_tokens')} "
        f"sanitize={new_record.get('sanitize_status')} "
        f"finish={new_record.get('finish_reason')} "
        f"api_error={bool(new_record.get('api_error'))}",
        file=sys.stderr,
    )

    probe["cells"][target_idx] = new_record
    verdict = _summarize_verdict(probe["cells"])
    probe["verdict"] = verdict["verdict"]
    probe["violators"] = verdict["violators"]
    probe["sanitization_failures"] = verdict["sanitization_failures"]
    probe["api_errors"] = verdict["api_errors"]
    payload = json.dumps(probe, indent=2, sort_keys=True)
    PROBE_PATH.write_text(payload, encoding="utf-8")
    artifact_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    print(file=sys.stderr)
    print(f"Verdict: {verdict['verdict']}", file=sys.stderr)
    print(
        f"Wrote {PROBE_PATH.relative_to(REPO_ROOT).as_posix()} "
        f"(sha256[:12] = {artifact_hash})",
        file=sys.stderr,
    )
    return 0 if not verdict["violators"] and not verdict["api_errors"] else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            f"Usage: {sys.argv[0]} <cell_id>",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
