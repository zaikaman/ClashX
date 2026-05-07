# ClashX Trading Backend

Python 3.11 FastAPI service for Pacifica integrations, realtime fanout, and Supabase-backed trading logic.

## Backend mode

The backend is now Supabase-only. There is no SQLAlchemy or Alembic path.

## Schema bootstrap

Apply the Supabase SQL in:

- `services/trading-backend/db/supabase_bot_tables.sql`

For existing environments that already have the bot tables, apply any additive repair scripts in:

- `services/trading-backend/db/migrations/versions`

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

## Vercel web API deployment

The FastAPI web API can be deployed as a separate Vercel project rooted at:

- `services/trading-backend`

Vercel uses `api/index.py` as the ASGI entrypoint and routes all requests through the existing `src.main:app`. Set `BACKGROUND_WORKERS_ENABLED=false` in the Vercel project so only the HTTP API runs there.

Keep the Heroku worker dyno running with `BACKGROUND_WORKERS_ENABLED=true`. After the Vercel backend is live, point the frontend `NEXT_PUBLIC_API_BASE_URL` at the Vercel backend URL.

Realtime stream endpoints currently use in-process memory for fanout, so worker-published events will not cross from the Heroku worker process to Vercel function instances without replacing the broadcaster with shared pub/sub.

## Live Pacifica smoke

The backend test suite includes a live Pacifica smoke path that validates market entry, close, IOC limit submission, and cancel-on-live-testnet against the delegated account when `PACIFICA_SMOKE_ENABLED=1` is set.
