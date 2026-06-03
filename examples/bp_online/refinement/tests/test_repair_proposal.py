from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
REFINEMENT_DIR = TESTS_DIR.parent
if str(REFINEMENT_DIR) not in sys.path:
    sys.path.insert(0, str(REFINEMENT_DIR))

from repair_proposal import (
    build_stub_repair_proposal,
    format_repair_proposal_preview,
    parse_repair_proposal,
)


class RepairProposalTests(unittest.TestCase):
    def setUp(self):
        self.repair_request = {
            "heuristic_artifact_id": "examples/bp_online/results/pops_best/population_generation_3.json",
            "heuristic_algorithm": "Score feasible bins by preferring tighter placements.",
            "heuristic_code": "def score(item, bins):\n    return -bins\n",
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
            "trace_preview": {
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
            },
            "allowed_patch_families": (),
            "banned_patch_families": (),
        }

    def test_parser_accepts_valid_proposed_patch(self):
        raw_json_text = json.dumps(
            {
                "status": "proposed_patch",
                "patch_family": "local_edit_stub",
                "confidence": 0.4,
                "rationale": "Localized stub rationale.",
                "proposed_change_summary": ["Adjust one local scoring branch."],
                "localized_edit_instructions": ["Edit only the score function body."],
                "proposed_code": "def score(item, bins):\n    return -bins\n",
            }
        )

        proposal = parse_repair_proposal(raw_json_text)

        self.assertEqual(proposal["status"], "proposed_patch")
        self.assertEqual(proposal["patch_family"], "local_edit_stub")
        self.assertEqual(proposal["proposed_change_summary"], ("Adjust one local scoring branch.",))

    def test_parser_accepts_prose_wrapped_fenced_json(self):
        raw_json_text = (
            "Here is a localized proposal.\n\n"
            "```json\n"
            "{\n"
            '  "status": "proposed_patch",\n'
            '  "patch_family": "local_edit_stub",\n'
            '  "confidence": 0.8,\n'
            '  "rationale": "Grounded in the failing case.",\n'
            '  "proposed_change_summary": [\n'
            '    "Adjust one local scoring branch."\n'
            "  ],\n"
            '  "localized_edit_instructions": [\n'
            '    "Edit only the score function body."\n'
            "  ],\n"
            '  "proposed_code": "def score(item, bins):\\n    return -bins\\n"\n'
            "}\n"
            "```"
        )

        proposal = parse_repair_proposal(raw_json_text)

        self.assertEqual(proposal["status"], "proposed_patch")
        self.assertEqual(proposal["confidence"], 0.8)
        self.assertEqual(proposal["localized_edit_instructions"], ("Edit only the score function body.",))

    def test_parser_accepts_prose_wrapped_plain_json(self):
        raw_json_text = (
            "I analyzed the case and propose this patch.\n\n"
            "{\n"
            '  "status": "no_patch",\n'
            '  "patch_family": null,\n'
            '  "confidence": 0.2,\n'
            '  "rationale": "Not enough signal.",\n'
            '  "proposed_change_summary": "Leave heuristic unchanged.",\n'
            '  "localized_edit_instructions": ["Provide more context."],\n'
            '  "proposed_code": null\n'
            "}\n"
            "\nThanks."
        )

        proposal = parse_repair_proposal(raw_json_text)

        self.assertEqual(proposal["status"], "no_patch")
        self.assertEqual(proposal["proposed_change_summary"], ("Leave heuristic unchanged.",))

    def test_parser_accepts_no_patch(self):
        raw_json_text = json.dumps(
            {
                "status": "no_patch",
                "patch_family": None,
                "confidence": 0.1,
                "rationale": "Not enough context.",
                "proposed_change_summary": "Leave heuristic unchanged.",
                "localized_edit_instructions": ["Provide more context."],
                "proposed_code": None,
            }
        )

        proposal = parse_repair_proposal(raw_json_text)

        self.assertEqual(proposal["status"], "no_patch")
        self.assertIsNone(proposal["patch_family"])
        self.assertIsNone(proposal["proposed_code"])

    def test_parser_rejects_invalid_status(self):
        raw_json_text = json.dumps(
            {
                "status": "ok",
                "patch_family": None,
                "confidence": 0.5,
                "rationale": "Bad status.",
                "proposed_change_summary": [],
                "localized_edit_instructions": [],
                "proposed_code": None,
            }
        )

        with self.assertRaisesRegex(ValueError, "Invalid repair proposal status"):
            parse_repair_proposal(raw_json_text)

    def test_parser_rejects_confidence_outside_range(self):
        raw_json_text = json.dumps(
            {
                "status": "no_patch",
                "patch_family": None,
                "confidence": 1.5,
                "rationale": "Bad confidence.",
                "proposed_change_summary": [],
                "localized_edit_instructions": [],
                "proposed_code": None,
            }
        )

        with self.assertRaisesRegex(ValueError, "confidence must be in \\[0, 1\\]"):
            parse_repair_proposal(raw_json_text)

    def test_parser_rejects_proposed_patch_with_empty_proposed_code(self):
        raw_json_text = json.dumps(
            {
                "status": "proposed_patch",
                "patch_family": "local_edit_stub",
                "confidence": 0.4,
                "rationale": "Missing code.",
                "proposed_change_summary": [],
                "localized_edit_instructions": [],
                "proposed_code": "",
            }
        )

        with self.assertRaisesRegex(ValueError, "proposed_code must be non-empty"):
            parse_repair_proposal(raw_json_text)

    def test_stub_output_is_deterministic(self):
        proposal_a = build_stub_repair_proposal(self.repair_request)
        proposal_b = build_stub_repair_proposal(self.repair_request)

        self.assertEqual(proposal_a, proposal_b)
        self.assertEqual(proposal_a["status"], "proposed_patch")
        self.assertEqual(proposal_a["patch_family"], "local_edit_stub")

    def test_preview_formatting_is_stable(self):
        proposal = build_stub_repair_proposal(self.repair_request)

        self.assertEqual(
            format_repair_proposal_preview(proposal),
            "status=proposed_patch\n"
            "patch_family=local_edit_stub\n"
            "confidence=0.35\n"
            "change_summary_count=2\n"
            "localized_edit_count=2\n"
            "has_proposed_code=True",
        )


if __name__ == "__main__":
    unittest.main()
