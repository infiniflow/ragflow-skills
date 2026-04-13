---
name: ragflow-dataset-ingest
description: "Use for RAGFlow dataset tasks: create, list, inspect, update, or delete datasets; upload, list, update, or delete documents; start or stop parsing; check parse status; retrieve chunks with `search.py`; list configured models; manage chat assistants; send chat messages; manage sessions; manage agents (智能体) and run agent completions; test connectivity."
user-invocable: true
metadata:
  openclaw:
    requires:
      env:
        - RAGFLOW_API_URL
        - RAGFLOW_API_KEY
      bins:
        - python3
    primaryEnv: RAGFLOW_API_KEY
---

# RAGFlow Dataset, Retrieval and Chat

Use only the bundled scripts in `scripts/`.
Prefer `--json` so returned fields can be relayed exactly.
Follow `reference.md` for all user-facing output.

## Use This Skill When

- the user wants to create, list, inspect, update, or delete RAGFlow datasets
- the user wants to upload, list, update, or delete documents in a dataset
- the user wants to start parsing, stop parsing, or check parse progress
- the user wants to retrieve chunks from one or more datasets
- the user wants to list configured RAGFlow models
- the user wants to create, list, or delete chat assistants
- the user wants to send a chat message or manage conversation sessions
- the user wants to list, inspect, or run RAGFlow agents (智能体) or manage agent sessions
- the user wants to test connectivity or diagnose configuration problems

## Core Workflow

1. Resolve the target dataset, document, or assistant IDs first.
2. Run the matching script from `scripts/`.
3. Use `--json` unless a script only needs a simple text response.
4. Return API fields exactly; do not guess missing details.

### Dataset & Document Commands

```bash
python3 scripts/datasets.py list --json
python3 scripts/datasets.py info DATASET_ID --json
python3 scripts/datasets.py create "Example Dataset" --description "Quarterly reports" --json
python3 scripts/datasets.py delete --ids ID1,ID2 --json
python3 scripts/update_dataset.py DATASET_ID --name "Updated Dataset" --json
python3 scripts/upload.py DATASET_ID /path/to/file.pdf --json
python3 scripts/upload.py list DATASET_ID --json
python3 scripts/upload.py delete DATASET_ID --ids DOC_ID1,DOC_ID2 --json
python3 scripts/update_document.py DATASET_ID DOC_ID --name "Updated Document" --json
python3 scripts/parse.py DATASET_ID DOC_ID1 [DOC_ID2 ...] --json
python3 scripts/stop_parse_documents.py DATASET_ID DOC_ID1 [DOC_ID2 ...] --json
python3 scripts/parse_status.py DATASET_ID --json
python3 scripts/list_documents.py DATASET_ID --json
```

### Chunk Management Commands

```bash
python3 scripts/chunks.py list   DATASET_ID DOCUMENT_ID --json
python3 scripts/chunks.py list   DATASET_ID DOCUMENT_ID --page 2 --page-size 20 --json
python3 scripts/chunks.py create DATASET_ID DOCUMENT_ID --content "chunk text" --json
python3 scripts/chunks.py update DATASET_ID DOCUMENT_ID CHUNK_ID --content "new text" --json
python3 scripts/chunks.py update DATASET_ID DOCUMENT_ID CHUNK_ID --available 0 --json
python3 scripts/chunks.py delete DATASET_ID DOCUMENT_ID --ids CID1,CID2 --json
python3 scripts/chunks.py switch DATASET_ID DOCUMENT_ID --ids CID1,CID2 --available 1 --json
```

### Retrieval & Models Commands

```bash
python3 scripts/search.py "query" --json
python3 scripts/search.py "query" DATASET_ID --json
python3 scripts/search.py --dataset-ids DATASET_ID1,DATASET_ID2 --doc-ids DOC_ID1,DOC_ID2 "query" --json
python3 scripts/search.py --retrieval-test --kb-id DATASET_ID "query" --json
python3 scripts/list_models.py --json
```

### Chat Assistant Commands

```bash
python3 scripts/chat_assistants.py list --json
python3 scripts/chat_assistants.py info ASSISTANT_ID --json
python3 scripts/chat_assistants.py create "Assistant Name" --dataset-ids ID1,ID2 --json
python3 scripts/chat_assistants.py create "Assistant Name" --dataset-ids ID1 --llm-id MODEL_ID --json
python3 scripts/chat_assistants.py delete --ids ID1,ID2 --json
```

### Chat Message & Session Commands

```bash
# Send a message (creates a new session automatically)
python3 scripts/chat.py message ASSISTANT_ID "Your question" --json

# Multi-turn conversation (reuse existing session)
python3 scripts/chat.py message ASSISTANT_ID "Follow-up question" --session-id SESSION_ID --json

# Session management
python3 scripts/chat.py sessions list ASSISTANT_ID --json
python3 scripts/chat.py sessions create ASSISTANT_ID --name "My Session" --json
python3 scripts/chat.py sessions delete ASSISTANT_ID --ids SID1,SID2 --json
```

### Agent Commands

Agents are workflow-based (canvas) AI assistants, distinct from chat assistants. They support complex multi-step reasoning, tool use, and branching logic.

```bash
# List all agents
python3 scripts/agents.py list --json
python3 scripts/agents.py list --page 2 --page-size 10 --json

# Show agent details
python3 scripts/agents.py info AGENT_ID --json

# Run an agent (creates a new session automatically)
python3 scripts/agents.py run AGENT_ID "Your question" --json

# Multi-turn agent conversation (reuse existing session)
python3 scripts/agents.py run AGENT_ID "Follow-up question" --session-id SESSION_ID --json

# Agent session management
python3 scripts/agents.py sessions list AGENT_ID --json
python3 scripts/agents.py sessions create AGENT_ID --name "My Session" --json
python3 scripts/agents.py sessions delete AGENT_ID --ids SID1,SID2 --json
```

### Diagnostics Commands

```bash
# Quick connectivity check
python3 scripts/diagnose.py --test --json

# Full diagnostic report (env vars, connection details, troubleshooting hints)
python3 scripts/diagnose.py --diagnose --json
```

## Guardrails

- For any delete action, list the exact items first and require explicit user confirmation before executing.
- Delete only by explicit IDs. If the user gives names or fuzzy descriptions, resolve IDs first.
- Upload does not start parsing. Start parsing only when the user asks for it.
- `parse.py` returns immediately after the start request; use `parse_status.py` for progress.
- For progress requests, use `parse_status.py` on the most specific scope available:
  - dataset specified: inspect that dataset
  - document IDs specified: pass `--doc-ids`
  - no dataset specified: list datasets first, then aggregate status across datasets
- If a parse status result includes `progress_msg`, surface it directly. For `FAIL`, treat it as the primary error detail.
- Use `--retrieval-test` only for single-dataset debugging or when the user explicitly asks for that endpoint.
- Creating a chat assistant requires at least one `--dataset-ids`. Confirm dataset IDs before creating.
- `chat.py message` without `--session-id` starts a fresh session. Use `--session-id` to continue a conversation.
- When diagnosing connection issues, run `diagnose.py --diagnose` first before asking the user to check config manually.
- For chunk delete, list chunks first and show IDs before executing. Chunk deletion is irreversible.
- `chunks.py switch` enables/disables chunks for retrieval without deleting them; prefer this over delete when the user wants to temporarily hide content.
- Agents (`agents.py`) are canvas-based workflow agents, distinct from chat assistants (`chat_assistants.py`). Use `agents.py` when the user refers to "agent" or "智能体"; use `chat_assistants.py` for "chat assistant" or "助手".
- `agents.py run` without `--session-id` starts a fresh agent session. Use `--session-id` to continue a multi-turn agent conversation.
- Agent execution (`agents.py run`) may be slow — agents can perform multi-step reasoning and tool calls. Do not assume a delay indicates failure.
- Agent create/update/delete is not supported via script (requires complex DSL). Direct users to the RAGFlow UI for agent authoring.

## Output Rules

- Follow `reference.md`.
- Use tables for 3+ items when possible.
- Preserve `api_error`, `error`, `message`, and related fields exactly as returned.
- Never fabricate progress percentages or inferred causes.
- For chat answers, present the `answer` field verbatim and list references below if `reference_count > 0`.
