#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Manage chunks within a RAGFlow document.

Usage:
  python3 scripts/chunks.py list   DATASET_ID DOCUMENT_ID --json
  python3 scripts/chunks.py create DATASET_ID DOCUMENT_ID --content "text" --json
  python3 scripts/chunks.py update DATASET_ID DOCUMENT_ID CHUNK_ID --content "text" --json
  python3 scripts/chunks.py delete DATASET_ID DOCUMENT_ID --ids CID1,CID2 --json
  python3 scripts/chunks.py switch DATASET_ID DOCUMENT_ID --ids CID1,CID2 --available 1 --json
"""

import argparse
import json
import urllib.parse
from typing import Any

from common import (
    ConfigError,
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

DEFAULT_PAGE_SIZE = 30
PREVIEW_LIMIT = 200


def _build_global_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")
    add_runtime_config_arguments(parser)
    return parser


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    global_parser = _build_global_parser()
    parser = argparse.ArgumentParser(
        description="Manage chunks within a RAGFlow document.",
        parents=[global_parser],
    )
    subparsers = parser.add_subparsers(dest="command")

    list_p = subparsers.add_parser("list", help="List chunks in a document", parents=[global_parser])
    list_p.add_argument("dataset_id")
    list_p.add_argument("document_id")
    list_p.add_argument("--page", type=int, default=1)
    list_p.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, dest="page_size")
    list_p.add_argument("--keywords", help="Filter by keywords")

    create_p = subparsers.add_parser("create", help="Create a chunk", parents=[global_parser])
    create_p.add_argument("dataset_id")
    create_p.add_argument("document_id")
    create_p.add_argument("--content", required=True, help="Chunk content text")
    create_p.add_argument("--important-keywords", dest="important_keywords",
                          help="Comma-separated important keywords")

    update_p = subparsers.add_parser("update", help="Update a chunk", parents=[global_parser])
    update_p.add_argument("dataset_id")
    update_p.add_argument("document_id")
    update_p.add_argument("chunk_id")
    update_p.add_argument("--content", help="Updated content text")
    update_p.add_argument("--important-keywords", dest="important_keywords",
                          help="Comma-separated important keywords")
    update_p.add_argument("--available", choices=("0", "1"),
                          help="Set availability: 1=enabled, 0=disabled")

    delete_p = subparsers.add_parser("delete", help="Delete chunks", parents=[global_parser])
    delete_p.add_argument("dataset_id")
    delete_p.add_argument("document_id")
    delete_p.add_argument("--ids", required=True, help="Comma-separated chunk IDs to delete")

    switch_p = subparsers.add_parser("switch", help="Toggle chunk availability", parents=[global_parser])
    switch_p.add_argument("dataset_id")
    switch_p.add_argument("document_id")
    switch_p.add_argument("--ids", required=True, help="Comma-separated chunk IDs")
    switch_p.add_argument("--available", required=True, choices=("0", "1"),
                          help="1=enable, 0=disable")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        raise SystemExit(1)
    return args


def _parse_ids(raw: str, *, label: str) -> list[str]:
    ids = [v.strip() for v in raw.split(",") if v.strip()]
    seen: set[str] = set()
    deduped = [v for v in ids if not (v in seen or seen.add(v))]  # type: ignore[func-returns-value]
    if not deduped:
        raise DataError(f"{label} must include at least one ID.")
    return deduped


def _chunk_url(base_url: str, dataset_id: str, document_id: str, chunk_id: str | None = None) -> str:
    ds = urllib.parse.quote(dataset_id, safe="")
    doc = urllib.parse.quote(document_id, safe="")
    base = f"{base_url}/api/v1/datasets/{ds}/documents/{doc}/chunks"
    if chunk_id:
        return f"{base}/{urllib.parse.quote(chunk_id, safe='')}"
    return base


def _normalize_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": chunk.get("id"),
        "content": chunk.get("content"),
        "available": chunk.get("available"),
        "important_keywords": chunk.get("important_keywords") or [],
        "document_id": chunk.get("document_id"),
        "dataset_id": chunk.get("dataset_id"),
        "positions": chunk.get("positions"),
    }


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def list_chunks(dataset_id: str, document_id: str, *,
                base_url: str, api_key: str,
                page: int = 1, page_size: int = DEFAULT_PAGE_SIZE,
                keywords: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if keywords:
        params["keywords"] = keywords
    query = urllib.parse.urlencode(params)
    payload = ensure_success(
        request_json(f"{_chunk_url(base_url, dataset_id, document_id)}?{query}", api_key)
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataError("Chunk list response missing data object.")
    raw_chunks = data.get("chunks", [])
    total = data.get("total", len(raw_chunks))
    chunks = [_normalize_chunk(c) for c in raw_chunks if isinstance(c, dict)]
    return {
        "checked_at": current_timestamp(),
        "dataset_id": dataset_id,
        "document_id": document_id,
        "page": page,
        "page_size": page_size,
        "count": len(chunks),
        "total": total,
        "chunks": chunks,
    }


def create_chunk(dataset_id: str, document_id: str, content: str, *,
                 base_url: str, api_key: str,
                 important_keywords: str | None = None) -> dict[str, Any]:
    if not content.strip():
        raise ConfigError("--content must not be empty.")
    body: dict[str, Any] = {"content": content}
    if important_keywords:
        body["important_keywords"] = [k.strip() for k in important_keywords.split(",") if k.strip()]
    payload = ensure_success(
        request_json(
            _chunk_url(base_url, dataset_id, document_id),
            api_key,
            method="POST",
            body=json.dumps(body).encode("utf-8"),
            content_type="application/json",
        )
    )
    data = payload.get("data")
    chunk = _normalize_chunk(data) if isinstance(data, dict) else {}
    return {
        "created_at": current_timestamp(),
        "dataset_id": dataset_id,
        "document_id": document_id,
        "chunk": chunk,
    }


def update_chunk(dataset_id: str, document_id: str, chunk_id: str, *,
                 base_url: str, api_key: str,
                 content: str | None = None,
                 important_keywords: str | None = None,
                 available: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if content is not None:
        body["content"] = content
    if important_keywords is not None:
        body["important_keywords"] = [k.strip() for k in important_keywords.split(",") if k.strip()]
    if available is not None:
        body["available"] = int(available)
    if not body:
        raise ConfigError("No update fields provided. Use --content, --important-keywords, or --available.")
    payload = ensure_success(
        request_json(
            _chunk_url(base_url, dataset_id, document_id, chunk_id),
            api_key,
            method="PUT",
            body=json.dumps(body).encode("utf-8"),
            content_type="application/json",
        )
    )
    data = payload.get("data")
    return {
        "updated_at": current_timestamp(),
        "dataset_id": dataset_id,
        "document_id": document_id,
        "chunk_id": chunk_id,
        "chunk": _normalize_chunk(data) if isinstance(data, dict) else {},
        "message": payload.get("message", ""),
    }


def delete_chunks(dataset_id: str, document_id: str, raw_ids: str, *,
                  base_url: str, api_key: str) -> dict[str, Any]:
    chunk_ids = _parse_ids(raw_ids, label="--ids")
    payload = ensure_success(
        request_json(
            _chunk_url(base_url, dataset_id, document_id),
            api_key,
            method="DELETE",
            body=json.dumps({"chunk_ids": chunk_ids}).encode("utf-8"),
            content_type="application/json",
        )
    )
    return {
        "deleted_at": current_timestamp(),
        "dataset_id": dataset_id,
        "document_id": document_id,
        "chunk_ids": chunk_ids,
        "message": payload.get("message", ""),
    }


def switch_chunks(dataset_id: str, document_id: str, raw_ids: str, available: str, *,
                  base_url: str, api_key: str) -> dict[str, Any]:
    chunk_ids = _parse_ids(raw_ids, label="--ids")
    body = {"chunk_ids": chunk_ids, "available": int(available)}
    ds = urllib.parse.quote(dataset_id, safe="")
    doc = urllib.parse.quote(document_id, safe="")
    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/datasets/{ds}/documents/{doc}/chunks/switch",
            api_key,
            method="POST",
            body=json.dumps(body).encode("utf-8"),
            content_type="application/json",
        )
    )
    return {
        "switched_at": current_timestamp(),
        "dataset_id": dataset_id,
        "document_id": document_id,
        "chunk_ids": chunk_ids,
        "available": int(available),
        "message": payload.get("message", ""),
    }


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _preview(text: str | None) -> str:
    if not text:
        return "unknown"
    compact = " ".join(text.split())
    return compact[:PREVIEW_LIMIT] + "..." if len(compact) > PREVIEW_LIMIT else compact


def _format_list(payload: dict[str, Any]) -> str:
    lines = [
        f"Checked at: {payload['checked_at']}",
        f"Dataset:    {payload['dataset_id']}",
        f"Document:   {payload['document_id']}",
        f"Chunks: {payload['count']} / total={payload['total']}  (page {payload['page']}, size {payload['page_size']})",
    ]
    for i, chunk in enumerate(payload["chunks"], 1):
        avail = "enabled" if chunk.get("available") else "disabled"
        lines.extend([
            "",
            f"[{i}] id: {chunk.get('id') or 'unknown'}  ({avail})",
            f"  content: {_preview(chunk.get('content'))}",
        ])
        kw = chunk.get("important_keywords") or []
        if kw:
            lines.append(f"  keywords: {', '.join(kw)}")
    return "\n".join(lines)


def _format_create(payload: dict[str, Any]) -> str:
    chunk = payload.get("chunk") or {}
    return "\n".join([
        f"Created at: {payload['created_at']}",
        f"Chunk ID:   {chunk.get('id') or 'unknown'}",
        f"Content:    {_preview(chunk.get('content'))}",
    ])


def _format_update(payload: dict[str, Any]) -> str:
    return "\n".join([
        f"Updated at: {payload['updated_at']}",
        f"Chunk ID:   {payload['chunk_id']}",
        f"Message:    {payload.get('message') or 'ok'}",
    ])


def _format_delete(payload: dict[str, Any]) -> str:
    lines = [
        f"Deleted at: {payload['deleted_at']}",
        f"Chunks:     {', '.join(payload['chunk_ids'])}",
    ]
    if payload.get("message"):
        lines.append(f"Message: {payload['message']}")
    return "\n".join(lines)


def _format_switch(payload: dict[str, Any]) -> str:
    state = "enabled" if payload["available"] else "disabled"
    lines = [
        f"Switched at: {payload['switched_at']}",
        f"Chunks:      {', '.join(payload['chunk_ids'])}",
        f"Available:   {state}",
    ]
    if payload.get("message"):
        lines.append(f"Message: {payload['message']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)

    try:
        base_url, api_key = resolve_runtime_config(args)

        if args.command == "list":
            payload = list_chunks(
                args.dataset_id, args.document_id,
                base_url=base_url, api_key=api_key,
                page=args.page, page_size=args.page_size,
                keywords=getattr(args, "keywords", None),
            )
            print(format_json(payload) if args.json_output else _format_list(payload))
            return 0

        if args.command == "create":
            payload = create_chunk(
                args.dataset_id, args.document_id, args.content,
                base_url=base_url, api_key=api_key,
                important_keywords=getattr(args, "important_keywords", None),
            )
            print(format_json(payload) if args.json_output else _format_create(payload))
            return 0

        if args.command == "update":
            payload = update_chunk(
                args.dataset_id, args.document_id, args.chunk_id,
                base_url=base_url, api_key=api_key,
                content=args.content,
                important_keywords=getattr(args, "important_keywords", None),
                available=getattr(args, "available", None),
            )
            print(format_json(payload) if args.json_output else _format_update(payload))
            return 0

        if args.command == "delete":
            payload = delete_chunks(
                args.dataset_id, args.document_id, args.ids,
                base_url=base_url, api_key=api_key,
            )
            print(format_json(payload) if args.json_output else _format_delete(payload))
            return 0

        if args.command == "switch":
            payload = switch_chunks(
                args.dataset_id, args.document_id, args.ids, args.available,
                base_url=base_url, api_key=api_key,
            )
            print(format_json(payload) if args.json_output else _format_switch(payload))
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
