---
name: ragflow-dataset-ingest
description: "Use for RAGFlow dataset and retrieval tasks: create, list, inspect, update, or delete datasets; list, upload, update, or delete documents in a dataset; start or stop parsing uploaded documents; check parser status through `parse_status.py`; and retrieve relevant chunks from RAGFlow datasets with `search.py`."
---

# RAGFlow Dataset And Retrieval

Use only the bundled scripts in `scripts/`.
Prefer `--json` for script execution so the returned fields can be relayed exactly.

## Trigger Phrases

Use this skill when the user intent matches any of these actions, in either Chinese or English, even if the wording is informal.

- List datasets
  Trigger phrases:
  "list datasets", "show datasets", "show all datasets", "what datasets do I have"
  "列出数据集", "查看数据集", "显示所有数据集", "我有哪些数据集"

- Show dataset details
  Trigger phrases:
  "dataset details", "show dataset info", "inspect dataset", "describe this dataset"
  "数据集详情", "查看数据集信息", "检查数据集", "显示这个数据集的信息"

- Create dataset
  Trigger phrases:
  "create dataset", "new dataset", "add a dataset"
  "创建数据集", "新建数据集", "添加数据集"

- Update dataset
  Trigger phrases:
  "rename dataset", "update dataset", "change dataset description", "modify dataset"
  "重命名数据集", "更新数据集", "修改数据集描述", "编辑数据集"

- Delete dataset
  Trigger phrases:
  "delete dataset", "remove dataset", "drop dataset"
  "删除数据集", "移除数据集", "清理数据集"

- Upload documents
  Trigger phrases:
  "upload file", "upload document", "add file to dataset", "import files"
  "上传文件", "上传文档", "把文件加到数据集", "导入文件"

- List documents
  Trigger phrases:
  "list documents", "show files", "show documents in dataset", "what files are in this dataset"
  "列出文档", "列出文件", "查看数据集里的文件", "这个数据集里有哪些文件"

- Update document
  Trigger phrases:
  "rename document", "update document", "edit document metadata"
  "重命名文档", "更新文档", "修改文档元数据"

- Delete document
  Trigger phrases:
  "delete document", "remove file", "delete file from dataset"
  "删除文档", "删除文件", "从数据集删除文件"

- Start parsing
  Trigger phrases:
  "parse document", "start parsing", "run parsing", "re-parse document"
  "解析文档", "开始解析", "执行解析", "重新解析文档"

- Stop parsing
  Trigger phrases:
  "stop parsing", "cancel parsing", "stop parse job"
  "停止解析", "取消解析", "停止解析任务"

- Check parsing status or progress
  Trigger phrases:
  "check parsing status", "show progress", "what is still running", "parsing progress"
  "查看解析状态", "查看进度", "还有哪些在运行", "解析进度"

- Search / retrieve
  Trigger phrases:
  "search knowledge base", "search dataset", "retrieve chunks", "find relevant content"
  "搜索知识库", "搜索数据集", "检索内容", "查找相关内容"

- List models
  Trigger phrases:
  "list models", "show models", "available models", "what models are available", "list llms", "show llms", "model providers"
  "列出模型", "查看模型", "可用模型", "有哪些模型", "列出大模型", "查看大模型", "模型供应商"

- Show model details or provider grouping
  Trigger phrases:
  "model details", "show model details", "group models by provider", "list all models including unavailable ones"
  "模型详情", "查看模型详情", "按供应商查看模型", "列出所有模型包括不可用模型"

## Workflow

For one-off usage, pass `--base-url` and `--api-key-file`.
For repeated usage, run one command with `--save-to-memory` and let later commands reuse the memory file or prompt interactively when needed.

```bash
python scripts/datasets.py create "My Dataset" --description "Optional description" --base-url http://127.0.0.1:9380 --api-key-file /path/to/key.txt --save-to-memory
python scripts/datasets.py list
python scripts/datasets.py info DATASET_ID
python scripts/update_dataset.py DATASET_ID --name "Renamed Dataset"
```

1. Create a dataset or confirm the target dataset.
2. Upload files.

When asking the user to provide files, prefer explicit local file paths. If the user's client supports drag-and-drop, they may also drop files into the conversation, but local paths work best and large drag-and-drop uploads may fail.

```bash
python scripts/upload.py list DATASET_ID --json
python scripts/upload.py DATASET_ID /path/to/file1 [/path/to/file2 ...]
python scripts/update_document.py DATASET_ID DOC_ID --name "Renamed Document"
```

Upload output returns `document_ids`. Pass those IDs into the next step.

Use delete commands when the task is cleanup instead of ingest:

```bash
python scripts/datasets.py delete --ids DATASET_ID1,DATASET_ID2
python scripts/upload.py delete DATASET_ID --ids DOC_ID1,DOC_ID2
```

⚠️ **DELETION REQUIRES CONFIRMATION**: Before executing any delete operation (datasets or documents):
1. List items to be deleted with details (names, IDs, counts)
2. Ask user for explicit confirmation (e.g., "yes", "confirm", "proceed")
3. Only proceed after user confirms

For dataset deletion, execute only against explicit dataset IDs. For document deletion, execute only against explicit document IDs. If the user gives filenames or a fuzzy description, list documents first, resolve exact IDs, get confirmation, and only then run the delete command. Do not perform fuzzy batch delete operations.

3. Start parsing, or stop parsing when explicitly requested.

```bash
python scripts/parse.py DATASET_ID DOC_ID1 [DOC_ID2 ...]
python scripts/stop_parse_documents.py DATASET_ID DOC_ID1 [DOC_ID2 ...]
python scripts/parse_status.py DATASET_ID
```

`parse.py` only sends the parse request and returns immediately.

`stop_parse_documents.py` sends a stop request for explicit document IDs, then returns one current status snapshot for those documents.

Use `parse_status.py` when the user asks to check progress or current parser status.
If `parse_status.py` returns an error, return the error message directly and do not guess the cause.
If a document status includes `progress_msg`, surface it automatically. For `FAIL` documents, treat `progress_msg` as the primary error detail.

For later requests like "Check the progress" or "Which files are currently being parsed", resolve scope by specificity:
- no dataset specified: inspect all datasets and all documents
- dataset specified: inspect all documents in that dataset
- document IDs specified: inspect only those documents

4. Retrieve chunks from one or more datasets when the user asks knowledge questions against RAGFlow.

```bash
python scripts/search.py "What does the warranty policy say?"
python scripts/search.py "What does the warranty policy say?" DATASET_ID
python scripts/search.py --dataset-ids DATASET_ID1,DATASET_ID2 --doc-ids DOC_ID1,DOC_ID2 "What does the warranty policy say?"
python scripts/search.py --threshold 0.7 --top-k 10 "query"
python scripts/search.py --retrieval-test --kb-id DATASET_ID "query"
```

5. Inspect configured LLM factories and models when the user asks what models are available.

```bash
python scripts/list_models.py --json
python scripts/list_models.py --include-details --json
python scripts/list_models.py --group-by factory --json
python scripts/list_models.py --all --group-by factory --include-details --json
```

## Model Listing

- default to listing only available models
- default to grouping by model `type`
- if multiple model groups or models are shown, prefer a table
- if the user asks for details, provider grouping, or unavailable models, expand the output accordingly
- prefer the grouped result in `groups` instead of reintroducing the raw server response shape

## Progress And Status Output

- summarize `RUNNING` items first when reporting progress
- status reporting should reflect the dataset document list API as-is; do not fabricate percentage progress

## Error Output

- when returning raw script output, preserve error fields exactly as returned
- if JSON output contains `api_error`, present that object directly rather than replacing it with a guessed explanation


## Scope

Support only:
- create datasets
- list datasets
- inspect datasets
- update datasets
- delete datasets
- upload documents to a dataset
- list documents in a dataset
- update documents in a dataset
- delete documents from a dataset
- start parsing documents in a dataset
- stop parsing documents in a dataset
- list all currently parsing documents in a dataset for broad progress requests
- aggregate parse progress across all datasets for broad progress requests
- retrieve relevant chunks from one or more datasets
- limit retrieval to specific dataset IDs or document IDs
- use `retrieval_test` for single-dataset debugging when needed
- list configured LLM factories and models through the web API

Do not use this skill for chunk editing, memory APIs, or other RAGFlow capabilities outside dataset operations and retrieval.

## Runtime Credentials

Do not use `.env` or shell environment variables for this skill.

Pass `--base-url` explicitly when needed. For the API key, prefer `--api-key-file /path/to/key.txt`, or let the script prompt securely.

All scripts also support `--memory-file` and `--save-to-memory`. The default memory file is `~/.codex/memories/ragflow_credentials.json`.

Example memory file:

```json
{
  "base_url": "http://127.0.0.1:9380",
  "api_key": "ragflow-your-api-key-here",
  "dataset_ids": ["dataset-id-1", "dataset-id-2"]
}
```

`base_url` must point to a trusted RAGFlow server because upload and update operations send document bytes and document metadata to that base URL over the API.

`api_key` should be a minimally scoped bearer token for that server. Do not reuse a broader admin credential unless that access level is actually required for the task.

Do not pass the raw API key directly on the command line because shell history and process listings may expose it.

## Endpoints
- `GET /api/v1/datasets`
- `POST /api/v1/datasets`
- `PUT /api/v1/datasets/<dataset_id>`
- `DELETE /api/v1/datasets`
- `GET /api/v1/datasets/<dataset_id>/documents`
- `POST /api/v1/datasets/<dataset_id>/documents`
- `PUT /api/v1/datasets/<dataset_id>/documents/<document_id>`
- `DELETE /api/v1/datasets/<dataset_id>/documents`
- `POST /api/v1/datasets/<dataset_id>/chunks`
- `DELETE /api/v1/datasets/<dataset_id>/chunks`
- `POST /api/v1/retrieval`
- `POST /api/v1/chunk/retrieval_test`
- `GET /v1/llm/my_llms`

## Commands

```bash
python scripts/datasets.py list --base-url http://127.0.0.1:9380 --api-key-file /path/to/key.txt
python scripts/datasets.py create "Example Dataset" --description "Quarterly reports" --save-to-memory
python scripts/datasets.py create "Example Dataset" --embedding-model bge-m3 --chunk-method naive --permission me
python scripts/datasets.py info DATASET_ID
python scripts/update_dataset.py DATASET_ID --name "Updated Dataset" --description "Updated description"
python scripts/datasets.py delete --ids DATASET_ID1,DATASET_ID2 --json
python scripts/upload.py list DATASET_ID --json
python scripts/upload.py DATASET_ID ./example.pdf --json
python scripts/update_document.py DATASET_ID DOC_ID --name "Updated Document" --enabled 1 --json
python scripts/upload.py delete DATASET_ID --ids DOC_ID1,DOC_ID2 --json
python scripts/datasets.py list --json
python scripts/parse.py DATASET_ID DOC_ID1 --json
python scripts/stop_parse_documents.py DATASET_ID DOC_ID1 --json
python scripts/parse_status.py DATASET_ID --json
python scripts/search.py "query"
python scripts/search.py "query" DATASET_ID --json
python scripts/search.py --dataset-ids DATASET_ID1,DATASET_ID2 --doc-ids DOC_ID1,DOC_ID2 "query" --json
python scripts/search.py --retrieval-test --kb-id DATASET_ID "query" --json
python scripts/list_models.py --json
python scripts/list_models.py --include-details --json
```

Once credentials are saved to the memory file, the later examples can omit `--base-url` and `--api-key-file`. If no memory value exists, the scripts will prompt for the missing value interactively.

## Notes

- Dataset creation supports `--avatar`, `--description`, `--embedding-model`, `--permission`, `--chunk-method`, and `--language`.
- Dataset update supports explicit flags or `--data` JSON payloads through `scripts/update_dataset.py`.
- Upload does not start parsing by itself.
- Prefer local file paths for uploads. Drag-and-drop is acceptable only when the client's UI supports it, and it may fail for large files.
- Document update supports explicit flags or `--data` JSON payloads through `scripts/update_document.py`.
- Parsing is asynchronous.
- `parse.py` returns immediately after the start request. Do not wait for parse status in this command.
- When a script returns an error, proactively include the error message in the same reply. Do not wait for the user to ask for the error details.
- If JSON output contains `api_error`, return that API error object directly instead of replacing it with a guessed explanation.
- If JSON output contains `error`, `api_error.message`, `status_error.message`, or `error_detail.message`, surface that message to the user immediately.
- A stop request may not flip the document to `CANCEL` immediately. Use the returned snapshot or `scripts/parse_status.py` to confirm the terminal state.
- For broad status/progress requests with no dataset specified, list datasets first and aggregate `scripts/parse_status.py DATASET_ID` across all datasets.
- If a dataset is specified, prefer `scripts/parse_status.py DATASET_ID` without `--doc-ids`.
- If document IDs are specified, pass `--doc-ids`.
- Retrieval defaults to `POST /api/v1/retrieval`.
- `scripts/search.py` accepts `dataset_ids` from the memory file as the default dataset scope when the user does not specify dataset IDs explicitly.
- Use `--retrieval-test` only when the user wants single-dataset debugging or specifically asks for that endpoint.
- `scripts/list_models.py` calls `GET /v1/llm/my_llms` and uses the resolved bearer API key from `--api-key-file`, the memory file, or a secure prompt.
