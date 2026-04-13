# ClashX

**Autonomous Trading Bot Platform Built on Pacifica Perpetuals Infrastructure**

ClashX is a full-stack, production-grade platform that transforms how users interact with decentralized perpetual futures markets. Rather than placing manual trades, users design, deploy, and manage autonomous trading bots that execute on their behalf through delegated wallet authorization on Pacifica's on-chain perpetuals exchange. The platform combines a visual bot builder, an AI-powered copilot, real-time performance tracking, copy trading mechanics, portfolio allocation, backtesting, and a creator marketplace into a single cohesive product.

Built for the **Pacifica Hackathon**, ClashX targets the **Trading Applications and Bots** track while simultaneously addressing elements of the **Analytics and Data**, **Social and Gamification**, and **DeFi Composability** tracks.

---

## Table of Contents

- [Product Overview](#product-overview)
- [Core Features](#core-features)
  - [Visual Bot Builder Studio](#visual-bot-builder-studio)
  - [AI Copilot](#ai-copilot)
  - [Bot Runtime Engine](#bot-runtime-engine)
  - [Copy Trading and Mirroring](#copy-trading-and-mirroring)
  - [Portfolio Baskets and Allocation](#portfolio-baskets-and-allocation)
  - [Backtesting Laboratory](#backtesting-laboratory)
  - [Creator Marketplace](#creator-marketplace)
  - [Bot Leaderboard and Discovery](#bot-leaderboard-and-discovery)
  - [Telegram Bot Integration](#telegram-bot-integration)
  - [Dashboard and Analytics](#dashboard-and-analytics)
  - [Trust and Reputation System](#trust-and-reputation-system)
- [Architecture](#architecture)
  - [High-Level Architecture Diagram](#high-level-architecture-diagram)
  - [Technology Stack](#technology-stack)
  - [Monorepo Structure](#monorepo-structure)
  - [Frontend Architecture](#frontend-architecture)
  - [Backend Architecture](#backend-architecture)
  - [Background Workers](#background-workers)
  - [Database Schema](#database-schema)
- [API Reference](#api-reference)
  - [Authentication and Authorization](#authentication-and-authorization)
  - [Bot Builder and Runtime](#bot-builder-and-runtime)
  - [Copy Trading](#copy-trading)
  - [Leaderboard and Marketplace](#leaderboard-and-marketplace)
  - [Portfolios](#portfolios)
  - [Backtests](#backtests)
  - [Copilot](#copilot)
  - [Telegram](#telegram)
  - [Realtime Streaming](#realtime-streaming)
  - [Trading](#trading)
  - [Operational Endpoints](#operational-endpoints)
- [Rules Engine and Strategy System](#rules-engine-and-strategy-system)
  - [Supported Conditions](#supported-conditions)
  - [Supported Actions](#supported-actions)
  - [Graph-Based Strategy Composition](#graph-based-strategy-composition)
  - [Validation Pipeline](#validation-pipeline)
- [Delegated Wallet Authorization](#delegated-wallet-authorization)
- [Performance Tracking and Metrics](#performance-tracking-and-metrics)
- [Risk Management](#risk-management)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Environment Setup](#environment-setup)
  - [Installation](#installation)
  - [Running the Development Servers](#running-the-development-servers)
  - [Database Migrations](#database-migrations)
- [Testing](#testing)
- [Deployment](#deployment)
- [Configuration Reference](#configuration-reference)
- [Hackathon Context](#hackathon-context)
- [License](#license)

---

## Product Overview

ClashX reimagines the perpetual futures trading experience by shifting the user's role from manual trader to bot operator. The platform is designed around a single insight: most retail traders lose money placing discretionary trades, but systematic, rule-based strategies with proper risk controls can outperform emotional decision-making. ClashX makes bot-driven trading accessible to everyone, from beginners who use pre-built templates to advanced quants who design sophisticated multi-condition strategies.

The product flow is straightforward:

1. **Connect your wallet** using Privy's embedded wallet authentication.
2. **Authorize delegated execution** so ClashX can place trades on your behalf through Pacifica's agent wallet system, without ever taking custody of your funds.
3. **Build a bot** using the visual graph-based builder or leverage the AI copilot to generate strategies from natural language descriptions.
4. **Backtest your strategy** against historical market data to validate performance before risking capital.
5. **Deploy the bot** to begin live automated trading on Pacifica's perpetuals markets.
6. **Monitor performance** through real-time dashboards, execution logs, and health indicators.
7. **Discover and copy** top-performing bots from the public leaderboard, either by live mirroring or by cloning their configuration into your own editable draft.
8. **Compose portfolios** by allocating capital across multiple bots with automatic drift-based rebalancing.

ClashX is not a custodial service. Users retain full control of their wallets at all times. The delegated authorization model ensures that ClashX can only execute trades within the boundaries set by the user, and authorization can be revoked instantly.

---

## Core Features

### Visual Bot Builder Studio

The builder studio is the centerpiece of ClashX's user experience. It provides a node-based graph editor (powered by React Flow / xyflow) where users visually compose trading strategies by connecting condition nodes to action nodes.

**Key capabilities:**

- **Drag-and-drop node editor**: Users place condition nodes (price thresholds, technical indicators, position states) and action nodes (open long, open short, close position, set stop-loss) onto a canvas and connect them with directional edges to define execution flow.
- **Template library**: Pre-built strategy templates covering common patterns like RSI mean-reversion, SMA crossover, breakout trading, and momentum following. Templates serve as starting points that users can customize.
- **Block catalog**: A curated set of approved condition and action blocks that can be combined freely. Each block has typed configuration parameters with validation.
- **Real-time validation**: As users build their strategy, the system continuously validates the graph for structural correctness, ensuring every entry action has a protective stop-loss, no orphan nodes exist, and all required parameters are filled.
- **Risk-adjusted sizing validation**: The builder checks that position sizing logic is consistent with the user's risk policy, flagging strategies that could exceed leverage or drawdown limits.
- **AI-assisted generation**: Users can describe a strategy in natural language and the AI copilot will generate the corresponding graph structure, which can then be fine-tuned in the visual editor.
- **Simulation mode**: Before deployment, users can simulate their strategy against recent market conditions to preview expected behavior.

The builder studio frontend component alone spans nearly 200KB of TypeScript/React code, reflecting the depth of the visual editing experience. The corresponding backend builder service handles template management, block catalog retrieval, market data for simulation, and AI-powered strategy generation.

### AI Copilot

ClashX includes a full-featured AI copilot that acts as a conversational trading assistant. The copilot is deeply integrated with the platform's data layer, enabling it to answer questions, generate strategies, analyze performance, and execute platform actions on behalf of the user.

**Architecture:**

- **Dual-provider failover**: The copilot and builder AI attempt requests against TrollLLM first, then fall back to OpenAI if the primary provider is unavailable. This ensures high availability of the AI assistant.
- **Tool-calling framework**: The copilot has access to a comprehensive tool catalog that enables it to query the database, inspect bot definitions, review execution history, examine portfolio allocations, and more. All tool calls are scoped to the authenticated user's data.
- **Conversation persistence**: Full conversation history is stored in Supabase with rolling summarization to manage context window limits. Each conversation tracks message count, token estimates, and summary state.
- **Scoped database access**: The copilot can query a controlled set of database tables (bot definitions, runtimes, execution events, backtest runs, copy relationships, portfolio baskets, and more) but all queries are automatically filtered to the authenticated user's wallet address.
- **Strategy generation**: Users can describe a trading strategy in plain English, and the copilot generates a complete bot definition with appropriate conditions, actions, risk parameters, and market scope.

**Supported tool actions include:**

- Querying bot definitions, runtimes, execution events, and backtest history
- Inspecting portfolio baskets and allocation members
- Reviewing copy trading relationships and activity
- Analyzing performance metrics and trade history
- Generating and modifying bot strategies
- Answering general questions about Pacifica markets and trading concepts

### Bot Runtime Engine

The runtime engine is responsible for the full lifecycle of bot execution: deployment, evaluation, action submission, pause/resume, and graceful shutdown.

**Lifecycle states:**

- `draft` - Bot definition created but not yet deployed
- `active` - Bot is live and evaluating rules on each tick
- `paused` - Bot is temporarily suspended; no new actions are submitted
- `stopped` - Bot is permanently deactivated

**Execution model:**

- The `BotRuntimeWorker` (a 105KB background worker) continuously polls for active runtimes, evaluates their rule sets against current market conditions, and submits actions to Pacifica when conditions are met.
- Each evaluation cycle fetches real-time price data, candlestick history, and current position state from Pacifica's REST and WebSocket APIs.
- The rules engine evaluates the bot's condition graph and returns a list of triggered actions.
- Actions are translated into Pacifica order submissions (market orders, limit orders, TWAP orders) with appropriate parameters.
- An idempotency layer (`bot_action_claims` table) prevents duplicate order submission in case of worker restarts or retries.
- Every execution event is logged to `bot_execution_events` with full request/response payloads for auditability.

**Advanced execution controls:**

- Configurable leverage per bot
- Take-profit and stop-loss automation
- Position sizing (fixed, percentage of equity, risk-based)
- Cooldown periods between trades
- Market scope restrictions (allowlist of trading pairs)
- Maximum drawdown limits with automatic pause

### Copy Trading and Mirroring

ClashX supports two distinct copy trading models:

**Live Mirroring:**
- When a user mirrors a source bot, every execution event from the source bot is replicated to the follower's wallet in real-time.
- The `BotCopyWorker` (a 42KB background worker) monitors source bot execution events and automatically submits corresponding orders for all active mirror relationships.
- Followers can configure a scale factor (in basis points) to adjust position sizes relative to the source bot. For example, a scale of 5000 bps means the follower takes positions at 50% of the source bot's size.
- Per-follower risk controls include maximum notional exposure limits and the ability to pause mirroring at any time.
- Copy execution events are tracked separately in `bot_copy_execution_events` with full attribution to the source event.

**Configuration Cloning:**
- Users can clone a public bot's strategy configuration into their own account as a new draft.
- The cloned bot is fully editable, allowing the user to modify conditions, actions, risk parameters, and market scope before deployment.
- Clone provenance is tracked in the `bot_clones` table, maintaining an auditable lineage from source to derivative.

**Access control:**
- Bot visibility can be set to `public`, `private`, `unlisted`, or `invite_only`.
- Invite-only bots support a whitelist of wallet addresses that are permitted to view and copy the strategy.
- The copy engine validates that the follower has an active delegated authorization before activating any mirror relationship.

### Portfolio Baskets and Allocation

ClashX extends beyond individual bot management with a portfolio allocation system that allows users to compose baskets of bots and manage them as a unified portfolio.

**Portfolio composition:**
- Users create named portfolio baskets and add multiple bot runtimes as allocation members.
- Each member has a target weight (percentage) and target notional allocation (USD).
- The system calculates optimal scale factors for each member's copy relationship to achieve the desired allocation.

**Rebalancing:**
- **Drift-based rebalancing**: The system monitors each member's actual allocation against the target. When drift exceeds a configurable threshold (default 6%), automatic rebalancing is triggered.
- **Interval-based rebalancing**: Portfolios can be configured to rebalance on a fixed schedule (e.g., every 60 minutes).
- **Manual rebalancing**: Users can trigger rebalancing on demand.
- Rebalance events are recorded in `portfolio_rebalance_events` with a summary of adjustments made.

**Risk policies:**
- Each portfolio has an associated risk policy defining maximum drawdown percentage, maximum per-member drawdown, minimum trust score for members, maximum number of active members, and automatic pause on stale source bots.
- A **kill switch** mechanism allows instant deactivation of all portfolio members if risk thresholds are breached.

**Background automation:**
- The `PortfolioAllocatorWorker` runs continuously, monitoring portfolios for drift and triggering rebalances as needed.

### Backtesting Laboratory

The backtesting lab allows users to validate their strategies against historical market data before risking real capital.

**Capabilities:**

- **Multi-symbol backtesting**: Strategies can reference multiple trading pairs, and the backtester fetches historical candlestick data for each referenced symbol.
- **Configurable timeframes**: Supports multiple candlestick intervals (1m, 5m, 15m, 1h, 4h, 1d) with automatic interval inference from the bot's rule conditions.
- **Realistic simulation**: Models position opening, closing, partial fills, and multiple concurrent positions per symbol.
- **Configurable assumptions**: Users can specify fee rates, slippage, and funding rates to model realistic trading costs.
- **Comprehensive metrics**: Each backtest run produces total PnL, percentage return, maximum drawdown, win rate, trade count, equity curve, and per-trade breakdown.
- **Progress streaming**: Long-running backtests stream progress updates via SSE, showing current stage, processed bars, and intermediate metrics.
- **Checkpoint and resume**: The backtester supports checkpointing, allowing long simulations to be paused and resumed without losing progress.
- **Indicator pre-computation**: For strategies using technical indicators (RSI, SMA, EMA, MACD, Bollinger Bands), the backtester pre-computes full indicator series before simulation to ensure consistent evaluation.

The backtesting service is the largest single service in the codebase at 1,767 lines, reflecting the complexity of accurately simulating multi-symbol, multi-indicator strategies with realistic position management.

### Creator Marketplace

The marketplace transforms bot creators into content producers, providing a discovery surface where users can browse, evaluate, and subscribe to public strategies.

**Creator profiles:**
- Creators can set up marketplace profiles with display names, slugs, headlines, bios, and social links.
- Each profile showcases the creator's published bots, performance history, and reputation metrics.
- Featured collections allow creators to curate groups of their best strategies.

**Discovery surfaces:**
- **Public bot discovery**: Browse all published bots with filtering by strategy type and creator.
- **Featured shelves**: Curated collections of high-performing or notable strategies.
- **Creator highlights**: Spotlight profiles of top-performing creators.
- **Marketplace overview**: A combined view of discovery, featured, and creator sections.

**Publishing workflow:**
- Bots progress through a publishing pipeline: draft, published, and delisted states.
- Each publication creates a strategy version snapshot, preserving the exact configuration at the time of publication.
- Publishing settings include access mode (public, invite-only), hero headlines, and custom notes.

**Performance snapshots:**
- The marketplace maintains pre-computed performance snapshots for all public bots, updated by the `BotRuntimeSnapshotWorker`.
- Creator snapshots aggregate metrics across all of a creator's bots, including marketplace reach scores and highlight summaries.

### Bot Leaderboard and Discovery

The leaderboard provides a competitive ranking of all public bot runtimes, driving discovery and engagement.

**Ranking factors:**
- Total PnL (realized and unrealized)
- Win streak
- Maximum drawdown
- Runtime uptime and health

**Features:**
- Real-time leaderboard updates with configurable refresh intervals
- Bot profile pages with detailed performance breakdowns
- Strategy passport panels showing trust scores, health metrics, and verification badges
- Creator reputation cards with aggregate statistics
- Direct copy/clone actions from leaderboard entries

### Telegram Bot Integration

ClashX includes a full Telegram bot integration that provides real-time notifications and portfolio monitoring directly in Telegram.

**Bot commands:**
- `/status` - Get a summary of your bot fleet (active bots, total PnL, open positions)
- `/bots` - Review individual bot health and recent activity
- `/positions` - View current open positions across all bots
- `/copy` - Check copy trading relationships and activity
- `/help` - Display available commands
- `/disconnect` - Unlink the Telegram chat from your ClashX account

**Wallet linking:**
- Users generate a one-time link code from the ClashX web interface.
- The code is sent to the Telegram bot via `/start <code>` to establish the connection.
- Link codes expire after a configurable TTL (default 20 minutes) for security.

**Notification preferences:**
- Users can configure which notification categories they receive:
  - `critical_alerts` - Bot stopped, authorization required, portfolio kill switch
  - `execution_failures` - Failed trade executions
  - `copy_activity` - Copy trading updates and mirror events

**Webhook integration:**
- The Telegram bot uses webhooks for incoming message handling.
- Outgoing notifications use the Telegram Bot API with rate limiting to respect Telegram's API constraints.

### Dashboard and Analytics

**User dashboard:**
- Fleet overview showing all owned bots with their current status, PnL, and health indicators.
- Real-time position monitoring across all active bots.
- Aggregate portfolio metrics including total equity, unrealized PnL, and daily performance.
- Quick actions for deploying, pausing, and stopping bots.

**Analytics page:**
- Detailed performance charts with configurable time ranges.
- Per-bot performance comparison.
- Execution event timeline with filterable event types.
- Risk metrics visualization including drawdown curves and exposure analysis.

### Trust and Reputation System

ClashX implements a multi-dimensional trust system that helps users evaluate bots before copying or mirroring them.

**Strategy Passport:**
- Each public bot has a strategy passport showing its verification status, including:
  - Strategy version history and change tracking
  - Backtest results for the currently deployed version
  - Publishing history and audit trail
  - Access mode and visibility settings

**Trust Score:**
- A composite score (0-100) computed from:
  - Runtime health (uptime percentage, heartbeat freshness)
  - Risk grade (based on drawdown vs policy limits)
  - Failure rate (percentage of failed actions)
  - Strategy drift (deviation between deployed version and published version)

**Health Classification:**
- Bots are classified into health tiers: `healthy`, `degraded`, `paused`, `stale`, `offline`, `failed`, `stopped`
- Each tier maps to an estimated uptime percentage used in trust score calculation.

**Trust Badges:**
- Visual badges displayed on bot cards and profiles:
  - Verified (clean health, low failure rate)
  - Stable (consistent performance, low drift)
  - Risk-managed (active risk controls within bounds)
  - Warning indicators for degraded health or high drift

**Creator Reputation:**
- Aggregate reputation scores for bot creators based on:
  - Average trust score across their published bots
  - Active mirror count (showing adoption)
  - Total clone count
  - Number of public bots
  - Best leaderboard rank

---

## Architecture

### High-Level Architecture Diagram

```
                                    +-----------------------+
                                    |    User (Web/Mobile)  |
                                    +-----------+-----------+
                                                |
                                    +-----------v-----------+
                                    |   Next.js 16 Frontend |
                                    |   (React 19 + TW CSS) |
                                    +-----------+-----------+
                                                |
                              +-----------------+-----------------+
                              |                                   |
                   +----------v----------+             +----------v----------+
                   |   Privy Auth Layer  |             |  FastAPI Backend    |
                   |   (Wallet Connect)  |             |  (Python 3.11+)    |
                   +---------------------+             +----------+----------+
                                                                  |
                         +----------------------------------------+-----------------------------+
                         |                |               |               |                     |
              +----------v---+   +--------v------+  +-----v------+  +----v--------+   +--------v-------+
              | Supabase     |   | Pacifica REST |  | Pacifica   |  | TrollLLM /  |   | Telegram Bot   |
              | PostgreSQL   |   | API           |  | WebSocket  |  | OpenAI API  |   | API            |
              | (30+ tables) |   | (Orders, Mkt) |  | (Realtime) |  | (Copilot)   |   | (Notifications)|
              +--------------+   +---------------+  +------------+  +-------------+   +----------------+

                              +----------------------------------------------+
                              |          Background Workers (5)              |
                              |  Bot Runtime | Copy | Snapshot | Portfolio   |
                              |  Backtest                                    |
                              +----------------------------------------------+
```

### Technology Stack

**Frontend:**

| Technology       | Version  | Purpose                                    |
|-----------------|----------|--------------------------------------------|
| Next.js          | 16.1.6   | React framework with App Router            |
| React            | 19.2.0   | UI library                                 |
| TypeScript       | 5.8.2    | Type-safe JavaScript                       |
| Tailwind CSS     | 3.4.17   | Utility-first CSS framework                |
| xyflow (React Flow) | 12.10.1 | Node-based graph editor for bot builder |
| Framer Motion    | 12.36.0  | Animation library                          |
| Lightweight Charts | 5.1.0  | Financial charting (TradingView)            |
| Lucide React     | 0.577.0  | Icon library                               |
| Privy React Auth | 3.16.0   | Embedded wallet authentication             |
| Solana Web3.js   | 1.98.4   | Solana blockchain interaction              |

**Backend:**

| Technology       | Version  | Purpose                                    |
|-----------------|----------|--------------------------------------------|
| Python           | 3.11+    | Runtime language                           |
| FastAPI          | 0.115+   | Async web framework                        |
| Uvicorn          | 0.32+    | ASGI server                                |
| Pydantic         | 2.10+    | Data validation and serialization          |
| HTTPX            | 0.28+    | Async HTTP client                          |
| Pacifica SDK     | 0.1+     | Pacifica DEX integration                   |
| Privy Client     | 0.5+     | Server-side auth verification              |
| Solders          | 0.19+    | Solana primitives                          |
| Websockets       | 14.1+    | WebSocket client for Pacifica streams      |
| Cryptography     | 44.0+    | Agent wallet encryption                    |
| Base58           | 2.1+     | Solana address encoding                    |

**Infrastructure:**

| Service          | Purpose                                    |
|------------------|--------------------------------------------|
| Supabase         | PostgreSQL database + REST API             |
| Vercel           | Frontend deployment                        |
| Railway/Render   | Backend API + worker deployment            |
| Pacifica Testnet | DEX order execution (Solana Devnet)        |
| Privy            | Wallet connect and user authentication     |

**Development tools:**

| Tool             | Purpose                                    |
|------------------|--------------------------------------------|
| Ruff             | Python linting and formatting              |
| Mypy             | Python static type checking                |
| Pytest           | Python test framework (38 test files)      |
| ESLint           | TypeScript/JavaScript linting              |
| Alembic          | Database migration management              |

### Monorepo Structure

```
ClashX/
+-- apps/
|   +-- web/                          # Next.js frontend application
|       +-- src/
|       |   +-- app/                  # App Router pages
|       |   |   +-- (app)/            # Authenticated app shell
|       |   |   |   +-- analytics/    # Performance analytics
|       |   |   |   +-- backtests/    # Backtesting laboratory
|       |   |   |   +-- bots/         # Bot fleet management
|       |   |   |   +-- builder/      # Visual bot builder studio
|       |   |   |   +-- copilot/      # AI assistant interface
|       |   |   |   +-- copy/         # Copy trading dashboard
|       |   |   |   +-- dashboard/    # User dashboard
|       |   |   |   +-- leaderboard/  # Public bot leaderboard
|       |   |   |   +-- marketplace/  # Creator marketplace
|       |   |   |   +-- telegram/     # Telegram integration setup
|       |   |   +-- onboarding/       # New user onboarding flow
|       |   |   +-- docs/             # Documentation pages
|       |   |   +-- terms/            # Terms of service
|       |   +-- components/           # Reusable UI components
|       |   |   +-- builder/          # Bot builder components (5 files)
|       |   |   +-- bots/             # Bot management components (9 files)
|       |   |   +-- copy/             # Copy trading components (8 files)
|       |   |   +-- leaderboard/      # Leaderboard components (7 files)
|       |   |   +-- dashboard/        # Dashboard components (2 files)
|       |   |   +-- copilot/          # Copilot UI (1 file)
|       |   |   +-- backtests/        # Backtest components (2 files)
|       |   |   +-- telegram/         # Telegram setup (1 file)
|       |   +-- lib/                  # Shared utilities and hooks
|       |       +-- app-shell.ts        # Application shell state
|       |       +-- clashx-auth.ts      # Authentication utilities
|       |       +-- sse-client.ts       # Server-Sent Events client
|       |       +-- public-bots.ts      # Public bot data fetching
|       |       +-- fleet-observability.ts # Fleet monitoring
|       |       +-- copy-dashboard.ts   # Copy trading state
|       |       +-- copy-portfolios.ts  # Portfolio state
|       |       +-- backtests.ts        # Backtest data layer
|       |       +-- telegram.ts         # Telegram integration
|       |       +-- pacifica-solana.ts   # Solana/Pacifica helpers
|       |       +-- pacifica-readiness.ts # Readiness checks
|       |       +-- bot-performance.ts  # Performance utilities
|       |       +-- onboarding-state.ts # Onboarding flow state
|       +-- tailwind.config.ts        # Tailwind configuration
|       +-- next.config.mjs           # Next.js configuration
|       +-- package.json
+-- services/
|   +-- trading-backend/              # FastAPI backend service
|       +-- src/
|       |   +-- api/                  # API route handlers (13 modules)
|       |   |   +-- auth.py             # Authentication endpoints
|       |   |   +-- bots.py             # Bot CRUD and lifecycle (36KB)
|       |   |   +-- builder.py          # Builder templates and blocks
|       |   |   +-- bot_copy.py         # Copy trading endpoints (18KB)
|       |   |   +-- copilot.py          # AI copilot endpoints (10KB)
|       |   |   +-- marketplace.py      # Marketplace endpoints (10KB)
|       |   |   +-- portfolios.py       # Portfolio endpoints (10KB)
|       |   |   +-- backtests.py        # Backtest endpoints (13KB)
|       |   |   +-- trading.py          # Trading data endpoints (10KB)
|       |   |   +-- pacifica.py         # Pacifica auth endpoints
|       |   |   +-- stream.py           # SSE streaming endpoints
|       |   |   +-- telegram.py         # Telegram webhook handler
|       |   +-- services/             # Business logic layer (38 modules)
|       |   |   +-- rules_engine.py           # Strategy evaluation (1,260 lines)
|       |   |   +-- bot_runtime_engine.py     # Runtime lifecycle (596 lines)
|       |   |   +-- bot_copy_engine.py        # Copy/mirror/clone (452 lines)
|       |   |   +-- bot_backtest_service.py   # Backtesting (1,767 lines)
|       |   |   +-- bot_performance_service.py # Performance calc (1,713 lines)
|       |   |   +-- bot_trust_service.py      # Trust scoring (699 lines)
|       |   |   +-- copilot_service.py        # AI copilot (1,071 lines)
|       |   |   +-- creator_marketplace_service.py # Marketplace (1,842 lines)
|       |   |   +-- portfolio_allocator_service.py # Portfolios (599 lines)
|       |   |   +-- telegram_service.py       # Telegram bot (688 lines)
|       |   |   +-- pacifica_client.py        # Pacifica API client (53KB)
|       |   |   +-- bot_builder_service.py    # Bot CRUD (19KB)
|       |   |   +-- bot_risk_service.py       # Risk validation (17KB)
|       |   |   +-- builder_ai_service.py     # AI strategy gen (21KB)
|       |   |   +-- trading_service.py        # Trading helpers (22KB)
|       |   |   +-- ... (23 more service modules)
|       |   +-- workers/              # Background workers (5 modules)
|       |   |   +-- bot_runtime_worker.py     # Runtime orchestration (105KB)
|       |   |   +-- bot_copy_worker.py        # Copy execution (42KB)
|       |   |   +-- backtest_job_worker.py    # Backtest queue (8KB)
|       |   |   +-- portfolio_allocator_worker.py # Rebalancing (5KB)
|       |   |   +-- bot_runtime_snapshot_worker.py # Snapshots (4KB)
|       |   +-- models/               # Data models (11 modules)
|       |   +-- core/                 # Settings and metrics
|       |   +-- middleware/           # Auth middleware
|       |   +-- db/                   # Database migrations
|       |   +-- main.py              # FastAPI application factory
|       |   +-- worker.py            # Worker process entry point
|       +-- tests/                    # Test suite (38 test files)
|       +-- db/
|           +-- current_schema.sql    # Reference database schema
|           +-- migrations/           # Alembic migration scripts (13)
+-- packages/
|   +-- shared-types/                 # Shared TypeScript types
+-- python-sdk/                       # Pacifica Python SDK (reference)
+-- specs/                            # Feature specifications
|   +-- 001-clashx-social-trading/
|       +-- spec.md                   # Product specification
|       +-- plan.md                   # Implementation plan
|       +-- tasks.md                  # Task breakdown
+-- .github/                          # CI/CD workflows and prompts
+-- package.json                      # Root monorepo scripts
+-- Procfile                          # Process definitions
+-- vercel.json                       # Vercel deployment config
+-- pacifica.yaml                     # Pacifica API specification (57KB)
```

### Frontend Architecture

The frontend follows Next.js App Router conventions with a clear separation between public pages and the authenticated app shell.

**Routing layout:**

- `/` - Public landing page with product overview and feature highlights
- `/onboarding` - Guided onboarding flow for new users (wallet connect, authorization, first bot)
- `/docs` - Documentation and help center
- `/terms` - Terms of service
- `/(app)/*` - Protected routes requiring authentication:
  - `/dashboard` - User home with fleet overview
  - `/builder` - Visual bot builder studio
  - `/bots` - Bot fleet management with detail views
  - `/leaderboard` - Public bot rankings and discovery
  - `/copy` - Copy trading dashboard and portfolio management
  - `/copilot` - AI assistant interface
  - `/backtests` - Historical strategy testing
  - `/marketplace` - Creator marketplace and discovery
  - `/analytics` - Performance analytics and charts
  - `/telegram` - Telegram bot connection and settings

**State management:**

The frontend uses a combination of React hooks and module-level state stores (in `lib/`) for managing application state. Key state modules include:

- `app-shell.ts` (12KB) - Global application state including active wallet, navigation, and auth context
- `fleet-observability.ts` (12KB) - Real-time fleet monitoring with SSE subscriptions
- `public-bots.ts` (13KB) - Public bot data fetching and caching for leaderboard/marketplace
- `pacifica-solana.ts` (11KB) - Solana transaction construction and Pacifica integration helpers
- `clashx-auth.ts` (8KB) - Authentication flow management with Privy
- `copy-dashboard.ts` (6KB) - Copy trading relationship state
- `copy-portfolios.ts` (4KB) - Portfolio basket state management

**Realtime updates:**

The frontend maintains persistent SSE connections to the backend for real-time updates. The `sse-client.ts` module provides a reusable SSE client that handles automatic reconnection, heartbeat monitoring, and typed event parsing. Realtime streams are available for individual bot runtimes, the leaderboard, and user-level events.

### Backend Architecture

The backend follows a layered architecture pattern:

1. **API Layer** (`src/api/`) - FastAPI route handlers that parse requests, authenticate users, and delegate to services. Each module is a self-contained router.
2. **Service Layer** (`src/services/`) - Business logic implementations. Services are stateless and compose other services as needed. The service layer is where all domain logic resides.
3. **Worker Layer** (`src/workers/`) - Long-running background tasks that poll for work on configurable intervals. Workers are started as part of the application lifecycle when `BACKGROUND_WORKERS_ENABLED=true`.
4. **Model Layer** (`src/models/`) - Pydantic-based data models and record types for database interaction.
5. **Core Layer** (`src/core/`) - Application settings, configuration, and performance metrics infrastructure.
6. **Middleware Layer** (`src/middleware/`) - Request middleware including Privy JWT verification and user resolution.

**Authentication flow:**

1. The frontend authenticates with Privy and obtains a JWT.
2. Every API request includes the Privy JWT in the `Authorization` header.
3. The `AuthMiddleware` verifies the JWT, extracts the wallet address, and resolves or creates the user record.
4. Handlers receive an `AuthenticatedUser` object with the verified user ID and wallet address.

**Database access:**

All database operations go through the `SupabaseRestClient`, which wraps Supabase's PostgREST API. This provides a consistent interface for CRUD operations with filtering, ordering, and pagination. The client handles error translation, retry logic, and response parsing.

### Background Workers

ClashX runs five background workers that handle asynchronous processing:

| Worker | File Size | Responsibility |
|--------|-----------|----------------|
| `BotRuntimeWorker` | 105KB | Core bot execution loop. Polls active runtimes, evaluates rules against live market data, submits orders to Pacifica, manages position state, handles cooldowns. |
| `BotCopyWorker` | 42KB | Monitors source bot execution events and replicates them to follower wallets. Handles scale factor calculation, per-follower risk limits, and copy event tracking. |
| `BacktestJobWorker` | 8KB | Processes queued backtest jobs asynchronously. Picks up backtest runs from the database and delegates to `BotBacktestService`. |
| `PortfolioAllocatorWorker` | 5KB | Monitors portfolio baskets for drift and triggers automatic rebalancing when thresholds are exceeded. |
| `BotRuntimeSnapshotWorker` | 4KB | Periodically computes and caches runtime performance snapshots for the marketplace and leaderboard. |

Workers use a lease-based coordination system (`worker_leases` table) to prevent duplicate processing in multi-instance deployments. Each worker acquires a lease before processing and releases it on completion.

**Process model:**

The application supports two process types defined in the `Procfile`:

```
web:    uvicorn src.main:app (BACKGROUND_WORKERS_ENABLED=false)
worker: python -m src.worker  (BACKGROUND_WORKERS_ENABLED=true)
```

In development, a single process runs both the API and workers. In production, the web and worker processes are typically separated for independent scaling.

### Database Schema

The database consists of 30+ PostgreSQL tables organized around the following domains:

**User and Authentication:**
- `users` - User accounts with wallet addresses, display names, auth provider, and Telegram connection fields
- `pacifica_authorizations` - Delegated wallet authorization records including agent wallet keys, builder approval signatures, and bind-agent signatures
- `worker_leases` - Distributed worker coordination leases

**Bot Definitions and Runtime:**
- `bot_definitions` - Bot strategy configurations with rules JSON, authoring mode, visibility, and market scope
- `bot_runtimes` - Active execution instances bound to specific wallets with status tracking
- `bot_execution_events` - Timestamped log of every bot decision and action
- `bot_action_claims` - Idempotency tokens preventing duplicate order submission
- `bot_strategy_versions` - Versioned snapshots of bot configurations for change tracking
- `bot_publishing_settings` - Publication state, access mode, and marketplace metadata
- `bot_publish_snapshots` - Point-in-time snapshots at publication
- `bot_runtime_snapshots` - Cached performance and health metrics for active runtimes

**Trade Tracking:**
- `bot_trade_lots` - Individual trade lot tracking with entry price, quantity, and side
- `bot_trade_closures` - Closed trade records with realized PnL
- `bot_trade_sync_state` - Synchronization state for trade reconciliation

**Copy Trading:**
- `bot_copy_relationships` - Mirror relationships between source bots and followers
- `bot_copy_execution_events` - Execution records for copied trades
- `bot_clones` - Clone provenance records
- `bot_invite_access` - Invite-only access whitelist
- `copy_relationships` - Legacy user-to-user copy relationships
- `copy_execution_events` - Legacy copy execution records

**Marketplace and Discovery:**
- `creator_marketplace_profiles` - Creator profiles with slugs, bios, and social links
- `featured_bots` - Curated featured bot collections
- `marketplace_runtime_snapshots` - Pre-computed marketplace display data
- `marketplace_creator_snapshots` - Aggregated creator metrics
- `bot_leaderboard_snapshots` - Historical leaderboard rankings
- `leaderboard_snapshots` - Legacy leaderboard data

**Portfolios:**
- `portfolio_baskets` - Portfolio definitions with rebalancing configuration
- `portfolio_allocation_members` - Individual bot allocations within portfolios
- `portfolio_rebalance_events` - Rebalancing event log
- `portfolio_risk_policies` - Per-portfolio risk limits and kill switch configuration

**AI and Copilot:**
- `copilot_conversations` - Conversation sessions with rolling summaries
- `copilot_messages` - Individual messages with role, content, and tool call data
- `ai_job_runs` - Async AI job queue for strategy generation

**Audit:**
- `audit_events` - Platform-wide audit trail for all significant actions

---

## API Reference

### Authentication and Authorization

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/pacifica/authorize` | Check authorization status for a wallet |
| `POST` | `/api/pacifica/authorize/start` | Initiate delegated wallet authorization |
| `POST` | `/api/pacifica/authorize/{id}/activate` | Complete authorization activation |

### Bot Builder and Runtime

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/bots` | List all bots owned by the authenticated user |
| `POST` | `/api/bots` | Create a new bot definition |
| `GET` | `/api/bots/{bot_id}` | Get bot details including runtime state |
| `PATCH` | `/api/bots/{bot_id}` | Update bot configuration |
| `POST` | `/api/bots/{bot_id}/validate` | Validate bot rules without deploying |
| `POST` | `/api/bots/{bot_id}/deploy` | Deploy bot to start live execution |
| `POST` | `/api/bots/{bot_id}/pause` | Pause active bot runtime |
| `POST` | `/api/bots/{bot_id}/resume` | Resume paused bot runtime |
| `POST` | `/api/bots/{bot_id}/stop` | Permanently stop bot runtime |
| `GET` | `/api/bots/{bot_id}/events` | List execution event history |

### Builder Metadata

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/builder/templates` | List available strategy templates |
| `GET` | `/api/builder/blocks` | List approved condition and action blocks |
| `GET` | `/api/builder/markets` | List available Pacifica markets |
| `POST` | `/api/builder/simulate` | Simulate a strategy against recent data |

### Copy Trading

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/bots/{runtime_id}/copy/preview` | Preview mirror relationship before activation |
| `POST` | `/api/bots/{runtime_id}/copy/mirror` | Activate live mirroring |
| `POST` | `/api/bots/{runtime_id}/copy/clone` | Clone bot configuration |
| `PATCH` | `/api/copy/{relationship_id}` | Update copy relationship parameters |
| `DELETE` | `/api/copy/{relationship_id}` | Deactivate copy relationship |

### Leaderboard and Marketplace

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/leaderboard/bots` | Get ranked list of public bots |
| `GET` | `/api/leaderboard/bots/{runtime_id}` | Get detailed bot profile |
| `GET` | `/api/marketplace/overview` | Get marketplace overview with discovery, featured, and creators |
| `GET` | `/api/marketplace/discover` | Browse published bots |
| `GET` | `/api/marketplace/creators/{id}` | Get creator profile |

### Portfolios

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/portfolios` | List user's portfolio baskets |
| `POST` | `/api/portfolios` | Create a new portfolio basket |
| `GET` | `/api/portfolios/{id}` | Get portfolio details with members |
| `PATCH` | `/api/portfolios/{id}` | Update portfolio configuration |
| `POST` | `/api/portfolios/{id}/rebalance` | Trigger manual rebalance |
| `DELETE` | `/api/portfolios/{id}` | Delete portfolio basket |

### Backtests

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/backtests` | Queue a new backtest run |
| `GET` | `/api/backtests` | List backtest runs for user |
| `GET` | `/api/backtests/{run_id}` | Get backtest results and metrics |

### Copilot

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/copilot/chat` | Send a message to the AI copilot |
| `GET` | `/api/copilot/conversations` | List conversation history |
| `GET` | `/api/copilot/conversations/{id}` | Get conversation with messages |

### Telegram

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/telegram/status` | Get Telegram connection status |
| `POST` | `/api/telegram/link` | Generate wallet link code |
| `PATCH` | `/api/telegram/preferences` | Update notification preferences |
| `POST` | `/api/telegram/disconnect` | Disconnect Telegram from wallet |
| `POST` | `/api/telegram/webhook` | Handle incoming Telegram updates |

### Realtime Streaming

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/stream/bots/{runtime_id}` | SSE stream for bot runtime events |
| `GET` | `/api/stream/leaderboard/bots` | SSE stream for leaderboard updates |
| `GET` | `/api/stream/user/{user_id}` | SSE stream for user-level events |

### Operational Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/healthz` | Health check with worker status |
| `GET` | `/healthz/perf` | Performance metrics snapshot |

---

## Rules Engine and Strategy System

The rules engine is the decision-making core of ClashX. It evaluates bot strategy graphs against live market data and produces a list of actions to execute.

### Supported Conditions

The rules engine supports over 50 approved condition types across several categories:

**Price conditions:**
- `price_above` / `price_below` - Simple price threshold comparisons
- `price_change_up` / `price_change_down` - Percentage price change over a lookback period
- `price_crosses_above` / `price_crosses_below` - Price crossing a specified level

**Technical indicator conditions:**
- `rsi_above` / `rsi_below` - Relative Strength Index thresholds
- `rsi_crosses_above` / `rsi_crosses_below` - RSI level crossovers
- `sma_above` / `sma_below` - Simple Moving Average comparisons
- `sma_crosses_above` / `sma_crosses_below` - SMA crossovers
- `ema_above` / `ema_below` - Exponential Moving Average comparisons
- `ema_crosses_above` / `ema_crosses_below` - EMA crossovers
- `macd_above_signal` / `macd_below_signal` - MACD signal line crossovers
- `macd_histogram_positive` / `macd_histogram_negative` - MACD histogram direction
- `bollinger_above_upper` / `bollinger_below_lower` - Bollinger Band breakouts
- `bollinger_squeeze` - Bollinger Band width contraction detection
- `volume_above` / `volume_below` - Volume threshold conditions
- `volume_spike` - Abnormal volume detection
- `vwap_above` / `vwap_below` - Volume-Weighted Average Price comparisons
- `atr_above` / `atr_below` - Average True Range volatility conditions
- `stochastic_above` / `stochastic_below` - Stochastic oscillator thresholds

**Position state conditions:**
- `has_open_position` / `no_open_position` - Check if a position exists
- `position_pnl_above` / `position_pnl_below` - Position PnL thresholds
- `position_size_above` / `position_size_below` - Position size thresholds
- `position_duration_above` - Time-in-position checks

**Logical operators:**
- `and` / `or` / `not` - Boolean combinators for composing complex conditions
- `always_true` / `always_false` - Constant conditions for testing

### Supported Actions

**Entry actions:**
- `open_long` - Open a long position
- `open_short` - Open a short position
- `place_market_order` - Submit a market order
- `place_limit_order` - Submit a limit order at a specified price
- `place_twap_order` - Submit a Time-Weighted Average Price order

**Exit actions:**
- `close_position` - Close an existing position
- `reduce_position` - Partially close a position

**Risk management actions:**
- `set_stop_loss` - Set or update a stop-loss level
- `set_take_profit` - Set or update a take-profit level
- `cancel_orders` - Cancel open orders

### Graph-Based Strategy Composition

Strategies in ClashX are represented as directed acyclic graphs (DAGs) where:

- **Trigger nodes** serve as the entry point for evaluation
- **Condition nodes** evaluate market data and produce boolean results
- **Action nodes** specify trading operations to execute when their parent conditions are met
- **Edges** define the flow of execution through the graph

The graph format allows for complex multi-branch strategies where different market conditions lead to different actions. For example, a strategy might check RSI and price simultaneously, opening a long position only when both conditions align, while setting a stop-loss through a separate branch of the graph.

**Graph inspection and validation:**

The rules engine performs structural analysis of strategy graphs before deployment:
- Detects unreachable nodes (not connected to the entry point)
- Validates that all entry actions (opens) have protective stop-losses reachable in the graph
- Checks for cycles that could cause infinite evaluation loops
- Verifies that all node configurations have valid parameters
- Counts reachable conditions and actions for complexity analysis

### Validation Pipeline

Before a bot can be deployed, it must pass a multi-stage validation pipeline:

1. **Structural validation**: The graph must be well-formed with a single entry point, no cycles, and all nodes reachable.
2. **Parameter validation**: All condition and action nodes must have valid, complete configurations.
3. **Risk validation**: The strategy must include protective stops for all entry actions and respect the risk policy's leverage and position size limits.
4. **Market scope validation**: All referenced symbols must be valid Pacifica markets.
5. **Readiness validation**: The user's delegated authorization must be active and the agent wallet must be funded.

---

## Delegated Wallet Authorization

ClashX uses Pacifica's builder program to enable non-custodial automated trading. The authorization flow works as follows:

1. **Agent wallet generation**: ClashX generates a unique agent wallet (Solana keypair) for each user.The agent private key is encrypted with AES using the platform's encryption key and stored in the database.
2. **Builder approval**: The user signs a message approving ClashX as a builder for their account, authorizing the platform to submit orders with a configurable maximum fee rate.
3. **Agent binding**: The user signs a second message binding the generated agent wallet to their account, granting it permission to act on their behalf.
4. **Activation**: Once both signatures are submitted and verified on-chain, the authorization status moves to `active` and bots can begin trading.

**Security properties:**
- The user's main wallet private key is never shared with ClashX.
- The agent wallet can only execute trades, not withdraw funds.
- Authorization can be revoked at any time by the user.
- Each authorization record includes the original signed messages and signatures for full auditability.
- The builder fee rate is capped and transparent.

---

## Performance Tracking and Metrics

ClashX provides comprehensive performance tracking at multiple levels:

**Per-bot performance:**
- Realized PnL from closed trades
- Unrealized PnL from open positions (computed from live Pacifica data)
- Total PnL (realized + unrealized)
- Win rate (percentage of profitable closed trades)
- Maximum drawdown percentage
- Trade count and average trade size
- Win/loss streaks

**Trade lot accounting:**
- Individual trade lots are tracked in the `bot_trade_lots` table with entry price, quantity, and side.
- When positions are closed, matching closures are recorded in `bot_trade_closures` with exit price and realized PnL.
- The `bot_trade_sync_state` table tracks reconciliation between bot execution events and Pacifica position history.

**Multi-runtime reconciliation:**
- When multiple bots trade on the same wallet, the performance service performs joint reconciliation to correctly attribute PnL to each bot based on their execution events and the overall wallet position history.

**Caching and snapshots:**
- The `BotRuntimeSnapshotWorker` periodically computes and caches performance metrics for all active runtimes.
- Cached snapshots are stored in `bot_runtime_snapshots` and `marketplace_runtime_snapshots` for fast retrieval.
- The performance cache has configurable TTL (default 60 seconds for active runtimes).

**HTTP latency tracking:**
- Every API request is instrumented with latency tracking via middleware.
- The `/healthz/perf` endpoint exposes aggregated performance metrics for monitoring.

---

## Risk Management

ClashX implements risk management at three levels:

**Bot-level risk policies:**
- Maximum leverage cap
- Maximum position size (absolute or percentage)
- Maximum drawdown before automatic pause
- Allowed symbol whitelist
- Cooldown period between trades
- Stop-loss requirements for all entry actions

**Copy-level risk controls:**
- Scale factor (basis points) for position sizing relative to source
- Maximum notional exposure per copy relationship
- Risk acknowledgment versioning (followers must acknowledge risk before activation)
- Automatic pause when source bot is paused, stopped, or health degrades

**Portfolio-level risk policies:**
- Maximum portfolio drawdown percentage (default 18%)
- Maximum per-member drawdown percentage (default 22%)
- Minimum trust score requirement for members (default 55)
- Maximum number of active members (default 5)
- Auto-pause on stale source bots
- Kill switch for immediate portfolio deactivation with reason tracking

---

## Getting Started

### Prerequisites

- **Node.js** 18+ and npm
- **Python** 3.11 or 3.12
- **Supabase** project (for PostgreSQL database)
- **Privy** account (for wallet authentication)
- **Pacifica Testnet** access (use code "Pacifica" at https://test-app.pacifica.fi/)

### Environment Setup

1. Copy the environment template:

```bash
cp .env.example .env
```

2. Fill in the required values in `.env`:

**Required for basic operation:**
- `SUPABASE_URL` - Your Supabase project URL
- `SUPABASE_ANON_KEY` - Supabase anonymous key
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key
- `NEXT_PUBLIC_SUPABASE_URL` - Same as SUPABASE_URL (for frontend)
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` - Same as SUPABASE_ANON_KEY (for frontend)
- `NEXT_PUBLIC_PRIVY_APP_ID` - Your Privy application ID
- `PRIVY_APP_ID` - Same Privy app ID (for backend verification)
- `PRIVY_VERIFICATION_KEY` - Privy verification key for JWT validation

**Required for Pacifica trading:**
- `PACIFICA_NETWORK` - Set to `Testnet` for development
- `PACIFICA_API_KEY` - Pacifica API key
- `PACIFICA_API_SECRET` - Pacifica API secret
- `PACIFICA_BUILDER_CODE` - Your Pacifica builder code
- `PACIFICA_AGENT_ENCRYPTION_KEY` - AES key for agent wallet encryption

**Optional for AI copilot:**
- `TROLLLLM_API_KEY` - TrollLLM API key
- `TROLLLLM_BASE_URL` - TrollLLM OpenAI-compatible base URL
- `TROLLLLM_MODEL` - TrollLLM primary model name
- `OPENAI_API_KEY` - OpenAI API key

**Optional for Telegram:**
- `TELEGRAM_BOT_TOKEN` - Telegram Bot API token
- `TELEGRAM_BOT_USERNAME` - Bot username
- `TELEGRAM_WEBHOOK_URL` - Public URL for webhook delivery

### Installation

**Frontend:**

```bash
npm run install:frontend
```

**Backend:**

```bash
npm run install:backend
```

This installs the Python package in editable mode with all dependencies.

### Running the Development Servers

**Start both frontend and backend:**

```bash
# Terminal 1: Frontend (Next.js on port 3000)
npm run frontend

# Terminal 2: Backend (FastAPI on port 8000)
npm run backend
```

Or use the shorthand for frontend only:

```bash
npm run dev
```

The frontend proxies API requests to `http://localhost:8000` as configured by `NEXT_PUBLIC_API_BASE_URL`.

### Database Migrations

ClashX uses Alembic for database migrations managed through the root `package.json`:

```bash
# Apply all pending migrations
npm run db:migrate

# Create a new migration
npm run db:migration:new
```

The current schema reference is available at `services/trading-backend/db/current_schema.sql`.

---

## Testing

The backend has a comprehensive test suite with 38 test files covering all major services:

```bash
cd services/trading-backend
pip install -e ".[dev]"
pytest
```

**Test coverage areas:**

| Test File | Lines | Coverage Area |
|-----------|-------|---------------|
| `test_bot_runtime_supabase.py` | 58KB | Bot runtime worker with Supabase integration |
| `test_bot_backtest_service.py` | 44KB | Backtesting simulation accuracy |
| `test_pacifica_trade_lifecycle.py` | 43KB | End-to-end Pacifica trade lifecycle |
| `test_bot_performance_service.py` | 42KB | Performance calculation and attribution |
| `test_bot_copy_worker.py` | 21KB | Copy trading execution and scaling |
| `test_pacifica_client.py` | 20KB | Pacifica API client behavior |
| `test_copilot_service.py` | 16KB | AI copilot tool calling and conversation |
| `test_worker_coordination_service.py` | 16KB | Distributed worker lease management |
| `test_builder_ai_service.py` | 15KB | AI strategy generation |
| `test_bot_copy_dashboard_service.py` | 14KB | Copy dashboard data aggregation |
| `test_pacifica_live_smoke.py` | 13KB | Live Pacifica API smoke tests |
| `test_creator_marketplace_service.py` | 12KB | Marketplace discovery and profiles |
| `test_portfolio_allocator_service.py` | 12KB | Portfolio rebalancing logic |
| `test_ai_job_runner_service.py` | 12KB | Async AI job processing |
| `test_rules_engine_graph.py` | 11KB | Graph-based strategy evaluation |
| ... | | 23 more test files |

**Frontend validation:**

```bash
cd apps/web
npm run typecheck    # TypeScript type checking
npm run lint         # ESLint checks
```

---

## Deployment

### Frontend (Vercel)

The frontend is configured for Vercel deployment via `vercel.json`:

```json
{
  "framework": "nextjs",
  "installCommand": "npm install",
  "buildCommand": "npm run build",
  "devCommand": "npm run dev"
}
```

### Backend (Railway / Render / Fly)

The backend uses a `Procfile` with two process types:

```
web:    uvicorn src.main:app --host 0.0.0.0 --port $PORT
worker: python -m src.worker
```

**Environment variables** must be configured on the hosting platform (see Configuration Reference below).

**Scaling considerations:**
- The `web` process handles API requests and should be horizontally scalable.
- The `worker` process handles background jobs and uses distributed leases for coordination across instances.
- The lease system ensures that only one worker instance processes each job at a time, preventing duplicate execution.

---

## Configuration Reference

All configuration is managed through environment variables. The complete list with defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | ClashX Trading Backend | Application display name |
| `APP_ENV` | development | Environment (development/production) |
| `AUTH_BYPASS` | false | Bypass auth for development |
| `BACKGROUND_WORKERS_ENABLED` | true | Enable background workers |
| `WORKER_INSTANCE_ID` | (PID) | Unique worker instance identifier |
| `CORS_ALLOWED_ORIGINS` | localhost:3000 | Comma-separated allowed origins |
| `SUPABASE_URL` | (required) | Supabase project URL |
| `SUPABASE_ANON_KEY` | (required) | Supabase anonymous key |
| `SUPABASE_SERVICE_ROLE_KEY` | (required) | Supabase service role key |
| `PACIFICA_NETWORK` | Pacifica | Network selection (Testnet/Pacifica) |
| `PACIFICA_REST_URL` | (auto) | Pacifica REST API base URL |
| `PACIFICA_WS_URL` | (auto) | Pacifica WebSocket URL |
| `PACIFICA_SOLANA_RPC_URL` | devnet | Solana RPC endpoint |
| `PACIFICA_GLOBAL_REQUESTS_PER_SECOND` | 12 | Global rate limit |
| `PACIFICA_PUBLIC_REQUESTS_PER_SECOND` | 8 | Public endpoint rate limit |
| `PACIFICA_PRIVATE_REQUESTS_PER_SECOND` | 8 | Private endpoint rate limit |
| `PACIFICA_WRITE_REQUESTS_PER_SECOND` | 4 | Write endpoint rate limit |
| `PACIFICA_MARKET_CACHE_TTL_SECONDS` | 15 | Market data cache TTL |
| `PACIFICA_PRICE_CACHE_TTL_SECONDS` | 5 | Price data cache TTL |
| `PACIFICA_SNAPSHOT_CACHE_TTL_SECONDS` | 8 | Snapshot cache TTL |
| `PACIFICA_FAST_EVALUATION_SECONDS` | 5 | Fast evaluation interval |
| `PACIFICA_ACTIVE_WALLET_POLL_SECONDS` | 4 | Active wallet poll interval |
| `PACIFICA_WARM_WALLET_POLL_SECONDS` | 15 | Warm wallet poll interval |
| `PACIFICA_IDLE_WALLET_POLL_SECONDS` | 45 | Idle wallet poll interval |
| `PACIFICA_PERFORMANCE_REFRESH_SECONDS` | 60 | Performance refresh interval |
| `TROLLLLM_API_KEY` | (optional) | TrollLLM API key |
| `TROLLLLM_BASE_URL` | https://chat.trollllm.xyz/v1 | TrollLLM OpenAI-compatible base URL |
| `TROLLLLM_MODEL` | claude-haiku-4.5 | TrollLLM primary model name |
| `OPENAI_API_KEY` | (optional) | OpenAI API key |
| `TELEGRAM_BOT_TOKEN` | (optional) | Telegram Bot API token |
| `TELEGRAM_LINK_CODE_TTL_MINUTES` | 20 | Link code expiry (min 5) |

---

## Hackathon Context

### Pacifica Hackathon

ClashX is built for the **Pacifica Hackathon**, a one-month online event (March 16 - April 16, 2026) designed to bring together developers, quants, and builders to create innovative applications on Pacifica's perpetuals infrastructure.

**Tracks addressed:**

1. **Trading Applications and Bots** (Primary) - ClashX is fundamentally a bot-building and execution platform.
2. **Analytics and Data** - The analytics dashboard, performance tracking, backtesting lab, and trust scoring system provide deep market intelligence.
3. **Social and Gamification** - The leaderboard, copy trading, creator marketplace, and reputation system create a social layer around bot performance.
4. **DeFi Composability** - Portfolio baskets, delegated execution, and the multi-bot allocation system demonstrate composability on top of Pacifica's perps infrastructure.

**Judging criteria alignment:**

- **Innovation**: Dual-path bot authoring (visual + AI-generated), graph-based strategy composition, portfolio basket allocation with drift rebalancing, multi-dimensional trust scoring, and AI copilot with tool-calling are all novel additions to the Pacifica ecosystem.
- **Technical Execution**: Full-stack implementation with 38+ service modules, 30+ database tables, 5 background workers, 38 test files, comprehensive API surface, and production-grade error handling.
- **User Experience**: Visual bot builder with drag-and-drop, AI copilot for natural language strategy creation, real-time SSE updates, Telegram integration for mobile monitoring, and a polished marketplace discovery experience.
- **Potential Impact**: ClashX makes automated trading accessible to non-technical users while providing the depth that advanced traders need. The copy trading and marketplace features create network effects that could drive adoption.
- **Presentation**: This comprehensive documentation, combined with the live product demo, demonstrates the breadth and depth of the implementation.

**Developer resources used:**

- Pacifica Python SDK (bundled in `python-sdk/`)
- Pacifica REST and WebSocket API documentation
- Pacifica OpenAPI specification (`pacifica.yaml`, 57KB)
- Pacifica Testnet for development and testing
- Privy for wallet authentication
- Supabase for database infrastructure

---

## Codebase Statistics

A quantitative overview of the ClashX codebase:

| Metric | Count |
|--------|-------|
| Total frontend source files | 83+ |
| Total backend source files | 78+ |
| Frontend component files | 43 |
| Backend API modules | 13 |
| Backend service modules | 38 |
| Backend worker modules | 5 |
| Backend data models | 11 |
| Database tables | 30+ |
| Database migrations | 13 |
| Test files | 38 |
| Frontend route pages | 17+ |
| Frontend library modules | 16 |
| API endpoints | 40+ |
| Rules engine conditions | 50+ |
| Environment variables | 40+ |

**Largest files by size:**

| File | Size | Description |
|------|------|-------------|
| `builder-graph-studio.tsx` | 197KB | Visual bot builder canvas |
| `bot_runtime_worker.py` | 105KB | Core bot execution worker |
| `backtesting-lab-page.tsx` | 86KB | Backtest UI laboratory |
| `creator_marketplace_service.py` | 85KB | Marketplace backend service |
| `bot_backtest_service.py` | 81KB | Backtesting simulation engine |
| `bot_performance_service.py` | 77KB | Performance calculation service |
| `rules_engine.py` | 58KB | Strategy evaluation engine |
| `pacifica_client.py` | 54KB | Pacifica DEX API client |
| `copilot_service.py` | 52KB | AI copilot with tool calling |
| `bots-fleet-page.tsx` | 51KB | Bot fleet management UI |
| `builder-flow-utils.ts` | 49KB | Builder graph utilities |
| `page.tsx` (landing) | 49KB | Landing page |
| `bot_copy_worker.py` | 42KB | Copy trading worker |
| `copilot-page.tsx` | 40KB | AI copilot chat interface |
| `bots.py` (API) | 36KB | Bot CRUD API routes |
| `dashboard-page.tsx` | 34KB | User dashboard |
| `analytics-page.tsx` | 34KB | Analytics dashboard |
| `portfolio_allocator_service.py` | 32KB | Portfolio allocation engine |
| `bot_trust_service.py` | 32KB | Trust and reputation scoring |
| `telegram_service.py` | 32KB | Telegram bot integration |
| `copy-trading-overview.tsx` | 30KB | Copy trading overview UI |
| `telegram-page.tsx` | 30KB | Telegram settings UI |
| `bot_runtime_engine.py` | 28KB | Runtime lifecycle management |
| `bot_copy_engine.py` | 26KB | Copy/mirror/clone logic |
| `bot_copy_dashboard_service.py` | 25KB | Copy dashboard aggregation |
| `trading_service.py` | 23KB | Trading data helpers |

**Lines of code in key service modules:**

| Module | Lines | Purpose |
|--------|-------|---------|
| `creator_marketplace_service.py` | 1,842 | Marketplace discovery, featured shelves, creator profiles |
| `bot_backtest_service.py` | 1,767 | Multi-symbol backtesting with indicator pre-computation |
| `bot_performance_service.py` | 1,713 | PnL tracking, trade lot accounting, multi-runtime reconciliation |
| `rules_engine.py` | 1,260 | Graph evaluation, condition matching, action normalization |
| `copilot_service.py` | 1,071 | Dual-provider AI chat with tool calling and conversation management |
| `bot_trust_service.py` | 699 | Trust scoring, health classification, reputation badges |
| `telegram_service.py` | 688 | Bot commands, webhook handling, notification delivery |
| `portfolio_allocator_service.py` | 599 | Portfolio composition, rebalancing, kill switch |
| `bot_runtime_engine.py` | 596 | Deploy/pause/resume/stop lifecycle and event logging |
| `bot_copy_engine.py` | 452 | Mirror activation, clone creation, relationship management |

---

## Acknowledgments

- **Pacifica** for providing the perpetuals infrastructure, API documentation, Python SDK, and testnet access that made this project possible.
- **Privy** for seamless embedded wallet authentication that simplifies the onboarding experience.
- **Supabase** for the PostgreSQL database and PostgREST API layer.
- **Fuul**, **Rhinofi**, **Privy**, and **Elfa AI** for sponsor tools available during the hackathon.

---

## License

This project was created for the Pacifica Hackathon. All rights reserved.
