#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import mimetypes
import os
import sys
import urllib.parse
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from common import (
    ApiError,
    ConfigError,
    DataError,
    ScriptError,
    add_runtime_config_arguments,
    configure_stdio_utf8,
    current_timestamp,
    decode_json_response,
    ensure_success,
    extract_error_message,
    format_json,
    request_json,
    resolve_runtime_config,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(argv) if argv is not None else sys.argv[1:]

    if argv and argv[0] in {"list", "delete"}:
        parser = argparse.ArgumentParser(description="Upload or delete documents in a RAGFlow dataset.")
        parser.add_argument("command", choices=("list", "delete"))
        parser.add_argument("dataset_id", help="Dataset ID")
        if argv[0] == "list":
            parser.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
            parser.add_argument("--page-size", type=int, default=100, help="Page size (default: 100)")
        else:
            parser.add_argument(
                "--ids",
                required=True,
                help="Comma-separated document IDs, for example: id_1,id_2",
            )
        parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")
        add_runtime_config_arguments(parser)
        return parser.parse_args(argv)

    parser = argparse.ArgumentParser(description="Upload or delete documents in a RAGFlow dataset.")
    parser.set_defaults(command="upload")
    parser.add_argument("dataset_id", help="Dataset ID")
    parser.add_argument("files", nargs="+", help="File paths to upload")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")
    add_runtime_config_arguments(parser)
    return parser.parse_args(argv)


def _build_multipart(file_paths: list[str]) -> tuple[str, bytes]:
    boundary = "----OpenClawBoundary" + uuid.uuid4().hex
    body = bytearray()

    for file_path in file_paths:
        filename = os.path.basename(file_path)
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with open(file_path, "rb") as file_obj:
            content = file_obj.read()

        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
        )
        body.extend(f"Content-Type: {mime}\r\n\r\n".encode())
        body.extend(content)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode())
    return boundary, bytes(body)


def _normalize_document(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": document.get("id"),
        "name": document.get("name"),
        "dataset_id": document.get("dataset_id"),
        "run": document.get("run"),
        "chunk_method": document.get("chunk_method"),
        "chunk_count": document.get("chunk_count"),
        "token_count": document.get("token_count"),
        "created_at": document.get("created_at"),
    }


def _parse_ids(raw_value: str) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()

    for item in raw_value.split(","):
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ids.append(value)

    if not ids:
        raise ConfigError("--ids must include at least one document ID.")
    return ids


def _validate_positive(name: str, value: int) -> None:
    if value <= 0:
        raise ConfigError(f"{name} must be greater than 0.")


def upload_documents(dataset_id: str, file_paths: list[str], *, base_url: str, api_key: str) -> dict[str, Any]:
    missing = [path for path in file_paths if not Path(path).exists()]
    if missing:
        raise ConfigError("File(s) not found: " + ", ".join(missing))

    boundary, body = _build_multipart(file_paths)
    url = f"{base_url}/api/v1/datasets/{dataset_id}/documents"
    request_obj = urllib.request.Request(url, data=body, method="POST")
    request_obj.add_header("Authorization", f"Bearer {api_key}")
    request_obj.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with urllib.request.urlopen(request_obj, timeout=120) as response:
            payload = decode_json_response(response.read())
    except urllib.error.HTTPError as exc:
        message = extract_error_message(exc.read())
        if message:
            raise ApiError(message) from None
        raise ApiError(f"HTTP request failed with status {exc.code}.") from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise ApiError(f"Upload failed: {reason}") from None

    ensure_success(payload)
    raw_documents = payload.get("data")
    if not isinstance(raw_documents, list):
        raise ScriptError("Upload response missing data list.")

    documents = [_normalize_document(document) for document in raw_documents]
    return {
        "dataset_id": dataset_id,
        "uploaded_at": current_timestamp(),
        "uploaded_count": len(documents),
        "document_ids": [document["id"] for document in documents if isinstance(document.get("id"), str)],
        "documents": documents,
    }


def list_documents(
    dataset_id: str,
    *,
    page: int,
    page_size: int,
    base_url: str,
    api_key: str,
) -> dict[str, Any]:
    normalized_dataset_id = dataset_id.strip()
    if not normalized_dataset_id:
        raise ConfigError("dataset_id must not be empty.")
    _validate_positive("--page", page)
    _validate_positive("--page-size", page_size)

    encoded_dataset_id = urllib.parse.quote(normalized_dataset_id, safe="")
    query = urllib.parse.urlencode({"page": page, "page_size": page_size})
    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/datasets/{encoded_dataset_id}/documents?{query}",
            api_key,
        )
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataError("Document list response missing data object.")
    raw_documents = data.get("docs")
    total = data.get("total")
    if not isinstance(raw_documents, list):
        raise DataError("Document list response missing data.docs.")
    if not isinstance(total, int):
        raise DataError("Document list response missing data.total.")

    documents = [_normalize_document(document) for document in raw_documents]
    return {
        "dataset_id": normalized_dataset_id,
        "checked_at": current_timestamp(),
        "page": page,
        "page_size": page_size,
        "count": len(documents),
        "total": total,
        "documents": documents,
    }


def delete_documents(dataset_id: str, raw_ids: str, *, base_url: str, api_key: str) -> dict[str, Any]:
    normalized_dataset_id = dataset_id.strip()
    if not normalized_dataset_id:
        raise ConfigError("dataset_id must not be empty.")

    document_ids = _parse_ids(raw_ids)
    encoded_dataset_id = urllib.parse.quote(normalized_dataset_id, safe="")
    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/datasets/{encoded_dataset_id}/documents",
            api_key,
            method="DELETE",
            body=format_json({"ids": document_ids}).encode("utf-8"),
            content_type="application/json",
        )
    )
    return {
        "dataset_id": normalized_dataset_id,
        "deleted_at": current_timestamp(),
        "deleted_count": len(document_ids),
        "document_ids": document_ids,
        "message": payload.get("message", ""),
        "data": payload.get("data"),
    }


def _format_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Dataset: {payload['dataset_id']}",
        f"Uploaded at: {payload['uploaded_at']}",
        f"Uploaded: {payload['uploaded_count']} document(s)",
    ]

    for document in payload["documents"]:
        lines.extend(
            [
                "",
                f"- {document.get('name') or 'unknown'}",
                f"  id: {document.get('id') or 'unknown'}",
                f"  run: {document.get('run') or 'unknown'}",
                f"  chunk_method: {document.get('chunk_method') or 'unknown'}",
            ]
        )

    if payload["document_ids"]:
        lines.extend(
            [
                "",
                "Next:",
                f"python scripts/parse.py {payload['dataset_id']} {' '.join(payload['document_ids'])}",
            ]
        )
    return "\n".join(lines)


def _format_delete_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Dataset: {payload['dataset_id']}",
        f"Deleted at: {payload['deleted_at']}",
        f"Deleted: {payload['deleted_count']} document(s)",
        f"IDs: {', '.join(payload['document_ids'])}",
    ]
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        lines.append(f"Message: {message.strip()}")
    return "\n".join(lines)


def _format_list_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Dataset: {payload['dataset_id']}",
        f"Checked at: {payload['checked_at']}",
        f"Documents: {payload['count']} / total={payload['total']}",
        f"Page: {payload['page']}",
        f"Page size: {payload['page_size']}",
    ]
    for document in payload["documents"]:
        lines.extend(
            [
                "",
                f"- {document.get('name') or 'unknown'}",
                f"  id: {document.get('id') or 'unknown'}",
                f"  run: {document.get('run') or 'unknown'}",
                f"  chunk_method: {document.get('chunk_method') or 'unknown'}",
                f"  chunks: {document.get('chunk_count') if document.get('chunk_count') is not None else 'unknown'}",
                f"  tokens: {document.get('token_count') if document.get('token_count') is not None else 'unknown'}",
            ]
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)

    try:
        base_url, api_key, _memory_config = resolve_runtime_config(args)
        if args.command == "list":
            payload = list_documents(
                args.dataset_id,
                page=args.page,
                page_size=args.page_size,
                base_url=base_url,
                api_key=api_key,
            )
            print(format_json(payload) if args.json_output else _format_list_text(payload))
            return 0

        if args.command == "delete":
            payload = delete_documents(args.dataset_id, args.ids, base_url=base_url, api_key=api_key)
            print(format_json(payload) if args.json_output else _format_delete_text(payload))
            return 0

        payload = upload_documents(
            args.dataset_id,
            args.files,
            base_url=base_url,
            api_key=api_key,
        )
        print(format_json(payload) if args.json_output else _format_text(payload))
        return 0
    except ScriptError as exc:
        if args.json_output:
            error_payload = {
                "dataset_id": getattr(args, "dataset_id", ""),
                "error": str(exc),
            }
            if getattr(args, "command", "upload") == "delete":
                error_payload.update(
                    {
                        "deleted_at": current_timestamp(),
                        "deleted_count": 0,
                        "document_ids": [],
                    }
                )
            elif getattr(args, "command", "upload") == "list":
                error_payload.update(
                    {
                        "checked_at": current_timestamp(),
                        "page": getattr(args, "page", 1),
                        "page_size": getattr(args, "page_size", 100),
                        "count": 0,
                        "total": 0,
                        "documents": [],
                    }
                )
            else:
                error_payload.update(
                    {
                        "uploaded_at": current_timestamp(),
                        "uploaded_count": 0,
                        "document_ids": [],
                        "documents": [],
                    }
                )
            print(
                format_json(error_payload)
            )
        else:
            print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
