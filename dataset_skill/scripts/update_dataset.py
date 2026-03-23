#!/usr/bin/env python3
#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import argparse
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from common import (
    ConfigError,
    DataError,
    ScriptError,
    add_runtime_config_arguments,
    configure_stdio_utf8,
    ensure_success,
    request_json,
    resolve_runtime_config,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update a dataset through the RAGFlow HTTP API.")
    parser.add_argument("dataset_id", help="Dataset ID")
    parser.add_argument("--name", help="Updated dataset name")
    parser.add_argument("--avatar", help="Updated avatar as data URL/base64")
    parser.add_argument("--description", help="Updated dataset description")
    parser.add_argument("--embedding-model", help="Updated embedding model")
    parser.add_argument("--permission", choices=("me", "team"), help="Updated dataset permission")
    parser.add_argument("--chunk-method", help="Updated chunk method")
    parser.add_argument("--pagerank", type=int, help="Updated pagerank")
    parser.add_argument(
        "--parser-config",
        help="Parser config JSON object or @path/to/file.json",
    )
    parser.add_argument(
        "--data",
        help="Raw JSON object payload or @path/to/file.json. Explicit flags override the same keys.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print raw JSON response")
    add_runtime_config_arguments(parser)
    return parser.parse_args(argv)


def _load_json_object(raw_value: str, option_name: str) -> dict[str, Any]:
    value = raw_value
    if raw_value.startswith("@"):
        path = Path(raw_value[1:]).expanduser()
        try:
            value = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"Failed to read {option_name} file {path}: {exc}") from exc

    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{option_name} must be valid JSON: {exc.msg}.") from exc

    if not isinstance(payload, dict):
        raise ConfigError(f"{option_name} must be a JSON object.")
    return payload


def _build_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if args.data:
        payload.update(_load_json_object(args.data, "--data"))

    field_values = {
        "name": args.name,
        "avatar": args.avatar,
        "description": args.description,
        "embedding_model": args.embedding_model,
        "permission": args.permission,
        "chunk_method": args.chunk_method,
        "pagerank": args.pagerank,
    }
    for key, value in field_values.items():
        if value is not None:
            payload[key] = value

    if args.parser_config is not None:
        payload["parser_config"] = _load_json_object(args.parser_config, "--parser-config")

    if not payload:
        raise ConfigError("No update fields provided. Use --data or at least one explicit update flag.")
    return payload


def _build_url(base_url: str, dataset_id: str) -> str:
    encoded_dataset_id = urllib.parse.quote(dataset_id, safe="")
    return f"{base_url}/api/v1/datasets/{encoded_dataset_id}"
def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = ensure_success(payload)

    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataError("Response missing data object.")
    return payload


def _print_summary(payload: dict[str, Any]) -> None:
    data = payload["data"]
    dataset_id = str(data.get("id", "")).strip() or "<missing-id>"
    name = str(data.get("name", "")).strip() or "<missing-name>"
    print(f"Updated dataset: {name} ({dataset_id})")

    details = []
    if data.get("description"):
        details.append(f"description={data['description']}")
    if data.get("embd_id"):
        details.append(f"embedding_model={data['embd_id']}")
    if data.get("permission"):
        details.append(f"permission={data['permission']}")
    if data.get("parser_id"):
        details.append(f"chunk_method={data['parser_id']}")
    if data.get("pagerank") is not None:
        details.append(f"pagerank={data['pagerank']}")
    if details:
        print("  " + ", ".join(details))


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    try:
        args = _parse_args(argv)
        base_url, api_key, _memory_config = resolve_runtime_config(args)
        payload = _build_payload(args)
        response = request_json(
            _build_url(base_url, args.dataset_id),
            api_key,
            method="PUT",
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )
        normalized = _normalize_payload(response)
    except ScriptError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(normalized, ensure_ascii=False, indent=2))
    else:
        _print_summary(normalized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
