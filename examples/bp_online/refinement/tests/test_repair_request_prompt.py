from __future__ import annotations

import sys
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
REFINEMENT_DIR = TESTS_DIR.parent
if str(REFINEMENT_DIR) not in sys.path:
    sys.path.insert(0, str(REFINEMENT_DIR))

from build_repair_request import (
    build_repair_prompt,
    build_repair_request,
    format_repair_prompt_preview,
    format_repair_request_preview,
)


class RepairRequestPromptTests(unittest.TestCase):
    def setUp(self):
        self.heuristic = {
            "artifact_path": "examples/bp_online/results/pops_best/population_generation_3.json",
            "generation_id": 3,
            "algorithm": "Score feasible bins by preferring tighter placements.",
            "code": "def score(item, bins):\n    return -bins\n",
            "objective": 1.23,
        }
        self.selected_failure_case = {
            "instance_id": "toy/case_1",
            "dataset_name": "toy",
            "case_name": "case_1",
            "capacity": 10.0,
            "num_items": 4,
            "bins_used": 3,
            "lower_bound": 2.0,
            "objective_gap": 0.5,
            "objective_value": 3.0,
            "selection_stage": "failure_pool",
            "selection_reason": "failure_pool objective_gap>0 ranked by objective_gap, objective_value, instance_id",
        }
        self.trace_preview = {
            "instance_id": "toy/case_1",
            "number_of_steps": 4,
            "number_of_new_bin_openings": 2,
            "key_steps": [
                {
                    "step_index": 0,
                    "item_size": 6.0,
                    "action_taken": "open_new_bin",
                    "chosen_bin_index": "new_bin",
                    "remaining_capacity_before": 10.0,
                    "remaining_capacity_after": 4.0,
                    "num_open_bins_before": 0,
                }
            ],
        }

    def test_repair_request_preserves_selected_case_and_trace(self):
        repair_request = build_repair_request(
            self.heuristic,
            self.selected_failure_case,
            self.trace_preview,
        )

        self.assertEqual(repair_request["instance_id"], "toy/case_1")
        self.assertEqual(repair_request["objective_gap"], 0.5)
        self.assertEqual(repair_request["trace_preview"], self.trace_preview)
        self.assertEqual(repair_request["allowed_patch_families"], ())
        self.assertEqual(repair_request["banned_patch_families"], ())

    def test_repair_prompt_includes_required_grounding_and_contract(self):
        repair_request = build_repair_request(
            self.heuristic,
            self.selected_failure_case,
            self.trace_preview,
        )
        repair_prompt = build_repair_prompt(repair_request)

        self.assertIn("def score(item, bins):", repair_prompt)
        self.assertIn('"objective_gap": 0.5', repair_prompt)
        self.assertIn('"trace_preview"', repair_prompt)
        self.assertIn("Propose a localized code edit, not a rewrite.", repair_prompt)
        self.assertIn("Return structured JSON only", repair_prompt)
        self.assertIn('"status": "proposed_patch | no_patch | unsupported_request"', repair_prompt)
        self.assertNotIn("ok | cannot_repair", repair_prompt)
        self.assertIn('"localized_edit_instructions"', repair_prompt)
        self.assertIn('"proposed_code"', repair_prompt)

    def test_instance_id_mismatch_raises_clear_error(self):
        mismatched_trace_preview = dict(self.trace_preview)
        mismatched_trace_preview["instance_id"] = "toy/case_2"

        with self.assertRaisesRegex(
            ValueError,
            "Selected failure case and trace preview must match on instance_id",
        ):
            build_repair_request(
                self.heuristic,
                self.selected_failure_case,
                mismatched_trace_preview,
            )

    def test_preview_helpers_are_stable(self):
        repair_request = build_repair_request(
            self.heuristic,
            self.selected_failure_case,
            self.trace_preview,
        )
        repair_prompt = build_repair_prompt(repair_request)

        self.assertEqual(
            format_repair_request_preview(repair_request),
            "heuristic_artifact_id=examples/bp_online/results/pops_best/population_generation_3.json\n"
            "instance_id=toy/case_1\n"
            "objective_gap=0.500000\n"
            "selection_stage=failure_pool\n"
            "algorithm=Score feasible bins by preferring tighter placements.\n"
            "trace_steps=4\n"
            "trace_new_bin_openings=2\n"
            "allowed_patch_families=()\n"
            "banned_patch_families=()",
        )
        prompt_preview = format_repair_prompt_preview(repair_prompt, max_chars=120)
        self.assertTrue(prompt_preview.startswith("You are repairing one bin-packing heuristic"))
        self.assertTrue(prompt_preview.endswith("..."))


if __name__ == "__main__":
    unittest.main()
