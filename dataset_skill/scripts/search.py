#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
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

DEFAULT_TOP_K = 5
DEFAULT_THRESHOLD = 0.2
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 30
PREVIEW_LIMIT = 240


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrieve relevant chunks from RAGFlow datasets.")
    parser.add_argument("query", help="Search query text")
    parser.add_argument(
        "dataset_id",
        nargs="?",
        help="Optional dataset ID shortcut. Used for standard retrieval, or as the fallback kb_id for --retrieval-test.",
    )
    parser.add_argument("--dataset-ids", help="Comma-separated dataset IDs")
    parser.add_argument("--doc-ids", help="Comma-separated document IDs")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help=f"Maximum results (default: {DEFAULT_TOP_K})")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Similarity threshold in the range [0, 1] (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument("--vector-weight", type=float, help="Vector similarity weight in the range [0, 1]")
    parser.add_argument("--page", type=int, default=DEFAULT_PAGE, help=f"Page number (default: {DEFAULT_PAGE})")
    parser.add_argument(
        "--page-size",
        "--size",
        dest="page_size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Page size (default: {DEFAULT_PAGE_SIZE})",
    )
    parser.add_argument("--keyword", action="store_true", help="Enable keyword extraction")
    parser.add_argument("--use-kg", action="store_true", help="Enable knowledge graph retrieval")
    parser.add_argument("--rerank-id", help="Optional rerank model ID")
    parser.add_argument("--search-id", help="Optional search session ID")
    parser.add_argument("--retrieval-test", action="store_true", help="Use /api/v1/chunk/retrieval_test")
    parser.add_argument("--kb-id", help="Dataset ID required by retrieval_test")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")
    add_runtime_config_arguments(parser)
    return parser.parse_args(argv)


def _validate_range(name: str, value: float, *, min_value: float = 0.0, max_value: float = 1.0) -> None:
    if value < min_value or value > max_value:
        raise ConfigError(f"{name} must be between {min_value} and {max_value}.")


def _parse_ids(raw_value: str, *, label: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for item in raw_value.split(","):
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)

    if not values:
        raise ConfigError(f"{label} must include at least one ID.")
    return values


def _resolve_dataset_ids(args: argparse.Namespace) -> list[str]:
    if args.dataset_ids:
        return _parse_ids(args.dataset_ids, label="--dataset-ids")
    if args.dataset_id:
        dataset_id = args.dataset_id.strip()
        if not dataset_id:
            raise ConfigError("dataset_id must not be empty.")
        return [dataset_id]
    return []


def _resolve_kb_id(args: argparse.Namespace, dataset_ids: list[str]) -> str:
    if args.kb_id:
        kb_id = args.kb_id.strip()
        if not kb_id:
            raise ConfigError("--kb-id must not be empty.")
        return kb_id
    if dataset_ids:
        return dataset_ids[0]
    raise ConfigError("--kb-id is required for --retrieval-test when no dataset ID is provided.")


def _normalize_content(chunk: dict[str, Any]) -> str:
    for key in ("content_with_weight", "content", "answer", "chunk"):
        value = chunk.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return " ".join(str(item) for item in value)
    return ""


def _normalize_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_name": chunk.get("document_keyword") or chunk.get("docnm_kwd") or chunk.get("document_name"),
        "document_id": chunk.get("document_id") or chunk.get("doc_id"),
        "dataset_id": chunk.get("dataset_id") or chunk.get("kb_id"),
        "chunk_id": chunk.get("chunk_id") or chunk.get("id"),
        "similarity": chunk.get("similarity"),
        "vector_similarity": chunk.get("vector_similarity"),
        "term_similarity": chunk.get("term_similarity"),
        "positions": chunk.get("positions"),
        "content": _normalize_content(chunk),
    }


def _extract_chunks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if data is None:
        return []
    if isinstance(data, dict):
        chunks = data.get("chunks")
        if chunks is None:
            return []
        if not isinstance(chunks, list):
            raise DataError("Retrieval response data.chunks must be a list.")
        return [_normalize_chunk(chunk) for chunk in chunks if isinstance(chunk, dict)]
    if isinstance(data, list):
        return [_normalize_chunk(chunk) for chunk in data if isinstance(chunk, dict)]
    raise DataError("Retrieval response data must be an object or array.")


def search(args: argparse.Namespace, *, base_url: str, api_key: str) -> dict[str, Any]:
    if args.top_k <= 0:
        raise ConfigError("--top-k must be greater than 0.")
    if args.page <= 0:
        raise ConfigError("--page must be greater than 0.")
    if args.page_size <= 0:
        raise ConfigError("--page-size must be greater than 0.")
    _validate_range("--threshold", args.threshold)
    if args.vector_weight is not None:
        _validate_range("--vector-weight", args.vector_weight)

    dataset_ids = _resolve_dataset_ids(args)
    doc_ids = _parse_ids(args.doc_ids, label="--doc-ids") if args.doc_ids else []

    body: dict[str, Any] = {
        "question": args.query,
        "top_k": args.top_k,
        "similarity_threshold": args.threshold,
        "page": args.page,
        "size": args.page_size,
    }
    if args.vector_weight is not None:
        body["vector_similarity_weight"] = args.vector_weight
    if doc_ids:
        body["document_ids"] = doc_ids
    if args.keyword:
        body["keyword"] = True
    if args.use_kg:
        body["use_kg"] = True
    if args.rerank_id:
        body["rerank_id"] = args.rerank_id
    if args.search_id:
        body["search_id"] = args.search_id

    api_name = "retrieval"
    kb_id: str | None = None
    if args.retrieval_test:
        api_name = "retrieval_test"
        kb_id = _resolve_kb_id(args, dataset_ids)
        body["kb_id"] = kb_id
        api_endpoint = f"{base_url}/api/v1/chunk/retrieval_test"
    else:
        if dataset_ids:
            body["dataset_ids"] = dataset_ids
        api_endpoint = f"{base_url}/api/v1/retrieval"

    payload = ensure_success(
        request_json(
            api_endpoint,
            api_key,
            method="POST",
            body=json.dumps(body).encode("utf-8"),
            content_type="application/json",
        )
    )
    chunks = _extract_chunks(payload)

    return {
        "checked_at": current_timestamp(),
        "query": args.query,
        "api": api_name,
        "dataset_ids": dataset_ids,
        "kb_id": kb_id,
        "doc_ids": doc_ids,
        "count": len(chunks),
        "chunks": chunks,
    }


def _format_similarity(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2%}"
    return "unknown"


def _format_preview(content: str) -> str:
    compact = " ".join(content.split())
    if not compact:
        return "unknown"
    if len(compact) <= PREVIEW_LIMIT:
        return compact
    return f"{compact[: PREVIEW_LIMIT - 3]}..."


def _format_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Checked at: {payload['checked_at']}",
        f"Query: {payload['query']}",
        f"API: {payload['api']}",
        f"Results: {payload['count']}",
    ]
    if payload["dataset_ids"]:
        lines.append(f"Dataset IDs: {', '.join(payload['dataset_ids'])}")
    if payload.get("kb_id"):
        lines.append(f"KB ID: {payload['kb_id']}")
    if payload["doc_ids"]:
        lines.append(f"Document IDs: {', '.join(payload['doc_ids'])}")

    if payload["count"] == 0:
        lines.append("No results found.")
        return "\n".join(lines)

    for index, chunk in enumerate(payload["chunks"], start=1):
        lines.extend(
            [
                "",
                f"[{index}] {chunk.get('document_name') or 'unknown'}",
                f"  similarity: {_format_similarity(chunk.get('similarity'))}",
                f"  document_id: {chunk.get('document_id') or 'unknown'}",
                f"  dataset_id: {chunk.get('dataset_id') or 'unknown'}",
                f"  chunk_id: {chunk.get('chunk_id') or 'unknown'}",
                f"  content: {_format_preview(chunk.get('content') or '')}",
            ]
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)

    try:
        base_url, api_key = resolve_runtime_config(args)
        payload = search(args, base_url=base_url, api_key=api_key)
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
