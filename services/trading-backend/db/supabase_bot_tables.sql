begin;

drop table if exists public.bot_leaderboard_snapshots cascade;
drop table if exists public.bot_clones cascade;
drop table if exists public.bot_copy_relationships cascade;
drop table if exists public.bot_execution_events cascade;
drop table if exists public.bot_trade_closures cascade;
drop table if exists public.bot_trade_lots cascade;
drop table if exists public.bot_trade_sync_state cascade;
drop table if exists public.bot_action_claims cascade;
drop table if exists public.worker_leases cascade;
drop table if exists public.bot_runtimes cascade;
drop table if exists public.bot_definitions cascade;

create table public.bot_definitions (
  id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  wallet_address varchar(128) not null,
  name varchar(120) not null,
  description text not null default '',
  visibility varchar(24) not null default 'private',
  market_scope varchar(120) not null default 'Pacifica perpetuals',
  strategy_type varchar(64) not null default 'rules',
  authoring_mode varchar(24) not null default 'visual',
  rules_version integer not null default 1,
  rules_json jsonb not null default '{}'::jsonb,
  sdk_bundle_ref varchar(255),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_bot_definitions_user_id on public.bot_definitions(user_id);
create index ix_bot_definitions_wallet_address on public.bot_definitions(wallet_address);
create index ix_bot_definitions_name on public.bot_definitions(name);
create index ix_bot_definitions_visibility on public.bot_definitions(visibility);

create table public.bot_runtimes (
  id uuid primary key,
  bot_definition_id uuid not null references public.bot_definitions(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  wallet_address varchar(128) not null,
  status varchar(24) not null default 'draft',
  mode varchar(24) not null default 'live',
  risk_policy_json jsonb not null default '{}'::jsonb,
  deployed_at timestamptz,
  stopped_at timestamptz,
  updated_at timestamptz not null default now()
);
create index ix_bot_runtimes_bot_definition_id on public.bot_runtimes(bot_definition_id);
create index ix_bot_runtimes_user_id on public.bot_runtimes(user_id);
create index ix_bot_runtimes_wallet_address on public.bot_runtimes(wallet_address);
create index ix_bot_runtimes_status on public.bot_runtimes(status);

create table public.bot_execution_events (
  id uuid primary key,
  runtime_id uuid not null references public.bot_runtimes(id) on delete cascade,
  event_type varchar(48) not null,
  decision_summary text not null default '',
  request_payload jsonb not null default '{}'::jsonb,
  result_payload jsonb not null default '{}'::jsonb,
  status varchar(24) not null default 'pending',
  error_reason text,
  created_at timestamptz not null default now()
);
create index ix_bot_execution_events_runtime_id on public.bot_execution_events(runtime_id);
create index ix_bot_execution_events_event_type on public.bot_execution_events(event_type);
create index ix_bot_execution_events_status on public.bot_execution_events(status);
create index ix_bot_execution_events_created_at on public.bot_execution_events(created_at);

create table public.bot_trade_lots (
  id uuid primary key,
  runtime_id uuid not null references public.bot_runtimes(id) on delete cascade,
  symbol varchar(32) not null,
  side varchar(16) not null,
  opened_at timestamptz not null,
  source varchar(24) not null default 'bot',
  source_event_id uuid,
  source_order_id varchar(64),
  source_history_id bigint,
  entry_price double precision not null default 0,
  quantity_opened double precision not null default 0,
  quantity_remaining double precision not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_bot_trade_lots_runtime_id on public.bot_trade_lots(runtime_id);
create index ix_bot_trade_lots_symbol on public.bot_trade_lots(symbol);
create index ix_bot_trade_lots_opened_at on public.bot_trade_lots(opened_at);

create table public.bot_trade_closures (
  id uuid primary key,
  runtime_id uuid not null references public.bot_runtimes(id) on delete cascade,
  lot_id uuid not null references public.bot_trade_lots(id) on delete cascade,
  symbol varchar(32) not null,
  side varchar(16) not null,
  closed_at timestamptz not null,
  source varchar(24) not null,
  source_event_id uuid,
  source_order_id varchar(64),
  source_history_id bigint,
  quantity_closed double precision not null default 0,
  entry_price double precision not null default 0,
  exit_price double precision not null default 0,
  realized_pnl double precision not null default 0,
  created_at timestamptz not null default now()
);
create index ix_bot_trade_closures_runtime_id on public.bot_trade_closures(runtime_id);
create index ix_bot_trade_closures_lot_id on public.bot_trade_closures(lot_id);
create index ix_bot_trade_closures_closed_at on public.bot_trade_closures(closed_at);

create table public.bot_trade_sync_state (
  runtime_id uuid primary key references public.bot_runtimes(id) on delete cascade,
  synced_at timestamptz not null default now(),
  execution_events_count integer not null default 0,
  position_history_count integer not null default 0,
  last_execution_at timestamptz,
  last_history_at timestamptz,
  last_error text
);

create table public.bot_action_claims (
  id uuid primary key,
  runtime_id uuid not null references public.bot_runtimes(id) on delete cascade,
  idempotency_key varchar(255) not null,
  claimed_by varchar(128) not null,
  created_at timestamptz not null default now(),
  unique (runtime_id, idempotency_key)
);
create index ix_bot_action_claims_runtime_id on public.bot_action_claims(runtime_id);
create index ix_bot_action_claims_created_at on public.bot_action_claims(created_at);

create table public.worker_leases (
  lease_key varchar(255) primary key,
  owner_id varchar(128) not null,
  expires_at timestamptz not null,
  updated_at timestamptz not null default now()
);
create index ix_worker_leases_expires_at on public.worker_leases(expires_at);

create table public.bot_copy_relationships (
  id uuid primary key,
  source_runtime_id uuid not null references public.bot_runtimes(id) on delete cascade,
  follower_user_id uuid not null references public.users(id) on delete cascade,
  follower_wallet_address varchar(128) not null,
  mode varchar(24) not null default 'mirror',
  scale_bps integer not null default 10000,
  status varchar(24) not null default 'active',
  risk_ack_version varchar(24) not null default 'v1',
  confirmed_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_bot_copy_relationships_source_runtime_id on public.bot_copy_relationships(source_runtime_id);
create index ix_bot_copy_relationships_follower_user_id on public.bot_copy_relationships(follower_user_id);
create index ix_bot_copy_relationships_follower_wallet_address on public.bot_copy_relationships(follower_wallet_address);
create index ix_bot_copy_relationships_status on public.bot_copy_relationships(status);

create table public.bot_clones (
  id uuid primary key,
  source_bot_definition_id uuid not null references public.bot_definitions(id) on delete cascade,
  new_bot_definition_id uuid not null references public.bot_definitions(id) on delete cascade,
  created_by_user_id uuid not null references public.users(id) on delete cascade,
  created_at timestamptz not null default now()
);
create index ix_bot_clones_source_bot_definition_id on public.bot_clones(source_bot_definition_id);
create index ix_bot_clones_new_bot_definition_id on public.bot_clones(new_bot_definition_id);
create index ix_bot_clones_created_by_user_id on public.bot_clones(created_by_user_id);

create table public.bot_leaderboard_snapshots (
  id uuid primary key,
  runtime_id uuid not null references public.bot_runtimes(id) on delete cascade,
  rank integer not null default 0,
  pnl_total double precision not null default 0,
  pnl_unrealized double precision not null default 0,
  win_streak integer not null default 0,
  drawdown double precision not null default 0,
  captured_at timestamptz not null default now()
);
create index ix_bot_leaderboard_snapshots_runtime_id on public.bot_leaderboard_snapshots(runtime_id);
create index ix_bot_leaderboard_snapshots_rank on public.bot_leaderboard_snapshots(rank);
create index ix_bot_leaderboard_snapshots_captured_at on public.bot_leaderboard_snapshots(captured_at);

commit;
