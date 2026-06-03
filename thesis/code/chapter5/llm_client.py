"""
thesis/code/chapter5/llm_client.py

Provider-pluggable LLM client for the chapter-5 proposal runner.
Supports two providers over OpenAI-compatible REST surfaces:

  - "gemini"  → gemini-2.5-pro via
                https://generativelanguage.googleapis.com/v1beta/openai
                Primary model per the 2026-04-21 decisions-log entry.
  - "groq"    → llama-3.3-70b-versatile via
                https://api.groq.com/openai/v1
                Provisional backup per the 2026-04-22 decisions-log
                entry. Honors `seed`; does not accept `reasoning_effort`.

Call through `call_llm(provider=..., ...)` for all new code.
`call_gemini` is a thin backward-compat alias for the runner's
existing import path.

Credentials: read from env. `GEMINI_API_KEY` or `GOOGLE_API_KEY`
for gemini; `GROQ_API_KEY` for groq.
"""
from __future__ import annotations

import http.client
import json
import math
import os
import subprocess
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

# Model strings per provider. Changing a value here swaps the model
# for all chapter-5 LLM work.
MODEL_IDS: Dict[str, str] = {
    "gemini": "gemini-2.5-pro",
    "groq": "llama-3.3-70b-versatile",
    "vertex": "gemini-2.5-pro",
}

PROVIDERS = frozenset(MODEL_IDS.keys())

# Legacy alias kept so external code that imports MODEL_ID from
# llm_client continues to work without modification.
MODEL_ID = MODEL_IDS["gemini"]

API_ENDPOINTS: Dict[str, str] = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
    # vertex endpoint is project/location-templated; resolved at call time.
    "vertex": "https://aiplatform.googleapis.com",
}

# Per-provider max_output_tokens defaults. Gemini's reasoning-model
# default (8192) is sized to accommodate hidden chain-of-thought
# tokens; Groq/Llama is non-reasoning and produces ~540 visible
# tokens on the chapter-5 smoke prompt, so a smaller reservation
# fits within Groq's free-tier 12k TPM budget. See
# thesis/docs/01_decisions_log.md, 2026-04-22 entry
# ("Per-provider max_output_tokens sizing" subsection).
MAX_OUTPUT_TOKENS_DEFAULTS: Dict[str, int] = {
    "gemini": 8192,
    "groq": 2048,
    "vertex": 8192,
}

REQUEST_PATH_SUFFIX = "/chat/completions"

VALID_REASONING_EFFORT = frozenset({"low", "medium", "high"})


def _resolve_api_key(provider: str) -> str:
    """Env-var lookup by provider. Raises RuntimeError if missing."""
    if provider == "gemini":
        k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not k:
            raise RuntimeError(
                "No API key found for provider 'gemini': set "
                "GEMINI_API_KEY or GOOGLE_API_KEY in the environment."
            )
        return k
    if provider == "groq":
        k = os.environ.get("GROQ_API_KEY")
        if not k:
            raise RuntimeError(
                "No API key found for provider 'groq': set "
                "GROQ_API_KEY in the environment."
            )
        return k
    raise ValueError(
        f"Unknown provider {provider!r}; valid providers: {sorted(PROVIDERS)}"
    )


def _post_chat_completions(
    endpoint: str,
    payload: Dict[str, Any],
    api_key: str,
    timeout_seconds: float,
) -> Any:
    """Shared HTTP POST helper. Returns (status, body_text). Does
    not parse JSON or interpret the body — caller handles that."""
    parsed = urlparse(endpoint)
    host = parsed.hostname
    if host is None:
        raise ValueError(f"Invalid endpoint: {endpoint}")
    base_path = parsed.path.rstrip("/")
    path = (
        base_path + REQUEST_PATH_SUFFIX
        if base_path
        else REQUEST_PATH_SUFFIX
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    conn = http.client.HTTPSConnection(host, timeout=timeout_seconds)
    try:
        conn.request("POST", path, json.dumps(payload), headers)
        res = conn.getresponse()
        body = res.read().decode("utf-8")
    finally:
        conn.close()
    return res.status, body


def _extract_error_message(obj: Any) -> str:
    """Tolerant error extraction. Handles OpenAI's dict-shaped
    `{"error": {...}}` and Google's native `[{"error": {...}}]`."""
    if isinstance(obj, dict):
        err = obj.get("error")
        if isinstance(err, dict):
            return err.get("message") or json.dumps(err)
        if err is not None:
            return json.dumps(err)
        return json.dumps(obj)[:500]
    if isinstance(obj, list) and obj:
        for item in obj:
            if isinstance(item, dict):
                err = item.get("error")
                if isinstance(err, dict):
                    return err.get("message") or json.dumps(err)
        return json.dumps(obj)[:500]
    return str(obj)[:500]


def _call_gemini(
    prompt: str,
    model: str,
    temperature: float,
    max_output_tokens: int,
    seed: Optional[int],
    reasoning_effort: Optional[str],
    timeout_seconds: float,
) -> Dict[str, Any]:
    """Send a chat-completion request to the Gemini OpenAI shim.

    Does NOT include `seed` in the payload (the shim rejects it with
    400 INVALID_ARGUMENT; confirmed 2026-04-21). Does include
    `reasoning_effort` when non-None. Returns the structured dict
    described in the module docstring.
    """
    if (
        reasoning_effort is not None
        and reasoning_effort not in VALID_REASONING_EFFORT
    ):
        raise ValueError(
            f"reasoning_effort must be one of {sorted(VALID_REASONING_EFFORT)} "
            f"or None; got {reasoning_effort!r}"
        )
    api_key = _resolve_api_key("gemini")
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_completion_tokens": max_output_tokens,
    }
    # `seed` intentionally absent; Gemini shim rejects it. We still
    # return seed_requested for provenance traceability.
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort

    status, body = _post_chat_completions(
        API_ENDPOINTS["gemini"], payload, api_key, timeout_seconds
    )
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse Gemini response as JSON "
            f"(status={status}): {body[:500]}"
        ) from exc

    if status >= 400:
        raise RuntimeError(
            f"Gemini API returned {status}: {_extract_error_message(parsed)} "
            f"(raw body prefix: {body[:300]})"
        )
    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"Gemini API returned status {status} with non-dict "
            f"body (type={type(parsed).__name__}): {body[:500]}"
        )

    choices = parsed.get("choices") or []
    if not choices:
        raise RuntimeError(f"Gemini returned no choices: {body[:500]}")
    choice = choices[0]
    text = choice.get("message", {}).get("content", "")

    return {
        "text": text,
        "model": model,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "reasoning_effort": reasoning_effort,
        "seed_requested": seed,
        "seed_honored": False,  # Gemini shim rejects seed entirely.
        "raw_response_metadata": {
            "usage": parsed.get("usage"),
            "finish_reason": choice.get("finish_reason"),
            "system_fingerprint": parsed.get("system_fingerprint"),
            "id": parsed.get("id"),
            "created": parsed.get("created"),
            "model_returned": parsed.get("model"),
        },
    }


def _call_groq(
    prompt: str,
    model: str,
    temperature: float,
    max_output_tokens: int,
    seed: Optional[int],
    reasoning_effort: Optional[str],
    timeout_seconds: float,
) -> Dict[str, Any]:
    """Send a chat-completion request to Groq.

    Groq accepts `seed` (honored for deterministic output). Groq
    does NOT accept `reasoning_effort` on non-reasoning Llama
    models; we silently drop it from the payload but still log
    the caller-requested value into the returned metadata for
    provenance.
    """
    api_key = _resolve_api_key("groq")
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_completion_tokens": max_output_tokens,
    }
    if seed is not None:
        payload["seed"] = int(seed)
    # reasoning_effort intentionally NOT added to payload — Groq
    # rejects it on non-reasoning models. We log it for provenance.

    status, body = _post_chat_completions(
        API_ENDPOINTS["groq"], payload, api_key, timeout_seconds
    )
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse Groq response as JSON "
            f"(status={status}): {body[:500]}"
        ) from exc

    if status >= 400:
        raise RuntimeError(
            f"Groq API returned {status}: {_extract_error_message(parsed)} "
            f"(raw body prefix: {body[:300]})"
        )
    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"Groq API returned status {status} with non-dict "
            f"body (type={type(parsed).__name__}): {body[:500]}"
        )

    choices = parsed.get("choices") or []
    if not choices:
        raise RuntimeError(f"Groq returned no choices: {body[:500]}")
    choice = choices[0]
    text = choice.get("message", {}).get("content", "")

    # Groq accepted the seed payload (we reached this branch via
    # status<400). Record seed_honored=True when the caller provided
    # a seed; None/False otherwise. This is "honored by acceptance";
    # byte-level determinism across repeated calls is typical but
    # not guaranteed by Groq without further flags.
    seed_honored: Optional[bool]
    if seed is None:
        seed_honored = None
    else:
        seed_honored = True

    return {
        "text": text,
        "model": model,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        # Provenance: we log what the caller asked for even though
        # Groq discarded it; downstream can see the mismatch.
        "reasoning_effort": reasoning_effort,
        "seed_requested": seed,
        "seed_honored": seed_honored,
        "raw_response_metadata": {
            "usage": parsed.get("usage"),
            "finish_reason": choice.get("finish_reason"),
            "system_fingerprint": parsed.get("system_fingerprint"),
            "id": parsed.get("id"),
            "created": parsed.get("created"),
            "model_returned": parsed.get("model"),
        },
    }


# Module-level cache for the gcloud-issued access token. Tokens last
# ~1 hour; refresh well before that to absorb clock skew and the
# variability Google sometimes applies to token lifetime.
_VERTEX_TOKEN_TTL_SECONDS = 30 * 60
_vertex_token_cache: Tuple[Optional[str], float] = (None, 0.0)


def _resolve_vertex_api_key() -> Optional[str]:
    """Return a Google Cloud API key for Vertex if the env supplies
    one (``VERTEX_API_KEY`` or, as a convenience fallback,
    ``GEMINI_API_KEY``/``GOOGLE_API_KEY``). Returns None when no
    API key is set; callers fall back to bearer-token auth.

    API-key auth is the right path when the project uses
    Vertex AI Express Mode or has issued a Google Cloud API key
    (e.g. ``AQ.``-prefixed) instead of OAuth user credentials.
    """
    for var in ("VERTEX_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        v = os.environ.get(var)
        if v:
            return v.strip()
    return None


def _resolve_vertex_access_token() -> str:
    """Return a Vertex AI bearer token.

    Priority:
      1. ``GOOGLE_CLOUD_ACCESS_TOKEN`` env var (caller-managed).
      2. In-memory cache, if not yet expired.
      3. Shell out to ``gcloud auth print-access-token`` and cache.

    Raises RuntimeError if gcloud is unavailable or fails.
    """
    global _vertex_token_cache
    forced = os.environ.get("GOOGLE_CLOUD_ACCESS_TOKEN")
    if forced:
        return forced.strip()
    cached, expires_at = _vertex_token_cache
    now = time.time()
    if cached is not None and now < expires_at:
        return cached
    proc = None
    last_err: Optional[BaseException] = None
    # Windows installs gcloud as gcloud.cmd; PATH-resolution from
    # subprocess does not always pick up .cmd shims. Try common names.
    for binary in ("gcloud", "gcloud.cmd", "gcloud.exe"):
        try:
            proc = subprocess.run(
                [binary, "auth", "print-access-token"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            break
        except FileNotFoundError as exc:
            last_err = exc
            continue
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"`{binary} auth print-access-token` failed "
                f"(rc={exc.returncode}): {exc.stderr.strip()[:300]}"
            ) from exc
    if proc is None:
        raise RuntimeError(
            "vertex provider could not locate the `gcloud` CLI. Either add "
            "it to PATH for this shell, or paste a token into the env: "
            "`export GOOGLE_CLOUD_ACCESS_TOKEN=$(gcloud auth print-access-token)` "
            "(token is valid ~1 hour)."
        ) from last_err
    token = proc.stdout.strip()
    if not token:
        raise RuntimeError("`gcloud auth print-access-token` returned empty token.")
    _vertex_token_cache = (token, now + _VERTEX_TOKEN_TTL_SECONDS)
    return token


def _vertex_thinking_budget(reasoning_effort: Optional[str]) -> int:
    """Map OpenAI-style reasoning_effort to a Vertex thinkingBudget.

    Vertex semantics for gemini-2.5-pro thinkingBudget:
      -1   → dynamic (model picks; recommended default)
       0   → thinking disabled (not supported on 2.5-pro; min is 128)
       N   → exact budget in tokens
    We map low/medium/high to small/medium/large explicit budgets so
    the chapter-6 records remain comparable to the OpenAI-shim runs.
    None → -1 (dynamic, model default).
    """
    if reasoning_effort is None:
        return -1
    # "medium" is capped at 10240 (not -1 dynamic) because Vertex
    # generateContent counts thinking + visible against the same
    # max_output_tokens budget. With max_output=12288 and dynamic
    # thinking, hard prompts trigger ~11.8K thoughts and starve the
    # visible-token output to ~490 tokens — truncating the code block
    # mid-stream and producing finish=MAX_TOKENS records that fail
    # sanitization. Capping thinking at 10240 reserves >=2048 visible
    # budget (original p90 visible was 1073). Trades a small thinking
    # parity gap on the hardest-prompt tail (AI-Studio p99 was 16456
    # thinking) for guaranteed clean completion.
    return {
        "low": 1024,
        "medium": 10240,
        "high": 24576,
    }[reasoning_effort]


def _call_vertex(
    prompt: str,
    model: str,
    temperature: float,
    max_output_tokens: int,
    seed: Optional[int],
    reasoning_effort: Optional[str],
    timeout_seconds: float,
) -> Dict[str, Any]:
    """Send a generateContent request to Vertex AI.

    Auth is the gcloud-issued bearer token. Endpoint shape:
      {API_ENDPOINTS[vertex]}/v1/projects/{PROJECT}/locations/{LOCATION}
        /publishers/google/models/{MODEL}:generateContent

    Reads project from GOOGLE_CLOUD_PROJECT, location from
    GOOGLE_CLOUD_LOCATION (default "global"). Caller passing seed is
    accepted but Vertex's generateContent surface does not honor it
    for gemini-2.5-pro at the time of writing — recorded as
    seed_honored=False for provenance, matching the gemini provider.
    """
    if (
        reasoning_effort is not None
        and reasoning_effort not in VALID_REASONING_EFFORT
    ):
        raise ValueError(
            f"reasoning_effort must be one of {sorted(VALID_REASONING_EFFORT)} "
            f"or None; got {reasoning_effort!r}"
        )
    api_key = _resolve_vertex_api_key()
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

    if api_key:
        # Vertex AI Express Mode / Google Cloud API key path.
        # Uses the publisher route without per-project scoping.
        base = API_ENDPOINTS["vertex"].rstrip("/")
        path = (
            f"/v1/publishers/google/models/{model}:generateContent"
        )
        token = None
    else:
        if not project:
            raise RuntimeError(
                "vertex provider requires either VERTEX_API_KEY/GEMINI_API_KEY "
                "(API-key auth) or GOOGLE_CLOUD_PROJECT (bearer-token auth) "
                "to be set."
            )
        token = _resolve_vertex_access_token()
        base = API_ENDPOINTS["vertex"].rstrip("/")
        path = (
            f"/v1/projects/{project}/locations/{location}"
            f"/publishers/google/models/{model}:generateContent"
        )

    payload: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
            "thinkingConfig": {
                "thinkingBudget": _vertex_thinking_budget(reasoning_effort),
            },
        },
    }

    parsed_url = urlparse(base)
    host = parsed_url.hostname
    if host is None:
        raise ValueError(f"Invalid vertex endpoint: {base}")
    if api_key:
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
    else:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    body_json = json.dumps(payload)
    # 429 retry-with-backoff. Vertex's Dynamic Shared Quota refills
    # second-to-second; a brief sleep often clears transient pressure.
    # 401 retry: gcloud token expired mid-run. Force a fresh token
    # and retry once before bubbling.
    # Cap 429 retries at 3 (backoff 30s/60s/90s); 401 retried once
    # with no backoff (token refresh is the fix).
    backoffs_429 = [30, 60, 90]
    status = 0
    body = ""
    last_attempt_idx = 0
    retried_401 = False
    attempt_idx = 0
    while True:
        last_attempt_idx = attempt_idx
        conn = http.client.HTTPSConnection(host, timeout=timeout_seconds)
        try:
            conn.request("POST", path, body_json, headers)
            res = conn.getresponse()
            body = res.read().decode("utf-8")
            status = res.status
        finally:
            conn.close()
        if status == 401 and not retried_401 and not api_key:
            # Bust the cache and force a fresh token, then retry once.
            # API-key auth has no equivalent refresh path; a 401 with an
            # API key means the key itself is bad, not stale.
            global _vertex_token_cache
            _vertex_token_cache = (None, 0.0)
            token = _resolve_vertex_access_token()
            headers["Authorization"] = f"Bearer {token}"
            retried_401 = True
            continue
        if status != 429:
            break
        if attempt_idx >= len(backoffs_429):
            break
        time.sleep(backoffs_429[attempt_idx])
        attempt_idx += 1
        if not api_key:
            # Refresh token if we crossed the cache boundary during backoff.
            token = _resolve_vertex_access_token()
            headers["Authorization"] = f"Bearer {token}"

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse Vertex response as JSON "
            f"(status={status}): {body[:500]}"
        ) from exc

    if status >= 400:
        retry_note = (
            f" [after {last_attempt_idx + 1} attempts incl. 429-backoff]"
            if status == 429 and last_attempt_idx > 0
            else ""
        )
        raise RuntimeError(
            f"Vertex API returned {status}{retry_note}: "
            f"{_extract_error_message(parsed)} "
            f"(raw body prefix: {body[:300]})"
        )
    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"Vertex API returned status {status} with non-dict body: "
            f"{body[:500]}"
        )

    candidates = parsed.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Vertex returned no candidates: {body[:500]}")
    cand = candidates[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))

    usage = parsed.get("usageMetadata") or {}
    return {
        "text": text,
        "model": model,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "reasoning_effort": reasoning_effort,
        "seed_requested": seed,
        "seed_honored": False,
        "raw_response_metadata": {
            "usage": {
                "prompt_tokens": usage.get("promptTokenCount"),
                "completion_tokens": usage.get("candidatesTokenCount"),
                "total_tokens": usage.get("totalTokenCount"),
                "thoughts_token_count": usage.get("thoughtsTokenCount"),
            },
            "finish_reason": cand.get("finishReason"),
            "model_returned": parsed.get("modelVersion"),
            "response_id": parsed.get("responseId"),
            "vertex_project": project,
            "vertex_location": location,
        },
    }


def call_llm(
    prompt: str,
    provider: str = "gemini",
    model: Optional[str] = None,
    temperature: float = 1.0,
    max_output_tokens: Optional[int] = None,
    seed: Optional[int] = None,
    reasoning_effort: Optional[str] = "low",
    timeout_seconds: float = 90.0,
) -> Dict[str, Any]:
    """Dispatch to the selected provider's chat-completions endpoint.

    If `max_output_tokens` is None, the provider-specific default
    from MAX_OUTPUT_TOKENS_DEFAULTS is used (gemini: 8192,
    groq: 2048). Callers that pass an explicit value override the
    default.

    Returns a structured dict (same shape as _call_gemini /
    _call_groq) plus a `provider` field identifying the backend
    that served the response.
    """
    if provider not in PROVIDERS:
        raise ValueError(
            f"Unknown provider {provider!r}; valid: {sorted(PROVIDERS)}"
        )
    if model is None:
        model = MODEL_IDS[provider]
    if max_output_tokens is None:
        max_output_tokens = MAX_OUTPUT_TOKENS_DEFAULTS[provider]

    if provider == "gemini":
        result = _call_gemini(
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            seed=seed,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
        )
    elif provider == "groq":
        result = _call_groq(
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            seed=seed,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
        )
    elif provider == "vertex":
        result = _call_vertex(
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            seed=seed,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
        )
    else:
        # Unreachable given the PROVIDERS membership check, but kept
        # for defensive clarity.
        raise ValueError(f"Unhandled provider {provider!r}")

    result["provider"] = provider
    return result


def call_gemini(
    prompt: str,
    model: str = MODEL_IDS["gemini"],
    temperature: float = 1.0,
    max_output_tokens: int = 8192,
    seed: Optional[int] = None,
    reasoning_effort: Optional[str] = "low",
    timeout_seconds: float = 90.0,
) -> Dict[str, Any]:
    """Thin backward-compat alias for `call_llm(provider="gemini", ...)`.

    Preserves the existing runner import path. New code should use
    `call_llm` directly.
    """
    return call_llm(
        prompt=prompt,
        provider="gemini",
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        seed=seed,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
    )
