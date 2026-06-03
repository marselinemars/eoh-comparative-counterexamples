"""
thesis/code/chapter5/sanitize.py

Two-stage sanitization of LLM proposals, per chapter5_design.md §8:

Stage 1 — extraction. Pull the Python code out of a potentially
structured response. Recognized output formats (first match wins):

    * "step_by_step_reasoning_then_code":
        STEP_BY_STEP_REASONING ... CODE <code>
    * "analysis_then_code":
        ANALYSIS ... CODE <code>
    * "code_only": no markers, first 200 chars look like Python
    * "malformed": none of the above (→ failed_extraction)

Stage 2 — validation. Three sub-checks on the extracted code:

    1. Parse check  — strip markdown fences, then `ast.parse`. Also
                      captures `exec` failures under `failed_parse`.
    2. Signature check — module must define a callable `score` with
                         exactly two positional arguments.
    3. Runtime check — one decision call (single item, 3-bin array)
                       must complete without raising and return a
                       numpy array of the expected shape.

Failure labels: failed_extraction, failed_parse, failed_signature,
failed_runtime. Reasoning text (when present) is preserved in the
returned dict for provenance but does not affect scoring.
"""
from __future__ import annotations

import ast
import inspect
import re
from typing import Any, Dict, Optional

import numpy as np


_FENCE_FULL = re.compile(
    r"^\s*```(?:[A-Za-z0-9_+-]+)?\s*\r?\n(.*?)\r?\n\s*```\s*$",
    re.DOTALL,
)
_FENCE_OPEN_ONLY = re.compile(
    r"^\s*```(?:[A-Za-z0-9_+-]+)?\s*\r?\n(.*)$", re.DOTALL
)
_FENCE_CLOSE_ONLY = re.compile(r"^(.*)\r?\n\s*```\s*$", re.DOTALL)

# Section markers. We match them on their own line (possibly with
# surrounding whitespace) to avoid false positives when the LLM
# writes "the CODE section" mid-sentence.
_STEP_MARKER = re.compile(
    r"(?:^|\n)[ \t]*STEP_BY_STEP_REASONING[ \t]*(?:\r?\n|$)"
)
_ANALYSIS_MARKER = re.compile(
    r"(?:^|\n)[ \t]*ANALYSIS[ \t]*(?:\r?\n|$)"
)
# CODE markers: we want ALL of them so we can split at the last one
# (covers the case where the reasoning text quotes the word CODE).
_CODE_MARKER = re.compile(
    r"(?:^|\n)[ \t]*CODE[ \t]*(?:\r?\n|$)"
)


def _strip_fences(text: str) -> str:
    """Remove a single outer markdown fence if present.

    Handles the common cases:
        ```python\n<code>\n```
        ```\n<code>\n```
    and the half-fenced failure modes where the LLM opened but
    didn't close (or vice versa).
    """
    m = _FENCE_FULL.match(text)
    if m:
        return m.group(1).strip()
    m = _FENCE_OPEN_ONLY.match(text)
    if m:
        inner = m.group(1)
        # try to also strip a trailing fence if present
        m2 = _FENCE_CLOSE_ONLY.match(inner)
        if m2:
            return m2.group(1).strip()
        return inner.strip()
    m = _FENCE_CLOSE_ONLY.match(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _strip_leading_code_header(text: str) -> str:
    """If the extracted code slice still starts with a line that is
    literally 'CODE' (possibly with whitespace), drop that line."""
    s = text.lstrip("\r\n")
    lines = s.split("\n", 1)
    if lines and lines[0].strip() == "CODE":
        return lines[1] if len(lines) > 1 else ""
    return s


def _looks_like_code_prefix(text: str) -> bool:
    """Heuristic: does the first ~200 chars of `text` look like
    Python source (contains `def score(`, `import`, `from`, `@`)?"""
    head = text.lstrip().lstrip("`").lstrip()[:200]
    if not head:
        return False
    return bool(
        re.search(r"(?:^|\n)\s*(?:import |from |def |@)", head)
        or "def score(" in head
    )


def extract_code(response: str) -> Dict[str, Any]:
    """Stage-1 extraction. See module docstring for format catalog.

    Returns
    -------
    dict with keys:
        code:              str        — the code slice to validate
        reasoning:         str | None — reasoning text if present
        format_detected:   str        — one of the four labels
        extraction_notes:  str        — human-readable note
    """
    if response is None:
        return {
            "code": "",
            "reasoning": None,
            "format_detected": "malformed",
            "extraction_notes": "response is None",
        }

    text = response

    # Case 1: STEP_BY_STEP_REASONING ... CODE
    step_m = _STEP_MARKER.search(text)
    if step_m:
        # Find the LAST CODE marker that comes after the STEP marker.
        search_from = step_m.end()
        last_code: Optional[re.Match[str]] = None
        for m in _CODE_MARKER.finditer(text, search_from):
            last_code = m
        if last_code is not None:
            reasoning = text[step_m.end(): last_code.start()].strip()
            code_slice = text[last_code.end():]
            code = _strip_fences(_strip_leading_code_header(code_slice))
            return {
                "code": code,
                "reasoning": reasoning or None,
                "format_detected": "step_by_step_reasoning_then_code",
                "extraction_notes": (
                    "STEP_BY_STEP_REASONING header at offset "
                    f"{step_m.start()}; last CODE header at offset "
                    f"{last_code.start()}"
                ),
            }

    # Case 2: ANALYSIS ... CODE
    analysis_m = _ANALYSIS_MARKER.search(text)
    if analysis_m:
        search_from = analysis_m.end()
        last_code = None
        for m in _CODE_MARKER.finditer(text, search_from):
            last_code = m
        if last_code is not None:
            reasoning = text[analysis_m.end(): last_code.start()].strip()
            code_slice = text[last_code.end():]
            code = _strip_fences(_strip_leading_code_header(code_slice))
            return {
                "code": code,
                "reasoning": reasoning or None,
                "format_detected": "analysis_then_code",
                "extraction_notes": (
                    "ANALYSIS header at offset "
                    f"{analysis_m.start()}; last CODE header at offset "
                    f"{last_code.start()}"
                ),
            }

    # Case 3: code-only (no structured markers)
    if _looks_like_code_prefix(text) or _looks_like_code_prefix(
        _strip_fences(text)
    ):
        return {
            "code": _strip_fences(text),
            "reasoning": None,
            "format_detected": "code_only",
            "extraction_notes": (
                "no structured markers; first 200 chars look like code"
            ),
        }

    # Case 4: malformed
    return {
        "code": text,
        "reasoning": None,
        "format_detected": "malformed",
        "extraction_notes": (
            "no STEP_BY_STEP_REASONING / ANALYSIS / CODE markers "
            "and first 200 chars do not look like Python source"
        ),
    }


def _make_failure(
    status: str,
    cleaned: Optional[str],
    error: str,
    reasoning: Optional[str],
    format_detected: str,
) -> Dict[str, Any]:
    return {
        "status": status,
        "cleaned_code": cleaned,
        "score_fn": None,
        "error": error,
        "reasoning": reasoning,
        "format_detected": format_detected,
    }


def sanitize(
    raw_response: str,
    sanity_instance: Dict[str, Any],
) -> Dict[str, Any]:
    """See module docstring.

    Parameters
    ----------
    raw_response:
        The LLM's raw text output.
    sanity_instance:
        An Instance-like dict with keys ``capacity``, ``items``. Used
        to construct one realistic call to `score`; only the first
        item and a small synthetic bin array are used.

    Returns
    -------
    dict with keys status, cleaned_code, score_fn, error, reasoning,
    format_detected.
    """
    extraction = extract_code(raw_response)
    reasoning = extraction["reasoning"]
    format_detected = extraction["format_detected"]

    if format_detected == "malformed":
        return _make_failure(
            "failed_extraction",
            None,
            extraction["extraction_notes"],
            reasoning,
            format_detected,
        )

    cleaned = _strip_fences(extraction["code"]).strip()
    if not cleaned:
        return _make_failure(
            "failed_parse",
            cleaned,
            "cleaned code is empty",
            reasoning,
            format_detected,
        )

    try:
        ast.parse(cleaned)
    except SyntaxError as exc:
        return _make_failure(
            "failed_parse",
            cleaned,
            f"SyntaxError: {exc}",
            reasoning,
            format_detected,
        )

    namespace: Dict[str, Any] = {"numpy": np, "np": np}
    try:
        exec(compile(cleaned, "<llm_proposal>", "exec"), namespace)
    except Exception as exc:
        return _make_failure(
            "failed_parse",
            cleaned,
            f"exec failed: {type(exc).__name__}: {exc}",
            reasoning,
            format_detected,
        )

    score_fn = namespace.get("score")
    if not callable(score_fn):
        return _make_failure(
            "failed_signature",
            cleaned,
            "module does not define a callable named `score`",
            reasoning,
            format_detected,
        )

    try:
        sig = inspect.signature(score_fn)
        positional = [
            p
            for p in sig.parameters.values()
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        if len(positional) != 2:
            return _make_failure(
                "failed_signature",
                cleaned,
                f"score has {len(positional)} positional args, expected 2",
                reasoning,
                format_detected,
            )
    except (TypeError, ValueError) as exc:
        return _make_failure(
            "failed_signature",
            cleaned,
            f"inspect.signature failed: {exc}",
            reasoning,
            format_detected,
        )

    try:
        capacity = float(sanity_instance["capacity"])
        item = float(sanity_instance["items"][0])
        bins = np.array([capacity, capacity, capacity], dtype=float)
        result = score_fn(item, bins)
        arr = np.asarray(result)
    except Exception as exc:
        return _make_failure(
            "failed_runtime",
            cleaned,
            f"score raised: {type(exc).__name__}: {exc}",
            reasoning,
            format_detected,
        )

    if arr.shape != bins.shape:
        return _make_failure(
            "failed_runtime",
            cleaned,
            f"score returned shape {arr.shape}, expected {bins.shape}",
            reasoning,
            format_detected,
        )

    return {
        "status": "ok",
        "cleaned_code": cleaned,
        "score_fn": score_fn,
        "error": None,
        "reasoning": reasoning,
        "format_detected": format_detected,
    }
