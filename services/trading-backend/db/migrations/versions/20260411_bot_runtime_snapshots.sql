begin;

create table if not exists public.bot_runtime_snapshots (
  runtime_id uuid not null,
  bot_definition_id uuid not null,
  user_id uuid,
  wallet_address character varying not null,
  status character varying not null default 'draft'::character varying,
  mode character varying not null default 'live'::character varying,
  health_json jsonb not null default '{}'::jsonb,
  metrics_json jsonb not null default '{}'::jsonb,
  performance_json jsonb not null default '{}'::jsonb,
  source_runtime_updated_at timestamp with time zone,
  last_computed_at timestamp with time zone not null default now(),
  constraint bot_runtime_snapshots_pkey primary key (runtime_id),
  constraint bot_runtime_snapshots_runtime_id_fkey foreign key (runtime_id) references public.bot_runtimes(id),
  constraint bot_runtime_snapshots_bot_definition_id_fkey foreign key (bot_definition_id) references public.bot_definitions(id),
  constraint bot_runtime_snapshots_user_id_fkey foreign key (user_id) references public.users(id)
);

create index if not exists ix_bot_runtime_snapshots_wallet_runtime
  on public.bot_runtime_snapshots(wallet_address, last_computed_at desc);

create index if not exists ix_bot_runtime_snapshots_bot_wallet
  on public.bot_runtime_snapshots(bot_definition_id, wallet_address, last_computed_at desc);

commit;
