begin;

create table if not exists public.bot_backtest_runs (
  id uuid primary key,
  bot_definition_id uuid not null references public.bot_definitions(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  wallet_address varchar(128) not null,
  bot_name_snapshot varchar(120) not null,
  market_scope_snapshot varchar(120) not null default 'Pacifica perpetuals',
  strategy_type_snapshot varchar(64) not null default 'rules',
  rules_snapshot_json jsonb not null default '{}'::jsonb,
  interval varchar(8) not null,
  start_time bigint not null,
  end_time bigint not null,
  initial_capital_usd double precision not null default 0,
  execution_model varchar(64) not null default 'candle_close_v2',
  pnl_total double precision not null default 0,
  pnl_total_pct double precision not null default 0,
  max_drawdown_pct double precision not null default 0,
  win_rate double precision not null default 0,
  trade_count integer not null default 0,
  status varchar(24) not null default 'completed',
  assumption_config_json jsonb not null default '{}'::jsonb,
  failure_reason text,
  result_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  updated_at timestamptz not null default now()
);

alter table public.bot_backtest_runs add column if not exists bot_definition_id uuid references public.bot_definitions(id) on delete cascade;
alter table public.bot_backtest_runs add column if not exists user_id uuid references public.users(id) on delete cascade;
alter table public.bot_backtest_runs add column if not exists wallet_address varchar(128);
alter table public.bot_backtest_runs add column if not exists bot_name_snapshot varchar(120);
alter table public.bot_backtest_runs add column if not exists market_scope_snapshot varchar(120) not null default 'Pacifica perpetuals';
alter table public.bot_backtest_runs add column if not exists strategy_type_snapshot varchar(64) not null default 'rules';
alter table public.bot_backtest_runs add column if not exists rules_snapshot_json jsonb not null default '{}'::jsonb;
alter table public.bot_backtest_runs add column if not exists interval varchar(8);
alter table public.bot_backtest_runs add column if not exists start_time bigint;
alter table public.bot_backtest_runs add column if not exists end_time bigint;
alter table public.bot_backtest_runs add column if not exists initial_capital_usd double precision not null default 0;
alter table public.bot_backtest_runs add column if not exists execution_model varchar(64) not null default 'candle_close_v2';
alter table public.bot_backtest_runs add column if not exists pnl_total double precision not null default 0;
alter table public.bot_backtest_runs add column if not exists pnl_total_pct double precision not null default 0;
alter table public.bot_backtest_runs add column if not exists max_drawdown_pct double precision not null default 0;
alter table public.bot_backtest_runs add column if not exists win_rate double precision not null default 0;
alter table public.bot_backtest_runs add column if not exists trade_count integer not null default 0;
alter table public.bot_backtest_runs add column if not exists status varchar(24) not null default 'completed';
alter table public.bot_backtest_runs add column if not exists assumption_config_json jsonb not null default '{}'::jsonb;
alter table public.bot_backtest_runs add column if not exists failure_reason text;
alter table public.bot_backtest_runs add column if not exists result_json jsonb not null default '{}'::jsonb;
alter table public.bot_backtest_runs add column if not exists created_at timestamptz not null default now();
alter table public.bot_backtest_runs add column if not exists completed_at timestamptz;
alter table public.bot_backtest_runs add column if not exists updated_at timestamptz not null default now();

alter table public.bot_backtest_runs alter column execution_model set default 'candle_close_v2';
alter table public.bot_backtest_runs alter column rules_snapshot_json set default '{}'::jsonb;
alter table public.bot_backtest_runs alter column assumption_config_json set default '{}'::jsonb;
alter table public.bot_backtest_runs alter column result_json set default '{}'::jsonb;
alter table public.bot_backtest_runs alter column created_at set default now();
alter table public.bot_backtest_runs alter column updated_at set default now();

update public.bot_backtest_runs as runs
set
  market_scope_snapshot = defs.market_scope,
  strategy_type_snapshot = defs.strategy_type
from public.bot_definitions as defs
where defs.id = runs.bot_definition_id
  and (
    runs.market_scope_snapshot is null
    or runs.market_scope_snapshot = ''
    or runs.market_scope_snapshot = 'Pacifica perpetuals'
    or runs.strategy_type_snapshot is null
    or runs.strategy_type_snapshot = ''
    or runs.strategy_type_snapshot = 'rules'
  );

update public.bot_backtest_runs
set assumption_config_json = coalesce(result_json -> 'assumption_config', '{}'::jsonb)
where coalesce(jsonb_typeof(assumption_config_json), 'null') = 'null'
   or assumption_config_json = '{}'::jsonb;

update public.bot_backtest_runs
set failure_reason = coalesce(result_json #>> '{preflight_issues,0}', 'Backtest failed.')
where status = 'failed'
  and (failure_reason is null or btrim(failure_reason) = '');

create index if not exists ix_bot_backtest_runs_bot_definition_id on public.bot_backtest_runs(bot_definition_id);
create index if not exists ix_bot_backtest_runs_user_id on public.bot_backtest_runs(user_id);
create index if not exists ix_bot_backtest_runs_wallet_address on public.bot_backtest_runs(wallet_address);
create index if not exists ix_bot_backtest_runs_status on public.bot_backtest_runs(status);
create index if not exists ix_bot_backtest_runs_completed_at on public.bot_backtest_runs(completed_at desc);

commit;
