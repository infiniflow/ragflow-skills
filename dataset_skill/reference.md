# Output Format Reference

Style guide for consistent RAGFlow skill responses.
Apply this reference to all user-facing output for this skill.

## Format Decision Matrix

| Information Type | Format | Use Case |
|-----------------|--------|----------|
| Multiple items (3+) with attributes | **Table** | Datasets list, search results |
| Sequential steps | **Numbered List** | Upload workflow, procedures |
| Features/options | **Bullet List** | Capability overview |
| Structured data | **JSON Code Block** | API responses |
| Document content | **Quote Block** | Retrieved chunks |
| Single object properties | **Definition List** | Dataset details |
| Status | **Emoji + Text** | ✅ Done, 🟡 Running, ❌ Failed |

## Common Formats

### Tables (3+ items)
```markdown
| Dataset | Docs | Chunks | Status |
|---------|------|--------|--------|
| delete  | 4    | 53     | ✅     |
```
- Abbreviate long IDs: `abc123...`
- Use emojis for status: ✅ ❌ 🟡 ⚠️

### Bullet Lists
```markdown
- **Upload documents** to dataset
- **Start parsing** to generate chunks
```
- Start with verbs for actions
- Max 2 indent levels

### Numbered Lists
```markdown
1. Create dataset
2. Upload files
3. Start parsing
```
- Use for sequential procedures

### Status Icons
| Icon | Meaning |
|------|---------|
| ✅ | Success |
| ❌ | Failed |
| 🟡 | In Progress |
| ⚠️ | Warning |
| ⬜ | Empty |

## Response Templates

**List operations:**
```markdown
📋 **Datasets** (3 total)

| Name | ID | Status | Chunks |
|------|-----|--------|--------|
| test | abc... | ✅ | 152 |
```

**Search results:**
```markdown
🔍 **Results** (2 found)

| # | Source | Similarity | Content |
|---|--------|------------|---------|
| 1 | doc.pdf | 85% | excerpt... |
```

**Object details:**
```markdown
📊 **Dataset Details**

**ID:** `1ce917df20e411f191a984ba59bc54d9`
**Name:** delete
**Chunks:** 53
```

### Chat Assistants (3+ items)
```markdown
🤖 **Chat Assistants** (7 total)

| Name | ID | LLM | Datasets |
|------|----|-----|---------|
| QA知识库-测试 | 010a...1237 | qwen-max@... | kb-id-1 |
```

### Chat Assistant Details
```markdown
🤖 **Assistant Details**

**Name:** QA知识库-测试
**ID:** `010aff04347e11f1b93f033b90d81237`
**LLM:** qwen-max@Tongyi-Qianwen
**Datasets:** `bff4b898...`, `a1b2c3d4...`
**Created:** 2026-04-01T10:00:00
```

### Sessions (3+ items)
```markdown
💬 **Sessions** (5 total, page 1/2)

| Name | ID | Created |
|------|----|---------|
| My Session | sess-abc... | 2026-04-10 |
```

### Chat Answer
```markdown
💬 **Answer** (session: `sess-abc123`)

{answer verbatim}

📎 **References** (2)

| # | Document | Similarity | Excerpt |
|---|----------|------------|---------|
| 1 | doc.pdf | 87% | excerpt... |
```

