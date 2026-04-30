#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Connection test and diagnostic tool for the RAGFlow skill.

Usage:
  python3 scripts/diagnose.py --test       Quick connectivity check
  python3 scripts/diagnose.py --diagnose   Full diagnostic report
  python3 scripts/diagnose.py --test --json
"""

import argparse
import os
from typing import Any

from common import (
    ApiError,
    ScriptError,
    add_runtime_config_arguments,
    configure_stdio_utf8,
    current_timestamp,
    ensure_success,
    format_json,
    request_json,
    resolve_runtime_config,
    RAGFLOW_API_URL_ENV,
    RAGFLOW_API_KEY_ENV,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test the RAGFlow connection and diagnose configuration problems."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--test", action="store_true", help="Quick connectivity check")
    mode.add_argument("--diagnose", action="store_true", help="Full diagnostic report")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")
    add_runtime_config_arguments(parser)
    return parser.parse_args(argv)


def _probe_datasets(base_url: str, api_key: str) -> dict[str, Any]:
    payload = ensure_success(request_json(f"{base_url}/api/v1/datasets", api_key, max_retries=1))
    datasets = payload.get("data")
    return {
        "ok": True,
        "dataset_count": len(datasets) if isinstance(datasets, list) else None,
    }


def _probe_chats(base_url: str, api_key: str) -> dict[str, Any]:
    payload = ensure_success(request_json(f"{base_url}/api/v1/chats", api_key, max_retries=1))
    data = payload.get("data")
    if isinstance(data, dict):
        count = len(data.get("chats", []))
    elif isinstance(data, list):
        count = len(data)
    else:
        count = None
    return {"ok": True, "assistant_count": count}


def run_test(base_url: str, api_key: str) -> dict[str, Any]:
    """Return a minimal pass/fail result."""
    try:
        ds = _probe_datasets(base_url, api_key)
        return {
            "checked_at": current_timestamp(),
            "status": "ok",
            "server": base_url,
            "dataset_count": ds["dataset_count"],
        }
    except ScriptError as exc:
        return {
            "checked_at": current_timestamp(),
            "status": "error",
            "message": str(exc),
        }


def _probe_result(base_url: str, api_key: str, probe_fn: Any) -> dict[str, Any]:
    try:
        return {**probe_fn(base_url, api_key), "status": "ok"}
    except ApiError as exc:
        return {"status": "error", "message": str(exc),
                "http_status": exc.http_status, "api_code": exc.api_code}
    except ScriptError as exc:
        return {"status": "error", "message": str(exc)}


def run_diagnose(base_url: str, api_key: str) -> dict[str, Any]:
    """Return a detailed diagnostic payload."""
    env_url = os.environ.get(RAGFLOW_API_URL_ENV, "")
    env_key = os.environ.get(RAGFLOW_API_KEY_ENV, "")

    datasets_result = _probe_result(base_url, api_key, _probe_datasets)
    chats_result = _probe_result(base_url, api_key, _probe_chats)
    overall_ok = datasets_result["status"] == "ok" and chats_result["status"] == "ok"

    return {
        "checked_at": current_timestamp(),
        "env": {
            RAGFLOW_API_URL_ENV: env_url or "<not set>",
            RAGFLOW_API_KEY_ENV: "set" if env_key else "<not set>",
        },
        "status": "ok" if overall_ok else "error",
        "endpoints": {
            "datasets": datasets_result,
            "chats": chats_result,
        },
    }


def _format_test(payload: dict[str, Any]) -> str:
    if payload["status"] == "ok":
        lines = [
            f"Status:  OK",
            f"Server:  {payload['server']}",
        ]
        if payload.get("dataset_count") is not None:
            lines.append(f"Datasets: {payload['dataset_count']}")
        return "\n".join(lines)
    return f"Status:  ERROR\nMessage: {payload.get('message', 'unknown')}"


def _format_endpoint(name: str, result: dict[str, Any]) -> list[str]:
    lines = [f"  [{name}]"]
    if result["status"] == "ok":
        lines.append(f"    Status: OK")
        for k, v in result.items():
            if k not in ("status", "ok") and v is not None:
                lines.append(f"    {k}: {v}")
    else:
        lines.append(f"    Status:  ERROR")
        lines.append(f"    Message: {result.get('message', 'unknown')}")
        if result.get("http_status") is not None:
            lines.append(f"    HTTP:    {result['http_status']}")
        if result.get("api_code") is not None:
            lines.append(f"    Code:    {result['api_code']}")
    return lines


def _format_diagnose(payload: dict[str, Any]) -> str:
    lines = [
        f"Checked at: {payload['checked_at']}",
        f"Status:     {payload['status'].upper()}",
        "",
        "Environment variables:",
    ]
    for k, v in payload["env"].items():
        lines.append(f"  {k}: {v}")

    lines += ["", "Endpoints:"]
    for name, result in payload.get("endpoints", {}).items():
        lines.extend(_format_endpoint(name, result))

    if payload["status"] != "ok":
        lines += [
            "",
            "Troubleshooting hints:",
            "  - Verify RAGFLOW_API_URL points to a running RAGFlow server.",
            "  - Verify RAGFLOW_API_KEY is a valid key from the RAGFlow Web UI.",
            "  - If HTTP 401, regenerate the API key in Settings -> API Keys.",
            "  - If connection refused, check that the server is up and the port is correct.",
        ]

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)

    try:
        base_url, api_key = resolve_runtime_config(args)
    except ScriptError as exc:
        if args.json_output:
            print(format_json({"checked_at": current_timestamp(), "error": str(exc)}))
        else:
            print(f"Error: {exc}")
        return 1

    if args.test:
        payload = run_test(base_url, api_key)
        print(format_json(payload) if args.json_output else _format_test(payload))
        return 0 if payload["status"] == "ok" else 1

    # --diagnose
    payload = run_diagnose(base_url, api_key)
    print(format_json(payload) if args.json_output else _format_diagnose(payload))
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
