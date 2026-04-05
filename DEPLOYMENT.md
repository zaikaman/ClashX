# Deployment

This repo is split into:

- `apps/web`: Next.js frontend for Vercel
- `services/trading-backend`: FastAPI backend for Heroku

## Frontend on Vercel

Create a Vercel project from this repository and set the project root directory to `apps/web`.

Set these environment variables in Vercel for `Production`, `Preview`, and `Development` as needed:

- `NEXT_PUBLIC_API_BASE_URL=https://<your-heroku-app>.herokuapp.com`
- `NEXT_PUBLIC_PRIVY_APP_ID=<your-privy-app-id>`
- `NEXT_PUBLIC_SUPABASE_URL=<your-supabase-url>`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-supabase-anon-key>`
- `NEXT_PUBLIC_SOLANA_RPC_URL=<optional-solana-rpc-url>`

Notes:

- The app no longer requires a checked-in root `.env` to build.
- The frontend reads `NEXT_PUBLIC_PRIVY_APP_ID` first. `PRIVY_APP_ID` is still accepted as a fallback for local compatibility.

## Backend on Heroku

This repo includes Heroku root files:

- `Procfile`
- `requirements.txt`
- `.python-version`

Create a Heroku app from the repository root and use the Python buildpack.

Set these config vars at minimum:

- `APP_ENV=production`
- `SUPABASE_URL=<your-supabase-url>`
- `SUPABASE_SERVICE_ROLE_KEY=<your-supabase-service-role-key>`
- `SUPABASE_ANON_KEY=<your-supabase-anon-key>`
- `PRIVY_APP_ID=<your-privy-app-id>`
- `PRIVY_VERIFICATION_KEY=<your-privy-verification-key>`
- `CORS_ALLOWED_ORIGINS=https://<your-vercel-project>.vercel.app,https://<your-custom-domain>`

Set additional existing app vars as required by your Pacifica and AI integrations:

- `PACIFICA_AGENT_ENCRYPTION_KEY`
- `PACIFICA_ACCOUNT_ADDRESS`
- `PACIFICA_PRIVATE_KEY`
- `PACIFICA_API_KEY`
- `PACIFICA_API_SECRET`
- `PACIFICA_AGENT_WALLET_PUBLIC_KEY`
- `PACIFICA_AGENT_PRIVATE_KEY`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `GEMINI_API_KEY`
- `GEMINI_BASE_URL`
- `GEMINI_MODEL`

Scale dynos after the first deploy:

```bash
heroku ps:scale web=1 worker=1 --app <your-heroku-app>
```

The `web` dyno runs the API with background workers disabled. The `worker` dyno runs only the long-lived background loops.

## Schema bootstrap

Before using production traffic, apply the required Supabase SQL from:

- `services/trading-backend/db/supabase_bot_tables.sql`

Apply any additive repair scripts from:

- `services/trading-backend/db/migrations/versions`

## Local development

The frontend wrapper script will load the workspace root `.env` if it exists. The backend already auto-loads the same root `.env`.
