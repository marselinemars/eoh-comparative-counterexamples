"""§4.5.3 failure-as-catastrophe sensitivity analysis on the E1+E2
decomposition.

Re-runs the three matched-pair contrasts from §4.5.3 with sanitization
failures treated as catastrophic values rather than excluded:

  1. Full vs no-reference  (chapter5 stratified_representative L1 k=4
                            vs §4.5 E1 no-reference control)
  2. Full vs gap-only      (same full cell vs §4.5 E2 gap-only control)
  3. Gap-only vs no-reference  (E2 vs E1)

Substitution value: worst observed Δ_step in the pooled three-cell
dataset (sanitization-ok proposals only). Conservative because (a) it
uses a real observed value rather than an arbitrary number, (b) it
is applied uniformly across all failure substitutions, and (c) it
matches a real catastrophic-tail magnitude observed in the data.

Matched-pair design: pairs are (set_index, seed_index) coordinates,
identical across the three cells (set_seed shared).

Outputs:
  thesis/artifacts/e1_e2_failure_as_catastrophe.json

This is a read-only analysis: no LLM calls, no artifact modifications
to existing files.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Iterable

import numpy as np

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "thesis" / "results"
ARTIFACTS = REPO / "thesis" / "artifacts"


# ---------- Loaders ---------------------------------------------------------

def load_full_cell() -> list[dict]:
    """Load all chapter-5 stratified_representative L1 k=4 records."""
    cell_dir = RESULTS / "chapter5_primary_batch_gemini"
    out: list[dict] = []
    for set_idx in range(20):
        for seed_idx in range(3):
            f = cell_dir / f"stratified_representative_{set_idx}_{seed_idx}.json"
            if not f.exists():
                raise FileNotFoundError(f)
            rec = json.loads(f.read_text(encoding="utf-8"))
            out.append(rec)
    return out


def load_e1_cell() -> list[dict]:
    """Load all chapter4_noref (E1) records."""
    cell_dir = RESULTS / "chapter4_noref_primary_batch_gemini"
    out: list[dict] = []
    for set_idx in range(20):
        for seed_idx in range(3):
            f = cell_dir / f"set{set_idx:02d}_seed{seed_idx}.json"
            if not f.exists():
                raise FileNotFoundError(f)
            rec = json.loads(f.read_text(encoding="utf-8"))
            out.append(rec)
    return out


def load_e2_cell() -> list[dict]:
    """Load all chapter4_gaponly (E2) records."""
    cell_dir = RESULTS / "chapter4_gaponly_primary_batch_gemini"
    out: list[dict] = []
    for set_idx in range(20):
        for seed_idx in range(3):
            f = cell_dir / f"set{set_idx:02d}_seed{seed_idx}.json"
            if not f.exists():
                raise FileNotFoundError(f)
            rec = json.loads(f.read_text(encoding="utf-8"))
            out.append(rec)
    return out


# ---------- Record-level helpers --------------------------------------------

def is_sanitize_ok(rec: dict) -> bool:
    return rec.get("sanitization", {}).get("status") == "ok"


def delta_step_or_none(rec: dict) -> float | None:
    if not is_sanitize_ok(rec):
        return None
    d = rec.get("scoring", {}).get("delta_step")
    return float(d) if d is not None else None


def key_of(rec: dict) -> tuple[int, int]:
    return (int(rec["set_index"]), int(rec["seed_index"]))


# ---------- Matched-pair contrasts ------------------------------------------

def matched_pairs(
    cell_a: list[dict],
    cell_b: list[dict],
    catastrophe_value: float | None,
) -> list[tuple[tuple[int, int], float, float]]:
    """Return [(key, delta_a, delta_b)] for matched pairs.

    If catastrophe_value is None (main analysis): exclude pairs in which
    either side failed sanitization.
    If catastrophe_value is given (sensitivity): substitute failed
    proposals' delta_step with the catastrophe value; keep all pairs.
    """
    by_a = {key_of(r): r for r in cell_a}
    by_b = {key_of(r): r for r in cell_b}
    common_keys = sorted(set(by_a.keys()) & set(by_b.keys()))

    pairs: list[tuple[tuple[int, int], float, float]] = []
    for k in common_keys:
        ra, rb = by_a[k], by_b[k]
        da = delta_step_or_none(ra)
        db = delta_step_or_none(rb)
        if catastrophe_value is None:
            if da is None or db is None:
                continue
            pairs.append((k, da, db))
        else:
            da_use = catastrophe_value if da is None else da
            db_use = catastrophe_value if db is None else db
            pairs.append((k, da_use, db_use))
    return pairs


def bootstrap_paired_mean_ci(
    diffs: np.ndarray, n_resamples: int = 10000, seed: int = 2026
) -> tuple[float, float, float]:
    """Return (mean, ci_low, ci_high) under percentile bootstrap."""
    rng = np.random.default_rng(seed)
    n = len(diffs)
    means = np.empty(n_resamples)
    for r in range(n_resamples):
        idx = rng.integers(0, n, n)
        means[r] = diffs[idx].mean()
    lo = float(np.percentile(means, 2.5))
    hi = float(np.percentile(means, 97.5))
    return (float(diffs.mean()), lo, hi)


def contrast(
    cell_a: list[dict],
    cell_b: list[dict],
    catastrophe_value: float | None,
) -> dict:
    pairs = matched_pairs(cell_a, cell_b, catastrophe_value)
    diffs = np.array([da - db for (_, da, db) in pairs], dtype=float)
    mean, lo, hi = bootstrap_paired_mean_ci(diffs)
    n_failures_substituted = 0
    if catastrophe_value is not None:
        by_a = {key_of(r): r for r in cell_a}
        by_b = {key_of(r): r for r in cell_b}
        common_keys = sorted(set(by_a.keys()) & set(by_b.keys()))
        for k in common_keys:
            if not is_sanitize_ok(by_a[k]) or not is_sanitize_ok(by_b[k]):
                n_failures_substituted += 1
    return {
        "n_pairs": int(len(diffs)),
        "n_failures_substituted": n_failures_substituted,
        "mean": mean,
        "ci_low": lo,
        "ci_high": hi,
        "excludes_zero": bool((lo > 0) or (hi < 0)),
    }


# ---------- Catastrophe value -----------------------------------------------

def pooled_worst_delta_step(cells: Iterable[list[dict]]) -> tuple[float, str]:
    """Return (worst observed Δ_step value, label of source cell)."""
    worst = None
    src = None
    for cell, label in cells:
        for r in cell:
            d = delta_step_or_none(r)
            if d is None:
                continue
            if worst is None or d < worst:
                worst = d
                src = label
    return (float(worst), str(src))


# ---------- Main ------------------------------------------------------------

def main() -> None:
    full = load_full_cell()
    e1 = load_e1_cell()
    e2 = load_e2_cell()

    print(f"Loaded full={len(full)}  E1={len(e1)}  E2={len(e2)} records")
    n_full_ok = sum(1 for r in full if is_sanitize_ok(r))
    n_e1_ok = sum(1 for r in e1 if is_sanitize_ok(r))
    n_e2_ok = sum(1 for r in e2 if is_sanitize_ok(r))
    print(f"  sanitize-ok: full={n_full_ok}  E1={n_e1_ok}  E2={n_e2_ok}")
    print(f"  failures   : full={len(full) - n_full_ok}  "
          f"E1={len(e1) - n_e1_ok}  E2={len(e2) - n_e2_ok}")

    catastrophe_value, catastrophe_source = pooled_worst_delta_step([
        (full, "full"), (e1, "E1"), (e2, "E2")
    ])
    print(f"\nCatastrophe value (worst observed Δ_step): {catastrophe_value:+.4f}")
    print(f"Source cell: {catastrophe_source}")

    contrasts_spec = [
        ("full_vs_no_reference", full, e1),
        ("full_vs_gap_only", full, e2),
        ("gap_only_vs_no_reference", e2, e1),
    ]

    main_analysis: dict[str, dict] = {}
    sensitivity_analysis: dict[str, dict] = {}

    print("\nMain analysis (failures excluded):")
    for name, ca, cb in contrasts_spec:
        r = contrast(ca, cb, catastrophe_value=None)
        main_analysis[name] = r
        print(f"  {name:30s} n={r['n_pairs']:3d} mean={r['mean']:+8.2f} "
              f"CI=[{r['ci_low']:+8.2f}, {r['ci_high']:+8.2f}]  "
              f"excl0={r['excludes_zero']}")

    print("\nSensitivity analysis (failures substituted with catastrophe value):")
    for name, ca, cb in contrasts_spec:
        r = contrast(ca, cb, catastrophe_value=catastrophe_value)
        sensitivity_analysis[name] = r
        print(f"  {name:30s} n={r['n_pairs']:3d} subst={r['n_failures_substituted']:2d} "
              f"mean={r['mean']:+8.2f} "
              f"CI=[{r['ci_low']:+8.2f}, {r['ci_high']:+8.2f}]  "
              f"excl0={r['excludes_zero']}")

    # Ordering preservation: for each contrast, did the sign of the
    # point estimate stay the same?
    ordering_preserved = all(
        (np.sign(main_analysis[n]["mean"]) == np.sign(sensitivity_analysis[n]["mean"]))
        or (main_analysis[n]["mean"] == 0 and sensitivity_analysis[n]["mean"] == 0)
        for n, _, _ in contrasts_spec
    )

    out = {
        "catastrophe_value": catastrophe_value,
        "catastrophe_source_cell": catastrophe_source,
        "main_analysis": main_analysis,
        "sensitivity_analysis": sensitivity_analysis,
        "ordering_preserved": bool(ordering_preserved),
    }

    out_path = ARTIFACTS / "e1_e2_failure_as_catastrophe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
