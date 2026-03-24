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
    parser = argparse.ArgumentParser(description="Create a dataset through the RAGFlow HTTP API.")
    parser.add_argument("name", help="Dataset name")
    parser.add_argument("--avatar", help="Dataset avatar")
    parser.add_argument("--description", help="Dataset description")
    parser.add_argument("--embedding-model", dest="embedding_model", help="Embedding model ID")
    parser.add_argument("--permission", help="Permission value, for example me or team")
    parser.add_argument("--chunk-method", dest="chunk_method", help="Chunking method / parser ID")
    parser.add_argument("--language", help="Dataset language")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print raw JSON response")
    add_runtime_config_arguments(parser)
    return parser.parse_args(argv)


def _build_payload(args: argparse.Namespace) -> dict[str, Any]:
    name = args.name.strip()
    if not name:
        raise ConfigError("Dataset name must not be empty.")

    payload: dict[str, Any] = {"name": name}
    if args.avatar:
        payload["avatar"] = args.avatar
    if args.description:
        payload["description"] = args.description
    if args.embedding_model:
        payload["embedding_model"] = args.embedding_model
    if args.permission:
        payload["permission"] = args.permission
    if args.chunk_method:
        payload["chunk_method"] = args.chunk_method
    if args.language:
        payload["language"] = args.language
    return payload
def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = ensure_success(payload)
    code = payload.get("code")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataError("Response missing data object.")

    return {
        "code": code,
        "message": payload.get("message", ""),
        "data": data,
    }


def _format_text(payload: dict[str, Any]) -> str:
    data = payload["data"]
    lines = ["Dataset created"]

    dataset_id = data.get("id")
    name = data.get("name")
    if name:
        lines.append(f"name: {name}")
    if dataset_id:
        lines.append(f"id: {dataset_id}")

    for key in ("embedding_model", "permission", "chunk_method", "language", "avatar", "description"):
        value = data.get(key)
        if value not in (None, ""):
            lines.append(f"{key}: {value}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)

    try:
        base_url, api_key = resolve_runtime_config(args)
        payload = request_json(
            f"{base_url}/api/v1/datasets",
            api_key,
            method="POST",
            body=json.dumps(_build_payload(args)).encode("utf-8"),
            content_type="application/json",
        )
        normalized = _normalize_payload(payload)

        if args.json_output:
            print(json.dumps(normalized, ensure_ascii=False, indent=2))
        else:
            print(_format_text(normalized))
        return 0
    except ScriptError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
