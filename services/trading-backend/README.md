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
- `stream_events`

Those tables are required for duplicate-prevention, worker coordination, and cross-process realtime stream fanout.

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

Vercel uses `api/index.py` as the ASGI entrypoint and routes requests through the existing `src.main:app`. Set `BACKGROUND_WORKERS_ENABLED=false` in the Vercel project so only the HTTP API runs there.

If the Vercel build logs show `npm run build --prefix apps/web`, the project is still using the repo root settings. Set the Vercel project Root Directory to `services/trading-backend` and redeploy.

The backend Vercel config installs Python dependencies from `requirements.txt`. If the runtime logs show `ModuleNotFoundError: No module named 'fastapi'`, make sure the project is using the checked-in `services/trading-backend/vercel.json` and does not override the install command with `npm install` in the Vercel dashboard.

Keep the Heroku worker dyno running with `BACKGROUND_WORKERS_ENABLED=true`. After the Vercel backend is live, point the frontend `NEXT_PUBLIC_API_BASE_URL` at the Vercel backend URL.

Realtime stream endpoints use the Supabase-backed `stream_events` table for cross-process fanout, so apply the latest database migration before cutting traffic over to the Vercel API.

## Live Pacifica smoke

The backend test suite includes a live Pacifica smoke path that validates market entry, close, IOC limit submission, and cancel-on-live-testnet against the delegated account when `PACIFICA_SMOKE_ENABLED=1` is set.
