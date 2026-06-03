"""Tests for thesis/code/chapter5/sanitize.py."""
from __future__ import annotations

import pytest

from thesis.code.chapter5.sanitize import sanitize


# Small sanity instance fixture: 3-item "packing" at capacity 100.
SANITY_INSTANCE = {
    "capacity": 100,
    "num_items": 3,
    "items": [40, 50, 60],
}


def test_clean_code_passes():
    raw = (
        "import numpy as np\n\n"
        "def score(item, bins):\n"
        "    return np.ones_like(bins)\n"
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "ok", result
    assert callable(result["score_fn"])
    assert result["error"] is None


def test_python_fence_stripped():
    raw = (
        "```python\n"
        "import numpy as np\n\n"
        "def score(item, bins):\n"
        "    return np.ones_like(bins)\n"
        "```\n"
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "ok", result


def test_bare_fence_stripped():
    raw = (
        "```\n"
        "import numpy as np\n\n"
        "def score(item, bins):\n"
        "    return np.ones_like(bins)\n"
        "```\n"
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "ok", result


def test_syntax_error_returns_failed_parse():
    raw = "def score(item, bins: !! this is not valid python\n"
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "failed_parse", result
    assert "SyntaxError" in (result["error"] or "")


def test_missing_score_returns_failed_signature():
    raw = (
        "import numpy as np\n\n"
        "def scorre(item, bins):\n"  # typo
        "    return np.ones_like(bins)\n"
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "failed_signature", result


def test_wrong_arity_score_returns_failed_signature():
    raw = (
        "import numpy as np\n\n"
        "def score(item):\n"  # only 1 positional arg
        "    return item\n"
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "failed_signature", result


def test_score_raises_returns_failed_runtime():
    raw = (
        "import numpy as np\n\n"
        "def score(item, bins):\n"
        "    raise RuntimeError('oops')\n"
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "failed_runtime", result
    assert "RuntimeError" in (result["error"] or "")


def test_score_wrong_shape_returns_failed_runtime():
    raw = (
        "import numpy as np\n\n"
        "def score(item, bins):\n"
        "    return np.zeros((len(bins) + 1,))\n"  # wrong length
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "failed_runtime", result
    assert "shape" in (result["error"] or "").lower()


def test_none_response_returns_failed_extraction():
    result = sanitize(None, SANITY_INSTANCE)
    assert result["status"] == "failed_extraction"


def test_empty_response_returns_failed_extraction():
    result = sanitize("", SANITY_INSTANCE)
    assert result["status"] == "failed_extraction"


# --- Stage-1 extraction tests ---------------------------------------

from thesis.code.chapter5.sanitize import extract_code  # noqa: E402


_GOOD_CODE = (
    "import numpy as np\n\n"
    "def score(item, bins):\n"
    "    return np.ones_like(bins)\n"
)


def test_step_by_step_reasoning_then_code_happy_path():
    raw = (
        "STEP_BY_STEP_REASONING\n"
        "1. The incumbent loses on near-median instances.\n"
        "2. Its weighting on mid-size bins is too low.\n"
        "3. I will increase the mid-bin weight.\n"
        "4. This should reduce bin count on those cases.\n"
        "CODE\n"
        f"{_GOOD_CODE}"
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "ok", result
    assert result["format_detected"] == "step_by_step_reasoning_then_code"
    assert result["reasoning"] is not None
    assert "near-median" in result["reasoning"]
    assert "STEP_BY_STEP_REASONING" not in result["cleaned_code"]
    assert "CODE" not in result["cleaned_code"].splitlines()[0]


def test_analysis_then_code_happy_path():
    raw = (
        "ANALYSIS\n"
        "The reference heuristic dominates on large-tail inputs.\n"
        "CODE\n"
        f"{_GOOD_CODE}"
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "ok", result
    assert result["format_detected"] == "analysis_then_code"
    assert result["reasoning"] is not None
    assert "large-tail" in result["reasoning"]


def test_malformed_response_returns_failed_extraction():
    raw = "Hello, I am an LLM and I would love to help you today."
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "failed_extraction", result
    assert result["format_detected"] == "malformed"


def test_markdown_fences_inside_code_section_stripped():
    raw = (
        "STEP_BY_STEP_REASONING\n"
        "1. ...\n"
        "CODE\n"
        "```python\n"
        f"{_GOOD_CODE}"
        "```\n"
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "ok", result
    assert "```" not in result["cleaned_code"]


def test_code_word_quoted_in_reasoning_splits_at_last_code_marker():
    raw = (
        "STEP_BY_STEP_REASONING\n"
        "1. I will now write some CODE below.\n"
        "2. The CODE will be a score function.\n"
        "CODE\n"
        f"{_GOOD_CODE}"
    )
    result = extract_code(raw)
    assert result["format_detected"] == "step_by_step_reasoning_then_code"
    # Reasoning must still contain the quoted CODE references from
    # the narrative (i.e., we did NOT split at the first marker).
    assert "write some CODE below" in result["reasoning"]
    assert "score function" in result["reasoning"]
    # Extracted code must parse and start with import.
    assert result["code"].lstrip().startswith("import numpy")


def test_reasoning_over_400_words_still_accepted():
    # Build a long reasoning blob (> 400 words).
    long_reasoning = "observation " * 500  # 500 words
    raw = (
        "STEP_BY_STEP_REASONING\n"
        f"{long_reasoning}\n"
        "CODE\n"
        f"{_GOOD_CODE}"
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "ok", result
    assert len(result["reasoning"].split()) > 400


def test_extracted_code_with_wrong_signature_returns_failed_signature():
    raw = (
        "STEP_BY_STEP_REASONING\n"
        "1. reasoning...\n"
        "CODE\n"
        "import numpy as np\n\n"
        "def score(item):\n"
        "    return item\n"
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "failed_signature", result
    assert result["format_detected"] == "step_by_step_reasoning_then_code"


def test_extracted_code_that_raises_returns_failed_runtime():
    raw = (
        "STEP_BY_STEP_REASONING\n"
        "1. reasoning...\n"
        "CODE\n"
        "import numpy as np\n\n"
        "def score(item, bins):\n"
        "    raise RuntimeError('boom')\n"
    )
    result = sanitize(raw, SANITY_INSTANCE)
    assert result["status"] == "failed_runtime", result
    assert result["format_detected"] == "step_by_step_reasoning_then_code"
