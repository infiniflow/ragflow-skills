#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from typing import Any

from common import (
    DataError,
    ScriptError,
    add_runtime_config_arguments,
    configure_stdio_utf8,
    current_timestamp,
    ensure_success,
    format_json,
    request_json,
    resolve_runtime_config,
)


def _build_global_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")
    add_runtime_config_arguments(parser)
    return parser


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    global_parser = _build_global_parser()
    parser = argparse.ArgumentParser(
        description="List, inspect, or create RAGFlow datasets.",
        parents=[global_parser],
    )
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="List datasets", parents=[global_parser])
    list_parser.set_defaults(command="list")

    info_parser = subparsers.add_parser("info", help="Show one dataset", parents=[global_parser])
    info_parser.add_argument("dataset_id", help="Dataset ID")
    info_parser.set_defaults(command="info")

    create_parser = subparsers.add_parser("create", help="Create a dataset", parents=[global_parser])
    create_parser.add_argument("name", help="Dataset name")
    create_parser.add_argument("--avatar", help="Dataset avatar")
    create_parser.add_argument("--description", default="", help="Dataset description")
    create_parser.add_argument("--embedding-model", dest="embedding_model", help="Embedding model ID")
    create_parser.add_argument("--permission", help="Permission value, for example me or team")
    create_parser.add_argument("--chunk-method", dest="chunk_method", help="Chunking method / parser ID")
    create_parser.add_argument("--language", help="Dataset language")
    create_parser.set_defaults(command="create")

    delete_parser = subparsers.add_parser("delete", help="Delete datasets", parents=[global_parser])
    delete_parser.add_argument(
        "--ids",
        required=True,
        help="Comma-separated dataset IDs, for example: id_1,id_2",
    )
    delete_parser.set_defaults(command="delete")

    args = parser.parse_args(argv)
    if not args.command:
        args.command = "list"
    return args


def _normalize_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": dataset.get("id"),
        "name": dataset.get("name"),
        "avatar": dataset.get("avatar"),
        "description": dataset.get("description"),
        "chunk_count": dataset.get("chunk_count"),
        "created_at": dataset.get("created_at"),
        "permission": dataset.get("permission"),
        "embedding_model": dataset.get("embedding_model") or dataset.get("embd_id"),
        "chunk_method": dataset.get("chunk_method") or dataset.get("parser_id"),
        "language": dataset.get("language"),
    }


def list_datasets(*, base_url: str, api_key: str) -> dict[str, Any]:
    payload = ensure_success(request_json(f"{base_url}/api/v1/datasets", api_key))
    datasets = payload.get("data")
    if not isinstance(datasets, list):
        raise DataError("Dataset list response missing data array.")
    normalized = [_normalize_dataset(dataset) for dataset in datasets]
    return {
        "checked_at": current_timestamp(),
        "count": len(normalized),
        "datasets": normalized,
    }


def dataset_info(dataset_id: str, *, base_url: str, api_key: str) -> dict[str, Any]:
    payload = list_datasets(base_url=base_url, api_key=api_key)
    for dataset in payload["datasets"]:
        if dataset.get("id") == dataset_id:
            return {
                "checked_at": current_timestamp(),
                "dataset": dataset,
            }
    raise DataError(f"Dataset not found: {dataset_id}")


def _build_create_payload(args: argparse.Namespace) -> dict[str, Any]:
    name = args.name.strip()
    if not name:
        raise DataError("Dataset name must not be empty.")

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


def _parse_ids(raw_value: str, *, label: str) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()

    for item in raw_value.split(","):
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ids.append(value)

    if not ids:
        raise DataError(f"{label} must include at least one ID.")
    return ids


def create_dataset(args: argparse.Namespace, *, base_url: str, api_key: str) -> dict[str, Any]:
    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/datasets",
            api_key,
            method="POST",
            body=json.dumps(_build_create_payload(args)).encode("utf-8"),
            content_type="application/json",
        )
    )
    dataset = payload.get("data")
    if not isinstance(dataset, dict):
        raise DataError("Dataset create response missing data object.")
    return {
        "created_at": current_timestamp(),
        "dataset": _normalize_dataset(dataset),
    }


def delete_datasets(raw_ids: str, *, base_url: str, api_key: str) -> dict[str, Any]:
    dataset_ids = _parse_ids(raw_ids, label="--ids")
    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/datasets",
            api_key,
            method="DELETE",
            body=json.dumps({"ids": dataset_ids}).encode("utf-8"),
            content_type="application/json",
        )
    )
    return {
        "deleted_at": current_timestamp(),
        "dataset_ids": dataset_ids,
        "message": payload.get("message", ""),
        "data": payload.get("data"),
    }


def _format_list(payload: dict[str, Any]) -> str:
    lines = [
        f"Checked at: {payload['checked_at']}",
        f"Datasets: {payload['count']}",
    ]
    for dataset in payload["datasets"]:
        lines.extend(
            [
                "",
                f"- {dataset.get('name') or 'unknown'}",
                f"  id: {dataset.get('id') or 'unknown'}",
                f"  chunks: {dataset.get('chunk_count') if dataset.get('chunk_count') is not None else 'unknown'}",
                f"  created_at: {dataset.get('created_at') or 'unknown'}",
            ]
        )
    return "\n".join(lines)


def _format_info(payload: dict[str, Any]) -> str:
    dataset = payload["dataset"]
    return "\n".join(
        [
            f"Checked at: {payload['checked_at']}",
            f"Name: {dataset.get('name') or 'unknown'}",
            f"ID: {dataset.get('id') or 'unknown'}",
            f"Description: {dataset.get('description') or 'unknown'}",
            f"Chunk count: {dataset.get('chunk_count') if dataset.get('chunk_count') is not None else 'unknown'}",
            f"Created at: {dataset.get('created_at') or 'unknown'}",
            f"Permission: {dataset.get('permission') or 'unknown'}",
        ]
    )


def _format_create(payload: dict[str, Any]) -> str:
    dataset = payload["dataset"]
    lines = [
        f"Created at: {payload['created_at']}",
        f"Name: {dataset.get('name') or 'unknown'}",
        f"ID: {dataset.get('id') or 'unknown'}",
        f"Description: {dataset.get('description') or 'unknown'}",
        f"Chunk count: {dataset.get('chunk_count') if dataset.get('chunk_count') is not None else 'unknown'}",
        f"Created at (server): {dataset.get('created_at') or 'unknown'}",
        f"Permission: {dataset.get('permission') or 'unknown'}",
    ]
    for label, key in (
        ("Avatar", "avatar"),
        ("Embedding model", "embedding_model"),
        ("Chunk method", "chunk_method"),
        ("Language", "language"),
    ):
        value = dataset.get(key)
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def _format_delete(payload: dict[str, Any]) -> str:
    lines = [
        f"Deleted at: {payload['deleted_at']}",
        f"Datasets: {', '.join(payload['dataset_ids'])}",
    ]
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        lines.append(f"Message: {message.strip()}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)

    try:
        base_url, api_key = resolve_runtime_config(args)

        if args.command == "list":
            payload = list_datasets(base_url=base_url, api_key=api_key)
            print(format_json(payload) if args.json_output else _format_list(payload))
            return 0

        if args.command == "info":
            payload = dataset_info(args.dataset_id, base_url=base_url, api_key=api_key)
            print(format_json(payload) if args.json_output else _format_info(payload))
            return 0

        if args.command == "create":
            payload = create_dataset(args, base_url=base_url, api_key=api_key)
            print(format_json(payload) if args.json_output else _format_create(payload))
            return 0

        if args.command == "delete":
            payload = delete_datasets(args.ids, base_url=base_url, api_key=api_key)
            print(format_json(payload) if args.json_output else _format_delete(payload))
            return 0

        raise DataError(f"Unsupported command: {args.command}")
    except ScriptError as exc:
        if args.json_output:
            print(format_json({"checked_at": current_timestamp(), "error": str(exc)}))
        else:
            print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
