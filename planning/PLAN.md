# FinAlly — AI Trading Workstation

## Table of Contents

1. [Vision](#1-vision)
2. [User Experience](#2-user-experience)
3. [Architecture Overview](#3-architecture-overview)
4. [Directory Structure](#4-directory-structure)
5. [Environment Variables](#5-environment-variables)
6. [Market Data](#6-market-data)
7. [Database](#7-database)
8. [API Endpoints](#8-api-endpoints)
9. [LLM Integration](#9-llm-integration)
10. [Frontend Design](#10-frontend-design)
11. [Docker & Deployment](#11-docker--deployment)
12. [Testing Strategy](#12-testing-strategy)

---

## Project Specification

## 1. Vision

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a single Docker command (or a provided start script). A browser opens to `http://localhost:8000`. No login, no signup. They immediately see:

- A watchlist of 10 default tickers with live-updating prices in a grid
- $10,000 in virtual cash
- A dark, data-rich trading terminal aesthetic
- An AI chat panel ready to assist

### What the User Can Do

- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, accumulated on the frontend from the SSE stream since page load (sparklines fill in progressively)
- **Click a ticker** to see a larger detailed chart in the main chart area
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog
- **Monitor their portfolio** — a heatmap (treemap) showing positions sized by weight and colored by P&L, plus a P&L chart tracking total portfolio value over time
- **View a positions table** — ticker, quantity, average cost, current price, unrealized P&L, % change
- **Chat with the AI assistant** — ask about their portfolio, get analysis, and have the AI execute trades and manage the watchlist through natural language
- **Manage the watchlist** — add/remove tickers manually or via the AI chat

### Visual Design

- **Dark theme**: backgrounds around `#0d1117` or `#1a1a2e`, muted gray borders, no pure black
- **Price flash animations**: brief green/red background highlight on price change, fading over ~500ms via CSS transitions
- **Connection status indicator**: a small colored dot (green = connected, yellow = reconnecting, red = disconnected) visible in the header
- **Professional, data-dense layout**: inspired by Bloomberg/trading terminals — every pixel earns its place
- **Responsive but desktop-first**: optimized for wide screens, functional on tablet

### Color Scheme

- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)

## 3. Architecture Overview

### Single Container, Single Port

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving         │
│                      (Next.js export)            │
│                                                 │
│  SQLite database (volume-mounted)               │
│  Background task: market data polling/sim        │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend**: FastAPI (Python), managed as a `uv` project
- **Database**: SQLite, single file at `db/finally.db`, volume-mounted for persistence
- **Real-time data**: Server-Sent Events (SSE) — simpler than WebSockets, one-way server→client push, works everywhere
- **AI integration**: LiteLLM → OpenRouter (Cerebras for fast inference), with structured outputs for trade execution
- **Market data**: Environment-variable driven — simulator by default, real data via Massive API if key provided

### Why These Choices

| Decision                | Rationale                                                                                     |
| ----------------------- | --------------------------------------------------------------------------------------------- |
| SSE over WebSockets     | One-way push is all we need; simpler, no bidirectional complexity, universal browser support  |
| Static Next.js export   | Single origin, no CORS issues, one port, one container, simple deployment                     |
| SQLite over Postgres    | No auth = no multi-user = no need for a database server; self-contained, zero config          |
| Single Docker container | Students run one command; no docker-compose for production, no service orchestration          |
| uv for Python           | Fast, modern Python project management; reproducible lockfile; what students should learn     |
| Market orders only      | Eliminates order book, limit order logic, partial fills — dramatically simpler portfolio math |

---

## 4. Directory Structure

```
finally/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python)
│   └── db/                   # Schema definitions, seed data, migration logic
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── scripts/
│   ├── start_mac.sh          # Launch Docker container (macOS/Linux)
│   ├── stop_mac.sh           # Stop Docker container (macOS/Linux)
│   ├── start_windows.ps1     # Launch Docker container (Windows PowerShell)
│   └── stop_windows.ps1      # Stop Docker container (Windows PowerShell)
├── test/                     # Playwright E2E tests + docker-compose.test.yml
├── db/                       # Volume mount target (SQLite file lives here at runtime)
│   └── .gitkeep              # Directory exists in repo; finally.db is gitignored
├── Dockerfile                # Multi-stage build (Node → Python)
├── docker-compose.yml        # Optional convenience wrapper
├── .env                      # Environment variables (gitignored, .env.example committed)
└── .gitignore
```

### Key Boundaries

- **`frontend/`** — Self-contained Next.js project; talks to backend via `/api/*` and `/api/stream/*`. Internal structure up to Frontend Engineer agent.
- **`backend/`** — Self-contained uv project; owns all server logic (routes, SSE, market data, LLM, database). Internal structure up to Backend/Market Data agents.
- **`backend/db/`** — Schema SQL and seed logic. Backend lazily initializes on first request.
- **`db/`** — Runtime volume mount point. SQLite file (`finally.db`) persists across restarts.
- **`planning/`** — Project-wide documentation; the shared contract for all agents.
- **`test/`** — Playwright E2E tests and `docker-compose.test.yml`. Unit tests live in `frontend/` and `backend/`.
- **`scripts/`** — Start/stop scripts wrapping Docker commands.

---

## 5. Environment Variables

```bash
# Required: OpenRouter API key for LLM chat functionality
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Optional: Massive (Polygon.io) API key for real market data
# If not set, the built-in market simulator is used (recommended for most users)
MASSIVE_API_KEY=

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false
```

### Behavior

- If `MASSIVE_API_KEY` is set and non-empty → backend uses Massive REST API for market data
- If `MASSIVE_API_KEY` is absent or empty → backend uses the built-in market simulator
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (for E2E tests)
- The backend reads `.env` from the project root (mounted into the container or read via docker `--env-file`)

---

## 6. Market Data

### Two Implementations, One Interface

Both the simulator and the Massive client implement the same abstract interface. The backend selects which to use based on the environment variable. All downstream code (SSE streaming, price cache, frontend) is agnostic to the source.

### Simulator (Default)

- Generates prices using geometric Brownian motion (GBM) with configurable drift and volatility per ticker
- Updates at ~500ms intervals
- Correlated moves across tickers (e.g., tech stocks move together)
- Occasional random "events" — sudden 2-5% moves on a ticker for drama
- Starts from realistic seed prices (e.g., AAPL ~$190, GOOGL ~$175, etc.)
- Runs as an in-process background task — no external dependencies

### Massive API (Optional)

- REST API polling (not WebSocket) — simpler, works on all tiers
- Polls for the union of all watched tickers on a configurable interval (tier-dependent via env var)
- Parses REST response into the same format as the simulator

### Shared Price Cache

- A single background task (simulator or Massive poller) writes to an in-memory price cache
- The cache holds the latest price, previous price, and timestamp for each ticker
- SSE streams read from this cache and push updates to connected clients
- This architecture supports future multi-user scenarios without changes to the data layer

### SSE Streaming

- Endpoint: `GET /api/stream/prices`
- Long-lived SSE connection; client uses native `EventSource` API
- Server pushes price updates for all tickers known to the system at a regular cadence (~500ms) — in the single-user model this is equivalent to the user's watchlist
- Each SSE event contains ticker, price, previous price, timestamp, and change direction
- Client handles reconnection automatically (EventSource has built-in retry)

---

## 7. Database

### SQLite with Lazy Initialization

The backend checks for the SQLite database on startup (or first request). If the file doesn't exist or tables are missing, it creates the schema and seeds default data. This means:

- No separate migration step
- No manual database setup
- Fresh Docker volumes start with a clean, seeded database automatically

### Schema

**Note:** All tables include a `user_id` column defaulting to `"default"` for future multi-user support without migration. Currently hardcoded to single-user mode.

**users_profile** — User state (cash balance)

- `id` TEXT PRIMARY KEY (`"default"`)
- `cash_balance` REAL (default: `10000.0`)
- `created_at` TEXT (ISO timestamp)
- `user_id` TEXT

**watchlist** — Tickers the user is watching

- `id` TEXT PRIMARY KEY (UUID)
- `ticker` TEXT
- `added_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**positions** — Current holdings (one row per ticker per user)

- `id` TEXT PRIMARY KEY (UUID)
- `ticker` TEXT
- `quantity` REAL (fractional shares supported)
- `avg_cost` REAL
- `updated_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**trades** — Trade history (append-only log)

- `id` TEXT PRIMARY KEY (UUID)
- `ticker` TEXT
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional shares supported)
- `price` REAL
- `executed_at` TEXT (ISO timestamp)

**portfolio_snapshots** — Portfolio value over time (for P&L chart). Recorded every 30 seconds by a background task, and immediately after each trade execution.

- `id` TEXT PRIMARY KEY (UUID)
- `total_value` REAL
- `recorded_at` TEXT (ISO timestamp)

**chat_messages** — Conversation history with LLM

- `id` TEXT PRIMARY KEY (UUID)
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT
- `actions` TEXT (JSON — trades executed, watchlist changes made; null for user messages)
- `created_at` TEXT (ISO timestamp)

### Default Seed Data

- One user profile: `id="default"`, `cash_balance=10000.0`
- Ten watchlist entries: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX

---

## 8. API Endpoints

### Market Data

| Method | Path                 | Description                                                                     |
| ------ | -------------------- | ------------------------------------------------------------------------------- |
| GET    | `/api/stream/prices` | SSE stream of live price updates (see [Section 6: Market Data](#6-market-data)) |

### Portfolio

| Method | Path                     | Description                                                  |
| ------ | ------------------------ | ------------------------------------------------------------ |
| GET    | `/api/portfolio`         | Current positions, cash balance, total value, unrealized P&L |
| POST   | `/api/portfolio/trade`   | Execute a trade: `{ticker, quantity, side}`                  |
| GET    | `/api/portfolio/history` | Portfolio value snapshots over time (for P&L chart)          |

### Watchlist

| Method | Path                      | Description                                  |
| ------ | ------------------------- | -------------------------------------------- |
| GET    | `/api/watchlist`          | Current watchlist tickers with latest prices |
| POST   | `/api/watchlist`          | Add a ticker: `{ticker}`                     |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker                              |

### Chat

| Method | Path        | Description                                                                                           |
| ------ | ----------- | ----------------------------------------------------------------------------------------------------- |
| POST   | `/api/chat` | Send a message, receive complete JSON response (see [Section 9: LLM Integration](#9-llm-integration)) |

### System

| Method | Path          | Description                          |
| ------ | ------------- | ------------------------------------ |
| GET    | `/api/health` | Health check (for Docker/deployment) |

### Error Response Format

All error responses return JSON with the following format:

```json
{
  "error": "Human-readable error message",
  "code": "ERROR_CODE",
  "details": { "key": "value" } // optional
}
```

**Common HTTP Status Codes**:

- `400 Bad Request` — Invalid input, malformed request
- `402 Payment Required` — Insufficient cash to buy
- `409 Conflict` — Insufficient shares to sell, ticker not found in watchlist
- `422 Unprocessable Entity` — Trade validation failed
- `500 Internal Server Error` — Server error

---

## 9. LLM Integration

When writing code to make calls to LLMs, use cerebras-inference skill to use LiteLLM via OpenRouter to the `openrouter/openai/gpt-oss-120b` model with Cerebras as the inference provider. Structured Outputs should be used to interpret the results.

There is an OPENROUTER_API_KEY in the .env file in the project root.

### How It Works

When the user sends a chat message, the backend:

1. Loads the user's current portfolio context (cash, positions with P&L, watchlist with live prices, total portfolio value)
2. Loads recent conversation history from the `chat_messages` table
3. Constructs a prompt with a system message, portfolio context, conversation history, and the user's new message
4. Calls the LLM via LiteLLM → OpenRouter, requesting structured output, using the cerebras-inference skill
5. Parses the complete structured JSON response
6. Auto-executes any trades or watchlist changes specified in the response
7. Stores the message and executed actions in `chat_messages`
8. Returns the complete JSON response to the frontend (no token-by-token streaming)

**LLM Response SLA**: Responses should complete in under 5 seconds 99% of the time for a smooth UX with a loading indicator.

### Structured Output Schema

The LLM is instructed to respond with JSON matching this schema:

```json
{
  "message": "Your conversational response to the user",
  "trades": [{ "ticker": "AAPL", "side": "buy", "quantity": 10 }],
  "watchlist_changes": [{ "ticker": "PYPL", "action": "add" }]
}
```

- `message` (required): The conversational text shown to the user
- `trades` (optional): Array of trades to auto-execute. Each trade goes through the same validation as manual trades (sufficient cash for buys, sufficient shares for sells)
- `watchlist_changes` (optional): Array of watchlist modifications

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:

- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

If a trade fails validation (e.g., insufficient cash), the error is included in the chat response so the LLM can inform the user.

### System Prompt Guidance

The LLM should be prompted as "FinAlly, an AI trading assistant" with instructions to:

- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Manage the watchlist proactively
- Be concise and data-driven in responses
- Always respond with valid structured JSON

### LLM Mock Mode

When `LLM_MOCK=true`, the backend returns deterministic mock responses instead of calling OpenRouter. This enables:

- Fast, free, reproducible E2E tests
- Development without an API key
- CI/CD pipelines

---

## 10. Frontend Design

### Layout

The frontend is a single-page application with a dense, terminal-inspired layout. The specific component architecture and layout system is up to the Frontend Engineer, but the UI should include these elements:

- **Watchlist panel** — grid/table of watched tickers with: ticker symbol, current price (flashing green/red on change), daily change %, and a sparkline mini-chart (accumulated from SSE since page load)
- **Main chart area** — larger chart for the currently selected ticker, with at minimum price over time. Clicking a ticker in the watchlist selects it here.
- **Portfolio heatmap** — treemap visualization where each rectangle is a position, sized by portfolio weight, colored by P&L (green = profit, red = loss)
- **P&L chart** — line chart showing total portfolio value over time, using data from `portfolio_snapshots`
- **Positions table** — tabular view of all positions: ticker, quantity, avg cost, current price, unrealized P&L, % change
- **Trade bar** — simple input area: ticker field, quantity field, buy button, sell button. Market orders, instant fill.
- **AI chat panel** — docked/collapsible sidebar. Message input, scrolling conversation history, loading indicator while waiting for LLM response. Trade executions and watchlist changes shown inline as confirmations.
- **Header** — portfolio total value (updating live), connection status indicator, cash balance

### Technical Notes

- Use `EventSource` for SSE connection to `/api/stream/prices`
- Canvas-based charting library preferred (Lightweight Charts or Recharts) for performance
- Price flash effect: on receiving a new price, briefly apply a CSS class with background color transition, then remove it
- All API calls go to the same origin (`/api/*`) — no CORS configuration needed
- Tailwind CSS for styling with a custom dark theme

---

## 11. Docker & Deployment

### Multi-Stage Dockerfile

```
Stage 1: Node 20 slim
  - Copy frontend/
  - npm install && npm run build (produces static export)

Stage 2: Python 3.12 slim
  - Install uv
  - Copy backend/
  - uv sync (install Python dependencies from lockfile)
  - Copy frontend build output into a static/ directory
  - Expose port 8000
  - CMD: uvicorn serving FastAPI app
```

FastAPI serves the static frontend files and all API routes on port 8000.

### Docker Volume

The SQLite database persists via a named Docker volume:

```bash
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

The `db/` directory in the project root maps to `/app/db` in the container. The backend writes `finally.db` to this path.

### Start/Stop Scripts

**`scripts/start_mac.sh`** (macOS/Linux):

- Builds the Docker image if not already built (or if `--build` flag passed)
- Runs the container with the volume mount, port mapping, and `.env` file
- Prints the URL to access the app
- Optionally opens the browser

**`scripts/stop_mac.sh`** (macOS/Linux):

- Stops and removes the running container
- Does NOT remove the volume (data persists)

**`scripts/start_windows.ps1`** / **`scripts/stop_windows.ps1`**: PowerShell equivalents for Windows.

All scripts should be idempotent — safe to run multiple times.

### Optional Cloud Deployment

The container is designed to deploy to AWS App Runner, Render, or any container platform. A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal, but is not part of the core build.

---

## 12. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:

- Market data: simulator generates valid prices, GBM math is correct, Massive API response parsing works, both implementations conform to the abstract interface
- Portfolio: trade execution logic, P&L calculations, edge cases (selling more than owned, buying with insufficient cash, selling at a loss)
- LLM: structured output parsing handles all valid schemas, graceful handling of malformed responses, trade validation within chat flow
- API routes: correct status codes, response shapes, error handling

**Frontend (React Testing Library or similar)**:

- Component rendering with mock data
- Price flash animation triggers correctly on price changes
- Watchlist CRUD operations
- Portfolio display calculations
- Chat message rendering and loading state

### E2E Tests (in `test/`)

**Infrastructure**: A separate `docker-compose.test.yml` in `test/` that spins up the app container plus a Playwright container. This keeps browser dependencies out of the production image.

**Environment**: Tests run with `LLM_MOCK=true` by default for speed and determinism.

**Key Scenarios**:

- Fresh start: default watchlist appears, $10k balance shown, prices are streaming
- Add and remove a ticker from the watchlist
- Buy shares: cash decreases, position appears, portfolio updates
- Sell shares: cash increases, position updates or disappears
- Portfolio visualization: heatmap renders with correct colors, P&L chart has data points
- AI chat (mocked): send a message, receive a response, trade execution appears inline
- SSE resilience: disconnect and verify reconnection

---

## 13. Review Notes & Clarifications

### Questions & Clarifications Needed

1. **Environment Variable Requirements (Section 5)**
   - `OPENROUTER_API_KEY` is marked "Required" but there's no fallback behavior defined. Should the frontend gracefully disable chat if the key is missing, or should the app fail to start?
   - Should `.env.example` be included in the repo with placeholder values for onboarding?
     ANSWER: YES

2. **SSE Streaming Efficiency (Section 6)**
   - The plan states SSE pushes "for all tickers known to the system at a regular cadence (~500ms)". In a single-user model this matches the watchlist, but what happens if the watchlist is empty? Does the stream still push every 500ms with no data?
   - Should we optimize to only push tickers that have price changes, or is the fixed cadence intentional for UX consistency?

3. **Database Race Conditions (Section 7)**
   - "Lazy initialization on first request" — what happens if two concurrent requests hit the database init simultaneously? Should we use a file lock or transaction to prevent double-initialization?
     ANSWER: Use transaction

4. **Trade Failure Handling (Section 8 & 9)**
   - When a trade fails validation (insufficient cash/shares), what HTTP status code should `/api/portfolio/trade` return? (400 Bad Request, 422 Unprocessable Entity, 402 Payment Required, or custom error?)
     ANSWER: Add a custom error for insufficient cash
   - When the LLM auto-executes a trade and it fails, the "error is included in the chat response" — but does the LLM know the trade failed, or does it see a successful response? Clarify the feedback loop.

5. **Connection Status Indicator (Section 10)**
   - The frontend shows a connection status dot (green/yellow/red), but the API spec doesn't define an endpoint for connection state. Should this be inferred from SSE connection state, or should there be a `/api/health` endpoint that the frontend polls?
     ANSWER: add a health api

6. **SSE Reconnection Strategy (Section 6)**
   - EventSource has built-in retry with exponential backoff, but the specifics (max retries, backoff duration) are browser-default. Should these be configurable or documented?
     ANSWER: pLease be configurable

### Simplifications Implemented ✓

1. **Reduce Database Schema Duplication** — Consolidated `user_id` repetition with a single note at the top of Section 7
2. **Consolidate Polling Interval Details** — Simplified Massive API description; polling intervals now configurable via env var
3. **Shorten Directory Structure Section** — Tightened "Key Boundaries" explanations to one line each
4. **Clarify Error Handling Patterns** — Added standardized error response format under API Endpoints
5. **Specify LLM Response Timeout** — Defined 5-second SLA for LLM responses in Section 9
6. **Table of Contents** — Added at document top for easy navigation
7. **Cross-Section Links** — Added references from API endpoints to detailed implementation sections

### Strengths of This Plan

- **Excellent detail and clarity** — agents have concrete specifications, not vague requirements
- **Clear architectural boundaries** — frontend/backend/database separation is crisp
- **Thoughtful tech choices** — the "Why These Choices" table justifies each decision
- **Single-user focus** — keeps scope tight while designing for future multi-user
- **Well-formatted** — tables, code blocks, and clear section numbering make it easy to navigate

### Minor Formatting Suggestions

- Add a Table of Contents at the top for quick navigation (sections 1–12)
- Consider linking from API endpoint descriptions (Section 8) to the detailed implementation notes in other sections (e.g., `/api/stream/prices` → Section 6)
