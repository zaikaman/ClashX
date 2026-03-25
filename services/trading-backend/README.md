# ClashX Trading Backend

Python 3.11 FastAPI service for Pacifica integrations, realtime fanout, and Supabase-backed trading logic.

## Backend mode

The backend is now Supabase-only. There is no SQLAlchemy or Alembic path.

## Schema bootstrap

Apply the Supabase SQL in:

- `services/trading-backend/db/supabase_bot_tables.sql`

This includes the runtime tables plus:

- `bot_action_claims`
- `worker_leases`

Those tables are required for duplicate-prevention and worker coordination.

## Start backend

From the workspace root run:

- `npm run backend`

## Worker deployment

Background workers are controlled with `BACKGROUND_WORKERS_ENABLED`.

- Web dyno: set `BACKGROUND_WORKERS_ENABLED=false`
- Worker dyno: set `BACKGROUND_WORKERS_ENABLED=true`

If you run a single combined process, leave it enabled.

## Live Pacifica smoke

The backend test suite includes a live Pacifica smoke path that validates market entry, close, IOC limit submission, and cancel-on-live-testnet against the delegated account when `PACIFICA_SMOKE_ENABLED=1` is set.
