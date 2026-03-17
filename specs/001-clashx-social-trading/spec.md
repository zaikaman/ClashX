# Feature Specification: ClashX Bot Builder Platform

**Feature Branch**: `001-clashx-social-trading`  
**Created**: 2026-03-05  
**Updated**: 2026-03-12  
**Status**: Draft  
**Input**: User direction: "Rebuild ClashX into a platform where people build trading bots instead of trading themselves. Users should be able to copy trading bots that perform well on the leaderboard. Bots should trade on behalf of users' wallets. The product should likely include an engine or library for building bots."

## Product Direction

ClashX is no longer a manual social trading app. It is a Pacifica-powered bot platform where users:
- create bots instead of placing discretionary trades by hand,
- authorize delegated execution for their own wallets,
- publish bot performance to public leaderboards,
- copy top bots either by mirroring live actions or cloning a bot configuration.

### Confirmed Scope Decisions

- **Custody model**: delegated per-user wallet execution only for MVP.
- **Bot authoring model**: dual-path authoring. Non-advanced users use blocks/templates in a rules engine; advanced users can use an SDK/library to build more sophisticated bots.
- **Bot capability scope**: advanced execution is in scope, including entries, exits, leverage, TP/SL, cooldowns, sizing logic, and advanced Pacifica order controls.
- **Copy model**: support both live mirroring and editable bot cloning in the product direction; MVP may sequence one before the other if needed.
- **Manual trading**: out of scope for the product experience.

## User Scenarios *(mandatory)*

### User Story 1 - Build and Deploy a Bot on My Wallet (Priority: P1)

As a user, I can configure a trading bot either from reusable blocks/templates or through an SDK-backed authoring path and deploy it against my own wallet through delegated execution so I can automate trading without giving up custody.

**Why this priority**: This is the core product loop. Without bot creation and deployment, there is no platform.

**Independent Validation**: A user can authorize their wallet, create a bot from blocks/templates or an SDK-authored definition, deploy it, and observe the bot placing Pacifica actions through the delegated runtime.

**Acceptance Scenarios**:

1. **Given** a connected wallet and an active delegated runtime, **When** a user creates a bot through the visual builder or SDK path and deploys it, **Then** the bot is stored, activated, and eligible to trade on behalf of that user wallet.
2. **Given** an active bot with configured entry, exit, and risk rules, **When** its rule conditions are met, **Then** the system submits the corresponding Pacifica actions under that user's delegated wallet authority.
3. **Given** a deployed bot, **When** a user pauses, edits, or stops it, **Then** future bot actions respect the updated runtime state immediately.

---

### User Story 2 - Discover and Copy Winning Bots (Priority: P2)

As a user, I can browse public bot leaderboards and copy a high-performing bot either by mirroring it live or cloning its configuration so I can benefit from proven automation.

**Why this priority**: Public bot discovery and copying is the growth loop that turns strategy performance into distribution.

**Independent Validation**: A user can select a ranked bot, review risk warnings, choose mirror or clone, confirm the action, and see either live mirrored execution or a new editable bot instance created.

**Acceptance Scenarios**:

1. **Given** a public leaderboard of active bots, **When** a user selects a bot, **Then** the platform shows performance, runtime metadata, and copy options before confirmation.
2. **Given** a user chooses live mirroring, **When** the source bot executes a Pacifica action, **Then** the follower wallet mirrors that action according to the selected scale and risk limits.
3. **Given** a user chooses cloning, **When** the copy is confirmed, **Then** a new bot instance is created under the user's account with editable rules and disabled or draft deployment state until the user activates it.

---

### User Story 3 - Monitor Runtime, Risk, and Advanced Execution (Priority: P3)

As a bot operator, I can inspect runtime status, execution history, and advanced controls so I can trust, tune, and govern automated trading behavior.

**Why this priority**: Advanced automation without clear control and observability is unsafe and hard to adopt.

**Independent Validation**: A user can view bot runtime health, recent actions, order outcomes, risk limits, and advanced execution settings, then modify those settings and observe runtime behavior change accordingly.

**Acceptance Scenarios**:

1. **Given** an active bot runtime, **When** a user opens the bot detail view, **Then** the platform shows status, recent execution history, linked wallet, current risk settings, and latest Pacifica interaction state.
2. **Given** a bot with advanced execution enabled, **When** the user updates leverage, TP/SL, sizing, cooldowns, or execution modes, **Then** future actions use the updated controls.
3. **Given** the runtime encounters a failure, **When** the user reviews the bot log, **Then** the platform shows the failed action, reason, and next recommended operator action.

---

### Edge Cases

- A delegated wallet authorization expires or becomes invalid while bots are still active; all related bots must pause and surface a re-authorization requirement.
- A copied bot attempts an action that violates follower-specific limits; the action is skipped and logged without affecting the source bot.
- A cloned bot includes a strategy block not supported in the follower's market scope; the clone remains in draft with a validation error.
- A source bot being mirrored is paused, deleted, or loses eligibility; mirror followers receive clear status and no new actions are submitted.
- Pacifica latency or upstream failures delay order acknowledgments; the UI must distinguish pending, accepted, retried, and failed actions.
- A user edits a bot while an action is already queued; the system must guarantee deterministic behavior for in-flight versus future actions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow users to create bot definitions tied to their account and wallet.
- **FR-002**: System MUST execute bot actions only through delegated per-user wallet authorization and MUST NOT require direct manual trading as a primary product flow.
- **FR-003**: System MUST provide a rules-engine-based bot builder for non-advanced users, including reusable conditions, actions, and parameter blocks.
- **FR-003a**: System MUST provide an SDK or library-based bot authoring path for advanced users that compiles or registers into the same runtime model as visually built bots.
- **FR-004**: System MUST allow bots to configure advanced Pacifica execution controls including leverage, sizing, TP/SL, cooldowns, and risk limits.
- **FR-005**: System MUST validate bot definitions before activation and block deployment of invalid configurations.
- **FR-006**: System MUST let users pause, resume, edit, clone, and stop their bot runtimes.
- **FR-007**: System MUST expose public bot leaderboards with performance and status fields sufficient for discovery and comparison.
- **FR-008**: System MUST allow users to copy a bot via live mirroring with explicit confirmation and risk acknowledgment.
- **FR-009**: System MUST allow users to copy a bot via configuration cloning into their own editable bot draft.
- **FR-010**: System MUST enforce follower-specific scaling, balance, and risk controls on mirrored execution.
- **FR-011**: System MUST maintain an auditable history of bot deployments, edits, runtime state changes, copy confirmations, and execution outcomes.
- **FR-012**: System MUST present clear pending, active, paused, failed, and stopped states for bot runtimes and copy relationships.
- **FR-013**: System MUST prevent duplicate bot actions caused by retries, reconnects, or repeated UI submissions.
- **FR-014**: System MUST support leaderboard updates frequently enough that users perceive bot competition as live.
- **FR-015**: System MUST provide users with runtime health and execution logs for every active or recently stopped bot.
- **FR-016**: System MUST separate source-bot ownership from copier-bot ownership so copied bots never share raw credentials or account custody.
- **FR-017**: System MUST support one-tap mobile and web flows for authorize runtime, deploy bot, mirror bot, and clone bot actions.

### Assumptions

- Users connect self-custodied wallets and authorize a delegated Pacifica runtime for their own account.
- Non-advanced users primarily create bots through the hosted rules engine.
- Advanced users can author bots through an SDK/library, but deployed bots still normalize into the platform's shared bot-definition schema and runtime controls.
- Pacifica remains the execution venue and source of trading truth.
- Bot strategies may be public in behavior and performance even if the internal rule graph is only partially exposed.
- Vaults and passive pooled products are deferred unless reintroduced in a later bot-native design.

### Key Entities *(include if feature involves data)*

- **Bot Definition**: A versioned bot configuration, whether visually composed or SDK-authored, describing conditions, actions, market scope, advanced execution settings, and risk controls.
- **Bot Runtime**: The active or inactive execution instance of a bot bound to a specific user wallet and delegated Pacifica authorization.
- **Bot Leaderboard Entry**: A public ranking view for a bot instance including performance, uptime, rank, and status.
- **Bot Execution Event**: A timestamped record of a bot decision, attempted action, Pacifica request, outcome, and any failure details.
- **Delegated Authorization**: The user-approved linkage that allows a bound Pacifica agent wallet to act on behalf of a specific user wallet.
- **Bot Copy Relationship**: A linkage between a source bot and a follower account for live mirrored execution with user-defined scaling and limits.
- **Bot Clone**: A newly created bot definition derived from an existing source bot, owned and editable by the destination user.
- **Risk Policy**: A set of user-level or bot-level controls such as max drawdown, market allowlist, leverage caps, cooldowns, and per-trade size limits.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 85% of users who begin bot setup complete delegated wallet authorization and bot deployment in under 5 minutes.
- **SC-002**: At least 95% of eligible bot actions are submitted to Pacifica within 5 seconds of their rule trigger being evaluated as true.
- **SC-003**: At least 90% of bot copy activations complete risk acknowledgment and confirmation on the first attempt.
- **SC-004**: At least 90% of users can pause or stop an active bot in under 10 seconds.
- **SC-005**: Bot leaderboard updates reflecting visible performance changes appear within 5 seconds for at least 95% of updates.
- **SC-006**: Within 90 days of launch, copied or cloned bots account for at least 30% of total active bot deployments.
- **SC-007**: Fewer than 3% of bot execution attempts fail due to platform-side duplication, invalid runtime state, or preventable validation errors.
