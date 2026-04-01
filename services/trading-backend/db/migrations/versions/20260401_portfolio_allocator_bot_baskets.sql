begin;

alter table public.bot_copy_relationships add column if not exists portfolio_basket_id uuid;
alter table public.bot_copy_relationships add column if not exists max_notional_usd double precision;

create index if not exists ix_bot_copy_relationships_portfolio_basket_id
  on public.bot_copy_relationships(portfolio_basket_id);

create table if not exists public.portfolio_baskets (
  id uuid primary key,
  owner_user_id uuid not null references public.users(id) on delete cascade,
  wallet_address varchar(128) not null,
  name varchar(120) not null,
  description text not null default '',
  status varchar(24) not null default 'draft',
  rebalance_mode varchar(24) not null default 'drift',
  rebalance_interval_minutes integer not null default 60,
  drift_threshold_pct double precision not null default 6,
  target_notional_usd double precision not null default 0,
  current_notional_usd double precision not null default 0,
  kill_switch_reason text,
  last_rebalanced_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.portfolio_baskets add column if not exists owner_user_id uuid references public.users(id) on delete cascade;
alter table public.portfolio_baskets add column if not exists wallet_address varchar(128);
alter table public.portfolio_baskets add column if not exists name varchar(120) not null default '';
alter table public.portfolio_baskets add column if not exists description text not null default '';
alter table public.portfolio_baskets add column if not exists status varchar(24) not null default 'draft';
alter table public.portfolio_baskets add column if not exists rebalance_mode varchar(24) not null default 'drift';
alter table public.portfolio_baskets add column if not exists rebalance_interval_minutes integer not null default 60;
alter table public.portfolio_baskets add column if not exists drift_threshold_pct double precision not null default 6;
alter table public.portfolio_baskets add column if not exists target_notional_usd double precision not null default 0;
alter table public.portfolio_baskets add column if not exists current_notional_usd double precision not null default 0;
alter table public.portfolio_baskets add column if not exists kill_switch_reason text;
alter table public.portfolio_baskets add column if not exists last_rebalanced_at timestamptz;
alter table public.portfolio_baskets add column if not exists created_at timestamptz not null default now();
alter table public.portfolio_baskets add column if not exists updated_at timestamptz not null default now();

create index if not exists ix_portfolio_baskets_wallet_address on public.portfolio_baskets(wallet_address);
create index if not exists ix_portfolio_baskets_owner_user_id on public.portfolio_baskets(owner_user_id);
create index if not exists ix_portfolio_baskets_status on public.portfolio_baskets(status);

create table if not exists public.portfolio_risk_policies (
  id uuid primary key,
  portfolio_basket_id uuid not null unique references public.portfolio_baskets(id) on delete cascade,
  max_drawdown_pct double precision not null default 18,
  max_member_drawdown_pct double precision not null default 22,
  min_trust_score integer not null default 55,
  max_active_members integer not null default 5,
  auto_pause_on_source_stale boolean not null default true,
  kill_switch_on_breach boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.portfolio_risk_policies add column if not exists portfolio_basket_id uuid references public.portfolio_baskets(id) on delete cascade;
alter table public.portfolio_risk_policies add column if not exists max_drawdown_pct double precision not null default 18;
alter table public.portfolio_risk_policies add column if not exists max_member_drawdown_pct double precision not null default 22;
alter table public.portfolio_risk_policies add column if not exists min_trust_score integer not null default 55;
alter table public.portfolio_risk_policies add column if not exists max_active_members integer not null default 5;
alter table public.portfolio_risk_policies add column if not exists auto_pause_on_source_stale boolean not null default true;
alter table public.portfolio_risk_policies add column if not exists kill_switch_on_breach boolean not null default true;
alter table public.portfolio_risk_policies add column if not exists created_at timestamptz not null default now();
alter table public.portfolio_risk_policies add column if not exists updated_at timestamptz not null default now();

create table if not exists public.portfolio_allocation_members (
  id uuid primary key,
  portfolio_basket_id uuid not null references public.portfolio_baskets(id) on delete cascade,
  source_runtime_id uuid not null references public.bot_runtimes(id) on delete cascade,
  target_weight_pct double precision not null default 0,
  target_notional_usd double precision not null default 0,
  max_scale_bps integer not null default 20000,
  target_scale_bps integer not null default 10000,
  relationship_id uuid references public.bot_copy_relationships(id) on delete set null,
  status varchar(24) not null default 'active',
  latest_scale_bps integer,
  last_rebalanced_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.portfolio_allocation_members add column if not exists portfolio_basket_id uuid references public.portfolio_baskets(id) on delete cascade;
alter table public.portfolio_allocation_members add column if not exists source_runtime_id uuid references public.bot_runtimes(id) on delete cascade;
alter table public.portfolio_allocation_members add column if not exists target_weight_pct double precision not null default 0;
alter table public.portfolio_allocation_members add column if not exists target_notional_usd double precision not null default 0;
alter table public.portfolio_allocation_members add column if not exists max_scale_bps integer not null default 20000;
alter table public.portfolio_allocation_members add column if not exists target_scale_bps integer not null default 10000;
alter table public.portfolio_allocation_members add column if not exists relationship_id uuid references public.bot_copy_relationships(id) on delete set null;
alter table public.portfolio_allocation_members add column if not exists status varchar(24) not null default 'active';
alter table public.portfolio_allocation_members add column if not exists latest_scale_bps integer;
alter table public.portfolio_allocation_members add column if not exists last_rebalanced_at timestamptz;
alter table public.portfolio_allocation_members add column if not exists created_at timestamptz not null default now();
alter table public.portfolio_allocation_members add column if not exists updated_at timestamptz not null default now();

create index if not exists ix_portfolio_allocation_members_portfolio_basket_id on public.portfolio_allocation_members(portfolio_basket_id);
create index if not exists ix_portfolio_allocation_members_source_runtime_id on public.portfolio_allocation_members(source_runtime_id);
create unique index if not exists ix_portfolio_allocation_members_unique_runtime_per_basket
  on public.portfolio_allocation_members(portfolio_basket_id, source_runtime_id);

create table if not exists public.portfolio_rebalance_events (
  id uuid primary key,
  portfolio_basket_id uuid not null references public.portfolio_baskets(id) on delete cascade,
  trigger varchar(32) not null default 'manual',
  status varchar(24) not null default 'completed',
  summary_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.portfolio_rebalance_events add column if not exists portfolio_basket_id uuid references public.portfolio_baskets(id) on delete cascade;
alter table public.portfolio_rebalance_events add column if not exists trigger varchar(32) not null default 'manual';
alter table public.portfolio_rebalance_events add column if not exists status varchar(24) not null default 'completed';
alter table public.portfolio_rebalance_events add column if not exists summary_json jsonb not null default '{}'::jsonb;
alter table public.portfolio_rebalance_events add column if not exists created_at timestamptz not null default now();

create index if not exists ix_portfolio_rebalance_events_portfolio_basket_id
  on public.portfolio_rebalance_events(portfolio_basket_id);
create index if not exists ix_portfolio_rebalance_events_created_at
  on public.portfolio_rebalance_events(created_at desc);

commit;
