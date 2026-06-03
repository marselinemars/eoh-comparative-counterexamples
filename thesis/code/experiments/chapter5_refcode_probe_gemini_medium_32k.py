"""
thesis/code/experiments/chapter5_refcode_probe_gemini_medium_32k.py

6-call Chapter-5 probe on Gemini 2.5 Pro at reasoning_effort=
"medium" with max_output_tokens=32768. Bumped from the prior
probe's 8192 after that truncated 100% of calls during hidden
reasoning.

Bypasses run_single_proposal (which pins reasoning_effort=low,
max_output_tokens=8192) via a local wrapper that threads both
settings explicitly through call_llm. Production defaults in
llm_client.py unchanged.

Skips strategies whose per-strategy provenance JSON already
exists in the output dir, so Change A (single exploratory
worst_only call) can be verified before Change B's remaining 5.

Usage:
    python thesis/code/experiments/chapter5_refcode_probe_gemini_medium_32k.py
    # optional: --only=worst_only   (run exactly one strategy)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


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


_load_env_file(Path(__file__).resolve().parents[3] / ".env")

import numpy as np  # noqa: E402

from thesis.code.chapter5 import (  # noqa: E402
    DETERMINISTIC_STRATEGY_NAMES,
    STOCHASTIC_STRATEGY_NAMES,
    STRATEGIES,
)
from thesis.code.chapter5.llm_client import call_llm  # noqa: E402
from thesis.code.chapter5.prompt_builder import build_prompt  # noqa: E402
from thesis.code.chapter5.sanitize import sanitize  # noqa: E402
from thesis.code.chapter5.seeds import llm_seed, set_seed  # noqa: E402
from thesis.code.counterexample import CounterexampleSet  # noqa: E402
from thesis.code.evaluation import bins_used  # noqa: E402
from thesis.code.incumbents import (  # noqa: E402
    get_h_eoh,
    load_final_population,
)
from thesis.code.score_cache import ScoreCache, code_hash  # noqa: E402
from thesis.code.splits import (  # noqa: E402
    load_split,
    qualified_instance_id,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
POOL_PATH = (
    REPO_ROOT / "thesis" / "artifacts" / "h_eoh_counterexample_pool.json"
)
OUTPUT_DIR = (
    REPO_ROOT
    / "thesis"
    / "results"
    / "chapter5_refcode_probe_gemini_medium_32k_2026_04_23"
)

PROVIDER = "gemini"
MODEL = "gemini-2.5-pro"
MAX_OUTPUT_TOKENS = 32768
TEMPERATURE = 1.0
REASONING_EFFORT = "medium"
TIMEOUT_SECONDS = 300.0
LATENCY_ABORT_SECONDS = 240.0
COST_ABORT_USD = 0.75
INTER_CALL_SLEEP_SECONDS = 3.0
MAX_CONSECUTIVE_FAILURES = 3

PRICE_INPUT_PER_M = 1.25
PRICE_OUTPUT_PER_M = 10.0

STRATEGIES_ORDER = [
    "worst_only",
    "worst_plus_best",
    "most_discriminative",
    "uniform_random",
    "random_discriminative",
    "stratified_representative",
]

INSTANCE_KEYWORDS = (
    "mean", "distribution", "histogram", "sample",
    "min", "max", "median", "quartile", "percentile",
)
REFERENCE_KEYWORDS = (
    "reference", "alternative", "other heuristic",
)


def _cost(usage: Dict[str, Any]) -> float:
    p = usage.get("prompt_tokens") or 0
    c = usage.get("completion_tokens") or 0
    total = usage.get("total_tokens") or (p + c)
    reasoning = max(0, total - p - c)
    return (
        p * PRICE_INPUT_PER_M / 1_000_000
        + (c + reasoning) * PRICE_OUTPUT_PER_M / 1_000_000
    )


def _mentions_any(text: Optional[str], keywords) -> bool:
    if not text:
        return False
    low = text.lower()
    for kw in keywords:
        if re.search(rf"\b{re.escape(kw)}\b", low):
            return True
    return False


def _first_reasoning_step(reasoning: Optional[str]) -> Optional[str]:
    if not reasoning:
        return None
    s = reasoning.strip()
    m = re.search(
        r"(?:^|\n)\s*1[\.\)]\s*(.+?)(?=\n\s*2[\.\)]|\Z)",
        s,
        re.DOTALL,
    )
    if m:
        return m.group(1).strip()[:500]
    parts = re.split(r"(?<=[\.\!\?])\s+", s)
    return (parts[0] if parts else s)[:500]


def _structural_summary(cleaned_code: Optional[str]) -> str:
    if not cleaned_code:
        return "(no code)"
    c = cleaned_code
    notes: List[str] = []
    helpers = len(re.findall(r"\bdef\s+\w+\s*\(", c)) - 1
    if helpers > 0:
        notes.append(f"{helpers} helper fn(s)")
    for term, label in [
        ("sigmoid", "sigmoid"), ("np.exp", "exp"), ("np.log", "log"),
        ("softmax", "softmax"), ("np.where", "np.where"),
        ("np.tanh", "tanh"), ("np.clip", "np.clip"),
        ("np.power", "np.power"), ("np.maximum", "np.maximum"),
        ("np.minimum", "np.minimum"),
    ]:
        if term in c:
            notes.append(label)
    consts = sorted({
        s for s in re.findall(r"(?<![\w\.])(\d+\.\d+|\d+)(?!\w)", c)
        if s not in ("0", "1", "2")
    })
    if consts:
        notes.append(f"consts={consts[:6]}")
    notes.append(f"{c.count(chr(10)) + 1} lines")
    return "; ".join(notes)


def _reference_code_for_pool(pool: CounterexampleSet) -> str:
    hashes = {c.reference_hash for c in pool}
    if len(hashes) != 1:
        raise RuntimeError(f"pool has !=1 reference: {hashes}")
    target = next(iter(hashes))
    for m in load_final_population():
        if m["code_hash"] == target:
            return m["code"]
    raise RuntimeError(f"reference hash {target!r} not in final pop")


def _score_on_split(score_fn, proposal_hash, split_name, cache):
    split = load_split(split_name)
    shim = types.ModuleType(f"proposal_{proposal_hash}")
    shim.score = score_fn
    per: List[float] = []
    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        b = cache.get_or_compute(
            proposal_hash, qid, lambda i=inst: bins_used(shim, i)
        )
        per.append(b)
    return {"per_instance": per, "mean": float(np.array(per).mean())}


def _baseline_on_split(module, h_hash, split_name, cache):
    split = load_split(split_name)
    per: List[float] = []
    for inst in split["instances"]:
        qid = qualified_instance_id(split_name, inst["instance_id"])
        b = cache.get_or_compute(
            h_hash, qid, lambda i=inst: bins_used(module, i)
        )
        per.append(b)
    return {"per_instance": per, "mean": float(np.array(per).mean())}


def _run_one_proposal(
    strategy_name: str,
    set_index: int,
    seed_index: int,
    pool: CounterexampleSet,
    h_eoh: Dict[str, Any],
    output_dir: Path,
    *,
    k: int = 4,
) -> Dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    strategy = STRATEGIES[strategy_name]
    derived_set_seed = set_seed(strategy_name, set_index)
    derived_llm_seed = llm_seed(strategy_name, set_index, seed_index)

    if strategy_name in STOCHASTIC_STRATEGY_NAMES:
        rng = np.random.default_rng(derived_set_seed)
        ce_set = strategy(pool, k, rng=rng)
    elif strategy_name in DETERMINISTIC_STRATEGY_NAMES:
        ce_set = strategy(pool, k)
    else:
        raise RuntimeError(f"unclassified: {strategy_name}")

    reference_code = _reference_code_for_pool(pool)
    prompt = build_prompt(
        counterexample_set=ce_set,
        incumbent_code=h_eoh["code"],
        reference_code=reference_code,
    )

    llm_response = call_llm(
        provider=PROVIDER,
        prompt=prompt,
        model=MODEL,
        seed=derived_llm_seed,
        reasoning_effort=REASONING_EFFORT,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        temperature=TEMPERATURE,
        timeout_seconds=TIMEOUT_SECONDS,
    )
    raw_response = llm_response["text"]

    sanity = load_split("train_select")["instances"][0]
    sanit = sanitize(raw_response, sanity)

    scoring: Optional[Dict[str, Any]] = None
    proposal_hash: Optional[str] = None
    if sanit["status"] == "ok":
        cache = ScoreCache()
        cleaned = sanit["cleaned_code"]
        proposal_hash = code_hash(cleaned)
        inc_module = types.ModuleType(f"incumbent_{h_eoh['code_hash']}")
        exec(
            compile(h_eoh["code"], "<h_eoh>", "exec"),
            inc_module.__dict__,
        )
        bs = _baseline_on_split(
            inc_module, h_eoh["code_hash"], "train_step", cache
        )
        bg = _baseline_on_split(
            inc_module, h_eoh["code_hash"], "train_gate", cache
        )
        ps = _score_on_split(
            sanit["score_fn"], proposal_hash, "train_step", cache
        )
        pg = _score_on_split(
            sanit["score_fn"], proposal_hash, "train_gate", cache
        )
        cache.save()
        d_step = bs["mean"] - ps["mean"]
        d_gate = bg["mean"] - pg["mean"]
        wins = sum(
            1 for b, p in zip(bs["per_instance"], ps["per_instance"])
            if p < b
        )
        n = len(bs["per_instance"])
        scoring = {
            "mean_bins_h_eoh_train_step": bs["mean"],
            "mean_bins_proposal_train_step": ps["mean"],
            "mean_bins_h_eoh_train_gate": bg["mean"],
            "mean_bins_proposal_train_gate": pg["mean"],
            "delta_step": d_step,
            "delta_gate": d_gate,
            "generalization_gap": d_step - d_gate,
            "win_rate_step": wins / n if n else None,
        }

    finished = datetime.now(timezone.utc).isoformat()
    record = {
        "provider": PROVIDER,
        "strategy_name": strategy_name,
        "set_index": set_index,
        "seed_index": seed_index,
        "set_seed": derived_set_seed,
        "llm_seed": derived_llm_seed,
        "reasoning_effort_used": REASONING_EFFORT,
        "max_output_tokens_used": MAX_OUTPUT_TOKENS,
        "prompt": prompt,
        "raw_response": raw_response,
        "llm_metadata": {
            "model": llm_response["model"],
            "temperature": llm_response["temperature"],
            "max_output_tokens": llm_response["max_output_tokens"],
            "reasoning_effort": llm_response["reasoning_effort"],
            "seed_requested": llm_response["seed_requested"],
            "seed_honored": llm_response["seed_honored"],
            "raw_response_metadata": llm_response["raw_response_metadata"],
        },
        "sanitization": {
            "status": sanit["status"],
            "error": sanit["error"],
            "cleaned_code": sanit["cleaned_code"],
            "reasoning": sanit.get("reasoning"),
            "format_detected": sanit.get("format_detected"),
        },
        "scoring": scoring,
        "proposal_hash": proposal_hash,
        "timestamps": {"started_at": started, "finished_at": finished},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{strategy_name}_{set_index}_{seed_index}.json"
    out.write_text(
        json.dumps(record, indent=2, sort_keys=True), encoding="utf-8"
    )
    return record


def _summarize_from_record(
    record: Dict[str, Any], latency: float
) -> Dict[str, Any]:
    md = record["llm_metadata"]["raw_response_metadata"]
    usage = md.get("usage") or {}
    scoring = record.get("scoring") or {}
    sanit = record.get("sanitization") or {}
    reasoning = sanit.get("reasoning")
    raw_response = record.get("raw_response", "")
    p = usage.get("prompt_tokens") or 0
    c = usage.get("completion_tokens") or 0
    t = usage.get("total_tokens") or (p + c)
    rt = max(0, t - p - c)
    return {
        "strategy_name": record["strategy_name"],
        "seed_index": record["seed_index"],
        "prompt_tokens": p,
        "completion_tokens": c,
        "total_tokens": t,
        "reasoning_tokens": rt,
        "reasoning_effort_used": REASONING_EFFORT,
        "max_output_tokens_used": MAX_OUTPUT_TOKENS,
        "finish_reason": md.get("finish_reason"),
        "sanitization_status": sanit.get("status"),
        "sanitization_error": sanit.get("error"),
        "format_detected": sanit.get("format_detected"),
        "reasoning": reasoning,
        "reasoning_length_chars": len(reasoning) if reasoning else 0,
        "delta_step": scoring.get("delta_step"),
        "delta_gate": scoring.get("delta_gate"),
        "generalization_gap": scoring.get("generalization_gap"),
        "win_rate_step": scoring.get("win_rate_step"),
        "cost_usd_estimate": _cost(usage),
        "latency_seconds": latency,
        "prompt_length_chars": len(record.get("prompt", "")),
        "response_mentions_instance_details": _mentions_any(
            reasoning or raw_response, INSTANCE_KEYWORDS
        ),
        "response_mentions_reference": _mentions_any(
            reasoning or raw_response, REFERENCE_KEYWORDS
        ),
        "raw_response_prefix": raw_response[:3000],
        "cleaned_code": sanit.get("cleaned_code"),
    }


def _load_existing_record(strategy_name: str) -> Optional[Dict[str, Any]]:
    path = OUTPUT_DIR / f"{strategy_name}_0_0.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--only",
        help="Run exactly this one strategy and exit.",
        default=None,
    )
    args = ap.parse_args()

    pool = CounterexampleSet.from_json(
        POOL_PATH.read_text(encoding="utf-8")
    )
    h_eoh = get_h_eoh()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(
        f"Chapter 5 refcode probe on Gemini 2.5 Pro "
        f"(medium, max={MAX_OUTPUT_TOKENS})"
    )
    print("=" * 72)

    targets = (
        [args.only] if args.only else list(STRATEGIES_ORDER)
    )
    rows: List[Dict[str, Any]] = []
    stopped = False
    stop_reason: Optional[str] = None
    consecutive_failures = 0
    last_call_end: Optional[float] = None

    for i, strategy_name in enumerate(targets):
        existing = _load_existing_record(strategy_name)
        if existing is not None and not args.only:
            md = existing["llm_metadata"]["raw_response_metadata"]
            fake_latency = 0.0
            ts = existing.get("timestamps") or {}
            if ts.get("started_at") and ts.get("finished_at"):
                try:
                    a = datetime.fromisoformat(ts["started_at"])
                    b = datetime.fromisoformat(ts["finished_at"])
                    fake_latency = (b - a).total_seconds()
                except Exception:
                    fake_latency = 0.0
            row = _summarize_from_record(existing, fake_latency)
            rows.append(row)
            print(
                f"\n[{i + 1}/{len(targets)}] {strategy_name}: "
                f"reusing existing record "
                f"(sanitize={row['sanitization_status']}, "
                f"d_step={row.get('delta_step')})"
            )
            continue

        if last_call_end is not None:
            elapsed = time.perf_counter() - last_call_end
            rem = INTER_CALL_SLEEP_SECONDS - elapsed
            if rem > 0:
                time.sleep(rem)

        print(
            f"\n[{i + 1}/{len(targets)}] strategy={strategy_name}"
        )
        t0 = time.perf_counter()
        try:
            record = _run_one_proposal(
                strategy_name=strategy_name,
                set_index=0,
                seed_index=0,
                pool=pool,
                h_eoh=h_eoh,
                output_dir=OUTPUT_DIR,
            )
        except Exception as exc:
            stopped = True
            stop_reason = f"{strategy_name}: {type(exc).__name__}: {exc}"
            print(f"  STOP (error): {stop_reason}")
            break
        latency = time.perf_counter() - t0
        last_call_end = time.perf_counter()
        row = _summarize_from_record(record, latency)
        rows.append(row)

        print(
            f"  finish={row['finish_reason']:<8} "
            f"sanitize={row['sanitization_status']:<18} "
            f"format={row['format_detected']!s}"
        )
        print(
            f"  tokens p/c/r={row['prompt_tokens']}/"
            f"{row['completion_tokens']}/{row['reasoning_tokens']} "
            f"cost=${row['cost_usd_estimate']:.4f} "
            f"latency={latency:.2f}s"
        )
        if row["delta_step"] is not None:
            print(
                f"  d_step={row['delta_step']:+.2f} "
                f"d_gate={row['delta_gate']:+.2f} "
                f"win_rate={row['win_rate_step']:.3f}"
            )
        print(
            f"  mentions_instance={row['response_mentions_instance_details']} "
            f"mentions_ref={row['response_mentions_reference']}"
        )

        if latency > LATENCY_ABORT_SECONDS:
            stopped = True
            stop_reason = f"latency {latency:.1f}s > {LATENCY_ABORT_SECONDS}s"
            print(f"  STOP: {stop_reason}")
            break
        if row["cost_usd_estimate"] > COST_ABORT_USD:
            stopped = True
            stop_reason = (
                f"call cost ${row['cost_usd_estimate']:.4f} > "
                f"${COST_ABORT_USD}"
            )
            print(f"  STOP: {stop_reason}")
            break
        if row["sanitization_status"] != "ok":
            consecutive_failures += 1
        else:
            consecutive_failures = 0
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            stopped = True
            stop_reason = f"{consecutive_failures} consecutive sanitize failures"
            print(f"  STOP: {stop_reason}")
            break

    # If we were running --only, skip aggregates; just write per-call.
    if args.only:
        print("\n(--only mode: skipping aggregate report)")
        return 0 if not stopped else 1

    # --- Per-call table -------------------------------------------------
    print()
    print("=" * 72)
    print("Per-call table")
    print("=" * 72)
    print(
        f"{'strategy':<26} {'san':<18} "
        f"{'d_step':>8} {'d_gate':>8} {'win':>5} "
        f"{'ptok':>6} {'ctok':>6} {'rtok':>6} "
        f"{'lat':>7} {'cost':>7}"
    )
    for r in rows:
        d_s = r.get("delta_step")
        d_g = r.get("delta_gate")
        wr = r.get("win_rate_step")
        print(
            f"{r['strategy_name']:<26} "
            f"{(r['sanitization_status'] or '?'):<18} "
            f"{(d_s if d_s is not None else float('nan')):>+8.2f} "
            f"{(d_g if d_g is not None else float('nan')):>+8.2f} "
            f"{(wr if wr is not None else float('nan')):>5.2f} "
            f"{r.get('prompt_tokens') or 0:>6d} "
            f"{r.get('completion_tokens') or 0:>6d} "
            f"{r.get('reasoning_tokens') or 0:>6d} "
            f"{r['latency_seconds']:>7.2f} "
            f"${r['cost_usd_estimate']:>6.4f}"
        )

    # --- Aggregates ----------------------------------------------------
    n = len(rows)
    n_ok = sum(1 for r in rows if r["sanitization_status"] == "ok")
    fmt_counts: Dict[str, int] = {}
    for r in rows:
        k = r.get("format_detected") or "(none)"
        fmt_counts[k] = fmt_counts.get(k, 0) + 1
    deltas = [r["delta_step"] for r in rows if r.get("delta_step") is not None]
    delta_range = (max(deltas) - min(deltas)) if deltas else 0.0
    median_delta = None
    if deltas:
        sd = sorted(deltas); m = len(sd)
        median_delta = (
            sd[m // 2] if m % 2 == 1
            else (sd[m // 2 - 1] + sd[m // 2]) / 2.0
        )
    near_parity = sum(1 for d in deltas if d >= -5)
    beats = sum(1 for d in deltas if d > 0)
    ok_rows = [r for r in rows if r["sanitization_status"] == "ok"]
    mi_rate = (
        sum(1 for r in ok_rows if r["response_mentions_instance_details"])
        / len(ok_rows)
    ) if ok_rows else 0.0
    mr_rate = (
        sum(1 for r in ok_rows if r["response_mentions_reference"])
        / len(ok_rows)
    ) if ok_rows else 0.0
    total_cost = sum(r["cost_usd_estimate"] for r in rows)
    mean_cost = (total_cost / n) if n > 0 else 0.0
    mean_latency = (
        sum(r["latency_seconds"] for r in rows) / n if n > 0 else 0.0
    )
    mean_rtokens = (
        sum(r.get("reasoning_tokens") or 0 for r in rows) / n
    ) if n > 0 else 0.0

    print()
    print("=" * 72)
    print("Cross-strategy aggregates")
    print("=" * 72)
    print(f"  sanitize_ok_rate: {n_ok}/{n}")
    print(f"  format_detected counts: {fmt_counts}")
    print(f"  instance-detail reference rate (ok-only): {mi_rate:.2f}")
    print(f"  reference-heuristic reference rate (ok-only): {mr_rate:.2f}")
    if deltas:
        print(
            f"  d_step range: [{min(deltas):+.2f}, {max(deltas):+.2f}] "
            f"spread={delta_range:.2f} median={median_delta:+.2f}"
        )
    print(f"  strategies with d_step >= -5: {near_parity}")
    print(f"  strategies with d_step > 0 (beats h_eoh): {beats}")
    print(f"  total cost: ${total_cost:.4f}  mean/call: ${mean_cost:.4f}")
    print(f"  mean latency: {mean_latency:.2f}s")
    print(f"  mean reasoning tokens: {mean_rtokens:.0f}")

    batch_cost = mean_cost * 360
    batch_wall = (mean_latency + INTER_CALL_SLEEP_SECONDS) * 360 / 3600.0
    print()
    print("=" * 72)
    print("Batch extrapolation (360 calls)")
    print("=" * 72)
    print(f"  cost: ${batch_cost:.2f}")
    print(f"  wall-clock: {batch_wall:.2f} hours")

    # Qualitative
    print()
    print("=" * 72)
    print("Qualitative per sanitize=ok proposal")
    print("=" * 72)
    qualitative: List[Dict[str, Any]] = []
    for r in rows:
        if r["sanitization_status"] != "ok":
            continue
        first = _first_reasoning_step(r.get("reasoning"))
        structural = _structural_summary(r.get("cleaned_code"))
        qualitative.append({
            "strategy": r["strategy_name"],
            "first_reasoning_step": first,
            "structural_code_summary": structural,
            "delta_step": r.get("delta_step"),
        })
        ds = r.get("delta_step")
        ds_str = f"{ds:+.2f}" if ds is not None else "n/a"
        print(f"- {r['strategy_name']} (d_step={ds_str})")
        print(f"    reasoning step 1: {first or '(no reasoning)'}")
        print(f"    code: {structural}")

    all_catastrophic = bool(deltas) and all(d < -50 for d in deltas)
    cat_C = stopped or n_ok <= 2 or all_catastrophic
    cat_A = (
        not cat_C
        and n_ok >= 4
        and near_parity >= 2
        and beats >= 1
        and mi_rate >= 0.5
        and mr_rate >= 0.3
        and delta_range >= 15
        and batch_cost < 200.0
        and batch_wall < 15.0
    )
    category = "C" if cat_C else ("A" if cat_A else "B")
    print()
    print("=" * 72)
    print(f"Go / no-go: category {category}")
    print("=" * 72)
    print(
        f"    n_ok>=4? {n_ok >= 4} ({n_ok}/{n})\n"
        f"    near_parity>=2? {near_parity >= 2} ({near_parity})\n"
        f"    beats>=1? {beats >= 1} ({beats})\n"
        f"    instance_ref>=0.50? {mi_rate >= 0.5} ({mi_rate:.2f})\n"
        f"    ref_heur_ref>=0.30? {mr_rate >= 0.3} ({mr_rate:.2f})\n"
        f"    spread>=15? {delta_range >= 15} ({delta_range:.2f})\n"
        f"    batch_cost<$200? {batch_cost < 200.0} (${batch_cost:.2f})\n"
        f"    batch_wall<15h? {batch_wall < 15.0} ({batch_wall:.2f}h)\n"
        f"    stopped_early? {stopped} "
        f"({stop_reason if stop_reason else 'n/a'})"
    )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": PROVIDER,
        "model": MODEL,
        "reasoning_effort_used": REASONING_EFFORT,
        "max_output_tokens_used": MAX_OUTPUT_TOKENS,
        "stopped_early": stopped,
        "stop_reason": stop_reason,
        "rows": rows,
        "aggregates": {
            "sanitize_ok": n_ok,
            "n_calls": n,
            "format_counts": fmt_counts,
            "instance_ref_rate": mi_rate,
            "reference_ref_rate": mr_rate,
            "d_step_range": delta_range,
            "d_step_median": median_delta,
            "near_parity_count": near_parity,
            "beats_h_eoh_count": beats,
            "total_cost_usd": total_cost,
            "mean_cost_usd": mean_cost,
            "mean_latency_seconds": mean_latency,
            "mean_reasoning_tokens": mean_rtokens,
            "batch_cost_usd_estimate": batch_cost,
            "batch_wall_clock_hours_estimate": batch_wall,
        },
        "qualitative": qualitative,
        "category": category,
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        f"\nSummary JSON: "
        f"{(OUTPUT_DIR / 'summary.json').relative_to(REPO_ROOT).as_posix()}"
    )
    return 0 if not stopped else 1


if __name__ == "__main__":
    raise SystemExit(main())
