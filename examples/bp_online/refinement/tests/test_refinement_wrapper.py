from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
REFINEMENT_DIR = TESTS_DIR.parent
if str(REFINEMENT_DIR) not in sys.path:
    sys.path.insert(0, str(REFINEMENT_DIR))

from evaluate_heuristic_cases import evaluate_heuristic_on_instances
from load_best_heuristic import (
    extract_heuristic_fields,
    find_newest_best_artifact,
    format_heuristic_preview,
    load_best_heuristic_artifact,
)


class RefinementWrapperTests(unittest.TestCase):
    def test_load_newest_best_artifact(self):
        tmp_dir = Path.cwd() / "refinement_test_artifacts"
        shutil.rmtree(tmp_dir, ignore_errors=True)
        try:
            pops_best = tmp_dir / "results" / "pops_best"
            pops_best.mkdir(parents=True)

            older = pops_best / "population_generation_1.json"
            newer = pops_best / "population_generation_3.json"
            older.write_text(json.dumps({"algorithm": "old", "code": "def score(item, bins): return bins", "objective": 2.0}), encoding="utf-8")
            newer.write_text(json.dumps({"algorithm": "new", "code": "def score(item, bins): return -bins", "objective": 1.0}), encoding="utf-8")

            artifact_path = find_newest_best_artifact(tmp_dir)
            payload = load_best_heuristic_artifact(artifact_path)
            extracted = extract_heuristic_fields(payload)

            self.assertEqual(artifact_path.name, "population_generation_3.json")
            self.assertEqual(extracted["algorithm"], "new")
            self.assertEqual(extracted["objective"], 1.0)
            self.assertIn("objective=1.0", format_heuristic_preview({"artifact_path": str(artifact_path), "generation_id": 3, **extracted}))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_evaluate_instances_returns_structured_results(self):
        code = (
            "import numpy as np\n\n"
            "def score(item, bins):\n"
            "    return -bins\n"
        )
        instances = [
            {
                "instance_id": "toy/test_0",
                "dataset_name": "toy",
                "case_name": "test_0",
                "capacity": 10,
                "num_items": 3,
                "items": [4, 6, 5],
                "lower_bound": 2.0,
            },
            {
                "instance_id": "toy/test_1",
                "dataset_name": "toy",
                "case_name": "test_1",
                "capacity": 10,
                "num_items": 4,
                "items": [3, 3, 4, 5],
                "lower_bound": 2.0,
            },
        ]

        results_a = evaluate_heuristic_on_instances(instances, code_string=code)
        results_b = evaluate_heuristic_on_instances(instances, code_string=code)

        self.assertEqual(results_a, results_b)
        self.assertEqual(len(results_a), 2)
        self.assertEqual(
            set(results_a[0].keys()),
            {
                "instance_id",
                "dataset_name",
                "case_name",
                "capacity",
                "num_items",
                "bins_used",
                "lower_bound",
                "objective_gap",
                "objective_value",
            },
        )


if __name__ == "__main__":
    unittest.main()
