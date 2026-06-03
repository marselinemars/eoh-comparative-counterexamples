from __future__ import annotations

import sys
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
REFINEMENT_DIR = TESTS_DIR.parent
if str(REFINEMENT_DIR) not in sys.path:
    sys.path.insert(0, str(REFINEMENT_DIR))

from build_trace_preview import (
    build_trace_previews_for_selected_cases,
    format_trace_preview,
)
from evaluate_heuristic_cases import load_heuristic_module_from_code


TRACE_CODE = (
    "import numpy as np\n\n"
    "def score(item, bins):\n"
    "    return -bins\n"
)


class TracePreviewTests(unittest.TestCase):
    def test_trace_preview_builds_for_selected_failure_cases(self):
        heuristic_module = load_heuristic_module_from_code(TRACE_CODE, module_name="trace_preview_test_a")
        instances = [
            {
                "instance_id": "toy/case_0",
                "dataset_name": "toy",
                "case_name": "case_0",
                "capacity": 10,
                "num_items": 4,
                "items": [6, 4, 5, 5],
                "lower_bound": 2.0,
            },
            {
                "instance_id": "toy/case_1",
                "dataset_name": "toy",
                "case_name": "case_1",
                "capacity": 10,
                "num_items": 3,
                "items": [8, 2, 1],
                "lower_bound": 2.0,
            },
        ]
        selected_failure_cases = [
            {
                "instance_id": "toy/case_0",
                "dataset_name": "toy",
                "case_name": "case_0",
                "capacity": 10.0,
                "num_items": 4,
                "bins_used": 2,
                "lower_bound": 2.0,
                "objective_gap": 0.25,
                "objective_value": 2.0,
                "selection_stage": "failure_pool",
                "selection_reason": "test",
            }
        ]

        previews = build_trace_previews_for_selected_cases(
            instances=instances,
            selected_failure_cases=selected_failure_cases,
            heuristic_module=heuristic_module,
            max_key_steps=4,
        )

        self.assertEqual(len(previews), 1)
        preview = previews[0]
        self.assertEqual(preview["instance_id"], "toy/case_0")
        self.assertEqual(preview["number_of_steps"], 4)
        self.assertEqual(preview["number_of_new_bin_openings"], 2)
        self.assertEqual(preview["key_steps"][0]["step_index"], 0)

    def test_trace_preview_is_deterministic_and_key_steps_stable(self):
        heuristic_module = load_heuristic_module_from_code(TRACE_CODE, module_name="trace_preview_test_b")
        instances = [
            {
                "instance_id": "toy/case_0",
                "dataset_name": "toy",
                "case_name": "case_0",
                "capacity": 10,
                "num_items": 4,
                "items": [6, 4, 5, 5],
                "lower_bound": 2.0,
            }
        ]
        selected_failure_cases = [
            {
                "instance_id": "toy/case_0",
                "dataset_name": "toy",
                "case_name": "case_0",
                "capacity": 10.0,
                "num_items": 4,
                "bins_used": 2,
                "lower_bound": 2.0,
                "objective_gap": 0.25,
                "objective_value": 2.0,
                "selection_stage": "failure_pool",
                "selection_reason": "test",
            }
        ]

        preview_a = build_trace_previews_for_selected_cases(
            instances=instances,
            selected_failure_cases=selected_failure_cases,
            heuristic_module=heuristic_module,
            max_key_steps=4,
        )
        preview_b = build_trace_previews_for_selected_cases(
            instances=instances,
            selected_failure_cases=selected_failure_cases,
            heuristic_module=heuristic_module,
            max_key_steps=4,
        )

        self.assertEqual(preview_a, preview_b)
        self.assertEqual(
            [step["step_index"] for step in preview_a[0]["key_steps"]],
            [0, 1, 2],
        )

    def test_trace_preview_formatting_is_stable(self):
        heuristic_module = load_heuristic_module_from_code(TRACE_CODE, module_name="trace_preview_test_c")
        instances = [
            {
                "instance_id": "toy/case_0",
                "dataset_name": "toy",
                "case_name": "case_0",
                "capacity": 10,
                "num_items": 4,
                "items": [6, 4, 5, 5],
                "lower_bound": 2.0,
            }
        ]
        selected_failure_cases = [
            {
                "instance_id": "toy/case_0",
                "dataset_name": "toy",
                "case_name": "case_0",
                "capacity": 10.0,
                "num_items": 4,
                "bins_used": 2,
                "lower_bound": 2.0,
                "objective_gap": 0.25,
                "objective_value": 2.0,
                "selection_stage": "failure_pool",
                "selection_reason": "test",
            }
        ]

        preview = build_trace_previews_for_selected_cases(
            instances=instances,
            selected_failure_cases=selected_failure_cases,
            heuristic_module=heuristic_module,
            max_key_steps=3,
        )[0]

        self.assertEqual(
            format_trace_preview(preview),
            "instance_id=toy/case_0\n"
            "number_of_steps=4\n"
            "number_of_new_bin_openings=2\n"
            "key_steps:\n"
            "step=0 item_size=6.00 action_taken=open_new_bin chosen_bin_index=new_bin remaining_capacity_before=10.00 remaining_capacity_after=4.00 num_open_bins_before=0\n"
            "step=1 item_size=4.00 action_taken=place_existing_bin chosen_bin_index=0 remaining_capacity_before=4.00 remaining_capacity_after=0.00 num_open_bins_before=1\n"
            "step=2 item_size=5.00 action_taken=open_new_bin chosen_bin_index=new_bin remaining_capacity_before=10.00 remaining_capacity_after=5.00 num_open_bins_before=1",
        )


if __name__ == "__main__":
    unittest.main()
