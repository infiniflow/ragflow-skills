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

