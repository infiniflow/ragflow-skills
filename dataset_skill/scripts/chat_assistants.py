#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Manage RAGFlow chat assistants (chats).

Usage:
  python3 scripts/chat_assistants.py list --json
  python3 scripts/chat_assistants.py info ASSISTANT_ID --json
  python3 scripts/chat_assistants.py create "Assistant Name" --dataset-ids ID1,ID2 --json
  python3 scripts/chat_assistants.py delete --ids ID1,ID2 --json
"""

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
        description="Manage RAGFlow chat assistants.",
        parents=[global_parser],
    )
    subparsers = parser.add_subparsers(dest="command")

    list_p = subparsers.add_parser("list", help="List all chat assistants", parents=[global_parser])
    list_p.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    list_p.add_argument("--page-size", type=int, default=30, dest="page_size", help="Page size (default: 30)")

    info_p = subparsers.add_parser("info", help="Show one chat assistant", parents=[global_parser])
    info_p.add_argument("assistant_id", help="Assistant ID")

    create_p = subparsers.add_parser("create", help="Create a chat assistant", parents=[global_parser])
    create_p.add_argument("name", help="Assistant name")
    create_p.add_argument(
        "--dataset-ids",
        dest="dataset_ids",
        required=True,
        help="Comma-separated dataset IDs to attach",
    )
    create_p.add_argument("--description", default="", help="Assistant description")
    create_p.add_argument("--prompt", help="System prompt override")
    create_p.add_argument("--llm-id", dest="llm_id", help="LLM model ID")

    delete_p = subparsers.add_parser("delete", help="Delete chat assistants", parents=[global_parser])
    delete_p.add_argument(
        "--ids",
        required=True,
        help="Comma-separated assistant IDs to delete",
    )

    args = parser.parse_args(argv)
    if not args.command:
        args.command = "list"
    return args


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


def _normalize_assistant(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "dataset_ids": item.get("dataset_ids") or item.get("kb_ids") or [],
        "llm_id": item.get("llm_id") or item.get("llm", {}).get("model_name") if isinstance(item.get("llm"), dict) else item.get("llm_id"),
        "created_at": item.get("create_date") or item.get("created_at"),
    }


def list_assistants(*, base_url: str, api_key: str, page: int = 1, page_size: int = 30) -> dict[str, Any]:
    import urllib.parse
    query = urllib.parse.urlencode({"page": page, "page_size": page_size})
    payload = ensure_success(request_json(f"{base_url}/api/v1/chats?{query}", api_key))
    data = payload.get("data")
    if isinstance(data, dict):
        raw = data.get("chats", [])
        total = data.get("total", len(raw))
    elif isinstance(data, list):
        raw = data
        total = len(raw)
    else:
        raise DataError("Chat assistant list response missing data array.")
    assistants = [_normalize_assistant(item) for item in raw]
    return {
        "checked_at": current_timestamp(),
        "page": page,
        "page_size": page_size,
        "count": len(assistants),
        "total": total,
        "assistants": assistants,
    }


def assistant_info(assistant_id: str, *, base_url: str, api_key: str) -> dict[str, Any]:
    all_payload = list_assistants(base_url=base_url, api_key=api_key)
    for asst in all_payload["assistants"]:
        if asst.get("id") == assistant_id:
            return {"checked_at": current_timestamp(), "assistant": asst}
    raise DataError(f"Chat assistant not found: {assistant_id}")


def create_assistant(args: argparse.Namespace, *, base_url: str, api_key: str) -> dict[str, Any]:
    name = args.name.strip()
    if not name:
        raise DataError("Assistant name must not be empty.")
    dataset_ids = _parse_ids(args.dataset_ids, label="--dataset-ids")

    body: dict[str, Any] = {
        "name": name,
        "dataset_ids": dataset_ids,
    }
    if args.description:
        body["description"] = args.description
    if args.llm_id:
        body["llm_id"] = args.llm_id
    if args.prompt:
        body["prompt"] = {"system": args.prompt}

    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/chats",
            api_key,
            method="POST",
            body=json.dumps(body).encode("utf-8"),
            content_type="application/json",
        )
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataError("Create assistant response missing data object.")
    return {
        "created_at": current_timestamp(),
        "assistant": _normalize_assistant(data),
    }


def delete_assistants(raw_ids: str, *, base_url: str, api_key: str) -> dict[str, Any]:
    assistant_ids = _parse_ids(raw_ids, label="--ids")
    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/chats",
            api_key,
            method="DELETE",
            body=json.dumps({"ids": assistant_ids}).encode("utf-8"),
            content_type="application/json",
        )
    )
    return {
        "deleted_at": current_timestamp(),
        "assistant_ids": assistant_ids,
        "message": payload.get("message", ""),
    }


def _format_list(payload: dict[str, Any]) -> str:
    total = payload.get("total", payload["count"])
    lines = [
        f"Checked at: {payload['checked_at']}",
        f"Assistants: {payload['count']} / total={total}  (page {payload.get('page',1)}, size {payload.get('page_size',30)})",
    ]
    for asst in payload["assistants"]:
        dataset_ids = asst.get("dataset_ids") or []
        lines.extend([
            "",
            f"- {asst.get('name') or 'unknown'}",
            f"  id: {asst.get('id') or 'unknown'}",
            f"  llm_id: {asst.get('llm_id') or 'unknown'}",
            f"  datasets: {', '.join(dataset_ids) or 'none'}",
            f"  created_at: {asst.get('created_at') or 'unknown'}",
        ])
    return "\n".join(lines)


def _format_info(payload: dict[str, Any]) -> str:
    asst = payload["assistant"]
    dataset_ids = asst.get("dataset_ids") or []
    return "\n".join([
        f"Checked at: {payload['checked_at']}",
        f"Name: {asst.get('name') or 'unknown'}",
        f"ID: {asst.get('id') or 'unknown'}",
        f"Description: {asst.get('description') or 'none'}",
        f"LLM: {asst.get('llm_id') or 'unknown'}",
        f"Datasets: {', '.join(dataset_ids) or 'none'}",
        f"Created at: {asst.get('created_at') or 'unknown'}",
    ])


def _format_create(payload: dict[str, Any]) -> str:
    asst = payload["assistant"]
    dataset_ids = asst.get("dataset_ids") or []
    return "\n".join([
        f"Created at: {payload['created_at']}",
        f"Name: {asst.get('name') or 'unknown'}",
        f"ID: {asst.get('id') or 'unknown'}",
        f"LLM: {asst.get('llm_id') or 'unknown'}",
        f"Datasets: {', '.join(dataset_ids)}",
    ])


def _format_delete(payload: dict[str, Any]) -> str:
    lines = [
        f"Deleted at: {payload['deleted_at']}",
        f"Assistants: {', '.join(payload['assistant_ids'])}",
    ]
    msg = payload.get("message")
    if isinstance(msg, str) and msg.strip():
        lines.append(f"Message: {msg.strip()}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)

    try:
        base_url, api_key = resolve_runtime_config(args)

        if args.command == "list":
            payload = list_assistants(base_url=base_url, api_key=api_key,
                                      page=getattr(args, "page", 1),
                                      page_size=getattr(args, "page_size", 30))
            print(format_json(payload) if args.json_output else _format_list(payload))
            return 0

        if args.command == "info":
            payload = assistant_info(args.assistant_id, base_url=base_url, api_key=api_key)
            print(format_json(payload) if args.json_output else _format_info(payload))
            return 0

        if args.command == "create":
            payload = create_assistant(args, base_url=base_url, api_key=api_key)
            print(format_json(payload) if args.json_output else _format_create(payload))
            return 0

        if args.command == "delete":
            payload = delete_assistants(args.ids, base_url=base_url, api_key=api_key)
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
