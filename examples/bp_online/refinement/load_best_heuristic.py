from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


BP_ONLINE_DIR = Path(__file__).resolve().parents[1]


def get_results_dir(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else BP_ONLINE_DIR
    return root / "results"


def get_pops_best_dir(base_dir: str | Path | None = None) -> Path:
    return get_results_dir(base_dir) / "pops_best"


def _generation_id(path: Path) -> int:
    match = re.search(r"population_generation_(\d+)\.json$", path.name)
    if match:
        return int(match.group(1))
    return -1


def find_newest_best_artifact(base_dir: str | Path | None = None) -> Path:
    pops_best_dir = get_pops_best_dir(base_dir)
    candidates = sorted(pops_best_dir.glob("population_generation_*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No best heuristic artifacts found under {pops_best_dir}. "
            "Run a bp_online EoH search first."
        )
    return max(candidates, key=lambda path: (_generation_id(path), path.stat().st_mtime))


def load_best_heuristic_artifact(artifact_path: str | Path) -> dict[str, Any]:
    artifact = Path(artifact_path)
    with artifact.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {artifact}, got {type(payload).__name__}.")
    return payload


def extract_heuristic_fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "algorithm": payload.get("algorithm"),
        "code": payload.get("code"),
        "objective": payload.get("objective"),
        "other_inf": payload.get("other_inf"),
    }


def load_newest_best_heuristic(base_dir: str | Path | None = None) -> dict[str, Any]:
    artifact_path = find_newest_best_artifact(base_dir)
    payload = load_best_heuristic_artifact(artifact_path)
    extracted = extract_heuristic_fields(payload)
    extracted["artifact_path"] = str(artifact_path)
    extracted["generation_id"] = _generation_id(artifact_path)
    return extracted


def _single_line(text: str | None) -> str:
    if not text:
        return "<missing>"
    return " ".join(str(text).split())


def format_heuristic_preview(
    heuristic: dict[str, Any],
    algorithm_chars: int = 140,
    code_chars: int = 180,
) -> str:
    algorithm = _single_line(heuristic.get("algorithm"))
    code = _single_line(heuristic.get("code"))
    if len(algorithm) > algorithm_chars:
        algorithm = algorithm[: algorithm_chars - 3] + "..."
    if len(code) > code_chars:
        code = code[: code_chars - 3] + "..."

    lines = [
        f"artifact_path={heuristic.get('artifact_path', '<unknown>')}",
        f"generation_id={heuristic.get('generation_id', '<unknown>')}",
        f"objective={heuristic.get('objective')}",
        f"algorithm={algorithm}",
        f"code={code}",
    ]
    return "\n".join(lines)
