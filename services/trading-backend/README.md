# ClashX Trading Backend

Python 3.11 FastAPI service for Pacifica integrations, realtime fanout, and trading logic.

## Database setup

The backend now uses Alembic migrations.

### Shared env

The backend reads configuration from the root `.env` file.

### Apply schema

From the workspace root run:

- `npm run db:migrate`

This applies the initial schema to the Supabase Postgres database configured by `DATABASE_URL`.

### Bootstrap Supabase-only bot tables

If your Supabase project was initialized before the bot runtime features were added, apply:

- `services/trading-backend/db/supabase_initial_schema.sql`

This SQL file now includes the missing bot tables:

- `bot_definitions`
- `bot_runtimes`
- `bot_execution_events`
- `bot_copy_relationships`
- `bot_clones`
- `bot_leaderboard_snapshots`

### Start backend

After migrations:

- `npm run backend`
