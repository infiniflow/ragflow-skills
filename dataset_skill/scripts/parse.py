#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json

from common import (
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


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start parsing uploaded RAGFlow documents and return immediately.")
    parser.add_argument("dataset_id", help="Dataset ID")
    parser.add_argument("document_ids", nargs="+", help="Document IDs to parse")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")
    add_runtime_config_arguments(parser)
    return parser.parse_args(argv)


def start_parse(dataset_id: str, document_ids: list[str], *, base_url: str, api_key: str) -> dict[str, object]:
    url = f"{base_url}/api/v1/datasets/{dataset_id}/chunks"
    body = json.dumps({"document_ids": document_ids}).encode("utf-8")
    response = ensure_success(
        request_json(
            url,
            api_key,
            method="POST",
            body=body,
            content_type="application/json",
        )
    )
    return {
        "dataset_id": dataset_id,
        "document_ids": document_ids,
        "parse_requested_at": current_timestamp(),
        "api_response": response,
    }


def _format_payload(payload: dict[str, object]) -> str:
    lines = [
        f"Dataset: {payload['dataset_id']}",
        f"Parse requested at: {payload['parse_requested_at']}",
    ]
    api_response = payload.get("api_response")
    if isinstance(api_response, dict):
        message = api_response.get("message")
        if isinstance(message, str) and message.strip():
            lines.append(f"API message: {message.strip()}")
    return "\n".join(lines)


def _build_error_payload(
    args: argparse.Namespace,
    exc: ScriptError,
    *,
    parse_request: dict[str, object] | None,
) -> dict[str, object]:
    payload: dict[str, object] = (
        dict(parse_request)
        if parse_request is not None
        else {
            "dataset_id": args.dataset_id,
            "document_ids": args.document_ids,
            "parse_requested_at": current_timestamp(),
        }
    )
    payload["error"] = str(exc)
    error_detail = serialize_script_error(exc)
    if error_detail.get("type") == "ApiError":
        payload["api_error"] = error_detail
    else:
        payload["error_detail"] = error_detail
    return payload


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)
    parse_request: dict[str, object] | None = None

    try:
        base_url, api_key = resolve_runtime_config(args)
        parse_request = start_parse(args.dataset_id, args.document_ids, base_url=base_url, api_key=api_key)
        print(format_json(parse_request) if args.json_output else _format_payload(parse_request))
        return 0
    except ScriptError as exc:
        if args.json_output:
            print(format_json(_build_error_payload(args, exc, parse_request=parse_request)))
        else:
            print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
