from __future__ import annotations

import sys
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
REFINEMENT_DIR = TESTS_DIR.parent
if str(REFINEMENT_DIR) not in sys.path:
    sys.path.insert(0, str(REFINEMENT_DIR))

from select_failure_cases import (
    format_failure_case_preview,
    format_selection_summary_preview,
    select_failure_cases,
)


def make_case(
    instance_id: str,
    *,
    objective_gap: float,
    objective_value: float,
    bins_used: int | None = None,
) -> dict[str, object]:
    bins_used = int(objective_value) if bins_used is None else bins_used
    return {
        "instance_id": instance_id,
        "dataset_name": "toy",
        "case_name": instance_id.split("/")[-1],
        "capacity": 10.0,
        "num_items": 4,
        "bins_used": bins_used,
        "lower_bound": 2.0,
        "objective_gap": objective_gap,
        "objective_value": objective_value,
    }


class FailureSelectionTests(unittest.TestCase):
    def test_zero_gap_cases_excluded_when_failures_exist(self):
        case_results = [
            make_case("toy/case_0", objective_gap=0.0, objective_value=2.0),
            make_case("toy/case_1", objective_gap=0.5, objective_value=3.0),
            make_case("toy/case_2", objective_gap=0.25, objective_value=2.5),
        ]

        selection = select_failure_cases(case_results, top_k=3)
        selected_ids = [case["instance_id"] for case in selection["selected_failure_cases"]]

        self.assertEqual(selected_ids, ["toy/case_1", "toy/case_2"])
        self.assertFalse(selection["selection_summary"]["fallback_all_instances_used"])

    def test_top_k_selection_comes_from_failure_pool(self):
        case_results = [
            make_case("toy/case_0", objective_gap=0.0, objective_value=5.0),
            make_case("toy/case_1", objective_gap=0.1, objective_value=2.1),
            make_case("toy/case_2", objective_gap=0.3, objective_value=2.3),
            make_case("toy/case_3", objective_gap=0.2, objective_value=2.2),
        ]

        selection = select_failure_cases(case_results, top_k=2)
        selected_ids = [case["instance_id"] for case in selection["selected_failure_cases"]]

        self.assertEqual(selected_ids, ["toy/case_2", "toy/case_3"])
        self.assertEqual(selection["selection_summary"]["failure_pool_size"], 3)

    def test_fallback_to_all_cases_when_no_failures_exist(self):
        case_results = [
            make_case("toy/case_0", objective_gap=0.0, objective_value=2.0),
            make_case("toy/case_1", objective_gap=0.0, objective_value=3.0),
            make_case("toy/case_2", objective_gap=0.0, objective_value=1.0),
        ]

        selection = select_failure_cases(case_results, top_k=2)
        selected_ids = [case["instance_id"] for case in selection["selected_failure_cases"]]

        self.assertEqual(selected_ids, ["toy/case_1", "toy/case_0"])
        self.assertTrue(selection["selection_summary"]["fallback_all_instances_used"])

    def test_ranking_is_deterministic(self):
        case_results = [
            make_case("toy/case_b", objective_gap=0.2, objective_value=3.0),
            make_case("toy/case_a", objective_gap=0.2, objective_value=3.0),
            make_case("toy/case_c", objective_gap=0.2, objective_value=2.0),
        ]

        selection_a = select_failure_cases(case_results, top_k=3)
        selection_b = select_failure_cases(list(reversed(case_results)), top_k=3)

        self.assertEqual(selection_a, selection_b)
        self.assertEqual(
            [case["instance_id"] for case in selection_a["selected_failure_cases"]],
            ["toy/case_a", "toy/case_b", "toy/case_c"],
        )

    def test_preview_helpers_return_stable_output(self):
        case_results = [
            make_case("toy/case_1", objective_gap=0.5, objective_value=3.0),
            make_case("toy/case_0", objective_gap=0.0, objective_value=2.0),
        ]

        selection = select_failure_cases(case_results, top_k=1)
        summary_preview = format_selection_summary_preview(selection["selection_summary"])
        case_preview = format_failure_case_preview(selection["selected_failure_cases"][0])

        self.assertEqual(
            summary_preview,
            "total_cases=2 failure_pool_size=1 selected_count=1 fallback_all_instances_used=False",
        )
        self.assertEqual(
            case_preview,
            "toy/case_1 bins_used=3 lower_bound=2.00 objective_gap=0.500000 selection_stage=failure_pool",
        )


if __name__ == "__main__":
    unittest.main()
