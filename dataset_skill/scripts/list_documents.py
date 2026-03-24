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
from typing import Any

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 10
DEFAULT_ORDERBY = "create_time"
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
    parser = argparse.ArgumentParser(description="List documents in a dataset through the RAGFlow HTTP API.")
    parser.add_argument("dataset_id", help="Dataset ID")
    parser.add_argument("--page", type=int, default=DEFAULT_PAGE, help=f"Page number (default: {DEFAULT_PAGE})")
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Page size (default: {DEFAULT_PAGE_SIZE})",
    )
    parser.add_argument("--orderby", default=DEFAULT_ORDERBY, help=f"Sort field (default: {DEFAULT_ORDERBY})")
    parser.add_argument("--asc", action="store_true", help="Sort ascending. Descending is the default.")
    parser.add_argument("--keywords", help="Filter by keywords")
    parser.add_argument("--id", dest="document_id", help="Filter by document ID")
    parser.add_argument("--name", help="Filter by document name")
    parser.add_argument("--suffix", help="Filter by file suffix, for example pdf")
    parser.add_argument("--run", help="Filter by parse run status, for example DONE")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print raw JSON response")
    add_runtime_config_arguments(parser)
    return parser.parse_args(argv)


def _validate_positive(name: str, value: int) -> None:
    if value <= 0:
        raise DataError(f"{name} must be greater than 0.")


def _build_documents_url(base_url: str, args: argparse.Namespace) -> str:
    dataset_id = args.dataset_id.strip()
    if not dataset_id:
        raise ConfigError("dataset_id must not be empty.")

    query: dict[str, Any] = {
        "page": args.page,
        "page_size": args.page_size,
        "orderby": args.orderby,
        "desc": str(not args.asc).lower(),
    }
    if args.keywords:
        query["keywords"] = args.keywords
    if args.document_id:
        query["id"] = args.document_id
    if args.name:
        query["name"] = args.name
    if args.suffix:
        query["suffix"] = args.suffix
    if args.run:
        query["run"] = args.run

    encoded_dataset_id = urllib.parse.quote(dataset_id, safe="")
    encoded_query = urllib.parse.urlencode(query)
    return f"{base_url}/api/v1/datasets/{encoded_dataset_id}/documents?{encoded_query}"
def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = ensure_success(payload)
    code = payload.get("code")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataError("Response missing data object.")

    docs = data.get("docs")
    total = data.get("total")
    if not isinstance(docs, list):
        raise DataError("Response missing data.docs.")
    if not isinstance(total, int):
        raise DataError("Response missing data.total.")

    return {
        "code": code,
        "message": payload.get("message", ""),
        "data": data,
    }


def _format_document_line(document: dict[str, Any]) -> str:
    document_id = str(document.get("id", "")).strip() or "<missing-id>"
    name = str(document.get("name", "")).strip() or "<missing-name>"
    lines = [f"{name} ({document_id})"]

    details = []
    for key, label in (
        ("run", "run"),
        ("type", "type"),
        ("chunk_count", "chunks"),
        ("token_count", "tokens"),
        ("size", "size"),
    ):
        value = document.get(key)
        if value not in (None, ""):
            details.append(f"{label}={value}")
    if details:
        lines.append("  " + ", ".join(details))

    return "\n".join(lines)


def _format_text(payload: dict[str, Any], dataset_id: str) -> str:
    data = payload["data"]
    docs = data["docs"]
    total = data["total"]

    lines = [f"Dataset: {dataset_id}", f"Documents: {len(docs)} / total={total}"]
    if not docs:
        return "\n".join(lines)

    for document in docs:
        lines.append("")
        lines.append(_format_document_line(document))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)

    try:
        _validate_positive("--page", args.page)
        _validate_positive("--page-size", args.page_size)
        base_url, api_key = resolve_runtime_config(args)
        payload = request_json(_build_documents_url(base_url, args), api_key)
        normalized = _normalize_payload(payload)

        if args.json_output:
            print(json.dumps(normalized, ensure_ascii=False, indent=2))
        else:
            print(_format_text(normalized, args.dataset_id.strip()))
        return 0
    except ScriptError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
