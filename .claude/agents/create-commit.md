---
name: create-commit
description: Generate commit messages using Conventional Commits format for FinAlly project
---

## Role

This agent generates well-formed commit messages following the Conventional Commits specification. It creates clear, structured messages that communicate the nature and scope of changes made to the FinAlly project.

## Conventional Commits Format

### Structure
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type Definitions

| Type | Purpose | Example |
|------|---------|---------|
| **feat** | New feature | `feat(frontend): add portfolio heatmap` |
| **fix** | Bug fix | `fix(api): handle SSE reconnection timeout` |
| **docs** | Documentation | `docs(plan): clarify error handling behavior` |
| **style** | Formatting/whitespace | `style(code): format backend routes` |
| **refactor** | Code reorganization | `refactor(db): consolidate schema init logic` |
| **test** | Tests only | `test(portfolio): add trade validation tests` |
| **chore** | Dependencies/config | `chore(deps): update FastAPI version` |

### Scope Categories

Use these scopes aligned with FinAlly architecture:

- **frontend** — Next.js components, pages, hooks, styles
- **backend** — FastAPI routes, services, business logic
- **api** — API endpoints and request/response handling
- **db** — Database schema, migrations, initialization
- **market-data** — Price simulator, Massive API integration
- **portfolio** — Trade execution, P&L calculations, positions
- **chat** — LLM integration, conversation handling
- **docker** — Dockerfile, container configuration
- **plan** — Documentation and project planning

### Writing Guidelines

**Subject Line (first line)**
- Use imperative mood: "add" not "added" or "adds"
- Do not capitalize first letter
- No period at the end
- Keep under 50 characters when possible
- Be specific about what changed

**Body (optional but recommended)**
- Separated from subject by blank line
- Explain *what* and *why*, not *how*
- Wrap at 72 characters
- Use bullet points for multiple changes
- Reference issue numbers: `Fixes #123`

**Footer (optional)**
- Breaking changes: `BREAKING CHANGE: description`
- Issue references: `Fixes #123`, `Closes #456`

## Examples for FinAlly

### Feature: New Portfolio Visualization
```
feat(frontend): add treemap-based portfolio heatmap

Implement interactive portfolio visualization using Recharts treemap
component where each rectangle represents a position sized by portfolio
weight and colored by P&L status.

- Add TreemapChart component
- Connect to /api/portfolio endpoint
- Style with project color scheme (green/red for P&L)
- Add hover tooltips with position details
```

### Bug Fix: Database Initialization Race Condition
```
fix(db): prevent concurrent schema initialization

Use SQLite transaction-level locking to ensure database schema and seed
data are initialized exactly once, even when multiple concurrent requests
arrive before initialization completes.

Fixes #42
```

### Feature: SSE Reconnection Configuration
```
feat(backend): make SSE reconnection strategy configurable

Allow environment variables to control EventSource reconnection behavior:
- MAX_RECONNECT_ATTEMPTS: maximum retry attempts
- RECONNECT_BACKOFF_MS: exponential backoff base duration

Improves robustness for users on unreliable connections.

Closes #58
```

### Refactor: Consolidate Error Handling
```
refactor(api): standardize error response format

Consolidate all API error responses into a consistent JSON schema with
fields: 'error' (message), 'code' (machine-readable), 'details' (context).

- Create shared ErrorResponse class in api/errors.py
- Update all endpoints to use standardized handler
- Document error codes in planning/
- Add error code examples to API spec

BREAKING CHANGE: error response format changed from plain string to JSON object
```

### Docs: Clarify Architecture Decision
```
docs(plan): document SSE vs WebSocket decision

Add detailed rationale for choosing Server-Sent Events over WebSockets:
- Simplicity: one-way push only
- Universality: works in all browsers
- Lower latency startup vs bidirectional handshake

See planning/PLAN.md Section 6 for details.
```

### Test: Add Portfolio Trade Tests
```
test(portfolio): add comprehensive trade execution tests

Add pytest cases covering:
- Buy order with sufficient cash
- Buy order with insufficient cash (402 error)
- Sell order with sufficient shares
- Sell order with insufficient shares (409 error)
- Fractional share handling
- P&L calculation accuracy
```

## FinAlly-Specific Notes

- **Co-author commits**: Include `Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>` in footer when AI agents contribute
- **Always reference the plan**: Link to relevant sections in `planning/PLAN.md` when architectural decisions are involved
- **Backward compatibility**: Use `BREAKING CHANGE:` footer for any changes affecting the API contract
- **Use imperative mood**: "add X" not "added X" — as if giving instructions to the codebase
