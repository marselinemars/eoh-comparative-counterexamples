"""Tests for thesis/code/chapter5/analysis.py."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict

import pytest

from thesis.code.chapter5.analysis import (
    H_EOH_CODE_HASH,
    build_combined_summary,
    build_summary,
    build_validation_summary,
    compute_cliffs_delta,
    compute_distribution_stats,
    compute_iqr_overlap,
    is_argmax_equivalent_to_h_eoh,
    load_primary_batch_proposals,
    load_validation_trajectories,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
PRIMARY_BATCH_DIR = (
    REPO_ROOT / "thesis" / "results" / "chapter5_primary_batch_gemini"
)


# --- compute_distribution_stats -----------------------------------


def test_distribution_stats_on_known_values():
    # Values: 0, 10, 20, ..., 90, plus a catastrophic -100 and a
    # positive-tail 100. n=12.
    values = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, -100, 100]
    s = compute_distribution_stats(values)
    assert s["n"] == 12
    # Median of 12 sorted values = mean of 6th and 7th.
    # sorted: [-100, 0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    # pos 6 (0-idx 5) = 40, pos 7 (0-idx 6) = 50, median = 45
    assert s["median"] == pytest.approx(45.0)
    # Mean = sum/12 = 450/12 = 37.5
    assert s["mean"] == pytest.approx(37.5)
    # IQR = p75 - p25. numpy default linear interp:
    # p25 = 17.5, p75 = 72.5 → IQR = 55
    assert s["iqr"] == pytest.approx(55.0)
    # positive_tail_mass: values > 0 → 10 of 12 (the -100 and 0 out)
    assert s["positive_tail_mass"] == pytest.approx(10 / 12)
    # near_parity_mass: |v| ≤ 5 → only the 0 → 1/12
    assert s["near_parity_mass"] == pytest.approx(1 / 12)
    # catastrophic_tail_mass: v < -50 → only -100 → 1/12
    assert s["catastrophic_tail_mass"] == pytest.approx(1 / 12)
    # Trimmed mean at 10% → drop 1 top + 1 bottom (k=floor(12*0.1)=1)
    # drops -100 and 100; average of [0..90] = 45.
    assert s["trimmed_mean_10pct"] == pytest.approx(45.0)


def test_distribution_stats_empty():
    s = compute_distribution_stats([])
    assert s["n"] == 0
    assert s["mean"] == 0.0


# --- compute_cliffs_delta -----------------------------------------


def test_cliffs_delta_xs_dominate():
    assert compute_cliffs_delta([1, 2, 3], [0, 0, 0]) == pytest.approx(1.0)


def test_cliffs_delta_ys_dominate():
    assert compute_cliffs_delta([1, 2, 3], [4, 5, 6]) == pytest.approx(-1.0)


def test_cliffs_delta_no_dominance():
    # Identical lists → every xs_i vs ys_j has one match (tie) and
    # symmetric wins/losses; net zero.
    assert compute_cliffs_delta([1, 2, 3], [1, 2, 3]) == pytest.approx(0.0)


# --- compute_iqr_overlap ------------------------------------------


def test_iqr_overlap_identical():
    xs = list(range(100))
    ys = list(range(100))
    assert compute_iqr_overlap(xs, ys) == pytest.approx(1.0)


def test_iqr_overlap_disjoint():
    xs = list(range(0, 11))
    ys = list(range(20, 31))
    assert compute_iqr_overlap(xs, ys) == pytest.approx(0.0)


def test_iqr_overlap_partial():
    # xs: 0..10, p25=2.5, p75=7.5, IQR band [2.5, 7.5]
    # ys: 5..15, p25=7.5, p75=12.5, IQR band [7.5, 12.5]
    # overlap_range = max(0, min(7.5,12.5) - max(2.5,7.5))
    #               = max(0, 7.5 - 7.5) = 0
    # total_range = 12.5 - 2.5 = 10
    # overlap = 0/10 = 0
    xs = list(range(0, 11))
    ys = list(range(5, 16))
    assert compute_iqr_overlap(xs, ys) == pytest.approx(0.0)

    # Shift ys down by 2: 3..13, p25=5.5, p75=10.5
    # overlap = min(7.5,10.5)-max(2.5,5.5) = 7.5-5.5 = 2
    # total = 10.5-2.5 = 8
    # overlap = 2/8 = 0.25
    ys2 = list(range(3, 14))
    assert compute_iqr_overlap(xs, ys2) == pytest.approx(0.25)


# --- full load + summary pipeline ---------------------------------


def _write_fake_record(
    path: Path,
    strategy: str,
    set_index: int,
    seed_index: int,
    delta_step: float,
    status: str = "ok",
    per_instance_bins_step: list[int] | None = None,
    per_instance_bins_gate: list[int] | None = None,
    proposal_hash: str | None = None,
) -> None:
    record: Dict[str, Any] = {
        "strategy_name": strategy,
        "set_index": set_index,
        "seed_index": seed_index,
        "sanitization": {"status": status},
        "proposal_hash": proposal_hash or f"h_{strategy}_{seed_index}",
        "scoring": {
            "delta_step": delta_step,
            "delta_gate": delta_step * 0.9,
            "generalization_gap": delta_step * 0.1,
            "win_rate_step": 0.5 if delta_step >= 0 else 0.1,
            "per_instance_bins_proposal_train_step": per_instance_bins_step,
            "per_instance_bins_proposal_train_gate": per_instance_bins_gate,
        } if status == "ok" else None,
    }
    path.write_text(json.dumps(record), encoding="utf-8")


# --- argmax-equivalence tests -------------------------------------


def test_is_argmax_equivalent_identical():
    assert is_argmax_equivalent_to_h_eoh(
        [2034, 2050, 2012], [2034, 2050, 2012]
    ) is True


def test_is_argmax_equivalent_single_diff():
    assert is_argmax_equivalent_to_h_eoh(
        [2034, 2050, 2012], [2034, 2050, 2013]
    ) is False


def test_argmax_equivalent_count_and_distinct_subset(tmp_path: Path):
    """Fixture: 5 proposals, 2 match h_eoh's per-instance bins.
    Verify counts and the argmax-distinct distribution.n."""
    H_STEP = [100, 101, 102]
    H_GATE = [200, 201, 202]
    # Two matching (delta_step=0, bins == h_eoh)
    _write_fake_record(
        tmp_path / "uniform_random_0_0.json",
        "uniform_random", 0, 0, 0.0,
        per_instance_bins_step=H_STEP,
        per_instance_bins_gate=H_GATE,
        proposal_hash="eq_hash_A",
    )
    _write_fake_record(
        tmp_path / "uniform_random_0_1.json",
        "uniform_random", 0, 1, 0.0,
        per_instance_bins_step=H_STEP,
        per_instance_bins_gate=H_GATE,
        proposal_hash="eq_hash_B",
    )
    # Three distinct (bins differ)
    _write_fake_record(
        tmp_path / "uniform_random_0_2.json",
        "uniform_random", 0, 2, -1.0,
        per_instance_bins_step=[101, 101, 102],
        per_instance_bins_gate=H_GATE,
        proposal_hash="d1",
    )
    _write_fake_record(
        tmp_path / "uniform_random_0_3.json",
        "uniform_random", 0, 3, +3.0,
        per_instance_bins_step=[99, 101, 99],
        per_instance_bins_gate=H_GATE,
        proposal_hash="d2",
    )
    _write_fake_record(
        tmp_path / "uniform_random_0_4.json",
        "uniform_random", 0, 4, -10.0,
        per_instance_bins_step=[110, 110, 110],
        per_instance_bins_gate=H_GATE,
        proposal_hash="d3",
    )

    proposals, _ = load_primary_batch_proposals(tmp_path)
    summary = build_summary(
        proposals,
        h_eoh_per_instance_by_split={
            "train_step": H_STEP,
            "train_gate": H_GATE,
        },
    )
    ps = summary["per_strategy"]["uniform_random"]
    assert ps["argmax_equivalent_count"] == 2
    assert ps["argmax_equivalent_rate"] == pytest.approx(0.4)
    assert ps["argmax_distinct_count"] == 3
    # argmax-distinct distribution sees only the 3 distinct Δ_step values
    dist = ps["argmax_distinct_distribution_delta_step"]
    assert dist["n"] == 3
    # aggregate
    agg = summary["aggregate_observations"]["argmax_equivalence"]
    assert agg["total_argmax_equivalent_on_train_step"] == 2
    assert agg["distinct_code_hashes_among_argmax_equivalent"] == 2


def test_build_summary_on_fake_fixture(tmp_path: Path):
    # Three strategies, three records each.
    for sd in range(3):
        _write_fake_record(
            tmp_path / f"worst_only_0_{sd}.json",
            "worst_only", 0, sd, -10.0 + sd,
        )
        _write_fake_record(
            tmp_path / f"uniform_random_0_{sd}.json",
            "uniform_random", 0, sd, 2.0 + sd,
        )
        _write_fake_record(
            tmp_path / f"stratified_representative_0_{sd}.json",
            "stratified_representative", 0, sd, 0.0,
        )
    # And one non-ok record that must be excluded.
    _write_fake_record(
        tmp_path / "worst_only_0_99.json",
        "worst_only", 0, 99, 0.0, status="failed_parse",
    )

    proposals, skipped = load_primary_batch_proposals(tmp_path)
    assert len(skipped) == 1  # the failed_parse record
    assert sum(len(v) for v in proposals.values()) == 9

    summary = build_summary(proposals, batch_id="test_fixture")
    assert summary["batch_id"] == "test_fixture"
    assert summary["n_proposals"] == 9
    assert summary["n_strategies"] == 3
    assert set(summary["strategies"]) == {
        "worst_only", "uniform_random", "stratified_representative"
    }
    # Per-strategy shape
    for s in summary["strategies"]:
        ps = summary["per_strategy"][s]
        assert ps["n_ok"] == 3
        assert "mean" in ps["delta_step"]
        assert "iqr" in ps["delta_step"]
    # Pairwise dicts cover C(3,2) = 3 pairs.
    assert len(summary["pairwise_cliffs_delta"]["delta_step"]) == 3
    assert len(summary["pairwise_iqr_overlap"]["delta_step"]) == 3
    # Aggregate observation populated (worst_only is the only
    # pure-loss strategy in the fixture).
    agg = summary["aggregate_observations"]["mixed_composition_vs_pure_loss"]
    assert agg["pure_loss_strategies"] == ["worst_only"]
    assert set(agg["mixed_composition_strategies"]) == {
        "uniform_random", "stratified_representative"
    }


# --- integration: real primary batch (skipped if absent) ----------


@pytest.mark.skipif(
    not PRIMARY_BATCH_DIR.exists(),
    reason="primary batch results not present on this checkout",
)
def test_integration_real_primary_batch_shape():
    proposals, skipped = load_primary_batch_proposals(PRIMARY_BATCH_DIR)
    assert len(proposals) >= 1
    summary = build_summary(proposals)
    # Real batch was 5 strategies (most_discriminative dropped).
    assert summary["n_strategies"] == 5
    assert "worst_only" in summary["strategies"]
    # Each strategy has a populated delta_step stats block.
    for s in summary["strategies"]:
        assert summary["per_strategy"][s]["delta_step"]["n"] == 60


# --- validation loader / summary tests ----------------------------


def _write_fake_trajectory_summary(
    path: Path,
    strategy: str,
    trajectory_index: int,
    reason_counts: Dict[str, int],
    delta_step_cumulative: float,
    final_incumbent_hash: str,
    steps: list | None = None,
) -> None:
    rec = {
        "strategy_name": strategy,
        "trajectory_index": trajectory_index,
        "steps": steps or [],
        "acceptance_reason_counts": reason_counts,
        "final_incumbent_hash": final_incumbent_hash,
        "delta_step_cumulative": delta_step_cumulative,
    }
    path.write_text(json.dumps(rec), encoding="utf-8")


def test_load_validation_trajectories_structure(tmp_path: Path):
    _write_fake_trajectory_summary(
        tmp_path / "uniform_random_traj0_trajectory_summary.json",
        "uniform_random", 0,
        {"accepted_improvement": 1, "rejected_regression": 2},
        +3.0, "deadbeef0001",
        steps=[
            {"step_index": 1, "accepted": True,
             "acceptance_reason": "accepted_improvement"},
            {"step_index": 2, "accepted": False,
             "acceptance_reason": "rejected_regression"},
            {"step_index": 3, "accepted": False,
             "acceptance_reason": "rejected_regression"},
        ],
    )
    trajs, skipped = load_validation_trajectories(tmp_path)
    assert skipped == []
    assert list(trajs.keys()) == ["uniform_random"]
    assert len(trajs["uniform_random"]) == 1
    t = trajs["uniform_random"][0]
    assert t["trajectory_index"] == 0
    assert t["delta_step_cumulative"] == pytest.approx(3.0)
    assert len(t["steps"]) == 3


def test_build_validation_summary_acceptance_counts(tmp_path: Path):
    # One strategy, two trajectories, hand-crafted reason counts.
    _write_fake_trajectory_summary(
        tmp_path / "uniform_random_traj0_trajectory_summary.json",
        "uniform_random", 0,
        {"accepted_improvement": 2, "rejected_regression": 3},
        +5.0, "abc0",
    )
    _write_fake_trajectory_summary(
        tmp_path / "uniform_random_traj1_trajectory_summary.json",
        "uniform_random", 1,
        {"rejected_regression": 5},
        +0.0, H_EOH_CODE_HASH,
    )
    trajs, _ = load_validation_trajectories(tmp_path)
    summary = build_validation_summary(trajs)
    ps = summary["per_strategy"]["uniform_random"]
    assert ps["n_trajectories"] == 2
    assert ps["n_accepted_steps"] == 2
    assert ps["n_rejected_steps"] == 8
    assert ps["acceptance_rate"] == pytest.approx(2 / 10)
    assert ps["n_trajectories_that_moved_off_h_eoh"] == 1
    assert ps["mean_delta_step_cumulative"] == pytest.approx(2.5)
    agg = summary["aggregate"]
    assert agg["total_acceptances"] == 2
    assert agg["total_rejections"] == 8
    assert agg["total_accepted_behavioral_change"] == 0
    assert agg["cross_strategy_ranking_by_mean_cumulative"] == [
        "uniform_random"
    ]


def test_build_summary_combines_primary_and_validation(tmp_path: Path):
    # Minimal primary fixture
    primary_dir = tmp_path / "primary"
    primary_dir.mkdir()
    for sd in range(3):
        _write_fake_record(
            primary_dir / f"uniform_random_0_{sd}.json",
            "uniform_random", 0, sd, -1.0 * sd,
            per_instance_bins_step=[100 + sd, 101, 102],
            per_instance_bins_gate=[200, 201, 202],
        )
    # Minimal validation fixture
    validation_dir = tmp_path / "validation"
    validation_dir.mkdir()
    _write_fake_trajectory_summary(
        validation_dir / "uniform_random_traj0_trajectory_summary.json",
        "uniform_random", 0,
        {"accepted_improvement": 1, "rejected_regression": 4},
        +2.0, "abc0",
    )

    primary_proposals, _ = load_primary_batch_proposals(primary_dir)
    validation_trajectories, _ = load_validation_trajectories(
        validation_dir
    )
    combined = build_combined_summary(
        primary_proposals,
        validation_trajectories,
        h_eoh_per_instance_by_split={
            "train_step": [100, 101, 102],
            "train_gate": [200, 201, 202],
        },
    )
    assert set(combined.keys()) == {
        "primary_batch",
        "validation_batch",
        "cross_batch_observations",
    }
    # Primary sub-summary shape
    assert "strategies" in combined["primary_batch"]
    assert "per_strategy" in combined["primary_batch"]
    # Validation sub-summary shape
    assert combined["validation_batch"]["per_strategy"][
        "uniform_random"
    ]["n_trajectories"] == 1
    # Cross-batch observation shape
    assert (
        "rank_inversions" in combined["cross_batch_observations"]
    )
