#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Send chat messages and manage sessions for a RAGFlow chat assistant.

Usage:
  # Session management
  python3 scripts/chat.py sessions list ASSISTANT_ID --json
  python3 scripts/chat.py sessions create ASSISTANT_ID --name "My Session" --json
  python3 scripts/chat.py sessions delete ASSISTANT_ID --ids SID1,SID2 --json

  # Send a message (non-streaming)
  python3 scripts/chat.py message ASSISTANT_ID "Your question here" --json
  python3 scripts/chat.py message ASSISTANT_ID "Follow-up" --session-id SESSION_ID --json
"""

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


def _build_global_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")
    add_runtime_config_arguments(parser)
    return parser


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    global_parser = _build_global_parser()
    parser = argparse.ArgumentParser(
        description="Send messages and manage sessions for a RAGFlow chat assistant.",
        parents=[global_parser],
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- sessions subcommand ---
    sessions_p = subparsers.add_parser("sessions", help="Manage sessions", parents=[global_parser])
    sess_sub = sessions_p.add_subparsers(dest="sessions_command")

    sess_list = sess_sub.add_parser("list", help="List sessions", parents=[global_parser])
    sess_list.add_argument("assistant_id", help="Assistant ID")
    sess_list.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    sess_list.add_argument("--page-size", type=int, default=30, dest="page_size", help="Page size (default: 30)")

    sess_create = sess_sub.add_parser("create", help="Create a session", parents=[global_parser])
    sess_create.add_argument("assistant_id", help="Assistant ID")
    sess_create.add_argument("--name", default="New session", help="Session name")

    sess_delete = sess_sub.add_parser("delete", help="Delete sessions", parents=[global_parser])
    sess_delete.add_argument("assistant_id", help="Assistant ID")
    sess_delete.add_argument(
        "--ids",
        required=True,
        help="Comma-separated session IDs to delete",
    )

    # --- message subcommand ---
    msg_p = subparsers.add_parser("message", help="Send a chat message", parents=[global_parser])
    msg_p.add_argument("assistant_id", help="Assistant ID")
    msg_p.add_argument("question", help="Message text to send")
    msg_p.add_argument(
        "--session-id",
        dest="session_id",
        help="Existing session ID for multi-turn conversation",
    )

    args = parser.parse_args(argv)
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


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def _normalize_session(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "assistant_id": item.get("chat_id") or item.get("assistant_id"),
        "created_at": item.get("create_date") or item.get("created_at"),
        "message_count": item.get("message_count"),
    }


def list_sessions(assistant_id: str, *, base_url: str, api_key: str,
                  page: int = 1, page_size: int = 30) -> dict[str, Any]:
    import urllib.parse
    query = urllib.parse.urlencode({"page": page, "page_size": page_size})
    payload = ensure_success(
        request_json(f"{base_url}/api/v1/chats/{assistant_id}/sessions?{query}", api_key)
    )
    raw = payload.get("data")
    if not isinstance(raw, list):
        raise DataError("Session list response missing data array.")
    sessions = [_normalize_session(item) for item in raw]
    return {
        "checked_at": current_timestamp(),
        "assistant_id": assistant_id,
        "page": page,
        "page_size": page_size,
        "count": len(sessions),
        "sessions": sessions,
    }


def create_session(assistant_id: str, name: str, *, base_url: str, api_key: str) -> dict[str, Any]:
    if not name.strip():
        raise ConfigError("Session name must not be empty.")
    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/chats/{assistant_id}/sessions",
            api_key,
            method="POST",
            body=json.dumps({"name": name}).encode("utf-8"),
            content_type="application/json",
        )
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataError("Create session response missing data object.")
    return {
        "created_at": current_timestamp(),
        "assistant_id": assistant_id,
        "session": _normalize_session(data),
    }


def delete_sessions(assistant_id: str, raw_ids: str, *, base_url: str, api_key: str) -> dict[str, Any]:
    session_ids = _parse_ids(raw_ids, label="--ids")
    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/chats/{assistant_id}/sessions",
            api_key,
            method="DELETE",
            body=json.dumps({"ids": session_ids}).encode("utf-8"),
            content_type="application/json",
        )
    )
    return {
        "deleted_at": current_timestamp(),
        "assistant_id": assistant_id,
        "session_ids": session_ids,
        "message": payload.get("message", ""),
    }


# ---------------------------------------------------------------------------
# Message / conversation
# ---------------------------------------------------------------------------

def send_message(
    assistant_id: str,
    question: str,
    *,
    session_id: str | None,
    base_url: str,
    api_key: str,
) -> dict[str, Any]:
    if not question.strip():
        raise ConfigError("Question must not be empty.")

    body: dict[str, Any] = {
        "question": question,
        "stream": False,
    }
    if session_id:
        body["session_id"] = session_id

    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/chats/{assistant_id}/completions",
            api_key,
            method="POST",
            body=json.dumps(body).encode("utf-8"),
            content_type="application/json",
        )
    )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataError("Chat completion response missing data object.")

    answer = data.get("answer") or ""
    returned_session_id = data.get("session_id") or session_id or ""
    reference = data.get("reference") or {}
    chunks = reference.get("chunks") or []

    return {
        "asked_at": current_timestamp(),
        "assistant_id": assistant_id,
        "session_id": returned_session_id,
        "question": question,
        "answer": answer,
        "reference_count": len(chunks),
        "references": [
            {
                "document_name": c.get("document_keyword") or c.get("docnm_kwd") or c.get("document_name"),
                "document_id": c.get("document_id") or c.get("doc_id"),
                "chunk_id": c.get("chunk_id") or c.get("id"),
                "similarity": c.get("similarity"),
                "content": (c.get("content_with_weight") or c.get("content") or "")[:300],
            }
            for c in chunks
            if isinstance(c, dict)
        ],
    }


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _format_sessions_list(payload: dict[str, Any]) -> str:
    lines = [
        f"Checked at: {payload['checked_at']}",
        f"Assistant: {payload['assistant_id']}",
        f"Sessions: {payload['count']}  (page {payload.get('page',1)}, size {payload.get('page_size',30)})",
    ]
    for sess in payload["sessions"]:
        lines.extend([
            "",
            f"- {sess.get('name') or 'unknown'}",
            f"  id: {sess.get('id') or 'unknown'}",
            f"  created_at: {sess.get('created_at') or 'unknown'}",
        ])
        if sess.get("message_count") is not None:
            lines.append(f"  messages: {sess['message_count']}")
    return "\n".join(lines)


def _format_session_create(payload: dict[str, Any]) -> str:
    sess = payload["session"]
    return "\n".join([
        f"Created at: {payload['created_at']}",
        f"Assistant: {payload['assistant_id']}",
        f"Name: {sess.get('name') or 'unknown'}",
        f"ID: {sess.get('id') or 'unknown'}",
    ])


def _format_session_delete(payload: dict[str, Any]) -> str:
    lines = [
        f"Deleted at: {payload['deleted_at']}",
        f"Assistant: {payload['assistant_id']}",
        f"Sessions: {', '.join(payload['session_ids'])}",
    ]
    msg = payload.get("message")
    if isinstance(msg, str) and msg.strip():
        lines.append(f"Message: {msg.strip()}")
    return "\n".join(lines)


def _format_message(payload: dict[str, Any]) -> str:
    lines = [
        f"Asked at: {payload['asked_at']}",
        f"Session: {payload['session_id'] or 'unknown'}",
        f"Q: {payload['question']}",
        f"A: {payload['answer']}",
    ]
    if payload["reference_count"]:
        lines.append(f"References: {payload['reference_count']}")
        for ref in payload["references"]:
            lines.extend([
                "",
                f"  [{ref.get('document_name') or 'unknown'}]",
                f"  doc_id: {ref.get('document_id') or 'unknown'}",
                f"  similarity: {ref.get('similarity', 'unknown')}",
                f"  content: {(ref.get('content') or '')[:200]}",
            ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdio_utf8()
    args = _parse_args(argv)

    def _err(msg: str) -> int:
        if args.json_output:
            print(format_json({"checked_at": current_timestamp(), "error": msg}))
        else:
            print(f"Error: {msg}")
        return 1

    try:
        base_url, api_key = resolve_runtime_config(args)
    except ScriptError as exc:
        return _err(str(exc))

    try:
        if args.command == "sessions":
            sc = args.sessions_command
            if sc == "list":
                payload = list_sessions(args.assistant_id, base_url=base_url, api_key=api_key,
                                        page=getattr(args, "page", 1),
                                        page_size=getattr(args, "page_size", 30))
                print(format_json(payload) if args.json_output else _format_sessions_list(payload))
                return 0
            if sc == "create":
                payload = create_session(args.assistant_id, args.name, base_url=base_url, api_key=api_key)
                print(format_json(payload) if args.json_output else _format_session_create(payload))
                return 0
            if sc == "delete":
                payload = delete_sessions(args.assistant_id, args.ids, base_url=base_url, api_key=api_key)
                print(format_json(payload) if args.json_output else _format_session_delete(payload))
                return 0
            return _err(f"Unknown sessions subcommand: {sc}")

        if args.command == "message":
            payload = send_message(
                args.assistant_id,
                args.question,
                session_id=getattr(args, "session_id", None),
                base_url=base_url,
                api_key=api_key,
            )
            print(format_json(payload) if args.json_output else _format_message(payload))
            return 0

        return _err("No command given. Use 'sessions' or 'message'.")

    except ScriptError as exc:
        return _err(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
