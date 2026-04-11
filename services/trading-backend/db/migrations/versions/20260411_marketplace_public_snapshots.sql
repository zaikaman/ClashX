begin;

create table if not exists public.marketplace_creator_snapshots (
  creator_id uuid not null,
  display_name character varying not null default ''::character varying,
  marketplace_reach_score integer not null default 0,
  highlight_json jsonb not null default '{}'::jsonb,
  profile_json jsonb not null default '{}'::jsonb,
  last_computed_at timestamp with time zone not null default now(),
  constraint marketplace_creator_snapshots_pkey primary key (creator_id),
  constraint marketplace_creator_snapshots_creator_id_fkey foreign key (creator_id) references public.users(id)
);

create index if not exists ix_marketplace_creator_snapshots_reach
  on public.marketplace_creator_snapshots(marketplace_reach_score desc, display_name asc);

create table if not exists public.marketplace_runtime_snapshots (
  runtime_id uuid not null,
  bot_definition_id uuid not null,
  creator_id uuid not null,
  strategy_type character varying not null default ''::character varying,
  rank integer not null default 0,
  row_json jsonb not null default '{}'::jsonb,
  detail_json jsonb not null default '{}'::jsonb,
  captured_at timestamp with time zone,
  last_computed_at timestamp with time zone not null default now(),
  constraint marketplace_runtime_snapshots_pkey primary key (runtime_id),
  constraint marketplace_runtime_snapshots_runtime_id_fkey foreign key (runtime_id) references public.bot_runtimes(id),
  constraint marketplace_runtime_snapshots_bot_definition_id_fkey foreign key (bot_definition_id) references public.bot_definitions(id),
  constraint marketplace_runtime_snapshots_creator_id_fkey foreign key (creator_id) references public.users(id)
);

create index if not exists ix_marketplace_runtime_snapshots_rank
  on public.marketplace_runtime_snapshots(rank asc, captured_at desc);

create index if not exists ix_marketplace_runtime_snapshots_strategy_creator
  on public.marketplace_runtime_snapshots(strategy_type, creator_id, rank asc);

commit;
