"""
thesis/code/chapter6/experiments/calibrate_chars_per_token.py

One-shot calibration: send a single Level-2 prompt at N=100 and
read back ``prompt_tokens`` from the Gemini API to derive the
empirical chars-per-token ratio for the dense-numeric trace
body.

The two prior 2026-04-25 rule locks (N=200, N=150) both
missed Gemini 2.5 Pro's 1,048,576-token input limit because
they were calibrated against assumed chars/token ratios
(4.0 then 2.06) that turned out to be too generous. This
script gets us the true number from a successful API
round-trip.

N=100 was chosen for the calibration prompt because both
prior probes confirm it is comfortably below any plausible
token limit (max k=4 char count is ~1.08 MB), so the call is
expected to succeed and return ``prompt_tokens`` in the
response usage metadata.

The script overrides the production renderer's
``select_trace_row_positions`` in module scope for the one
call, then restores it. The production renderer (and the
locked design-doc rule) is not modified by running this
script.

Usage:
    python -m thesis.code.chapter6.experiments.calibrate_chars_per_token

Prints to stderr:
- prompt char count
- prompt_tokens from the API
- empirical chars/token ratio r = chars / prompt_tokens
- whether the proposal sanitized OK
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

import numpy as np


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_env_file(Path(__file__).resolve().parents[4] / ".env")

from thesis.code.chapter5 import STRATEGIES  # noqa: E402
from thesis.code.chapter5.llm_client import call_llm  # noqa: E402
from thesis.code.chapter5.sanitize import sanitize  # noqa: E402
from thesis.code.chapter6 import prompt_renderer  # noqa: E402
from thesis.code.chapter6.batch_runner import (  # noqa: E402
    _build_incumbent_module,
    llm_seed_ch6,
    set_seed_ch6,
)
from thesis.code.chapter6.trace_extractor import extract_incumbent_trace  # noqa: E402
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.incumbents import get_h_eoh, load_final_population  # noqa: E402
from thesis.code.splits import load_split  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
POOL_PATH = REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"

CALIBRATION_N = 50
CALIBRATION_HEAD = 10
CALIBRATION_TAIL = 40


def _select_calibration(n_trace_rows: int) -> List[int]:
    if n_trace_rows <= CALIBRATION_N:
        return list(range(n_trace_rows))
    head = list(range(CALIBRATION_HEAD))
    tail = np.linspace(
        CALIBRATION_HEAD, n_trace_rows - 1, CALIBRATION_TAIL, dtype=int
    ).tolist()
    return sorted(set(head) | {int(t) for t in tail})


def main() -> int:
    pool = CounterexampleSet.from_json(POOL_PATH.read_text(encoding="utf-8"))
    h_eoh = get_h_eoh()
    reference_hash = next(iter({c.reference_hash for c in pool}))
    reference_source = next(
        m["code"]
        for m in load_final_population()
        if m["code_hash"] == reference_hash
    )

    # Reproduce the smoke driver's first-cell input exactly.
    set_seed = set_seed_ch6("stratified_representative", 0, 2)
    llm_seed = llm_seed_ch6("stratified_representative", 0, 0, 2)
    rng = np.random.default_rng(set_seed)
    counterexample_set = STRATEGIES["stratified_representative"](pool, 4, rng=rng)

    inc_mod = _build_incumbent_module(h_eoh)
    train_select = load_split("train_select")
    instance_lookup = {
        f"thesis_train_select:{inst['instance_id']}": inst
        for inst in train_select["instances"]
    }
    traces = [
        extract_incumbent_trace(instance_lookup[ce.instance_id], inc_mod)
        for ce in counterexample_set.items
    ]

    original_selector = prompt_renderer.select_trace_row_positions
    prompt_renderer.select_trace_row_positions = _select_calibration
    try:
        prompt = prompt_renderer.render_level2_prompt(
            counterexample_set=counterexample_set,
            traces=traces,
            incumbent_source=h_eoh["code"],
            reference_source=reference_source,
            instance_data_by_id=instance_lookup,
        )
    finally:
        prompt_renderer.select_trace_row_positions = original_selector

    char_count = len(prompt)
    print(
        f"calibration N={CALIBRATION_N}: prompt char count = {char_count:,}",
        file=sys.stderr,
    )

    response = call_llm(
        provider="gemini",
        prompt=prompt,
        seed=llm_seed,
        reasoning_effort="medium",
        max_output_tokens=32768,
        timeout_seconds=300.0,
    )

    raw_meta = response.get("raw_response_metadata") or {}
    usage = raw_meta.get("usage") if isinstance(raw_meta, dict) else None
    prompt_tokens = (
        usage.get("prompt_tokens") if isinstance(usage, dict) else None
    )

    if prompt_tokens is None:
        print(
            f"calibration FAILED: no prompt_tokens in response usage; "
            f"usage={usage}",
            file=sys.stderr,
        )
        return 1

    ratio = char_count / prompt_tokens
    print(
        f"calibration prompt_tokens (from API): {prompt_tokens:,}",
        file=sys.stderr,
    )
    print(
        f"calibration empirical chars/token ratio r = {ratio:.4f}",
        file=sys.stderr,
    )

    sanity_instance = train_select["instances"][0]
    sanitize_result = sanitize(response["text"], sanity_instance)
    sanitize_status = sanitize_result["status"]
    print(
        f"calibration sanitize_status = {sanitize_status}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
