#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

HTTP_TIMEOUT = 30
RAGFLOW_API_URL_ENV = "RAGFLOW_API_URL"
RAGFLOW_API_KEY_ENV = "RAGFLOW_API_KEY"


class ScriptError(Exception):
    pass


class ConfigError(ScriptError):
    pass


class ApiError(ScriptError):
    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        api_code: Any | None = None,
        response_payload: Any | None = None,
        response_body: str | None = None,
    ):
        super().__init__(message)
        self.http_status = http_status
        self.api_code = api_code
        self.response_payload = response_payload
        self.response_body = response_body


class DataError(ScriptError):
    pass


def current_timestamp() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def configure_stdio_utf8() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        return

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            continue


def add_runtime_config_arguments(parser: Any) -> None:
    requirement = (
        f"Runtime prerequisites: set {RAGFLOW_API_URL_ENV} and {RAGFLOW_API_KEY_ENV} "
        "in the environment before running this script."
    )
    existing_epilog = getattr(parser, "epilog", None)
    parser.epilog = f"{existing_epilog}\n\n{requirement}" if existing_epilog else requirement


def _require_env_var(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    raise ConfigError(f"{name} environment variable is required.")


def resolve_base_url(cli_base_url: str | None = None) -> str:
    base_url = (cli_base_url or "").strip() or _require_env_var(RAGFLOW_API_URL_ENV)

    parsed = urllib.parse.urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ConfigError(
            f"Invalid {RAGFLOW_API_URL_ENV}. Use an absolute URL such as http://127.0.0.1:9380."
        )
    return base_url.rstrip("/")


def require_api_key(api_key: str | None = None) -> str:
    api_key = (api_key or "").strip() or _require_env_var(RAGFLOW_API_KEY_ENV)
    return api_key


def resolve_runtime_config(args: Any) -> tuple[str, str]:
    base_url = resolve_base_url(getattr(args, "base_url", None))
    api_key = require_api_key(getattr(args, "api_key", None))
    return base_url, api_key


def decode_json_response(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise ApiError("Received a non-JSON response from the server.") from exc

    if not isinstance(payload, dict):
        raise DataError("Expected a JSON object from the server.")
    return payload


def decode_response_text(body: bytes) -> str | None:
    if not body:
        return None
    try:
        text = body.decode("utf-8", errors="replace").strip()
    except Exception:
        return None
    return text or None


def decode_json_body(body: bytes) -> Any | None:
    text = decode_response_text(body)
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def extract_error_message(body: bytes) -> str | None:
    payload = decode_json_body(body)
    if not isinstance(payload, dict):
        return None

    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return None


def serialize_script_error(exc: ScriptError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": exc.__class__.__name__,
        "message": str(exc),
    }
    if isinstance(exc, ApiError):
        if exc.http_status is not None:
            payload["http_status"] = exc.http_status
        if exc.api_code is not None:
            payload["api_code"] = exc.api_code
        if exc.response_payload is not None:
            payload["response"] = exc.response_payload
        elif exc.response_body:
            payload["response_body"] = exc.response_body
    return payload


def request_json(
    url: str,
    api_key: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    content_type: str | None = None,
    accept: str = "application/json",
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    if accept:
        headers["Accept"] = accept
    if content_type:
        headers["Content-Type"] = content_type

    request_obj = urllib.request.Request(url, headers=headers, data=body, method=method)

    try:
        with urllib.request.urlopen(request_obj, timeout=HTTP_TIMEOUT) as response:
            return decode_json_response(response.read())
    except urllib.error.HTTPError as exc:
        body_bytes = exc.read()
        response_payload = decode_json_body(body_bytes)
        response_text = decode_response_text(body_bytes)
        message = extract_error_message(body_bytes)
        if message:
            raise ApiError(
                message,
                http_status=exc.code,
                api_code=response_payload.get("code") if isinstance(response_payload, dict) else None,
                response_payload=response_payload,
                response_body=response_text,
            ) from None
        raise ApiError(
            f"HTTP request failed with status {exc.code}.",
            http_status=exc.code,
            api_code=response_payload.get("code") if isinstance(response_payload, dict) else None,
            response_payload=response_payload,
            response_body=response_text,
        ) from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise ApiError(f"HTTP request failed: {reason}") from None


def ensure_success(payload: dict[str, Any]) -> dict[str, Any]:
    code = payload.get("code")
    if code != 0:
        message = payload.get("message") or f"API returned code {code}."
        raise ApiError(str(message), api_code=code, response_payload=payload)
    return payload


def format_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
