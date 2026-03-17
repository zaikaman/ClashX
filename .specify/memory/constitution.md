<!--
Sync Impact Report
- Version change: N/A → 1.0.0
- Modified principles:
  - [PRINCIPLE_1_NAME] → I. Code Quality First
  - [PRINCIPLE_2_NAME] → II. UX Consistency by Default
  - [PRINCIPLE_3_NAME] → III. Performance Budgets Are Mandatory
  - [PRINCIPLE_4_NAME] → IV. Simplicity and Maintainability
  - [PRINCIPLE_5_NAME] → V. Documentation and Decision Traceability
- Added sections:
  - Engineering Constraints
  - Delivery Workflow
- Removed sections:
  - None
- Templates requiring updates:
  - ✅ updated: .specify/templates/plan-template.md
  - ✅ updated: .specify/templates/spec-template.md
  - ✅ updated: .specify/templates/tasks-template.md
  - ⚠ pending: .specify/templates/commands/*.md (directory not present)
- Deferred follow-ups:
  - None
-->

# ClashX Constitution

## Core Principles

### I. Code Quality First
All production code MUST be readable, consistently formatted, and maintainable.
Changes MUST pass static analysis and linting configured for the repository.
Public interfaces MUST be explicit and stable within a feature scope, and complex
logic MUST be decomposed into small, named units with clear responsibilities.
Rationale: code quality is the primary control for long-term delivery speed.

### II. UX Consistency by Default
User-facing behavior MUST follow established interaction patterns, naming, and
visual conventions used in the product. New UI elements MUST reuse existing
design primitives before introducing variants. Error states and loading states
MUST be predictable and consistent across flows.
Rationale: consistent UX reduces user friction and support burden.

### III. Performance Budgets Are Mandatory
Every feature MUST define measurable performance budgets in its plan (latency,
throughput, memory, render time, or startup time as applicable). Implementations
MUST avoid regressions against existing baselines and MUST document trade-offs
when budget exceptions are approved.
Rationale: performance is a product requirement, not a post-release task.

### IV. Simplicity and Maintainability
Designs MUST prefer the simplest solution that satisfies current requirements.
Premature abstraction, speculative extensibility, and unnecessary dependencies
MUST be avoided. Refactors that reduce cognitive load and duplication SHOULD be
included when they are low risk and bounded.
Rationale: simplicity improves reliability, onboarding, and change safety.

### V. Documentation and Decision Traceability
Feature specs, plans, and tasks MUST record key implementation decisions,
constraints, and performance/UX implications. Any material deviation from the
constitution MUST include explicit rationale and approval context in writing.
Rationale: traceability enables faster reviews and accountable evolution.

## Engineering Constraints

- Feature specifications MUST include explicit quality, UX consistency, and
  performance requirements.
- Testing tasks are OPTIONAL unless explicitly requested by the feature scope,
  contract, or compliance requirements.
- Work items MUST include concrete file paths and avoid ambiguous ownership.
- Any approved exception to a principle MUST be time-bound and tracked.

## Delivery Workflow

1. Specification MUST define user scenarios, measurable outcomes, and applicable
   performance constraints.
2. Planning MUST include constitution gates for code quality, UX consistency,
   and performance budgets before implementation begins.
3. Task generation MUST organize work by user story and include quality,
   consistency, and performance validation activities.
4. Review and merge MUST confirm constitution compliance and document approved
   exceptions.

## Governance

This constitution supersedes conflicting local practices for specification,
planning, and task generation. Amendments require: (1) a documented proposal,
(2) explicit impact assessment on templates and active workflows, and (3) team
approval recorded in repository history.

Versioning policy follows semantic versioning:
- MAJOR: incompatible governance change or principle removal/redefinition.
- MINOR: new principle/section or materially expanded guidance.
- PATCH: wording clarifications and non-semantic refinements.

Compliance review expectations:
- Every plan MUST pass a constitution check before implementation.
- Every pull request SHOULD reference applicable principle compliance.
- Exceptions MUST be documented with owner, scope, and expiration/review date.

**Version**: 1.0.0 | **Ratified**: 2026-03-02 | **Last Amended**: 2026-03-02
