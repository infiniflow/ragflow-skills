#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
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
    serialize_script_error,
)
from parse_status import collect_status_payload, format_status_text


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stop parsing RAGFlow documents and return a current parser status snapshot.",
    )
    parser.add_argument("dataset_id", help="Dataset ID")
    parser.add_argument("document_ids", nargs="+", help="One or more document IDs to stop parsing")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")
    add_runtime_config_arguments(parser)
    return parser.parse_args(argv)


def stop_parse(dataset_id: str, document_ids: list[str], *, base_url: str, api_key: str) -> dict[str, Any]:
    url = f"{base_url}/api/v1/datasets/{dataset_id}/chunks"
    response = ensure_success(
        request_json(
            url,
            api_key,
            method="DELETE",
            body=json.dumps({"document_ids": document_ids}).encode("utf-8"),
            content_type="application/json",
        )
    )

    payload: dict[str, Any] = {
        "dataset_id": dataset_id,
        "document_ids": document_ids,
        "stop_requested_at": current_timestamp(),
        "api_response": response,
    }
    message = response.get("message")
    if isinstance(message, str) and message.strip():
        payload["message"] = message.strip()
    data = response.get("data")
    if data is not None:
        payload["data"] = data
    return payload


def _format_payload(payload: dict[str, Any]) -> str:
    lines = [
        f"Dataset: {payload['dataset_id']}",
        f"Stop requested at: {payload['stop_requested_at']}",
    ]
    message = payload.get("message")
    if isinstance(message, str) and message:
        lines.append(f"Message: {message}")
    lines.extend(
        [
            "",
            format_status_text(payload["status"]),
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)
    stop_request: dict[str, Any] | None = None
    phase = "validate"

    try:
        base_url, api_key = resolve_runtime_config(args)
        phase = "stop_parse"
        stop_request = stop_parse(args.dataset_id, args.document_ids, base_url=base_url, api_key=api_key)
        phase = "status"
        status_payload = collect_status_payload(
            args.dataset_id,
            args.document_ids,
            base_url=base_url,
            api_key=api_key,
        )
        payload = {**stop_request, "status": status_payload}
        print(format_json(payload) if args.json_output else _format_payload(payload))
        return 0
    except ScriptError as exc:
        if args.json_output:
            payload: dict[str, Any] = (
                dict(stop_request)
                if stop_request is not None
                else {
                    "dataset_id": args.dataset_id,
                    "document_ids": args.document_ids,
                    "stop_requested_at": current_timestamp(),
                }
            )
            payload["error"] = str(exc)
            error_detail = serialize_script_error(exc)
            if phase == "stop_parse" and isinstance(exc, ApiError):
                payload["api_error"] = error_detail
            elif phase == "status" or stop_request is not None:
                payload["status_error"] = error_detail
            else:
                payload["error_detail"] = error_detail
            print(
                format_json(payload)
            )
        else:
            print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
