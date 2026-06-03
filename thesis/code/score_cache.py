"""
thesis/code/score_cache.py

Persistent per-instance score cache.

Keys a heuristic by sha256 hash of its source code (12 hex chars);
keys an instance by a stable source-qualified ID. The cache stores
integer `bins_used` values, which are deterministic for a given
(heuristic, instance) pair.

Cache file format (JSON, human-readable):
    {
      "schema_version": 1,
      "entries": {
        "<code_hash>|<instance_id>": {
          "code_hash": "...",
          "instance_id": "...",
          "bins_used": 2011
        },
        ...
      }
    }

The composite key uses "|" as the separator. Code hashes are 12 hex
chars; instance IDs are "source:inner_id" strings
(e.g. "pickle_1k:test_0", "eoh_inline_5k:test_3"). Neither component
can contain "|", so the joined key is unambiguous.

Conventions:
    bins_used is always the integer count of bins used under
    `evaluation.bins_used`. The cache does not store floats, scores,
    or gaps — only the raw primitive from which those derive. All
    derived quantities (score, gap, fitness, objective) can be
    recomputed from bins_used deterministically.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_PATH = REPO_ROOT / "thesis" / "artifacts" / "score_cache.json"


def code_hash(code: str) -> str:
    """Canonical 12-hex-char sha256 of a heuristic's source string."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]


class ScoreCache:
    """Persistent dict of (code_hash, instance_id) -> bins_used.

    Thread-safe for writes via a simple lock. Not process-safe — if
    two processes write simultaneously, last-writer-wins.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path is not None else DEFAULT_CACHE_PATH
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._load()

    # -- persistence ----------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Score cache at {self.path} is corrupted: {exc}. "
                "Delete the file to start fresh; cache entries are "
                "reproducible from source."
            ) from exc
        version = payload.get("schema_version")
        if version != SCHEMA_VERSION:
            raise RuntimeError(
                f"Score cache at {self.path} has schema_version "
                f"{version!r}, expected {SCHEMA_VERSION}. Upgrade "
                "logic is not implemented."
            )
        self._entries = payload.get("entries", {})

    def save(self) -> None:
        """Write the cache to disk atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "schema_version": SCHEMA_VERSION,
            "entries": self._entries,
        }
        with self._lock:
            tmp.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            tmp.replace(self.path)

    # -- public API -----------------------------------------------------

    @staticmethod
    def _key(code_h: str, instance_id: str) -> str:
        if "|" in code_h or "|" in instance_id:
            raise ValueError(
                "Cache key components must not contain '|': "
                f"code_hash={code_h!r}, instance_id={instance_id!r}"
            )
        return f"{code_h}|{instance_id}"

    def get(self, code_h: str, instance_id: str) -> Optional[int]:
        """Return cached bins_used or None."""
        entry = self._entries.get(self._key(code_h, instance_id))
        return None if entry is None else int(entry["bins_used"])

    def put(self, code_h: str, instance_id: str, bins_used_value: int) -> None:
        """Record a (heuristic, instance) -> bins_used pair."""
        if not isinstance(bins_used_value, int):
            raise TypeError(
                f"bins_used must be int, got {type(bins_used_value).__name__}"
            )
        with self._lock:
            self._entries[self._key(code_h, instance_id)] = {
                "code_hash": code_h,
                "instance_id": instance_id,
                "bins_used": bins_used_value,
            }

    def get_or_compute(
        self,
        code_h: str,
        instance_id: str,
        compute: Callable[[], int],
    ) -> int:
        """Return cached value or compute, store, and return.

        The `compute` callable takes no arguments and returns an int.
        On cache miss, it is invoked exactly once. Does NOT save to
        disk — the caller is responsible for batching `save()` calls
        at a sensible granularity (e.g. once per experiment or once
        per heuristic).
        """
        cached = self.get(code_h, instance_id)
        if cached is not None:
            return cached
        value = compute()
        self.put(code_h, instance_id, value)
        return value

    def __contains__(self, key: tuple) -> bool:
        code_h, instance_id = key
        return self._key(code_h, instance_id) in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def stats(self) -> Dict[str, int]:
        """Basic cache stats for logging."""
        hashes = {e["code_hash"] for e in self._entries.values()}
        instances = {e["instance_id"] for e in self._entries.values()}
        return {
            "entries": len(self._entries),
            "unique_heuristics": len(hashes),
            "unique_instances": len(instances),
        }
