#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import sys
import urllib.parse
from dataclasses import asdict, dataclass
from typing import Any

from common import (
    ApiError,
    ConfigError,
    DataError,
    ScriptError,
    add_runtime_config_arguments,
    configure_stdio_utf8,
    current_timestamp,
    ensure_success,
    format_json,
    request_json,
    require_api_key,
    resolve_base_url,
    resolve_runtime_config,
    serialize_script_error,
)

DEFAULT_PAGE_SIZE = 100
STATUS_ORDER = ("UNSTART", "RUNNING", "DONE", "FAIL", "CANCEL")
TERMINAL_STATES = {"DONE", "FAIL", "CANCEL"}
RUN_STATUS_MAP = {
    "0": "UNSTART",
    "1": "RUNNING",
    "2": "CANCEL",
    "3": "DONE",
    "4": "FAIL",
}


@dataclass
class DocumentStatus:
    id: str
    name: str
    run: str
    chunk_count: int
    token_count: int
    progress_msg: Any | None = None


def parse_doc_ids(raw_value: str | None) -> list[str] | None:
    if raw_value is None:
        return None

    doc_ids: list[str] = []
    seen: set[str] = set()
    for item in raw_value.split(","):
        doc_id = item.strip()
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        doc_ids.append(doc_id)

    if not doc_ids:
        raise ConfigError("--doc-ids must include at least one document ID.")
    return doc_ids


def _build_documents_url(base_url: str, dataset_id: str, page: int, page_size: int) -> str:
    encoded_dataset_id = urllib.parse.quote(dataset_id, safe="")
    query = urllib.parse.urlencode({"page": page, "page_size": page_size})
    return f"{base_url}/api/v1/datasets/{encoded_dataset_id}/documents?{query}"


def _fetch_documents_page(base_url: str, api_key: str, dataset_id: str, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    payload = ensure_success(request_json(_build_documents_url(base_url, dataset_id, page, page_size), api_key))
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataError("Response missing data object.")

    docs = data.get("docs")
    total = data.get("total")
    if not isinstance(docs, list):
        raise DataError("Response missing data.docs.")
    if not isinstance(total, int):
        raise DataError("Response missing data.total.")
    return docs, total


def _fetch_all_documents(base_url: str, api_key: str, dataset_id: str) -> list[dict[str, Any]]:
    all_docs: list[dict[str, Any]] = []
    page = 1
    total: int | None = None

    while True:
        docs, page_total = _fetch_documents_page(base_url, api_key, dataset_id, page, DEFAULT_PAGE_SIZE)
        if total is None:
            total = page_total
        all_docs.extend(docs)

        if len(all_docs) >= total or not docs:
            return all_docs[:total]
        page += 1


def _coerce_required_string(document_id: str, field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataError(f"Document {document_id} is missing a valid {field_name}.")
    return value.strip()


def _coerce_required_int(document_id: str, field_name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise DataError(f"Document {document_id} is missing a valid {field_name}.")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise DataError(f"Document {document_id} is missing a valid {field_name}.") from None
    if number < 0:
        raise DataError(f"Document {document_id} is missing a valid {field_name}.")
    return number


def _normalize_run(value: Any, document_id: str) -> str:
    if isinstance(value, int):
        mapped = RUN_STATUS_MAP.get(str(value))
        if mapped:
            return mapped
    elif isinstance(value, str):
        raw_value = value.strip()
        mapped = RUN_STATUS_MAP.get(raw_value)
        if mapped:
            return mapped
        normalized = raw_value.upper()
        if normalized in STATUS_ORDER:
            return normalized

    raise DataError(f"Document {document_id} has an unsupported run status: {value!r}.")


def _normalize_progress_msg(value: Any) -> Any | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return value


def _normalize_document(raw_doc: dict[str, Any]) -> DocumentStatus:
    if not isinstance(raw_doc, dict):
        raise DataError("Response contains a malformed document entry.")

    raw_id = raw_doc.get("id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise DataError("Response contains a document with a missing id.")
    document_id = raw_id.strip()

    return DocumentStatus(
        id=document_id,
        name=_coerce_required_string(document_id, "name", raw_doc.get("name")),
        run=_normalize_run(raw_doc.get("run"), document_id),
        chunk_count=_coerce_required_int(document_id, "chunk_count", raw_doc.get("chunk_count")),
        token_count=_coerce_required_int(document_id, "token_count", raw_doc.get("token_count")),
        progress_msg=_normalize_progress_msg(raw_doc.get("progress_msg")),
    )


def _select_documents(documents: list[DocumentStatus], target_ids: list[str] | None) -> list[DocumentStatus]:
    if not target_ids:
        return documents

    documents_by_id = {document.id: document for document in documents}
    missing_ids = [doc_id for doc_id in target_ids if doc_id not in documents_by_id]
    if missing_ids:
        raise DataError("--doc-ids contains document IDs that were not found in the dataset: " + ", ".join(missing_ids))
    return [documents_by_id[doc_id] for doc_id in target_ids]


def _build_payload(dataset_id: str, documents: list[DocumentStatus]) -> dict[str, Any]:
    summary = {"total": len(documents)}
    for status in STATUS_ORDER:
        summary[status] = 0

    for document in documents:
        summary[document.run] += 1

    return {
        "dataset_id": dataset_id,
        "checked_at": current_timestamp(),
        "summary": summary,
        "documents": [asdict(document) for document in documents],
        "all_terminal": all(document.run in TERMINAL_STATES for document in documents),
    }


def collect_status_payload(
    dataset_id: str,
    target_ids: list[str] | None = None,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    resolved_base_url = resolve_base_url(base_url)
    resolved_api_key = require_api_key(api_key)
    raw_documents = _fetch_all_documents(resolved_base_url, resolved_api_key, dataset_id)
    documents = [_normalize_document(raw_doc) for raw_doc in raw_documents]
    return _build_payload(dataset_id, _select_documents(documents, target_ids))


def format_status_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    documents = payload["documents"]
    lines = [
        f"Dataset: {payload['dataset_id']}",
        f"Checked at: {payload['checked_at']}",
        f"Watching: {summary['total']} document(s)",
        "",
    ]

    for status in STATUS_ORDER:
        lines.append(f"{status}: {summary[status]}")

    for document in documents:
        lines.extend(
            [
                "",
                f"[{document['run']}] {document['name']}",
                f"id: {document['id']}",
                f"chunks: {document['chunk_count']}",
                f"tokens: {document['token_count']}",
            ]
        )
        progress_msg = document.get("progress_msg")
        if progress_msg is not None:
            rendered_progress = progress_msg if isinstance(progress_msg, str) else json.dumps(progress_msg, ensure_ascii=False)
            if rendered_progress:
                label = "error" if document["run"] == "FAIL" else "message"
                lines.append(f"{label}: {rendered_progress}")
    return "\n".join(lines)


def _write_error(
    exc: ScriptError,
    json_output: bool,
    dataset_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    if json_output:
        error_payload: dict[str, Any] = {}
        if payload:
            error_payload.update(payload)
        elif dataset_id:
            error_payload["dataset_id"] = dataset_id
        if "checked_at" not in error_payload:
            error_payload["checked_at"] = current_timestamp()
        error_payload["error"] = str(exc)
        error_detail = serialize_script_error(exc)
        if isinstance(exc, ApiError):
            error_payload["api_error"] = error_detail
        else:
            error_payload["error_detail"] = error_detail
        print(format_json(error_payload))
        return

    print(f"Error: {exc}", file=sys.stderr)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show document parse status for a dataset.")
    parser.add_argument("dataset_id", help="Dataset ID")
    parser.add_argument("--doc-ids", help="Comma-separated document IDs to monitor")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")
    add_runtime_config_arguments(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)

    try:
        target_ids = parse_doc_ids(args.doc_ids)
        base_url, api_key = resolve_runtime_config(args)

        payload = collect_status_payload(
            args.dataset_id,
            target_ids,
            base_url=base_url,
            api_key=api_key,
        )
        print(format_json(payload) if args.json_output else format_status_text(payload))
        return 0
    except ScriptError as exc:
        _write_error(exc, args.json_output, dataset_id=args.dataset_id)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
