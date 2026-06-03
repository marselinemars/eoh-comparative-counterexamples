"""
thesis/code/incumbents.py

Canonical pipeline for producing the thesis's incumbent heuristic
`h_eoh` and its reference pool.

  * h_eoh — fitness-best member of EoH's final population.

Library usage:
    from thesis.code.incumbents import get_h_eoh, get_reference_pool
    h = get_h_eoh()
    refs = get_reference_pool(h)

CLI usage:
    python -m thesis.code.incumbents --extract h_eoh
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
FINAL_POP_PATH = (
    REPO_ROOT / "examples" / "bp_online" / "results" / "pops"
    / "population_generation_10.json"
)
ARTIFACTS_DIR = REPO_ROOT / "thesis" / "artifacts"


def _add_hash(member: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a population member with a code_hash field added
    (sha256 of the code field, UTF-8 encoded, first 12 hex chars)."""
    out = dict(member)
    out["code_hash"] = hashlib.sha256(
        member["code"].encode("utf-8")
    ).hexdigest()[:12]
    return out


def load_final_population() -> List[Dict[str, Any]]:
    """Load EoH's canonical final population.

    Returns a list of dicts with keys:
        code, algorithm, objective, other_inf, code_hash.
    """
    raw = json.loads(FINAL_POP_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(
            f"Expected a JSON list at {FINAL_POP_PATH}, got {type(raw)}"
        )
    return [_add_hash(m) for m in raw]


def get_h_eoh() -> Dict[str, Any]:
    """Fitness-best member of EoH's final population (minimum objective).

    Lower objective is better in the bp_online final-population JSON
    (verified: pops_best/population_generation_N.json equals the
    min-objective member of pops/population_generation_N.json for all
    available N).
    """
    pop = load_final_population()
    return min(pop, key=lambda m: m["objective"])


def get_reference_pool(incumbent: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Members of the final population other than the incumbent,
    identified by code_hash. Canonically ordered by ascending
    objective (best reference first)."""
    pop = load_final_population()
    refs = [m for m in pop if m["code_hash"] != incumbent["code_hash"]]
    return sorted(refs, key=lambda m: m["objective"])


def extract_h_eoh_to_artifact() -> Path:
    """Write h_eoh as a standalone Python file in thesis/artifacts/.

    The output file is deterministic given a fixed final-population
    JSON: identical inputs produce byte-identical outputs.
    """
    h_eoh = get_h_eoh()
    ref_pool = get_reference_pool(h_eoh)
    pool_lines = "\n".join(
        f"        - {m['code_hash']}  (objective {m['objective']})"
        for m in ref_pool
    )

    header = (
        '"""\n'
        "h_eoh — the fitness-best heuristic from EoH's final "
        "population.\n"
        "\n"
        "This file is generated. Do not edit directly. Regenerate "
        "with:\n"
        "    python -m thesis.code.incumbents --extract h_eoh\n"
        "\n"
        "Provenance\n"
        "----------\n"
        f"Source file  : "
        f"{FINAL_POP_PATH.relative_to(REPO_ROOT).as_posix()}\n"
        f"Code hash    : {h_eoh['code_hash']} (sha256, first 12 hex)\n"
        f"Objective    : {h_eoh['objective']} (lower is better)\n"
        "\n"
        "Reference pool (non-incumbent members of the final "
        "population):\n"
        f"{pool_lines}\n"
        "\n"
        "Algorithm description (from EoH's LLM at time of generation):\n"
        f"    {h_eoh['algorithm']}\n"
        '"""\n\n'
    )

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS_DIR / "h_eoh.py"
    out_path.write_text(header + h_eoh["code"], encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract the canonical thesis incumbent.",
    )
    parser.add_argument(
        "--extract",
        choices=["h_eoh"],
        required=True,
        help="Which incumbent to extract.",
    )
    args = parser.parse_args()

    if args.extract == "h_eoh":
        out = extract_h_eoh_to_artifact()
        h = get_h_eoh()
        print(f"Wrote {out.relative_to(REPO_ROOT).as_posix()}")
        print(f"  code_hash: {h['code_hash']}")
        print(f"  objective: {h['objective']}")


if __name__ == "__main__":
    main()
