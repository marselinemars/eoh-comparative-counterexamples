import http.client
import json
import os
import re
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_int(name):
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return int(value)


class InterfaceAPI:
    def __init__(self, api_endpoint, api_key, model_LLM, debug_mode):
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self.model_LLM = model_LLM
        self.debug_mode = debug_mode
        self.n_trial = 5
        self.request_timeout = int(os.getenv("EOH_API_TIMEOUT", "250"))
        self._scheme, self._host, self._port, self._path = self._parse_endpoint(api_endpoint)
        self.log_raw_io = self.debug_mode or _env_bool("EOH_LLM_LOG", False)
        log_dir = os.getenv("EOH_LLM_LOG_DIR")
        self.log_dir = Path(log_dir) if log_dir else Path.cwd() / "llm_logs"
        if self.log_raw_io:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            print(f"- raw LLM request logging enabled: {self.log_dir}")

    def _parse_endpoint(self, api_endpoint):
        endpoint = api_endpoint.strip()
        if "://" not in endpoint:
            endpoint = "https://" + endpoint

        parsed = urlparse(endpoint)
        if not parsed.hostname:
            raise ValueError(f"Invalid API endpoint: {api_endpoint}")

        scheme = parsed.scheme.lower()
        base_path = parsed.path.rstrip("/")
        if base_path.endswith("/chat/completions"):
            request_path = base_path
        elif base_path:
            request_path = base_path + "/chat/completions"
        else:
            request_path = "/v1/chat/completions"

        return scheme, parsed.hostname, parsed.port, request_path

    def _sanitize_headers(self, headers):
        sanitized = dict(headers)
        if "Authorization" in sanitized:
            sanitized["Authorization"] = "Bearer ***REDACTED***"
        return sanitized

    def _new_log_record(self, prompt_content, payload, headers):
        return {
            "log_id": uuid.uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "endpoint": self.api_endpoint,
            "request_path": self._path,
            "model": self.model_LLM,
            "request_timeout_seconds": self.request_timeout,
            "request": {
                "headers": self._sanitize_headers(headers),
                "payload": payload,
                "payload_raw": json.dumps(payload, ensure_ascii=False),
                "prompt_chars": len(prompt_content),
            },
            "attempts": [],
        }

    def _write_log(self, log_record):
        if not self.log_raw_io:
            return

        log_path = self.log_dir / f"{log_record['created_at'].replace(':', '-')}__{log_record['pid']}__{log_record['log_id']}.json"
        with log_path.open("w", encoding="utf-8") as handle:
            json.dump(log_record, handle, indent=2, ensure_ascii=False)

    def _extract_retry_delay(self, response_headers, error_message):
        retry_after = response_headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

        match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", error_message, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))

        return float(os.getenv("EOH_RATE_LIMIT_FALLBACK_SECONDS", "15"))

    def get_response(self, prompt_content):
        payload = {
            "model": self.model_LLM,
            "messages": [
                # {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt_content}
            ],
        }

        reasoning_effort = os.getenv("EOH_REASONING_EFFORT")
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort

        reasoning_format = os.getenv("EOH_REASONING_FORMAT")
        include_reasoning = os.getenv("EOH_INCLUDE_REASONING")
        if reasoning_format:
            payload["reasoning_format"] = reasoning_format
        elif include_reasoning is not None:
            payload["include_reasoning"] = _env_bool("EOH_INCLUDE_REASONING")

        max_completion_tokens = _env_int("EOH_MAX_COMPLETION_TOKENS")
        if max_completion_tokens is not None:
            payload["max_completion_tokens"] = max_completion_tokens

        payload_explanation = json.dumps(payload)

        headers = {
            "Authorization": "Bearer " + self.api_key,
            "User-Agent": "Apifox/1.0.0 (https://apifox.com)",
            "Content-Type": "application/json",
            "x-api2d-no-cache": 1,
        }

        log_record = self._new_log_record(prompt_content, payload, headers)
        response = None
        n_trial = 0
        while True:
            if n_trial >= self.n_trial:
                log_record["final_response"] = response
                self._write_log(log_record)
                return response

            attempt = {
                "attempt_number": len(log_record["attempts"]) + 1,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "counted_retry_number": n_trial + 1,
            }
            try:
                connection_cls = (
                    http.client.HTTPConnection
                    if self._scheme == "http"
                    else http.client.HTTPSConnection
                )
                conn = connection_cls(self._host, self._port, timeout=self.request_timeout)
                conn.request("POST", self._path, payload_explanation, headers)
                res = conn.getresponse()
                data = res.read().decode("utf-8")
                attempt["http_status"] = res.status
                attempt["response_headers"] = dict(res.getheaders())
                attempt["raw_response_body"] = data
                json_data = json.loads(data)
                attempt["parsed_response"] = json_data
                error_message = json_data.get("error", {}).get("message", data)
                if res.status == 429:
                    retry_delay = self._extract_retry_delay(attempt["response_headers"], error_message)
                    retry_delay = max(1.0, retry_delay + float(os.getenv("EOH_RATE_LIMIT_BUFFER_SECONDS", "1")))
                    attempt["rate_limit_backoff_seconds"] = retry_delay
                    attempt["rate_limit_counted_as_retry"] = False
                    if self.debug_mode:
                        print(f"Rate limited by LLM API. Waiting {retry_delay:.2f}s before retrying...")
                    time.sleep(retry_delay)
                    continue
                if res.status >= 400:
                    raise RuntimeError(
                        f"API returned status {res.status}: "
                        + error_message
                    )
                choice = json_data["choices"][0]
                response = choice["message"]["content"]
                attempt["finish_reason"] = choice.get("finish_reason")
                attempt["usage"] = json_data.get("usage")
                attempt["parsed_content"] = response
                break
            except Exception as exc:
                n_trial += 1
                attempt["error"] = f"{type(exc).__name__}: {exc}"
                attempt["traceback"] = traceback.format_exc()
                attempt["counted_retry_number"] = n_trial
                attempt["counted_as_retry"] = True
                if self.debug_mode:
                    print(f"Error in API. Restarting the process... {exc}")
                continue
            finally:
                attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
                log_record["attempts"].append(attempt)
                log_record["final_response"] = response
                self._write_log(log_record)
                try:
                    conn.close()
                except Exception:
                    pass
             

        return response
