---
description: "Task list for implementing and upgrading ClashX Bot Builder Platform"
---

# Tasks: ClashX Bot Builder Platform

**Input**: Design documents from `/specs/001-clashx-social-trading/`  
**Prerequisites**: `plan.md` (required), `spec.md` (required)

## Phase 1: Reusable Foundation (Already Available / Adapt)

**Purpose**: Preserve and adapt infrastructure that still fits the bot platform.

- [X] T001 Reuse frontend monorepo app and backend service scaffolding in `apps/web/` and `services/trading-backend/`
- [X] T002 Reuse auth/session plumbing in `services/trading-backend/src/api/auth.py` and `services/trading-backend/src/middleware/auth.py`
- [X] T003 Reuse delegated Pacifica authorization flow in `services/trading-backend/src/api/pacifica.py` and `apps/web/src/components/pacifica/agent-authorization-panel.tsx`
- [X] T004 Reuse Pacifica client wrapper and upstream error handling in `services/trading-backend/src/services/pacifica_client.py`
- [X] T005 Reuse SSE/realtime infrastructure in `services/trading-backend/src/api/stream.py`, `services/trading-backend/src/services/event_broadcaster.py`, and `apps/web/src/lib/sse-client.ts`
- [X] T006 Reposition marketing/app shell around bot building and bot copying in `apps/web/src/app/page.tsx` and `apps/web/src/app/(app)/layout.tsx`
- [X] T007 Replace manual trade route with builder redirect in `apps/web/src/app/(app)/trade/page.tsx`
- [X] T008 Update planning artifacts to the bot-platform direction in `specs/001-clashx-social-trading/spec.md`, `specs/001-clashx-social-trading/plan.md`, and `specs/001-clashx-social-trading/tasks.md`

---

## Phase 2: Bot Domain Foundation (Blocking)

**Purpose**: Introduce core bot entities, schemas, and builder metadata.

**⚠️ CRITICAL**: Complete this phase before runtime or copy implementation.

- [X] T009 Create bot definition and bot runtime models in `services/trading-backend/src/models/bot_definition.py` and `services/trading-backend/src/models/bot_runtime.py`
- [X] T010 [P] Create bot execution event, bot leaderboard snapshot, bot copy relationship, and bot clone models in `services/trading-backend/src/models/bot_execution_event.py`, `services/trading-backend/src/models/bot_leaderboard_snapshot.py`, `services/trading-backend/src/models/bot_copy_relationship.py`, and `services/trading-backend/src/models/bot_clone.py`
- [X] T011 [P] Define shared rules-engine schemas and TypeScript types in `packages/shared-types/README.md` and `packages/shared-types/bot-schemas/*`
- [X] T011a [P] Define SDK manifest, registration schema, and normalization contract in `packages/shared-types/bot-schemas/*` and `specs/001-clashx-social-trading/contracts/`
- [X] T012 Implement backend bot builder service for create/read/update/version flows in `services/trading-backend/src/services/bot_builder_service.py`
- [X] T013 Implement builder metadata service for templates, blocks, and market capabilities in `services/trading-backend/src/services/builder_catalog_service.py`
- [X] T014 Implement bot CRUD and validation APIs in `services/trading-backend/src/api/bots.py`
- [X] T015 Implement builder metadata APIs in `services/trading-backend/src/api/builder.py`
- [X] T015a Implement SDK manifest, validation, and registration APIs in `services/trading-backend/src/api/sdk.py`

**Checkpoint**: Bot definitions and builder schemas exist and can be created/validated.

---

## Phase 3: User Story 1 - Build and Deploy a Bot (Priority: P1) 🎯 MVP

**Goal**: A user can build a bot from blocks/templates or via the SDK and deploy it on their own delegated wallet.

**Independent Validation**: Create a bot from the visual builder or SDK path, validate it, deploy it, and observe runtime state changes and Pacifica-bound execution attempts.

### Implementation for User Story 1

- [X] T016 [P] [US1] Implement rules evaluation engine for approved conditions/actions in `services/trading-backend/src/services/rules_engine.py`
- [X] T017 [P] [US1] Implement bot runtime engine for deploy, pause, resume, stop, and state transitions in `services/trading-backend/src/services/bot_runtime_engine.py`
- [X] T018 [US1] Implement advanced risk and execution policy service (leverage, TP/SL, cooldowns, sizing, max drawdown) in `services/trading-backend/src/services/bot_risk_service.py`
- [X] T019 [US1] Implement runtime APIs (`POST /deploy`, `POST /pause`, `POST /resume`, `POST /stop`, `GET /events`) in `services/trading-backend/src/api/bots.py`
- [X] T020 [US1] Implement active bot runtime worker with idempotent Pacifica execution queue in `services/trading-backend/src/workers/bot_runtime_worker.py`
- [X] T021 [US1] Build bot studio page and initial rules-builder UI in `apps/web/src/app/(app)/build/page.tsx` and `apps/web/src/components/builder/`
- [X] T021a [US1] Build SDK authoring entry, docs, and registration flow in `apps/web/src/app/(app)/sdk/page.tsx` and `apps/web/src/components/sdk/`
- [X] T022 [US1] Build owned bots list and bot detail/runtime pages in `apps/web/src/app/(app)/bots/page.tsx` and `apps/web/src/app/(app)/bots/[botId]/page.tsx`
- [X] T023 [US1] Build runtime controls and execution-log surfaces in `apps/web/src/components/bots/runtime-controls.tsx` and `apps/web/src/components/bots/execution-log.tsx`
- [X] T024 [US1] Add validation/simulation UX before deploy in `apps/web/src/components/builder/bot-validation-panel.tsx`
- [X] T024a [US1] Add SDK bundle validation and normalization service in `services/trading-backend/src/services/sdk_registry_service.py`

**Checkpoint**: US1 is independently functional and demoable.

---

## Phase 4: User Story 2 - Discover and Copy Winning Bots (Priority: P2)

**Goal**: Users can discover top bots and either mirror them live or clone them into editable drafts.

**Independent Validation**: Open leaderboard, inspect a bot, then complete both mirror and clone flows with proper confirmation and resulting state changes.

### Implementation for User Story 2

- [X] T025 [P] [US2] Implement bot leaderboard engine for ranking active runtimes in `services/trading-backend/src/services/bot_leaderboard_engine.py`
- [X] T026 [US2] Implement mirror and clone copy engine in `services/trading-backend/src/services/bot_copy_engine.py`
- [X] T027 [US2] Implement copy preview, mirror activation, clone creation, update, and stop APIs in `services/trading-backend/src/api/bot_copy.py`
- [X] T028 [US2] Implement follower execution worker for mirrored bot actions in `services/trading-backend/src/workers/bot_copy_worker.py`
- [X] T029 [US2] Build public bot leaderboard and bot profile screens in `apps/web/src/app/(app)/leaderboard/page.tsx` and `apps/web/src/app/(app)/leaderboard/[runtimeId]/page.tsx`
- [X] T030 [US2] Build mirror-preview confirmation modal with risk acknowledgement in `apps/web/src/components/copy/bot-mirror-modal.tsx`
- [X] T031 [US2] Build clone-flow summary and draft creation UX in `apps/web/src/components/copy/bot-clone-modal.tsx`
- [X] T032 [US2] Build copy management page for mirrored and cloned bots in `apps/web/src/app/(app)/copy/page.tsx`
- [X] T033 [US2] Update leaderboard CTA components to support mirror and clone actions in `apps/web/src/components/leaderboard/trader-card.tsx` or replacement bot card component

**Checkpoint**: US2 is independently functional with explicit confirmation and both copy paths represented.

---

## Phase 5: User Story 3 - Monitor Runtime, Risk, and Advanced Execution (Priority: P3)

**Goal**: Bot operators can inspect health, risk, and advanced execution details and tune behavior safely.

**Independent Validation**: Open a deployed bot, review logs and health, update runtime controls, and observe new runtime behavior.

### Implementation for User Story 3

- [X] T034 [P] [US3] Implement runtime health/heartbeat tracking in `services/trading-backend/src/services/runtime_health_service.py`
- [X] T035 [US3] Implement runtime metrics and failure reason aggregation in `services/trading-backend/src/services/runtime_observability_service.py`
- [X] T036 [US3] Implement runtime detail endpoints for health, metrics, and risk state in `services/trading-backend/src/api/bots.py`
- [X] T037 [US3] Build advanced execution settings UI (leverage, TP/SL, cooldowns, market scope, sizing mode) in `apps/web/src/components/bots/advanced-settings-panel.tsx`
- [X] T038 [US3] Build runtime health and metrics cards in `apps/web/src/components/bots/runtime-health-card.tsx`
- [X] T039 [US3] Build failure review and recovery UI in `apps/web/src/components/bots/runtime-failure-panel.tsx`

**Checkpoint**: US3 is independently functional and gives operators trust and control.

---

## Phase 6: Migration and Cleanup

**Purpose**: Remove or adapt leftover manual-trading and trader-first assumptions.

- [X] T040 Replace remaining `trader` terminology in backend/frontend DTOs and copy where product-visible in `apps/web/src/**` and `services/trading-backend/src/**`
- [X] T041 Remove or archive manual trading components in `apps/web/src/components/trading/` if no longer needed by runtime-facing UX
- [X] T042 Replace league-specific participation semantics with bot registration semantics where appropriate in `services/trading-backend/src/api/leagues.py`, `services/trading-backend/src/services/league_service.py`, and frontend league screens
- [X] T043 Update operator tooling to publish bot competitions rather than trader competitions in `apps/web/src/app/(app)/operator/` and related backend admin APIs

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Hardening, docs, and demo readiness.

- [ ] T044 [P] Document bot API contracts and realtime payloads in `specs/001-clashx-social-trading/contracts/openapi.yaml` and `specs/001-clashx-social-trading/contracts/events.md`
- [ ] T045 Add metrics for rule evaluation, queue lag, Pacifica ack latency, and leaderboard delay in `services/trading-backend/src/observability/metrics.py`
- [ ] T046 Implement reconciliation worker for runtime state vs Pacifica state in `services/trading-backend/src/workers/bot_reconcile_worker.py`
- [ ] T047 [P] Add builder and runtime quickstart documentation in `specs/001-clashx-social-trading/quickstart.md`
- [ ] T048 [P] Prepare demo script for authorize → build → deploy → leaderboard → mirror/clone in `specs/001-clashx-social-trading/demo-script.md`
- [ ] T049 Create submission and launch checklist in `specs/001-clashx-social-trading/submission-checklist.md`

---

## Phase 8: Stress Lab + Explainability

**Purpose**: Turn ClashX into a serious strategy research terminal with clearer reasoning behind every trade.

- [x] T050 [P] Extend backtest assumptions for fees, funding, slippage, and scenario toggles in `services/trading-backend/src/services/bot_backtest_service.py` and `services/trading-backend/src/api/backtests.py`
- [x] T051 [P] Add market-regime slicing and compare-run summary generation in `services/trading-backend/src/services/bot_backtest_service.py` and `apps/web/src/lib/backtests.ts`
- [x] T052 Implement parameter sweep and variant testing services plus persisted run groups in `services/trading-backend/src/services/bot_backtest_service.py` and `services/trading-backend/src/models/`
- [x] T053 Implement backtest optimization and compare APIs in `services/trading-backend/src/api/backtests.py`
- [x] T054 Implement runtime/backtest explainability service for condition traces, trigger reasons, and action rationale in `services/trading-backend/src/services/runtime_explainability_service.py`
- [x] T055 Expose explainability payloads for live events and backtest trades in `services/trading-backend/src/api/bots.py` and `services/trading-backend/src/api/backtests.py`
- [x] T056 Build Stress Lab controls for assumptions, regime filters, and compare views in `apps/web/src/components/backtests/backtesting-lab-page.tsx` and `apps/web/src/components/backtests/backtest-chart.tsx`
- [x] T057 Build a "Why this trade happened" timeline for runtime and replayed events in `apps/web/src/components/bots/execution-log.tsx` and `apps/web/src/components/backtests/backtesting-lab-page.tsx`

**Checkpoint**: A judge can inspect why a bot acted, pressure-test assumptions, and compare variants without leaving the product.

---

## Phase 9: Strategy Passport + Trust Layer

**Purpose**: Make every public bot feel verifiable, investable, and easier to compare.

- [ ] T058 [P] Implement trust metrics service for uptime, failure rate, drift, and risk grading in `services/trading-backend/src/services/bot_trust_service.py`
- [ ] T059 [P] Add strategy version history and publish snapshots in `services/trading-backend/src/models/` and `services/trading-backend/src/services/bot_builder_service.py`
- [ ] T060 Implement creator profile aggregation and reputation summaries in `services/trading-backend/src/services/bot_trust_service.py` and `services/trading-backend/src/services/bot_copy_engine.py`
- [ ] T061 Expand leaderboard and public bot profile APIs with passport, drift, and creator metadata in `services/trading-backend/src/api/bot_copy.py`
- [ ] T062 Build public strategy passport sections, trust badges, and drift visuals in `apps/web/src/app/(app)/leaderboard/page.tsx`, `apps/web/src/app/(app)/leaderboard/[runtimeId]/page.tsx`, and `apps/web/src/components/leaderboard/`
- [ ] T063 Build creator profile surfaces and public reputation modules in `apps/web/src/components/leaderboard/` and related public app routes

**Checkpoint**: Every public bot profile clearly communicates risk, trust, history, and live-vs-backtest behavior.

---

## Phase 10: Portfolio Allocator / Bot Baskets

**Purpose**: Expand ClashX from one-bot copying into multi-bot allocation and portfolio automation.

- [ ] T064 [P] Define portfolio basket, allocation member, and portfolio risk policy models in `services/trading-backend/src/models/`
- [ ] T065 Implement portfolio allocator service for weights, caps, and bot-basket lifecycle in `services/trading-backend/src/services/portfolio_allocator_service.py`
- [ ] T066 Implement portfolio-level drawdown controls, rebalance logic, and kill switch handling in `services/trading-backend/src/services/portfolio_risk_service.py`
- [ ] T067 Implement portfolio allocation and basket management APIs in `services/trading-backend/src/api/`
- [ ] T068 Implement portfolio monitoring/rebalancing worker in `services/trading-backend/src/workers/portfolio_allocator_worker.py`
- [ ] T069 Build bot-basket creation, allocation controls, and portfolio kill switch UI in `apps/web/src/app/(app)/copy/page.tsx` and new portfolio allocation surfaces in `apps/web/src/components/copy/`
- [ ] T070 Build portfolio health, rebalance history, and allocation insights panels in `apps/web/src/components/copy/` and related operating views

**Checkpoint**: Users can allocate capital across multiple bots and manage risk at the portfolio level instead of one mirror at a time.

---

## Phase 11: AI Copilot Expansion

**Purpose**: Use AI to critique, explain, and improve strategies based on real performance and runtime signals.

- [ ] T071 [P] Expand builder AI support for bot critique, safer parameter suggestions, and setup guidance in `services/trading-backend/src/services/builder_ai_service.py`
- [ ] T072 [P] Implement AI summaries for backtests, runtime failures, and performance drift in `services/trading-backend/src/services/ai_copilot_service.py`
- [ ] T073 Implement copilot APIs for critique, explanation, optimization, and summaries in `services/trading-backend/src/api/builder.py`, `services/trading-backend/src/api/backtests.py`, and related AI endpoints
- [ ] T074 Build copilot UX in builder, backtests, and bot detail pages in `apps/web/src/components/builder/`, `apps/web/src/components/backtests/`, and `apps/web/src/components/bots/`
- [ ] T075 Connect copilot recommendations to trust, drift, and allocation signals so suggestions stay grounded in real bot behavior in `services/trading-backend/src/services/`

**Checkpoint**: AI becomes a product copilot for understanding and improving bots, not just a draft generator.

---

## Phase 12: Creator Marketplace Layer

**Purpose**: Turn ClashX into a creator-driven bot marketplace with stronger publishing and discovery loops.

- [ ] T076 [P] Define creator profile, publishing, featured bot, and invite-access models in `services/trading-backend/src/models/`
- [ ] T077 Implement creator marketplace service for discoverability, featured collections, copy stats, and publishing controls in `services/trading-backend/src/services/creator_marketplace_service.py`
- [ ] T078 Implement creator, featured, and publishing APIs in `services/trading-backend/src/api/`
- [ ] T079 Build creator pages, featured shelves, and public discovery modules in `apps/web/src/app/(app)/leaderboard/page.tsx`, new creator routes, and `apps/web/src/components/leaderboard/`
- [ ] T080 Build publishing controls for public, private, unlisted, and invite-only bot access in `apps/web/src/components/builder/` and `apps/web/src/components/bots/`
- [ ] T081 Build creator-facing stats surfaces for followers, copies, and marketplace reach in `apps/web/src/components/leaderboard/` and related creator pages

**Checkpoint**: ClashX supports a real creator and discovery loop around high-quality public bots.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: already reusable
- **Phase 2**: blocks all user stories
- **Phase 3 (US1)**: depends on Phase 2
- **Phase 4 (US2)**: depends on Phases 2-3 and leaderboard availability
- **Phase 5 (US3)**: depends on live runtimes from Phase 3
- **Phase 6**: can begin after Phase 3 and continue in parallel
- **Phase 7**: after target stories are stable
- **Phase 8**: depends on Phases 3 and 5, and benefits from Phase 7 hardening
- **Phase 9**: depends on Phases 4, 5, and 8 for trustworthy public metrics
- **Phase 10**: depends on Phases 4-5 and should consume trust signals from Phase 9 where possible
- **Phase 11**: depends on Phases 8-10 so AI recommendations are grounded in real strategy and portfolio data
- **Phase 12**: depends on Phases 9-11 for creator trust, richer discovery, and stronger product differentiation

### User Story Dependency Graph

- **US1 (P1)** → bot creation and deployment
- **US2 (P2)** → depends on deployed/ranked bots from US1
- **US3 (P3)** → depends on active runtime data from US1
- **Stress Lab + Explainability** → depends on runtime and backtest data from US1/US3
- **Strategy Passport + Trust Layer** → depends on public bot data from US2 and explainability/research data from Phase 8
- **Portfolio Allocator / Bot Baskets** → depends on copy/runtime foundations from US2/US3
- **AI Copilot Expansion** → depends on research, trust, and allocator signals
- **Creator Marketplace Layer** → depends on trust and public profile systems

Suggested order: **US1 → US2 → US3 → Stress Lab + Explainability → Strategy Passport + Trust Layer → Portfolio Allocator / Bot Baskets → AI Copilot Expansion → Creator Marketplace Layer**, with cleanup tasks running alongside.

### Parallel Opportunities

- Phase 2: T010, T011, T011a, T013 can run in parallel after T009
- US1: T016 and T018 can run in parallel; frontend T021/T021a/T024 can start once API shapes stabilize
- US2: T025 and T029 can run in parallel; T030/T031 can proceed after preview contract agreement
- US3: T034 and T037 can run in parallel after runtime detail endpoints are defined
- Polish: T044, T045, T047, T048 can run in parallel
- Stress Lab: T050/T051/T054 can run in parallel before frontend integration
- Trust Layer: T058/T059/T060 can run in parallel before public UI wiring
- Portfolio Allocator: T064/T065/T066 can run in parallel before basket UI
- AI Copilot: T071/T072 can run in parallel after Phase 8 and 9 contracts stabilize
- Marketplace: T076/T077 can run in parallel before creator-facing pages

---

## Implementation Strategy

### MVP First

1. Keep bot domain, runtime, leaderboard, and copy foundations stable
2. Prioritize Stress Lab + Explainability to strengthen technical credibility
3. Ship Strategy Passport + Trust Layer so public bots feel trustworthy
4. Expand into Portfolio Allocator / Bot Baskets for platform-scale scope

### Incremental Delivery

1. Stress Lab + Explainability
2. Strategy Passport + Trust Layer
3. Portfolio Allocator / Bot Baskets
4. AI Copilot Expansion
5. Creator Marketplace Layer

### Notes

- Manual trading is not the target experience anymore.
- SDK-specific expansion is not part of the current upgrade roadmap and should remain deferred unless reprioritized later.
- If scope pressure appears, prioritize **Phase 8**, then **Phase 9**, then **Phase 10** before taking on AI and marketplace work.
