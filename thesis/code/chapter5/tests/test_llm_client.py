"""Hermetic tests for thesis/code/chapter5/llm_client.py.

All tests mock the HTTP layer — no real API calls, no env-var
credential reads beyond setting dummy `GEMINI_API_KEY` and
`GROQ_API_KEY` in-process so the client's auth-precheck passes.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def dummy_api_keys(monkeypatch):
    """Every test in this module gets dummy keys for both
    providers; never touch the real env."""
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-gemini-key-not-a-real-credential")
    monkeypatch.setenv("GROQ_API_KEY", "dummy-groq-key-not-a-real-credential")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    yield


def _ok_response_bytes(
    content: str = "def score(item, bins):\n    return bins\n",
    model: str = "gemini-2.5-pro",
):
    payload = {
        "id": "chat-test-001",
        "model": model,
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        },
        "created": 1_700_000_000,
    }
    return json.dumps(payload).encode("utf-8")


def _mocked_conn(status: int, body_bytes: bytes, captured: dict):
    """Build a mock HTTPSConnection that captures request args and
    returns a response with the given status and body."""
    conn = MagicMock()

    def fake_request(method, path, body, headers):
        captured["method"] = method
        captured["path"] = path
        captured["host_from_conn"] = None  # set below on construction
        captured["body"] = body
        captured["headers"] = dict(headers) if headers else {}

    response = MagicMock()
    response.status = status
    response.read.return_value = body_bytes
    conn.request.side_effect = fake_request
    conn.getresponse.return_value = response
    return conn


# --- Gemini provider tests (provider="gemini" via call_llm) ------------

def test_payload_does_not_contain_seed():
    """Even with seed=12345, the Gemini request payload must not
    include the `seed` field — Gemini's OpenAI shim rejects it."""
    from thesis.code.chapter5.llm_client import call_llm

    captured = {}
    mock_conn = _mocked_conn(200, _ok_response_bytes(), captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        call_llm("hello", provider="gemini", seed=12345)

    payload = json.loads(captured["body"])
    assert "seed" not in payload, (
        f"seed must not appear in Gemini payload; got keys "
        f"{sorted(payload.keys())}"
    )
    assert payload["model"] == "gemini-2.5-pro"
    assert payload["temperature"] == 1.0
    assert payload["max_completion_tokens"] == 8192
    assert payload["messages"][0]["content"] == "hello"


def test_metadata_records_seed_honored_false_when_seed_requested():
    from thesis.code.chapter5.llm_client import call_llm

    captured = {}
    mock_conn = _mocked_conn(200, _ok_response_bytes(), captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        result = call_llm("hello", provider="gemini", seed=12345)

    assert result["seed_requested"] == 12345
    assert result["seed_honored"] is False
    assert result["provider"] == "gemini"


def test_metadata_records_seed_requested_even_when_none():
    from thesis.code.chapter5.llm_client import call_llm

    captured = {}
    mock_conn = _mocked_conn(200, _ok_response_bytes(), captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        result = call_llm("hello", provider="gemini", seed=None)

    assert result["seed_requested"] is None
    assert result["seed_honored"] is False


def test_http_400_with_dict_error_raises_with_message():
    from thesis.code.chapter5.llm_client import call_llm

    body = json.dumps(
        {"error": {"message": "test-error-text", "code": 400}}
    ).encode("utf-8")
    captured = {}
    mock_conn = _mocked_conn(400, body, captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        with pytest.raises(RuntimeError) as exc_info:
            call_llm("hello", provider="gemini", seed=None)

    msg = str(exc_info.value)
    assert "400" in msg
    assert "test-error-text" in msg


def test_http_400_with_list_shaped_error_body_handled():
    from thesis.code.chapter5.llm_client import call_llm

    body = json.dumps(
        [{"error": {"message": "list-shaped-error-text", "code": 400}}]
    ).encode("utf-8")
    captured = {}
    mock_conn = _mocked_conn(400, body, captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        with pytest.raises(RuntimeError) as exc_info:
            call_llm("hello", provider="gemini", seed=None)

    msg = str(exc_info.value)
    assert "400" in msg
    assert "list-shaped-error-text" in msg


def test_successful_response_returns_expected_metadata_shape():
    from thesis.code.chapter5.llm_client import call_llm

    captured = {}
    mock_conn = _mocked_conn(200, _ok_response_bytes(), captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        result = call_llm("hello", provider="gemini", seed=42)

    assert result["text"].startswith("def score(item, bins):")
    assert result["model"] == "gemini-2.5-pro"
    assert result["provider"] == "gemini"
    usage = result["raw_response_metadata"]["usage"]
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 50
    assert result["raw_response_metadata"]["finish_reason"] == "stop"


def test_missing_api_key_raises_clear_error(monkeypatch):
    """If neither GEMINI_API_KEY nor GOOGLE_API_KEY is set, raise."""
    from thesis.code.chapter5.llm_client import call_llm

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="API key"):
        call_llm("hello", provider="gemini", seed=None)


def test_payload_includes_reasoning_effort_when_set():
    from thesis.code.chapter5.llm_client import call_llm

    captured = {}
    mock_conn = _mocked_conn(200, _ok_response_bytes(), captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        call_llm("hello", provider="gemini", seed=None, reasoning_effort="low")

    payload = json.loads(captured["body"])
    assert payload.get("reasoning_effort") == "low"


def test_payload_excludes_reasoning_effort_when_none():
    from thesis.code.chapter5.llm_client import call_llm

    captured = {}
    mock_conn = _mocked_conn(200, _ok_response_bytes(), captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        call_llm("hello", provider="gemini", seed=None, reasoning_effort=None)

    payload = json.loads(captured["body"])
    assert "reasoning_effort" not in payload


def test_metadata_includes_reasoning_effort():
    from thesis.code.chapter5.llm_client import call_llm

    captured = {}
    mock_conn = _mocked_conn(200, _ok_response_bytes(), captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        result = call_llm(
            "hello", provider="gemini", seed=None, reasoning_effort="medium"
        )
    assert result["reasoning_effort"] == "medium"

    captured2 = {}
    mock_conn2 = _mocked_conn(200, _ok_response_bytes(), captured2)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn2,
    ):
        result2 = call_llm(
            "hello", provider="gemini", seed=None, reasoning_effort=None
        )
    assert result2["reasoning_effort"] is None


def test_reasoning_effort_rejects_invalid_values():
    from thesis.code.chapter5.llm_client import call_llm

    for bad in ("ultra", "none", "LOW", "", 42, 0.5):
        with pytest.raises(ValueError, match="reasoning_effort"):
            call_llm("hello", provider="gemini", seed=None, reasoning_effort=bad)


# --- Backward-compat alias --------------------------------------------

def test_call_gemini_alias_still_works():
    from thesis.code.chapter5.llm_client import call_gemini

    captured = {}
    mock_conn = _mocked_conn(200, _ok_response_bytes(), captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        result = call_gemini("hello", seed=None)
    assert result["provider"] == "gemini"


# --- Provider dispatch ------------------------------------------------

def test_call_llm_invalid_provider_raises():
    from thesis.code.chapter5.llm_client import call_llm

    with pytest.raises(ValueError, match="provider"):
        call_llm("hello", provider="bogus", seed=None)


def test_call_llm_dispatches_to_groq_when_provider_groq():
    from thesis.code.chapter5.llm_client import call_llm

    groq_ok = _ok_response_bytes(model="llama-3.3-70b-versatile")
    captured = {}
    mock_conn = _mocked_conn(200, groq_ok, captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ) as mock_cls:
        result = call_llm("hello", provider="groq", seed=None)

    # Confirm the host used for the connection is Groq's.
    host_arg = mock_cls.call_args.args[0] if mock_cls.call_args.args else None
    assert host_arg == "api.groq.com", (
        f"Expected Groq host; got {host_arg!r}"
    )
    assert result["provider"] == "groq"
    assert result["model"] == "llama-3.3-70b-versatile"


def test_groq_payload_includes_seed_when_set():
    from thesis.code.chapter5.llm_client import call_llm

    groq_ok = _ok_response_bytes(model="llama-3.3-70b-versatile")
    captured = {}
    mock_conn = _mocked_conn(200, groq_ok, captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        call_llm("hello", provider="groq", seed=98765)

    payload = json.loads(captured["body"])
    assert payload.get("seed") == 98765, (
        f"Groq payload must include seed; got {sorted(payload.keys())}"
    )


def test_groq_payload_excludes_reasoning_effort():
    """Groq rejects reasoning_effort on non-reasoning Llama models;
    client must drop it from the payload even if caller set it."""
    from thesis.code.chapter5.llm_client import call_llm

    groq_ok = _ok_response_bytes(model="llama-3.3-70b-versatile")
    captured = {}
    mock_conn = _mocked_conn(200, groq_ok, captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        result = call_llm(
            "hello", provider="groq", seed=None, reasoning_effort="low"
        )

    payload = json.loads(captured["body"])
    assert "reasoning_effort" not in payload
    # But the caller's value still propagates to the returned
    # metadata for provenance.
    assert result["reasoning_effort"] == "low"


def test_groq_uses_correct_default_model():
    from thesis.code.chapter5.llm_client import call_llm

    groq_ok = _ok_response_bytes(model="llama-3.3-70b-versatile")
    captured = {}
    mock_conn = _mocked_conn(200, groq_ok, captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        call_llm("hello", provider="groq", model=None, seed=None)

    payload = json.loads(captured["body"])
    assert payload["model"] == "llama-3.3-70b-versatile"


def test_groq_missing_api_key_raises_clear_error(monkeypatch):
    from thesis.code.chapter5.llm_client import call_llm

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="API key"):
        call_llm("hello", provider="groq", seed=None)


def test_groq_seed_honored_true_when_seed_provided():
    """On a successful Groq call with seed set, seed_honored=True
    (acceptance-based: Groq accepts seed, we report honored)."""
    from thesis.code.chapter5.llm_client import call_llm

    groq_ok = _ok_response_bytes(model="llama-3.3-70b-versatile")
    captured = {}
    mock_conn = _mocked_conn(200, groq_ok, captured)
    with patch(
        "thesis.code.chapter5.llm_client.http.client.HTTPSConnection",
        return_value=mock_conn,
    ):
        result = call_llm("hello", provider="groq", seed=42)
    assert result["seed_honored"] is True
    assert result["seed_requested"] == 42
