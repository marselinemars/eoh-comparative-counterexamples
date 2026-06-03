"""Tests for thesis/code/score_cache.py.

Run:
    python -m pytest thesis/code/tests/test_score_cache.py -q

These tests exercise cache correctness, persistence, and the
cache-vs-fresh-computation equivalence that the whole design rests
on.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from thesis.code.score_cache import SCHEMA_VERSION, ScoreCache, code_hash


def _tmp_cache(tmp_path: Path) -> Path:
    return tmp_path / "score_cache.json"


def test_empty_cache_starts_empty(tmp_path):
    cache = ScoreCache(path=_tmp_cache(tmp_path))
    assert len(cache) == 0
    assert cache.get("aaaaaaaaaaaa", "pickle_1k:test_0") is None


def test_put_then_get_roundtrip(tmp_path):
    cache = ScoreCache(path=_tmp_cache(tmp_path))
    cache.put("aaaaaaaaaaaa", "pickle_1k:test_0", 430)
    assert cache.get("aaaaaaaaaaaa", "pickle_1k:test_0") == 430
    assert len(cache) == 1


def test_save_and_reload(tmp_path):
    path = _tmp_cache(tmp_path)
    cache = ScoreCache(path=path)
    cache.put("aaaaaaaaaaaa", "pickle_1k:test_0", 430)
    cache.put("bbbbbbbbbbbb", "eoh_inline_5k:test_3", 2011)
    cache.save()

    reloaded = ScoreCache(path=path)
    assert len(reloaded) == 2
    assert reloaded.get("aaaaaaaaaaaa", "pickle_1k:test_0") == 430
    assert reloaded.get("bbbbbbbbbbbb", "eoh_inline_5k:test_3") == 2011


def test_reject_pipe_in_key(tmp_path):
    cache = ScoreCache(path=_tmp_cache(tmp_path))
    with pytest.raises(ValueError):
        cache.put("aaaa|aaaaaa", "pickle_1k:test_0", 1)
    with pytest.raises(ValueError):
        cache.put("aaaaaaaaaaaa", "pickle_1k|test_0", 1)


def test_reject_non_int_bins_used(tmp_path):
    cache = ScoreCache(path=_tmp_cache(tmp_path))
    with pytest.raises(TypeError):
        cache.put("aaaaaaaaaaaa", "pickle_1k:test_0", 430.0)


def test_schema_version_mismatch_raises(tmp_path):
    path = _tmp_cache(tmp_path)
    path.write_text(
        json.dumps({"schema_version": 999, "entries": {}}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="schema_version"):
        ScoreCache(path=path)


def test_corrupt_file_raises(tmp_path):
    path = _tmp_cache(tmp_path)
    path.write_text("not valid json {", encoding="utf-8")
    with pytest.raises(RuntimeError, match="corrupted"):
        ScoreCache(path=path)


def test_get_or_compute_invokes_once_and_caches(tmp_path):
    cache = ScoreCache(path=_tmp_cache(tmp_path))
    calls = []

    def compute():
        calls.append(1)
        return 42

    v1 = cache.get_or_compute("aaaaaaaaaaaa", "pickle_1k:test_0", compute)
    v2 = cache.get_or_compute("aaaaaaaaaaaa", "pickle_1k:test_0", compute)
    assert v1 == 42
    assert v2 == 42
    assert len(calls) == 1  # compute invoked exactly once


def test_code_hash_is_12_hex_chars():
    h = code_hash("def score(item, bins):\n    return bins\n")
    assert len(h) == 12
    assert all(c in "0123456789abcdef" for c in h)


def test_cache_matches_fresh_computation_on_final_population(tmp_path):
    """End-to-end: for one heuristic on one real instance, the cached
    value must equal a fresh computation. This is the correctness
    guarantee the whole cache design rests on.
    """
    from thesis.code.evaluation import (
        bins_used,
        load_heuristic_from_code,
        load_instances,
    )
    from thesis.code.incumbents import load_final_population

    pop = load_final_population()
    h = min(pop, key=lambda m: m["objective"])
    instances = load_instances(size="1k", capacity=100)
    iid = "test_0"
    inst = instances[iid]

    module = load_heuristic_from_code(h["code"], module_name="h_fresh_under_test")
    fresh = bins_used(module, inst)

    cache = ScoreCache(path=_tmp_cache(tmp_path))
    cached = cache.get_or_compute(
        h["code_hash"],
        f"pickle_1k:{iid}",
        lambda: bins_used(module, inst),
    )
    assert cached == fresh, (
        f"Cache disagrees with fresh computation: cached={cached}, "
        f"fresh={fresh}. This is a cache-correctness regression."
    )


def test_schema_version_constant_is_1():
    """Lock the schema version. Bumping it is a deliberate event."""
    assert SCHEMA_VERSION == 1
