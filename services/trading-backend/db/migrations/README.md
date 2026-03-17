# Database Migrations

Migration scripts for ClashX trading backend live here.

## Current tool

This backend now uses Alembic.

## Apply migrations

From the repo root:

1. Install backend dependencies
2. Run `npm run db:migrate`

Or from `services/trading-backend/`:

1. `alembic upgrade head`

## Create a new migration

From `services/trading-backend/`:

1. `alembic revision --autogenerate -m "describe change"`

## Notes

- Alembic reads `DATABASE_URL` from the shared root `.env`
- `DATABASE_URL` should point at your Supabase Postgres instance
- The initial migration is in `db/migrations/versions/20260306_0001_initial_schema.py`
- Run migrations before starting the backend against Postgres
