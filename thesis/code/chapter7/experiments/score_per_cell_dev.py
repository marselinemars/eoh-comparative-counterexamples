"""thesis/code/chapter7/experiments/score_per_cell_dev.py

Chapter 7 §6.3 / Stage-2-task-spec dev scoring: for each of the 14
primary cells, find the proposal with the highest Δ_step on
``train_step``, score it against the ``dev`` split, and write
the resulting Δ_dev back into the per-proposal record AND into a
top-level summary artifact.

This is the read-only-once dev evaluation per the design doc:
the post-hoc full-dev pass on every accepted validation step is
§18.8 and is out of scope here.

Usage::

    python -m thesis.code.chapter7.experiments.score_per_cell_dev
"""
from __future__ import annotations

import json
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from thesis.code.evaluation import bins_used  # noqa: E402
from thesis.code.incumbents import get_h_eoh  # noqa: E402
from thesis.code.score_cache import ScoreCache  # noqa: E402
from thesis.code.splits import load_split, qualified_instance_id  # noqa: E402

RESULTS_DIR = REPO_ROOT / "thesis" / "results" / "chapter7_primary_batch_gemini"
ARTIFACTS_DIR = REPO_ROOT / "thesis" / "artifacts"
DEV_SUMMARY_PATH = ARTIFACTS_DIR / "chapter7_per_cell_dev_scoring.json"

CELL_IDS = [f"CH7-{i:02d}" for i in range(1, 15)]


def _ok_records_by_cell() -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {cid: [] for cid in CELL_IDS}
    for cid in CELL_IDS:
        for path in sorted(RESULTS_DIR.glob(f"{cid}_set*.json")):
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            san = d.get("sanitization") or {}
            if san.get("status") != "ok":
                continue
            d["_path"] = str(path)
            out[cid].append(d)
    return out


def _delta_step(rec: Dict[str, Any]) -> Optional[float]:
    s = rec.get("scoring") or {}
    val = s.get("delta_step")
    return float(val) if isinstance(val, (int, float)) else None


def _score_on_dev(
    code: str,
    proposal_hash: str,
    cache: ScoreCache,
    dev_instances: List[Dict[str, Any]],
) -> Tuple[List[int], float]:
    mod = types.ModuleType(f"proposal_{proposal_hash}")
    exec(compile(code, f"<{proposal_hash}>", "exec"), mod.__dict__)
    per_instance: List[int] = []
    for inst in dev_instances:
        qid = qualified_instance_id("dev", inst["instance_id"])
        b = cache.get_or_compute(
            proposal_hash, qid, lambda i=inst: bins_used(mod, i)
        )
        per_instance.append(int(b))
    return per_instance, sum(per_instance) / len(per_instance)


def _score_baseline_dev(
    incumbent_module, incumbent_hash: str, cache: ScoreCache,
    dev_instances: List[Dict[str, Any]],
) -> Tuple[List[int], float]:
    per_instance: List[int] = []
    for inst in dev_instances:
        qid = qualified_instance_id("dev", inst["instance_id"])
        b = cache.get_or_compute(
            incumbent_hash, qid, lambda i=inst: bins_used(incumbent_module, i)
        )
        per_instance.append(int(b))
    return per_instance, sum(per_instance) / len(per_instance)


def main() -> int:
    by_cell = _ok_records_by_cell()
    cache = ScoreCache()
    dev = load_split("dev")
    dev_instances = dev["instances"]
    print(
        f"Loaded {sum(len(v) for v in by_cell.values())} sanitize-ok records "
        f"across {len(by_cell)} cells; dev split has {len(dev_instances)} "
        f"instances",
        file=sys.stderr,
    )
    h_eoh = get_h_eoh()
    incumbent_hash = h_eoh["code_hash"]
    incumbent_module = _build_incumbent_module(h_eoh)
    baseline_per_instance, baseline_mean = _score_baseline_dev(
        incumbent_module, incumbent_hash, cache, dev_instances
    )
    print(
        f"Baseline (h_eoh) dev mean bins_used = {baseline_mean:.4f}",
        file=sys.stderr,
    )

    out_per_cell: Dict[str, Dict[str, Any]] = {}
    for cid, recs in by_cell.items():
        if not recs:
            out_per_cell[cid] = {"status": "no_sanitize_ok_records"}
            continue
        # Highest Δ_step (most positive = best on train_step).
        scored = [(r, _delta_step(r)) for r in recs]
        scored = [(r, ds) for r, ds in scored if ds is not None]
        if not scored:
            out_per_cell[cid] = {"status": "no_delta_step_records"}
            continue
        best_rec, best_ds = max(scored, key=lambda t: t[1])
        proposal_hash = best_rec.get("proposal_hash")
        cleaned_code = (best_rec.get("sanitization") or {}).get("cleaned_code")
        if not (proposal_hash and cleaned_code):
            out_per_cell[cid] = {
                "status": "missing_hash_or_code",
                "set_index": best_rec.get("set_index"),
                "seed_index": best_rec.get("seed_index"),
            }
            continue
        per_inst, prop_mean = _score_on_dev(
            cleaned_code, proposal_hash, cache, dev_instances
        )
        delta_dev = baseline_mean - prop_mean
        # Update record on disk in place: add scoring.delta_dev.
        path = Path(best_rec["_path"])
        try:
            disk = json.loads(path.read_text(encoding="utf-8"))
            scoring = disk.get("scoring") or {}
            scoring["delta_dev"] = float(delta_dev)
            scoring["dev_per_instance"] = per_inst
            scoring["dev_mean_bins"] = float(prop_mean)
            scoring["dev_baseline_mean_bins"] = float(baseline_mean)
            disk["scoring"] = scoring
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(disk, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)
        except Exception as exc:
            print(f"  [{cid}] warn: failed to update record on disk: {exc}",
                  file=sys.stderr)
        out_per_cell[cid] = {
            "status": "ok",
            "set_index": best_rec.get("set_index"),
            "seed_index": best_rec.get("seed_index"),
            "proposal_hash": proposal_hash,
            "delta_step": float(best_ds),
            "delta_gate": (
                float((best_rec.get("scoring") or {}).get("delta_gate"))
                if (best_rec.get("scoring") or {}).get("delta_gate") is not None
                else None
            ),
            "delta_dev": float(delta_dev),
            "dev_mean_bins": float(prop_mean),
            "dev_baseline_mean_bins": float(baseline_mean),
            "n_dev_instances": len(dev_instances),
        }
        print(
            f"  {cid}: top_set={best_rec.get('set_index'):03d} "
            f"top_seed={best_rec.get('seed_index'):03d} "
            f"Δ_step={best_ds:+.2f} Δ_dev={delta_dev:+.2f}",
            file=sys.stderr,
        )

    cache.save()

    summary = {
        "schema_version": 1,
        "chapter": "chapter7",
        "design_doc_section": "§6.3 / Stage 2 dev scoring",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "incumbent_hash": incumbent_hash,
        "dev_split_size": len(dev_instances),
        "baseline_mean_bins_dev": float(baseline_mean),
        "per_cell": out_per_cell,
    }
    DEV_SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"Wrote {DEV_SUMMARY_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
