#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Manage RAGFlow agents and their sessions.

Usage:
  # List agents
  python3 scripts/agents.py list --json
  python3 scripts/agents.py list --page 2 --page-size 10 --json

  # Agent info
  python3 scripts/agents.py info AGENT_ID --json

  # Session management
  python3 scripts/agents.py sessions list AGENT_ID --json
  python3 scripts/agents.py sessions create AGENT_ID --name "My Session" --json
  python3 scripts/agents.py sessions delete AGENT_ID --ids SID1,SID2 --json

  # Run agent (send a message)
  python3 scripts/agents.py run AGENT_ID "Your question here" --json
  python3 scripts/agents.py run AGENT_ID "Follow-up" --session-id SESSION_ID --json
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
        description="Manage RAGFlow agents and their sessions.",
        parents=[global_parser],
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- list subcommand ---
    list_p = subparsers.add_parser("list", help="List agents", parents=[global_parser])
    list_p.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    list_p.add_argument("--page-size", type=int, default=30, dest="page_size", help="Page size (default: 30)")

    # --- info subcommand ---
    info_p = subparsers.add_parser("info", help="Show agent details", parents=[global_parser])
    info_p.add_argument("agent_id", help="Agent ID")

    # --- sessions subcommand ---
    sessions_p = subparsers.add_parser("sessions", help="Manage agent sessions", parents=[global_parser])
    sess_sub = sessions_p.add_subparsers(dest="sessions_command")

    sess_list = sess_sub.add_parser("list", help="List sessions", parents=[global_parser])
    sess_list.add_argument("agent_id", help="Agent ID")
    sess_list.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    sess_list.add_argument("--page-size", type=int, default=30, dest="page_size", help="Page size (default: 30)")

    sess_create = sess_sub.add_parser("create", help="Create a session", parents=[global_parser])
    sess_create.add_argument("agent_id", help="Agent ID")
    sess_create.add_argument("--name", default="New session", help="Session name")

    sess_delete = sess_sub.add_parser("delete", help="Delete sessions", parents=[global_parser])
    sess_delete.add_argument("agent_id", help="Agent ID")
    sess_delete.add_argument(
        "--ids",
        required=True,
        help="Comma-separated session IDs to delete",
    )

    # --- run subcommand ---
    run_p = subparsers.add_parser("run", help="Run agent (send a message)", parents=[global_parser])
    run_p.add_argument("agent_id", help="Agent ID")
    run_p.add_argument("question", help="Message text to send")
    run_p.add_argument(
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
# Agents
# ---------------------------------------------------------------------------

def _normalize_agent(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "title": item.get("title") or item.get("name"),
        "description": item.get("description"),
        "category": item.get("canvas_category"),
        "permission": item.get("permission"),
        "created_at": item.get("create_date") or item.get("created_at"),
    }


def list_agents(*, base_url: str, api_key: str,
                page: int = 1, page_size: int = 30) -> dict[str, Any]:
    import urllib.parse
    query = urllib.parse.urlencode({"page": page, "page_size": page_size})
    payload = ensure_success(
        request_json(f"{base_url}/api/v1/agents?{query}", api_key)
    )
    raw = payload.get("data")
    if not isinstance(raw, list):
        raise DataError("Agent list response missing data array.")
    agents = [_normalize_agent(item) for item in raw]
    return {
        "checked_at": current_timestamp(),
        "page": page,
        "page_size": page_size,
        "count": len(agents),
        "agents": agents,
    }


def agent_info(agent_id: str, *, base_url: str, api_key: str) -> dict[str, Any]:
    import urllib.parse
    query = urllib.parse.urlencode({"id": agent_id})
    payload = ensure_success(
        request_json(f"{base_url}/api/v1/agents?{query}", api_key)
    )
    raw = payload.get("data")
    if not isinstance(raw, list) or not raw:
        raise DataError(f"Agent not found: {agent_id}")
    return {
        "checked_at": current_timestamp(),
        "agent": _normalize_agent(raw[0]),
    }


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def _normalize_session(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "agent_id": item.get("agent_id"),
        "created_at": item.get("create_date") or item.get("created_at"),
        "round": item.get("round"),
    }


def list_sessions(agent_id: str, *, base_url: str, api_key: str,
                  page: int = 1, page_size: int = 30) -> dict[str, Any]:
    import urllib.parse
    query = urllib.parse.urlencode({"page": page, "page_size": page_size})
    payload = ensure_success(
        request_json(f"{base_url}/api/v1/agents/{agent_id}/sessions?{query}", api_key)
    )
    raw = payload.get("data")
    if not isinstance(raw, list):
        raise DataError("Session list response missing data array.")
    sessions = [_normalize_session(item) for item in raw]
    return {
        "checked_at": current_timestamp(),
        "agent_id": agent_id,
        "page": page,
        "page_size": page_size,
        "count": len(sessions),
        "sessions": sessions,
    }


def create_session(agent_id: str, name: str, *, base_url: str, api_key: str) -> dict[str, Any]:
    if not name.strip():
        raise ConfigError("Session name must not be empty.")
    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/agents/{agent_id}/sessions",
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
        "agent_id": agent_id,
        "session": _normalize_session(data),
    }


def delete_sessions(agent_id: str, raw_ids: str, *, base_url: str, api_key: str) -> dict[str, Any]:
    session_ids = _parse_ids(raw_ids, label="--ids")
    payload = ensure_success(
        request_json(
            f"{base_url}/api/v1/agents/{agent_id}/sessions",
            api_key,
            method="DELETE",
            body=json.dumps({"ids": session_ids}).encode("utf-8"),
            content_type="application/json",
        )
    )
    return {
        "deleted_at": current_timestamp(),
        "agent_id": agent_id,
        "session_ids": session_ids,
        "message": payload.get("message", ""),
    }


# ---------------------------------------------------------------------------
# Run (completions)
# ---------------------------------------------------------------------------

def run_agent(
    agent_id: str,
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
            f"{base_url}/api/v1/agents/{agent_id}/completions",
            api_key,
            method="POST",
            body=json.dumps(body).encode("utf-8"),
            content_type="application/json",
        )
    )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataError("Agent completion response missing data object.")

    answer = data.get("answer") or ""
    returned_session_id = data.get("session_id") or session_id or ""
    reference = data.get("reference") or {}
    chunks = reference.get("chunks") or []

    return {
        "ran_at": current_timestamp(),
        "agent_id": agent_id,
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

def _format_agents_list(payload: dict[str, Any]) -> str:
    lines = [
        f"Checked at: {payload['checked_at']}",
        f"Agents: {payload['count']}  (page {payload.get('page', 1)}, size {payload.get('page_size', 30)})",
    ]
    for agent in payload["agents"]:
        lines.extend([
            "",
            f"- {agent.get('title') or 'unknown'}",
            f"  id: {agent.get('id') or 'unknown'}",
            f"  category: {agent.get('category') or 'unknown'}",
            f"  created_at: {agent.get('created_at') or 'unknown'}",
        ])
        if agent.get("description"):
            lines.append(f"  description: {agent['description']}")
    return "\n".join(lines)


def _format_agent_info(payload: dict[str, Any]) -> str:
    agent = payload["agent"]
    lines = [
        f"Checked at: {payload['checked_at']}",
        f"Title: {agent.get('title') or 'unknown'}",
        f"ID: {agent.get('id') or 'unknown'}",
        f"Category: {agent.get('category') or 'unknown'}",
        f"Permission: {agent.get('permission') or 'unknown'}",
        f"Created at: {agent.get('created_at') or 'unknown'}",
    ]
    if agent.get("description"):
        lines.append(f"Description: {agent['description']}")
    return "\n".join(lines)


def _format_sessions_list(payload: dict[str, Any]) -> str:
    lines = [
        f"Checked at: {payload['checked_at']}",
        f"Agent: {payload['agent_id']}",
        f"Sessions: {payload['count']}  (page {payload.get('page', 1)}, size {payload.get('page_size', 30)})",
    ]
    for sess in payload["sessions"]:
        lines.extend([
            "",
            f"- {sess.get('name') or 'unknown'}",
            f"  id: {sess.get('id') or 'unknown'}",
            f"  created_at: {sess.get('created_at') or 'unknown'}",
        ])
        if sess.get("round") is not None:
            lines.append(f"  rounds: {sess['round']}")
    return "\n".join(lines)


def _format_session_create(payload: dict[str, Any]) -> str:
    sess = payload["session"]
    return "\n".join([
        f"Created at: {payload['created_at']}",
        f"Agent: {payload['agent_id']}",
        f"Name: {sess.get('name') or 'unknown'}",
        f"ID: {sess.get('id') or 'unknown'}",
    ])


def _format_session_delete(payload: dict[str, Any]) -> str:
    lines = [
        f"Deleted at: {payload['deleted_at']}",
        f"Agent: {payload['agent_id']}",
        f"Sessions: {', '.join(payload['session_ids'])}",
    ]
    msg = payload.get("message")
    if isinstance(msg, str) and msg.strip():
        lines.append(f"Message: {msg.strip()}")
    return "\n".join(lines)


def _format_run(payload: dict[str, Any]) -> str:
    lines = [
        f"Ran at: {payload['ran_at']}",
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
        if args.command == "list":
            payload = list_agents(
                base_url=base_url, api_key=api_key,
                page=getattr(args, "page", 1),
                page_size=getattr(args, "page_size", 30),
            )
            print(format_json(payload) if args.json_output else _format_agents_list(payload))
            return 0

        if args.command == "info":
            payload = agent_info(args.agent_id, base_url=base_url, api_key=api_key)
            print(format_json(payload) if args.json_output else _format_agent_info(payload))
            return 0

        if args.command == "sessions":
            sc = args.sessions_command
            if sc == "list":
                payload = list_sessions(
                    args.agent_id, base_url=base_url, api_key=api_key,
                    page=getattr(args, "page", 1),
                    page_size=getattr(args, "page_size", 30),
                )
                print(format_json(payload) if args.json_output else _format_sessions_list(payload))
                return 0
            if sc == "create":
                payload = create_session(args.agent_id, args.name, base_url=base_url, api_key=api_key)
                print(format_json(payload) if args.json_output else _format_session_create(payload))
                return 0
            if sc == "delete":
                payload = delete_sessions(args.agent_id, args.ids, base_url=base_url, api_key=api_key)
                print(format_json(payload) if args.json_output else _format_session_delete(payload))
                return 0
            return _err(f"Unknown sessions subcommand: {sc}")

        if args.command == "run":
            payload = run_agent(
                args.agent_id,
                args.question,
                session_id=getattr(args, "session_id", None),
                base_url=base_url,
                api_key=api_key,
            )
            print(format_json(payload) if args.json_output else _format_run(payload))
            return 0

        return _err("No command given. Use 'list', 'info', 'sessions', or 'run'.")

    except ScriptError as exc:
        return _err(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
