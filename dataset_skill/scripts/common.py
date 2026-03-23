#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import getpass
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

HTTP_TIMEOUT = 30
DEFAULT_MEMORY_FILE = Path.home() / ".codex" / "memories" / "ragflow_credentials.json"


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


def resolve_memory_file(cli_memory_file: str | None = None) -> Path:
    if cli_memory_file:
        return Path(cli_memory_file).expanduser()
    return DEFAULT_MEMORY_FILE


def load_memory_config(memory_file: str | Path | None = None) -> dict[str, Any]:
    path = resolve_memory_file(str(memory_file) if memory_file is not None else None)
    if not path.is_file():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Failed to read memory file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Memory file {path} must contain a JSON object.") from exc

    if not isinstance(payload, dict):
        raise ConfigError(f"Memory file {path} must contain a JSON object.")
    return payload


def save_memory_config(memory_config: dict[str, Any], memory_file: str | Path | None = None) -> Path:
    path = resolve_memory_file(str(memory_file) if memory_file is not None else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(memory_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Failed to write memory file {path}: {exc}") from exc
    return path


def add_runtime_config_arguments(parser: Any) -> None:
    parser.add_argument(
        "--base-url",
        help="Absolute base URL for the RAGFlow server. If omitted, read from --memory-file or prompt interactively.",
    )
    parser.add_argument(
        "--api-key-file",
        help="Path to a file containing the RAGFlow API key. Safer than putting the key on the command line.",
    )
    parser.add_argument(
        "--memory-file",
        help=f"JSON memory file used to read cached credentials (default: {DEFAULT_MEMORY_FILE}).",
    )
    parser.add_argument(
        "--save-to-memory",
        action="store_true",
        help="Save the resolved base URL and API key back to --memory-file after prompting or loading them.",
    )


def _read_api_key_file(api_key_file: str) -> str:
    path = Path(api_key_file).expanduser()
    try:
        api_key = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigError(f"Failed to read API key file {path}: {exc}") from exc
    if not api_key:
        raise ConfigError(f"API key file {path} is empty.")
    return api_key


def _prompt_non_empty(prompt: str, *, secret: bool = False) -> str:
    while True:
        value = getpass.getpass(prompt) if secret else input(prompt)
        value = value.strip()
        if value:
            return value
        print("Value must not be empty.", file=sys.stderr)


def resolve_base_url(cli_base_url: str | None = None, *, memory_config: dict[str, Any] | None = None) -> str:
    raw_value = cli_base_url
    if raw_value is None and memory_config:
        memory_base_url = memory_config.get("base_url")
        if memory_base_url is not None:
            raw_value = str(memory_base_url)

    base_url = (raw_value or "").strip()
    if not base_url:
        base_url = _prompt_non_empty("RAGFlow base URL: ")

    parsed = urllib.parse.urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ConfigError("Invalid base URL. Use an absolute URL such as http://127.0.0.1:9380.")
    return base_url.rstrip("/")


def require_api_key(
    *,
    api_key_file: str | None = None,
    memory_config: dict[str, Any] | None = None,
) -> str:
    api_key = ""
    if api_key_file:
        api_key = _read_api_key_file(api_key_file)
    elif memory_config and memory_config.get("api_key") is not None:
        api_key = str(memory_config.get("api_key") or "").strip()

    if not api_key:
        api_key = _prompt_non_empty("RAGFlow API key: ", secret=True)

    if not api_key:
        raise ConfigError("RAGFlow API key is required.")
    return api_key


def resolve_runtime_config(args: Any) -> tuple[str, str, dict[str, Any]]:
    memory_file = getattr(args, "memory_file", None)
    memory_config = load_memory_config(memory_file)
    base_url = resolve_base_url(getattr(args, "base_url", None), memory_config=memory_config)
    api_key = require_api_key(
        api_key_file=getattr(args, "api_key_file", None),
        memory_config=memory_config,
    )

    if getattr(args, "save_to_memory", False):
        updated_config = dict(memory_config)
        updated_config["base_url"] = base_url
        updated_config["api_key"] = api_key
        save_memory_config(updated_config, memory_file)
        memory_config = updated_config

    return base_url, api_key, memory_config


def parse_dataset_ids_config(raw_value: Any, *, label: str) -> list[str]:
    if raw_value is None:
        return []

    if isinstance(raw_value, list):
        values: list[str] = []
        seen: set[str] = set()
        for item in raw_value:
            value = str(item).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            values.append(value)
        if not values:
            raise ConfigError(f"{label} must include at least one dataset ID when it is set.")
        return values

    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return parse_dataset_ids_config(parsed, label=label)
        if isinstance(parsed, str):
            return parse_dataset_ids_config(parsed.split(","), label=label)
        values = [item.strip() for item in text.split(",") if item.strip()]
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        if not deduped:
            raise ConfigError(f"{label} must include at least one dataset ID when it is set.")
        return deduped

    raise ConfigError(f"{label} must be a JSON array or a comma-separated string.")


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
