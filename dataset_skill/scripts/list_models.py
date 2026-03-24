#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from common import (
    ApiError,
    ConfigError,
    DataError,
    ScriptError,
    add_runtime_config_arguments,
    configure_stdio_utf8,
    current_timestamp,
    decode_json_body,
    decode_json_response,
    decode_response_text,
    ensure_success,
    extract_error_message,
    format_json,
    resolve_runtime_config,
)

HTTP_TIMEOUT = 30
DEFAULT_API_PATH = "/v1/llm/my_llms"
DEFAULT_GROUP_BY = "type"
AVAILABLE_STATUSES = {"1", 1, True}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List available LLMs from the RAGFlow web API.")
    parser.add_argument(
        "--include-details",
        action="store_true",
        help="Request the detailed response shape returned by include_details=true.",
    )
    parser.add_argument(
        "--group-by",
        choices=("type", "factory"),
        default=DEFAULT_GROUP_BY,
        help=f"Group models by type or factory (default: {DEFAULT_GROUP_BY})",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_unavailable",
        help="Include unavailable models. By default only available models are listed.",
    )
    parser.add_argument(
        "--api-path",
        default=DEFAULT_API_PATH,
        help=f"Endpoint path (default: {DEFAULT_API_PATH})",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")
    add_runtime_config_arguments(parser)
    return parser.parse_args(argv)


def _build_headers(api_key: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _request_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request_obj = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(request_obj, timeout=HTTP_TIMEOUT) as response:
            return decode_json_response(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read()
        response_payload = decode_json_body(body)
        response_text = decode_response_text(body)
        message = extract_error_message(body)
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


def _normalize_llm(item: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "id": item.get("id"),
        "type": item.get("type"),
        "name": item.get("name"),
        "used_token": item.get("used_token"),
        "status": item.get("status"),
        "factory": item.get("factory"),
    }

    if "api_base" in item:
        normalized["api_base"] = item.get("api_base")
    if "max_tokens" in item:
        normalized["max_tokens"] = item.get("max_tokens")
    return normalized


def _normalize_data(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        raise DataError("Response missing data object.")

    factories: list[dict[str, Any]] = []
    for factory_name, factory_payload in data.items():
        if not isinstance(factory_name, str) or not factory_name.strip():
            raise DataError("Response contains an invalid llm_factory key.")
        if not isinstance(factory_payload, dict):
            raise DataError(f"Factory {factory_name!r} payload is malformed.")

        llms = factory_payload.get("llm")
        if not isinstance(llms, list):
            raise DataError(f"Factory {factory_name!r} is missing llm list.")

        factories.append(
            {
                "name": factory_name,
                "tags": factory_payload.get("tags"),
                "llms": [
                    _normalize_llm({**item, "factory": factory_name})
                    for item in llms
                    if isinstance(item, dict)
                ],
            }
        )

    factories.sort(key=lambda item: item["name"])
    return factories


def _is_available(status: Any) -> bool:
    return status in AVAILABLE_STATUSES or str(status).strip() in {"1", "true", "True"}


def _group_models(
    factories: list[dict[str, Any]],
    *,
    group_by: str,
    include_details: bool,
    include_unavailable: bool,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for factory in factories:
        factory_name = factory["name"]
        factory_tags = factory.get("tags")
        for llm in factory["llms"]:
            if not include_unavailable and not _is_available(llm.get("status")):
                continue

            key = factory_name if group_by == "factory" else str(llm.get("type") or "unknown")
            if key not in grouped:
                grouped[key] = {
                    "name": key,
                    "factory": factory_name if group_by == "factory" else None,
                    "tags": factory_tags if group_by == "factory" else None,
                    "models": [],
                }

            model = {
                "id": llm.get("id"),
                "name": llm.get("name"),
                "type": llm.get("type"),
                "factory": llm.get("factory"),
                "used_token": llm.get("used_token"),
                "status": llm.get("status"),
            }
            if include_details:
                if "api_base" in llm:
                    model["api_base"] = llm.get("api_base")
                if "max_tokens" in llm:
                    model["max_tokens"] = llm.get("max_tokens")

            grouped[key]["models"].append(model)

    groups = list(grouped.values())
    groups.sort(key=lambda item: item["name"])
    for group in groups:
        group["models"].sort(key=lambda item: ((item.get("name") or ""), (item.get("id") or "")))
    return groups


def list_models(
    *,
    base_url: str,
    api_key: str,
    include_details: bool,
    api_path: str,
    group_by: str,
    include_unavailable: bool,
) -> dict[str, Any]:
    path = api_path.strip() or DEFAULT_API_PATH
    if not path.startswith("/"):
        raise ConfigError("--api-path must start with '/'.")

    query = urllib.parse.urlencode({"include_details": str(include_details).lower()})
    payload = ensure_success(
        _request_json(
            f"{base_url}{path}?{query}",
            _build_headers(api_key),
        )
    )

    factories = _normalize_data(payload.get("data"))
    groups = _group_models(
        factories,
        group_by=group_by,
        include_details=include_details,
        include_unavailable=include_unavailable,
    )
    return {
        "checked_at": current_timestamp(),
        "include_details": include_details,
        "group_by": group_by,
        "available_only": not include_unavailable,
        "factory_count": len(factories),
        "llm_count": sum(len(group["models"]) for group in groups),
        "groups": groups,
    }


def _format_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Checked at: {payload['checked_at']}",
        f"Factories: {payload['factory_count']}",
        f"Available models: {payload['llm_count']}",
        f"Group by: {payload['group_by']}",
        f"Available only: {str(payload['available_only']).lower()}",
        f"Include details: {str(payload['include_details']).lower()}",
    ]

    for group in payload["groups"]:
        lines.extend(
            [
                "",
                f"[{group['name']}]",
                f"models: {len(group['models'])}",
            ]
        )
        if payload["group_by"] == "factory":
            lines.append(f"tags: {group.get('tags') if group.get('tags') is not None else 'none'}")
        for llm in group["models"]:
            lines.append(
                f"- {llm.get('name') or 'unknown'} "
                f"(id: {llm.get('id') or 'unknown'}, "
                f"type: {llm.get('type') or 'unknown'}, "
                f"factory: {llm.get('factory') or 'unknown'})"
            )
            if payload["include_details"]:
                lines.append(
                    f"  used_token: {llm.get('used_token') if llm.get('used_token') is not None else 'unknown'}, "
                    f"status: {llm.get('status') or 'unknown'}, "
                    f"api_base: {llm.get('api_base') or ''}, "
                    f"max_tokens: {llm.get('max_tokens') if llm.get('max_tokens') is not None else 'unknown'}"
                )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)

    try:
        base_url, api_key = resolve_runtime_config(args)
        payload = list_models(
            base_url=base_url,
            api_key=api_key,
            include_details=args.include_details,
            api_path=args.api_path,
            group_by=args.group_by,
            include_unavailable=args.include_unavailable,
        )
        print(format_json(payload) if args.json_output else _format_text(payload))
        return 0
    except ScriptError as exc:
        if args.json_output:
            print(format_json({"checked_at": current_timestamp(), "error": str(exc)}))
        else:
            print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
