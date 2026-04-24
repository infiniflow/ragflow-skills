#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Manage RAGFlow chat assistants (chats).

Usage:
  python3 scripts/chat_assistants.py list --json
  python3 scripts/chat_assistants.py info ASSISTANT_ID --json
  python3 scripts/chat_assistants.py create "Assistant Name" --dataset-ids ID1,ID2 --json
  python3 scripts/chat_assistants.py update ASSISTANT_ID --name "New Name" --json
  python3 scripts/chat_assistants.py update ASSISTANT_ID --system "You are..." --prologue "Hi!" --json
  python3 scripts/chat_assistants.py update ASSISTANT_ID --temperature 0.1 --similarity-threshold 0.3 --json
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

    info_p = subparsers.add_parser("info", help="Show full config of one chat assistant", parents=[global_parser])
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
    create_p.add_argument("--system", dest="system", help="System prompt")
    create_p.add_argument("--prologue", dest="prologue", help="Opening greeting shown to users")
    create_p.add_argument("--llm-id", dest="llm_id", help="LLM model ID")
    create_p.add_argument("--temperature", type=float, dest="temperature", help="LLM temperature (e.g. 0.1)")
    create_p.add_argument("--similarity-threshold", type=float, dest="similarity_threshold", help="Retrieval similarity threshold")
    create_p.add_argument("--top-n", type=int, dest="top_n", help="Number of chunks to retrieve")
    create_p.add_argument("--rerank-id", dest="rerank_id", help="Reranker model ID")

    update_p = subparsers.add_parser("update", help="Update a chat assistant", parents=[global_parser])
    update_p.add_argument("assistant_id", help="Assistant ID to update")
    update_p.add_argument("--name", dest="name", help="New assistant name")
    update_p.add_argument("--description", dest="description", help="New description")
    update_p.add_argument("--dataset-ids", dest="dataset_ids", help="Comma-separated dataset IDs (replaces existing)")
    update_p.add_argument("--llm-id", dest="llm_id", help="LLM model ID")
    update_p.add_argument("--temperature", type=float, dest="temperature", help="LLM temperature (e.g. 0.1)")
    update_p.add_argument("--system", dest="system", help="System prompt text")
    update_p.add_argument("--prologue", dest="prologue", help="Opening greeting shown to users")
    update_p.add_argument("--empty-response", dest="empty_response", help="Reply when no chunks retrieved")
    update_p.add_argument("--similarity-threshold", type=float, dest="similarity_threshold", help="Retrieval similarity threshold")
    update_p.add_argument("--top-n", type=int, dest="top_n", help="Number of chunks to retrieve")
    update_p.add_argument("--rerank-id", dest="rerank_id", help="Reranker model ID (empty string to disable)")

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
    llm_id = item.get("llm_id")
    if not llm_id and isinstance(item.get("llm"), dict):
        llm_id = item["llm"].get("model_name")
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "dataset_ids": item.get("dataset_ids") or item.get("kb_ids") or [],
        "llm_id": llm_id,
        "created_at": item.get("create_date") or item.get("created_at"),
    }


def _normalize_full_assistant(item: dict[str, Any]) -> dict[str, Any]:
    llm_id = item.get("llm_id")
    if not llm_id and isinstance(item.get("llm"), dict):
        llm_id = item["llm"].get("model_name")

    prompt_config = item.get("prompt_config") or {}
    llm_setting = item.get("llm_setting") or {}

    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "dataset_ids": item.get("dataset_ids") or item.get("kb_ids") or [],
        "llm_id": llm_id,
        "temperature": llm_setting.get("temperature"),
        "rerank_id": item.get("rerank_id") or "",
        "similarity_threshold": item.get("similarity_threshold"),
        "top_n": item.get("top_n"),
        "top_k": item.get("top_k"),
        "vector_similarity_weight": item.get("vector_similarity_weight"),
        "language": item.get("language"),
        "prompt_config": {
            "system": prompt_config.get("system", ""),
            "prologue": prompt_config.get("prologue", ""),
            "empty_response": prompt_config.get("empty_response", ""),
            "quote": prompt_config.get("quote", True),
            "keyword": prompt_config.get("keyword", False),
            "reasoning": prompt_config.get("reasoning", False),
            "refine_multiturn": prompt_config.get("refine_multiturn", False),
            "toc_enhance": prompt_config.get("toc_enhance", False),
        },
        "created_at": item.get("create_date") or item.get("created_at"),
        "updated_at": item.get("update_date") or item.get("updated_at"),
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
    payload = ensure_success(request_json(f"{base_url}/api/v1/chats/{assistant_id}", api_key))
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataError(f"Chat assistant not found: {assistant_id}")
    return {
        "checked_at": current_timestamp(),
        "assistant": _normalize_full_assistant(data),
    }


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
    if args.temperature is not None:
        body["llm_setting"] = {"temperature": args.temperature}
    if args.similarity_threshold is not None:
        body["similarity_threshold"] = args.similarity_threshold
    if args.top_n is not None:
        body["top_n"] = args.top_n
    if args.rerank_id:
        body["rerank_id"] = args.rerank_id

    prompt_config: dict[str, Any] = {}
    if args.system:
        prompt_config["system"] = args.system
    if args.prologue:
        prompt_config["prologue"] = args.prologue
    if prompt_config:
        body["prompt_config"] = prompt_config

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


def update_assistant(args: argparse.Namespace, *, base_url: str, api_key: str) -> dict[str, Any]:
    assistant_id = args.assistant_id

    # Fetch current config to use as base for prompt_config merging
    current_payload = ensure_success(request_json(f"{base_url}/api/v1/chats/{assistant_id}", api_key))
    current = current_payload.get("data")
    if not isinstance(current, dict):
        raise DataError(f"Chat assistant not found: {assistant_id}")

    body: dict[str, Any] = {}

    if args.name is not None:
        body["name"] = args.name.strip()
    if args.description is not None:
        body["description"] = args.description
    if args.dataset_ids is not None:
        body["dataset_ids"] = _parse_ids(args.dataset_ids, label="--dataset-ids")
    if args.llm_id is not None:
        body["llm_id"] = args.llm_id
    if args.temperature is not None:
        existing_llm_setting = dict(current.get("llm_setting") or {})
        existing_llm_setting["temperature"] = args.temperature
        body["llm_setting"] = existing_llm_setting
    if args.similarity_threshold is not None:
        body["similarity_threshold"] = args.similarity_threshold
    if args.top_n is not None:
        body["top_n"] = args.top_n
    if args.rerank_id is not None:
        body["rerank_id"] = args.rerank_id

    # Merge prompt_config fields individually so unspecified fields are preserved
    prompt_updates: dict[str, Any] = {}
    if args.system is not None:
        prompt_updates["system"] = args.system
    if args.prologue is not None:
        prompt_updates["prologue"] = args.prologue
    if args.empty_response is not None:
        prompt_updates["empty_response"] = args.empty_response
    if prompt_updates:
        existing_prompt = dict(current.get("prompt_config") or {})
        existing_prompt.update(prompt_updates)
        body["prompt_config"] = existing_prompt

    if not body:
        raise DataError("No fields to update. Provide at least one update flag.")

    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/chats/{assistant_id}",
            api_key,
            method="PUT",
            body=json.dumps(body).encode("utf-8"),
            content_type="application/json",
        )
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        # Some RAGFlow versions return data=True on success; re-fetch to confirm
        updated = ensure_success(request_json(f"{base_url}/api/v1/chats/{assistant_id}", api_key))
        data = updated.get("data") or {}

    return {
        "updated_at": current_timestamp(),
        "assistant_id": assistant_id,
        "updated_fields": list(body.keys()),
        "assistant": _normalize_full_assistant(data),
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
    pc = asst.get("prompt_config") or {}
    system_preview = (pc.get("system") or "")[:120].replace("\n", " ")
    if len(pc.get("system") or "") > 120:
        system_preview += "..."
    lines = [
        f"Checked at: {payload['checked_at']}",
        f"Name:                  {asst.get('name') or 'unknown'}",
        f"ID:                    {asst.get('id') or 'unknown'}",
        f"Description:           {asst.get('description') or 'none'}",
        f"LLM:                   {asst.get('llm_id') or 'unknown'}",
        f"Temperature:           {asst.get('temperature') if asst.get('temperature') is not None else 'unknown'}",
        f"Datasets:              {', '.join(dataset_ids) or 'none'}",
        f"Rerank model:          {asst.get('rerank_id') or 'none'}",
        f"Similarity threshold:  {asst.get('similarity_threshold') if asst.get('similarity_threshold') is not None else 'unknown'}",
        f"Top N:                 {asst.get('top_n') if asst.get('top_n') is not None else 'unknown'}",
        f"Vector sim weight:     {asst.get('vector_similarity_weight') if asst.get('vector_similarity_weight') is not None else 'unknown'}",
        f"Language:              {asst.get('language') or 'unknown'}",
        f"Prologue:              {pc.get('prologue') or 'none'}",
        f"Empty response:        {pc.get('empty_response') or 'none'}",
        f"Quote references:      {pc.get('quote')}",
        f"Keyword search:        {pc.get('keyword')}",
        f"Reasoning:             {pc.get('reasoning')}",
        f"System prompt:         {system_preview or 'none'}",
        f"Created at:            {asst.get('created_at') or 'unknown'}",
        f"Updated at:            {asst.get('updated_at') or 'unknown'}",
    ]
    return "\n".join(lines)


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


def _format_update(payload: dict[str, Any]) -> str:
    asst = payload["assistant"]
    fields = ", ".join(payload.get("updated_fields") or [])
    return "\n".join([
        f"Updated at: {payload['updated_at']}",
        f"Assistant ID: {payload['assistant_id']}",
        f"Updated fields: {fields}",
        f"Name: {asst.get('name') or 'unknown'}",
        f"LLM: {asst.get('llm_id') or 'unknown'}",
        f"Temperature: {asst.get('temperature')}",
        f"Similarity threshold: {asst.get('similarity_threshold')}",
        f"Top N: {asst.get('top_n')}",
        f"Rerank: {asst.get('rerank_id') or 'none'}",
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

        if args.command == "update":
            payload = update_assistant(args, base_url=base_url, api_key=api_key)
            print(format_json(payload) if args.json_output else _format_update(payload))
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
