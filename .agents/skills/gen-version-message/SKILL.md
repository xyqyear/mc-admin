---
name: gen-version-message
description: Generate MC Admin version update entries for `frontend-react/src/config/versionConfig.ts` from recent git tags, commits, and issue numbers, then prepare the conventional `chore(version)` commit message. Use when Codex needs to summarize release changes for end users, collect missing issue numbers, update version metadata, or draft the version update commit.
---

# Generate Version Message Skill

Generate a version update message for `versionConfig.ts` and create a commit for the changes.

## Workflow

### Step 1: Gather Information

1. Read `frontend-react/src/config/versionConfig.ts` to understand the current version and structure
2. Get the latest tag and commits since then:

   ```bash
   git describe --tags --abbrev=0  # Get latest tag
   git log --oneline <latest_tag>..HEAD --no-merges
   ```

### Step 2: Parse and Collect Issue Numbers

1. Parse issue numbers from commit messages (format: `#XXX`)
2. Group commits by issue - commits working on the same issue should be identified together
3. For commits WITHOUT issue numbers, ask the user using AskUserQuestion:
   - Present each commit (or group of related commits) that lacks an issue number
   - If you can infer a likely issue number from context, include it as an option
   - Options should include: the inferred issue number (if any), "No issue", and allow custom input
   - Ask for one issue at a time, grouping related commits together

### Step 2.5: Handle Missing Issues (if applicable)

If the user indicates that an issue doesn't exist yet and needs to be created:

1. **Complete all questions first** - Continue asking about all remaining commits
2. **Summarize commits needing new issues** - List all commits where the user said "Create new issue"
3. **STOP and wait** - Tell the user to create the necessary issues on GitHub and provide the new issue numbers
4. **Resume after user provides issue numbers** - Once the user provides the new issue numbers, map them to the corresponding commits and continue to Step 3

### Step 3: Generate Version Update Message

Follow this style guide for the version update message:

**Structure:**

```typescript
{
  version: 'X.X.X',           // Semantic version
  date: 'YYYY-MM-DD',         // Today's date
  title: '简短标题',           // Concise Chinese title (5-15 chars)
  description: '一句话描述',   // One-sentence Chinese description
  features?: string[],        // New features (optional)
  fixes?: string[],           // Bug fixes (optional)
  improvements?: string[]     // Improvements (optional)
}
```

**Style Guidelines:**

- **Language**: Chinese for user-facing text (title, description, features, fixes, improvements)
- **Title**: Concise, describes the main theme (e.g., "控制台系统重构", "文件上传权限修复")
- **Description**: One sentence explaining the update's value to users
- **Versioning**:
  - Any release that changes the database schema or Alembic migrations must be a major version.
  - Otherwise choose semantic versioning by user-visible impact: feature release = minor, patch-only release = patch.
- **Features/Fixes/Improvements**:
  - Each item is a concise sentence
  - Include issue reference at the end: `#XXX`
  - Focus on user impact, not implementation details
  - Group related changes into single items when appropriate
  - NOT a one-to-one mapping of commits - synthesize into user-friendly descriptions
  - Count only net changes compared with the previous released version.
  - Do not list fixes or improvements that only stabilize a newly introduced feature before release; fold them into the feature description or omit them.
  - List `fixes` only for regressions/bugs that existed in the previous released version.
  - List `improvements` only for existing behavior that is better than the previous released version.

**Examples from existing entries:**

```typescript
{
  version: '1.4.0',
  date: '2026-01-25',
  title: '控制台系统重构',
  description: '控制台后端架构重构，使用 Docker 原生 API 实现更可靠的日志流式传输，并新增终端命令历史导航功能。',
  features: [
    '终端支持上下箭头键选择历史指令 #101'
  ],
  improvements: [
    '使用 docker-py attach socket 替代基于文件的日志读取和基于mc-send-to-console的指令发送',
  ],
  fixes: [
    '修复控制台日志重复显示的问题 #80'
  ]
}
```

### Step 4: User Approval

1. Present the generated version update entry to the user
2. Ask for approval using AskUserQuestion with options:
   - "Approve and write"
   - "Edit first" (user provides modifications)
3. If approved, use the Edit tool to add the new entry to `versionConfig.ts`
   - Add the new entry at the END of the `versionUpdates` array (before the closing `]`)

### Step 5: Suggest A Commit Message

**Commit Message Style:**

```text
chore(version): update description for version vX.X.X
```

- Use `chore(version)` scope
- Format: `update description for version vX.X.X`
- No body needed for simple version updates
- Use the exact version number with `v` prefix

## Important Notes

- The version update message is for END USERS, not developers
- Synthesize multiple related commits into single, user-friendly descriptions
- One issue may span multiple commits - only mention the issue once in the update
- Always include issue numbers where available for traceability
- If a commit is purely internal (refactoring with no user impact), it may be omitted or grouped under "improvements"
